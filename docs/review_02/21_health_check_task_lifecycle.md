# 21 — `_health_check_task` 生命周期不安全

**严重度**：🟡 Major  
**文件**：`main.py` (行 28-38, 行 133-138)

## 问题

`_health_check_task` 属性在 `__init__` 中未声明，仅在 `initialize()` 中条件创建：

```python
# __init__ 中未声明 _health_check_task
def __init__(self, context: Context) -> None:
    super().__init__(context)
    self._config_manager: ConfigManager | None = None
    # ... 其他 7 个属性都声明了，唯独没有 _health_check_task

# initialize 中条件创建
health_interval = api_config.get("health_check_interval", 60)
if health_interval > 0:
    self._health_check_task = asyncio.create_task(...)

# terminate 中依赖 hasattr 防御
async def terminate(self) -> None:
    if hasattr(self, '_health_check_task'):
        self._health_check_task.cancel()
```

三个问题：

1. **属性不声明**：违反 Python 最佳实践，也让 IDE 和类型检查器无法追踪该属性。

2. **`hasattr` 防御脆弱**：如果 `initialize()` 因为异常提前返回（初始化其他模块时出错），`_health_check_task` 不会被设置，`terminate()` 中的 `hasattr` 会跳过清理——这恰好是正确的行为，但纯属巧合而非有意的设计。

3. **缺少 `asyncio.CancelledError` 处理**：`_health_check_loop` 中的 `await asyncio.sleep(interval)` 在被取消时会抛出 `CancelledError`，但代码未捕获，异常会传播到事件循环的默认 handler。虽然通常无害，但日志中不会有明确的关闭日志。

## 修复建议

```python
def __init__(self, context: Context) -> None:
    super().__init__(context)
    self._health_check_task: asyncio.Task | None = None
    # ... 其他属性

async def initialize(self) -> None:
    ...
    health_interval = api_config.get("health_check_interval", 60)
    if health_interval > 0:
        self._health_check_task = asyncio.create_task(...)

async def terminate(self) -> None:
    if self._health_check_task:
        self._health_check_task.cancel()
        try:
            await self._health_check_task
        except asyncio.CancelledError:
            pass
    ...
```

**Why**：在正常使用中不会触发问题，但当 `initialize()` 失败时，`terminate()` 的行为不应依赖巧合。

**How to apply**：将属性声明加入 `__init__`，在 `terminate()` 中显式等待任务取消并捕获 `CancelledError`。
