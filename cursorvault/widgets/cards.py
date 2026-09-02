# -*- coding: utf-8 -*-
"""卡片组件 v4 - Fluent 画廊卡片.

改进：
- 216px 宽度，封面对角圆角 8，与卡片圆角 12 解耦
- 封面占 4:3，留白更大，信息层级更清晰
- 徽标用描边弱化，不再高饱和
- hover 仅改变边框，不改底色跳变
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models import Theme
from ..ui_theme import token as _token
from ..zhutix_client import ZhutixPack
from .vector_icons import ICON, set_button_icon, vector_pixmap


def _rounded_pixmap(pm: QPixmap, w: int, h: int, radius: int = 8) -> QPixmap:
    if pm.isNull():
        return pm
    target = pm.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    # 居中裁剪
    cw = min(target.width(), w)
    ch = min(target.height(), h)
    x = (target.width() - cw) // 2
    y = (target.height() - ch) // 2
    target = target.copy(x, y, cw, ch)
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, target)
    p.end()
    return out


class CoverWidget(QWidget):
    """封面：带占位符 + 右下角悬浮操作."""

    action_clicked = pyqtSignal()

    def __init__(self, w: int = 188, h: int = 124, radius: int = 8, parent=None):
        super().__init__(parent)
        self._w = w
        self._h = h
        self._radius = radius
        self.setFixedSize(w, h)

        self._img = QLabel(self)
        self._img.setFixedSize(w, h)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setStyleSheet(
            f"background: rgba(148,163,184,0.14); border-radius: {radius}px; color: #94a3b8;"
        )
        self._img.setPixmap(
            vector_pixmap(
                ICON.IMAGE,
                int(w * 0.32),
                _token("text-tertiary", "#94a3b8"),
            )
        )
        self._img.lower()

        self._dim = QWidget(self)
        self._dim.setFixedSize(w, h)
        self._dim.setStyleSheet(f"background: rgba(15,23,42,0.04); border-radius: {radius}px;")
        self._dim.hide()

        self._btn = QPushButton(self)
        self._btn.setObjectName("coverAction")
        self._btn.setFixedSize(36, 36)
        self._btn.setIconSize(QSize(20, 20))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.hide()
        self._btn.clicked.connect(self.action_clicked.emit)

    def set_pixmap(self, pm: Optional[QPixmap]) -> None:
        if pm and not pm.isNull():
            rounded = _rounded_pixmap(pm, self._w, self._h, self._radius)
            self._img.setPixmap(rounded)
            self._img.setStyleSheet(f"background: transparent; border-radius: {self._radius}px;")
        else:
            self._img.setPixmap(
                vector_pixmap(
                    ICON.IMAGE,
                    int(self._w * 0.32),
                    _token("text-tertiary", "#94a3b8"),
                )
            )
            self._img.setStyleSheet(
                f"background: rgba(148,163,184,0.14); border-radius: {self._radius}px;"
            )

    def set_action_icon(self, name: str) -> None:
        """name 是 ICON.* 常量，对应 vector_icons.py 的图标名.

        封面动作按钮是 accent 实心圆底，所以图标用 accent-text；
        disabled 时 QSS 把底色换成 surface-2，图标相应跟着 text-tertiary。
        """
        set_button_icon(
            self._btn, name, size=20,
            role="accent-text", disabled_role="text-tertiary",
        )

    def set_action_enabled(self, enabled: bool) -> None:
        self._btn.setEnabled(enabled)

    def enterEvent(self, event) -> None:
        self._btn.move(self._w - 36 - 8, self._h - 36 - 8)
        self._btn.raise_()
        self._dim.show()
        self._dim.raise_()
        self._btn.raise_()
        self._btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._btn.hide()
        self._dim.hide()
        super().leaveEvent(event)


class SkeletonCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("skeletonCard")
        self.setFixedSize(216, 260)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        # cover placeholder
        box = QFrame()
        box.setObjectName("skeletonBox")
        box.setFixedSize(192, 124)
        lay.addWidget(box)
        for w, h in ((140, 14), (100, 11), (60, 10)):
            b = QFrame()
            b.setObjectName("skeletonBox")
            b.setFixedSize(w, h)
            lay.addWidget(b)
        lay.addStretch()


class PackCard(QFrame):
    """在线素材卡片."""

    download_clicked = pyqtSignal(object)
    apply_clicked = pyqtSignal(str)

    CARD_W = 216
    COVER_W = 192
    COVER_H = 124

    def __init__(self, pack: ZhutixPack, installed: bool = False, parent=None):
        super().__init__(parent)
        self.pack = pack
        self._installed = installed
        self.setObjectName("packCard")
        self.setFixedSize(self.CARD_W, 260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self._cover = CoverWidget(self.COVER_W, self.COVER_H, radius=8)
        self._cover.set_action_icon(ICON.CHECK if self._installed else ICON.DOWNLOAD)
        # 只要未安装就保持可点：没有现成直链的包点击后会走后台解析
        # （详情页/文章页/b2 接口 5 级链路），禁用会让点击零反馈、
        # 且锁死那些实际能解析出直链的包。
        self._cover.set_action_enabled(not self._installed)
        self._cover.action_clicked.connect(lambda: self.download_clicked.emit(self.pack))
        lay.addWidget(self._cover)

        title = QLabel(self.pack.title)
        title.setObjectName("packTitle")
        title.setWordWrap(True)
        title.setMaximumHeight(36)
        lay.addWidget(title)

        # meta row: 日期 + 徽标
        sub = QHBoxLayout()
        sub.setSpacing(6)
        date = QLabel((self.pack.modified or "")[:10] or "—")
        date.setObjectName("packSubtitle")
        sub.addWidget(date)
        sub.addStretch()
        # 徽标只描述「有没有现成直链」，不影响按钮是否可点
        can_direct = bool(self.pack.has_direct_link or self.pack.download_url)
        if self._installed:
            tag = QLabel("已安装")
            tag.setObjectName("packBadge")
            tag.setProperty("tone", "installed")
        elif can_direct:
            tag = QLabel("可下载")
            tag.setObjectName("packBadge")
            tag.setProperty("tone", "accent")
        else:
            tag = QLabel("需 VIP")
            tag.setObjectName("packBadge")
            tag.setProperty("tone", "warn")
        sub.addWidget(tag)
        lay.addLayout(sub)
        lay.addStretch()

    def set_preview_pixmap(self, pm: QPixmap) -> None:
        self._cover.set_pixmap(pm)

    def set_downloading(self) -> None:
        self._cover.set_action_icon(ICON.MORE)
        self._cover.set_action_enabled(False)

    def reset_download_button(self) -> None:
        self._cover.set_action_icon(ICON.CHECK if self._installed else ICON.DOWNLOAD)
        self._cover.set_action_enabled(not self._installed)

    def set_installed_state(self) -> None:
        self._installed = True
        self._cover.set_action_icon(ICON.CHECK)
        self._cover.set_action_enabled(False)


class ThemeCard(QFrame):
    """本地主题卡片."""

    apply_clicked = pyqtSignal(str)
    view_clicked = pyqtSignal(str)

    CARD_W = 216
    COVER_W = 192
    COVER_H = 124

    def __init__(self, theme: Theme, preview_pixmap: Optional[QPixmap] = None, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("packCard")
        self.setFixedSize(self.CARD_W, 260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build(preview_pixmap)

    def _build(self, pm: Optional[QPixmap]) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self._cover = CoverWidget(self.COVER_W, self.COVER_H, radius=8)
        self._cover.set_action_icon(ICON.CHECK)
        self._cover.action_clicked.connect(lambda: self.apply_clicked.emit(self.theme.name))
        if pm and not pm.isNull():
            self._cover.set_pixmap(pm)
        lay.addWidget(self._cover)

        title = QLabel(self.theme.display_name)
        title.setObjectName("packTitle")
        title.setWordWrap(True)
        title.setMaximumHeight(36)
        lay.addWidget(title)

        sub = QHBoxLayout()
        sub.setSpacing(6)
        count = len(self.theme.cursor_files) if self.theme.cursor_files else 0
        meta = QLabel(f"{count}/15")
        meta.setObjectName("packSubtitle")
        sub.addWidget(meta)
        sub.addStretch()
        if self.theme.is_complete():
            tag = QLabel("完整")
            tag.setObjectName("packBadge")
            tag.setProperty("tone", "installed")
        else:
            tag = QLabel("部分")
            tag.setObjectName("packBadge")
            tag.setProperty("tone", "warn")
        sub.addWidget(tag)
        lay.addLayout(sub)
        lay.addStretch()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.view_clicked.emit(self.theme.name)
        super().mouseReleaseEvent(event)
