#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta
from .database import get_db_connection

logger = logging.getLogger(__name__)


def get_config(key):
    """获取配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM configs WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result['value'] if result else None


def set_config(key, value, description=None):
    """设置配置"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if description:
        cursor.execute(
            "INSERT OR REPLACE INTO configs (key, value, description, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (key, value, description)
        )
    else:
        cursor.execute(
            "UPDATE configs SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (value, key)
        )

    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_all_configs():
    """获取所有配置"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM configs")
    configs = {row['key']: {'value': row['value'], 'description': row['description']} for row in cursor.fetchall()}
    conn.close()
    return configs


def get_or_create_session(user_id, model_id=None, command_id=None):
    """获取或创建会话，支持模型和命令维度"""
    conn = get_db_connection()
    cursor = conn.cursor()

    timeout_minutes = int(get_config("session_timeout") or "30")
    timeout_timestamp = datetime.now() - timedelta(minutes=timeout_minutes)

    # 查找活动会话
    if model_id and command_id:
        cursor.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? AND model_id = ? AND command_id = ? AND is_active = 1
                AND last_active_at > ?
            ORDER BY last_active_at DESC LIMIT 1
        """, (user_id, model_id, command_id, timeout_timestamp))
    elif model_id:
        cursor.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? AND model_id = ? AND command_id IS NULL AND is_active = 1
                AND last_active_at > ?
            ORDER BY last_active_at DESC LIMIT 1
        """, (user_id, model_id, timeout_timestamp))
    elif command_id:
        cursor.execute("""
            SELECT s.* FROM sessions s
            JOIN commands c ON s.command_id = c.id
            WHERE s.user_id = ? AND s.command_id = ? AND s.is_active = 1
                AND s.last_active_at > ?
            ORDER BY s.last_active_at DESC LIMIT 1
        """, (user_id, command_id, timeout_timestamp))
    else:
        cursor.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? AND is_active = 1 AND last_active_at > ?
            ORDER BY last_active_at DESC LIMIT 1
        """, (user_id, timeout_timestamp))

    session = cursor.fetchone()

    if session:
        cursor.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP, last_active_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session['id'],)
        )
        conn.commit()
        session_id = session['id']
        conversation_id = session['conversation_id']
    else:
        if not model_id and command_id:
            cursor.execute("SELECT model_id FROM commands WHERE id = ?", (command_id,))
            result = cursor.fetchone()
            if result:
                model_id = result['model_id']

        if not model_id:
            default_model_id = get_config("default_model")
            if default_model_id:
                try:
                    model_id = int(default_model_id)
                except (ValueError, TypeError):
                    model_id = None

        cursor.execute(
            """INSERT INTO sessions 
               (user_id, model_id, command_id, last_active_at) 
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
            (user_id, model_id, command_id)
        )
        conn.commit()
        session_id = cursor.lastrowid
        conversation_id = None

    conn.close()
    return session_id, conversation_id


def update_session_conversation(session_id, conversation_id):
    """更新会话的conversation_id和最后活动时间"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE sessions 
           SET conversation_id = ?, 
               updated_at = CURRENT_TIMESTAMP, 
               last_active_at = CURRENT_TIMESTAMP 
           WHERE id = ?""",
        (conversation_id, session_id)
    )
    conn.commit()
    conn.close()
    return True


def add_message(session_id, user_id, content, is_user=1):
    """添加消息记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (session_id, user_id, content, is_user) VALUES (?, ?, ?, ?)",
        (session_id, user_id, content, is_user)
    )
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    return message_id


def get_session_model(session_id):
    """获取会话关联的模型"""
    from .model import get_model

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.* 
        FROM models m
        JOIN sessions s ON s.model_id = m.id
        WHERE s.id = ?
    """, (session_id,))
    model = cursor.fetchone()
    conn.close()

    if not model:
        default_model_id = get_config("default_model")
        if default_model_id:
            default_model = get_model(model_id=default_model_id)
            if default_model:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE sessions SET model_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (default_model['id'], session_id)
                )
                conn.commit()
                conn.close()
                return default_model
        return None

    return dict(model) if model else None