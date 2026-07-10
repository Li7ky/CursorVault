#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CursorVault - 鼠标素材库

一站式鼠标光标主题管理与替换工具。
内置 10 套精美游标主题，一键替换系统游标。

用法:
    python main.py

依赖:
    PyQt6, Pillow
"""

from __future__ import annotations

import sys
from pathlib import Path


def main():
    """主入口."""
    # 确保在当前目录运行
    base_dir = Path(__file__).resolve().parent

    # 将项目根目录加入 Python 路径
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    from cursorvault.app import run

    run(base_dir)


if __name__ == "__main__":
    main()
