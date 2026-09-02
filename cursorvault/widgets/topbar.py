# -*- coding: utf-8 -*-
"""顶栏 v4 - 56px Fluent 命令栏.

左侧：页面标题 + 副标题（由 MainWindow 驱动）
中部：搜索框（带放大镜前缀）
右侧：导入主按钮 + 次级图标按钮
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..ui_theme import token as _token
from .vector_icons import ICON, set_button_icon, vector_icon, vector_pixmap


class TopBar(QWidget):
    """顶栏：标题区 + 搜索 + 操作."""

    search_changed = pyqtSignal(str)
    theme_toggle_requested = pyqtSignal()
    update_check_requested = pyqtSignal()
    import_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(56)
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 8, 16, 8)
        root.setSpacing(16)

        # ── 左：标题区 ──
        title_wrap = QWidget()
        tv = QVBoxLayout(title_wrap)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(1)
        self._title = QLabel("在线素材库")
        self._title.setObjectName("topBarTitle")
        tv.addWidget(self._title)
        self._sub = QLabel("浏览并下载 Windows 光标主题")
        self._sub.setObjectName("topBarSub")
        tv.addWidget(self._sub)
        root.addWidget(title_wrap, 0)

        root.addStretch(1)

        # ── 中：搜索 ──
        search_wrap = QWidget()
        search_wrap.setFixedWidth(320)
        sw = QHBoxLayout(search_wrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(0)
        self._search = QLineEdit()
        self._search.setObjectName("searchBox")
        self._search.setPlaceholderText("搜索主题名称…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(36)
        # 用 LeadingPosition 加图标
        self._search.addAction(
            QIcon(vector_pixmap(ICON.SEARCH, 16, _token("text-tertiary", "#94a3b8"))),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search.textChanged.connect(self.search_changed.emit)
        sw.addWidget(self._search)
        root.addWidget(search_wrap)

        # ── 右：操作 ──
        # 导入主按钮（带导入图标）
        self._import_btn = QPushButton("  导入主题")
        self._import_btn.setObjectName("topPrimaryBtn")
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.setToolTip("从本地文件夹导入 .cur / .ani")
        self._import_btn.setIconSize(QSize(18, 18))
        # 蓝底主按钮 → 图标用 accent-text（亮色下是白、暗色下是近黑）
        set_button_icon(
            self._import_btn, ICON.IMPORT, size=18,
            role="accent-text", disabled_role="accent-text",
        )
        self._import_btn.clicked.connect(self.import_requested.emit)
        root.addWidget(self._import_btn)

        # 分隔细线（用 QWidget 模拟，颜色跟随主题令牌）
        sep = QWidget()
        sep.setFixedSize(1, 20)
        sep.setStyleSheet(f"background: {_token('border-subtle', '#e8eaef')};")
        root.addWidget(sep)

        # 明暗切换（默认亮色图标，暗色时切换）
        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("topActionBtn")
        self._theme_btn.setToolTip("切换明/暗主题")
        self._theme_btn.setCheckable(True)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setFixedSize(QSize(36, 36))
        self._theme_btn.setIconSize(QSize(20, 20))
        set_button_icon(self._theme_btn, ICON.SUN, size=20)
        self._theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        root.addWidget(self._theme_btn)

        # 检查更新
        self._update_btn = QPushButton()
        self._update_btn.setObjectName("topActionBtn")
        self._update_btn.setToolTip("检查更新")
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.setFixedSize(QSize(36, 36))
        self._update_btn.setIconSize(QSize(20, 20))
        set_button_icon(self._update_btn, ICON.REFRESH, size=20, role="icon-refresh")
        self._update_btn.clicked.connect(self.update_check_requested.emit)
        root.addWidget(self._update_btn)

    # ── 公共接口 ──
    def set_page_info(self, title: str, subtitle: str = "") -> None:
        self._title.setText(title)
        if subtitle:
            self._sub.setText(subtitle)
            self._sub.setVisible(True)
        else:
            self._sub.setVisible(False)

    def search_text(self) -> str:
        return self._search.text().strip()

    def clear_search(self) -> None:
        self._search.clear()

    def set_dark(self, dark: bool) -> None:
        if hasattr(self, "_theme_btn"):
            self._theme_btn.setChecked(dark)
            # 切主题时更新图标：亮色 → 太阳，提示"点击进入暗色"；暗色 → 月亮
            if dark:
                set_button_icon(self._theme_btn, ICON.MOON, size=20)
            else:
                set_button_icon(self._theme_btn, ICON.SUN, size=20)
