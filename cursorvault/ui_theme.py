# -*- coding: utf-8 -*-
"""CursorVault 视觉设计系统 v4 - Fluent Atlas.

设计语言：Windows 11 Fluent (Mica/Acrylic) + Linear 精密排版 + Notion 留白
- 背景：分层 Mica 质感，侧栏与主画布微差区分，不用纯黑
- 主色：蓝 #2563EB (light) / #60A5FA-dark，保证在任何底色上可辨
- 圆角：8 / 12 / 16 分级，卡片 12、按钮 8、输入框 8
- 阴影：仅卡片与抽屉有柔和阴影，其余靠描边
- 动效：hover 用边框与底色微变，无位移
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# 设计令牌（Semantic Tokens）
# ═══════════════════════════════════════════════════════════════

DARK_TOKENS: dict[str, str] = {
    # ── 背景层 ──
    "bg-app":            "#1a1d23",
    "bg-base":           "#1a1d23",
    "bg-canvas":         "#1e2128",
    "bg-sidebar":        "#171a20",
    "bg-topbar":         "#1e2128",
    "bg-bottombar":      "#1e2128",
    "bg-drawer":         "#1e2128",
    "bg-card":           "#252830",
    "bg-overlay":        "rgba(0,0,0,0.48)",

    # ── 表面层 ──
    "surface-0":         "#1e2128",
    "surface-1":         "#252830",
    "surface-2":         "#2e323d",
    "surface-3":         "#363b48",
    "surface-hover":     "#2a2e39",

    # ── 主色（Fluent Blue）──
    "accent":            "#60a5fa",
    "accent-strong":     "#3b82f6",
    "accent-soft":       "rgba(96,165,250,0.14)",
    "accent-ring":       "rgba(96,165,250,0.28)",
    "accent-text":       "#0b1220",

    # ── 文字 ──
    "text-primary":      "#f1f5f9",
    "text-secondary":    "#94a3b8",
    "text-tertiary":     "#64748b",
    "text-disabled":     "#475569",
    "text-on-accent":    "#0b1220",

    # ── 描边 ──
    "border-subtle":     "#2a2e38",
    "border-default":    "#333844",
    "border-strong":     "#3f4554",
    "border-focus":      "#60a5fa",

    # ── 状态 ──
    "success":           "#34d399",
    "warning":           "#fbbf24",
    "error":             "#f87171",
    "info":              "#60a5fa",
    "success-soft":      "rgba(52,211,153,0.12)",
    "warning-soft":      "rgba(251,191,36,0.12)",
    "error-soft":        "rgba(248,113,113,0.10)",
    "info-soft":         "rgba(96,165,250,0.10)",

    # ── 功能图标配色 ──
    # 语义化上色：同类功能一个色相，明暗各自调对比度保证在各自底色上可读。
    # 导航/工具栏图标用它来区分功能，比统一灰色更容易扫视定位。
    "icon-globe":        "#60a5fa",   # 在线素材库
    "icon-folder":       "#fbbf24",   # 本地主题
    "icon-save":         "#22d3ee",   # 备份
    "icon-restore":      "#34d399",   # 恢复
    "icon-refresh":      "#a78bfa",   # 刷新
    "icon-download":     "#60a5fa",   # 下载
    "icon-check":        "#34d399",   # 已完成/已安装
    "icon-import":       "#a5b4fc",   # 导入
    "icon-trash":        "#f87171",   # 删除
    "icon-info":         "#60a5fa",   # 信息
    "icon-cursor":       "#c4b5fd",   # 鼠标
    "icon-neutral":      "#94a3b8",   # 中性：关闭/更多/搜索等

    # ── 字体 ──
    "font-family":       '"Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif',
    "font-mono":         '"Cascadia Code", "JetBrains Mono", Consolas, monospace',
}

LIGHT_TOKENS: dict[str, str] = {
    # ── 背景层 ──
    "bg-app":            "#f3f4f6",
    "bg-base":           "#f3f4f6",
    "bg-canvas":         "#ffffff",
    "bg-sidebar":        "#f8f9fb",
    "bg-topbar":         "#ffffff",
    "bg-bottombar":      "#ffffff",
    "bg-drawer":         "#ffffff",
    "bg-card":           "#ffffff",
    "bg-overlay":        "rgba(15,23,42,0.32)",

    # ── 表面层 ──
    "surface-0":         "#ffffff",
    "surface-1":         "#f8f9fb",
    "surface-2":         "#eef0f3",
    "surface-3":         "#e2e5ea",
    "surface-hover":     "#f1f3f6",

    # ── 主色（Fluent Blue）──
    "accent":            "#2563eb",
    "accent-strong":     "#1d4ed8",
    "accent-soft":       "rgba(37,99,235,0.08)",
    "accent-ring":       "rgba(37,99,235,0.18)",
    "accent-text":       "#ffffff",

    # ── 文字 ──
    "text-primary":      "#0f172a",
    "text-secondary":    "#64748b",
    "text-tertiary":     "#94a3b8",
    "text-disabled":     "#cbd5e1",
    "text-on-accent":    "#ffffff",

    # ── 描边 ──
    "border-subtle":     "#e8eaef",
    "border-default":    "#dde1e8",
    "border-strong":     "#cbd5e1",
    "border-focus":      "#2563eb",

    # ── 状态 ──
    "success":           "#059669",
    "warning":           "#d97706",
    "error":             "#dc2626",
    "info":              "#2563eb",
    "success-soft":      "rgba(5,150,105,0.08)",
    "warning-soft":      "rgba(217,119,6,0.08)",
    "error-soft":        "rgba(220,38,38,0.08)",
    "info-soft":         "rgba(37,99,235,0.06)",

    # ── 功能图标配色 ──
    # 语义化上色：详见 DARK_TOKENS 同段注释。浅色下用 600/700 级保证在白底上的对比度。
    "icon-globe":        "#2563eb",   # 在线素材库
    "icon-folder":       "#d97706",   # 本地主题
    "icon-save":         "#0891b2",   # 备份
    "icon-restore":      "#059669",   # 恢复
    "icon-refresh":      "#7c3aed",   # 刷新
    "icon-download":     "#2563eb",   # 下载
    "icon-check":        "#059669",   # 已完成/已安装
    "icon-import":       "#4f46e5",   # 导入
    "icon-trash":        "#dc2626",   # 删除
    "icon-info":         "#2563eb",   # 信息
    "icon-cursor":       "#7c3aed",   # 鼠标
    "icon-neutral":      "#64748b",   # 中性：关闭/更多/搜索等

    # ── 字体 ──
    "font-family":       '"Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif',
    "font-mono":         '"Cascadia Code", "JetBrains Mono", Consolas, monospace',
}

THEMES: dict[str, dict[str, str]] = {
    "dark": DARK_TOKENS,
    "light": LIGHT_TOKENS,
}

# 运行时主题注册表：供组件 inline 样式跟随当前明暗（避免硬编码浅色背景）
_current_theme = "light"


def set_current_theme(theme: str) -> None:
    global _current_theme
    _current_theme = "dark" if theme == "dark" else "light"


def current_theme() -> str:
    return _current_theme


def token(name: str, fallback: str = "transparent") -> str:
    """返回当前主题令牌值；未定义时回退."""
    t = get_tokens(_current_theme)
    return t.get(name, fallback)


def get_tokens(theme: str = "dark") -> dict[str, str]:
    return THEMES.get(theme, LIGHT_TOKENS)


def build_stylesheet(theme: str = "light") -> str:
    t = get_tokens(theme)
    return _QSS_TEMPLATE.format(**t)


# ═══════════════════════════════════════════════════════════════
# QSS 模板 - v4 Fluent Atlas
# ═══════════════════════════════════════════════════════════════

_QSS_TEMPLATE = """
/* ═══ 基础 ═══ */
* {{
    font-family: {font-family};
    font-size: 13px;
    outline: none;
    -webkit-font-smoothing: antialiased;
}}

QMainWindow {{
    background-color: {bg-app};
}}

QWidget#centralWidget {{
    background-color: {bg-app};
}}

QWidget {{
    background: transparent;
    color: {text-primary};
}}

/* ── 原生控件覆盖 ── */
QToolButton {{
    background: transparent;
    color: {text-secondary};
    border: none;
    border-radius: 8px;
}}
QToolButton:hover {{ background: {surface-2}; color: {text-primary}; }}
QToolButton:pressed {{ background: {surface-3}; }}
QToolButton:checked {{ background: {accent-soft}; color: {accent}; }}

QMenuBar {{
    background: {bg-topbar};
    color: {text-primary};
    border-bottom: 1px solid {border-subtle};
    padding: 2px 8px;
}}
QMenuBar::item {{
    background: transparent; color: {text-secondary};
    padding: 5px 10px; border-radius: 6px; margin: 2px;
}}
QMenuBar::item:selected {{ background: {surface-2}; color: {text-primary}; }}

QMenu {{
    background: {surface-0};
    color: {text-primary};
    border: 1px solid {border-default};
    border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 18px 8px 14px;
    border-radius: 8px;
    color: {text-primary};
}}
QMenu::item:selected {{ background: {accent-soft}; color: {accent}; }}
QMenu::separator {{ height: 1px; background: {border-subtle}; margin: 6px 8px; }}

QToolTip {{
    background: {text-primary};
    color: {bg-canvas};
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
QStatusBar {{ background: {bg-app}; color: {text-tertiary}; border-top: 1px solid {border-subtle}; }}

/* ═══ 侧边栏 260px ═══ */
QWidget#sidebar {{
    background-color: {bg-sidebar};
    border-right: 1px solid {border-subtle};
}}
QWidget#sidebarBrand {{
    background: transparent;
}}
QLabel#brandTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {text-primary};
    letter-spacing: -0.3px;
    background: transparent;
}}
QLabel#brandSubtitle {{
    font-size: 11px;
    font-weight: 600;
    color: {text-tertiary};
    letter-spacing: 0.6px;
    background: transparent;
}}
QLabel#brandIcon {{
    background: {accent};
    color: {accent-text};
    border-radius: 8px;
    font-size: 15px;
    font-weight: 400;
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol";
}}
QLabel#navSectionLabel {{
    color: {text-tertiary};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.0px;
    background: transparent;
    padding: 0 4px;
}}
QPushButton#navBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 10px 12px;
    color: {text-secondary};
    font-size: 13px;
    font-weight: 600;
    text-align: left;
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI", "Microsoft YaHei UI", sans-serif;
}}
QPushButton#navBtn:hover {{
    background: {surface-1};
    color: {text-primary};
    border: 1px solid {border-subtle};
}}
QPushButton#navBtn:checked {{
    background: {accent-soft};
    color: {accent};
    border: 1px solid transparent;
    font-weight: 700;
}}
QLabel#navCount {{
    background: {surface-2};
    color: {text-tertiary};
    border-radius: 6px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#navCount[active="true"] {{
    background: {accent-soft};
    color: {accent};
}}
QFrame#sidebarSep {{
    background: {border-subtle};
    max-height: 1px;
    min-height: 1px;
}}
QScrollArea#sidebarScroll {{
    background: transparent;
    border: none;
}}
QWidget#themeListItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}}
QWidget#themeListItem:hover {{
    background: {surface-1};
    border: 1px solid {border-subtle};
}}
QWidget#themeListItem[active="true"] {{
    background: {accent-soft};
    border: 1px solid {accent-soft};
}}
QLabel#themeItemTitle {{
    font-size: 12.5px;
    font-weight: 600;
    color: {text-primary};
    background: transparent;
}}
QLabel#themeItemSub {{
    font-size: 11px;
    color: {text-tertiary};
    background: transparent;
}}
QLabel#themeItemBadge {{
    background: {surface-2};
    color: {text-tertiary};
    border-radius: 5px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#sidebarFooter {{
    color: {text-tertiary};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
    background: transparent;
}}
QPushButton#sidebarToolBtn {{
    background: transparent;
    border: 1px solid {border-subtle};
    border-radius: 8px;
    color: {text-tertiary};
    font-size: 15px;
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol";
    min-width: 36px;
    min-height: 36px;
    max-width: 36px;
    max-height: 36px;
}}
QPushButton#sidebarToolBtn:hover {{
    background: {surface-1};
    color: {text-primary};
    border: 1px solid {border-default};
}}
QLabel#toolLabel {{
    color: {text-tertiary};
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    padding: 0;
}}
QLabel#toolLabel:hover {{
    color: {text-primary};
}}

/* ═══ 顶栏 56px ═══ */
QWidget#topBar {{
    background-color: {bg-topbar};
    border-bottom: 1px solid {border-subtle};
}}
QLabel#topBarTitle {{
    font-size: 17px;
    font-weight: 700;
    color: {text-primary};
    letter-spacing: -0.3px;
    background: transparent;
}}
QLabel#topBarSub {{
    font-size: 12px;
    color: {text-tertiary};
    background: transparent;
}}
QLineEdit#searchBox {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 8px;
    padding: 0 12px 0 36px;
    color: {text-primary};
    selection-background-color: {accent-soft};
    selection-color: {text-primary};
    font-size: 13px;
}}
QLineEdit#searchBox:hover {{ border: 1px solid {border-default}; background: {surface-0}; }}
QLineEdit#searchBox:focus {{ border: 1px solid {accent}; background: {surface-0}; }}
QLineEdit#searchBox::placeholder {{ color: {text-tertiary}; }}

QPushButton#topActionBtn {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 8px;
    padding: 0;
    color: {text-secondary};
    font-size: 15px;
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol";
    min-width: 36px;
    min-height: 36px;
    max-width: 36px;
    max-height: 36px;
}}
QPushButton#topActionBtn:hover {{
    background: {surface-2};
    color: {text-primary};
    border: 1px solid {border-default};
}}
QPushButton#topActionBtn:checked {{
    background: {accent-soft};
    color: {accent};
    border: 1px solid {accent-soft};
}}
QPushButton#topPrimaryBtn {{
    background: {accent};
    color: {accent-text};
    border: none;
    border-radius: 8px;
    padding: 0 14px;
    font-weight: 700;
    font-size: 13px;
    min-height: 36px;
    font-family: "Segoe Fluent Icons","Segoe MDL2 Assets","Segoe UI","Microsoft YaHei UI",sans-serif;
}}
QPushButton#topPrimaryBtn:hover {{ background: {accent-strong}; }}
QPushButton#topPrimaryBtn:pressed {{ background: {accent-strong}; }}

/* ═══ 内容区 ═══ */
QStackedWidget#contentStack {{ background-color: {bg-canvas}; }}
QStackedWidget {{ background-color: {bg-canvas}; }}
QScrollArea#onlineScroll {{ background-color: {bg-canvas}; }}
QScrollArea {{ background-color: {bg-canvas}; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#mainColumn {{ background-color: {bg-canvas}; }}
QWidget#onlineGridHost {{ background-color: {bg-canvas}; }}

QLabel#pageEyebrow {{
    color: {text-tertiary};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    background: transparent;
}}
QLabel#pageTitle {{
    font-size: 24px;
    font-weight: 780;
    color: {text-primary};
    letter-spacing: -0.6px;
    background: transparent;
}}
QLabel#pageSubtitle {{
    color: {text-secondary};
    font-size: 13px;
    background: transparent;
}}

/* 筛选分段 */
QFrame#filterSegment {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 8px;
}}
QPushButton#filterChip {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    color: {text-secondary};
    font-weight: 600;
    font-size: 12.5px;
}}
QPushButton#filterChip:hover {{ color: {text-primary}; }}
QPushButton#filterChip:checked {{
    background: {surface-0};
    color: {text-primary};
    border: 1px solid {border-subtle};
}}

/* ═══ 卡片 ═══ */
QFrame#packCard {{
    background-color: {bg-card};
    border: 1px solid {border-subtle};
    border-radius: 12px;
}}
QFrame#packCard:hover {{
    border: 1px solid {border-default};
}}
QLabel#packTitle {{
    font-size: 13.5px;
    font-weight: 650;
    color: {text-primary};
    background: transparent;
}}
QLabel#packSubtitle {{
    font-size: 12px;
    color: {text-tertiary};
    background: transparent;
}}
QLabel#packBadge {{
    background: {surface-1};
    color: {text-secondary};
    border: 1px solid {border-subtle};
    border-radius: 6px;
    padding: 3px 8px;
    font-weight: 700;
    font-size: 11px;
}}
QLabel#packBadge[tone="accent"] {{ background: {accent-soft}; color: {accent}; border: 1px solid transparent; }}
QLabel#packBadge[tone="installed"] {{ background: {success-soft}; color: {success}; border: 1px solid transparent; }}
QLabel#packBadge[tone="warn"] {{ background: {warning-soft}; color: {warning}; border: 1px solid transparent; }}
QLabel#packBadge[tone="error"] {{ background: {error-soft}; color: {error}; border: 1px solid transparent; }}

QPushButton#coverAction {{
    background: {accent};
    color: {accent-text};
    border: none;
    border-radius: 18px;
    font-size: 15px;
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol";
    font-weight: 400;
}}
QPushButton#coverAction:hover {{ background: {accent-strong}; }}
QPushButton#coverAction:disabled {{ background: {surface-2}; color: {text-tertiary}; }}

/* 骨架 */
QFrame#skeletonCard {{
    background-color: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 12px;
}}
QFrame#skeletonBox {{ background: {surface-2}; border-radius: 6px; }}

/* 空状态 */
QLabel#emptyState {{
    color: {text-tertiary};
    font-size: 13px;
    padding: 32px;
    background: transparent;
}}
QLabel#emptyTitle {{
    color: {text-secondary};
    font-size: 15px;
    font-weight: 700;
    background: transparent;
}}
QLabel#emptySub {{
    color: {text-tertiary};
    font-size: 12.5px;
    background: transparent;
}}

/* 分页 */
QPushButton#toolBtn {{
    background: {surface-0};
    border: 1px solid {border-default};
    border-radius: 8px;
    padding: 6px 12px;
    color: {text-secondary};
    font-weight: 600;
    font-size: 12px;
    min-height: 32px;
}}
QPushButton#toolBtn:hover {{ background: {surface-1}; color: {text-primary}; border: 1px solid {border-strong}; }}
QPushButton#toolBtn:disabled {{ background: {surface-1}; color: {text-disabled}; border: 1px solid {border-subtle}; }}
QLineEdit#pageInput {{
    background: {surface-0};
    border: 1px solid {border-default};
    border-radius: 8px;
    padding: 6px 10px;
    color: {text-primary};
}}
QLineEdit#pageInput:focus {{ border: 1px solid {accent}; }}
QLabel#pageLabel {{ color: {text-secondary}; font-size: 12px; font-weight: 600; padding: 0 6px; }}

/* ═══ 底栏 48px ═══ */
QWidget#bottomBar {{
    background-color: {bg-bottombar};
    border-top: 1px solid {border-subtle};
}}
QLabel#nowPlayingTitle {{
    font-size: 12.5px;
    font-weight: 650;
    color: {text-primary};
    background: transparent;
}}
QLabel#nowPlayingSub {{
    font-size: 11.5px;
    color: {text-tertiary};
    background: transparent;
}}
QLabel#nowPlayingCover {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 8px;
    color: {text-tertiary};
}}
QLabel#bottomStatus {{
    font-size: 11.5px;
    color: {text-tertiary};
    background: transparent;
}}

/* ═══ 详情抽屉 380px ═══ */
QWidget#detailDrawer {{
    background-color: {bg-drawer};
    border-left: 1px solid {border-default};
}}
QLabel#drawerEyebrow {{
    color: {text-tertiary};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    background: transparent;
}}
QLabel#drawerTitle {{
    font-size: 20px;
    font-weight: 760;
    color: {text-primary};
    letter-spacing: -0.4px;
    background: transparent;
}}
QLabel#drawerSubtitle {{
    font-size: 12px;
    color: {text-tertiary};
    background: transparent;
}}
QLabel#drawerCover {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 12px;
    color: {text-tertiary};
}}
QFrame#cursorLargeFrame {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 12px;
}}
QLabel#cursorLargeName {{
    font-size: 13px;
    font-weight: 650;
    color: {text-primary};
    background: transparent;
}}
QFrame#cursorCard {{
    background: {surface-0};
    border: 1px solid {border-subtle};
    border-radius: 10px;
}}
QFrame#cursorCard:hover {{ background: {surface-1}; border: 1px solid {border-default}; }}
QLabel#cursorCardName {{
    font-size: 10px;
    color: {text-tertiary};
    background: transparent;
}}
QFrame#cursorCard[active="true"] {{
    background: {accent-soft};
    border: 1px solid {accent};
}}
QFrame#cursorCard[active="true"] QLabel#cursorCardName {{ color: {accent}; font-weight: 700; }}

/* ═══ 按钮 ═══ */
QPushButton#primaryBtn {{
    background: {accent};
    color: {accent-text};
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 700;
    font-size: 13px;
}}
QPushButton#primaryBtn:hover {{ background: {accent-strong}; }}
QPushButton#primaryBtn:disabled {{ background: {surface-2}; color: {text-disabled}; }}
QFrame#queueCard {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 12px;
}}
QFrame#queueCard QLabel {{
    background: transparent;
}}
QLabel#queueCardTitle {{
    color: {text-primary};
    font-size: 14px;
    font-weight: 700;
}}
QLabel#queueCardPhase {{
    color: {text-tertiary};
    font-size: 12px;
}}
QPushButton#secondaryBtn {{
    background: {surface-0};
    border: 1px solid {border-default};
    border-radius: 8px;
    padding: 9px 16px;
    color: {text-primary};
    font-weight: 600;
    font-size: 13px;
}}
QPushButton#secondaryBtn:hover {{ background: {surface-1}; border: 1px solid {border-strong}; }}
QPushButton#dangerBtn {{
    background: transparent;
    border: 1px solid {border-default};
    border-radius: 8px;
    padding: 9px 16px;
    color: {error};
    font-weight: 600;
    font-size: 13px;
}}
QPushButton#dangerBtn:hover {{ background: {error-soft}; border: 1px solid {error}; }}
QPushButton#ghostBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: {text-tertiary};
    font-size: 14px;
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol";
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
}}
QPushButton#ghostBtn:hover {{ background: {surface-1}; color: {text-primary}; }}

/* ═══ 通知 ═══ */
QFrame#notificationBanner {{
    background: {info-soft};
    border-bottom: 1px solid {border-subtle};
}}
QLabel#notificationText {{ color: {text-primary}; font-size: 12.5px; background: transparent; }}
QPushButton#bannerAction {{
    background: {accent}; color: {accent-text};
    border: none; border-radius: 8px; padding: 7px 14px; font-weight: 700; font-size: 12px;
}}
QPushButton#bannerAction:hover {{ background: {accent-strong}; }}

/* ═══ 滚动条 ═══ */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {border-strong};
    border-radius: 4px;
    min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: {text-tertiary}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {border-strong};
    border-radius: 4px;
    min-width: 36px;
}}
QScrollBar::handle:horizontal:hover {{ background: {text-tertiary}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* 进度 */
QProgressBar {{
    background: {surface-2};
    border: none;
    border-radius: 2px;
    height: 3px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 2px; }}

/* 对话框 */
QDialog#customDialog {{
    background: {bg-canvas};
    border: 1px solid {border-default};
    border-radius: 16px;
}}
QLabel#dialogIcon {{
    background: {accent-soft};
    color: {accent};
    border-radius: 20px;
    font-size: 20px;
    font-weight: 400;
    font-family: "Segoe Fluent Icons","Segoe MDL2 Assets","Segoe UI Symbol";
}}
QLabel#dialogBodyBox {{
    background: {surface-1};
    border: 1px solid {border-subtle};
    border-radius: 8px;
    color: {text-secondary};
    padding: 12px;
    font-size: 12px;
}}
QDialog#softDialog {{
    background: {bg-canvas};
    border: 1px solid {border-default};
    border-radius: 16px;
}}
QLabel#softIcon {{
    background: {warning-soft};
    border-radius: 23px;
}}
QLabel#softIcon[tone="success"] {{ background: {success-soft}; }}
QLabel#softIcon[tone="accent"] {{ background: {accent-soft}; }}
QLabel#softIcon[tone="error"] {{ background: {error-soft}; }}
QLabel#softTitle {{
    color: {text-primary};
    font-size: 16px;
    font-weight: 700;
    background: transparent;
}}
QLabel#softBody {{
    color: {text-secondary};
    font-size: 13px;
    background: transparent;
}}
QMessageBox {{ background: {bg-canvas}; }}
QMessageBox QLabel {{ color: {text-primary}; font-size: 13px; }}
QMessageBox QPushButton {{
    background: {surface-0};
    border: 1px solid {border-default};
    border-radius: 8px;
    padding: 7px 16px;
    color: {text-primary};
    font-weight: 600;
    min-width: 72px;
}}
QMessageBox QPushButton:hover {{ background: {surface-1}; }}
QMessageBox QPushButton:default {{ background: {accent}; color: {accent-text}; border: none; }}
QMessageBox QPushButton:default:hover {{ background: {accent-strong}; }}
"""

APP_STYLESHEET: str = build_stylesheet("light")
