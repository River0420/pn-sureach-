"""程式圖示 —— 一顆 IC，畫出來的不是圖檔

用畫的而不是放 png，有兩個實際好處：
  · 任何尺寸都清晰，不用準備一整套 @1x/@2x/@3x
  · 顏色可以跟著系統走（見下面的 tray_icon）

工作列圖示只有 16px，這是所有設計決定的前提。所以：
  · 24px 以下不畫 pin-1 圓點（那顆點在 16px 只會變成一團髒）
  · 腳位寬度用比例算，縮小後仍然看得出「這東西有腳」

macOS 和 Windows 對「跟著主題變色」的處理完全不同：
  · macOS 有 template image：只吃形狀，系統自己上色（淺色列畫黑、
    深色列畫白、反白時自動反轉）。這是選單列圖示的標準做法，
    也是為什麼原生 App 的圖示看起來都像同一套。
  · Windows 沒有這套。給什麼顏色就是什麼顏色，只能自己看主題挑。
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap

from core import plat

# 大尺寸的配色（檔案總管、安裝畫面）。工作列不用這組，那邊是單色。
BODY = "#2F3336"
PINS = "#C9A227"

# 畫的時候放大這麼多倍再縮回去 —— 直接畫 16px 的話邊緣會有鋸齒
SUPERSAMPLE = 8

# 工作列圖示的尺寸集合。Qt 會自己挑最接近的那張。
TRAY_SIZES = (16, 20, 24, 32, 44, 64)
# .ico 裡要放的尺寸（Windows 檔案總管會依情境挑用）
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size, body, pins=None):
    """畫一顆 IC。pins 留空就整顆同色（工作列用）。"""
    s = size * SUPERSAMPLE
    pix = QPixmap(s, s)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)

    body_color = QColor(body)
    pin_color = QColor(pins) if pins else body_color

    # 腳位：左右各三隻。先畫，才會被本體壓在下面。
    p.setBrush(pin_color)
    for y in (0.30, 0.50, 0.70):
        p.drawRoundedRect(QRectF(s * .04, s * (y - .055), s * .20, s * .11),
                          s * .03, s * .03)
        p.drawRoundedRect(QRectF(s * .76, s * (y - .055), s * .20, s * .11),
                          s * .03, s * .03)

    p.setBrush(body_color)
    p.drawRoundedRect(QRectF(s * .20, s * .18, s * .60, s * .64), s * .08, s * .08)

    # pin-1 的圓點是挖空的，不是另外畫一個顏色 ——
    # 這樣單色模式下它在深色列上也還是看得見。
    if size >= 24:
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.setBrush(QColor("#000000"))
        p.drawEllipse(QPointF(s * .32, s * .31), s * .065, s * .065)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    p.end()
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _dark_background():
    """工作列現在是深色的嗎 —— 只有 Windows 需要問這件事"""
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        return True     # 問不到就當深色：Windows 工作列預設是深的


def tray_icon():
    """常駐圖示

    macOS 走 template image：畫成黑色交給系統，它會自己處理深淺色和反白。
    Windows 沒有這機制，只能自己看主題挑顏色，並在主題變了之後重畫
    （見 main.py 接 colorSchemeChanged 的地方）。
    """
    color = "#000000" if plat.MACOS else (
        "#FFFFFF" if _dark_background() else "#1F1E1B")
    icon = QIcon()
    for size in TRAY_SIZES:
        icon.addPixmap(draw(size, color))
    if plat.MACOS:
        icon.setIsMask(True)
    return icon


def app_icon():
    """視窗與工作列的程式圖示 —— 這個是上色的"""
    icon = QIcon()
    for size in ICO_SIZES:
        icon.addPixmap(draw(size, BODY, PINS))
    return icon
