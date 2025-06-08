% rebase('layout.tpl', title='错误')
<h2>发生错误</h2>
<div class="alert alert-error">
    <p>{{error_message}}</p>
</div>
<a href="{{back_url}}" class="btn">返回</a>