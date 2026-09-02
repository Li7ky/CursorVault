"""主题管理：管理导入的游标主题.

支持两种导入方式:
1. 从本地 .cur 目录导入
2. 从下载的 .rar/.zip/.7z 压缩包导入（自动解压+映射）
"""

from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Optional

from .models import CursorType, Theme
from .downloader import (
    find_cursor_files,
    build_cursor_map,
    install_pack_from_archive,
    InstallResult,
)


def sanitize_theme_slug(name: str) -> str:
    """将用户输入/远程 slug 规范化为安全的目录名."""
    name = (name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = name.strip(" .")
    if not name or name in {".", ".."}:
        raise ValueError("主题名称不能为空，且不能包含路径分隔符")
    if any(char in name for char in ("/", "\\", ":")):
        raise ValueError("主题名称不能包含路径分隔符")
    return name


class ThemeManager:
    """主题管理器：管理本地已导入的游标主题."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.themes_dir = self.base_dir / "themes"
        self.imported_dir = self.themes_dir / "imported"
        self.download_dir = self.themes_dir / "downloads"
        self.imported_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._themes: dict[str, Theme] = {}
        self._load_imported_themes()

    def _theme_dir_for_name(self, name: str) -> Path:
        """Return a theme directory guaranteed to stay under ``imported``."""
        name = sanitize_theme_slug(name)
        root = self.imported_dir.resolve()
        candidate = (root / name).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("主题名称必须位于主题目录内")
        return candidate

    def _read_theme_from_dir(self, theme_dir: Path) -> Optional[Theme]:
        if not theme_dir.is_dir():
            return None

        name = theme_dir.name
        cursor_files: dict[CursorType, Path] = {}
        for ct in CursorType:
            for suffix in (".cur", ".ani"):
                cursor_path = theme_dir / f"{ct.value}{suffix}"
                if cursor_path.exists():
                    cursor_files[ct] = cursor_path
                    break

        if not cursor_files:
            return None

        theme = Theme(
            name=name,
            display_name=name,
            cursor_files=cursor_files,
        )

        source_file = theme_dir / ".source"
        if source_file.exists():
            try:
                theme.source_url = source_file.read_text("utf-8").strip()
            except OSError:
                pass

        name_file = theme_dir / ".name"
        if name_file.exists():
            try:
                theme.display_name = name_file.read_text("utf-8").strip() or name
            except OSError:
                pass

        return theme

    def _load_imported_themes(self) -> None:
        """扫描 imported 目录加载已经导入的主题."""
        with self._lock:
            self._themes.clear()
            if not self.imported_dir.exists():
                return
            for theme_dir in sorted(self.imported_dir.iterdir()):
                theme = self._read_theme_from_dir(theme_dir)
                if theme:
                    self._themes[theme.name] = theme

    def reload(self) -> None:
        """重新扫描磁盘上的主题."""
        self._load_imported_themes()

    @property
    def themes(self) -> list[Theme]:
        with self._lock:
            return list(self._themes.values())

    def get_theme(self, name: str) -> Optional[Theme]:
        with self._lock:
            return self._themes.get(name)

    def get_cursor_file(self, theme_name: str, cursor_type: CursorType) -> Optional[Path]:
        """获取主题中指定类型的游标文件路径."""
        with self._lock:
            theme = self._themes.get(theme_name)
            if not theme:
                return None
            path = theme.cursor_files.get(cursor_type)
            if path and path.exists():
                return path

        # 磁盘回退：.cur / .ani
        try:
            theme_dir = self._theme_dir_for_name(theme_name)
        except ValueError:
            return None
        for suffix in (".cur", ".ani"):
            candidate = theme_dir / f"{cursor_type.value}{suffix}"
            if candidate.exists():
                return candidate
        return None

    def theme_exists(self, name: str) -> bool:
        with self._lock:
            return name in self._themes

    def import_cur_directory(
        self,
        name: str,
        source_dir: Path,
        source_url: str = "",
        display_name: str = "",
        overwrite: bool = False,
    ) -> Optional[Theme]:
        """从目录导入一组 .cur/.ani 文件作为主题."""
        slug = sanitize_theme_slug(name)
        with self._lock:
            if slug in self._themes and not overwrite:
                raise FileExistsError(f"主题「{slug}」已存在")

            theme_dir = self._theme_dir_for_name(slug)
            if theme_dir.exists() and overwrite:
                shutil.rmtree(theme_dir, ignore_errors=True)
            theme_dir.mkdir(parents=True, exist_ok=True)

            cursor_map = build_cursor_map(find_cursor_files(source_dir))
            cursor_files: dict[CursorType, Path] = {}
            for ct, src in cursor_map.items():
                suffix = src.suffix.lower()
                dst = theme_dir / f"{ct.value}{suffix}"
                try:
                    shutil.copy2(src, dst)
                    alternate = theme_dir / f"{ct.value}{'.ani' if suffix == '.cur' else '.cur'}"
                    alternate.unlink(missing_ok=True)
                    cursor_files[ct] = dst
                except OSError:
                    continue

            if not cursor_files:
                self._cleanup_empty_theme_dir(theme_dir)
                return None

            shown = (display_name or slug).strip() or slug
            if source_url:
                (theme_dir / ".source").write_text(source_url, "utf-8")
            (theme_dir / ".name").write_text(shown, "utf-8")

            theme = Theme(
                name=slug,
                display_name=shown,
                source_url=source_url,
                cursor_files=cursor_files,
            )
            self._themes[slug] = theme
            return theme

    def install_from_archive(
        self,
        archive_path: Path,
        slug: str,
        display_name: str = "",
        source_url: str = "",
    ) -> tuple[Optional[Theme], str]:
        """从压缩包安装光标主题.

        Returns:
            (theme, error_message) 成功时 error 为空字符串。
        """
        slug = sanitize_theme_slug(slug)
        with self._lock:
            theme_dir = self._theme_dir_for_name(slug)
            theme_dir.mkdir(parents=True, exist_ok=True)

            result: InstallResult = install_pack_from_archive(
                archive_path, theme_dir, slug
            )
            if not result.files:
                self._cleanup_empty_theme_dir(theme_dir)
                return None, result.error or "安装失败：未知错误"

            if source_url:
                (theme_dir / ".source").write_text(source_url, "utf-8")
            if display_name:
                (theme_dir / ".name").write_text(display_name, "utf-8")

            theme = Theme(
                name=slug,
                display_name=display_name or slug,
                source_url=source_url,
                cursor_files=result.files,
            )
            self._themes[slug] = theme
            return theme, ""

    def _cleanup_empty_theme_dir(self, theme_dir: Path) -> None:
        """安装失败时清理空目录，避免留下垃圾."""
        try:
            if not theme_dir.exists():
                return
            # 仅当没有有效游标文件时删除
            has_cursor = any(
                (theme_dir / f"{ct.value}{suffix}").exists()
                for ct in CursorType
                for suffix in (".cur", ".ani")
            )
            if has_cursor:
                return
            shutil.rmtree(theme_dir, ignore_errors=True)
            # 若父级是 imported 且空，不动
        except OSError:
            pass

    def remove_theme(self, name: str) -> bool:
        """删除已导入的主题."""
        with self._lock:
            if name not in self._themes:
                return False
            try:
                theme_dir = self._theme_dir_for_name(name)
            except ValueError:
                return False
            if theme_dir.exists():
                shutil.rmtree(theme_dir, ignore_errors=True)
            del self._themes[name]
            return True

    def get_theme_dir(self, name: str) -> Optional[Path]:
        """获取主题文件目录."""
        with self._lock:
            theme = self._themes.get(name)
            if not theme:
                return None
            try:
                path = self._theme_dir_for_name(theme.name)
            except ValueError:
                return None
            if path.exists():
                return path
            return None

    def is_installed(self, slug: str) -> bool:
        """检查指定 slug 的主题是否已安装."""
        with self._lock:
            return slug in self._themes
