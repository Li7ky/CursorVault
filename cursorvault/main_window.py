# -*- coding: utf-8 -*-
"""CursorVault 主窗口."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSize, QTimer, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QPixmap, QAction, QIcon, QIntValidator, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLabel, QPushButton,
    QSplitter, QScrollArea, QFrame, QTabWidget,
    QMessageBox, QStatusBar, QMenu, QMenuBar,
    QFileDialog, QProgressBar, QGridLayout, QInputDialog,
    QLineEdit, QTextEdit, QComboBox,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from . import __version__, __app_name__
from .theme_manager import ThemeManager
from .downloader import find_cursor_files
from .cursor_preview import CursorGalleryWidget
from .system_cursor import system_cursor_api
from .zhutix_client import ZhutixClient, ZhutixPack
from .models import CursorType

APP_STYLESHEET = """
    /* ── 纯正传统桌面原生风格 (Classic Desktop GUI) ── */
    * {
        font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        font-size: 9pt;
    }
    QMainWindow, QWidget {
        background-color: #f0f0f0;
        color: #000000;
    }
    QToolBar {
        background-color: #f0f0f0;
        border-bottom: 1px solid #d4d4d4;
        padding: 2px;
    }
    QListWidget {
        background-color: #ffffff;
        border: 1px solid #828790;
    }
    QListWidget::item {
        padding: 4px;
        border-bottom: 1px solid #f0f0f0;
    }
    QListWidget::item:selected {
        background-color: #0078d7;
        color: #ffffff;
    }
    QListWidget::item:hover:!selected {
        background-color: #e5f1fb;
    }
    QPushButton {
        background-color: #e1e1e1;
        border: 1px solid #adadad;
        padding: 4px 12px;
        border-radius: 0px;
        min-height: 22px;
    }
    QPushButton:hover {
        background-color: #e5f1fb;
        border-color: #0078d7;
    }
    QPushButton:pressed {
        background-color: #cce4f7;
        border-color: #005499;
    }
    QPushButton:disabled {
        background-color: #f0f0f0;
        border-color: #cccccc;
        color: #a0a0a0;
    }
    QLineEdit {
        border: 1px solid #828790;
        padding: 2px 4px;
        background: #ffffff;
    }
    QLineEdit:focus {
        border-color: #0078d7;
    }
    QTabWidget::pane {
        border: 1px solid #828790;
        background-color: #ffffff;
        top: -1px;
    }
    QTabBar::tab {
        background: #f0f0f0;
        border: 1px solid #828790;
        padding: 4px 12px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background: #ffffff;
        border-bottom-color: #ffffff;
    }
    QSplitter::handle {
        background-color: #d4d4d4;
        width: 1px;
    }
    QScrollArea {
        border: 1px solid #828790;
        background: #ffffff;
    }
    QFrame#packCard {
        background-color: #ffffff;
        border: 1px solid #d4d4d4;
    }
    QFrame#packCard:hover {
        border-color: #0078d7;
        background-color: #f3f9ff;
    }
    """

# ── 在线素材库：后台线程 ────────────────────────────────────────

class FetchPacksThread(QThread):
    """后台线程：获取光标包列表."""

    packs_ready = pyqtSignal(list)    # list[ZhutixPack]
    progress = pyqtSignal(int, int)   # current_page, total_pages
    error = pyqtSignal(str)

    def __init__(self, client: ZhutixClient, page: int = 1, per_page: int = 50):
        super().__init__()
        self._client = client
        self._page = page
        self._per_page = per_page

    def run(self):
        try:
            packs = self._client.fetch_page(self._page, self._per_page)
            self.progress.emit(self._page, self._client.total_pages or 1)
            self.packs_ready.emit(packs)
        except Exception as e:
            self.error.emit(str(e))


class DownloadPackThread(QThread):
    """后台线程：下载光标包."""

    progress = pyqtSignal(int, int)   # downloaded, total
    finished_signal = pyqtSignal(bool, str, object)  # success, message, pack
    extract_signal = pyqtSignal(str)  # status message during extraction

    def __init__(
        self,
        client: ZhutixClient,
        pack: ZhutixPack,
        download_dir: Path,
        theme_manager: ThemeManager,
    ):
        super().__init__()
        self._client = client
        self._pack = pack
        self._download_dir = download_dir
        self._theme_manager = theme_manager

    def run(self):
        try:
            # 下载
            self.extract_signal.emit("正在下载...")
            archive_path = self._client.download_pack(
                self._pack,
                self._download_dir,
                progress_cb=lambda d, t: self.progress.emit(d, t),
            )
            if not archive_path:
                self.finished_signal.emit(False, "下载失败：无法获取下载链接", self._pack)
                return

            # 安装（解压+映射）
            self.extract_signal.emit("正在解压并安装...")
            theme = self._theme_manager.install_from_archive(
                archive_path,
                slug=self._pack.slug,
                display_name=self._pack.title,
                source_url=self._pack.url,
            )
            if theme:
                count = len(theme.cursor_files)
                self.finished_signal.emit(
                    True,
                    f"安装成功！已导入 {count} 个光标文件",
                    self._pack,
                )
            else:
                self.finished_signal.emit(
                    False,
                    "安装失败：压缩包中未找到可识别的光标文件\n"
                    "可能是压缩格式不支持或文件命名不规范",
                    self._pack,
                )
        except Exception as e:
            self.finished_signal.emit(False, f"安装出错: {e}", self._pack)


# ── 在线素材库：骨架屏卡片 ────────────────────────────────────────

class SkeletonCard(QFrame):
    """加载中的占位卡片."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("packCard")
        self.setFixedSize(240, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        img = QLabel()
        img.setObjectName("skeleton")
        img.setFixedSize(212, 120)
        layout.addWidget(img)

        title = QLabel()
        title.setObjectName("skeleton")
        title.setFixedSize(150, 16)
        layout.addWidget(title)

        meta = QLabel()
        meta.setObjectName("skeleton")
        meta.setFixedSize(80, 12)
        layout.addWidget(meta)

        layout.addStretch()

        btn = QLabel()
        btn.setObjectName("skeleton")
        btn.setFixedSize(232, 34)
        layout.addWidget(btn)


# ── 在线素材库：光标包卡片 ────────────────────────────────────────

class PackCard(QFrame):
    """单个在线光标包卡片 — 精致版 v2."""

    download_clicked = pyqtSignal(object)  # ZhutixPack
    apply_clicked = pyqtSignal(str)        # slug

    def __init__(self, pack: ZhutixPack, installed: bool = False, parent=None):
        super().__init__(parent)
        self.pack = pack
        self._installed = installed
        self.setObjectName("packCard")
        self.setFixedSize(240, 260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ── 预览图区 ──
        self._preview_label = QLabel()
        self._preview_label.setObjectName("packPreview")
        self._preview_label.setFixedSize(212, 120)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setText("加载中...")
        self._preview_label.setStyleSheet(
            "color: #8a9bb0; font-size: 12px;"
        )
        layout.addWidget(self._preview_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── 标题行 ──
        title_label = QLabel(pack.title)
        title_label.setObjectName("packTitle")
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(40)
        layout.addWidget(title_label)

        # ── 信息标签行 ──
        info_row = QHBoxLayout()
        info_row.setSpacing(6)

        date_str = pack.modified[:10] if pack.modified else ""
        if date_str:
            date_tag = QLabel(date_str)
            date_tag.setObjectName("packDateTag")
            info_row.addWidget(date_tag)

        if installed:
            badge = QLabel("已安装")
            badge.setObjectName("installedBadge")
            info_row.addWidget(badge)

        info_row.addStretch()
        layout.addLayout(info_row)

        layout.addStretch()

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._download_btn = QPushButton("下载安装")
        self._download_btn.setObjectName("downloadBtn")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.clicked.connect(lambda: self.download_clicked.emit(self.pack))
        btn_row.addWidget(self._download_btn, 1)

        if installed:
            self._apply_btn = QPushButton("应用")
            self._apply_btn.setObjectName("applyOnlineBtn")
            self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._apply_btn.clicked.connect(lambda: self.apply_clicked.emit(self.pack.slug))
            btn_row.addWidget(self._apply_btn)
            self._download_btn.setText("已安装")
            self._download_btn.setEnabled(False)

        layout.addLayout(btn_row)

    def set_preview_pixmap(self, pixmap: QPixmap):
        """设置预览图."""
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                232, 130,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_label.setPixmap(scaled)
        else:
            self._preview_label.setText("无预览图")

    def set_downloading(self):
        """标记为下载中."""
        self._download_btn.setText("下载中...")
        self._download_btn.setEnabled(False)
        self._download_btn.repaint()

    def set_installed_state(self):
        """标记为已安装."""
        self._installed = True
        self._download_btn.setText("已安装")
        self._download_btn.setEnabled(False)
        if not hasattr(self, "_apply_btn"):
            self._apply_btn = QPushButton("应用")
            self._apply_btn.setObjectName("applyOnlineBtn")
            self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._apply_btn.clicked.connect(lambda: self.apply_clicked.emit(self.pack.slug))
            self.layout().itemAt(self.layout().count() - 1).layout().addWidget(self._apply_btn)


# ── 在线素材库面板 ────────────────────────────────────────────

class OnlineLibraryPanel(QWidget):
    """在线素材库面板：浏览致美化光标包，下载并安装."""

    pack_download_requested = pyqtSignal(object)   # ZhutixPack
    pack_apply_requested = pyqtSignal(str)          # slug

    def __init__(self, theme_manager: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._client = ZhutixClient()
        self._packs: list[ZhutixPack] = []
        self._cards: dict[str, PackCard] = {}  # slug -> card
        self._skeleton_cards: list[SkeletonCard] = []
        self._current_page = 1
        self._total_pages = 1
        self._per_page = 40
        self._filter = "all"
        self._fetch_thread: Optional[FetchPacksThread] = None
        self._network = QNetworkAccessManager(self)
        self._preview_jobs: dict[str, QNetworkReply] = {}  # slug -> reply

        self._setup_ui()
        self._fetch_packs()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(6)

        # ── 顶部标题栏 ──
        header_bar = QHBoxLayout()
        header_bar.setSpacing(16)

        # 标题 + 统计
        header_left = QVBoxLayout()
        header_left.setSpacing(2)

        title = QLabel("在线素材库")
        title.setObjectName("onlineTitle")
        header_left.addWidget(title)

        self._count_label = QLabel("从致美化实时获取")
        self._count_label.setObjectName("onlineCount")
        header_left.addWidget(self._count_label)

        header_bar.addLayout(header_left)
        header_bar.addStretch()

        # 搜索框
        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setPlaceholderText("🔍  搜索光标包名称...")

        self._search_input.textChanged.connect(self._on_search)

        header_bar.addWidget(self._search_input)

        # 刷新按钮
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("toolBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._fetch_packs)
        header_bar.addWidget(refresh_btn)

        layout.addLayout(header_bar)

        # ── 筛选标签 ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)
        filter_bar.addStretch()

        self._filter_buttons = {}
        for key, label in [("all", "全部"), ("latest", "最新"), ("hot", "热门")]:
            btn = QPushButton(label)
            btn.setObjectName("filterTag")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._on_filter_clicked(k))
            self._filter_buttons[key] = btn
            filter_bar.addWidget(btn)

        self._filter_buttons["all"].setChecked(True)
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        # ── 进度条 ──
        self._progress = QProgressBar()
        self._progress.setObjectName("globalProgress")
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(3)
        layout.addWidget(self._progress)

        # ── 状态标签 ──
        self._status_label = QLabel("正在加载...")
        self._status_label.setObjectName("onlineStatus")
        layout.addWidget(self._status_label)

        # ── 光标包网格 (滚动) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setContentsMargins(4, 4, 4, 8)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        # ── 空状态 ──
        self._empty_state = QWidget()
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setContentsMargins(0, 40, 0, 40)
        empty_icon = QLabel("")
        empty_icon.setObjectName("emptyStateIcon")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_text = QLabel("暂无符合条件的光标包")
        empty_text.setObjectName("emptyState")
        empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_text)
        self._empty_state.setVisible(False)
        layout.addWidget(self._empty_state)

        # ── 分页栏 ──
        page_bar_widget = QWidget()
        page_bar_widget.setObjectName("pageBarWidget")
        page_bar = QHBoxLayout(page_bar_widget)
        page_bar.setContentsMargins(16, 8, 16, 8)
        page_bar.setSpacing(12)

        page_bar.addStretch()

        self._first_btn = QPushButton("首页")
        self._first_btn.setObjectName("toolBtn")
        self._first_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._first_btn.clicked.connect(self._first_page)
        self._first_btn.setEnabled(False)
        page_bar.addWidget(self._first_btn)

        self._prev_btn = QPushButton("← 上一页")
        self._prev_btn.setObjectName("toolBtn")
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self._prev_page)
        self._prev_btn.setEnabled(False)
        page_bar.addWidget(self._prev_btn)

        self._page_label = QLabel("1 / 1")
        self._page_label.setObjectName("pageLabel")
        page_bar.addWidget(self._page_label)

        self._next_btn = QPushButton("下一页 →")
        self._next_btn.setObjectName("toolBtn")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._next_page)
        self._next_btn.setEnabled(False)
        page_bar.addWidget(self._next_btn)

        self._last_btn = QPushButton("末页")
        self._last_btn.setObjectName("toolBtn")
        self._last_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._last_btn.clicked.connect(self._last_page)
        self._last_btn.setEnabled(False)
        page_bar.addWidget(self._last_btn)

        page_jump = QHBoxLayout()
        page_jump.setSpacing(6)
        page_jump_label = QLabel("跳转至")
        page_jump_label.setObjectName("pageTotal")
        page_jump.addWidget(page_jump_label)

        self._page_input = QLineEdit()
        self._page_input.setObjectName("pageInput")
        self._page_input.setValidator(QIntValidator(1, 9999))
        self._page_input.returnPressed.connect(self._go_to_page_input)
        page_jump.addWidget(self._page_input)

        page_jump_total = QLabel("页")
        page_jump_total.setObjectName("pageTotal")
        page_jump.addWidget(page_jump_total)
        page_bar.addLayout(page_jump)

        page_bar.addStretch()
        layout.addWidget(page_bar_widget)

    def _on_filter_clicked(self, key: str):
        """筛选标签切换."""
        if self._filter == key:
            return
        self._filter = key
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)
        self._current_page = 1
        self._fetch_packs()

    def _show_skeletons(self):
        """显示骨架屏占位卡片."""
        self._clear_cards()
        self._empty_state.setVisible(False)
        for i in range(8):
            card = SkeletonCard(self._grid_container)
            row = i // 4
            col = i % 4
            self._grid_layout.addWidget(card, row, col)
            self._skeleton_cards.append(card)

    def _hide_skeletons(self):
        """隐藏骨架屏."""
        for card in self._skeleton_cards:
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._skeleton_cards.clear()

    def _fetch_packs(self):
        """获取当前页的光标包列表."""
        if self._fetch_thread and self._fetch_thread.isRunning():
            self._status_label.setText("正在加载，请等待当前请求完成")
            return
        self._progress.setVisible(True)
        self._status_label.setText(f"正在加载第 {self._current_page} 页...")
        self._prev_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        self._first_btn.setEnabled(False)
        self._last_btn.setEnabled(False)

        self._show_skeletons()

        self._fetch_thread = FetchPacksThread(self._client, self._current_page, self._per_page)
        self._fetch_thread.packs_ready.connect(self._on_packs_ready)
        self._fetch_thread.progress.connect(self._on_fetch_progress)
        self._fetch_thread.error.connect(self._on_fetch_error)
        self._fetch_thread.finished.connect(self._fetch_thread.deleteLater)
        self._fetch_thread.start()

    def _clear_cards(self):
        """清空所有卡片."""
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        for card in self._skeleton_cards:
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._skeleton_cards.clear()

    def _on_packs_ready(self, packs: list):
        """光标包列表获取完成."""
        self._packs = packs
        self._progress.setVisible(False)
        self._hide_skeletons()
        total = self._client.total or 0

        if not packs:
            self._empty_state.setVisible(True)
            self._status_label.setText("暂无数据")
        else:
            self._empty_state.setVisible(False)
            self._status_label.setText(
                f"  共 {total} 个光标包  ·  第 {self._current_page}/{self._total_pages} 页  ·  本页 {len(packs)} 个"
            )
        self._count_label.setText(f"共 {total} 个光标包，实时同步自致美化")

        # 更新分页按钮
        self._prev_btn.setEnabled(self._current_page > 1)
        self._next_btn.setEnabled(
            self._total_pages > 0 and self._current_page < self._total_pages
        )
        self._first_btn.setEnabled(self._current_page > 1)
        self._last_btn.setEnabled(
            self._total_pages > 0 and self._current_page < self._total_pages
        )
        self._page_label.setText(f"{self._current_page} / {self._total_pages or 1}")

        # 创建卡片
        for i, pack in enumerate(packs):
            installed = self._theme_manager.is_installed(pack.slug)
            card = PackCard(pack, installed=installed)
            card.download_clicked.connect(self._on_download_clicked)
            card.apply_clicked.connect(self._on_apply_clicked)

            row = i // 4
            col = i % 4
            self._grid_layout.addWidget(card, row, col)
            self._grid_layout.setColumnStretch(col, 1)
            self._cards[pack.slug] = card

            # 异步加载预览图
            self._load_preview(pack)

    def _on_fetch_progress(self, page: int, total_pages: int):
        self._total_pages = total_pages

    def _on_fetch_error(self, err: str):
        self._progress.setVisible(False)
        self._hide_skeletons()
        self._status_label.setText(f"加载失败: {err}")
        QMessageBox.warning(self, "加载失败", f"获取光标包列表失败:\n{err}")

    def _load_preview(self, pack: ZhutixPack):
        """异步加载预览图."""
        url = self._client.get_preview_url(pack)
        if not url:
            return

        reply = self._network.get(QNetworkRequest(QUrl(url)))
        self._preview_jobs[pack.slug] = reply
        reply.finished.connect(lambda: self._on_preview_loaded(pack.slug, reply))

    def _on_preview_loaded(self, slug: str, reply: QNetworkReply):
        """预览图加载完成."""
        reply.deleteLater()
        self._preview_jobs.pop(slug, None)

        if reply.error() != QNetworkReply.NetworkError.NoError:
            return

        data = reply.readAll()
        pixmap = QPixmap()
        if pixmap.loadFromData(bytes(data)):
            card = self._cards.get(slug)
            if card:
                card.set_preview_pixmap(pixmap)

    def _on_download_clicked(self, pack: ZhutixPack):
        """下载安装按钮点击."""
        if pack.slug in self._cards:
            self._cards[pack.slug].set_downloading()
        self._status_label.setText(f"正在下载安装: {pack.title}...")
        self.pack_download_requested.emit(pack)

    def _on_apply_clicked(self, slug: str):
        """应用已安装的主题."""
        self.pack_apply_requested.emit(slug)

    def _on_search(self, text: str):
        """搜索过滤."""
        text = text.strip().lower()
        visible_count = 0
        for slug, card in self._cards.items():
            if not text:
                card.show()
                visible_count += 1
            else:
                match = text in card.pack.title.lower() or text in slug.lower()
                card.setVisible(match)
                if match:
                    visible_count += 1
        self._empty_state.setVisible(visible_count == 0 and len(self._cards) > 0)

    def _first_page(self):
        if self._current_page != 1:
            self._current_page = 1
            self._fetch_packs()

    def _prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            self._fetch_packs()

    def _next_page(self):
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._fetch_packs()

    def _last_page(self):
        if self._current_page != self._total_pages and self._total_pages > 0:
            self._current_page = self._total_pages
            self._fetch_packs()

    def _go_to_page_input(self):
        """跳转到输入的页码."""
        try:
            page = int(self._page_input.text().strip())
        except ValueError:
            return
        if page < 1 or page > self._total_pages:
            QMessageBox.warning(self, "页码错误", f"请输入 1 到 {self._total_pages} 之间的页码")
            return
        if page != self._current_page:
            self._current_page = page
            self._fetch_packs()
        self._page_input.clear()

    def on_pack_installed(self, slug: str):
        """某个包安装完成后刷新卡片状态."""
        card = self._cards.get(slug)
        if card:
            card.set_installed_state()
        self._status_label.setText(f"安装完成: {slug}")

    def refresh_installed_status(self):
        """刷新所有卡片的安装状态."""
        for slug, card in self._cards.items():
            if self._theme_manager.is_installed(slug):
                card.set_installed_state()


# ── 主窗口 ────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """CursorVault 主窗口."""

    def __init__(self, theme_manager: ThemeManager):
        super().__init__()
        self.theme_manager = theme_manager
        self._current_theme = None
        self._download_threads: dict[str, DownloadPackThread] = {}
        self._online_panel: Optional[OnlineLibraryPanel] = None

        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(APP_STYLESHEET)

        self._setup_menu_bar()
        self._setup_ui()
        self._setup_status_bar()
        self._load_themes()

    def _setup_menu_bar(self):
        """设置菜单栏."""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        import_action = QAction("导入游标目录...", self)
        import_action.triggered.connect(self._import_cursors)
        file_menu.addAction(import_action)
        file_menu.addSeparator()
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 工具菜单
        tool_menu = menubar.addMenu("工具(&T)")
        backup_action = QAction("备份当前游标", self)
        backup_action.triggered.connect(self._backup_cursors)
        tool_menu.addAction(backup_action)
        restore_action = QAction("恢复游标", self)
        restore_action.triggered.connect(self._restore_cursors)
        tool_menu.addAction(restore_action)
        tool_menu.addSeparator()
        refresh_action = QAction("刷新系统游标", self)
        refresh_action.triggered.connect(self._refresh_system_cursors)
        tool_menu.addAction(refresh_action)
        tool_menu.addSeparator()
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction(f"关于 {__app_name__}", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        # 设置主界面布局 — 干净、专业、高信息密度
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ===== 原生桌面工具栏 =====
        toolbar = self.addToolBar("常用操作")
        toolbar.setMovable(False)

        self.backup_btn = QAction("备份系统光标", self)
        self.backup_btn.triggered.connect(self._backup_cursors)
        toolbar.addAction(self.backup_btn)

        self.import_btn = QAction("导入自定义...", self)
        self.import_btn.triggered.connect(self._import_cursors)
        toolbar.addAction(self.import_btn)

        # ===== 进度条 =====
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("globalProgress")
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ===== 主体区域 =====
        body_widget = QWidget()
        body_widget.setObjectName("bodyWidget")
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Tab 容器：本地主题 + 在线素材库
        self._tabs = QTabWidget()
        self._tabs.setObjectName("mainTabs")
        self._tabs.setDocumentMode(True)

        # --- Tab 1: 本地主题 ---
        local_tab = QWidget()
        local_layout = QHBoxLayout(local_tab)
        local_layout.setContentsMargins(4, 4, 4, 4)
        local_layout.setSpacing(4)

        # 左侧边栏
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(16)

        sidebar_header_w = QWidget()
        sidebar_header_layout = QHBoxLayout(sidebar_header_w)
        sidebar_header_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_header_layout.setSpacing(8)

        sidebar_title = QLabel("主题列表")
        sidebar_title.setObjectName("sidebarTitle")
        sidebar_header_layout.addWidget(sidebar_title)

        self.theme_count_badge = QLabel("0")
        self.theme_count_badge.setObjectName("countBadge")
        sidebar_header_layout.addWidget(self.theme_count_badge)

        sidebar_header_layout.addStretch()
        sidebar_layout.addWidget(sidebar_header_w)

        # 搜索框 — 使用 CSS padding-left 实现图标效果
        self._local_search = QLineEdit()
        self._local_search.setObjectName("searchInput")
        self._local_search.setPlaceholderText("🔍  搜索本地主题...")

        self._local_search.textChanged.connect(self._on_local_search)
        sidebar_layout.addWidget(self._local_search)

        self.theme_list = QListWidget()
        self.theme_list.setObjectName("themeList")
        self.theme_list.setIconSize(QSize(44, 44))
        self.theme_list.setSpacing(3)
        self.theme_list.currentRowChanged.connect(self._on_theme_selected)
        sidebar_layout.addWidget(self.theme_list)


        # 右侧内容区
        content_panel = QWidget()
        content_panel.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(sidebar)
        splitter.addWidget(content_panel)
        splitter.setStretchFactor(1, 1)
        local_layout.addWidget(splitter)

        # 主题信息栏
        self.theme_info_bar = QWidget()
        self.theme_info_bar.setObjectName("themeInfoBar")
        self.theme_info_bar.setVisible(False)
        info_layout = QHBoxLayout(self.theme_info_bar)
        info_layout.setContentsMargins(20, 16, 20, 16)
        info_layout.setSpacing(16)

        self.theme_icon_label = QLabel()
        self.theme_icon_label.setObjectName("themeInfoIcon")
        self.theme_icon_label.setFixedSize(56, 56)
        self.theme_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.theme_icon_label)

        info_text_col = QVBoxLayout()
        info_text_col.setSpacing(4)
        self.theme_title_label = QLabel("选择一个主题")
        self.theme_title_label.setObjectName("themeInfoTitle")
        info_text_col.addWidget(self.theme_title_label)

        self.theme_meta_label = QLabel("点击左侧主题开始预览光标样式")
        self.theme_meta_label.setObjectName("themeInfoMeta")
        info_text_col.addWidget(self.theme_meta_label)

        tags_row = QHBoxLayout()
        tags_row.setSpacing(6)
        self._theme_count_tag = QLabel("")
        self._theme_count_tag.setObjectName("themeInfoTag")
        self._theme_count_tag.setVisible(False)
        tags_row.addWidget(self._theme_count_tag)
        self._theme_complete_tag = QLabel("")
        self._theme_complete_tag.setObjectName("themeInfoTag")
        self._theme_complete_tag.setVisible(False)
        tags_row.addWidget(self._theme_complete_tag)
        tags_row.addStretch()
        info_text_col.addLayout(tags_row)

        info_layout.addLayout(info_text_col, 1)

        info_layout.addStretch()

        # 操作按钮
        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(10)

        self.apply_btn = QPushButton("应用到系统")
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self._apply_theme)
        self.apply_btn.setEnabled(False)
        action_layout.addWidget(self.apply_btn)

        self._open_source_btn = QPushButton("来源网页")
        self._open_source_btn.setObjectName("toolBtn")
        self._open_source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_source_btn.clicked.connect(self._open_theme_source)
        self._open_source_btn.setVisible(False)
        action_layout.addWidget(self._open_source_btn)

        self._delete_theme_btn = QPushButton("删除")
        self._delete_theme_btn.setObjectName("dangerBtn")
        self._delete_theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_theme_btn.clicked.connect(self._delete_current_theme)
        self._delete_theme_btn.setVisible(False)
        action_layout.addWidget(self._delete_theme_btn)

        info_layout.addWidget(action_row)
        content_layout.addWidget(self.theme_info_bar)

        # 预览区域
        preview_scroll = QScrollArea()
        preview_scroll.setObjectName("previewScroll")
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        preview_container = QWidget()
        preview_container.setObjectName("previewContainer")
        self.preview_layout = QVBoxLayout(preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(0)

        preview_scroll.setWidget(preview_container)
        content_layout.addWidget(preview_scroll)



        self._tabs.addTab(local_tab, "本地主题")

        # --- Tab 2: 在线素材库 ---
        self._online_panel = OnlineLibraryPanel(self.theme_manager)
        self._online_panel.pack_download_requested.connect(self._download_pack)
        self._online_panel.pack_apply_requested.connect(self._apply_online_pack)
        self._tabs.addTab(self._online_panel, "在线素材库")

        body_layout.addWidget(self._tabs)
        main_layout.addWidget(body_widget, 1)

    def _setup_status_bar(self):
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 - 请选择主题")

    def _load_themes(self):
        # 加载主题列表
        self.theme_list.blockSignals(True)
        self.theme_list.clear()
        self._theme_items: list[tuple[QListWidgetItem, str]] = []

        for theme in self.theme_manager.themes:
            item = QListWidgetItem()
            item.setText(theme.display_name)
            item.setData(Qt.ItemDataRole.UserRole, theme.name)
            item.setSizeHint(QSize(0, 64))
            item.setToolTip(theme.source_url if theme.source_url else "本地导入主题")

            # 尝试加载主题图标
            theme_dir = self.theme_manager.get_theme_dir(theme.name)
            preview_path = theme_dir / "preview.png" if theme_dir else None
            if preview_path and preview_path.exists():
                pixmap = QPixmap(str(preview_path))
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap.scaled(
                        44, 44,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )))

            self.theme_list.addItem(item)
            self._theme_items.append((item, theme.name))

        self.theme_list.blockSignals(False)

        # 更新主题计数
        total = self.theme_list.count()
        self.theme_count_badge.setText(str(total))

        if total > 0:
            self.theme_list.setCurrentRow(0)

    def _install_initial_themes(self):
        # 启动时自动安装所有尚未安装的主题
        uninstalled = [t for t in self.theme_manager.themes if not t.installed]
        if not uninstalled:
            return

    def _refresh_theme_cards(self):
        # 刷新主题列表显示
        for i in range(self.theme_list.count()):
            item = self.theme_list.item(i)
            if item:
                theme_name = item.data(Qt.ItemDataRole.UserRole)
                theme = self.theme_manager.get_theme(theme_name)
                if theme:
                    display = theme.display_name
                    item.setText(display)

    def _on_local_search(self, text: str):
        # 本地主题搜索过滤
        text = text.strip().lower()
        for item, _ in self._theme_items:
            if not text:
                item.setHidden(False)
            else:
                item.setHidden(text not in item.text().lower())

    def _on_theme_selected(self, row: int):
        # 主题选中事件
        if row < 0:
            return

        item = self.theme_list.item(row)
        if not item:
            return

        theme_name = item.data(Qt.ItemDataRole.UserRole)
        theme = self.theme_manager.get_theme(theme_name)
        if not theme:
            return

        self._current_theme = theme

        # 显示信息栏
        self.theme_info_bar.setVisible(True)
        self.theme_title_label.setText(theme.display_name)

        # 尝试加载主题图标
        theme_dir = self.theme_manager.get_theme_dir(theme_name)
        preview_path = theme_dir / "preview.png" if theme_dir else None
        if preview_path and preview_path.exists():
            pixmap = QPixmap(str(preview_path))
            if not pixmap.isNull():
                self.theme_icon_label.setPixmap(pixmap.scaled(
                    52, 52, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
        else:
            self.theme_icon_label.clear()
            self.theme_icon_label.setText("🖱️")


        # 更新元信息
        installed_count = len(theme.cursor_files) if theme.cursor_files else 0
        total_count = 15 # CursorType enum count
        complete = theme.is_complete()

        self.theme_meta_label.setText(
            f"{installed_count} 个光标文件 · {'完整套装' if complete else '部分光标'}"
        )
        self._theme_count_tag.setText(f"{installed_count}/{total_count}")
        self._theme_count_tag.setVisible(True)
        self._theme_complete_tag.setText("完整" if complete else "不完整")
        self._theme_complete_tag.setVisible(True)

        # 来源/删除按钮
        has_source = bool(theme.source_url)
        self._open_source_btn.setVisible(has_source)
        self._open_source_btn.setProperty("source_url", theme.source_url)
        self._delete_theme_btn.setVisible(True)
        self._delete_theme_btn.setProperty("theme_name", theme.name)

        # 更新按钮状态 - 有 cursor_files 就可以应用
        can_apply = bool(theme.cursor_files)
        self.apply_btn.setEnabled(can_apply)

        # 清除旧预览
        while self.preview_layout.count():
            w = self.preview_layout.takeAt(0)
            if w and w.widget():
                w.widget().deleteLater()

        # 构建预览
        if can_apply:
            preview_widget = CursorGalleryWidget(theme, theme_dir)
            self.preview_layout.addWidget(preview_widget)

        self.status_bar.showMessage(f"已选择: {theme.display_name}")

    def _open_theme_source(self):
        # 打开主题来源网页
        url = self._open_source_btn.property("source_url")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _delete_current_theme(self):
        # 删除当前选中的主题
        theme_name = self._delete_theme_btn.property("theme_name")
        if not theme_name:
            return
        theme = self.theme_manager.get_theme(theme_name)
        if not theme:
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除主题「{theme.display_name}」吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if self.theme_manager.remove_theme(theme_name):
                self._load_themes()
                self.theme_info_bar.setVisible(False)
                self.status_bar.showMessage(f"已删除: {theme.display_name}")
                QMessageBox.information(self, "删除成功", f"主题「{theme.display_name}」已删除")
            else:
                QMessageBox.warning(self, "删除失败", "主题删除失败")
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    def _apply_theme(self):
        # 应用当前主题到系统
        if not self._current_theme or not self._current_theme.cursor_files:
            QMessageBox.warning(self, "无法应用", "当前主题不完整，缺少部分游标文件")
            return

        reply = QMessageBox.question(
            self, "确认应用",
            f"确定要应用主题「{self._current_theme.display_name}」到系统游标吗？\n建议先备份当前设置。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage("正在应用游标主题...")
        self.apply_btn.setEnabled(False)

        try:
            results = system_cursor_api.apply_theme(self._current_theme.cursor_files)
            failed = [ct.value for ct, success in results.items() if not success]
            if failed:
                raise RuntimeError(f"以下游标未能应用：{', '.join(failed)}")
            self.status_bar.showMessage(f"已应用: {self._current_theme.display_name}")
            QMessageBox.information(self, "应用成功", f"主题「{self._current_theme.display_name}」已应用到系统游标")
        except Exception as e:
            QMessageBox.critical(self, "应用失败", f"应用失败：{str(e)}\n请尝试以管理员身份运行本程序")
        finally:
            self.apply_btn.setEnabled(True)

    def _import_cursors(self):
        # 导入自定义游标
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择包含 .cur 文件的目录"
        )
        if not dir_path:
            return

        import_path = Path(dir_path)
        cur_files = find_cursor_files(import_path)
        if not cur_files:
            QMessageBox.warning(self, "导入失败", "所选目录中没有 .cur 或 .ani 文件")
            return

        # 让用户输入主题名称
        name, ok = QInputDialog.getText(
            self, "主题名称", "请输入主题显示名称:",
            text=import_path.name,
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        # 通过 theme_manager 导入
        try:
            theme = self.theme_manager.import_cur_directory(name, import_path)
        except ValueError as exc:
            QMessageBox.warning(self, "主题名称无效", str(exc))
            return
        if not theme:
            QMessageBox.warning(
                self, "导入失败",
                "无法识别目录中的游标文件。\n"
                "请确保文件名包含以下关键字之一：\n"
                "arrow, help, wait, crosshair, ibeam, pen, no, "
                "hand, uparrow, sizeall, sizenesw, sizens, sizenwse, sizewe"
            )
            return

        # 刷新列表
        self._load_themes()
        self.status_bar.showMessage(f"已导入主题: {theme.display_name}")
        QMessageBox.information(
            self, "导入成功",
            f"主题「{theme.display_name}」已导入\n"
            f"包含 {len(theme.cursor_files)} 个游标文件"
        )

    def _backup_cursors(self):
        # 备份当前系统游标
        backup_dir = self.theme_manager.base_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            success = system_cursor_api.backup_current_cursors(backup_dir)
            if success:
                QMessageBox.information(
                    self, "备份成功",
                    f"当前系统游标已备份到：\n{backup_dir / 'cursors_backup.reg'}"
                )
                self.status_bar.showMessage("备份成功")
            else:
                QMessageBox.warning(self, "备份失败", "备份游标失败，请以管理员身份运行")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def _restore_cursors(self):
        # 从备份恢复
        backup_dir = self.theme_manager.base_dir / "backup"
        reg_file = backup_dir / "cursors_backup.reg"
        if not reg_file.exists():
            QMessageBox.warning(self, "无备份", "未找到备份文件。请先通过「工具 - 备份当前游标」创建备份。")
            return
        reply = QMessageBox.question(
            self, "确认恢复",
            f"确定要从备份恢复系统游标吗？\n备份文件：{reg_file}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            success = system_cursor_api.restore_from_backup(backup_dir)
            if success:
                QMessageBox.information(self, "恢复成功", "系统游标已恢复")
                self.status_bar.showMessage("游标已恢复")
            else:
                QMessageBox.warning(self, "恢复失败", "恢复失败，请以管理员身份运行")
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

    def _refresh_system_cursors(self):
        # 刷新系统游标
        try:
            system_cursor_api.refresh_cursors()
            self.status_bar.showMessage("系统游标已刷新")
        except Exception as e:
            QMessageBox.critical(self, "刷新失败", str(e))

    def _show_about(self):
        # 关于对话框
        QMessageBox.about(
            self, f"关于 CursorVault",
            f"<h2>CursorVault 鼠标素材库</h2>"
            f"<p>版本 {__version__}</p>"
            f"<p>一款开源免费的 Windows 鼠标光标主题管理与替换工具。</p>"
            f"<p>支持从致美化 (zhutix.com) 下载的游标主题，一键替换系统游标。</p>"
            f"<hr><p>技术栈：Python 3 + PyQt6</p>"
            f"<p>协议：MIT License</p>"
        )

    # ── 在线素材库：下载安装 ────────────────────────────────────

    def _download_pack(self, pack: ZhutixPack):
        """下载并安装在线光标包."""
        if any(thread.isRunning() for thread in self._download_threads.values()):
            self.status_bar.showMessage("已有下载任务正在进行，请等待完成后再试")
            if self._online_panel and pack.slug in self._online_panel._cards:
                card = self._online_panel._cards[pack.slug]
                card._download_btn.setText("下载安装")
                card._download_btn.setEnabled(True)
            return
        download_dir = self.theme_manager.download_dir

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage(f"正在下载: {pack.title}...")

        thread = DownloadPackThread(
            ZhutixClient(),
            pack,
            download_dir,
            self.theme_manager,
        )
        self._download_threads[pack.slug] = thread
        thread.progress.connect(self._on_download_progress)
        thread.extract_signal.connect(
            lambda msg: self.status_bar.showMessage(msg)
        )
        thread.finished_signal.connect(
            lambda ok, msg, p: self._on_download_finished(ok, msg, p)
        )
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._download_threads.pop(pack.slug, None))
        thread.start()

    def _on_download_progress(self, downloaded: int, total: int):
        """下载进度回调."""
        if total > 0:
            pct = int(downloaded * 100 / total)
            self.progress_bar.setValue(pct)

    def _on_download_finished(self, success: bool, message: str, pack):
        """下载安装完成回调."""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(message)

        if success:
            # 刷新本地主题列表
            self._load_themes()
            # 刷新在线面板的安装状态
            if self._online_panel:
                self._online_panel.on_pack_installed(pack.slug)
            QMessageBox.information(self, "安装成功", message)
        else:
            QMessageBox.warning(self, "安装失败", message)
            # 恢复下载按钮状态
            if self._online_panel and pack.slug in self._online_panel._cards:
                card = self._online_panel._cards[pack.slug]
                card._download_btn.setText("下载安装")
                card._download_btn.setEnabled(True)

    def _apply_online_pack(self, slug: str):
        """应用在线安装的主题."""
        theme = self.theme_manager.get_theme(slug)
        if not theme or not theme.cursor_files:
            QMessageBox.warning(self, "无法应用", "该主题没有可用的光标文件")
            return

        self._current_theme = theme

        reply = QMessageBox.question(
            self, "确认应用",
            f"确定要应用主题「{theme.display_name}」到系统游标吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage("正在应用游标主题...")
        try:
            results = system_cursor_api.apply_theme(theme.cursor_files)
            failed = [ct.value for ct, success in results.items() if not success]
            if failed:
                raise RuntimeError(f"以下游标未能应用：{', '.join(failed)}")
            self.status_bar.showMessage(f"已应用: {theme.display_name}")
            QMessageBox.information(
                self, "应用成功",
                f"主题「{theme.display_name}」已应用到系统游标"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "应用失败",
                f"应用失败：{str(e)}\n请尝试以管理员身份运行本程序"
            )

    def closeEvent(self, event):
        event.accept()
