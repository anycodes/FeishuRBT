% rebase('layout.tpl', title='模型管理')
<h2>模型管理</h2>
<a href="/admin/models/add" class="btn">添加模型</a>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>名称</th>
            <th>描述</th>
            <th>类型</th>
            <th>API地址</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for model in models:
        <tr>
            <td>{{model['id']}}</td>
            <td>{{model['name']}}</td>
            <td>{{model['description']}}</td>
            <td>{{model['dify_type']}}</td>
            <td>{{model['dify_url']}}</td>
            <td>
                <a href="/admin/models/edit/{{model['id']}}" class="btn btn-primary">编辑</a>
                <a href="/admin/models/delete/{{model['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除吗？')">删除</a>
            </td>
        </tr>
        % end
    </tbody>
</table>