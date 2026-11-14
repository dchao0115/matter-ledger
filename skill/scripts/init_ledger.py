#!/usr/bin/env python3
"""Create a MatterLedger project folder from the bundled starter.

Usage:
    python3 scripts/init_ledger.py --target ../my-project --name "我的项目" --id my-project
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTER = ROOT / "assets" / "starter"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a MatterLedger project folder.")
    parser.add_argument("--target", required=True, help="Target project directory")
    parser.add_argument("--name", required=True, help="Project display name")
    parser.add_argument("--id", required=True, help="Stable project id (lowercase, hyphenated)")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if target.exists() and not target.is_dir():
        print(f"目标路径是文件，不是目录：{target}", file=sys.stderr)
        return 2
    if target.exists() and any(target.iterdir()):
        print(f"目标目录已存在且非空，停止：{target}", file=sys.stderr)
        return 2
    if not STARTER.is_dir():
        print(f"找不到 starter 目录：{STARTER}", file=sys.stderr)
        return 2

    target.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    for src in sorted(STARTER.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(STARTER)
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        if not src.name.endswith(".模板.md"):
            text = (
                text.replace("{{PROJECT_ID}}", args.id)
                .replace("{{PROJECT_NAME}}", args.name)
                .replace("{{DATE}}", today)
            )
        dst.write_text(text, encoding="utf-8")

    for dirname in ("决策记录", "模块", "参考"):
        (target / dirname).mkdir(parents=True, exist_ok=True)

    print(f"已创建：{target}")
    for path in sorted(target.rglob("*")):
        if path.is_file():
            print(f" - {path.relative_to(target)}")
    print("\n下一步：打开 事项台账.md，写第一条事项（阶段 + 下一步）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
