"""主题管理：管理从致美化导入的游标主题.

支持两种导入方式:
1. 从本地 .cur 目录导入
2. 从致美化下载的 .rar/.zip 压缩包导入（自动解压+映射）
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from .models import CursorType, Theme
from .downloader import find_cursor_files, build_cursor_map, install_pack_from_archive


# ── 主题管理器 ────────────────────────────────────────────────

class ThemeManager:
    """主题管理器：管理从致美化导入的游标主题."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.themes_dir = self.base_dir / "themes"
        self.imported_dir = self.themes_dir / "imported"
        self.download_dir = self.themes_dir / "downloads"
        self.imported_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self._themes: dict[str, Theme] = {}
        self._load_imported_themes()

    def _load_imported_themes(self):
        """扫描 imported 目录加载已经导入的主题."""
        if not self.imported_dir.exists():
            return
        for theme_dir in sorted(self.imported_dir.iterdir()):
            if not theme_dir.is_dir():
                continue

            name = theme_dir.name
            cursor_files: dict[CursorType, Path] = {}

            for ct in CursorType:
                cur_path = theme_dir / f"{ct.value}.cur"
                if cur_path.exists():
                    cursor_files[ct] = cur_path

            if not cursor_files:
                continue

            theme = Theme(
                name=name,
                display_name=name,
                cursor_files=cursor_files,
                installed=theme_dir.exists(),
            )

            # 读取 .source 文件获取来源 URL
            source_file = theme_dir / ".source"
            if source_file.exists():
                theme.source_url = source_file.read_text("utf-8").strip()

            # 读取显示名称
            name_file = theme_dir / ".name"
            if name_file.exists():
                theme.display_name = name_file.read_text("utf-8").strip()

            self._themes[name] = theme

    @property
    def themes(self) -> list[Theme]:
        return list(self._themes.values())

    def get_theme(self, name: str) -> Optional[Theme]:
        return self._themes.get(name)

    def import_cur_directory(self, name: str, source_dir: Path, source_url: str = "") -> Optional[Theme]:
        """从目录导入一组 .cur 文件作为主题."""
        theme_dir = self.imported_dir / name
        theme_dir.mkdir(parents=True, exist_ok=True)

        cursor_files: dict[CursorType, Path] = {}
        for ct in CursorType:
            src = source_dir / f"{ct.value}.cur"
            if src.exists():
                dst = theme_dir / f"{ct.value}.cur"
                if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                    dst.write_bytes(src.read_bytes())
                cursor_files[ct] = dst

        if not cursor_files:
            return None

        # 保存来源 URL
        if source_url:
            (theme_dir / ".source").write_text(source_url, "utf-8")

        theme = Theme(
            name=name,
            display_name=name,
            source_url=source_url,
            cursor_files=cursor_files,
            installed=True,
        )
        self._themes[name] = theme
        return theme

    def install_from_archive(
        self,
        archive_path: Path,
        slug: str,
        display_name: str = "",
        source_url: str = "",
    ) -> Optional[Theme]:
        """从压缩包安装光标主题.

        1. 解压压缩包
        2. 查找 .cur/.ani 文件
        3. 映射到标准游标类型
        4. 安装到主题目录

        Args:
            archive_path: 压缩包路径
            slug: 主题标识 (用作目录名)
            display_name: 显示名称
            source_url: 来源 URL

        Returns:
            安装的主题，失败返回 None
        """
        theme_dir = self.imported_dir / slug
        theme_dir.mkdir(parents=True, exist_ok=True)

        # 解压并安装
        cursor_map = install_pack_from_archive(archive_path, theme_dir, slug)
        if not cursor_map:
            return None

        # 保存元数据
        if source_url:
            (theme_dir / ".source").write_text(source_url, "utf-8")
        if display_name:
            (theme_dir / ".name").write_text(display_name, "utf-8")

        theme = Theme(
            name=slug,
            display_name=display_name or slug,
            source_url=source_url,
            cursor_files=cursor_map,
            installed=True,
        )
        self._themes[slug] = theme
        return theme

    def remove_theme(self, name: str) -> bool:
        """删除已导入的主题."""
        if name not in self._themes:
            return False

        theme_dir = self.imported_dir / name
        if theme_dir.exists():
            shutil.rmtree(theme_dir)

        del self._themes[name]
        return True

    def get_theme_dir(self, name: str) -> Optional[Path]:
        """获取主题文件目录."""
        theme = self._themes.get(name)
        if not theme:
            return None
        path = self.imported_dir / theme.name
        if path.exists():
            return path
        return None

    def is_installed(self, slug: str) -> bool:
        """检查指定 slug 的主题是否已安装."""
        return slug in self._themes
