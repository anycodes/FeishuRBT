#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pytest
from config import Config


def test_config_defaults():
    """测试配置默认值"""
    assert Config.DB_PATH == "lark_dify_bot.db"
    assert Config.MAX_RETRIES == 3
    assert Config.INITIAL_RETRY_DELAY == 2
    assert Config.ADMIN_TOKEN_EXPIRE_MINUTES == 60
    assert Config.STATIC_DIR == "static"


def test_config_environment_variables():
    """测试环境变量配置"""
    # 设置环境变量
    os.environ['VERIFICATION_TOKEN'] = 'test_token'
    os.environ['APP_ID'] = 'test_app_id'

    # 重新导入配置以获取新的环境变量
    import importlib
    import config
    importlib.reload(config)

    assert config.Config.VERIFICATION_TOKEN == 'test_token'
    assert config.Config.APP_ID == 'test_app_id'

    # 清理
    del os.environ['VERIFICATION_TOKEN']
    del os.environ['APP_ID']