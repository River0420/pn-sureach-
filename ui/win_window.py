"""Windows 原生視窗行為

比 macOS 那邊需要做的少很多，因為 Qt 的 `Qt.Tool` 旗標在 Windows 上
本來就等於「工具視窗」：不進工作列、不進 Alt+Tab。所以這裡只補兩件
Qt 做不到的事：

1. 叫出視窗時把鍵盤焦點搶過來（Windows 預設不讓背景程式這樣做，
   但按熱鍵的那一刻系統會給我們這個資格）
2. Windows 11 的圓角

沒有原生陰影可用。無邊框視窗在 Windows 上本來就沒有系統陰影，
而 Qt 的陰影特效實測會讓每次重繪從 1ms 變成 23ms，打字直接卡住，
所以寧可沒有陰影 —— 卡片本身有邊框和圓角，看起來不會沒有邊界。

對外介面由 ui/native_window.py 統一，這裡不要直接被 import。
"""

import ctypes

try:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi")
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    AVAILABLE = True
except Exception:
    _user32 = _dwmapi = None
    AVAILABLE = False

HAS_NATIVE_SHADOW = False

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def _hwnd(widget):
    try:
        handle = int(widget.winId())
        return handle if handle else None
    except Exception:
        return None


def become_accessory():
    """Windows 不需要做什麼 —— Qt.Tool 已經讓它不出現在工作列和 Alt+Tab"""
    return True


def make_overlay(widget):
    """Windows 11 圓角。失敗也無所謂（Windows 10 沒有這個 API）"""
    if not AVAILABLE:
        return False
    handle = _hwnd(widget)
    if handle is None:
        return False
    try:
        pref = ctypes.c_int(DWMWCP_ROUND)
        _dwmapi.DwmSetWindowAttribute(
            handle, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref), ctypes.sizeof(pref))
        return True
    except Exception:
        return False      # Windows 10 會失敗，這很正常


def refresh_shadow(widget):
    """Windows 沒有要重算的原生陰影"""
    return False


def focus_without_switching(widget):
    """把鍵盤焦點搶過來

    Windows 平常禁止背景程式呼叫 SetForegroundWindow（防止畫面被搶），
    但按下註冊過的全域熱鍵時，系統會把「前景權」暫時交給收到熱鍵的程序，
    所以在這個時間點呼叫是會成功的。

    回傳 False 代表沒拿到，呼叫端要退回 Qt 自己的 activateWindow()，
    不然使用者會看到一個打不了字的視窗。
    """
    if not AVAILABLE:
        return False
    handle = _hwnd(widget)
    if handle is None:
        return False
    try:
        _user32.SetForegroundWindow(handle)
        return _user32.GetForegroundWindow() == handle
    except Exception:
        return False


def activate_app():
    """退路：Windows 上沒有「把整個 App 叫到前景」這種概念，交給 Qt 處理"""
    return False
