# 料號查詢小工具

macOS 選單列常駐工具。按 `⌥Space` 叫出查詢視窗，**打字就直接找**，
下面即時列出最相近的 6 筆（含價格、庫存摘要），按 `return` 才進到單筆完整資料。
資料來自本機的 Excel / CSV，不連外網。

```
⌥Space          叫出視窗
打字            直接找，不用按 return
↑ ↓             選
return          看這一筆的完整資料
esc             從完整資料回清單；在清單再按一次關掉視窗
```

目前狀態：**MVP，只能在已安裝相依套件的機器上跑**（尚未打包成 .app）。

---

## 執行

```bash
pip3 install -r requirements.txt
```

之後雙擊 `啟動料號查詢.command`，或：

```bash
python3 main.py
```

第一次啟動需要「輔助使用」權限（全域熱鍵要用）。程式會自己引導你去開，
開完不用重開，兩秒內會自動接上。

---

## 微調畫面與行為

所有可調整的東西都在 `config/settings.json`（第一次啟動會自動產生完整預設值）。
改完重開程式即可，**不需要動任何程式碼**。

| 想改什麼 | 改哪裡 |
|---|---|
| 視窗寬度、內距、圓角 | `window.width` / `padding_*` / `radius` |
| 清單列幾筆 | `window.list_rows` 與 `data.result_limit`（取小的） |
| 每列右邊帶幾個欄位當摘要 | `window.list_fields`（0 = 只顯示料號） |
| 摘要欄位之間的分隔符號 | `window.list_sep` |
| 清單列高、字級 | `theme.list_row_padding` / `list_key_size` / `list_value_size` |
| 料號右邊的來源小標籤 | `window.source_badge`（留空 = 不顯示，預設不顯示） |
| 猜「欄位名稱在第幾列」往下看幾列 | `data.header_scan_rows` |
| 打幾個字開始找 | `data.search_min_len` |
| 每按一鍵就找 / 加延遲 | `window.search_debounce_ms`（0 = 立刻） |
| 視窗出現位置 | `window.anchor`：`top-right` / `top-left` / `top-center` / `center` |
| 配色 | `theme.bg` / `text` / `accent` … |
| 字級 | `theme.*_size`（`base_size` 是 pt，其餘是 px） |
| 熱鍵 | `hotkey.keycode` + `hotkey.modifiers`（`cmd`/`alt`/`ctrl`/`shift`） |
| 最多幾個來源檔 | `data.max_sources`（上限 5） |
| 資料筆數上限 | `data.max_rows_per_source`（0 = 不限） |
| 關掉 Excel 解析快取 | `data.cache: false` |
| CSV 編碼嘗試順序 | `data.csv_encodings` |

改壞了就把 `config/settings.json` 刪掉，重開會重新產生預設值。

---

## 架構

```
core/            完全不依賴 Qt，可以在背景執行緒整包跑完
  paths.py         所有會被寫入的路徑（打包時只要改這裡）
  settings.py      使用者可調設定，含預設值與版本升級
  book_config.py   匯入了哪些檔案、顯示哪些欄位
  local_lookup.py  讀檔、建索引、查詢；Snapshot 是不可變的載入結果
  hotkey.py        全域熱鍵（Quartz event tap）
  permission.py    輔助使用權限的偵測與引導
ui/              Qt 介面
  style.py         QSS，由 settings 產生
  popup.py         熱鍵查詢視窗（清單 / 詳細兩個畫面）
  result_view.py   查詢結果的畫法（彈窗與匯入預覽共用）
  import_dialog.py 匯入設定視窗
  mac_window.py    macOS 原生視窗行為
main.py          組裝、選單列、背景載入、熱鍵生命週期
```

### 兩條不能違反的規則

1. **`core/` 不准 import Qt。** 資料載入必須能在背景執行緒跑完，
   否則大檔案會讓整個介面凍住。
2. **不准用 `QGraphicsDropShadowEffect`。** 陰影一律交給 macOS 原生。
   實測用 Qt 的陰影特效會讓每次重繪從 0.5ms 變成 23ms，打字就會頓。
3. **清單那幾列不准每次搜尋都重建。** 它們是開機就建好的常駐 widget，
   搜尋時只換文字、多的 `hide()`。每按一鍵重建 6 個 widget 要多花 3~4ms，
   打字會有黏滯感。同理，選取狀態用 QSS 屬性（`sel="true"`）切換，
   不要用 `setStyleSheet()` —— 那會重新解析整份樣式表。

---

## 效能實測（MacBook, Python 3.14, PySide6 6.11）

| 項目 | 數字 |
|---|---|
| 第一次按熱鍵到視窗出現 | ~28 ms |
| 之後每次 | ~16 ms |
| **每按一個鍵（搜尋 + 重畫 6 列）** | **0.94 ms** |
| 上下鍵移動選取 | 0.53 ms |
| 15 萬列（3 檔 × 5 萬）冷啟動載入 | 3.3 秒（背景，不卡介面） |
| 同上，有快取 | 0.26 秒 |
| 邊打邊找（15 萬列，開頭比對） | 0.023 ms |
| 查無（15 萬列，會掃全表的最壞情況） | 2.7 ms |
| 15 萬列時的記憶體 | ~250 MB |

### 實際檔案的載入時間（不走快取，最壞情況）

| 資料 | 解析 + 建索引 | 記憶體 |
|---|---|---|
| 1 檔 12,000 列 × 10 欄（799 KB） | 0.66 秒 | 94 MB |
| 2 檔各 12,000 列 | 1.04 秒 | 109 MB |
| 3 檔共 74,000 列（50k + 12k + 12k） | 3.16 秒 | 148 MB |

載入是在背景執行緒跑的，這段時間介面照樣可以用。第二次開機走快取只要 0.2~0.3 秒。
查詢速度在這三種情況下都是 0.04 ms —— 跟資料量無關。

### 為什麼資料變大也不會變慢

邊打邊找**只組 6 筆**的欄位資料，跟總列數無關：

1. 找 key 是排序好的索引 + 二分搜尋 → O(log n)
2. 組資料是固定 6 次 `iloc` → O(1)

唯一會掃全表的是「開頭完全沒中，改用中間包含比對」那一段（15 萬列 2.7ms）。
所以它只在前面幾段一筆都沒中的時候才跑 —— 也就是使用者本來就查不到東西的時候。

啟動時會花約 0.5 秒預熱查詢視窗，這是刻意的——把成本從「使用者第一次按熱鍵」
搬到「開機」。

---

## 還沒做（下一階段）

- 打包成 `.app`（py2app）+ Developer ID 簽章 + 公證
- 設定與資料改放 `~/Library/Application Support/`（只需改 `core/paths.py`）
- 深色模式
- 授權機制
- 更大的資料量改用 SQLite
