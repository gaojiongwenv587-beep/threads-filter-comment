# threads-filter-comment

> 依賴 [threads-skills](https://github.com/gaojiongwenv587-beep/threads-skills) 提供帖子輸入。

**純篩選工具** — 輸入帖子列表，關鍵詞篩選 + 三維熱度評分 + AI 判斷，輸出適合評論的帖子。

不抓取、不發送，只做篩選。支援 macOS / Linux / Windows。

---

## 環境需求

- Python 3.8+
- Windows 需在 PowerShell 或命令提示字符中執行

---

## 使用方式

### macOS / Linux — 從 stdin（管道）

```bash
cd ~/Desktop/threadsskill/threads-skills
uv run python scripts/cli.py list-feeds --limit 200 \
  | python ~/Desktop/threads-filter-comment/filter-comment.py
```

### Windows — 從 stdin（PowerShell）

```powershell
cd C:\Users\你的用戶名\Desktop\threadsskill\threads-skills
uv run python scripts/cli.py list-feeds --limit 200 `
  | python C:\Users\你的用戶名\Desktop\threads-filter-comment\filter-comment.py
```

> **Windows 注意**：PowerShell 管道符是反引號 `` ` `` 換行，若不換行直接用 `|` 即可。

### 從文件輸入（跨平台）

```bash
# macOS / Linux
python filter-comment.py --posts-file /tmp/posts.json

# Windows
python filter-comment.py --posts-file C:\Users\你\Desktop\posts.json
```

### 三源輸入（Feed + 關鍵詞搜索 + 對標帳號）

```bash
python filter-comment.py \
  --feed-file /tmp/feed.json \
  --keyword-file /tmp/keyword.json \
  --benchmark-file /tmp/benchmark.json
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
  "total_deduplicated": 180,
  "total_filtered": 5,
  "results": [
    {
      "post": { "postId": "...", "content": "...", "url": "...", "likeCount": "..." },
      "sources": ["feed", "keyword"],
      "priority": "high",
      "match_reason": "韓國/首爾相關",
      "score_total": 72.3,
      "score_interaction": 35.0,
      "score_cross_source": 20.0,
      "score_timeliness": 25.0,
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

結果按綜合熱度分（互動 40% + 跨源 35% + 時效 25%）降序排列。

---

## 配置

### macOS / Linux

```bash
cp config.example.json ~/.threads-filter-comment.json
```

### Windows（命令提示字符）

```cmd
copy config.example.json %USERPROFILE%\.threads-filter-comment.json
```

### Windows（PowerShell）

```powershell
Copy-Item config.example.json "$env:USERPROFILE\.threads-filter-comment.json"
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

### macOS / Linux

```bash
# 篩選 → 取第一條 → 發送評論
RESULT=$(uv run python scripts/cli.py list-feeds --limit 200 \
  | python filter-comment.py --only-approved)
URL=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['post']['url'])")
COMMENT=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['ai_comment'])")
uv run python scripts/cli.py reply-thread --url "$URL" --content "$COMMENT"
```

### Windows（PowerShell）

```powershell
# 篩選結果存到臨時文件再處理（Windows 管道對 JSON 更穩定）
uv run python scripts/cli.py list-feeds --limit 200 `
  | python filter-comment.py --only-approved | Out-File -Encoding utf8 $env:TEMP\result.json

$result = Get-Content $env:TEMP\result.json -Raw | ConvertFrom-Json
$url     = $result.results[0].post.url
$comment = $result.results[0].ai_comment
uv run python scripts/cli.py reply-thread --url $url --content $comment
```
