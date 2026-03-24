#!/usr/bin/env python3
"""Threads 醫美篩選 — 純篩選工具。

從 stdin 或 --posts-file 讀入帖子 JSON，
關鍵詞篩選 + AI 判斷，輸出適合評論的帖子列表。

使用方式：
    # 從 stdin
    uv run python scripts/cli.py list-feeds --limit 200 | python filter-comment.py

    # 從文件
    python filter-comment.py --posts-file /tmp/posts.json

    # 關閉 AI（只做關鍵詞篩選）
    python filter-comment.py --no-ai --posts-file /tmp/posts.json

輸出（stdout JSON）：
    {
      "total_input": 200,
      "total_filtered": 5,
      "results": [
        {
          "post": { ...原始帖子欄位... },
          "priority": "high",
          "match_reason": "韓國相關",
          "ai_should_comment": true,
          "ai_comment": "...",
          "ai_reason": "..."
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

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


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            config.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"⚠️  讀取配置失敗：{e}", file=sys.stderr)
    return config


def parse_likes(post: dict) -> int:
    try:
        return int(post.get("likeCount", "0").replace(",", "").replace("K", "000"))
    except Exception:
        return 0


def keyword_filter(posts: list, config: dict) -> list[dict]:
    """關鍵詞篩選，返回帶優先級的候選列表。"""
    keywords     = config.get("keywords", DEFAULT_CONFIG["keywords"])
    exclude      = config.get("exclude_keywords", DEFAULT_CONFIG["exclude_keywords"])
    priority_kws = config.get("priority_keywords", DEFAULT_CONFIG["priority_keywords"])

    results = []
    for post in posts:
        content = post.get("content", "")

        # 排除政治
        if any(kw in content for kw in POLITICAL_KEYWORDS):
            continue
        # 排除同業/廣告
        if any(kw in content for kw in exclude):
            continue

        if any(kw in content for kw in priority_kws):
            results.append({"post": post, "priority": "high", "match_reason": "韓國/首爾相關"})
        elif any(kw in content for kw in keywords):
            results.append({"post": post, "priority": "medium", "match_reason": "醫美相關"})

    # 高優先在前，同優先級按點讚數降序
    results.sort(key=lambda x: (0 if x["priority"] == "high" else 1, -parse_likes(x["post"])))
    return results


def analyze_with_ai(content: str, config: dict) -> dict | None:
    """AI 判斷是否適合評論並生成評論文字。"""
    api_url = config.get("ai_api_url", "")
    api_key = config.get("ai_api_key", "")
    if not api_url or not api_key:
        print("  ⚠️  AI 未配置（ai_api_url / ai_api_key 為空）", file=sys.stderr)
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


def run(posts: list, config: dict, ai_enabled: bool) -> dict:
    """主篩選邏輯，返回結果 dict。"""
    candidates = keyword_filter(posts, config)
    print(f"關鍵詞篩選：{len(posts)} → {len(candidates)} 條候選", file=sys.stderr)

    results = []
    for item in candidates:
        post    = item["post"]
        content = post.get("content", "")
        entry   = {
            "post":             post,
            "priority":         item["priority"],
            "match_reason":     item["match_reason"],
            "ai_should_comment": None,
            "ai_comment":        "",
            "ai_reason":         "",
        }

        if ai_enabled and config.get("ai_enabled", True):
            print(f"  AI 分析：{post.get('postId', '')} ...", file=sys.stderr)
            ai = analyze_with_ai(content, config)
            if ai:
                entry["ai_should_comment"] = ai.get("should_comment")
                entry["ai_comment"]        = ai.get("comment", "")
                entry["ai_reason"]         = ai.get("reason", "")
        else:
            entry["ai_should_comment"] = True  # 不用 AI 則預設通過

        results.append(entry)

    return {
        "total_input":    len(posts),
        "total_filtered": len(results),
        "results":        results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Threads 醫美篩選（純篩選，不抓取不發送）")
    parser.add_argument("--posts-file", help="帖子 JSON 文件路徑（不指定則從 stdin 讀）")
    parser.add_argument("--no-ai", action="store_true", help="關閉 AI 分析，只做關鍵詞篩選")
    parser.add_argument("--only-approved", action="store_true",
                        help="只輸出 ai_should_comment=true 的帖子")
    args = parser.parse_args()

    # 讀入帖子
    if args.posts_file:
        raw = Path(args.posts_file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    try:
        data = json.loads(raw)
        # 兼容 list-feeds 輸出格式（{"posts": [...]}）和純數組
        if isinstance(data, dict):
            posts = data.get("posts", data.get("feeds", []))
        elif isinstance(data, list):
            posts = data
        else:
            posts = []
    except Exception as e:
        print(json.dumps({"error": f"JSON 解析失敗：{e}"}, ensure_ascii=False))
        sys.exit(1)

    config = load_config()
    output = run(posts, config, ai_enabled=not args.no_ai)

    if args.only_approved:
        output["results"] = [r for r in output["results"] if r.get("ai_should_comment")]
        output["total_filtered"] = len(output["results"])

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
