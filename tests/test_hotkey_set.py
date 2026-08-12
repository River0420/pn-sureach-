"""設定快捷鍵：錄鍵、驗證、存檔、當場生效

這一支要守住的重點，是「使用者選的當下就知道能不能用」那條路：
錄得到 → 擋掉不能用的組合 → 真的掛上去試 → 存下來 → 畫面上的字跟著換。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtGui import QKeyEvent                             # noqa: E402
from PySide6.QtWidgets import QApplication                      # noqa: E402

app = QApplication.instance() or QApplication([])

from core import hotkey, plat, settings                         # noqa: E402
from ui import hotkey_dialog                                    # noqa: E402
from ui.hotkey_dialog import HotkeyDialog                       # noqa: E402

PASS = FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    mark = "✓" if cond else "✗"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {mark} {label}" + (f" → {extra}" if extra else ""))


def press(recorder, qt_key, qt_mods, native=None):
    """模擬一次真的按鍵，走 keyPressEvent 這條完整的路

    修飾鍵一定要包成 Qt.KeyboardModifier(...)：直接丟單一個 Qt.ShiftModifier
    進去，PySide6 會挑到別的建構子多載，做出來的事件 modifiers() 是空的 ——
    測試會假失敗，而程式其實是好的。
    """
    event = QKeyEvent(QKeyEvent.KeyPress, qt_key,
                      Qt.KeyboardModifier(qt_mods), 0, native or 0, 0)
    recorder.keyPressEvent(event)


print("\n[1] plat：原生鍵碼認得出按鍵名稱")
check("macOS 的 49 是 space" if plat.MACOS else "Windows 的 0x20 是 space",
      plat.key_from_native(49 if plat.MACOS else 0x20) == "space")
check("認不得的鍵碼回 None", plat.key_from_native(9999) is None)
# enter / escape / backspace 是別名，反查要給正式名稱
check("別名不會蓋掉正式名稱",
      plat.key_from_native(36 if plat.MACOS else 0x0D) == "return")

print("\n[2] plat：熱鍵拼成中文")
if plat.MACOS:
    check("⌥⇧Space 拼得出來",
          plat.spell("space", ["alt", "shift"]) == "option + shift + 空白鍵")
    check("順序跟符號一致（option 在 shift 前）",
          plat.spell("space", ["alt", "shift"]).index("option")
          < plat.spell("space", ["alt", "shift"]).index("shift"))
    check("字母鍵用大寫", plat.spell("q", ["alt"]) == "option + Q")
else:
    check("Windows 不用拼（本來就是英文）", plat.spell("space", ["alt"]) == "")

print("\n[3] hotkey.is_valid：擋掉不能用的組合")
check("沒有修飾鍵 → 擋掉", hotkey.is_valid("space", [])[0] is False)
check("擋掉時說得出原因", "修飾鍵" in hotkey.is_valid("space", [])[1])
check("不支援的按鍵 → 擋掉", hotkey.is_valid("§", ["alt"])[0] is False)
check("⌥⇧Space → 可以", hotkey.is_valid("space", ["alt", "shift"])[0] is True)
check("單一修飾鍵也可以", hotkey.is_valid("q", ["cmd"])[0] is True)

print("\n[4] 錄鍵：按住的當下就要即時顯示（不能慢一拍）")
# Qt 的 event.modifiers() 給的是「按下去之前」的狀態：按 Shift 的那個事件裡
# 一個修飾鍵都沒有，按 Alt 的事件裡只有 Shift。照抄的話畫面永遠慢一拍，
# 使用者按住 ⌥⇧ 卻只看到 ⌥，會以為錄壞了。
dlg = HotkeyDialog()
rec = dlg.recorder
dlg._arm_record()
check("進錄鍵模式後 recorder 是 armed", rec.armed is True)

press(rec, Qt.Key_Shift, Qt.NoModifier)          # 按下 shift（此時狀態還是空的）
check("按住 shift → 當場顯示 ⇧", rec.text() == plat.MOD_LABELS["shift"], rec.text())
check("還在錄", rec.armed is True)

press(rec, Qt.Key_Alt, Qt.ShiftModifier)         # 再按 alt（狀態只有 shift）
check("再按住 alt → 兩顆都顯示",
      set(rec.text()) == {plat.MOD_LABELS["shift"], plat.MOD_LABELS["alt"]},
      rec.text())

# 補上主鍵才算完成
press(rec, Qt.Key_Space, Qt.AltModifier | Qt.ShiftModifier,
      native=49 if plat.MACOS else 0x20)
check("按下 space → 錄完了", rec.armed is False)
check("錄到的是 alt+shift", sorted(dlg.mods) == ["alt", "shift"], str(dlg.mods))
check("錄到的按鍵是 space", dlg.key == "space")

print("\n[4b] 錄鍵：放開修飾鍵，顯示也要跟著少一顆")
dlg._arm_record()
press(rec, Qt.Key_Shift, Qt.NoModifier)
press(rec, Qt.Key_Alt, Qt.ShiftModifier)
release = QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_Alt,
                    Qt.KeyboardModifier(Qt.ShiftModifier | Qt.AltModifier), 0, 0, 0)
rec.keyReleaseEvent(release)
check("放開 alt → 只剩 ⇧", rec.text() == plat.MOD_LABELS["shift"], rec.text())

print("\n[5] 錄鍵：原生鍵碼優先，不被鍵盤配置影響")
dlg._arm_record()
# Qt 說是 Key_Aring（⌥A 在某些配置下的結果），但原生鍵碼是 A
press(rec, Qt.Key_Aring, Qt.AltModifier, native=0 if plat.MACOS else 0x41)
check("照原生鍵碼判成 a", dlg.key == "a", dlg.key)

print("\n[6] 已知會撞到系統的組合要先警告")
if plat.MACOS:
    dlg._pick(["cmd"], "space")
    check("⌘Space 被點名", "Spotlight" in dlg.status.text(), dlg.status.text())
    dlg._pick(["cmd", "shift"], "space")
    check("加一顆 shift 就不再警告", "Spotlight" not in dlg.status.text())
else:
    dlg._pick(["alt"], "space")
    check("Alt+Space 被點名", "視窗選單" in dlg.status.text(), dlg.status.text())
    dlg._pick(["alt", "shift"], "space")
    check("加一顆 shift 就不再警告", "視窗選單" not in dlg.status.text())

print("\n[7] 有沒有試按過，靠狀態列講，不是靠按鈕改字")
dlg._pick(["alt", "shift"], "space")
check("沒試按過 → 狀態列催你去試", "試按看看" in dlg.status.text(), dlg.status.text())
check("按鈕就是「儲存熱鍵」", dlg.ok_btn.text() == "儲存熱鍵", dlg.ok_btn.text())
dlg._verified.add((tuple(dlg.mods), dlg.key))
dlg._show_current()
check("試按過 → 狀態列說已確認", "確認" in dlg.status.text(), dlg.status.text())
check("按鈕字不會跟著變", dlg.ok_btn.text() == "儲存熱鍵", dlg.ok_btn.text())

print("\n[8] 不能用的組合不給按「用這組」")
dlg._pick([], "space")
check("沒修飾鍵 → 用這組是灰的", dlg.ok_btn.isEnabled() is False)
check("沒修飾鍵 → 試按看看也是灰的", dlg.test_btn.isEnabled() is False)
dlg._pick(["alt"], "q")
check("換成合法的組合 → 兩顆都亮回來",
      dlg.ok_btn.isEnabled() and dlg.test_btn.isEnabled())

print("\n[9] 試按之前一定要先把主監聽停掉")
# 不停的話，在 Windows 上拿同一組去試會撞到自己，回報「被佔走了」
paused = []
dlg2 = HotkeyDialog(on_pause=lambda: paused.append("pause"),
                    on_resume=lambda: paused.append("resume"))
dlg2._pick(["alt", "shift"], "space")
dlg2._start_test()
check("開始試按前有呼叫 on_pause", paused[:1] == ["pause"], str(paused))
if dlg2._probe is not None:
    check("試按中「用這組」是鎖住的", dlg2.ok_btn.isEnabled() is False)
    dlg2._hit_on_main()                      # 假裝使用者按到了
    check("按到之後就標記成已驗證",
          (tuple(dlg2.mods), dlg2.key) in dlg2._verified)
    check("按到之後 probe 收掉了", dlg2._probe is None)
    check("收掉時有呼叫 on_resume", "resume" in paused, str(paused))
else:
    # 沒有輔助使用權限時掛不上，這條路要走「講原因」而不是靜靜失敗
    check("掛不上時狀態列講得出原因", "掛不上" in dlg2.status.text(),
          dlg2.status.text())
    check("掛不上時也要把主監聽接回去", "resume" in paused, str(paused))

print("\n[10] 存檔：寫進設定檔而且各種寫法都跟著換")
before_key, before_mods = hotkey.KEY, list(hotkey.MODIFIERS)
try:
    label = hotkey.save("q", ["cmd", "shift"])
    check("KEY 換了", hotkey.KEY == "q")
    check("MODIFIERS 換了", hotkey.MODIFIERS == ["shift", "cmd"], str(hotkey.MODIFIERS))
    check("KEYCODE 跟著換", hotkey.KEYCODE == plat.key_code("q"))
    check("LABEL 跟著換", label == plat.describe("q", ["shift", "cmd"]), label)
    check("拼字版也跟著換", hotkey.HOTKEY_LABEL in hotkey.HOTKEY_SPELLED)
    check("寫進 settings", settings.get("hotkey.key") == "q")
    check("舊的 label 有被清掉（不然會顯示上一組）",
          settings.get("hotkey.label") == "")
finally:
    hotkey.save(before_key, before_mods)
check("復原成功", hotkey.KEY == before_key and hotkey.MODIFIERS == before_mods)

print("\n[11] 引導視窗：快捷鍵排在匯入前面")
from ui.welcome import WelcomeDialog                            # noqa: E402
w = WelcomeDialog(needs_permission=False, on_hotkey=lambda: False)
titles = [step.wrapped[0][0].text() for step in w._steps]
hot = next(i for i, t in enumerate(titles) if "叫出查詢視窗" in t)
imp = next(i for i, t in enumerate(titles) if "匯入" in t)
check("快捷鍵那一步在匯入前面", hot < imp, " / ".join(titles))
check("標題寫著目前這一組", hotkey.HOTKEY_LABEL in titles[hot], titles[hot])

print("\n[12] 引導視窗：換完快捷鍵，那一列的字要跟著換")
state = {"mods": ["ctrl", "shift"], "key": "f2"}


def fake_change():
    hotkey.save(state["key"], state["mods"])
    return True


w2 = WelcomeDialog(needs_permission=False, on_hotkey=fake_change)
try:
    w2._change_hotkey()
    title = w2.hotkey_step.wrapped[0][0].text()
    check("標題換成新的組合", plat.describe("f2", ["ctrl", "shift"]) in title, title)
    detail = w2.hotkey_step.wrapped[1][0].text()
    if plat.MACOS:
        check("說明也重拼了", "control + shift + F2" in detail, detail)
finally:
    hotkey.save(before_key, before_mods)

print("\n[13] 沒給 on_hotkey 就不要出現「換一組」按鈕")
w3 = WelcomeDialog(needs_permission=False)
from PySide6.QtWidgets import QPushButton                        # noqa: E402
buttons = [b.text() for b in w3.hotkey_step.findChildren(QPushButton)]
check("沒有換一組按鈕", "換一組" not in buttons, str(buttons))

print("\n[14] 預設清單本身要是合法的")
for mods, key, _note in hotkey_dialog.PRESETS:
    ok, why = hotkey.is_valid(key, mods)
    check(f"{plat.describe(key, plat.mod_names(mods))} 可用", ok, why)
check("第一個是出貨預設 shift+alt+space",
      hotkey_dialog.PRESETS[0][0] == ["shift", "alt"]
      and hotkey_dialog.PRESETS[0][1] == "space")

print("\n[15] 符號旁邊一定要有拼出來的字")
# ⌃⇧Space 這種東西沒人看得懂。大方框放符號，底下永遠跟一行中文。
d = HotkeyDialog()
d._pick(["ctrl", "shift"], "space")
check("⌃⇧Space 有拼出來",
      d.spelled.text() == ("control + shift + 空白鍵" if plat.MACOS
                           else "Ctrl + Shift + 空白鍵"), d.spelled.text())
d._pick(["alt"], "q")
check("換一組，拼字跟著換",
      d.spelled.text() == ("option + Q" if plat.MACOS else "Alt + Q"),
      d.spelled.text())
d._arm_record()
d._on_partial(["alt", "shift"])
check("錄鍵按住的當下也拼出來",
      d.spelled.text() == ("option + shift" if plat.MACOS else "Alt + Shift"),
      d.spelled.text())
check("大方框同時顯示符號", d.recorder.text() == "⌥⇧" if plat.MACOS else True,
      d.recorder.text())

print(f"\n===== {PASS} 過 / {FAIL} 失敗 =====")
sys.exit(1 if FAIL else 0)
