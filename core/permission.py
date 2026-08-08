"""輔助使用（Accessibility）權限 —— 只有 macOS 需要

Windows 的 RegisterHotKey 不需要任何額外權限，所以在 Windows 上這個模組
整個是空殼：`NEEDED` 是 False，`is_trusted()` 永遠回 True，
main.py 靠 `NEEDED` 決定要不要顯示那一整串權限引導。

以下說明只適用 macOS。

全域熱鍵要靠這個權限才能監聽鍵盤。macOS 把權限記在「啟動這個程式的那個 App」
身上（responsible process），所以從 Terminal 啟動就要授權 Terminal、包成 .app
之後就是授權那個 .app —— 換一種啟動方式權限就得重給一次。

沒授權時 pynput 只會在背景印一行警告，使用者按了熱鍵完全沒反應也不知道為什麼。
這個模組負責把它變成看得見、而且能一路點下去解決的流程。
"""

import ctypes
import ctypes.util
import os
import subprocess

from core import plat

SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)

if plat.MACOS:
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
        AVAILABLE = True
    except Exception:
        AVAILABLE = False
else:
    AVAILABLE = False

# 這個平台到底需不需要跟使用者要權限
NEEDED = plat.MACOS and AVAILABLE


def is_trusted():
    if not AVAILABLE:
        return True     # 不是 macOS 就不擋
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return True


def request(prompt=True):
    """跳出系統那個「要不要開啟輔助使用」的對話框"""
    if not AVAILABLE:
        return False
    try:
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))
    except Exception:
        return False


def responsible_app():
    """權限實際上是記在誰身上

    macOS 不是看「這個 Python 程序」，而是看「是誰啟動它的」（responsible
    process）。從終端機啟動就是終端機、從 Finder 雙擊 .app 就是那個 .app。
    直接把答案問出來，使用者才不用猜要在清單裡打開哪一個。
    """
    try:
        lib = ctypes.CDLL(ctypes.util.find_library("System"))
        func = lib.responsibility_get_pid_responsible_for_pid
        func.argtypes = [ctypes.c_int]
        func.restype = ctypes.c_int
        pid = func(os.getpid())
        if pid <= 0:
            return None
        path = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
        if not path:
            return None
        # /A/B/Foo.app/Contents/MacOS/foo -> Foo
        for part in path.split("/"):
            if part.endswith(".app"):
                return part[:-4]
        return os.path.basename(path)
    except Exception:
        return None


def open_settings():
    try:
        subprocess.Popen(["open", SETTINGS_URL])
        return True
    except Exception:
        return False
