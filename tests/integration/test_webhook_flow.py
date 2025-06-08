#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import json
from unittest.mock import patch, MagicMock
from bottle import Bottle


def test_webhook_creation_and_call_flow(test_db, sample_model, sample_webhook):
    """测试Webhook创建和调用流程"""
    from models.model import add_model
    from models.webhook import create_webhook, get_webhook, add_webhook_subscription
    from handlers.webhook_handler import setup_webhook_routes

    # 创建模型
    model_id = add_model(
        sample_model['name'],
        sample_model['description'],
        sample_model['dify_url'],
        sample_model['dify_type'],
        sample_model['api_key']
    )

    # 创建webhook
    webhook_id, api_token, config_token = create_webhook(
        sample_webhook['name'],
        sample_webhook['description'],
        model_id,
        sample_webhook['prompt_template'],
        sample_webhook['bypass_ai']
    )

    assert webhook_id is not None
    assert api_token is not None
    assert config_token is not None

    # 添加订阅
    success, sub_id = add_webhook_subscription(webhook_id, "user", "test_user", "test_creator")
    assert success is True

    # 验证webhook可以正确获取
    webhook = get_webhook(api_token=api_token)
    assert webhook is not None
    assert webhook['id'] == webhook_id


@pytest.mark.parametrize("bypass_ai,expected_processing", [
    (0, "AI处理"),
    (1, "直接推送")
])
def test_webhook_processing_modes(test_db, sample_model, bypass_ai, expected_processing):
    """测试不同的Webhook处理模式"""
    from models.model import add_model
    from models.webhook import create_webhook

    # 创建模型
    model_id = add_model(
        sample_model['name'],
        sample_model['description'],
        sample_model['dify_url'],
        sample_model['dify_type'],
        sample_model['api_key']
    )

    # 创建webhook
    webhook_id, api_token, config_token = create_webhook(
        f'Test Webhook {bypass_ai}',
        'Test webhook for processing mode',
        model_id,
        'Test: {data}',
        bypass_ai
    )

    # 验证处理模式
    from models.webhook import get_webhook
    webhook = get_webhook(webhook_id=webhook_id)
    assert webhook['bypass_ai'] == bypass_ai