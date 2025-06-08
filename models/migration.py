#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import traceback
from datetime import datetime
from .database import get_db_connection

logger = logging.getLogger(__name__)


class DatabaseMigration:
    """数据库迁移管理类"""

    def __init__(self):
        self.migrations_dir = "migrations"
        self.ensure_migrations_dir()
        self.ensure_migration_table()

    def ensure_migrations_dir(self):
        """确保迁移目录存在"""
        os.makedirs(self.migrations_dir, exist_ok=True)

    def ensure_migration_table(self):
        """确保迁移记录表存在"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS db_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checksum TEXT
            )
            ''')
            conn.commit()
            logger.info("迁移记录表初始化完成")
        except Exception as e:
            logger.error(f"创建迁移记录表失败: {e}")
            conn.rollback()
        finally:
            conn.close()

    def get_current_version(self):
        """获取当前数据库版本"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT version FROM db_migrations ORDER BY version DESC LIMIT 1")
            result = cursor.fetchone()
            if result:
                return result['version']
            return "0.0.0"
        except Exception as e:
            logger.warning(f"获取数据库版本失败: {e}")
            return "0.0.0"
        finally:
            conn.close()

    def get_applied_migrations(self):
        """获取已应用的迁移列表"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT version FROM db_migrations ORDER BY version")
            return [row['version'] for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"获取已应用迁移列表失败: {e}")
            return []
        finally:
            conn.close()

    def record_migration(self, version, name, checksum=None):
        """记录已应用的迁移"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT OR REPLACE INTO db_migrations (version, name, checksum) VALUES (?, ?, ?)",
                (version, name, checksum)
            )
            conn.commit()
            logger.info(f"记录迁移: {version} - {name}")
        except Exception as e:
            logger.error(f"记录迁移失败: {e}")
            conn.rollback()
        finally:
            conn.close()

    def apply_migration(self, migration_func, version, name):
        """应用单个迁移"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            logger.info(f"开始应用迁移: {version} - {name}")

            # 开始事务
            cursor.execute("BEGIN")

            # 执行迁移
            migration_func(cursor)

            # 记录迁移
            cursor.execute(
                "INSERT OR REPLACE INTO db_migrations (version, name) VALUES (?, ?)",
                (version, name)
            )

            # 提交事务
            conn.commit()
            logger.info(f"迁移应用成功: {version} - {name}")
            return True

        except Exception as e:
            logger.error(f"迁移应用失败: {version} - {name}: {e}")
            logger.error(traceback.format_exc())
            conn.rollback()
            return False
        finally:
            conn.close()

    def run_migrations(self):
        """执行所有未应用的迁移"""
        applied_migrations = set(self.get_applied_migrations())

        # 获取所有可用的迁移
        available_migrations = self.get_available_migrations()

        # 找出未应用的迁移
        pending_migrations = []
        for version, migration_info in available_migrations:
            if version not in applied_migrations:
                pending_migrations.append((version, migration_info))

        if not pending_migrations:
            logger.info("没有需要应用的迁移")
            return True

        # 按版本号排序
        pending_migrations.sort(key=lambda x: self.version_to_tuple(x[0]))

        success_count = 0
        for version, migration_info in pending_migrations:
            if self.apply_migration(migration_info['func'], version, migration_info['name']):
                success_count += 1
            else:
                logger.error(f"迁移失败，停止后续迁移: {version}")
                break

        logger.info(f"迁移完成，成功应用 {success_count}/{len(pending_migrations)} 个迁移")
        return success_count == len(pending_migrations)

    def version_to_tuple(self, version_str):
        """将版本字符串转换为元组，用于比较"""
        try:
            return tuple(map(int, version_str.split('.')))
        except:
            return (0, 0, 0)

    def get_available_migrations(self):
        """获取所有可用的迁移"""
        return [
            ("1.0.0", {"name": "初始化数据库", "func": self.migrate_1_0_0}),
            ("1.1.0", {"name": "添加会话扩展字段", "func": self.migrate_1_1_0}),
            ("1.2.0", {"name": "添加Webhook支持", "func": self.migrate_1_2_0}),
            ("1.3.0", {"name": "添加图片缓存支持", "func": self.migrate_1_3_0}),
            ("1.4.0", {"name": "添加Webhook回退机制", "func": self.migrate_1_4_0}),
            ("1.5.0", {"name": "优化索引和性能", "func": self.migrate_1_5_0}),
        ]

    def column_exists(self, cursor, table_name, column_name):
        """检查表中是否存在指定列"""
        try:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            return column_name in columns
        except:
            return False

    def table_exists(self, cursor, table_name):
        """检查表是否存在"""
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            return cursor.fetchone() is not None
        except:
            return False

    def index_exists(self, cursor, index_name):
        """检查索引是否存在"""
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
            return cursor.fetchone() is not None
        except:
            return False

    # ==================== 迁移脚本 ====================

    def migrate_1_0_0(self, cursor):
        """1.0.0 - 初始化数据库基础结构"""
        logger.info("执行迁移 1.0.0: 初始化数据库基础结构")

        # 用户表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            name TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # 模型表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            dify_url TEXT NOT NULL,
            dify_type TEXT NOT NULL,
            api_key TEXT NOT NULL,
            parameters TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # 命令表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            trigger TEXT UNIQUE NOT NULL,
            model_id INTEGER,
            parameters TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES models (id)
        )
        ''')

        # 配置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS configs (
            key TEXT PRIMARY KEY,
            value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # 会话表（基础版本）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            model_id INTEGER,
            conversation_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES models (id)
        )
        ''')

        # 消息记录表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            user_id TEXT NOT NULL,
            content TEXT,
            is_user INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
        ''')

        # 管理员令牌表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expired_at TIMESTAMP,
            is_valid INTEGER DEFAULT 1
        )
        ''')

        # 插入默认配置
        cursor.execute("INSERT OR IGNORE INTO configs (key, value, description) VALUES (?, ?, ?)",
                       ("default_model", "", "默认使用的模型ID"))
        cursor.execute("INSERT OR IGNORE INTO configs (key, value, description) VALUES (?, ?, ?)",
                       ("session_timeout", "30", "会话超时时间（分钟）"))

    def migrate_1_1_0(self, cursor):
        """1.1.0 - 添加会话扩展字段"""
        logger.info("执行迁移 1.1.0: 添加会话扩展字段")

        # 检查并添加会话表的新字段
        if not self.column_exists(cursor, "sessions", "last_active_at"):
            cursor.execute("ALTER TABLE sessions ADD COLUMN last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            logger.info("添加sessions.last_active_at字段")

        if not self.column_exists(cursor, "sessions", "is_active"):
            cursor.execute("ALTER TABLE sessions ADD COLUMN is_active INTEGER DEFAULT 1")
            logger.info("添加sessions.is_active字段")

        if not self.column_exists(cursor, "sessions", "command_id"):
            cursor.execute("ALTER TABLE sessions ADD COLUMN command_id INTEGER DEFAULT NULL")
            logger.info("添加sessions.command_id字段")
            # 添加外键约束（如果需要）

    def migrate_1_2_0(self, cursor):
        """1.2.0 - 添加Webhook支持"""
        logger.info("执行迁移 1.2.0: 添加Webhook支持")

        # Webhook表
        if not self.table_exists(cursor, "webhooks"):
            cursor.execute('''
            CREATE TABLE webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                token TEXT UNIQUE NOT NULL,
                config_token TEXT UNIQUE NOT NULL,
                model_id INTEGER,
                prompt_template TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models (id)
            )
            ''')
            logger.info("创建webhooks表")

        # Webhook订阅表
        if not self.table_exists(cursor, "webhook_subscriptions"):
            cursor.execute('''
            CREATE TABLE webhook_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (webhook_id) REFERENCES webhooks (id),
                UNIQUE(webhook_id, target_type, target_id)
            )
            ''')
            logger.info("创建webhook_subscriptions表")

        # Webhook调用日志表
        if not self.table_exists(cursor, "webhook_logs"):
            cursor.execute('''
            CREATE TABLE webhook_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id INTEGER,
                request_data TEXT,
                response TEXT,
                status INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (webhook_id) REFERENCES webhooks (id)
            )
            ''')
            logger.info("创建webhook_logs表")

    def migrate_1_3_0(self, cursor):
        """1.3.0 - 添加图片缓存支持"""
        logger.info("执行迁移 1.3.0: 添加图片缓存支持")

        # 图片缓存表
        if not self.table_exists(cursor, "image_cache"):
            cursor.execute('''
            CREATE TABLE image_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                image_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
            ''')
            logger.info("创建image_cache表")

    def migrate_1_4_0(self, cursor):
        """1.4.0 - 添加Webhook回退机制"""
        logger.info("执行迁移 1.4.0: 添加Webhook回退机制")

        # 检查并添加bypass_ai字段
        if not self.column_exists(cursor, "webhooks", "bypass_ai"):
            cursor.execute("ALTER TABLE webhooks ADD COLUMN bypass_ai INTEGER DEFAULT 0")
            logger.info("添加webhooks.bypass_ai字段")

        # 检查并添加fallback_mode字段
        if not self.column_exists(cursor, "webhooks", "fallback_mode"):
            cursor.execute("ALTER TABLE webhooks ADD COLUMN fallback_mode TEXT DEFAULT 'original'")
            logger.info("添加webhooks.fallback_mode字段")

        # 检查并添加fallback_message字段
        if not self.column_exists(cursor, "webhooks", "fallback_message"):
            cursor.execute("ALTER TABLE webhooks ADD COLUMN fallback_message TEXT DEFAULT NULL")
            logger.info("添加webhooks.fallback_message字段")

    def migrate_1_5_0(self, cursor):
        """1.5.0 - 优化索引和性能"""
        logger.info("执行迁移 1.5.0: 优化索引和性能")

        # 创建索引以提高查询性能
        indexes = [
            ("idx_users_user_id", "CREATE INDEX IF NOT EXISTS idx_users_user_id ON users (user_id)"),
            ("idx_sessions_user_id", "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id)"),
            ("idx_sessions_active",
             "CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions (user_id, is_active, last_active_at)"),
            ("idx_messages_session_id", "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id)"),
            ("idx_webhook_subscriptions_webhook_id",
             "CREATE INDEX IF NOT EXISTS idx_webhook_subscriptions_webhook_id ON webhook_subscriptions (webhook_id)"),
            ("idx_webhook_logs_webhook_id",
             "CREATE INDEX IF NOT EXISTS idx_webhook_logs_webhook_id ON webhook_logs (webhook_id, created_at)"),
            ("idx_image_cache_user_expires",
             "CREATE INDEX IF NOT EXISTS idx_image_cache_user_expires ON image_cache (user_id, expires_at)"),
            ("idx_admin_tokens_valid",
             "CREATE INDEX IF NOT EXISTS idx_admin_tokens_valid ON admin_tokens (user_id, is_valid, expired_at)"),
        ]

        for index_name, index_sql in indexes:
            if not self.index_exists(cursor, index_name):
                cursor.execute(index_sql)
                logger.info(f"创建索引: {index_name}")

    def backup_database(self):
        """备份数据库"""
        import shutil
        from config import Config

        try:
            backup_path = f"{Config.DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(Config.DB_PATH, backup_path)
            logger.info(f"数据库备份成功: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            return None

    def validate_database_integrity(self):
        """验证数据库完整性"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 执行PRAGMA integrity_check
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()

            if result and result[0] == "ok":
                logger.info("数据库完整性检查通过")
                return True
            else:
                logger.error(f"数据库完整性检查失败: {result}")
                return False

        except Exception as e:
            logger.error(f"数据库完整性检查出错: {e}")
            return False
        finally:
            conn.close()


def init_database_with_migration():
    """使用迁移系统初始化数据库"""
    logger.info("开始数据库初始化...")

    migration = DatabaseMigration()

    # 备份数据库（如果存在）
    from config import Config
    if os.path.exists(Config.DB_PATH):
        backup_path = migration.backup_database()
        if backup_path:
            logger.info(f"已备份现有数据库到: {backup_path}")

    # 验证数据库完整性
    if os.path.exists(Config.DB_PATH):
        if not migration.validate_database_integrity():
            logger.error("数据库完整性检查失败，请检查数据库文件")
            return False

    # 获取当前版本
    current_version = migration.get_current_version()
    logger.info(f"当前数据库版本: {current_version}")

    # 执行迁移
    success = migration.run_migrations()

    if success:
        # 再次验证数据库完整性
        if migration.validate_database_integrity():
            new_version = migration.get_current_version()
            logger.info(f"数据库迁移成功！当前版本: {new_version}")
            return True
        else:
            logger.error("迁移后数据库完整性检查失败")
            return False
    else:
        logger.error("数据库迁移失败")
        return False


def get_database_info():
    """获取数据库信息（用于管理界面）"""
    migration = DatabaseMigration()

    current_version = migration.get_current_version()
    applied_migrations = migration.get_applied_migrations()
    available_migrations = [version for version, _ in migration.get_available_migrations()]

    return {
        "current_version": current_version,
        "applied_migrations": applied_migrations,
        "available_migrations": available_migrations,
        "pending_migrations": [v for v in available_migrations if v not in applied_migrations]
    }