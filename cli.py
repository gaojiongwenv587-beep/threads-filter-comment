"""CLI 入口：filter-comment

用法：
    python cli.py [--posts-file FILE] [--no-ai] [--only-approved]
    python cli.py --feed-file F1 --keyword-file F2 --benchmark-file F3

所有參數與 filter-comment.py 完全一致，此文件只做路徑引導。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_main():
    """動態載入 filter-comment.py（繞過連字符無法直接 import 的限制）。"""
    script = Path(__file__).parent / "filter-comment.py"
    if not script.exists():
        print(f"[error] 找不到 {script}", file=sys.stderr)
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("filter_comment", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.main


if __name__ == "__main__":
    _load_main()()
