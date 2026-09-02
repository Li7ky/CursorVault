# -*- coding: utf-8 -*-
"""后台工作线程：在线素材拉取 / 下载安装 / 更新检查 / 更新应用.

逻辑保持不变，仅从 main_window.py 抽出以便组件化。
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from ..theme_manager import ThemeManager
from ..zhutix_client import ZhutixClient, ZhutixPack
from ..updater import GitHubUpdater, ReleaseInfo


class FetchPacksThread(QThread):
    """后台线程：获取光标包列表（含预览 URL 解析）."""

    packs_ready = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(
        self,
        client: ZhutixClient,
        page: int = 1,
        per_page: int = 50,
        orderby: str = "date",
        order: str = "desc",
    ):
        super().__init__()
        self._client = client
        self._page = page
        self._per_page = per_page
        self._orderby = orderby
        self._order = order

    def run(self) -> None:
        try:
            # 性能优化：先快速返回列表（仅从 content 正则提取预览，不过多 media API），
            # 让卡片先显示；剩余未命中预览的由 UI 层懒加载，避免 24 个 media 请求同步阻塞 3-5s
            packs = self._client.fetch_page(
                self._page,
                self._per_page,
                orderby=self._orderby,
                order=self._order,
                resolve_previews=False,
            )
            self.progress.emit(self._page, self._client.total_pages or 1)
            self.packs_ready.emit(packs)
        except Exception as e:
            self.error.emit(str(e))


class DownloadPackThread(QThread):
    """后台线程：下载光标包并安装."""

    progress = pyqtSignal(int, int)
    finished_signal = pyqtSignal(bool, str, object)
    extract_signal = pyqtSignal(str)

    def __init__(
        self,
        client: ZhutixClient,
        pack: ZhutixPack,
        download_dir: Path,
        theme_manager: ThemeManager,
    ):
        super().__init__()
        self._client = client
        self._pack = pack
        self._download_dir = download_dir
        self._theme_manager = theme_manager
        self._abort = False

    def request_abort(self) -> None:
        self._abort = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            self.extract_signal.emit("正在获取下载链接…")
            url = self._client.resolve_download_url(self._pack)
            if not url:
                detail = getattr(self._client, "last_error", "") or (
                    "该素材需要 VIP 才能下载（无公开直链）"
                )
                self.finished_signal.emit(
                    False, f"NO_DIRECT_LINK::{detail}", self._pack
                )
                return

            self.extract_signal.emit("正在下载…")
            archive_path = self._client.download_pack(
                self._pack,
                self._download_dir,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                should_abort=lambda: self._abort or self.isInterruptionRequested(),
            )
            if self._abort or self.isInterruptionRequested():
                self.finished_signal.emit(False, "下载已取消", self._pack)
                return
            if not archive_path:
                detail = getattr(self._client, "last_error", "") or "下载失败"
                self.finished_signal.emit(False, f"下载失败：{detail}", self._pack)
                return

            size_kb = max(1, archive_path.stat().st_size // 1024)
            self.extract_signal.emit(
                f"正在解压并安装…（{archive_path.name} · {size_kb} KB）"
            )

            slug = (self._pack.slug or "").strip() or f"pack_{self._pack.post_id}"
            theme, err = self._theme_manager.install_from_archive(
                archive_path,
                slug=slug,
                display_name=self._pack.title or slug,
                source_url=self._pack.url,
            )
            if theme:
                self._save_preview_image(theme)
                count = len(theme.cursor_files)
                complete = (
                    "完整 15 类"
                    if theme.is_complete()
                    else f"{count}/15 类（可正常使用）"
                )
                self.finished_signal.emit(
                    True,
                    f"安装成功！已导入 {count} 个光标文件（{complete}）",
                    self._pack,
                )
            else:
                msg = err or "安装失败：未能从压缩包中识别游标文件"
                msg += f"\n\n文件：{archive_path.name}（{size_kb} KB）"
                self.finished_signal.emit(False, msg, self._pack)
        except Exception as e:
            tb = traceback.format_exc()
            try:
                log = self._download_dir / "last_install_error.txt"
                log.write_text(tb, encoding="utf-8")
            except OSError:
                pass
            self.finished_signal.emit(False, f"安装出错: {e}", self._pack)

    def _save_preview_image(self, theme) -> None:
        """安装成功后把在线预览图存为主题目录下的 preview.png（失败静默）."""
        try:
            if self._abort or self.isInterruptionRequested():
                return
            theme_dir = self._theme_manager.get_theme_dir(theme.name)
            if not theme_dir:
                return
            dest = theme_dir / "preview.png"
            if dest.exists():
                return
            pack = self._pack
            url = pack.preview_url or self._client.get_preview_url(pack)
            if not url:
                url = ZhutixClient._extract_preview_from_content(pack.content or "")
            if not url:
                return
            resp = self._client._session.get(
                url, headers=self._client.DOWNLOAD_HEADERS, timeout=15
            )
            if resp.ok and resp.content:
                dest.write_bytes(resp.content)
        except (requests.RequestException, OSError):
            pass


class CheckUpdateThread(QThread):
    """后台检查 GitHub 最新版本."""

    finished_ok = pyqtSignal(object, bool)
    failed = pyqtSignal(str, bool)

    def __init__(self, base_dir: Path, silent: bool = False, parent=None):
        super().__init__(parent)
        self._base_dir = base_dir
        self.silent = silent

    def run(self) -> None:
        try:
            updater = GitHubUpdater(self._base_dir)
            info = updater.check_latest()
            if info is None:
                self.failed.emit(updater.last_error or "检查更新失败", self.silent)
            else:
                self.finished_ok.emit(info, self.silent)
        except Exception as e:
            self.failed.emit(str(e), self.silent)


class ApplyUpdateThread(QThread):
    """后台下载并应用更新."""

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, base_dir: Path, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self._base_dir = base_dir
        self._release = release

    def run(self) -> None:
        try:
            updater = GitHubUpdater(self._base_dir)
            ok = updater.download_and_apply(
                self._release,
                progress_cb=lambda d, t: self.progress.emit(d, t),
            )
            if ok:
                self.finished_ok.emit(self._release)
            else:
                self.failed.emit(updater.last_error or "更新失败")
        except Exception as e:
            self.failed.emit(str(e))
