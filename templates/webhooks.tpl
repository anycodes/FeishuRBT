% rebase('layout.tpl', title='Webhook管理')
<h2>Webhook管理</h2>
<p>Webhook允许外部系统调用机器人并将消息推送给订阅者。</p>
<a href="/admin/webhooks/add" class="btn">添加Webhook</a>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>名称</th>
            <th>描述</th>
            <th>模型</th>
            <th>订阅数</th>
            <th>处理模式</th>
            <th>状态</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for webhook in webhooks:
        <tr>
            <td>{{webhook['id']}}</td>
            <td>{{webhook['name']}}</td>
            <td>{{webhook['description'] or '-'}}</td>
            <td>{{webhook['model_name']}}</td>
            <td>
                % subscription_count = len(get_webhook_subscriptions(webhook['id']))
                <a href="/admin/webhooks/subscriptions/{{webhook['id']}}">
                    {{subscription_count}} 个订阅
                </a>
            </td>
            <td>{{("直接推送" if webhook['bypass_ai'] else "AI处理")}}</td>
            <td>{{("启用" if webhook['is_active'] else "禁用")}}</td>
            <td>
                <a href="/admin/webhooks/edit/{{webhook['id']}}" class="btn btn-primary">编辑</a>
                <a href="/admin/webhooks/regenerate-token/{{webhook['id']}}?type=api" class="btn btn-warning" onclick="return confirm('确定要重新生成API Token吗？')">重新生成API Token</a>
                <a href="/admin/webhooks/regenerate-token/{{webhook['id']}}?type=config" class="btn btn-warning" onclick="return confirm('确定要重新生成配置Token吗？')">重新生成配置Token</a>
                <a href="/admin/webhook-logs/{{webhook['id']}}" class="btn btn-info">查看日志</a>
                <a href="/admin/webhooks/delete/{{webhook['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除吗？')">删除</a>
            </td>
        </tr>
        % end
    </tbody>
</table>