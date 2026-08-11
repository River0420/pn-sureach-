"""產生 assets/app.ico —— exe 在檔案總管裡的圖示

平常不用跑。只有改了 ui/appicon.py 的畫法之後才需要重新產生一次，
產物要 commit 進去（打包時 CI 上沒有 Pillow）。

    python3 tools/make_ico.py

工作列的常駐圖示不走這個檔案 —— 那個是程式啟動時即時畫的，
而且是單色的（見 ui/appicon.py 的說明）。
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QBuffer
from PySide6.QtWidgets import QApplication

from ui import appicon

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "app.ico")


def to_pil(pixmap):
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    pixmap.save(buf, "PNG")
    return Image.open(io.BytesIO(buf.data().data())).convert("RGBA")


def main():
    QApplication.instance() or QApplication(sys.argv)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    frames = [to_pil(appicon.draw(s, appicon.BODY, appicon.PINS))
              for s in appicon.ICO_SIZES]
    # 最大的那張當主圖，其餘全部塞進同一個 .ico。
    # 每個尺寸都是分別畫的，不是把大圖縮小 —— 小尺寸那幾張沒有 pin-1 圓點。
    frames[-1].save(OUT, format="ICO",
                    sizes=[(s, s) for s in appicon.ICO_SIZES],
                    append_images=frames[:-1])
    print(f"寫出 {OUT}　{os.path.getsize(OUT):,} bytes　"
          f"尺寸 {', '.join(str(s) for s in appicon.ICO_SIZES)}")


if __name__ == "__main__":
    main()
