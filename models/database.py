#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import logging
from config import Config

logger = logging.getLogger(__name__)

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA encoding = 'UTF-8'")
    conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
    conn.text_factory = str
    return conn

def init_database():
    """初始化数据库（使用迁移系统）"""
    from .migration import init_database_with_migration
    return init_database_with_migration()