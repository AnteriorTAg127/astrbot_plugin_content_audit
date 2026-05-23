# Issue 03 — audit_log 表从未写入

**严重度**: 🔴 Critical
**涉及文件**: `message_handler.py`, `stats_manager.py`
**类型**: 功能缺失

## 现象

`stats_manager.record_audit()` 方法已定义，SQLite `audit_log` 表也已建好，但整个代码库中没有任何地方调用 `record_audit()`。

`message_handler.handle()` 审核完每条消息后：
- 违规 → 走 `violation_handler.handle()` → 写入 `violation_records`
- 合规 → 直接 `logger.debug("文本审核通过")`，**不写日志**

后果：
- `get_stats()` 中 `today_audits` / `total_audits` 永远返回 0
- `/文本审核 状态` 命令显示的"今日审核"始终为 0
- 无法追踪审核覆盖率

## 修复方案

在 `message_handler.handle()` 中，审核 API 返回后（无论是否违规），调用 `record_audit()`：

```python
# message_handler.py, 第 100 行附近，audit() 调用之后
result = await self._audit_client.audit(message_str, skip_llm=skip_llm)

# 新增：记录审计日志
await self._stats_manager.record_audit(
    group_id=group_id,
    user_id=user_id,
    user_name=user_name,
    text_preview=message_str[:200],  # 截断长文本
    has_violation=1 if result.has_violation else 0,
    source=result.source,
    request_id=result.request_id,
)

if result.error:
    ...
```

注意：需要将 `stats_manager` 注入到 `message_handler` 或通过 `violation_handler` 间接调用。
