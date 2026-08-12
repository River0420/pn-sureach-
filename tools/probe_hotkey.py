"""為什麼在某些 App 裡按熱鍵沒反應 —— 用量的，不要用猜的

回答一個問題：**事件到底有沒有送到我們的監聽器？**

  有送到 → 問題在後面（視窗沒跳、跳出來又馬上被搶走焦點）
  沒送到 → 問題在前面，有東西比我們更早把它吃掉

最常見的「前面」是 macOS 的**安全輸入模式**（Secure Event Input）。
密碼欄位、以及某些 Electron／終端機類的 App 會打開它，一旦開啟，
**所有 CGEventTap 都收不到鍵盤事件** —— 這是系統防側錄的機制，
不是我們的程式壞掉，也沒有任何辦法繞過。所以這裡每秒也記錄一次
「現在是不是安全輸入模式、當時前景是哪個 App」。

只監聽 Space（keycode 49），不會記錄你打的任何其他東西。
純觀察，不攔截 —— 跑這支的時候你原本的熱鍵照常運作。
"""

import ctypes
import sys
import time

from AppKit import NSWorkspace
from Quartz import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource,
                    CFRunLoopGetCurrent, CFRunLoopRunInMode, CGEventGetFlags,
                    CGEventGetIntegerValueField, CGEventTapCreate,
                    CGEventTapEnable, kCFAllocatorDefault,
                    kCFRunLoopDefaultMode, kCGEventKeyDown,
                    kCGEventMaskForAllEvents, kCGEventTapOptionListenOnly,
                    kCGHeadInsertEventTap, kCGKeyboardEventKeycode,
                    kCGSessionEventTap)

SECONDS = 180
SPACE = 49
SHIFT, CTRL, ALT, CMD = 1 << 17, 1 << 18, 1 << 19, 1 << 20
MASK = SHIFT | CTRL | ALT | CMD
NAMES = [(SHIFT, "⇧"), (CTRL, "⌃"), (ALT, "⌥"), (CMD, "⌘")]

_carbon = ctypes.CDLL(
    "/System/Library/Frameworks/Carbon.framework/Versions/A/Carbon")
_carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool


def secure_input():
    try:
        return bool(_carbon.IsSecureEventInputEnabled())
    except Exception:
        return None


def frontmost():
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.localizedName() if app else "?"
    except Exception:
        return "?"


def describe(flags):
    return "".join(sym for bit, sym in NAMES if flags & bit) or "（無修飾鍵）"


def handler(proxy, etype, event, refcon):
    if etype == kCGEventKeyDown:
        if CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode) == SPACE:
            flags = CGEventGetFlags(event) & MASK
            print(f"  ✅ 收到  {describe(flags):<6} Space   "
                  f"前景：{frontmost()}", flush=True)
    return event


tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap,
                       kCGEventTapOptionListenOnly, kCGEventMaskForAllEvents,
                       handler, None)
if not tap:
    print("建不起來 event tap —— 這個終端機沒有「輔助使用」權限。", flush=True)
    print("系統設定 → 隱私權與安全性 → 輔助使用，把「終端機」打開。", flush=True)
    sys.exit(1)

CFRunLoopAddSource(CFRunLoopGetCurrent(),
                   CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0),
                   kCFRunLoopDefaultMode)
CGEventTapEnable(tap, True)

print(f"開始監聽 {SECONDS} 秒。請照這個順序做，每個地方按兩三次 ⌥Space：")
print()
print("  1) 先在「備忘錄」或桌面按　　　← 這是對照組，應該會有反應")
print("  2) 切到 Chrome 開 google.com 按")
print("  3) 切到 Claude Code 按")
print()
print("看下面有沒有印出「✅ 收到」就知道事件有沒有送到。")
print("=" * 62, flush=True)

end = time.time() + SECONDS
last_state = None
while time.time() < end:
    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.25, False)
    state = (secure_input(), frontmost())
    if state != last_state:
        secure, app = state
        if secure:
            print(f"  🔒 {app} 開啟了「安全輸入模式」"
                  f"—— 這種狀態下所有全域熱鍵都收不到事件", flush=True)
        elif last_state is not None and last_state[0]:
            print(f"  🔓 安全輸入模式解除（現在前景：{app}）", flush=True)
        last_state = state

print("=" * 62)
print("結束。把上面整段複製給我。", flush=True)
