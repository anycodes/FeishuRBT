# 开发者文档

欢迎来到飞书Dify机器人项目的开发者文档！本文档将帮助您了解项目结构、架构设计以及如何进行二次开发。

## 目录

- [项目概述](#项目概述)
- [目录结构](#目录结构)
- [架构设计](#架构设计)
- [核心模块](#核心模块)
- [二次开发指南](#二次开发指南)
- [代码规范](#代码规范)
- [测试指南](#测试指南)
- [部署指南](#部署指南)

## 项目概述

这是一个集成了飞书机器人和Dify AI服务的智能对话系统，具有以下核心功能：

- 🤖 飞书机器人集成（支持私聊和群聊）
- 🧠 Dify AI模型集成（支持Chatbot、Agent、Flow）
- 📝 自定义命令系统
- 🔗 Webhook事件通知
- 📊 Web管理界面
- 💾 数据库迁移系统
- 📸 图片处理缓存

## 目录结构

```
lark-dify-bot/
├── app.py                      # 应用主入口
├── config.py                   # 配置管理
├── requirements.txt            # Python依赖
├── Dockerfile                  # Docker镜像构建
├── docker-compose.yml         # Docker编排配置
├── .env                        # 环境变量（需自行创建）
├── .dockerignore              # Docker忽略文件
├── docs/                       # 文档目录
│   ├── README.md              # 用户文档
│   └── dev/                   # 开发者文档
├── models/                     # 数据模型层
│   ├── __init__.py
│   ├── database.py            # 数据库连接和基础操作
│   ├── migration.py           # 数据库迁移系统
│   ├── user.py               # 用户相关操作
│   ├── model.py              # AI模型管理
│   ├── command.py            # 命令管理
│   ├── webhook.py            # Webhook管理
│   └── session.py            # 会话管理
├── handlers/                   # 请求处理层
│   ├── __init__.py
│   ├── lark_handler.py       # 飞书事件处理
│   ├── command_handler.py    # 命令处理逻辑
│   ├── webhook_handler.py    # Webhook处理
│   └── admin_handler.py      # 管理界面处理
├── services/                   # 服务层
│   ├── __init__.py
│   ├── dify_service.py       # Dify API服务
│   ├── lark_service.py       # 飞书API服务
│   └── cache_service.py      # 缓存服务
├── utils/                      # 工具层
│   ├── __init__.py
│   ├── helpers.py            # 通用工具函数
│   └── decorators.py         # 装饰器
├── templates/                  # 前端模板
│   ├── layout.tpl            # 布局模板
│   ├── models.tpl            # 模型管理
│   ├── commands.tpl          # 命令管理
│   ├── webhooks.tpl          # Webhook管理
│   └── ...                   # 其他页面模板
└── static/                     # 静态资源
    └── css/
        └── style.css         # 样式文件
```

## 架构设计

### 分层架构

```
┌─────────────────────────────────────────┐
│               用户界面层                │
│  飞书客户端 ←→ Web管理界面 ←→ Webhook API │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│               请求处理层                │
│   lark_handler ← command_handler →      │
│   admin_handler ← webhook_handler       │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│               业务逻辑层                │
│   用户管理 ← 模型管理 → 命令管理        │
│   会话管理 ← Webhook管理                │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│               服务层                    │
│   dify_service ← lark_service →         │
│   cache_service                         │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│               数据持久层                │
│   SQLite数据库 ← 文件系统缓存           │
└─────────────────────────────────────────┘
```

### 数据流向

1. **用户消息流向**：
   ```
   飞书客户端 → lark_handler → command_handler → dify_service → 数据库
                                      ↓
   飞书客户端 ← lark_service ← command_handler ← dify_service
   ```

2. **Webhook流向**：
   ```
   外部系统 → webhook_handler → dify_service → lark_service → 飞书客户端
                      ↓
   数据库（日志记录）
   ```

3. **管理界面流向**：
   ```
   Web浏览器 → admin_handler → models/* → 数据库
                      ↓
   Web浏览器 ← templates/* ← admin_handler
   ```

## 核心模块

### 1. 配置管理 (config.py)

负责管理所有配置参数，包括：
- 飞书应用配置
- API配置
- 数据库配置
- 缓存配置

### 2. 数据模型层 (models/)

#### database.py
- 数据库连接管理
- 基础数据库操作
- UTF-8编码处理

#### migration.py
- 数据库版本控制
- 向后兼容的迁移系统
- 数据完整性验证

#### user.py
- 用户信息管理
- 管理员权限控制
- 用户创建和更新

#### model.py
- AI模型配置管理
- 模型增删改查
- 参数验证

#### command.py
- 自定义命令管理
- 触发器匹配
- 命令参数处理

#### webhook.py
- Webhook配置管理
- 订阅关系管理
- Token生成和验证

#### session.py
- 会话状态管理
- 配置项管理
- 消息记录

### 3. 请求处理层 (handlers/)

#### lark_handler.py
- 飞书事件接收和解析
- 消息类型判断
- 用户身份验证
- @机器人识别和处理

#### command_handler.py
- 命令解析和路由
- 权限验证
- 业务逻辑调用

#### webhook_handler.py
- Webhook请求处理
- AI处理模式切换
- 订阅者通知

#### admin_handler.py
- Web管理界面路由
- 表单处理
- 权限验证

### 4. 服务层 (services/)

#### dify_service.py
- Dify API调用
- 流式响应处理
- 错误处理和重试

#### lark_service.py
- 飞书API调用
- 消息发送
- Token管理

#### cache_service.py
- 图片缓存管理
- 过期清理
- 存储优化

### 5. 工具层 (utils/)

#### helpers.py
- 通用工具函数
- 数据格式转换
- Token管理

#### decorators.py
- 权限验证装饰器
- 请求处理装饰器

## 二次开发指南

### 环境准备

1. **Python环境**：
   ```bash
   # 推荐使用Python 3.9+
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # venv\Scripts\activate   # Windows
   
   pip install -r requirements.txt
   ```

2. **配置环境变量**：
   ```bash
   cp .env.example .env
   # 编辑.env文件，填入你的配置
   ```

3. **初始化数据库**：
   ```bash
   python app.py
   ```

### 常见开发场景

#### 1. 添加新的AI模型类型

1. 在 `config.py` 中添加新的模型类型：
   ```python
   VALID_MODEL_TYPES = ["chatbot", "agent", "flow", "your_new_type"]
   ```

2. 在 `services/dify_service.py` 中添加处理函数：
   ```python
   def ask_dify_your_new_type(model, query, conversation_id=None, user_id="default_user", streaming=True):
       # 实现您的逻辑
       pass
   ```

3. 在 `handlers/command_handler.py` 中添加调用：
   ```python
   elif model['dify_type'] == 'your_new_type':
       stream = ask_dify_your_new_type(model, content, conversation_id, user_id)
   ```

#### 2. 添加新的命令

1. 在 `handlers/command_handler.py` 中的 `handle_command` 函数添加：
   ```python
   elif cmd == "your-command":
       handle_your_command(args, sender_id, reply_func)
       return True
   ```

2. 实现处理函数：
   ```python
   def handle_your_command(args, sender_id, reply_func):
       # 实现您的命令逻辑
       reply_func("命令执行结果")
   ```

3. 在 `show_help` 函数中添加帮助信息。

#### 3. 添加新的管理页面

1. 在 `handlers/admin_handler.py` 中添加路由：
   ```python
   @app.get('/admin/your-feature')
   @require_admin
   def admin_your_feature(user_id):
       # 获取数据
       data = get_your_data()
       return template('your_feature', data=data)
   ```

2. 创建模板文件 `templates/your_feature.tpl`：
   ```html
   % rebase('layout.tpl', title='您的功能')
   <h2>您的功能</h2>
   <!-- 您的HTML内容 -->
   ```

3. 在 `templates/layout.tpl` 中添加导航链接。

#### 4. 添加数据库迁移

1. 在 `models/migration.py` 的 `get_available_migrations` 中添加：
   ```python
   ("1.6.0", {"name": "添加新功能表", "func": self.migrate_1_6_0}),
   ```

2. 实现迁移函数：
   ```python
   def migrate_1_6_0(self, cursor):
       """1.6.0 - 添加新功能表"""
       if not self.table_exists(cursor, "your_table"):
           cursor.execute('''
           CREATE TABLE your_table (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT NOT NULL,
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )
           ''')
           logger.info("创建your_table表")
   ```

#### 5. 扩展Webhook功能

1. 在 `handlers/webhook_handler.py` 中修改处理逻辑：
   ```python
   def handle_ai_processing(webhook, data):
       # 添加您的自定义处理逻辑
       if webhook.get('custom_processing'):
           return your_custom_processing(data)
       
       # 原有逻辑...
   ```

2. 在数据库中添加相应字段（通过迁移）。

### 开发最佳实践

#### 1. 代码结构
- 遵循分层架构，不要跨层调用
- 每个函数职责单一
- 使用类型提示（推荐）

#### 2. 错误处理
```python
try:
    # 业务逻辑
    result = some_operation()
    return result
except SpecificException as e:
    logger.error(f"具体错误描述: {e}")
    # 处理特定错误
except Exception as e:
    logger.error(f"未预期错误: {e}")
    logger.error(traceback.format_exc())
    # 通用错误处理
```

#### 3. 日志记录
```python
import logging
logger = logging.getLogger(__name__)

# 使用不同级别的日志
logger.debug("调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息")
```

#### 4. 数据库操作
```python
def your_database_operation():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SQL语句", (参数,))
        conn.commit()
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"数据库操作失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
```

## 代码规范

### Python代码规范

1. **遵循PEP 8**
2. **命名规范**：
   - 函数和变量使用下划线命名：`user_name`
   - 类使用驼峰命名：`DatabaseMigration`
   - 常量使用全大写：`MAX_RETRIES`

3. **导入顺序**：
   ```python
   # 标准库
   import os
   import json
   
   # 第三方库
   from bottle import Bottle
   
   # 本地模块
   from config import Config
   from models.user import get_user
   ```

4. **文档字符串**：
   ```python
   def function_name(param1, param2):
       """
       函数简短描述
       
       Args:
           param1 (str): 参数1描述
           param2 (int): 参数2描述
           
       Returns:
           bool: 返回值描述
       """
       pass
   ```

### 前端代码规范

1. **HTML模板**：
   - 使用语义化标签
   - 保持结构清晰
   - 合理使用CSS类

2. **CSS**：
   - 使用有意义的类名
   - 避免使用!important
   - 保持响应式设计

## 测试指南

### 单元测试

创建 `tests/` 目录进行测试：

```python
# tests/test_user.py
import unittest
from models.user import get_user, add_user

class TestUser(unittest.TestCase):
    def test_add_user(self):
        # 测试用户添加
        result = add_user("test_user", "测试用户")
        self.assertTrue(result)
    
    def test_get_user(self):
        # 测试用户获取
        user = get_user("test_user")
        self.assertIsNotNone(user)
        self.assertEqual(user['name'], "测试用户")

if __name__ == '__main__':
    unittest.main()
```

### 集成测试

```python
# tests/test_integration.py
import requests
import unittest

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.base_url = "http://localhost:8080"
    
    def test_ping(self):
        response = requests.get(f"{self.base_url}/ping")
        self.assertEqual(response.text, "pong")
    
    def test_webhook(self):
        # 测试webhook接口
        webhook_url = f"{self.base_url}/api/webhook/test_token"
        data = {"message": "test"}
        response = requests.post(webhook_url, json=data)
        # 验证响应
```

### 手动测试

1. **飞书机器人测试**：
   - 发送各种类型的消息
   - 测试@机器人功能
   - 测试命令执行

2. **管理界面测试**：
   - 测试各个管理功能
   - 测试权限控制
   - 测试表单验证

3. **Webhook测试**：
   - 使用curl或Postman测试
   - 验证不同数据格式
   - 测试错误处理

## 部署指南

### 开发环境

```bash
# 直接运行
python app.py

# 或使用Docker
docker-compose up -d
```

### 生产环境

1. **使用Docker Compose**：
   ```bash
   # 构建镜像
   docker-compose build
   
   # 启动服务
   docker-compose up -d
   
   # 查看日志
   docker-compose logs -f
   ```

2. **使用反向代理（推荐）**：
   - 使用Nginx作为反向代理
   - 配置SSL证书
   - 设置请求限流

3. **监控和日志**：
   - 配置日志轮转
   - 监控系统资源
   - 设置告警机制

### 性能优化

1. **数据库优化**：
   - 定期清理过期数据
   - 添加必要的索引
   - 监控查询性能

2. **缓存优化**：
   - 合理设置缓存过期时间
   - 定期清理无效缓存
   - 监控缓存命中率

3. **API优化**：
   - 使用连接池
   - 设置合理的超时时间
   - 实现断路器模式

## 常见问题

### 开发环境问题

1. **依赖安装失败**：
   - 检查Python版本
   - 使用国内镜像源
   - 更新pip版本

2. **数据库迁移失败**：
   - 检查数据库文件权限
   - 备份原有数据
   - 查看详细错误日志

3. **飞书回调失败**：
   - 检查网络连通性
   - 验证Token配置
   - 查看飞书开发者后台

### 生产环境问题

1. **内存占用过高**：
   - 检查是否有内存泄漏
   - 优化缓存策略
   - 调整工作进程数

2. **响应速度慢**：
   - 优化数据库查询
   - 添加缓存层
   - 检查网络延迟

## 贡献指南

1. **Fork项目**
2. **创建功能分支**：`git checkout -b feature/your-feature`
3. **提交更改**：`git commit -am 'Add some feature'`
4. **推送分支**：`git push origin feature/your-feature`
5. **创建Pull Request**

### 提交规范

```
type(scope): subject

body

footer
```

类型说明：
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式修改
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建工具或辅助工具的变动

## 联系方式

如有问题，欢迎通过以下方式联系：

- 提交Issue
- 发起Discussion
- 邮件联系

---

感谢您的贡献！🎉
```

## docs/dev/api.md

```markdown
# API文档

本文档描述了飞书Dify机器人项目的各种API接口。

## 目录

- [飞书事件接口](#飞书事件接口)
- [Webhook API](#webhook-api)
- [管理界面API](#管理界面api)
- [内部API](#内部api)

## 飞书事件接口

### POST /webhook/event

接收飞书平台的事件回调。

**请求头**：
```
Content-Type: application/json
```

**请求体**：
```json
{
  "schema": "2.0",
  "header": {
    "event_id": "xxxx",
    "event_type": "im.message.receive_v1",
    "create_time": "1234567890",
    "token": "your_verification_token",
    "app_id": "your_app_id",
    "tenant_key": "your_tenant_key"
  },
  "event": {
    "sender": {
      "sender_id": {
        "union_id": "xxxx",
        "user_id": "xxxx",
        "open_id": "xxxx"
      },
      "sender_type": "user",
      "tenant_key": "xxxx"
    },
    "message": {
      "message_id": "xxxx",
      "root_id": "xxxx",
      "parent_id": "xxxx",
      "create_time": "1234567890",
      "chat_id": "xxxx",
      "chat_type": "p2p",
      "message_type": "text",
      "content": "{\"text\":\"hello world\"}",
      "mentions": []
    }
  }
}
```

**响应**：
```json
{
  "code": 0,
  "msg": "success"
}
```

## Webhook API

### POST /api/webhook/{token}

外部系统通过此接口向机器人发送事件通知。

**路径参数**：
- `token`: Webhook的API Token

**请求头**：
```
Content-Type: application/json
```

**请求体示例**：
```json
{
  "message": "GitHub仓库有新的Push",
  "repository": "lark-dify-bot",
  "author": "developer",
  "commits": 3,
  "url": "https://github.com/user/repo/commit/xxx"
}
```

**响应**：
```json
{
  "success": true,
  "message": "AI处理成功，已发送给 2/2 个订阅者"
}
```

**错误响应**：
```json
{
  "error": "无效的webhook token"
}
```

## 管理界面API

### 模型管理

#### GET /admin/models
获取所有模型列表

#### POST /admin/models/add
添加新模型

**请求体**：
```
name=GPT-4&description=OpenAI GPT-4模型&dify_url=https://api.dify.ai&dify_type=chatbot&api_key=xxx
```

#### GET/POST /admin/models/edit/{id}
编辑指定模型

#### GET /admin/models/delete/{id}
删除指定模型

### 命令管理

#### GET /admin/commands
获取所有命令列表

#### POST /admin/commands/add
添加新命令

#### GET/POST /admin/commands/edit/{id}
编辑指定命令

#### GET /admin/commands/delete/{id}
删除指定命令

### Webhook管理

#### GET /admin/webhooks
获取所有Webhook列表

#### POST /admin/webhooks/add
添加新Webhook

#### GET/POST /admin/webhooks/edit/{id}
编辑指定Webhook

#### GET /admin/webhooks/delete/{id}
删除指定Webhook

#### GET /admin/webhooks/regenerate-token/{id}
重新生成Webhook Token

**查询参数**：
- `type`: `api` 或 `config`

## 内部API

### 健康检查

#### GET /ping
系统健康检查

**响应**：
```
pong
```

### 静态资源

#### GET /static/{filepath}
提供静态文件服务

## 错误处理

所有API都遵循统一的错误处理格式：

**HTTP状态码**：
- `200`: 成功
- `400`: 请求参数错误
- `401`: 未授权
- `403`: 权限不足
- `404`: 资源不存在
- `500`: 服务器内部错误

**错误响应格式**：
```json
{
  "error": "错误描述",
  "code": "ERROR_CODE",
  "details": "详细错误信息"
}
```

## 认证和授权

### 飞书事件认证
使用Verification Token进行验证。

### 管理界面认证
使用基于时间的临时Token进行认证：
1. 通过飞书发送 `\admin-login` 命令获取登录链接
2. 点击链接自动设置认证Cookie
3. Token有效期为60分钟，活动时会自动续期

### Webhook认证
使用随机生成的API Token进行认证。

## 限流和安全

1. **请求去重**：使用事件ID防止重复处理
2. **Token验证**：所有敏感接口都需要Token验证
3. **输入验证**：严格验证所有输入参数
4. **SQL注入防护**：使用参数化查询
5. **XSS防护**：模板自动转义HTML内容

## 开发和调试

### 本地测试
```bash
# 启动服务
python app.py

# 测试健康检查
curl http://localhost:8080/ping

# 测试Webhook（需要有效token）
curl -X POST http://localhost:8080/api/webhook/your_token \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

### 日志级别
- `DEBUG`: 详细调试信息
- `INFO`: 一般信息
- `WARNING`: 警告信息
- `ERROR`: 错误信息

### 监控指标
- API响应时间
- 错误率
- 并发连接数
- 数据库查询性能
- 内存使用情况
```

## docs/dev/database.md

```markdown
# 数据库设计文档

本文档描述了飞书Dify机器人项目的数据库设计和数据模型。

## 数据库概述

项目使用SQLite作为数据库，支持完整的迁移系统，确保向后兼容性。

## 表结构设计

### 用户表 (users)

存储用户基本信息和权限。

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,           -- 飞书用户ID
    name TEXT,                              -- 用户名称
    is_admin INTEGER DEFAULT 0,             -- 是否为管理员(0/1)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**索引**：
```sql
CREATE INDEX idx_users_user_id ON users (user_id);
```

### 模型表 (models)

存储AI模型配置信息。

```sql
CREATE TABLE models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,              -- 模型名称
    description TEXT,                       -- 模型描述
    dify_url TEXT NOT NULL,                 -- Dify API地址
    dify_type TEXT NOT NULL,                -- 模型类型(chatbot/agent/flow)
    api_key TEXT NOT NULL,                  -- API密钥
    parameters TEXT,                        -- 额外参数(JSON格式)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 命令表 (commands)

存储自定义命令配置。

```sql
CREATE TABLE commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                     -- 命令名称
    description TEXT,                       -- 命令描述
    trigger TEXT UNIQUE NOT NULL,           -- 触发词
    model_id INTEGER,                       -- 关联模型ID
    parameters TEXT,                        -- 命令参数(JSON格式)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models (id)
);
```

### 配置表 (configs)

存储系统配置项。

```sql
CREATE TABLE configs (
    key TEXT PRIMARY KEY,                   -- 配置键
    value TEXT,                            -- 配置值
    description TEXT,                      -- 配置描述
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**预设配置**：
- `default_model`: 默认模型ID
- `session_timeout`: 会话超时时间(分钟)

### 会话表 (sessions)

存储用户会话状态。

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,                  -- 用户ID
    model_id INTEGER,                       -- 使用的模型ID
    conversation_id TEXT,                   -- Dify对话ID
    command_id INTEGER DEFAULT NULL,        -- 关联的命令ID
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 最后活动时间
    is_active INTEGER DEFAULT 1,           -- 是否活跃(0/1)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models (id)
);
```

**索引**：
```sql
CREATE INDEX idx_sessions_user_id ON sessions (user_id);
CREATE INDEX idx_sessions_active ON sessions (user_id, is_active, last_active_at);
```

### 消息记录表 (messages)

存储对话消息历史。

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,                     -- 会话ID
    user_id TEXT NOT NULL,                  -- 用户ID
    content TEXT,                          -- 消息内容
    is_user INTEGER DEFAULT 1,             -- 是否为用户消息(0/1)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id)
);
```

**索引**：
```sql
CREATE INDEX idx_messages_session_id ON messages (session_id);
```

### 管理员令牌表 (admin_tokens)

存储管理员登录令牌。

```sql
CREATE TABLE admin_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,             -- 登录令牌
    user_id TEXT NOT NULL,                  -- 用户ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 最后活动时间
    expired_at TIMESTAMP,                   -- 过期时间
    is_valid INTEGER DEFAULT 1             -- 是否有效(0/1)
);
```

**索引**：
```sql
CREATE INDEX idx_admin_tokens_valid ON admin_tokens (user_id, is_valid, expired_at);
```

### Webhook表 (webhooks)

存储Webhook配置。

```sql
CREATE TABLE webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                     -- Webhook名称
    description TEXT,                       -- 描述
    token TEXT UNIQUE NOT NULL,             -- API令牌
    config_token TEXT UNIQUE NOT NULL,      -- 配置令牌(用户订阅用)
    model_id INTEGER,                       -- 关联模型ID
    prompt_template TEXT,                   -- 提示模板
    bypass_ai INTEGER DEFAULT 0,           -- 是否绕过AI处理(0/1)
    fallback_mode TEXT DEFAULT 'original', -- 失败回退模式
    fallback_message TEXT DEFAULT NULL,    -- 自定义回退消息
    is_active INTEGER DEFAULT 1,           -- 是否启用(0/1)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES models (id)
);
```

### Webhook订阅表 (webhook_subscriptions)

存储Webhook订阅关系。

```sql
CREATE TABLE webhook_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER NOT NULL,            -- Webhook ID
    target_type TEXT NOT NULL,              -- 目标类型(user/chat)
    target_id TEXT NOT NULL,                -- 目标ID
    created_by TEXT,                        -- 创建者ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (webhook_id) REFERENCES webhooks (id),
    UNIQUE(webhook_id, target_type, target_id)  -- 防止重复订阅
);
```

**索引**：
```sql
CREATE INDEX idx_webhook_subscriptions_webhook_id ON webhook_subscriptions (webhook_id);
```

### Webhook调用日志表 (webhook_logs)

存储Webhook调用记录。

```sql
CREATE TABLE webhook_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER,                     -- Webhook ID
    request_data TEXT,                      -- 请求数据
    response TEXT,                         -- 响应内容
    status INTEGER,                        -- HTTP状态码
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (webhook_id) REFERENCES webhooks (id)
);
```

**索引**：
```sql
CREATE INDEX idx_webhook_logs_webhook_id ON webhook_logs (webhook_id, created_at);
```

### 图片缓存表 (image_cache)

存储临时图片缓存信息。

```sql
CREATE TABLE image_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,                  -- 用户ID
    image_path TEXT NOT NULL,               -- 图片路径
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL          -- 过期时间
);
```

**索引**：
```sql
CREATE INDEX idx_image_cache_user_expires ON image_cache (user_id, expires_at);
```

### 迁移记录表 (db_migrations)

跟踪数据库迁移版本。

```sql
CREATE TABLE db_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT UNIQUE NOT NULL,           -- 迁移版本
    name TEXT NOT NULL,                     -- 迁移名称
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 应用时间
    checksum TEXT                          -- 校验和(预留)
);
```

## 数据关系图

```
users (用户)
├── sessions (会话) ─── models (模型)
│   └── messages (消息)
├── admin_tokens (管理员令牌)
└── webhook_subscriptions (订阅) ─── webhooks (Webhook) ─── models (模型)
                                         └── webhook_logs (日志)

commands (命令) ─── models (模型)
configs (配置)
image_cache (图片缓存)
db_migrations (迁移记录)
```

## 迁移系统

### 版本管理

迁移系统使用语义化版本号管理数据库结构变更：

- `1.0.0`: 初始数据库结构
- `1.1.0`: 添加会话扩展字段
- `1.2.0`: 添加Webhook支持
- `1.3.0`: 添加图片缓存支持
- `1.4.0`: 添加Webhook回退机制
- `1.5.0`: 优化索引和性能

### 迁移流程

1. **检查当前版本**
2. **获取待应用迁移**
3. **按版本顺序执行**
4. **记录迁移状态**
5. **验证数据完整性**

### 迁移安全措施

- **事务保护**：每个迁移在事务中执行
- **自动备份**：迁移前自动备份数据库
- **完整性检查**：迁移后验证数据完整性
- **回滚支持**：失败时自动回滚

## 性能优化

### 索引策略

1. **主键索引**：所有表都有自增主键
2. **唯一索引**：防止数据重复
3. **查询索引**：针对常用查询添加复合索引
4. **外键索引**：提高关联查询性能

### 查询优化

1. **分页查询**：大数据量时使用LIMIT和OFFSET
2. **条件索引**：where条件字段都有索引
3. **避免SELECT ***：只查询需要的字段
4. **批量操作**：使用事务进行批量插入/更新

### 存储优化

1. **数据清理**：定期清理过期数据
2. **压缩优化**：使用VACUUM命令优化存储
3. **日志轮转**：控制日志表大小
4. **缓存策略**：合理使用应用层缓存

## 数据维护

### 定期清理

```sql
-- 清理过期图片缓存
DELETE FROM image_cache WHERE expires_at < datetime('now');

-- 清理过期管理员令牌
DELETE FROM admin_tokens WHERE expired_at < datetime('now') AND is_valid = 0;

-- 清理旧日志(保留30天)
DELETE FROM webhook_logs WHERE created_at < datetime('now', '-30 days');
```

### 数据备份

```bash
# 备份数据库
sqlite3 lark_dify_bot.db ".backup backup_$(date +%Y%m%d_%H%M%S).db"

# 恢复数据库
sqlite3 lark_dify_bot.db ".restore backup_20231201_120000.db"
```

### 监控查询

```sql
-- 查看表大小
SELECT name, 
       COUNT(*) as count,
       (SELECT COUNT(*) FROM pragma_table_info(name)) as columns
FROM sqlite_master 
WHERE type='table' 
ORDER BY name;

-- 查看索引使用情况
EXPLAIN QUERY PLAN SELECT * FROM sessions WHERE user_id = 'xxx' AND is_active = 1;
```