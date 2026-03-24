#!/usr/bin/env python3
"""Threads 醫美篩選評論 — 從首頁推薦抓帖，AI 判斷是否適合評論，自動發送。"""

import json
import subprocess
import sys
import os
import time
import urllib.request
from pathlib import Path

# ── 基本路徑 ──────────────────────────────────────────────────
CONFIG_FILE  = Path.home() / ".threads-filter-comment.json"
LOCK_FILE    = "/tmp/threads-filter-comment.lock"
LOCK_TIMEOUT = 200
STATE_FILE   = "/tmp/threads-filter-comment-state.json"

# ── 預設配置（所有值都可在 config 檔覆蓋）────────────────────
DEFAULT_CONFIG = {
    # Threads 帳號名稱（同 list-accounts 顯示的名稱）
    "account": "",
    # threads-skills 項目根目錄（含 scripts/cli.py）
    "threads_skills_dir": str(Path.home() / "Desktop/threadsskill/threads-skills"),
    # 執行日誌路徑
    "log_file": str(Path.home() / ".threads/filter-comment.log"),

    # ── 周期控制 ───────────────────────────────────────────────
    "max_runs_per_cycle": 4,
    "rest_duration_hours": 1,

    # ── AI 配置 ────────────────────────────────────────────────
    "ai_enabled": True,
    "ai_api_url": "",        # 必填，例：http://192.168.1.x:8003/v1/chat/completions
    "ai_api_key": "",        # 必填
    "ai_model": "Qwen/Qwen3.5-27B-FP8",

    # ── 推廣文案（留空則只發 AI 評論）─────────────────────────
    "promo_text": "",
    # 推廣文案前的 @mention（留空則不加）
    "promo_mention": "",

    # ── 關鍵詞 ─────────────────────────────────────────────────
    "keywords": [
        # 外貌 / 皮膚 / 保養
        "外貌", "皮膚", "保養", "護膚", "抗老", "美白", "痘痘", "毛孔", "斑點",
        # 醫美 / 微整
        "醫美", "整形", "微整", "玻尿酸", "肉毒", "雷射", "光療", "美容診所",
        # 自信 / 變美
        "自信", "變美", "外貌焦慮", "素顏", "底妝", "遮瑕",
    ],
    "exclude_keywords": [
        # 同業 / 廣告
        "醫院", "診所", "院長", "醫生推薦", "我們家", "歡迎預約", "歡迎諮詢",
        "價格", "優惠", "促銷", "line:", "微信", "wechat",
    ],
    # 高優先級：含這些詞的帖子優先選
    "priority_keywords": [
        "韓國", "首爾", "江南", "釜山",
        "韓國醫美", "首爾醫美", "飛韓國",
    ],
}


# ── 工具函式 ──────────────────────────────────────────────────

def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            user_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config.update(user_config)
        except Exception as e:
            print(f"⚠️  讀取配置失敗：{e}")
    return config


def get_log_file(config: dict) -> Path:
    p = Path(config.get("log_file", DEFAULT_CONFIG["log_file"]))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            return json.loads(open(STATE_FILE, encoding="utf-8").read())
    except Exception:
        pass
    return {"runs_in_cycle": 0, "cycle_start": time.time()}


def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def check_should_rest(config: dict) -> tuple:
    state = load_state()
    max_runs  = config.get("max_runs_per_cycle", 4)
    rest_secs = config.get("rest_duration_hours", 1) * 3600
    if state.get("runs_in_cycle", 0) >= max_runs:
        rest_end = state.get("cycle_start", 0) + rest_secs
        if time.time() < rest_end:
            mins = int((rest_end - time.time()) / 60)
            return True, f"休息中，還有 {mins} 分鐘", state
    return False, "", state


def update_state(success: bool, config: dict) -> None:
    state = load_state()
    max_runs   = config.get("max_runs_per_cycle", 4)
    rest_hours = config.get("rest_duration_hours", 1)
    if success:
        runs = state.get("runs_in_cycle", 0) + 1
        if runs >= max_runs:
            state = {"runs_in_cycle": 0, "cycle_start": time.time()}
            print(f"  📊 本周期已執行 {max_runs} 次，開始休息 {rest_hours} 小時")
        else:
            state["runs_in_cycle"] = runs
            print(f"  📊 本周期已執行 {runs}/{max_runs} 次")
    save_state(state)


def acquire_lock() -> bool:
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            age = time.time() - os.stat(LOCK_FILE).st_mtime
            if age > LOCK_TIMEOUT:
                os.unlink(LOCK_FILE)
                return acquire_lock()
        except Exception:
            pass
        return False


def release_lock() -> None:
    try:
        os.unlink(LOCK_FILE)
    except Exception:
        pass


def log_result(config: dict, status: str, message: str, post_url: str = "") -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    log = get_log_file(config)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n[{ts}] {status}\n{message}\n")
        if post_url:
            f.write(f"帖子連結：{post_url}\n")
        f.write("-" * 50 + "\n")


def run_cli(config: dict, *args) -> tuple:
    skill_dir   = Path(config.get("threads_skills_dir", DEFAULT_CONFIG["threads_skills_dir"]))
    venv_python = skill_dir / ".venv" / "bin" / "python"
    python      = str(venv_python) if venv_python.exists() else "python3"
    account     = config.get("account", "")
    cmd = [python, str(skill_dir / "scripts" / "cli.py")]
    if account:
        cmd += ["--account", account]
    cmd += list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.stdout, result.stderr, result.returncode


# ── 篩選邏輯 ──────────────────────────────────────────────────

def is_political(content: str) -> bool:
    political = ["政治", "政府", "總統", "選舉", "政策", "議員", "政黨",
                 "民主", "獨裁", "共產", "資本主義", "社會主義"]
    return any(kw in content for kw in political)


def find_suitable_post(posts: list, config: dict) -> tuple:
    keywords     = config.get("keywords", DEFAULT_CONFIG["keywords"])
    exclude      = config.get("exclude_keywords", DEFAULT_CONFIG["exclude_keywords"])
    priority_kws = config.get("priority_keywords", DEFAULT_CONFIG["priority_keywords"])

    priority_candidates = []
    topic_candidates    = []

    for post in posts:
        content = post.get("content", "")
        if is_political(content):
            continue
        if any(kw in content for kw in exclude):
            continue
        if any(kw in content for kw in priority_kws):
            priority_candidates.append(post)
        elif any(kw in content for kw in keywords):
            topic_candidates.append(post)

    def parse_likes(p: dict) -> int:
        try:
            return int(p.get("likeCount", "0").replace(",", "").replace("K", "000"))
        except Exception:
            return 0

    if priority_candidates:
        print(f"  ✅ 高優先帖子 {len(priority_candidates)} 個候選")
        best = sorted(priority_candidates, key=parse_likes, reverse=True)[0]
        return best, "高優先（韓國/首爾相關）"
    elif topic_candidates:
        print(f"  ✅ 醫美相關帖子 {len(topic_candidates)} 個候選")
        best = sorted(topic_candidates, key=parse_likes, reverse=True)[0]
        return best, "醫美相關"
    else:
        print(f"  ❌ 未找到適合帖子（共檢查 {len(posts)} 條）")
        return None, ""


# ── AI 分析 ───────────────────────────────────────────────────

def analyze_with_ai(content: str, config: dict):
    if not config.get("ai_enabled", True):
        return None
    api_url = config.get("ai_api_url", "")
    api_key = config.get("ai_api_key", "")
    if not api_url or not api_key:
        print("  ⚠️  AI 未配置（ai_api_url / ai_api_key 為空），跳過 AI 分析")
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
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
    except Exception as e:
        print(f"  AI 分析失敗：{e}")
    return None


def build_comment(ai_comment: str, config: dict) -> str:
    mention = config.get("promo_mention", "").strip()
    promo   = config.get("promo_text", "").strip()
    parts   = []
    if mention:
        parts.append(mention)
    parts.append(ai_comment or "蠻認同的！最近也在研究醫美保養，皮膚狀態差很多～")
    if promo:
        parts.append(promo)
    return "\n\n".join(parts)


# ── 主流程 ────────────────────────────────────────────────────

def main() -> bool:
    config = load_config()

    should_rest, rest_msg, state = check_should_rest(config)
    if should_rest:
        print(f"\n⏸️  {rest_msg}（本周期 {state.get('runs_in_cycle',0)}/{config.get('max_runs_per_cycle',4)} 次）")
        return True

    if not acquire_lock():
        print("跳過：上一次任務仍在執行中")
        return True

    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 開始執行醫美篩選評論")
        print(f"周期：{state.get('runs_in_cycle',0)+1}/{config.get('max_runs_per_cycle',4)} 次\n")

        # 1. 抓首頁推薦
        print("1. 抓取首頁推薦（200 條）...")
        stdout, stderr, code = run_cli(config, "list-feeds", "--limit", "200")
        if code != 0:
            print(f"  ❌ 抓取失敗：{stderr}")
            log_result(config, "❌ 失敗", "抓取首頁推薦失敗")
            update_state(False, config)
            return False

        try:
            data  = json.loads(stdout)
            posts = data.get("posts", data.get("feeds", []))
            print(f"  獲取 {len(posts)} 條帖子")
        except Exception as e:
            print(f"  ❌ JSON 解析失敗：{e}")
            update_state(False, config)
            return False

        if not posts:
            print("  ❌ 未獲取到帖子")
            log_result(config, "❌ 失敗", "未獲取到帖子")
            update_state(False, config)
            return False

        # 2. 篩選 + AI 判斷（最多嘗試 5 次，每次刷新）
        success      = False
        post_url     = ""
        post_content = ""
        ai_comment   = ""
        post_id      = ""

        for attempt in range(1, 6):
            print(f"\n2. 篩選帖子...{'（第 '+str(attempt)+' 次）' if attempt > 1 else ''}")
            target, reason = find_suitable_post(posts, config)

            if not target:
                if attempt < 5:
                    print(f"  刷新首頁重試 ({attempt}/5)...")
                    time.sleep(2)
                    stdout, _, code = run_cli(config, "list-feeds", "--limit", "200")
                    if code == 0:
                        try:
                            posts = json.loads(stdout).get("posts", [])
                            print(f"  刷新後獲取 {len(posts)} 條")
                        except Exception:
                            pass
                continue

            post_url     = target.get("url", "")
            post_id      = target.get("postId", "")
            post_content = target.get("content", "")
            print(f"  選中：{post_id}（{reason}）")
            print(f"  內容：{post_content[:80]}...")

            print("\n3. AI 分析...")
            ai_result = analyze_with_ai(post_content, config)
            if not ai_result and not config.get("ai_enabled", True):
                ai_result = {"should_comment": True, "comment": ""}

            if ai_result and ai_result.get("should_comment"):
                ai_comment = ai_result.get("comment", "")
                print(f"  ✅ AI 同意評論：{ai_comment[:60]}...")
                success = True
                break
            else:
                reason_txt = (ai_result.get("reason", "") if ai_result else "AI 分析失敗")
                print(f"  ❌ AI 判斷跳過：{reason_txt}")
                if attempt < 5:
                    print(f"  刷新重試 ({attempt}/5)...")
                    time.sleep(2)
                    stdout, _, code = run_cli(config, "list-feeds", "--limit", "200")
                    if code == 0:
                        try:
                            posts = json.loads(stdout).get("posts", [])
                        except Exception:
                            pass

        if not success:
            msg = "嘗試 5 次後未找到適合帖子"
            print(f"\n⚠️  {msg}")
            log_result(config, "⚠️ 跳過", msg)
            update_state(False, config)
            return True

        # 3. 防重複檢查
        print("\n4. 檢查是否已回覆...")
        stdout, _, code = run_cli(config, "list-replied")
        if code == 0:
            try:
                replied_ids = json.loads(stdout).get("post_ids", [])
                if post_id in replied_ids:
                    print(f"  已回覆過 {post_id}，跳過")
                    update_state(False, config)
                    return True
            except Exception:
                pass

        # 4. 發送評論
        print("\n5. 發送評論...")
        final = build_comment(ai_comment, config)
        stdout, stderr, code = run_cli(config, "reply-thread", "--url", post_url, "--content", final)

        if code != 0:
            print(f"  ❌ 發送失敗：{stderr}")
            log_result(config, "❌ 失敗", f"發送失敗：{stderr}", post_url)
            update_state(False, config)
            return False

        print(f"\n{'='*50}")
        print(f"✅ 成功評論！")
        print(f"帖子：{post_url}")
        print(f"評論：{ai_comment[:80]}...")
        print(f"{'='*50}")
        log_result(config, "✅ 成功",
                   f"內容：{post_content[:80]}\n評論：{ai_comment[:80]}", post_url)
        update_state(True, config)
        return True

    except Exception as e:
        import traceback
        print(f"❌ 執行異常：{e}")
        traceback.print_exc()
        update_state(False, config)
        return False
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
