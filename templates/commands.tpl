% rebase('layout.tpl', title='命令管理')
<h2>命令管理</h2>
<a href="/admin/commands/add" class="btn">添加命令</a>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>名称</th>
            <th>描述</th>
            <th>触发指令</th>
            <th>关联模型</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for cmd in commands:
        <tr>
            <td>{{cmd['id']}}</td>
            <td>{{cmd['name']}}</td>
            <td>{{cmd['description']}}</td>
            <td>{{cmd['trigger']}}</td>
            <td>{{cmd['model_name']}}</td>
            <td>
                <a href="/admin/commands/edit/{{cmd['id']}}" class="btn btn-primary">编辑</a>
                <a href="/admin/commands/delete/{{cmd['id']}}" class="btn btn-danger" onclick="return confirm('确定要删除吗？')">删除</a>
            </td>
        </tr>
        % end
    </tbody>
</table>