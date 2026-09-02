# -*- coding: utf-8 -*-
"""底部状态栏 v4 - 48px 极简命令栏."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QSize, QRectF, QEasingCurve, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ui_theme import token as _token
from ..models import Theme
from .vector_icons import ICON, vector_pixmap


class ProgressPill(QWidget):
    """自绘进度胶囊：确定态为主色渐变填充，不定态为来回滑动的光斑.

    Fluent 观感的关键点：
    - 轨道是全圆角胶囊（高度的一半），不再是 2px 细线
    - 填充用水平渐变（accent → accent-strong），右缘带一点柔光
    - 不定态（total=0，直链解析阶段）用一个渐变光斑来回巡航，暗示"在忙"
    """

    def __init__(self, parent=None, width: int = 260, height: int = 6):
        super().__init__(parent)
        self._w = width
        self._h = height
        self._value = 0.0        # 0..1
        self._indeterminate = False
        self._pos = 0.0          # 不定态光斑中心 0..1
        self.setFixedSize(width, height)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1400)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_tick)

    # ── 公共接口（与 QProgressBar 对齐，方便替换）──
    def setRange(self, lo: int, hi: int) -> None:
        self._indeterminate = hi <= lo
        if self._indeterminate:
            if self._anim.state() != QVariantAnimation.State.Running:
                self._anim.start()
        else:
            self._anim.stop()

    def setValue(self, v: int) -> None:
        if self._indeterminate or v <= 0:
            self._value = 0.0
        else:
            self._value = max(0.0, min(1.0, v / 100.0))
        self.update()

    def show(self) -> None:  # noqa: D102
        super().show()
        if self._indeterminate:
            self._anim.start()

    def hide(self) -> None:  # noqa: D102
        super().hide()
        self._anim.stop()

    def _on_tick(self, v: float) -> None:
        self._pos = float(v)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self._h / 2.0
        track = QColor(_token("surface-3", "#e2e5ea"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0.0, 0.0, self._w, self._h), r, r)

        accent = QColor(_token("accent", "#2563eb"))
        strong = QColor(_token("accent-strong", "#1d4ed8"))
        if self._indeterminate:
            # 光斑：约 1/3 宽，渐变透明→accent→透明，来回巡航
            span = self._w / 3.0
            cx = self._pos * (self._w + span) - span / 2.0
            x0 = max(0.0, cx - span / 2.0)
            x1 = min(self._w, cx + span / 2.0)
            if x1 > x0:
                g = QLinearGradient(x0, 0, x1, 0)
                c = QColor(accent)
                c.setAlpha(0)
                g.setColorAt(0.0, c)
                g.setColorAt(0.5, accent)
                c2 = QColor(accent)
                c2.setAlpha(0)
                g.setColorAt(1.0, c2)
                p.setBrush(g)
                p.drawRoundedRect(QRectF(x0, 0.0, x1 - x0, self._h), r, r)
        elif self._value > 0:
            fw = max(r * 2.0, self._w * self._value)
            g = QLinearGradient(0, 0, fw, 0)
            g.setColorAt(0.0, strong)
            g.setColorAt(1.0, accent)
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0.0, 0.0, fw, self._h), r, r)
        p.end()


def _rounded(pm: QPixmap, size: int, radius: int) -> QPixmap:
    if pm.isNull():
        return pm
    target = pm.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, target)
    p.end()
    return out


def _placeholder_cover(px: int = 20, color: str = "#94a3b8") -> QPixmap:
    """封面占位：IMAGE 矢量图标（无字体依赖）."""
    return vector_pixmap(ICON.IMAGE, px, color)


class BottomBar(QWidget):
    apply_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bottomBar")
        self.setFixedHeight(48)
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 6, 16, 6)
        root.setSpacing(12)

        # 左：封面 + 标题
        left_wrap = QWidget()
        ll = QHBoxLayout(left_wrap)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)

        self._cover = QLabel()
        self._cover.setObjectName("nowPlayingCover")
        self._cover.setFixedSize(32, 32)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setPixmap(_placeholder_cover(20, _token("text-tertiary", "#94a3b8")))
        ll.addWidget(self._cover)

        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 2, 0, 2)
        self._title = QLabel("未选择主题")
        self._title.setObjectName("nowPlayingTitle")
        col.addWidget(self._title)
        self._sub = QLabel("从侧边栏或网格中选择一个主题以预览")
        self._sub.setObjectName("nowPlayingSub")
        col.addWidget(self._sub)
        ll.addLayout(col)
        root.addWidget(left_wrap, 1)

        # 中：状态 + 进度
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(3)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress = ProgressPill(width=260, height=6)
        self._progress.setVisible(False)
        cl.addWidget(self._progress, 0, Qt.AlignmentFlag.AlignHCenter)
        self._status = QLabel("就绪")
        self._status.setObjectName("bottomStatus")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self._status)
        root.addWidget(center, 1)

        # 右：应用按钮
        self._apply_btn = QPushButton("应用到系统")
        self._apply_btn.setObjectName("primaryBtn")
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.setMinimumHeight(32)
        self._apply_btn.setMinimumWidth(120)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self.apply_requested.emit)
        root.addWidget(self._apply_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def set_now_playing(self, theme: Optional[Theme], theme_dir=None) -> None:
        if theme is None:
            self._title.setText("未选择主题")
            self._sub.setText("从侧边栏或网格中选择一个主题以预览")
            self._cover.setPixmap(
                _placeholder_cover(20, _token("text-tertiary", "#94a3b8"))
            )
            self._apply_btn.setEnabled(False)
            return
        self._title.setText(theme.display_name)
        count = len(theme.cursor_files) if theme.cursor_files else 0
        complete = "完整套装" if theme.is_complete() else f"{count}/15  部分"
        self._sub.setText(f"{count} 个光标  ·  {complete}")
        self._apply_btn.setEnabled(bool(theme.cursor_files))
        pm = QPixmap()
        if theme_dir and (theme_dir / "preview.png").exists():
            pm = QPixmap(str(theme_dir / "preview.png"))
        if not pm.isNull():
            self._cover.setPixmap(_rounded(pm, 32, 6))
        else:
            self._cover.setPixmap(
                _placeholder_cover(20, _token("text-tertiary", "#94a3b8"))
            )

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def show_progress(self, on: bool) -> None:
        self._progress.setVisible(on)

    def set_progress(self, value: int, total: int) -> None:
        if total > 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(int(value * 100 / total))
        else:
            self._progress.setRange(0, 0)
