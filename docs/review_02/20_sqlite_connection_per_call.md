# 20 — 每条消息新建+销毁 SQLite 连接

**严重度**：🟡 Major  
**文件**：`stats_manager.py` (所有方法)

## 问题

`StatsManager` 中每个数据库方法都调用 `_get_conn()`，该方法每次创建全新的 `aiosqlite.Connection`：

```python
async def _get_conn(self) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(self._db_path)
    conn.row_factory = aiosqlite.Row
    return conn
```

每个公共方法（`record_audit`, `record_violation`, `get_violation_count`, `get_violations`, `get_stats` 等）都是 `conn = await self._get_conn()` → `do_work` → `await conn.close()` 的模式。

## 影响

在一次 `message_handler.handle()` 调用中，连接创建/销毁序列为：

```
record_audit() → connect → INSERT → commit → close
record_violation() → connect → SELECT → INSERT → commit → close
get_violation_count() → connect → SELECT → close
```

一条违规消息 = **3 次 connect + 3 次 close**。在高频群场景下（如大群每秒数十条消息），SQLite 文件的打开/关闭开销不可忽略，且频繁调用 `connect` 无法利用 SQLite 的 WAL 模式并发读优势。

## 修复建议

方案 A：共享连接。在 `__init__` 中持有一个连接实例，所有方法复用：

```python
class StatsManager:
    def __init__(self, data_dir: str) -> None:
        self._db_path = os.path.join(data_dir, "content_audit.db")
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def close(self):
        if self._conn:
            await self._conn.close()
```

方案 B（更保守）：连接池或连接上下文管理器，避免长期持有一个可能超时的连接。

**注意**：如果采用方案 A，需在 `main.py` 的 `terminate()` 中调用 `self._stats_manager.close()`。

**Why**：连接复用是数据库访问的基本优化，影响性能但不影响正确性。

**How to apply**：方案 A 简单且对 SQLite 完全可行（SQLite 的单写入锁与 aiosqlite 的异步适配配合良好）。如果担心连接意外关闭，加入重连逻辑。
