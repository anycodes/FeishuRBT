#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from .database import get_db_connection

logger = logging.getLogger(__name__)


def get_user(user_id):
    """获取用户信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None


def add_user(user_id, name="", is_admin=0):
    """添加用户"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, name, is_admin) VALUES (?, ?, ?)",
                   (user_id, name, is_admin))
    conn.commit()
    conn.close()
    return True


def check_admin(user_id):
    """检查用户是否是管理员"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result['is_admin'] == 1:
        return True
    return False


def set_user_admin(user_id, is_admin=1):
    """设置用户管理员权限"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (is_admin, user_id))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_all_users():
    """获取所有用户"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY is_admin DESC, created_at DESC")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users