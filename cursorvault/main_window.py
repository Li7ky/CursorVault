# -*- coding: utf-8 -*-
"""CursorVault 主窗口."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    Qt,
    QSize,
    QThread,
    pyqtSignal,
    QUrl,
    QTimer,
    QStandardPaths,
)
from PyQt6.QtGui import QPixmap, QAction, QIcon, QIntValidator, QDesktopServices, QResizeEvent
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QSplitter,
    QScrollArea,
    QFrame,
    QTabWidget,
    QMessageBox,
    QStatusBar,
    QFileDialog,
    QProgressBar,
    QGridLayout,
    QInputDialog,
    QLineEdit,
    QToolBar,
    QSizePolicy,
    QButtonGroup,
)
from PyQt6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkRequest,
    QNetworkReply,
    QNetworkDiskCache,
)

from . import __version__, __app_name__
from .theme_manager import ThemeManager, sanitize_theme_slug
from .downloader import find_cursor_files
from .cursor_preview import CursorGalleryWidget
from .system_cursor import system_cursor_api
from .zhutix_client import ZhutixClient, ZhutixPack
from .ui_theme import APP_STYLESHEET
from .models import CursorType, CURSOR_CHINESE_NAMES
from .updater import GitHubUpdater, ReleaseInfo, is_newer

# ── 在线素材库：后台线程 ────────────────────────────────────────

class FetchPacksThread(QThread):
    """后台线程：获取光标包列表（含预览 URL 解析）."""

    packs_ready = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(
        self,
        client: ZhutixClient,
        page: int = 1,
        per_page: int = 50,
        orderby: str = "date",
        order: str = "desc",
    ):
        super().__init__()
        self._client = client
        self._page = page
        self._per_page = per_page
        self._orderby = orderby
        self._order = order

    def run(self) -> None:
        try:
            packs = self._client.fetch_page(
                self._page,
                self._per_page,
                orderby=self._orderby,
                order=self._order,
                resolve_previews=True,
            )
            self.progress.emit(self._page, self._client.total_pages or 1)
            self.packs_ready.emit(packs)
        except Exception as e:
            self.error.emit(str(e))


class DownloadPackThread(QThread):
    """后台线程：下载光标包."""

    progress = pyqtSignal(int, int)
    finished_signal = pyqtSignal(bool, str, object)
    extract_signal = pyqtSignal(str)

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
        self._abort = False

    def request_abort(self) -> None:
        self._abort = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            # 先解析直链（多策略）
            self.extract_signal.emit("正在获取下载链接…")
            url = self._client.resolve_download_url(self._pack)
            if not url:
                detail = getattr(self._client, "last_error", "") or (
                    "该素材需要 VIP 才能下载（无公开直链）"
                )
                # 特殊标记：让 UI 弹出并可选打开官网
                self.finished_signal.emit(
                    False,
                    f"NO_DIRECT_LINK::{detail}",
                    self._pack,
                )
                return

            self.extract_signal.emit("正在下载…")
            archive_path = self._client.download_pack(
                self._pack,
                self._download_dir,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                should_abort=lambda: self._abort or self.isInterruptionRequested(),
            )
            if self._abort or self.isInterruptionRequested():
                self.finished_signal.emit(False, "下载已取消", self._pack)
                return
            if not archive_path:
                detail = getattr(self._client, "last_error", "") or "下载失败"
                self.finished_signal.emit(False, f"下载失败：{detail}", self._pack)
                return

            size_kb = max(1, archive_path.stat().st_size // 1024)
            self.extract_signal.emit(
                f"正在解压并安装…（{archive_path.name} · {size_kb} KB）"
            )

            slug = (self._pack.slug or "").strip() or f"pack_{self._pack.post_id}"
            theme, err = self._theme_manager.install_from_archive(
                archive_path,
                slug=slug,
                display_name=self._pack.title or slug,
                source_url=self._pack.url,
            )
            if theme:
                count = len(theme.cursor_files)
                complete = (
                    "完整 15 类"
                    if theme.is_complete()
                    else f"{count}/15 类（可正常使用）"
                )
                self.finished_signal.emit(
                    True,
                    f"安装成功！已导入 {count} 个光标文件（{complete}）",
                    self._pack,
                )
            else:
                # 永远不要再显示旧的笼统文案；附带文件信息便于排查
                msg = err or "安装失败：未能从压缩包中识别游标文件"
                msg += f"\n\n文件：{archive_path.name}（{size_kb} KB）"
                self.finished_signal.emit(False, msg, self._pack)
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            try:
                log = self._download_dir / "last_install_error.txt"
                log.write_text(tb, encoding="utf-8")
            except OSError:
                pass
            self.finished_signal.emit(False, f"安装出错: {e}", self._pack)


class CheckUpdateThread(QThread):
    """后台检查 GitHub 最新版本."""

    finished_ok = pyqtSignal(object, bool)  # ReleaseInfo, silent
    failed = pyqtSignal(str, bool)  # error, silent

    def __init__(self, base_dir: Path, silent: bool = False, parent=None):
        super().__init__(parent)
        self._base_dir = base_dir
        self.silent = silent

    def run(self) -> None:
        try:
            updater = GitHubUpdater(self._base_dir)
            info = updater.check_latest()
            if info is None:
                self.failed.emit(updater.last_error or "检查更新失败", self.silent)
            else:
                self.finished_ok.emit(info, self.silent)
        except Exception as e:
            self.failed.emit(str(e), self.silent)


class ApplyUpdateThread(QThread):
    """后台下载并应用更新."""

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(object)  # ReleaseInfo
    failed = pyqtSignal(str)

    def __init__(self, base_dir: Path, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self._base_dir = base_dir
        self._release = release

    def run(self) -> None:
        try:
            updater = GitHubUpdater(self._base_dir)
            ok = updater.download_and_apply(
                self._release,
                progress_cb=lambda d, t: self.progress.emit(d, t),
            )
            if ok:
                self.finished_ok.emit(self._release)
            else:
                self.failed.emit(updater.last_error or "更新失败")
        except Exception as e:
            self.failed.emit(str(e))


# ── 在线素材库：骨架屏 / 卡片 ───────────────────────────────────

class SkeletonCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("packCard")
        self.setFixedSize(248, 272)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        for w, h in ((220, 124), (160, 14), (96, 12)):
            box = QLabel()
            box.setFixedSize(w, h)
            box.setStyleSheet("background: #e2e8f0; border-radius: 8px;")
            layout.addWidget(box)
        layout.addStretch()
        btn = QLabel()
        btn.setFixedSize(220, 36)
        btn.setStyleSheet("background: #e2e8f0; border-radius: 9px;")
        layout.addWidget(btn)


class PackCard(QFrame):
    download_clicked = pyqtSignal(object)
    apply_clicked = pyqtSignal(str)

    def __init__(self, pack: ZhutixPack, installed: bool = False, parent=None):
        super().__init__(parent)
        self.pack = pack
        self._installed = installed
        self.setObjectName("packCard")
        self.setFixedSize(248, 272)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self._preview_label = QLabel()
        self._preview_label.setObjectName("packPreview")
        self._preview_label.setFixedSize(220, 124)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setText("加载中...")
        layout.addWidget(self._preview_label, alignment=Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(pack.title)
        title_label.setObjectName("packTitle")
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(40)
        layout.addWidget(title_label)

        info_row = QHBoxLayout()
        info_row.setSpacing(6)
        date_str = pack.modified[:10] if pack.modified else ""
        if date_str:
            date_tag = QLabel(date_str)
            date_tag.setObjectName("packDateTag")
            info_row.addWidget(date_tag)
        self._badge = QLabel("已安装")
        self._badge.setObjectName("installedBadge")
        self._badge.setVisible(installed)
        info_row.addWidget(self._badge)

        can_direct = bool(pack.has_direct_link or pack.download_url)
        # 无公开直链 = 软件内不能一键下，需 VIP 在官网下载
        self._link_badge = QLabel("可直链" if can_direct else "需要VIP才能下载")
        self._link_badge.setObjectName(
            "installedBadge" if can_direct else "themeInfoTag"
        )
        if not can_direct:
            self._link_badge.setProperty("tone", "warn")
            self._link_badge.setToolTip("此素材需要 VIP 才能下载，软件内无法直接获取。")
        else:
            self._link_badge.setToolTip("支持在本软件内一键下载安装")
        info_row.addWidget(self._link_badge)
        info_row.addStretch()
        layout.addLayout(info_row)
        layout.addStretch()

        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(8)
        self._download_btn = QPushButton("下载安装" if can_direct else "需要VIP才能下载")
        self._download_btn.setObjectName("downloadBtn" if can_direct else "toolBtn")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.setToolTip(
            "一键下载并安装" if can_direct else "需要VIP才能下载"
        )
        self._download_btn.clicked.connect(lambda: self.download_clicked.emit(self.pack))
        self._btn_row.addWidget(self._download_btn, 1)

        self._apply_btn = QPushButton("应用")
        self._apply_btn.setObjectName("applyOnlineBtn")
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.clicked.connect(lambda: self.apply_clicked.emit(self.pack.slug))
        self._apply_btn.setVisible(installed)
        self._btn_row.addWidget(self._apply_btn)

        if installed:
            self._download_btn.setText("已安装")
            self._download_btn.setEnabled(False)

        layout.addLayout(self._btn_row)

    def set_preview_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                220,
                124,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_label.setPixmap(scaled)
            self._preview_label.setText("")
        else:
            self._preview_label.clear()
            self._preview_label.setText("无预览图")

    def set_downloading(self) -> None:
        self._download_btn.setText("下载中...")
        self._download_btn.setEnabled(False)

    def reset_download_button(self) -> None:
        if self._installed:
            self._download_btn.setText("已安装")
            self._download_btn.setEnabled(False)
        else:
            can_direct = bool(self.pack.has_direct_link or self.pack.download_url)
            self._download_btn.setText(
                "下载安装" if can_direct else "需要VIP才能下载"
            )
            self._download_btn.setObjectName("downloadBtn" if can_direct else "toolBtn")
            self._download_btn.setEnabled(True)
            # 刷新样式
            self._download_btn.style().unpolish(self._download_btn)
            self._download_btn.style().polish(self._download_btn)

    def set_installed_state(self) -> None:
        self._installed = True
        self._badge.setVisible(True)
        self._download_btn.setText("已安装")
        self._download_btn.setEnabled(False)
        self._apply_btn.setVisible(True)


# ── 在线素材库面板 ────────────────────────────────────────────

class OnlineLibraryPanel(QWidget):
    pack_download_requested = pyqtSignal(object)
    pack_apply_requested = pyqtSignal(str)

    # 筛选 → WP orderby / order（三项互斥，语义区分）
    FILTER_ORDER = {
        "latest": ("date", "desc"),      # 最新发布
        "hot": ("modified", "desc"),     # 近期更新
        "all": ("id", "desc"),           # 全部（按 ID）
    }
    FILTER_LABELS = {
        "latest": "最新发布",
        "hot": "近期更新",
        "all": "全部",
    }
    MAX_CONCURRENT_PREVIEWS = 6
    # 与 PackCard / SkeletonCard 固定宽度保持一致
    CARD_WIDTH = 248
    CARD_GAP = 12
    GRID_SIDE_MIN = 12

    def __init__(self, theme_manager: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._client = ZhutixClient()
        self._packs: list[ZhutixPack] = []
        self._cards: dict[str, PackCard] = {}
        self._skeleton_cards: list[SkeletonCard] = []
        self._current_page = 1
        self._total_pages = 1
        self._per_page = 24  # 更少卡片，滚动更顺
        self._filter = "latest"
        self._grid_cols = 4
        self._fetch_thread: Optional[FetchPacksThread] = None
        self._fetch_generation = 0
        self._pending_refetch = False
        self._network = QNetworkAccessManager(self)
        self._setup_network_cache()
        self._preview_jobs: dict[str, QNetworkReply] = {}
        self._preview_queue: list[ZhutixPack] = []
        self._active_previews = 0
        self._shutting_down = False

        # 搜索 / 列数防抖
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._apply_search)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._update_grid_columns)

        self._setup_ui()
        self._fetch_packs()

    def _setup_network_cache(self) -> None:
        cache = QNetworkDiskCache(self)
        cache_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        if not cache_dir:
            cache_dir = str(Path.home() / ".cursorvault_cache")
        cache.setCacheDirectory(str(Path(cache_dir) / "preview_images"))
        cache.setMaximumCacheSize(64 * 1024 * 1024)
        self._network.setCache(cache)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 10)
        layout.setSpacing(8)

        # ── 顶栏：标题 | 分段筛选 | 搜索 + 刷新 ──
        header = QWidget()
        header.setObjectName("onlineHeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("在线素材库")
        title.setObjectName("onlineTitle")
        title_col.addWidget(title)
        self._count_label = QLabel("加载中…")
        self._count_label.setObjectName("onlineCount")
        title_col.addWidget(self._count_label)
        top_row.addLayout(title_col, 0)
        top_row.addStretch(1)

        # 互斥分段筛选（QButtonGroup，一次只能选一个）
        segment = QFrame()
        segment.setObjectName("filterSegment")
        seg_layout = QHBoxLayout(segment)
        seg_layout.setContentsMargins(4, 4, 4, 4)
        seg_layout.setSpacing(0)

        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: dict[str, QPushButton] = {}
        filter_defs = [
            ("latest", "最新发布", "按发布日期从新到旧"),
            ("hot", "近期更新", "按最近修改时间"),
            ("all", "全部", "按条目 ID 排列"),
        ]
        for i, (key, label, tip) in enumerate(filter_defs):
            btn = QPushButton(label)
            btn.setObjectName("filterTag")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip)
            btn.setProperty("filterKey", key)
            btn.setMinimumWidth(84)
            self._filter_group.addButton(btn, i)
            self._filter_buttons[key] = btn
            seg_layout.addWidget(btn)
        self._filter_buttons["latest"].setChecked(True)
        self._filter_group.idClicked.connect(self._on_filter_id_clicked)
        top_row.addWidget(segment, 0)

        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchInput")
        self._search_input.setPlaceholderText("搜索本页名称…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedWidth(220)
        self._search_input.textChanged.connect(self._on_search_text)
        top_row.addWidget(self._search_input)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("toolBtn")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._fetch_packs)
        top_row.addWidget(refresh_btn)

        header_layout.addLayout(top_row)

        status_row = QHBoxLayout()
        self._status_label = QLabel("正在加载…")
        self._status_label.setObjectName("onlineStatus")
        status_row.addWidget(self._status_label, 1)
        header_layout.addLayout(status_row)

        self._progress = QProgressBar()
        self._progress.setObjectName("globalProgress")
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(3)
        header_layout.addWidget(self._progress)
        layout.addWidget(header)

        # ── 内容区（网格水平居中，左右留白对称） ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 始终预留纵向滚动条宽度，避免出现/消失时左右视觉偏移
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setObjectName("onlineScroll")
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._grid_host = QWidget()
        self._grid_host.setObjectName("onlineGridHost")
        host_layout = QVBoxLayout(self._grid_host)
        # 左右边距由 _sync_grid_geometry 动态均分
        host_layout.setContentsMargins(0, 4, 0, 8)
        host_layout.setSpacing(0)
        host_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._grid_container = QWidget()
        self._grid_container.setObjectName("onlineGridContainer")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setHorizontalSpacing(self.CARD_GAP)
        self._grid_layout.setVerticalSpacing(self.CARD_GAP)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        # 不拉伸列，卡片保持固定宽度，剩余空间分给两侧
        host_layout.addWidget(
            self._grid_container,
            0,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        )

        self._empty_state = QLabel("暂无符合条件的光标包")
        self._empty_state.setObjectName("emptyState")
        self._empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state.setVisible(False)
        host_layout.addWidget(self._empty_state)
        host_layout.addStretch(1)

        self._scroll.setWidget(self._grid_host)
        layout.addWidget(self._scroll, 1)

        # ── 底部分页（紧凑） ──
        page_bar_widget = QWidget()
        page_bar_widget.setObjectName("pageBarWidget")
        page_bar = QHBoxLayout(page_bar_widget)
        page_bar.setContentsMargins(12, 8, 12, 8)
        page_bar.setSpacing(8)

        self._status_page = QLabel("")
        self._status_page.setObjectName("onlineStatus")
        page_bar.addWidget(self._status_page, 1)

        self._first_btn = QPushButton("首页")
        self._first_btn.setObjectName("toolBtn")
        self._first_btn.clicked.connect(self._first_page)
        page_bar.addWidget(self._first_btn)

        self._prev_btn = QPushButton("上一页")
        self._prev_btn.setObjectName("toolBtn")
        self._prev_btn.clicked.connect(self._prev_page)
        page_bar.addWidget(self._prev_btn)

        self._page_label = QLabel("1 / 1")
        self._page_label.setObjectName("pageLabel")
        page_bar.addWidget(self._page_label)

        self._next_btn = QPushButton("下一页")
        self._next_btn.setObjectName("toolBtn")
        self._next_btn.clicked.connect(self._next_page)
        page_bar.addWidget(self._next_btn)

        self._last_btn = QPushButton("末页")
        self._last_btn.setObjectName("toolBtn")
        self._last_btn.clicked.connect(self._last_page)
        page_bar.addWidget(self._last_btn)

        page_jump_label = QLabel("跳至")
        page_jump_label.setObjectName("pageTotal")
        page_bar.addWidget(page_jump_label)
        self._page_input = QLineEdit()
        self._page_input.setObjectName("pageInput")
        self._page_input.setValidator(QIntValidator(1, 9999))
        self._page_input.setFixedWidth(52)
        self._page_input.returnPressed.connect(self._go_to_page_input)
        page_bar.addWidget(self._page_input)
        page_jump_total = QLabel("页")
        page_jump_total.setObjectName("pageTotal")
        page_bar.addWidget(page_jump_total)

        layout.addWidget(page_bar_widget)
        self._set_page_buttons_enabled(False)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._resize_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # 首次显示时视口宽度才准确，补一次对称布局
        QTimer.singleShot(0, self._sync_grid_geometry)

    def _on_filter_id_clicked(self, _btn_id: int) -> None:
        btn = self._filter_group.checkedButton()
        if btn is None:
            return
        key = btn.property("filterKey")
        if not key or key == self._filter:
            return
        self._filter = key
        self._current_page = 1
        self._search_input.clear()
        self._fetch_packs()

    def _viewport_content_width(self) -> int:
        """滚动区可用于排布卡片的宽度（视口已扣除滚动条）。"""
        vw = self._scroll.viewport().width()
        if vw <= 0:
            vw = max(self.width() - 40, 260)
        return max(vw, 260)

    def _calc_grid_cols(self, usable_width: int) -> int:
        inner = max(self.CARD_WIDTH, usable_width - 2 * self.GRID_SIDE_MIN)
        cols = max(1, (inner + self.CARD_GAP) // (self.CARD_WIDTH + self.CARD_GAP))
        while cols > 1:
            need = (
                cols * self.CARD_WIDTH
                + (cols - 1) * self.CARD_GAP
                + 2 * self.GRID_SIDE_MIN
            )
            if need <= usable_width:
                break
            cols -= 1
        return cols

    def _sync_grid_geometry(self) -> None:
        """按视口宽度计算列数，并均分左右留白，保证对称。"""
        usable = self._viewport_content_width()
        cols = self._calc_grid_cols(usable)
        content_w = cols * self.CARD_WIDTH + max(0, cols - 1) * self.CARD_GAP
        leftover = max(0, usable - content_w)
        side = max(self.GRID_SIDE_MIN, leftover // 2)
        right = leftover - side  # 奇数像素差分给一侧，最多差 1px

        host_layout = self._grid_host.layout()
        if host_layout is not None:
            host_layout.setContentsMargins(side, 8, right, 12)

        self._grid_container.setFixedWidth(content_w)

        cols_changed = cols != self._grid_cols
        self._grid_cols = cols
        if cols_changed and (self._cards or self._skeleton_cards):
            self._relayout_cards()

    def _update_grid_columns(self) -> None:
        self._sync_grid_geometry()

    def _relayout_cards(self) -> None:
        if self._cards:
            ordered: list = list(self._cards.values())
        elif self._skeleton_cards:
            ordered = list(self._skeleton_cards)
        else:
            return

        self._grid_container.setUpdatesEnabled(False)
        try:
            for card in ordered:
                self._grid_layout.removeWidget(card)
            for i, card in enumerate(ordered):
                self._grid_layout.addWidget(
                    card,
                    i // self._grid_cols,
                    i % self._grid_cols,
                    Qt.AlignmentFlag.AlignTop,
                )
        finally:
            self._grid_container.setUpdatesEnabled(True)

    def _set_page_buttons_enabled(self, enabled: bool) -> None:
        if not enabled:
            for b in (
                self._first_btn,
                self._prev_btn,
                self._next_btn,
                self._last_btn,
            ):
                b.setEnabled(False)
            return
        self._first_btn.setEnabled(self._current_page > 1)
        self._prev_btn.setEnabled(self._current_page > 1)
        can_next = self._total_pages > 0 and self._current_page < self._total_pages
        self._next_btn.setEnabled(can_next)
        self._last_btn.setEnabled(can_next)

    def _abort_preview_jobs(self) -> None:
        self._preview_queue.clear()
        for reply in list(self._preview_jobs.values()):
            try:
                reply.finished.disconnect()
            except TypeError:
                pass
            try:
                reply.abort()
                reply.deleteLater()
            except RuntimeError:
                pass
        self._preview_jobs.clear()
        self._active_previews = 0

    def _show_skeletons(self) -> None:
        self._clear_cards()
        self._empty_state.setVisible(False)
        self._sync_grid_geometry()
        n = min(self._grid_cols * 2, 8)
        self._grid_container.setUpdatesEnabled(False)
        try:
            for i in range(n):
                card = SkeletonCard(self._grid_container)
                self._grid_layout.addWidget(
                    card,
                    i // self._grid_cols,
                    i % self._grid_cols,
                    Qt.AlignmentFlag.AlignTop,
                )
                self._skeleton_cards.append(card)
        finally:
            self._grid_container.setUpdatesEnabled(True)

    def _hide_skeletons(self) -> None:
        for card in self._skeleton_cards:
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._skeleton_cards.clear()

    def _fetch_packs(self) -> None:
        if self._shutting_down:
            return
        if self._fetch_thread and self._fetch_thread.isRunning():
            # 加载中再次切换：标记待刷新，丢弃即将返回的旧结果
            self._pending_refetch = True
            self._fetch_generation += 1
            self._status_label.setText("正在切换，请稍候…")
            return

        self._pending_refetch = False
        orderby, order = self.FILTER_ORDER.get(self._filter, ("date", "desc"))
        self._fetch_generation += 1
        gen = self._fetch_generation

        self._progress.setVisible(True)
        self._status_label.setText(f"正在加载第 {self._current_page} 页…")
        self._set_page_buttons_enabled(False)
        self._show_skeletons()

        self._fetch_thread = FetchPacksThread(
            self._client,
            self._current_page,
            self._per_page,
            orderby=orderby,
            order=order,
        )
        self._fetch_thread.packs_ready.connect(
            lambda packs, g=gen: self._on_packs_ready(packs, g)
        )
        self._fetch_thread.progress.connect(self._on_fetch_progress)
        self._fetch_thread.error.connect(
            lambda err, g=gen: self._on_fetch_error(err, g)
        )
        self._fetch_thread.finished.connect(self._on_fetch_thread_finished)
        self._fetch_thread.start()

    def _on_fetch_thread_finished(self) -> None:
        thread = self.sender()
        if thread is not None:
            thread.deleteLater()
        self._fetch_thread = None
        if self._pending_refetch and not self._shutting_down:
            self._pending_refetch = False
            self._fetch_packs()

    def _clear_cards(self) -> None:
        self._abort_preview_jobs()
        self._grid_container.setUpdatesEnabled(False)
        try:
            for card in self._cards.values():
                self._grid_layout.removeWidget(card)
                card.deleteLater()
            self._cards.clear()
            self._hide_skeletons()
        finally:
            self._grid_container.setUpdatesEnabled(True)

    def _on_packs_ready(self, packs: list, generation: int) -> None:
        if self._shutting_down or generation != self._fetch_generation:
            return
        self._packs = packs
        self._progress.setVisible(False)
        self._hide_skeletons()
        total = self._client.total or 0

        filter_hint = self.FILTER_LABELS.get(self._filter, "")
        self._count_label.setText(f"共 {total} 个  ·  {filter_hint}")

        if not packs:
            self._empty_state.setVisible(True)
            self._status_label.setText("暂无数据")
            self._status_page.setText("")
        else:
            self._empty_state.setVisible(False)
            self._status_label.setText(
                f"第 {self._current_page}/{self._total_pages or 1} 页  ·  本页 {len(packs)} 个"
            )
            self._status_page.setText(f"每页 {self._per_page} 个")

        self._set_page_buttons_enabled(True)
        self._page_label.setText(f"{self._current_page} / {self._total_pages or 1}")

        # 批量创建卡片，关闭重绘；先同步对称边距与列数
        self._sync_grid_geometry()
        self._grid_container.setUpdatesEnabled(False)
        try:
            for i, pack in enumerate(packs):
                installed = self._theme_manager.is_installed(pack.slug)
                card = PackCard(pack, installed=installed)
                card.download_clicked.connect(self._on_download_clicked)
                card.apply_clicked.connect(self._on_apply_clicked)
                self._grid_layout.addWidget(
                    card,
                    i // self._grid_cols,
                    i % self._grid_cols,
                    Qt.AlignmentFlag.AlignTop,
                )
                self._cards[pack.slug] = card
        finally:
            self._grid_container.setUpdatesEnabled(True)
        # 创建后再次校准（滚动条状态可能变化）
        QTimer.singleShot(0, self._sync_grid_geometry)

        # 预览图限流加载
        for pack in packs:
            self._enqueue_preview(pack)

        if self._search_input.text().strip():
            self._apply_search()

    def _on_fetch_progress(self, page: int, total_pages: int) -> None:
        self._total_pages = total_pages

    def _on_fetch_error(self, err: str, generation: int) -> None:
        if generation != self._fetch_generation:
            return
        self._progress.setVisible(False)
        self._hide_skeletons()
        self._status_label.setText(f"加载失败: {err}")
        self._set_page_buttons_enabled(True)
        QMessageBox.warning(self, "加载失败", f"获取光标包列表失败:\n{err}")

    def _enqueue_preview(self, pack: ZhutixPack) -> None:
        url = self._client.peek_preview_url(pack) or pack.preview_url
        if not url:
            card = self._cards.get(pack.slug)
            if card:
                card.set_preview_pixmap(QPixmap())
            return
        self._preview_queue.append(pack)
        self._pump_previews()

    def _pump_previews(self) -> None:
        while (
            self._active_previews < self.MAX_CONCURRENT_PREVIEWS
            and self._preview_queue
            and not self._shutting_down
        ):
            pack = self._preview_queue.pop(0)
            if pack.slug not in self._cards:
                continue
            url = self._client.peek_preview_url(pack) or pack.preview_url
            if not url:
                continue
            request = QNetworkRequest(QUrl(url))
            request.setAttribute(
                QNetworkRequest.Attribute.CacheLoadControlAttribute,
                QNetworkRequest.CacheLoadControl.PreferCache,
            )
            reply = self._network.get(request)
            self._preview_jobs[pack.slug] = reply
            self._active_previews += 1
            reply.finished.connect(
                lambda slug=pack.slug, r=reply: self._on_preview_loaded(slug, r)
            )

    def _on_preview_loaded(self, slug: str, reply: QNetworkReply) -> None:
        self._preview_jobs.pop(slug, None)
        self._active_previews = max(0, self._active_previews - 1)
        try:
            if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
                return
            card = self._cards.get(slug)
            if not card:
                return
            if reply.error() != QNetworkReply.NetworkError.NoError:
                card.set_preview_pixmap(QPixmap())
                return
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(bytes(data)):
                card.set_preview_pixmap(pixmap)
            else:
                card.set_preview_pixmap(QPixmap())
        finally:
            reply.deleteLater()
            self._pump_previews()

    def _on_download_clicked(self, pack: ZhutixPack) -> None:
        if pack.slug in self._cards:
            self._cards[pack.slug].set_downloading()
        self._status_label.setText(f"正在下载安装: {pack.title}…")
        self.pack_download_requested.emit(pack)

    def _on_apply_clicked(self, slug: str) -> None:
        self.pack_apply_requested.emit(slug)

    def _on_search_text(self, _text: str) -> None:
        self._search_timer.start()

    def _apply_search(self) -> None:
        text = self._search_input.text().strip().lower()
        visible_count = 0
        self._grid_container.setUpdatesEnabled(False)
        try:
            for slug, card in self._cards.items():
                if not text:
                    card.setVisible(True)
                    visible_count += 1
                else:
                    match = text in card.pack.title.lower() or text in slug.lower()
                    card.setVisible(match)
                    if match:
                        visible_count += 1
        finally:
            self._grid_container.setUpdatesEnabled(True)

        self._empty_state.setVisible(visible_count == 0 and len(self._cards) > 0)
        if text and self._cards:
            self._status_label.setText(
                f"本页「{text}」：{visible_count} 个结果"
            )
        elif self._packs:
            self._status_label.setText(
                f"第 {self._current_page}/{self._total_pages or 1} 页  ·  本页 {len(self._packs)} 个"
            )

    def _first_page(self) -> None:
        if self._current_page != 1:
            self._current_page = 1
            self._fetch_packs()

    def _prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._fetch_packs()

    def _next_page(self) -> None:
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._fetch_packs()

    def _last_page(self) -> None:
        if self._current_page != self._total_pages and self._total_pages > 0:
            self._current_page = self._total_pages
            self._fetch_packs()

    def _go_to_page_input(self) -> None:
        try:
            page = int(self._page_input.text().strip())
        except ValueError:
            return
        if page < 1 or page > max(1, self._total_pages):
            QMessageBox.warning(
                self, "页码错误", f"请输入 1 到 {self._total_pages or 1} 之间的页码"
            )
            return
        if page != self._current_page:
            self._current_page = page
            self._fetch_packs()
        self._page_input.clear()

    def on_pack_installed(self, slug: str) -> None:
        card = self._cards.get(slug)
        if card:
            card.set_installed_state()
        self._status_label.setText(f"安装完成: {slug}")

    def reset_pack_download_button(self, slug: str) -> None:
        card = self._cards.get(slug)
        if card:
            card.reset_download_button()

    def refresh_installed_status(self) -> None:
        for slug, card in self._cards.items():
            if self._theme_manager.is_installed(slug):
                card.set_installed_state()

    def shutdown(self) -> None:
        """窗口关闭时清理网络与线程."""
        self._shutting_down = True
        self._search_timer.stop()
        self._resize_timer.stop()
        self._abort_preview_jobs()
        if self._fetch_thread and self._fetch_thread.isRunning():
            self._fetch_thread.requestInterruption()
            self._fetch_thread.wait(2000)


# ── 主窗口 ────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, theme_manager: ThemeManager):
        super().__init__()
        self.theme_manager = theme_manager
        self._current_theme = None
        self._download_threads: dict[str, DownloadPackThread] = {}
        self._online_panel: Optional[OnlineLibraryPanel] = None
        self._preview_widget: Optional[CursorGalleryWidget] = None

        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setMinimumSize(1120, 740)
        self.resize(1280, 820)
        self.setStyleSheet(APP_STYLESHEET)
        self._update_thread: Optional[QThread] = None
        self._pending_manual_update_check = False
        self._apply_window_icon()

        self._setup_menu_bar()
        self._setup_ui()
        self._setup_status_bar()
        self._load_themes()
        # 启动数秒后静默检查更新（有新版本才弹窗）
        QTimer.singleShot(2500, self._check_update_silent)

    def _apply_window_icon(self) -> None:
        """设置窗口 / 任务栏图标."""
        base = self.theme_manager.base_dir if hasattr(self, "theme_manager") else None
        # theme_manager 在 set 之后才有；构造早期用路径推断
        roots = []
        if base is not None:
            roots.append(Path(base))
        roots.append(Path(__file__).resolve().parent.parent)
        for root in roots:
            for name in ("assets/app_icon.ico", "assets/app_icon.png"):
                path = root / name
                if path.exists():
                    icon = QIcon(str(path))
                    if not icon.isNull():
                        self.setWindowIcon(icon)
                        return

    def _setup_menu_bar(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")
        import_action = QAction("导入游标目录...", self)
        import_action.triggered.connect(self._import_cursors)
        file_menu.addAction(import_action)
        file_menu.addSeparator()
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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

        help_menu = menubar.addMenu("帮助(&H)")
        update_action = QAction("检查更新...", self)
        update_action.triggered.connect(self._check_update_manual)
        help_menu.addAction(update_action)
        help_menu.addSeparator()
        about_action = QAction(f"关于 {__app_name__}", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(10)

        toolbar = QToolBar("常用操作")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        self.backup_btn = QAction("备份系统光标", self)
        self.backup_btn.triggered.connect(self._backup_cursors)
        toolbar.addAction(self.backup_btn)

        self.import_btn = QAction("导入自定义…", self)
        self.import_btn.triggered.connect(self._import_cursors)
        toolbar.addAction(self.import_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("globalProgress")
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        main_layout.addWidget(self.progress_bar)

        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("mainTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(False)

        # --- 本地主题 ---
        local_tab = QWidget()
        local_layout = QHBoxLayout(local_tab)
        local_layout.setContentsMargins(2, 4, 2, 2)
        local_layout.setSpacing(12)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(340)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 14, 14, 14)
        sidebar_layout.setSpacing(10)

        sidebar_header_w = QWidget()
        sidebar_header_layout = QHBoxLayout(sidebar_header_w)
        sidebar_header_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_title = QLabel("主题列表")
        sidebar_title.setObjectName("sidebarTitle")
        sidebar_header_layout.addWidget(sidebar_title)
        self.theme_count_badge = QLabel("0")
        self.theme_count_badge.setObjectName("countBadge")
        sidebar_header_layout.addWidget(self.theme_count_badge)
        sidebar_header_layout.addStretch()
        sidebar_layout.addWidget(sidebar_header_w)

        self._local_search = QLineEdit()
        self._local_search.setObjectName("searchInput")
        self._local_search.setPlaceholderText("搜索本地主题…")
        self._local_search.setClearButtonEnabled(True)
        self._local_search.textChanged.connect(self._on_local_search)
        sidebar_layout.addWidget(self._local_search)

        self.theme_list = QListWidget()
        self.theme_list.setObjectName("themeList")
        self.theme_list.setIconSize(QSize(40, 40))
        self.theme_list.setSpacing(2)
        self.theme_list.setUniformItemSizes(True)
        self.theme_list.currentRowChanged.connect(self._on_theme_selected)
        sidebar_layout.addWidget(self.theme_list, 1)

        self._local_empty = QLabel("还没有本地主题\n可从在线库安装，或导入自定义目录")
        self._local_empty.setObjectName("emptyState")
        self._local_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._local_empty.setVisible(False)
        sidebar_layout.addWidget(self._local_empty)

        content_panel = QWidget()
        content_panel.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.theme_info_bar = QWidget()
        self.theme_info_bar.setObjectName("themeInfoBar")
        self.theme_info_bar.setVisible(False)
        info_layout = QHBoxLayout(self.theme_info_bar)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_layout.setSpacing(14)

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

        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)

        self.apply_btn = QPushButton("应用到系统")
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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

        # 单一滚动区（画廊内部不再嵌套滚动）
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("previewScroll")
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.preview_container = QWidget()
        self.preview_container.setObjectName("previewInner")
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(8, 8, 8, 8)
        self.preview_layout.setSpacing(0)
        self.preview_scroll.setWidget(self.preview_container)
        content_layout.addWidget(self.preview_scroll, 1)

        self._preview_placeholder = QLabel(
            "选择左侧主题以预览光标\n或切换到「在线素材库」下载新主题"
        )
        self._preview_placeholder.setObjectName("emptyState")
        self._preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_layout.addWidget(self._preview_placeholder)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(sidebar)
        splitter.addWidget(content_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])
        splitter.setHandleWidth(10)
        local_layout.addWidget(splitter)

        self._tabs.addTab(local_tab, "  本地主题  ")

        self._online_panel = OnlineLibraryPanel(self.theme_manager)
        self._online_panel.pack_download_requested.connect(self._download_pack)
        self._online_panel.pack_apply_requested.connect(self._apply_online_pack)
        self._tabs.addTab(self._online_panel, "  在线素材库  ")

        body_layout.addWidget(self._tabs)
        main_layout.addWidget(body_widget, 1)

    def _setup_status_bar(self) -> None:
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 — 请选择主题或打开在线素材库")

    def _clear_preview(self, show_placeholder: bool = True) -> None:
        if self._preview_widget is not None:
            try:
                self._preview_widget.cleanup()
            except Exception:
                pass
            self._preview_widget = None
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if show_placeholder:
            self._preview_placeholder = QLabel(
                "选择左侧主题以预览光标\n或切换到「在线素材库」下载新主题"
            )
            self._preview_placeholder.setObjectName("emptyState")
            self._preview_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_layout.addWidget(self._preview_placeholder)

    def _load_themes(self) -> None:
        # 记住当前选中主题，避免下载完成后被强制跳回第一项
        prev_name = None
        if self._current_theme is not None:
            prev_name = getattr(self._current_theme, "name", None)
        current_item = self.theme_list.currentItem()
        if current_item is not None:
            prev_name = current_item.data(Qt.ItemDataRole.UserRole) or prev_name

        self.theme_manager.reload()
        self.theme_list.blockSignals(True)
        self.theme_list.clear()
        self._theme_items: list[tuple[QListWidgetItem, str]] = []

        select_row = 0
        for idx, theme in enumerate(self.theme_manager.themes):
            item = QListWidgetItem()
            item.setText(theme.display_name)
            item.setData(Qt.ItemDataRole.UserRole, theme.name)
            item.setSizeHint(QSize(0, 52))
            count = theme.get_cursor_count()
            tip = f"{count}/15 个光标"
            if theme.source_url:
                tip += f"\n{theme.source_url}"
            else:
                tip += "\n本地导入主题"
            item.setToolTip(tip)

            theme_dir = self.theme_manager.get_theme_dir(theme.name)
            preview_path = theme_dir / "preview.png" if theme_dir else None
            if preview_path and preview_path.exists():
                pixmap = QPixmap(str(preview_path))
                if not pixmap.isNull():
                    item.setIcon(
                        QIcon(
                            pixmap.scaled(
                                40,
                                40,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )
                    )
            self.theme_list.addItem(item)
            self._theme_items.append((item, theme.name))
            if prev_name and theme.name == prev_name:
                select_row = idx

        self.theme_list.blockSignals(False)
        total = self.theme_list.count()
        self.theme_count_badge.setText(str(total))
        self._local_empty.setVisible(total == 0)
        self.theme_list.setVisible(total > 0)

        if total > 0:
            self.theme_list.setCurrentRow(select_row)
        else:
            self._current_theme = None
            self._clear_preview(show_placeholder=True)
            self.theme_info_bar.setVisible(False)
            self.apply_btn.setEnabled(False)
            self._delete_theme_btn.setVisible(False)
            self._open_source_btn.setVisible(False)

        if self._online_panel:
            self._online_panel.refresh_installed_status()

    def _on_local_search(self, text: str) -> None:
        text = text.strip().lower()
        for item, _ in self._theme_items:
            if not text:
                item.setHidden(False)
            else:
                item.setHidden(text not in item.text().lower())

    def _on_theme_selected(self, row: int) -> None:
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
        self.theme_info_bar.setVisible(True)
        self.theme_title_label.setText(theme.display_name)

        theme_dir = self.theme_manager.get_theme_dir(theme_name)
        preview_path = theme_dir / "preview.png" if theme_dir else None
        if preview_path and preview_path.exists():
            pixmap = QPixmap(str(preview_path))
            if not pixmap.isNull():
                self.theme_icon_label.setPixmap(
                    pixmap.scaled(
                        52,
                        52,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                self.theme_icon_label.clear()
                self.theme_icon_label.setText("🖱️")
        else:
            self.theme_icon_label.clear()
            self.theme_icon_label.setText("🖱️")

        installed_count = len(theme.cursor_files) if theme.cursor_files else 0
        total_count = 15
        complete = theme.is_complete()
        self.theme_meta_label.setText(
            f"{installed_count} 个光标文件 · {'完整套装' if complete else '部分光标'}"
        )
        self._theme_count_tag.setText(f"{installed_count}/{total_count}")
        self._theme_count_tag.setToolTip(
            "已识别的游标类型数 / Windows 标准 15 类\n"
            "（标准选择、帮助、后台运行、忙碌、精确、文本、手写、不可用、\n"
            "移动、四种缩放、备用、链接）"
        )
        self._theme_count_tag.setVisible(True)
        if complete:
            self._theme_complete_tag.setText("完整套装")
            self._theme_complete_tag.setToolTip(
                "已包含全部 15 种 Windows 标准游标，可完整替换系统指针。"
            )
            self._theme_complete_tag.setProperty("tone", "")
        else:
            self._theme_complete_tag.setText(f"部分 {installed_count}/15")
            missing = [
                CURSOR_CHINESE_NAMES.get(ct, ct.value)
                for ct in CursorType
                if ct not in (theme.cursor_files or {})
            ]
            miss_txt = "、".join(missing[:8])
            if len(missing) > 8:
                miss_txt += "…"
            self._theme_complete_tag.setToolTip(
                f"只识别到 {installed_count} 种游标，未包含全部 15 类。\n"
                f"仍可正常应用，仅会替换已有类型。\n"
                f"缺少：{miss_txt}"
            )
            self._theme_complete_tag.setProperty("tone", "warn")
        # 刷新动态属性样式
        self._theme_complete_tag.style().unpolish(self._theme_complete_tag)
        self._theme_complete_tag.style().polish(self._theme_complete_tag)
        self._theme_complete_tag.setVisible(True)

        has_source = bool(theme.source_url)
        self._open_source_btn.setVisible(has_source)
        self._open_source_btn.setProperty("source_url", theme.source_url)
        self._delete_theme_btn.setVisible(True)
        self._delete_theme_btn.setProperty("theme_name", theme.name)

        can_apply = bool(theme.cursor_files)
        self.apply_btn.setEnabled(can_apply)

        self._clear_preview(show_placeholder=False)
        if can_apply:
            self._preview_widget = CursorGalleryWidget(theme, theme_dir)
            self.preview_layout.addWidget(self._preview_widget)
        else:
            self._clear_preview(show_placeholder=True)

        self.status_bar.showMessage(f"已选择: {theme.display_name}")

    def _open_theme_source(self) -> None:
        url = self._open_source_btn.property("source_url")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _delete_current_theme(self) -> None:
        theme_name = self._delete_theme_btn.property("theme_name")
        if not theme_name:
            return
        theme = self.theme_manager.get_theme(theme_name)
        if not theme:
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除主题「{theme.display_name}」吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if self.theme_manager.remove_theme(theme_name):
                self._current_theme = None
                self._clear_preview(show_placeholder=True)
                self._load_themes()
                self.theme_info_bar.setVisible(False)
                self.status_bar.showMessage(f"已删除: {theme.display_name}")
                QMessageBox.information(
                    self, "删除成功", f"主题「{theme.display_name}」已删除"
                )
            else:
                QMessageBox.warning(self, "删除失败", "主题删除失败")
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    def _apply_theme_files(self, theme) -> None:
        """持久化应用主题（写注册表 + 刷新）."""
        results = system_cursor_api.apply_theme(
            theme.cursor_files,
            scheme_name=f"CursorVault - {theme.display_name}",
            persistent=True,
        )
        failed = [ct.value for ct, success in results.items() if not success]
        if failed:
            raise RuntimeError(f"以下游标未能应用：{', '.join(failed)}")

    def _apply_theme(self) -> None:
        if not self._current_theme or not self._current_theme.cursor_files:
            QMessageBox.warning(self, "无法应用", "当前主题没有可应用的游标文件")
            return

        incomplete = not self._current_theme.is_complete()
        msg = (
            f"确定要应用主题「{self._current_theme.display_name}」到系统游标吗？\n"
            "将写入注册表并立即生效，重启后仍保留。\n建议先备份当前设置。"
        )
        if incomplete:
            msg += (
                f"\n\n注意：该主题不完整（{len(self._current_theme.cursor_files)}/15），"
                "仅会替换已有类型。"
            )

        reply = QMessageBox.question(
            self,
            "确认应用",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage("正在应用游标主题（持久化）...")
        self.apply_btn.setEnabled(False)
        try:
            self._apply_theme_files(self._current_theme)
            self.status_bar.showMessage(f"已应用: {self._current_theme.display_name}")
            QMessageBox.information(
                self,
                "应用成功",
                f"主题「{self._current_theme.display_name}」已应用到系统游标。\n"
                "设置已写入注册表，重启后仍然有效。",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "应用失败",
                f"应用失败：{e}\n\n"
                "提示：写入当前用户游标注册表通常不需要管理员权限。\n"
                "若仍失败，请检查游标文件是否损坏，或尝试注销后重试。",
            )
        finally:
            self.apply_btn.setEnabled(True)

    def _import_cursors(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择包含 .cur / .ani 文件的目录"
        )
        if not dir_path:
            return

        import_path = Path(dir_path)
        cur_files = find_cursor_files(import_path)
        if not cur_files:
            QMessageBox.warning(
                self, "导入失败", "所选目录中没有 .cur 或 .ani 文件"
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "主题名称",
            "请输入主题名称（将用作目录名）:",
            text=import_path.name,
        )
        if not ok or not name.strip():
            return

        try:
            slug = sanitize_theme_slug(name)
        except ValueError as exc:
            QMessageBox.warning(self, "主题名称无效", str(exc))
            return

        overwrite = False
        if self.theme_manager.theme_exists(slug):
            reply = QMessageBox.question(
                self,
                "主题已存在",
                f"主题「{slug}」已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            overwrite = True

        try:
            theme = self.theme_manager.import_cur_directory(
                slug,
                import_path,
                display_name=name.strip(),
                overwrite=overwrite,
            )
        except FileExistsError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        except ValueError as exc:
            QMessageBox.warning(self, "主题名称无效", str(exc))
            return

        if not theme:
            QMessageBox.warning(
                self,
                "导入失败",
                "无法识别目录中的游标文件。\n"
                "请确保文件名包含标准关键字（如 arrow、wait、hand）\n"
                "或使用 cur01–cur15 / Windows Aero 命名。",
            )
            return

        self._load_themes()
        # 选中新导入主题
        for i in range(self.theme_list.count()):
            item = self.theme_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == theme.name:
                self.theme_list.setCurrentRow(i)
                break

        self.status_bar.showMessage(f"已导入主题: {theme.display_name}")
        QMessageBox.information(
            self,
            "导入成功",
            f"主题「{theme.display_name}」已导入\n"
            f"包含 {len(theme.cursor_files)} 个游标文件",
        )

    def _backup_cursors(self) -> None:
        backup_dir = self.theme_manager.base_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            success = system_cursor_api.backup_current_cursors(backup_dir)
            if success:
                QMessageBox.information(
                    self,
                    "备份成功",
                    f"当前系统游标已备份到：\n{backup_dir / 'cursors_backup.reg'}",
                )
                self.status_bar.showMessage("备份成功")
            else:
                QMessageBox.warning(
                    self,
                    "备份失败",
                    "备份游标失败。请确认有权限导出当前用户注册表。",
                )
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def _restore_cursors(self) -> None:
        backup_dir = self.theme_manager.base_dir / "backup"
        reg_file = backup_dir / "cursors_backup.reg"
        if not reg_file.exists():
            QMessageBox.warning(
                self,
                "无备份",
                "未找到备份文件。请先通过「工具 → 备份当前游标」创建备份。",
            )
            return
        reply = QMessageBox.question(
            self,
            "确认恢复",
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
                QMessageBox.warning(
                    self,
                    "恢复失败",
                    "恢复失败。请确认备份文件有效，并可写入当前用户注册表。",
                )
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

    def _refresh_system_cursors(self) -> None:
        try:
            system_cursor_api.refresh_cursors()
            self.status_bar.showMessage("系统游标已从注册表刷新")
        except Exception as e:
            QMessageBox.critical(self, "刷新失败", str(e))

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            f"<h2>{__app_name__}</h2>"
            f"<p>版本 {__version__}</p>"
            f"<p>Windows 鼠标光标主题管理工具。</p>"
            f"<p>可在线浏览并下载光标素材，也可导入本地主题，"
            f"一键应用到系统，重启后仍然有效。</p>"
            f"<p>支持备份与恢复当前游标设置，方便随时切换与还原。</p>"
            f"<p>支持自动检查并安装新版本。</p>",
        )

    # ── 云更新（GitHub Releases） ─────────────────────────────

    def _check_update_silent(self) -> None:
        # 若用户已手动点过检查，则跳过静默
        if self._update_thread and self._update_thread.isRunning():
            return
        self._start_update_check(silent=True)

    def _check_update_manual(self) -> None:
        self._start_update_check(silent=False)

    def _start_update_check(self, silent: bool = False) -> None:
        if self._update_thread and self._update_thread.isRunning():
            # 手动检查时若已有任务：结束后再查一次；无更新则不打扰
            if not silent:
                self._pending_manual_update_check = True
            return

        self._pending_manual_update_check = False
        thread = CheckUpdateThread(
            self.theme_manager.base_dir, silent=silent, parent=self
        )
        self._update_thread = thread
        thread.finished_ok.connect(self._on_update_check_ok)
        thread.failed.connect(self._on_update_check_failed)
        thread.finished.connect(self._on_update_thread_finished)
        thread.start()

    def _on_update_thread_finished(self) -> None:
        thread = self.sender()
        if thread is not None:
            thread.deleteLater()
        self._update_thread = None
        if getattr(self, "_pending_manual_update_check", False):
            self._pending_manual_update_check = False
            QTimer.singleShot(100, self._check_update_manual)

    def _on_update_check_failed(self, err: str, silent: bool = False) -> None:
        # 启动静默检查失败不打扰；手动检查要弹窗
        if silent:
            return
        QMessageBox.warning(
            self,
            "检查更新",
            f"检查更新失败。\n\n{err}",
        )

    def _on_update_check_ok(self, info: object, silent: bool = False) -> None:
        release = info  # ReleaseInfo
        if release is None:
            if not silent:
                QMessageBox.information(self, "检查更新", "暂时无法获取版本信息。")
            return

        remote_ver = getattr(release, "version", "")

        # 已是最新
        if not is_newer(remote_ver, __version__):
            # 启动静默：无更新不弹窗
            if silent:
                return
            # 手动检查：弹窗提示已是最新（不提「云端版本」）
            QMessageBox.information(
                self,
                "检查更新",
                f"当前已是最新版本。\n\n当前版本：v{__version__}",
            )
            return

        # 有可更新版本：弹窗（静默/手动都会提示）
        notes = (getattr(release, "body", "") or "").strip()
        if len(notes) > 500:
            notes = notes[:500] + "…"
        detail = f"发现新版本 v{remote_ver}，是否立即更新？"
        if notes:
            detail += f"\n\n{notes}"

        reply = QMessageBox.question(
            self,
            "发现新版本",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_apply_update(release)

    def _start_apply_update(self, release: ReleaseInfo) -> None:
        if self._update_thread and self._update_thread.isRunning():
            QMessageBox.information(self, "更新", "已有更新任务正在进行。")
            return
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage(f"正在下载更新 v{release.version}…")

        thread = ApplyUpdateThread(self.theme_manager.base_dir, release, self)
        self._update_thread = thread
        thread.progress.connect(self._on_download_progress)
        thread.finished_ok.connect(self._on_update_applied)
        thread.failed.connect(self._on_update_apply_failed)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_update_applied(self, release: object) -> None:
        self.progress_bar.setVisible(False)
        ver = getattr(release, "version", "")
        self.status_bar.showMessage(f"已更新到 v{ver}，请重启程序", 10000)
        QMessageBox.information(
            self,
            "更新完成",
            f"已成功更新到 v{ver}。\n\n请关闭并重新打开本程序以使用新版本。",
        )

    def _on_update_apply_failed(self, err: str) -> None:
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("更新失败")
        QMessageBox.warning(self, "更新失败", err)

    def _download_pack(self, pack: ZhutixPack) -> None:
        # 无公开直链：仅弹窗提示，不下载、不打开官网
        if not pack.download_url and not pack.has_direct_link:
            if self._online_panel:
                self._online_panel.reset_pack_download_button(pack.slug)
            self._show_vip_required_dialog(pack)
            return

        if any(thread.isRunning() for thread in self._download_threads.values()):
            self.status_bar.showMessage("已有下载任务正在进行，请等待完成后再试")
            if self._online_panel:
                self._online_panel.reset_pack_download_button(pack.slug)
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
        thread.extract_signal.connect(lambda msg: self.status_bar.showMessage(msg))
        thread.finished_signal.connect(self._on_download_finished)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda s=pack.slug: self._download_threads.pop(s, None))
        thread.start()

    def _show_vip_required_dialog(self, pack=None) -> None:
        """VIP 素材：仅弹窗提示，不打开官网。"""
        title = getattr(pack, "title", "") if pack else ""
        self.status_bar.showMessage("需要VIP才能下载")
        if title:
            text = f"「{title}」需要VIP才能下载。\n\n软件内无法直接获取此资源。"
        else:
            text = "该素材需要VIP才能下载。\n\n软件内无法直接获取此资源。"
        QMessageBox.information(self, "需要VIP才能下载", text)

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setValue(int(downloaded * 100 / total))
        else:
            self.progress_bar.setRange(0, 0)

    def _on_download_finished(self, success: bool, message: str, pack) -> None:
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)

        if success:
            self.status_bar.showMessage(message)
            self._load_themes()
            if self._online_panel:
                self._online_panel.on_pack_installed(pack.slug)
            QMessageBox.information(self, "安装成功", message)
            return

        # VIP / 无公开直链：仅弹窗提示，不打开官网
        if isinstance(message, str) and message.startswith("NO_DIRECT_LINK::"):
            if self._online_panel:
                self._online_panel.reset_pack_download_button(pack.slug)
            self._show_vip_required_dialog(pack)
            return

        self.status_bar.showMessage(message)
        QMessageBox.warning(self, "安装失败", message)
        if self._online_panel:
            self._online_panel.reset_pack_download_button(pack.slug)

    def _apply_online_pack(self, slug: str) -> None:
        theme = self.theme_manager.get_theme(slug)
        if not theme or not theme.cursor_files:
            QMessageBox.warning(self, "无法应用", "该主题没有可用的光标文件")
            return

        self._current_theme = theme
        reply = QMessageBox.question(
            self,
            "确认应用",
            f"确定要应用主题「{theme.display_name}」到系统游标吗？\n"
            "将写入注册表并立即生效，重启后仍保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage("正在应用游标主题...")
        try:
            self._apply_theme_files(theme)
            self.status_bar.showMessage(f"已应用: {theme.display_name}")
            QMessageBox.information(
                self,
                "应用成功",
                f"主题「{theme.display_name}」已应用到系统游标\n"
                "设置已写入注册表，重启后仍然有效。",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "应用失败",
                f"应用失败：{e}\n\n"
                "提示：写入当前用户游标注册表通常不需要管理员权限。",
            )

    def closeEvent(self, event) -> None:
        # 取消在线面板请求
        if self._online_panel:
            self._online_panel.shutdown()

        # 中止下载线程
        running = [
            t for t in self._download_threads.values() if t.isRunning()
        ]
        if running:
            self.status_bar.showMessage("正在停止后台任务...")
            for t in running:
                t.request_abort()
            for t in running:
                t.wait(3000)

        self._clear_preview()
        event.accept()
