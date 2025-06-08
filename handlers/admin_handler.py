#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from bottle import request, response, redirect, static_file, template, TEMPLATE_PATH

from config import Config
from models.model import get_all_models, get_model, add_model, update_model, delete_model
from models.command import get_all_commands, get_command, add_command, update_command, delete_command
from models.webhook import (get_all_webhooks, get_webhook, create_webhook, update_webhook,
                            regenerate_webhook_tokens, get_webhook_subscriptions, get_webhook_logs, delete_webhook)
from models.user import get_all_users, set_user_admin
from models.session import get_all_configs, set_config, get_config
from utils.decorators import require_admin
from utils.helpers import parse_utf8, ensure_utf8

logger = logging.getLogger(__name__)

def setup_admin_routes(app):
    """设置管理界面相关路由"""

    @app.get('/admin')
    def admin_redirect():
        """管理界面根路径，重定向到模型管理"""
        from utils.helpers import validate_admin_token

        token = request.query.get('token')
        if token:
            valid, _ = validate_admin_token(token)
            if valid:
                response.set_cookie('admin_token', token, path='/')
                return redirect('/admin/models')

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
        from utils.helpers import invalidate_admin_token

        token = request.get_cookie('admin_token')
        if token:
            invalidate_admin_token(token)
            response.delete_cookie('admin_token')

        return redirect('/admin/login')

    # 模型管理路由
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
                            message="所有必填字段都必须填写", message_type="alert-error")

        if get_model(model_name=name):
            return template('model_form', model=None, title="添加模型", action="/admin/models/add",
                            message=f"名为 '{name}' 的模型已存在", message_type="alert-error")

        model_id = add_model(name, description, dify_url, dify_type, api_key)
        if model_id:
            return redirect('/admin/models')
        else:
            return template('model_form', model=None, title="添加模型", action="/admin/models/add",
                            message="添加模型失败", message_type="alert-error")

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
                            message="所有必填字段都必须填写", message_type="alert-error")

        if name != model['name'] and get_model(model_name=name):
            return template('model_form', model=model, title="编辑模型", action=f"/admin/models/edit/{model_id}",
                            message=f"名为 '{name}' 的模型已存在", message_type="alert-error")

        if update_model(model_id, name, description, dify_url, dify_type, api_key):
            return redirect('/admin/models')
        else:
            return template('model_form', model=model, title="编辑模型", action=f"/admin/models/edit/{model_id}",
                            message="更新模型失败", message_type="alert-error")

    @app.get('/admin/models/delete/<model_id:int>')
    @require_admin
    def admin_models_delete(user_id, model_id):
        """删除模型"""
        delete_model(model_id)
        return redirect('/admin/models')

    # 命令管理路由
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
                            message="所有字段都必须填写", message_type="alert-error")

        success, result = add_command(name, description, trigger, model_id)
        if success:
            return redirect('/admin/commands')
        else:
            models = get_all_models()
            return template('command_form', command=None, models=models, title="添加命令", action="/admin/commands/add",
                            message=result, message_type="alert-error")

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
                            message="所有字段都必须填写", message_type="alert-error")

        success, message = update_command(command_id, name, description, trigger, model_id)
        if success:
            return redirect('/admin/commands')
        else:
            models = get_all_models()
            return template('command_form', command=command, models=models, title="编辑命令",
                            action=f"/admin/commands/edit/{command_id}",
                            message=message, message_type="alert-error")

    @app.get('/admin/commands/delete/<command_id:int>')
    @require_admin
    def admin_commands_delete(user_id, command_id):
        """删除命令"""
        delete_command(command_id)
        return redirect('/admin/commands')

    # Webhook管理路由
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
        bypass_ai = int(request_forms.get('bypass_ai', 0))
        fallback_mode = ensure_utf8(request_forms.get('fallback_mode', 'original'))
        fallback_message = ensure_utf8(request_forms.get('fallback_message'))

        if not all([name, model_id]):
            models = get_all_models()
            return template('webhook_form', webhook=None, models=models,
                            title="添加Webhook", action="/admin/webhooks/add",
                            message="所有必填字段都必须填写", message_type="alert-error")

        webhook_id, api_token, config_token = create_webhook(name, description, model_id,
                                                             prompt_template, bypass_ai,
                                                             fallback_mode, fallback_message)
        if webhook_id:
            webhook_url = f"{request.urlparts.scheme}://{request.urlparts.netloc}/api/webhook/{api_token}"
            return template('webhook_created', name=name, webhook_url=webhook_url,
                            api_token=api_token, config_token=config_token)
        else:
            models = get_all_models()
            return template('webhook_form', webhook=None, models=models,
                            title="添加Webhook", action="/admin/webhooks/add",
                            message="创建Webhook失败", message_type="alert-error")

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
        bypass_ai = int(request_forms.get('bypass_ai', 0))
        fallback_mode = ensure_utf8(request_forms.get('fallback_mode', 'original'))
        fallback_message = ensure_utf8(request_forms.get('fallback_message'))

        if not all([name, model_id]):
            models = get_all_models()
            return template('webhook_form', webhook=webhook, models=models,
                            title="编辑Webhook", action=f"/admin/webhooks/edit/{webhook_id}",
                            message="所有必填字段都必须填写", message_type="alert-error")

        if update_webhook(webhook_id, name, description, model_id, prompt_template,
                          bypass_ai, fallback_mode, fallback_message, is_active):
            return redirect('/admin/webhooks')
        else:
            models = get_all_models()
            return template('webhook_form', webhook=webhook, models=models,
                            title="编辑Webhook", action=f"/admin/webhooks/edit/{webhook_id}",
                            message="更新Webhook失败", message_type="alert-error")

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
        from models.database import get_db_connection

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
        delete_webhook(webhook_id)
        return redirect('/admin/webhooks')

    # 系统配置路由
    @app.get('/admin/config')
    @require_admin
    def admin_config(user_id):
        """系统配置页面"""
        configs = get_all_configs()
        models = get_all_models()

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

        if default_model_id:
            set_config("default_model", default_model_id)

        if session_timeout:
            try:
                timeout = int(session_timeout)
                if timeout > 0:
                    set_config("session_timeout", str(timeout))
            except ValueError:
                pass

        return redirect('/admin/config')

    # 用户管理路由
    @app.get('/admin/users')
    @require_admin
    def admin_users(user_id):
        """用户管理页面"""
        users = get_all_users()
        return template('users', users=users)

    @app.get('/admin/users/toggle_admin/<user_id_to_toggle>')
    @require_admin
    def admin_toggle_admin(user_id, user_id_to_toggle):
        """切换用户管理员状态"""
        from models.user import get_user
        from models.database import get_db_connection

        if user_id == user_id_to_toggle:
            return redirect('/admin/users')

        user = get_user(user_id_to_toggle)
        if user:
            new_status = 0 if user['is_admin'] == 1 else 1
            set_user_admin(user_id_to_toggle, new_status)

            if new_status == 0:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE user_id = ?", (user_id_to_toggle,))
                conn.commit()
                conn.close()

        return redirect('/admin/users')

    # 数据库管理路由
    @app.get('/admin/database')
    @require_admin
    def admin_database_info(user_id):
        """数据库信息页面"""
        from models.migration import get_database_info
        db_info = get_database_info()
        return template('database_info', db_info=db_info)

    @app.post('/admin/database/migrate')
    @require_admin
    def admin_force_migrate(user_id):
        """强制执行迁移"""
        from models.migration import DatabaseMigration

        migration = DatabaseMigration()
        success = migration.run_migrations()

        if success:
            message = "迁移执行成功"
            message_type = "alert-success"
        else:
            message = "迁移执行失败，请查看日志"
            message_type = "alert-error"

        from models.migration import get_database_info
        db_info = get_database_info()
        return template('database_info', db_info=db_info, message=message, message_type=message_type)

    # 日志查看路由
    @app.get('/admin/logs')
    @require_admin
    def admin_logs(user_id):
        """日志查看页面"""
        log_content = ""
        try:
            with open('lark_bot.log', 'r', encoding='utf-8') as f:
                lines = f.readlines()[-1000:]
                log_content = ''.join(lines)
        except Exception as e:
            log_content = f"读取日志文件出错: {str(e)}"

        return template('logs', log_content=log_content)

    # 静态文件服务
    @app.get('/static/<filepath:path>')
    def serve_static(filepath):
        """提供静态文件"""
        return static_file(filepath, root=Config.STATIC_DIR)