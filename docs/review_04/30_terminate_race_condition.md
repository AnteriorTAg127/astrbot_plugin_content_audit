# Issue 30 — `terminate()` 健康检查任务取消后未 await，关闭 session 时存在竞态

**严重度**：🔴 Critical  
**涉及文件**：`main.py`（行 149-157）  
**类型**：并发安全 / 资源泄露

## 现象

`terminate()` 方法取消健康检查后台任务后，没有 `await` 该任务完成，直接关闭 `audit_client` 和 `stats_manager`。此时健康检查协程可能仍在执行 `health_check()` → `_get_session()`，而 `_session` 已被 `close()` 销毁。

```python
async def terminate(self) -> None:
    if self._health_check_task is not None:
        self._health_check_task.cancel()          # 发出取消请求，但不等待完成
    if self._audit_client:
        await self._audit_client.close()           # 可能和仍在运行的 health check 冲突
    if self._stats_manager:
        await self._stats_manager.close()
```

`asyncio.Task.cancel()` 只是向任务**发送取消请求**，任务并不会立即终止。它会在下一个 `await` 点抛出 `CancelledError`。在 `_health_check_loop` 中：

```python
async def _health_check_loop(self, interval: int) -> None:
    try:
        while True:
            await asyncio.sleep(interval)            # ← cancel() 后最早在此处触发 CancelledError
            # ...
            result = await self._audit_client.health_check()  # 但如果在 sleep 后、这行之前...
```

如果 `cancel()` 恰好在 `await asyncio.sleep(interval)` 返回后、`health_check()` 调用前被处理，任务可能在 `close()` 之后仍然尝试发起 HTTP 请求，触发 `aiohttp.ClientSession` 已关闭的异常。

## 问题分析

时序窗口：

```
terminate()                              _health_check_loop()
    │                                         │
    ├─ cancel() ──────────────────────────►   │ (正在 sleep)
    │                                         │ sleep 返回
    ├─ await close() 销毁 session             │ → CancelledError 还未处理
    │                                         ├─ health_check() 尝试用已关闭的 session
    │                                         └─ 异常
    └─ await close() stats
```

虽然 `CancelledError` 最终会被捕获，但如果 `interval` 较小（如默认 60 秒），在健康检查执行期间触发 `terminate()` 的概率不低。

## 修复方案

在 `cancel()` 后 `await` 任务完成:

```python
async def terminate(self) -> None:
    if self._health_check_task is not None:
        self._health_check_task.cancel()
        try:
            await self._health_check_task    # 等待任务真正结束
        except asyncio.CancelledError:
            pass
    if self._audit_client:
        await self._audit_client.close()
    if self._stats_manager:
        await self._stats_manager.close()
    logger.info("文本审核插件已卸载")
```

**Why**：`cancel()` + `await task` 是 asyncio 中安全取消后台任务的标准模式。`await` 确保任务协程完全退出（包括 `finally` 块和上下文管理器清理）后再释放资源。

**How to apply**：仅修改 `main.py` 的 `terminate()` 方法，加入 `await self._health_check_task`。
