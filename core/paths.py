"""所有會被寫入的路徑都集中在這裡

打包成單一 exe 之後，`__file__` 會指到 PyInstaller 解壓出來的暫存資料夾
（每次執行都不一樣，而且程式關掉就沒了）。設定檔和快取寫進去等於沒寫，
使用者調好的東西下次開就不見了。所以打包後一律以「exe 自己在哪」為準。
"""

import os
import sys

APP_NAME = "PN Anywhere"

FROZEN = getattr(sys, "frozen", False)
IN_APP_BUNDLE = FROZEN and ".app/Contents/" in os.path.abspath(sys.executable)


def _app_dir():
    """程式的家 —— 設定、資料、快取都放這底下

    三種情況，三個答案：

    · 直接跑原始碼 → 專案資料夾
    · Windows 的 exe → exe 所在的資料夾。整包是可攜的，
      使用者看得到、改得到、整個資料夾複製走就搬家完成。
    · macOS 的 .app → ~/Library/Application Support/PN Anywhere

    .app 那個不能比照 Windows 辦理。.app 是一個「包」，慣例上是唯讀的；
    而且 Gatekeeper 對沒簽章的 App 會做 translocation —— 把它掛載到一個
    隨機的唯讀路徑再執行。寫進包裡的東西不是失敗就是下次開就不見了。
    """
    if IN_APP_BUNDLE:
        return os.path.join(os.path.expanduser("~/Library/Application Support"),
                            APP_NAME)
    if FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = _app_dir()
BASE_DIR = APP_DIR

CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
BOOK_CONFIG_PATH = os.path.join(CONFIG_DIR, "book_config.json")
LOG_PATH = os.path.join(BASE_DIR, "PN Anywhere.log")


def ensure(directory):
    os.makedirs(directory, exist_ok=True)
    return directory
