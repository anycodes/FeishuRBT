#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from models.user import add_user, get_user, check_admin, set_user_admin, get_all_users


def test_add_user(test_db, sample_user):
    """测试添加用户"""
    result = add_user(sample_user['user_id'], sample_user['name'], sample_user['is_admin'])
    assert result is True

    # 验证用户已添加
    user = get_user(sample_user['user_id'])
    assert user is not None
    assert user['user_id'] == sample_user['user_id']
    assert user['name'] == sample_user['name']
    assert user['is_admin'] == sample_user['is_admin']


def test_get_user_not_exists(test_db):
    """测试获取不存在的用户"""
    user = get_user('non_existent_user')
    assert user is None


def test_check_admin(test_db):
    """测试管理员权限检查"""
    # 添加普通用户
    add_user('normal_user', 'Normal User', 0)
    assert check_admin('normal_user') is False

    # 添加管理员用户
    add_user('admin_user', 'Admin User', 1)
    assert check_admin('admin_user') is True


def test_set_user_admin(test_db, sample_user):
    """测试设置用户管理员权限"""
    # 添加普通用户
    add_user(sample_user['user_id'], sample_user['name'], 0)
    assert check_admin(sample_user['user_id']) is False

    # 设置为管理员
    result = set_user_admin(sample_user['user_id'], 1)
    assert result is True
    assert check_admin(sample_user['user_id']) is True

    # 取消管理员权限
    result = set_user_admin(sample_user['user_id'], 0)
    assert result is True
    assert check_admin(sample_user['user_id']) is False


def test_get_all_users(test_db):
    """测试获取所有用户"""
    # 添加几个用户
    add_user('user1', 'User 1', 0)
    add_user('user2', 'User 2', 1)
    add_user('user3', 'User 3', 0)

    users = get_all_users()
    assert len(users) == 3

    # 验证管理员排在前面
    assert users[0]['is_admin'] == 1