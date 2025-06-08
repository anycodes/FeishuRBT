#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import subprocess
import os


def run_tests():
    """运行测试套件"""
    print("开始运行测试...")

    # 基本测试命令
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",  # 详细输出
        "--tb=short",  # 简短的错误信息
        "--cov=models",  # 覆盖率检查
        "--cov=services",
        "--cov=utils",
        "--cov=handlers",
        "--cov-report=term-missing",  # 显示未覆盖的行
        "--cov-report=html",  # HTML覆盖率报告
    ]

    # 运行测试
    try:
        result = subprocess.run(cmd, cwd=os.path.dirname(__file__))
        return result.returncode
    except Exception as e:
        print(f"运行测试时出错: {e}")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    if exit_code == 0:
        print("\n✅ 所有测试通过！")
        print("📊 查看覆盖率报告: htmlcov/index.html")
    else:
        print("\n❌ 测试失败！")

    sys.exit(exit_code)