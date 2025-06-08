% rebase('layout.tpl', title='系统配置')
<h2>系统配置</h2>

<form action="/admin/config/update" method="post">
    <div>
        <label for="default_model">默认模型:</label>
        <select id="default_model" name="default_model">
            <option value="">-- 不设置默认模型 --</option>
            % for model in models:
            <option value="{{model['id']}}" {{'selected' if default_model and str(default_model['id']) == str(model['id']) else ''}}>{{model['name']}}</option>
            % end
        </select>
    </div>

    <div>
        <label for="session_timeout">会话超时时间（分钟）:</label>
        <input type="number" id="session_timeout" name="session_timeout" value="{{configs.get('session_timeout', {}).get('value', '30')}}" min="1" required>
    </div>

    <div>
        <button type="submit" class="btn btn-primary">保存配置</button>
    </div>
</form>