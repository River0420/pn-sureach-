"""macOS 全域熱鍵（自己接 Quartz 事件，不透過 pynput）

為什麼不用 pynput：它的 macOS 監聽器會在背景執行緒呼叫 AppKit 的
`NSEvent.eventWithCGEvent_` 來解析按鍵，而 macOS 15 的輸入法／caps-lock 處理
會斷言「必須在主執行緒」，踩到就整個程式 SIGTRAP 崩潰。

這裡直接用 Core Graphics 的 event tap：比對 keycode 與修飾鍵就好，
全程不碰 AppKit，回呼只做一件事 —— 送出 Qt signal 回主執行緒。
順便把熱鍵本身吃掉，不會再傳給使用者當時所在的 App。

對外介面由 core/hotkey.py 統一，這裡不要直接被 import。
"""

import threading

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
    AVAILABLE = True
except Exception:
    AVAILABLE = False
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

_FLAGS = {
    "shift": kCGEventFlagMaskShift,
    "ctrl": kCGEventFlagMaskControl,
    "alt": kCGEventFlagMaskAlternate,
    "cmd": kCGEventFlagMaskCommand,
}

UNAVAILABLE_REASON = "找不到 Quartz（pyobjc-framework-Quartz 沒裝好）"


def modifier_mask(mods):
    mask = 0
    for name in mods or []:
        mask |= _FLAGS.get(name, 0)
    return mask


class Listener:
    """在自己的執行緒上跑一個 CFRunLoop，監聽並攔截熱鍵"""

    def __init__(self, callback, keycode, mods):
        self.callback = callback
        self.keycode = keycode
        self.modifiers = modifier_mask(mods)
        self.tap = None
        self.ok = False
        self.error = ""
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
            self.error = "建立 event tap 失敗（通常是沒有輔助使用權限）"
            return
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
