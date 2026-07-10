# -*- coding: utf-8 -*-
"""CursorVault 启动入口."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cursorvault.app import run

if __name__ == "__main__":
    run()
