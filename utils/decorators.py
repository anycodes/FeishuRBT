#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from functools import wraps
from bottle import request, response, redirect
from .helpers import validate_admin_token

logger = logging.getLogger(__name__)

def require_admin(func):
    """验证管理员token的装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = request.query.get('token') or request.get_cookie('admin_token')

        if not token:
            return redirect('/admin/login')

        valid, user_id = validate_admin_token(token)
        if not valid:
            return redirect('/admin/login')

        # 设置cookie便于后续请求
        response.set_cookie('admin_token', token, path='/')

        # 将user_id传递给被装饰的函数
        kwargs['user_id'] = user_id
        return func(*args, **kwargs)

    return wrapper