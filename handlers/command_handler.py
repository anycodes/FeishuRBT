#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from models.user import check_admin
from models.model import get_model, get_all_models, add_model, update_model, delete_model
from models.command import get_command, get_all_commands, add_command, update_command, delete_command
from models.session import get_config, set_config, get_or_create_session, add_message, get_session_model
from models.webhook import (get_webhook, get_all_webhooks, create_webhook, update_webhook, delete_webhook,
                            add_webhook_subscription, remove_webhook_subscription, get_user_subscriptions)
from models.user import get_user, add_user, set_user_admin
from services.dify_service import process_dify_message
from utils.helpers import create_admin_token, validate_admin_token, invalidate_admin_token
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def is_command(text):
    """检查文本是否是命令"""
    return text.startswith("\\") or text.startswith("/")


def parse_command(text):
    """解析命令和参数"""
    if not is_command(text):
        return None, None

    cmd_text = text[1:].strip()
    parts = cmd_text.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    return cmd, args


def is_user_command(cmd):
    """检查是否是普通用户可用的命令"""
    user_commands = [
        "help", "model-list", "model-info", "command-list", "change-model",
        "clear", "session-info", "subscribe-event", "unsubscribe-event", "list-subscriptions",
        "webhook-list"
    ]
    return cmd in user_commands


def is_admin_command(cmd):
    """检查是否是管理员命令"""
    admin_commands = [
        "admin-login", "admin-logout", "admin-add", "admin-remove",
        "model-add", "model-delete", "model-update", "set-default-model", "set-session-timeout",
        "command-add", "command-delete", "command-update",
        "webhook-add", "webhook-delete", "webhook-status"
    ]
    return cmd in admin_commands or any(
        cmd.startswith(prefix) for prefix in ["admin-", "model-", "command-", "webhook-", "set-"])


def handle_command(cmd, args, sender_id, sender_type="user", chat_id=None, reply_func=None):
    """处理系统命令"""
    is_admin = check_admin(sender_id)

    # 特殊命令：init-admin
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
    elif cmd == "webhook-list":
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
        elif cmd == "webhook-add":
            handle_webhook_add(args, reply_func)
            return True
        elif cmd == "webhook-delete":
            handle_webhook_delete(args, reply_func)
            return True
        elif cmd == "webhook-status":
            handle_webhook_status(args, reply_func)
            return True

    # 自定义命令处理
    command = get_command(trigger=f"\\{cmd}")
    if command:
        handle_custom_command(command, args, sender_id, reply_func)
        return True

    # 未知命令
    reply_func(f"未知命令: `\\{cmd}`\n使用 `\\help` 查看可用命令。")
    return True


def handle_init_admin(user_id, reply_func):
    """处理初始管理员设置命令"""
    from models.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_admin = 1")
    result = cursor.fetchone()
    conn.close()

    if result and result['count'] > 0:
        reply_func("初始化管理员失败：系统中已存在管理员账号，该命令已失效。")
        return

    user = get_user(user_id)
    if user:
        set_user_admin(user_id, 1)
    else:
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

    from models.model import get_model
    default_model_id = get_config("default_model")
    default_model = get_model(model_id=default_model_id) if default_model_id else None
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

    reply_text = f"## （{model['id']}）模型：{model['name']}\n\n"
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

    session_id, _ = get_or_create_session(user_id, model['id'])
    reply_func(f"已将当前会话模型切换为：{model['name']}。\n\n您可以开始提问了！")


def handle_clear_session(user_id, reply_func):
    """清除当前会话"""
    from models.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE sessions SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    conn.commit()
    affected = conn.total_changes
    conn.close()

    get_or_create_session(user_id)

    if affected > 0:
        reply_func("会话历史已清除，我们可以开始新的对话了！")
    else:
        reply_func("没有找到活动的会话，开始新的对话吧！")


def handle_session_info(user_id, reply_func):
    """查看当前会话状态"""
    from models.database import get_db_connection

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


def handle_subscribe_event(args, sender_id, sender_type, chat_id, reply_func):
    """处理订阅事件命令"""
    config_token = args.strip()
    if not config_token:
        reply_func("请提供有效的配置令牌，例如：`\\subscribe-event abc123`")
        return

    webhook = get_webhook(config_token=config_token)
    if not webhook:
        reply_func(f"未找到配置令牌为 '{config_token}' 的webhook事件")
        return

    if sender_type == "group":
        target_type = "chat"
        target_id = chat_id
        target_desc = "当前群组"
    else:
        target_type = "user"
        target_id = sender_id
        target_desc = "您"

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

    webhook = get_webhook(config_token=config_token)
    if not webhook:
        reply_func(f"未找到配置令牌为 '{config_token}' 的webhook事件")
        return

    if sender_type == "group":
        target_type = "chat"
        target_id = chat_id
        target_desc = "当前群组"
    else:
        target_type = "user"
        target_id = sender_id
        target_desc = "您"

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


def handle_webhook_list(reply_func):
    """列出所有可用的webhook"""
    webhooks = get_all_webhooks()

    if not webhooks:
        reply_func("系统中没有配置任何webhook")
        return

    reply_text = "## 可用的Webhook事件\n\n"
    for webhook in webhooks:
        status = "启用" if webhook['is_active'] == 1 else "禁用"
        reply_text += f"### ({webhook['id']}) {webhook['name']} ({status})\n"
        if webhook['description']:
            reply_text += f"{webhook['description']}\n"
        reply_text += f"- 订阅令牌: `{webhook['config_token']}`\n"
        reply_text += f"- 订阅命令: `\\subscribe-event {webhook['config_token']}`\n\n"
    reply_func(reply_text)


def handle_admin_login(user_id, reply_func):
    """管理员登录"""
    from bottle import request

    token = create_admin_token(user_id)
    admin_url = f"{request.urlparts.scheme}://{request.urlparts.netloc}/admin?token={token}"

    reply_text = f"管理员登录成功，请点击以下链接进入管理界面：\n\n{admin_url}\n\n该链接有效期为60分钟，请勿泄露。"
    reply_func(reply_text)


def handle_admin_logout(user_id, reply_func):
    """管理员退出"""
    from models.database import get_db_connection

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

    user = get_user(user_id)
    if not user:
        add_user(user_id, "", 1)
        reply_func(f"已添加新用户 '{user_id}' 并授予管理员权限。")
        return

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

    user = get_user(user_id)
    if not user:
        reply_func(f"用户 '{user_id}' 不存在。")
        return

    if set_user_admin(user_id, 0):
        from models.database import get_db_connection

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
    parts = args.split(' ', 4)
    if len(parts) < 5:
        reply_func("参数不足，格式应为：`\\model-add [名称] [描述] [Dify地址] [类型] [密钥]`")
        return

    name, description, dify_url, dify_type, api_key = parts

    if get_model(model_name=name):
        reply_func(f"名为 '{name}' 的模型已存在。")
        return

    valid_types = ["chatbot", "agent", "flow"]
    if dify_type not in valid_types:
        reply_func(f"无效的模型类型，类型应为以下之一：{', '.join(valid_types)}")
        return

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

    success, message = delete_model(model['id'])
    if success:
        reply_func(f"已删除模型：{model_name}")
    else:
        reply_func(f"删除模型失败：{message}")


def handle_model_update(args, reply_func):
    """更新模型参数"""
    parts = args.split(' ', 2)
    if len(parts) < 3:
        reply_func("参数不足，格式应为：`\\model-update [模型名称] [参数名] [新值]`")
        return

    model_name, param_name, new_value = parts

    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    valid_params = ["name", "description", "dify_url", "dify_type", "api_key"]
    if param_name not in valid_params:
        reply_func(f"无效的参数名，参数应为以下之一：{', '.join(valid_params)}")
        return

    if param_name == "name" and new_value != model_name:
        if get_model(model_name=new_value):
            reply_func(f"名为 '{new_value}' 的模型已存在。")
            return

    if param_name == "dify_type":
        valid_types = ["chatbot", "agent", "flow"]
        if new_value not in valid_types:
            reply_func(f"无效的模型类型，类型应为以下之一：{', '.join(valid_types)}")
            return

    update_params = {param_name: new_value}

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

    if set_config("default_model", str(model['id'])):
        reply_func(f"已将默认模型设置为：{model_name}")
    else:
        reply_func("设置默认模型失败。")


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


def handle_command_add(args, reply_func):
    """添加命令"""
    parts = args.split(' ', 3)
    if len(parts) < 4:
        reply_func("参数不足，格式应为：`\\command-add [名称] [简介] [启动指令] [模型]`")
        return

    name, description, trigger, model_name = parts

    if get_command(trigger=trigger):
        reply_func(f"触发指令 '{trigger}' 已存在。")
        return

    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型。")
        return

    success, result = add_command(name, description, trigger, model['id'])
    if success:
        reply_func(f"成功添加命令：{name}，触发指令：{trigger}")
    else:
        reply_func(f"添加命令失败：{result}")


def handle_command_delete(args, reply_func):
    """删除命令"""
    from models.database import get_db_connection

    command_name = args.strip()
    if not command_name:
        reply_func("请指定命令名称，例如：`\\command-delete 翻译`")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM commands WHERE name = ?", (command_name,))
    command = cursor.fetchone()
    conn.close()

    if not command:
        reply_func(f"未找到名为 '{command_name}' 的命令。")
        return

    if delete_command(command['id']):
        reply_func(f"已删除命令：{command_name}")
    else:
        reply_func("删除命令失败。")


def handle_command_update(args, reply_func):
    """更新命令参数"""
    from models.database import get_db_connection

    parts = args.split(' ', 2)
    if len(parts) < 3:
        reply_func("参数不足，格式应为：`\\command-update [命令名称] [参数名] [新值]`")
        return

    command_name, param_name, new_value = parts

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM commands WHERE name = ?", (command_name,))
    command = cursor.fetchone()
    conn.close()

    if not command:
        reply_func(f"未找到名为 '{command_name}' 的命令。")
        return

    valid_params = ["name", "description", "trigger", "model_id"]
    if param_name not in valid_params:
        reply_func(f"无效的参数名，参数应为以下之一：{', '.join(valid_params)}")
        return

    if param_name == "model_id":
        model = get_model(model_name=new_value)
        if not model:
            reply_func(f"未找到名为 '{new_value}' 的模型。")
            return
        new_value = model['id']

    update_params = {param_name: new_value}

    success, message = update_command(command['id'], **update_params)
    if success:
        reply_func(f"已更新命令 '{command_name}' 的 {param_name} 为 '{new_value}'。")
    else:
        reply_func(f"更新命令失败：{message}")


def handle_webhook_add(args, reply_func):
    """添加webhook (管理员命令)"""
    parts = args.split(' ', 2)
    if len(parts) < 3:
        reply_func("参数不足，格式应为: `\\webhook-add [名称] [描述] [模型名称]`")
        return

    name, description, model_name = parts

    model = get_model(model_name=model_name)
    if not model:
        reply_func(f"未找到名为 '{model_name}' 的模型")
        return

    webhook_id, api_token, config_token = create_webhook(name, description, model['id'])

    if webhook_id:
        reply_text = f"## Webhook已创建\n\n"
        reply_text += f"- 名称: {name}\n"
        reply_text += f"- 描述: {description}\n"
        reply_text += f"- 配置令牌: `{config_token}`\n"
        reply_text += f"- 订阅命令: `\\subscribe-event {config_token}`\n\n"

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

    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        reply_func(f"未找到ID为 {webhook_id} 的webhook")
        return

    if delete_webhook(webhook_id):
        reply_func(f"已成功删除webhook: {webhook['name']}")
    else:
        reply_func(f"删除webhook失败")


def handle_webhook_status(args, reply_func):
    """修改webhook状态 (管理员命令)"""
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

    webhook = get_webhook(webhook_id=webhook_id)
    if not webhook:
        reply_func(f"未找到ID为 {webhook_id} 的webhook")
        return

    if update_webhook(webhook_id, is_active=new_status):
        status_str = "启用" if new_status == 1 else "禁用"
        reply_func(f"已将webhook「{webhook['name']}」状态设置为: {status_str}")
    else:
        reply_func("更新webhook状态失败")


def handle_custom_command(command, args, user_id, reply_func):
    """处理自定义命令"""
    model_id = command['model_id']
    if not model_id:
        reply_func(f"该命令未关联任何模型，无法执行。")
        return

    model = get_model(model_id=model_id)
    if not model:
        reply_func(f"命令关联的模型不存在，无法执行。")
        return

    query = f"{command['name']}：{args}" if args else command['name']

    session_id, conversation_id = get_or_create_session(user_id, model_id, command['id'])

    add_message(session_id, user_id, query, is_user=1)

    reply_func(f"正在处理命令：{command['name']}...")

    try:
        full_response = process_dify_message(model, query, conversation_id, user_id, session_id)
        reply_func(full_response)
    except Exception as e:
        logger.error(f"处理命令出错: {str(e)}")
        reply_func(f"处理命令时出错: {str(e)}")