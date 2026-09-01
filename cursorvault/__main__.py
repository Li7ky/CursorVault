"""CursorVault 入口.

通过 python -m cursorvault 启动时使用此入口。
实际启动逻辑委托给 app.py 中的 run() 函数，
确保样式表、图标等配置一致。
"""

from __future__ import annotations

from .app import run


def main() -> None:
    """启动 CursorVault."""
    run()


if __name__ == "__main__":
    main()
