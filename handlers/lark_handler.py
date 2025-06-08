# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import threading
from collections import deque
from bottle import request, HTTPResponse

from config import Config
from models.user import get_user, add_user
from services.lark_service import send_message
from services.cache_service import ImageCacheService
from .command_handler import handle_command, is_command, parse_command
from utils.helpers import is_bot_mentioned, remove_mentions_improved, ensure_utf8

logger = logging.getLogger(__name__)

# 请求去重
processed_events = deque(maxlen=100)
processing_lock = threading.RLock()

# 图片缓存服务
image_cache = ImageCacheService()


def setup_lark_routes(app):
    """设置飞书相关路由"""

    @app.post('/webhook/event')
    def event_handler():
        """处理飞书事件"""
        try:
            body = request.body.read().decode('utf-8')
            logger.info(f"收到请求: {body}")

            event_data = json.loads(body)

            # URL验证处理
            if event_data.get("type") == "url_verification":
                challenge = event_data.get("challenge")
                token = event_data.get("token")

                logger.info(f"处理URL验证请求: challenge={challenge}, token={token}")

                if token != Config.VERIFICATION_TOKEN:
                    logger.warning(f"Token验证失败: {token}")
                    return HTTPResponse(
                        status=401,
                        body=json.dumps({"error": "invalid token"}),
                        headers={'Content-Type': 'application/json'}
                    )

                return HTTPResponse(
                    status=200,
                    body=json.dumps({"challenge": challenge}),
                    headers={'Content-Type': 'application/json'}
                )

            # 验证Token
            if "header" in event_data:
                token = event_data.get("header", {}).get("token")
            else:
                token = event_data.get("token")

            if token != Config.VERIFICATION_TOKEN:
                logger.warning(f"Token验证失败: {token}")
                return HTTPResponse(
                    status=401,
                    body=json.dumps({"error": "invalid token"}),
                    headers={'Content-Type': 'application/json'}
                )

            # 加锁处理事件
            with processing_lock:
                if "schema" in event_data and event_data.get("schema") == "2.0":
                    handle_v2_event(event_data)
                else:
                    handle_v1_event(event_data)

            return HTTPResponse(
                status=200,
                body=json.dumps({"code": 0, "msg": "success"}),
                headers={'Content-Type': 'application/json'}
            )

        except Exception as e:
            logger.error(f"处理事件出错: {str(e)}")
            import traceback
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

    if event_id in processed_events:
        logger.info(f"跳过重复事件: {event_id}")
        return True

    processed_events.append(event_id)

    if event_type == "im.message.receive_v1":
        event = event_data.get("event", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id")
        message = event.get("message", {})
        msg_type = message.get("message_type")
        chat_type = message.get("chat_type")
        chat_id = message.get("chat_id")

        logger.info(f"收到v2.0消息: 类型={msg_type}, 发送者={sender_id}, 聊天类型={chat_type}")

        # 处理不同类型的消息
        if msg_type == "text":
            content_json = json.loads(message.get("content", "{}"))
            text_content = content_json.get("text", "")
            mentions = message.get("mentions", [])

            handle_text_message(sender_id, text_content, chat_type, chat_id, mentions)

        elif msg_type == "image":
            handle_image_message(sender_id, message, chat_type, chat_id)
        else:
            # 其他类型消息的处理
            reply_func = create_reply_function(sender_id, chat_type, chat_id, [])
            reply_func("目前只支持文本和图片消息。")

    return True


def handle_v1_event(event_data):
    """处理v1.0版本的事件"""
    if event_data.get("type") == "event_callback":
        event = event_data.get("event", {})
        event_type = event.get("type")

        event_id = event_data.get("uuid")
        if event_id in processed_events:
            logger.info(f"跳过重复事件: {event_id}")
            return True

        processed_events.append(event_id)

        if event_type == "im.message.receive_v1" or event_type == "message":
            sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id")
            message = event.get("message", {})
            msg_type = message.get("message_type")
            chat_type = message.get("chat_type")
            chat_id = message.get("chat_id")

            logger.info(f"收到v1.0消息: 类型={msg_type}, 发送者={sender_id}, 聊天类型={chat_type}")

            if msg_type == "text":
                content_json = json.loads(message.get("content", "{}"))
                text_content = content_json.get("text", "")
                mentions = message.get("mentions", [])

                handle_text_message(sender_id, text_content, chat_type, chat_id, mentions)

            elif msg_type == "image":
                handle_image_message(sender_id, message, chat_type, chat_id)
            else:
                reply_func = create_reply_function(sender_id, chat_type, chat_id, [])
                reply_func("目前只支持文本和图片消息。")

    return True


def handle_text_message(sender_id, text_content, chat_type, chat_id, mentions):
    """处理文本消息"""
    # 检查用户是否存在
    user = get_user(sender_id)
    if not user:
        add_user(sender_id)

    # 群聊逻辑处理
    is_mention = False
    original_text = text_content

    if chat_type == "group" and mentions:
        is_mention = is_bot_mentioned(mentions)
        if is_mention:
            # 改进的@内容移除
            text_content = remove_mentions_improved(text_content, mentions)
            logger.info(f"机器人被@，处理请求: {text_content}")

    # 检查是否有缓存的图片
    cached_image_key = image_cache.get_user_image_key(sender_id)

    # 创建回复函数
    reply_func = create_reply_function(sender_id, chat_type, chat_id, mentions)

    # 仅处理私聊消息或群聊中@机器人的消息
    if chat_type != "group" or (chat_type == "group" and is_mention):
        if cached_image_key:
            # 有缓存图片，结合文本和图片处理
            handle_text_with_cached_image(sender_id, text_content, cached_image_key, reply_func)
        else:
            # 正常文本处理
            if is_command(text_content):
                cmd, args = parse_command(text_content)
                if cmd:
                    sender_type = "group" if chat_type == "group" else "user"
                    handle_command(cmd, args, sender_id, sender_type, chat_id, reply_func)
                else:
                    process_message(sender_id, text_content, reply_func)
            else:
                process_message(sender_id, text_content, reply_func)


def handle_image_message(sender_id, message, chat_type, chat_id):
    """处理图片消息"""
    # 检查用户是否存在
    user = get_user(sender_id)
    if not user:
        add_user(sender_id)

    # 创建回复函数
    reply_func = create_reply_function(sender_id, chat_type, chat_id, [])

    # 仅在私聊中处理图片，群聊需要@机器人
    if chat_type != "group":
        try:
            content_json = json.loads(message.get("content", "{}"))
            image_key = content_json.get("image_key", "")

            if image_key:
                # 缓存图片key
                if image_cache.save_user_image_key(sender_id, image_key):
                    reply_func(
                        "我收到了您的图片！请告诉我您希望我对这张图片做什么？\n\n例如：\n- 描述图片内容\n- 翻译图片中的文字\n- 分析图片数据\n- 提取图片中的信息\n\n（此图片将在5分钟后自动清除）")
                else:
                    reply_func("图片缓存失败，请重新发送。")
            else:
                reply_func("抱歉，无法获取图片信息。")
        except Exception as e:
            logger.error(f"处理图片消息出错: {e}")
            reply_func("处理图片时出现错误，请稍后重试。")
    else:
        reply_func("群聊中的图片处理需要@机器人。")


def handle_text_with_cached_image(sender_id, text, cached_image_key, reply_func):
    """处理带缓存图片的文本消息"""
    try:
        reply_func("正在分析图片并处理您的请求，请稍候...")

        # 下载并缓存图片
        image_path = image_cache.download_and_cache_image(sender_id, cached_image_key)

        if not image_path:
            reply_func("抱歉，无法下载图片，请重新发送图片。")
            image_cache.clear_user_image(sender_id)
            return

        # 获取用户会话和模型
        from models.session import get_or_create_session, get_session_model, add_message

        session_id, conversation_id = get_or_create_session(sender_id)
        model = get_session_model(session_id)

        if not model:
            reply_func("当前没有设置默认模型，无法处理图片。请先使用 `\\change-model [模型名称]` 命令选择一个模型。")
            image_cache.clear_user_image(sender_id)
            return

        # 添加用户消息记录（包含图片信息）
        user_message = f"[图片] {text}"
        add_message(session_id, sender_id, user_message, is_user=1)

        # 调用图片+文本处理
        from services.dify_service import process_image_and_text

        try:
            response = process_image_and_text(model, image_path, text, conversation_id, sender_id, session_id)
            reply_func(response)
        except Exception as e:
            logger.error(f"AI处理图片+文本失败: {e}")
            # 降级处理：只处理文本，告知用户图片信息
            fallback_text = f"我收到了您发送的图片，您的问题是：{text}\n\n由于图片处理遇到问题，我只能根据您的文字描述来回答。"
            from services.dify_service import process_dify_message
            fallback_response = process_dify_message(model, fallback_text, conversation_id, sender_id, session_id)
            reply_func(fallback_response)

        # 处理完后清除缓存
        image_cache.clear_user_image(sender_id)

    except Exception as e:
        logger.error(f"处理图片+文本出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
        reply_func("处理图片和文本时出现错误，请稍后重试。")
        image_cache.clear_user_image(sender_id)


def create_reply_function(sender_id, chat_type, chat_id, mentions):
    """创建回复函数"""
    is_mention = bool(mentions and is_bot_mentioned(mentions))
    reply_id = chat_id if is_mention and chat_type == "group" else sender_id
    reply_type = "chat_id" if is_mention and chat_type == "group" else "open_id"

    def reply(content):
        try:
            if reply_type == "open_id":
                send_message(open_id=reply_id, content=content)
            else:
                send_message(chat_id=reply_id, content=content)
        except Exception as e:
            logger.error(f"发送消息失败: {e}")

    return reply


def process_message(sender_id, content, reply_func):
    """处理用户消息的核心函数"""
    from models.session import get_or_create_session, get_session_model, add_message
    from services.dify_service import process_dify_message

    try:
        # 获取用户会话
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
            full_response = process_dify_message(model, content, conversation_id, sender_id, session_id)
            reply_func(full_response)
            return True
        except Exception as e:
            logger.error(f"处理消息出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            reply_func(f"处理消息时出错: {str(e)}")
            return False

    except Exception as e:
        logger.error(f"消息处理全局错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        reply_func("消息处理时发生意外错误，请稍后重试。")
        return False
