"""已停用 —— 舊 tkinter 版留下來的檔案，可以直接刪掉

原本這裡 `import tkinter`，別人的 Python 環境不一定有 tkinter，會炸。
現在只是轉接到 ui.style，避免任何殘留的 import 出事。
設計 token 一律去 ui/style.py 拿（它又是從 core/settings.py 產生的）。
"""

from ui.style import (  # noqa: F401
    ACCENT,
    ACCENT_SOFT,
    BG,
    BORDER,
    DANGER,
    TEXT as TEXT_MAIN,
    TEXT_MUTED,
)
