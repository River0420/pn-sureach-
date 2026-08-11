# PyInstaller 打包設定（Windows）
#
# 一次產出兩個執行檔，共用同一份執行環境（只佔一份空間）：
#   PN Anywhere.exe        正常使用，沒有黑色視窗
#   PN Anywhere-診斷版.exe  會開一個終端機視窗，把每一步印出來
#
# 為什麼要有診斷版：正常版如果在別人的電腦上啟動失敗，畫面上什麼都不會有，
# 使用者只看到「雙擊沒反應」。診斷版死在哪一行，那一行就會留在螢幕上。
# 這是遠端 debug 唯一的抓手，不能省。
#
# config / data / cache 刻意不打包進去 —— 它們是使用者的東西，
# 要放在 exe 旁邊讓人看得到、改得到、備份得走（見 core/paths.py）。
#
# 寫法是 PyInstaller 6 的。5 以前的 cipher / zipped_data /
# win_no_prefer_redirects 這些參數已經被拿掉了，不要加回來。

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

APP = "PN Anywhere"
ICON = os.path.join(ROOT, "assets", "app.ico")

# pandas 的 Excel 引擎是執行時才動態 import 的，PyInstaller 掃不到，要自己講
HIDDEN = [
    "openpyxl",
    "xlrd",                 # 舊版 .xls
    "lxml",                 # 偽裝成 .xls 的 HTML 表格
    "lxml.etree",
    "html5lib",
    "pandas._libs.tslibs.base",
]

# 用不到又很大的東西，明講不要，省下數十 MB 和啟動時間
EXCLUDES = [
    "tkinter", "matplotlib", "scipy", "PIL", "pytest", "IPython",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts",
    "PySide6.QtQuick", "PySide6.QtQml",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 壓縮很容易被防毒誤判成病毒，不要用
    console=False,          # 正常使用不要黑色視窗
    disable_windowed_traceback=False,
    icon=ICON,
)

console = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=f"{APP}-診斷版",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,           # 這個就是要看得到訊息
    icon=ICON,
)

coll = COLLECT(
    gui,
    console,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP,
)
