#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import pytest
import tempfile
import sqlite3
from unittest.mock import patch

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import Config
from models.database import get_db_connection
from models.migration import DatabaseMigration


@pytest.fixture(scope="session")
def test_config():
    """测试配置"""
    # 使用临时数据库
    test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    test_db.close()

    original_db_path = Config.DB_PATH
    Config.DB_PATH = test_db.name

    yield Config

    # 清理
    Config.DB_PATH = original_db_path
    try:
        os.unlink(test_db.name)
    except:
        pass


@pytest.fixture(scope="function")
def test_db(test_config):
    """测试数据库fixture"""
    # 初始化测试数据库
    migration = DatabaseMigration()
    migration.run_migrations()

    yield Config.DB_PATH

    # 清理数据库
    conn = get_db_connection()
    cursor = conn.cursor()

    # 清空所有表
    tables = [
        'webhook_logs', 'webhook_subscriptions', 'webhooks',
        'messages', 'sessions', 'commands', 'models',
        'admin_tokens', 'users', 'configs', 'image_cache',
        'db_migrations'
    ]

    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            pass  # 表可能不存在

    conn.commit()
    conn.close()


@pytest.fixture
def sample_user():
    """示例用户数据"""
    return {
        'user_id': 'test_user_123',
        'name': 'Test User',
        'is_admin': 0
    }


@pytest.fixture
def sample_model():
    """示例模型数据"""
    return {
        'name': 'Test Model',
        'description': 'A test model',
        'dify_url': 'https://api.dify.ai/v1',
        'dify_type': 'chatbot',
        'api_key': 'test_api_key'
    }


@pytest.fixture
def sample_command():
    """示例命令数据"""
    return {
        'name': 'Test Command',
        'description': 'A test command',
        'trigger': '\\test',
        'model_id': 1
    }


@pytest.fixture
def sample_webhook():
    """示例webhook数据"""
    return {
        'name': 'Test Webhook',
        'description': 'A test webhook',
        'model_id': 1,
        'prompt_template': 'Test: {data}',
        'bypass_ai': 0,
        'fallback_mode': 'original'
    }


@pytest.fixture
def mock_lark_api():
    """模拟飞书API响应"""
    with patch('services.lark_service.http_request_with_retry') as mock:
        mock.return_value = b'{"code": 0, "msg": "success", "tenant_access_token": "test_token"}'
        yield mock


@pytest.fixture
def mock_dify_api():
    """模拟Dify API响应"""
    with patch('services.dify_service.dify_request') as mock:
        mock.return_value = {"answer": "Test response", "conversation_id": "test_conv_123"}
        yield mock