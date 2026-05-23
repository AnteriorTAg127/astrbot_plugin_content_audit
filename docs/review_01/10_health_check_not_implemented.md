# Issue 10 — health_check_interval 配置项未实际实现

**严重度**: 🟡 Major
**涉及文件**: `_conf_schema.json`, `main.py`, `audit_client.py`
**类型**: 功能缺失

## 现象

`_conf_schema.json` 定义了 `api.health_check_interval`（默认 60 秒），`audit_client.health_check()` 方法也已实现，但没有任何地方启动定时健康检查任务。

## 修复方案

在 `main.py` 的 `initialize()` 中启动一个后台任务：

```python
import asyncio

async def initialize(self) -> None:
    # ... 现有初始化代码 ...

    # 启动健康检查后台任务
    health_interval = api_config.get("health_check_interval", 60)
    if health_interval > 0:
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(health_interval)
        )

async def _health_check_loop(self, interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        result = await self._audit_client.health_check()
        if result is None:
            logger.warning("审核 API 健康检查失败")

async def terminate(self) -> None:
    if hasattr(self, '_health_check_task'):
        self._health_check_task.cancel()
    if self._audit_client:
        await self._audit_client.close()
```

注意：`asyncio.create_task` 返回的 task 需要持有引用以防止被 GC 回收。
