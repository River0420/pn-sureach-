"""「試按看看」：從真的按下去，到畫面上出現 ✓

這一支跟 test_hotkey_set.py 不一樣的地方，是它**不作弊**。
那邊測邏輯時直接呼叫 _hit_on_main()，等於跳過了整段跨執行緒的路 ——
而第一次上線壞掉的就是那一段：熱鍵明明收到了，通知卻送不回主執行緒
（QTimer.singleShot 建在沒有事件迴圈的監聽執行緒上，永遠不會跑），
畫面一路等到 10 秒逾時。

所以這裡真的掛上 event tap、真的合成一次按鍵、真的跑 Qt 事件迴圈。
沒有輔助使用權限的環境（CI）掛不上 tap，那就改驗「有沒有好好講原因」。
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication          # noqa: E402

app = QApplication.instance() or QApplication([])

from core import hotkey, plat                       # noqa: E402
from ui.hotkey_dialog import HotkeyDialog           # noqa: E402

PASS = FAIL = SKIP = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {'✓' if cond else '✗'} {label}" + (f" → {extra}" if extra else ""))


def pump(seconds):
    """跑 Qt 事件迴圈，讓佇列訊號真的送得到"""
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def send_hotkey(mods, key):
    """合成一次真的鍵盤事件送進系統"""
    from Quartz import (CGEventCreateKeyboardEvent, CGEventPost,
                        CGEventSetFlags, kCGHIDEventTap)
    flags = {"shift": 1 << 17, "ctrl": 1 << 18, "alt": 1 << 19, "cmd": 1 << 20}
    mask = 0
    for m in mods:
        mask |= flags[m]
    code = plat.key_code(key)
    for down in (True, False):
        event = CGEventCreateKeyboardEvent(None, code, down)
        CGEventSetFlags(event, mask)
        CGEventPost(kCGHIDEventTap, event)


MODS, KEY = ["shift", "alt"], "space"

print("\n[1] 直接用 hotkey.probe：熱鍵收得到嗎")
hits = []
probe = hotkey.probe(KEY, MODS, lambda: hits.append(1))
have_tap = probe.ok
if not have_tap:
    print(f"  （掛不上 event tap：{probe.error}）")
    print("  這台機器沒有輔助使用權限（CI 就是這樣），跳過真的按鍵那幾項")
    check("掛不上時要講得出原因", bool(probe.error), probe.error)
else:
    check("熱鍵掛得上", probe.ok)   # macOS 是 event tap，Windows 是 RegisterHotKey
    if plat.MACOS:
        send_hotkey(MODS, KEY)
        pump(0.8)
        check("送出 ⌥⇧Space → 收到 1 次", len(hits) == 1, str(len(hits)))
        send_hotkey(["alt"], KEY)          # 修飾鍵不吻合
        pump(0.8)
        check("送出 ⌥Space（不吻合）→ 沒有多收", len(hits) == 1, str(len(hits)))
probe.stop()
check("stop() 之後 ok 變回 False", probe.ok is False)

print("\n[2] 整條路：按下去 → 視窗上出現「已經確認可以用」")
resumed = []
dlg = HotkeyDialog(on_resume=lambda: resumed.append(1))
dlg._pick(MODS, KEY)
dlg._start_test()

if dlg._probe is None:
    # 掛不上（沒權限）：這條路的要求是「當場講原因」，不是靜靜失敗
    check("掛不上時狀態列有講原因", "掛不上" in dlg.status.text(), dlg.status.text())
    check("掛不上時主監聽有接回去", bool(resumed))
    check("掛不上時不會標記成已驗證",
          (tuple(dlg.mods), dlg.key) not in dlg._verified)
else:
    check("倒數中：狀態列在請使用者按", "現在按一次" in dlg.status.text(),
          dlg.status.text())
    if plat.MACOS:
        send_hotkey(MODS, KEY)
        pump(1.5)          # 這裡就是原本壞掉的地方：訊號要跨執行緒送回來
        check("按下去之後標記成已驗證",
              (tuple(dlg.mods), dlg.key) in dlg._verified)
        check("狀態列變成已確認", "確認" in dlg.status.text(), dlg.status.text())
        check("probe 自動收掉了", dlg._probe is None)
        check("主監聽接回去了", bool(resumed))
        check("按鈕還是「儲存熱鍵」", dlg.ok_btn.text() == "儲存熱鍵", dlg.ok_btn.text())
    else:
        dlg._stop_test()

print("\n[3] 沒按到就是要老實說沒按到")
dlg2 = HotkeyDialog()
dlg2._pick(MODS, KEY)
dlg2._start_test()
if dlg2._probe is not None:
    dlg2._left = 0
    dlg2._tick()                            # 直接推到逾時那一刻
    check("逾時後說沒收到", "沒收到" in dlg2.status.text(), dlg2.status.text())
    check("逾時後不算已驗證",
          (tuple(dlg2.mods), dlg2.key) not in dlg2._verified)
    check("逾時後 probe 收掉了", dlg2._probe is None)
    check("逾時後按鈕還是「儲存熱鍵」", dlg2.ok_btn.text() == "儲存熱鍵")
else:
    print("  （掛不上，跳過）")
dlg2._stop_test()

print(f"\n===== {PASS} 過 / {FAIL} 失敗 =====")
sys.exit(1 if FAIL else 0)
