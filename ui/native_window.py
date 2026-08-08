"""原生視窗行為 —— 對外的統一介面

實作分在 mac_window.py 和 win_window.py。兩邊要做的事差很多
（macOS 要把 App 降級成 accessory、要自己維護陰影；Windows 靠 Qt.Tool
就夠了但要搶前景權），但呼叫端只看到同一組函式。

每個函式都回傳 bool：成功了沒。呼叫端不該假設一定成功 ——
在 offscreen 測試環境、在缺套件的機器上，這些通通會回 False，
程式必須還是能跑。
"""

from core import plat

if plat.WINDOWS:
    from ui import win_window as _impl
else:
    from ui import mac_window as _impl

AVAILABLE = _impl.AVAILABLE
HAS_NATIVE_SHADOW = _impl.HAS_NATIVE_SHADOW

become_accessory = _impl.become_accessory
make_overlay = _impl.make_overlay
refresh_shadow = _impl.refresh_shadow
focus_without_switching = _impl.focus_without_switching
activate_app = _impl.activate_app
