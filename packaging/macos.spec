# PyInstaller 打包設定（macOS）
#
# 產出一個 PN Anywhere.app，使用者拖進「應用程式」就能用，不需要裝 Python。
#
# 跟 Windows 版的三個關鍵差別：
#
# 1. LSUIElement = True
#    這是常駐工具，不該出現在 Dock 也不該出現在 ⌘Tab。
#    程式裡的 become_accessory() 執行時也會做一次，但 Info.plist 先講
#    才不會在啟動的前半秒閃一下 Dock 圖示。
#
# 2. NSAppleEventsUsageDescription / 輔助使用
#    全域熱鍵要「輔助使用」權限。系統的授權對話框會顯示這個 App 的名字，
#    所以 bundle_identifier 要固定 —— 一改，使用者授權過的紀錄就失效，
#    得重新授權一次。
#
# 3. 設定檔不寫在 .app 裡面
#    見 core/paths.py：.app 是唯讀的包，而且沒簽章的 App 會被 Gatekeeper
#    translocate 到隨機唯讀路徑。設定一律走 ~/Library/Application Support。
#
# 沒有 Developer ID 簽章的話，使用者第一次要右鍵 →「打開」才開得起來
# （等同 Windows 的 SmartScreen）。買憑證是 $99/年。

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

APP = "PN Anywhere"
ICON = os.path.join(ROOT, "assets", "app.icns")
BUNDLE_ID = "com.pnanywhere.app"

HIDDEN = [
    "openpyxl",
    "xlrd",
    "lxml",
    "lxml.etree",
    "html5lib",
    "pandas._libs.tslibs.base",
    # pyobjc 的東西全部明寫。core/permission.py 是在 try/except 裡 import
    # ApplicationServices 的，PyInstaller 掃不到 —— 少了它，程式會以為
    # 自己不需要輔助使用權限，於是跳過整個授權引導，改跳一個叫使用者去改
    # settings.json 的錯誤訊息。使用者完全不知道該做什麼。
    # 這個 bug 在 v1.0 真的發生了。
    "ApplicationServices",
    "HIServices",
    "Quartz",
    "AppKit",
    "Foundation",
    "objc",
]

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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,       # 跟著 runner 的架構走
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP,
)

app = BUNDLE(
    coll,
    name=f"{APP}.app",
    icon=ICON,
    bundle_identifier=BUNDLE_ID,
    info_plist={
        "LSUIElement": True,            # 常駐工具：不進 Dock、不進 ⌘Tab
        "NSHighResolutionCapable": True,
        "CFBundleDisplayName": APP,
        "CFBundleName": APP,
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "",
    },
)
