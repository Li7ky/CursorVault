"""在线光标素材客户端.

通过 REST API 获取鼠标指针素材列表，
支持分页浏览、预览图获取、下载链接提取。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import requests


BASE_URL = "https://zhutix.com"
API_BASE = f"{BASE_URL}/wp-json/wp/v2"
CURSORS_TAG_ID = 218  # 标签 "鼠标指针" 的 ID


@dataclass
class ZhutixPack:
    """在线素材库中的一个鼠标指针素材包."""

    post_id: int
    slug: str
    title: str
    url: str
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    modified: str = ""
    content: str = ""
    # True=正文含直链，可一键下载；False=多半是 VIP/积分隐藏下载
    has_direct_link: bool = False


class ZhutixClient:
    """在线光标素材列表客户端 (REST API)."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html;q=0.9",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    DOWNLOAD_HEADERS = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://zhutix.com/",
    }

    def __init__(self, timeout: int = 20):
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        self.timeout = timeout
        self._total: Optional[int] = None
        self._total_pages: Optional[int] = None
        self._media_cache: dict[int, str] = {}
        self.last_error: str = ""

    @property
    def total(self) -> Optional[int]:
        return self._total

    @property
    def total_pages(self) -> Optional[int]:
        return self._total_pages

    def fetch_page(
        self,
        page: int = 1,
        per_page: int = 50,
        orderby: str = "date",
        order: str = "desc",
        resolve_previews: bool = True,
    ) -> list[ZhutixPack]:
        """获取指定页的光标包列表.

        Args:
            page: 页码，从 1 开始
            per_page: 每页数量 (最大 100)
            orderby: WP 排序字段 date / modified / title / id
            order: asc / desc
            resolve_previews: 在后台解析 featured_media 预览图（勿在 UI 线程调用）
        """
        params = {
            "per_page": per_page,
            "page": page,
            "tags": CURSORS_TAG_ID,
            "orderby": orderby,
            "order": order,
            "_fields": "id,slug,title,link,featured_media,modified,content",
        }

        try:
            resp = self._session.get(
                f"{API_BASE}/posts", params=params, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"获取在线素材列表失败 (page={page}): {e}") from e

        self._total = int(resp.headers.get("X-WP-Total", self._total or 0))
        self._total_pages = int(resp.headers.get("X-WP-TotalPages", self._total_pages or 0))

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
                preview_url=None,
                modified=post.get("modified", ""),
                content=content,
            )
            pack.download_url = self._extract_download_url(content)
            pack.has_direct_link = bool(pack.download_url)
            pack.preview_url = self._extract_preview_from_content(content)

            fm_id = post.get("featured_media", 0) or 0
            if fm_id:
                pack._featured_media_id = fm_id  # type: ignore[attr-defined]

            packs.append(pack)

        if resolve_previews:
            self.resolve_previews(packs)

        return packs

    def resolve_previews(self, packs: list[ZhutixPack]) -> None:
        """批量解析仍缺预览图的包（应在工作线程调用）."""
        for pack in packs:
            if pack.preview_url:
                continue
            self.get_preview_url(pack)

    def fetch_all(self, per_page: int = 100, progress_cb=None) -> list[ZhutixPack]:
        """获取全部光标包."""
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

    def peek_preview_url(self, pack: ZhutixPack) -> Optional[str]:
        """非阻塞：仅返回已缓存/已解析的预览 URL，不发网络请求."""
        if pack.preview_url:
            return pack.preview_url
        fm_id = getattr(pack, "_featured_media_id", 0) or 0
        if fm_id and fm_id in self._media_cache:
            url = self._media_cache[fm_id]
            pack.preview_url = url
            return url
        return None

    def get_preview_url(self, pack: ZhutixPack) -> Optional[str]:
        """获取光标包的预览图 URL（可能发起 HTTP，勿在 UI 线程调用）."""
        cached = self.peek_preview_url(pack)
        if cached:
            return cached

        fm_id = getattr(pack, "_featured_media_id", 0) or 0
        if not fm_id:
            return None

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

    @staticmethod
    def _extract_download_url(html: str) -> Optional[str]:
        """从 HTML/正文中提取可直链下载的压缩包地址."""
        if not html:
            return None

        patterns = [
            # 站内常见直链域名
            r'(https?://(?:123|vip2|vip)\.zhutix\.com/[^\s"\'<>]+?\.(?:rar|zip|7z)(?:\?[^\s"\'<>]*)?)',
            # 其它 zhutix 子域
            r'(https?://[a-z0-9.-]*zhutix\.[a-z]+/[^\s"\'<>]+?\.(?:rar|zip|7z)(?:\?[^\s"\'<>]*)?)',
            # 正文里任意 rar/zip/7z（排除图片 CDN 误伤概率低）
            r'(https?://[^\s"\'<>]+?\.(?:rar|zip|7z)(?:\?[^\s"\'<>]*)?)',
        ]
        found: list[str] = []
        for pat in patterns:
            found.extend(re.findall(pat, html, flags=re.IGNORECASE))

        # 清洗 HTML 实体 / 引号尾巴
        cleaned: list[str] = []
        for u in found:
            u = (
                u.replace("&amp;", "&")
                .replace("&#038;", "&")
                .rstrip(").,;\"'")
            )
            # 排除明显不是资源包的
            low = u.lower()
            if any(x in low for x in (".jpg", ".png", ".gif", ".webp", ".svg", "avatar")):
                continue
            cleaned.append(u)

        if not cleaned:
            return None

        # 优先 123 电信直链，再 vip2
        for u in cleaned:
            if "123.zhutix.com" in u:
                return u
        for u in cleaned:
            if "vip2.zhutix.com" in u or "vip.zhutix.com" in u:
                return u
        return cleaned[0]

    def resolve_download_url(self, pack: ZhutixPack) -> Optional[str]:
        """多策略解析下载直链（应在工作线程调用）."""
        self.last_error = ""

        # 1) 已有
        if pack.download_url:
            pack.has_direct_link = True
            return pack.download_url

        # 2) 已缓存 content
        url = self._extract_download_url(pack.content or "")
        if url:
            pack.download_url = url
            pack.has_direct_link = True
            return url

        # 3) 重新拉详情 content
        detail = self.fetch_detail(pack.slug)
        if detail:
            if detail.content:
                pack.content = detail.content
            url = detail.download_url or self._extract_download_url(detail.content or "")
            if url:
                pack.download_url = url
                pack.has_direct_link = True
                return url

        # 4) 抓取完整文章页 HTML
        page_url = pack.url or f"{BASE_URL}/ico/{pack.slug}/"
        try:
            resp = self._session.get(page_url, timeout=self.timeout)
            if resp.ok:
                url = self._extract_download_url(resp.text)
                if url:
                    pack.download_url = url
                    pack.has_direct_link = True
                    return url
        except requests.RequestException:
            pass

        # 5) b2 隐藏内容接口（访客若可见直链则可拿到；VIP 隐藏则通常只有积分按钮）
        try:
            resp = self._session.post(
                f"{BASE_URL}/wp-json/b2/v1/getHiddenContent",
                json={"id": pack.post_id},
                headers={
                    **self.HEADERS,
                    "Content-Type": "application/json",
                    "Referer": page_url,
                },
                timeout=self.timeout,
            )
            if resp.ok:
                data = resp.json()
                html = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
                url = self._extract_download_url(html)
                if url:
                    pack.download_url = url
                    pack.has_direct_link = True
                    return url
                # 有隐藏块但只有积分下载按钮
                if "b2creditpay" in html or "javascript:void" in html:
                    self.last_error = "该素材需要VIP才能下载。"
                    return None
        except Exception:
            pass

        self.last_error = "该素材需要VIP才能下载。"
        return None

    @staticmethod
    def _extract_preview_from_content(html: str) -> Optional[str]:
        """从 content HTML 中提取第一张预览图."""
        pattern = r'(https?://dl\.zhutix\.net/[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|webp))'
        matches = re.findall(pattern, html, re.IGNORECASE)
        if matches:
            return matches[0]
        # 兜底：任意 img src
        img = re.search(
            r'<img[^>]+src=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|gif|webp))["\']',
            html,
            re.IGNORECASE,
        )
        if img:
            return img.group(1)
        return None

    def fetch_detail(self, slug: str) -> Optional[ZhutixPack]:
        """通过 slug 获取单个光标包的完整详情."""
        params = {
            "slug": slug,
            "_fields": "id,slug,title,link,featured_media,modified,content",
        }
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
        pack.has_direct_link = bool(pack.download_url)
        pack.preview_url = self._extract_preview_from_content(content)
        fm_id = post.get("featured_media", 0) or 0
        if fm_id:
            pack._featured_media_id = fm_id  # type: ignore[attr-defined]
            if not pack.preview_url:
                self.get_preview_url(pack)
        return pack

    @staticmethod
    def safe_download_filename(url: str, fallback: str = "pack.bin") -> str:
        """从下载 URL 提取安全文件名."""
        try:
            path = unquote(urlparse(url).path)
            name = Path(path).name
        except Exception:
            name = ""
        if not name:
            name = fallback
        name = re.sub(r"[^\w.\-()+\u4e00-\u9fff]+", "_", name, flags=re.UNICODE)
        name = name.strip("._") or fallback
        if not re.search(r"\.(rar|zip|7z)$", name, re.IGNORECASE):
            # 尝试从 URL 猜扩展名
            lower = url.lower()
            for ext in (".rar", ".zip", ".7z"):
                if ext in lower:
                    name = name + ext
                    break
        return name[:180]

    def download_pack(
        self,
        pack: ZhutixPack,
        dest_dir: Path,
        progress_cb=None,
        should_abort=None,
    ) -> Optional[Path]:
        """下载光标包到指定目录.

        should_abort: 可选回调，返回 True 时中止下载。
        成功返回本地路径；失败返回 None，错误信息写在 self.last_error。
        """
        self.last_error = ""
        if not pack.download_url:
            pack.download_url = self.resolve_download_url(pack)
            if not pack.download_url:
                if not self.last_error:
                    self.last_error = "无法获取下载链接（该素材可能需要 VIP 才能下载）"
                return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = self.safe_download_filename(
            pack.download_url, fallback=f"{pack.slug or f'pack_{pack.post_id}'}.rar"
        )
        dest_path = dest_dir / filename

        try:
            resp = requests.get(
                pack.download_url,
                headers=self.DOWNLOAD_HEADERS,
                stream=True,
                timeout=90,
                allow_redirects=True,
            )
            resp.raise_for_status()

            # Content-Disposition 优先
            cd = resp.headers.get("Content-Disposition") or ""
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.I)
            if m:
                raw_name = unquote(m.group(1).strip())
                if raw_name:
                    filename = self.safe_download_filename(
                        raw_name, fallback=filename
                    )
                    dest_path = dest_dir / filename

            total = int(resp.headers.get("content-length", 0) or 0)
            downloaded = 0
            tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if should_abort and should_abort():
                        f.close()
                        tmp_path.unlink(missing_ok=True)
                        self.last_error = "下载已取消"
                        return None
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total)

            if not tmp_path.exists() or tmp_path.stat().st_size < 32:
                tmp_path.unlink(missing_ok=True)
                self.last_error = "下载文件为空或过小"
                return None

            # 按文件头校正扩展名 / 拦截 HTML 错误页
            from .downloader import detect_archive_kind

            kind = detect_archive_kind(tmp_path)
            if kind == "html":
                tmp_path.unlink(missing_ok=True)
                self.last_error = (
                    "下载到的是网页而不是压缩包（链接可能失效或需要浏览器打开）"
                )
                return None
            if kind in {"rar", "zip", "7z"}:
                fixed = dest_dir / f"{Path(filename).stem}.{kind}"
                if dest_path.exists():
                    dest_path.unlink(missing_ok=True)
                tmp_path.replace(fixed)
                dest_path = fixed
            else:
                if dest_path.exists():
                    dest_path.unlink(missing_ok=True)
                tmp_path.replace(dest_path)

            return dest_path
        except requests.RequestException as e:
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            part = dest_path.with_suffix(dest_path.suffix + ".part")
            part.unlink(missing_ok=True)
            self.last_error = f"网络下载失败: {e}"
            return None
