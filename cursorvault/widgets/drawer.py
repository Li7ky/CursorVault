# -*- coding: utf-8 -*-
"""右侧详情抽屉 v4 - 380px Fluent 详情面板."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter as _perf_counter
from typing import Optional

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..cursor_preview import _get_cur_pixmap
from ..models import CursorType, CURSOR_CHINESE_NAMES, Theme
from ..theme_manager import ThemeManager
from ..ui_theme import token as _token
from .vector_icons import ICON, set_button_icon, vector_pixmap


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


class _CursorMiniCard(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, cursor_type: CursorType, parent=None):
        super().__init__(parent)
        self.cursor_type = cursor_type
        self.setObjectName("cursorCard")
        self.setFixedSize(66, 76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 4)
        lay.setSpacing(2)
        self._img = QLabel()
        self._img.setFixedSize(42, 42)
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._img, alignment=Qt.AlignmentFlag.AlignCenter)
        name = CURSOR_CHINESE_NAMES.get(cursor_type, cursor_type.value)
        short = name[:4] if len(name) > 4 else name
        n = QLabel(short)
        n.setObjectName("cursorCardName")
        n.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(n)

    def set_path(self, path: Optional[Path]) -> None:
        if path:
            pm = _get_cur_pixmap(path, 42)
            if pm:
                self._img.setPixmap(pm)
                self._img.setText("")
                return
        self._img.clear()
        self._img.setText("—")
        self._img.setStyleSheet("color: #94a3b8; font-size: 14px; background: transparent;")

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.cursor_type)
        super().mouseReleaseEvent(event)


class DetailDrawer(QWidget):
    apply_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailDrawer")
        # 关键：自定义 QWidget 子类必须开启此属性，否则 QSS 背景/边框不会绘制，
        # 抽屉会变透明，顶栏与底栏内容会透过抽屉显示（叠字、串色）
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(380)
        self.hide()
        self._theme: Optional[Theme] = None
        self._theme_dir: Optional[Path] = None
        self._active_cursor: Optional[CursorType] = None
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(self._load_next_batch)
        self._pending_queue: list[tuple[CursorType, Optional[Path]]] = []
        self._load_gen = 0
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(20, 16, 16, 12)
        tl.setSpacing(10)

        head_row = QHBoxLayout()
        head_row.setSpacing(12)
        head_row.addStretch()
        close = QPushButton()
        close.setObjectName("ghostBtn")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFixedSize(32, 32)
        close.setIconSize(QSize(18, 18))
        set_button_icon(close, ICON.CLOSE, size=18, role="icon-neutral")
        close.clicked.connect(self._close)
        head_row.addWidget(close)
        tl.addLayout(head_row)

        self._eyebrow = QLabel("主题详情")
        self._eyebrow.setObjectName("drawerEyebrow")
        tl.addWidget(self._eyebrow)

        self._title = QLabel("主题")
        self._title.setObjectName("drawerTitle")
        self._title.setWordWrap(True)
        tl.addWidget(self._title)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("drawerSubtitle")
        meta_row.addWidget(self._subtitle)
        meta_row.addStretch()
        self._count_tag = QLabel("")
        self._count_tag.setObjectName("packBadge")
        meta_row.addWidget(self._count_tag)
        self._complete_tag = QLabel("")
        self._complete_tag.setObjectName("packBadge")
        meta_row.addWidget(self._complete_tag)
        tl.addLayout(meta_row)

        self._cover = QLabel()
        self._cover.setObjectName("drawerCover")
        self._cover.setFixedSize(340, 148)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tl.addWidget(self._cover)

        root.addWidget(top)

        # 滚动内容
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(20, 8, 20, 12)
        il.setSpacing(14)

        # 大预览
        self._large_frame = QFrame()
        self._large_frame.setObjectName("cursorLargeFrame")
        lf = QVBoxLayout(self._large_frame)
        lf.setContentsMargins(16, 18, 16, 14)
        lf.setSpacing(8)
        lf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._large_img = QLabel()
        self._large_img.setFixedSize(120, 120)
        self._large_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lf.addWidget(self._large_img, alignment=Qt.AlignmentFlag.AlignCenter)
        self._large_name = QLabel("标准选择")
        self._large_name.setObjectName("cursorLargeName")
        self._large_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lf.addWidget(self._large_name)
        il.addWidget(self._large_frame)

        section_title = QLabel("全部光标  ·  点击切换预览")
        section_title.setObjectName("drawerEyebrow")
        il.addWidget(section_title)

        grid_wrap = QWidget()
        gl = QGridLayout(grid_wrap)
        gl.setSpacing(6)
        gl.setContentsMargins(0, 0, 0, 0)
        cols = 5
        self._mini_cards: dict[CursorType, _CursorMiniCard] = {}
        for i, ct in enumerate(CursorType):
            c = _CursorMiniCard(ct)
            c.clicked.connect(self._show_large)
            gl.addWidget(c, i // cols, i % cols)
            self._mini_cards[ct] = c
        il.addWidget(grid_wrap)
        il.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # 底部操作
        action = QWidget()
        al = QVBoxLayout(action)
        al.setContentsMargins(16, 12, 16, 16)
        al.setSpacing(8)

        self._apply_btn = QPushButton("应用到系统")
        self._apply_btn.setObjectName("primaryBtn")
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.setMinimumHeight(40)
        self._apply_btn.clicked.connect(self._on_apply)
        al.addWidget(self._apply_btn)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setObjectName("dangerBtn")
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setMinimumHeight(36)
        self._delete_btn.clicked.connect(self._on_delete)
        row.addWidget(self._delete_btn)
        al.addLayout(row)
        root.addWidget(action)

    def show_theme(
        self,
        theme: Theme,
        theme_dir: Optional[Path],
        theme_manager: ThemeManager,
    ) -> None:
        self._theme = theme
        self._theme_dir = theme_dir
        self._title.setText(theme.display_name)
        count = len(theme.cursor_files) if theme.cursor_files else 0
        self._count_tag.setText(f"{count}/15")
        self._count_tag.setProperty("tone", "installed" if theme.is_complete() else "")
        self._count_tag.style().unpolish(self._count_tag)
        self._count_tag.style().polish(self._count_tag)

        self._complete_tag.setText("完整" if theme.is_complete() else "部分")
        self._complete_tag.setProperty("tone", "installed" if theme.is_complete() else "warn")
        self._complete_tag.style().unpolish(self._complete_tag)
        self._complete_tag.style().polish(self._complete_tag)

        self._subtitle.setText("在线主题" if theme.source_url else "本地导入")

        self._apply_btn.setEnabled(bool(theme.cursor_files))

        pm = QPixmap()
        if theme_dir and (theme_dir / "preview.png").exists():
            pm = QPixmap(str(theme_dir / "preview.png"))
        if not pm.isNull():
            self._cover.setPixmap(_rounded(pm, 148, 12))
        else:
            self._cover.setPixmap(
                vector_pixmap(ICON.IMAGE, 56, _token("text-tertiary", "#94a3b8"))
            )

        # 先重置为占位，异步分批加载真实位图，避免一次性 15 次 GDI 阻塞 UI
        self._load_gen += 1
        self._load_timer.stop()
        self._pending_queue.clear()
        for ct, card in self._mini_cards.items():
            card.set_path(None)
            card.set_active(False)
            path = theme.cursor_files.get(ct) if theme.cursor_files else None
            if not path and theme_dir:
                for suf in (".cur", ".ani"):
                    p = theme_dir / f"{ct.value}{suf}"
                    if p.exists():
                        path = p
                        break
            self._pending_queue.append((ct, path))
        self.show()
        self.raise_()
        # 大预览也是一次 GDI 调用（冷缓存约 4ms），放在 show() 之后，
        # 让抽屉先画出骨架再补内容，避免整块面板延迟出现
        self._show_large(CursorType.ARROW)
        # 下一帧开始分批加载
        self._load_timer.start(0)

    def _load_next_batch(self) -> None:
        if not self.isVisible() or not self._pending_queue:
            return
        gen = self._load_gen
        # 按「时间预算」而不是固定个数切批：缓存命中时几乎 0ms，可以一口气做完；
        # 冷缓存时每次 GDI 渲染 3–6ms，跑满 8ms 就把剩余部分让给下一帧，
        # 保证单帧不会超过 60fps 的预算（16.7ms）。
        budget_ms = 8.0
        deadline = _perf_counter() + budget_ms / 1000.0
        processed = 0
        while self._pending_queue and processed < 6:
            ct, path = self._pending_queue.pop(0)
            card = self._mini_cards.get(ct)
            if card:
                card.set_path(path)
            processed += 1
            if _perf_counter() >= deadline:
                break
        if self._pending_queue and gen == self._load_gen:
            self._load_timer.start(16)

    def _show_large(self, ct: CursorType) -> None:
        if not self._theme:
            return
        if self._active_cursor is not None and self._active_cursor in self._mini_cards:
            self._mini_cards[self._active_cursor].set_active(False)
        self._active_cursor = ct
        if ct in self._mini_cards:
            self._mini_cards[ct].set_active(True)

        path = None
        if self._theme.cursor_files:
            path = self._theme.cursor_files.get(ct)
        if not path and self._theme_dir:
            for suf in (".cur", ".ani"):
                p = self._theme_dir / f"{ct.value}{suf}"
                if p.exists():
                    path = p
                    break
        if path:
            pm = _get_cur_pixmap(path, 120)
            if pm:
                self._large_img.setPixmap(pm)
                self._large_img.setText("")
            else:
                self._large_img.clear()
                self._large_img.setText("—")
                self._large_img.setStyleSheet("color: #94a3b8; font-size: 18px;")
        else:
            self._large_img.clear()
            self._large_img.setText("—")
            self._large_img.setStyleSheet("color: #94a3b8; font-size: 18px;")
        name = CURSOR_CHINESE_NAMES.get(ct, ct.value)
        suffix = ""
        if path and path.suffix.lower() == ".ani":
            suffix = "  ·  动画"
        self._large_name.setText(f"{name}{suffix}")

    def _on_apply(self) -> None:
        if self._theme:
            self.apply_requested.emit(self._theme.name)

    def _on_delete(self) -> None:
        if self._theme:
            self.delete_requested.emit(self._theme.name)

    def _close(self) -> None:
        self.hide()
        self.closed.emit()
