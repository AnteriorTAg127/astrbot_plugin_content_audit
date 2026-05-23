# Issue 35 — `_get_client()` 在 AdminManager / ViolationHandler 中重复实现

**严重度**：🟡 Major  
**涉及文件**：`admin_manager.py`（行 24-46）、`violation_handler.py`（行 29-46）  
**类型**：代码重复 / 可维护性

## 现象

两个模块各自实现了几乎完全相同的"从事件对象中提取平台客户端"的逻辑：

**admin_manager.py `_fetch_admins()` 行 28-43**：
```python
client = None
try:
    from astrbot.api.platform import PlatformAdapterType
    platform = self._context.get_platform(PlatformAdapterType.AIOCQHTTP)
    if platform:
        client = platform.get_client()
except Exception:
    pass
if client is None:
    for attr_name in ("client", "_client", "bot", "_bot", "platform"):
        client = getattr(event, attr_name, None)
        if client is not None:
            break
```

**violation_handler.py `_get_client()` 行 32-46**：
```python
try:
    from astrbot.api.platform import PlatformAdapterType
    platform = self._context.get_platform(PlatformAdapterType.AIOCQHTTP)
    if platform:
        client = platform.get_client()
        if client:
            return client
except Exception:
    pass
for attr_name in ("client", "_client", "bot", "_bot", "platform"):
    client = getattr(event, attr_name, None)
    if client is not None:
        return client
return None
```

两段逻辑的差异仅在于返回值处理（一个返回 `set[str]`，一个返回 `client`），获取客户端的核心逻辑完全一致。

## 问题分析

重复代码的问题：
1. **维护成本双倍**：如果 AstrBot API 变化或发现更好的客户端获取方式，需要改两处
2. **分歧风险**：两个版本已经出现了细微差异（如变量初始化方式），后续可能分化
3. **违反 DRY 原则**：同目录下已有公共模块的结构（`config_manager` 被所有模块引用），适合抽取共享工具

## 修复方案

将客户端获取逻辑提取为一个独立的工具函数，放置在新文件 `platform_utils.py` 中：

```python
"""平台客户端获取工具"""
from __future__ import annotations

from typing import Any


def get_platform_client(context, event) -> Any | None:
    """从事件对象和上下文中提取平台客户端

    优先使用文档化 API (PlatformAdapterType)，失败时回退到属性搜索。
    """
    # Try documented API first
    try:
        from astrbot.api.platform import PlatformAdapterType
        platform = context.get_platform(PlatformAdapterType.AIOCQHTTP)
        if platform:
            client = platform.get_client()
            if client:
                return client
    except Exception:
        pass

    # Fallback: attribute search
    for attr_name in ("client", "_client", "bot", "_bot", "platform"):
        client = getattr(event, attr_name, None)
        if client is not None:
            return client

    return None
```

然后在各模块中替换为：

```python
from .platform_utils import get_platform_client

# admin_manager.py
client = get_platform_client(self._context, event)

# violation_handler.py
client = get_platform_client(self._context, event)
```

**Why**：提取公共函数消除重复，降低维护成本。新增文件不超过 30 行，不会增加模块复杂度。如果未来需要支持其他平台适配器（如 Telegram），只需修改一处。

**How to apply**：
1. 新建 `platform_utils.py`
2. 修改 `admin_manager.py` 和 `violation_handler.py`，替换为调用公共函数
