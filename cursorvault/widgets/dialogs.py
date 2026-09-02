# -*- coding: utf-8 -*-
"""对话框与通知横幅 - Notion 风格克制."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ui_theme import token as _token
from .vector_icons import ICON, set_button_icon, set_label_icon, vector_pixmap


class UpdateDialog(QDialog):
    """发现新版本对话框."""

    def __init__(
        self,
        current_version: str,
        new_version: str,
        release_notes: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("customDialog")
        self.setWindowTitle("发现新版本")
        self.setFixedSize(440, 360)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self._setup(current_version, new_version, release_notes)

    def _setup(self, cur: str, new: str, notes: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(14)

        icon = QLabel()
        icon.setObjectName("dialogIcon")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(icon)
        # dialogIcon 的 QSS 底是 accent-soft，图标用刷新紫/蓝系保持一致观感
        set_label_icon(icon, ICON.REFRESH, size=28, role="icon-refresh")

        col = QVBoxLayout()
        col.setSpacing(6)
        title = QLabel("发现新版本")
        title.setStyleSheet(
            "font-size: 19px; font-weight: 700; color: #f5f6f8; background: transparent;"
        )
        col.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        old = QLabel(f"v{cur}")
        old.setStyleSheet("color: #7a8195; font-size: 12px; background: transparent;")
        row.addWidget(old)
        arrow = QLabel()
        arrow.setFixedSize(20, 20)
        arrow.setStyleSheet("color: #7a8195; background: transparent;")
        row.addWidget(arrow)
        set_label_icon(arrow, ICON.EXTERNAL, size=14, role="text-tertiary")
        tag = QLabel(f"v{new}")
        tag.setObjectName("packBadge")
        tag.setProperty("tone", "accent")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(tag)
        row.addStretch()
        col.addLayout(row)
        header.addLayout(col, 1)
        layout.addLayout(header)

        msg = QLabel(
            "新版本已发布，建议更新以获得更好的体验。\n"
            "更新包含新功能、修复和改进。"
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #b3b8c5; background: transparent; font-size: 13px;")
        layout.addWidget(msg)

        if notes:
            t = QLabel("更新说明")
            t.setStyleSheet(
                "color: #7a8195; font-weight: 700; font-size: 11px; "
                "letter-spacing: 1.2px; background: transparent;"
            )
            layout.addWidget(t)
            body = QLabel(notes[:300] + ("…" if len(notes) > 300 else ""))
            body.setWordWrap(True)
            body.setObjectName("dialogBodyBox")
            body.setMinimumHeight(60)
            body.setMaximumHeight(120)
            layout.addWidget(body)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        later = QPushButton("稍后再说")
        later.setObjectName("secondaryBtn")
        later.setCursor(Qt.CursorShape.PointingHandCursor)
        later.setMinimumHeight(38)
        later.clicked.connect(self.reject)
        btns.addWidget(later)

        upd = QPushButton("立即更新")
        upd.setObjectName("primaryBtn")
        upd.setCursor(Qt.CursorShape.PointingHandCursor)
        upd.setMinimumHeight(38)
        upd.clicked.connect(self.accept)
        btns.addWidget(upd)
        layout.addLayout(btns)


class NotificationBanner(QFrame):
    """顶部通知横幅."""

    closed = pyqtSignal()
    action_clicked = pyqtSignal()

    def __init__(self, message: str = "", action_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("notificationBanner")
        self._message = message
        self._action_text = action_text
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 16, 0)
        layout.setSpacing(12)

        icon = QLabel()
        icon.setObjectName("notificationText")
        icon.setFixedSize(20, 20)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        set_label_icon(icon, ICON.REFRESH, size=18, role="text-tertiary")

        self._msg = QLabel(self._message)
        self._msg.setObjectName("notificationText")
        self._msg.setWordWrap(True)
        layout.addWidget(self._msg, 1)

        if self._action_text:
            self._action_btn = QPushButton(self._action_text)
            self._action_btn.setObjectName("bannerAction")
            self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._action_btn.clicked.connect(self.action_clicked.emit)
            layout.addWidget(self._action_btn)

        close = QPushButton()
        close.setObjectName("ghostBtn")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(32, 32)
        close.setIconSize(QSize(16, 16))
        set_button_icon(close, ICON.CLOSE, size=16)
        close.clicked.connect(self._on_close)
        layout.addWidget(close)

    def _on_close(self) -> None:
        self.hide()
        self.closed.emit()

    def set_message(self, message: str) -> None:
        self._message = message
        self._msg.setText(message)

    def set_action_text(self, text: str) -> None:
        self._action_text = text
        if hasattr(self, "_action_btn"):
            self._action_btn.setText(text)


class SoftDialog(QDialog):
    """轻量俏皮提示卡：圆底图标 + 标题 + 说明 +「知道了」.

    用于替代系统 QMessageBox 提示（下载受限、网络失败等），
    视觉与 UpdateDialog 同一语言：soft 圆底图标、克制留白。
    """

    def __init__(
        self,
        title: str,
        body: str,
        parent=None,
        icon_name: str = ICON.LOCK,
        icon_role: str = "warning",
        icon_tone: str = "warning",
    ):
        super().__init__(parent)
        self.setObjectName("softDialog")
        self.setWindowTitle(title)
        self.setFixedWidth(432)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
        )
        self._build(title, body, icon_name, icon_role, icon_tone)

    def _build(
        self, title: str, body: str, icon_name: str, icon_role: str, icon_tone: str
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 22)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(14)

        icon = QLabel()
        icon.setObjectName("softIcon")
        # 圆底颜色随语义切换（warning/success/accent/error），QSS 按 tone 取 soft 色
        icon.setProperty("tone", icon_tone)
        icon.setFixedSize(46, 46)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(icon)
        set_label_icon(icon, icon_name, size=22, role=icon_role)

        col = QVBoxLayout()
        col.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("softTitle")
        t.setWordWrap(True)
        col.addWidget(t)
        head.addLayout(col, 1)
        root.addLayout(head)

        msg = QLabel(body)
        msg.setObjectName("softBody")
        msg.setWordWrap(True)
        root.addWidget(msg)

        root.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        ok = QPushButton("知道了")
        ok.setObjectName("secondaryBtn")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setMinimumHeight(36)
        ok.setMinimumWidth(96)
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        root.addLayout(btns)