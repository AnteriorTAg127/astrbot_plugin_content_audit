# Issue 08 — MessageHandler/ViolationHandler 构造函数缺少类型标注

**严重度**: 🟡 Major
**涉及文件**: `message_handler.py`, `violation_handler.py`
**类型**: 代码质量

## 现象

```python
# message_handler.py:12
def __init__(self, config_manager, admin_manager, audit_client, violation_handler) -> None:

# violation_handler.py:14
def __init__(self, config_manager, stats_manager) -> None:
```

参数完全无类型标注，IDE 无法提供自动补全，类型检查器无法发现传参错误。

## 修复方案

```python
# message_handler.py
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

class MessageHandler:
    def __init__(
        self,
        config_manager: ConfigManager,
        admin_manager: AdminManager,
        audit_client: AuditClient,
        violation_handler: ViolationHandler,
    ) -> None:
```

```python
# violation_handler.py
from __future__ import annotations

class ViolationHandler:
    def __init__(
        self,
        config_manager: ConfigManager,
        stats_manager: StatsManager,
    ) -> None:
```

注意：如果使用 `from __future__ import annotations`，`violation_handler.py` 中 `ViolationHandler.__init__` 引用 `ConfigManager` 和 `StatsManager` 时需要确保它们在同一模块或已导入。推荐在文件顶部做 TYPE_CHECKING 导入以避免循环引用。
