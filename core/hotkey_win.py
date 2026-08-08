"""Windows 全域熱鍵（RegisterHotKey）

Windows 這邊比 macOS 單純很多：作業系統有現成的全域熱鍵 API，
不需要監聽所有鍵盤事件，也**不需要任何額外權限**——
沒有「輔助使用」那一關要過。

RegisterHotKey 把熱鍵註冊在「呼叫它的那條執行緒」上，訊息也只送到那條執行緒的
訊息佇列。所以這裡開一條自己的執行緒，註冊完就在上面跑訊息迴圈；
收到 WM_HOTKEY 只做一件事 —— 呼叫 callback（由呼叫端負責丟回 Qt 主執行緒）。

對外介面由 core/hotkey.py 統一，這裡不要直接被 import。
"""

import ctypes
import threading
from ctypes import wintypes

try:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    AVAILABLE = True
except Exception:
    _user32 = _kernel32 = None
    AVAILABLE = False

UNAVAILABLE_REASON = "載入 user32.dll 失敗（這不是 Windows？）"

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000      # 按著不放不要連發

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0xA17          # 隨便挑的，只在本執行緒內要唯一

_FLAGS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "shift": MOD_SHIFT, "cmd": MOD_WIN}

# RegisterHotKey 失敗時 GetLastError 的常見值，翻成看得懂的話。
# 這是使用者在公司電腦上最可能踩到的一關，訊息要能直接指向解法。
_ERRORS = {
    1409: "這組熱鍵已經被其他程式註冊走了（換一組，改 config/settings.json 的 hotkey）",
    1400: "視窗代號無效",
    5: "被系統拒絕（權限不足，或有防護軟體擋下）",
    87: "熱鍵參數不正確",
}


def modifier_mask(mods):
    mask = MOD_NOREPEAT
    for name in mods or []:
        mask |= _FLAGS.get(name, 0)
    return mask


class Listener:
    """在自己的執行緒上註冊熱鍵並跑訊息迴圈"""

    def __init__(self, callback, keycode, mods):
        self.callback = callback
        self.keycode = keycode
        self.modifiers = modifier_mask(mods)
        self.ok = False
        self.error = ""
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()

    def _run(self):
        self._thread_id = _kernel32.GetCurrentThreadId()
        registered = _user32.RegisterHotKey(
            None, HOTKEY_ID, self.modifiers, self.keycode)
        if not registered:
            code = ctypes.get_last_error()
            self.error = _ERRORS.get(code, f"RegisterHotKey 失敗（錯誤碼 {code}）")
            self._ready.set()
            return

        self.ok = True
        self._ready.set()
        try:
            msg = wintypes.MSG()
            # GetMessage 回傳 0 代表收到 WM_QUIT，-1 是錯誤，兩種都該離開
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            _user32.UnregisterHotKey(None, HOTKEY_ID)
            self.ok = False

    def start(self):
        if not AVAILABLE:
            self.error = UNAVAILABLE_REASON
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self.ok

    def stop(self):
        """讓那條執行緒收到 WM_QUIT 自己收尾

        UnregisterHotKey 一定要在註冊它的那條執行緒上呼叫，
        所以不能從這裡直接解除，只能請它自己走完 finally。
        """
        self.ok = False
        if self._thread_id:
            try:
                _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None
