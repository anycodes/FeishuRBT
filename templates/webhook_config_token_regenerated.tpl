% rebase('layout.tpl', title='配置Token已重新生成')
<h2>配置Token已重新生成</h2>

<div class="alert alert-success">
    <p>Webhook「{{name}}」的配置Token已成功重新生成！</p>
    <p>用户需要使用新的配置Token重新订阅。</p>
</div>

<div class="card">
    <h3>新的配置Token (订阅用)</h3>
    <p><code>{{config_token}}</code></p>
    <div class="alert alert-info">
        新的订阅命令: <code>\subscribe-event {{config_token}}</code>
    </div>
    <button class="btn" onclick="copyToClipboard('{{config_token}}')">复制Token</button>
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