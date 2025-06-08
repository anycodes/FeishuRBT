#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import urllib.request
import urllib.parse
from config import Config
from utils.helpers import http_request_with_retry, is_markdown

logger = logging.getLogger(__name__)

def get_tenant_access_token():
    """获取tenant_access_token用于API调用"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "app_id": Config.APP_ID,
        "app_secret": Config.APP_SECRET
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

    # 检测是否为Markdown格式
    if content and is_markdown(content):
        logger.info("检测到Markdown格式内容，使用富文本格式发送")
        post_content = {
            "zh_cn": {
                "title": "",
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