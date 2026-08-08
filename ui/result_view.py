"""查詢結果的畫法 —— 熱鍵彈窗與匯入視窗的預覽共用同一份，才不會兩邊長不一樣"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy

from core import settings

_W = settings.section("window")

LABEL_WIDTH = _W["field_label_width"]
ROW_GAP = _W["row_gap"]
HERO_GAP = _W["hero_gap"]

# 料號右邊那顆小標籤（預設不顯示）
SOURCE_BADGE = (_W.get("source_badge") or "").strip()
BADGE_ROOM = 64 if SOURCE_BADGE else 0


class ElidingLabel(QLabel):
    """太長就中間省略，滑鼠移上去看得到完整內容

    料號長度不受控（有人一貼就是 40 個字），直接換行會把卡片撐得很醜，
    被裁切又看不到後面。中間省略 + tooltip 是兩邊都顧得到的做法。
    """

    def __init__(self, text, obj, mode=Qt.ElideMiddle, max_width=0):
        super().__init__(objectName=obj)
        self._full = text or ""
        self._mode = mode
        self.setToolTip(self._full)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        if max_width > 0:
            self.setMaximumWidth(max_width)
        self.setText(self._full)

    def set_full(self, text):
        """換內容但不重建 widget —— 清單每按一個鍵都會呼叫，不能有額外成本"""
        self._full = text or ""
        self.setToolTip(self._full)
        super().setText(self._full)
        self._apply_elide()

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._full), fm.height())

    def minimumSizeHint(self):
        return QSize(0, self.fontMetrics().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        fm = self.fontMetrics()
        available = max(0, self.width())
        if fm.horizontalAdvance(self._full) <= available:
            if self.text() != self._full:
                super().setText(self._full)
            return
        super().setText(fm.elidedText(self._full, self._mode, available))


def label(text, obj):
    lab = QLabel(text, objectName=obj)
    lab.setWordWrap(True)
    return lab


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout():
            sub = item.layout()
            clear(sub)
            sub.deleteLater()


def fill(body, data, label_width=None, content_width=0):
    label_width = LABEL_WIDTH if label_width is None else label_width
    key_room = max(0, content_width - BADGE_ROOM) if content_width else 0

    head = QHBoxLayout()
    head.setSpacing(9)
    head.addWidget(ElidingLabel(data["_key"], "partNumber", max_width=key_room))
    if SOURCE_BADGE:
        head.addWidget(QLabel(SOURCE_BADGE, objectName="badge"))
    head.addStretch()
    body.addLayout(head)

    typed = data.get("_typed")
    if typed:
        body.addSpacing(5)
        body.addWidget(label(f"你輸入的是「{typed}」，忽略符號差異後對到上面這筆", "hint"))
    body.addSpacing(16)

    fields = data.get("_fields") or []
    for i, (name, value) in enumerate(fields):
        if i == 0:
            body.addWidget(label(name, "fieldLabel"))
            body.addSpacing(1)
            body.addWidget(label(value or "—", "heroValue"))
            if len(fields) > 1:
                body.addSpacing(HERO_GAP)
            continue
        row = QHBoxLayout()
        row.setSpacing(14)
        name_lab = label(name, "fieldLabel")
        name_lab.setFixedWidth(label_width)
        name_lab.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        row.addWidget(name_lab)
        row.addWidget(label(value or "—", "fieldValue"), 1)
        body.addLayout(row)
        if i < len(fields) - 1:
            body.addSpacing(ROW_GAP)

    missing = data.get("_missing") or []
    if missing:
        body.addSpacing(15)
        body.addWidget(label("這幾個檔案查不到這筆料號：" + "、".join(missing), "hint"))
