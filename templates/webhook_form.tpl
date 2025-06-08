% rebase('layout.tpl', title=title)
<h2>{{title}}</h2>
<a href="/admin/webhooks" class="btn">返回列表</a>

<form action="{{action}}" method="post">
    <div>
        <label for="name">Webhook名称:</label>
        <input type="text" id="name" name="name" value="{{webhook['name'] if webhook else ''}}" required>
    </div>

    <div>
        <label for="description">描述:</label>
        <textarea id="description" name="description" rows="3">{{webhook['description'] if webhook else ''}}</textarea>
    </div>

    <div>
        <label for="bypass_ai">处理模式:</label>
        <select id="bypass_ai" name="bypass_ai">
            <option value="0" {{'selected' if webhook and webhook['bypass_ai'] == 0 else ''}}>使用AI分析后推送</option>
            <option value="1" {{'selected' if webhook and webhook['bypass_ai'] == 1 else ''}}>直接推送原始消息</option>
        </select>
        <small>选择"直接推送"将原样转发接收到的数据，不经过AI处理</small>
    </div>

    <div>
        <label for="model_id">使用模型（仅在上面选择使用AI分析后推送选项时生效）:</label>
        <select id="model_id" name="model_id" required>
            % for model in models:
            <option value="{{model['id']}}" {{'selected' if webhook and str(webhook['model_id']) == str(model['id']) else ''}}>{{model['name']}}</option>
            % end
        </select>
    </div>

    <div>
        <label for="prompt_template">提示词模板(可选):</label>
        <textarea id="prompt_template" name="prompt_template" rows="5" placeholder="在此编写提示词模板，使用{data}表示接收到的数据。例如：请分析以下数据并提炼关键信息：{data}">{{webhook['prompt_template'] if webhook else ''}}</textarea>
        <small>如果不填写，将使用默认模板：分析以下数据:\n\n{data}</small>
    </div>

    <div>
        <label for="fallback_mode">AI处理失败时:</label>
        <select id="fallback_mode" name="fallback_mode">
            <option value="original" {{'selected' if webhook and webhook.get('fallback_mode') == 'original' else ''}}>发送原始数据</option>
            <option value="custom" {{'selected' if webhook and webhook.get('fallback_mode') == 'custom' else ''}}>发送自定义消息</option>
            <option value="silent" {{'selected' if webhook and webhook.get('fallback_mode') == 'silent' else ''}}>静默失败（不发送）</option>
        </select>
    </div>

    <div>
        <label for="fallback_message">自定义失败消息:</label>
        <textarea id="fallback_message" name="fallback_message" rows="2" placeholder="AI处理失败时发送的自定义消息">{{webhook['fallback_message'] if webhook else ''}}</textarea>
        <small>仅在上面选择"发送自定义消息"时生效</small>
    </div>

    % if webhook:
    <div>
        <label for="is_active">状态:</label>
        <select id="is_active" name="is_active">
            <option value="1" {{'selected' if webhook and webhook['is_active'] == 1 else ''}}>启用</option>
            <option value="0" {{'selected' if webhook and webhook['is_active'] == 0 else ''}}>禁用</option>
        </select>
    </div>

    <div>
        <label>配置Token:</label>
        <div class="code-display">{{webhook['config_token']}}</div>
        <small>用户使用此Token订阅，命令：\subscribe-event {{webhook['config_token']}}</small>
    </div>
    % end

    <div>
        <button type="submit" class="btn btn-primary">保存</button>
    </div>
</form>