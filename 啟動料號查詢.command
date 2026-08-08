#!/bin/bash
# 雙擊這個檔案就能啟動料號查詢小工具
cd "$(dirname "$0")"

PY="${SOURCING_PYTHON:-python3}"

# 鎖定用的 port 從設定檔讀，改了設定這裡也會跟著對
PORT=$("$PY" - <<'EOF' 2>/dev/null || echo 49731
from core import settings
print(settings.get("app.lock_port", 49731))
EOF
)

if "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$PORT))==0 else 1)" 2>/dev/null; then
    echo "料號查詢小工具已經在執行中了。"
    echo "→ 按 Option+空白鍵 就能查詢"
    echo ""
    echo "（這個視窗可以關掉）"
    sleep 3
    exit 0
fi

echo "正在啟動料號查詢小工具…"
nohup "$PY" -u main.py > sourcing-tool.log 2>&1 &
APP_PID=$!
sleep 3

# 用 PID 判斷，不要用 pgrep 比對指令字串（換個啟動方式就比對不到）
if kill -0 "$APP_PID" 2>/dev/null; then
    echo ""
    echo "  已啟動！"
    echo "  · 按 Option+空白鍵（⌥Space）呼叫查詢視窗"
    echo "  · 選單列（右上角）橘色 P 圖示可匯入 Price Book"
    echo ""
    echo "  這個視窗可以直接關掉，程式會繼續在背景執行。"
else
    echo ""
    echo "  啟動失敗，錯誤訊息："
    cat sourcing-tool.log
fi
sleep 4
