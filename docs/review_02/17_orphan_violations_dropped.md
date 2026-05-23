# 17 — 未配置管理群时违规事件静默丢弃

**严重度**：🔴 Critical  
**文件**：`violation_handler.py` (行 162-165)，`message_handler.py`

## 问题

当被管理群未配置 `manage_group_id` 时，`ViolationHandler.handle()` 在流程最开头就 `return`，导致违规事件**完全不记录**——既不落库也不发通报。

```python
# violation_handler.py 行 162-165
manage_group_id = self._config_manager.get_manage_group_id(group_id)
if not manage_group_id:
    logger.warning(f"群 {group_id} 未配置管理群，无法发送通报")
    return  # ← 违规数据丢失！
```

而 `message_handler.py` 在第 117 行已先执行 `record_audit()` 将审核结果写入了 `audit_log`，但调用链是：

```
message_handler.handle()
  → record_audit() ✅ 已写入 audit_log
  → violation_handler.handle()
      → manage_group_id 为空 → return ❌ violation_records 未写入
```

结果：`audit_log` 有记录，`violation_records` 无记录——数据不完整且违反设计文档 §二 "管理群通报始终生效" 但这里连通报都不发。

## 修复建议

1. 在 `handle()` 开头将通报失败降级为**日志通报**（log-only），而非直接退出。
2. 即使没有管理群，也应将违规写入 `violation_records`。
3. 最小改动方案：在 `return` 前先调用 `_stats_manager.record_violation()`，将 `action_recall` 和 `action_mute` 设为 0。

```python
if not manage_group_id:
    logger.warning(f"群 {group_id} 未配置管理群，仅记录违规不通报")
    await self._stats_manager.record_violation(
        group_id=group_id, user_id=user_id, user_name=user_name,
        text_preview=text_preview, request_id=result.request_id,
        action_recall=0, action_mute=0, mute_duration=0,
    )
    return
```

**Why**：运维人员可能在添加群配置时忘记填写 `manage_group_id`，导致违规数据完全不可见且不可恢复。

**How to apply**：将违规记录写入从"通报后记录"改为"始终记录"，通报作为可选的后置步骤。
