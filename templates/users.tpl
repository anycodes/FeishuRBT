% rebase('layout.tpl', title='用户管理')
<h2>用户管理</h2>

<table>
    <thead>
        <tr>
            <th>ID</th>
            <th>用户ID</th>
            <th>用户名</th>
            <th>角色</th>
            <th>创建时间</th>
            <th>操作</th>
        </tr>
    </thead>
    <tbody>
        % for user in users:
        <tr>
            <td>{{user['id']}}</td>
            <td>{{user['user_id']}}</td>
            <td>{{user['name'] or '未设置'}}</td>
            <td>{{'管理员' if user['is_admin'] else '普通用户'}}</td>
            <td>{{user['created_at']}}</td>
            <td>
                % if user['is_admin']:
                <a href="/admin/users/toggle_admin/{{user['user_id']}}" class="btn btn-danger">取消管理员</a>
                % else:
                <a href="/admin/users/toggle_admin/{{user['user_id']}}" class="btn btn-primary">设为管理员</a>
                % end
            </td>
        </tr>
        % end
    </tbody>
</table>