"""自我診斷報告

存在的理由：這個程式會被拿到一台我摸不到的電腦上跑（公司的 Windows），
出問題的時候沒辦法在那台機器上追。所以程式要能自己把「我是誰、我在哪、
哪一步壞了」寫成一段純文字，讓使用者複製起來帶走。

原則：
- 不能失敗。每一段都各自 try 起來，其中一段爆了不能害整份報告生不出來 ——
  偏偏最需要這份報告的時候，就是有東西正在爆的時候。
- 不含個資以外必要的東西。會有檔案路徑（debug 一定要），沒有料號內容。
- 純文字、可以整段複製貼上。
"""

import os
import platform
import sys
import time
import unicodedata

from core import book_config, paths, plat, settings

LOG_TAIL_LINES = 25
LABEL_WIDTH = 20


def _width(text):
    """中文字在等寬字體裡佔兩格，用 len() 對齊會歪掉"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _row(label, value):
    return f"{label}{' ' * max(1, LABEL_WIDTH - _width(label))}{value}"


def _safe(fn, default="（取不到）"):
    try:
        return fn()
    except Exception as e:
        return f"（失敗：{e}）"


def _versions():
    out = []
    for name in ("PySide6", "pandas", "openpyxl", "pyperclip"):
        try:
            mod = __import__(name)
            out.append((name, getattr(mod, "__version__", "?")))
        except Exception as e:
            out.append((name, f"沒裝或載入失敗：{type(e).__name__}"))
    return out


def _frozen():
    """是不是被 PyInstaller 打包過 —— 打包後找不到檔案的原因跟沒打包時不一樣"""
    if getattr(sys, "frozen", False):
        return f"是（bundle: {getattr(sys, '_MEIPASS', '?')}）"
    return "否（直接跑原始碼）"


def _log_tail():
    try:
        if not os.path.exists(paths.LOG_PATH):
            return ["（沒有 log 檔）"]
        with open(paths.LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-LOG_TAIL_LINES:]] or ["（log 是空的）"]
    except Exception as e:
        return [f"（讀不到 log：{e}）"]


def _data_section(price_book):
    lines = []
    try:
        snap = price_book.snapshot
        lines.append(_row("來源檔數量", len(snap.sources)))
        lines.append(_row("總筆數", f"{snap.row_count:,}"))
        lines.append(_row("載入耗時", f"{snap.elapsed:.2f} 秒"))
        for s in snap.sources:
            lines.append(f"  · {s['name']}　料號欄「{s['key_column']}」"
                         f"　{len(s['df']):,} 列　{len(s['df'].columns)} 欄")
        for err in snap.errors:
            lines.append(f"  ⚠ 載入問題：{err}")
        if not snap.sources:
            lines.append("  （還沒匯入任何檔案）")
    except Exception as e:
        lines.append(f"（讀不到資料狀態：{e}）")
    return lines


def _probe_query(price_book):
    """真的跑一次查詢，證明整條路是通的、順便量速度

    比「載入成功」有用得多 —— 載入成功但查不到東西是實際會發生的狀況
    （料號欄選錯、編碼壞掉），這一段會直接抓出來。
    """
    try:
        snap = price_book.snapshot
        if not snap.loose_keys:
            return [_row("查詢測試", "跳過（沒有資料）")]
        sample = snap.loose_display.get(snap.loose_keys[0], snap.loose_keys[0])
        t0 = time.perf_counter()
        results = price_book.search(sample)
        ms = (time.perf_counter() - t0) * 1000
        hit = "命中" if results else "查無 ⚠"
        return [_row("查詢測試",
                     f"用「{sample}」查 → {hit}，{len(results)} 筆，{ms:.3f} ms")]
    except Exception as e:
        return [_row("查詢測試", f"失敗：{type(e).__name__}: {e}")]


def report(price_book=None, hotkey_state=None):
    """產生完整報告

    price_book / hotkey_state 可以不給（例如程式還沒起來就要診斷），
    給了就多幾段內容。hotkey_state 是 {"ok": bool, "error": str, "label": str}。
    """
    from core import hotkey, permission

    L = []
    add = L.append

    add("=" * 52)
    add(f"{paths.APP_NAME}　診斷報告")
    add(time.strftime("產生時間　%Y-%m-%d %H:%M:%S"))
    add("=" * 52)

    add("")
    add("【執行環境】")
    bits = 64 if sys.maxsize > 2**32 else 32
    add(_row("作業系統", f"{plat.NAME} {_safe(platform.release)}"))
    add(_row("系統版本", _safe(platform.version)))
    add(_row("機器架構", _safe(platform.machine)))
    add(_row("Python", f"{sys.version.split()[0]}（{bits} 位元）"))
    add(_row("打包狀態", _safe(_frozen)))
    add(_row("程式位置", paths.APP_DIR))
    add(_row("設定檔位置", paths.CONFIG_DIR))

    add("")
    add("【套件】")
    for name, ver in _versions():
        add(_row(name, ver))

    add("")
    add("【熱鍵】")
    add(_row("設定", f"{hotkey.HOTKEY_LABEL}"
                     f"（key={hotkey.KEY} modifiers={hotkey.MODIFIERS}）"))
    add(_row("這個平台的鍵碼", hotkey.KEYCODE))
    add(_row("後端可用",
             "是" if hotkey.AVAILABLE else "否 —— " + hotkey.UNAVAILABLE_REASON))
    if hotkey_state is None:
        add(_row("目前狀態", "（不知道，程式沒把狀態傳進來）"))
    elif hotkey_state.get("ok"):
        add(_row("目前狀態", "已掛上 ✓"))
        revived = hotkey_state.get("revived", 0)
        if revived:
            # 這一行是在回答「為什麼有時候按了沒反應」。
            # macOS 對會吃掉按鍵的 event tap 有逾時限制，回呼太慢就整個停用；
            # 程式每秒檢查一次再開回來，但被停用的那段時間按的鍵是真的丟了。
            add(_row("被系統停用又救回", f"{revived} 次 ⚠"))
            add(_row("這代表什麼", "偶爾按了沒反應是這個造成的，"
                                   "被停用的那一兩秒內按的鍵會漏掉"))
    else:
        add(_row("目前狀態", f"沒掛上 ⚠　{hotkey_state.get('error') or '原因不明'}"))
        add(_row("解法", "選單列圖示 →「設定快捷鍵…」換一組（可以當場試按確認）"))

    add("")
    add("【權限】")
    if permission.NEEDED:
        try:
            trusted = "已授權" if permission.is_trusted() else "未授權 ⚠"
        except Exception as e:
            trusted = f"查不到（{e}）"
        add(_row("輔助使用權限", trusted))
        add(_row("權限記在誰身上", _safe(permission.responsible_app) or "（不確定）"))
    else:
        add(f"{plat.NAME} 不需要額外權限就能用全域熱鍵")

    add("")
    add("【資料】")
    try:
        # 還沒匯入過任何東西時 load() 回的是 None，不是空字典 ——
        # 直接 .get() 會變成一句看不懂的 'NoneType' 錯誤，
        # 而「還沒匯入」其實是全新安裝最normal的狀態，不該長得像故障。
        cfg = book_config.load() or {}
        add(_row("設定檔來源數", len(cfg.get("sources", []))))
    except Exception as e:
        add(_row("設定檔", f"讀不到：{e}"))
    if price_book is not None:
        for line in _data_section(price_book):
            add(line)
        for line in _probe_query(price_book):
            add(line)
    else:
        add("（程式尚未載入資料）")

    add("")
    add("【設定】")
    for key in ("window.width", "window.anchor", "window.list_rows",
                "data.result_limit", "data.max_rows_per_source"):
        add(_row(key, _safe(lambda k=key: settings.get(k))))

    add("")
    add(f"【最近 {LOG_TAIL_LINES} 行 log】")
    for line in _log_tail():
        add(line)

    add("")
    add("=" * 52)
    add("把整段複製起來就可以拿去問了。")
    return "\n".join(L)
