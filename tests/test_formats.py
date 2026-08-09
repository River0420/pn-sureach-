"""各種「其實不是它看起來那樣」的檔案都要讀得進來

ERP 匯出的檔案很少是乾淨的 .xlsx。實際會遇到：
  · 真的舊版 .xls（OLE2 二進位）
  · 副檔名寫 .xls，內容其實是 HTML 表格
  · 副檔名寫 .xls，內容其實是 tab 分隔的純文字
  · Big5 編碼的 CSV
四種都要能讀，而且讀不了的時候要講人話、要講怎麼辦。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core import local_lookup
from core.local_lookup import _sniff, detect_header_row, list_sheets, read_table

PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix="fmt-")


def check(name, ok, note=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {name}" + (f" → {note}" if note else ""))
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" → {note}" if note else ""))


def path(name):
    return os.path.join(TMP, name)


ROWS = [["A-100", 12.5, 300], ["A-200", 8.0, 50], ["B-300", 4.25, 1200]]
COLS = ["料號", "單價", "庫存"]

# ---------------------------------------------------------------- 產生檔案
# 1. 正常的 xlsx
pd.DataFrame(ROWS, columns=COLS).to_excel(path("normal.xlsx"), index=False)

# 2. 副檔名寫 .xls，內容是 HTML 表格（很多報表引擎就是這樣吐的）
html = "<html><body><table>"
html += "<tr>" + "".join(f"<th>{c}</th>" for c in COLS) + "</tr>"
for r in ROWS:
    html += "<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>"
html += "</table></body></html>"
with open(path("fake_html.xls"), "w", encoding="utf-8") as f:
    f.write(html)

# 3. 副檔名寫 .xls，內容是 tab 分隔的純文字
with open(path("fake_text.xls"), "w", encoding="cp950") as f:
    f.write("\t".join(COLS) + "\n")
    for r in ROWS:
        f.write("\t".join(str(v) for v in r) + "\n")

# 4. Big5 的 CSV，前面還有兩列抬頭
with open(path("erp.csv"), "w", encoding="cp950") as f:
    f.write("◎◎電子股份有限公司\n")
    f.write("庫存暨報價表\n")
    f.write(",".join(COLS) + "\n")
    for r in ROWS:
        f.write(",".join(str(v) for v in r) + "\n")

# ---------------------------------------------------------------- 測試
print("\n[1] 認得出檔案真正的格式")
check("正常 xlsx", _sniff(path("normal.xlsx")) == "xlsx", _sniff(path("normal.xlsx")))
check("假裝成 xls 的 HTML", _sniff(path("fake_html.xls")) == "html",
      _sniff(path("fake_html.xls")))
check("假裝成 xls 的純文字", _sniff(path("fake_text.xls")) == "text",
      _sniff(path("fake_text.xls")))

print("\n[2] 四種都讀得進來，欄位名稱要對")
CASES = [
    ("normal.xlsx", 0),
    ("fake_html.xls", 0),
    ("fake_text.xls", 0),
    ("erp.csv", None),          # None = 讓程式自己猜標題列
]
for name, header in CASES:
    try:
        hr = detect_header_row(path(name)) if header is None else header
        df = read_table(path(name), None, hr)
        cols = [str(c).strip() for c in df.columns]
        ok = cols == COLS and len(df) == len(ROWS)
        check(f"{name:16s}", ok, f"欄位 {cols}　{len(df)} 列")
    except Exception as e:
        check(f"{name:16s}", False, f"{type(e).__name__}: {e}")

print("\n[3] 值要正確，不能被讀成一團字串")
df = read_table(path("fake_html.xls"), None, 0)
check("HTML 表格的數字有轉成數字", float(df["單價"].iloc[0]) == 12.5,
      str(df["單價"].iloc[0]))
df = read_table(path("fake_text.xls"), None, 0)
check("tab 分隔有正確切開", list(df.columns) == COLS, str(list(df.columns)))
check("Big5 中文沒有亂碼", "料號" in df.columns)

print("\n[4] 工作表清單：不是真 Excel 就回空的，不要爆")
check("正常 xlsx 有工作表", len(list_sheets(path("normal.xlsx"))) >= 1)
check("HTML 偽裝的回空清單", list_sheets(path("fake_html.xls")) == [])
check("純文字偽裝的回空清單", list_sheets(path("fake_text.xls")) == [])
check("CSV 回空清單", list_sheets(path("erp.csv")) == [])

print("\n[5] 猜標題列在偽裝檔上也要work")
check("CSV 前面兩列抬頭有跳過", detect_header_row(path("erp.csv")) == 2,
      str(detect_header_row(path("erp.csv"))))

print("\n[6] 真的讀不了的時候要講人話")
with open(path("broken.xls"), "wb") as f:
    f.write(b"\xd0\xcf\x11\xe0" + b"\x00" * 200)      # 假的 OLE2 標頭
try:
    read_table(path("broken.xls"), None, 0)
    check("壞掉的 xls 要丟例外", False, "居然沒丟")
except Exception as e:
    msg = str(e)
    check("壞掉的 xls 有丟例外", True, f"{type(e).__name__}")
    check("訊息不是空的", bool(msg.strip()), msg[:60])

print(f"\n===== {PASS} 過 / {FAIL} 失敗 =====")
sys.exit(1 if FAIL else 0)
