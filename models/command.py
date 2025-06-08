#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
from .database import get_db_connection

logger = logging.getLogger(__name__)

def get_command(command_id=None, trigger=None):
    """获取命令信息"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if command_id:
        cursor.execute("""
            SELECT c.*, m.name as model_name 
            FROM commands c 
            LEFT JOIN models m ON c.model_id = m.id 
            WHERE c.id = ?
        """, (command_id,))
    elif trigger:
        cursor.execute("""
            SELECT c.*, m.name as model_name 
            FROM commands c 
            LEFT JOIN models m ON c.model_id = m.id 
            WHERE c.trigger = ?
        """, (trigger,))
    else:
        conn.close()
        return None

    command = cursor.fetchone()
    conn.close()
    return dict(command) if command else None

def get_all_commands():
    """获取所有命令"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, m.name as model_name 
        FROM commands c 
        LEFT JOIN models m ON c.model_id = m.id 
        ORDER BY c.name
    """)
    commands = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return commands

def add_command(name, description, trigger, model_id, parameters=None):
    """添加命令"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 检查触发命令是否已存在
    cursor.execute("SELECT id FROM commands WHERE trigger = ?", (trigger,))
    if cursor.fetchone():
        conn.close()
        return False, "该触发命令已存在"

    # 添加命令
    cursor.execute(
        "INSERT INTO commands (name, description, trigger, model_id, parameters) VALUES (?, ?, ?, ?, ?)",
        (name, description, trigger, model_id, json.dumps(parameters or {}))
    )
    conn.commit()
    command_id = cursor.lastrowid
    conn.close()
    return True, command_id

def update_command(command_id, name=None, description=None, trigger=None, model_id=None, parameters=None):
    """更新命令"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 如果要更新触发命令，先检查是否已存在
    if trigger:
        cursor.execute("SELECT id FROM commands WHERE trigger = ? AND id != ?", (trigger, command_id))
        if cursor.fetchone():
            conn.close()
            return False, "该触发命令已存在"

    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if trigger is not None:
        updates.append("trigger = ?")
        params.append(trigger)
    if model_id is not None:
        updates.append("model_id = ?")
        params.append(model_id)
    if parameters is not None:
        updates.append("parameters = ?")
        params.append(json.dumps(parameters))

    updates.append("updated_at = CURRENT_TIMESTAMP")

    if updates:
        query = f"UPDATE commands SET {', '.join(updates)} WHERE id = ?"
        params.append(command_id)
        cursor.execute(query, params)
        conn.commit()
        affected = conn.total_changes
        conn.close()
        return affected > 0, "更新成功"

    conn.close()
    return False, "没有可更新的内容"

def delete_command(command_id):
    """删除命令"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM commands WHERE id = ?", (command_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0