#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os


class Config:
    """配置管理类"""

    # 数据库配置
    DB_PATH = "lark_dify_bot.db"

    # 飞书应用配置
    VERIFICATION_TOKEN = os.environ.get("VERIFICATION_TOKEN", "your_verification_token")
    APP_ID = os.environ.get("APP_ID", "your_app_id")
    APP_SECRET = os.environ.get("APP_SECRET", "your_app_secret")
    BOT_NAME = os.environ.get("BOT_NAME", "Dify机器人")
    BOT_OPEN_ID = os.environ.get("BOT_OPEN_ID", "")

    # API配置
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 2
    RETRY_BACKOFF_FACTOR = 1.5
    API_TIMEOUT = 60

    # Web管理界面配置
    ADMIN_TOKEN_EXPIRE_MINUTES = 60
    STATIC_DIR = "static"

    # 图片缓存配置
    IMAGE_CACHE_EXPIRE_MINUTES = 5
    IMAGE_CACHE_MAX_SIZE = 10 * 1024 * 1024  # 10MB