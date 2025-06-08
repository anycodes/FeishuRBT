#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import logging
from datetime import datetime, timedelta
from config import Config
from models.database import get_db_connection

logger = logging.getLogger(__name__)


class ImageCacheService:
    """图片缓存服务"""

    def __init__(self):
        self.cache_dir = tempfile.mkdtemp()
        logger.info(f"图片缓存目录: {self.cache_dir}")

    def save_user_image_key(self, user_id, image_key):
        """保存用户图片key到缓存"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 清理该用户的旧缓存
        self.clear_user_image(user_id)

        # 计算过期时间
        expires_at = datetime.now() + timedelta(minutes=Config.IMAGE_CACHE_EXPIRE_MINUTES)

        # 保存到数据库
        cursor.execute(
            """INSERT INTO image_cache (user_id, image_path, expires_at) 
               VALUES (?, ?, ?)""",
            (user_id, image_key, expires_at)
        )
        conn.commit()
        conn.close()

        logger.info(f"用户 {user_id} 的图片已缓存: {image_key}")
        return True

    def save_user_image(self, user_id, image_data):
        """保存用户图片数据到缓存"""
        timestamp = datetime.now()
        image_path = os.path.join(self.cache_dir, f"{user_id}_{timestamp.timestamp()}.jpg")

        try:
            with open(image_path, 'wb') as f:
                f.write(image_data)

            conn = get_db_connection()
            cursor = conn.cursor()

            # 清理该用户的旧缓存
            self.clear_user_image(user_id)

            # 计算过期时间
            expires_at = datetime.now() + timedelta(minutes=Config.IMAGE_CACHE_EXPIRE_MINUTES)

            # 保存到数据库
            cursor.execute(
                """INSERT INTO image_cache (user_id, image_path, expires_at) 
                   VALUES (?, ?, ?)""",
                (user_id, image_path, expires_at)
            )
            conn.commit()
            conn.close()

            logger.info(f"用户 {user_id} 的图片已缓存: {image_path}")
            return image_path
        except Exception as e:
            logger.error(f"保存图片缓存失败: {e}")
            return None

    def get_user_image(self, user_id):
        """获取用户缓存的图片"""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT image_path, expires_at FROM image_cache 
               WHERE user_id = ? AND expires_at > CURRENT_TIMESTAMP
               ORDER BY id DESC LIMIT 1""",
            (user_id,)
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            image_path = result['image_path']
            # 检查文件是否存在（对于本地文件）
            if os.path.exists(image_path):
                return image_path
            else:
                # 文件不存在，清理数据库记录
                self.clear_user_image(user_id)
                return None

        return None

    def clear_user_image(self, user_id):
        """清除用户缓存的图片"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取要删除的文件路径
        cursor.execute(
            "SELECT image_path FROM image_cache WHERE user_id = ?",
            (user_id,)
        )
        results = cursor.fetchall()

        # 删除文件
        for result in results:
            image_path = result['image_path']
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"删除缓存文件: {image_path}")
                except Exception as e:
                    logger.error(f"删除缓存文件失败: {e}")

        # 删除数据库记录
        cursor.execute("DELETE FROM image_cache WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        logger.info(f"清除用户 {user_id} 的图片缓存")

    def cleanup_expired_cache(self):
        """清理过期的缓存"""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取过期的缓存记录
        cursor.execute(
            "SELECT image_path FROM image_cache WHERE expires_at <= CURRENT_TIMESTAMP"
        )
        results = cursor.fetchall()

        # 删除过期文件
        for result in results:
            image_path = result['image_path']
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"删除过期缓存文件: {image_path}")
                except Exception as e:
                    logger.error(f"删除过期缓存文件失败: {e}")

        # 删除过期记录
        cursor.execute("DELETE FROM image_cache WHERE expires_at <= CURRENT_TIMESTAMP")
        conn.commit()
        affected = conn.total_changes
        conn.close()

        if affected > 0:
            logger.info(f"清理了 {affected} 个过期缓存记录")

        return affected