# -*- coding: utf-8 -*-
"""CursorVault 主窗口 v4 - Fluent Atlas 全新布局.

布局：
  ┌──────────────────────────────────────────────┐
  │ 侧边栏 260 │  顶栏 56 + Banner + 内容 Stack + 底栏 48 │
  │            │  抽屉 380 叠层在主列右侧（overlay）    │
  └──────────────────────────────────────────────┘
逻辑层保持不变，仅重做视觉与交互编排。
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, __app_name__
from .theme_manager import ThemeManager, sanitize_theme_slug
from .downloader import find_cursor_files
from .system_cursor import system_cursor_api
from .zhutix_client import ZhutixClient, ZhutixPack
from .updater import GitHubUpdater, ReleaseInfo, is_newer
from .ui_theme import build_stylesheet

from .widgets.sidebar import Sidebar
from .widgets.topbar import TopBar
from .widgets.grid_panel import OnlineGridPanel, LocalGridPanel
from .widgets.drawer import DetailDrawer
from .widgets.bottombar import BottomBar
from .widgets.dialogs import UpdateDialog, NotificationBanner, SoftDialog
from .widgets.queue_panel import DownloadQueuePanel
from .widgets.threads import (
    DownloadPackThread,
    CheckUpdateThread,
    ApplyUpdateThread,
)
from .preview_backfill import PreviewBackfiller
from .cursor_preview import clear_cursor_pixmap_cache, warmup_cursor_renderer
from .widgets.vector_icons import ICON, retheme_icons


class _ClickShield(QWidget):
    """点击即关闭抽屉的遮罩（用真正的事件覆盖，避免 PyQt 实例属性失效）."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 自定义 QWidget 子类必须开启，否则样式表半透明背景不绘制，遮罩不可见
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, theme_manager: ThemeManager):
        super().__init__()
        self.theme_manager = theme_manager
        self._current_theme = None
        self._current_theme_dir: Optional[Path] = None
        self._ui_theme: str = "light"
        self._download_threads: dict[str, DownloadPackThread] = {}
        # 下载队列元数据：slug -> {title, phase, done, total}（驱动侧边栏 tab 页）
        self._download_meta: dict[str, dict] = {}
        self._pill_slug: Optional[str] = None     # 全局进度条当前跟随的任务
        self._concurrency_notified = False        # 本次并发潮是否已提示过
        self._update_thread = None
        self._preview_backfiller: Optional[PreviewBackfiller] = None
        self._pending_manual_update_check = False

        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setMinimumSize(1080, 680)
        self.resize(1280, 800)
        self._apply_style()
        self._apply_window_icon()

        self._build_ui()
        self._topbar.set_dark(self._ui_theme == "dark")
        self._apply_titlebar_theme()
        self._setup_menu_bar()
        self._reload_themes()
        self._sync_topbar_title("online")
        QTimer.singleShot(2500, self._check_update_silent)
        # GDI 首次渲染要 ~30ms，趁启动空闲预热掉，别砸在用户第一次开抽屉那一帧
        QTimer.singleShot(300, warmup_cursor_renderer)

    # ─────────────────────── 样式与图标 ───────────────────────
    def _apply_style(self) -> None:
        from .ui_theme import set_current_theme

        set_current_theme(self._ui_theme)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet(self._ui_theme))

    def _apply_window_icon(self) -> None:
        base = self.theme_manager.base_dir
        roots = [Path(base), Path(__file__).resolve().parent.parent]
        for root in roots:
            for name in ("assets/app_icon.ico", "assets/app_icon.png"):
                p = root / name
                if p.exists():
                    icon = QIcon(str(p))
                    if not icon.isNull():
                        self.setWindowIcon(icon)
                        return

    # ─────────────────────── UI 组装 ───────────────────────
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        self._central = central

        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # 侧边栏 260
        self._sidebar = Sidebar()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.nav_changed.connect(self._on_nav)
        self._sidebar.theme_activated.connect(self._on_sidebar_theme)
        self._sidebar.backup_requested.connect(self._backup_cursors)
        self._sidebar.restore_requested.connect(self._restore_cursors)
        self._sidebar.refresh_cursors_requested.connect(self._refresh_system_cursors)
        h.addWidget(self._sidebar)

        # 主列
        self._main_col = QWidget()
        self._main_col.setObjectName("mainColumn")
        v = QVBoxLayout(self._main_col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 顶栏
        self._topbar = TopBar()
        self._topbar.setObjectName("topBar")
        self._topbar.search_changed.connect(self._on_search)
        self._topbar.theme_toggle_requested.connect(self._toggle_theme)
        self._topbar.update_check_requested.connect(lambda: self._check_update_manual())
        self._topbar.import_requested.connect(self._import_cursors)
        v.addWidget(self._topbar)

        # 通知横幅（置于顶栏下方，随主列宽度自适应）
        self._banner = NotificationBanner(parent=self._main_col)
        self._banner.setObjectName("notificationBanner")
        self._banner.setVisible(False)
        self._banner.action_clicked.connect(self._on_banner_action)
        self._banner.closed.connect(self._on_banner_closed)
        v.addWidget(self._banner)

        # 内容栈
        self._stack = QStackedWidget()
        self._stack.setObjectName("contentStack")
        self._online = OnlineGridPanel(self.theme_manager)
        self._online.pack_download_requested.connect(self._download_pack)
        self._online.pack_apply_requested.connect(self._apply_online_pack)
        self._local = LocalGridPanel(self.theme_manager)
        self._local.theme_apply_requested.connect(self._apply_by_name)
        self._local.theme_view_requested.connect(self._open_drawer)
        self._queue_page = DownloadQueuePanel()
        self._stack.addWidget(self._online)
        self._stack.addWidget(self._local)
        self._stack.addWidget(self._queue_page)
        self._stack.setCurrentWidget(self._online)
        v.addWidget(self._stack, 1)

        # 底栏
        self._bottombar = BottomBar()
        self._bottombar.setObjectName("bottomBar")
        self._bottombar.apply_requested.connect(self._apply_current)
        v.addWidget(self._bottombar)

        h.addWidget(self._main_col, 1)

        # ── 抽屉叠层（不占布局，悬浮在 central 右侧）──
        self._drawer = DetailDrawer(parent=central)
        self._drawer.setObjectName("detailDrawer")
        self._drawer.apply_requested.connect(self._apply_by_name)
        self._drawer.delete_requested.connect(self._delete_by_name)
        self._drawer.closed.connect(self._on_drawer_closed)
        self._drawer.hide()

        # 半透明遮罩（点击关闭抽屉）
        self._drawer_dim = _ClickShield(central)
        self._drawer_dim.setObjectName("drawerDim")
        self._drawer_dim.setStyleSheet("background: rgba(15,23,42,0.22); border: none;")
        self._drawer_dim.hide()
        self._drawer_dim.clicked.connect(self._close_drawer)

        # 确保抽屉在最上层
        self._drawer.raise_()

        # 初次布局后定位
        QTimer.singleShot(0, self._position_drawer)

    def _position_drawer(self) -> None:
        if not hasattr(self, "_drawer") or not hasattr(self, "_central"):
            return
        cw = self._central.width()
        ch = self._central.height()
        dw = self._drawer.width()
        # 抽屉高度与 central 同高
        if self._drawer.isVisible():
            self._drawer.setGeometry(cw - dw, 0, dw, ch)
            self._drawer_dim.setGeometry(0, 0, cw - dw, ch)
            self._drawer_dim.show()
            self._drawer_dim.raise_()
            self._drawer.raise_()
        else:
            self._drawer_dim.hide()

    def _close_drawer(self) -> None:
        self._drawer.hide()
        self._drawer_dim.hide()
        self._on_drawer_closed()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_drawer()

    def _setup_menu_bar(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("文件(&F)")
        a = QAction("导入游标目录…", self); a.triggered.connect(self._import_cursors)
        file_menu.addAction(a)
        file_menu.addSeparator()
        a = QAction("退出(&X)", self); a.setShortcut("Ctrl+Q"); a.triggered.connect(self.close)
        file_menu.addAction(a)

        tool_menu = mb.addMenu("工具(&T)")
        a = QAction("备份当前游标", self); a.triggered.connect(self._backup_cursors)
        tool_menu.addAction(a)
        a = QAction("恢复游标", self); a.triggered.connect(self._restore_cursors)
        tool_menu.addAction(a)
        tool_menu.addSeparator()
        a = QAction("刷新系统游标", self); a.triggered.connect(self._refresh_system_cursors)
        tool_menu.addAction(a)

        help_menu = mb.addMenu("帮助(&H)")
        a = QAction("检查更新…", self); a.triggered.connect(self._check_update_manual)
        help_menu.addAction(a)
        help_menu.addSeparator()
        a = QAction(f"关于 {__app_name__}", self); a.triggered.connect(self._show_about)
        help_menu.addAction(a)

    # ─────────────────────── 导航 / 搜索 / 主题 ───────────────────────
    def _sync_topbar_title(self, key: str) -> None:
        if key == "online":
            self._topbar.set_page_info("在线素材库", "浏览并下载 Windows 光标主题")
        elif key == "queue":
            self._topbar.set_page_info("下载队列", "实时查看正在下载的素材与进度")
        else:
            cnt = len(self.theme_manager.themes) if hasattr(self.theme_manager, "themes") else 0
            self._topbar.set_page_info("本地主题", f"已安装 {cnt} 个主题  ·  点击卡片查看详情")

    def _on_nav(self, key: str) -> None:
        if key == "online":
            self._stack.setCurrentWidget(self._online)
        elif key == "queue":
            self._stack.setCurrentWidget(self._queue_page)
        else:
            self._stack.setCurrentWidget(self._local)
        self._sync_topbar_title(key)
        # 切换页面时若抽屉开着，保持但更新遮罩位置
        self._position_drawer()

    def _on_search(self, text: str) -> None:
        if self._stack.currentWidget() is self._online:
            self._online.on_search(text)
        elif self._stack.currentWidget() is self._local:
            self._local.on_search(text)
        # 下载队列页不响应搜索

    def _toggle_theme(self) -> None:
        self._ui_theme = "light" if self._ui_theme == "dark" else "dark"
        self._apply_style()
        self._topbar.set_dark(self._ui_theme == "dark")
        # 主题切换后，所有已注册的矢量图标按新色令牌重绘
        retheme_icons()
        self._apply_titlebar_theme()
        # 同步遮罩颜色（暗色下稍深）
        if self._ui_theme == "dark":
            self._drawer_dim.setStyleSheet("background: rgba(0,0,0,0.42); border: none;")
        else:
            self._drawer_dim.setStyleSheet("background: rgba(15,23,42,0.22); border: none;")

    def _on_sidebar_theme(self, name: str) -> None:
        self._sidebar.select_view("local")
        self._open_drawer(name)

    # ─────────────────────── 主题列表加载 ───────────────────────
    def _reload_themes(self) -> None:
        self.theme_manager.reload()
        themes = self.theme_manager.themes
        self._sidebar.refresh_themes(themes)
        self._local.load_themes(themes)
        self._online.refresh_installed()
        self._sync_topbar_title(self._sidebar._active_nav if hasattr(self._sidebar, "_active_nav") else "online")
        self._maybe_backfill_previews()

    # ─────────────── 缺失预览图后台回填 ───────────────
    def _maybe_backfill_previews(self) -> None:
        """为已安装但缺 preview.png 的在线来源主题补预览图（Qt 异步，无线程）."""
        if self._preview_backfiller is None:
            self._preview_backfiller = PreviewBackfiller(self)
            self._preview_backfiller.preview_ready.connect(self._on_preview_backfilled)
        jobs = []
        for theme in self.theme_manager.themes:
            if not theme.source_url:
                continue
            d = self.theme_manager.get_theme_dir(theme.name)
            if not d or (d / "preview.png").exists():
                continue
            jobs.append((theme.name, d, theme.source_url))
        if jobs:
            self._preview_backfiller.submit(jobs)

    def _on_preview_backfilled(self, _name: str) -> None:
        # 合并多次刷新，避免逐张重建卡片闪烁
        if not hasattr(self, "_preview_refresh_timer"):
            self._preview_refresh_timer = QTimer(self)
            self._preview_refresh_timer.setSingleShot(True)
            self._preview_refresh_timer.setInterval(400)
            self._preview_refresh_timer.timeout.connect(self._refresh_local_cards)
        self._preview_refresh_timer.start()

    def _refresh_local_cards(self) -> None:
        try:
            self._local.load_themes(self.theme_manager.themes)
        except Exception:
            pass

    # ─────────────────────── 详情抽屉 ───────────────────────
    def _open_drawer(self, theme_name: str) -> None:
        theme = self.theme_manager.get_theme(theme_name)
        if not theme:
            return
        self._current_theme = theme
        self._current_theme_dir = self.theme_manager.get_theme_dir(theme_name)
        self._drawer.show_theme(theme, self._current_theme_dir, self.theme_manager)
        self._bottombar.set_now_playing(theme, self._current_theme_dir)
        self._sidebar.select_view("local")
        self._stack.setCurrentWidget(self._local)
        self._sync_topbar_title("local")
        self._position_drawer()

    def _on_drawer_closed(self) -> None:
        self._drawer_dim.hide()
        self._position_drawer()

    # ─────────────────────── 应用主题 ───────────────────────
    def _apply_current(self) -> None:
        if self._current_theme:
            self._apply_by_name(self._current_theme.name)

    def _apply_by_name(self, name: str) -> None:
        theme = self.theme_manager.get_theme(name)
        if not theme or not theme.cursor_files:
            QMessageBox.warning(self, "无法应用", "该主题没有可用的光标文件")
            return
        self._current_theme = theme
        self._current_theme_dir = self.theme_manager.get_theme_dir(name)
        incomplete = not theme.is_complete()
        msg = f"确定要应用主题「{theme.display_name}」到系统游标吗？\n将写入注册表并立即生效，重启后仍保留。"
        if incomplete:
            msg += f"\n\n注意：该主题不完整（{len(theme.cursor_files)}/15），仅会替换已有类型。"
        if QMessageBox.question(self, "确认应用", msg) != QMessageBox.StandardButton.Yes:
            return
        self._bottombar.set_status("正在应用游标主题（持久化）…")
        try:
            self._apply_theme_files(theme)
            self._bottombar.set_status(f"已应用: {theme.display_name}")
            self._bottombar.set_now_playing(theme, self._current_theme_dir)
            QMessageBox.information(self, "应用成功",
                f"主题「{theme.display_name}」已应用到系统游标。\n设置已写入注册表，重启后仍然有效。")
        except Exception as e:
            QMessageBox.critical(self, "应用失败", f"应用失败：{e}")

    def _apply_theme_files(self, theme) -> None:
        results = system_cursor_api.apply_theme(
            theme.cursor_files,
            scheme_name=f"CursorVault - {theme.display_name}",
            persistent=True,
        )
        failed = [ct.value for ct, ok in results.items() if not ok]
        if failed:
            raise RuntimeError(f"以下游标未能应用：{', '.join(failed)}")

    def _apply_online_pack(self, slug: str) -> None:
        self._apply_by_name(slug)

    # ─────────────────────── 删除 / 来源 ───────────────────────
    def _delete_by_name(self, name: str) -> None:
        theme = self.theme_manager.get_theme(name)
        if not theme:
            return
        if QMessageBox.question(self, "确认删除",
                f"确定要删除主题「{theme.display_name}」吗？此操作不可恢复。"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.theme_manager.remove_theme(name):
                self._current_theme = None
                self._close_drawer()
                self._bottombar.set_now_playing(None)
                # 主题目录已删，缓存里的位图必须一起失效，否则重新导入同名主题会显示旧图
                clear_cursor_pixmap_cache()
                self._reload_themes()
                self._bottombar.set_status(f"已删除: {theme.display_name}")
                QMessageBox.information(self, "删除成功", f"主题「{theme.display_name}」已删除")
            else:
                QMessageBox.warning(self, "删除失败", "主题删除失败")
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))

    # ─────────────────────── 导入 ───────────────────────
    def _import_cursors(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "选择包含 .cur / .ani 文件的目录")
        if not dir_path:
            return
        import_path = Path(dir_path)
        if not find_cursor_files(import_path):
            QMessageBox.warning(self, "导入失败", "所选目录中没有 .cur 或 .ani 文件")
            return
        name, ok = QInputDialog.getText(self, "主题名称", "请输入主题名称（将用作目录名）:", text=import_path.name)
        if not ok or not name.strip():
            return
        try:
            slug = sanitize_theme_slug(name)
        except ValueError as exc:
            QMessageBox.warning(self, "主题名称无效", str(exc))
            return
        overwrite = False
        if self.theme_manager.theme_exists(slug):
            if QMessageBox.question(self, "主题已存在", f"主题「{slug}」已存在，是否覆盖？") == QMessageBox.StandardButton.Yes:
                overwrite = True
            else:
                return
        try:
            theme = self.theme_manager.import_cur_directory(slug, import_path, display_name=name.strip(), overwrite=overwrite)
        except (FileExistsError, ValueError) as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        if not theme:
            QMessageBox.warning(self, "导入失败", "无法识别目录中的游标文件命名。")
            return
        self._reload_themes()
        self._open_drawer(theme.name)
        self._bottombar.set_status(f"已导入主题: {theme.display_name}")

    # ─────────────────────── 备份 / 恢复 / 刷新 ───────────────────────
    def _backup_cursors(self) -> None:
        backup_dir = self.theme_manager.base_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            if system_cursor_api.backup_current_cursors(backup_dir):
                QMessageBox.information(self, "备份成功", f"当前系统游标已备份到：\n{backup_dir / 'cursors_backup.reg'}")
                self._bottombar.set_status("备份成功")
            else:
                QMessageBox.warning(self, "备份失败", "备份游标失败，请确认有权限导出当前用户注册表。")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def _restore_cursors(self) -> None:
        reg_file = self.theme_manager.base_dir / "backup" / "cursors_backup.reg"
        if not reg_file.exists():
            QMessageBox.warning(self, "无备份", "未找到备份文件。请先备份当前游标。")
            return
        if QMessageBox.question(self, "确认恢复", f"确定要从备份恢复系统游标吗？") != QMessageBox.StandardButton.Yes:
            return
        try:
            if system_cursor_api.restore_from_backup(self.theme_manager.base_dir / "backup"):
                QMessageBox.information(self, "恢复成功", "系统游标已恢复")
                self._bottombar.set_status("游标已恢复")
            else:
                QMessageBox.warning(self, "恢复失败", "恢复失败，请确认备份文件有效。")
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

    def _refresh_system_cursors(self) -> None:
        try:
            system_cursor_api.refresh_cursors()
            self._bottombar.set_status("系统游标已从注册表刷新")
        except Exception as e:
            QMessageBox.critical(self, "刷新失败", str(e))

    # ─────────────────────── 下载 ───────────────────────
    def _download_pack(self, pack: ZhutixPack) -> None:
        # 注意：不再对「无现成直链」的包做前置 VIP 拦截。
        # 一律进后台线程：先走 5 级直链解析（详情页/文章页/b2 接口），
        # 期间状态栏 + 忙碌进度条持续有反馈；确实拿不到才弹 VIP 对话框（带具体原因）。
        # 支持多任务并发下载：侧边栏「下载队列」tab 实时展示，凑够 2 个时横幅提示。
        if pack.slug in self._download_threads:
            self._bottombar.set_status("该素材已在下载队列中，去「下载队列」页看看进度吧")
            self._online.reset_pack_button(pack.slug)
            return
        active = len(self._download_threads)
        self._download_meta[pack.slug] = {
            "title": pack.title,
            "phase": "正在排队…",
            "done": 0,
            "total": 0,
        }
        self._pill_slug = pack.slug
        self._bottombar.show_progress(True)
        # 0,0 = 不定态忙碌进度条：解析直链阶段没有字节数可报，但要让用户看到在动
        self._bottombar.set_progress(0, 0)
        self._refresh_download_ui()
        thread = DownloadPackThread(ZhutixClient(), pack, self.theme_manager.download_dir, self.theme_manager)
        self._download_threads[pack.slug] = thread
        thread.progress.connect(lambda d, t, s=pack.slug: self._on_pack_progress(s, d, t))
        thread.extract_signal.connect(lambda msg, s=pack.slug: self._on_pack_phase(s, msg))
        thread.finished_signal.connect(self._on_download_finished)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda s=pack.slug: self._download_threads.pop(s, None))
        thread.start()
        # 首次并发（1 → 2）时横幅提示一次；全部结束后重置标志
        if active == 1 and not self._concurrency_notified:
            self._concurrency_notified = True
            self._banner.set_message("有多个素材正在同时下载，可到侧边栏「下载队列」查看各自进度")
            self._banner.set_action_text("")
            self._banner.show()

    def _on_pack_progress(self, slug: str, done: int, total: int) -> None:
        meta = self._download_meta.get(slug)
        if meta:
            meta["done"], meta["total"] = done, total
        self._refresh_download_ui()

    def _on_pack_phase(self, slug: str, phase: str) -> None:
        meta = self._download_meta.get(slug)
        if meta:
            meta["phase"] = phase
        self._refresh_download_ui()

    def _refresh_download_ui(self) -> None:
        """按 _download_meta 统一刷新：侧边栏徽标 / 队列页 / 全局进度条 / 状态栏."""
        metas = self._download_meta
        n = len(metas)
        # 侧边栏「下载队列」tab 徽标（0 隐藏）
        self._sidebar.set_queue_count(n)
        # 队列页实时刷新（常驻 stack，切换即可查看）
        self._queue_page.set_items([dict(m, slug=s) for s, m in metas.items()])
        # 全局进度条跟随 _pill_slug（任务结束后顺延到下一个）
        if self._pill_slug not in metas:
            self._pill_slug = next(reversed(metas)) if metas else None
        if self._pill_slug:
            m = metas[self._pill_slug]
            self._bottombar.show_progress(True)
            self._bottombar.set_progress(m["done"], m["total"])
        else:
            self._bottombar.show_progress(False)
        # 状态栏：单任务显示其阶段文字，多任务显示汇总
        if n == 1:
            only = next(iter(metas.values()))
            self._bottombar.set_status(f"{only['title']}：{only['phase']}" if only["phase"] == "正在排队…" else only["phase"])
        elif n > 1:
            self._bottombar.set_status(f"正在下载 {n} 个素材，点侧边栏「下载队列」查看…")

    def _show_vip_dialog(self, pack=None, detail: str = "") -> None:
        title = getattr(pack, "title", "") if pack else ""
        if not title:
            title = "该素材"
        is_vip = "VIP" in detail or "vip" in detail
        is_network = any(
            k in detail for k in ("网络", "失败", "超时", "抓取", "空或过小")
        )
        if is_vip:
            head = "这颗宝藏在 VIP 货架上"
            body = (
                f"「{title}」被站方请进了 VIP 专属货架——需持卡入场。\n\n"
                "免费区同样精彩，或手动下载后用「导入主题」把它接回家。"
            )
            icon_name, icon_role = ICON.LOCK, "warning"
            status = "该素材需要 VIP"
        elif is_network:
            head = "网络开了个小差"
            body = (
                f"「{title}」在取件路上被网络绊了一脚。\n\n"
                f"{detail}\n\n"
                "稍等片刻，再点一次下载多半就好了。"
            )
            icon_name, icon_role = ICON.REFRESH, "icon-refresh"
            status = "网络开了个小差，稍后再试"
        else:
            head = "暂时无法直接下载"
            body = (
                f"「{title}」这颗宝藏暂时取不出来。\n\n"
                f"{detail}\n\n"
                "可手动下载后用「导入主题」把它接回家。"
            )
            icon_name, icon_role = ICON.LOCK, "warning"
            status = "该素材暂时无法直接下载"
        self._bottombar.set_status(status)
        SoftDialog(head, body, parent=self, icon_name=icon_name,
                   icon_role=icon_role).exec()

    def _on_download_finished(self, success: bool, message: str, pack) -> None:
        self._download_meta.pop(pack.slug, None)
        if not self._download_meta:
            self._concurrency_notified = False   # 下一波并发再提示一次
        self._refresh_download_ui()
        if success:
            self._bottombar.set_status(message)
            self._reload_themes()
            self._online.on_pack_installed(pack.slug)
            pack_title = getattr(pack, "title", "") or "新素材"
            SoftDialog(
                "新宝贝到手！",
                (
                    f"「{pack_title}」已顺利入住本地主题库。\n\n"
                    f"{message}\n\n"
                    "去「本地主题」一键换上，指针马上焕新！"
                ),
                parent=self,
                icon_name=ICON.CHECK,
                icon_role="icon-check",
                icon_tone="success",
            ).exec()
            return
        if isinstance(message, str) and message.startswith("NO_DIRECT_LINK::"):
            detail = message[len("NO_DIRECT_LINK::"):]
            self._online.reset_pack_button(pack.slug)
            self._show_vip_dialog(pack, detail=detail)
            return
        self._bottombar.set_status(message)
        QMessageBox.warning(self, "安装失败", message)
        self._online.reset_pack_button(pack.slug)

    # ─────────────────────── 更新 ───────────────────────
    def _check_update_silent(self) -> None:
        if self._update_thread and self._update_thread.isRunning():
            return
        self._start_update_check(silent=True)

    def _check_update_manual(self) -> None:
        self._start_update_check(silent=False)

    def _start_update_check(self, silent: bool = False) -> None:
        if self._update_thread and self._update_thread.isRunning():
            if not silent:
                self._pending_manual_update_check = True
            return
        self._pending_manual_update_check = False
        thread = CheckUpdateThread(self.theme_manager.base_dir, silent=silent, parent=self)
        self._update_thread = thread
        thread.finished_ok.connect(self._on_update_ok)
        thread.failed.connect(self._on_update_failed)
        thread.finished.connect(self._on_update_thread_done)
        thread.start()

    def _on_update_thread_done(self) -> None:
        t = self.sender()
        if t is not None:
            t.deleteLater()
        self._update_thread = None
        if getattr(self, "_pending_manual_update_check", False):
            self._pending_manual_update_check = False
            QTimer.singleShot(100, self._check_update_manual)

    def _on_update_failed(self, err: str, silent: bool = False) -> None:
        if silent:
            return
        QMessageBox.warning(self, "检查更新", f"检查更新失败。\n\n{err}")

    def _on_update_ok(self, info: object, silent: bool = False) -> None:
        release = info
        if release is None:
            if not silent:
                QMessageBox.information(self, "检查更新", "暂时无法获取版本信息。")
            return
        remote = getattr(release, "version", "")
        if not is_newer(remote, __version__):
            if not silent:
                QMessageBox.information(self, "检查更新", f"当前已是最新版本。\n\n当前版本：v{__version__}")
            return
        self._pending_update_release = release
        self._banner.set_message(f"发现新版本 v{remote}，建议更新以获得更好的体验")
        self._banner.set_action_text("立即更新")
        self._banner.show()

    def _on_banner_action(self) -> None:
        self._banner.hide()
        rel = getattr(self, "_pending_update_release", None)
        if rel:
            self._pending_update_release = None
            self._start_apply_update(rel)

    def _on_banner_closed(self) -> None:
        self._pending_update_release = None

    def _start_apply_update(self, release: ReleaseInfo) -> None:
        if self._update_thread and self._update_thread.isRunning():
            QMessageBox.information(self, "更新", "已有更新任务正在进行。")
            return
        self._bottombar.show_progress(True)
        self._bottombar.set_progress(0, 100)
        self._bottombar.set_status(f"正在下载更新 v{release.version}…")
        thread = ApplyUpdateThread(self.theme_manager.base_dir, release, self)
        self._update_thread = thread
        thread.progress.connect(lambda d, t: self._bottombar.set_progress(d, t))
        thread.finished_ok.connect(self._on_update_applied)
        thread.failed.connect(self._on_update_apply_failed)
        thread.finished.connect(self._on_update_thread_done)
        thread.start()

    def _on_update_applied(self, release: object) -> None:
        self._bottombar.show_progress(False)
        ver = getattr(release, "version", "")
        self._bottombar.set_status(f"已更新到 v{ver}，请重启程序")
        QMessageBox.information(self, "更新完成", f"已成功更新到 v{ver}。\n\n请关闭并重新打开本程序以使用新版本。")

    def _on_update_apply_failed(self, err: str) -> None:
        self._bottombar.show_progress(False)
        self._bottombar.set_status("更新失败")
        QMessageBox.warning(self, "更新失败", err)

    # ─────────────────────── 关于 ───────────────────────
    def _show_about(self) -> None:
        QMessageBox.about(self, "关于",
            f"<h2>{__app_name__}</h2>"
            f"<p>版本 <b>{__version__}</b> &nbsp;·&nbsp; <span style='color:#2563eb'>v1.x → v2.x 重大升级</span></p>"
            f"<p>Windows 鼠标光标主题管理工具。</p>"
            f"<p>在线浏览下载光标素材，导入本地主题，一键应用到系统，重启后仍然有效。</p>"
            f"<p>支持备份恢复、自动更新。</p>")

    # ─────────────────────── 窗口标题栏明暗 ───────────────────────
    def _apply_titlebar_theme(self) -> None:
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            dark = 1 if self._ui_theme == "dark" else 0
            val = ctypes.c_int(dark)
            d = ctypes.windll.dwmapi
            for attr in (20, 19):
                if d.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)
                ) == 0:
                    break
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_titlebar_theme()
        QTimer.singleShot(0, self._position_drawer)

    def closeEvent(self, event) -> None:
        if self._online:
            try:
                self._online.shutdown()
            except Exception:
                pass
        running = [t for t in self._download_threads.values() if t.isRunning()]
        if self._update_thread and self._update_thread.isRunning():
            running.append(self._update_thread)
        if self._preview_backfiller is not None:
            # 纯 Qt 异步：abort 立即断开请求，无线程需要等待
            self._preview_backfiller.abort()
        if running:
            self._bottombar.set_status("正在停止后台任务…")
            for t in running:
                try:
                    t.request_abort()
                except AttributeError:
                    t.requestInterruption()
            for t in running:
                t.wait(3000)
        event.accept()
