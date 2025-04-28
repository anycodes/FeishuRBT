# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import uuid
import random
import logging
import threading
import sqlite3
import secrets
import hashlib
import traceback
import urllib.request
import urllib.parse
import urllib.error
import ssl
import re
import socket
from datetime import datetime, timedelta
from collections import deque
from bottle import Bottle, request, response, HTTPResponse, static_file, template, redirect

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lark_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 创建Bottle应用
app = Bottle()

# 数据库路径
DB_PATH = "lark_dify_bot.db"

# 飞书应用凭证 - 应该从配置文件或环境变量获取
VERIFICATION_TOKEN = os.environ.get("VERIFICATION_TOKEN", "your_verification_token")
APP_ID = os.environ.get("APP_ID", "your_app_id")
APP_SECRET = os.environ.get("APP_SECRET", "your_app_secret")
BOT_NAME = os.environ.get("BOT_NAME", "Dify机器人")  # 机器人的名称，用于识别@消息
BOT_OPEN_ID = os.environ.get("BOT_OPEN_ID", "")  # 如果有机器人的open_id，可以填写

# 请求去重
processed_events = deque(maxlen=100)
processing_lock = threading.RLock()

# 重试机制配置
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2  # 初始重试延迟(秒)
RETRY_BACKOFF_FACTOR = 1.5  # 延迟增长因子
API_TIMEOUT = 60  # API超时时间(秒)

# Web管理界面配置
ADMIN_TOKEN_EXPIRE_MINUTES = 60  # token失效时间(分钟)
STATIC_DIR = "static"  # 静态文件目录


# 工具函数 - 确保UTF-8编码
def ensure_utf8(text):
    """确保文本是UTF-8编码的字符串"""
    if text is None:
        return None
    if isinstance(text, bytes):
        return text.decode('utf-8')
    return text


def parse_utf8(request):
    # 1. 获取原始数据
    body = request.body.read()
    body_str = body.decode('utf-8')  # URL 编码的数据是 ASCII 兼容的

    # 2. 解析 URL 编码的数据
    form_data = {}
    for pair in body_str.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            key = urllib.parse.unquote_plus(key)
            value = urllib.parse.unquote_plus(value)
            form_data[key] = value
    return form_data


def init_database():
    """初始化SQLite数据库"""
    conn = sqlite3.connect(DB_PATH)
    # 确保SQLite可以处理UTF-8
    conn.execute("PRAGMA encoding = 'UTF-8'")
    cursor = conn.cursor()

    # 用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT UNIQUE NOT NULL,
        name TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 模型表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        dify_url TEXT NOT NULL,
        dify_type TEXT NOT NULL,
        api_key TEXT NOT NULL,
        parameters TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 命令表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        trigger TEXT UNIQUE NOT NULL,
        model_id INTEGER,
        parameters TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (model_id) REFERENCES models (id)
    )
    ''')

    # 配置表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS configs (
        key TEXT PRIMARY KEY,
        value TEXT,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 会话表 - 基础结构
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        model_id INTEGER,
        conversation_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (model_id) REFERENCES models (id)
    )
    ''')

    # 消息记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        user_id TEXT NOT NULL,
        content TEXT,
        is_user INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions (id)
    )
    ''')

    # 管理员令牌表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT UNIQUE NOT NULL,
        user_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expired_at TIMESTAMP,
        is_valid INTEGER DEFAULT 1
    )
    ''')

    # 创建默认配置
    cursor.execute("INSERT OR IGNORE INTO configs (key, value, description) VALUES (?, ?, ?)",
                   ("default_model", "", "默认使用的模型ID"))
    
    # 添加会话超时配置（分钟）
    cursor.execute("INSERT OR IGNORE INTO configs (key, value, description) VALUES (?, ?, ?)",
                  ("session_timeout", "30", "会话超时时间（分钟）"))

    # 向后兼容性处理 - 动态检查和添加列/表
    try:
        # ---------- 处理sessions表 ----------
        # 检查是否需要添加新列
        cursor.execute("PRAGMA table_info(sessions)")
        columns = {col[1] for col in cursor.fetchall()}
        
        if "last_active_at" not in columns:
            logger.info("向sessions表添加last_active_at列")
            cursor.execute("ALTER TABLE sessions ADD COLUMN last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        
        if "is_active" not in columns:
            logger.info("向sessions表添加is_active列")
            cursor.execute("ALTER TABLE sessions ADD COLUMN is_active INTEGER DEFAULT 1")
            
        if "command_id" not in columns:
            logger.info("向sessions表添加command_id列")
            cursor.execute("ALTER TABLE sessions ADD COLUMN command_id INTEGER DEFAULT NULL")
            
        # ---------- 创建新的webhook相关表 ----------
        # Webhook表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            token TEXT UNIQUE NOT NULL,
            config_token TEXT UNIQUE NOT NULL,
            model_id INTEGER,
            prompt_template TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES models (id)
        )
        ''')
        
        # Webhook订阅表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (webhook_id) REFERENCES webhooks (id),
            UNIQUE(webhook_id, target_type, target_id)
        )
        ''')
        
        # Webhook调用日志表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS webhook_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id INTEGER,
            request_data TEXT,
            response TEXT,
            status INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (webhook_id) REFERENCES webhooks (id)
        )
        ''')
            
    except Exception as e:
        logger.error(f"数据库更新时出错: {e}")
        logger.error(traceback.format_exc())

    conn.commit()
    conn.close()

    logger.info("数据库初始化完成")


def init_static_dir():
    """初始化静态文件目录"""
    os.makedirs(STATIC_DIR, exist_ok=True)

    # 如果没有CSS文件，创建一个简单的样式文件
    css_dir = os.path.join(STATIC_DIR, 'css')
    os.makedirs(css_dir, exist_ok=True)

    style_path = os.path.join(css_dir, 'style.css')
    if not os.path.exists(style_path):
        with open(style_path, 'w', encoding='utf-8') as f:
            f.write('''
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background-color: white;
                padding: 20px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            h1, h2 {
                color: #333;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }
            table, th, td {
                border: 1px solid #ddd;
            }
            th, td {
                padding: 12px;
                text-align: left;
            }
            th {
                background-color: #f2f2f2;
            }
            tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .btn {
                display: inline-block;
                padding: 8px 12px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                text-decoration: none;
                margin-right: 5px;
            }
            .btn-danger {
                background-color: #f44336;
            }
            .btn-primary {
                background-color: #2196F3;
            }
            .btn-warning {
                background-color: #ff9800;
            }
            .btn-info {
                background-color: #00bcd4;
            }
            form {
                margin-top: 20px;
            }
            input, textarea, select {
                width: 100%;
                padding: 8px;
                margin: 5px 0 15px 0;
                display: inline-block;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: border-box;
            }
            label {
                font-weight: bold;
            }
            .card {
                background-color: white;
                border-radius: 5px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 15px;
                margin-bottom: 20px;
            }
            .alert {
                padding: 10px 15px;
                border-radius: 4px;
                margin-bottom: 15px;
            }
            .alert-success {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .alert-info {
                background-color: #d1ecf1;
                color: #0c5460;
                border: 1px solid #bee5eb;
            }
            .alert-warning {
                background-color: #fff3cd;
                color: #856404;
                border: 1px solid #ffeeba;
            }
            .alert-error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .log-content {
                max-height: 150px;
                max-width: 300px;
                overflow: auto;
                white-space: pre-wrap;
                font-family: monospace;
                font-size: 12px;
                background-color: #f5f5f5;
                padding: 5px;
                border-radius: 3px;
            }
            .code-display {
                font-family: monospace;
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                margin-bottom: 10px;
            }
            ''')

    # 创建管理页面的HTML模板目录
    templates_dir = 'views'
    os.makedirs(templates_dir, exist_ok=True)

    # 创建基本模板文件
    create_base_templates(templates_dir)

    logger.info("静态文件目录初始化完成")


def create_base_templates(templates_dir):
    """创建基本的HTML模板文件"""
    # 创建布局模板
    layout_path = os.path.join(templates_dir, 'layout.tpl')
    if not os.path.exists(layout_path):
        with open(layout_path, 'w', encoding='utf-8') as f:
            f.write('''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title or 'Dify机器人管理'}}</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <div class="container">
        <h1>Dify机器人管理</h1>
        <nav>
            <a href="/admin/models" class="btn">模型管理</a>
            <a href="/admin/commands" class="btn">命令管理</a>
            <a href="/admin/webhooks" class="btn">Webhook管理</a>
            <a href="/admin/config" class="btn">系统配置</a>
            <a href="/admin/users" class="btn">用户管理</a>
            <a href="/admin/logs" class="btn">日志查看</a>
            <a href="/admin/logout" class="btn btn-danger">退出登录</a>
        </nav>
        <hr>
        %if defined('message'):
        <div class="alert {{message_type or 'info'}}">
            {{message}}
        </div>
        %end

        {{!base}}
    </div>
</body>
</html>''')

    # 创建模型列表模板
    models_path = os.path.join(templates_dir, 'models.tpl')
    if not os.path.exists(models_path):
        with open(models_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='模型管理')
<h2>模型管理</h2>
<a href="/admin/models/add" class="btn">添加模型</a>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>名称</th>
            <th>描述</th>
            <th>类型</th>
            <th>API地址</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for model in models:
        <tr>
            <td>{{model['id']}}</td>
            <td>{{model['name']}}</td>
            <td>{{model['description']}}</td>
            <td>{{model['dify_type']}}</td>
            <td>{{model['dify_url']}}</td>
            <td>
                <a href="/admin/models/edit/{{model['id']}}" class="btn btn-primary">编辑</a>
                <a href="/admin/models/delete/{{model['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除吗？')">删除</a>
            </td>
        </tr>
        % end
    </tbody>
</table>''')

    # 创建模型表单模板
    model_form_path = os.path.join(templates_dir, 'model_form.tpl')
    if not os.path.exists(model_form_path):
        with open(model_form_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title=title)
<h2>{{title}}</h2>
<a href="/admin/models" class="btn">返回列表</a>

<form action="{{action}}" method="post">
    <div>
        <label for="name">模型名称:</label>
        <input type="text" id="name" name="name" value="{{model['name'] if model else ''}}" required>
    </div>

    <div>
        <label for="description">模型描述:</label>
        <textarea id="description" name="description" rows="3">{{model['description'] if model else ''}}</textarea>
    </div>

    <div>
        <label for="dify_url">Dify API地址:</label>
        <input type="text" id="dify_url" name="dify_url" value="{{model['dify_url'] if model else ''}}" required>
    </div>

    <div>
        <label for="dify_type">模型类型:</label>
        <select id="dify_type" name="dify_type" required>
            <option value="chatbot" {{'selected' if model and model['dify_type'] == 'chatbot' else ''}}>Chatbot</option>
            <option value="agent" {{'selected' if model and model['dify_type'] == 'agent' else ''}}>Agent</option>
            <option value="flow" {{'selected' if model and model['dify_type'] == 'flow' else ''}}>Flow</option>
        </select>
    </div>

    <div>
        <label for="api_key">API密钥:</label>
        <input type="text" id="api_key" name="api_key" value="{{model['api_key'] if model else ''}}" required>
    </div>

    <div>
        <button type="submit" class="btn btn-primary">保存</button>
    </div>
</form>''')

    # 创建命令列表模板
    commands_path = os.path.join(templates_dir, 'commands.tpl')
    if not os.path.exists(commands_path):
        with open(commands_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='命令管理')
<h2>命令管理</h2>
<a href="/admin/commands/add" class="btn">添加命令</a>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>名称</th>
            <th>描述</th>
            <th>触发指令</th>
            <th>关联模型</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for cmd in commands:
        <tr>
            <td>{{cmd['id']}}</td>
            <td>{{cmd['name']}}</td>
            <td>{{cmd['description']}}</td>
            <td>{{cmd['trigger']}}</td>
            <td>{{cmd['model_name']}}</td>
            <td>
                <a href="/admin/commands/edit/{{cmd['id']}}" class="btn btn-primary">编辑</a>
                <a href="/admin/commands/delete/{{cmd['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除吗？')">删除</a>
            </td>
        </tr>
        % end
    </tbody>
</table>''')

    # 创建命令表单模板
    command_form_path = os.path.join(templates_dir, 'command_form.tpl')
    if not os.path.exists(command_form_path):
        with open(command_form_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title=title)
<h2>{{title}}</h2>
<a href="/admin/commands" class="btn">返回列表</a>

<form action="{{action}}" method="post">
    <div>
        <label for="name">命令名称:</label>
        <input type="text" id="name" name="name" value="{{command['name'] if command else ''}}" required>
    </div>

    <div>
        <label for="description">命令描述:</label>
        <textarea id="description" name="description" rows="3">{{command['description'] if command else ''}}</textarea>
    </div>

    <div>
        <label for="trigger">触发指令:</label>
        <input type="text" id="trigger" name="trigger" value="{{command['trigger'] if command else ''}}" required>
        <small>例如：\\hello</small>
    </div>

    <div>
        <label for="model_id">关联模型:</label>
        <select id="model_id" name="model_id" required>
            % for model in models:
            <option value="{{model['id']}}" {{'selected' if command and str(command['model_id']) == str(model['id']) else ''}}>{{model['name']}}</option>
            % end
        </select>
    </div>

    <div>
        <button type="submit" class="btn btn-primary">保存</button>
    </div>
</form>''')

    # 创建系统配置模板
    config_path = os.path.join(templates_dir, 'config.tpl')
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='系统配置')
<h2>系统配置</h2>

<form action="/admin/config/update" method="post">
    <div>
        <label for="default_model">默认模型:</label>
        <select id="default_model" name="default_model">
            <option value="">-- 不设置默认模型 --</option>
            % for model in models:
            <option value="{{model['id']}}" {{'selected' if default_model and str(default_model['id']) == str(model['id']) else ''}}>{{model['name']}}</option>
            % end
        </select>
    </div>
    
    <div>
        <label for="session_timeout">会话超时时间（分钟）:</label>
        <input type="number" id="session_timeout" name="session_timeout" value="{{configs.get('session_timeout', {}).get('value', '30')}}" min="1" required>
    </div>

    <div>
        <button type="submit" class="btn btn-primary">保存配置</button>
    </div>
</form>''')

    # 创建用户管理模板
    users_path = os.path.join(templates_dir, 'users.tpl')
    if not os.path.exists(users_path):
        with open(users_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='用户管理')
<h2>用户管理</h2>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>用户ID</th>
            <th>用户名</th>
            <th>角色</th>
            <th>创建时间</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for user in users:
        <tr>
            <td>{{user['id']}}</td>
            <td>{{user['user_id']}}</td>
            <td>{{user['name'] or '未设置'}}</td>
            <td>{{'管理员' if user['is_admin'] else '普通用户'}}</td>
            <td>{{user['created_at']}}</td>
            <td>
                % if user['is_admin']:
                <a href="/admin/users/toggle_admin/{{user['user_id']}}" class="btn btn-danger">取消管理员</a>
                % else:
                <a href="/admin/users/toggle_admin/{{user['user_id']}}" class="btn btn-primary">设为管理员</a>
                % end
            </td>
        </tr>
        % end
    </tbody>
</table>''')

    # 创建日志查看模板
    logs_path = os.path.join(templates_dir, 'logs.tpl')
    if not os.path.exists(logs_path):
        with open(logs_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='日志查看')
<h2>系统日志</h2>
<p><small>显示最近1000行日志</small></p>

<div style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow: auto; max-height: 600px;">
    <pre>{{log_content}}</pre>
</div>

<script>
// 自动滚动到底部
window.onload = function() {
    var logContainer = document.querySelector('pre').parentElement;
    logContainer.scrollTop = logContainer.scrollHeight;
};
</script>''')

    # 创建错误页面模板
    error_path = os.path.join(templates_dir, 'error.tpl')
    if not os.path.exists(error_path):
        with open(error_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='错误')
<h2>发生错误</h2>
<div class="alert error">
    <p>{{error_message}}</p>
</div>
<a href="{{back_url}}" class="btn">返回</a>''')

    # 创建Webhook相关模板 - 新增部分
    # 1. Webhook列表模板
    webhooks_path = os.path.join(templates_dir, 'webhooks.tpl')
    if not os.path.exists(webhooks_path):
        with open(webhooks_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='Webhook管理')
<h2>Webhook管理</h2>
<p>Webhook允许外部系统调用机器人并将消息推送给订阅者。</p>
<a href="/admin/webhooks/add" class="btn">添加Webhook</a>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>名称</th>
            <th>描述</th>
            <th>模型</th>
            <th>订阅数</th>
            <th>状态</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for webhook in webhooks:
        <tr>
            <td>{{webhook['id']}}</td>
            <td>{{webhook['name']}}</td>
            <td>{{webhook['description'] or '-'}}</td>
            <td>{{webhook['model_name']}}</td>
            <td>
                % subscription_count = len(get_webhook_subscriptions(webhook['id']))
                <a href="/admin/webhooks/subscriptions/{{webhook['id']}}">
                    {{subscription_count}} 个订阅
                </a>
            </td>
            <td>{{("启用" if webhook['is_active'] else "禁用")}}</td>
            <td>
                <a href="/admin/webhooks/edit/{{webhook['id']}}" class="btn btn-primary">编辑</a>
                <a href="/admin/webhooks/regenerate-token/{{webhook['id']}}?type=api" class="btn btn-warning" onclick="return confirm('确定要重新生成API Token吗？旧的Token将立即失效！')">重新生成API Token</a>
                <a href="/admin/webhooks/regenerate-token/{{webhook['id']}}?type=config" class="btn btn-warning" onclick="return confirm('确定要重新生成配置Token吗？用户将需要重新订阅！')">重新生成配置Token</a>
                <a href="/admin/webhook-logs/{{webhook['id']}}" class="btn btn-info">查看日志</a>
                <a href="/admin/webhooks/delete/{{webhook['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除吗？这将删除所有相关订阅！')">删除</a>
            </td>
        </tr>
        % end
    </tbody>
</table>''')

    # 2. Webhook表单模板
    webhook_form_path = os.path.join(templates_dir, 'webhook_form.tpl')
    if not os.path.exists(webhook_form_path):
        with open(webhook_form_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title=title)
<h2>{{title}}</h2>
<a href="/admin/webhooks" class="btn">返回列表</a>

<form action="{{action}}" method="post">
    <div>
        <label for="name">Webhook名称:</label>
        <input type="text" id="name" name="name" value="{{webhook['name'] if webhook else ''}}" required>
    </div>

    <div>
        <label for="description">描述:</label>
        <textarea id="description" name="description" rows="3">{{webhook['description'] if webhook else ''}}</textarea>
    </div>

    <div>
        <label for="model_id">使用模型:</label>
        <select id="model_id" name="model_id" required>
            % for model in models:
            <option value="{{model['id']}}" {{'selected' if webhook and str(webhook['model_id']) == str(model['id']) else ''}}>{{model['name']}}</option>
            % end
        </select>
    </div>

    <div>
        <label for="prompt_template">提示词模板(可选):</label>
        <textarea id="prompt_template" name="prompt_template" rows="5" placeholder="在此编写提示词模板，使用{data}表示接收到的数据。例如：请分析以下数据并提炼关键信息：{data}">{{webhook['prompt_template'] if webhook else ''}}</textarea>
        <small>如果不填写，将使用默认模板：分析以下数据:\n\n{data}</small>
    </div>

    % if webhook:
    <div>
        <label for="is_active">状态:</label>
        <select id="is_active" name="is_active">
            <option value="1" {{'selected' if webhook and webhook['is_active'] == 1 else ''}}>启用</option>
            <option value="0" {{'selected' if webhook and webhook['is_active'] == 0 else ''}}>禁用</option>
        </select>
    </div>
    
    <div>
        <label>配置Token:</label>
        <div class="code-display">{{webhook['config_token']}}</div>
        <small>用户使用此Token订阅，命令：\subscribe-event {{webhook['config_token']}}</small>
    </div>
    % end

    <div>
        <button type="submit" class="btn btn-primary">保存</button>
    </div>
</form>

<style>
.code-display {
    font-family: monospace;
    background-color: #f5f5f5;
    padding: 10px;
    border-radius: 4px;
    margin-bottom: 10px;
}
</style>''')

    # 3. Webhook创建成功模板
    webhook_created_path = os.path.join(templates_dir, 'webhook_created.tpl')
    if not os.path.exists(webhook_created_path):
        with open(webhook_created_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='Webhook创建成功')
<h2>Webhook创建成功</h2>

<div class="alert alert-success">
    <p>您的Webhook「{{name}}」已成功创建！</p>
</div>

<div class="card">
    <h3>Webhook URL (API Token)</h3>
    <p><code>{{webhook_url}}</code></p>
    <p>外部系统使用此URL发送请求</p>
    <button class="btn" onclick="copyToClipboard('{{webhook_url}}')">复制URL</button>
</div>

<div class="card">
    <h3>API Token</h3>
    <p><code>{{api_token}}</code></p>
    <p class="alert alert-warning">请保存此Token！出于安全考虑，此Token仅会显示一次。</p>
    <button class="btn" onclick="copyToClipboard('{{api_token}}')">复制Token</button>
</div>

<div class="card">
    <h3>配置Token (订阅用)</h3>
    <p><code>{{config_token}}</code></p>
    <p>用户使用此Token订阅webhook通知</p>
    <div class="alert alert-info">
        订阅命令: <code>\subscribe-event {{config_token}}</code>
    </div>
    <button class="btn" onclick="copyToClipboard('{{config_token}}')">复制Token</button>
</div>

<p>
    <a href="/admin/webhooks" class="btn">返回Webhook列表</a>
</p>

<script>
function copyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    alert('已复制到剪贴板');
}
</script>''')

    # 4. API Token重新生成模板
    webhook_api_token_regenerated_path = os.path.join(templates_dir, 'webhook_api_token_regenerated.tpl')
    if not os.path.exists(webhook_api_token_regenerated_path):
        with open(webhook_api_token_regenerated_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='API Token已重新生成')
<h2>API Token已重新生成</h2>

<div class="alert alert-success">
    <p>Webhook「{{name}}」的API Token已成功重新生成！</p>
    <p>旧的API Token已失效，请更新所有使用此Webhook的外部系统。</p>
</div>

<div class="card">
    <h3>新的Webhook URL</h3>
    <p><code>{{webhook_url}}</code></p>
    <button class="btn" onclick="copyToClipboard('{{webhook_url}}')">复制URL</button>
</div>

<div class="card">
    <h3>新的API Token</h3>
    <p><code>{{api_token}}</code></p>
    <p class="alert alert-warning">请保存此Token！出于安全考虑，此Token仅会显示一次。</p>
    <button class="btn" onclick="copyToClipboard('{{api_token}}')">复制Token</button>
</div>

<p>
    <a href="/admin/webhooks" class="btn">返回Webhook列表</a>
</p>

<script>
function copyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    alert('已复制到剪贴板');
}
</script>''')

    # 5. 配置Token重新生成模板
    webhook_config_token_regenerated_path = os.path.join(templates_dir, 'webhook_config_token_regenerated.tpl')
    if not os.path.exists(webhook_config_token_regenerated_path):
        with open(webhook_config_token_regenerated_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='配置Token已重新生成')
<h2>配置Token已重新生成</h2>

<div class="alert alert-success">
    <p>Webhook「{{name}}」的配置Token已成功重新生成！</p>
    <p>用户需要使用新的配置Token重新订阅。</p>
</div>

<div class="card">
    <h3>新的配置Token (订阅用)</h3>
    <p><code>{{config_token}}</code></p>
    <div class="alert alert-info">
        新的订阅命令: <code>\subscribe-event {{config_token}}</code>
    </div>
    <button class="btn" onclick="copyToClipboard('{{config_token}}')">复制Token</button>
</div>

<p>
    <a href="/admin/webhooks" class="btn">返回Webhook列表</a>
</p>

<script>
function copyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    alert('已复制到剪贴板');
}
</script>''')

    # 6. Webhook订阅列表模板
    webhook_subscriptions_path = os.path.join(templates_dir, 'webhook_subscriptions.tpl')
    if not os.path.exists(webhook_subscriptions_path):
        with open(webhook_subscriptions_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='Webhook订阅列表')
<h2>「{{webhook['name']}}」订阅列表</h2>
<a href="/admin/webhooks" class="btn">返回Webhook列表</a>

<div class="card">
    <h3>配置Token (用于订阅)</h3>
    <p><code>{{webhook['config_token']}}</code></p>
    <div class="alert alert-info">
        用户订阅命令: <code>\subscribe-event {{webhook['config_token']}}</code>
    </div>
</div>

<h3>当前订阅 ({{len(subscriptions)}})</h3>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>类型</th>
            <th>目标ID</th>
            <th>创建者</th>
            <th>创建时间</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for sub in subscriptions:
        <tr>
            <td>{{sub['id']}}</td>
            <td>{{sub['target_type']}}</td>
            <td>{{sub['target_id']}}</td>
            <td>{{sub['created_by'] or '-'}}</td>
            <td>{{sub['created_at']}}</td>
            <td>
                <a href="/admin/webhooks/remove-subscription/{{sub['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除此订阅吗？')">删除</a>
            </td>
        </tr>
        % end
        % if not subscriptions:
        <tr>
            <td colspan="6" class="text-center">暂无订阅</td>
        </tr>
        % end
    </tbody>
</table>''')

    # 7. Webhook日志模板
    webhook_logs_path = os.path.join(templates_dir, 'webhook_logs.tpl')
    if not os.path.exists(webhook_logs_path):
        with open(webhook_logs_path, 'w', encoding='utf-8') as f:
            f.write('''% rebase('layout.tpl', title='Webhook调用日志')
<h2>「{{webhook['name']}}」调用日志</h2>
<a href="/admin/webhooks" class="btn">返回Webhook列表</a>

<p>显示最近100条调用记录</p>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>时间</th>
            <th>状态</th>
            <th>请求数据</th>
            <th>响应</th>
        </tr>
    </thead>
    <tbody>
        % for log in logs:
        <tr>
            <td>{{log['id']}}</td>
            <td>{{log['created_at']}}</td>
            <td>{{log['status']}}</td>
            <td>
                <div class="log-content">{{log['request_data']}}</div>
            </td>
            <td>
                <div class="log-content">{{log['response']}}</div>
            </td>
        </tr>
        % end
        % if not logs:
        <tr>
            <td colspan="5" class="text-center">暂无调用记录</td>
        </tr>
        % end
    </tbody>
</table>

<style>
.log-content {
    max-height: 150px;
    max-width: 300px;
    overflow: auto;
    white-space: pre-wrap;
    font-family: monospace;
    font-size: 12px;
    background-color: #f5f5f5;
    padding: 5px;
    border-radius: 3px;
}
</style>''')
            

# 数据库操作函数
def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 返回字典格式的结果

    # 设置编码
    conn.execute("PRAGMA encoding = 'UTF-8'")

    # 使用原生字符串，不进行编码转换
    conn.text_factory = str

    return conn


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


def set_user_admin(user_id, is_admin=1):
    """设置用户管理员权限"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin = ? WHERE user_id = ?", (is_admin, user_id))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


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

    # 处理参数
    if parameters is None:
        parameters = {}

    if isinstance(parameters, dict):
        parameters_json = json.dumps(parameters, ensure_ascii=False)
    else:
        try:
            # 尝试解析字符串参数
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

    # 构建更新语句
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

    # 执行更新
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

    # 构建更新语句
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

    # 执行更新
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


def get_default_model():
    """获取默认模型"""
    default_model_id = get_config("default_model")
    if default_model_id:
        return get_model(model_id=default_model_id)
    return None


def create_admin_token(user_id):
    """创建管理员token"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 失效该用户的所有历史token
    cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE user_id = ?", (user_id,))

    # 创建新token
    token = secrets.token_urlsafe(32).replace("_", "x")
    expired_at = datetime.now() + timedelta(minutes=ADMIN_TOKEN_EXPIRE_MINUTES)

    cursor.execute(
        "INSERT INTO admin_tokens (token, user_id, expired_at) VALUES (?, ?, ?)",
        (token, user_id, expired_at)
    )

    conn.commit()
    conn.close()

    return token


def validate_admin_token(token):
    """验证管理员token是否有效"""
    if not token:
        return False, None

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.*, u.is_admin 
        FROM admin_tokens t
        JOIN users u ON t.user_id = u.user_id
        WHERE t.token = ? AND t.is_valid = 1 AND t.expired_at > CURRENT_TIMESTAMP
    """, (token,))

    result = cursor.fetchone()

    if not result:
        conn.close()
        return False, None

    # 用户必须是管理员
    if not result['is_admin']:
        conn.close()
        return False, None

    # 更新最后活动时间
    cursor.execute(
        "UPDATE admin_tokens SET last_active_at = CURRENT_TIMESTAMP WHERE token = ?",
        (token,)
    )

    # 更新过期时间
    new_expired_at = datetime.now() + timedelta(minutes=ADMIN_TOKEN_EXPIRE_MINUTES)
    cursor.execute(
        "UPDATE admin_tokens SET expired_at = ? WHERE token = ?",
        (new_expired_at, token)
    )

    conn.commit()
    user_id = result['user_id']
    conn.close()

    return True, user_id


def invalidate_admin_token(token):
    """使管理员token失效"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE token = ?", (token,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def invalidate_all_admin_tokens():
    """使所有管理员token失效"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE admin_tokens SET is_valid = 0")
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def get_or_create_session(user_id, model_id=None, command_id=None):
    """获取或创建会话，支持模型和命令维度"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取会话超时配置（分钟）
    timeout_minutes = int(get_config("session_timeout") or "30")
    timeout_timestamp = datetime.now() - timedelta(minutes=timeout_minutes)

    # 查找活动会话，考虑模型和命令维度
    if model_id and command_id:
        # 精确匹配模型ID和命令ID
        cursor.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? AND model_id = ? AND command_id = ? AND is_active = 1
                AND last_active_at > ?
            ORDER BY last_active_at DESC LIMIT 1
        """, (user_id, model_id, command_id, timeout_timestamp))
    elif model_id:
        # 匹配模型ID，无命令ID
        cursor.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? AND model_id = ? AND command_id IS NULL AND is_active = 1
                AND last_active_at > ?
            ORDER BY last_active_at DESC LIMIT 1
        """, (user_id, model_id, timeout_timestamp))
    elif command_id:
        # 匹配命令ID，无指定模型ID（使用命令的关联模型）
        cursor.execute("""
            SELECT s.* FROM sessions s
            JOIN commands c ON s.command_id = c.id
            WHERE s.user_id = ? AND s.command_id = ? AND s.is_active = 1
                AND s.last_active_at > ?
            ORDER BY s.last_active_at DESC LIMIT 1
        """, (user_id, command_id, timeout_timestamp))
    else:
        # 查找最近有效的会话，无特定模型或命令要求
        cursor.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? AND is_active = 1 AND last_active_at > ?
            ORDER BY last_active_at DESC LIMIT 1
        """, (user_id, timeout_timestamp))

    session = cursor.fetchone()

    if session:
        # 更新现有会话的活动时间
        cursor.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP, last_active_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session['id'],)
        )
        conn.commit()
        session_id = session['id']
        conversation_id = session['conversation_id']
    else:
        # 处理要创建的新会话的模型ID
        if not model_id and command_id:
            # 如果只指定了命令ID，从命令获取关联的模型ID
            cursor.execute("SELECT model_id FROM commands WHERE id = ?", (command_id,))
            result = cursor.fetchone()
            if result:
                model_id = result['model_id']

        if not model_id:
            # 获取默认模型ID
            default_model_id = get_config("default_model")
            # 确保model_id是整数类型
            if default_model_id:
                try:
                    model_id = int(default_model_id)
                except (ValueError, TypeError):
                    model_id = None

        # 创建新会话
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

    # 如果未找到模型，尝试获取默认模型
    if not model:
        default_model = get_default_model()
        if default_model:
            # 更新会话使用默认模型
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


# Webhook相关函数
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


def create_webhook(name, description, model_id, prompt_template=None):
    """创建新的webhook，返回主token和配置token"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 生成唯一token (用于API调用)
    api_token = secrets.token_urlsafe(32)
    # 生成唯一配置token (用于用户订阅)
    config_token = secrets.token_urlsafe(8)  # 短一些便于用户使用
    
    cursor.execute(
        """INSERT INTO webhooks 
           (name, description, token, config_token, model_id, prompt_template) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, description, api_token, config_token, model_id, prompt_template)
    )
    conn.commit()
    webhook_id = cursor.lastrowid
    conn.close()
    
    return webhook_id, api_token, config_token


def get_webhook(webhook_id=None, api_token=None, config_token=None):
    """获取webhook信息，支持通过ID、API token或配置token查询"""
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
                  prompt_template=None, is_active=None):
    """更新webhook"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 构建更新语句
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
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(is_active)
        
    updates.append("updated_at = CURRENT_TIMESTAMP")
    
    # 执行更新
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
    """重新生成webhook的token，可以选择性重新生成API token或配置token"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    tokens = {}
    
    # 生成新API token
    if regen_api:
        new_api_token = secrets.token_urlsafe(32)
        updates.append("token = ?")
        params.append(new_api_token)
        tokens['api_token'] = new_api_token
    
    # 生成新配置token
    if regen_config:
        new_config_token = secrets.token_urlsafe(8)
        updates.append("config_token = ?")
        params.append(new_config_token)
        tokens['config_token'] = new_config_token
    
    if not updates:
        conn.close()
        return False, {}
    
    # 更新时间戳
    updates.append("updated_at = CURRENT_TIMESTAMP")
    
    # 执行更新
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
        # 唯一约束失败，表示已存在相同订阅
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
        # 包括用户参与的群组订阅
        cursor.execute("""
            SELECT ws.*, w.name as webhook_name, w.description as webhook_description
            FROM webhook_subscriptions ws
            JOIN webhooks w ON ws.webhook_id = w.id
            WHERE (ws.target_type = 'user' AND ws.target_id = ?) 
               OR (ws.created_by = ?)
            ORDER BY ws.created_at DESC
        """, (user_id, user_id))
    else:
        # 只包括用户个人订阅
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
    
    # 将数据转换为JSON字符串
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
    
    # 首先删除所有订阅
    cursor.execute("DELETE FROM webhook_subscriptions WHERE webhook_id = ?", (webhook_id,))
    
    # 然后删除webhook本身
    cursor.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    
    conn.commit()
    affected = conn.total_changes
    conn.close()
    
    return affected > 0


# 飞书API相关函数
def get_tenant_access_token():
    """获取tenant_access_token用于API调用"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "app_id": APP_ID,
        "app_secret": APP_SECRET
    }

    data_bytes = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        response_data = http_request_with_retry(req)
        if response_data:
            response_json = json.loads(response_data.decode('utf-8'))
            token = response_json.get("tenant_access_token")
            logger.info(f"成功获取tenant_access_token: {token[:10]}...")
            return token
        return None
    except Exception as e:
        logger.error(f"获取tenant_access_token失败: {e}")
        return None


def send_message(open_id=None, chat_id=None, content=None):
    """发送消息到用户或群组，支持文本和Markdown格式"""
    base_url = "https://open.feishu.cn/open-apis/im/v1/messages"

    params = {"receive_id_type": "open_id" if open_id else "chat_id"}
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_tenant_access_token()}"
    }

    # 检测是否为Markdown格式，如果是则使用富文本(post)格式发送
    if content and is_markdown(content):
        logger.info("检测到Markdown格式内容，使用富文本格式发送")
        # 构建富文本消息，使用md标签包装Markdown内容
        post_content = {
            "zh_cn": {  # 简体中文，可以根据需要添加其他语言
                "title": "",  # 空标题
                "content": [
                    [
                        {
                            "tag": "md",
                            "text": content
                        }
                    ]
                ]
            }
        }

        data = {
            "receive_id": open_id if open_id else chat_id,
            "msg_type": "post",
            "content": json.dumps(post_content)
        }
    else:
        # 普通文本消息
        msg_content = {"text": content} if content else {"text": "Hello, I'm a bot!"}

        data = {
            "receive_id": open_id if open_id else chat_id,
            "msg_type": "text",
            "content": json.dumps(msg_content)
        }

    data_bytes = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        response_data = http_request_with_retry(req)
        if response_data:
            response_json = json.loads(response_data.decode('utf-8'))
            logger.info(f"消息发送成功: {response_json}")
            return response_json
        return {"code": -1, "msg": "请求失败"}
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        return {"code": -1, "msg": str(e)}


# Dify API相关函数
def dify_request(model, endpoint, method="POST", data=None, files=None, params=None, stream=False):
    """统一处理Dify API请求"""
    base_url = model['dify_url'].rstrip('/')
    url = f"{base_url}/{endpoint.lstrip('/')}"

    logger.info(url)

    headers = {
        "Authorization": f"Bearer {model['api_key']}"
    }

    # 默认为JSON请求
    if not files:
        headers["Content-Type"] = "application/json"

    # 构建请求
    if method == "GET":
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
    else:  # POST, PUT, DELETE等
        if files:
            # 实现multipart/form-data逻辑
            # 注意：这需要完整的multipart实现，这里简化处理
            logger.warning("文件上传功能需要特殊处理，当前实现可能不完整")
            # 如果需要上传文件，应该使用适当的库如requests
            boundary = '----WebKitFormBoundary' + ''.join(random.sample('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 16))
            headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
            # 这里需要完整的multipart/form-data编码实现
            data_bytes = b''  # 需要正确实现
        elif data:
            data_bytes = json.dumps(data).encode('utf-8')
        else:
            data_bytes = None

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    # 忽略SSL验证
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        if stream:
            # 处理流式响应
            return urllib.request.urlopen(req, context=ctx, timeout=API_TIMEOUT)
        else:
            # 处理普通响应
            with urllib.request.urlopen(req, context=ctx, timeout=API_TIMEOUT) as response:
                response_data = response.read()
                if response_data:
                    return json.loads(response_data.decode('utf-8'))
                return None
    except Exception as e:
        logger.error(f"Dify API请求失败: {e}")
        logger.error(traceback.format_exc())
        return None


def ask_dify_chatbot(model, query, conversation_id=None, user_id="default_user", streaming=True):
    """向Dify聊天机器人API发送请求"""
    data = {
        "query": query,
        "inputs": {},
        "user": user_id,
        "response_mode": "streaming" if streaming else "blocking"
    }

    if conversation_id:
        data["conversation_id"] = conversation_id

    if streaming:
        # 流式模式，返回响应对象
        response_obj = dify_request(model, "chat-messages", data=data, stream=True)
        # 检查返回值是否为None
        if response_obj is None:
            logger.error("无法连接到Dify API或获取有效响应")
            return None  # 返回None，让调用方处理
        return response_obj
    else:
        # 阻塞模式，返回结果
        response = dify_request(model, "chat-messages", data=data)

        if response and "answer" in response:
            # 保存conversation_id
            return response["answer"], response.get("conversation_id")

        logger.warning(f"未找到回答字段: {response}")
        return "抱歉，无法获取回答", None


def ask_dify_agent(model, query, conversation_id=None, user_id="default_user", streaming=True):
    """向Dify Agent API发送请求"""
    # Agent API与聊天机器人API相同
    return ask_dify_chatbot(model, query, conversation_id, user_id, streaming)


def ask_dify_flow(model, query, conversation_id=None, user_id="default_user", streaming=True):
    """向Dify Flow API发送请求"""
    # Flow API也与聊天机器人API相同
    return ask_dify_chatbot(model, query, conversation_id, user_id, streaming)


def process_dify_stream(stream, session_id, user_id):
    """处理Dify流式响应并逐步返回结果"""
    if stream is None:
        error_msg = "无法获取流式响应"
        logger.error(error_msg)
        yield error_msg
        return error_msg, None

    full_response = ""
    conversation_id = None
    buffer = b""

    try:
        while True:
            chunk = stream.read(1024)
            if not chunk:
                break

            buffer += chunk

            # 处理完整的SSE事件
            while b"\n\n" in buffer:
                try:
                    event, buffer = buffer.split(b"\n\n", 1)
                    if event.startswith(b"data: "):
                        event_data = event[6:]  # 移除 "data: " 前缀
                        try:
                            event_json = json.loads(event_data)
                            event_type = event_json.get("event")

                            # 处理不同类型的事件
                            if event_type == "message":
                                # 基础聊天机器人消息
                                response_part = event_json.get("answer", "")
                                full_response += response_part
                                yield response_part

                            elif event_type == "agent_message":
                                # Agent模式文本块
                                response_part = event_json.get("answer", "")
                                full_response += response_part
                                yield response_part

                            elif event_type == "workflow_started":
                                # Flow模式开始事件
                                logger.info(f"Workflow started: {event_json}")

                            elif event_type == "node_started":
                                # Flow模式节点开始
                                logger.info(f"Node started: {event_json}")

                            elif event_type == "node_finished":
                                # Flow模式节点完成
                                logger.info(f"Node finished: {event_json}")

                            elif event_type == "workflow_finished":
                                # Flow模式完成
                                logger.info(f"Workflow finished: {event_json}")

                            elif event_type == "agent_thought":
                                # Agent思考过程
                                logger.info(f"Agent thought: {event_json}")
                                # 可以选择性地将思考过程也返回给用户
                                thought = event_json.get("thought", "")
                                # if thought:
                                #     yield f"\n[Agent思考] {thought}\n"

                            elif event_type == "message_file":
                                # 文件事件
                                logger.info(f"File message: {event_json}")
                                file_url = event_json.get("url", "")
                                if file_url:
                                    yield f"\n[文件] {file_url}\n"

                            elif event_type == "message_end":
                                # 保存会话ID
                                if "conversation_id" in event_json:
                                    conversation_id = event_json["conversation_id"]
                                    update_session_conversation(session_id, conversation_id)
                                logger.info("Message stream ended")

                            elif event_type == "error":
                                # 错误处理
                                error_msg = f"处理出错: {event_json.get('message', '未知错误')}"
                                logger.error(error_msg)
                                yield error_msg
                                full_response += error_msg

                        except json.JSONDecodeError:
                            logger.error(f"解析响应JSON失败: {event_data}")
                except ValueError:
                    # 处理不完整的事件
                    break
    except Exception as e:
        error_msg = f"处理流式响应出错: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        yield error_msg
        full_response += error_msg
    finally:
        # 确保流关闭
        try:
            if stream:
                stream.close()
        except:
            pass

    # 添加消息记录
    if full_response:
        add_message(session_id, user_id, full_response, is_user=0)

    # 返回完整响应和会话ID
    return full_response, conversation_id


# 工具函数
def format_data_for_ai(data):
    """将数据格式化为适合AI处理的文本格式"""
    if isinstance(data, str):
        return data
        
    if isinstance(data, dict):
        formatted = ""
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, indent=2)
            formatted += f"{key}: {value}\n"
        return formatted
    
    # 如果是列表或其他类型，直接转为字符串
    return json.dumps(data, ensure_ascii=False, indent=2)


def http_request_with_retry(req, context=None, max_retries=MAX_RETRIES,
                            initial_delay=INITIAL_RETRY_DELAY, backoff_factor=RETRY_BACKOFF_FACTOR,
                            timeout=None):
    """执行HTTP请求，使用指数级退避策略自动重试失败的请求"""
    retries = 0
    current_delay = initial_delay

    # 如果设置了timeout，需要使用socket.setdefaulttimeout
    old_timeout = None
    if timeout:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)

    try:
        while retries <= max_retries:
            try:
                if context:
                    with urllib.request.urlopen(req, context=context) as response:
                        return response.read()
                else:
                    with urllib.request.urlopen(req) as response:
                        return response.read()
            except (urllib.error.URLError, socket.timeout) as e:
                retries += 1

                # 记录错误信息
                error_msg = str(e)
                if isinstance(e, urllib.error.HTTPError) and hasattr(e, 'code'):
                    error_msg = f"HTTP Error {e.code}: {e.reason}"
                    # 尝试读取更详细的错误信息
                    if hasattr(e, 'read'):
                        try:
                            error_content = e.read().decode('utf-8')
                            logger.error(f"错误详情: {error_content}")
                        except:
                            pass
                elif isinstance(e, socket.timeout):
                    error_msg = "Connection timed out"

                # 检查是否继续重试
                if retries <= max_retries:
                    logger.warning(f"请求失败: {error_msg}，将在{current_delay:.1f}秒后重试 ({retries}/{max_retries})")
                    time.sleep(current_delay)
                    current_delay *= backoff_factor  # 指数级增加延迟
                else:
                    logger.error(f"请求失败，已达最大重试次数: {error_msg}")
                    raise e
    finally:
        # 恢复原来的超时设置
        if timeout and old_timeout is not None:
            socket.setdefaulttimeout(old_timeout)

    return None


# 判断文本是否为Markdown格式
def is_markdown(text):
    """简单判断文本是否包含Markdown格式"""
    # 匹配常见的Markdown格式，如标题、列表、链接、粗体、代码块等
    markdown_patterns = [
        r'#{1,6}\s+\S+',  # 标题
        r'\*\*.*?\*\*',  # 粗体
        r'\*.*?\*',  # 斜体
        r'`.*?`',  # 行内代码
        r'```[\s\S]*?```',  # 代码块
        r'!$$.*?$$$$.*?$$',  # 图片
        r'$$.*?$$$$.*?$$',  # 链接
        r'^\s*[*+-]\s+',  # 无序列表
        r'^\s*\d+\.\s+',  # 有序列表
        r'^\s*>\s+',  # 引用
        r'^-{3,}$',  # 水平线
    ]

    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE):
            return True

    return False


def is_command(text):
    """检查文本是否是命令"""
    return text.startswith("\\") or text.startswith("/")


def parse_command(text):
    """解析命令和参数"""
    if not is_command(text):
        return None, None

    # 移除前导反斜杠
    cmd_text = text[1:].strip()

    # 分割命令和参数
    parts = cmd_text.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    return cmd, args


# 添加更新命令的查询功能
def is_user_command(cmd):
    """检查是否是普通用户可用的命令"""
    user_commands = [
        "help", "model-list", "model-info", "command-list", "change-model", 
        "clear", "session-info", "subscribe-event", "unsubscribe-event", "list-subscriptions",
        "webhook-list"  # 添加webhook-list为用户命令
    ]
    return cmd in user_commands


def is_admin_command(cmd):
    """检查是否是管理员命令"""
    admin_commands = [
        "admin-login", "admin-logout", "admin-add", "admin-remove",
        "model-add", "model-delete", "model-update", "set-default-model", "set-session-timeout",
        "command-add", "command-delete", "command-update",
        "webhook-add", "webhook-delete", "webhook-status"  # 添加webhook相关管理命令
    ]
    # 检查命令或命令前缀是否在管理员命令列表中
    return cmd in admin_commands or any(cmd.startswith(prefix) for prefix in ["admin-", "model-", "command-", "webhook-", "set-"])


def handle_subscribe_event(args, sender_id, sender_type, chat_id, reply_func):
    """处理订阅事件命令"""
    config_token = args.strip()
    if not config_token:
        reply_func("请提供有效的配置令牌，例如：`\\subscribe-event abc123`")
        return
    
    # 通过配置token查找webhook
    webhook = get_webhook(config_token=config_token)
    if not webhook:
        reply_func(f"未找到配置令牌为 '{config_token}' 的webhook事件")
        return
    
    # 确定订阅目标
    if sender_type == "group":
        target_type = "chat"
        target_id = chat_id
        target_desc = "当前群组"
    else:
        target_type = "user"
        target_id = sender_id
        target_desc = "您"
    
    # 添加订阅
    success, result = add_webhook_subscription(webhook['id'], target_type, target_id, sender_id)
    if success:
        reply_func(f"{target_desc}已成功订阅「{webhook['name']}」事件通知")
    else:
        reply_func(f"订阅失败: {result}")


def handle_unsubscribe_event(args, sender_id, sender_type, chat_id, reply_func):
    """处理取消订阅事件命令"""
    config_token = args.strip()
    if not config_token:
        reply_func("请提供有效的配置令牌，例如：`\\unsubscribe-event abc123`")
        return
    
    # 通过配置token查找webhook
    webhook = get_webhook(config_token=config_token)
    if not webhook:
        reply_func(f"未找到配置令牌为 '{config_token}' 的webhook事件")
        return
    
    # 确定订阅目标
    if sender_type == "group":
        target_type = "chat"
        target_id = chat_id
        target_desc = "当前群组"
    else:
        target_type = "user"
        target_id = sender_id
        target_desc = "您"
    
    # 取消订阅
    if remove_webhook_subscription(webhook['id'], target_type, target_id):
        reply_func(f"{target_desc}已成功取消订阅「{webhook['name']}」事件通知")
    else:
        reply_func(f"{target_desc}未订阅「{webhook['name']}」事件通知")


def handle_list_subscriptions(sender_id, reply_func):
    """列出用户的所有订阅"""
    subscriptions = get_user_subscriptions(sender_id)
    
    if not subscriptions:
        reply_func("您当前没有任何事件订阅")
        return
    
    reply_text = "## 您的事件订阅\n\n"
    
    # 按webhook分组显示
    webhook_groups = {}
    for sub in subscriptions:
        webhook_id = sub['webhook_id']
        if webhook_id not in webhook_groups:
            webhook_groups[webhook_id] = {
                'name': sub['webhook_name'],
                'description': sub['webhook_description'],
                'subscriptions': []
            }
        webhook_groups[webhook_id]['subscriptions'].append(sub)
    
    for webhook_id, group in webhook_groups.items():
        reply_text += f"### {group['name']}\n"
        if group['description']:
            reply_text += f"{group['description']}\n"
        
        for sub in group['subscriptions']:
            if sub['target_type'] == 'user':
                target_desc = "个人"
            else:
                target_desc = "群组"
            reply_text += f"- {target_desc} (创建于 {sub['created_at']})\n"
    
    reply_func(reply_text)


# 添加处理webhook-list命令的函数
def handle_webhook_list(reply_func):
    """列出所有可用的webhook"""
    webhooks = get_all_webhooks()
    
    if not webhooks:
        reply_func("系统中没有配置任何webhook")
        return
    
    reply_text = "## 可用的Webhook事件\n\n"
    for webhook in webhooks:
        status = "启用" if webhook['is_active'] == 1 else "禁用"
        reply_text += f"### {webhook['name']} ({status})\n"
        if webhook['description']:
            reply_text += f"{webhook['description']}\n"
        reply_text += f"- 订阅令牌: `{webhook['config_token']}`\n"
        reply_text += f"- 订阅命令: `\\subscribe-event {webhook['config_token']}`\n\n"
    
    reply_func(reply_text)


# 添加处理管理员webhook命令的函数
def handle_webhook_add(args, reply_func):
    """添加webhook (管理员命令)"""
    # 解析参数：名称 描述 模型名称
    parts = args.split(' ', 2)
    if len(parts) < 3:
        reply_func("参数不足，格式应为: `\\webhook-add [名称] [描述] [模型名称]`")
        return
    
    name, description, model_name = parts
    
    # 查找模型
    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型")
        return
    
    # 创建webhook
    webhook_id, api_token, config_token = create_webhook(name, description, model['id'])
    
    if webhook_id:
        reply_text = f"## Webhook已创建\n\n"
        reply_text += f"- 名称: {name}\n"
        reply_text += f"- 描述: {description}\n"
        reply_text += f"- 配置令牌: `{config_token}`\n"
        reply_text += f"- 订阅命令: `\\subscribe-event {config_token}`\n\n"
        
        # 安全原因不在聊天中显示完整API令牌
        api_token_masked = f"{api_token[:5]}...{api_token[-5:]}"
        reply_text += f"API令牌已生成 ({api_token_masked})，请通过管理界面查看完整令牌。"
        
        reply_func(reply_text)
    else:
        reply_func("创建webhook失败")


def handle_webhook_delete(args, reply_func):
    """删除webhook (管理员命令)"""
    webhook_id = args.strip()
    
    try:
        webhook_id = int(webhook_id)
    except ValueError:
        reply_func("请提供有效的webhook ID，例如: `\\webhook-delete 1`")
        return
    
    # 查找webhook
    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        reply_func(f"未找到ID为 {webhook_id} 的webhook")
        return
    
    # 删除webhook
    if delete_webhook(webhook_id):
        reply_func(f"已成功删除webhook: {webhook['name']}")
    else:
        reply_func(f"删除webhook失败")


def handle_webhook_status(args, reply_func):
    """修改webhook状态 (管理员命令)"""
    # 解析参数：ID 状态(启用/禁用)
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        reply_func("参数不足，格式应为: `\\webhook-status [ID] [启用/禁用]`")
        return
    
    try:
        webhook_id = int(parts[0])
    except ValueError:
        reply_func("请提供有效的webhook ID")
        return
    
    status_text = parts[1].strip()
    if status_text == "启用":
        new_status = 1
    elif status_text == "禁用":
        new_status = 0
    else:
        reply_func("状态参数无效，应为`启用`或`禁用`")
        return
    
    # 查找webhook
    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        reply_func(f"未找到ID为 {webhook_id} 的webhook")
        return
    
    # 更新状态
    if update_webhook(webhook_id, is_active=new_status):
        status_str = "启用" if new_status == 1 else "禁用"
        reply_func(f"已将webhook「{webhook['name']}」状态设置为: {status_str}")
    else:
        reply_func("更新webhook状态失败")


def is_bot_mentioned(mentions):
    """检查消息中是否@了机器人"""
    if not mentions:
        return False

    for mention in mentions:
        # 通过名称或ID匹配
        mention_name = mention.get("name", "")
        mention_id = mention.get("id", {}).get("open_id", "")

        # 检查是否匹配机器人名称或ID
        if (BOT_NAME and BOT_NAME in mention_name) or (BOT_OPEN_ID and BOT_OPEN_ID == mention_id):
            return True

    return False


def remove_mentions(text, mentions):
    """从文本中删除@部分"""
    if not mentions:
        return text

    for mention in mentions:
        mention_name = mention.get("name", "")
        if mention_name:
            # 删除@用户名
            text = text.replace(f"@{mention_name}", "").strip()

    return text


# 处理系统命令
def handle_command(cmd, args, sender_id, sender_type="user", chat_id=None, reply_func=None):
    """处理系统命令"""
    is_admin = check_admin(sender_id)

    # 特殊命令：init-admin（初始管理员设置）
    if cmd == "init-admin":
        handle_init_admin(sender_id, reply_func)
        return True

    # 检查命令权限
    if is_admin_command(cmd) and not is_admin:
        reply_func("抱歉，该命令只能由管理员使用。")
        return True

    # 通用命令处理
    if cmd == "help":
        show_help(is_admin, reply_func)
        return True

    # 用户命令
    if cmd == "model-list":
        handle_model_list(reply_func)
        return True
    elif cmd == "model-info":
        handle_model_info(args, reply_func)
        return True
    elif cmd == "command-list":
        handle_command_list(reply_func)
        return True
    elif cmd == "change-model":
        handle_change_model(args, sender_id, reply_func)
        return True
    elif cmd == "clear":
        handle_clear_session(sender_id, reply_func)
        return True
    elif cmd == "session-info":
        handle_session_info(sender_id, reply_func)
        return True
    elif cmd == "subscribe-event":
        handle_subscribe_event(args, sender_id, sender_type, chat_id, reply_func)
        return True
    elif cmd == "unsubscribe-event":
        handle_unsubscribe_event(args, sender_id, sender_type, chat_id, reply_func)
        return True
    elif cmd == "list-subscriptions":
        handle_list_subscriptions(sender_id, reply_func)
        return True
    elif cmd == "webhook-list":  # 添加webhook-list命令处理
        handle_webhook_list(reply_func)
        return True

    # 管理员命令
    if is_admin:
        if cmd == "admin-login":
            handle_admin_login(sender_id, reply_func)
            return True
        elif cmd == "admin-logout":
            handle_admin_logout(sender_id, reply_func)
            return True
        elif cmd == "admin-add":
            handle_admin_add(args, reply_func)
            return True
        elif cmd == "admin-remove":
            handle_admin_remove(args, reply_func)
            return True
        elif cmd == "model-add":
            handle_model_add(args, reply_func)
            return True
        elif cmd == "model-delete":
            handle_model_delete(args, reply_func)
            return True
        elif cmd == "model-update":
            handle_model_update(args, reply_func)
            return True
        elif cmd == "set-default-model":
            handle_set_default_model(args, reply_func)
            return True
        elif cmd == "set-session-timeout":
            handle_set_session_timeout(args, reply_func)
            return True
        elif cmd == "command-add":
            handle_command_add(args, reply_func)
            return True
        elif cmd == "command-delete":
            handle_command_delete(args, reply_func)
            return True
        elif cmd == "command-update":
            handle_command_update(args, reply_func)
            return True
        elif cmd == "webhook-add":  # 添加webhook管理命令处理
            handle_webhook_add(args, reply_func)
            return True
        elif cmd == "webhook-delete":
            handle_webhook_delete(args, reply_func)
            return True
        elif cmd == "webhook-status":
            handle_webhook_status(args, reply_func)
            return True

    # 自定义命令处理 - 这里是API调用的部分
    command = get_command(trigger=f"\\{cmd}")
    if command:
        handle_custom_command(command, args, sender_id, reply_func)
        return True

    # 未知命令
    reply_func(f"未知命令: `\\{cmd}`\n使用 `\\help` 查看可用命令。")
    return True


# 添加init-admin命令的处理函数
def handle_init_admin(user_id, reply_func):
    """处理初始管理员设置命令"""
    # 检查是否已有管理员
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_admin = 1")
    result = cursor.fetchone()
    conn.close()

    if result and result['count'] > 0:
        reply_func("初始化管理员失败：系统中已存在管理员账号，该命令已失效。")
        return

    # 将当前用户设置为管理员
    user = get_user(user_id)
    if user:
        # 更新用户为管理员
        set_user_admin(user_id, 1)
    else:
        # 创建新用户并设置为管理员
        add_user(user_id, "", 1)

    reply_func("恭喜！您已成功设置为系统管理员。\n\n您现在可以使用所有管理员命令，例如 `\\admin-login` 来访问管理界面。")


def show_help(is_admin, reply_func):
    """显示帮助信息"""
    help_text = "## 可用命令列表\n\n"

    # 通用命令
    help_text += "### 通用命令\n"
    help_text += "- `\\help` - 显示此帮助信息\n"
    help_text += "- `\\model-list` - 列出所有可用模型\n"
    help_text += "- `\\model-info [模型名称]` - 查看指定模型详情\n"
    help_text += "- `\\command-list` - 列出所有可用自定义命令\n"
    help_text += "- `\\change-model [模型名称]` - 切换当前对话使用的模型\n"
    help_text += "- `\\clear` - 清除当前会话历史\n"
    help_text += "- `\\session-info` - 查看当前会话状态\n"
    help_text += "- `\\webhook-list` - 查看所有可订阅的webhook\n" 
    help_text += "- `\\subscribe-event [配置令牌]` - 订阅事件通知\n"
    help_text += "- `\\unsubscribe-event [配置令牌]` - 取消订阅事件通知\n"
    help_text += "- `\\list-subscriptions` - 查看您的所有订阅\n"

    # 自定义命令
    commands = get_all_commands()
    if commands:
        help_text += "\n### 自定义命令\n"
        for cmd in commands:
            help_text += f"- `{cmd['trigger']}` - {cmd['description']}\n"

    # 管理员命令
    if is_admin:
        help_text += "\n### 管理员命令\n"
        help_text += "- `\\admin-login` - 管理员登录\n"
        help_text += "- `\\admin-logout` - 管理员退出\n"
        help_text += "- `\\admin-add [用户ID]` - 添加管理员权限\n"
        help_text += "- `\\admin-remove [用户ID]` - 移除管理员权限\n"
        help_text += "- `\\model-add [名称] [描述] [Dify地址] [类型] [密钥]` - 添加模型\n"
        help_text += "- `\\model-delete [名称]` - 删除模型\n"
        help_text += "- `\\model-update [名称] [参数] [新值]` - 更新模型参数\n"
        help_text += "- `\\set-default-model [名称]` - 设置默认模型\n"
        help_text += "- `\\set-session-timeout [分钟]` - 设置会话超时时间\n"
        help_text += "- `\\command-add [名称] [简介] [启动指令] [模型]` - 添加命令\n"
        help_text += "- `\\command-delete [名称]` - 删除命令\n"
        help_text += "- `\\command-update [名称] [参数] [新值]` - 更新命令\n"
        help_text += "- `\\webhook-add [名称] [描述] [模型]` - 添加webhook\n"
        help_text += "- `\\webhook-delete [ID]` - 删除webhook\n"
        help_text += "- `\\webhook-status [ID] [启用/禁用]` - 修改webhook状态\n"

    reply_func(help_text)


def handle_model_list(reply_func):
    """列出所有模型"""
    models = get_all_models()
    if not models:
        reply_func("当前没有配置任何模型。")
        return

    # 获取默认模型
    default_model = get_default_model()
    default_model_id = default_model['id'] if default_model else None

    reply_text = "## 可用模型列表\n\n"
    for model in models:
        is_default = "(默认)" if model['id'] == default_model_id else ""
        reply_text += f"- **{model['name']}** {is_default} - {model['description']}\n"

    reply_text += "\n使用 `\\model-info [模型名称]` 查看详细信息"
    reply_func(reply_text)


def handle_model_info(args, reply_func):
    """查看模型详情"""
    model_name = args.strip()
    if not model_name:
        reply_func("请指定模型名称，例如：`\\model-info GPT-4`")
        return

    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    reply_text = f"## 模型：{model['name']}\n\n"
    reply_text += f"- **描述**：{model['description']}\n"
    reply_text += f"- **类型**：{model['dify_type']}\n"
    reply_text += f"- **API地址**：{model['dify_url']}\n"

    reply_func(reply_text)


def handle_command_list(reply_func):
    """列出所有命令"""
    commands = get_all_commands()
    if not commands:
        reply_func("当前没有配置任何自定义命令。")
        return

    reply_text = "## 可用自定义命令列表\n\n"
    for cmd in commands:
        reply_text += f"- **{cmd['trigger']}** - {cmd['description']} (使用模型: {cmd['model_name']})\n"

    reply_func(reply_text)


def handle_change_model(args, user_id, reply_func):
    """切换当前对话模型"""
    model_name = args.strip()
    if not model_name:
        reply_func("请指定模型名称，例如：`\\change-model GPT-4`")
        return

    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    # 获取或创建用户会话
    session_id, _ = get_or_create_session(user_id, model['id'])

    reply_func(f"已将当前会话模型切换为：{model['name']}。\n\n您可以开始提问了！")


# 给用户添加清除会话的功能
def handle_clear_session(user_id, reply_func):
    """清除当前会话"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 将用户所有活动会话标记为非活动
    cursor.execute(
        "UPDATE sessions SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    conn.commit()
    affected = conn.total_changes
    conn.close()

    # 创建新的默认会话
    get_or_create_session(user_id)

    if affected > 0:
        reply_func("会话历史已清除，我们可以开始新的对话了！")
    else:
        reply_func("没有找到活动的会话，开始新的对话吧！")


def handle_admin_login(user_id, reply_func):
    """管理员登录"""
    # 生成管理员token，并发送携带token的Web界面链接
    token = create_admin_token(user_id)
    admin_url = f"{request.urlparts.scheme}://{request.urlparts.netloc}/admin?token={token}"

    reply_text = f"管理员登录成功，请点击以下链接进入管理界面：\n\n{admin_url}\n\n该链接有效期为{ADMIN_TOKEN_EXPIRE_MINUTES}分钟，请勿泄露。"
    reply_func(reply_text)


def handle_admin_logout(user_id, reply_func):
    """管理员退出"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()

    if affected > 0:
        reply_func("管理员已退出，所有管理会话已失效。")
    else:
        reply_func("当前没有有效的管理会话。")


def handle_admin_add(args, reply_func):
    """添加管理员"""
    user_id = args.strip()
    if not user_id:
        reply_func("请指定用户ID，例如：`\\admin-add ou_xxxx`")
        return

    # 检查用户是否存在
    user = get_user(user_id)
    if not user:
        # 新用户，直接添加
        add_user(user_id, "", 1)
        reply_func(f"已添加新用户 '{user_id}' 并授予管理员权限。")
        return

    # 更新现有用户
    if set_user_admin(user_id, 1):
        reply_func(f"已为用户 '{user_id}' 授予管理员权限。")
    else:
        reply_func(f"用户 '{user_id}' 已经是管理员。")


def handle_admin_remove(args, reply_func):
    """移除管理员"""
    user_id = args.strip()
    if not user_id:
        reply_func("请指定用户ID，例如：`\\admin-remove ou_xxxx`")
        return

    # 检查用户是否存在
    user = get_user(user_id)
    if not user:
        reply_func(f"用户 '{user_id}' 不存在。")
        return

    # 更新用户权限
    if set_user_admin(user_id, 0):
        # 使该用户的所有token失效
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        reply_func(f"已移除用户 '{user_id}' 的管理员权限。")
    else:
        reply_func(f"用户 '{user_id}' 不是管理员。")


def handle_model_add(args, reply_func):
    """添加模型"""
    # 解析参数：名称 描述 Dify地址 类型 密钥
    parts = args.split(' ', 4)
    if len(parts) < 5:
        reply_func("参数不足，格式应为：`\\model-add [名称] [描述] [Dify地址] [类型] [密钥]`")
        return

    name, description, dify_url, dify_type, api_key = parts

    # 检查名称是否已存在
    if get_model(model_name=name):
        reply_func(f"名为 '{name}' 的模型已存在。")
        return

    # 验证类型
    valid_types = ["chatbot", "agent", "flow"]
    if dify_type not in valid_types:
        reply_func(f"无效的模型类型，类型应为以下之一：{', '.join(valid_types)}")
        return

    # 添加模型
    model_id = add_model(name, description, dify_url, dify_type, api_key)
    if model_id:
        reply_func(f"成功添加模型：{name}")
    else:
        reply_func("添加模型失败。")


def handle_model_delete(args, reply_func):
    """删除模型"""
    model_name = args.strip()
    if not model_name:
        reply_func("请指定模型名称，例如：`\\model-delete GPT-4`")
        return

    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    # 删除模型
    success, message = delete_model(model['id'])
    if success:
        reply_func(f"已删除模型：{model_name}")
    else:
        reply_func(f"删除模型失败：{message}")


def handle_model_update(args, reply_func):
    """更新模型参数"""
    # 解析参数：模型名称 参数名 新值
    parts = args.split(' ', 2)
    if len(parts) < 3:
        reply_func("参数不足，格式应为：`\\model-update [模型名称] [参数名] [新值]`")
        return

    model_name, param_name, new_value = parts

    # 获取模型
    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    # 更新对应参数
    valid_params = ["name", "description", "dify_url", "dify_type", "api_key"]
    if param_name not in valid_params:
        reply_func(f"无效的参数名，参数应为以下之一：{', '.join(valid_params)}")
        return

    # 如果更新名称，检查新名称是否已存在
    if param_name == "name" and new_value != model_name:
        if get_model(model_name=new_value):
            reply_func(f"名为 '{new_value}' 的模型已存在。")
            return

    # 如果更新类型，验证类型
    if param_name == "dify_type":
        valid_types = ["chatbot", "agent", "flow"]
        if new_value not in valid_types:
            reply_func(f"无效的模型类型，类型应为以下之一：{', '.join(valid_types)}")
            return

    # 构建更新参数
    update_params = {param_name: new_value}

    # 执行更新
    if update_model(model['id'], **update_params):
        reply_func(f"已更新模型 '{model_name}' 的 {param_name} 为 '{new_value}'。")
    else:
        reply_func(f"更新模型失败。")


def handle_set_default_model(args, reply_func):
    """设置默认模型"""
    model_name = args.strip()
    if not model_name:
        reply_func("请指定模型名称，例如：`\\set-default-model GPT-4`")
        return

    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    # 设置默认模型
    if set_config("default_model", str(model['id'])):
        reply_func(f"已将默认模型设置为：{model_name}")
    else:
        reply_func("设置默认模型失败。")


def handle_command_add(args, reply_func):
    """添加命令"""
    # 解析参数：名称 简介 启动指令 模型
    parts = args.split(' ', 3)
    if len(parts) < 4:
        reply_func("参数不足，格式应为：`\\command-add [名称] [简介] [启动指令] [模型]`")
        return

    name, description, trigger, model_name = parts

    # 检查触发指令是否已存在
    if get_command(trigger=trigger):
        reply_func(f"触发指令 '{trigger}' 已存在。")
        return

    # 检查模型是否存在
    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    # 添加命令
    success, result = add_command(name, description, trigger, model['id'])
    if success:
        reply_func(f"成功添加命令：{name}，触发指令：{trigger}")
    else:
        reply_func(f"添加命令失败：{result}")


def handle_command_delete(args, reply_func):
    """删除命令"""
    command_name = args.strip()
    if not command_name:
        reply_func("请指定命令名称，例如：`\\command-delete 翻译`")
        return

    # 获取命令信息（按名称）
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM commands WHERE name = ?", (command_name,))
    command = cursor.fetchone()
    conn.close()

    if not command:
        reply_func(f"未找到名为 '{command_name}' 的命令。")
        return

    # 删除命令
    if delete_command(command['id']):
        reply_func(f"已删除命令：{command_name}")
    else:
        reply_func("删除命令失败。")


def handle_command_update(args, reply_func):
    """更新命令参数"""
    # 解析参数：命令名称 参数名 新值
    parts = args.split(' ', 2)
    if len(parts) < 3:
        reply_func("参数不足，格式应为：`\\command-update [命令名称] [参数名] [新值]`")
        return

    command_name, param_name, new_value = parts

    # 获取命令信息（按名称）
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM commands WHERE name = ?", (command_name,))
    command = cursor.fetchone()
    conn.close()

    if not command:
        reply_func(f"未找到名为 '{command_name}' 的命令。")
        return

    # 更新对应参数
    valid_params = ["name", "description", "trigger", "model_id"]
    if param_name not in valid_params:
        reply_func(f"无效的参数名，参数应为以下之一：{', '.join(valid_params)}")
        return

    # 特殊处理模型ID
    if param_name == "model_id":
        # 需要将模型名称转换为ID
        model = get_model(model_name=new_value)
        if not model:
            reply_func(f"未找到名为 '{new_value}' 的模型。")
            return
        new_value = model['id']

    # 构建更新参数
    update_params = {param_name: new_value}

    # 执行更新
    success, message = update_command(command['id'], **update_params)
    if success:
        reply_func(f"已更新命令 '{command_name}' 的 {param_name} 为 '{new_value}'。")
    else:
        reply_func(f"更新命令失败：{message}")


# 添加会话超时设置功能
def handle_set_session_timeout(args, reply_func):
    """设置会话超时时间"""
    try:
        timeout = int(args.strip())
        if timeout < 1:
            reply_func("超时时间必须大于0分钟")
            return

        set_config("session_timeout", str(timeout))
        reply_func(f"会话超时时间已设置为 {timeout} 分钟")
    except ValueError:
        reply_func("请输入有效的分钟数，例如：`\\set-session-timeout 30`")


# 添加查看当前会话状态功能
def handle_session_info(user_id, reply_func):
    """查看当前会话状态"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.*, m.name as model_name, c.name as command_name
        FROM sessions s
        LEFT JOIN models m ON s.model_id = m.id
        LEFT JOIN commands c ON s.command_id = c.id
        WHERE s.user_id = ? AND s.is_active = 1
        ORDER BY s.last_active_at DESC
    """, (user_id,))

    sessions = cursor.fetchall()
    conn.close()

    if not sessions:
        reply_func("您当前没有活动的会话")
        return

    timeout_minutes = int(get_config("session_timeout") or "30")

    reply_text = "## 当前活动会话\n\n"
    for session in sessions:
        last_active = datetime.strptime(session['last_active_at'], "%Y-%m-%d %H:%M:%S")
        time_diff = datetime.now() - last_active
        minutes_left = max(0, timeout_minutes - int(time_diff.total_seconds() / 60))

        reply_text += f"- **会话ID**: {session['id']}\n"
        reply_text += f"  - 模型: {session['model_name'] or '未指定'}\n"
        if session['command_name']:
            reply_text += f"  - 命令: {session['command_name']}\n"
        reply_text += f"  - 会话ID: {session['conversation_id'] or '新会话'}\n"
        reply_text += f"  - 最后活动: {session['last_active_at']}\n"
        reply_text += f"  - 剩余时间: {minutes_left} 分钟\n\n"

    reply_func(reply_text)


def handle_custom_command(command, args, user_id, reply_func):
    """处理自定义命令"""
    model_id = command['model_id']
    if not model_id:
        reply_func(f"该命令未关联任何模型，无法执行。")
        return

    # 获取模型信息
    model = get_model(model_id=model_id)
    if not model:
        reply_func(f"命令关联的模型不存在，无法执行。")
        return

    # 构建查询
    query = f"{command['name']}：{args}" if args else command['name']

    # 获取或创建专用于此命令的会话
    session_id, conversation_id = get_or_create_session(user_id, model_id, command['id'])

    # 添加用户消息记录
    add_message(session_id, user_id, query, is_user=1)

    # 根据模型类型选择对应的处理函数
    reply_func(f"正在处理命令：{command['name']}...")

    try:
        stream = None
        if model['dify_type'] == 'chatbot':
            stream = ask_dify_chatbot(model, query, conversation_id, user_id)
        elif model['dify_type'] == 'agent':
            stream = ask_dify_agent(model, query, conversation_id, user_id)
        elif model['dify_type'] == 'flow':
            stream = ask_dify_flow(model, query, conversation_id, user_id)
        else:
            reply_func(f"不支持的模型类型：{model['dify_type']}")
            return

        # 检查stream是否为None
        if stream is None:
            reply_func("无法连接到Dify API，请检查API地址和密钥是否正确，或者网络连接是否正常。")
            return

        # 处理流式响应
        full_response = ""
        for chunk in process_dify_stream(stream, session_id, user_id):
            full_response += chunk

        reply_func(full_response)
    except Exception as e:
        logger.error(f"处理命令出错: {str(e)}")
        logger.error(traceback.format_exc())
        reply_func(f"处理命令时出错: {str(e)}")


# 更新主消息处理函数，确保使用正确的会话
def process_message(sender_id, content, reply_func):
    """处理用户消息的核心函数"""
    # 检查是否为命令
    if is_command(content):
        cmd, args = parse_command(content)
        if cmd:
            # 命令处理完全由handle_command函数处理，不会走到后面的API调用
            return handle_command(cmd, args, sender_id, reply_func=reply_func)

    # 到这里说明是普通消息，需要API调用
    # 获取用户会话（不指定命令ID，只指定模型ID或使用默认模型）
    session_id, conversation_id = get_or_create_session(sender_id)
    model = get_session_model(session_id)

    if not model:
        reply_func(
            "当前没有设置默认模型，请先使用 `\\change-model [模型名称]` 命令选择一个模型，或者联系管理员设置默认模型。")
        return True

    # 添加用户消息记录
    add_message(session_id, sender_id, content, is_user=1)

    # 发送消息到Dify
    reply_func("正在思考中，请稍候...")

    try:
        # 这部分是API调用
        if model['dify_type'] == 'chatbot':
            stream = ask_dify_chatbot(model, content, conversation_id, sender_id)
        elif model['dify_type'] == 'agent':
            stream = ask_dify_agent(model, content, conversation_id, sender_id)
        elif model['dify_type'] == 'flow':
            stream = ask_dify_flow(model, content, conversation_id, sender_id)
        else:
            reply_func(f"不支持的模型类型：{model['dify_type']}")
            return True

        # 检查stream是否为None
        if stream is None:
            reply_func("无法连接到Dify API，请检查API地址和密钥是否正确，或者网络连接是否正常。")
            return True

        # 处理流式响应
        full_response = ""
        for chunk in process_dify_stream(stream, session_id, sender_id):
            full_response += chunk

        reply_func(full_response)
        return True
    except Exception as e:
        logger.error(f"处理消息出错: {str(e)}")
        logger.error(traceback.format_exc())
        reply_func(f"处理消息时出错: {str(e)}")
        return False


# 飞书事件处理
@app.post('/webhook/event')
def event_handler():
    """处理飞书事件"""
    try:
        # 获取请求体
        body = request.body.read().decode('utf-8')
        logger.info(f"收到请求: {body}")

        # 解析JSON
        event_data = json.loads(body)

        # URL验证处理
        if event_data.get("type") == "url_verification":
            challenge = event_data.get("challenge")
            token = event_data.get("token")

            logger.info(f"处理URL验证请求: challenge={challenge}, token={token}")

            # 验证token
            if token != VERIFICATION_TOKEN:
                logger.warning(f"Token验证失败: {token}")
                return HTTPResponse(
                    status=401,
                    body=json.dumps({"error": "invalid token"}),
                    headers={'Content-Type': 'application/json'}
                )

            # 返回验证响应
            return HTTPResponse(
                status=200,
                body=json.dumps({"challenge": challenge}),
                headers={'Content-Type': 'application/json'}
            )

        # 验证Token (对于非验证请求)
        if "header" in event_data:  # v2.0 事件
            token = event_data.get("header", {}).get("token")
        else:  # v1.0 事件
            token = event_data.get("token")

        if token != VERIFICATION_TOKEN:
            logger.warning(f"Token验证失败: {token}")
            return HTTPResponse(
                status=401,
                body=json.dumps({"error": "invalid token"}),
                headers={'Content-Type': 'application/json'}
            )

        # 加锁处理事件，防止并发处理相同事件
        with processing_lock:
            # 处理不同版本的事件
            if "schema" in event_data and event_data.get("schema") == "2.0":
                # 处理 v2.0 事件
                handle_v2_event(event_data)
            else:
                # 处理 v1.0 事件
                handle_v1_event(event_data)

        # 立即返回成功响应，后续处理异步进行
        return HTTPResponse(
            status=200,
            body=json.dumps({"code": 0, "msg": "success"}),
            headers={'Content-Type': 'application/json'}
        )

    except Exception as e:
        logger.error(f"处理事件出错: {str(e)}")
        logger.error(traceback.format_exc())
        return HTTPResponse(
            status=500,
            body=json.dumps({"error": str(e)}),
            headers={'Content-Type': 'application/json'}
        )


def handle_v2_event(event_data):
    """处理v2.0版本的事件"""
    header = event_data.get("header", {})
    event_type = header.get("event_type")
    event_id = header.get("event_id")

    # 事件去重检查
    if event_id in processed_events:
        logger.info(f"跳过重复事件: {event_id}")
        return True

    # 添加到已处理事件列表
    processed_events.append(event_id)

    # 处理消息事件
    if event_type == "im.message.receive_v1":
        event = event_data.get("event", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id")
        message = event.get("message", {})
        msg_type = message.get("message_type")
        chat_type = message.get("chat_type")
        content_json = json.loads(message.get("content", "{}"))
        text_content = content_json.get("text", "")
        chat_id = message.get("chat_id")

        logger.info(f"收到v2.0消息: 类型={msg_type}, 发送者={sender_id}, 聊天类型={chat_type}, 内容={text_content}")

        # 判断是否是群聊@消息
        is_mention = False
        mentions = message.get("mentions", [])

        if chat_type == "group" and mentions:
            # 检查是否@了机器人
            is_mention = is_bot_mentioned(mentions)
            if is_mention:
                # 去除@机器人部分的文本
                text_content = remove_mentions(text_content, mentions)
                logger.info(f"机器人被@，处理请求: {text_content}")

        # 确定回复方式：私聊用open_id，群聊@用chat_id
        reply_id = chat_id if is_mention and chat_type == "group" else sender_id
        reply_type = "chat_id" if is_mention and chat_type == "group" else "open_id"
        
        # 处理消息所处的环境类型
        sender_type = "group" if chat_type == "group" else "user"

        # 仅处理私聊消息或群聊中@机器人的消息
        if chat_type != "group" or (chat_type == "group" and is_mention):
            # 检查用户是否存在，不存在则添加
            user = get_user(sender_id)
            if not user:
                add_user(sender_id)

            # 定义回复函数
            def reply(content):
                if reply_type == "open_id":
                    send_message(open_id=reply_id, content=content)
                else:
                    send_message(chat_id=reply_id, content=content)

            # 处理消息
            if msg_type == "text":
                # 检查是否为命令
                if is_command(text_content):
                    cmd, args = parse_command(text_content)
                    if cmd:
                        # 处理命令，传递聊天类型和群ID
                        handle_command(cmd, args, sender_id, sender_type, chat_id, reply)
                    else:
                        # 未能解析出命令，按普通消息处理
                        process_message(sender_id, text_content, reply)
                else:
                    process_message(sender_id, text_content, reply)
            else:
                reply("目前只支持文本消息。")

    return True


def handle_v1_event(event_data):
    """处理v1.0版本的事件"""
    # 类似于v2.0的处理，但适应v1.0的结构
    if event_data.get("type") == "event_callback":
        event = event_data.get("event", {})
        event_type = event.get("type")

        # 事件去重检查
        event_id = event_data.get("uuid")
        if event_id in processed_events:
            logger.info(f"跳过重复事件: {event_id}")
            return True

        # 添加到已处理事件列表
        processed_events.append(event_id)

        # 处理消息事件
        if event_type == "im.message.receive_v1" or event_type == "message":
            sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id")
            message = event.get("message", {})
            msg_type = message.get("message_type")
            chat_type = message.get("chat_type")
            content_json = json.loads(message.get("content", "{}"))
            text_content = content_json.get("text", "")
            chat_id = message.get("chat_id")

            logger.info(f"收到v1.0消息: 类型={msg_type}, 发送者={sender_id}, 聊天类型={chat_type}, 内容={text_content}")

            # 判断是否是群聊@消息
            is_mention = False
            mentions = message.get("mentions", [])

            if chat_type == "group" and mentions:
                # 检查是否@了机器人
                is_mention = is_bot_mentioned(mentions)
                if is_mention:
                    # 去除@机器人部分的文本
                    text_content = remove_mentions(text_content, mentions)
                    logger.info(f"机器人被@，处理请求: {text_content}")

            # 确定回复方式：私聊用open_id，群聊@用chat_id
            reply_id = chat_id if is_mention and chat_type == "group" else sender_id
            reply_type = "chat_id" if is_mention and chat_type == "group" else "open_id"
            
            # 处理消息所处的环境类型
            sender_type = "group" if chat_type == "group" else "user"

            # 仅处理私聊消息或群聊中@机器人的消息
            if chat_type != "group" or (chat_type == "group" and is_mention):
                # 检查用户是否存在，不存在则添加
                user = get_user(sender_id)
                if not user:
                    add_user(sender_id)

                # 定义回复函数
                def reply(content):
                    if reply_type == "open_id":
                        send_message(open_id=reply_id, content=content)
                    else:
                        send_message(chat_id=reply_id, content=content)

                # 处理消息
                if msg_type == "text":
                    # 检查是否为命令
                    if is_command(text_content):
                        cmd, args = parse_command(text_content)
                        if cmd:
                            # 处理命令，传递聊天类型和群ID
                            handle_command(cmd, args, sender_id, sender_type, chat_id, reply)
                        else:
                            # 未能解析出命令，按普通消息处理
                            process_message(sender_id, text_content, reply)
                    else:
                        process_message(sender_id, text_content, reply)
                else:
                    reply("目前只支持文本消息。")

    return True


@app.post('/api/webhook/<token>')
def webhook_endpoint(token):
    """外部系统通过webhook调用机器人"""
    try:
        # 验证token
        webhook = get_webhook(api_token=token)
        if not webhook:
            logger.warning(f"无效的webhook token: {token}")
            return HTTPResponse(
                status=401,
                body=json.dumps({"error": "无效的webhook token"}),
                headers={'Content-Type': 'application/json'}
            )
        
        # 获取请求数据
        try:
            # 尝试解析JSON
            body = request.body.read().decode('utf-8')
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                # 如果不是JSON，尝试解析表单数据
                data = parse_utf8(request)
                if not data:
                    # 如果仍然为空，直接使用原始数据
                    data = {"raw_content": body}
        except Exception as e:
            logger.error(f"解析webhook请求数据出错: {e}")
            data = {"error": "无法解析请求数据"}
        
        # 记录请求
        logger.info(f"接收到webhook调用: {webhook['name']}, 数据: {data}")
        
        # 获取模型信息
        model = {
            'id': webhook['model_id'],
            'name': webhook['model_name'],
            'dify_type': webhook['dify_type'],
            'dify_url': webhook['dify_url'],
            'api_key': webhook['api_key']
        }
        
        # 准备给AI的输入
        prompt_template = webhook['prompt_template']
        formatted_input = format_data_for_ai(data)
        
        if prompt_template:
            # 如果有自定义提示模板，使用模板格式化输入
            query = prompt_template.replace("{data}", formatted_input)
        else:
            # 否则使用默认格式
            query = f"分析以下数据:\n\n{formatted_input}"
        
        # 调用Dify API进行分析
        try:
            # 这里使用非流式响应
            if model['dify_type'] == 'chatbot':
                answer, _ = ask_dify_chatbot(model, query, None, "webhook", streaming=False)
            elif model['dify_type'] == 'agent':
                answer, _ = ask_dify_agent(model, query, None, "webhook", streaming=False)
            elif model['dify_type'] == 'flow':
                answer, _ = ask_dify_flow(model, query, None, "webhook", streaming=False)
            else:
                answer = f"不支持的模型类型: {model['dify_type']}"
                
            logger.info(f"AI分析结果: {answer}")
            
            # 获取所有订阅此webhook的目标
            subscriptions = get_webhook_subscriptions(webhook['id'])
            
            if not subscriptions:
                logger.warning(f"Webhook {webhook['name']} 没有订阅者，无法发送通知")
                
                # 记录调用日志
                log_webhook_call(webhook['id'], data, answer, 200)
                
                return HTTPResponse(
                    status=200,
                    body=json.dumps({
                        "success": True,
                        "message": "处理成功，但没有订阅者",
                        "answer": answer
                    }),
                    headers={'Content-Type': 'application/json'}
                )
            
            # 发送结果到所有订阅者
            sent_count = 0
            for sub in subscriptions:
                try:
                    if sub['target_type'] == "user":
                        # 发送给用户
                        response = send_message(open_id=sub['target_id'], content=answer)
                    else:
                        # 发送给群组
                        response = send_message(chat_id=sub['target_id'], content=answer)
                    
                    if response.get("code") == 0:
                        sent_count += 1
                except Exception as e:
                    logger.error(f"发送消息到 {sub['target_type']}:{sub['target_id']} 失败: {e}")
            
            # 记录调用日志
            log_webhook_call(webhook['id'], data, answer, 200)
            
            # 返回成功响应
            return HTTPResponse(
                status=200,
                body=json.dumps({
                    "success": True,
                    "message": f"处理成功，已发送给 {sent_count}/{len(subscriptions)} 个订阅者",
                    "answer": answer
                }),
                headers={'Content-Type': 'application/json'}
            )
            
        except Exception as e:
            # 记录错误日志
            error_msg = f"处理webhook调用出错: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            # 记录调用日志
            log_webhook_call(webhook['id'], data, error_msg, 500)
            
            # 返回错误响应
            return HTTPResponse(
                status=500,
                body=json.dumps({"error": error_msg}),
                headers={'Content-Type': 'application/json'}
            )
            
    except Exception as e:
        logger.error(f"Webhook处理全局错误: {str(e)}")
        logger.error(traceback.format_exc())
        return HTTPResponse(
            status=500,
            body=json.dumps({"error": str(e)}),
            headers={'Content-Type': 'application/json'}
        )


# Web管理界面
def require_admin(func):
    """验证管理员token的装饰器"""

    def wrapper(*args, **kwargs):
        token = request.query.get('token') or request.get_cookie('admin_token')

        if not token:
            return redirect('/admin/login')

        valid, user_id = validate_admin_token(token)
        if not valid:
            return redirect('/admin/login')

        # 设置cookie便于后续请求
        response.set_cookie('admin_token', token, path='/')

        # 将user_id传递给被装饰的函数
        kwargs['user_id'] = user_id
        return func(*args, **kwargs)

    return wrapper


@app.get('/admin')
def admin_redirect():
    """管理界面根路径，重定向到模型管理"""
    token = request.query.get('token')
    if token:
        # 验证token
        valid, _ = validate_admin_token(token)
        if valid:
            response.set_cookie('admin_token', token, path='/')
            return redirect('/admin/models')

    # 使用cookie中的token
    token = request.get_cookie('admin_token')
    if token:
        valid, _ = validate_admin_token(token)
        if valid:
            return redirect('/admin/models')

    return redirect('/admin/login')


@app.get('/admin/login')
def admin_login():
    """管理界面登录页面"""
    return """
    <html lang="zh-CN">
    <head>
        <title>管理员登录</title>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f5f5f5;
            }
            .login-box {
                background: white;
                padding: 40px;
                border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                text-align: center;
            }
            h1 {
                margin-bottom: 30px;
                color: #333;
            }
            p {
                color: #666;
                margin-bottom: 20px;
            }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>飞书Dify Bot管理界面</h1>
            <p>请通过飞书发送 <code>\\admin-login</code> 命令登录</p>
            <p>登录后，通过生成的链接访问此页面</p>
        </div>
    </body>
    </html>
    """


@app.get('/admin/logout')
def admin_logout():
    """管理员退出登录"""
    token = request.get_cookie('admin_token')
    if token:
        invalidate_admin_token(token)
        response.delete_cookie('admin_token')

    return redirect('/admin/login')


@app.get('/admin/models')
@require_admin
def admin_models(user_id):
    """模型管理页面"""
    models = get_all_models()
    return template('models', models=models)


@app.get('/admin/models/add')
@require_admin
def admin_models_add_form(user_id):
    """添加模型表单"""
    return template('model_form', model=None, title="添加模型", action="/admin/models/add")


@app.post('/admin/models/add')
@require_admin
def admin_models_add(user_id):
    """处理添加模型请求"""
    request_forms = parse_utf8(request)
    name = ensure_utf8(request_forms.get('name'))
    description = ensure_utf8(request_forms.get('description'))
    dify_url = ensure_utf8(request_forms.get('dify_url'))
    dify_type = ensure_utf8(request_forms.get('dify_type'))
    api_key = ensure_utf8(request_forms.get('api_key'))

    if not all([name, dify_url, dify_type, api_key]):
        return template('model_form', model=None, title="添加模型", action="/admin/models/add",
                        message="所有必填字段都必须填写", message_type="error")

    # 检查名称是否已存在
    if get_model(model_name=name):
        return template('model_form', model=None, title="添加模型", action="/admin/models/add",
                        message=f"名为 '{name}' 的模型已存在", message_type="error")

    # 添加模型
    model_id = add_model(name, description, dify_url, dify_type, api_key)
    if model_id:
        return redirect('/admin/models')
    else:
        return template('model_form', model=None, title="添加模型", action="/admin/models/add",
                        message="添加模型失败", message_type="error")


@app.get('/admin/models/edit/<model_id:int>')
@require_admin
def admin_models_edit_form(user_id, model_id):
    """编辑模型表单"""
    model = get_model(model_id=model_id)
    if not model:
        return redirect('/admin/models')

    return template('model_form', model=model, title="编辑模型", action=f"/admin/models/edit/{model_id}")


@app.post('/admin/models/edit/<model_id:int>')
@require_admin
def admin_models_edit(user_id, model_id):
    """处理编辑模型请求"""
    model = get_model(model_id=model_id)
    if not model:
        return redirect('/admin/models')

    request_forms = parse_utf8(request)
    name = ensure_utf8(request_forms.get('name'))
    description = ensure_utf8(request_forms.get('description'))
    dify_url = ensure_utf8(request_forms.get('dify_url'))
    dify_type = ensure_utf8(request_forms.get('dify_type'))
    api_key = ensure_utf8(request_forms.get('api_key'))

    if not all([name, dify_url, dify_type, api_key]):
        return template('model_form', model=model, title="编辑模型", action=f"/admin/models/edit/{model_id}",
                        message="所有必填字段都必须填写", message_type="error")

    # 检查名称是否已存在（且不是当前模型）
    if name != model['name'] and get_model(model_name=name):
        return template('model_form', model=model, title="编辑模型", action=f"/admin/models/edit/{model_id}",
                        message=f"名为 '{name}' 的模型已存在", message_type="error")

    # 更新模型
    if update_model(model_id, name, description, dify_url, dify_type, api_key):
        return redirect('/admin/models')
    else:
        return template('model_form', model=model, title="编辑模型", action=f"/admin/models/edit/{model_id}",
                        message="更新模型失败", message_type="error")


@app.get('/admin/models/delete/<model_id:int>')
@require_admin
def admin_models_delete(user_id, model_id):
    """删除模型"""
    success, message = delete_model(model_id)
    # 重定向回模型列表
    return redirect('/admin/models')


@app.get('/admin/commands')
@require_admin
def admin_commands(user_id):
    """命令管理页面"""
    commands = get_all_commands()
    return template('commands', commands=commands)


@app.get('/admin/commands/add')
@require_admin
def admin_commands_add_form(user_id):
    """添加命令表单"""
    models = get_all_models()
    return template('command_form', command=None, models=models, title="添加命令", action="/admin/commands/add")


@app.post('/admin/commands/add')
@require_admin
def admin_commands_add(user_id):
    """处理添加命令请求"""
    request_forms = parse_utf8(request)
    name = ensure_utf8(request_forms.get('name'))
    description = ensure_utf8(request_forms.get('description'))
    trigger = ensure_utf8(request_forms.get('trigger'))
    model_id = request_forms.get('model_id')

    if not all([name, description, trigger, model_id]):
        models = get_all_models()
        return template('command_form', command=None, models=models, title="添加命令", action="/admin/commands/add",
                        message="所有字段都必须填写", message_type="error")

    # 添加命令
    success, result = add_command(name, description, trigger, model_id)
    if success:
        return redirect('/admin/commands')
    else:
        models = get_all_models()
        return template('command_form', command=None, models=models, title="添加命令", action="/admin/commands/add",
                        message=result, message_type="error")


@app.get('/admin/commands/edit/<command_id:int>')
@require_admin
def admin_commands_edit_form(user_id, command_id):
    """编辑命令表单"""
    command = get_command(command_id=command_id)
    if not command:
        return redirect('/admin/commands')

    models = get_all_models()
    return template('command_form', command=command, models=models, title="编辑命令",
                    action=f"/admin/commands/edit/{command_id}")


@app.post('/admin/commands/edit/<command_id:int>')
@require_admin
def admin_commands_edit(user_id, command_id):
    """处理编辑命令请求"""
    command = get_command(command_id=command_id)
    if not command:
        return redirect('/admin/commands')

    request_forms = parse_utf8(request)
    name = ensure_utf8(request_forms.get('name'))
    description = ensure_utf8(request_forms.get('description'))
    trigger = ensure_utf8(request_forms.get('trigger'))
    model_id = request_forms.get('model_id')

    if not all([name, description, trigger, model_id]):
        models = get_all_models()
        return template('command_form', command=command, models=models, title="编辑命令",
                        action=f"/admin/commands/edit/{command_id}",
                        message="所有字段都必须填写", message_type="error")

    # 更新命令
    success, message = update_command(command_id, name, description, trigger, model_id)
    if success:
        return redirect('/admin/commands')
    else:
        models = get_all_models()
        return template('command_form', command=command, models=models, title="编辑命令",
                        action=f"/admin/commands/edit/{command_id}",
                        message=message, message_type="error")


@app.get('/admin/commands/delete/<command_id:int>')
@require_admin
def admin_commands_delete(user_id, command_id):
    """删除命令"""
    delete_command(command_id)
    # 重定向回命令列表
    return redirect('/admin/commands')


@app.get('/admin/config')
@require_admin
def admin_config(user_id):
    """系统配置页面"""
    configs = get_all_configs()
    models = get_all_models()

    # 获取默认模型
    default_model = None
    default_model_id = configs.get('default_model', {}).get('value')
    if default_model_id:
        default_model = get_model(model_id=default_model_id)

    return template('config', configs=configs, models=models, default_model=default_model)


@app.post('/admin/config/update')
@require_admin
def admin_config_update(user_id):
    """更新系统配置"""
    default_model_id = request.forms.get('default_model')
    session_timeout = request.forms.get('session_timeout')

    # 更新默认模型
    if default_model_id:
        set_config("default_model", default_model_id)

    # 更新会话超时
    if session_timeout:
        try:
            timeout = int(session_timeout)
            if timeout > 0:
                set_config("session_timeout", str(timeout))
        except ValueError:
            pass

    return redirect('/admin/config')


@app.get('/admin/users')
@require_admin
def admin_users(user_id):
    """用户管理页面"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY is_admin DESC, created_at DESC")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return template('users', users=users)


@app.get('/admin/users/toggle_admin/<user_id>')
@require_admin
def admin_toggle_admin(user_id, user_id_to_toggle):
    """切换用户管理员状态"""
    # 不能切换自己的管理员状态
    if user_id == user_id_to_toggle:
        return redirect('/admin/users')

    # 获取用户当前状态
    user = get_user(user_id_to_toggle)
    if user:
        # 切换状态
        new_status = 0 if user['is_admin'] == 1 else 1
        set_user_admin(user_id_to_toggle, new_status)

        # 如果取消管理员权限，使其所有token失效
        if new_status == 0:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE user_id = ?", (user_id_to_toggle,))
            conn.commit()
            conn.close()

    return redirect('/admin/users')


@app.get('/admin/logs')
@require_admin
def admin_logs(user_id):
    """日志查看页面"""
    # 读取最新的日志内容
    log_content = ""
    try:
        with open('lark_bot.log', 'r') as f:
            # 读取最后1000行
            lines = f.readlines()[-1000:]
            log_content = ''.join(lines)
    except Exception as e:
        log_content = f"读取日志文件出错: {str(e)}"

    return template('logs', log_content=log_content)


@app.get('/admin/webhooks')
@require_admin
def admin_webhooks(user_id):
    """Webhook管理页面"""
    webhooks = get_all_webhooks()
    return template('webhooks', webhooks=webhooks, get_webhook_subscriptions=get_webhook_subscriptions)


@app.get('/admin/webhooks/add')
@require_admin
def admin_webhooks_add_form(user_id):
    """添加Webhook表单"""
    models = get_all_models()
    return template('webhook_form', webhook=None, models=models, 
                   title="添加Webhook", action="/admin/webhooks/add")


@app.post('/admin/webhooks/add')
@require_admin
def admin_webhooks_add(user_id):
    """处理添加Webhook请求"""
    request_forms = parse_utf8(request)
    name = ensure_utf8(request_forms.get('name'))
    description = ensure_utf8(request_forms.get('description'))
    model_id = request_forms.get('model_id')
    prompt_template = ensure_utf8(request_forms.get('prompt_template'))
    
    if not all([name, model_id]):
        models = get_all_models()
        return template('webhook_form', webhook=None, models=models, 
                       title="添加Webhook", action="/admin/webhooks/add",
                       message="所有必填字段都必须填写", message_type="error")
                       
    # 创建webhook
    webhook_id, api_token, config_token = create_webhook(name, description, model_id, prompt_template)
    if webhook_id:
        # 显示确认页面，包含webhook URL和token
        webhook_url = f"{request.urlparts.scheme}://{request.urlparts.netloc}/api/webhook/{api_token}"
        return template('webhook_created', name=name, webhook_url=webhook_url, 
                       api_token=api_token, config_token=config_token)
    else:
        models = get_all_models()
        return template('webhook_form', webhook=None, models=models, 
                       title="添加Webhook", action="/admin/webhooks/add",
                       message="创建Webhook失败", message_type="error")


@app.get('/admin/webhooks/edit/<webhook_id:int>')
@require_admin
def admin_webhooks_edit_form(user_id, webhook_id):
    """编辑Webhook表单"""
    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        return redirect('/admin/webhooks')
        
    models = get_all_models()
    return template('webhook_form', webhook=webhook, models=models, 
                   title="编辑Webhook", action=f"/admin/webhooks/edit/{webhook_id}")


@app.post('/admin/webhooks/edit/<webhook_id:int>')
@require_admin
def admin_webhooks_edit(user_id, webhook_id):
    """处理编辑Webhook请求"""
    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        return redirect('/admin/webhooks')
        
    request_forms = parse_utf8(request)
    name = ensure_utf8(request_forms.get('name'))
    description = ensure_utf8(request_forms.get('description'))
    model_id = request_forms.get('model_id')
    prompt_template = ensure_utf8(request_forms.get('prompt_template'))
    is_active = int(request_forms.get('is_active', 1))
    
    if not all([name, model_id]):
        models = get_all_models()
        return template('webhook_form', webhook=webhook, models=models, 
                       title="编辑Webhook", action=f"/admin/webhooks/edit/{webhook_id}",
                       message="所有必填字段都必须填写", message_type="error")
                       
    # 更新webhook
    if update_webhook(webhook_id, name, description, model_id, prompt_template, is_active):
        return redirect('/admin/webhooks')
    else:
        models = get_all_models()
        return template('webhook_form', webhook=webhook, models=models, 
                       title="编辑Webhook", action=f"/admin/webhooks/edit/{webhook_id}",
                       message="更新Webhook失败", message_type="error")


@app.get('/admin/webhooks/regenerate-token/<webhook_id:int>')
@require_admin
def admin_webhooks_regenerate_token(user_id, webhook_id):
    """重新生成Webhook Token"""
    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        return redirect('/admin/webhooks')
    
    token_type = request.query.get('type', 'api')
    
    if token_type == 'api':
        success, tokens = regenerate_webhook_tokens(webhook_id, regen_api=True, regen_config=False)
        if success and 'api_token' in tokens:
            webhook_url = f"{request.urlparts.scheme}://{request.urlparts.netloc}/api/webhook/{tokens['api_token']}"
            return template('webhook_api_token_regenerated', name=webhook['name'], 
                           webhook_url=webhook_url, api_token=tokens['api_token'])
    elif token_type == 'config':
        success, tokens = regenerate_webhook_tokens(webhook_id, regen_api=False, regen_config=True)
        if success and 'config_token' in tokens:
            return template('webhook_config_token_regenerated', name=webhook['name'], 
                           config_token=tokens['config_token'])
    
    return redirect('/admin/webhooks')


@app.get('/admin/webhooks/subscriptions/<webhook_id:int>')
@require_admin
def admin_webhook_subscriptions(user_id, webhook_id):
    """查看Webhook订阅列表"""
    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        return redirect('/admin/webhooks')
    
    subscriptions = get_webhook_subscriptions(webhook_id)
    
    return template('webhook_subscriptions', webhook=webhook, subscriptions=subscriptions)


@app.get('/admin/webhooks/remove-subscription/<subscription_id:int>')
@require_admin
def admin_remove_subscription(user_id, subscription_id):
    """管理员移除订阅"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取订阅信息以便之后跳转回正确的页面
    cursor.execute("SELECT webhook_id FROM webhook_subscriptions WHERE id = ?", (subscription_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return redirect('/admin/webhooks')
    
    webhook_id = result['webhook_id']
    
    # 删除订阅
    cursor.execute("DELETE FROM webhook_subscriptions WHERE id = ?", (subscription_id,))
    conn.commit()
    conn.close()
    
    return redirect(f'/admin/webhooks/subscriptions/{webhook_id}')


@app.get('/admin/webhook-logs/<webhook_id:int>')
@require_admin
def admin_webhook_logs(user_id, webhook_id):
    """查看Webhook调用日志"""
    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        return redirect('/admin/webhooks')
    
    logs = get_webhook_logs(webhook_id)
    
    return template('webhook_logs', webhook=webhook, logs=logs)


@app.get('/admin/webhooks/delete/<webhook_id:int>')
@require_admin
def admin_webhooks_delete(user_id, webhook_id):
    """删除webhook"""
    if delete_webhook(webhook_id):
        return redirect('/admin/webhooks')
    else:
        # 显示错误信息
        return template('error', error_message="删除Webhook失败", back_url="/admin/webhooks")


@app.get('/static/<filepath:path>')
def serve_static(filepath):
    """提供静态文件"""
    return static_file(filepath, root=STATIC_DIR)


# 健康检查接口
@app.get('/ping')
def ping():
    """健康检查接口"""
    return "pong"


# 主入口
def main():
    """主入口函数"""
    # 初始化数据库
    init_database()

    # 初始化静态文件目录
    init_static_dir()

    # 启动服务
    logger.info("飞书Dify机器人服务启动")
    
    # 检查是否安装了waitress（一个生产级WSGI服务器）
    try:
        from waitress import serve
        logger.info("使用waitress服务器启动应用")
        serve(app, host='0.0.0.0', port=8080, threads=10)  # 使用10个线程处理请求
        
    except ImportError:
        # 如果没有安装waitress，则使用bottle的内置服务器，但提醒用户
        logger.warning("未检测到waitress，使用Bottle默认服务器。生产环境建议安装waitress: pip install waitress")
        app.run(host='0.0.0.0', port=8080, debug=False, server='auto')  # 尝试使用最佳可用服务器
