"""全量自动化回归入口（M8 · 人员 6）。

对整个 tests/ 目录做一次可运行自动化测试回归，汇总通过 / 失败 / 跳过，
并提示需要单独用其它运行器执行的用例（如 M2 的 Node.js 前端编辑器测试）。

运行：
    python tests/M8_integration_deploy/test_code/run_regression.py
等价于文档中建议的：
    python -m pytest tests/ -q
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def main() -> int:
    print("=" * 64)
    print("M8 全量回归：python -m pytest tests/ -q")
    print("=" * 64)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(ROOT),
    )

    print("\n" + "-" * 64)
    print("补充：以下测试不在 pytest 收集范围内，需单独执行：")
    print("  · 人员 2 前端编辑器：node tests/M2_model_editor/test_code/test_model_editor.js")
    print("  · 人员 4 训练闭环 / 人员 6 Nginx 反代与三端端到端：见各自设计文档「手工验证」清单")
    print("-" * 64)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
