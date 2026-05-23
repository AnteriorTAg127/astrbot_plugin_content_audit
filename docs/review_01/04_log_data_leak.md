# Issue 04 — _log 命令跨管理群泄漏违规数据

**严重度**: 🔴 Critical
**涉及文件**: `command_handler.py`
**类型**: 数据泄漏 / 权限问题

## 现象

`command_handler._log()` 方法：

```python
async def _log(self, event, group_id, args):
    violations = await self._stats_manager.get_violations(
        group_id=None,  # ← 查全部群！
        page=page, page_size=page_size
    )
```

当 `group_id=None` 时，查询返回数据库中所有群的全部违规记录。

但该方法已经有管理群网关校验（`is_manage_group`），表明意图是：管理群只能看到自己管辖的群的数据。如果 bot 同时服务于多个独立的管理群，管理群 A 的管理员能看到管理群 B 的违规数据。

## 修复方案

改为传入当前管理群关联的被管理群 ID 列表：

```python
async def _log(self, event, group_id, args):
    managed_groups = self._config_manager.get_managed_group_ids(group_id)
    if not managed_groups:
        return "📋 违规日志\n暂无关联的被管理群"

    # 按关联的被管理群过滤
    all_violations = []
    for mg_id in managed_groups:
        violations = await self._stats_manager.get_violations(
            group_id=mg_id, page=page, page_size=page_size
        )
        all_violations.extend(violations)
    
    # 按时间排序后截取 page_size 条
    all_violations.sort(key=lambda v: v['created_at'], reverse=True)
    all_violations = all_violations[:page_size]
```

或者为 `StatsManager.get_violations` 增加 `group_ids: list[str]` 参数支持多群查询。
