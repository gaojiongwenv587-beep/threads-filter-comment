# threads-filter-comment

> 依賴 [threads-skills](https://github.com/gaojiongwenv587-beep/threads-skills) 作為底層自動化引擎。

從 Threads 首頁推薦抓帖，關鍵詞篩選 + AI 智能判斷，自動發送醫美推廣評論。

**核心流程：**
抓取 200 條首頁帖子 → 關鍵詞篩選（韓國/醫美相關）→ AI 判斷是否適合評論 → 生成評論 → 發送

---

## 系統要求

- macOS / Linux
- Python 3.11+
- [threads-skills](https://github.com/gaojiongwenv587-beep/threads-skills) 已安裝並登入 Threads

---

## 快速開始

### 1. 安裝 threads-skills

```bash
git clone https://github.com/gaojiongwenv587-beep/threads-skills ~/Desktop/threadsskill/threads-skills
cd ~/Desktop/threadsskill/threads-skills
uv sync
python scripts/cli.py check-login
```

### 2. 配置

```bash
cp config.example.json ~/.threads-filter-comment.json
nano ~/.threads-filter-comment.json
```

必填項：
- `account` — threads-skills 帳號名稱
- `threads_skills_dir` — threads-skills 根目錄路徑
- `ai_api_url` / `ai_api_key` — 本地 AI API（兼容 OpenAI 格式）

選填：
- `promo_text` — 推廣文案（留空則只發 AI 評論）
- `promo_mention` — 推廣帳號 @mention

### 3. 執行

```bash
bash run.sh
```

或直接：

```bash
cd ~/Desktop/threadsskill/threads-skills
uv run python ~/Desktop/threads-filter-comment/filter-comment.py
```

---

## 功能特點

- **多級篩選**：高優先（韓國/首爾相關）> 醫美相關，按點讚數排序
- **AI 判斷**：分析帖子身份、情緒、需求，判斷是否適合評論
- **防重複**：自動跳過已回覆的帖子
- **周期控制**：每 N 次後休息，防止帳號過度活躍
- **自動刷新**：未找到合適帖子時最多刷新 5 次

---

## 配置說明

```json
{
  "account": "帳號名稱",
  "threads_skills_dir": "/path/to/threads-skills",
  "ai_api_url": "http://192.168.x.x:8003/v1/chat/completions",
  "ai_api_key": "your_key",
  "ai_model": "Qwen/Qwen3.5-27B-FP8",
  "promo_mention": "@your_clinic",
  "promo_text": "推廣文案",
  "max_runs_per_cycle": 4,
  "rest_duration_hours": 1,
  "keywords": ["醫美", "整形", "護膚", "..."],
  "exclude_keywords": ["診所", "院長", "..."],
  "priority_keywords": ["韓國", "首爾", "江南", "..."]
}
```

---

## 定時任務

```bash
# 每 15 分鐘執行一次
*/15 * * * * bash /path/to/threads-filter-comment/run.sh >> ~/.threads/filter-comment.log 2>&1
```

---

## 日誌

- 執行日誌：`~/.threads/filter-comment.log`（自動創建）
- 狀態文件：`/tmp/threads-filter-comment-state.json`
