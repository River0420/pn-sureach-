"""本地 Price Book 的讀檔、索引與查詢

這個模組完全不碰 Qt，也不碰任何 UI —— 它可以在背景執行緒整包跑完，
主執行緒只負責把做好的結果（Snapshot）換上去。這是資料量大也不會卡的關鍵。
"""

import hashlib
import numbers
import os
import re
import shutil
import time
from bisect import bisect_left
from collections import Counter

import pandas as pd

from core import book_config, paths, settings

# 從 Outlook / PDF / 網頁複製料號時常常夾帶的雜訊字元
_NOISE = re.compile(r"[\s\-_/\\.,;:#*+()\[\]{}'\"]+")

MAX_ROWS = settings.get("data.max_rows_per_source", 0)

# 邊打邊找：打幾個字開始找、一次列幾筆、幾個字以上才做「包含」比對
RESULT_LIMIT = settings.get("data.result_limit", 6)
SEARCH_MIN_LEN = settings.get("data.search_min_len", 1)
SUBSTRING_MIN_LEN = settings.get("data.substring_min_len", 2)

CACHE_VERSION = 1

STATUS_LOADING = "loading"
STATUS_EMPTY = "empty"
STATUS_READY = "ready"
STATUS_ERROR = "error"

EXCEL_EXTS = (".xlsx", ".xlsm", ".xls")


# --------------------------------------------------------------- 讀檔

def _read_csv(path, header_row):
    """CSV 編碼一個一個試 —— 台灣 ERP 匯出的多半是 Big5(cp950)，不是 UTF-8"""
    last = None
    for encoding in settings.get("data.csv_encodings", ["utf-8-sig", "cp950"]):
        try:
            return pd.read_csv(path, header=header_row, encoding=encoding)
        except UnicodeDecodeError as e:
            last = e
            continue
    raise last or UnicodeDecodeError("csv", b"", 0, 1, "無法判斷這個 CSV 的編碼")


def read_table(path, sheet=None, header_row=0):
    ext = os.path.splitext(path)[1].lower()
    if ext in EXCEL_EXTS:
        df = pd.read_excel(path, sheet_name=sheet or 0, header=header_row)
    else:
        df = _read_csv(path, header_row)
    if MAX_ROWS and len(df) > MAX_ROWS:
        df = df.head(MAX_ROWS)
    return df


def _cache_key(path, sheet, header_row):
    stat = os.stat(path)
    raw = "|".join(str(x) for x in (
        CACHE_VERSION, os.path.abspath(path), stat.st_mtime_ns, stat.st_size,
        sheet, header_row, MAX_ROWS, pd.__version__,
    ))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _prune_cache():
    keep = settings.get("data.cache_keep", 24)
    try:
        files = [os.path.join(paths.CACHE_DIR, f)
                 for f in os.listdir(paths.CACHE_DIR) if f.endswith(".pkl")]
        if len(files) <= keep:
            return
        files.sort(key=os.path.getmtime)
        for old in files[:len(files) - keep]:
            os.remove(old)
    except Exception:
        pass


def read_table_cached(path, sheet=None, header_row=0):
    """解析過的表格存成 pickle，檔案沒變動就直接讀快取

    Excel 解析是整個流程最慢的一段（10 萬列約 2.4 秒），
    快取之後第二次開機幾乎是瞬間。來源檔一改動 key 就變了，不會讀到舊資料。
    """
    if not settings.get("data.cache", True):
        return read_table(path, sheet, header_row)

    try:
        cache_path = os.path.join(paths.CACHE_DIR, _cache_key(path, sheet, header_row) + ".pkl")
    except OSError:
        return read_table(path, sheet, header_row)

    if os.path.exists(cache_path):
        try:
            df = pd.read_pickle(cache_path)
            os.utime(cache_path, None)      # 標記為最近使用過，不要被清掉
            return df
        except Exception:
            try:
                os.remove(cache_path)
            except OSError:
                pass

    df = read_table(path, sheet, header_row)
    try:
        paths.ensure(paths.CACHE_DIR)
        df.to_pickle(cache_path)
        _prune_cache()
    except Exception:
        pass
    return df


PROBE_COLS = 64


def _read_raw(path, sheet, rows):
    """不套標題列，原封不動讀前幾列 —— 用來猜欄位名稱在哪一列"""
    ext = os.path.splitext(path)[1].lower()
    if ext in EXCEL_EXTS:
        return pd.read_excel(path, sheet_name=sheet or 0, header=None, nrows=rows)
    # CSV 一定要自己給欄位數：pandas 是拿第一行來決定有幾欄，
    # 而抬頭那行往往只有一格，後面真正的欄位名稱那行就會整個被吃掉。
    for encoding in settings.get("data.csv_encodings", ["utf-8-sig", "cp950"]):
        try:
            return pd.read_csv(path, header=None, nrows=rows, encoding=encoding,
                               names=range(PROBE_COLS), engine="python")
        except UnicodeDecodeError:
            continue
    raise ValueError("無法判斷這個 CSV 的編碼")


def detect_header_row(path, sheet=None, scan=None):
    """猜欄位名稱在第幾列（0 起算）

    ERP 匯出的 Excel 常常前面有標題、日期、公司抬頭那幾列，欄位名稱不在第一列，
    直接讀就會把「報表日期」當成欄位名。這裡先讀前幾列來判斷，
    使用者就不用自己數是第幾列 —— 絕大多數檔案都是第 1 列，猜對了他根本不用管。

    判斷標準：格子填得最滿、彼此不重複、而且大部分是文字（欄位名稱幾乎都是文字，
    資料列常常有一堆數字）。同分取最上面那一列。猜不出來就回 0。
    """
    scan = scan or settings.get("data.header_scan_rows", 12)
    try:
        raw = _read_raw(path, sheet, scan)
    except Exception:
        return 0
    if raw.empty:
        return 0

    best, best_score = 0, -1
    for i in range(len(raw)):
        values = [v for v in raw.iloc[i].tolist() if not pd.isna(v)
                  and str(v).strip() != ""]
        if not values:
            continue
        texts = [str(v).strip() for v in values]
        if len(set(texts)) != len(texts):
            continue                       # 欄位名稱不會重複
        wordy = sum(1 for v in values if isinstance(v, str))
        if wordy * 2 < len(values):
            continue                       # 一半以上是數字，這比較像資料列
        score = len(values) * 10 + wordy
        if score > best_score:
            best, best_score = i, score
    return best


def list_sheets(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in EXCEL_EXTS:
        return pd.ExcelFile(path).sheet_names
    return []


# --------------------------------------------------------------- 正規化

def _halfwidth(text):
    """全形轉半形 —— 從 Word / 中文輸入法貼過來的料號常常是全形"""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def norm(value):
    """料號正規化 —— 跨檔案比對的共同標準

    Excel 有時把純數字料號讀成 float（1234 -> 1234.0），
    不處理的話兩個檔案就對不起來。
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _halfwidth(str(value)).strip().upper()


def loose(value):
    """寬鬆比對用 —— 再把符號和空白全部拿掉

    STM32-F103 C8T6、stm32f103c8t6、ＳＴＭ32F103C8T6 都會收斂成同一個字串。
    真的收斂成空字串（例如純中文品名）就退回 norm，不要製造假的碰撞。
    """
    text = norm(value)
    stripped = _NOISE.sub("", text)
    return stripped or text


def format_value(value, decimal=False):
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    # numpy 的 int64 不是 python int，要用 numbers 才抓得到，不然庫存不會加千分位
    if isinstance(value, numbers.Number) and not isinstance(value, bool):
        return f"{value:,.2f}" if decimal else f"{int(round(value)):,}"
    return str(value).strip()


def decimal_columns(df):
    """哪些欄位要顯示小數

    只看 dtype 不夠：整數欄位只要有一格空白，pandas 就會讀成 float，
    庫存 1234 會變成 1,234.00。所以實際看值有沒有小數部分。
    """
    out = set()
    for column in df.columns:
        series = df[column]
        if not pd.api.types.is_float_dtype(series):
            continue
        values = series.dropna()
        if len(values) == 0:
            continue
        try:
            if bool((values % 1 == 0).all()):
                continue        # 全是整數，只是被 NaN 逼成 float
        except TypeError:
            pass
        out.add(str(column))
    return out


# --------------------------------------------------------------- 索引

def build_indexes(df, key_column):
    """一次掃完就把三個索引都做出來

    刻意用 .tolist() 先把整欄拉成 python list 再跑迴圈：
    逐列 df.iloc[i][col] 取值在 10 萬列會多花 1.5 秒，這樣只要 0.1 秒。

    回傳 (精確索引, 去符號索引, 去符號 -> 原始寫法)。重複料號取最後一筆。
    """
    exact, loose_index, display = {}, {}, {}
    if key_column not in df.columns:
        return exact, loose_index, display

    values = df[key_column].tolist()
    for pos, value in enumerate(values):
        k = norm(value)
        if not k:
            continue
        exact[k] = pos
        lk = _NOISE.sub("", k) or k
        loose_index[lk] = pos
        if lk not in display:
            display[lk] = str(value).strip()
    return exact, loose_index, display


def build_key_index(df, key_column):
    return build_indexes(df, key_column)[0]


def field_labels(display_columns, source_names):
    """欄位標籤 —— 不同檔案有同名欄位時，補上檔名才分得出來"""
    counts = Counter(d["column"] for d in display_columns)
    out = []
    for d in display_columns:
        label = d["column"]
        if counts[label] > 1:
            short = source_names.get(d["source"], d["source"])
            out.append((d["source"], d["column"], f"{label}（{short}）"))
        else:
            out.append((d["source"], d["column"], label))
    return out


# --------------------------------------------------------------- 匯入

def import_sources(sources, display_columns):
    """把每個來源檔複製一份到 data/，並存下欄位對應設定

    sources: [{id, src_path, sheet, header_row, key_column}]
    display_columns: [{source, column}]，順序就是彈窗顯示順序
    """
    paths.ensure(book_config.DATA_DIR)
    saved = []
    for s in sources:
        ext = os.path.splitext(s["src_path"])[1].lower()
        dest = os.path.join(book_config.DATA_DIR, f"source_{s['id']}{ext}")
        if os.path.abspath(s["src_path"]) != os.path.abspath(dest):
            shutil.copy2(s["src_path"], dest)
        saved.append({
            "id": s["id"],
            "name": s.get("name") or os.path.basename(s["src_path"]),
            "path": dest,
            "source_path": s["src_path"],
            "sheet": s.get("sheet"),
            "header_row": s.get("header_row", 0),
            "key_column": s["key_column"],
        })
    config = {
        "version": book_config.VERSION,
        "sources": saved,
        "display_columns": list(display_columns),
    }
    book_config.save(config)
    return config


# --------------------------------------------------------------- 快照

class Snapshot:
    """一次載入的完整結果 —— 在背景執行緒做好，再整包換給主執行緒

    做成不可變的快照，就不會有「載到一半被查詢」的中間狀態。
    """

    def __init__(self, config=None, sources=None, errors=None, elapsed=0.0):
        self.config = config
        self.sources = sources or []
        self.errors = errors or []
        self.elapsed = elapsed
        self.loose_keys = []
        self.loose_display = {}
        if self.sources:
            self._build_suggest_index()

    def _build_suggest_index(self):
        display = {}
        for source in self.sources:
            for lk, raw in source["display"].items():
                if lk not in display:
                    display[lk] = raw
        self.loose_display = display
        self.loose_keys = sorted(display)

    @property
    def row_count(self):
        return sum(len(s["df"]) for s in self.sources)


def build_snapshot():
    """讀檔 + 建索引，全部在呼叫端的執行緒上跑（可以是背景執行緒）"""
    started = time.perf_counter()
    config = book_config.load()
    if not config:
        return Snapshot()

    loaded, errors = [], []
    for s in config.get("sources", []):
        name = s.get("name") or os.path.basename(s.get("path") or "?")
        path = s.get("path")
        if not path or not os.path.exists(path):
            errors.append(f"{name}：找不到檔案")
            continue
        try:
            df = read_table_cached(path, s.get("sheet"), s.get("header_row", 0))
        except Exception as e:
            errors.append(f"{name}：讀取失敗（{e}）")
            continue
        key = s.get("key_column")
        if key not in df.columns:
            errors.append(f"{name}：找不到料號欄位「{key}」")
            continue
        exact, loose_index, display = build_indexes(df, key)
        loaded.append({
            "id": s["id"],
            "name": name,
            "key_column": key,
            "df": df,
            "index": exact,
            "loose_index": loose_index,
            "display": display,
            "decimal": decimal_columns(df),
        })

    elapsed = time.perf_counter() - started
    if not loaded:
        return Snapshot(errors=errors, elapsed=elapsed)
    return Snapshot(config=config, sources=loaded, errors=errors, elapsed=elapsed)


# --------------------------------------------------------------- 查詢

class LocalPriceBook:
    """把多個來源檔以共用料號串起來的查詢索引

    本身只持有一份 Snapshot。載入是外面的事（可以丟到背景執行緒），
    做好之後呼叫 apply() 換上去，換的瞬間是一個指派，不會卡到 UI。
    """

    def __init__(self, snapshot=None):
        self._snap = snapshot or Snapshot()
        self._loading = False

    # ---------- 狀態 ----------
    def mark_loading(self):
        self._loading = True

    def apply(self, snapshot):
        self._snap = snapshot
        self._loading = False

    def reload(self):
        """同步載入 —— 只在測試或沒有 UI 的場合用"""
        self.apply(build_snapshot())

    @property
    def snapshot(self):
        return self._snap

    @property
    def is_configured(self):
        return bool(self._snap.sources)

    @property
    def status(self):
        """回傳 (狀態, 給使用者看的一句話)"""
        if self._loading:
            return STATUS_LOADING, "資料載入中…"
        snap = self._snap
        if snap.sources:
            if snap.errors:
                return STATUS_READY, "有檔案沒載入成功：" + "；".join(snap.errors)
            return STATUS_READY, None
        if snap.errors:
            return STATUS_ERROR, "；".join(snap.errors)
        return STATUS_EMPTY, None

    @property
    def display_columns(self):
        return [label for _, _, label in self._labels()]

    # ---------- 內部 ----------
    def _labels(self):
        snap = self._snap
        if not snap.config:
            return []
        names = {s["id"]: s["name"] for s in snap.sources}
        return field_labels(snap.config.get("display_columns", []), names)

    def _rows_for(self, index_name, key):
        rows = {}
        for s in self._snap.sources:
            pos = s[index_name].get(key)
            rows[s["id"]] = None if pos is None else s["df"].iloc[pos]
        return rows if any(r is not None for r in rows.values()) else None

    # ---------- 對外 ----------
    def _result(self, rows, typed=None):
        """把命中的那幾列組成彈窗要的字典

        lookup()（單筆精確查詢）和 search()（邊打邊找）共用這一段，
        兩邊的顯示格式才不會有一天長得不一樣。
        """
        snap = self._snap
        by_id = {s["id"]: s for s in snap.sources}
        display_key = (typed or "").strip()
        for s in snap.sources:
            row = rows[s["id"]]
            if row is not None:
                display_key = str(row[s["key_column"]]).strip()
                break

        fields = []
        for sid, col, label in self._labels():
            row = rows.get(sid)
            src = by_id.get(sid)
            if row is None or src is None or col not in row.index:
                fields.append((label, ""))
            else:
                fields.append((label, format_value(row[col], col in src["decimal"])))

        typed = str(typed).strip() if typed else ""
        return {
            "_key": display_key,
            "_fields": fields,
            "_matched": [s["name"] for s in snap.sources if rows.get(s["id"]) is not None],
            "_missing": [s["name"] for s in snap.sources if rows.get(s["id"]) is None],
            # 忽略符號差異才對上的話要講出來，不能讓人誤以為是逐字命中
            "_typed": typed if typed and typed != display_key else None,
        }

    def candidates(self, text, limit=None):
        """邊打邊找要顯示哪幾筆料號（回傳去符號後的 key，已排好順序）

        順序就是「像不像」的順序，四個階段，湊滿就停：
        1. 完全一樣
        2. 開頭符合 —— 打 STM32F103 想找 STM32F103C8T6，這是最常見的情境
        3. 把使用者打的字尾去掉再找 —— 貼進來的是 STM32F103C8T6TR，
           實際料號是 STM32F103C8T6
        4. 中間包含 —— 只記得料號中間那段的時候（打 358 找 LM358DR）

        第 4 段是唯一會掃全部 key 的，所以只有在前面三段「一筆都沒中」
        才會走到。前面中了一筆但沒湊滿 limit 也不補 —— 補的代價是掃完
        整份索引（15 萬列 3.6ms），而那正好是「打完整料號」的情況，
        也就是最常按到的那一次。開頭有中就已經是最好的答案了。
        """
        limit = limit or RESULT_LIMIT
        snap = self._snap
        q = loose(text)
        if len(q) < SEARCH_MIN_LEN or not snap.loose_keys:
            return []

        keys, seen = [], set()

        def add(k):
            if k in seen:
                return
            seen.add(k)
            keys.append(k)

        if q in snap.loose_display:
            add(q)

        i = bisect_left(snap.loose_keys, q)
        while i < len(snap.loose_keys) and snap.loose_keys[i].startswith(q):
            add(snap.loose_keys[i])
            i += 1
            if len(keys) >= limit:
                return keys[:limit]

        for n in range(len(q) - 1, SEARCH_MIN_LEN - 1, -1):
            if q[:n] in snap.loose_display:
                add(q[:n])
                if len(keys) >= limit:
                    return keys[:limit]

        if not keys and len(q) >= SUBSTRING_MIN_LEN:
            for k in snap.loose_keys:
                if q in k:
                    add(k)
                    if len(keys) >= limit:
                        break
        return keys[:limit]

    def search(self, text, limit=None):
        """邊打邊找 —— 回傳最多 limit 筆完整結果，順序就是相近程度

        只組 limit 筆（預設 6）的欄位，所以跟資料量無關：
        找 key 是二分搜尋，組資料是固定 6 次 iloc。
        """
        if not self._snap.sources:
            return []
        out = []
        for key in self.candidates(text, limit):
            rows = self._rows_for("loose_index", key)
            if rows is not None:
                out.append(self._result(rows))
        return out

    def lookup(self, part_number: str):
        snap = self._snap
        if not snap.sources:
            return None

        loosened = False
        key = norm(part_number)
        rows = self._rows_for("index", key) if key else None
        if rows is None:
            key = loose(part_number)
            rows = self._rows_for("loose_index", key) if key else None
            loosened = rows is not None
        if rows is None:
            return None
        return self._result(rows, typed=part_number if loosened else None)
