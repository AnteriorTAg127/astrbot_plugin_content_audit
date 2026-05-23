# Issue 07 — 平台客户端获取方式依赖内部实现

**严重度**: 🟡 Major
**涉及文件**: `admin_manager.py`, `violation_handler.py`
**类型**: API 兼容性

## 现象

两个文件都通过遍历 `event` 对象的属性名（`client/_client/bot/_bot/platform`）来猜测平台客户端：

```python
# admin_manager.py:29-30
for attr_name in ("client", "_client", "bot", "_bot", "platform"):
    client = getattr(event, attr_name, None)
    if client is not None:
        break
```

同样的问题出现在 `violation_handler.py:21-25`。

这是完全依赖 AstrBot 内部实现的脆弱代码——不同消息平台适配器（aiocqhttp、qq_official、telegram 等）暴露客户端的方式可能完全不同。

## 修复方案

AstrBot 文档提供了两种获取平台客户端的正确方式：

**方式一**：通过平台适配器类型获取
```python
from astrbot.api.platform import AiocqhttpAdapter
platform = self.context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
client = platform.get_client()
```

**方式二**：通过 event 直接访问（aiocqhttp 特化）
```python
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
if isinstance(event, AiocqhttpMessageEvent):
    client = event.bot
```

推荐方式一，因为它不依赖平台特化类型。但注意：

- `admin_manager._fetch_admins()` 返回的 `members` 结构和 `send_group_msg`/`delete_msg`/`set_group_ban` 等方法的可用性仍取决于具体平台适配器
- 建议为 `admin_manager` 和 `violation_handler` 注入 `context`，通过 `context.get_platform()` 获取平台实例
- 或者接收一个 `client` 对象作为依赖注入（由 `main.py` 在 `initialize()` 中获取后传入）
