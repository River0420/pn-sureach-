"""產生 assets/app.ico 與 assets/app.icns —— 程式檔本身的圖示

    .ico   Windows 檔案總管
    .icns  macOS 的 .app（Finder、⌘Tab、通知）

平常不用跑。只有改了 ui/appicon.py 的畫法之後才需要重新產生一次，
產物要 commit 進去（打包時 CI 上沒有 Pillow）。

    python3 tools/make_ico.py

工作列／選單列的常駐圖示不走這個檔案 —— 那個是程式啟動時即時畫的，
而且是單色的（見 ui/appicon.py 的說明）。

.icns 要用 macOS 內建的 iconutil 產生，所以這支只能在 Mac 上跑。
"""

import io
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QBuffer
from PySide6.QtWidgets import QApplication

from ui import appicon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
ICO = os.path.join(ASSETS, "app.ico")
ICNS = os.path.join(ASSETS, "app.icns")

# macOS 的 iconset 要的檔名格式是固定的：(邊長, 檔名)
ICONSET = [(16, "icon_16x16"), (32, "icon_16x16@2x"),
           (32, "icon_32x32"), (64, "icon_32x32@2x"),
           (128, "icon_128x128"), (256, "icon_128x128@2x"),
           (256, "icon_256x256"), (512, "icon_256x256@2x"),
           (512, "icon_512x512"), (1024, "icon_512x512@2x")]


def to_pil(pixmap):
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    pixmap.save(buf, "PNG")
    return Image.open(io.BytesIO(buf.data().data())).convert("RGBA")


def make_ico():
    frames = [to_pil(appicon.draw(s, appicon.BODY, appicon.PINS))
              for s in appicon.ICO_SIZES]
    # 最大的那張當主圖，其餘全部塞進同一個 .ico。
    # 每個尺寸都是分別畫的，不是把大圖縮小 —— 小尺寸那幾張沒有 pin-1 圓點。
    frames[-1].save(ICO, format="ICO",
                    sizes=[(s, s) for s in appicon.ICO_SIZES],
                    append_images=frames[:-1])
    print(f"寫出 {ICO}　{os.path.getsize(ICO):,} bytes　"
          f"尺寸 {', '.join(str(s) for s in appicon.ICO_SIZES)}")


def make_icns():
    if not shutil.which("iconutil"):
        print("跳過 .icns —— 找不到 iconutil（這支只有 macOS 有）")
        return
    work = os.path.join(ASSETS, "app.iconset")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    for size, name in ICONSET:
        to_pil(appicon.draw(size, appicon.BODY, appicon.PINS)).save(
            os.path.join(work, name + ".png"))
    subprocess.run(["iconutil", "-c", "icns", work, "-o", ICNS], check=True)
    shutil.rmtree(work, ignore_errors=True)
    print(f"寫出 {ICNS}　{os.path.getsize(ICNS):,} bytes　"
          f"{len(ICONSET)} 個尺寸")


def main():
    QApplication.instance() or QApplication(sys.argv)
    os.makedirs(ASSETS, exist_ok=True)
    make_ico()
    make_icns()


if __name__ == "__main__":
    main()
