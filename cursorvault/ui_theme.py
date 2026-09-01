# -*- coding: utf-8 -*-
"""CursorVault 全局视觉主题（专业桌面软件风格）。"""

APP_STYLESHEET = """
/* ── Design tokens ──
   bg: #f8fafc  surface: #ffffff  primary: #6366f1
   text: #0f172a  muted: #64748b  border: #e2e8f0
*/
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    outline: none;
}

QMainWindow {
    background: #f4f6f9;
    color: #172033;
}
QWidget {
    color: #172033;
}
QToolTip {
    background: #172033;
    color: #ffffff;
    border: 1px solid #2f3b52;
    padding: 6px 8px;
}

QWidget#centralWidget {
    background: #f4f6f9;
}

/* ── 顶部区域 ── */
QWidget#topArea {
    background: #ffffff;
    border-bottom: 1px solid #dfe4ec;
}
QLabel#appTitle {
    font-size: 16px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#versionLabel {
    font-size: 11px;
    color: #94a3b8;
    background: #f1f5f9;
    border-radius: 4px;
    padding: 2px 6px;
}
QPushButton#toolbarBtn {
    background: #6366f1;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: 500;
}
QPushButton#toolbarBtn:hover {
    background: #4f46e5;
}
QPushButton#toolbarBtn:pressed {
    background: #4338ca;
}
QPushButton#toolbarBtnSecondary {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 16px;
    color: #64748b;
    font-weight: 500;
}
QPushButton#toolbarBtnSecondary:hover {
    background: #e2e8f0;
    color: #475569;
}

QMenuBar {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 2px 6px;
    spacing: 2px;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 6px;
    color: #334155;
}
QMenuBar::item:selected {
    background: #eef2ff;
    color: #4f46e5;
}
QMenu {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 28px 8px 14px;
    border-radius: 6px;
    color: #334155;
}
QMenu::item:selected {
    background: #eef2ff;
    color: #4f46e5;
}
QMenu::separator {
    height: 1px;
    background: #e2e8f0;
    margin: 4px 8px;
}

QToolBar {
    background: #ffffff;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    padding: 8px 16px;
    spacing: 8px;
}
QToolBar QToolButton {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 16px;
    color: #475569;
    font-weight: 500;
}
QToolBar QToolButton:hover {
    background: #eef2ff;
    border-color: #a5b4fc;
    color: #4f46e5;
}
QToolBar QToolButton:pressed {
    background: #e0e7ff;
}

QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    padding: 2px 8px;
}
QStatusBar::item {
    border: none;
}

QTabWidget#mainTabs::pane {
    border: none;
    background: transparent;
    top: 0;
    margin-top: 8px;
}
QTabBar::tab {
    background: transparent;
    border: none;
    color: #667085;
    padding: 11px 22px;
    margin-right: 4px;
    border-radius: 8px;
    font-weight: 600;
    min-width: 96px;
    min-height: 20px;
}
QTabBar::tab:hover {
    background: #f1f5f9;
    color: #334155;
}
QTabBar::tab:selected {
    background: #315efb;
    color: #ffffff;
    border: none;
}

QSplitter::handle {
    background: transparent;
    width: 8px;
}
QSplitter::handle:hover {
    background: #cbd5e1;
    border-radius: 4px;
}

/* ── Sidebar ── */
QWidget#sidebar {
    background: #ffffff;
    border: 1px solid #dfe4ec;
    border-radius: 12px;
}
QWidget#sidebarHeader {
    background: #f8faff;
    border: 1px solid #e5e9f1;
    border-radius: 10px;
}
QLabel#sidebarTitle {
    font-size: 14px;
    font-weight: 600;
    color: #334155;
}
QListWidget#themeList {
    background: transparent;
    border: none;
    outline: none;
    padding: 8px;
}
QListWidget#themeList::item {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 10px 12px;
    margin: 2px 0;
    color: #334155;
}
QListWidget#themeList::item:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
}
QListWidget#themeList::item:selected {
    background: #eef2ff;
    color: #4f46e5;
    border-color: #a5b4fc;
}

/* ── Content / info bar ── */
QWidget#contentPanel {
    background: transparent;
}
QWidget#themeInfoBar {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QLabel#themeInfoTitle {
    font-size: 16px;
    font-weight: 600;
    color: #0f172a;
}
QLabel#themeInfoMeta {
    color: #64748b;
    font-size: 12px;
}
QLabel#themeInfoIcon {
    background: linear-gradient(135deg, #6366f1, #4f46e5);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    font-size: 24px;
}
QLabel#themeInfoTag, QLabel#countBadge, QLabel#packDateTag {
    background: #eef2ff;
    color: #4f46e5;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#themeInfoTag[tone="warn"], QLabel#incompleteBadge {
    background: #fef3c7;
    color: #b45309;
}
QLabel#countBadge {
    min-width: 18px;
    qproperty-alignment: AlignCenter;
}
QLabel#installedBadge {
    background: #ecfdf5;
    color: #047857;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}

QScrollArea#previewScroll {
    background: #ffffff;
    border: 1px solid #dfe4ec;
    border-radius: 12px;
    padding: 2px;
}
QScrollArea#previewScroll > QWidget > QWidget {
    background: #ffffff;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    height: 0;
}

/* ── Buttons ── */
QPushButton {
    background: #ffffff;
    border: 1px solid #d7dde7;
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 22px;
    color: #344054;
    font-weight: 600;
}
QPushButton:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
}
QPushButton:pressed {
    background: #e2e8f0;
}
QPushButton:disabled {
    background: #f1f5f9;
    border-color: #e2e8f0;
    color: #94a3b8;
}
QPushButton#applyBtn, QPushButton#downloadBtn, QPushButton#applyOnlineBtn {
    background: #315efb;
    border: none;
    border-radius: 8px;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 20px;
}
QPushButton#applyBtn:hover, QPushButton#downloadBtn:hover, QPushButton#applyOnlineBtn:hover {
    background: #244bd1;
}
QPushButton#applyBtn:pressed, QPushButton#downloadBtn:pressed, QPushButton#applyOnlineBtn:pressed {
    background: #4338ca;
}
QPushButton#applyBtn:disabled, QPushButton#downloadBtn:disabled {
    background: #c7d2fe;
    color: #ffffff;
}
QPushButton#dangerBtn {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
    color: #dc2626;
    font-weight: 500;
}
QPushButton#dangerBtn:hover {
    background: #fee2e2;
    border-color: #fca5a5;
}
QPushButton#toolBtn {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    color: #475569;
    font-weight: 500;
}
QPushButton#toolBtn:hover {
    background: #e2e8f0;
    border-color: #cbd5e1;
    color: #1e293b;
}
/* ── 在线素材库头部 ── */
QWidget#onlineHeaderCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
}
QLabel#onlineTitle {
    font-size: 18px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#onlineCount {
    font-size: 12px;
    color: #94a3b8;
}
QPushButton#refreshBtn {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 16px;
    color: #475569;
    font-weight: 500;
}
QPushButton#refreshBtn:hover {
    background: #e2e8f0;
    border-color: #cbd5e1;
}
QFrame#filterSegment {
    background: #f1f5f9;
    border: none;
    border-radius: 8px;
}
QPushButton#filterTag {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    color: #64748b;
    font-weight: 500;
    font-size: 12px;
}
QPushButton#filterTag:hover {
    background: #e2e8f0;
    color: #334155;
}
QPushButton#filterTag:checked {
    background: #ffffff;
    color: #6366f1;
    font-weight: 600;
    border: 1px solid #e2e8f0;
}
QPushButton#filterTag:checked:hover {
    background: #ffffff;
    color: #4f46e5;
}

/* ── Inputs ── */
QLineEdit, QLineEdit#searchInput, QLineEdit#pageInput {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 12px;
    color: #0f172a;
    selection-background-color: #c7d2fe;
}
QLineEdit:focus, QLineEdit#searchInput:focus, QLineEdit#pageInput:focus {
    border: 2px solid #315efb;
    background: #ffffff;
}
QLineEdit#pageInput {
    max-width: 64px;
    min-width: 48px;
    padding: 6px 8px;
}

/* ── Online library ── */
QLabel#onlineTitle {
    font-size: 20px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#onlineCount, QLabel#onlineStatus, QLabel#pageTotal, QLabel#pageLabel {
    color: #64748b;
    font-size: 12px;
}
QLabel#pageLabel {
    font-weight: 700;
    color: #334155;
    min-width: 64px;
    qproperty-alignment: AlignCenter;
}
QLabel#packTitle {
    font-weight: 650;
    color: #0f172a;
    font-size: 13px;
}
QLabel#packPreview {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    color: #94a3b8;
}
QLabel#emptyState {
    color: #94a3b8;
    font-size: 13px;
    padding: 40px;
    line-height: 1.8;
}
QFrame#packCard {
    background: #ffffff;
    border: 1px solid #dfe4ec;
    border-radius: 12px;
}
QFrame#packCard:hover {
    border-color: #9db4ff;
    background: #f8faff;
}
QWidget#pageBarWidget {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QWidget#onlineHeaderCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QScrollArea#onlineScroll {
    background: transparent;
    border: none;
}
QWidget#onlineGridHost {
    background: transparent;
}

QProgressBar#globalProgress {
    border: none;
    background: #e2e8f0;
    border-radius: 0px;
    max-height: 3px;
    min-height: 3px;
    text-align: center;
}
QProgressBar#globalProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #22c55e, stop:1 #16a34a);
    border-radius: 0px;
}

/* ── Notification Banner ── */
QFrame#notificationBanner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366f1, stop:1 #4f46e5);
    border: none;
    min-height: 48px;
    max-height: 48px;
}

QMessageBox {
    background: #ffffff;
}
QMessageBox QLabel {
    color: #334155;
}

/* ── Custom Dialog ── */
QDialog#customDialog {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}
QLabel#dialogIcon {
    background: linear-gradient(135deg, #6366f1, #4f46e5);
    color: #ffffff;
    border-radius: 24px;
    font-size: 28px;
    font-weight: 700;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
}
QLabel#dialogTitle {
    font-size: 18px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#dialogMessage {
    font-size: 14px;
    color: #475569;
    line-height: 1.5;
}
QLabel#dialogVersion {
    background: #eef2ff;
    color: #4f46e5;
    border-radius: 8px;
    padding: 4px 12px;
    font-size: 13px;
    font-weight: 600;
}
QLabel#releaseNotes {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px;
    color: #475569;
    font-size: 12px;
}
QPushButton#dialogPrimaryBtn {
    background: #6366f1;
    border: 1px solid #4f46e5;
    color: #ffffff;
    font-weight: 600;
    padding: 10px 24px;
    border-radius: 10px;
    font-size: 14px;
}
QPushButton#dialogPrimaryBtn:hover {
    background: #4f46e5;
    border-color: #4338ca;
}
QPushButton#dialogPrimaryBtn:pressed {
    background: #4338ca;
}
QPushButton#dialogSecondaryBtn {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    color: #475569;
    font-weight: 500;
    padding: 10px 24px;
    border-radius: 10px;
    font-size: 14px;
}
QPushButton#dialogSecondaryBtn:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
    color: #1e293b;
}
QPushButton#dialogSecondaryBtn:pressed {
    background: #e2e8f0;
}
"""
