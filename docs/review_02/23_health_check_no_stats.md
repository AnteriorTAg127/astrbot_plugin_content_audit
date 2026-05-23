# 23 — 健康检查失败无统计指标

**严重度**：🟢 Minor  
**文件**：`main.py` (行 126-131)，`audit_client.py` (行 82-96)

## 问题

`_health_check_loop` 在健康检查失败时仅输出日志警告：

```python
async def _health_check_loop(self, interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        result = await self._audit_client.health_check()
        if result is None:
            logger.warning("审核 API 健康检查失败")
```

没有任何计数、时间戳记录或指标暴露。运维人员无法通过命令查看 API 的健康历史——只能翻日志。而设计文档 §六中 `/文本审核 状态` 的描述提到应包含"API 健康状态"，但当前实现中状态命令不返回任何健康信息。

## 修复建议

在 `StatsManager` 或 `AuditClient` 中增加轻量级健康指标记录：

```python
class AuditClient:
    def __init__(self, ...):
        ...
        self._last_health_ok: bool = True
        self._last_health_time: float = 0
        self._health_fail_count: int = 0

    async def health_check(self) -> dict | None:
        ...
        self._last_health_time = time.time()
        if result is None:
            self._health_fail_count += 1
            self._last_health_ok = False
        else:
            self._last_health_ok = True
```
并将 `_last_health_ok` 和 `_health_fail_count` 暴露给 `/文本审核 状态` 命令。

**Why**：运维可观测性是生产级插件的基本需求，当前实现只满足了"最简可行"。

**How to apply**：在 `AuditClient` 增加简单计数器，在 `command_handler._status` 中读取并展示。
