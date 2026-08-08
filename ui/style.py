"""設計 token 與 QSS —— 全部由 core.settings 產生

這個檔案不該再出現任何寫死的顏色或字級。要微調畫面請改 config/settings.json
的 theme / window 區塊，改完重開程式即可。
"""

import os

from core import settings

_T = settings.section("theme")
_W = settings.section("window")

_CHECK = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "check.svg"
).replace("\\", "/")

# ---------- 顏色 ----------
BG = _T["bg"]
SURFACE = _T["surface"]
BORDER = _T["border"]
BORDER_SOFT = _T["border_soft"]
TEXT = _T["text"]
TEXT_SOFT = _T["text_soft"]
TEXT_MUTED = _T["text_muted"]
ACCENT = _T["accent"]
ACCENT_HOVER = _T["accent_hover"]
ACCENT_SOFT = _T["accent_soft"]
GREEN = _T["green"]
DANGER = _T["danger"]

# ---------- 字級 ----------
BASE_SIZE = _T["base_size"]
SEARCH_SIZE = _T["search_size"]
PART_NUMBER_SIZE = _T["part_number_size"]
HERO_SIZE = _T["hero_size"]
FIELD_LABEL_SIZE = _T["field_label_size"]
FIELD_VALUE_SIZE = _T["field_value_size"]
HINT_SIZE = _T["hint_size"]
ERROR_SIZE = _T["error_size"]
BADGE_SIZE = _T["badge_size"]
LIST_KEY_SIZE = _T["list_key_size"]
LIST_VALUE_SIZE = _T["list_value_size"]
LIST_ROW_PADDING = _T["list_row_padding"]

RADIUS = _W["radius"]

POPUP_QSS = f"""
#card {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
#search {{
    background: transparent;
    border: none;
    color: {TEXT};
    font-size: {SEARCH_SIZE}px;
    font-weight: 500;
    padding: 2px 0;
}}
#search::placeholder {{
    color: {TEXT_MUTED};
}}
#divider {{
    background-color: {BORDER_SOFT};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
#partNumber {{
    color: {TEXT};
    font-size: {PART_NUMBER_SIZE}px;
    font-weight: 600;
    letter-spacing: 0.2px;
}}
#badge {{
    color: {ACCENT};
    background-color: {ACCENT_SOFT};
    border-radius: 5px;
    padding: 3px 8px;
    font-size: {BADGE_SIZE}px;
    font-weight: 700;
    letter-spacing: 0.6px;
}}
#fieldLabel {{
    color: {TEXT_MUTED};
    font-size: {FIELD_LABEL_SIZE}px;
    font-weight: 400;
}}
#fieldValue {{
    color: {TEXT_SOFT};
    font-size: {FIELD_VALUE_SIZE}px;
    font-weight: 500;
}}
#heroValue {{
    color: {ACCENT};
    font-size: {HERO_SIZE}px;
    font-weight: 650;
    letter-spacing: -0.3px;
}}
#hint {{
    color: {TEXT_MUTED};
    font-size: {HINT_SIZE}px;
}}
#errorTitle {{
    color: {DANGER};
    font-size: {ERROR_SIZE}px;
    font-weight: 600;
}}
/* ---------- 邊打邊找的結果清單 ---------- */
/* 選取狀態是用 QSS 的屬性選擇器切換（sel="true"），不是換 stylesheet 字串，
   Qt 只要重跑一次 polish，不會重新解析整份 QSS。 */
#listRow {{
    background: transparent;
    border: none;
    border-radius: 8px;
}}
#listRow[sel="true"] {{
    background-color: {ACCENT_SOFT};
}}
#listRow[hot="true"] {{
    background-color: {BORDER_SOFT};
}}
#listKey {{
    color: {TEXT};
    font-size: {LIST_KEY_SIZE}px;
    font-weight: 500;
    background: transparent;
}}
#listRow[sel="true"] #listKey {{
    color: {ACCENT};
    font-weight: 650;
}}
#listValue {{
    color: {TEXT_MUTED};
    font-size: {LIST_VALUE_SIZE}px;
    font-weight: 500;
    background: transparent;
}}
#listRow[sel="true"] #listValue {{
    color: {ACCENT};
}}
#counter {{
    color: {TEXT_MUTED};
    font-size: {HINT_SIZE}px;
    font-weight: 500;
}}
"""

DIALOG_QSS = f"""
QDialog {{
    background-color: {BG};
}}
QLabel {{
    color: {TEXT};
    font-size: 13px;
}}
#dlgTitle {{
    font-size: 20px;
    font-weight: 650;
    color: {TEXT};
}}
#dlgSub {{
    font-size: 13px;
    color: {TEXT_MUTED};
}}
#sectionLabel {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}
#keyLabel {{
    font-size: 14px;
    font-weight: 700;
    color: {ACCENT};
}}
#searchBox {{
    background-color: {ACCENT_SOFT};
    border: 1px solid #EBD5C8;
    border-radius: 11px;
}}
#searchBox QComboBox {{
    background-color: {SURFACE};
    border: 1.5px solid {ACCENT};
    font-weight: 600;
}}
#searchBox QLabel {{
    background: transparent;
}}
#fileName {{
    font-size: 13px;
    color: {TEXT_SOFT};
}}
QComboBox, QSpinBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 10px;
    font-size: 13px;
    color: {TEXT};
    min-height: 20px;
}}
QComboBox:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 7px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT};
    padding: 4px;
}}
QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    color: {TEXT};
}}
QPushButton:hover {{ background-color: {BORDER_SOFT}; }}
QPushButton#primary {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{
    background-color: {BORDER};
    border-color: {BORDER};
    color: {TEXT_MUTED};
}}
#colScroll {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
#colScroll QWidget {{ background-color: {SURFACE}; }}
QCheckBox {{
    font-size: 13px;
    color: {TEXT};
    spacing: 8px;
    padding: 3px 0;
}}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1.5px solid {BORDER};
    border-radius: 4px;
    background-color: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    image: url("{_CHECK}");
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
#colPreview {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 30px;
}}
QScrollBar:horizontal {{
    background: transparent; height: 8px; margin: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER}; border-radius: 4px; min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

/* ---------- 拖放區 ---------- */
#dropZone {{
    background-color: {SURFACE};
    border: 1.5px dashed {BORDER};
    border-radius: 12px;
}}
#dropZone[dragging="true"] {{
    border: 1.5px dashed {ACCENT};
    background-color: {ACCENT_SOFT};
}}
#dropTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT};
}}
#dropHint {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}

/* ---------- 來源檔案卡片 ---------- */
#slot {{
    background-color: {SURFACE};
    border: 1.5px dashed {BORDER};
    border-radius: 12px;
}}
#slot[filled="true"] {{
    border: 1px solid {BORDER};
}}
#slot[dragging="true"] {{
    border: 1.5px dashed {ACCENT};
    background-color: {ACCENT_SOFT};
}}
#slot QComboBox, #slot QSpinBox {{
    padding: 3px 8px;
    font-size: 12px;
    min-height: 17px;
}}
#slotBadge {{
    color: {ACCENT};
    background-color: {ACCENT_SOFT};
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 700;
}}
#slotName {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}
#slotEmpty {{
    font-size: 13px;
    font-weight: 500;
    color: {TEXT_MUTED};
}}
#slotMeta {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}
#slotField {{
    font-size: 11px;
    color: {TEXT_SOFT};
    font-weight: 500;
}}
#matchOk {{
    font-size: 11px;
    font-weight: 600;
    color: {GREEN};
}}
#matchBad {{
    font-size: 11px;
    font-weight: 600;
    color: {DANGER};
}}
#linkBtn {{
    border: none;
    background: transparent;
    color: {TEXT_MUTED};
    font-size: 12px;
    padding: 2px 5px;
    min-width: 0;
}}
#linkBtn:hover {{
    background: transparent;
    color: {ACCENT};
}}

/* ---------- 查詢預覽 ---------- */
/* QScrollArea 有三層（自己 → viewport → 內容 widget），
   只設最外層的話中間那層會用預設的 palette 畫出來（在深色系統上是黑的）。
   三層都要指定，底色才會一致。 */
#previewPane {{
    background-color: {BORDER_SOFT};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
#previewPane > QWidget {{
    background-color: {BORDER_SOFT};
}}
#previewInner {{
    background-color: {BORDER_SOFT};
}}

/* ---------- 表格預覽 ---------- */
QTableWidget {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER_SOFT};
    font-size: 12px;
    color: {TEXT_SOFT};
}}
QTableWidget::item {{
    padding: 4px 8px;
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
}}
QHeaderView::section {{
    background-color: {BG};
    color: {TEXT};
    border: none;
    border-right: 1px solid {BORDER_SOFT};
    border-bottom: 1px solid {BORDER};
    padding: 7px 10px;
    font-size: 12px;
    font-weight: 600;
}}
QHeaderView::section:hover {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
}}
QTableCornerButton::section {{
    background-color: {BG}; border: none;
}}

/* ---------- 欄位拖曳清單 ---------- */
QListWidget {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 5px;
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}
QListWidget::item {{
    padding: 7px 10px;
    border-radius: 7px;
    margin: 1px 2px;
    color: {TEXT};
}}
QListWidget::item:hover {{
    background-color: {BORDER_SOFT};
}}
QListWidget::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
}}
#selectedList {{
    border: 1px solid {ACCENT};
}}
#listCaption {{
    font-size: 12px;
    font-weight: 600;
    color: {TEXT};
}}
#listCaptionKey {{
    font-size: 12px;
    font-weight: 700;
    color: {ACCENT};
}}
#stepNum {{
    background-color: {ACCENT};
    color: white;
    border-radius: 9px;
    font-size: 11px;
    font-weight: 700;
}}
#listHint {{
    font-size: 11px;
    color: {TEXT_MUTED};
}}
#fieldFilter {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
    color: {TEXT};
}}
#fieldFilter:focus {{
    border-color: {ACCENT};
}}
#moveBtn {{
    font-size: 15px;
    font-weight: 600;
    padding: 5px 9px;
    min-width: 34px;
    color: {TEXT_SOFT};
}}
#emptyNote {{
    font-size: 12px;
    color: {TEXT_MUTED};
}}
"""
