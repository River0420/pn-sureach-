"""邊打邊找的功能與效能測試（headless）"""
import os, sys, time, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from core import local_lookup
from core.local_lookup import LocalPriceBook, Snapshot, build_indexes, decimal_columns

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name} {extra}")
    else:    fail += 1; print(f"  ✗ {name} {extra}")


def make_book(rows):
    """rows: list of (part, price, stock)"""
    df = pd.DataFrame(rows, columns=["料號", "單價", "庫存"])
    exact, loose_idx, disp = build_indexes(df, "料號")
    snap = Snapshot.__new__(Snapshot)
    snap.config = {"display_columns": [{"source": "s1", "column": "單價"},
                                       {"source": "s1", "column": "庫存"}]}
    snap.sources = [{"id": "s1", "name": "主檔", "key_column": "料號", "df": df,
                     "index": exact, "loose_index": loose_idx, "display": disp,
                     "decimal": decimal_columns(df)}]
    snap.errors = []; snap.elapsed = 0.0
    snap._build_suggest_index()
    return LocalPriceBook(snap)


print("\n[1] 邊打邊找：找得到嗎")
book = make_book([
    ("STM32F103C8T6", 12.5, 320),
    ("STM32F103C8T6TR", 13.0, 12),
    ("STM32F103RCT6", 22.0, 8),
    ("STM32F407VGT6", 45.0, 0),
    ("LM358DR", 1.2, 9000),
    ("LM358N", 1.5, 400),
    ("0402-10K-1%", 0.01, 500000),
])
r = book.search("STM")
check("打 3 個字就有結果", len(r) == 4, f"→ {len(r)} 筆")
check("開頭符合的都在", {x["_key"] for x in r} >= {"STM32F103C8T6", "STM32F407VGT6"})
r = book.search("S")
check("打 1 個字就開始找", len(r) == 4, f"→ {len(r)} 筆")
r = book.search("STM32F103C8T6")
check("完全符合的排第一", r[0]["_key"] == "STM32F103C8T6")
r = book.search("STM32F103C8T6TRXX")
check("打太長也找得回來", r and r[0]["_key"] == "STM32F103C8T6TR", f"→ {r[0]['_key']}")
r = book.search("358")
check("只記得中間那段也找得到", {x["_key"] for x in r} == {"LM358DR", "LM358N"})
r = book.search("stm32 f103-c8t6")
check("大小寫、空白、破折號都不影響", r[0]["_key"] == "STM32F103C8T6")
r = book.search("ZZZZZZ")
check("真的沒有就回空的", r == [])
r = book.search("0402 10K 1%")
check("含符號的料號查得到", r and r[0]["_key"] == "0402-10K-1%", f"→ {r and r[0]['_key']}")

print("\n[2] 只列 6 筆")
many = make_book([(f"AB{i:06d}", i, i) for i in range(5000)])
r = many.search("AB")
check("預設最多 6 筆", len(r) == 6, f"→ {len(r)} 筆")
check("limit 參數有效", len(many.search("AB", 3)) == 3)

print("\n[3] 結果內容完整（information 都在裡面）")
r = book.search("LM358DR")[0]
check("有料號", r["_key"] == "LM358DR")
check("欄位齊全", [n for n, _ in r["_fields"]] == ["單價", "庫存"], f"→ {r['_fields']}")
check("小數欄顯示小數", r["_fields"][0][1] == "1.20", f"→ {r['_fields'][0][1]}")
check("整數欄不加小數", r["_fields"][1][1] == "9,000", f"→ {r['_fields'][1][1]}")

print("\n[4] 5 萬 + 15 萬列的速度")
BIG = 50000
big_rows = [(f"PN{i:08d}-REV{i%9}", 10 + i % 900, i % 5000) for i in range(BIG)]
t = time.perf_counter(); big = make_book(big_rows); build_s = time.perf_counter() - t
print(f"    5 萬列建索引 {build_s:.2f}s")

def bench(fn, n=200):
    ts = []
    for i in range(n):
        a = time.perf_counter(); fn(i); ts.append((time.perf_counter() - a) * 1000)
    return statistics.median(ts), max(ts)

med, mx = bench(lambda i: big.search(f"PN{i:08d}"))
check("完整料號（5萬）中位數 < 0.5ms", med < 0.5, f"→ {med:.3f}ms / 最慢 {mx:.2f}ms")
med, mx = bench(lambda i: big.search("PN0001"))
check("打一半（5萬）中位數 < 1ms", med < 1.0, f"→ {med:.3f}ms / 最慢 {mx:.2f}ms")
# 最壞情況：前綴完全沒中，要掃全表做「包含」比對
med, mx = bench(lambda i: big.search("ZZZQQ"), n=30)
check("查無（5萬，最壞情況）< 60ms", med < 60, f"→ {med:.1f}ms")
med, mx = bench(lambda i: big.search("REV3"), n=30)
check("中間比對（5萬）< 60ms", med < 60, f"→ {med:.1f}ms")

huge = make_book([(f"PN{i:08d}-REV{i%9}", 10 + i % 900, i % 5000) for i in range(150000)])
med, mx = bench(lambda i: huge.search(f"PN{i:08d}"))
check("完整料號（15萬）中位數 < 0.5ms", med < 0.5, f"→ {med:.3f}ms")
med, mx = bench(lambda i: huge.search("PN00001"))
check("打一半（15萬）中位數 < 0.5ms", med < 0.5, f"→ {med:.3f}ms")
med, mx = bench(lambda i: huge.search("ZZZQQ"), n=20)
check("查無（15萬，最壞情況）< 150ms", med < 150, f"→ {med:.1f}ms")

print("\n[5] 視窗：清單 → 詳細 → 返回")
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from ui.popup import PopupWindow, MODE_LIST, MODE_DETAIL, MODE_MESSAGE, summary_text

app = QApplication.instance() or QApplication(sys.argv)
p = PopupWindow(on_search=book.search, on_status=lambda: (local_lookup.STATUS_READY, None))
p.prewarm()

def press(key):
    ev = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
    if not p.eventFilter(p.search, ev):
        p.keyPressEvent(ev)

p.show_query()
check("沒打字時是提示畫面", p._mode == MODE_MESSAGE)

p.search.setText("STM")
p._run_search()
check("打字後直接變清單（不用按 return）", p._mode == MODE_LIST)
visible = [r for r in p.rows if r.isVisible()]
check("清單有 4 列", len(visible) == 4, f"→ {len(visible)}")
check("第一列預選", p.rows[0].property("sel") == "true")
check("列上看得到摘要", p.rows[0].value.text() != "", f"→「{p.rows[0].value.text()}」")

press(Qt.Key_Down)
check("↓ 換下一筆", p._sel == 1 and p.rows[1].property("sel") == "true")
press(Qt.Key_Up); press(Qt.Key_Up)
check("↑ 會繞回最後一筆", p._sel == 3, f"→ {p._sel}")

p._select(0)
press(Qt.Key_Return) if False else p._enter_detail()
check("return 進到詳細畫面", p._mode == MODE_DETAIL)
check("詳細畫面清單收起來", not any(r.isVisible() for r in p.rows))
check("詳細畫面有返回提示", "esc" in p.foot.text(), f"→「{p.foot.text()}」")

press(Qt.Key_Down)
check("詳細畫面 ↓ 直接換下一筆（不用退回清單）",
      p._mode == MODE_DETAIL and p._sel == 1)

press(Qt.Key_Escape)
check("esc 從詳細回清單", p._mode == MODE_LIST, f"→ {p._mode}")
check("回清單後保留原本選的那一筆", p._sel == 1)
check("視窗還開著", p.isVisible())

press(Qt.Key_Escape)
check("清單再按 esc 才關掉視窗", not p.isVisible())

p.show_query()
p.search.setText("ZZZZZZ"); p._run_search()
check("查無會講出來", p._mode == MODE_MESSAGE)

p.show_query(prefill="LM358DR")
check("貼上料號直接就有清單", p._mode == MODE_LIST and p._results[0]["_key"] == "LM358DR")

print("\n[6] 打字時的重繪成本")
p.show_query()
p.search.setText("STM"); p._run_search(); p.grab()
ts = []
for i, text in enumerate(["S", "ST", "STM", "STM3", "STM32", "STM32F"] * 12):
    p.search.setText(text)
    a = time.perf_counter(); p._run_search(); p.grab()
    ts.append((time.perf_counter() - a) * 1000)
med = statistics.median(ts)
check("每按一個鍵（搜尋+重畫）中位數 < 16ms", med < 16, f"→ {med:.2f}ms / 最慢 {max(ts):.1f}ms")

ts = []
for _ in range(60):
    a = time.perf_counter(); p._select(p._sel + 1); p.grab()
    ts.append((time.perf_counter() - a) * 1000)
check("上下鍵移動選取 < 8ms", statistics.median(ts) < 8, f"→ {statistics.median(ts):.2f}ms")

ts = []
for _ in range(30):
    p.hide()
    a = time.perf_counter(); p.show_query(prefill="STM32F103C8T6"); ts.append((time.perf_counter()-a)*1000)
check("按熱鍵到視窗出現 < 40ms", statistics.median(ts) < 40, f"→ {statistics.median(ts):.1f}ms")

print(f"\n===== {ok} 過 / {fail} 失敗 =====")
sys.exit(1 if fail else 0)
