from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
    QVBoxLayout, QWidget,
)

from core import local_lookup, settings
from ui import native_window, result_view, style

_W = settings.section("window")

WIDTH = _W["width"]
PAD_X = _W["padding_x"]
PAD_TOP = _W["padding_top"]
PAD_BOTTOM = _W["padding_bottom"]
ANCHOR = _W["anchor"]
EDGE_X = _W["edge_x"]
EDGE_Y = _W["edge_y"]
DIVIDER_GAP_TOP = _W["divider_gap_top"]
DIVIDER_GAP_BOTTOM = _W["divider_gap_bottom"]
PREFILL_MAX = _W["prefill_max_chars"]
# 設定要求原生陰影、而且這個平台真的有（Windows 的無邊框視窗沒有）
NATIVE_SHADOW = (_W.get("shadow", "native") == "native"
                 and native_window.HAS_NATIVE_SHADOW)

LIST_ROWS = max(1, min(_W["list_rows"], settings.get("data.result_limit", 6)))
LIST_FIELDS = max(0, _W["list_fields"])
LIST_ROW_GAP = _W["list_row_gap"]
LIST_SEP = _W["list_sep"]
DEBOUNCE_MS = max(0, _W["search_debounce_ms"])

MODE_MESSAGE = "message"     # 提示、查無、載入中
MODE_LIST = "list"           # 邊打邊找的結果清單
MODE_DETAIL = "detail"       # 點進去看某一筆的完整資料


def summary_text(result):
    """清單右邊那行摘要 —— 取前幾個欄位的值，讓人不用點進去就看得到重點"""
    values = [v for _, v in (result.get("_fields") or []) if v]
    return LIST_SEP.join(values[:LIST_FIELDS])


class ResultRow(QFrame):
    """清單裡的一列：左邊料號、右邊摘要

    選取狀態用 QSS 屬性切換（sel="true"）再 polish 一次，
    不要用 setStyleSheet —— 那會讓 Qt 重新解析整份樣式，上下鍵就會頓。
    """

    def __init__(self, on_click, on_hover):
        super().__init__(objectName="listRow")
        self._on_click = on_click
        self._on_hover = on_hover
        self.setProperty("sel", "false")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

        pad = style.LIST_ROW_PADDING
        row = QHBoxLayout(self)
        row.setContentsMargins(9, pad, 9, pad)
        row.setSpacing(12)
        self.key = result_view.ElidingLabel("", "listKey")
        self.value = QLabel("", objectName="listValue")
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # 摘要不讓它被壓縮，優先犧牲左邊的料號（料號本來就會中間省略）
        self.value.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        row.addWidget(self.key, 1)
        row.addWidget(self.value, 0)

    def set_data(self, key, value):
        self.key.set_full(key)
        self.value.setText(value)

    def set_selected(self, on):
        self.setProperty("sel", "true" if on else "false")
        self._repolish()

    def _repolish(self):
        for w in (self, self.key, self.value):
            w.style().unpolish(w)
            w.style().polish(w)

    def enterEvent(self, event):
        self._on_hover(self)
        super().enterEvent(event)

    def mousePressEvent(self, event):
        self._on_click(self)
        super().mousePressEvent(event)


class PopupWindow(QWidget):
    """熱鍵查詢視窗

    行為：打字就直接找（不用按 return），下面列出最相近的幾筆，
    按 return 或點一下才進到單筆的完整資料，esc 從詳細回清單、再一次關掉視窗。

    速度上的三個關鍵，改動前請先看這裡：

    1. 陰影用 macOS 原生的（NSWindow 依 alpha 自己畫，GPU 完成）。
       絕對不要改回 QGraphicsDropShadowEffect —— 實測每次重繪從 1.1ms
       變成 23.3ms，打字就會頓。
    2. 視窗在程式啟動時就用 prewarm() 建好、字體與 QSS 都套過一次。
       不預熱的話第一次按熱鍵要多花 200ms 以上。
    3. 清單那幾列是固定數量的常駐 widget（開機就建好），每次搜尋只換文字、
       用不到的就 hide()。每按一鍵重建 widget 的話 6 列要多花 3~4ms，
       打字會有黏滯感。
    """

    def __init__(self, on_search, on_status, on_open=None):
        super().__init__()
        self.on_search = on_search
        self.on_status = on_status
        self.on_open = on_open           # 進到詳細畫面時通知外面（目前只給測試用）
        self._results = []
        self._sel = 0
        self._mode = MODE_MESSAGE
        self._warm = False

        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        if not NATIVE_SHADOW:
            flags |= Qt.NoDropShadowWindowHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(style.POPUP_QSS)
        self.setFixedWidth(WIDTH)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame(objectName="card")
        self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        shell.addWidget(self.card)

        box = QVBoxLayout(self.card)
        box.setContentsMargins(PAD_X, PAD_TOP, PAD_X, PAD_BOTTOM)
        box.setSpacing(0)

        self.search = QLineEdit(objectName="search")
        self.search.setPlaceholderText("輸入料號，邊打邊找")
        self.search.returnPressed.connect(self._enter_detail)
        self.search.textEdited.connect(self._on_text_edited)
        self.search.installEventFilter(self)
        box.addWidget(self.search)

        divider = QFrame(objectName="divider")
        box.addSpacing(DIVIDER_GAP_TOP)
        box.addWidget(divider)
        box.addSpacing(DIVIDER_GAP_BOTTOM)

        # 訊息／詳細資料放這裡，每次重畫
        self.body = QVBoxLayout()
        self.body.setSpacing(0)
        box.addLayout(self.body)

        # 清單是固定 LIST_ROWS 個常駐 widget，只換文字不重建
        self.list_box = QVBoxLayout()
        self.list_box.setContentsMargins(0, 0, 0, 0)
        self.list_box.setSpacing(LIST_ROW_GAP)
        self.rows = []
        for _ in range(LIST_ROWS):
            row = ResultRow(self._row_clicked, self._row_hovered)
            row.hide()
            self.list_box.addWidget(row)
            self.rows.append(row)
        box.addLayout(self.list_box)

        self.foot = QLabel("", objectName="hint")
        self.foot.setContentsMargins(0, 12, 0, 0)
        self.foot.hide()
        box.addWidget(self.foot)

        # 0ms 的 timer 不是延遲，是把同一輪事件迴圈裡的連續按鍵併成一次搜尋
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._run_search)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

    # ---------- 預熱 ----------
    def prewarm(self):
        """啟動時就把貴的事情做完：建原生視窗、套 QSS、解析字體、跑一次排版

        做完之後按熱鍵只剩下 move + show，感覺才會是「瞬間出現」。
        """
        if self._warm:
            return
        self.ensurePolished()
        self.winId()                       # 逼 Qt 現在就建立 NSWindow
        native_window.make_overlay(self)      # 只做這一次
        self.setWindowOpacity(0.0)
        self.move(-30000, -30000)          # 在螢幕外，使用者看不到
        self._warm_styles()                # grab() 對隱藏的視窗也有效

        # 一定要讓事件迴圈真的跑過：macOS 把視窗實體化、合成第一個畫面、
        # 輸入框第一次取得焦點時初始化輸入法(TSM)，加起來將近 300ms。
        # 而且要跑兩輪 —— 實際使用是「顯示→隱藏→再顯示」，
        # 只暖第一次顯示的話，第一次真的按熱鍵還是會多花約 100ms。
        for _ in range(2):
            self.show()
            QApplication.processEvents()
            self.search.setFocus()
            QApplication.processEvents()
            self.hide()
            QApplication.processEvents()

        self.setWindowOpacity(1.0)
        self._warm = True

    def _warm_styles(self):
        """三種畫面都先畫一次，讓 Qt 把每條 QSS 規則都比對過

        只預熱空白畫面不夠：第一次真的查到結果時，#listRow / #partNumber /
        #heroValue 這些規則才第一次套用，實測會多花 130ms —— 剛好就是
        使用者「第一次按覺得慢」的那一下。
        """
        fake = {
            "_key": "WARMUP-0000",
            "_fields": [("欄位", "0"), ("欄位", "0")],
            "_missing": ["warm"],
            "_typed": None,
        }
        self.show_results([fake] * LIST_ROWS)
        self.grab()          # 真的畫一次，字體與樣式才會在此刻解析完
        self._enter_detail()
        self.grab()
        self.show_message("查無「WARMUP」", "errorTitle", "本地 Price Book 沒有這筆料號")
        self.grab()
        self.show_placeholder()
        self.grab()

    # ---------- 畫面 ----------
    def _clear_body(self):
        result_view.clear(self.body)

    def _hide_rows(self):
        for row in self.rows:
            row.hide()

    def show_message(self, title, obj, hint=None):
        self._mode = MODE_MESSAGE
        self._results = []
        self._clear_body()
        self._hide_rows()
        self.foot.hide()
        self.body.addWidget(result_view.label(title, obj))
        if hint:
            self.body.addSpacing(6)
            self.body.addWidget(result_view.label(hint, "hint"))
        self._fit()

    def show_placeholder(self):
        status, message = self.on_status()
        if status == local_lookup.STATUS_LOADING:
            return self.show_message("資料載入中…", "hint")
        if status == local_lookup.STATUS_ERROR:
            return self.show_message("Price Book 載入失敗", "errorTitle",
                                     message or "請重新匯入")
        if status == local_lookup.STATUS_EMPTY:
            return self.show_message("尚未匯入 Price Book", "errorTitle",
                                     "點選單列圖示 → 匯入 Price Book")
        return self.show_message("打字就直接找　·　↑↓ 選　·　return 看完整資料", "hint")

    def show_results(self, results):
        """清單畫面 —— 打字之後看到的就是這個"""
        self._mode = MODE_LIST
        self._results = results[:LIST_ROWS]
        self._sel = 0
        self._clear_body()
        for i, row in enumerate(self.rows):
            if i < len(self._results):
                data = self._results[i]
                row.set_data(data["_key"], summary_text(data))
                row.set_selected(i == 0)
                row.show()
            else:
                row.hide()
        self.foot.setText("↑↓ 選　·　return 看完整資料　·　esc 關閉")
        self.foot.show()
        self._fit()

    def show_detail(self, index):
        """單筆完整資料 —— 從清單按 return 或點一下才會進來"""
        if not self._results:
            return
        self._sel = index % len(self._results)
        self._mode = MODE_DETAIL
        self._hide_rows()
        self._clear_body()
        result_view.fill(self.body, self._results[self._sel],
                         content_width=WIDTH - 2 * PAD_X)
        total = len(self._results)
        if total > 1:
            self.foot.setText(f"第 {self._sel + 1} / {total} 筆　·　"
                              f"↑↓ 換一筆　·　esc 回清單")
        else:
            self.foot.setText("esc 回清單")
        self.foot.show()
        self._fit()
        if self.on_open:
            self.on_open(self._results[self._sel])

    def _fit(self):
        self.layout().invalidate()
        self.adjustSize()
        if NATIVE_SHADOW and self._warm:
            native_window.refresh_shadow(self)

    # ---------- 搜尋 ----------
    def _on_text_edited(self, _text):
        self._timer.start(DEBOUNCE_MS)

    def _run_search(self):
        text = self.search.text().strip()
        if not text:
            return self.show_placeholder()

        status, message = self.on_status()
        if status != local_lookup.STATUS_READY:
            return self.show_placeholder()

        try:
            results = self.on_search(text, LIST_ROWS) or []
        except Exception as e:
            return self.show_message("查詢時出錯", "errorTitle", str(e))

        if not results:
            return self.show_message(f"查無「{text}」", "errorTitle",
                                     "本地 Price Book 沒有相近的料號")
        self.show_results(results)

    # ---------- 操作 ----------
    def _select(self, index):
        if not self._results:
            return False
        index %= len(self._results)
        if index == self._sel and self._mode == MODE_LIST:
            return True
        if self._mode == MODE_LIST:
            self.rows[self._sel].set_selected(False)
            self.rows[index].set_selected(True)
            self._sel = index
        else:
            self.show_detail(index)     # 詳細畫面上下鍵直接換下一筆，不用退回清單
        return True

    def _enter_detail(self):
        if self._mode == MODE_LIST and self._results:
            self.show_detail(self._sel)

    def _back(self):
        """從詳細退回清單；已經在清單就關掉視窗"""
        if self._mode == MODE_DETAIL and self._results:
            keep = self._sel
            self.show_results(self._results)
            self._select(keep)
            return True
        return False

    def _row_clicked(self, row):
        self.show_detail(self.rows.index(row))

    def _row_hovered(self, row):
        index = self.rows.index(row)
        if self._mode == MODE_LIST and index < len(self._results):
            self._select(index)

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Down and self._select(self._sel + 1):
                return True
            if key == Qt.Key_Up and self._select(self._sel - 1):
                return True
            if key == Qt.Key_Escape and self._back():
                return True
        return super().eventFilter(obj, event)

    # ---------- 位置與顯示 ----------
    def _current_screen(self):
        """用滑鼠位置判斷使用者現在在看哪一個螢幕"""
        app = QGuiApplication.instance()
        pos = QCursor.pos()
        for screen in app.screens():
            if screen.geometry().contains(pos):
                return screen
        return app.primaryScreen()

    def _reposition(self):
        screen = self._current_screen()
        if not screen:
            return
        geo = screen.availableGeometry()
        if ANCHOR == "top-left":
            x = geo.left() + EDGE_X
        elif ANCHOR in ("top-center", "center"):
            x = geo.center().x() - self.width() // 2
        else:                                     # top-right（預設）
            x = geo.right() - self.width() - EDGE_X
        y = geo.center().y() - self.height() // 2 if ANCHOR == "center" else geo.top() + EDGE_Y
        self.move(x, y)

    def show_query(self, prefill=""):
        self.search.setText(prefill)
        if prefill:
            self._run_search()          # 貼進來的料號直接就有清單，不用再按一次
        else:
            self.show_placeholder()

        # 位置一定要在 show 之前算好，show 之後再 move 會看到視窗跳一下
        self._fit()
        self._reposition()

        self.show()
        self.raise_()
        if not native_window.focus_without_switching(self):
            native_window.activate_app()
            self.activateWindow()
        self.search.setFocus()
        self.search.selectAll()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if not self._back():
                self.hide()
        else:
            super().keyPressEvent(event)

    def event(self, event):
        if event.type() == QEvent.WindowDeactivate:
            self.hide()
        return super().event(event)


def clipboard_prefill(text):
    """剪貼簿內容適不適合當預填 —— 太長或有換行就當作不是料號"""
    text = (text or "").strip()
    if not text or "\n" in text or len(text) > PREFILL_MAX:
        return ""
    return text
