# -*- coding: utf-8 -*-
"""CursorVault 应用程序入口."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import __version__
from .main_window import MainWindow
from .theme_manager import ThemeManager
from .ui_theme import APP_STYLESHEET, build_stylesheet


def app_icon(base_dir: Path) -> QIcon:
    """加载应用图标（优先 ico，其次 png）."""
    candidates = [
        base_dir / "assets" / "app_icon.ico",
        base_dir / "assets" / "app_icon.png",
        base_dir / "cursorvault" / "assets" / "app_icon.ico",
    ]
    icon = QIcon()
    for path in candidates:
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return icon


def create_app(base_dir: Path | None = None) -> QApplication:
    """创建 CursorVault 应用程序."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    app = QApplication(sys.argv)
    app.setApplicationName("CursorVault")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("CursorVault")
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet("light"))

    icon = app_icon(base_dir)
    if not icon.isNull():
        app.setWindowIcon(icon)
    return app


def run(base_dir: Path | None = None) -> None:
    """运行 CursorVault 主程序."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    app = create_app(base_dir)

    # 应用游标写入 HKCU 注册表，通常不需要管理员权限；不再强提示 UAC。
    theme_manager = ThemeManager(base_dir)
    window = MainWindow(theme_manager)
    icon = app.windowIcon()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
