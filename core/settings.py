"""使用者可調的設定 —— 排版、配色、視窗尺寸、熱鍵、資料上限都在這裡

程式裡任何「數字」或「顏色」都不該直接寫死在各個模組，一律從這裡拿。
想微調畫面就改 config/settings.json，改完重開程式即可，不用碰程式碼。
沒有 settings.json 也能跑，全部走 DEFAULTS。

新增設定項就往 DEFAULTS 加一層 key；使用者的舊設定檔會自動補上新欄位
（deep merge），不會因為少一個 key 就壞掉。
"""

import copy
import json
import os

from core import paths, plat

VERSION = 2

DEFAULTS = {
    "version": VERSION,

    # ---------- 熱鍵 ----------
    "hotkey": {
        # 按鍵名稱，macOS 和 Windows 通用：space / return / esc / tab /
        # f1~f12 / a~z。程式會自己翻成各平台的鍵碼。
        "key": "space",
        # 可填 cmd(win) / alt(option) / ctrl / shift，可複選。
        # 預設用三顆是刻意的：Alt+Space 在 Windows 上是系統的視窗選單，
        # 也是很多常駐工具（輸入法、截圖、啟動器）搶著註冊的熱門組合，
        # 加一顆 Shift 幾乎就不會撞到了。
        "modifiers": ["shift", "alt"],
        # 留空字串代表自動產生（macOS 顯示 ⌥⇧Space，Windows 顯示 Alt+Shift+Space）
        "label": "",
    },

    # ---------- 查詢視窗 ----------
    "window": {
        "width": 420,
        "padding_x": 22,          # 卡片左右內距
        "padding_top": 20,
        "padding_bottom": 20,
        "anchor": "top-right",    # top-right / top-left / top-center / center
        "edge_x": 14,             # 離螢幕邊緣
        "edge_y": 8,
        "radius": 14,
        # native = 用 macOS 原生陰影（快）；none = 不要陰影
        "shadow": "native",
        "field_label_width": 92,  # 左邊欄位名稱的固定寬度
        # 料號右邊那顆小標籤的字。留空 = 不顯示。
        # 以後真的接了 DigiKey / Mouser API，才需要標出這筆價格是哪來的。
        "source_badge": "",
        "prefill_max_chars": 64,  # 剪貼簿超過這個長度就不自動帶入
        "divider_gap_top": 14,    # 輸入框與分隔線的距離
        "divider_gap_bottom": 16,
        "row_gap": 9,             # 欄位之間
        "hero_gap": 14,           # 主要欄位與其餘欄位之間

        # ---------- 邊打邊找的清單 ----------
        "list_rows": 6,           # 一次列幾筆（跟 data.result_limit 取小的）
        "list_fields": 2,         # 每一列右邊帶幾個欄位當摘要
        "list_row_gap": 2,        # 列與列之間
        "list_sep": "  ·  ",      # 摘要欄位之間的分隔符號
        # 0 = 每按一個鍵就找（查詢只要 0.02ms，不需要延遲）。
        # 資料非常大又想更省的話可以設 60~120。
        "search_debounce_ms": 0,
    },

    # ---------- 配色與字級 ----------
    "theme": {
        "bg": "#FAF9F5",
        "surface": "#FFFFFF",
        "border": "#E8E4DA",
        "border_soft": "#F0EDE5",
        "text": "#2B2A26",
        "text_soft": "#6B675C",
        "text_muted": "#9B9689",
        "accent": "#C96442",
        "accent_hover": "#B85838",
        "accent_soft": "#F6EAE3",
        "green": "#5A7D5A",
        "danger": "#B0483A",

        "base_size": 13,          # App 全域字級（pt）
        "search_size": 19,        # 以下都是 px
        "part_number_size": 16,
        "hero_size": 21,
        "field_label_size": 12,
        "field_value_size": 13,
        "hint_size": 13,
        "error_size": 15,
        "badge_size": 10,
        "list_key_size": 14,      # 清單左邊的料號
        "list_value_size": 13,    # 清單右邊的摘要
        "list_row_padding": 7,    # 清單每一列的上下內距
    },

    # ---------- 資料 ----------
    "data": {
        "max_sources": 3,             # 最多幾個來源檔（上限 5）
        "max_rows_per_source": 0,     # 0 = 不限；設 200000 就只讀前 20 萬列
        "warn_rows": 300000,          # 超過這個列數在匯入畫面提醒
        "header_scan_rows": 12,       # 猜「欄位名稱在第幾列」時往下看幾列
        "result_limit": 6,            # 邊打邊找最多列幾筆
        "search_min_len": 1,          # 打幾個字就開始找
        "substring_min_len": 2,       # 幾個字以上才做「中間包含」比對
        "cache": True,                # 把解析過的 Excel 快取起來，第二次開機秒開
        "cache_keep": 24,             # 快取檔數量上限
        "csv_encodings": ["utf-8-sig", "cp950", "utf-8", "latin-1"],
    },

    # ---------- 程式行為 ----------
    "app": {
        "lock_port": 49731,
        "permission_poll_ms": 2000,
    },
}


def _merge(base, override):
    """使用者設定蓋在預設值上；使用者沒寫的 key 一律沿用預設"""
    out = copy.deepcopy(base)
    if not isinstance(override, dict):
        return out
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _migrate(data):
    """舊版設定檔升級

    v1 → v2：熱鍵從 macOS 的 virtual keycode 數字改成跨平台的按鍵名稱。
    在這裡就翻好，後面的程式碼只要認得 `key` 一種寫法。
    """
    if not isinstance(data, dict):
        return {}
    hk = data.get("hotkey")
    if isinstance(hk, dict) and "keycode" in hk:
        code = hk.pop("keycode")
        hk.setdefault("key", plat.key_name(code))
    return data


def _read():
    try:
        with open(paths.SETTINGS_PATH, encoding="utf-8") as f:
            return _migrate(json.load(f))
    except FileNotFoundError:
        return {}
    except Exception:
        # 設定檔壞掉不該讓程式打不開 —— 退回預設值繼續跑
        return {}


_data = _merge(DEFAULTS, _read())


def all():
    return _data


def get(dotted, default=None):
    """settings.get("window.width")"""
    node = _data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def section(name):
    value = get(name)
    return value if isinstance(value, dict) else {}


def save(data=None):
    """把目前（或指定的）設定寫回 settings.json"""
    paths.ensure(paths.CONFIG_DIR)
    payload = _data if data is None else _merge(DEFAULTS, data)
    with open(paths.SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def write_defaults_if_missing():
    """第一次啟動時把完整預設值寫出來，使用者才知道有哪些東西可以改"""
    if not os.path.exists(paths.SETTINGS_PATH):
        try:
            save(_data)
        except Exception:
            pass
