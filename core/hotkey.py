"""全域熱鍵 —— 對外的統一介面

實作分在 hotkey_mac.py（Quartz event tap）和 hotkey_win.py（RegisterHotKey），
兩邊差很多，但對 main.py 來說都只是 `start(callback)` 回傳一個有 `.ok`
和 `.stop()` 的東西。

熱鍵要改就改 config/settings.json 的 hotkey 區塊，`key` 寫名稱（"space"、
"f2"、"q"），`modifiers` 寫 ["alt"] 這種清單。舊設定檔寫 macOS 鍵碼數字的
也照樣認得。
"""

from core import plat, settings

if plat.WINDOWS:
    from core import hotkey_win as _impl
else:
    from core import hotkey_mac as _impl

AVAILABLE = _impl.AVAILABLE
UNAVAILABLE_REASON = _impl.UNAVAILABLE_REASON

# 舊設定檔寫的是 macOS 鍵碼數字，settings._migrate() 已經在讀檔時翻成名稱了，
# 所以這裡只要認得 hotkey.key 一種寫法。
KEY = plat.key_name(settings.get("hotkey.key"))
MODIFIERS = plat.mod_names(settings.get("hotkey.modifiers", ["alt"]))
KEYCODE = plat.key_code(KEY)
HOTKEY_LABEL = settings.get("hotkey.label") or plat.describe(KEY, MODIFIERS)

# 相容舊名稱（其他模組還在讀）
QUARTZ = AVAILABLE


def start(callback):
    """開始監聽熱鍵，回傳 listener

    失敗時 listener 仍然是個物件，但 `.ok` 是 False、`.error` 會有原因，
    呼叫端要把那句話講給使用者聽，不要靜靜地沒反應。
    回傳值一定要留著，之後才停得掉。
    """
    listener = _impl.Listener(callback, KEYCODE, MODIFIERS)
    try:
        listener.start()
    except Exception as e:
        listener.ok = False
        listener.error = str(e)
    return listener
