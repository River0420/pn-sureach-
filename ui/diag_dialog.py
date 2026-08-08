"""診斷報告視窗

只有一個重點：**「複製全部」那顆按鈕要好按**。這個視窗存在的目的
不是給人閱讀，是讓使用者把整份報告複製起來帶去問人。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from core import diagnostics, paths
from ui import style


class DiagDialog(QDialog):
    def __init__(self, price_book=None, hotkey_state=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("診斷資訊")
        self.resize(680, 620)
        self.text = diagnostics.report(price_book, hotkey_state)

        box = QVBoxLayout(self)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(10)

        head = QLabel("下面這段是程式的自我檢查結果。有問題的話，"
                      "按「複製全部」再貼給對方，比描述症狀有用得多。")
        head.setWordWrap(True)
        box.addWidget(head)

        view = QPlainTextEdit(self.text)
        view.setReadOnly(True)
        # 等寬字：報告是對齊排版的，用比例字體會全部歪掉
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPointSize(11)
        view.setFont(mono)
        view.setLineWrapMode(QPlainTextEdit.NoWrap)
        box.addWidget(view, 1)

        row = QHBoxLayout()
        self.note = QLabel("")
        row.addWidget(self.note, 1)

        save_btn = QPushButton("存成檔案")
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)

        copy_btn = QPushButton("複製全部")
        copy_btn.setDefault(True)
        copy_btn.clicked.connect(self._copy)
        row.addWidget(copy_btn)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        box.addLayout(row)

        self.setStyleSheet(style.DIALOG_QSS)

    def _copy(self):
        QApplication.clipboard().setText(self.text)
        self.note.setText("已複製到剪貼簿 ✓")

    def _save(self):
        """存到程式旁邊，不跳存檔對話框

        會用到這個功能的時候通常是程式怪怪的，少一個對話框就少一個變數。
        路徑直接寫在畫面上讓使用者自己去拿。
        """
        path = paths.LOG_PATH.replace(".log", "-診斷.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text)
            self.note.setText(f"已存到 {path}")
        except Exception as e:
            self.note.setText(f"存檔失敗：{e}")
