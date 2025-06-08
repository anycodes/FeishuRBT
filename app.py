#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from bottle import Bottle, run, TEMPLATE_PATH
from waitress import serve

from config import Config
from models.database import init_database
from handlers.lark_handler import setup_lark_routes
from handlers.webhook_handler import setup_webhook_routes
from handlers.admin_handler import setup_admin_routes
from utils.helpers import init_static_dir

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lark_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 配置模板路径
TEMPLATE_PATH.insert(0, 'templates')  # 将 templates 目录添加到模板搜索路径

# 创建Bottle应用
app = Bottle()


def setup_routes():
    """设置所有路由"""
    setup_lark_routes(app)
    setup_webhook_routes(app)
    setup_admin_routes(app)


def main():
    """主入口函数"""
    # 初始化数据库
    init_database()

    # 初始化静态文件目录
    init_static_dir()

    # 设置路由
    setup_routes()

    # 健康检查接口
    @app.get('/ping')
    def ping():
        return "pong"

    # 启动服务
    logger.info("飞书Dify机器人服务启动")

    try:
        logger.info("使用waitress服务器启动应用")
        serve(app, host='0.0.0.0', port=8080, threads=10)
    except ImportError:
        logger.warning("未检测到waitress，使用Bottle默认服务器")
        app.run(host='0.0.0.0', port=8080, debug=False, server='auto')


if __name__ == '__main__':
    main()