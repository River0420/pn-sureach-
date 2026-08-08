"""所有會被寫入的路徑都集中在這裡

現在都放在程式資料夾底下，方便開發與測試。
之後打包成 .app（那裡是唯讀的）只要改這個檔案的 BASE_DIR 一行，
其餘程式碼完全不用動。
"""

import os

APP_NAME = "料號查詢"

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 打包後改成：
#   BASE_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
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
