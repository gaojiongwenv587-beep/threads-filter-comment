#!/bin/bash
# 醫美篩選評論 — 便捷執行腳本
# 使用方式：bash run.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 讀取 threads_skills_dir（從 config 文件）
CONFIG_FILE="$HOME/.threads-filter-comment.json"
if [ -f "$CONFIG_FILE" ]; then
    THREADS_DIR=$(python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d.get('threads_skills_dir',''))" 2>/dev/null)
fi

# 預設路徑
if [ -z "$THREADS_DIR" ]; then
    THREADS_DIR="$HOME/Desktop/threadsskill/threads-skills"
fi

# 用 threads-skills 的 uv 環境執行
cd "$THREADS_DIR"
uv run python "$SCRIPT_DIR/filter-comment.py"
