% rebase('layout.tpl', title='Webhook订阅列表')
<h2>「{{webhook['name']}}」订阅列表</h2>
<a href="/admin/webhooks" class="btn">返回Webhook列表</a>

<div class="card">
    <h3>配置Token (用于订阅)</h3>
    <p><code>{{webhook['config_token']}}</code></p>
    <div class="alert alert-info">
        用户订阅命令: <code>\subscribe-event {{webhook['config_token']}}</code>
    </div>
</div>

<h3>当前订阅 ({{len(subscriptions)}})</h3>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>类型</th>
            <th>目标ID</th>
            <th>创建者</th>
            <th>创建时间</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for sub in subscriptions:
        <tr>
            <td>{{sub['id']}}</td>
            <td>{{sub['target_type']}}</td>
            <td>{{sub['target_id']}}</td>
            <td>{{sub['created_by'] or '-'}}</td>
            <td>{{sub['created_at']}}</td>
            <td>
                <a href="/admin/webhooks/remove-subscription/{{sub['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除此订阅吗？')">删除</a>
            </td>
        </tr>
        % end
        % if not subscriptions:
        <tr>
            <td colspan="6" style="text-align: center;">暂无订阅</td>
        </tr>
        % end
    </tbody>
</table>