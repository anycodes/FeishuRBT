#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from utils.helpers import (
    ensure_utf8, is_markdown, is_bot_mentioned, remove_mentions_improved,
    format_data_for_ai, create_admin_token, validate_admin_token
)
from config import Config


def test_ensure_utf8():
    """测试UTF-8编码确保"""
    # 测试字符串
    assert ensure_utf8("test") == "test"

    # 测试字节
    assert ensure_utf8(b"test") == "test"

    # 测试None
    assert ensure_utf8(None) is None

    # 测试中文
    assert ensure_utf8("测试") == "测试"
    assert ensure_utf8("测试".encode('utf-8')) == "测试"


def test_is_markdown():
    """测试Markdown格式检测"""
    # 标题
    assert is_markdown("# 这是标题") is True
    assert is_markdown("## 二级标题") is True

    # 粗体
    assert is_markdown("这是**粗体**文本") is True

    # 代码
    assert is_markdown("这是`代码`") is True
    assert is_markdown("```\ncode block\n```") is True

    # 列表
    assert is_markdown("- 列表项") is True
    assert is_markdown("1. 有序列表") is True

    # 普通文本
    assert is_markdown("普通文本") is False


def test_is_bot_mentioned():
    """测试机器人@检测"""
    # 模拟飞书@数据
    mentions_with_bot = [
        {"name": Config.BOT_NAME, "id": {"open_id": "bot_123"}}
    ]

    mentions_without_bot = [
        {"name": "其他用户", "id": {"open_id": "user_456"}}
    ]

    assert is_bot_mentioned(mentions_with_bot) is True
    assert is_bot_mentioned(mentions_without_bot) is False
    assert is_bot_mentioned([]) is False
    assert is_bot_mentioned(None) is False


def test_remove_mentions_improved():
    """测试改进的@移除"""
    mentions = [{"name": "TestBot"}]

    # 测试各种@格式
    assert remove_mentions_improved("@TestBot 你好", mentions) == "你好"
    assert remove_mentions_improved("你好 @TestBot", mentions) == "你好"
    assert remove_mentions_improved("@TestBot", mentions) == ""
    assert remove_mentions_improved("@TestBot  你好  世界", mentions) == "你好 世界"


def test_format_data_for_ai():
    """测试AI数据格式化"""
    # 字符串
    assert format_data_for_ai("test") == "test"

    # 字典
    data = {"key1": "value1", "key2": {"nested": "value"}}
    result = format_data_for_ai(data)
    assert "key1: value1" in result
    assert "key2:" in result

    # 列表
    data = ["item1", "item2"]
    result = format_data_for_ai(data)
    assert "item1" in result
    assert "item2" in result


def test_admin_token_lifecycle(test_db):
    """测试管理员token生命周期"""
    from models.user import add_user

    # 添加管理员用户
    user_id = "admin_test"
    add_user(user_id, "Admin Test", 1)

    # 创建token
    token = create_admin_token(user_id)
    assert token is not None
    assert len(token) > 20

    # 验证token
    valid, returned_user_id = validate_admin_token(token)
    assert valid is True
    assert returned_user_id == user_id

    # 验证无效token
    valid, _ = validate_admin_token("invalid_token")
    assert valid is False

    # 验证空token
    valid, _ = validate_admin_token(None)
    assert valid is False