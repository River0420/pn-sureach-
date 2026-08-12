"""設定快捷鍵

這個視窗要回答使用者心裡唯一的問題：**「這組到底能不能用？」**

而那個問題在兩個系統上答案的來源不一樣：

- Windows 有 RegisterHotKey，撞到別的程式會直接失敗，**選的當下就知道**。
- macOS 沒有「註冊」這回事 —— 我們是監聽全部鍵盤事件，任何組合都掛得上，
  系統不會、也無法告訴我們「這組被 Alfred 用走了」。

所以不能只靠查詢。這裡的做法是**當場掛上去、請使用者真的按一次**：
按了有反應才點亮「用這組」。這比查表可靠 —— 查表只知道系統沒登記，
按下去有反應才是真的能用。

錄鍵本身不需要任何權限：視窗有焦點，直接接 Qt 的按鍵事件就好。
需要權限的只有最後那一步「試按看看」，因為那才用到全域監聽。
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from core import hotkey, plat
from ui import style

# Qt 在 macOS 上預設把 Control 和 Command 對調（讓跨平台程式的 ⌘C 自動變 Ctrl+C）。
# 錄熱鍵要的是使用者實際按了哪顆，所以這裡要把它換回來。
if plat.MACOS:
    _QT_MODS = ((Qt.ControlModifier, "cmd"), (Qt.AltModifier, "alt"),
                (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "ctrl"))
else:
    _QT_MODS = ((Qt.ControlModifier, "ctrl"), (Qt.AltModifier, "alt"),
                (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "cmd"))

# 按下去只有修飾鍵、還沒到「主鍵」的那些
_BARE = {Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta,
         Qt.Key_CapsLock, Qt.Key_AltGr}

# 修飾鍵自己被按下時，是哪一顆。同樣要考慮 macOS 的 Control/Command 對調。
#
# 為什麼需要這張表：Qt 的 event.modifiers() 給的是「這一下按之前」的狀態。
# 按下 Shift 的那個事件裡 modifiers() 是空的，按下 Alt 的事件裡只有 Shift。
# 直接拿來顯示的話畫面會慢一拍 —— 使用者按住 ⌥⇧ 只看到 ⌥，看起來像壞掉。
# 所以按下時要把自己這一顆補進去，放開時要把自己這一顆拿掉。
_KEY_AS_MOD = {
    Qt.Key_Shift: "shift", Qt.Key_Alt: "alt",
    Qt.Key_Control: "cmd" if plat.MACOS else "ctrl",
    Qt.Key_Meta: "ctrl" if plat.MACOS else "cmd",
}

# 現成選項。第一個是出貨預設 —— 三顆鍵是為了 Windows：
# Alt+Space 在那邊是系統的視窗選單。
PRESETS = [
    (["shift", "alt"], "space", "預設"),
    (["alt"], "space", "兩顆鍵" if plat.MACOS else ""),
    (["ctrl", "shift"], "space", ""),
    (["shift", "alt"], "q", ""),
]

# 已知會撞到系統的組合，錄到就先講一聲。抓不完，但這幾個最常見。
_KNOWN_BAD = {
    ("cmd", "space"): "這是 Spotlight 的快捷鍵",
    ("ctrl", "space"): "這是切換輸入法的快捷鍵",
    ("cmd", "tab"): "這是切換 App 的快捷鍵",
} if plat.MACOS else {
    ("alt", "space"): "這是 Windows 的視窗選單快捷鍵",
    ("alt", "tab"): "這是切換視窗的快捷鍵",
    ("cmd", "space"): "這是切換輸入法的快捷鍵",
}


SAVE_LABEL = "儲存熱鍵"

# 「試按看看」做過沒有，交給狀態列那一行講（「按試按看看確認」／「已經確認可以用 ✓」）。
# 按鈕本身不隨狀態改字 —— 同一顆按鈕做同一件事，字卻一直變，只會讓人遲疑。


def _spell(key, mods):
    """把一組熱鍵拼成看得懂的字

    macOS 拿 plat.spell()（「option + shift + 空白鍵」）。
    Windows 的 Alt+Shift+Space 已經是英文單字了，只有 Space 值得翻，
    免得跟上面那行大字一模一樣。
    """
    mods = plat.mod_names(mods)
    spelled = plat.spell(key, mods)
    if spelled:
        return spelled
    words = [plat.MOD_LABELS[m] for m in mods]
    words.append(plat.SPELLED_KEYS.get(key, key.upper()))
    return " + ".join(words)


def _known_bad(mods, key):
    """只看單一修飾鍵的組合 —— 加了第二顆修飾鍵就不再撞到那些系統快捷鍵"""
    return _KNOWN_BAD.get((mods[0], key)) if len(mods) == 1 else None


class Recorder(QLabel):
    """按什麼就顯示什麼的大方框"""
    recorded = Signal(list, str)          # (修飾鍵清單, 按鍵名稱)
    partial = Signal(list)                # 只按著修飾鍵，還沒按主鍵

    def __init__(self):
        super().__init__(objectName="recorder")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(76)
        self.setFocusPolicy(Qt.StrongFocus)
        self.armed = False                # 測試中就不要再吃按鍵

    def _mods(self, event):
        state = event.modifiers()
        return [name for flag, name in _QT_MODS if state & flag]

    def keyPressEvent(self, event):
        if not self.armed:
            return super().keyPressEvent(event)
        mods = self._mods(event)
        if event.key() in _BARE:
            own = _KEY_AS_MOD.get(event.key())      # 自己這一顆還沒算進去
            if own and own not in mods:
                mods.append(own)
            self.partial.emit(mods)
            return
        # 原生鍵碼不受鍵盤配置和 option 死鍵影響，優先用它
        name = plat.key_from_native(event.nativeVirtualKey())
        if not name:
            text = event.text().strip().lower()
            name = text if text in plat.KEYS else None
        if not name:
            self.partial.emit(mods)       # 不支援的鍵：當作還沒按完
            return
        self.recorded.emit(mods, name)

    def keyReleaseEvent(self, event):
        if self.armed and event.key() in _BARE:
            mods = self._mods(event)
            own = _KEY_AS_MOD.get(event.key())      # 放開了，但狀態裡還在
            if own in mods:
                mods.remove(own)
            self.partial.emit(mods)
        else:
            super().keyReleaseEvent(event)


class HotkeyDialog(QDialog):
    """回傳值：accept() 代表使用者按了「用這組」，結果在 self.chosen"""

    # 熱鍵被按到時，是在監聽執行緒上收到的，不能從那裡碰畫面。
    # 一定要用 signal 送回主執行緒 —— 這個 QDialog 建在主執行緒上，
    # 跨執行緒 emit 會自動走佇列連線，安全地在主執行緒執行。
    #
    # 這裡原本寫 QTimer.singleShot(0, ...)，那是錯的：singleShot 會把
    # 計時器建在「呼叫它的那條執行緒」上，而監聽執行緒沒有 Qt 事件迴圈，
    # 所以那個 callback 永遠不會跑 —— 熱鍵明明收到了，畫面卻一直在等，
    # 10 秒後報「沒收到」。
    hit = Signal()

    def __init__(self, on_pause=None, on_resume=None, parent=None):
        super().__init__(parent)
        self.hit.connect(self._hit_on_main)
        # 試按之前一定要把主程式的監聽關掉。不關的話在 Windows 上拿
        # 同一組去試會撞到自己，回報「已經被其他程式註冊走了」。
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.chosen = None
        self._probe = None
        self._verified = set()            # 已經按過、確認有反應的組合

        self.mods = list(hotkey.MODIFIERS)
        self.key = hotkey.KEY

        self.setWindowTitle("設定快捷鍵")
        self.setStyleSheet(style.DIALOG_QSS)
        self.setFixedWidth(460)
        self._build()
        self._show_current()

    # ---------------- 版面 ----------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        root.addWidget(QLabel("設定快捷鍵", objectName="dlgTitle"))
        root.addSpacing(4)
        root.addWidget(QLabel("在任何軟體裡按這一組，就會叫出查詢視窗。",
                              objectName="dlgSub"))
        root.addSpacing(16)

        self.recorder = Recorder()
        self.recorder.recorded.connect(self._on_recorded)
        self.recorder.partial.connect(self._on_partial)
        root.addWidget(self.recorder)
        root.addSpacing(5)

        # ⌃ ⌥ ⇧ 這些符號不是每個人都認得。大方框裡放符號（短、好看），
        # 底下永遠跟一行拼出來的字 —— 沒有這一行，使用者根本不知道自己選了什麼。
        self.spelled = QLabel("", objectName="recorderSpelled")
        self.spelled.setAlignment(Qt.AlignCenter)
        root.addWidget(self.spelled)
        root.addSpacing(8)

        self.status = QLabel("", objectName="hint")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(38)
        self.status.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status)
        root.addSpacing(14)

        root.addWidget(QLabel("常用組合", objectName="listCaption"))
        root.addSpacing(6)
        presets = QHBoxLayout()
        presets.setSpacing(7)
        for mods, key, note in PRESETS:
            label = plat.describe(key, plat.mod_names(mods))
            btn = QPushButton(f"{label}\n{note}" if note else label)
            btn.setToolTip(_spell(key, mods))     # 按鈕太窄放不下，用提示補
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _c=False, m=mods, k=key: self._pick(m, k))
            presets.addWidget(btn, 1)
        root.addLayout(presets)
        root.addSpacing(20)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addSpacing(8)
        self.record_btn = QPushButton("自己按一組…")
        self.record_btn.clicked.connect(self._arm_record)
        row.addWidget(self.record_btn)
        row.addSpacing(8)
        self.test_btn = QPushButton("試按看看")
        self.test_btn.clicked.connect(self._start_test)
        row.addWidget(self.test_btn)
        row.addSpacing(8)
        self.ok_btn = QPushButton(SAVE_LABEL, objectName="primary")
        self.ok_btn.clicked.connect(self._accept)
        row.addWidget(self.ok_btn)
        root.addLayout(row)

    # ---------------- 狀態 ----------------
    def _combo(self):
        return (tuple(self.mods), self.key)

    def _label(self):
        return plat.describe(self.key, plat.mod_names(self.mods))

    def _set_status(self, text, ok=None):
        self.status.setText(text)
        self.status.setObjectName(
            "hint" if ok is None else ("matchOk" if ok else "matchBad"))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _show_current(self):
        self.recorder.setText(self._label())
        self.spelled.setText(_spell(self.key, self.mods))
        valid, why = hotkey.is_valid(self.key, self.mods)
        if not valid:
            self._set_status(why, ok=False)
        elif self._combo() in self._verified:
            self._set_status("已經確認可以用 ✓", ok=True)
        else:
            bad = _known_bad(plat.mod_names(self.mods), self.key)
            if bad:
                self._set_status(f"{bad}，八成會搶不到 —— 建議換一組", ok=False)
            else:
                self._set_status("按「試按看看」確認這組真的能用", ok=None)
        self._sync_buttons(valid)

    def _sync_buttons(self, valid):
        testing = self._probe is not None
        self.test_btn.setEnabled(valid and not testing)
        self.record_btn.setEnabled(not testing)
        self.ok_btn.setEnabled(valid and not testing)

    def _pick(self, mods, key):
        self._stop_test()
        self.mods, self.key = plat.mod_names(mods), key
        self._show_current()

    # ---------------- 錄鍵 ----------------
    def _arm_record(self):
        self._stop_test()
        self.recorder.armed = True
        self.recorder.setFocus()
        self.recorder.setText("請按下你要的組合…")
        self._set_status("同時按住修飾鍵和主鍵，例如 option + shift + 空白鍵"
                         if plat.MACOS else
                         "同時按住修飾鍵和主鍵，例如 Alt + Shift + 空白鍵")
        self.record_btn.setEnabled(False)

    def _on_partial(self, mods):
        if not self.recorder.armed:
            return
        mods = plat.mod_names(mods)
        shown = "".join(plat.MOD_LABELS[m] for m in mods)
        self.recorder.setText(shown or "請按下你要的組合…")
        # 按住的當下就把名字寫出來，使用者才知道自己壓著的是哪幾顆
        self.spelled.setText(" + ".join(
            plat.SPELLED_MODS[m] if plat.MACOS else plat.MOD_LABELS[m]
            for m in mods))

    def _on_recorded(self, mods, key):
        self.recorder.armed = False
        self.record_btn.setEnabled(True)
        self.mods, self.key = plat.mod_names(mods), key
        self._show_current()

    # ---------------- 試按 ----------------
    def _start_test(self):
        """真的把這組掛上去，等使用者按

        Windows 掛不上就當場知道原因（多半是被別的程式佔走）；
        macOS 掛得上不代表沒人搶，所以一定要等到真的按下去才算數。
        """
        if self.on_pause:
            self.on_pause()
        self.recorder.armed = False
        self._probe = hotkey.probe(self.key, self.mods, self.hit.emit)

        if not self._probe.ok:
            reason = self._probe.error or "原因不明"
            self._stop_test()
            self._set_status(f"這組掛不上 —— {reason}", ok=False)
            return

        self._left = 10
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)
        self._tick()
        self._sync_buttons(True)

    def _tick(self):
        if self._probe is None:
            return
        if self._left <= 0:
            self._stop_test()
            self._set_status(f"等了 10 秒沒收到 {self._label()} —— "
                             "可能被別的程式搶走了，換一組試試。", ok=False)
            self._show_current_keep_status()
            return
        self._set_status(f"現在按一次 {self._label()}　（{self._left} 秒）")
        self._left -= 1

    def _hit_on_main(self):
        """熱鍵真的被按到了 —— 這是唯一可靠的證據（已經回到主執行緒）"""
        if self._probe is None:
            return
        self._verified.add(self._combo())
        self._stop_test()
        self._show_current()

    def _stop_test(self):
        timer = getattr(self, "_tick_timer", None)
        if timer is not None:
            timer.stop()
            self._tick_timer = None
        if self._probe is not None:
            try:
                self._probe.stop()
            except Exception:
                pass
            self._probe = None
            if self.on_resume:
                self.on_resume()
        self._sync_buttons(hotkey.is_valid(self.key, self.mods)[0])

    def _show_current_keep_status(self):
        """重畫按鈕但不要蓋掉剛寫上去的失敗訊息"""
        self.recorder.setText(self._label())
        self.spelled.setText(_spell(self.key, self.mods))
        self._sync_buttons(hotkey.is_valid(self.key, self.mods)[0])

    # ---------------- 收尾 ----------------
    def _accept(self):
        self._stop_test()
        self.chosen = (list(self.mods), self.key)
        self.accept()

    def reject(self):
        self._stop_test()
        super().reject()
