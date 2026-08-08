"""跑在哪個作業系統，以及跨平台的按鍵名稱對照

熱鍵的鍵碼在 macOS 和 Windows 上是兩套完全不同的數字（Space 在 macOS 是 49，
在 Windows 是 0x20）。與其讓使用者去查表，settings.json 裡一律寫**名稱**
（"space"、"f2"、"q"），由這裡翻成當下平台要的數字。

舊的設定檔寫的是 macOS 鍵碼數字，在 macOS 上照樣認得，不會因為升級就壞掉。
"""

import sys

MACOS = sys.platform == "darwin"
WINDOWS = sys.platform.startswith("win")
LINUX = not MACOS and not WINDOWS

NAME = "macOS" if MACOS else ("Windows" if WINDOWS else "Linux")

# 修飾鍵的顯示方式：macOS 用符號，Windows 用文字
if MACOS:
    MOD_LABELS = {"ctrl": "⌃", "alt": "⌥", "shift": "⇧", "cmd": "⌘"}
    MOD_JOIN = ""
    MOD_ORDER = ["ctrl", "alt", "shift", "cmd"]     # macOS 慣例 ⌃⌥⇧⌘
else:
    MOD_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "cmd": "Win"}
    MOD_JOIN = "+"
    MOD_ORDER = ["ctrl", "alt", "shift", "cmd"]

# 使用者可能寫的各種別名 → 內部統一名稱
MOD_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt",
    "shift": "shift",
    "cmd": "cmd", "command": "cmd", "win": "cmd", "super": "cmd", "meta": "cmd",
}

# 按鍵名稱 → (macOS 鍵碼, Windows 虛擬鍵碼)
KEYS = {
    "space": (49, 0x20), "return": (36, 0x0D), "enter": (36, 0x0D),
    "tab": (48, 0x09), "esc": (53, 0x1B), "escape": (53, 0x1B),
    "delete": (51, 0x08), "backspace": (51, 0x08),
    "f1": (122, 0x70), "f2": (120, 0x71), "f3": (99, 0x72), "f4": (118, 0x73),
    "f5": (96, 0x74), "f6": (97, 0x75), "f7": (98, 0x76), "f8": (100, 0x77),
    "f9": (101, 0x78), "f10": (109, 0x79), "f11": (103, 0x7A), "f12": (111, 0x7B),
    "a": (0, 0x41), "b": (11, 0x42), "c": (8, 0x43), "d": (2, 0x44),
    "e": (14, 0x45), "f": (3, 0x46), "g": (5, 0x47), "h": (4, 0x48),
    "i": (34, 0x49), "j": (38, 0x4A), "k": (40, 0x4B), "l": (37, 0x4C),
    "m": (46, 0x4D), "n": (45, 0x4E), "o": (31, 0x4F), "p": (35, 0x50),
    "q": (12, 0x51), "r": (15, 0x52), "s": (1, 0x53), "t": (17, 0x54),
    "u": (32, 0x55), "v": (9, 0x56), "w": (13, 0x57), "x": (7, 0x58),
    "y": (16, 0x59), "z": (6, 0x5A),
}

# 反查：macOS 鍵碼 → 名稱（給舊設定檔和顯示用）
_BY_MAC = {mac: name for name, (mac, _) in KEYS.items()}


def key_name(value, default="space"):
    """把設定檔裡的值正規化成按鍵名稱

    接受三種寫法：名稱字串（"space"）、macOS 鍵碼數字（49，舊設定檔）、
    以及 None（用預設）。認不出來就退回預設，不要讓程式因為打錯字就沒熱鍵。
    """
    if value is None:
        return default
    if isinstance(value, str):
        name = value.strip().lower()
        return name if name in KEYS else default
    try:
        return _BY_MAC.get(int(value), default)
    except (TypeError, ValueError):
        return default


def key_code(name):
    """按鍵名稱 → 當下平台要的鍵碼"""
    mac, win = KEYS.get(name, KEYS["space"])
    return mac if MACOS else win


def mod_names(values):
    """把設定檔的修飾鍵清單正規化，順序固定、不重複"""
    got = set()
    for v in values or []:
        name = MOD_ALIASES.get(str(v).strip().lower())
        if name:
            got.add(name)
    return [m for m in MOD_ORDER if m in got]


def describe(key, mods):
    """給使用者看的熱鍵寫法：macOS 是 ⌥Space，Windows 是 Alt+Space"""
    parts = [MOD_LABELS[m] for m in mods]
    label = key.upper() if len(key) == 1 else key.capitalize()
    if MOD_JOIN:
        return MOD_JOIN.join(parts + [label])
    return "".join(parts) + label
