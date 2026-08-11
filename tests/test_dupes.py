"""同一個料號出現好幾列，以及識別碼被讀成數字的問題

兩件事：

1. 階梯報價、不同批號、改版沒刪舊列 —— 同一個料號佔好幾列是常態。
   以前索引只留最後一筆，另外幾筆等於不存在，而使用者在抄價格的
   那一刻不會知道。現在要數得出來有幾筆，也要拿得到其中任何一筆。

2. 料號欄一定要當文字讀。純數字的識別碼（員工編號 0012345、
   貨號 0080）被 pandas 讀成數字的話，前導零會不見，而且不會報錯。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

from core.local_lookup import (LocalPriceBook, Snapshot, build_indexes,
                               decimal_columns, read_table)

PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix="dup-")


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}" + (f" → {extra}" if extra else ""))
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" → {extra}" if extra else ""))


def path(name):
    return os.path.join(TMP, name)


def source(sid, name, rows, columns=("料號", "單價", "庫存")):
    df = pd.DataFrame(rows, columns=list(columns))
    exact, loose_idx, disp = build_indexes(df, "料號")
    return {"id": sid, "name": name, "key_column": "料號", "df": df,
            "index": exact, "loose_index": loose_idx, "display": disp,
            "decimal": decimal_columns(df)}


def make_book(sources, display):
    snap = Snapshot.__new__(Snapshot)
    snap.config = {"display_columns": display}
    snap.sources = sources
    snap.errors = []
    snap.elapsed = 0.0
    snap._build_suggest_index()
    return LocalPriceBook(snap)


# ---------------------------------------------------------------- 索引
print("\n[1] 索引存的是列號清單")
df = pd.DataFrame([
    ("ABC-100", 12.5, 100),      # 0
    ("ABC-100", 11.2, 1000),     # 1  階梯報價，同一顆
    ("ABC-100", 9.8, 5000),      # 2
    ("XYZ-200", 3.0, 50),        # 3
    (None, 1.0, 1),              # 4  空白料號，不該進索引
], columns=["料號", "單價", "庫存"])
exact, loose_idx, disp = build_indexes(df, "料號")

check("重複的料號收集了三筆", exact["ABC-100"] == [0, 1, 2], str(exact["ABC-100"]))
check("沒重複的也是清單", exact["XYZ-200"] == [3], str(exact["XYZ-200"]))
check("空白料號不進索引", len(exact) == 2, str(sorted(exact)))
check("去符號索引一樣收集", loose_idx["ABC100"] == [0, 1, 2], str(loose_idx["ABC100"]))
check("顯示用的原始寫法留第一個", disp["ABC100"] == "ABC-100", disp["ABC100"])

# ---------------------------------------------------------------- 查詢
print("\n[2] 查詢：預設維持原本行為（最後一筆）")
book = make_book(
    [source("s1", "報價單", [("ABC-100", 12.5, 100), ("ABC-100", 11.2, 1000),
                            ("ABC-100", 9.8, 5000), ("XYZ-200", 3.0, 50)])],
    [{"source": "s1", "column": "單價"}, {"source": "s1", "column": "庫存"}])

r = book.lookup("ABC-100")
check("預設拿到最後一筆", dict(r["_fields"])["單價"] == "9.80", dict(r["_fields"])["單價"])
check("有講總共幾筆", r["_dup"] == 3, str(r["_dup"]))
check("有講現在是第幾筆", r["_dup_at"] == 2, str(r["_dup_at"]))

print("\n[3] 查詢：拿得到其中任何一筆")
for i, price in enumerate(["12.50", "11.20", "9.80"]):
    r = book.lookup("ABC-100", variant=i)
    got = dict(r["_fields"])["單價"]
    check(f"第 {i + 1} 筆", got == price and r["_dup_at"] == i, f"{got}／at={r['_dup_at']}")

r = book.lookup("ABC-100", variant=99)
check("超出範圍會夾住，不會爆", dict(r["_fields"])["單價"] == "9.80")

print("\n[4] 沒重複的時候，_dup 是 1")
r = book.lookup("XYZ-200")
check("單筆料號 _dup=1", r["_dup"] == 1, str(r["_dup"]))
check("單筆料號 _dup_at=0", r["_dup_at"] == 0, str(r["_dup_at"]))

print("\n[5] 兩個檔案重複筆數不一樣時各走各的")
# 報價單有 3 筆階梯價，庫存表只有 1 筆 —— 切到第 3 筆時，
# 庫存表要繼續顯示它那唯一一筆，不能變成空的。
book2 = make_book(
    [source("s1", "報價單", [("ABC-100", 12.5, 0), ("ABC-100", 11.2, 0),
                            ("ABC-100", 9.8, 0)]),
     source("s2", "庫存表", [("ABC-100", 0, 777)])],
    [{"source": "s1", "column": "單價"}, {"source": "s2", "column": "庫存"}])

for i in range(3):
    r = book2.lookup("ABC-100", variant=i)
    f = dict(r["_fields"])
    check(f"第 {i + 1} 筆：報價跟著換，庫存不動",
          f["庫存"] == "777" and r["_dup"] == 3, f"單價 {f['單價']}／庫存 {f['庫存']}")

r = book2.lookup("ABC-100")
check("兩邊都命中，_missing 是空的", r["_missing"] == [], str(r["_missing"]))

print("\n[6] 邊打邊找也要帶著筆數")
hits = book.search("ABC")
check("找得到", len(hits) == 1, f"{len(hits)} 筆")
check("清單裡也知道有 3 筆", hits and hits[0]["_dup"] == 3,
      str(hits[0]["_dup"]) if hits else "—")

# ---------------------------------------------------------------- 讀檔
print("\n[7] 料號欄一律當文字讀")
pd.DataFrame([["0012345", 10], ["0080", 20], ["1234567890123456789", 30]],
             columns=["貨號", "單價"]).to_excel(path("codes.xlsx"), index=False)

plain = read_table(path("codes.xlsx"), None, 0)
typed = read_table(path("codes.xlsx"), None, 0, key_column="貨號")
codes = [str(v) for v in typed["貨號"].tolist()]
check("前導零留住了", codes[0] == "0012345", codes[0])
check("短的也留住了", codes[1] == "0080", codes[1])
check("19 位數沒被浮點數改掉", codes[2] == "1234567890123456789", codes[2])
check("單價還是數字，沒被一起變成文字",
      pd.api.types.is_numeric_dtype(typed["單價"]), str(typed["單價"].dtype))
check("不指定欄位時維持原樣（沒有偷改行為）", len(plain) == 3)

print("\n[8] CSV 也要一樣")
with open(path("codes.csv"), "wb") as f:
    f.write("貨號,單價\n0012345,10\n0080,20\n".encode("utf-8"))
typed = read_table(path("codes.csv"), None, 0, key_column="貨號")
check("CSV 前導零留住了", str(typed["貨號"].iloc[0]) == "0012345",
      str(typed["貨號"].iloc[0]))
check("CSV 單價還是數字", pd.api.types.is_numeric_dtype(typed["單價"]),
      str(typed["單價"].dtype))

print("\n[9] 指定不存在的欄位不能讓程式爆掉")
try:
    got = read_table(path("codes.csv"), None, 0, key_column="不存在的欄位")
    check("安靜忽略", len(got) == 2, f"{len(got)} 列")
except Exception as e:
    check("安靜忽略", False, f"{type(e).__name__}: {e}")

print("\n[10] 畫面：清單就看得到「3 筆」，詳細畫面左右鍵可以換")
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ui.popup import MODE_DETAIL, MODE_LIST, PopupWindow, summary_text

app = QApplication.instance() or QApplication(sys.argv)
p = PopupWindow(on_search=book.search,
                on_status=lambda: ("ready", None),
                on_variant=book.lookup)
p.prewarm()


def press(key):
    ev = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
    if not p.eventFilter(p.search, ev):
        p.keyPressEvent(ev)


check("清單摘要有帶筆數", "3 筆" in summary_text(book.search("ABC")[0]),
      summary_text(book.search("ABC")[0]))
check("沒重複的不要加雜訊", "筆" not in summary_text(book.search("XYZ")[0]),
      summary_text(book.search("XYZ")[0]))

p.search.setText("ABC")
p._run_search()
check("打字後是清單", p._mode == MODE_LIST)

press(Qt.Key_Return)
p._enter_detail()
check("進到詳細畫面", p._mode == MODE_DETAIL)
check("預設顯示最後一筆", dict(p._results[0]["_fields"])["單價"] == "9.80",
      dict(p._results[0]["_fields"])["單價"])
check("腳註有提示左右鍵", "←" in p.foot.text(), p.foot.text())

press(Qt.Key_Right)
check("→ 繞回第 1 筆", dict(p._results[0]["_fields"])["單價"] == "12.50",
      dict(p._results[0]["_fields"])["單價"])
press(Qt.Key_Right)
check("再 → 到第 2 筆", dict(p._results[0]["_fields"])["單價"] == "11.20",
      dict(p._results[0]["_fields"])["單價"])
press(Qt.Key_Left)
check("← 退回第 1 筆", dict(p._results[0]["_fields"])["單價"] == "12.50",
      dict(p._results[0]["_fields"])["單價"])
check("還在詳細畫面", p._mode == MODE_DETAIL)

p.search.setText("XYZ")
p._run_search()
p._enter_detail()
before = p.foot.text()
press(Qt.Key_Right)
check("沒重複的料號左右鍵不作用", p.foot.text() == before and "←" not in before,
      before)

print(f"\n===== {PASS} 過 / {FAIL} 失敗 =====")
sys.exit(1 if FAIL else 0)
