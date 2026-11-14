"""文档治理提交门禁：运行 check --strict --logic，结构、核对指纹或 L3 规则任一不通过即返回非零。

用法（在交付包根执行）：python "代码层/packages/governance/docgov/gate.py" [--config "治理层/project.json"]
供 git pre-commit 钩子或收尾流程调用；只读，不修改任何文件。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "docgov.py"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="文档治理提交门禁：check --strict --logic 的包装，供 pre-commit 或收尾流程调用")
    parser.add_argument("--config", default="治理层/project.json",
                        help="project.json 位置；默认相对当前目录，与 CLI 用法一致")
    args = parser.parse_args(argv)
    result = subprocess.run([sys.executable, str(TOOL), "--config", args.config, "check", "--strict", "--logic"],
                            capture_output=True, text=True, encoding="utf-8")
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode == 0:
        print("文档治理门禁：通过（结构、核对指纹、L3 规则全部通过）")
    else:
        print("文档治理门禁：未通过；按上面 check 输出修复后重新提交，工具不自动修改")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
