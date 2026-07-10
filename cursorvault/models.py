"""数据模型：游标类型、主题定义、系统游标映射。
移除了内置渲染主题 (BUILTIN_THEMES)，
数据源改为致美化 (zhutix.com) 下载的游标包。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class CursorType(str, enum.Enum):
    """Windows 标准游标类型."""

    ARROW = "arrow"  # 标准选择
    HELP = "help"  # 帮助选择
    APPSTARTING = "appstarting"  # 后台运行
    WAIT = "wait"  # 忙碌
    CROSSHAIR = "crosshair"  # 精确选择
    IBEAM = "ibeam"  # 文本选择
    PEN = "pen"  # 手写
    NO = "no"  # 不可用
    SIZEALL = "sizeall"  # 移动
    SIZENESW = "sizenesw"  # 对角线调整1
    SIZENS = "sizens"  # 垂直调整
    SIZENWSE = "sizenwse"  # 对角线调整2
    SIZEWE = "sizewe"  # 水平调整
    UPARROW = "uparrow"  # 备用选择
    HAND = "hand"  # 链接选择


# Windows 系统游标 ID 映射
OCR_MAP: dict[CursorType, int] = {
    CursorType.ARROW: 32512,
    CursorType.IBEAM: 32513,
    CursorType.WAIT: 32514,
    CursorType.CROSSHAIR: 32515,
    CursorType.UPARROW: 32516,
    CursorType.SIZENWSE: 32642,
    CursorType.SIZENESW: 32643,
    CursorType.SIZEWE: 32644,
    CursorType.SIZENS: 32645,
    CursorType.SIZEALL: 32646,
    CursorType.NO: 32648,
    CursorType.HAND: 32649,
    CursorType.APPSTARTING: 32650,
    CursorType.HELP: 32651,
    CursorType.PEN: 32631,
}

# 注册表值名称映射
REGISTRY_VALUE_MAP: dict[CursorType, str] = {
    CursorType.ARROW: "Arrow",
    CursorType.HELP: "Help",
    CursorType.APPSTARTING: "AppStarting",
    CursorType.WAIT: "Wait",
    CursorType.CROSSHAIR: "Crosshair",
    CursorType.IBEAM: "IBeam",
    CursorType.PEN: "NWPen",
    CursorType.NO: "No",
    CursorType.SIZEALL: "SizeAll",
    CursorType.SIZENESW: "SizeNESW",
    CursorType.SIZENS: "SizeNS",
    CursorType.SIZENWSE: "SizeNWSE",
    CursorType.SIZEWE: "SizeWE",
    CursorType.UPARROW: "UpArrow",
    CursorType.HAND: "Hand",
}

# 游标中文名称
CURSOR_CHINESE_NAMES: dict[CursorType, str] = {
    CursorType.ARROW: "标准选择",
    CursorType.HELP: "帮助选择",
    CursorType.APPSTARTING: "后台运行",
    CursorType.WAIT: "忙碌",
    CursorType.CROSSHAIR: "精确选择",
    CursorType.IBEAM: "文本选择",
    CursorType.PEN: "手写",
    CursorType.NO: "不可用",
    CursorType.SIZEALL: "移动",
    CursorType.SIZENESW: "对角线调整1",
    CursorType.SIZENS: "垂直调整",
    CursorType.SIZENWSE: "对角线调整2",
    CursorType.SIZEWE: "水平调整",
    CursorType.UPARROW: "备用选择",
    CursorType.HAND: "链接选择",
}

# 热点坐标 (x, y) - 相对于光标图像
HOTSPOT_MAP: dict[CursorType, tuple[int, int]] = {
    CursorType.ARROW: (4, 4),
    CursorType.HELP: (4, 4),
    CursorType.APPSTARTING: (4, 4),
    CursorType.WAIT: (16, 16),
    CursorType.CROSSHAIR: (16, 16),
    CursorType.IBEAM: (16, 16),
    CursorType.PEN: (16, 16),
    CursorType.NO: (16, 16),
    CursorType.SIZEALL: (16, 16),
    CursorType.SIZENESW: (16, 16),
    CursorType.SIZENS: (16, 16),
    CursorType.SIZENWSE: (16, 16),
    CursorType.SIZEWE: (16, 16),
    CursorType.UPARROW: (16, 4),
    CursorType.HAND: (8, 4),
}


@dataclass
class CursorPack:
    """从致美化获取的鼠标指针包信息."""
    id: str  # 唯一标识 (从 URL 提取)
    title: str  # 显示标题
    url: str  # 详情页链接
    preview_url: Optional[str] = None  # 预览图链接
    description: str = ""
    author: str = ""
    date: str = ""


@dataclass
class Theme:
    """已安装的游标主题."""
    name: str  # 主题目录名
    display_name: str  # 显示名称
    source_url: str = ""  # 来源页面 URL
    cursor_files: dict[CursorType, Path] = field(default_factory=dict)
    installed: bool = False

    def get_cursor_count(self) -> int:
        return len(self.cursor_files)

    def is_complete(self) -> bool:
        return all(ct in self.cursor_files for ct in CursorType)
