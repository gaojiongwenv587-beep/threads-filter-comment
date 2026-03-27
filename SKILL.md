---
name: threads-filter-comment
description: "Threads 醫美 AI 篩選。觸發詞：篩選帖子、AI篩選、醫美篩選、過濾帖子、找適合評論的帖子、哪些帖子適合評論、篩選目標用戶、找潛在客戶帖子、醫美相關帖子篩選、filter-comment。輸入帖子JSON，輸出AI判斷後適合評論的候選列表，不抓取不發送。"
---

# threads-filter-comment — 醫美篩選 Skill

純篩選工具：接收帖子 JSON → 關鍵詞過濾 → AI 判斷 → 返回候選帖子列表。

## 🚫 內容禁區（最高優先級）

絕對禁止處理任何政治相關內容，遇到自動過濾跳過。

## 語言規則（強制）

AI 生成的評論建議一律使用**繁體中文**。

---

## 使用方式

### 基本用法（管道）

```bash
# 先抓帖，再篩選
uv run python scripts/cli.py list-feeds --limit 200 | python filter-comment.py

# 只輸出 AI 同意評論的結果
uv run python scripts/cli.py list-feeds --limit 200 | python filter-comment.py --only-approved
```

### 從文件輸入

```bash
python filter-comment.py --posts-file /tmp/posts.json
python filter-comment.py --posts-file /tmp/posts.json --only-approved
```

### 僅關鍵詞篩選（不調 AI）

```bash
python filter-comment.py --no-ai --posts-file /tmp/posts.json
```

---

## 輸出格式

```json
{
  "total_input": 200,
  "total_filtered": 5,
  "results": [
    {
      "post": { "postId": "...", "url": "...", "content": "...", "likeCount": "..." },
      "priority": "high",
      "match_reason": "韓國/首爾相關",
      "ai_should_comment": true,
      "ai_comment": "蠻認同的！最近也在研究...",
      "ai_reason": "作者有潛在需求"
    }
  ]
}
```

- `priority: "high"` — 含韓國/首爾/江南等高優先關鍵詞
- `priority: "medium"` — 含醫美/護膚/整形等一般關鍵詞
- 結果按優先級降序、點讚數降序排列

---

## 配置文件

`~/.threads-filter-comment.json`，複製 `config.example.json` 修改：

| 欄位 | 說明 |
|------|------|
| `ai_enabled` | 是否啟用 AI 判斷 |
| `ai_api_url` | AI API 地址（兼容 OpenAI 格式） |
| `ai_api_key` | AI API 密鑰 |
| `ai_model` | 模型名稱 |
| `keywords` | 目標關鍵詞（醫美相關） |
| `exclude_keywords` | 排除關鍵詞（同業/廣告） |
| `priority_keywords` | 高優先關鍵詞（韓國/首爾） |

---

## 典型工作流

1. 用 `list-feeds` 或 `search` 抓帖子
2. 輸入本 Skill 篩選
3. 取 `results[0]`（最優帖子）
4. 用 `reply-thread` 發送 `ai_comment`
