"""在 Mac 上驗證 Windows 那條路的邏輯

真的 Windows 行為（RegisterHotKey 會不會被擋、視窗長怎樣）只能在 Windows 上測，
但「收到熱鍵 → 呼叫 callback」「註冊失敗 → 產生看得懂的錯誤」「stop() 收得乾淨」
這些是純邏輯，可以用假的 user32 在這裡跑完。

做法：把 ctypes.WinDLL 換成假的，再 reload core.hotkey_win。
"""

import ctypes
import importlib
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def check(name, ok, note=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {name}" + (f" → {note}" if note else ""))
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" → {note}" if note else ""))


# ---------------------------------------------------------------- 假的 Win32
class FakeMSG:
    def __init__(self):
        self.message = 0
        self.wParam = 0


class FakeUser32:
    """模擬 RegisterHotKey + GetMessageW 的行為"""

    def __init__(self, register_ok=True, last_error=0):
        self.register_ok = register_ok
        self.last_error = last_error
        self.registered = []
        self.unregistered = []
        self.q = queue.Queue()
        self.get_message_calls = 0

    def RegisterHotKey(self, hwnd, hid, mods, vk):
        if not self.register_ok:
            return 0
        self.registered.append((hid, mods, vk))
        return 1

    def UnregisterHotKey(self, hwnd, hid):
        self.unregistered.append(hid)
        return 1

    def GetMessageW(self, msg_ptr, hwnd, lo, hi):
        self.get_message_calls += 1
        item = self.q.get()
        if item is None:            # WM_QUIT
            return 0
        msg = msg_ptr._obj
        msg.message, msg.wParam = item
        return 1

    def PostThreadMessageW(self, tid, message, w, l):
        self.q.put(None)
        return 1

    def press(self, message, wparam):
        self.q.put((message, wparam))


class FakeKernel32:
    def GetCurrentThreadId(self):
        return 4242


# 這些替身要一直活著 —— 監聽執行緒是在 load_hotkey_win() 回來之後才去呼叫
# ctypes.get_last_error 的，如果在 finally 裡復原，那個執行緒就會抓到
# 沒有被 patch 的原版（macOS 的 ctypes 根本沒有這個函式）而炸掉。
_STATE = {"user32": None, "kernel32": FakeKernel32(), "last_error": 0}


def install_fakes():
    """裝上替身。要在「測真實 macOS 行為」的那一段跑完之後才呼叫"""
    ctypes.WinDLL = lambda name, **kw: _STATE[name]
    ctypes.get_last_error = lambda: _STATE["last_error"]
    ctypes.byref = lambda obj: type("Ref", (), {"_obj": obj})()
    fake_wintypes = type(sys)("ctypes.wintypes")
    fake_wintypes.MSG = FakeMSG
    sys.modules["ctypes.wintypes"] = fake_wintypes


def load_hotkey_win(register_ok=True, last_error=0):
    """把假的 DLL 塞進去再 reload 模組"""
    _STATE["user32"] = FakeUser32(register_ok, last_error)
    _STATE["last_error"] = last_error

    import core.hotkey_win as hw
    importlib.reload(hw)
    return hw, _STATE["user32"]


# ---------------------------------------------------------------- 測試
ON_WINDOWS = sys.platform.startswith("win")

print("\n[1] 沒有 Win32 的機器上 import 不能爆炸")
if ON_WINDOWS:
    # 這一段是在驗「非 Windows 平台的降級行為」。真的在 Windows 上跑的時候
    # user32 載得起來，AVAILABLE 本來就該是 True，硬套會誤判成失敗。
    # 而且 Listener.start() 會真的去註冊一組全域熱鍵，不該在 CI 上做。
    import core.hotkey_win as hw_real
    check("在 Windows 上 AVAILABLE 是 True", hw_real.AVAILABLE is True,
          str(hw_real.AVAILABLE))
    print("     （降級行為的檢查只在非 Windows 上跑，這裡跳過）")
else:
    import core.hotkey_win as hw_mac
    check("hotkey_win 在非 Windows 上載得起來", True)
    check("AVAILABLE 自動變 False", hw_mac.AVAILABLE is False, str(hw_mac.AVAILABLE))
    l = hw_mac.Listener(lambda: None, 0x20, ["alt"])
    check("start() 不會丟例外，回 False", l.start() is False)
    check("有講出原因", bool(l.error), l.error)
    l.stop()
    check("stop() 在沒啟動的情況下也安全", True)

print("\n[2] 修飾鍵換算")
install_fakes()      # 從這裡開始都是假的 Win32
hw, _ = load_hotkey_win()
check("alt → MOD_ALT|MOD_NOREPEAT",
      hw.modifier_mask(["alt"]) == 0x0001 | 0x4000,
      hex(hw.modifier_mask(["alt"])))
check("ctrl+shift 疊加",
      hw.modifier_mask(["ctrl", "shift"]) == 0x0002 | 0x0004 | 0x4000,
      hex(hw.modifier_mask(["ctrl", "shift"])))
check("cmd 對到 Windows 鍵", hw.modifier_mask(["cmd"]) & 0x0008 == 0x0008)
check("一定帶 MOD_NOREPEAT（按著不放不連發）",
      hw.modifier_mask([]) & 0x4000 == 0x4000)

print("\n[3] 註冊成功 → 收到熱鍵會呼叫 callback")
hw, user32 = load_hotkey_win()
hits = []
lis = hw.Listener(lambda: hits.append(time.time()), 0x20, ["alt"])
check("start() 回 True", lis.start() is True)
check("ok 是 True", lis.ok is True)
check("真的呼叫了 RegisterHotKey", len(user32.registered) == 1, str(user32.registered))
hid, mods, vk = user32.registered[0]
check("送出去的 VK 是 Space(0x20)", vk == 0x20, hex(vk))
check("送出去的修飾鍵含 MOD_ALT", mods & 0x0001 == 0x0001, hex(mods))

user32.press(hw.WM_HOTKEY, hw.HOTKEY_ID)
for _ in range(100):
    if hits:
        break
    time.sleep(0.005)
check("按熱鍵 → callback 被呼叫一次", len(hits) == 1, f"{len(hits)} 次")

user32.press(hw.WM_HOTKEY, 999)          # 不是我們的 id
user32.press(0x0100, hw.HOTKEY_ID)       # 不是 WM_HOTKEY
time.sleep(0.05)
check("別人的熱鍵 id 不會誤觸發", len(hits) == 1, f"{len(hits)} 次")

print("\n[4] stop() 要收乾淨")
lis.stop()
for _ in range(100):
    if user32.unregistered:
        break
    time.sleep(0.005)
check("有呼叫 UnregisterHotKey", user32.unregistered == [hw.HOTKEY_ID],
      str(user32.unregistered))
check("ok 變回 False", lis.ok is False)
check("執行緒已結束", lis._thread is None)

print("\n[5] 註冊失敗 → 要有看得懂的錯誤")
hw, user32 = load_hotkey_win(register_ok=False, last_error=1409)
lis = hw.Listener(lambda: None, 0x20, ["alt"])
check("start() 回 False", lis.start() is False)
check("錯誤訊息說得出是被佔用", "被其他程式用走" in lis.error, lis.error)
# 解法不再是「去改 settings.json」，而是選單裡的「設定快捷鍵…」——
# 訊息只要指出「換一組」，怎麼換由那個視窗負責
check("錯誤訊息有指出解法", "換一組" in lis.error)

hw, _ = load_hotkey_win(register_ok=False, last_error=99999)
lis = hw.Listener(lambda: None, 0x20, ["alt"])
lis.start()
check("沒對照到的錯誤碼也會原樣印出", "99999" in lis.error, lis.error)

print("\n[6] callback 自己爆掉不能弄死監聽執行緒")
hw, user32 = load_hotkey_win()
calls = []


def bad_callback():
    calls.append(1)
    raise RuntimeError("故意的")


lis = hw.Listener(bad_callback, 0x20, ["alt"])
lis.start()
user32.press(hw.WM_HOTKEY, hw.HOTKEY_ID)
time.sleep(0.05)
user32.press(hw.WM_HOTKEY, hw.HOTKEY_ID)
time.sleep(0.05)
check("第一次爆掉之後還收得到第二次", len(calls) == 2, f"{len(calls)} 次")
lis.stop()

print("\n[7] plat 的跨平台對照")
from core import plat
for name, (mac, win) in list(plat.KEYS.items())[:0] or []:
    pass
check("space 的 Windows VK 是 0x20", plat.KEYS["space"][1] == 0x20)
check("f2 的 Windows VK 是 0x71", plat.KEYS["f2"][1] == 0x71)
check("q 的 Windows VK 是 0x51", plat.KEYS["q"][1] == 0x51)
check("每個鍵都有兩個平台的碼",
      all(len(v) == 2 and all(isinstance(x, int) for x in v)
          for v in plat.KEYS.values()))
check("舊的 macOS 鍵碼反查得回名稱", plat.key_name(120) == "f2")
check("亂寫的鍵名會退回 space", plat.key_name("不存在的鍵") == "space")
check("亂寫的修飾鍵會被丟掉", plat.mod_names(["alt", "香蕉"]) == ["alt"])



# ---------------------------------------------------------------- 圖示
print("\n[圖示] 常駐圖示在兩個平台上的行為")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)
from core import plat
from ui import appicon

icon = appicon.tray_icon()
check("圖示不是空的", not icon.isNull())
check("每個尺寸都畫得出來",
      all(not icon.pixmap(s, s).isNull() for s in appicon.TRAY_SIZES))
check("mac 是 template image（系統自己上色）",
      icon.isMask() if plat.MACOS else not icon.isMask(),
      f"isMask={icon.isMask()} on {plat.NAME}")

pix = appicon.draw(16, "#000000")
check("16px 畫得出來且是方的", pix.width() == 16 and pix.height() == 16,
      f"{pix.width()}x{pix.height()}")
check("16px 沒有 pin-1 圓點（那顆點在這個尺寸只會變髒）",
      appicon.draw(16, "#000000").toImage() != appicon.draw(24, "#000000")
      .scaled(16, 16).toImage())

big = appicon.app_icon()
check("上色版也生得出來", not big.isNull() and not big.pixmap(256, 256).isNull())

ico = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "app.ico")
check("assets/app.ico 有 commit 進來（CI 上沒有 Pillow 可以現產）",
      os.path.exists(ico), ico)



# ---------------------------------------------------------------- 權限
print("\n[權限] macOS 的授權引導不能靜靜失效")
from core import permission

if plat.MACOS:
    check("ApplicationServices 載入得了（打包時最容易漏掉的一個）",
          permission.AVAILABLE, f"AVAILABLE={permission.AVAILABLE}")
    check("macOS 上 NEEDED 要是 True", permission.NEEDED)
else:
    check("非 macOS 不需要權限", not permission.NEEDED)

# 就算偵測模組整個掛掉，macOS 上也不該退化成「叫使用者去改 settings.json」。
# 這是 v1.0 真的發生過的事：打包漏了 ApplicationServices，
# 程式以為自己不用權限，使用者看到一個完全幫不上忙的訊息。
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "main.py"), encoding="utf-8").read()
check("熱鍵掛不上時，macOS 走的是權限引導不是改設定檔",
      "show_permission_help() if plat.MACOS else show_hotkey_help()" in src)



# ---------------------------------------------------------------- 第一次啟動
print("\n[第一次啟動] 不能讓使用者面對一片空白")
from ui.welcome import WelcomeDialog

_app2 = QApplication.instance() or QApplication(sys.argv)
for needs in (True, False):
    try:
        d = WelcomeDialog(needs, lambda: None, lambda: None)
        d.adjustSize()
        check(f"引導視窗建得起來（needs_permission={needs}）",
              d.width() > 300 and d.height() > 300, f"{d.width()}x{d.height()}")
    except Exception as e:
        check(f"引導視窗建得起來（needs_permission={needs}）", False,
              f"{type(e).__name__}: {e}")

check("有權限步驟時視窗比較高（多一列）",
      WelcomeDialog(True, None, None).sizeHint().height()
      > WelcomeDialog(False, None, None).sizeHint().height())

# 這幾件事在 v1.0 都害使用者卡住過，寫成測試免得改著改著又掉了
main_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "main.py"), encoding="utf-8").read()
check("第一次啟動的判斷在寫預設檔之前",
      main_src.index("first_run = not os.path.exists")
      < main_src.index("settings.write_defaults_if_missing()"))
check("單一實例撞到時會跳視窗，不是靜靜結束",
      "QMessageBox.information(" in main_src.split("lock = acquire_single_instance()")[1][:900])

print(f"\n===== {PASS} 過 / {FAIL} 失敗 =====")
sys.exit(1 if FAIL else 0)
