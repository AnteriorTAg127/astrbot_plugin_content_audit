# Issue 01 — sqlite3 同步库阻塞事件循环

**严重度**: 🔴 Critical
**涉及文件**: `stats_manager.py`, `requirements.txt`
**类型**: 同步/异步问题

## 现象

`stats_manager.py` 全量使用 Python 标准库 `sqlite3`，虽然包了 `asyncio.to_thread()`，但：

1. `sqlite3` 是纯同步库，每次 DB 操作都占用默认线程池的一个工作线程
2. AstrBot 明确禁止使用同步 I/O 库（参考其禁止 `requests` 的原则），原因是一致的——同步阻塞会拖慢整个事件循环
3. `asyncio.to_thread()` 只是把阻塞转移到线程池，高并发场景下线程池耗尽仍会导致主页面卡死

## 修复方案

替换为 `aiosqlite`：

1. `requirements.txt` 增加 `aiosqlite>=0.20.0`
2. `stats_manager.py` 改为全异步：

```python
import aiosqlite

class StatsManager:
    def __init__(self, data_dir: str) -> None:
        self._db_path = os.path.join(data_dir, "content_audit.db")

    async def _get_conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def init_db(self) -> None:
        conn = await self._get_conn()
        try:
            await conn.executescript("""...""")
            await conn.commit()
        finally:
            await conn.close()
```

所有方法去掉 `asyncio.to_thread()` 包裹，改为直接 `await conn.execute(...)` / `await conn.commit()`。
