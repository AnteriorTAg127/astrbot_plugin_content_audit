# Issue 14 — 降级放行无 API 故障统计

**严重度**: 🟢 Minor
**涉及文件**: `audit_client.py`, `message_handler.py`, `stats_manager.py`
**类型**: 可观测性

## 现象

当审核 API 不可用时：
- `audit_client.audit()` 返回 `AuditResult(has_violation=False, error=str(e))`
- `message_handler.handle()` 检测到 `result.error` 后 `logger.info("审核 API 不可用，降级放行")` 并 `return`

这个设计（降级放行）本身是合理的——不应因审核服务宕机而让整个群聊功能瘫痪。但缺少任何计数器来追踪 API 故障频率，运维者无法感知审核服务是否长期处于降级状态。

## 修复方案

在 `stats_manager` 中增加 API 健康统计，或用日志级别区分：

**方案 A（轻量）**：提高日志级别
```python
# message_handler.py
if result.error:
    logger.warning(f"审核 API 不可用，降级放行 (连续失败需关注): group={group_id}, error={result.error}")
```

**方案 B（完整）**：增加 SQLite 表 `api_errors` 记录故障
```sql
CREATE TABLE IF NOT EXISTS api_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_message TEXT,
    created_at TEXT
);
```

每次 API 失败时写入，在状态命令中展示 API 可用率。
