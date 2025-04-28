# 多平台扩展指南：支持企业微信、钉钉、Slack和Discord

本文档提供了如何将现有的飞书Dify机器人扩展到其他平台（企业微信、钉钉、Slack和Discord）的详细指南。

- [1. 企业微信扩展](#1-企业微信扩展)
- [2. 钉钉扩展](#2-钉钉扩展)
- [3. Slack扩展](#3-slack扩展)
- [4. Discord扩展](#4-discord扩展)
- [5. 统一消息处理器](#5-统一消息处理器)
- [6. 主程序集成](#6-主程序集成)
- [7. 数据库结构调整](#7-数据库结构调整)
- [8. 管理界面调整](#8-管理界面调整)
- [9. 部署说明](#9-部署说明)
- [10. 安全考虑](#10-安全考虑)
- [11. 测试](#11-测试)
- 
## 总体架构设计

为了支持多个平台，我们需要采用模块化的设计，主要包括以下几个核心组件：

1. **平台适配器（Platform Adapters）**：每个聊天平台需要一个独立的适配器，负责处理平台特定的事件和API调用
2. **消息处理器（Message Processor）**：统一的消息处理逻辑，与平台无关
3. **配置系统（Configuration System）**：支持多平台的配置管理
4. **统一的数据模型（Unified Data Models）**：跨平台的用户、会话和消息数据结构

## 1. 企业微信扩展

### 1.1 前期准备

1. 在[企业微信开发者平台](https://work.weixin.qq.com/wework_admin/frame#apps)创建应用
2. 获取必要的凭证信息：
   - 企业ID（corpid）
   - 应用Secret（corpsecret）
   - 应用ID（agentid）
   - Token和EncodingAESKey（用于消息加解密）

### 1.2 代码实现

创建`wework_adapter.py`文件：

```python
import json
import time
import hashlib
import requests
from bottle import Bottle, request, HTTPResponse
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
import logging

logger = logging.getLogger(__name__)

class WeworkAdapter:
    def __init__(self, config, message_processor):
        self.config = config
        self.message_processor = message_processor
        self.app = Bottle()
        self.token_cache = {'access_token': None, 'expires_at': 0}
        
        # 注册路由
        self.app.route('/webhook/wework', method=['GET', 'POST'], callback=self.handle_webhook)
        
    def handle_webhook(self):
        """处理企业微信回调请求"""
        # GET请求用于URL验证
        if request.method == 'GET':
            return self._handle_verification()
        
        # POST请求处理实际消息
        try:
            # 解密消息
            xml_data = self._decrypt_message(request.body.read())
            
            # 解析XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_data)
            
            msg_type = root.find('MsgType').text
            if msg_type == 'text':
                from_user_id = root.find('FromUserName').text
                content = root.find('Content').text
                
                # 调用统一的消息处理器
                def reply_func(response_text):
                    self.send_message(from_user_id, response_text)
                
                self.message_processor.process_message(from_user_id, content, reply_func, platform='wework')
            
            # 必须回复success，否则企业微信会重试
            return "success"
        
        except Exception as e:
            logger.error(f"处理企业微信消息出错: {str(e)}")
            return "success"  # 仍然返回success以避免重试
    
    def _handle_verification(self):
        """处理URL验证请求"""
        msg_signature = request.query.msg_signature
        timestamp = request.query.timestamp
        nonce = request.query.nonce
        echostr = request.query.echostr
        
        # 验证签名并解密echostr
        # 具体实现略（需要使用企业微信提供的加解密算法）
        decrypted_echostr = self._decrypt_echostr(echostr, msg_signature, timestamp, nonce)
        return decrypted_echostr
    
    def _decrypt_message(self, encrypted_xml):
        """解密消息内容"""
        # 企业微信的消息解密逻辑
        # 根据企业微信文档实现，略
        pass
    
    def _decrypt_echostr(self, echostr, msg_signature, timestamp, nonce):
        """解密验证字符串"""
        # 企业微信的echostr解密逻辑
        # 根据企业微信文档实现，略
        pass
    
    def get_access_token(self):
        """获取企业微信访问令牌"""
        now = time.time()
        
        # 检查缓存的token是否有效
        if self.token_cache['access_token'] and self.token_cache['expires_at'] > now:
            return self.token_cache['access_token']
        
        # 获取新token
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        params = {
            'corpid': self.config['WEWORK_CORP_ID'],
            'corpsecret': self.config['WEWORK_CORP_SECRET']
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            if data['errcode'] == 0:
                self.token_cache['access_token'] = data['access_token']
                self.token_cache['expires_at'] = now + data['expires_in'] - 200  # 提前200秒过期
                return self.token_cache['access_token']
            else:
                logger.error(f"获取企业微信access_token失败: {data}")
                return None
        except Exception as e:
            logger.error(f"获取企业微信access_token出错: {str(e)}")
            return None
    
    def send_message(self, user_id, content):
        """发送消息给用户"""
        token = self.get_access_token()
        if not token:
            return False
        
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        
        # 检测是否为Markdown格式
        if is_markdown(content):
            msg_type = "markdown"
        else:
            msg_type = "text"
        
        message = {
            "touser": user_id,
            "msgtype": msg_type,
            "agentid": self.config['WEWORK_AGENT_ID']
        }
        
        # 根据消息类型设置内容
        if msg_type == "text":
            message[msg_type] = {"content": content}
        else:
            message[msg_type] = {"content": content}
        
        try:
            response = requests.post(url, json=message)
            result = response.json()
            
            if result['errcode'] == 0:
                return True
            else:
                logger.error(f"发送企业微信消息失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送企业微信消息出错: {str(e)}")
            return False
```

### 1.3 配置

在主配置文件中添加企业微信相关配置：

```python
# 企业微信配置
WEWORK_ENABLED = os.environ.get("WEWORK_ENABLED", "false").lower() == "true"
WEWORK_CORP_ID = os.environ.get("WEWORK_CORP_ID", "")
WEWORK_CORP_SECRET = os.environ.get("WEWORK_CORP_SECRET", "")
WEWORK_AGENT_ID = os.environ.get("WEWORK_AGENT_ID", "")
WEWORK_TOKEN = os.environ.get("WEWORK_TOKEN", "")
WEWORK_ENCODING_AES_KEY = os.environ.get("WEWORK_ENCODING_AES_KEY", "")
```

## 2. 钉钉扩展

### 2.1 前期准备

1. 在[钉钉开发者平台](https://open-dev.dingtalk.com/)创建机器人应用
2. 获取必要的凭证信息：
   - AppKey和AppSecret
   - 加密TOKEN和加密密钥（用于验证和解密消息）

### 2.2 代码实现

创建`dingtalk_adapter.py`文件：

```python
import json
import time
import hmac
import hashlib
import base64
import requests
from bottle import Bottle, request, HTTPResponse
import logging

logger = logging.getLogger(__name__)

class DingtalkAdapter:
    def __init__(self, config, message_processor):
        self.config = config
        self.message_processor = message_processor
        self.app = Bottle()
        self.token_cache = {'access_token': None, 'expires_at': 0}
        
        # 注册路由
        self.app.route('/webhook/dingtalk', method=['POST'], callback=self.handle_webhook)
    
    def handle_webhook(self):
        """处理钉钉回调请求"""
        try:
            # 验证请求签名
            timestamp = request.headers.get('timestamp')
            sign = request.headers.get('sign')
            
            if not self._verify_signature(timestamp, sign):
                return HTTPResponse(status=401, body=json.dumps({"errcode": 401, "errmsg": "signature verification failed"}))
            
            # 解析请求体
            data = request.json
            
            # 处理不同类型的事件
            if 'text' in data.get('text', {}):
                user_id = data.get('senderStaffId')
                content = data['text']['content'].strip()
                conversation_id = data.get('conversationId')
                
                # 判断是否是@机器人的消息
                is_at_bot = False
                at_users = data.get('atUsers', [])
                for user in at_users:
                    if user.get('dingtalkId') == self.config.get('DINGTALK_BOT_USER_ID'):
                        is_at_bot = True
                        break
                
                # 如果是群聊，只处理@机器人的消息
                if conversation_id and '@' in content and not is_at_bot:
                    return HTTPResponse(status=200, body=json.dumps({"success": True}))
                
                # 移除@提及
                if '@' in content:
                    # 简单地移除所有@xxxx格式的文本
                    import re
                    content = re.sub(r'@[\w-\u9fa5]+\s*', '', content).strip()
                
                # 调用统一的消息处理器
                def reply_func(response_text):
                    if conversation_id:
                        self.send_group_message(conversation_id, response_text)
                    else:
                        self.send_message(user_id, response_text)
                
                self.message_processor.process_message(user_id, content, reply_func, platform='dingtalk')
            
            # 返回成功
            return HTTPResponse(status=200, body=json.dumps({"success": True}))
            
        except Exception as e:
            logger.error(f"处理钉钉消息出错: {str(e)}")
            return HTTPResponse(status=200, body=json.dumps({"success": True}))  # 仍然返回成功以避免钉钉重试
    
    def _verify_signature(self, timestamp, sign):
        """验证钉钉请求签名"""
        token = self.config['DINGTALK_TOKEN']
        string_to_sign = f"{timestamp}\n{token}"
        hmac_code = hmac.new(token.encode(), string_to_sign.encode(), digestmod=hashlib.sha256).digest()
        calculated_sign = base64.b64encode(hmac_code).decode()
        return calculated_sign == sign
    
    def get_access_token(self):
        """获取钉钉访问令牌"""
        now = time.time()
        
        # 检查缓存的token是否有效
        if self.token_cache['access_token'] and self.token_cache['expires_at'] > now:
            return self.token_cache['access_token']
        
        # 获取新token
        url = "https://oapi.dingtalk.com/gettoken"
        params = {
            'appkey': self.config['DINGTALK_APP_KEY'],
            'appsecret': self.config['DINGTALK_APP_SECRET']
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            if data['errcode'] == 0:
                self.token_cache['access_token'] = data['access_token']
                self.token_cache['expires_at'] = now + data['expires_in'] - 200  # 提前200秒过期
                return self.token_cache['access_token']
            else:
                logger.error(f"获取钉钉access_token失败: {data}")
                return None
        except Exception as e:
            logger.error(f"获取钉钉access_token出错: {str(e)}")
            return None
    
    def send_message(self, user_id, content):
        """发送消息给用户"""
        token = self.get_access_token()
        if not token:
            return False
        
        url = f"https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token={token}"
        
        # 检测是否为Markdown格式
        if is_markdown(content):
            msg_type = "markdown"
            msg_data = {
                "title": "消息通知",
                "text": content
            }
        else:
            msg_type = "text"
            msg_data = {
                "content": content
            }
        
        data = {
            "userid_list": user_id,
            "agent_id": self.config['DINGTALK_AGENT_ID'],
            "msg": {
                "msgtype": msg_type,
                msg_type: msg_data
            }
        }
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            
            if result['errcode'] == 0:
                return True
            else:
                logger.error(f"发送钉钉消息失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送钉钉消息出错: {str(e)}")
            return False
    
    def send_group_message(self, conversation_id, content):
        """发送群聊消息"""
        token = self.get_access_token()
        if not token:
            return False
        
        url = f"https://oapi.dingtalk.com/chat/send?access_token={token}"
        
        # 检测是否为Markdown格式
        if is_markdown(content):
            msg_type = "markdown"
            msg_data = {
                "title": "消息通知",
                "text": content
            }
        else:
            msg_type = "text"
            msg_data = {
                "content": content
            }
        
        data = {
            "chatid": conversation_id,
            "msg": {
                "msgtype": msg_type,
                msg_type: msg_data
            }
        }
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            
            if result['errcode'] == 0:
                return True
            else:
                logger.error(f"发送钉钉群聊消息失败: {result}")
                return False
        except Exception as e:
            logger.error(f"发送钉钉群聊消息出错: {str(e)}")
            return False
```

### 2.3 配置

在主配置文件中添加钉钉相关配置：

```python
# 钉钉配置
DINGTALK_ENABLED = os.environ.get("DINGTALK_ENABLED", "false").lower() == "true"
DINGTALK_APP_KEY = os.environ.get("DINGTALK_APP_KEY", "")
DINGTALK_APP_SECRET = os.environ.get("DINGTALK_APP_SECRET", "")
DINGTALK_AGENT_ID = os.environ.get("DINGTALK_AGENT_ID", "")
DINGTALK_TOKEN = os.environ.get("DINGTALK_TOKEN", "")  # 用于签名验证
DINGTALK_BOT_USER_ID = os.environ.get("DINGTALK_BOT_USER_ID", "")  # 机器人的UserId
```

## 3. Slack扩展

### 3.1 前期准备

1. 在[Slack API网站](https://api.slack.com/apps)创建一个新应用
2. 配置和获取必要的权限和凭证：
   - Bot Token（以xoxb-开头）
   - Signing Secret（用于验证请求）
   - 添加必要的Bot范围权限（如chat:write, im:history等）
   - 启用事件订阅并设置回调URL

### 3.2 代码实现

创建`slack_adapter.py`文件：

```python
import json
import time
import hmac
import hashlib
import requests
from bottle import Bottle, request, HTTPResponse
import logging

logger = logging.getLogger(__name__)

class SlackAdapter:
    def __init__(self, config, message_processor):
        self.config = config
        self.message_processor = message_processor
        self.app = Bottle()
        
        # 注册路由
        self.app.route('/webhook/slack/events', method=['POST'], callback=self.handle_events)
        self.app.route('/webhook/slack/interactivity', method=['POST'], callback=self.handle_interactivity)
    
    def handle_events(self):
        """处理Slack事件API回调"""
        # 验证请求签名
        if not self._verify_slack_signature():
            return HTTPResponse(status=401, body="Invalid signature")
        
        data = request.json
        
        # URL验证挑战
        if data.get('type') == 'url_verification':
            return HTTPResponse(
                status=200,
                body=json.dumps({"challenge": data['challenge']}),
                headers={'Content-Type': 'application/json'}
            )
        
        # 处理事件回调
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            event_type = event.get('type')
            
            # 消息事件
            if event_type == 'message':
                # 跳过机器人自己的消息
                if event.get('bot_id'):
                    return HTTPResponse(status=200, body="OK")
                
                user_id = event.get('user')
                channel_id = event.get('channel')
                text = event.get('text', '').strip()
                
                # 判断是否需要处理此消息
                if not text:
                    return HTTPResponse(status=200, body="OK")
                
                # 检查是否提及了机器人（在频道中）
                is_dm = channel_id.startswith('D')  # 私信渠道以D开头
                is_mentioned = f"<@{self.config['SLACK_BOT_USER_ID']}>" in text
                
                # 仅处理DM或@机器人的消息
                if not (is_dm or is_mentioned):
                    return HTTPResponse(status=200, body="OK")
                
                # 移除@机器人部分
                if is_mentioned:
                    text = text.replace(f"<@{self.config['SLACK_BOT_USER_ID']}>", "").strip()
                
                # 调用消息处理
                def reply_func(response_text):
                    self.send_message(channel_id, response_text)
                
                self.message_processor.process_message(user_id, text, reply_func, platform='slack')
        
        # 必须立即返回200
        return HTTPResponse(status=200, body="OK")
    
    def handle_interactivity(self):
        """处理交互操作（按钮点击等）"""
        # 验证请求签名
        if not self._verify_slack_signature():
            return HTTPResponse(status=401, body="Invalid signature")
        
        # 解析表单数据
        payload = json.loads(request.forms.get('payload'))
        
        # 处理不同类型的交互
        # ...（根据需要实现特定的交互逻辑）
        
        return HTTPResponse(status=200, body="OK")
    
    def _verify_slack_signature(self):
        """验证Slack请求签名"""
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        signature = request.headers.get('X-Slack-Signature', '')
        
        # 防止重放攻击，拒绝处理5分钟以前的请求
        if abs(time.time() - int(timestamp)) > 300:
            return False
        
        # 构建签名
        request_body = request.body.read()
        sig_basestring = f"v0:{timestamp}:{request_body.decode()}"
        
        # 使用Slack签名密钥计算HMAC
        my_signature = 'v0=' + hmac.new(
            self.config['SLACK_SIGNING_SECRET'].encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # 比较签名
        return hmac.compare_digest(my_signature, signature)
    
    def send_message(self, channel_id, content):
        """发送消息到Slack"""
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            'Authorization': f"Bearer {self.config['SLACK_BOT_TOKEN']}",
            'Content-Type': 'application/json'
        }
        
        # 判断是否为Markdown格式文本
        if is_markdown(content):
            # Slack使用mrkdwn格式
            payload = {
                'channel': channel_id,
                'text': content,
                'mrkdwn': True
            }
        else:
            payload = {
                'channel': channel_id,
                'text': content
            }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            data = response.json()
            
            if data.get('ok'):
                return True
            else:
                logger.error(f"发送Slack消息失败: {data}")
                return False
        except Exception as e:
            logger.error(f"发送Slack消息出错: {str(e)}")
            return False
```

### 3.3 配置

在主配置文件中添加Slack相关配置：

```python
# Slack配置
SLACK_ENABLED = os.environ.get("SLACK_ENABLED", "false").lower() == "true"
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")  # 以xoxb-开头的Bot Token
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
SLACK_BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "")  # 机器人的用户ID
```

## 4. Discord扩展

### 4.1 前期准备

1. 在[Discord Developer Portal](https://discord.com/developers/applications)创建一个新应用
2. 获取Bot Token和应用ID
3. 配置Bot权限并邀请它到您的服务器

### 4.2 代码实现

由于Discord Bot主要基于WebSocket连接而非Webhook，我们需要使用Discord API库。创建`discord_adapter.py`文件：

```python
import asyncio
import threading
import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class DiscordAdapter:
    def __init__(self, config, message_processor):
        self.config = config
        self.message_processor = message_processor
        
        # 创建Discord客户端
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True  # 需要在Discord开发者门户启用此权限
        
        self.client = commands.Bot(command_prefix="!", intents=intents)
        
        # 注册事件处理器
        @self.client.event
        async def on_ready():
            logger.info(f"Discord Bot已登录为 {self.client.user}")
            
        @self.client.event
        async def on_message(message):
            # 忽略自己的消息
            if message.author == self.client.user:
                return
            
            # 提取消息内容和上下文
            content = message.content
            author_id = str(message.author.id)
            channel_id = str(message.channel.id)
            
            # 判断是否需要处理
            # 1. 私信直接处理
            # 2. 频道中@机器人才处理
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = self.client.user in message.mentions
            
            if not (is_dm or is_mentioned):
                return
            
            # 移除@机器人部分
            if is_mentioned:
                content = content.replace(f"<@{self.client.user.id}>", "").strip()
                content = content.replace(f"<@!{self.client.user.id}>", "").strip()
            
            # 定义回复函数
            async def async_reply(response_text):
                # Discord消息长度限制
                if len(response_text) > 2000:
                    # 分块发送
                    chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                    for chunk in chunks:
                        await message.channel.send(chunk)
                else:
                    await message.channel.send(response_text)
            
            # 使用线程池处理消息，避免阻塞Discord事件循环
            def process_and_reply():
                def sync_reply(response_text):
                    # 创建异步任务并在事件循环中执行
                    asyncio.run_coroutine_threadsafe(async_reply(response_text), self.client.loop)
                
                # 调用通用消息处理器
                self.message_processor.process_message(author_id, content, sync_reply, platform='discord')
            
            # 启动处理线程
            threading.Thread(target=process_and_reply).start()
    
    def start(self):
        """启动Discord机器人"""
        token = self.config['DISCORD_BOT_TOKEN']
        if not token:
            logger.error("Discord Bot Token未设置，无法启动")
            return
        
        # 在新线程中运行机器人
        def run_bot():
            try:
                self.client.run(token)
            except Exception as e:
                logger.error(f"Discord Bot运行错误: {str(e)}")
        
        threading.Thread(target=run_bot, daemon=True).start()
        logger.info("Discord Bot已启动")
```

### 4.3 配置

在主配置文件中添加Discord相关配置：

```python
# Discord配置
DISCORD_ENABLED = os.environ.get("DISCORD_ENABLED", "false").lower() == "true"
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_APPLICATION_ID = os.environ.get("DISCORD_APPLICATION_ID", "")
```

## 5. 统一消息处理器

为了让各平台适配器能共享相同的消息处理逻辑，我们需要创建一个统一的消息处理器。创建`message_processor.py`文件：

```python
import logging
from . import db_operations

logger = logging.getLogger(__name__)

class MessageProcessor:
    def __init__(self, dify_client, config):
        self.dify_client = dify_client
        self.config = config
    
    def process_message(self, user_id, content, reply_func, platform='lark'):
        """
        处理用户消息的统一入口
        
        参数:
        - user_id: 平台上的用户ID
        - content: 消息内容
        - reply_func: 回复函数，用于发送回复
        - platform: 平台标识(lark/wework/dingtalk/slack/discord)
        """
        try:
            # 平台用户ID格式化（添加平台前缀）
            platform_user_id = f"{platform}:{user_id}"
            
            # 获取或创建用户
            db_user = db_operations.get_user(platform_user_id)
            if not db_user:
                db_operations.add_user(platform_user_id)
            
            # 检查是否为命令
            if self.is_command(content):
                cmd, args = self.parse_command(content)
                if cmd:
                    # 处理命令
                    return self.handle_command(cmd, args, platform_user_id, reply_func)
            
            # 普通消息处理
            # 获取用户会话
            session_id, conversation_id = db_operations.get_or_create_session(platform_user_id)
            model = db_operations.get_session_model(session_id)
            
            if not model:
                reply_func("当前没有设置默认模型，请先使用 `\\change-model [模型名称]` 命令选择一个模型，或联系管理员设置默认模型。")
                return True
            
            # 添加用户消息记录
            db_operations.add_message(session_id, platform_user_id, content, is_user=1)
            
            # 发送正在思考的提示
            reply_func("正在思考中，请稍候...")
            
            # 调用Dify API
            try:
                stream = None
                if model['dify_type'] == 'chatbot':
                    stream = self.dify_client.ask_chatbot(model, content, conversation_id, platform_user_id)
                elif model['dify_type'] == 'agent':
                    stream = self.dify_client.ask_agent(model, content, conversation_id, platform_user_id)
                elif model['dify_type'] == 'flow':
                    stream = self.dify_client.ask_flow(model, content, conversation_id, platform_user_id)
                else:
                    reply_func(f"不支持的模型类型：{model['dify_type']}")
                    return True
                
                # 检查stream是否有效
                if stream is None:
                    reply_func("无法连接到Dify API，请检查配置和网络连接。")
                    return True
                
                # 处理流式响应
                full_response = ""
                for chunk in self.dify_client.process_stream(stream, session_id, platform_user_id):
                    full_response += chunk
                
                reply_func(full_response)
                return True
                
            except Exception as e:
                logger.error(f"处理消息出错: {str(e)}")
                reply_func(f"处理消息时出错: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"消息处理器全局错误: {str(e)}")
            reply_func("抱歉，处理您的消息时发生了错误，请稍后再试。")
            return False
    
    def is_command(self, text):
        """检查是否是命令"""
        return text.startswith("\\") or text.startswith("/")
    
    def parse_command(self, text):
        """解析命令和参数"""
        if not self.is_command(text):
            return None, None
        
        # 移除前导符号
        cmd_text = text[1:].strip()
        
        # 分割命令和参数
        parts = cmd_text.split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        
        return cmd, args
    
    def handle_command(self, cmd, args, user_id, reply_func):
        """处理命令"""
        # 调用现有的命令处理功能
        # 注意: 您需要修改现有的handle_command函数以支持跨平台用户ID
        
        # 这里假设您有一个跨平台的命令处理函数
        from commands import handle_cross_platform_command
        return handle_cross_platform_command(cmd, args, user_id, reply_func)
```

## 6. 主程序集成

修改主程序，集成所有平台适配器：

```python
def main():
    """主入口函数"""
    # 初始化数据库
    init_database()
    
    # 初始化静态文件目录
    init_static_dir()
    
    # 创建消息处理器
    message_processor = MessageProcessor(dify_client, config)
    
    # 飞书适配器
    from lark_adapter import LarkAdapter
    lark_adapter = LarkAdapter(config, message_processor)
    app.merge(lark_adapter.app)
    
    # 根据配置启用其他平台
    if config.get('WEWORK_ENABLED'):
        from wework_adapter import WeworkAdapter
        wework_adapter = WeworkAdapter(config, message_processor)
        app.merge(wework_adapter.app)
        
    if config.get('DINGTALK_ENABLED'):
        from dingtalk_adapter import DingtalkAdapter
        dingtalk_adapter = DingtalkAdapter(config, message_processor)
        app.merge(dingtalk_adapter.app)
        
    if config.get('SLACK_ENABLED'):
        from slack_adapter import SlackAdapter
        slack_adapter = SlackAdapter(config, message_processor)
        app.merge(slack_adapter.app)
        
    if config.get('DISCORD_ENABLED'):
        from discord_adapter import DiscordAdapter
        discord_adapter = DiscordAdapter(config, message_processor)
        discord_adapter.start()
    
    # 启动服务
    logger.info("多平台Dify机器人服务启动")
    app.run(host='0.0.0.0', port=8080, debug=False)

if __name__ == '__main__':
    main()
```

## 7. 数据库结构调整

为了支持多平台用户，我们需要调整数据库结构，主要是更新用户识别方式：

```sql
-- 修改用户表的user_id字段说明
-- 新的user_id格式: platform:original_id，例如 lark:ou_123, wework:userid123
ALTER TABLE users RENAME TO users_old;
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,  -- 格式为 platform:id，如 lark:ou_123
    platform TEXT NOT NULL,        -- 用户来源平台
    platform_user_id TEXT NOT NULL, -- 平台原始用户ID
    name TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 迁移数据
INSERT INTO users (user_id, platform, platform_user_id, name, is_admin, created_at)
SELECT 'lark:' || user_id, 'lark', user_id, name, is_admin, created_at
FROM users_old;

-- 创建索引
CREATE INDEX idx_users_platform_id ON users(platform, platform_user_id);
```

## 8. 管理界面调整

更新管理界面，支持多平台用户管理：

1. 添加平台选择器到用户管理页面
2. 显示用户来源平台
3. 添加按平台过滤功能

```html
<!-- 用户管理页面片段 -->
<div class="filter-section">
    <label for="platform-filter">按平台筛选:</label>
    <select id="platform-filter" onchange="filterUsers()">
        <option value="all">所有平台</option>
        <option value="lark">飞书</option>
        <option value="wework">企业微信</option>
        <option value="dingtalk">钉钉</option>
        <option value="slack">Slack</option>
        <option value="discord">Discord</option>
    </select>
</div>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>平台</th>
            <th>用户ID</th>
            <th>用户名</th>
            <th>角色</th>
            <th>创建时间</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for user in users:
        <tr class="user-row" data-platform="{{user['platform']}}">
            <td>{{user['id']}}</td>
            <td>{{user['platform']}}</td>
            <td>{{user['platform_user_id']}}</td>
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
</table>

<script>
function filterUsers() {
    var platform = document.getElementById('platform-filter').value;
    var rows = document.getElementsByClassName('user-row');
    
    for (var i = 0; i < rows.length; i++) {
        if (platform === 'all' || rows[i].getAttribute('data-platform') === platform) {
            rows[i].style.display = '';
        } else {
            rows[i].style.display = 'none';
        }
    }
}
</script>
```

## 9. 部署说明

### 9.1 环境变量配置

使用环境变量来配置各平台的参数：

```
# 基础配置
VERIFICATION_TOKEN=xxxx
APP_ID=xxxx
APP_SECRET=xxxx
BOT_NAME=DifyBot
BOT_OPEN_ID=xxxx

# 企业微信配置
WEWORK_ENABLED=false
WEWORK_CORP_ID=xxxx
WEWORK_CORP_SECRET=xxxx
WEWORK_AGENT_ID=xxxx
WEWORK_TOKEN=xxxx
WEWORK_ENCODING_AES_KEY=xxxx

# 钉钉配置
DINGTALK_ENABLED=false
DINGTALK_APP_KEY=xxxx
DINGTALK_APP_SECRET=xxxx
DINGTALK_AGENT_ID=xxxx
DINGTALK_TOKEN=xxxx
DINGTALK_BOT_USER_ID=xxxx

# Slack配置
SLACK_ENABLED=false
SLACK_BOT_TOKEN=xoxb-xxxx
SLACK_SIGNING_SECRET=xxxx
SLACK_BOT_USER_ID=xxxx

# Discord配置
DISCORD_ENABLED=false
DISCORD_BOT_TOKEN=xxxx
DISCORD_APPLICATION_ID=xxxx
```

### 9.2 Docker 部署

创建Dockerfile：

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录和日志目录
RUN mkdir -p /data /logs

# 设置工作目录和数据卷
VOLUME ["/data", "/logs"]

# 设置环境变量
ENV DB_PATH=/data/lark_dify_bot.db
ENV LOG_PATH=/logs/lark_bot.log

# 暴露端口
EXPOSE 8080

# 启动应用
CMD ["python", "app.py"]
```

创建docker-compose.yml：

```yaml
version: '3'

services:
  dify-bot:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
      - ./logs:/logs
    env_file:
      - .env
    restart: unless-stopped
```

### 9.3 平台回调URL设置

各平台的回调URL设置：

- 飞书: `https://your-domain.com/webhook/event`
- 企业微信: `https://your-domain.com/webhook/wework`
- 钉钉: `https://your-domain.com/webhook/dingtalk`
- Slack: `https://your-domain.com/webhook/slack/events`
- Discord: 不需要回调URL，使用Bot Token直接建立WebSocket连接

## 10. 安全考虑

1. **请求验证**: 每个平台都有自己的请求验证机制，确保正确实现
2. **数据隔离**: 使用平台前缀区分不同平台的用户
3. **令牌管理**: 安全存储各平台的令牌和密钥
4. **速率限制**: 实现速率限制，防止滥用
5. **错误处理**: 优雅处理错误，不暴露敏感信息

## 11. 测试

为每个平台创建简单的测试脚本：

```python
# test_wework.py
import requests
import hashlib
import time
import json

# 配置信息
TEST_URL = "http://localhost:8080/webhook/wework"
TEST_CORP_ID = "test_corp_id"
TEST_TOKEN = "test_token"

# 模拟企业微信消息
data = {
    "ToUserName": "企业号",
    "FromUserName": "test_user",
    "CreateTime": int(time.time()),
    "MsgType": "text",
    "Content": "你好",
    "MsgId": "123456789",
    "AgentID": "1"
}

# 发送请求
response = requests.post(TEST_URL, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
```

为其他平台创建类似的测试脚本。

## 结论

通过实现这些适配器和修改现有代码，您可以将Dify机器人扩展到多个平台，同时保持核心业务逻辑的一致性。每个平台都有其特定的API和消息格式，但通过抽象公共部分并使用适配器模式，可以实现代码的模块化和可维护性。

这个扩展过程需要对各平台API有较深入的了解，因此建议在开始实施前先仔细阅读每个平台的开发文档。
