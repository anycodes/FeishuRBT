#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import traceback
from bottle import request, HTTPResponse

from config import Config
from models.webhook import get_webhook, get_webhook_subscriptions, log_webhook_call
from services.lark_service import send_message
from services.dify_service import ask_dify_blocking
from utils.helpers import format_data_for_ai, parse_utf8, ensure_utf8

logger = logging.getLogger(__name__)


def setup_webhook_routes(app):
    """设置Webhook相关路由"""

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
                body = request.body.read().decode('utf-8')
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = parse_utf8(request)
                    if not data:
                        data = {"raw_content": body}
            except Exception as e:
                logger.error(f"解析webhook请求数据出错: {e}")
                data = {"error": "无法解析请求数据"}

            # 记录请求
            logger.info(f"接收到webhook调用: {webhook['name']}, 数据: {data}")

            # 获取所有订阅此webhook的目标
            subscriptions = get_webhook_subscriptions(webhook['id'])

            if not subscriptions:
                logger.warning(f"Webhook {webhook['name']} 没有订阅者，无法发送通知")
                log_webhook_call(webhook['id'], data, "无订阅者", 200)

                return HTTPResponse(
                    status=200,
                    body=json.dumps({
                        "success": True,
                        "message": "处理成功，但没有订阅者",
                    }),
                    headers={'Content-Type': 'application/json'}
                )

            # 处理消息
            if webhook.get('bypass_ai', 0) == 1:
                # 直接推送模式
                message = handle_direct_push(data)
                logger.info(f"直接推送模式，发送消息: {message[:100]}...")
            else:
                # AI处理模式
                message = handle_ai_processing(webhook, data)
                logger.info(f"AI处理结果: {message}")

            # 发送到所有订阅者
            sent_count = send_to_subscribers(subscriptions, message)

            # 记录调用日志
            log_webhook_call(webhook['id'], data, message, 200)

            # 返回成功响应
            mode = "直接推送" if webhook.get('bypass_ai', 0) == 1 else "AI处理"
            return HTTPResponse(
                status=200,
                body=json.dumps({
                    "success": True,
                    "message": f"{mode}成功，已发送给 {sent_count}/{len(subscriptions)} 个订阅者",
                }),
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


def handle_direct_push(data):
    """处理直接推送模式"""
    if isinstance(data, dict):
        # 优先使用特定字段
        if 'message' in data:
            return str(data['message'])
        elif 'content' in data:
            return str(data['content'])
        elif 'text' in data:
            return str(data['text'])
        else:
            # 格式化整个字典，但不加前缀
            message = ""
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, indent=2)
                message += f"**{key}**: {value}\n"
            return message.strip()
    else:
        return str(data)


def handle_ai_processing(webhook, data):
    """处理AI分析模式"""
    model = {
        'id': webhook['model_id'],
        'name': webhook['model_name'],
        'dify_type': webhook['dify_type'],
        'dify_url': webhook['dify_url'],
        'api_key': webhook['api_key']
    }

    # 准备AI输入
    formatted_input = format_data_for_ai(data)
    prompt_template = webhook['prompt_template']

    if prompt_template:
        query = prompt_template.replace("{data}", formatted_input)
    else:
        query = f"分析以下数据:\n\n{formatted_input}"

    try:
        # 调用AI处理
        answer = ask_dify_blocking(model, query, None, "webhook")
        return answer if answer else handle_ai_failure(webhook, data, "AI返回空结果")
    except Exception as e:
        error_msg = f"AI处理出错: {str(e)}"
        logger.error(error_msg)
        return handle_ai_failure(webhook, data, error_msg)


def handle_ai_failure(webhook, original_data, error_msg):
    """处理AI失败的回退方案"""
    fallback_mode = webhook.get('fallback_mode', 'original')

    if fallback_mode == 'original':
        # 发送原始数据
        return format_data_for_ai(original_data)
    elif fallback_mode == 'custom':
        # 发送自定义消息
        custom_msg = webhook.get('fallback_message', '处理失败，请稍后重试')
        return f"{custom_msg}\n\n原始数据：{format_data_for_ai(original_data)}"
    elif fallback_mode == 'silent':
        # 静默失败，不发送通知
        return None
    else:
        # 默认发送错误信息
        return f"处理出错：{error_msg}"


def send_to_subscribers(subscriptions, message):
    """发送消息到所有订阅者"""
    if message is None:
        return 0

    sent_count = 0
    for sub in subscriptions:
        try:
            if sub['target_type'] == "user":
                response = send_message(open_id=sub['target_id'], content=message)
            else:
                response = send_message(chat_id=sub['target_id'], content=message)

            if response.get("code") == 0:
                sent_count += 1
        except Exception as e:
            logger.error(f"发送消息到 {sub['target_type']}:{sub['target_id']} 失败: {e}")

    return sent_count