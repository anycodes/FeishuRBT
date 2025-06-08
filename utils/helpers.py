# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import socket
import time
import secrets
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

from config import Config

logger = logging.getLogger(__name__)


def ensure_utf8(text):
    """确保文本是UTF-8编码的字符串"""
    if text is None:
        return None
    if isinstance(text, bytes):
        return text.decode('utf-8')
    return text


def parse_utf8(request):
    """解析URL编码的表单数据"""
    body = request.body.read()
    body_str = body.decode('utf-8')

    form_data = {}
    for pair in body_str.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
            key = urllib.parse.unquote_plus(key)
            value = urllib.parse.unquote_plus(value)
            form_data[key] = value
    return form_data


def clean_command_args(args_text):
    """清理命令参数中的@信息，只保留第一个token"""
    if not args_text:
        return ""

    # 移除@开头的所有内容（包括@_user_数字格式）
    cleaned = re.sub(r'@\S+', '', args_text).strip()

    # 如果清理后为空，则取第一个单词
    if not cleaned:
        words = args_text.split()
        if words:
            # 取第一个不是@开头的单词
            for word in words:
                if not word.startswith('@'):
                    return word

    # 取第一个单词作为token（通常token是第一个参数）
    if cleaned:
        return cleaned.split()[0]

    return ""


def is_markdown(text):
    """简单判断文本是否包含Markdown格式"""
    markdown_patterns = [
        r'#{1,6}\s+\S+',  # 标题
        r'\*\*.*?\*\*',  # 粗体
        r'\*[^*]+\*',  # 斜体（更严格的匹配）
        r'`.*?`',  # 行内代码
        r'```[\s\S]*?```',  # 代码块
        r'!\[.*?\]\(.*?\)',  # 图片：![alt](url)
        r'\[.*?\]\(.*?\)',  # 链接：[text](url)
        r'^\s*[*+-]\s+',  # 无序列表
        r'^\s*\d+\.\s+',  # 有序列表
        r'^\s*>\s+',  # 引用
        r'^-{3,}$',  # 水平线
    ]

    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE):
            return True

    return False


def is_bot_mentioned(mentions):
    """检查消息中是否@了机器人"""
    if not mentions:
        return False

    for mention in mentions:
        mention_name = mention.get("name", "")
        mention_id = mention.get("id", {}).get("open_id", "")

        if (Config.BOT_NAME and Config.BOT_NAME in mention_name) or (
                Config.BOT_OPEN_ID and Config.BOT_OPEN_ID == mention_id):
            return True

    return False


def remove_mentions_improved(text, mentions):
    """改进的@内容移除函数"""
    if not mentions:
        return text

    cleaned_text = text
    for mention in mentions:
        mention_name = mention.get("name", "")
        if mention_name:
            # 更全面的@移除模式
            patterns = [
                f"@{mention_name}",
                f"@{mention_name} ",
                f" @{mention_name}",
                f" @{mention_name} "
            ]
            for pattern in patterns:
                cleaned_text = cleaned_text.replace(pattern, "")

    # 移除@_user_数字格式
    cleaned_text = re.sub(r'@_user_\d+', '', cleaned_text)
    # 清理多余的空格
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    return cleaned_text


def http_request_with_retry(req, context=None, max_retries=Config.MAX_RETRIES,
                            initial_delay=Config.INITIAL_RETRY_DELAY,
                            backoff_factor=Config.RETRY_BACKOFF_FACTOR,
                            timeout=None):
    """执行HTTP请求，使用指数级退避策略自动重试失败的请求"""
    retries = 0
    current_delay = initial_delay

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

                error_msg = str(e)
                if isinstance(e, urllib.error.HTTPError) and hasattr(e, 'code'):
                    error_msg = f"HTTP Error {e.code}: {e.reason}"
                    if hasattr(e, 'read'):
                        try:
                            error_content = e.read().decode('utf-8')
                            logger.error(f"错误详情: {error_content}")
                        except:
                            pass
                elif isinstance(e, socket.timeout):
                    error_msg = "Connection timed out"

                if retries <= max_retries:
                    logger.warning(f"请求失败: {error_msg}，将在{current_delay:.1f}秒后重试 ({retries}/{max_retries})")
                    time.sleep(current_delay)
                    current_delay *= backoff_factor
                else:
                    logger.error(f"请求失败，已达最大重试次数: {error_msg}")
                    raise e
    finally:
        if timeout and old_timeout is not None:
            socket.setdefaulttimeout(old_timeout)

    return None


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

    return json.dumps(data, ensure_ascii=False, indent=2)


def create_admin_token(user_id):
    """创建管理员token"""
    from models.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()

    # 失效该用户的所有历史token
    cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE user_id = ?", (user_id,))

    # 创建新token
    token = secrets.token_urlsafe(32).replace("_", "x")
    expired_at = datetime.now() + timedelta(minutes=Config.ADMIN_TOKEN_EXPIRE_MINUTES)

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

    from models.database import get_db_connection

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

    if not result['is_admin']:
        conn.close()
        return False, None

    # 更新最后活动时间和过期时间
    cursor.execute(
        "UPDATE admin_tokens SET last_active_at = CURRENT_TIMESTAMP WHERE token = ?",
        (token,)
    )

    new_expired_at = datetime.now() + timedelta(minutes=Config.ADMIN_TOKEN_EXPIRE_MINUTES)
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
    from models.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE admin_tokens SET is_valid = 0 WHERE token = ?", (token,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def init_static_dir():
    """初始化静态文件目录"""
    # 创建静态文件目录
    os.makedirs(Config.STATIC_DIR, exist_ok=True)

    # 创建CSS目录
    css_dir = os.path.join(Config.STATIC_DIR, 'css')
    os.makedirs(css_dir, exist_ok=True)

    # 创建模板目录
    templates_dir = 'templates'
    os.makedirs(templates_dir, exist_ok=True)

    logger.info("静态文件目录初始化完成")

