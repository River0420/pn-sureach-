"""全域熱鍵（自己接 Quartz 事件，不透過 pynput）

為什麼不用 pynput：它的 macOS 監聽器會在背景執行緒呼叫 AppKit 的
`NSEvent.eventWithCGEvent_` 來解析按鍵，而 macOS 15 的輸入法／caps-lock 處理
會斷言「必須在主執行緒」，踩到就整個程式 SIGTRAP 崩潰。

這裡直接用 Core Graphics 的 event tap：比對 keycode 與修飾鍵就好，
全程不碰 AppKit，回呼只做一件事 —— 送出 Qt signal 回主執行緒。
順便把熱鍵本身吃掉，不會再傳給使用者當時所在的 App。

要換熱鍵改 config/settings.json 的 hotkey 區塊即可。
"""

import threading

from core import settings

try:
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRun,
        CFRunLoopStop,
        CGEventGetFlags,
        CGEventGetIntegerValueField,
        CGEventMaskBit,
        CGEventTapCreate,
        CGEventTapEnable,
        kCFRunLoopCommonModes,
        kCGEventFlagMaskAlternate,
        kCGEventFlagMaskCommand,
        kCGEventFlagMaskControl,
        kCGEventFlagMaskShift,
        kCGEventKeyDown,
        kCGEventKeyUp,
        kCGEventTapDisabledByTimeout,
        kCGEventTapDisabledByUserInput,
        kCGEventTapOptionDefault,
        kCGHeadInsertEventTap,
        kCGKeyboardEventKeycode,
        kCGSessionEventTap,
    )
    QUARTZ = True
except Exception:
    QUARTZ = False
    kCGEventFlagMaskShift = 1 << 17
    kCGEventFlagMaskControl = 1 << 18
    kCGEventFlagMaskAlternate = 1 << 19
    kCGEventFlagMaskCommand = 1 << 20
    kCGEventKeyDown = 10
    kCGEventKeyUp = 11

MOD_MASK = (
    kCGEventFlagMaskShift
    | kCGEventFlagMaskControl
    | kCGEventFlagMaskAlternate
    | kCGEventFlagMaskCommand
)

_MOD_FLAGS = {
    "shift": kCGEventFlagMaskShift,
    "ctrl": kCGEventFlagMaskControl,
    "control": kCGEventFlagMaskControl,
    "alt": kCGEventFlagMaskAlternate,
    "option": kCGEventFlagMaskAlternate,
    "opt": kCGEventFlagMaskAlternate,
    "cmd": kCGEventFlagMaskCommand,
    "command": kCGEventFlagMaskCommand,
}

# 顯示順序照 macOS 慣例：⌃⌥⇧⌘
_MOD_SYMBOLS = [
    ("ctrl", kCGEventFlagMaskControl, "⌃"),
    ("alt", kCGEventFlagMaskAlternate, "⌥"),
    ("shift", kCGEventFlagMaskShift, "⇧"),
    ("cmd", kCGEventFlagMaskCommand, "⌘"),
]

# 常用鍵的顯示名稱，沒列到的就顯示 key<代碼>
_KEY_NAMES = {
    49: "Space", 36: "Return", 48: "Tab", 53: "Esc", 51: "Delete",
    122: "F1", 120: "F2", 99: "F3", 118: "F4", 96: "F5", 97: "F6",
    98: "F7", 100: "F8", 101: "F9", 109: "F10", 103: "F11", 111: "F12",
    0: "A", 11: "B", 8: "C", 2: "D", 14: "E", 3: "F", 5: "G", 4: "H",
    34: "I", 38: "J", 40: "K", 37: "L", 46: "M", 45: "N", 31: "O",
    35: "P", 12: "Q", 15: "R", 1: "S", 17: "T", 32: "U", 9: "V",
    13: "W", 7: "X", 16: "Y", 6: "Z",
}


def _modifier_mask(names):
    mask = 0
    for name in names or []:
        mask |= _MOD_FLAGS.get(str(name).strip().lower(), 0)
    return mask


def describe(keycode, mask):
    symbols = "".join(sym for _, flag, sym in _MOD_SYMBOLS if mask & flag)
    return symbols + _KEY_NAMES.get(keycode, f"key{keycode}")


KEYCODE = settings.get("hotkey.keycode", 49)
HOTKEY_MODIFIERS = _modifier_mask(settings.get("hotkey.modifiers", ["alt"]))
HOTKEY_LABEL = settings.get("hotkey.label") or describe(KEYCODE, HOTKEY_MODIFIERS)

# 相容舊名稱
SPACE_KEYCODE = 49


class HotkeyListener:
    """在自己的執行緒上跑一個 CFRunLoop，監聽並攔截熱鍵"""

    def __init__(self, callback, keycode=None, modifiers=None):
        self.callback = callback
        self.keycode = KEYCODE if keycode is None else keycode
        self.modifiers = HOTKEY_MODIFIERS if modifiers is None else modifiers
        self.tap = None
        self.ok = False
        self._thread = None
        self._runloop = None
        self._source = None

    def matches(self, event_type, event):
        if event_type not in (kCGEventKeyDown, kCGEventKeyUp):
            return False
        if CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode) != self.keycode:
            return False
        # 修飾鍵要完全吻合，⌘⌥Space 這種組合要放行
        return (CGEventGetFlags(event) & MOD_MASK) == self.modifiers

    def _handler(self, proxy, event_type, event, refcon):
        # 系統偶爾會把 tap 關掉（逾時或使用者操作），要自己開回來
        if event_type in (kCGEventTapDisabledByTimeout,
                          kCGEventTapDisabledByUserInput):
            if self.tap is not None:
                CGEventTapEnable(self.tap, True)
            return event

        if not self.matches(event_type, event):
            return event

        if event_type == kCGEventKeyDown:
            try:
                self.callback()
            except Exception:
                pass
        return None      # 吃掉，不往下傳給前景 App

    def _run(self):
        self.tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp),
            self._handler,
            None,
        )
        if self.tap is None:
            return      # 沒有輔助使用權限，main.py 會處理提示
        source = CFMachPortCreateRunLoopSource(None, self.tap, 0)
        self._runloop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._runloop, source, kCFRunLoopCommonModes)
        CGEventTapEnable(self.tap, True)
        self._source = source      # 留著參考，不要被回收
        self.ok = True
        CFRunLoopRun()
        self.ok = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # 等 tap 建好，才知道到底有沒有成功
        for _ in range(40):
            if self.ok or (self._thread and not self._thread.is_alive()):
                break
            threading.Event().wait(0.025)
        return self.ok

    def stop(self):
        """把 event tap 收掉並讓那條執行緒結束

        沒有這個的話，權限被關掉再打開時會疊出第二個 tap，
        熱鍵按一次就會跳兩次視窗。
        """
        self.ok = False
        try:
            if self.tap is not None:
                CGEventTapEnable(self.tap, False)
            if self._runloop is not None:
                CFRunLoopStop(self._runloop)
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.tap = None
        self._source = None
        self._runloop = None
        self._thread = None


def start(callback):
    """開始監聽熱鍵，回傳 listener（失敗時 listener.ok 為 False）

    callback 會在監聽執行緒上被呼叫，裡面只能做執行緒安全的事。
    回傳值一定要留著，之後才停得掉。
    """
    if not QUARTZ:
        return None
    listener = HotkeyListener(callback)
    listener.start()
    return listener
