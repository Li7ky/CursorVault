# -*- coding: utf-8 -*-
"""自绘矢量图标集.

为什么不用 Segoe Fluent Icons 字体了
-----------------------------------
原实现把 ``\\uE774`` 这类字形当字符塞进 QPushButton / QLabel，依赖系统装有
"Segoe Fluent Icons" 或 "Segoe MDL2 Assets"。三个硬伤：

1. 精简版 / LTSC / 部分 Win10 没这两个字体 → 直接显示豆腐块 ▯
2. 字形是按字号排版的，不同按钮里视觉大小和基线对不齐
3. 颜色只能跟 QSS 的 ``color`` 走，描边粗细无法统一，明暗主题下对比度失控

这里改成 QPainter 在 24×24 设计网格上直接描边生成 QIcon：
零字体依赖、线宽/端点/圆角统一、颜色跟随设计令牌、明暗切换时整体重绘。

用法
----
    from .vector_icons import set_button_icon, set_label_icon, retheme_icons

    set_button_icon(btn, ICON.REFRESH, size=18)          # QAbstractButton
    set_label_icon(label, ICON.GLOBE, size=36,            # QLabel
                   role="text-tertiary")

切换明暗主题后调用一次 ``retheme_icons()``，所有已注册控件会按新令牌重绘。
"""

from __future__ import annotations

import math
import weakref
from typing import Callable, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QAbstractButton, QLabel

from ..ui_theme import token

# 设计网格：所有坐标都按 24×24 写，渲染时整体缩放到目标尺寸
GRID = 24.0

# 当前笔画/填充色。vector_pixmap 在调用 drawer 前写入，drawer 里需要实心元素时
# 直接读它，不要写死颜色——否则暗色主题下实心部分会变成「黑底黑图」。
_INK = "#1a1d23"

# 图标名常量
class ICON:
    GLOBE = "globe"
    FOLDER = "folder"
    SAVE = "save"
    RESTORE = "restore"
    REFRESH = "refresh"
    DOWNLOAD = "download"
    IMPORT = "import"
    CHECK = "check"
    CLOSE = "close"
    MORE = "more"
    SUN = "sun"
    MOON = "moon"
    IMAGE = "image"
    CURSOR = "cursor"
    TRASH = "trash"
    SEARCH = "search"
    INFO = "info"
    EXTERNAL = "external"
    LOCK = "lock"


# ═══════════════════════════════════════════════════════════════
# 绘制原语
# ═══════════════════════════════════════════════════════════════

def _pt(x: float, y: float) -> QPointF:
    return QPointF(x, y)


def _line(p: QPainter, x1: float, y1: float, x2: float, y2: float) -> None:
    p.drawLine(_pt(x1, y1), _pt(x2, y2))


def _poly(p: QPainter, pts, close: bool = False) -> None:
    path = QPainterPath()
    path.moveTo(_pt(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(_pt(x, y))
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _sample_arc(
    cx: float, cy: float, r: float, a0: float, a1: float, steps: int = 60
) -> list:
    """只采样不落笔，返回折线点（角度为数学角，单位：度）。

    _arc() 会直接画出来，这里要的是点集，供调用方拼自定义闭合路径。
    """
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _arc(p: QPainter, cx: float, cy: float, r: float, a0: float, a1: float) -> list:
    """画一段圆弧（角度为数学角，Qt 的 y 轴向下，所以视觉上是顺时针增大）.

    Returns:
        采样点列表，便于调用方接着画箭头。
    """
    sweep = abs(a1 - a0)
    steps = max(10, int(sweep / 3))
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    path = QPainterPath()
    path.moveTo(_pt(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(_pt(x, y))
    p.drawPath(path)
    return pts


def _arrow_head(
    p: QPainter,
    tip: tuple[float, float],
    direction: tuple[float, float],
    size: float = 4.4,
    spread: float = 30.0,
) -> None:
    """在 tip 处画一个开口朝 direction 的箭头。"""
    dx, dy = direction
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    for sign in (1.0, -1.0):
        a = math.radians(spread * sign)
        rx = dx * math.cos(a) - dy * math.sin(a)
        ry = dx * math.sin(a) + dy * math.cos(a)
        _line(p, tip[0], tip[1], tip[0] - rx * size, tip[1] - ry * size)


def _circle(p: QPainter, cx: float, cy: float, r: float) -> None:
    p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))


def _round_rect(
    p: QPainter, x: float, y: float, w: float, h: float, r: float
) -> None:
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


# ═══════════════════════════════════════════════════════════════
# 各图标绘制函数（坐标系固定 24×24）
# ═══════════════════════════════════════════════════════════════

def _draw_globe(p: QPainter) -> None:
    _circle(p, 12, 12, 8.5)
    p.drawEllipse(QRectF(12 - 3.9, 12 - 8.5, 7.8, 17.0))
    _line(p, 3.5, 12, 20.5, 12)


def _draw_folder(p: QPainter) -> None:
    _poly(
        p,
        [(3.2, 6.6), (9.0, 6.6), (11.3, 9.4), (20.8, 9.4), (20.8, 18.4), (3.2, 18.4)],
        close=True,
    )


def _draw_save(p: QPainter) -> None:
    # 软盘外框（只描边）
    _round_rect(p, 3.4, 4.4, 17.2, 15.2, 2.4)
    # 顶部凹口矩形
    _poly(p, [(8.6, 4.4), (8.6, 9.4), (15.4, 9.4), (15.4, 4.4)])
    # 底部小标签
    _line(p, 8.4, 15.4, 15.6, 15.4)
    _line(p, 15.6, 15.4, 15.6, 17.6)
    _line(p, 15.6, 17.6, 8.4, 17.6)
    _line(p, 8.4, 17.6, 8.4, 15.4)


def _draw_restore(p: QPainter) -> None:
    # 逆时针回环箭头（与 refresh 的顺时针区分）；_arc 收的是角度制
    pts = _arc(p, 12, 12, 7.5, 235, -55)
    # 末端切线：角度递减方向的切向为 (sin θ, -cos θ)
    _arrow_head(p, pts[-1], (math.sin(math.radians(-55)), -math.cos(math.radians(-55))))


def _draw_refresh(p: QPainter) -> None:
    # 顺时针回环箭头
    pts = _arc(p, 12, 12, 7.5, -55, 235)
    # 角度递增方向的切向为 (-sin θ, cos θ)
    _arrow_head(p, pts[-1], (-math.sin(math.radians(235)), math.cos(math.radians(235))))


def _draw_download(p: QPainter) -> None:
    _line(p, 12, 4.2, 12, 14.4)
    _poly(p, [(7.6, 10.4), (12, 15.0), (16.4, 10.4)])
    _line(p, 5.2, 18.6, 18.8, 18.6)


def _draw_import(p: QPainter) -> None:
    _line(p, 12, 15.2, 12, 5.0)
    _poly(p, [(7.6, 9.6), (12, 5.0), (16.4, 9.6)])
    _line(p, 5.2, 18.6, 18.8, 18.6)


def _draw_check(p: QPainter) -> None:
    _poly(p, [(5.0, 12.6), (9.7, 17.1), (19.0, 7.0)])


def _draw_close(p: QPainter) -> None:
    _line(p, 6.4, 6.4, 17.6, 17.6)
    _line(p, 17.6, 6.4, 6.4, 17.6)


def _draw_more(p: QPainter) -> None:
    # 三点：用实心圆点，描边会糊成一团
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(_INK))
    for x in (6.0, 12.0, 18.0):
        p.drawEllipse(QRectF(x - 1.45, 12 - 1.45, 2.9, 2.9))
    p.restore()


def _draw_sun(p: QPainter) -> None:
    _circle(p, 12, 12, 4.0)
    for i in range(8):
        a = math.radians(i * 45)
        c, s = math.cos(a), math.sin(a)
        _line(p, 12 + c * 6.6, 12 + s * 6.6, 12 + c * 9.2, 12 + s * 9.2)


def _draw_moon(p: QPainter) -> None:
    """月牙 = 大圆 (12,12,r=9) 减去右上方"咬口"圆 (17.588,5.888,r=7)。

    不用 QPainterPath.arcTo 是因为 Qt 的角度/扫掠方向语义在多段拼接时极容易搞反，
    这里改成：解析求出两圆交点，再沿各自"可见"的那段弧采样成折线拼成一条闭合路径，
    所见即所得，改参数也不会突然翻车。

    两圆交点（也是月牙的两个尖角）：
        A ≈ (11.21, 3.00)   —— 靠近 12 点
        B ≈ (21.00, 12.00)  —— 3 点
    外弧取远离咬口圆的一侧（A → 左 → 下 → B），内弧取咬口圆伸进大圆的那一段（B → A）。
    """
    outer = _sample_arc(12.0, 12.0, 9.0, -95.02, -360.02)
    inner = _sample_arc(17.588, 5.888, 7.0, 60.84, 204.37)

    path = QPainterPath()
    path.moveTo(_pt(*outer[0]))
    for x, y in outer[1:]:
        path.lineTo(_pt(x, y))
    for x, y in inner[1:]:  # inner[0] 与 outer[-1] 同为 B 点，跳过避免零长线段
        path.lineTo(_pt(x, y))
    path.closeSubpath()

    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(_INK))
    p.drawPath(path)
    p.restore()


def _draw_image(p: QPainter) -> None:
    # 相框
    _round_rect(p, 3.2, 4.8, 17.6, 14.4, 2.6)
    # 太阳/月亮小圆
    _circle(p, 8.7, 9.8, 1.7)
    # 山的折线
    _poly(p, [(3.8, 17.2), (8.5, 12.4), (12.2, 16.0), (15.6, 12.0), (20.2, 16.6)])


def _draw_cursor(p: QPainter) -> None:
    # 鼠标指针是实心形状，描边版本在小尺寸下认不出来
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(_INK))  # 实心形状必须跟随当前主题色
    _poly(
        p,
        [
            (6.0, 3.0),
            (6.0, 17.2),
            (10.1, 13.6),
            (12.6, 19.4),
            (15.3, 18.2),
            (12.9, 12.6),
            (18.6, 12.3),
        ],
        close=True,
    )
    p.restore()


def _draw_trash(p: QPainter) -> None:
    _line(p, 4.2, 7.2, 19.8, 7.2)
    _poly(p, [(9.8, 7.2), (9.8, 4.9), (14.2, 4.9), (14.2, 7.2)])
    _poly(p, [(6.2, 7.2), (7.3, 19.7), (16.7, 19.7), (17.8, 7.2)], close=True)
    _line(p, 10.4, 10.9, 10.4, 16.3)
    _line(p, 13.6, 10.9, 13.6, 16.3)


def _draw_search(p: QPainter) -> None:
    _circle(p, 10.6, 10.6, 6.2)
    _line(p, 15.2, 15.2, 20.2, 20.2)


def _draw_info(p: QPainter) -> None:
    # 主圆要稍小于 8.6，否则圆点会被它「吞掉」看不出独立的 i
    _circle(p, 12, 12, 8.0)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(_INK))
    p.drawEllipse(QRectF(12 - 1.0, 5.6, 2.0, 2.0))
    p.restore()
    _line(p, 12, 10.4, 12, 16.6)


def _draw_external(p: QPainter) -> None:
    # 外框：右下角缺口的方块（呼应「跳出窗口」的语义）
    _poly(p, [(18.6, 14.6), (18.6, 18.6), (5.4, 18.6), (5.4, 5.4), (9.6, 5.4)])
    # 右上角小箭头
    _poly(p, [(14.4, 5.4), (18.6, 5.4), (18.6, 9.6)], close=True)
    # 箭头斜线（从右上到内容区中段）
    _line(p, 18.6, 5.4, 10.6, 13.4)


def _draw_lock(p: QPainter) -> None:
    # 锁梁：从锁体上方升起的圆弧（开口向下）
    _arc(p, 12, 10.2, 4.1, 180, 360)
    # 锁体：圆角方
    _round_rect(p, 6.4, 10.2, 11.2, 9.4, 2.4)
    # 锁孔：竖线 + 圆点
    _line(p, 12, 13.6, 12, 16.2)


_DRAWERS: dict[str, Callable[[QPainter], None]] = {
    ICON.GLOBE: _draw_globe,
    ICON.FOLDER: _draw_folder,
    ICON.SAVE: _draw_save,
    ICON.RESTORE: _draw_restore,
    ICON.REFRESH: _draw_refresh,
    ICON.DOWNLOAD: _draw_download,
    ICON.IMPORT: _draw_import,
    ICON.CHECK: _draw_check,
    ICON.CLOSE: _draw_close,
    ICON.MORE: _draw_more,
    ICON.SUN: _draw_sun,
    ICON.MOON: _draw_moon,
    ICON.IMAGE: _draw_image,
    ICON.CURSOR: _draw_cursor,
    ICON.TRASH: _draw_trash,
    ICON.SEARCH: _draw_search,
    ICON.INFO: _draw_info,
    ICON.EXTERNAL: _draw_external,
    ICON.LOCK: _draw_lock,
}


# ═══════════════════════════════════════════════════════════════
# 渲染
# ═══════════════════════════════════════════════════════════════

def _device_ratio() -> float:
    app = QGuiApplication.instance()
    if app is None:
        return 1.0
    try:
        return max(1.0, float(app.devicePixelRatio()))
    except Exception:
        return 1.0


_PIXMAP_STORE: dict[tuple, QPixmap] = {}


def vector_pixmap(name: str, size: int = 18, color: str = "#475569") -> QPixmap:
    dpr = _device_ratio()
    key = (name, size, color, dpr)
    cached = _PIXMAP_STORE.get(key)
    if cached is not None:
        return cached

    drawer = _DRAWERS.get(name)
    px = max(1, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    if drawer is not None:
        global _INK
        _INK = color
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        scale = px / GRID
        p.scale(scale, scale)
        pen = QPen(QColor(color), 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        # 默认 NoBrush，drawer 需要实心元素时自己 setBrush
        p.setBrush(Qt.BrushStyle.NoBrush)
        drawer(p)
        p.end()

    # 缓存上限保护：卡片会不断创建销毁，颜色/尺寸组合有限，给个宽松上限
    if len(_PIXMAP_STORE) > 400:
        _PIXMAP_STORE.clear()
    _PIXMAP_STORE[key] = pm
    return pm


def vector_icon(
    name: str,
    size: int = 18,
    color: str = "#475569",
    disabled_color: Optional[str] = None,
) -> QIcon:
    """生成带 Normal / Disabled 两态的 QIcon."""
    icon = QIcon()
    icon.addPixmap(vector_pixmap(name, size, color), QIcon.Mode.Normal)
    if disabled_color:
        icon.addPixmap(
            vector_pixmap(name, size, disabled_color), QIcon.Mode.Disabled
        )
    return icon


# ═══════════════════════════════════════════════════════════════
# 主题感知的控件绑定
# ═══════════════════════════════════════════════════════════════

# 用弱引用登记表：卡片会被反复创建销毁，强引用会让它永远不释放
_REGISTRY: "weakref.WeakKeyDictionary[object, tuple]" = weakref.WeakKeyDictionary()


def _apply_spec(widget, spec: tuple) -> None:
    kind, name, size, role, disabled_role = spec
    color = token(role, "#475569")
    disabled = token(disabled_role, "#94a3b8") if disabled_role else None
    try:
        if kind == "button":
            widget.setIcon(vector_icon(name, size, color, disabled))
            widget.setIconSize(QSize(size, size))
        else:
            pm = vector_pixmap(name, size, color)
            widget.setPixmap(pm)
            widget.setText("")
    except RuntimeError:
        # 底层 C++ 对象已析构
        _REGISTRY.pop(widget, None)


def set_button_icon(
    btn: QAbstractButton,
    name: str,
    size: int = 18,
    role: str = "text-secondary",
    disabled_role: str = "text-disabled",
) -> None:
    """给按钮绑定矢量图标，并登记以便切主题时重绘。"""
    spec = ("button", name, size, role, disabled_role)
    _REGISTRY[btn] = spec
    _apply_spec(btn, spec)


def set_label_icon(
    label: QLabel,
    name: str,
    size: int = 36,
    role: str = "text-tertiary",
) -> None:
    """给 QLabel 绑定矢量图标（会清掉 label 上的占位文字）。"""
    spec = ("label", name, size, role, None)
    _REGISTRY[label] = spec
    _apply_spec(label, spec)


def retheme_icons() -> None:
    """主题切换后重绘所有已登记图标。"""
    for widget, spec in list(_REGISTRY.items()):
        _apply_spec(widget, spec)


def forget_icons(widget) -> None:
    """控件销毁前主动注销（可选，弱引用会自动回收）。"""
    _REGISTRY.pop(widget, None)
