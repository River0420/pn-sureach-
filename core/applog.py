"""程式輸出：確保中文印得出來，而且一定會留下 log 檔

兩個問題都是 Windows 才有的，但修法對兩邊都安全：

1. Windows 主控台預設是 cp950 / cp1252，`print("已載入 3 個檔案")` 會直接
   丟 UnicodeEncodeError 把程式弄死。實際跑起來才炸，而且炸在最沒道理的地方。

2. macOS 那邊是靠 `啟動料號查詢.command` 把輸出轉向到檔案，Windows 沒有
   那一層，所以不會有 log 檔 —— 偏偏診斷報告最有用的就是那幾行紀錄。
   這裡自己接手，不依賴外面怎麼啟動。

打包成沒有主控台的 exe 時，`sys.stdout` 會是 None，所有動作都要能接受這件事。
"""

import os
import sys

from core import paths

MAX_BYTES = 512 * 1024      # log 超過就從頭來過，不要無限長大


class _Tee:
    """同時寫到原本的輸出和 log 檔

    任何一邊失敗都不能影響另一邊 —— log 寫不進去（沒權限、磁碟滿了）
    不該讓程式印不出東西，反過來也一樣。
    """

    def __init__(self, stream, handle):
        self._stream = stream
        self._handle = handle

    def write(self, text):
        if self._stream is not None:
            try:
                self._stream.write(text)
            except Exception:
                pass
        if self._handle is not None:
            try:
                self._handle.write(text)
                self._handle.flush()
            except Exception:
                pass
        return len(text)

    def flush(self):
        for target in (self._stream, self._handle):
            if target is not None:
                try:
                    target.flush()
                except Exception:
                    pass

    def isatty(self):
        try:
            return bool(self._stream and self._stream.isatty())
        except Exception:
            return False


def _fix_encoding(stream):
    """讓這個輸出串流吃得下中文

    errors="replace" 是刻意的：真的遇到印不出來的字元，寧可印成問號，
    也不要讓整個程式因為一行訊息就掛掉。
    """
    if stream is None:
        return None
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return stream


def _open_log():
    try:
        paths.ensure(os.path.dirname(paths.LOG_PATH) or ".")
        mode = "a"
        if (os.path.exists(paths.LOG_PATH)
                and os.path.getsize(paths.LOG_PATH) > MAX_BYTES):
            mode = "w"
        return open(paths.LOG_PATH, mode, encoding="utf-8", errors="replace")
    except Exception:
        return None      # 寫不了 log 不是致命的，程式要照跑


def install():
    """在 main() 最開頭呼叫，越早越好 —— 之前的輸出就留不下來了"""
    out = _fix_encoding(sys.stdout)
    err = _fix_encoding(sys.stderr)
    handle = _open_log()
    sys.stdout = _Tee(out, handle)
    sys.stderr = _Tee(err, handle)
    return handle is not None
