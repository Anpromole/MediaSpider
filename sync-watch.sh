#!/bin/bash
# MediaSpider 实时同步监听脚本 (轻量级轮询)

SRC="/home/anpromole/workspace/doge-code/MediaSpider"
DST="/mnt/c/Users/pc/Desktop/test/MediaSpider"
SYNC_SCRIPT="$SRC/sync-to-windows.sh"
STATE_FILE="/tmp/mediaspider-sync-state"

# 仅监控关键文件的修改时间
get_state() {
    find "$SRC" -type f \( -name "*.py" -o -name "*.md" -o -name "*.json" \) \
        ! -path "*/.git/*" ! -path "*/__pycache__/*" ! -path "*/venv/*" ! -path "*/.idea/*" \
        ! -path "*/.data/*" ! -path "*/.config/*" \
        -printf '%T@ %p\n' 2>/dev/null | sort
}

echo "=== MediaSpider 实时同步监听 (轻量级) ==="
echo "监控目录：$SRC"
echo "目标目录：$DST"
echo "轮询间隔：5 秒 (低占用)"
echo ""

get_state > "$STATE_FILE"

while true; do
    sleep 5
    CURRENT=$(get_state)
    PREV=$(cat "$STATE_FILE")

    if [ "$CURRENT" != "$PREV" ]; then
        echo "[$(date '+%H:%M:%S')] 文件变化 -> 同步中..."
        echo "$CURRENT" > "$STATE_FILE"
        "$SYNC_SCRIPT" >/dev/null 2>&1 && echo "  ✓ 同步完成" || echo "  ✗ 同步失败"
    fi
done
