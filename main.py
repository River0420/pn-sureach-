import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import pyperclip

from core import applog, hotkey, local_lookup, paths, permission, plat, settings
from core.local_lookup import LocalPriceBook
from ui import native_window, popup as popup_mod, style
from ui.diag_dialog import DiagDialog
from ui.import_dialog import ImportDialog
from ui.popup import PopupWindow

LOCK_PORT = settings.get("app.lock_port", 49731)
PERMISSION_POLL_MS = settings.get("app.permission_poll_ms", 2000)


def acquire_single_instance():
    """用綁定本機 port 當作鎖，避免重複啟動造成熱鍵重複觸發"""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.listen(1)
    except OSError:
        return None
    return sock


def make_icon():
    pix = QPixmap(44, 44)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(style.ACCENT))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(3, 3, 38, 38, 11, 11)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPointSize(20)
    f.setWeight(QFont.Bold)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "P")
    p.end()
    return QIcon(pix)


def install_crash_handler():
    """沒攔到的例外要留下痕跡，而且要讓使用者看得到

    打包成沒有主控台的 exe 之後，未處理的例外預設是「視窗消失，什麼都沒有」。
    使用者只會說「它突然不見了」，而那是最難查的一種回報。
    這裡至少保證兩件事：寫進 log、跳一個看得到的視窗。
    """
    import traceback

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        print("=== 未處理的錯誤 ===\n" + text, flush=True)
        try:
            QMessageBox.critical(
                None, "程式發生錯誤",
                f"{exc_type.__name__}: {exc}\n\n"
                f"詳細內容已寫進：\n{paths.LOG_PATH}\n\n"
                "可以從工作列圖示的「診斷資訊…」複製完整報告。")
        except Exception:
            pass      # 連對話框都開不了（Qt 還沒起來），至少 log 有了

    sys.excepthook = hook


class Bridge(QObject):
    """把背景執行緒的熱鍵事件安全送回 Qt 主執行緒"""
    triggered = Signal()


class LoadSignals(QObject):
    done = Signal(object)


class BookLoader(QRunnable):
    """在背景執行緒讀 Excel 並建索引

    10 萬列的檔案解析要好幾秒，放在主執行緒會讓整個介面凍住
    （開機時凍、按「重新載入」時也凍）。這裡整包在背景做完，
    主執行緒只負責把做好的 Snapshot 換上去，那是一個指派而已。

    signals 一定要由外面傳進來、而且活得比這個 runnable 久：
    QRunnable 跑完會被 Qt 立刻刪掉，如果訊號物件掛在它自己身上，
    跨執行緒的佇列訊號還沒送到主執行緒就跟著消失，載入結果會靜靜地不見。
    """

    def __init__(self, signals):
        super().__init__()
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            snapshot = local_lookup.build_snapshot()
        except Exception as e:                       # 背景執行緒不能讓例外逃走
            snapshot = local_lookup.Snapshot(errors=[str(e)])
        self.signals.done.emit(snapshot)


def main():
    # 第一件事：讓輸出吃得下中文、而且會留下 log。
    # Windows 的主控台預設編碼印不出中文，會在最莫名其妙的地方把程式弄死。
    applog.install()
    install_crash_handler()
    print(f"=== 啟動（{plat.NAME}）===", flush=True)

    lock = acquire_single_instance()
    if lock is None:
        print("已經有一個實例在執行了，這次不重複啟動。", flush=True)
        return
    settings.write_defaults_if_missing()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # 用系統字體物件，不要用字體名稱字串 —— 名稱對不上時 Qt 會去掃整份字體
    # 清單找替代品，開機平白多花 100ms 以上
    base_font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    base_font.setPointSize(style.BASE_SIZE)
    app.setFont(base_font)
    # 常駐小工具：不進 Dock、不進 ⌘Tab，叫出查詢視窗時不會把使用者的畫面切走
    native_window.become_accessory()

    price_book = LocalPriceBook()
    popup = PopupWindow(
        on_search=price_book.search,
        on_status=lambda: price_book.status,
    )
    # 先把視窗建好藏起來，第一次按熱鍵才不會慢半拍
    popup.prewarm()

    state = {"hotkey": None, "loading": False, "announce": False}

    # ---------------- 資料載入 ----------------
    load_signals = LoadSignals()      # 常駐，不能讓它跟著 runnable 一起被回收

    def load_book(announce=False):
        if state["loading"]:
            return
        state["loading"] = True
        state["announce"] = announce
        price_book.mark_loading()
        tray.setToolTip("料號查詢小工具 —— 載入中…")
        act_reload.setEnabled(False)
        QThreadPool.globalInstance().start(BookLoader(load_signals))

    def on_loaded(snapshot):
        announce = state["announce"]
        state["loading"] = False
        price_book.apply(snapshot)
        act_reload.setEnabled(True)

        if snapshot.sources:
            rows = snapshot.row_count
            tray.setToolTip(f"料號查詢小工具　·　{rows:,} 筆資料")
            print(f"已載入 {len(snapshot.sources)} 個檔案、{rows:,} 筆資料"
                  f"（{snapshot.elapsed:.1f} 秒）", flush=True)
            if announce:
                tray.showMessage("料號查詢小工具",
                                 f"已重新載入 {rows:,} 筆資料", make_icon(), 3000)
        else:
            tray.setToolTip("料號查詢小工具　·　尚未匯入 Price Book")

        # 讀檔失敗過去是靜默 continue，使用者只看到「尚未匯入」卻不知道為什麼
        if snapshot.errors:
            for line in snapshot.errors:
                print("載入問題：" + line, flush=True)
            act_error.setText("⚠︎  載入有問題…")
            act_error.setVisible(True)
            state["errors"] = snapshot.errors
        else:
            act_error.setVisible(False)

        if popup.isVisible():
            popup.show_placeholder()

    load_signals.done.connect(on_loaded)

    def show_errors():
        native_window.activate_app()
        QMessageBox.warning(
            None, "載入 Price Book 時有問題",
            "\n".join(state.get("errors", [])) + "\n\n可以從選單列重新匯入。")

    # ---------------- 查詢視窗 ----------------
    def open_popup():
        try:
            text = popup_mod.clipboard_prefill(pyperclip.paste())
        except Exception:
            text = ""
        # 這裡刻意不呼叫 activate_app()：查詢視窗只要鍵盤焦點，
        # 不該把使用者原本的 App 整個切掉
        popup.show_query(prefill=text)

    bridge = Bridge()
    bridge.triggered.connect(open_popup)

    def open_import():
        popup.hide()
        native_window.activate_app()
        dlg = ImportDialog(on_done=lambda: load_book(announce=False))
        dlg.raise_()
        dlg.activateWindow()
        dlg.exec()

    # ---------------- 熱鍵 ----------------
    def start_hotkey():
        """開熱鍵之前一定要先把舊的關掉

        以前沒有 stop()，權限關掉再打開就會疊出第二個 event tap，
        按一次熱鍵會跳兩次視窗。
        """
        stop_hotkey()
        listener = hotkey.start(bridge.triggered.emit)
        state["hotkey"] = listener
        ok = bool(listener and listener.ok)
        state["hotkey_error"] = "" if ok else (getattr(listener, "error", "") or "原因不明")
        if ok:
            print(f"熱鍵 {hotkey.HOTKEY_LABEL}：已掛上", flush=True)
        else:
            print(f"熱鍵 {hotkey.HOTKEY_LABEL}：掛不上 —— {state['hotkey_error']}", flush=True)
        # 熱鍵掛不上不是致命的（圖示選單照樣能查），但一定要看得見，
        # 不然使用者只會覺得「按了沒反應」然後放棄
        act_hotkey.setVisible(not ok and not permission.NEEDED)
        return ok

    def stop_hotkey():
        listener = state.get("hotkey")
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        state["hotkey"] = None

    def show_hotkey_help():
        """熱鍵掛不上時的說明（Windows 主要會用到這個）

        最常見的原因是熱鍵被別的常駐程式先註冊走了，所以重點是
        「怎麼換一組」，而不是「怎麼修好這一組」。
        """
        native_window.activate_app()
        box = QMessageBox()
        box.setWindowTitle("熱鍵沒掛上")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"{hotkey.HOTKEY_LABEL} 現在不會有反應")
        box.setInformativeText(
            f"原因：{state.get('hotkey_error') or '不明'}\n\n"
            "在那之前，點工作列圖示 → 查詢，功能完全一樣。\n\n"
            "要換一組熱鍵的話，關掉程式，打開 config/settings.json，改這兩行：\n"
            '    "key": "space"          （可填 space / f2 / q …）\n'
            '    "modifiers": ["alt"]    （ctrl / alt / shift / cmd）\n'
            "存檔後重開程式。\n\n"
            "詳細情況可以從選單的「診斷資訊…」複製給對方看。"
        )
        box.setStandardButtons(QMessageBox.Ok)
        diag_btn = box.addButton("看診斷資訊", QMessageBox.ActionRole)
        box.exec()
        if box.clickedButton() is diag_btn:
            open_diag()

    def open_diag():
        native_window.activate_app()
        listener = state.get("hotkey")
        DiagDialog(
            price_book=price_book,
            hotkey_state={
                "ok": bool(listener and listener.ok),
                "error": state.get("hotkey_error", ""),
                "label": hotkey.HOTKEY_LABEL,
            },
        ).exec()

    def show_permission_help():
        native_window.activate_app()
        owner = permission.responsible_app()
        target = f"「{owner}」" if owner else "這次啟動用的那個 App"
        box = QMessageBox()
        box.setWindowTitle("需要「輔助使用」權限")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"{hotkey.HOTKEY_LABEL} 熱鍵現在不會有反應")
        box.setInformativeText(
            f"請到 系統設定 → 隱私權與安全性 → 輔助使用，把 {target} 打開。\n\n"
            "（macOS 的權限是記在「啟動這個程式的那個 App」身上，不是記在程式本身，"
            f"所以這次要開的是 {target}。換一種方式啟動就得再給一次。）\n\n"
            "打開之後不用重開，程式會自己接上。\n"
            "在那之前，點選單列的橘色 P 圖示 → 查詢，一樣可以用。"
        )
        box.setStandardButtons(QMessageBox.Ok)
        open_btn = box.addButton("打開系統設定", QMessageBox.ActionRole)
        box.setDefaultButton(open_btn)
        box.exec()
        if box.clickedButton() is open_btn:
            permission.open_settings()

    def watch_permission(trusted_now):
        """持續盯著權限狀態

        權限隨時可能被開或被關，而 event tap 只在建立的那一刻檢查一次，
        失敗就安靜地什麼都不做 —— 使用者按了沒反應也不知道為什麼。
        這裡每兩秒看一次，一開就自己把熱鍵接回來，一關就把警告放回選單。
        """
        watch_state = {"trusted": trusted_now}
        timer = QTimer()

        def poll():
            trusted = permission.is_trusted()
            if trusted == watch_state["trusted"]:
                return
            watch_state["trusted"] = trusted
            act_perm.setVisible(not trusted)
            if trusted:
                start_hotkey()
                tray.showMessage(
                    "料號查詢小工具",
                    f"權限已開啟，現在可以按 {hotkey.HOTKEY_LABEL} 查詢了",
                    make_icon(),
                    4000,
                )
            else:
                stop_hotkey()

        timer.timeout.connect(poll)
        timer.start(PERMISSION_POLL_MS)
        state["perm_timer"] = timer

    # ---------------- 結束 ----------------
    def quit_app():
        stop_hotkey()
        try:
            lock.close()
        except Exception:
            pass
        tray.hide()
        app.quit()

    # ---------------- 選單列 ----------------
    tray = QSystemTrayIcon(make_icon())
    tray.setToolTip("料號查詢小工具")
    menu = QMenu()
    act_query = QAction(f"查詢          {hotkey.HOTKEY_LABEL}", menu)
    act_query.triggered.connect(open_popup)
    menu.addAction(act_query)
    menu.addSeparator()
    act_perm = QAction("⚠︎  開啟輔助使用權限…", menu)
    act_perm.triggered.connect(show_permission_help)
    act_perm.setVisible(False)
    menu.addAction(act_perm)
    act_hotkey = QAction("⚠︎  熱鍵沒掛上…", menu)
    act_hotkey.triggered.connect(show_hotkey_help)
    act_hotkey.setVisible(False)
    menu.addAction(act_hotkey)
    act_error = QAction("⚠︎  載入有問題…", menu)
    act_error.triggered.connect(show_errors)
    act_error.setVisible(False)
    menu.addAction(act_error)
    act_import = QAction("匯入 Price Book…", menu)
    act_import.triggered.connect(open_import)
    menu.addAction(act_import)
    act_reload = QAction("重新載入", menu)
    act_reload.triggered.connect(lambda: load_book(announce=True))
    menu.addAction(act_reload)
    menu.addSeparator()
    act_diag = QAction("診斷資訊…", menu)
    act_diag.triggered.connect(open_diag)
    menu.addAction(act_diag)
    act_quit = QAction("結束", menu)
    act_quit.triggered.connect(quit_app)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.show()

    # ---------------- 起跑 ----------------
    load_book()

    if not hotkey.AVAILABLE:
        print(f"熱鍵後端不可用：{hotkey.UNAVAILABLE_REASON}", flush=True)

    if permission.NEEDED:
        # macOS：沒有輔助使用權限的話，熱鍵會安靜地失效 —— 一定要講出來
        trusted = permission.is_trusted()
        if trusted:
            start_hotkey()
        act_perm.setVisible(not trusted)
        if not trusted:
            print("沒有輔助使用權限，熱鍵不會有反應", flush=True)
            permission.request()
            show_permission_help()
        watch_permission(trusted)
    else:
        # Windows：不需要權限，直接註冊。失敗的話選單會出現警告項目，
        # 而且工作列圖示 → 查詢照樣能用，不會變成完全不能操作的狀態。
        if not start_hotkey():
            show_hotkey_help()

    print(f"已啟動，常駐選單列。按 {hotkey.HOTKEY_LABEL} 查詢。", flush=True)

    code = app.exec()
    stop_hotkey()
    sys.exit(code)


if __name__ == "__main__":
    main()
