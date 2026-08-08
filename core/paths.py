"""所有會被寫入的路徑都集中在這裡

打包成單一 exe 之後，`__file__` 會指到 PyInstaller 解壓出來的暫存資料夾
（每次執行都不一樣，而且程式關掉就沒了）。設定檔和快取寫進去等於沒寫，
使用者調好的東西下次開就不見了。所以打包後一律以「exe 自己在哪」為準。
"""

import os
import sys

APP_NAME = "料號查詢"


def _app_dir():
    """程式的家 —— 設定、資料、快取都放這底下

    直接跑原始碼時是專案資料夾；打包成 exe 後是 exe 所在的資料夾，
    使用者看得到、改得到、備份得走。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = _app_dir()

# 之後如果要改放系統的使用者資料夾（macOS 的 Application Support、
# Windows 的 %LOCALAPPDATA%），只要改這一行，其餘程式碼完全不用動。
BASE_DIR = APP_DIR

CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
BOOK_CONFIG_PATH = os.path.join(CONFIG_DIR, "book_config.json")
LOG_PATH = os.path.join(BASE_DIR, "sourcing-tool.log")


def ensure(directory):
    os.makedirs(directory, exist_ok=True)
    return directory
