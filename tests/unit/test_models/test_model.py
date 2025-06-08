#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from models.model import add_model, get_model, get_all_models, update_model, delete_model


def test_add_model(test_db, sample_model):
    """测试添加模型"""
    model_id = add_model(
        sample_model['name'],
        sample_model['description'],
        sample_model['dify_url'],
        sample_model['dify_type'],
        sample_model['api_key']
    )

    assert model_id is not None
    assert isinstance(model_id, int)

    # 验证模型已添加
    model = get_model(model_id=model_id)
    assert model is not None
    assert model['name'] == sample_model['name']
    assert model['dify_type'] == sample_model['dify_type']


def test_get_model_by_name(test_db, sample_model):
    """测试通过名称获取模型"""
    model_id = add_model(
        sample_model['name'],
        sample_model['description'],
        sample_model['dify_url'],
        sample_model['dify_type'],
        sample_model['api_key']
    )

    model = get_model(model_name=sample_model['name'])
    assert model is not None
    assert model['id'] == model_id


def test_get_model_not_exists(test_db):
    """测试获取不存在的模型"""
    model = get_model(model_id=999)
    assert model is None

    model = get_model(model_name='non_existent')
    assert model is None


def test_update_model(test_db, sample_model):
    """测试更新模型"""
    model_id = add_model(
        sample_model['name'],
        sample_model['description'],
        sample_model['dify_url'],
        sample_model['dify_type'],
        sample_model['api_key']
    )

    # 更新模型
    new_name = 'Updated Model'
    result = update_model(model_id, name=new_name)
    assert result is True

    # 验证更新
    model = get_model(model_id=model_id)
    assert model['name'] == new_name


def test_delete_model_with_dependencies(test_db, sample_model):
    """测试删除有依赖的模型"""
    from models.command import add_command

    # 添加模型
    model_id = add_model(
        sample_model['name'],
        sample_model['description'],
        sample_model['dify_url'],
        sample_model['dify_type'],
        sample_model['api_key']
    )

    # 添加依赖的命令
    add_command('Test Command', 'Test', '\\test', model_id)

    # 尝试删除模型（应该失败）
    success, message = delete_model(model_id)
    assert success is False
    assert "关联的命令" in message


def test_get_all_models(test_db):
    """测试获取所有模型"""
    # 添加几个模型
    for i in range(3):
        add_model(f'Model {i}', f'Description {i}', 'https://api.test.com', 'chatbot', f'key_{i}')

    models = get_all_models()
    assert len(models) == 3