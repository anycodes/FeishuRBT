#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
from .database import get_db_connection

logger = logging.getLogger(__name__)

def get_model(model_id=None, model_name=None):
    """获取模型信息"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if model_id:
        cursor.execute("SELECT * FROM models WHERE id = ?", (model_id,))
    elif model_name:
        cursor.execute("SELECT * FROM models WHERE name = ?", (model_name,))
    else:
        conn.close()
        return None

    model = cursor.fetchone()
    conn.close()
    return dict(model) if model else None

def get_all_models():
    """获取所有模型"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM models ORDER BY name")
    models = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return models

def add_model(name, description, dify_url, dify_type, api_key, parameters=None):
    """添加模型"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if parameters is None:
        parameters = {}

    if isinstance(parameters, dict):
        parameters_json = json.dumps(parameters, ensure_ascii=False)
    else:
        try:
            json.loads(parameters)
            parameters_json = parameters
        except (TypeError, json.JSONDecodeError):
            parameters_json = json.dumps({}, ensure_ascii=False)

    try:
        cursor.execute(
            "INSERT INTO models (name, description, dify_url, dify_type, api_key, parameters) VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, dify_url, dify_type, api_key, parameters_json)
        )
        conn.commit()
        model_id = cursor.lastrowid
        conn.close()
        return model_id
    except Exception as e:
        logger.error(f"添加模型失败: {str(e)}")
        conn.close()
        return None

def update_model(model_id, name=None, description=None, dify_url=None, dify_type=None, api_key=None, parameters=None):
    """更新模型"""
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
    if dify_url is not None:
        updates.append("dify_url = ?")
        params.append(dify_url)
    if dify_type is not None:
        updates.append("dify_type = ?")
        params.append(dify_type)
    if api_key is not None:
        updates.append("api_key = ?")
        params.append(api_key)
    if parameters is not None:
        updates.append("parameters = ?")
        params.append(json.dumps(parameters))

    updates.append("updated_at = CURRENT_TIMESTAMP")

    if updates:
        query = f"UPDATE models SET {', '.join(updates)} WHERE id = ?"
        params.append(model_id)
        cursor.execute(query, params)
        conn.commit()
        affected = conn.total_changes
        conn.close()
        return affected > 0

    conn.close()
    return False

def delete_model(model_id):
    """删除模型"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 先检查是否有命令关联此模型
    cursor.execute("SELECT COUNT(*) as count FROM commands WHERE model_id = ?", (model_id,))
    result = cursor.fetchone()
    if result and result['count'] > 0:
        conn.close()
        return False, "该模型有关联的命令，无法删除"

    # 检查是否为默认模型
    cursor.execute("SELECT value FROM configs WHERE key = 'default_model'")
    result = cursor.fetchone()
    if result and result['value'] == str(model_id):
        conn.close()
        return False, "该模型为默认模型，无法删除"

    # 执行删除
    cursor.execute("DELETE FROM models WHERE id = ?", (model_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0, "删除成功"