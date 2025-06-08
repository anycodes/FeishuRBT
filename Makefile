.PHONY: test test-unit test-integration coverage clean

# 安装测试依赖
install-test:
	pip install -r requirements-test.txt

# 运行所有测试
test:
	python run_tests.py

# 只运行单元测试
test-unit:
	pytest tests/unit/ -v

# 只运行集成测试
test-integration:
	pytest tests/integration/ -v

# 生成覆盖率报告
coverage:
	pytest tests/ --cov=models --cov=services --cov=utils --cov=handlers --cov-report=html --cov-report=term

# 清理测试文件
clean:
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .coverage
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete

# 运行特定测试
test-models:
	pytest tests/unit/test_models/ -v

test-services:
	pytest tests/unit/test_services/ -v

# 快速测试（跳过慢速测试）
test-fast:
	pytest tests/ -v -m "not slow"