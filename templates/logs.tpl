% rebase('layout.tpl', title='日志查看')
<h2>系统日志</h2>
<p><small>显示最近1000行日志</small></p>

<div style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow: auto; max-height: 600px;">
    <pre>{{log_content}}</pre>
</div>

<script>
// 自动滚动到底部
window.onload = function() {
    var logContainer = document.querySelector('pre').parentElement;
    logContainer.scrollTop = logContainer.scrollHeight;
};
</script>