# threads-filter-comment - Threads 筛选评论技能

## 概述
基于首页推荐流，通过关键词筛选 + AI 智能判断，自动评论合适的帖子。支持自定义关键词、AI 分析、防重复评论、周期性执行控制。

## 使用场景
- 主动推广：在首页推荐中寻找潜在客户并评论
- 内容营销：筛选与品牌相关的帖子进行互动
- 社群运营：自动发现并回复目标受众的内容

## 触发方式

### 自然语言触发
```
"筛选评论首页推荐"
"搜索医美相关帖子并评论"
"在首页找合适的帖子评论"
```

### CLI 命令
```bash
cd /opt/homebrew/lib/node_modules/openclaw/skills/threads-skills
. .venv/bin/activate
python scripts/cli.py filter-comment --mode home-feed --keywords "医美，整形"
```

## 功能特性

### 1. 多级筛选
- **关键词过滤**：支持目标关键词（包含）和排除关键词（排除）
- **AI 智能判断**：分析帖子内容、作者身份、情绪、需求，判断是否适合评论
- **优先级排序**：韩国相关 > 医美相关 > 其他

### 2. 智能刷新
- 未找到合适帖子时自动刷新首页
- 最多尝试 5 次，每次刷新获取新内容
- 避免重复评论同一帖子

### 3. 周期控制
- 每周期执行 N 次后自动休息
- 防止过度活跃导致账号风险
- 状态持久化保存

### 4. AI 评论生成
- 分析帖子内容和上下文
- 生成自然、贴切的评论
- 自动附加推广信息（可选）

## 配置选项

### 环境变量
```bash
THREADS_ACCOUNT="账号 3"           # Threads 账号名称
THREADS_KEYWORDS="医美，整形，护肤"   # 目标关键词（逗号分隔）
THREADS_EXCLUDE="醫院，診所，價格"    # 排除关键词（逗号分隔）
THREADS_MAX_RUNS=4                 # 每周期最大执行次数
THREADS_REST_HOURS=1               # 休息时间（小时）
THREADS_AI_ENABLED=true            # 是否启用 AI 分析
THREADS_PROMO_TEXT="..."           # 推广文案（可选）
```

### 配置文件
创建 `~/.threads-filter-comment.json`：
```json
{
  "account": "账号 3",
  "keywords": ["医美", "整形", "护肤", "抗老"],
  "exclude": ["醫院", "診所", "價格", "優惠"],
  "korea_keywords": ["韓國", "首爾", "江南"],
  "max_runs_per_cycle": 4,
  "rest_duration_hours": 1,
  "ai_enabled": true,
  "ai_api_url": "http://localhost:8003/v1/chat/completions",
  "ai_api_key": "YOUR_KEY",
  "promo_text": "推广文案内容"
}
```

## 工作流程

```
1. 抓取首页推荐（200 条）
   ↓
2. 关键词筛选（韩国相关 > 医美相关）
   ↓
3. AI 分析（身份/情绪/需求/适合度）
   ↓
4. 生成评论（AI 评论 + 推广文案）
   ↓
5. 检查是否已回复
   ↓
6. 发送评论
   ↓
7. 更新执行状态
```

## 输出示例

### 成功评论
```
✅ 成功评论 1 条帖子
帖子链接：https://www.threads.net/@username/post/ABC123
帖子内容：最近想去韓國做醫美，有推薦嗎...
AI 评论：蠻認同的！最近也在研究醫美保養...
```

### 跳过（不适合）
```
⚠️ 本次执行跳过：尝试 5 次后仍未找到合适帖子
```

### 周期休息
```
⏸️ 休息中，還有 45 分鐘
   本周期已执行 4/4 次
```

## 高级用法

### 自定义 AI 提示词
修改 `analyze_post_with_ai()` 函数中的 prompt 参数，调整 AI 的判断逻辑和评论风格。

### 多账号轮询
```bash
for account in "账号 1" "账号 2" "账号 3"; do
  THREADS_ACCOUNT=$account python filter-comment.py
  sleep 60
done
```

### 定时任务集成
```bash
# crontab -e
*/15 * * * * cd /path/to/skill && python filter-comment.py >> log.txt 2>&1
```

## 日志文件
- **执行日志**：`~/workspace/threads-filter-comment-log.txt`
- **已回复帖子**：通过 `list-replied` 命令记录
- **状态文件**：`/tmp/threads-filter-comment-state.json`

## 故障排查

### 问题：抓取失败
**原因**：未登录 / Chrome 未运行 / 网络问题
**解决**：先执行 `check-login` 检查登录状态

### 问题：AI 分析超时
**原因**：AI API 不可达 / 响应慢
**解决**：检查 AI 服务状态，或设置 `THREADS_AI_ENABLED=false` 跳过 AI 分析

### 问题：重复评论
**原因**：已回复记录丢失
**解决**：检查 `list-replied` 功能是否正常，手动清理重复记录

## 相关文件
- `filter-comment.py` - 主脚本
- `config.example.json` - 配置示例
- `README.md` - 详细说明

## 依赖
- threads-skills（主技能）
- Python 3.8+
- requests, json, subprocess

## 更新日志
- v1.0.0 (2026-03-23)
  - 初始版本
  - 支持关键词筛选 + AI 判断
  - 支持周期控制
  - 支持自动刷新重试
