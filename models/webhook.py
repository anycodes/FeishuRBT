#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import secrets
import sqlite3
import logging
from .database import get_db_connection

logger = logging.getLogger(__name__)


def get_all_webhooks():
    """获取所有webhooks"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.*, m.name as model_name
        FROM webhooks w
        JOIN models m ON w.model_id = m.id
        ORDER BY w.created_at DESC
    """)
    webhooks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return webhooks


def create_webhook(name, description, model_id, prompt_template=None, bypass_ai=0, fallback_mode='original',
                   fallback_message=None):
    """创建新的webhook"""
    conn = get_db_connection()
    cursor = conn.cursor()

    api_token = secrets.token_urlsafe(32)
    config_token = secrets.token_urlsafe(8)

    cursor.execute(
        """INSERT INTO webhooks 
           (name, description, token, config_token, model_id, prompt_template, 
            bypass_ai, fallback_mode, fallback_message) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, description, api_token, config_token, model_id, prompt_template,
         bypass_ai, fallback_mode, fallback_message)
    )
    conn.commit()
    webhook_id = cursor.lastrowid
    conn.close()

    return webhook_id, api_token, config_token


def get_webhook(webhook_id=None, api_token=None, config_token=None):
    """获取webhook信息"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if webhook_id:
        cursor.execute("""
            SELECT w.*, m.name as model_name, m.dify_type, m.dify_url, m.api_key
            FROM webhooks w
            JOIN models m ON w.model_id = m.id
            WHERE w.id = ?
        """, (webhook_id,))
    elif api_token:
        cursor.execute("""
            SELECT w.*, m.name as model_name, m.dify_type, m.dify_url, m.api_key
            FROM webhooks w
            JOIN models m ON w.model_id = m.id
            WHERE w.token = ? AND w.is_active = 1
        """, (api_token,))
    elif config_token:
        cursor.execute("""
            SELECT w.*, m.name as model_name, m.dify_type, m.dify_url, m.api_key
            FROM webhooks w
            JOIN models m ON w.model_id = m.id
            WHERE w.config_token = ?
        """, (config_token,))
    else:
        conn.close()
        return None

    webhook = cursor.fetchone()
    conn.close()

    return dict(webhook) if webhook else None


def update_webhook(webhook_id, name=None, description=None, model_id=None,
                   prompt_template=None, bypass_ai=None, fallback_mode=None,
                   fallback_message=None, is_active=None):
    """更新webhook"""
    conn = get_db_connection()
    cursor = conn.cursor()

    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if model_id is not None:
        updates.append("model_id = ?")
        params.append(model_id)
    if prompt_template is not None:
        updates.append("prompt_template = ?")
        params.append(prompt_template)
    if bypass_ai is not None:
        updates.append("bypass_ai = ?")
        params.append(bypass_ai)
    if fallback_mode is not None:
        updates.append("fallback_mode = ?")
        params.append(fallback_mode)
    if fallback_message is not None:
        updates.append("fallback_message = ?")
        params.append(fallback_message)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(is_active)

    updates.append("updated_at = CURRENT_TIMESTAMP")

    if updates:
        query = f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?"
        params.append(webhook_id)

        cursor.execute(query, params)
        conn.commit()
        affected = conn.total_changes
        conn.close()

        return affected > 0

    conn.close()
    return False


def regenerate_webhook_tokens(webhook_id, regen_api=True, regen_config=False):
    """重新生成webhook的token"""
    conn = get_db_connection()
    cursor = conn.cursor()

    updates = []
    params = []
    tokens = {}

    if regen_api:
        new_api_token = secrets.token_urlsafe(32)
        updates.append("token = ?")
        params.append(new_api_token)
        tokens['api_token'] = new_api_token

    if regen_config:
        new_config_token = secrets.token_urlsafe(8)
        updates.append("config_token = ?")
        params.append(new_config_token)
        tokens['config_token'] = new_config_token

    if not updates:
        conn.close()
        return False, {}

    updates.append("updated_at = CURRENT_TIMESTAMP")

    query = f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?"
    params.append(webhook_id)

    cursor.execute(query, params)
    conn.commit()
    affected = conn.total_changes
    conn.close()

    return affected > 0, tokens


def add_webhook_subscription(webhook_id, target_type, target_id, created_by=None):
    """添加webhook订阅"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """INSERT INTO webhook_subscriptions 
               (webhook_id, target_type, target_id, created_by) 
               VALUES (?, ?, ?, ?)""",
            (webhook_id, target_type, target_id, created_by)
        )
        conn.commit()
        subscription_id = cursor.lastrowid
        conn.close()
        return True, subscription_id
    except sqlite3.IntegrityError:
        conn.close()
        return False, "该目标已订阅此webhook"
    except Exception as e:
        conn.close()
        return False, str(e)


def remove_webhook_subscription(webhook_id, target_type, target_id):
    """删除webhook订阅"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """DELETE FROM webhook_subscriptions 
           WHERE webhook_id = ? AND target_type = ? AND target_id = ?""",
        (webhook_id, target_type, target_id)
    )
    conn.commit()
    affected = conn.total_changes
    conn.close()

    return affected > 0


def get_webhook_subscriptions(webhook_id):
    """获取特定webhook的所有订阅"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT * FROM webhook_subscriptions 
           WHERE webhook_id = ? 
           ORDER BY created_at DESC""",
        (webhook_id,)
    )

    subscriptions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return subscriptions


def get_user_subscriptions(user_id, include_chat=True):
    """获取用户已订阅的所有webhook"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if include_chat:
        cursor.execute("""
            SELECT ws.*, w.name as webhook_name, w.description as webhook_description
            FROM webhook_subscriptions ws
            JOIN webhooks w ON ws.webhook_id = w.id
            WHERE (ws.target_type = 'user' AND ws.target_id = ?) 
               OR (ws.created_by = ?)
            ORDER BY ws.created_at DESC
        """, (user_id, user_id))
    else:
        cursor.execute("""
            SELECT ws.*, w.name as webhook_name, w.description as webhook_description
            FROM webhook_subscriptions ws
            JOIN webhooks w ON ws.webhook_id = w.id
            WHERE ws.target_type = 'user' AND ws.target_id = ?
            ORDER BY ws.created_at DESC
        """, (user_id,))

    subscriptions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return subscriptions


def log_webhook_call(webhook_id, request_data, response, status):
    """记录webhook调用日志"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if isinstance(request_data, dict):
        request_data = json.dumps(request_data, ensure_ascii=False)
    else:
        request_data = str(request_data)

    if not isinstance(response, str):
        response = json.dumps(response, ensure_ascii=False)

    cursor.execute(
        """INSERT INTO webhook_logs 
           (webhook_id, request_data, response, status) 
           VALUES (?, ?, ?, ?)""",
        (webhook_id, request_data, response, status)
    )
    conn.commit()
    conn.close()
    return True


def get_webhook_logs(webhook_id, limit=100):
    """获取webhook调用日志"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT * FROM webhook_logs 
           WHERE webhook_id = ? 
           ORDER BY created_at DESC 
           LIMIT ?""",
        (webhook_id, limit)
    )

    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return logs


def delete_webhook(webhook_id):
    """删除webhook及其所有订阅"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM webhook_subscriptions WHERE webhook_id = ?", (webhook_id,))
    cursor.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))

    conn.commit()
    affected = conn.total_changes
    conn.close()

    return affected > 0