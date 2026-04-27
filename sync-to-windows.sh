#!/bin/bash
# MediaSpider 同步脚本 - Linux (WSL) -> Windows

SRC="/home/anpromole/workspace/doge-code/MediaSpider"
DST="/mnt/c/Users/pc/Desktop/test/MediaSpider"

# 排除项
EXCLUDES=(
    ".git"
    "__pycache__"
    "*.pyc"
    ".idea"
    "venv"
    "*.log"
    ".DS_Store"
    ".data"
    ".config"
)

# 构建 rsync 排除参数
RSYNC_EXCLUDES=()
for exc in "${EXCLUDES[@]}"; do
    RSYNC_EXCLUDES+=("--exclude=$exc")
done

echo "=== MediaSpider 同步 (Linux -> Windows) ==="
echo "源目录：$SRC"
echo "目标目录：$DST"
echo ""

# 执行同步
rsync -av --delete "${RSYNC_EXCLUDES[@]}" "$SRC/" "$DST/"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ 同步完成"
else
    echo ""
    echo "✗ 同步失败"
    exit 1
fi
