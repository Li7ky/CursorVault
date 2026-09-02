# -*- coding: utf-8 -*-
"""侧边栏 v4 - 260px Fluent 导航面板.

结构：
  Brand (icon + title)
  Nav Section (在线/本地 + 数量)
  Separator
  已安装主题列表（可滚动）
  Spacer
  工具行 + 版本
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from .vector_icons import ICON, set_button_icon, set_label_icon


class _ClickLabel(QLabel):
    """带点击信号的 QLabel（供工具文字标签复用按钮行为）."""

    clicked = pyqtSignal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)

    def mousePressEvent(self, event) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ThemeItem(QWidget):
    activated = pyqtSignal(str)

    def __init__(self, name: str, display: str, count_text: str, parent=None):
        super().__init__(parent)
        self._name = name
        self.setObjectName("themeListItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        # 小色块代替图标
        dot = QLabel("◆")
        dot.setStyleSheet("font-size: 8px; color: #94a3b8; background: transparent; border: none;")
        dot.setFixedWidth(12)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(dot)

        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(display)
        t.setObjectName("themeItemTitle")
        # truncated
        t.setMaximumWidth(150)
        col.addWidget(t)
        s = QLabel(count_text)
        s.setObjectName("themeItemSub")
        col.addWidget(s)
        lay.addLayout(col, 1)

        badge = QLabel(count_text.split("·")[-1].strip() if "·" in count_text else count_text)
        badge.setObjectName("themeItemBadge")
        lay.addWidget(badge)

    def set_active(self, on: bool) -> None:
        self.setProperty("active", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._name)
        super().mouseReleaseEvent(event)


class Sidebar(QWidget):
    """左侧 260px 导航 + 已装主题列表."""

    nav_changed = pyqtSignal(str)  # "online" | "local"
    theme_activated = pyqtSignal(str)
    backup_requested = pyqtSignal()
    restore_requested = pyqtSignal()
    refresh_cursors_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(260)
        self._themes_cache: list = []
        self._active_nav = "online"
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(0)

        # ── Brand ──
        brand = QWidget()
        brand.setObjectName("sidebarBrand")
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(4, 2, 4, 10)
        bl.setSpacing(10)
        self._brand_icon = QLabel()
        self._brand_icon.setObjectName("brandIcon")
        self._brand_icon.setFixedSize(32, 32)
        self._brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self._brand_icon)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 0, 0, 0)
        title = QLabel("CursorVault")
        title.setObjectName("brandTitle")
        col.addWidget(title)
        sub = QLabel(f"鼠标素材库  v{__version__}")
        sub.setObjectName("brandSubtitle")
        col.addWidget(sub)
        bl.addLayout(col, 1)
        root.addWidget(brand)
        # 品牌图标在 accent 蓝底上（QSS #brandIcon background: accent），必须用 accent-text
        set_label_icon(self._brand_icon, ICON.CURSOR, size=28, role="accent-text")

        # ── 导航区 ──
        sec = QLabel("浏览")
        sec.setObjectName("navSectionLabel")
        sec.setContentsMargins(6, 8, 0, 8)
        root.addWidget(sec)

        self._nav_btns: dict[str, QPushButton] = {}
        self._nav_counts: dict[str, QLabel] = {}
        nav_wrap = QVBoxLayout()
        nav_wrap.setSpacing(4)
        nav_icon_map = {"online": ICON.GLOBE, "local": ICON.FOLDER, "queue": ICON.DOWNLOAD}
        nav_role_map = {
            "online": "icon-globe",
            "local": "icon-folder",
            "queue": "icon-download",
        }
        for key, label in (
            ("online", "在线素材库"),
            ("local", "本地主题"),
            ("queue", "下载队列"),
        ):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)
            btn = QPushButton(f"  {label}")
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.setIconSize(QSize(18, 18))
            set_button_icon(btn, nav_icon_map[key], size=18, role=nav_role_map[key])
            btn.clicked.connect(lambda _, k=key: self._on_nav(k))
            rl.addWidget(btn, 1)
            count = QLabel("")
            count.setObjectName("navCount")
            count.setVisible(False)
            rl.addWidget(count)
            count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            nav_wrap.addWidget(row)
            self._nav_btns[key] = btn
            self._nav_counts[key] = count
        root.addLayout(nav_wrap)
        self._nav_btns["online"].setChecked(True)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setObjectName("sidebarSep")
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addSpacing(14)
        root.addWidget(sep)
        root.addSpacing(14)

        # ── 已装主题区 ──
        list_head = QHBoxLayout()
        list_head.setContentsMargins(6, 0, 6, 8)
        list_head.setSpacing(6)
        lh_label = QLabel("已安装")
        lh_label.setObjectName("navSectionLabel")
        list_head.addWidget(lh_label)
        list_head.addStretch()
        self._installed_count = QLabel("0")
        self._installed_count.setObjectName("navCount")
        list_head.addWidget(self._installed_count)
        root.addLayout(list_head)

        # 滚动列表
        self._scroll = QScrollArea()
        self._scroll.setObjectName("sidebarScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 4, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._empty_label = QLabel("暂无主题\n去在线库下载或导入本地")
        self._empty_label.setObjectName("emptySub")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #94a3b8; font-size: 12px; padding: 16px 8px; background: transparent;")
        self._list_layout.addWidget(self._empty_label)
        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, 1)

        # ── 工具行（带文字标签）──
        tools_label = QLabel("系统工具")
        tools_label.setObjectName("navSectionLabel")
        tools_label.setContentsMargins(6, 12, 0, 8)
        root.addWidget(tools_label)

        tools = QHBoxLayout()
        tools.setContentsMargins(2, 0, 2, 0)
        tools.setSpacing(6)

        def _make_tool(name: str, tooltip: str, signal) -> QWidget:
            cell = QWidget()
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(4)
            cl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            btn = QPushButton()
            btn.setObjectName("sidebarToolBtn")
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(QSize(44, 44))
            btn.setIconSize(QSize(20, 20))
            cl.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            lbl = _ClickLabel(name)
            lbl.setObjectName("toolLabel")
            lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lbl.clicked.connect(btn.click)
            cl.addWidget(lbl)
            cell._btn = btn  # type: ignore
            return cell

        backup_cell = _make_tool("备份", "备份当前游标", self.backup_requested.emit)
        restore_cell = _make_tool("恢复", "恢复游标", self.restore_requested.emit)
        refresh_cell = _make_tool("刷新", "刷新系统游标", self.refresh_cursors_requested.emit)
        set_button_icon(backup_cell._btn, ICON.SAVE, size=20, role="icon-save")  # type: ignore
        set_button_icon(restore_cell._btn, ICON.RESTORE, size=20, role="icon-restore")  # type: ignore
        set_button_icon(refresh_cell._btn, ICON.REFRESH, size=20, role="icon-refresh")  # type: ignore
        self._backup_btn = backup_cell._btn  # type: ignore
        self._restore_btn = restore_cell._btn  # type: ignore
        self._refresh_btn = refresh_cell._btn  # type: ignore

        for cell in (backup_cell, restore_cell, refresh_cell):
            tools.addWidget(cell)
        tools.addStretch()
        root.addLayout(tools)

    # ── 公共接口 ──
    def select_view(self, key: str) -> None:
        if key not in self._nav_btns:
            return
        for k, b in self._nav_btns.items():
            b.setChecked(k == key)
        self._active_nav = key
        self.nav_changed.emit(key)

    def _on_nav(self, key: str) -> None:
        for k, b in self._nav_btns.items():
            b.setChecked(k == key)
        self._active_nav = key
        self.nav_changed.emit(key)

    def set_queue_count(self, count: int) -> None:
        """下载队列导航徽标：进行中的任务数，0 隐藏."""
        badge = self._nav_counts.get("queue")
        if badge is None:
            return
        if count > 0:
            badge.setText(str(count))
            badge.setVisible(True)
        else:
            badge.setVisible(False)

    def refresh_themes(self, themes) -> None:
        self._themes_cache = list(themes)
        # 更新导航计数
        cnt = len(self._themes_cache)
        self._installed_count.setText(str(cnt))
        # 重建列表项
        # 清理旧
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self._themes_cache:
            self._empty_label = QLabel("暂无主题\n去在线库下载或导入本地")
            self._empty_label.setObjectName("emptySub")
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._empty_label.setStyleSheet("color: #94a3b8; font-size: 12px; padding: 16px 8px; background: transparent;")
            self._list_layout.addWidget(self._empty_label)
            # 隐藏本地计数徽标
            self._nav_counts["local"].setVisible(False)
        else:
            for th in self._themes_cache:
                count = len(th.cursor_files) if getattr(th, "cursor_files", None) else 0
                sub = f"{count}/15  ·  {'完整' if getattr(th, 'is_complete', lambda: False)() else '部分'}"
                item = _ThemeItem(th.name, th.display_name, sub)
                item.activated.connect(self.theme_activated.emit)
                self._list_layout.addWidget(item)
            self._list_layout.addStretch(1)
            self._nav_counts["local"].setText(str(cnt))
            self._nav_counts["local"].setVisible(True)
        # 更新按钮角标
        self._nav_counts["local"].setProperty("active", "true" if self._active_nav == "local" else "false")
        self._nav_counts["local"].style().unpolish(self._nav_counts["local"])
        self._nav_counts["local"].style().polish(self._nav_counts["local"])
