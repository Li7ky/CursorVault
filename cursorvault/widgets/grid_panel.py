# -*- coding: utf-8 -*-
"""主内容网格 v4 - Fluent 画廊网格."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl, QStandardPaths, pyqtSignal
from PyQt6.QtGui import QIntValidator, QPixmap, QResizeEvent
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme_manager import ThemeManager
from ..zhutix_client import ZhutixClient, ZhutixPack
from .cards import PackCard, SkeletonCard, ThemeCard
from .vector_icons import ICON, set_button_icon, set_label_icon
from .threads import FetchPacksThread


class _RowWidget(QWidget):
    """报告 sizeHint 宽度至少为 ``min_width`` 的行容器.

    QVBoxLayout 不会主动把 Expanding 子 widget 水平撑满，必须让子 widget 的
    sizeHint 至少与可用宽度一样。靠这个类把 viewport 宽度注入到 row 自己的
    sizeHint 里，行才会铺满 VBox 内部 stretch 才能居中卡片。
    """

    def __init__(self, min_width: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._min_w = max(0, int(min_width))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        s = super().sizeHint()
        return QSize(max(s.width(), self._min_w), s.height())

    def set_min_width(self, w: int) -> None:
        if self._min_w == w:
            return
        self._min_w = max(0, int(w))
        self.updateGeometry()


class _GridMixin:
    """行 HBox 居中布局的网格 mixin.

    把所有卡片按 ``_grid_cols`` 分行，每行装进一个带 stretch 的 QHBoxLayout，
    由 QVBoxLayout 自上而下排列。这样：
      - 满行：stretch 0，卡片自然按 gap 排列，整体居中
      - 不满的最后一行：卡片在 HBox 内部自动居中
    比 QGridLayout 的「最后一行永远靠左」友好得多。
    """

    CARD_W = 216
    CARD_GAP = 16
    SIDE_MIN = 20

    def _cols(self, usable: int) -> int:
        inner = max(self.CARD_W, usable - 2 * self.SIDE_MIN)
        cols = max(1, (inner + self.CARD_GAP) // (self.CARD_W + self.CARD_GAP))
        while cols > 1:
            need = cols * self.CARD_W + (cols - 1) * self.CARD_GAP + 2 * self.SIDE_MIN
            if need <= usable:
                break
            cols -= 1
        return cols

    def _build_row_layout(self, container: QWidget) -> QVBoxLayout:
        """构造容纳多行 HBox 的 VBox。"""
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.CARD_GAP)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        return layout

    def _populate_rows(
        self,
        vbox: QVBoxLayout,
        cards: list[QWidget],
        cols: int,
        min_width: int = 0,
    ) -> None:
        """清空并按 cols 把 cards 分行，水平居中。

        实现要点：
        - 每个 row 是一个 QWidget，水平方向 Expanding，撑满 VBox 宽度
        - row 内部用 HBoxLayout 装卡片 + 左右 stretch，让卡片组水平居中
        - **关键**：QVBoxLayout 不会因为子 widget 的 Expanding sizePolicy 就把它水平
          撑满——它只会按 sizeHint().width() 给宽度。所以我们自定义 row 的 sizeHint
          让它至少 = min_width（即 viewport 宽度），行才会铺满，内部 stretch 才有意义。

        - **不要**给 row 传 AlignHCenter，否则 Qt 会按 sizeHint 居中放置而不展开。
        """
        while vbox.count():
            item = vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not cards or cols <= 0:
            return
        for i in range(0, len(cards), cols):
            row = _RowWidget(min_width, vbox.parentWidget())
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(self.CARD_GAP)
            row_layout.addStretch(1)
            for c in cards[i:i + cols]:
                row_layout.addWidget(c)
            row_layout.addStretch(1)
            vbox.addWidget(row)


class OnlineGridPanel(QWidget, _GridMixin):
    pack_download_requested = pyqtSignal(object)
    pack_apply_requested = pyqtSignal(str)
    pack_view_requested = pyqtSignal(object)

    FILTER_ORDER = {
        "latest": ("date", "desc"),
        "hot": ("modified", "desc"),
        "all": ("id", "desc"),
    }
    FILTER_LABELS = {"latest": "最新发布", "hot": "近期更新", "all": "全部"}
    MAX_CONCURRENT_PREVIEWS = 6

    def __init__(self, theme_manager: ThemeManager, parent=None):
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._client = ZhutixClient()
        self._packs: list[ZhutixPack] = []
        self._cards: dict[str, PackCard] = {}
        self._skeletons: list[SkeletonCard] = []
        self._page = 1
        self._total_pages = 1
        self._per_page = 24
        self._filter = "latest"
        self._grid_cols = 4
        self._fetch_thread: Optional[FetchPacksThread] = None
        self._generation = 0
        self._pending_refetch = False
        self._network = QNetworkAccessManager(self)
        self._setup_cache()
        self._preview_jobs: dict[str, QNetworkReply] = {}
        self._preview_queue: list[ZhutixPack] = []
        self._active_previews = 0
        self._shutting_down = False

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._apply_search)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._sync_grid)

        self._build()
        self._fetch()

    def _setup_cache(self) -> None:
        cache = QNetworkDiskCache(self)
        d = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        if not d:
            d = str(Path.home() / ".cursorvault_cache")
        cache.setCacheDirectory(str(Path(d) / "preview_images"))
        cache.setMaximumCacheSize(64 * 1024 * 1024)
        self._network.setCache(cache)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head = QWidget()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(24, 20, 24, 12)
        hl.setSpacing(10)

        # Eyebrow + Title Row
        eyebrow = QLabel("ONLINE  ·  发现")
        eyebrow.setObjectName("pageEyebrow")
        hl.addWidget(eyebrow)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("在线素材库")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._refresh_btn = QPushButton("  刷新")
        self._refresh_btn.setObjectName("secondaryBtn")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setMinimumHeight(32)
        self._refresh_btn.setIconSize(QSize(16, 16))
        set_button_icon(self._refresh_btn, ICON.REFRESH, size=16, role="icon-refresh")
        self._refresh_btn.clicked.connect(self._fetch)
        title_row.addWidget(self._refresh_btn)
        hl.addLayout(title_row)

        self._count = QLabel("加载中…")
        self._count.setObjectName("pageSubtitle")
        hl.addWidget(self._count)

        # Filter segment
        ctrl = QHBoxLayout()
        ctrl.setSpacing(12)
        seg = QFrame()
        seg.setObjectName("filterSegment")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        from PyQt6.QtWidgets import QButtonGroup
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_btns: dict[str, QPushButton] = {}
        for i, key in enumerate(("latest", "hot", "all")):
            b = QPushButton(self.FILTER_LABELS[key])
            b.setObjectName("filterChip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(28)
            b.setProperty("filterKey", key)
            self._filter_group.addButton(b, i)
            self._filter_btns[key] = b
            sl.addWidget(b)
        self._filter_btns["latest"].setChecked(True)
        self._filter_group.idClicked.connect(self._on_filter)
        ctrl.addWidget(seg)
        ctrl.addStretch()
        hl.addLayout(ctrl)

        self._status = QLabel("正在加载…")
        self._status.setObjectName("packSubtitle")
        hl.addWidget(self._status)

        self._progress = QLabel("")
        self._progress.setObjectName("pageSubtitle")
        self._progress.setVisible(False)
        hl.addWidget(self._progress)
        layout.addWidget(head)

        # Scroll grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setObjectName("onlineScroll")
        self._host = QWidget()
        self._host.setObjectName("onlineGridHost")
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(self.SIDE_MIN, 8, self.SIDE_MIN, 12)
        self._host_layout.setSpacing(0)
        self._host_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        # 容器：内部用 VBox 装行 HBox，每行水平居中
        self._container = QWidget()
        self._container.setObjectName("onlineGridInner")
        self._rows_layout = self._build_row_layout(self._container)
        self._host_layout.addWidget(self._container, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # Empty with title+sub
        self._empty_wrap = QWidget()
        self._empty_wrap.setVisible(False)
        el = QVBoxLayout(self._empty_wrap)
        el.setContentsMargins(32, 48, 32, 48)
        el.setSpacing(8)
        el.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._empty_icon = QLabel()
        self._empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self._empty_icon)
        set_label_icon(self._empty_icon, ICON.IMAGE, size=40, role="icon-neutral")
        et = QLabel("暂无符合条件的光标包")
        et.setObjectName("emptyTitle")
        et.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(et)
        es = QLabel("换个关键词或切换筛选试试")
        es.setObjectName("emptySub")
        es.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(es)
        self._host_layout.addWidget(self._empty_wrap)

        self._host_layout.addStretch(1)
        self._scroll.setWidget(self._host)
        layout.addWidget(self._scroll, 1)

        self._page_bar = self._build_page_bar()
        layout.addWidget(self._page_bar)
        self._set_pages_enabled(False)

    def _build_page_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("pageBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(24, 10, 24, 10)
        bl.setSpacing(8)
        self._page_status = QLabel("")
        self._page_status.setObjectName("packSubtitle")
        bl.addWidget(self._page_status, 1)
        self._first_btn = QPushButton("首页")
        self._first_btn.setObjectName("toolBtn")
        self._first_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._first_btn.clicked.connect(self._first)
        bl.addWidget(self._first_btn)
        self._prev_btn = QPushButton("‹")
        self._prev_btn.setObjectName("toolBtn")
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self._prev)
        bl.addWidget(self._prev_btn)
        self._page_label = QLabel("1 / 1")
        self._page_label.setObjectName("pageLabel")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self._page_label)
        self._next_btn = QPushButton("›")
        self._next_btn.setObjectName("toolBtn")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._next)
        bl.addWidget(self._next_btn)
        self._last_btn = QPushButton("末页")
        self._last_btn.setObjectName("toolBtn")
        self._last_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._last_btn.clicked.connect(self._last)
        bl.addWidget(self._last_btn)
        bl.addSpacing(8)
        bl.addWidget(QLabel("跳至"))
        self._page_input = QLineEdit()
        self._page_input.setObjectName("pageInput")
        self._page_input.setValidator(QIntValidator(1, 9999))
        self._page_input.setFixedWidth(48)
        self._page_input.setFixedHeight(32)
        self._page_input.returnPressed.connect(self._goto_input)
        bl.addWidget(self._page_input)
        bl.addWidget(QLabel("页"))
        self._page_buttons = [self._first_btn, self._prev_btn, self._next_btn, self._last_btn]
        return bar

    def resizeEvent(self, e: QResizeEvent) -> None:
        super().resizeEvent(e)
        self._resize_timer.start()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        QTimer.singleShot(0, self._sync_grid)

    def _viewport_width(self) -> int:
        vw = self._scroll.viewport().width()
        return max(vw, 260) if vw > 0 else max(self.width() - 40, 260)

    def _sync_grid(self) -> None:
        usable = self._viewport_width()
        cols = self._cols(usable)
        if cols != self._grid_cols:
            self._grid_cols = cols
            self._relayout()
            return
        # 列数未变，但窗口宽度可能变了 → 更新每行 min_width 让卡片重新居中
        for i in range(self._rows_layout.count()):
            w = self._rows_layout.itemAt(i).widget()
            if isinstance(w, _RowWidget):
                w.set_min_width(usable)

    def _relayout(self) -> None:
        ordered = list(self._cards.values()) or list(self._skeletons)
        self._container.setUpdatesEnabled(False)
        try:
            self._populate_rows(
                self._rows_layout, ordered, self._grid_cols,
                min_width=self._viewport_width(),
            )
        finally:
            self._container.setUpdatesEnabled(True)

    def _fetch(self) -> None:
        if self._shutting_down:
            return
        if self._fetch_thread and self._fetch_thread.isRunning():
            self._pending_refetch = True
            self._generation += 1
            self._status.setText("正在切换…")
            return
        self._pending_refetch = False
        orderby, order = self.FILTER_ORDER.get(self._filter, ("date", "desc"))
        self._generation += 1
        gen = self._generation
        self._status.setText(f"正在加载第 {self._page} 页…")
        self._set_pages_enabled(False)
        self._show_skeletons()
        self._fetch_thread = FetchPacksThread(
            self._client, self._page, self._per_page, orderby=orderby, order=order
        )
        self._fetch_thread.packs_ready.connect(lambda p, g=gen: self._on_ready(p, g))
        self._fetch_thread.progress.connect(self._on_progress)
        self._fetch_thread.error.connect(lambda e, g=gen: self._on_error(e, g))
        self._fetch_thread.finished.connect(self._on_thread_done)
        self._fetch_thread.start()

    def _on_thread_done(self) -> None:
        t = self.sender()
        if t is not None:
            t.deleteLater()
        self._fetch_thread = None
        if self._pending_refetch and not self._shutting_down:
            self._pending_refetch = False
            self._fetch()

    def _on_filter(self, _id: int) -> None:
        b = self._filter_group.checkedButton()
        if b is None:
            return
        key = b.property("filterKey")
        if not key or key == self._filter:
            return
        self._filter = key
        self._page = 1
        self._fetch()

    def _show_skeletons(self) -> None:
        self._clear_cards()
        self._empty_wrap.setVisible(False)
        self._sync_grid()
        n = min(self._grid_cols * 2, 8)
        self._container.setUpdatesEnabled(False)
        for _ in range(n):
            self._skeletons.append(SkeletonCard(self._container))
        self._populate_rows(
            self._rows_layout, list(self._skeletons), self._grid_cols,
            min_width=self._viewport_width(),
        )
        self._container.setUpdatesEnabled(True)

    def _hide_skeletons(self) -> None:
        for c in self._skeletons:
            c.setParent(None)
            c.deleteLater()
        self._skeletons.clear()

    def _clear_cards(self) -> None:
        self._abort_previews()
        self._container.setUpdatesEnabled(False)
        for c in self._cards.values():
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        self._hide_skeletons()
        # 同时清空行
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._container.setUpdatesEnabled(True)

    def _on_ready(self, packs: list, gen: int) -> None:
        if self._shutting_down or gen != self._generation:
            return
        self._packs = packs
        self._hide_skeletons()
        total = self._client.total or 0
        self._count.setText(f"共 {total} 个主题  ·  {self.FILTER_LABELS.get(self._filter, '')}")
        if not packs:
            self._empty_wrap.setVisible(True)
            self._status.setText("暂无数据")
            self._page_status.setText("")
        else:
            self._empty_wrap.setVisible(False)
            self._status.setText(f"第 {self._page}/{self._total_pages or 1} 页  ·  本页 {len(packs)} 个")
            self._page_status.setText(f"每页 {self._per_page} 个")
        self._set_pages_enabled(True)
        self._page_label.setText(f"{self._page} / {self._total_pages or 1}")
        self._sync_grid()
        self._container.setUpdatesEnabled(False)
        try:
            for i, pack in enumerate(packs):
                installed = self._theme_manager.is_installed(pack.slug)
                card = PackCard(pack, installed=installed)
                card.download_clicked.connect(self._on_download)
                card.apply_clicked.connect(self._on_apply)
                self._cards[pack.slug] = card
            self._populate_rows(
                self._rows_layout, list(self._cards.values()), self._grid_cols,
                min_width=self._viewport_width(),
            )
        finally:
            self._container.setUpdatesEnabled(True)
        QTimer.singleShot(0, self._sync_grid)
        for pack in packs:
            self._enqueue_preview(pack)
        if self._search_text():
            self._apply_search()

    def _on_progress(self, _page: int, total_pages: int) -> None:
        self._total_pages = total_pages

    def _on_error(self, err: str, gen: int) -> None:
        if gen != self._generation:
            return
        self._hide_skeletons()
        self._status.setText(f"加载失败: {err}")
        self._set_pages_enabled(True)

    def _abort_previews(self) -> None:
        self._preview_queue.clear()
        for r in list(self._preview_jobs.values()):
            try:
                r.finished.disconnect()
            except TypeError:
                pass
            try:
                r.abort()
                r.deleteLater()
            except RuntimeError:
                pass
        self._preview_jobs.clear()
        self._active_previews = 0

    def _enqueue_preview(self, pack: ZhutixPack) -> None:
        url = self._client.peek_preview_url(pack) or pack.preview_url
        if not url:
            c = self._cards.get(pack.slug)
            if c:
                c.set_preview_pixmap(QPixmap())
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
            req = QNetworkRequest(QUrl(url))
            req.setAttribute(
                QNetworkRequest.Attribute.CacheLoadControlAttribute,
                QNetworkRequest.CacheLoadControl.PreferCache,
            )
            r = self._network.get(req)
            self._preview_jobs[pack.slug] = r
            self._active_previews += 1
            r.finished.connect(lambda slug=pack.slug, rep=r: self._on_preview(slug, rep))

    def _on_preview(self, slug: str, r: QNetworkReply) -> None:
        self._preview_jobs.pop(slug, None)
        self._active_previews = max(0, self._active_previews - 1)
        try:
            if r.error() == QNetworkReply.NetworkError.OperationCanceledError:
                return
            c = self._cards.get(slug)
            if not c:
                return
            if r.error() != QNetworkReply.NetworkError.NoError:
                c.set_preview_pixmap(QPixmap())
                return
            pm = QPixmap()
            if pm.loadFromData(bytes(r.readAll())):
                c.set_preview_pixmap(pm)
            else:
                c.set_preview_pixmap(QPixmap())
        finally:
            r.deleteLater()
            self._pump_previews()

    def _on_download(self, pack: ZhutixPack) -> None:
        if pack.slug in self._cards:
            self._cards[pack.slug].set_downloading()
        self.pack_download_requested.emit(pack)

    def _on_apply(self, slug: str) -> None:
        self.pack_apply_requested.emit(slug)

    def _search_text(self) -> str:
        return getattr(self, "_search_text_cache", "").strip().lower() if hasattr(self, "_search_text_cache") else ""

    def on_search(self, text: str) -> None:
        self._search_text_cache = text
        self._search_timer.start()

    def _apply_search(self) -> None:
        text = getattr(self, "_search_text_cache", "").strip().lower()
        vis = 0
        self._container.setUpdatesEnabled(False)
        try:
            for slug, card in self._cards.items():
                match = not text or text in card.pack.title.lower() or text in slug.lower()
                card.setVisible(match)
                vis += int(match)
            # 重新分行：不可见的不进 row（QHBoxLayout 不会自动跳过不可见项）
            visible = [c for c in self._cards.values() if c.isVisible()]
            self._populate_rows(
                self._rows_layout, visible, self._grid_cols,
                min_width=self._viewport_width(),
            )
        finally:
            self._container.setUpdatesEnabled(True)
        self._empty_wrap.setVisible(vis == 0 and bool(self._cards))
        if text:
            self._status.setText(f"“{text}”：{vis} 个结果")

    def _set_pages_enabled(self, en: bool) -> None:
        if not en:
            for b in self._page_buttons:
                b.setEnabled(False)
            return
        self._first_btn.setEnabled(self._page > 1)
        self._prev_btn.setEnabled(self._page > 1)
        can_next = self._total_pages > 0 and self._page < self._total_pages
        self._next_btn.setEnabled(can_next)
        self._last_btn.setEnabled(can_next)

    def _first(self) -> None:
        if self._page != 1:
            self._page = 1
            self._fetch()

    def _prev(self) -> None:
        if self._page > 1:
            self._page -= 1
            self._fetch()

    def _next(self) -> None:
        if self._page < self._total_pages:
            self._page += 1
            self._fetch()

    def _last(self) -> None:
        if self._page != self._total_pages and self._total_pages > 0:
            self._page = self._total_pages
            self._fetch()

    def _goto_input(self) -> None:
        try:
            p = int(self._page_input.text().strip())
        except ValueError:
            return
        if p < 1 or p > max(1, self._total_pages):
            return
        if p != self._page:
            self._page = p
            self._fetch()
        self._page_input.clear()

    def on_pack_installed(self, slug: str) -> None:
        c = self._cards.get(slug)
        if c:
            c.set_installed_state()

    def reset_pack_button(self, slug: str) -> None:
        c = self._cards.get(slug)
        if c:
            c.reset_download_button()

    def refresh_installed(self) -> None:
        for slug, c in self._cards.items():
            if self._theme_manager.is_installed(slug):
                c.set_installed_state()

    def shutdown(self) -> None:
        self._shutting_down = True
        self._search_timer.stop()
        self._resize_timer.stop()
        self._abort_previews()
        if self._fetch_thread and self._fetch_thread.isRunning():
            self._fetch_thread.requestInterruption()
            self._fetch_thread.wait(2000)


class LocalGridPanel(QWidget, _GridMixin):
    theme_apply_requested = pyqtSignal(str)
    theme_view_requested = pyqtSignal(str)
    theme_delete_requested = pyqtSignal(str)

    def __init__(self, theme_manager: ThemeManager, parent=None):
        super().__init__(parent)
        self._tm = theme_manager
        self._cards: dict[str, ThemeCard] = {}
        self._grid_cols = 4
        self._load_sig: tuple = ()
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._sync_grid)
        # 与在线面板一致：搜索防抖。原来每敲一个字符都要把全部卡片
        # deleteLater 再重建一遍，输入 6 个字符就是 6 次全量重建。
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._apply_search)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head = QWidget()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(24, 20, 24, 16)
        hl.setSpacing(8)
        eyebrow = QLabel("LOCAL  ·  本地")
        eyebrow.setObjectName("pageEyebrow")
        hl.addWidget(eyebrow)
        t = QLabel("本地主题")
        t.setObjectName("pageTitle")
        hl.addWidget(t)
        self._count = QLabel("0 个主题")
        self._count.setObjectName("pageSubtitle")
        hl.addWidget(self._count)
        layout.addWidget(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._host = QWidget()
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(self.SIDE_MIN, 8, self.SIDE_MIN, 12)
        self._host_layout.setSpacing(0)
        self._host_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._container = QWidget()
        self._container.setObjectName("localGridInner")
        self._rows_layout = self._build_row_layout(self._container)
        self._host_layout.addWidget(self._container, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._empty_wrap = QWidget()
        el = QVBoxLayout(self._empty_wrap)
        el.setContentsMargins(32, 48, 32, 48)
        el.setSpacing(10)
        el.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._empty_icon_local = QLabel()
        self._empty_icon_local.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self._empty_icon_local)
        set_label_icon(self._empty_icon_local, ICON.FOLDER, size=40, role="icon-folder")
        et = QLabel("还没有本地主题")
        et.setObjectName("emptyTitle")
        et.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(et)
        es = QLabel("从在线库下载，或点击右上角“导入主题”")
        es.setObjectName("emptySub")
        es.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(es)
        self._empty_wrap.setVisible(False)
        self._host_layout.addWidget(self._empty_wrap)
        self._host_layout.addStretch(1)
        self._scroll.setWidget(self._host)
        layout.addWidget(self._scroll, 1)

    def resizeEvent(self, e: QResizeEvent) -> None:
        super().resizeEvent(e)
        self._resize_timer.start()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        QTimer.singleShot(0, self._sync_grid)

    def _viewport_width(self) -> int:
        vw = self._scroll.viewport().width()
        return max(vw, 260) if vw > 0 else max(self.width() - 40, 260)

    def _sync_grid(self) -> None:
        usable = self._viewport_width()
        cols = self._cols(usable)
        if cols != self._grid_cols:
            self._grid_cols = cols
            self._relayout()
            return
        for i in range(self._rows_layout.count()):
            w = self._rows_layout.itemAt(i).widget()
            if isinstance(w, _RowWidget):
                w.set_min_width(usable)

    def _relayout(self) -> None:
        ordered = list(self._cards.values())
        self._container.setUpdatesEnabled(False)
        try:
            self._populate_rows(
                self._rows_layout, ordered, self._grid_cols,
                min_width=self._viewport_width(),
            )
        finally:
            self._container.setUpdatesEnabled(True)

    def _themes_signature(self, themes) -> tuple:
        """主题集合指纹：用于跳过无变化时的全量重建.

        ``load_themes`` 会被下载完成、预览图回填、导入等多处调用，每次都把全部
        ThemeCard 销毁重建一次。指纹里包含 preview.png 是否存在，所以预览图回填
        完成后指纹会变，仍然会重建。
        """
        sig = []
        for t in themes:
            d = self._tm.get_theme_dir(t.name)
            has_preview = bool(d and (d / "preview.png").exists())
            sig.append((t.name, t.display_name, len(t.cursor_files or {}), has_preview))
        return tuple(sig)

    def load_themes(self, themes, force: bool = False) -> None:
        themes = list(themes)
        sig = self._themes_signature(themes)
        if not force and sig == self._load_sig:
            return
        self._load_sig = sig

        for c in self._cards.values():
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        self._sync_grid()
        self._container.setUpdatesEnabled(False)
        try:
            for theme in themes:
                pm = self._theme_preview(theme)
                card = ThemeCard(theme, preview_pixmap=pm)
                card.apply_clicked.connect(self.theme_apply_requested.emit)
                card.view_clicked.connect(self.theme_view_requested.emit)
                self._cards[theme.name] = card
            self._populate_rows(
                self._rows_layout, list(self._cards.values()), self._grid_cols,
                min_width=self._viewport_width(),
            )
        finally:
            self._container.setUpdatesEnabled(True)
        self._count.setText(f"{len(themes)} 个主题")
        self._empty_wrap.setVisible(len(themes) == 0)
        QTimer.singleShot(0, self._sync_grid)
        # 重建后要重新套用当前搜索词，否则关键词会被静默丢掉
        if self._search_timer.isActive() or getattr(self, "_search_text_cache", ""):
            self._apply_search()

    def _theme_preview(self, theme) -> QPixmap:
        """读取主题封面，并按卡片尺寸降采样后再交给卡片.

        直接把原图（常见 1000×600 以上）塞给 ThemeCard，每个卡片还要各自
        copy + 缩放一次；这里统一缩到封面尺寸，内存和 CPU 都省一大截。
        """
        d = self._tm.get_theme_dir(theme.name)
        if not d:
            return QPixmap()
        p = d / "preview.png"
        if not p.exists():
            return QPixmap()
        pm = QPixmap(str(p))
        if pm.isNull():
            return QPixmap()
        # 2 倍封面尺寸足够高清，再大只是浪费
        max_w = self.CARD_W * 2
        if pm.width() > max_w:
            pm = pm.scaledToWidth(
                max_w, Qt.TransformationMode.SmoothTransformation
            )
        return pm

    def on_search(self, text: str) -> None:
        self._search_text_cache = text
        self._search_timer.start()

    def _apply_search(self) -> None:
        t = getattr(self, "_search_text_cache", "").strip().lower()
        self._container.setUpdatesEnabled(False)
        try:
            for name, card in self._cards.items():
                match = not t or t in card.theme.display_name.lower() or t in name.lower()
                card.setVisible(match)
            # 重新分行：不可见的不进 row（QHBoxLayout 不会自动跳过不可见项）
            visible = [c for c in self._cards.values() if c.isVisible()]
            self._populate_rows(
                self._rows_layout, visible, self._grid_cols,
                min_width=self._viewport_width(),
            )
        finally:
            self._container.setUpdatesEnabled(True)
        self._empty_wrap.setVisible(len(visible) == 0 and bool(self._cards))
