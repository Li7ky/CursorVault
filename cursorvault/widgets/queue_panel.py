# -*- coding: utf-8 -*-
"""下载队列页 - 侧边栏「下载队列」tab 的实时任务可视化.

每个进行中的任务一张卡片：标题 + 阶段文字 + 独立进度胶囊。
set_items() 由主窗口在下载信号到达时全量刷新（任务数少，重建成本可忽略）。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .bottombar import ProgressPill
from .vector_icons import ICON, set_label_icon


class _QueueCard(QFrame):
    """单任务卡片：标题 + 阶段 + 进度胶囊."""

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("queueCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel(item.get("title", ""))
        title.setObjectName("queueCardTitle")
        title.setToolTip(item.get("title", ""))
        top.addWidget(title, 1)
        phase = QLabel(item.get("phase", ""))
        phase.setObjectName("queueCardPhase")
        top.addWidget(phase, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(top)

        pill = ProgressPill(width=520, height=6)
        total = item.get("total", 0)
        if total > 0:
            pill.setRange(0, 100)
            pill.setValue(int(item.get("done", 0) * 100 / total))
        else:
            pill.setRange(0, 0)   # 不定态：光斑巡航
        v.addWidget(pill)


class DownloadQueuePanel(QWidget):
    """下载队列页：大标题 + 任务卡片列表 + 空状态."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("queuePanel")
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(6)

        kicker = QLabel("QUEUE · 实时进度")
        kicker.setObjectName("pageEyebrow")
        root.addWidget(kicker)

        title = QLabel("下载队列")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        self._sub = QLabel("正在取件的素材会出现在这里，取好自动放进本地主题库")
        self._sub.setObjectName("pageSubtitle")
        root.addWidget(self._sub)

        root.addSpacing(10)

        # 空状态
        self._empty = QWidget()
        ev = QVBoxLayout(self._empty)
        ev.setContentsMargins(0, 48, 0, 0)
        ev.setSpacing(12)
        ev.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        icon = QLabel()
        icon.setFixedSize(56, 56)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_label_icon(icon, ICON.IMAGE, size=44, role="icon-neutral")
        ev.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_text = QLabel("没有正在进行的下载")
        empty_text.setObjectName("emptySub")
        ev.addWidget(empty_text, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self._empty)

        # 卡片列表
        self._cards_host = QWidget()
        self._cards = QVBoxLayout(self._cards_host)
        self._cards.setContentsMargins(0, 0, 0, 0)
        self._cards.setSpacing(10)
        root.addWidget(self._cards_host)
        root.addStretch(1)

    def set_items(self, items: list[dict]) -> None:
        """items: [{slug, title, phase, done, total}]，全量重建卡片."""
        while self._cards.count():
            it = self._cards.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        n = len(items)
        self._empty.setVisible(n == 0)
        if n > 1:
            self._sub.setText(
                f"{n} 个素材正在同时取件，取好会自动放进本地主题库"
            )
        else:
            self._sub.setText("正在取件的素材会出现在这里，取好自动放进本地主题库")
        for it in items:
            self._cards.addWidget(_QueueCard(it))
