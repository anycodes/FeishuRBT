<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title or 'Dify机器人管理'}}</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <div class="container">
        <h1>Dify机器人管理</h1>
        <nav>
            <a href="/admin/models" class="btn">模型管理</a>
            <a href="/admin/commands" class="btn">命令管理</a>
            <a href="/admin/webhooks" class="btn">Webhook管理</a>
            <a href="/admin/config" class="btn">系统配置</a>
            <a href="/admin/users" class="btn">用户管理</a>
            <a href="/admin/database" class="btn">数据库信息</a>
            <a href="/admin/logs" class="btn">日志查看</a>
            <a href="/admin/logout" class="btn btn-danger">退出登录</a>
        </nav>
        <hr>
        %if defined('message'):
        <div class="alert {{message_type or 'alert-info'}}">
            {{message}}
        </div>
        %end

        {{!base}}
    </div>
</body>
</html>