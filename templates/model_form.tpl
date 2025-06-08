% rebase('layout.tpl', title=title)
<h2>{{title}}</h2>
<a href="/admin/models" class="btn">返回列表</a>

<form action="{{action}}" method="post">
    <div>
        <label for="name">模型名称:</label>
        <input type="text" id="name" name="name" value="{{model['name'] if model else ''}}" required>
    </div>

    <div>
        <label for="description">模型描述:</label>
        <textarea id="description" name="description" rows="3">{{model['description'] if model else ''}}</textarea>
    </div>

    <div>
        <label for="dify_url">Dify API地址:</label>
        <input type="text" id="dify_url" name="dify_url" value="{{model['dify_url'] if model else ''}}" required>
    </div>

    <div>
        <label for="dify_type">模型类型:</label>
        <select id="dify_type" name="dify_type" required>
            <option value="chatbot" {{'selected' if model and model['dify_type'] == 'chatbot' else ''}}>Chatbot</option>
            <option value="agent" {{'selected' if model and model['dify_type'] == 'agent' else ''}}>Agent</option>
            <option value="flow" {{'selected' if model and model['dify_type'] == 'flow' else ''}}>Flow</option>
        </select>
    </div>

    <div>
        <label for="api_key">API密钥:</label>
        <input type="text" id="api_key" name="api_key" value="{{model['api_key'] if model else ''}}" required>
    </div>

    <div>
        <button type="submit" class="btn btn-primary">保存</button>
    </div>
</form>