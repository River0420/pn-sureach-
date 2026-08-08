import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from core import book_config, hotkey, local_lookup, settings
from ui import result_view, style

KEY_HINTS = ("料號", "品號", "part", "pn", "mpn", "型號", "item")
EXTS = (".xlsx", ".xlsm", ".xls", ".csv")
MARKS = "①②③④⑤"
MAX_SOURCES = max(1, min(settings.get("data.max_sources", 3), len(MARKS)))
WARN_ROWS = settings.get("data.warn_rows", 300000)
MAX_HEADER_ROW = 30
SEED_FIELDS = 3
# 第一次載入時優先塞這些欄位 —— 業務最常看的就是價格、庫存、交期
SEED_HINTS = ("成本", "價", "庫存", "交期", "訂購量", "moq", "stock", "price", "cost", "lead")

SPEC_ROLE = Qt.UserRole + 1


def sid_index(sid):
    """"s2" -> 1；設定檔被改壞也不要整個崩掉"""
    try:
        return int(str(sid)[1:]) - 1
    except (TypeError, ValueError):
        return -1


def make_item(sid, column, tip=""):
    """欄位項目把來源記在 UserRole，不要靠解析顯示文字反推

    顯示的 ①②③ 只是給人看的；欄位名稱剛好以那些字元開頭時，
    解析文字會判斷錯來源。
    """
    index = sid_index(sid)
    mark = MARKS[index] if 0 <= index < len(MARKS) else "?"
    item = QListWidgetItem(f"{mark} {column}")
    item.setData(SPEC_ROLE, (sid, column))
    if tip:
        item.setToolTip(tip)
    return item


def spec_of(item):
    spec = item.data(SPEC_ROLE)
    if isinstance(spec, (tuple, list)) and len(spec) == 2:
        return str(spec[0]), str(spec[1])
    text = item.text()
    if text and text[0] in MARKS:
        return f"s{MARKS.index(text[0]) + 1}", text[1:].strip()
    return "s1", text.strip()


def first_url(event):
    urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
    for url in urls:
        path = url.toLocalFile()
        if path.lower().endswith(EXTS):
            return path
    return None


class SourceSlot(QFrame):
    """一個來源檔案：檔案 + 工作表 + 它自己的料號欄位"""
    changed = Signal()
    pickRequested = Signal(object)

    def __init__(self, idx):
        super().__init__(objectName="slot")
        self.idx = idx
        self.sid = f"s{idx + 1}"
        self.mark = MARKS[idx]
        self.path = None
        self.df = None
        self.key_index = {}
        self.decimal = set()
        self._restoring = None
        self._header_manual = False      # 使用者自己攤開過就一直開著
        self._header_shown = False

        self.setAcceptDrops(True)
        self.setProperty("filled", "false")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 12)
        lay.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(QLabel(f"{self.mark} 檔案{idx + 1}", objectName="slotBadge"))
        top.addStretch()
        self.swap_btn = QPushButton("更換", objectName="linkBtn")
        self.swap_btn.clicked.connect(lambda: self.pickRequested.emit(self))
        self.clear_btn = QPushButton("✕", objectName="linkBtn")
        self.clear_btn.setToolTip("移除這個檔案")
        self.clear_btn.clicked.connect(self.clear_source)
        top.addWidget(self.swap_btn)
        top.addWidget(self.clear_btn)
        lay.addLayout(top)
        lay.addSpacing(9)

        self.name_lab = QLabel("把 Excel 拖進來", objectName="slotEmpty")
        lay.addWidget(self.name_lab)
        lay.addSpacing(1)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        self.meta_lab = QLabel("或點「選擇檔案」", objectName="slotMeta")
        meta_row.addWidget(self.meta_lab)
        meta_row.addStretch()
        # 標題列平常不該出現 —— 99% 的檔案欄位名稱就在第一列，程式自己猜得到。
        # 只有猜錯的時候使用者才需要它，所以收在這個連結後面。
        self.header_link = QPushButton("欄位名稱不對？", objectName="linkBtn")
        self.header_link.setToolTip("如果下面的「料號欄位」選單裡是日期、公司抬頭那種東西，\n"
                                    "代表欄位名稱不在第一列，點這裡調整")
        self.header_link.clicked.connect(self._toggle_header_row)
        self.header_link.setVisible(False)
        meta_row.addWidget(self.header_link)
        lay.addLayout(meta_row)
        lay.addSpacing(10)

        self.sheet_box = QComboBox()
        self.sheet_box.setEnabled(False)
        self.sheet_box.currentIndexChanged.connect(self._reload_frame)
        self.sheet_row = self._field_row("工作表", self.sheet_box)
        lay.addWidget(self.sheet_row)
        lay.addSpacing(5)

        # 很多 ERP 匯出的 Excel 上面會有標題／日期列，欄位名稱不在第一列
        self.header_box = QSpinBox()
        self.header_box.setRange(1, MAX_HEADER_ROW)
        self.header_box.setValue(1)
        self.header_box.setToolTip("欄位名稱在第幾列（Excel 的列號）")
        self.header_box.valueChanged.connect(self._reload_frame)
        self.header_row_widget = self._field_row("欄位名稱在第", self.header_box, 78)
        lay.addWidget(self.header_row_widget)
        lay.addSpacing(5)

        self.key_box = QComboBox()
        self.key_box.setEnabled(False)
        self.key_box.currentTextChanged.connect(self._on_key_changed)
        self.key_row = self._field_row("料號欄位", self.key_box)
        lay.addWidget(self.key_row)
        lay.addSpacing(8)

        self.match_lab = QLabel("", objectName="slotMeta")
        self.match_lab.setWordWrap(True)
        lay.addWidget(self.match_lab)
        lay.addStretch()

        self.pick_btn = QPushButton("選擇檔案…")
        self.pick_btn.clicked.connect(lambda: self.pickRequested.emit(self))
        lay.addWidget(self.pick_btn)

        self._show_empty()

    def _field_row(self, caption, widget, label_width=52):
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        lab = QLabel(caption, objectName="slotField")
        lab.setFixedWidth(label_width)
        row.addWidget(lab)
        row.addWidget(widget, 1)
        return host

    # ---------- 狀態 ----------
    @property
    def is_loaded(self):
        return self.df is not None

    @property
    def name(self):
        return os.path.basename(self.path) if self.path else ""

    @property
    def key_column(self):
        return self.key_box.currentText()

    @property
    def header_row(self):
        """UI 顯示 Excel 的列號（從 1 起算），pandas 要的是 0 起算"""
        return self.header_box.value() - 1

    def columns(self):
        return [] if self.df is None else [str(c) for c in self.df.columns]

    def _set_flag(self, prop, value):
        self.setProperty(prop, "true" if value else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    @staticmethod
    def _relabel(widget, obj_name):
        """換 objectName 之後要重新套一次樣式，不然 QSS 不會生效"""
        widget.setObjectName(obj_name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _show_empty(self):
        self.name_lab.setText("把 Excel 拖進來")
        self._relabel(self.name_lab, "slotEmpty")
        self.name_lab.setToolTip("")
        self.meta_lab.setText("或點「選擇檔案」")
        self.match_lab.setText("")
        self.swap_btn.setVisible(False)
        self.clear_btn.setVisible(False)
        self.pick_btn.setVisible(True)
        # 還沒放檔案時，空的工作表／料號欄位只是干擾
        self.sheet_row.setVisible(False)
        self._set_header_visible(False)
        self.header_link.setVisible(False)
        self.key_row.setVisible(False)
        self._set_flag("filled", False)

    def _show_filled(self, rows):
        self.name_lab.setText(self.name)
        self._relabel(self.name_lab, "slotName")
        self.name_lab.setToolTip(self.path or "")
        note = f"{rows:,} 筆資料"
        if rows >= WARN_ROWS:
            note += "　·　資料量偏大，載入會久一點"
        self.meta_lab.setText(note)
        self.swap_btn.setVisible(True)
        self.clear_btn.setVisible(True)
        self.pick_btn.setVisible(False)
        self.sheet_row.setVisible(True)
        self.key_row.setVisible(True)
        # 猜出來不是第一列的話就主動攤開，讓使用者看到程式做了什麼決定；
        # 是第一列（絕大多數）就收起來，不要拿一個沒意義的欄位佔版面
        self.header_link.setVisible(True)
        self._set_header_visible(self.header_row != 0 or self._header_manual)
        self._set_flag("filled", True)

    def set_match(self, text, ok=True):
        self.match_lab.setText(text)
        self._relabel(self.match_lab, "matchOk" if ok else "matchBad")

    # ---------- 載入 ----------
    def load(self, path, restore=None):
        try:
            sheets = local_lookup.list_sheets(path)
        except Exception as e:
            QMessageBox.critical(self, "讀取失敗", f"無法開啟這個檔案：\n{e}")
            return False

        self.path = path
        self._restoring = restore

        self.sheet_box.blockSignals(True)
        self.sheet_box.clear()
        if sheets:
            self.sheet_box.addItems([str(s) for s in sheets])
            self.sheet_box.setEnabled(len(sheets) > 1)
            if restore and restore.get("sheet") in sheets:
                self.sheet_box.setCurrentText(str(restore["sheet"]))
        else:
            self.sheet_box.addItem("—")
            self.sheet_box.setEnabled(False)
        self.sheet_box.blockSignals(False)

        # 上次匯入時設過就沿用，沒有就自己猜 —— 使用者不用管欄位名稱在第幾列
        if restore is not None:
            header = restore.get("header_row", 0)
        else:
            sheet = self.sheet_box.currentText() if self.sheet_box.isEnabled() else None
            header = local_lookup.detect_header_row(path, sheet)
        self.header_box.blockSignals(True)
        self.header_box.setValue(header + 1)
        self.header_box.blockSignals(False)
        self._header_manual = False

        return self._reload_frame()

    def _set_header_visible(self, show):
        """自己記狀態，不要問 isVisible()

        視窗還沒 show 出來的時候，isVisible() 一律是 False（祖先是隱藏的），
        拿它當判斷依據會讓連結文字跟實際狀態對不起來。
        """
        self._header_shown = show
        self.header_row_widget.setVisible(show)
        self.header_link.setText("收起來" if show else "欄位名稱不對？")

    def _toggle_header_row(self):
        self._header_manual = not self._header_shown
        self._set_header_visible(not self._header_shown)

    def _reload_frame(self):
        if not self.path:
            return False
        sheet = self.sheet_box.currentText() if self.sheet_box.isEnabled() else None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # 走快取：這裡讀過一次，之後程式啟動載入同一個檔就不用再解析 Excel
            self.df = local_lookup.read_table_cached(self.path, sheet, self.header_row)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "讀取失敗", str(e))
            return False
        else:
            QApplication.restoreOverrideCursor()

        columns = self.columns()
        if not columns:
            return False

        restore = getattr(self, "_restoring", None)
        if restore and restore.get("key_column") in columns:
            key = restore["key_column"]
        else:
            key = next(
                (c for c in columns if any(h in c.lower() for h in KEY_HINTS)),
                columns[0],
            )
        self._restoring = None

        self.key_box.blockSignals(True)
        self.key_box.clear()
        self.key_box.addItems(columns)
        self.key_box.setCurrentText(key)
        self.key_box.setEnabled(True)
        self.key_box.blockSignals(False)

        self._reindex()
        self._show_filled(len(self.df))
        self.changed.emit()
        return True

    def _reindex(self):
        self.key_index, _, _ = local_lookup.build_indexes(self.df, self.key_column)
        self.decimal = local_lookup.decimal_columns(self.df)

    def _on_key_changed(self, key):
        if self.df is None or not key:
            return
        self._reindex()
        self.changed.emit()

    def clear_source(self):
        self.path = None
        self.df = None
        self.key_index = {}
        self.key_box.blockSignals(True)
        self.key_box.clear()
        self.key_box.setEnabled(False)
        self.key_box.blockSignals(False)
        self.sheet_box.blockSignals(True)
        self.sheet_box.clear()
        self.sheet_box.setEnabled(False)
        self.sheet_box.blockSignals(False)
        self._show_empty()
        self.changed.emit()

    def sample(self, column, n=3):
        if self.df is None or column not in self.columns():
            return ""
        vals = [local_lookup.format_value(v, column in self.decimal)
                for v in self.df[column].head(n)]
        vals = [v for v in vals if v]
        return f"{self.name}\n例：" + "、".join(vals) if vals else self.name

    # ---------- 拖放 ----------
    def dragEnterEvent(self, event):
        if first_url(event):
            event.acceptProposedAction()
            self._set_flag("dragging", True)

    def dragLeaveEvent(self, event):
        self._set_flag("dragging", False)

    def dropEvent(self, event):
        self._set_flag("dragging", False)
        path = first_url(event)
        if path:
            event.acceptProposedAction()
            self.load(path)


class FieldList(QListWidget):
    """可互相拖曳、可排序的欄位清單"""
    changed = Signal()

    def __init__(self, obj_name=None, placeholder=""):
        super().__init__()
        if obj_name:
            self.setObjectName(obj_name)
        self.placeholder = placeholder
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDropIndicatorShown(True)
        self.setUniformItemSizes(True)
        self.setMinimumHeight(150)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.changed.emit()
        source = event.source()
        if isinstance(source, FieldList) and source is not self:
            source.changed.emit()

    def specs(self):
        return [spec_of(self.item(i)) for i in range(self.count())]

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() or not self.placeholder:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(style.TEXT_MUTED))
        painter.drawText(
            self.viewport().rect().adjusted(18, 0, -18, 0),
            Qt.AlignCenter | Qt.TextWordWrap,
            self.placeholder,
        )


class ImportDialog(QDialog):
    def __init__(self, on_done, parent=None):
        super().__init__(parent)
        self.on_done = on_done
        self._restoring = False
        self._user_touched = False
        self._redraw_pending = False

        self.setWindowTitle("匯入 Price Book")
        self.setStyleSheet(style.DIALOG_QSS)
        self.setAcceptDrops(True)
        self._build()

        # 讓 Qt 自己算出「內容不會互相重疊」的最小尺寸，不要用猜的。
        # 要用「檔案都放好」的狀態去量，不然之後載入檔案會被擠到。
        for slot in self.slots:
            slot.sheet_row.setVisible(True)
            slot.header_row_widget.setVisible(True)
            slot.key_row.setVisible(True)
        self.layout().activate()
        need = self.layout().minimumSize()
        for slot in self.slots:
            if not slot.is_loaded:
                slot.sheet_row.setVisible(False)
                slot.header_row_widget.setVisible(False)
                slot.key_row.setVisible(False)
        self.setMinimumSize(max(940, need.width()), need.height())
        self.resize(max(1040, need.width()), max(660, need.height()))

        self._restore_existing()
        self._refresh_all()

    # ---------------- UI ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        root.addWidget(QLabel("匯入 Price Book", objectName="dlgTitle"))
        root.addSpacing(4)
        root.addWidget(QLabel(
            f"最多 {MAX_SOURCES} 個檔案，用彼此共用的料號欄位串成同一張查詢卡",
            objectName="dlgSub"))
        root.addSpacing(16)

        root.addLayout(self._step("1", "放進 Excel 檔案", f"最多 {MAX_SOURCES} 個，可以只放一個"))
        root.addSpacing(8)

        slots_row = QHBoxLayout()
        slots_row.setSpacing(11)
        self.slots = []
        for i in range(MAX_SOURCES):
            slot = SourceSlot(i)
            slot.changed.connect(self._refresh_all)
            slot.pickRequested.connect(self.choose_file)
            slots_row.addWidget(slot, 1)
            self.slots.append(slot)
        root.addLayout(slots_row)
        root.addSpacing(18)

        bottom = QHBoxLayout()
        bottom.setSpacing(18)
        bottom.addWidget(self._config_pane(), 3)
        bottom.addWidget(self._preview_pane(), 2)
        root.addLayout(bottom, 1)
        root.addSpacing(14)

        self.status = QLabel("", objectName="emptyNote")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        root.addSpacing(11)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        btns.addSpacing(8)
        self.save_btn = QPushButton("儲存並套用", objectName="primary")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        btns.addWidget(self.save_btn)
        root.addLayout(btns)

    def _step(self, number, title, hint):
        row = QHBoxLayout()
        row.setSpacing(8)
        badge = QLabel(number, objectName="stepNum")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(19, 19)
        row.addWidget(badge)
        row.addWidget(QLabel(title, objectName="sectionLabel"))
        row.addWidget(QLabel(hint, objectName="listHint"))
        row.addStretch()
        return row

    def _config_pane(self):
        pane = QWidget()
        col = QVBoxLayout(pane)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        col.addLayout(self._step("2", "挑要顯示哪些欄位", "把想看的拖到右邊"))
        col.addSpacing(3)
        col.addWidget(QLabel(
            "欄位前面的 ① ② ③ 代表它來自哪個檔案　·　右邊由上往下就是顯示順序",
            objectName="listHint"))
        col.addSpacing(9)

        lists = QHBoxLayout()
        lists.setSpacing(11)

        left = QVBoxLayout()
        left.setSpacing(5)
        head_l = QHBoxLayout()
        head_l.setSpacing(7)
        head_l.addWidget(QLabel("不顯示", objectName="listCaption"))
        self.available_hint = QLabel("查詢時看不到這些", objectName="listHint")
        head_l.addWidget(self.available_hint)
        head_l.addStretch()
        left.addLayout(head_l)

        # 欄位動輒幾十個，用捲的找很久 —— 打字直接篩
        self.field_filter = QLineEdit(objectName="fieldFilter")
        self.field_filter.setPlaceholderText("搜尋欄位…")
        self.field_filter.setClearButtonEnabled(True)
        self.field_filter.textChanged.connect(self._apply_field_filter)
        left.addWidget(self.field_filter)

        self.available = FieldList(placeholder="檔案裡的欄位\n全都拉到右邊了")
        self.available.itemDoubleClicked.connect(
            lambda i: self._move(self.available, self.selected))
        self.available.changed.connect(self._after_field_change)
        left.addWidget(self.available)
        lists.addLayout(left, 1)

        mid = QVBoxLayout()
        mid.addStretch()
        add = QPushButton("→", objectName="moveBtn")
        add.setToolTip("改成查詢時要顯示")
        add.clicked.connect(lambda: self._move(self.available, self.selected))
        mid.addWidget(add)
        mid.addSpacing(6)
        remove = QPushButton("←", objectName="moveBtn")
        remove.setToolTip("改成查詢時不顯示")
        remove.clicked.connect(lambda: self._move(self.selected, self.available))
        mid.addWidget(remove)
        mid.addStretch()
        lists.addLayout(mid)

        right = QVBoxLayout()
        right.setSpacing(5)
        head = QHBoxLayout()
        head.setSpacing(7)
        head.addWidget(QLabel("要顯示", objectName="listCaptionKey"))
        head.addWidget(QLabel("查詢時看得到，最上面那個會放大", objectName="listHint"))
        head.addStretch()
        right.addLayout(head)
        self.selected = FieldList("selectedList", placeholder="把左邊的欄位拖過來\n這裡放的就是查詢時會看到的")
        self.selected.itemDoubleClicked.connect(
            lambda i: self._move(self.selected, self.available))
        self.selected.changed.connect(self._after_field_change)
        right.addWidget(self.selected)
        lists.addLayout(right, 1)

        col.addLayout(lists, 1)
        return pane

    def _preview_pane(self):
        pane = QWidget()
        col = QVBoxLayout(pane)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        col.addLayout(self._step("3", "確認查詢畫面", "拖欄位時會即時跟著變"))
        col.addSpacing(3)
        self.preview_key = QLabel(f"按 {hotkey.HOTKEY_LABEL} 查詢時，實際會看到的畫面", objectName="listHint")
        col.addWidget(self.preview_key)
        col.addSpacing(9)

        scroll = QScrollArea(objectName="previewPane")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget(objectName="previewInner")
        wrap = QVBoxLayout(inner)
        wrap.setContentsMargins(16, 16, 16, 16)
        wrap.setSpacing(0)

        self.preview_card = QFrame(objectName="card")
        self.preview_card.setStyleSheet(style.POPUP_QSS)
        self.preview_body = QVBoxLayout(self.preview_card)
        self.preview_body.setContentsMargins(20, 18, 20, 18)
        self.preview_body.setSpacing(0)
        wrap.addWidget(self.preview_card)
        wrap.addStretch()

        scroll.setWidget(inner)
        col.addWidget(scroll, 1)
        return pane

    # ---------------- 檔案 ----------------
    def _restore_existing(self):
        config = book_config.load()
        if not config:
            return
        self._restoring = True
        by_id = {}
        for source in config.get("sources", []):
            path = source.get("source_path")
            if not path or not os.path.exists(path):
                path = source.get("path")
            if not path or not os.path.exists(path):
                continue
            index = sid_index(source.get("id"))
            if 0 <= index < MAX_SOURCES and self.slots[index].load(path, restore=source):
                by_id[source["id"]] = self.slots[index]
        self._restoring = False

        if not by_id:
            return

        wanted = [(d["source"], d["column"]) for d in config.get("display_columns", [])]
        valid = self._valid_specs()
        chosen = [s for s in wanted if s in valid]
        rest = [s for s in valid if s not in chosen]
        self._fill_list(self.selected, chosen)
        self._fill_list(self.available, rest)

    def choose_file(self, slot):
        path, _ = QFileDialog.getOpenFileName(
            self, f"選擇檔案{slot.idx + 1}", os.path.expanduser("~"),
            "Excel / CSV (*.xlsx *.xlsm *.xls *.csv);;所有檔案 (*)",
        )
        if path:
            slot.load(path)

    def dragEnterEvent(self, event):
        if first_url(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = first_url(event)
        if not path:
            return
        target = next((s for s in self.slots if not s.is_loaded), None)
        if target is None:
            return QMessageBox.information(
                self, "位置滿了",
                f"最多同時放 {MAX_SOURCES} 個檔案。\n先按某張卡片右上角的 ✕ 或「更換」再試一次。")
        event.acceptProposedAction()
        target.load(path)

    # ---------------- 欄位 ----------------
    def _valid_specs(self):
        """目前所有可挑選的欄位（料號欄位本身不列入，它會當成標題）"""
        out = []
        for slot in self.slots:
            if not slot.is_loaded:
                continue
            key = slot.key_column
            out.extend((slot.sid, c) for c in slot.columns() if c != key)
        return out

    def _fill_list(self, widget, specs):
        widget.clear()
        for sid, column in specs:
            slot = self._slot(sid)
            widget.addItem(make_item(sid, column, slot.sample(column) if slot else ""))

    def _slot(self, sid):
        return next((s for s in self.slots if s.sid == sid), None)

    def _sync_fields(self):
        """來源變動後只增減受影響的欄位，使用者排好的順序完全保留"""
        valid = self._valid_specs()
        valid_set = set(valid)

        # 同一個欄位只能出現在一邊；顯示欄位優先留著
        keep = set()
        for widget in (self.selected, self.available):
            for i in range(widget.count() - 1, -1, -1):
                spec = spec_of(widget.item(i))
                if spec not in valid_set or (widget is self.available and spec in keep):
                    widget.takeItem(i)
            keep |= set(widget.specs())

        present = set(self.available.specs()) | set(self.selected.specs())
        added = [s for s in valid if s not in present]
        for sid, column in added:
            slot = self._slot(sid)
            self.available.addItem(make_item(sid, column, slot.sample(column) if slot else ""))

        # 顯示欄位是空的就給個起手式，不然預覽沒東西看；
        # 但使用者自己動手清空過就不再插手
        if added and not self._user_touched and self.selected.count() == 0:
            for spec in self._seed_picks():
                row = self.available.specs().index(spec)
                self.selected.addItem(self.available.takeItem(row))

        # 清單重建過，篩選條件要重新套一次，不然剛換檔案就整片跑出來
        self._apply_field_filter()

    def _seed_picks(self):
        """挑幾個當起手式：先挑價格庫存交期這類，不夠再照順序補"""
        specs = self.available.specs()
        picked = [s for s in specs if any(h in s[1].lower() for h in SEED_HINTS)]
        for spec in specs:
            if len(picked) >= SEED_FIELDS:
                break
            if spec not in picked:
                picked.append(spec)
        return picked[:SEED_FIELDS]

    def _apply_field_filter(self, *_):
        """打字篩「不顯示」那一欄

        只是把不符合的列 setHidden，不動資料 —— 篩選中照樣可以拖、可以按 →，
        清空搜尋框全部就回來了。已經拉到右邊的欄位不篩，那邊本來就沒幾個。
        """
        query = self.field_filter.text().strip().lower()
        shown = 0
        for i in range(self.available.count()):
            item = self.available.item(i)
            _, column = spec_of(item)
            hit = not query or query in column.lower()
            item.setHidden(not hit)
            shown += hit
        total = self.available.count()
        if query:
            self.available_hint.setText(f"符合 {shown} / {total} 個欄位")
        else:
            self.available_hint.setText("查詢時看不到這些")

    def _move(self, src, dst):
        # 被篩掉（看不見）的項目不該被搬走，使用者根本看不到它被選著
        for item in src.selectedItems():
            if item.isHidden():
                continue
            dst.addItem(src.takeItem(src.row(item)))
        self._apply_field_filter()
        self._after_field_change()

    def _after_field_change(self):
        """欄位有動就重畫預覽

        拖曳時 Qt 是「先送 drop 事件、之後才把項目從來源清單移掉」，
        當場重畫會讀到還沒移除的舊狀態，所以排到下一輪事件迴圈再畫。
        """
        self._user_touched = True
        if self._redraw_pending:
            return
        self._redraw_pending = True
        QTimer.singleShot(0, self._redraw_fields)

    def _redraw_fields(self):
        self._redraw_pending = False
        self._apply_field_filter()      # 拖進來的新項目也要照篩選條件走
        self._update_preview()
        self._sync_state()

    def keyPressEvent(self, event):
        """搜尋欄位時按 esc 是清掉搜尋，不是關掉整個匯入視窗"""
        if (event.key() == Qt.Key_Escape
                and self.field_filter.hasFocus() and self.field_filter.text()):
            self.field_filter.clear()
            return
        super().keyPressEvent(event)

    # ---------------- 比對狀況 ----------------
    def _refresh_all(self):
        if self._restoring:
            return
        self._sync_fields()
        self._refresh_matches()
        self._update_preview()
        self._sync_state()

    def _refresh_matches(self):
        loaded = [s for s in self.slots if s.is_loaded]
        for slot in self.slots:
            if not slot.is_loaded:
                slot.set_match("")
                continue
            base = loaded[0]
            if slot is base:
                slot.set_match(f"{len(slot.key_index):,} 個料號　·　比對基準", ok=True)
            elif not slot.key_index:
                slot.set_match("這一欄讀不到料號", ok=False)
            else:
                hit = len(set(slot.key_index) & set(base.key_index))
                if hit:
                    slot.set_match(f"與 {base.mark} 對到 {hit:,} 個料號", ok=True)
                else:
                    slot.set_match(f"與 {base.mark} 對不到料號，換一個料號欄位試試", ok=False)

    # ---------------- 預覽 ----------------
    def _sample_key(self):
        """挑一個能示範的料號 —— 越多檔案都有的越好，同分取第一個檔案的第一筆"""
        loaded = [s for s in self.slots if s.is_loaded and s.key_index]
        if not loaded:
            return None, None
        order = list(loaded[0].key_index.keys())
        best = max(order, key=lambda k: sum(1 for s in loaded if k in s.key_index))
        base = loaded[0]
        raw = str(base.df.iloc[base.key_index[best]][base.key_column]).strip()
        return best, raw

    def _update_preview(self):
        result_view.clear(self.preview_body)
        self.preview_key.setText(f"按 {hotkey.HOTKEY_LABEL} 查詢時，實際會看到的畫面")

        loaded = [s for s in self.slots if s.is_loaded]
        if not loaded:
            self.preview_body.addWidget(
                result_view.label("放進檔案後，這裡會顯示查詢結果長什麼樣子", "hint"))
            return

        specs = self.selected.specs()
        if not specs:
            self.preview_body.addWidget(
                result_view.label("把欄位拖到「要顯示」那一欄，這裡就會即時跟著變", "hint"))
            return

        key, raw = self._sample_key()
        if key is None:
            self.preview_body.addWidget(result_view.label("這個檔案讀不到料號", "hint"))
            return

        names = {s.sid: s.name for s in loaded}
        labels = local_lookup.field_labels(
            [{"source": sid, "column": col} for sid, col in specs], names)

        fields = []
        for sid, column, text in labels:
            slot = self._slot(sid)
            pos = slot.key_index.get(key) if slot else None
            if slot is None or pos is None:
                fields.append((text, ""))
            else:
                value = slot.df.iloc[pos][column]
                fields.append((text, local_lookup.format_value(value, column in slot.decimal)))

        missing = [s.name for s in loaded if key not in s.key_index]
        self.preview_key.setText(f"拿「{raw}」當範例，按 {hotkey.HOTKEY_LABEL} 查詢時就長這樣")
        result_view.fill(
            self.preview_body,
            {"_key": raw, "_fields": fields, "_missing": missing},
            label_width=84,
        )

    # ---------------- 狀態與儲存 ----------------
    def _sync_state(self):
        loaded = [s for s in self.slots if s.is_loaded]
        count = self.selected.count()
        self.save_btn.setEnabled(bool(loaded) and count > 0)

        if not loaded:
            self.status.setText("先放至少一個檔案進來")
        elif count == 0:
            self.status.setText("還沒選要顯示什麼 —— 把欄位拖到右邊的「要顯示」")
        else:
            keys = "、".join(f"{s.mark} {s.key_column}" for s in loaded)
            self.status.setText(f"料號欄位：{keys}　·　查詢時會顯示 {count} 個欄位")

    def save(self):
        loaded = [s for s in self.slots if s.is_loaded]
        specs = self.selected.specs()
        if not loaded or not specs:
            return QMessageBox.warning(self, "尚未設定", "請確認檔案放好了，而且右邊「要顯示」至少有一個欄位")

        sources = [{
            "id": s.sid,
            "name": s.name,
            "src_path": s.path,
            "sheet": s.sheet_box.currentText() if s.sheet_box.isEnabled() else None,
            "header_row": s.header_row,
            "key_column": s.key_column,
        } for s in loaded]
        display = [{"source": sid, "column": col} for sid, col in specs]

        local_lookup.import_sources(sources, display)
        self.on_done()

        names = {s.sid: s.name for s in loaded}
        shown = "、".join(text for _, _, text in local_lookup.field_labels(display, names))
        lines = [f"{s.mark} {s.name}　{len(s.df):,} 筆（料號欄位：{s.key_column}）" for s in loaded]
        message = "\n".join(lines) + f"\n\n查詢時會顯示：{shown}"

        dupes = [s for s in loaded if len(s.key_index) < len(s.df)]
        if dupes:
            detail = "、".join(f"{s.mark} {len(s.df) - len(s.key_index):,} 筆" for s in dupes)
            message += f"\n\n注意：有重複料號（{detail}），查詢時只會顯示最後一筆。"

        QMessageBox.information(self, "匯入完成", message)
        self.accept()
