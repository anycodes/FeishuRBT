% rebase('layout.tpl', title='API Token已重新生成')
<h2>API Token已重新生成</h2>

<div class="alert alert-success">
    <p>Webhook「{{name}}」的API Token已成功重新生成！</p>
    <p>旧的API Token已失效，请更新所有使用此Webhook的外部系统。</p>
</div>

<div class="card">
    <h3>新的Webhook URL</h3>
    <p><code>{{webhook_url}}</code></p>
    <button class="btn" onclick="copyToClipboard('{{webhook_url}}')">复制URL</button>
</div>

<div class="card">
    <h3>新的API Token</h3>
    <p><code>{{api_token}}</code></p>
    <p class="alert alert-warning">请保存此Token！出于安全考虑，此Token仅会显示一次。</p>
    <button class="btn" onclick="copyToClipboard('{{api_token}}')">复制Token</button>
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