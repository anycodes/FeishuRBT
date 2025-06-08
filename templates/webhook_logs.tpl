% rebase('layout.tpl', title='Webhook调用日志')
<h2>「{{webhook['name']}}」调用日志</h2>
<a href="/admin/webhooks" class="btn">返回Webhook列表</a>

<p>显示最近100条调用记录</p>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>时间</th>
            <th>状态</th>
            <th>请求数据</th>
            <th>响应</th>
        </tr>
    </thead>
    <tbody>
        % for log in logs:
        <tr>
            <td>{{log['id']}}</td>
            <td>{{log['created_at']}}</td>
            <td>{{log['status']}}</td>
            <td>
                <div class="log-content">{{log['request_data']}}</div>
            </td>
            <td>
                <div class="log-content">{{log['response']}}</div>
            </td>
        </tr>
        % end
        % if not logs:
        <tr>
            <td colspan="5" style="text-align: center;">暂无调用记录</td>
        </tr>
        % end
    </tbody>
</table>

<style>
.log-content {
    max-height: 150px;
    max-width: 300px;
    overflow: auto;
    white-space: pre-wrap;
    font-family: monospace;
    font-size: 12px;
    background-color: #f5f5f5;
    padding: 5px;
    border-radius: 3px;
}
</style>