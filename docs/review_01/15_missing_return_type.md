# Issue 15 — cmd_content_audit 方法返回类型缺失

**严重度**: 🟢 Minor
**涉及文件**: `main.py`
**类型**: 代码质量

## 现象

```python
@filter.command("文本审核")
async def cmd_content_audit(self, event: AstrMessageEvent):
    """文本审核命令入口（仅管理群可用）"""
    ...
    yield event.plain_result(reply)
```

方法没有返回类型标注。虽然 Python 的 `yield` 使函数变为生成器，但类型标注应为 `AsyncGenerator` 或至少 `Any`。

## 修复方案

```python
from collections.abc import AsyncGenerator
from astrbot.api.event import MessageEventResult

@filter.command("文本审核")
async def cmd_content_audit(
    self, event: AstrMessageEvent
) -> AsyncGenerator[MessageEventResult, None]:
    ...
```

或者如果不想引入额外 import：

```python
from typing import Any

@filter.command("文本审核")
async def cmd_content_audit(self, event: AstrMessageEvent) -> Any:
    ...
```
