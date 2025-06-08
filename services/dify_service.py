#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import ssl
import random
import logging
import urllib.request
import urllib.parse
from datetime import datetime

from config import Config
from models.session import update_session_conversation, add_message
from utils.helpers import http_request_with_retry

logger = logging.getLogger(__name__)


def dify_request(model, endpoint, method="POST", data=None, files=None, params=None, stream=False):
    """统一处理Dify API请求"""
    base_url = model['dify_url'].rstrip('/')
    url = f"{base_url}/{endpoint.lstrip('/')}"

    logger.info(f"Dify API请求: {url}")

    headers = {
        "Authorization": f"Bearer {model['api_key']}"
    }

    if not files:
        headers["Content-Type"] = "application/json"

    if method == "GET":
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
    else:
        if files:
            logger.warning("文件上传功能需要特殊处理")
            boundary = '----WebKitFormBoundary' + ''.join(
                random.sample('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', 16))
            headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
            data_bytes = b''
        elif data:
            data_bytes = json.dumps(data).encode('utf-8')
        else:
            data_bytes = None

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        if stream:
            return urllib.request.urlopen(req, context=ctx, timeout=Config.API_TIMEOUT)
        else:
            with urllib.request.urlopen(req, context=ctx, timeout=Config.API_TIMEOUT) as response:
                response_data = response.read()
                if response_data:
                    return json.loads(response_data.decode('utf-8'))
                return None
    except Exception as e:
        logger.error(f"Dify API请求失败: {e}")
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
        response_obj = dify_request(model, "chat-messages", data=data, stream=True)
        if response_obj is None:
            logger.error("无法连接到Dify API或获取有效响应")
            return None
        return response_obj
    else:
        response = dify_request(model, "chat-messages", data=data)
        if response and "answer" in response:
            return response["answer"], response.get("conversation_id")
        logger.warning(f"未找到回答字段: {response}")
        return "抱歉，无法获取回答", None


def ask_dify_agent(model, query, conversation_id=None, user_id="default_user", streaming=True):
    """向Dify Agent API发送请求"""
    return ask_dify_chatbot(model, query, conversation_id, user_id, streaming)


def ask_dify_flow(model, query, conversation_id=None, user_id="default_user", streaming=True):
    """向Dify Flow API发送请求"""
    return ask_dify_chatbot(model, query, conversation_id, user_id, streaming)


def ask_dify_blocking(model, query, conversation_id=None, user_id="default_user"):
    """阻塞式调用Dify API"""
    if model['dify_type'] == 'chatbot':
        answer, _ = ask_dify_chatbot(model, query, conversation_id, user_id, streaming=False)
    elif model['dify_type'] == 'agent':
        answer, _ = ask_dify_agent(model, query, conversation_id, user_id, streaming=False)
    elif model['dify_type'] == 'flow':
        answer, _ = ask_dify_flow(model, query, conversation_id, user_id, streaming=False)
    else:
        answer = f"不支持的模型类型: {model['dify_type']}"

    return answer


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

            while b"\n\n" in buffer:
                try:
                    event, buffer = buffer.split(b"\n\n", 1)
                    if event.startswith(b"data: "):
                        event_data = event[6:]
                        try:
                            event_json = json.loads(event_data)
                            event_type = event_json.get("event")

                            if event_type == "message":
                                response_part = event_json.get("answer", "")
                                full_response += response_part
                                yield response_part

                            elif event_type == "agent_message":
                                response_part = event_json.get("answer", "")
                                full_response += response_part
                                yield response_part

                            elif event_type == "workflow_started":
                                logger.info(f"Workflow started: {event_json}")

                            elif event_type == "node_started":
                                logger.info(f"Node started: {event_json}")

                            elif event_type == "node_finished":
                                logger.info(f"Node finished: {event_json}")

                            elif event_type == "workflow_finished":
                                logger.info(f"Workflow finished: {event_json}")

                            elif event_type == "agent_thought":
                                logger.info(f"Agent thought: {event_json}")

                            elif event_type == "message_file":
                                logger.info(f"File message: {event_json}")
                                file_url = event_json.get("url", "")
                                if file_url:
                                    yield f"\n[文件] {file_url}\n"

                            elif event_type == "message_end":
                                if "conversation_id" in event_json:
                                    conversation_id = event_json["conversation_id"]
                                    update_session_conversation(session_id, conversation_id)
                                logger.info("Message stream ended")

                            elif event_type == "error":
                                error_msg = f"处理出错: {event_json.get('message', '未知错误')}"
                                logger.error(error_msg)
                                yield error_msg
                                full_response += error_msg

                        except json.JSONDecodeError:
                            logger.error(f"解析响应JSON失败: {event_data}")
                except ValueError:
                    break
    except Exception as e:
        error_msg = f"处理流式响应出错: {str(e)}"
        logger.error(error_msg)
        yield error_msg
        full_response += error_msg
    finally:
        try:
            if stream:
                stream.close()
        except:
            pass

    if full_response:
        add_message(session_id, user_id, full_response, is_user=0)

    return full_response, conversation_id


def process_dify_message(model, content, conversation_id, user_id, session_id):
    """处理Dify消息并返回完整响应"""
    try:
        if model['dify_type'] == 'chatbot':
            stream = ask_dify_chatbot(model, content, conversation_id, user_id)
        elif model['dify_type'] == 'agent':
            stream = ask_dify_agent(model, content, conversation_id, user_id)
        elif model['dify_type'] == 'flow':
            stream = ask_dify_flow(model, content, conversation_id, user_id)
        else:
            return f"不支持的模型类型：{model['dify_type']}"

        if stream is None:
            return "无法连接到Dify API，请检查API地址和密钥是否正确，或者网络连接是否正常。"

        full_response = ""
        for chunk in process_dify_stream(stream, session_id, user_id):
            full_response += chunk

        return full_response
    except Exception as e:
        logger.error(f"处理Dify消息出错: {str(e)}")
        return f"处理消息时出错: {str(e)}"