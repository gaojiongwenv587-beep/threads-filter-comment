#!/bin/bash
# Threads 筛选评论 - 测试脚本

echo "🧪 测试 Threads 筛选评论 Skill"
echo "=========================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/../../.."

# 1. 检查文件完整性
echo ""
echo "1️⃣  检查文件完整性..."
FILES=(
    "SKILL.md"
    "filter-comment.py"
    "cli.py"
    "config.example.json"
    "README.md"
    "run.sh"
)

all_exist=true
for file in "${FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$file" ]; then
        echo "   ✅ $file"
    else
        echo "   ❌ $file (缺失)"
        all_exist=false
    fi
done

if [ "$all_exist" = true ]; then
    echo "   🎉 所有文件完整"
else
    echo "   ⚠️  部分文件缺失"
    exit 1
fi

# 2. 检查 Python 语法
echo ""
echo "2️⃣  检查 Python 语法..."
cd "$SKILL_DIR"
if [ -d ".venv" ]; then
    . .venv/bin/activate
    python -m py_compile "$SCRIPT_DIR/filter-comment.py"
    if [ $? -eq 0 ]; then
        echo "   ✅ Python 语法正确"
    else
        echo "   ❌ Python 语法错误"
        exit 1
    fi
else
    echo "   ⚠️  虚拟环境不存在，跳过语法检查"
fi

# 3. 检查配置文件
echo ""
echo "3️⃣  检查配置文件..."
if [ -f "~/.threads-filter-comment.json" ]; then
    echo "   ✅ 配置文件存在"
    echo "   配置内容："
    cat ~/.threads-filter-comment.json | python -m json.tool --indent 2 | head -20
else
    echo "   ⚠️  配置文件不存在"
    echo "   请复制示例配置：cp $SCRIPT_DIR/config.example.json ~/.threads-filter-comment.json"
fi

# 4. 检查 Threads 登录状态
echo ""
echo "4️⃣  检查 Threads 登录状态..."
if [ -d ".venv" ]; then
    python scripts/cli.py check-login --account "账号 3" | head -10
else
    echo "   ⚠️  虚拟环境不存在"
fi

echo ""
echo "=========================="
echo "✅ 测试完成"
