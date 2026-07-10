# -*- coding: utf-8 -*-
"""CursorVault 应用程序入口."""

from __future__ import annotations

import sys
from pathlib import Path

import ctypes

from PyQt6.QtWidgets import QApplication, QMessageBox

from .main_window import MainWindow, APP_STYLESHEET
from .theme_manager import ThemeManager


def create_app(base_dir: Path | None = None) -> QApplication:
    """创建 CursorVault 应用程序."""
    app = QApplication(sys.argv)
    app.setApplicationName("CursorVault")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("CursorVault")

    # 全局样式
    app.setStyleSheet(APP_STYLESHEET)

    return app


def run(base_dir: Path | None = None) -> None:
    """运行 CursorVault 主程序."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    app = create_app(base_dir)

    # 检查管理员权限（仅在 Windows 上需要）
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if not is_admin:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("权限提示")
            msg.setText("CursorVault 未以管理员权限运行")
            msg.setInformativeText(
                "更换系统游标需要管理员权限。\n\n"
                "如果后续无法成功替换游标，请右键以管理员身份重新运行本程序。"
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
    except Exception:
        pass  # 非 Windows 系统跳过

    theme_manager = ThemeManager(base_dir)
    window = MainWindow(theme_manager)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
