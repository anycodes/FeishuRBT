#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import ssl
import random
import logging
import urllib.request
import urllib.parse
import traceback
import os
import mimetypes
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

    if method == "GET":
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
    else:
        if files:
            # 处理multipart/form-data文件上传
            data_bytes, content_type = encode_multipart_formdata(files, data)
            headers['Content-Type'] = content_type
        elif data:
            headers["Content-Type"] = "application/json"
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
        logger.error(traceback.format_exc())
        return None


def encode_multipart_formdata(files, fields=None):
    """编码multipart/form-data"""
    boundary = '----WebKitFormBoundary' + ''.join(
        random.choices('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', k=16))
    body = []

    # 添加表单字段
    if fields:
        for key, value in fields.items():
            body.append(f'--{boundary}'.encode())
            body.append(f'Content-Disposition: form-data; name="{key}"'.encode())
            body.append(b'')
            body.append(str(value).encode())

    # 添加文件
    for key, file_info in files.items():
        body.append(f'--{boundary}'.encode())

        if isinstance(file_info, dict):
            filename = file_info.get('filename', 'file')
            content = file_info.get('content', b'')
            content_type = file_info.get('content_type', 'application/octet-stream')
        else:
            # 假设是文件路径
            filename = os.path.basename(file_info)
            content_type, _ = mimetypes.guess_type(file_info)
            if content_type is None:
                content_type = 'application/octet-stream'

            with open(file_info, 'rb') as f:
                content = f.read()

        body.append(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode())
        body.append(f'Content-Type: {content_type}'.encode())
        body.append(b'')
        body.append(content)

    body.append(f'--{boundary}--'.encode())

    content_type = f'multipart/form-data; boundary={boundary}'
    return b'\r\n'.join(body), content_type


def upload_file_to_dify(model, file_path, user_id="default_user"):
    """上传文件到Dify"""
    try:
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return None

        # 检查文件类型
        file_ext = os.path.splitext(file_path)[1].lower()
        supported_formats = ['.png', '.jpg', '.jpeg', '.webp', '.gif']

        if file_ext not in supported_formats:
            logger.error(f"不支持的文件格式: {file_ext}")
            return None

        # 检查文件大小（假设限制为10MB）
        file_size = os.path.getsize(file_path)
        max_size = 10 * 1024 * 1024  # 10MB

        if file_size > max_size:
            logger.error(f"文件过大: {file_size} bytes, 最大支持: {max_size} bytes")
            return None

        # 准备上传
        files = {
            'file': file_path
        }

        fields = {
            'user': user_id
        }

        logger.info(f"开始上传文件: {file_path}")
        response = dify_request(model, "files/upload", files=files, data=fields)

        if response and 'id' in response:
            logger.info(f"文件上传成功: {response['id']}")
            return response
        else:
            logger.error(f"文件上传失败: {response}")
            return None

    except Exception as e:
        logger.error(f"上传文件出错: {e}")
        logger.error(traceback.format_exc())
        return None


def get_dify_file_types_support():
    """获取Dify支持的文件类型"""
    # 根据API文档，支持以下图片格式
    return ['.png', '.jpg', '.jpeg', '.webp', '.gif']


def ask_dify_chatbot(model, query, conversation_id=None, user_id="default_user", streaming=True, files=None):
    """向Dify聊天机器人API发送请求，支持文件"""
    data = {
        "query": query,
        "inputs": {},
        "user": user_id,
        "response_mode": "streaming" if streaming else "blocking"
    }

    if conversation_id:
        data["conversation_id"] = conversation_id

    # 添加文件支持
    if files:
        data["files"] = files

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


def ask_dify_agent(model, query, conversation_id=None, user_id="default_user", streaming=True, files=None):
    """向Dify Agent API发送请求"""
    return ask_dify_chatbot(model, query, conversation_id, user_id, streaming, files)


def ask_dify_flow(model, query, conversation_id=None, user_id="default_user", streaming=True, files=None):
    """向Dify Flow API发送请求"""
    return ask_dify_chatbot(model, query, conversation_id, user_id, streaming, files)


def ask_dify_blocking(model, query, conversation_id=None, user_id="default_user", files=None):
    """阻塞式调用Dify API"""
    if model['dify_type'] == 'chatbot':
        answer, _ = ask_dify_chatbot(model, query, conversation_id, user_id, streaming=False, files=files)
    elif model['dify_type'] == 'agent':
        answer, _ = ask_dify_agent(model, query, conversation_id, user_id, streaming=False, files=files)
    elif model['dify_type'] == 'flow':
        answer, _ = ask_dify_flow(model, query, conversation_id, user_id, streaming=False, files=files)
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
    file_urls = []  # 收集文件URL

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
                                    file_urls.append(file_url)
                                    yield f"\n[文件] {file_url}\n"

                            elif event_type == "tts_message":
                                # TTS音频流事件
                                logger.info("收到TTS音频流事件")
                                # 这里可以处理音频数据，当前只记录日志

                            elif event_type == "tts_message_end":
                                # TTS音频流结束
                                logger.info("TTS音频流结束")

                            elif event_type == "message_replace":
                                # 消息内容替换事件
                                replace_answer = event_json.get("answer", "")
                                logger.info(f"消息被替换: {replace_answer}")
                                full_response = replace_answer  # 替换整个回复
                                yield f"\n[消息已更新] {replace_answer}\n"

                            elif event_type == "ping":
                                # 保持连接的ping事件
                                logger.debug("收到ping事件")

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
        logger.error(traceback.format_exc())
        yield error_msg
        full_response += error_msg
    finally:
        try:
            if stream:
                stream.close()
        except:
            pass

    # 如果有文件，将文件信息也加入到响应中
    if file_urls:
        file_info = "\n\n生成的文件:\n" + "\n".join([f"- {url}" for url in file_urls])
        full_response += file_info

    if full_response:
        add_message(session_id, user_id, full_response, is_user=0)

    return full_response, conversation_id


def process_dify_message(model, content, conversation_id, user_id, session_id, files=None):
    """处理Dify消息并返回完整响应"""
    try:
        if model['dify_type'] == 'chatbot':
            stream = ask_dify_chatbot(model, content, conversation_id, user_id, files=files)
        elif model['dify_type'] == 'agent':
            stream = ask_dify_agent(model, content, conversation_id, user_id, files=files)
        elif model['dify_type'] == 'flow':
            stream = ask_dify_flow(model, content, conversation_id, user_id, files=files)
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
        logger.error(traceback.format_exc())
        return f"处理消息时出错: {str(e)}"


def process_image_and_text(model, image_path, text, conversation_id, user_id, session_id):
    """处理图片和文本的组合输入"""
    try:
        logger.info(f"处理图片+文本: 图片={image_path}, 文本={text}")

        # 1. 先上传图片到Dify
        upload_result = upload_file_to_dify(model, image_path, user_id)

        if not upload_result:
            # 上传失败，降级处理
            logger.warning("图片上传失败，降级为纯文本处理")
            return process_fallback_image_text(model, image_path, text, conversation_id, user_id, session_id)

        # 2. 构建files参数
        files = [
            {
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": upload_result['id']
            }
        ]

        # 3. 发送带图片的请求
        logger.info(f"发送图片+文本请求到Dify API")
        return process_dify_message(model, text, conversation_id, user_id, session_id, files=files)

    except Exception as e:
        logger.error(f"处理图片和文本组合失败: {e}")
        logger.error(traceback.format_exc())
        # 最终降级：只处理文本部分
        return process_fallback_image_text(model, image_path, text, conversation_id, user_id, session_id)


def process_fallback_image_text(model, image_path, text, conversation_id, user_id, session_id):
    """图片处理失败时的降级方案"""
    try:
        import os
        image_name = os.path.basename(image_path) if image_path else "未知图片"

        if text.strip():
            # 有文本内容
            combined_text = f"用户发送了一张图片（{image_name}），并提出问题：{text}\n\n请根据用户的文字描述来回答问题。"
        else:
            # 只有图片，没有文本
            combined_text = f"用户发送了一张图片（{image_name}）。抱歉，目前无法直接分析图片内容，请您描述一下图片的内容或者您希望了解什么？"

        logger.info(f"图片+文本降级处理: {combined_text}")
        return process_dify_message(model, combined_text, conversation_id, user_id, session_id)

    except Exception as e:
        logger.error(f"降级处理也失败了: {e}")
        return "抱歉，处理图片时遇到问题，请稍后重试或发送文字消息。"


def validate_dify_connection(model):
    """验证Dify连接是否正常"""
    try:
        # 发送一个简单的测试请求
        test_response = ask_dify_blocking(model, "hello", None, "test_user")
        return test_response is not None and test_response.strip() != ""
    except Exception as e:
        logger.error(f"Dify连接验证失败: {e}")
        return False


def stop_dify_response(model, task_id, user_id):
    """停止Dify流式响应"""
    try:
        data = {"user": user_id}
        response = dify_request(model, f"chat-messages/{task_id}/stop", data=data)

        if response and response.get("result") == "success":
            logger.info(f"成功停止任务: {task_id}")
            return True
        else:
            logger.error(f"停止任务失败: {response}")
            return False

    except Exception as e:
        logger.error(f"停止Dify响应出错: {e}")
        return False


def get_conversation_history(model, conversation_id, user_id, limit=20, first_id=None):
    """获取会话历史消息"""
    try:
        params = {
            "conversation_id": conversation_id,
            "user": user_id,
            "limit": limit
        }

        if first_id:
            params["first_id"] = first_id

        response = dify_request(model, "messages", method="GET", params=params)

        if response and "data" in response:
            return response["data"]
        else:
            logger.error(f"获取会话历史失败: {response}")
            return []

    except Exception as e:
        logger.error(f"获取会话历史出错: {e}")
        return []


def send_message_feedback(model, message_id, rating, user_id, content=None):
    """发送消息反馈"""
    try:
        data = {
            "rating": rating,  # "like", "dislike", None
            "user": user_id
        }

        if content:
            data["content"] = content

        response = dify_request(model, f"messages/{message_id}/feedbacks", data=data)

        if response and response.get("result") == "success":
            logger.info(f"反馈发送成功: message_id={message_id}, rating={rating}")
            return True
        else:
            logger.error(f"发送反馈失败: {response}")
            return False

    except Exception as e:
        logger.error(f"发送反馈出错: {e}")
        return False