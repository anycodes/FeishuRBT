% rebase('layout.tpl', title='Webhook创建成功')
<h2>Webhook创建成功</h2>

<div class="alert alert-success">
    <p>您的Webhook「{{name}}」已成功创建！</p>
</div>

<div class="card">
    <h3>Webhook URL</h3>
    <p><code>{{webhook_url}}</code></p>
    <p>外部系统使用此URL发送POST请求</p>
    <button class="btn" onclick="copyToClipboard('{{webhook_url}}')">复制URL</button>
</div>

<div class="card">
    <h3>API Token</h3>
    <p><code>{{api_token}}</code></p>
    <p class="alert alert-warning">请保存此Token！出于安全考虑，此Token仅会显示一次。</p>
    <button class="btn" onclick="copyToClipboard('{{api_token}}')">复制Token</button>
</div>

<div class="card">
    <h3>配置Token (订阅用)</h3>
    <p><code>{{config_token}}</code></p>
    <p>用户使用此Token订阅webhook通知</p>
    <div class="alert alert-info">
        订阅命令: <code>\subscribe-event {{config_token}}</code>
    </div>
    <button class="btn" onclick="copyToClipboard('{{config_token}}')">复制Token</button>
</div>

<div class="card">
    <h3>使用说明</h3>
    <h4>POST请求示例</h4>
    <pre><code>curl -X POST {{webhook_url}} \
  -H "Content-Type: application/json" \
  -d '{"message": "这是一条测试消息", "source": "外部系统"}'</code></pre>

    <h4>表单数据示例</h4>
    <pre><code>curl -X POST {{webhook_url}} \
  -d "message=测试消息&source=外部系统"</code></pre>

    <h4>常见集成场景</h4>
    <ul>
        <li><strong>GitHub</strong>: 代码推送、Issue创建等事件</li>
        <li><strong>支付系统</strong>: 支付成功、退款等通知</li>
        <li><strong>监控系统</strong>: 告警、恢复等状态变化</li>
        <li><strong>CI/CD</strong>: 构建完成、部署结果等</li>
    </ul>
</div>

<p>
    <a href="/admin/webhooks" class="btn">返回Webhook列表</a>
</p>

<script>
function copyToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    alert('已复制到剪贴板');
}
</script>