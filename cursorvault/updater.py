# -*- coding: utf-8 -*-
"""GitHub 云更新：检查 Releases 并下载安装。"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

import requests

from . import __version__

# GitHub 仓库
GITHUB_OWNER = "Li7ky"
GITHUB_REPO = "CursorVault"
API_LATEST = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# 更新时允许覆盖的相对路径前缀（保护用户数据）
ALLOWED_UPDATE_PREFIXES = (
    "cursorvault/",
    "assets/",
    "main.py",
    "run.py",
    "requirements.txt",
    "README.md",
    "LICENSE",
)

# 绝对不要覆盖
BLOCKED_PREFIXES = (
    "themes/",
    "backup/",
    ".git/",
    "updates/",
    "__pycache__/",
)


@dataclass
class ReleaseInfo:
    tag: str
    version: str
    name: str
    body: str
    zip_url: Optional[str]
    html_url: str


def normalize_version(text: str) -> str:
    """v1.0.0 / 1.0.0 -> 1.0.0"""
    text = (text or "").strip()
    text = re.sub(r"^[vV]", "", text)
    # 只保留数字和点
    m = re.match(r"(\d+(?:\.\d+)*)", text)
    return m.group(1) if m else text


def version_tuple(ver: str) -> tuple[int, ...]:
    parts = normalize_version(ver).split(".")
    out: list[int] = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out) if out else (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return version_tuple(remote) > version_tuple(local)


class GitHubUpdater:
    """从 GitHub Releases 检查并应用更新."""

    def __init__(self, base_dir: Path, timeout: int = 20):
        self.base_dir = Path(base_dir).resolve()
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": f"CursorVault/{__version__}",
                "Accept": "application/vnd.github+json",
            }
        )
        self.last_error = ""

    def check_latest(self) -> Optional[ReleaseInfo]:
        """查询最新 Release，失败返回 None 并设置 last_error."""
        self.last_error = ""
        info = self._check_via_api()
        if info is not None:
            return info
        # API 限流或失败时，用页面跳转兜底
        return self._check_via_redirect()

    def _check_via_api(self) -> Optional[ReleaseInfo]:
        try:
            resp = self._session.get(API_LATEST, timeout=self.timeout)
            if resp.status_code == 404:
                self.last_error = "仓库尚无正式发布版本"
                return None
            if resp.status_code == 403:
                self.last_error = "GitHub API 访问受限，尝试备用方式…"
                return None
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            self.last_error = f"连接 GitHub 失败：{e}"
            return None
        except json.JSONDecodeError:
            self.last_error = "GitHub 返回数据无效"
            return None

        tag = data.get("tag_name") or ""
        version = normalize_version(tag)
        assets = data.get("assets") or []
        zip_url = None
        for a in assets:
            name = (a.get("name") or "").lower()
            url = a.get("browser_download_url")
            if not url:
                continue
            if name.endswith(".zip") and "cursorvault" in name:
                zip_url = url
                break
        if not zip_url:
            for a in assets:
                name = (a.get("name") or "").lower()
                url = a.get("browser_download_url")
                if url and name.endswith(".zip"):
                    zip_url = url
                    break
        if not zip_url:
            zip_url = data.get("zipball_url")

        return ReleaseInfo(
            tag=tag,
            version=version,
            name=data.get("name") or tag,
            body=(data.get("body") or "").strip(),
            zip_url=zip_url,
            html_url=data.get("html_url") or RELEASES_PAGE,
        )

    def _check_via_redirect(self) -> Optional[ReleaseInfo]:
        """不走 API：跟随 /releases/latest 重定向解析版本号."""
        try:
            resp = self._session.get(
                f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest",
                timeout=self.timeout,
                allow_redirects=True,
            )
            final = str(resp.url or "")
            m = re.search(r"/releases/tag/([^/?#]+)", final)
            if not m:
                # 页面内再找
                m = re.search(r"/releases/tag/(v?[\d.]+)", resp.text or "")
            if not m:
                if not self.last_error:
                    self.last_error = "无法解析最新版本信息"
                return None
            tag = unquote(m.group(1))
            version = normalize_version(tag)
            # 兜底：优先按规范文件名 CursorVault-vX.Y.Z.zip 猜资源地址
            zip_url = (
                f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
                f"/releases/download/{tag}/CursorVault-v{version}.zip"
            )
            return ReleaseInfo(
                tag=tag,
                version=version,
                name=f"CursorVault {tag}",
                body="",
                zip_url=zip_url,
                html_url=final or RELEASES_PAGE,
            )
        except requests.RequestException as e:
            self.last_error = f"连接 GitHub 失败：{e}"
            return None


    def download_and_apply(
        self,
        release: ReleaseInfo,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """下载更新包并覆盖程序文件（保留 themes/ backup/）."""
        self.last_error = ""
        if not release.zip_url:
            self.last_error = "该版本没有可下载的更新包"
            return False

        updates_dir = self.base_dir / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        zip_path = updates_dir / f"CursorVault-{release.version}.zip"

        try:
            # 下载
            with self._session.get(
                release.zip_url, stream=True, timeout=120
            ) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0) or 0)
                done = 0
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        if progress_cb:
                            progress_cb(done, total)

            # 解压到临时目录
            with tempfile.TemporaryDirectory(prefix="cv_upd_") as tmp:
                tmp_path = Path(tmp)
                extract_root = tmp_path / "extract"
                extract_root.mkdir()
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_root)

                # GitHub zipball 会多一层目录；release asset 可能没有
                source_root = self._find_package_root(extract_root)
                if source_root is None:
                    self.last_error = "更新包结构无法识别"
                    return False

                self._copy_update_files(source_root)

            # 记录已安装版本标记
            stamp = updates_dir / "installed_version.txt"
            stamp.write_text(release.version, encoding="utf-8")
            return True
        except Exception as e:
            self.last_error = f"更新失败：{e}"
            return False

    def _find_package_root(self, extract_root: Path) -> Optional[Path]:
        """定位包含 cursorvault/ 或 main.py 的包根目录."""
        if (extract_root / "cursorvault").is_dir() or (extract_root / "main.py").is_file():
            return extract_root
        for child in extract_root.iterdir():
            if not child.is_dir():
                continue
            if (child / "cursorvault").is_dir() or (child / "main.py").is_file():
                return child
        # 再深一层
        for child in extract_root.rglob("cursorvault"):
            if child.is_dir():
                return child.parent
        return None

    def _is_allowed(self, rel: str) -> bool:
        rel = rel.replace("\\", "/")
        if rel.startswith("./"):
            rel = rel[2:]
        for b in BLOCKED_PREFIXES:
            if rel == b.rstrip("/") or rel.startswith(b):
                return False
        # pycache
        if "__pycache__" in rel.split("/"):
            return False
        if rel.endswith(".pyc"):
            return False
        for a in ALLOWED_UPDATE_PREFIXES:
            if rel == a.rstrip("/") or rel.startswith(a):
                return True
        # 允许更新包根目录下的 py 入口
        if "/" not in rel and rel.endswith(".py"):
            return True
        return False

    def _copy_update_files(self, source_root: Path) -> None:
        # 双层 root 校验：source_root 自身的路径 + 每次计算的目标路径。
        # _is_allowed 仅靠字符串前缀判断，可能被设计过的相对路径（如 a/b/../themes/x）
        # 绕过，所以必须配合 resolve() + is_relative_to() 做硬约束。
        try:
            base_resolved = self.base_dir.resolve()
        except OSError:
            base_resolved = self.base_dir
        try:
            source_resolved = source_root.resolve()
        except OSError:
            source_resolved = source_root

        for path in source_root.rglob("*"):
            if not path.is_file():
                continue
            # 文件必须真正在 source_root 下
            try:
                path.resolve().relative_to(source_resolved)
            except (ValueError, OSError):
                continue
            rel = path.relative_to(source_root).as_posix()
            if not self._is_allowed(rel):
                continue
            dest = (self.base_dir / rel).resolve()
            # 目标路径必须真正在 base_dir 下
            try:
                dest.relative_to(base_resolved)
            except ValueError:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

