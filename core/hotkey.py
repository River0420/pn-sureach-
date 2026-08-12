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
def _refresh(key, mods, label=""):
    """把目前這一組熱鍵的各種寫法算好，掛回模組上

    這些值會被 UI 到處讀，而使用者隨時可以在「設定快捷鍵…」裡換一組，
    所以不能只在 import 時算一次。讀的人一律用 hotkey.HOTKEY_LABEL 這種
    屬性存取（不要 from ... import），換了才跟得上。
    """
    global KEY, MODIFIERS, KEYCODE, HOTKEY_LABEL, HOTKEY_SPELLED
    KEY = plat.key_name(key)
    MODIFIERS = plat.mod_names(mods)
    KEYCODE = plat.key_code(KEY)
    HOTKEY_LABEL = label or plat.describe(KEY, MODIFIERS)
    # 說明畫面用的長版：「⌥⇧Space（option + shift + 空白鍵）」。
    # Windows 上 spell() 回空字串，這裡就跟短版一樣。
    spelled = plat.spell(KEY, MODIFIERS)
    HOTKEY_SPELLED = f"{HOTKEY_LABEL}（{spelled}）" if spelled else HOTKEY_LABEL


# 舊設定檔寫的是 macOS 鍵碼數字，settings._migrate() 已經在讀檔時翻成名稱了。
_refresh(settings.get("hotkey.key"),
         settings.get("hotkey.modifiers", ["alt"]),
         settings.get("hotkey.label") or "")


def save(key, mods):
    """換一組熱鍵並寫進設定檔 —— 不負責重開監聽，那是呼叫端的事

    label 一律清空，讓它跟著新組合自動產生；留著舊的會顯示成上一組。
    """
    _refresh(key, mods)
    settings._data.setdefault("hotkey", {}).update(
        key=KEY, modifiers=list(MODIFIERS), label="")
    settings.save()
    return HOTKEY_LABEL


def is_valid(key, mods):
    """能不能拿來當全域熱鍵；不行的話回一句給使用者看的原因

    至少要一個修飾鍵：不然使用者在任何地方打字都會叫出查詢視窗，
    而且那個鍵會被我們吃掉，等於整台電腦少一個按鍵。
    """
    if not plat.mod_names(mods):
        return False, "至少要搭配一個修飾鍵（⌘ ⌥ ⌃ ⇧）"
    if not key or key not in plat.KEYS:
        return False, "這個按鍵不支援，換一個試試"
    return True, ""

# 相容舊名稱（其他模組還在讀）
QUARTZ = AVAILABLE


def _listen(callback, keycode, mods):
    listener = _impl.Listener(callback, keycode, mods)
    try:
        listener.start()
    except Exception as e:
        listener.ok = False
        listener.error = str(e)
    return listener


def start(callback):
    """開始監聽熱鍵，回傳 listener

    失敗時 listener 仍然是個物件，但 `.ok` 是 False、`.error` 會有原因，
    呼叫端要把那句話講給使用者聽，不要靜靜地沒反應。
    回傳值一定要留著，之後才停得掉。
    """
    return _listen(callback, KEYCODE, MODIFIERS)


def probe(key, mods, callback):
    """暫時掛上一組熱鍵，讓使用者當場按按看能不能用

    這是「選的當下就知道」唯一兩邊都可靠的做法：

    - Windows 這一步就抓得到衝突 —— RegisterHotKey 撞到別人會直接失敗，
      listener.error 會寫「已經被其他程式註冊走了」。
    - macOS 抓不到。我們是監聽全部鍵盤事件，不是向系統註冊，所以沒有
      「這組已被佔用」這種回答可拿。真正的證據只有一個：使用者按下去，
      callback 有沒有被呼叫。

    呼叫端用完一定要 stop()，而且要先把正在跑的主監聽關掉 ——
    不然在 Windows 上拿同一組去試，會撞到自己而回報「被佔走了」。
    """
    return _listen(callback, plat.key_code(plat.key_name(key)),
                   plat.mod_names(mods))
