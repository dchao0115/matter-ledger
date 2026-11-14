"""把 gate.py 安装为 git pre-commit 钩子，使提交时强制执行结构、核对指纹与 L3 规则。

默认只在「包所在 git 仓库根 == 交付包根」的独立项目中安装；包嵌套在更大仓库中时需 --force，
避免让宿主仓库的每次提交都触发本包的门禁。钩子只读检查，不修改文件。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[4]
GATE = Path(__file__).resolve().parent / "gate.py"


def git_root(start):
    try:
        out = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    text = out.stdout.strip()
    return Path(text).resolve() if text else None


def hook_body():
    return ("#!/bin/sh\n"
            "# 文档治理门禁（由 代码层/packages/governance/docgov/install_gate_hook.py 安装）\n"
            f'exec "{sys.executable}" "{GATE}" --config "{PACKAGE / "治理层" / "project.json"}"\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description="安装文档治理 git pre-commit 钩子（调用 gate.py）")
    parser.add_argument("--force", action="store_true", help="包嵌套在更大仓库中时也安装")
    args = parser.parse_args(argv)
    root = git_root(PACKAGE)
    if root is None:
        print("未找到 git 仓库；请在独立项目中初始化 git 后再安装。")
        return 2
    if root != PACKAGE.resolve() and not args.force:
        print(f"包位于更大仓库（仓库根 {root}）中，默认不安装以免影响宿主仓库的每次提交；确认要安装时加 --force。")
        return 2
    hook = root / ".git" / "hooks" / "pre-commit"
    if hook.exists():
        print(f"已存在 {hook}，未覆盖；请手工合并以下内容：")
        print(hook_body())
        return 2
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(hook_body(), encoding="utf-8")
    hook.chmod(0o755)
    print(f"已安装 pre-commit 钩子：{hook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
