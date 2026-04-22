#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Threads 醫美篩選 — 純篩選工具。

從 stdin 或 --posts-file 讀入帖子 JSON，
關鍵詞篩選 + 三維熱度評分 + AI 判斷，輸出適合評論的帖子列表。

使用方式：
    # 單源（從 stdin）
    uv run python scripts/cli.py list-feeds --limit 200 | python filter-comment.py

    # 單源（從文件）
    python filter-comment.py --posts-file /tmp/posts.json

    # 三源（Feed + 關鍵詞搜索 + 對標帳號）
    python filter-comment.py \\
        --feed-file /tmp/feed.json \\
        --keyword-file /tmp/keyword.json \\
        --benchmark-file /tmp/benchmark.json

    # 關閉 AI（只做關鍵詞篩選 + 評分）
    python filter-comment.py --no-ai --posts-file /tmp/posts.json

輸出（stdout JSON）：
    {
      "total_input": 200,
      "total_deduplicated": 180,
      "total_filtered": 5,
      "results": [
        {
          "post": { ...原始帖子欄位... },
          "sources": ["feed", "keyword"],
          "priority": "high",
          "match_reason": "韓國相關",
          "score_total": 72.3,
          "score_interaction": 35.0,
          "score_cross_source": 20.0,
          "score_timeliness": 25.0,
          "ai_should_comment": true,
          "ai_comment": "...",
          "ai_reason": "..."
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
from pathlib import Path


def _ensure_utf8_streams() -> None:
    """Windows 下強制 stdin/stdout/stderr 使用 UTF-8，避免中文亂碼。"""
    if sys.platform != "win32":
        return
    if hasattr(sys.stdin, "buffer"):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


CONFIG_FILE = Path.home() / ".threads-filter-comment.json"

DEFAULT_CONFIG = {
    "ai_enabled": True,
    "ai_api_url": "",
    "ai_api_key": "",
    "ai_model": "Qwen/Qwen3.5-27B-FP8",

    "keywords": [
        "外貌", "皮膚", "保養", "護膚", "抗老", "美白", "痘痘", "毛孔", "斑點",
        "醫美", "整形", "微整", "玻尿酸", "肉毒", "雷射", "光療", "美容診所",
        "自信", "變美", "外貌焦慮", "素顏", "底妝", "遮瑕",
    ],
    "exclude_keywords": [
        "醫院", "診所", "院長", "醫生推薦", "我們家", "歡迎預約", "歡迎諮詢",
        "價格", "優惠", "促銷", "line:", "微信", "wechat",
    ],
    "priority_keywords": [
        "韓國", "首爾", "江南", "釜山",
        "韓國醫美", "首爾醫美", "飛韓國",
    ],
}

POLITICAL_KEYWORDS = [
    "政治", "政府", "總統", "選舉", "政策", "議員", "政黨",
    "民主", "獨裁", "共產", "資本主義", "社會主義",
]


# ─── 輔助函式 ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[warn] 讀取配置失敗：{e}", file=sys.stderr)
    return config


def parse_count(val: object) -> int:
    """將 likeCount / replyCount / repostCount 轉為整數。支援 '1.2K'、'3M'。"""
    if val is None:
        return 0
    s = str(val).strip().replace(",", "")
    try:
        if s.upper().endswith("K"):
            return int(float(s[:-1]) * 1_000)
        if s.upper().endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        return int(float(s))
    except Exception:
        return 0


def load_posts_from_file(path: str, source: str) -> list[dict]:
    """載入帖子文件，為每條帖子打上 _source 標籤。"""
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict):
        posts = data.get("posts", data.get("feeds", data.get("results", [])))
    elif isinstance(data, list):
        posts = data
    else:
        posts = []
    for post in posts:
        post["_source"] = source
    return posts


def merge_and_deduplicate(all_posts: list[dict]) -> list[dict]:
    """去重，同一 postId 合併 sources 集合。"""
    seen: dict[str, dict] = {}
    for post in all_posts:
        pid = post.get("postId") or post.get("url", "")
        source = post.pop("_source", "feed")
        if pid not in seen:
            seen[pid] = post
            seen[pid]["_sources"] = {source}
        else:
            seen[pid]["_sources"].add(source)
    return list(seen.values())


# ─── 三維熱度評分 ──────────────────────────────────────────────────────────────

def _cross_source_score(sources: set[str]) -> float:
    """跨源驗證分（滿分 35）。

    三源同時出現 → 35  最強熱點信號
    Feed + 對標  → 22  平台推流 + 同行關注
    Feed + 關鍵詞 → 20  平台推流 + 主動搜索
    僅 Feed      → 10
    僅關鍵詞     → 8
    僅對標帳號   → 8
    """
    has_feed      = "feed" in sources
    has_keyword   = "keyword" in sources
    has_benchmark = "benchmark" in sources
    if has_feed and has_keyword and has_benchmark:
        return 35.0
    if has_feed and has_benchmark:
        return 22.0
    if has_feed and has_keyword:
        return 20.0
    if has_feed:
        return 10.0
    if has_keyword:
        return 8.0
    if has_benchmark:
        return 8.0
    return 0.0


def _timeliness_score(created_at_raw: object, now: float) -> float:
    """時效性分（滿分 25）。

    0-6h   → 25.0  發酵中，參與價值最高
    6-24h  → 16.7  正常
    24-48h → 10.0  熱度衰減
    48h+   →  3.3  基本冷卻
    """
    if not created_at_raw:
        return 5.0
    try:
        ts = float(str(created_at_raw).strip())
    except Exception:
        return 5.0

    age_hours = (now - ts) / 3600
    if age_hours <= 6:
        multiplier = 1.000   # 原始 ×1.5，歸一化後 1.0
    elif age_hours <= 24:
        multiplier = 0.667   # ×1.0 / 1.5
    elif age_hours <= 48:
        multiplier = 0.400   # ×0.6 / 1.5
    else:
        multiplier = 0.133   # ×0.2 / 1.5
    return round(25.0 * multiplier, 1)


def compute_scores(candidates: list[dict], now: float) -> list[dict]:
    """計算三維熱度分並寫回 candidates，按綜合分降序排列。

    互動分（40）：歸一化(點贊 + 回覆×2 + 轉發×3)
    跨源分（35）：根據來源組合給分
    時效分（25）：根據發帖時間衰減
    綜合分 = 互動×0.4 + 跨源×0.35 + 時效×0.25
    """
    # 計算原始互動值，用於全局歸一化
    raw_interactions = []
    for item in candidates:
        post = item["post"]
        raw = (
            parse_count(post.get("likeCount"))
            + parse_count(post.get("replyCount")) * 2
            + parse_count(post.get("repostCount")) * 3
        )
        raw_interactions.append(raw)

    max_interaction = max(raw_interactions, default=1) or 1

    for item, raw in zip(candidates, raw_interactions):
        i_score = round((raw / max_interaction) * 40.0, 1)
        c_score = _cross_source_score(item.get("_sources", {"feed"}))
        t_score = _timeliness_score(item["post"].get("createdAt"), now)

        item["score_interaction"]  = i_score
        item["score_cross_source"] = c_score
        item["score_timeliness"]   = t_score
        item["score_total"]        = round(i_score * 0.4 + c_score * 0.35 + t_score * 0.25, 1)

    candidates.sort(key=lambda x: x["score_total"], reverse=True)
    return candidates


# ─── 關鍵詞篩選 ────────────────────────────────────────────────────────────────

def keyword_filter(posts: list[dict], config: dict) -> list[dict]:
    """關鍵詞篩選，返回帶優先級的候選列表（保留 _sources）。"""
    keywords     = config.get("keywords", DEFAULT_CONFIG["keywords"])
    exclude      = config.get("exclude_keywords", DEFAULT_CONFIG["exclude_keywords"])
    priority_kws = config.get("priority_keywords", DEFAULT_CONFIG["priority_keywords"])

    results = []
    for post in posts:
        content = post.get("content", "")

        if any(kw in content for kw in POLITICAL_KEYWORDS):
            continue
        if any(kw in content for kw in exclude):
            continue

        if any(kw in content for kw in priority_kws):
            results.append({
                "post": post,
                "priority": "high",
                "match_reason": "韓國/首爾相關",
                "_sources": post.get("_sources", {"feed"}),
            })
        elif any(kw in content for kw in keywords):
            results.append({
                "post": post,
                "priority": "medium",
                "match_reason": "醫美相關",
                "_sources": post.get("_sources", {"feed"}),
            })

    return results


# ─── AI 分析 ───────────────────────────────────────────────────────────────────

def analyze_with_ai(content: str, config: dict) -> dict | None:
    """AI 判斷是否適合評論並生成評論文字。"""
    api_url = config.get("ai_api_url", "")
    api_key = config.get("ai_api_key", "")
    if not api_url or not api_key:
        print("  [warn] AI 未配置（ai_api_url / ai_api_key 為空）", file=sys.stderr)
        return None

    prompt = f"""你是一個台灣女孩，關注醫美保養。判斷是否要在這個帖子留言。

帖子內容：{content}

判斷標準：
✅ 適合：作者有潛在需求（求建議、規劃、好奇）、情緒正面或中性
❌ 不適合：純吐槽/抱怨、從業人員、情緒負面、留言會顯得突兀

直接返回 JSON（不要其他文字）：
{{"should_comment":true/false,"reason":"理由","comment":"如果適合，寫出繁體中文評論（50-150字，自然呼應帖子後帶出醫美話題，禁硬廣）"}}"""

    try:
        data = json.dumps({
            "model": config.get("ai_model", DEFAULT_CONFIG["ai_model"]),
            "messages": [
                {"role": "system", "content": "你是台灣女孩，用繁體中文回覆。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 400,
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")

        req = urllib.request.Request(
            api_url, data=data,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = (result["choices"][0]["message"].get("content") or
                    result["choices"][0]["message"].get("reasoning") or "")
            s, e = text.find("{"), text.rfind("}") + 1
            if s >= 0 and e > s:
                return json.loads(text[s:e])
    except Exception as ex:
        print(f"  AI 分析失敗：{ex}", file=sys.stderr)
    return None


# ─── 主流程 ────────────────────────────────────────────────────────────────────

def run(posts: list[dict], config: dict, ai_enabled: bool, total_input: int) -> dict:
    """主篩選邏輯。

    1. 關鍵詞篩選（排除廣告/政治）
    2. 三維熱度評分（互動 + 跨源 + 時效）
    3. AI 語境判斷
    """
    now = time.time()

    candidates = keyword_filter(posts, config)
    print(f"關鍵詞篩選：{len(posts)} → {len(candidates)} 條候選", file=sys.stderr)

    candidates = compute_scores(candidates, now)

    results = []
    for item in candidates:
        post    = item["post"]
        content = post.get("content", "")
        sources = sorted(item.get("_sources", {"feed"}))

        # 清除 post 上殘留的 _sources（set 不能 JSON 序列化）
        post.pop("_sources", None)

        entry = {
            "post":              post,
            "sources":           sources,
            "priority":          item["priority"],
            "match_reason":      item["match_reason"],
            "score_total":       item["score_total"],
            "score_interaction": item["score_interaction"],
            "score_cross_source": item["score_cross_source"],
            "score_timeliness":  item["score_timeliness"],
            "ai_should_comment": None,
            "ai_comment":        "",
            "ai_reason":         "",
        }

        if ai_enabled and config.get("ai_enabled", True):
            print(f"  AI 分析：{post.get('postId', '')} (分數 {item['score_total']}) ...",
                  file=sys.stderr)
            ai = analyze_with_ai(content, config)
            if ai:
                entry["ai_should_comment"] = ai.get("should_comment")
                entry["ai_comment"]        = ai.get("comment", "")
                entry["ai_reason"]         = ai.get("reason", "")
        else:
            entry["ai_should_comment"] = True

        results.append(entry)

    return {
        "total_input":        total_input,
        "total_deduplicated": len(posts),
        "total_filtered":     len(results),
        "results":            results,
    }


def main() -> None:
    _ensure_utf8_streams()
    parser = argparse.ArgumentParser(description="Threads 醫美篩選（純篩選，不抓取不發送）")

    # 單源輸入
    parser.add_argument("--posts-file", help="帖子 JSON 文件路徑（不指定則從 stdin 讀），source=feed")

    # 三源輸入（與 --posts-file 互斥）
    parser.add_argument("--feed-file",      help="首頁 Feed JSON 文件")
    parser.add_argument("--keyword-file",   help="關鍵詞搜索結果 JSON 文件")
    parser.add_argument("--benchmark-file", help="對標帳號帖子 JSON 文件")

    parser.add_argument("--no-ai", action="store_true", help="關閉 AI 分析，只做關鍵詞篩選 + 評分")
    parser.add_argument("--only-approved", action="store_true",
                        help="只輸出 ai_should_comment=true 的帖子")
    args = parser.parse_args()

    all_posts: list[dict] = []

    if args.feed_file or args.keyword_file or args.benchmark_file:
        # 三源模式
        if args.feed_file:
            posts = load_posts_from_file(args.feed_file, "feed")
            print(f"Feed：載入 {len(posts)} 條", file=sys.stderr)
            all_posts.extend(posts)
        if args.keyword_file:
            posts = load_posts_from_file(args.keyword_file, "keyword")
            print(f"關鍵詞：載入 {len(posts)} 條", file=sys.stderr)
            all_posts.extend(posts)
        if args.benchmark_file:
            posts = load_posts_from_file(args.benchmark_file, "benchmark")
            print(f"對標帳號：載入 {len(posts)} 條", file=sys.stderr)
            all_posts.extend(posts)
    else:
        # 單源模式（stdin 或 --posts-file）
        if args.posts_file:
            raw = Path(args.posts_file).read_text(encoding="utf-8")
        else:
            raw = sys.stdin.read()

        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                posts = data.get("posts", data.get("feeds", data.get("results", [])))
            elif isinstance(data, list):
                posts = data
            else:
                posts = []
        except Exception as e:
            print(json.dumps({"error": f"JSON 解析失敗：{e}"}, ensure_ascii=False))
            sys.exit(1)

        for p in posts:
            p["_source"] = "feed"
        all_posts.extend(posts)

    total_input = len(all_posts)

    # 去重並合併 sources
    merged = merge_and_deduplicate(all_posts)
    print(f"去重：{total_input} → {len(merged)} 條", file=sys.stderr)

    # 把 _sources 從 post 移到外層（避免污染 post 原始資料）
    for post in merged:
        post["_sources"] = post.pop("_sources", {"feed"})

    config = load_config()
    output = run(merged, config, ai_enabled=not args.no_ai, total_input=total_input)

    if args.only_approved:
        output["results"] = [r for r in output["results"] if r.get("ai_should_comment")]
        output["total_filtered"] = len(output["results"])

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
