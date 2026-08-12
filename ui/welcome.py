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


def _hotkey_detail():
    """macOS 的 ⌥⇧ 沒人認得，要拼出來；Windows 的 Alt+Shift+Space 本來就讀得懂"""
    spelled = plat.spell(hotkey.KEY, hotkey.MODIFIERS)
    prefix = f"也就是 {spelled}。" if spelled else ""
    # 剪貼簿預填是這個程式最省時間的一招，但它完全看不出來 ——
    # 沒講的話使用者只會乖乖地「按熱鍵、打字」，慢一倍。
    return (f"{prefix}在任何軟體裡都能按。"
            "先把料號複製起來再按，它會自動填好、直接把答案查出來；"
            "沒複製也行，按了打字就開始找。查完按 esc 關掉。")


def _step(number, title, detail, button=None, on_click=None):
    """一列：編號、說明、（可選的）動作按鈕"""
    row = QHBoxLayout()
    row.setSpacing(12)
    row.setContentsMargins(0, 0, 0, 0)     # 預設有 9px 邊界，會偷走文字的寬度

    badge = QLabel(str(number), objectName="stepBadge")
    badge.setFixedSize(26, 26)
    badge.setAlignment(Qt.AlignCenter)
    row.addWidget(badge, 0, Qt.AlignTop)

    text = QVBoxLayout()
    text.setSpacing(2)
    # 自動換行的 QLabel 預設的 sizeHint 只有一行高，放進巢狀 layout 會被壓扁，
    # 後面的行就被裁掉。正解是讓 sizePolicy 明講「我的高度由寬度決定」——
    # QVBoxLayout 只有在這個旗標打開時才會去問 heightForWidth()。
    #
    # 我先前試過「自己算可用寬度、再 setMinimumHeight」，錯了兩次：
    # 一次忘了 layout 預設有 9px 邊界，一次量到的寬度不是最終寬度。
    # 只要是自己算的就會有算錯的一天，交給 Qt 算。
    wrapped = []
    for widget, name in ((QLabel(title), "stepTitle"), (QLabel(detail), "stepDetail")):
        widget.setObjectName(name)
        widget.setWordWrap(True)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        policy.setHeightForWidth(True)
        widget.setSizePolicy(policy)
        text.addWidget(widget)
        wrapped.append(widget)
    row.addLayout(text, 1)

    if button:
        btn = QPushButton(button)
        
        btn.setCursor(Qt.PointingHandCursor)
        if on_click:
            btn.clicked.connect(on_click)
        row.addWidget(btn, 0, Qt.AlignTop)

    holder = QWidget()
    holder.setLayout(row)
    # 外層的 QVBoxLayout 是去問 holder 要多高，不是去問裡面的 label。
    # holder 沒宣告 heightForWidth 的話，外層只會拿到「一行」的 sizeHint，
    # 裡面的 label 講得再清楚也沒用 —— 這一層漏掉就整段前功盡棄。
    holder_policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    holder_policy.setHeightForWidth(True)
    holder.setSizePolicy(holder_policy)
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

        self._steps = steps
        self.adjustSize()

    def showEvent(self, event):
        """真正的高度只有在視窗顯示出來、寬度分配完之後才量得準

        heightForWidth 的 sizePolicy 在這種「QVBoxLayout 包 QWidget 包
        QHBoxLayout 包 QVBoxLayout 包 QLabel」的巢狀結構裡傳不上去，
        外層拿到的還是一行的 sizeHint。所以宣告完還要在這裡補一刀：
        等寬度發下來，問每個 label 這個寬度要多高，不夠就撐開。

        放在 showEvent 而不是 __init__，是因為 __init__ 時 width() 還不是
        最終值 —— 我在那裡量過兩次，兩次都量錯，兩次都裁掉最後一行。
        """
        super().showEvent(event)
        self._fix_heights()

    def _fix_heights(self):
        self.layout().activate()
        grew = False
        for step in self._steps:
            for label in step.wrapped:
                width = label.width()
                if width <= 1:
                    continue
                need = label.heightForWidth(width)
                if label.minimumHeight() < need:
                    label.setMinimumHeight(need)
                    grew = True
        if grew:
            self.layout().activate()
            self.adjustSize()

    def _change_hotkey(self):
        """開設定快捷鍵的視窗；換好了就把這一列的字換掉"""
        if not self._on_hotkey or not self._on_hotkey():
            return
        title, detail = self.hotkey_step.wrapped
        title.setText(f"用 {hotkey.HOTKEY_LABEL} 叫出查詢視窗")
        detail.setText(_hotkey_detail())
        self._fix_heights()
        self.adjustSize()
