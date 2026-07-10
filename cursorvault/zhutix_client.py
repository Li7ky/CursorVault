"""致美化 (zhutix.com) 鼠标指针素材客户端.

通过 WordPress REST API 获取鼠标指针素材列表，
支持分页浏览、预览图获取、下载链接提取。

API 文档:
    GET /wp-json/wp/v2/posts?per_page=100&page=1&tags=218
        &_fields=id,slug,title,link,featured_media,modified,content
    GET /wp-json/wp/v2/media/{id}  -> source_url
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests


BASE_URL = "https://zhutix.com"
API_BASE = f"{BASE_URL}/wp-json/wp/v2"
CURSORS_TAG_ID = 218  # 标签 "鼠标指针" 的 ID


@dataclass
class ZhutixPack:
    """致美化上的一个鼠标指针素材包."""

    post_id: int                 # WordPress 文章 ID
    slug: str                    # URL 标识 (如 black-glass-cus)
    title: str                   # 显示标题
    url: str                     # 详情页 URL
    preview_url: Optional[str] = None  # 预览图 URL
    download_url: Optional[str] = None  # .rar 下载链接
    modified: str = ""           # 更新时间
    content: str = ""            # 详情页 HTML (用于提取下载链接)


class ZhutixClient:
    """从致美化网站获取鼠标指针素材列表的客户端 (REST API)."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html;q=0.9",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    # 下载所需的 Referer
    DOWNLOAD_HEADERS = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://zhutix.com/",
    }

    def __init__(self, timeout: int = 20):
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        self.timeout = timeout
        self._total: Optional[int] = None       # 总数
        self._total_pages: Optional[int] = None  # 总页数
        self._media_cache: dict[int, str] = {}   # media_id -> preview_url

    # ── 列表获取 ──────────────────────────────────────────────

    @property
    def total(self) -> Optional[int]:
        return self._total

    @property
    def total_pages(self) -> Optional[int]:
        return self._total_pages

    def fetch_page(self, page: int = 1, per_page: int = 50) -> list[ZhutixPack]:
        """获取指定页的光标包列表 (通过 REST API).

        Args:
            page: 页码，从 1 开始
            per_page: 每页数量 (最大 100)

        Returns:
            光标包列表
        """
        params = {
            "per_page": per_page,
            "page": page,
            "tags": CURSORS_TAG_ID,
            "_fields": "id,slug,title,link,featured_media,modified,content",
        }

        try:
            resp = self._session.get(
                f"{API_BASE}/posts", params=params, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"获取致美化列表失败 (page={page}): {e}") from e

        # 从响应头获取分页信息
        if self._total is None:
            self._total = int(resp.headers.get("X-WP-Total", 0))
        if self._total_pages is None:
            self._total_pages = int(resp.headers.get("X-WP-TotalPages", 0))

        posts = resp.json()
        packs: list[ZhutixPack] = []
        for post in posts:
            title_html = post.get("title", {}).get("rendered", "")
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            content = post.get("content", {}).get("rendered", "")

            pack = ZhutixPack(
                post_id=post["id"],
                slug=post.get("slug", ""),
                title=title,
                url=post.get("link", ""),
                preview_url=None,  # 需要单独请求 media API
                modified=post.get("modified", ""),
                content=content,
            )
            # 尝试从 content 中提取下载链接
            pack.download_url = self._extract_download_url(content)
            # 尝试从 content 中提取预览图
            pack.preview_url = self._extract_preview_from_content(content)

            # 如果有 featured_media，记录以便后续批量获取
            fm_id = post.get("featured_media", 0)
            if fm_id:
                pack._featured_media_id = fm_id  # type: ignore

            packs.append(pack)

        return packs

    def fetch_all(self, per_page: int = 100, progress_cb=None) -> list[ZhutixPack]:
        """获取全部光标包.

        Args:
            per_page: 每页数量
            progress_cb: 回调函数 (current_page, total_pages)
        """
        # 先请求第一页获取总页数
        first = self.fetch_page(1, per_page)
        all_packs = list(first)

        if progress_cb:
            progress_cb(1, self._total_pages or 1)

        if self._total_pages:
            for page in range(2, self._total_pages + 1):
                try:
                    packs = self.fetch_page(page, per_page)
                    all_packs.extend(packs)
                except RuntimeError:
                    break
                if progress_cb:
                    progress_cb(page, self._total_pages)

        return all_packs

    # ── 预览图获取 ──────────────────────────────────────────────

    def get_preview_url(self, pack: ZhutixPack) -> Optional[str]:
        """获取光标包的预览图 URL.

        优先使用 content 中提取的，否则请求 media API。
        """
        if pack.preview_url:
            return pack.preview_url

        fm_id = getattr(pack, "_featured_media_id", 0)
        if not fm_id:
            return None

        if fm_id in self._media_cache:
            return self._media_cache[fm_id]

        try:
            resp = self._session.get(
                f"{API_BASE}/media/{fm_id}", timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                url = data.get("source_url")
                if url:
                    self._media_cache[fm_id] = url
                    pack.preview_url = url
                    return url
        except requests.RequestException:
            pass
        return None

    # ── 下载链接提取 ──────────────────────────────────────────────

    @staticmethod
    def _extract_download_url(html: str) -> Optional[str]:
        """从详情页 HTML 中提取 .rar 下载链接."""
        # 匹配 123.zhutix.com 或 vip2.zhutix.com 的下载链接
        pattern = r'(https?://(?:123|vip2)\.zhutix\.com/[^\s"\'<>]+\.(?:rar|zip|7z))'
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            # 优先返回 123.zhutix.com 的链接
            for url in matches:
                if "123.zhutix.com" in url:
                    return url
            return matches[0]
        return None

    @staticmethod
    def _extract_preview_from_content(html: str) -> Optional[str]:
        """从 content HTML 中提取第一张预览图."""
        # 匹配 dl.zhutix.net 的图片
        pattern = r'(https?://dl\.zhutix\.net/[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|webp))'
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            return matches[0]
        return None

    # ── 详情页 ──────────────────────────────────────────────

    def fetch_detail(self, slug: str) -> Optional[ZhutixPack]:
        """通过 slug 获取单个光标包的完整详情."""
        params = {"slug": slug, "_fields": "id,slug,title,link,featured_media,modified,content"}
        try:
            resp = self._session.get(
                f"{API_BASE}/posts", params=params, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException:
            return None

        posts = resp.json()
        if not posts:
            return None

        post = posts[0]
        title_html = post.get("title", {}).get("rendered", "")
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        content = post.get("content", {}).get("rendered", "")

        pack = ZhutixPack(
            post_id=post["id"],
            slug=post.get("slug", ""),
            title=title,
            url=post.get("link", ""),
            modified=post.get("modified", ""),
            content=content,
        )
        pack.download_url = self._extract_download_url(content)
        pack.preview_url = self._extract_preview_from_content(content)
        fm_id = post.get("featured_media", 0)
        if fm_id:
            pack._featured_media_id = fm_id  # type: ignore
        return pack

    # ── 下载 ──────────────────────────────────────────────

    def download_pack(
        self,
        pack: ZhutixPack,
        dest_dir: Path,
        progress_cb=None,
    ) -> Optional[Path]:
        """下载光标包到指定目录.

        Args:
            pack: 光标包信息
            dest_dir: 目标目录
            progress_cb: 回调 (downloaded_bytes, total_bytes)

        Returns:
            下载的文件路径，失败返回 None
        """
        if not pack.download_url:
            # 尝试重新获取详情
            detail = self.fetch_detail(pack.slug)
            if detail:
                pack.download_url = detail.download_url
            if not pack.download_url:
                return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        # 从 URL 提取文件名
        filename = pack.download_url.rsplit("/", 1)[-1]
        dest_path = dest_dir / filename

        try:
            resp = requests.get(
                pack.download_url,
                headers=self.DOWNLOAD_HEADERS,
                stream=True,
                timeout=60,
            )
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total)

            return dest_path
        except requests.RequestException:
            if dest_path.exists():
                dest_path.unlink()
            return None
