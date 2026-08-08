"""macOS 原生視窗行為

預設的 Qt App 是「一般應用程式」，叫出視窗時 macOS 會做完整的 App 切換：
Dock 跳、選單列換掉、視窗如果在別的桌面還會把整個桌面切過去。
對常駐小工具來說這很擾人，所以這裡把它降級成 accessory，
再把彈窗改成不搶焦點的浮動面板。
"""

from ctypes import c_void_p

try:
    import objc
    from AppKit import (
        NSApp,
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSStatusWindowLevel,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorStationary,
    )
    AVAILABLE = True
except Exception:
    AVAILABLE = False

# NSWindowStyleMaskNonactivatingPanel —— 能收鍵盤但不會讓整個 App 變成前景
NONACTIVATING_PANEL = 1 << 7


def become_accessory():
    """變成選單列小工具：不進 Dock、不進 ⌘Tab、不會把使用者的畫面切走"""
    if not AVAILABLE:
        return False
    try:
        NSApplication.sharedApplication()
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        return True
    except Exception:
        return False


def _is_cocoa():
    """winId() 只有在 cocoa 平台才是 NSView

    不檢查就直接轉型的話，換成別的 QPA 平台（測試用的 offscreen、
    未來的 Windows 版）會拿到不是 NSView 的指標，直接 segfault。
    """
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    return app is not None and app.platformName() == "cocoa"


def _ns_window(widget):
    if not _is_cocoa():
        return None
    try:
        view = objc.objc_object(c_void_p=int(widget.winId()))
        return view.window()
    except Exception:
        return None


def make_overlay(widget):
    """讓這個視窗浮在所有東西上面，包含全螢幕的 App，而且跟著目前的桌面走"""
    if not AVAILABLE:
        return False
    window = _ns_window(widget)
    if window is None:
        return False
    try:
        window.setStyleMask_(window.styleMask() | NONACTIVATING_PANEL)
        window.setLevel_(NSStatusWindowLevel)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        window.setHidesOnDeactivate_(False)
        return True
    except Exception:
        return False


def refresh_shadow(widget):
    """視窗大小變了要叫 macOS 重算陰影，不然會殘留上一次的輪廓

    我們用的是原生陰影（GPU 畫的，幾乎不花時間），不是 Qt 的
    QGraphicsDropShadowEffect —— 那個每次重繪要 20ms 以上，打字會頓。
    """
    if not AVAILABLE:
        return False
    window = _ns_window(widget)
    if window is None:
        return False
    try:
        window.invalidateShadow()
        return True
    except Exception:
        return False


def focus_without_switching(widget):
    """只把鍵盤交給這個視窗，不動使用者原本的前景 App

    回傳 False 代表沒拿到鍵盤，呼叫端要退回一般的搶焦點做法，
    不然使用者會看到一個打不了字的視窗。
    """
    if not AVAILABLE:
        return False
    window = _ns_window(widget)
    if window is None:
        return False
    try:
        window.orderFrontRegardless()
        window.makeKeyWindow()
        return bool(window.isKeyWindow())
    except Exception:
        return False


def activate_app():
    """退路：真的拿不到鍵盤時，才用一般的方式把 App 叫到前景"""
    if not AVAILABLE:
        return False
    try:
        NSApplication.sharedApplication()
        NSApp.activateIgnoringOtherApps_(True)
        return True
    except Exception:
        return False
