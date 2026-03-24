# threads-filter-comment

> 依賴 [threads-skills](https://github.com/gaojiongwenv587-beep/threads-skills) 提供帖子輸入。

**純篩選工具** — 輸入帖子列表，關鍵詞篩選 + AI 判斷，輸出適合評論的帖子。

不抓取、不發送，只做篩選。

---

## 使用方式

### 從 stdin（管道）

```bash
cd ~/Desktop/threadsskill/threads-skills
uv run python scripts/cli.py list-feeds --limit 200 | python ~/Desktop/threads-filter-comment/filter-comment.py
```

### 從文件

```bash
python filter-comment.py --posts-file /tmp/posts.json
```

### 只做關鍵詞篩選（不調 AI）

```bash
python filter-comment.py --no-ai --posts-file /tmp/posts.json
```

### 只輸出 AI 同意評論的帖子

```bash
python filter-comment.py --only-approved --posts-file /tmp/posts.json
```

---

## 輸出格式

```json
{
  "total_input": 200,
  "total_filtered": 5,
  "results": [
    {
      "post": { "postId": "...", "content": "...", "url": "...", "likeCount": "..." },
      "priority": "high",
      "match_reason": "韓國/首爾相關",
      "ai_should_comment": true,
      "ai_comment": "蠻認同的！最近也在研究...",
      "ai_reason": "作者有潛在需求"
    }
  ]
}
```

`priority` 值：
- `high` — 含韓國/首爾/江南等高優先關鍵詞
- `medium` — 含醫美/護膚/變美等一般關鍵詞

結果按優先級降序、點讚數降序排列。

---

## 配置

複製配置文件：

```bash
cp config.example.json ~/.threads-filter-comment.json
```

關鍵欄位：

```json
{
  "ai_enabled": true,
  "ai_api_url": "http://192.168.x.x:8003/v1/chat/completions",
  "ai_api_key": "your_key",
  "ai_model": "Qwen/Qwen3.5-27B-FP8",
  "keywords": ["醫美", "整形", "護膚", "..."],
  "exclude_keywords": ["診所", "院長", "優惠", "..."],
  "priority_keywords": ["韓國", "首爾", "江南", "..."]
}
```

---

## 與 threads-skills 組合使用

篩選後的結果由外部（OpenClaw / 腳本）決定如何處理：

```bash
# 篩選 → 取第一條 → 發送評論
RESULT=$(uv run python scripts/cli.py list-feeds --limit 200 | python filter-comment.py --only-approved)
URL=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['post']['url'])")
COMMENT=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['ai_comment'])")
uv run python scripts/cli.py reply-thread --url "$URL" --content "$COMMENT"
```
