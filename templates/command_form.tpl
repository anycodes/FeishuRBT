% rebase('layout.tpl', title=title)
<h2>{{title}}</h2>
<a href="/admin/commands" class="btn">返回列表</a>

<form action="{{action}}" method="post">
    <div>
        <label for="name">命令名称:</label>
        <input type="text" id="name" name="name" value="{{command['name'] if command else ''}}" required>
    </div>

    <div>
        <label for="description">命令描述:</label>
        <textarea id="description" name="description" rows="3">{{command['description'] if command else ''}}</textarea>
    </div>

    <div>
        <label for="trigger">触发指令:</label>
        <input type="text" id="trigger" name="trigger" value="{{command['trigger'] if command else ''}}" required>
        <small>例如：\hello</small>
    </div>

    <div>
        <label for="model_id">关联模型:</label>
        <select id="model_id" name="model_id" required>
            % for model in models:
            <option value="{{model['id']}}" {{'selected' if command and str(command['model_id']) == str(model['id']) else ''}}>{{model['name']}}</option>
            % end
        </select>
    </div>

    <div>
        <button type="submit" class="btn btn-primary">保存</button>
    </div>
</form>