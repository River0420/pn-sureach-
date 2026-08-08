import json
import os

from core import paths

CONFIG_DIR = paths.CONFIG_DIR
CONFIG_PATH = paths.BOOK_CONFIG_PATH
DATA_DIR = paths.DATA_DIR

VERSION = 2


def migrate(config):
    """把舊版的單檔設定轉成多來源格式，讓既有設定不用重匯"""
    if not config:
        return None
    if config.get("version") == VERSION:
        return config
    path = config.get("path")
    if not path or not config.get("key_column"):
        return None
    src = config.get("source_path") or path
    return {
        "version": VERSION,
        "sources": [{
            "id": "s1",
            "name": os.path.basename(src),
            "path": path,
            "source_path": config.get("source_path"),
            "sheet": config.get("sheet"),
            "header_row": config.get("header_row", 0),
            "key_column": config["key_column"],
        }],
        "display_columns": [
            {"source": "s1", "column": c} for c in config.get("display_columns", [])
        ],
    }


def _absolute(path):
    """設定檔裡存的是相對於資料夾的路徑，換一台電腦才不會失效"""
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(paths.BASE_DIR, path))


def _relative(path):
    if not path:
        return path
    try:
        rel = os.path.relpath(path, paths.BASE_DIR)
    except ValueError:
        return path
    # 只有真的在資料夾底下才存相對路徑，不然 ../../ 會更難懂
    return rel if not rel.startswith("..") else path


def load():
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = migrate(json.load(f))
    except Exception:
        return None
    if not config:
        return None
    for source in config.get("sources", []):
        source["path"] = _absolute(source.get("path"))
        source["source_path"] = _absolute(source.get("source_path"))
    return config


def save(config):
    paths.ensure(CONFIG_DIR)
    payload = json.loads(json.dumps(config, ensure_ascii=False))
    for source in payload.get("sources", []):
        source["path"] = _relative(source.get("path"))
        # 原始檔在使用者自己的位置，維持絕對路徑（下次匯入才找得回去）
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
