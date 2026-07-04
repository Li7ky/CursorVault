"""游标预览控件."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import (
    QPainter,
    QPixmap,
    QImage,
    QFont,
    QColor,
    QPaintEvent,
    QMouseEvent,
    QCursor,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGridLayout,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)

from .models import CursorType, CURSOR_CHINESE_NAMES, Theme
from .theme_manager import ThemeManager


def resolve_cursor_path(
    theme: Theme,
    cursor_type: CursorType,
    theme_dir: Optional[Path] = None,
) -> Optional[Path]:
    """解析主题中某类型游标的文件路径（.cur / .ani）."""
    if theme.cursor_files and cursor_type in theme.cursor_files:
        path = theme.cursor_files[cursor_type]
        if path and Path(path).exists():
            return Path(path)
    if theme_dir:
        for suffix in (".cur", ".ani"):
            candidate = Path(theme_dir) / f"{cursor_type.value}{suffix}"
            if candidate.exists():
                return candidate
    return None


def _get_cur_pixmap(
    cursor_file: Optional[Path],
    size: int = 64,
) -> Optional[QPixmap]:
    """通过 Win32 API 渲染 .cur 和 .ani 文件为 QPixmap."""
    if not cursor_file or not Path(cursor_file).exists():
        return None

    try:
        import win32gui
        import win32con
        import ctypes
        import struct

        path = str(Path(cursor_file))
        flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        try:
            hcursor = win32gui.LoadImage(0, path, win32con.IMAGE_CURSOR, 0, 0, flags)
        except Exception:
            return None

        if not hcursor:
            return None

        hdc = None
        memdc = None
        hbitmap = None
        old_bmp = None
        info = None

        try:
            info = win32gui.GetIconInfo(hcursor)
            # info: fIcon, xHotspot, yHotspot, hbmMask, hbmColor
            color_bmp = info[4] or info[3]
            if not color_bmp:
                return None
            bmp_info = win32gui.GetObject(color_bmp)
            actual_width = bmp_info.bmWidth
            actual_height = bmp_info.bmHeight
            if not info[4]:  # 仅掩码时高度翻倍
                actual_height = max(1, actual_height // 2)

            img = QImage(
                actual_width,
                actual_height,
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            img.fill(0)

            hdc = win32gui.GetDC(0)
            memdc = win32gui.CreateCompatibleDC(hdc)

            bmi = ctypes.create_string_buffer(40)
            ctypes.memmove(
                bmi,
                struct.pack(
                    "LllHHLLllLL",
                    40,
                    actual_width,
                    -actual_height,
                    1,
                    32,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ),
                40,
            )

            ppv_bits = ctypes.c_void_p()
            hbitmap = ctypes.windll.gdi32.CreateDIBSection(
                memdc, bmi, 0, ctypes.byref(ppv_bits), None, 0
            )
            if not hbitmap or not ppv_bits.value:
                return None

            old_bmp = win32gui.SelectObject(memdc, hbitmap)
            win32gui.DrawIconEx(
                memdc,
                0,
                0,
                hcursor,
                actual_width,
                actual_height,
                0,
                0,
                win32con.DI_NORMAL,
            )
            ctypes.memmove(
                int(img.bits()),
                ppv_bits.value,
                actual_width * actual_height * 4,
            )

            if img.isNull():
                return None

            return QPixmap.fromImage(img).scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        finally:
            if old_bmp is not None and memdc:
                win32gui.SelectObject(memdc, old_bmp)
            if hbitmap:
                win32gui.DeleteObject(hbitmap)
            if memdc:
                win32gui.DeleteDC(memdc)
            if hdc is not None:
                win32gui.ReleaseDC(0, hdc)
            try:
                win32gui.DestroyIcon(hcursor)
            except Exception:
                pass
            if info:
                if info[3]:
                    try:
                        win32gui.DeleteObject(info[3])
                    except Exception:
                        pass
                if info[4]:
                    try:
                        win32gui.DeleteObject(info[4])
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error loading cursor {cursor_file}: {e}")
        return None


def _is_animated_cursor(path: Optional[Path]) -> bool:
    return bool(path and Path(path).suffix.lower() == ".ani")


class AnimatedCursorLabel(QLabel):
    """大预览标签：对 .ani 做简易帧轮询刷新（Win32 当前帧）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cursor_path: Optional[Path] = None
        self._display_size = 144
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def set_cursor_file(self, path: Optional[Path], size: int = 144) -> None:
        self._timer.stop()
        self._cursor_path = Path(path) if path else None
        self._display_size = size
        self._refresh_frame()
        if _is_animated_cursor(self._cursor_path):
            self._timer.start(120)

    def stop_animation(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._refresh_frame()

    def _refresh_frame(self) -> None:
        if not self._cursor_path:
            self.clear()
            self.setText("🖱️")
            return
        pm = _get_cur_pixmap(self._cursor_path, self._display_size)
        if pm:
            self.setPixmap(pm)
            self.setText("")
        else:
            self.clear()
            self.setText("🖱️")


class CursorCard(QFrame):
    """单个游标类型的预览卡片."""

    def __init__(self, cursor_type: CursorType, parent=None):
        super().__init__(parent)
        self.cursor_type = cursor_type
        self._pixmap: Optional[QPixmap] = None
        self._size = 52
        self._missing = False

        self.setFixedSize(104, 112)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet(
            """
            CursorCard {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 6px;
            }
            CursorCard:hover {
                background: #eff6ff;
                border: 1px solid #93c5fd;
            }
            """
        )

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(12)
        self._shadow.setColor(QColor(15, 23, 42, 18))
        self._shadow.setOffset(0, 2)
        self.setGraphicsEffect(self._shadow)

    def set_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        self._pixmap = pixmap
        self._missing = pixmap is None
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._pixmap:
            pm = self._pixmap.scaled(
                self._size,
                self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - pm.width()) // 2
            painter.drawPixmap(x, 10, pm)
        else:
            painter.setPen(QColor("#cbd5e1"))
            painter.drawText(
                QRect(0, 10, self.width(), self._size),
                Qt.AlignmentFlag.AlignCenter,
                "—",
            )

        name = CURSOR_CHINESE_NAMES.get(self.cursor_type, self.cursor_type.value)
        painter.setPen(QColor("#475569" if self._pixmap else "#94a3b8"))
        font = QFont("Segoe UI", 8)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(
            QRect(0, self.height() - 24, self.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            name,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            parent = self.parent()
            while parent:
                if hasattr(parent, "show_large_preview"):
                    parent.show_large_preview(self.cursor_type)
                    break
                parent = parent.parent() if hasattr(parent, "parent") else None


class CursorGridPanel(QWidget):
    """游标类型网格面板（可选复用组件）."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_name: Optional[str] = None
        self._theme_manager: Optional[ThemeManager] = None
        self._cards: dict[CursorType, CursorCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._large_label = AnimatedCursorLabel()
        self._large_label.setFixedSize(160, 160)
        self._large_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._large_label.setStyleSheet(
            "background: #ffffff; border: 1px solid #e4e9f0; border-radius: 12px;"
        )

        large_wrapper = QHBoxLayout()
        large_wrapper.addStretch()
        large_wrapper.addWidget(self._large_label)
        large_wrapper.addStretch()

        self._type_name_label = QLabel("标准选择")
        self._type_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._type_name_label.setStyleSheet(
            "color: #1a2332; font-size: 14px; font-weight: 600;"
        )
        self._type_name_label.setVisible(False)

        layout.addLayout(large_wrapper)
        layout.addWidget(self._type_name_label)

        grid_widget = QWidget()
        self._grid_layout = QGridLayout(grid_widget)
        self._grid_layout.setSpacing(8)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(grid_widget)

    def load_theme(self, theme_name: str, theme_manager: ThemeManager) -> None:
        self._theme_name = theme_name
        self._theme_manager = theme_manager

        for card in self._cards.values():
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        theme = theme_manager.get_theme(theme_name)
        if not theme:
            return

        cols = 5
        for i, cursor_type in enumerate(CursorType):
            card = CursorCard(cursor_type)
            cursor_file = theme_manager.get_cursor_file(theme_name, cursor_type)
            if cursor_file:
                pm = _get_cur_pixmap(cursor_file, 48)
                card.set_pixmap(pm)
            else:
                card.set_pixmap(None)
            self._grid_layout.addWidget(card, i // cols, i % cols)
            self._cards[cursor_type] = card

        self.show_large_preview(CursorType.ARROW)

    def show_large_preview(self, cursor_type: CursorType) -> None:
        if not self._theme_manager or not self._theme_name:
            return
        cursor_file = self._theme_manager.get_cursor_file(self._theme_name, cursor_type)
        self._large_label.set_cursor_file(cursor_file, 128)
        name = CURSOR_CHINESE_NAMES.get(cursor_type, cursor_type.value)
        self._type_name_label.setText(name)
        self._type_name_label.setVisible(True)


class CursorGalleryWidget(QWidget):
    """游标画廊：显示主题的所有游标预览（无内层滚动，交给外层）."""

    def __init__(self, theme: Theme, theme_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._theme_dir = Path(theme_dir) if theme_dir else None
        self._large_type: Optional[CursorType] = None
        self._cards: dict[CursorType, CursorCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 16)
        layout.setSpacing(14)

        # 大预览
        large_wrapper = QHBoxLayout()
        large_wrapper.addStretch()

        large_container = QFrame()
        large_container.setObjectName("galleryLargeFrame")
        large_container.setStyleSheet(
            """
            QFrame#galleryLargeFrame {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
            """
        )
        large_container_layout = QVBoxLayout(large_container)
        large_container_layout.setContentsMargins(18, 16, 18, 14)
        large_container_layout.setSpacing(10)

        self._large_label = AnimatedCursorLabel()
        self._large_label.setFixedSize(188, 188)
        self._large_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._large_label.setStyleSheet(
            "background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px;"
        )
        self._large_label.setToolTip("点击下方卡片切换大预览；.ani 会自动刷新")
        large_container_layout.addWidget(
            self._large_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self._type_name_label = QLabel("标准选择")
        self._type_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._type_name_label.setStyleSheet(
            "color: #2563eb; font-size: 14px; font-weight: 700; background: transparent;"
        )
        self._type_name_label.setVisible(False)
        large_container_layout.addWidget(self._type_name_label)

        large_wrapper.addWidget(large_container)
        large_wrapper.addStretch()
        layout.addLayout(large_wrapper)

        header = QLabel(
            f"{theme.display_name}  ·  共 {len(theme.cursor_files)} / {len(CursorType)} 个光标"
        )
        header.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600; padding: 4px 2px;"
        )
        layout.addWidget(header)

        grid_widget = QWidget()
        grid_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._grid = QGridLayout(grid_widget)
        self._grid.setSpacing(8)
        self._grid.setContentsMargins(0, 0, 0, 0)

        cols = 6
        for i, cursor_type in enumerate(CursorType):
            card = CursorCard(cursor_type)
            path = resolve_cursor_path(theme, cursor_type, self._theme_dir)
            pm = _get_cur_pixmap(path, 52) if path else None
            card.set_pixmap(pm)
            self._grid.addWidget(card, i // cols, i % cols)
            self._cards[cursor_type] = card

        layout.addWidget(grid_widget)
        layout.addStretch(1)

        self.show_large_preview(CursorType.ARROW)

    def show_large_preview(self, cursor_type: CursorType) -> None:
        self._large_type = cursor_type
        path = resolve_cursor_path(self._theme, cursor_type, self._theme_dir)
        self._large_label.set_cursor_file(path, 144)
        name = CURSOR_CHINESE_NAMES.get(cursor_type, cursor_type.value)
        suffix = "（动画）" if _is_animated_cursor(path) else ""
        self._type_name_label.setText(f"{name}{suffix}")
        self._type_name_label.setVisible(True)

    def cleanup(self) -> None:
        self._large_label.stop_animation()
