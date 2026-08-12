"""第一次啟動時的引導視窗

為什麼需要這個：這是常駐工具，啟動之後畫面上什麼都不會發生 ——
不進 Dock、不進工作列、沒有主視窗，只在選單列多一顆小圖示。

對做這個程式的人來說「當然是這樣」，對第一次拿到的人來說就是
「我雙擊了，然後呢？壞了嗎？」。實測有人卡在這裡直接放棄，
而且他不會來問你，他只會覺得這東西不能用。

所以第一次開一定要有一個看得見的東西，講三件事：
  1. 它已經在跑了，圖示在哪
  2. 熱鍵是什麼
  3. 還差什麼才能用（權限、匯入資料）

只在沒有設定檔的時候出現一次。之後不再打擾。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from core import hotkey, paths, plat
from ui import appicon, style


WIDTH = 470          # 固定寬度，換行結果才可預測
_MARGIN_X = 30
_BADGE_W, _GAP = 26, 12
_BUTTON_ROOM = 86    # 「去開啟」「匯入」那一顆的寬度


def _text_width(has_button):
    """說明文字實際拿得到多少寬 —— 算出來，不要用猜的"""
    room = WIDTH - 2 * _MARGIN_X - _BADGE_W - _GAP
    return room - (_BUTTON_ROOM + _GAP) if has_button else room


def _hotkey_detail():
    """macOS 的 ⌥⇧ 沒人認得，要拼出來；Windows 的 Alt+Shift+Space 本來就讀得懂"""
    spelled = plat.spell(hotkey.KEY, hotkey.MODIFIERS)
    prefix = f"也就是 {spelled}。" if spelled else ""
    return (f"{prefix}在任何軟體裡都能按，打字就直接找，"
            "不用按 Enter，查完按 esc 關掉。")


def _step(number, title, detail, button=None, on_click=None):
    """一列：編號、說明、（可選的）動作按鈕"""
    row = QHBoxLayout()
    row.setSpacing(12)

    badge = QLabel(str(number), objectName="stepBadge")
    badge.setFixedSize(26, 26)
    badge.setAlignment(Qt.AlignCenter)
    row.addWidget(badge, 0, Qt.AlignTop)

    text = QVBoxLayout()
    text.setSpacing(2)
    # 自動換行的 QLabel 預設的 sizeHint 不含換行後的高度，放進巢狀 layout
    # 會被壓扁成一行，第二行就疊上去了。真正的高度等視窗建好、樣式套過
    # 之後再由 _fix_wrapped_heights() 算 —— 在這裡問會用到還沒套 QSS 的字體。
    avail = _text_width(bool(button))
    wrapped = []
    for widget, name in ((QLabel(title), "stepTitle"), (QLabel(detail), "stepDetail")):
        widget.setObjectName(name)
        widget.setWordWrap(True)
        widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        text.addWidget(widget)
        wrapped.append((widget, avail))
    row.addLayout(text, 1)

    if button:
        btn = QPushButton(button)
        
        btn.setCursor(Qt.PointingHandCursor)
        if on_click:
            btn.clicked.connect(on_click)
        row.addWidget(btn, 0, Qt.AlignTop)

    holder = QWidget()
    holder.setLayout(row)
    holder.wrapped = wrapped
    return holder


class WelcomeDialog(QDialog):
    def __init__(self, needs_permission, on_permission=None, on_import=None,
                 on_hotkey=None):
        super().__init__()
        self.setWindowTitle(f"歡迎使用 {paths.APP_NAME}")
        self.setModal(False)
        self.setFixedWidth(WIDTH)
        self.setStyleSheet(style.DIALOG_QSS)

        where = "螢幕右上角的選單列" if plat.MACOS else "螢幕右下角的工作列"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(0)

        icon = QLabel()
        icon.setPixmap(appicon.draw(52, appicon.BODY, appicon.PINS))
        layout.addWidget(icon, 0, Qt.AlignHCenter)
        layout.addSpacing(14)

        title = QLabel(f"{paths.APP_NAME} 已經在執行了", objectName="welcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = QLabel(f"它住在{where}，長得像上面那顆晶片。\n"
                     f"這個程式沒有主視窗，所以{'Dock' if plat.MACOS else '工作列'}"
                     f"上不會有它 —— 這是正常的。",
                     objectName="welcomeSub")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addSpacing(24)

        # 順序是有意的：權限 → 快捷鍵 → 匯入。
        # 快捷鍵排在匯入前面，是因為它是這個程式唯一的入口 ——
        # 資料匯得再漂亮，叫不出視窗就是零。
        steps = []
        n = 1
        if needs_permission:
            steps.append(_step(
                n, "開啟「輔助使用」權限",
                "熱鍵要這個權限才能用。按右邊直接開設定頁，把清單裡的"
                "本程式打勾。",
                "去開啟", on_permission))
            n += 1

        self.hotkey_step = _step(
            n, f"用 {hotkey.HOTKEY_LABEL} 叫出查詢視窗", _hotkey_detail(),
            "換一組" if on_hotkey else None, self._change_hotkey)
        self._on_hotkey = on_hotkey
        steps.append(self.hotkey_step)
        n += 1

        steps.append(_step(
            n, "匯入你的報價單 / 庫存表",
            "Excel 或 CSV 都可以，最多三個檔案。程式會用料號把它們串起來。",
            "匯入", on_import))

        for i, step in enumerate(steps):
            layout.addWidget(step)
            if i < len(steps) - 1:
                layout.addSpacing(16)
        layout.addSpacing(26)

        close = QPushButton("知道了")
        close.setObjectName("primary")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignHCenter)

        foot = QLabel("這個畫面只會出現這一次。"
                      f"之後有問題就點{where}的圖示 →「診斷資訊…」。",
                      objectName="welcomeFoot")
        foot.setAlignment(Qt.AlignCenter)
        foot.setWordWrap(True)
        layout.addSpacing(14)
        layout.addWidget(foot)

        # 樣式套過之後才量得到真正的字體，這時候換行高度才算得準
        self.ensurePolished()
        self._steps = steps
        self._fix_heights()

    def _fix_heights(self):
        for step in self._steps:
            for widget, avail in step.wrapped:
                widget.ensurePolished()
                widget.setMinimumHeight(widget.heightForWidth(avail))

    def _change_hotkey(self):
        """開設定快捷鍵的視窗；換好了就把這一列的字換掉"""
        if not self._on_hotkey or not self._on_hotkey():
            return
        title, detail = (w for w, _ in self.hotkey_step.wrapped)
        title.setText(f"用 {hotkey.HOTKEY_LABEL} 叫出查詢視窗")
        detail.setText(_hotkey_detail())
        self._fix_heights()
        self.adjustSize()
