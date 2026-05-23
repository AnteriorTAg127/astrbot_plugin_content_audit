# 26 — 智能审查关闭时仍拉取管理员缓存

**严重度**：🟢 Minor  
**文件**：`message_handler.py` (行 84-88)

## 问题

```python
# 第 6 步：智能审查决策 (行 84-88)
group_config = self._config_manager.get_group_config(group_id)
if group_config and group_config.get("auto_censor_no_admin_minutes", 0) > 0:
    is_admin_cached = await self._admin_manager.is_user_admin_cached(event, group_id, user_id)
    if is_admin_cached:
        self._admin_manager.record_admin_message(group_id)
```

这段代码无条件检查 `auto_censor_no_admin_minutes > 0`，但没有先检查 `enable_auto_censor`。

当 `enable_auto_censor = false`（全量审查模式）但 `auto_censor_no_admin_minutes = 30`（例如从其他群配置复制过来的默认值）时，仍会触发管理员缓存查询和发言时间记录——但这些数据在 `should_enable_censor()` 中完全不会被使用，因为全量审查模式直接走第一条决策分支。

## 影响

- `is_user_admin_cached` 在缓存未命中时会拉取群成员列表（平台 API 调用）
- `record_admin_message` 记录到 `_last_admin_message_time` 字典中，但无人读取

浪费程度取决于：有多少群在 `enable_auto_censor=false` 时仍设置了 `auto_censor_no_admin_minutes > 0`。

## 修复建议

将条件改为同时检查 `enable_auto_censor`：

```python
if (
    group_config
    and group_config.get("enable_auto_censor", False)
    and group_config.get("auto_censor_no_admin_minutes", 0) > 0
):
    ...
```

**Why**：虽然对正确性无影响，但对性能敏感场景（大量消息的群）节省不必要的 API 调用。

**How to apply**：在条件中增加 `enable_auto_censor` 的检查，确保只在智能审查启用时才追踪管理员活动。
