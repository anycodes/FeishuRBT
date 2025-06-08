% rebase('layout.tpl', title='数据库信息')
<h2>数据库信息</h2>

<div class="card">
    <h3>当前状态</h3>
    <p><strong>当前版本:</strong> {{db_info['current_version']}}</p>
    <p><strong>已应用迁移数:</strong> {{len(db_info['applied_migrations'])}}</p>
    <p><strong>待应用迁移数:</strong> {{len(db_info['pending_migrations'])}}</p>
</div>

% if db_info['pending_migrations']:
<div class="card">
    <h3>待应用迁移</h3>
    <ul>
        % for migration in db_info['pending_migrations']:
        <li>{{migration}}</li>
        % end
    </ul>
    <form action="/admin/database/migrate" method="post" onsubmit="return confirm('确定要执行迁移吗？建议先备份数据库。')">
        <button type="submit" class="btn btn-warning">执行迁移</button>
    </form>
</div>
% end

<div class="card">
    <h3>迁移历史</h3>
    <table>
        <thead>
            <tr>
                <th>版本</th>
                <th>状态</th>
            </tr>
        </thead>
        <tbody>
            % for migration in db_info['available_migrations']:
            <tr>
                <td>{{migration}}</td>
                <td>
                    % if migration in db_info['applied_migrations']:
                    <span style="color: green;">✓ 已应用</span>
                    % else:
                    <span style="color: orange;">待应用</span>
                    % end
                </td>
            </tr>
            % end
        </tbody>
    </table>
</div>