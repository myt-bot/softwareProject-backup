"""M1 用户与项目管理模块 测试入口。

运行方式：
    cd d:\softwareProject
    python tests\M1_user_project\test_code\run_all.py

编写者：甘淞文
"""

import sys
import unittest
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))


def run_all_tests():
    """发现并运行所有测试。"""
    loader = unittest.TestLoader()
    test_dir = Path(__file__).resolve().parent

    suite = loader.discover(
        start_dir=str(test_dir),
        pattern="test_*.py",
        top_level_dir=str(test_dir.parent.parent.parent),
    )

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出摘要
    print("\n" + "=" * 60)
    print("测试摘要")
    print("=" * 60)
    print(f"  运行: {result.testsRun}")
    print(f"  成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  失败: {len(result.failures)}")
    print(f"  错误: {len(result.errors)}")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
