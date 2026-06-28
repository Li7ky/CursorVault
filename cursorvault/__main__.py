"""CursorVault 入口."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme_manager import ThemeManager


def main() -> int:
    import sys
    app = QApplication(sys.argv)
    base_dir = Path(__file__).resolve().parent.parent
    theme_manager = ThemeManager(base_dir)
    window = MainWindow(theme_manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
