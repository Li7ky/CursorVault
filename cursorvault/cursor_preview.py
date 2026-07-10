"""游标预览控件."""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSize, QRect, QTimer, QPoint
from PyQt6.QtGui import (
    QPainter, QPixmap, QImage, QFont, QColor, QPen, QBrush,
    QPaintEvent, QMouseEvent, QWheelEvent, QCursor, QAction,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QFrame, QScrollArea, QSizePolicy, QPushButton, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QToolTip,
)

from .models import CursorType, CURSOR_CHINESE_NAMES, HOTSPOT_MAP, Theme
from .theme_manager import ThemeManager


# ---------- 工具函数 ----------

def _get_cur_pixmap(
    cursor_file: Optional[Path],
    size: int = 64,
) -> Optional[QPixmap]:
    """通过 Win32 API 渲染 .cur 和 .ani 文件为 QPixmap."""
    if not cursor_file or not cursor_file.exists():
        return None

    try:
        import win32gui
        import win32con
        import ctypes
        import struct

        path = str(cursor_file)

        # Win32 LoadImage 会在文件不存在时抛出异常，但我们在前面已经拦截了
        flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        try:
            hcursor = win32gui.LoadImage(0, path, win32con.IMAGE_CURSOR, 0, 0, flags)
        except Exception:
            return None

        if not hcursor:
            return None

        # 获取光标的实际物理尺寸
        info = win32gui.GetIconInfo(hcursor)
        bmp_info = win32gui.GetObject(info[3])
        actual_width = bmp_info.bmWidth
        actual_height = bmp_info.bmHeight
        if info[4] == 0:  # 如果是黑白掩码，高度是两倍
            actual_height = actual_height // 2

        # 使用实际尺寸创建画布
        img = QImage(actual_width, actual_height, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0) # 填充为全透明

        hdc = win32gui.GetDC(0)
        memdc = win32gui.CreateCompatibleDC(hdc)

        bmi = ctypes.create_string_buffer(40 + 12)
        ctypes.memmove(bmi, struct.pack("LllHHLLllLL", 40, actual_width, -actual_height, 1, 32, 0, 0, 0, 0, 0, 0), 40)

        ppvBits = ctypes.c_void_p()
        hbitmap = ctypes.windll.gdi32.CreateDIBSection(memdc, bmi, 0, ctypes.byref(ppvBits), None, 0)

        old_bmp = win32gui.SelectObject(memdc, hbitmap)

        # 将光标绘制到内存 DC (不拉伸)
        win32gui.DrawIconEx(memdc, 0, 0, hcursor, actual_width, actual_height, 0, 0, win32con.DI_NORMAL)

        # 将像素数据拷贝到 QImage
        ctypes.memmove(int(img.bits()), ppvBits.value, actual_width * actual_height * 4)

        win32gui.SelectObject(memdc, old_bmp)
        win32gui.DeleteObject(hbitmap)
        win32gui.DeleteDC(memdc)
        win32gui.ReleaseDC(0, hdc)
        win32gui.DestroyIcon(hcursor)
        win32gui.DeleteObject(info[3])
        if info[4]: win32gui.DeleteObject(info[4])

        if img.isNull():
            return None

        # 最后，将实际大小的图片平滑缩放到 UI 要求的尺寸
        return QPixmap.fromImage(img).scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception as e:
        print(f"Error loading cursor {cursor_file}: {e}")
        return None


# ---------- 动画刷新图标 ----------

class AnimatedCursorLabel(QLabel):
    """显示动画游标的标签（旋转效果）. """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmaps: list[QPixmap] = []
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        self._running = False
        self._size = 64

    def set_frames(self, pixmaps: list[QPixmap]):
        self._pixmaps = pixmaps
        self._frame = 0
        if pixmaps:
            self.setPixmap(pixmaps[0])
        self.update()

    def start_animation(self):
        if self._pixmaps and len(self._pixmaps) > 1:
            self._running = True
            self._timer.start(100)

    def stop_animation(self):
        self._running = False
        self._timer.stop()

    def set_display_size(self, size: int):
        self._size = size

    def _next_frame(self):
        if not self._pixmaps:
            return
        self._frame = (self._frame + 1) % len(self._pixmaps)
        self.setPixmap(self._pixmaps[self._frame])
        self.update()


# ---------- 单个游标卡片 ----------

from PyQt6.QtWidgets import QGraphicsDropShadowEffect
class CursorCard(QFrame):
    """单个游标类型的预览卡片 — 现代圆角风格."""

    def __init__(self, cursor_type: CursorType, parent=None):
        super().__init__(parent)
        self.cursor_type = cursor_type
        self._pixmap: Optional[QPixmap] = None
        self._size = 52

        self.setFixedSize(100, 110)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setStyleSheet("""
            CursorCard {
                background: #ffffff;
                border: 1px solid #e4e9f0;
                border-radius: 14px;
                padding: 6px;
            }
            CursorCard:hover {
                background: #f4f9ff;
                border: 1.5px solid #4a90d9;
            }
        """)

        # 添加精美阴影
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(10)
        self._shadow.setColor(QColor(0, 0, 0, 10))
        self._shadow.setOffset(0, 2)
        self.setGraphicsEffect(self._shadow)

    def enterEvent(self, event):
        self._shadow.setBlurRadius(20)
        self._shadow.setColor(QColor(0, 0, 0, 20))
        self._shadow.setOffset(0, 6)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow.setBlurRadius(10)
        self._shadow.setColor(QColor(0, 0, 0, 10))
        self._shadow.setOffset(0, 2)
        super().leaveEvent(event)

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制光标
        if self._pixmap:
            pm = self._pixmap.scaled(
                self._size, self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - pm.width()) // 2
            y = 10
            painter.drawPixmap(x, y, pm)

        # 绘制名称
        name = CURSOR_CHINESE_NAMES.get(self.cursor_type, self.cursor_type.value)
        painter.setPen(QColor("#546e7a"))
        font = QFont("Microsoft YaHei UI", 8)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.drawText(
            QRect(0, self.height() - 24, self.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            name,
        )

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_show_large_preview(self.cursor_type)

    def parent_show_large_preview(self, cursor_type: CursorType):
        """通知父窗口显示大预览."""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'show_large_preview'):
                parent.show_large_preview(cursor_type)
                break
            parent = parent.parent() if hasattr(parent, 'parent') else None


# ---------- 游标网格面板 ----------

class CursorGridPanel(QWidget):
    """游标类型网格面板，显示主题中所有游标."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_name: Optional[str] = None
        self._theme_manager: Optional[ThemeManager] = None
        self._cards: dict[CursorType, CursorCard] = {}
        self._large_pixmap: Optional[QPixmap] = None
        self._large_type: Optional[CursorType] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 大预览区域
        self._large_label = QLabel()
        self._large_label.setFixedSize(160, 160)
        self._large_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._large_label.setStyleSheet("""
            background: #ffffff;
            border: 1px solid #e4e9f0;
            border-radius: 12px;
        """)
        self._large_label.setToolTip("鼠标类型预览")

        large_wrapper = QHBoxLayout()
        large_wrapper.addStretch()
        large_wrapper.addWidget(self._large_label)
        large_wrapper.addStretch()

        # 游标名称标签
        self._type_name_label = QLabel("标准选择")
        self._type_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._type_name_label.setStyleSheet("color: #1a2332; font-size: 14px; font-weight: 600;")
        self._type_name_label.setVisible(False)

        layout.addLayout(large_wrapper)
        layout.addWidget(self._type_name_label)

        # 网格滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 6px; background: #e4e9f0; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #b0bec5; border-radius: 3px; }
        """)

        grid_widget = QWidget()
        self._grid_layout = QGridLayout(grid_widget)
        self._grid_layout.setSpacing(8)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

    def load_theme(self, theme_name: str, theme_manager: ThemeManager):
        """加载主题到网格."""
        self._theme_name = theme_name
        self._theme_manager = theme_manager

        # 清除旧卡片
        for card in self._cards.values():
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        theme = theme_manager.get_theme(theme_name)
        if not theme:
            return

        # 创建卡片
        cols = 5
        for i, cursor_type in enumerate(CursorType):
            card = CursorCard(cursor_type)

            # 从 .cur 文件加载
            cursor_file = theme_manager.get_cursor_file(theme_name, cursor_type)
            pm = None
            if cursor_file:
                pm = _get_cur_pixmap(cursor_file, 48)

            if pm:
                card.set_pixmap(pm)

            row = i // cols
            col = i % cols
            self._grid_layout.addWidget(card, row, col)
            self._cards[cursor_type] = card

        # 默认显示第一个
        first_type = CursorType.ARROW
        self.show_large_preview(first_type)

    def show_large_preview(self, cursor_type: CursorType):
        """在大预览区域显示指定游标."""
        if not self._theme_manager or not self._theme_name:
            return

        self._large_type = cursor_type
        # 从 .cur 文件加载大图
        pm = None
        cursor_file = self._theme_manager.get_cursor_file(self._theme_name, cursor_type)
        if cursor_file:
            pm = _get_cur_pixmap(cursor_file, 128)
        if pm:
            self._large_label.setPixmap(pm)
        else:
            self._large_label.clear()

        name = CURSOR_CHINESE_NAMES.get(cursor_type, cursor_type.value)
        self._type_name_label.setText(name)
        self._type_name_label.setVisible(True)


# ---------- 主题预览图块 ----------

class ThemeCard(QFrame):
    """主题预览卡片 (左侧列表项)."""

    selected_signal = None  # 将在外部连接

    def __init__(
        self,
        theme_name: str,
        display_name: str,
        description: str,
        color: str,
        installed: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.theme_name = theme_name
        self.display_name = display_name
        self.description = description
        self._color = color
        self._installed = installed
        self._selected = False

        self.setFixedHeight(72)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_style()

        # 添加轻微阴影
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(10)
        self._shadow.setColor(QColor(0, 0, 0, 10))
        self._shadow.setOffset(0, 2)
        self.setGraphicsEffect(self._shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 颜色指示器
        self._color_dot = QFrame()
        self._color_dot.setFixedSize(32, 32)
        self._color_dot.setStyleSheet(f"""
            background: {color};
            border-radius: 8px;
            border: 2px solid rgba(255,255,255,0.1);
        """)
        layout.addWidget(self._color_dot)

        # 文字信息
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        self._name_label = QLabel(display_name)
        self._name_label.setStyleSheet("color: #1a2332; font-size: 13px; font-weight: bold;")
        text_layout.addWidget(self._name_label)

        self._desc_label = QLabel(description)
        self._desc_label.setStyleSheet("color: #8a9bb0; font-size: 10px;")
        self._desc_label.setWordWrap(True)
        self._desc_label.setMaximumHeight(32)
        text_layout.addWidget(self._desc_label)

        layout.addLayout(text_layout, 1)

        # 安装状态
        self._status_label = QLabel()
        self._status_label.setFixedSize(20, 20)
        layout.addWidget(self._status_label)
        self._update_status()

    def enterEvent(self, event):
        if not self._selected:
            self._shadow.setBlurRadius(20)
            self._shadow.setColor(QColor(0, 0, 0, 20))
            self._shadow.setOffset(0, 6)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._selected:
            self._shadow.setBlurRadius(10)
            self._shadow.setColor(QColor(0, 0, 0, 10))
            self._shadow.setOffset(0, 2)
        super().leaveEvent(event)

    def _update_style(self):
        if self._selected:
            self.setStyleSheet("""
                ThemeCard {
                    background: #f4f9ff;
                    border: 1.5px solid #4a90d9;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                ThemeCard {
                    background: #1a1a2e;
                    border: 1px solid #2a2a3e;
                    border-radius: 10px;
                }
                ThemeCard:hover {
                    background: #22223a;
                    border: 1px solid #3a3a5a;
                }
            """)

    def _update_status(self):
        if self._installed:
            self._status_label.setStyleSheet("""
                background: #2a8a3a;
                border-radius: 10px;
                color: #fff;
                font-size: 10px;
                qproperty-text: "✓";
            """)
        else:
            self._status_label.setStyleSheet("""
                background: #3a3a4a;
                border-radius: 10px;
                color: #666;
                font-size: 10px;
                qproperty-text: "○";
            """)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def set_installed(self, installed: bool):
        self._installed = installed
        self._update_status()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'on_selected') and self.on_selected:
                self.on_selected(self.theme_name)


class ThemeListPanel(QWidget):
    """左侧主题列表面板."""

    theme_selected = None  # signal: callable(theme_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, ThemeCard] = {}
        self._selected_name: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标题
        title = QLabel("🎨 主题列表")
        title.setStyleSheet("color: #ccc; font-size: 16px; font-weight: bold; padding: 8px 4px;")
        layout.addWidget(title)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 6px; background: #e4e9f0; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #b0bec5; border-radius: 3px; }
        """)

        scroll_widget = QWidget()
        self._card_layout = QVBoxLayout(scroll_widget)
        self._card_layout.setSpacing(8)
        self._card_layout.setContentsMargins(8, 8, 8, 8)
        self._card_layout.addStretch()

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

    def load_themes(self, themes):
        """加载主题列表."""
        for card in self._cards.values():
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        for theme in themes:
            card = ThemeCard(
                theme_name=theme.name,
                display_name=theme.display_name,
                description="",
                color="#4a90d9",
                installed=theme.installed,
            )
            card.on_selected = self._on_card_selected
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)
            self._cards[theme.name] = card

        # 默认选中第一个
        if themes:
            self._select_theme(themes[0].name)

    def _on_card_selected(self, theme_name: str):
        self._select_theme(theme_name)

    def _select_theme(self, theme_name: str):
        # 取消旧的选中
        if self._selected_name and self._selected_name in self._cards:
            self._cards[self._selected_name].set_selected(False)

        self._selected_name = theme_name
        if theme_name in self._cards:
            self._cards[theme_name].set_selected(True)
            if self.theme_selected:
                self.theme_selected(theme_name)

    def update_status(self, theme_name: str, installed: bool):
        if theme_name in self._cards:
            self._cards[theme_name].set_installed(installed)

    @property
    def selected_theme(self) -> Optional[str]:
        return self._selected_name


class CursorGalleryWidget(QWidget):
    """游标画廊：显示主题的所有游标预览."""

    def __init__(self, theme: Theme, theme_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._theme_dir = Path(theme_dir) if theme_dir else None
        self._large_type: Optional[CursorType] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 大预览区域
        large_wrapper = QHBoxLayout()
        large_wrapper.addStretch()

        large_container = QFrame()
        large_container.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #e4e9f0;
                border-radius: 16px;
                padding: 10px;
            }
        """)
        large_container_layout = QVBoxLayout(large_container)
        large_container_layout.setContentsMargins(0, 0, 0, 0)
        large_container_layout.setSpacing(8)

        self._large_label = QLabel()
        self._large_label.setFixedSize(180, 180)
        self._large_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._large_label.setStyleSheet("background: transparent; border: none;")
        self._large_label.setToolTip("点击卡片查看大预览")
        large_container_layout.addWidget(self._large_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self._type_name_label = QLabel("标准选择")
        self._type_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._type_name_label.setStyleSheet(
            "color: #4a90d9; font-size: 15px; font-weight: 700; background: transparent;"
        )
        self._type_name_label.setVisible(False)
        large_container_layout.addWidget(self._type_name_label)

        large_wrapper.addWidget(large_container)
        large_wrapper.addStretch()
        layout.addLayout(large_wrapper)

        # 标题区域
        header = QLabel(f"  {theme.display_name} — 共 {len(theme.cursor_files)} 个光标")
        header.setStyleSheet(
            "color: #546e7a; font-size: 13px; padding: 4px 8px; font-weight: 500;"
        )
        layout.addWidget(header)

        # 网格滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 6px; background: #e4e9f0; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #b0bec5; border-radius: 3px; }
        """)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(8, 8, 8, 8)

        self._cards: dict[CursorType, CursorCard] = {}

        # 填充游标卡片
        cols = 6
        for i, cursor_type in enumerate(CursorType):
            card = CursorCard(cursor_type)

            pm = None
            if theme.cursor_files and cursor_type in theme.cursor_files:
                pm = _get_cur_pixmap(theme.cursor_files[cursor_type], 52)
            if not pm and self._theme_dir:
                cur_path = self._theme_dir / f"{cursor_type.value}.cur"
                pm = _get_cur_pixmap(cur_path, 52)
            if pm:
                card.set_pixmap(pm)

            row = i // cols
            col = i % cols
            grid.addWidget(card, row, col)
            self._cards[cursor_type] = card

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll)

        # 默认显示第一个游标的大预览
        first_type = CursorType.ARROW
        self.show_large_preview(first_type)

    def show_large_preview(self, cursor_type: CursorType):
        """在大预览区域显示指定游标."""
        self._large_type = cursor_type

        pm = None
        if self._theme.cursor_files and cursor_type in self._theme.cursor_files:
            pm = _get_cur_pixmap(self._theme.cursor_files[cursor_type], 144)
        if not pm and self._theme_dir:
            cur_path = self._theme_dir / f"{cursor_type.value}.cur"
            pm = _get_cur_pixmap(cur_path, 144)

        if pm:
            self._large_label.setPixmap(pm)
        else:
            self._large_label.clear()
            self._large_label.setText("🖱️")
            self._large_label.setStyleSheet(
                "color: #b0bec5; font-size: 48px; background: transparent; border: none;"
            )

        name = CURSOR_CHINESE_NAMES.get(cursor_type, cursor_type.value)
        self._type_name_label.setText(name)
        self._type_name_label.setVisible(True)
