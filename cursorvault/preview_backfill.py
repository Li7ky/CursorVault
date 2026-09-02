# -*- coding: utf-8 -*-
"""为已安装主题回填在线预览图.

全部基于 QNetworkAccessManager 在主线程异步完成——不使用任何后台线程。
（requests + Python 线程在进程退出时会与解释器清理产生概率性 0xC0000409 竞态，
Qt 异步网络无此问题，在线素材面板即采用同机制。）

每个主题的回填链：文章详情 content 图 → featured media → og:image 兜底。
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, QUrl, QUrlQuery, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .zhutix_client import API_BASE, ZhutixClient

_OG_IMAGE_PATTERNS = [
    re.compile(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
        re.IGNORECASE,
    ),
]


def _slug_from_source(source_url: str) -> str:
    m = re.search(r"/ico/([^/?#]+)/?\s*$", source_url or "")
    return m.group(1) if m else ""


class PreviewBackfiller(QObject):
    """队列化的预览图回填器：逐主题串行请求，全部异步，可随时 abort."""

    preview_ready = pyqtSignal(str)  # theme_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        try:
            self._nam.setTransferTimeout(15000)
        except Exception:
            pass
        self._queue: list[tuple[str, Path, str]] = []
        self._busy = False
        self._theme_name = ""
        self._theme_dir: Optional[Path] = None
        self._source_url = ""
        self._reply: Optional[QNetworkReply] = None

    # ── 对外接口 ──
    def submit(self, jobs: list[tuple[str, Path, str]]) -> None:
        self._queue.extend(jobs)
        self._pump()

    def abort(self) -> None:
        """清空队列并放弃进行中的请求（连接自动清理，无线程需要等待）。"""
        self._queue.clear()
        self._busy = False
        self._theme_name = ""
        self._theme_dir = None
        self._source_url = ""
        if self._reply is not None:
            rep, self._reply = self._reply, None
            try:
                rep.finished.disconnect()
            except TypeError:
                pass
            rep.abort()
            rep.deleteLater()

    # ── 内部流程 ──
    def _get(self, url: QUrl, headers: dict, cb: Callable[[], None]) -> None:
        req = QNetworkRequest(url)
        for k, v in headers.items():
            req.setRawHeader(k.encode("utf-8"), v.encode("utf-8"))
        self._reply = self._nam.get(req)
        self._reply.finished.connect(cb)

    def _pump(self) -> None:
        if self._busy or not self._queue:
            return
        name, theme_dir, source_url = self._queue.pop(0)
        if (
            not theme_dir
            or not theme_dir.exists()
            or (theme_dir / "preview.png").exists()
        ):
            QTimer.singleShot(0, self._pump)
            return
        self._busy = True
        self._theme_name = name
        self._theme_dir = theme_dir
        self._source_url = source_url
        slug = _slug_from_source(source_url)
        if slug:
            q = QUrlQuery()
            q.addQueryItem("slug", slug)
            q.addQueryItem("_fields", "featured_media,content")
            url = QUrl(f"{API_BASE}/posts")
            url.setQuery(q)
            self._get(url, ZhutixClient.HEADERS, self._on_detail)
        else:
            self._fallback_page()

    def _take_reply(self) -> tuple[Optional[bytes], bool]:
        rep, self._reply = self._reply, None
        if rep is None:
            return None, False
        data = bytes(rep.readAll())
        ok = rep.error() == QNetworkReply.NetworkError.NoError and bool(data)
        rep.deleteLater()
        return (data if ok else None), ok

    def _on_detail(self) -> None:
        data, ok = self._take_reply()
        if ok and data:
            try:
                posts = json.loads(data.decode("utf-8", "replace"))
                if posts:
                    post = posts[0]
                    content = post.get("content", {}).get("rendered", "")
                    url = ZhutixClient._extract_preview_from_content(content)
                    if url:
                        self._download_image(url)
                        return
                    fm = post.get("featured_media", 0) or 0
                    if fm:
                        self._get(
                            QUrl(f"{API_BASE}/media/{fm}"),
                            ZhutixClient.HEADERS,
                            self._on_media,
                        )
                        return
            except (ValueError, AttributeError, KeyError):
                pass
        self._fallback_page()

    def _on_media(self) -> None:
        data, ok = self._take_reply()
        if ok and data:
            try:
                url = json.loads(data.decode("utf-8", "replace")).get("source_url")
                if url:
                    self._download_image(url)
                    return
            except (ValueError, AttributeError):
                pass
        self._fallback_page()

    def _fallback_page(self) -> None:
        if self._source_url:
            self._get(QUrl(self._source_url), ZhutixClient.HEADERS, self._on_page)
        else:
            self._finish()

    def _on_page(self) -> None:
        data, ok = self._take_reply()
        if ok and data:
            html = data.decode("utf-8", "replace")
            for pat in _OG_IMAGE_PATTERNS:
                m = pat.search(html)
                if m:
                    self._download_image(unescape(m.group(1)))
                    return
        self._finish()

    def _download_image(self, url: str) -> None:
        self._get(QUrl(url), ZhutixClient.DOWNLOAD_HEADERS, self._on_image)

    def _on_image(self) -> None:
        data, ok = self._take_reply()
        if ok and data and self._theme_dir is not None:
            try:
                dest = self._theme_dir / "preview.png"
                tmp = dest.with_suffix(".png.part")
                tmp.write_bytes(data)
                tmp.replace(dest)
                self.preview_ready.emit(self._theme_name)
            except OSError:
                pass
        self._finish()

    def _finish(self) -> None:
        self._busy = False
        self._theme_name = ""
        self._theme_dir = None
        self._source_url = ""
        self._pump()
