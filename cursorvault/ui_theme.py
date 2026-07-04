# -*- coding: utf-8 -*-
"""CursorVault 全局视觉主题（浅色 · 现代卡片风）."""

APP_STYLESHEET = """
/* ── Design tokens ──
   bg: #f1f5f9  surface: #ffffff  primary: #2563eb
   text: #0f172a  muted: #64748b  border: #e2e8f0
*/
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    outline: none;
}

QMainWindow {
    background: #f1f5f9;
    color: #0f172a;
}

QWidget#centralWidget {
    background: #f1f5f9;
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
    background: #eff6ff;
    color: #1d4ed8;
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
    background: #eff6ff;
    color: #1d4ed8;
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
    padding: 8px 12px;
    spacing: 8px;
}
QToolBar QToolButton {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px 14px;
    color: #334155;
    font-weight: 500;
}
QToolBar QToolButton:hover {
    background: #eff6ff;
    border-color: #93c5fd;
    color: #1d4ed8;
}
QToolBar QToolButton:pressed {
    background: #dbeafe;
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
    color: #64748b;
    padding: 10px 20px;
    margin-right: 4px;
    border-radius: 10px;
    font-weight: 600;
    min-width: 88px;
}
QTabBar::tab:hover {
    background: #e2e8f0;
    color: #334155;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #2563eb;
    border: 1px solid #e2e8f0;
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
    border: 1px solid #e2e8f0;
    border-radius: 14px;
}
QLabel#sidebarTitle {
    font-size: 15px;
    font-weight: 700;
    color: #0f172a;
    padding-left: 2px;
}
QListWidget#themeList {
    background: transparent;
    border: none;
    outline: none;
    padding: 4px;
}
QListWidget#themeList::item {
    background: #f8fafc;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 10px 12px;
    margin: 3px 2px;
    color: #334155;
}
QListWidget#themeList::item:hover {
    background: #eff6ff;
    border-color: #bfdbfe;
}
QListWidget#themeList::item:selected {
    background: #2563eb;
    color: #ffffff;
    border-color: #1d4ed8;
}

/* ── Content / info bar ── */
QWidget#contentPanel {
    background: transparent;
}
QWidget#themeInfoBar {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
}
QLabel#themeInfoTitle {
    font-size: 18px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#themeInfoMeta {
    color: #64748b;
    font-size: 12px;
}
QLabel#themeInfoIcon {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    font-size: 22px;
}
QLabel#themeInfoTag, QLabel#countBadge, QLabel#packDateTag {
    background: #eff6ff;
    color: #1d4ed8;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#themeInfoTag[tone="warn"], QLabel#incompleteBadge {
    background: #fff7ed;
    color: #c2410c;
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
    border: 1px solid #e2e8f0;
    border-radius: 14px;
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
    border: 1px solid #e2e8f0;
    border-radius: 9px;
    padding: 7px 14px;
    min-height: 20px;
    color: #334155;
    font-weight: 500;
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
    background: #2563eb;
    border: 1px solid #1d4ed8;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 16px;
}
QPushButton#applyBtn:hover, QPushButton#downloadBtn:hover, QPushButton#applyOnlineBtn:hover {
    background: #1d4ed8;
    border-color: #1e40af;
}
QPushButton#applyBtn:pressed, QPushButton#downloadBtn:pressed, QPushButton#applyOnlineBtn:pressed {
    background: #1e40af;
}
QPushButton#applyBtn:disabled, QPushButton#downloadBtn:disabled {
    background: #93c5fd;
    border-color: #93c5fd;
    color: #eff6ff;
}
QPushButton#dangerBtn {
    background: #fff1f2;
    border: 1px solid #fecdd3;
    color: #be123c;
    font-weight: 600;
}
QPushButton#dangerBtn:hover {
    background: #ffe4e6;
    border-color: #fda4af;
}
QPushButton#toolBtn {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    color: #475569;
}
QPushButton#toolBtn:hover {
    background: #eff6ff;
    border-color: #93c5fd;
    color: #1d4ed8;
}
QFrame#filterSegment {
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}
QPushButton#filterTag {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 7px 14px;
    color: #64748b;
    font-weight: 600;
    min-height: 18px;
}
QPushButton#filterTag:hover {
    background: #e2e8f0;
    color: #334155;
}
QPushButton#filterTag:checked {
    background: #2563eb;
    color: #ffffff;
}
QPushButton#filterTag:checked:hover {
    background: #1d4ed8;
    color: #ffffff;
}

/* ── Inputs ── */
QLineEdit, QLineEdit#searchInput, QLineEdit#pageInput {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 8px 12px;
    color: #0f172a;
    selection-background-color: #bfdbfe;
}
QLineEdit:focus, QLineEdit#searchInput:focus, QLineEdit#pageInput:focus {
    border: 1px solid #2563eb;
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
    font-size: 14px;
    padding: 32px;
}
QFrame#packCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
}
QFrame#packCard:hover {
    border-color: #93c5fd;
    background: #f8fbff;
}
QWidget#pageBarWidget {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QWidget#onlineHeaderCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
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
    border-radius: 3px;
    max-height: 4px;
    min-height: 4px;
}
QProgressBar#globalProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3b82f6, stop:1 #2563eb);
    border-radius: 3px;
}

QMessageBox {
    background: #ffffff;
}
QMessageBox QLabel {
    color: #334155;
}
"""
