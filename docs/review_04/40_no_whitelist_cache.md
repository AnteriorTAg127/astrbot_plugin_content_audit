# Issue 40 — `is_whitelisted()` 每次消息都查 DB，无内存缓存

**严重度**：🟢 Minor  
**涉及文件**：`config_manager.py`（行 103-109）  
**类型**：性能

## 现象

每条消息进入审核流水线时，`message_handler.handle()` 都会调用 `is_whitelisted()`，后者每次都查询 SQLite 数据库：

```python
async def is_whitelisted(self, user_id: str) -> bool:
    whitelist = self.config.get("whitelist", {})
    if not whitelist.get("enabled", False):
        return False
    users = await self._stats_manager.get_whitelist()
    return user_id in users
```

而 `get_whitelist()` 做的是 `SELECT user_id FROM whitelist`，返回全量表。

对于活跃群聊，每秒可能有数条消息。如果 whitelist 未启用则不查 DB（short-circuit return），但如果启用了白名单，每条消息都做一次全表扫描。白名单通常是小表（几十到几百条），但高频查询仍会积累 SQLite 的 IO 开销。

## 问题分析

对比 `AdminManager` 已经有了内存缓存机制（`_admin_cache` + TTL），白名单却每次都查 DB。白名单的特点很适合缓存：

- 变更频率低（管理员手动添加/删除）
- 读频率极高（每条消息检查一次）
- 数据量小（几十到几百个 QQ 号）

当前没有缓存，且 `is_whitelisted()` 的调用在审核 API 请求之前（行 116），意味着每次都需要等 DB 查询结果才能决定是否跳过审核。

## 修复方案

参照 `AdminManager` 的模式，在 `ConfigManager` 或 `StatsManager` 中添加白名单缓存：

```python
class ConfigManager:
    def __init__(self, ...):
        ...
        self._whitelist_cache: set[str] | None = None
        self._whitelist_cache_time: float = 0.0
        self._whitelist_cache_ttl: int = 60  # 白名单变更频率低，可设较长的 TTL

    async def _refresh_whitelist_cache(self) -> None:
        users = await self._stats_manager.get_whitelist()
        self._whitelist_cache = set(users)
        self._whitelist_cache_time = asyncio.get_event_loop().time()

    async def is_whitelisted(self, user_id: str) -> bool:
        whitelist = self.config.get("whitelist", {})
        if not whitelist.get("enabled", False):
            return False
        # 懒加载 + TTL 过期刷新
        now = asyncio.get_event_loop().time()
        if (self._whitelist_cache is None
                or now - self._whitelist_cache_time > self._whitelist_cache_ttl):
            await self._refresh_whitelist_cache()
        return user_id in self._whitelist_cache

    def invalidate_whitelist_cache(self) -> None:
        """白名单变更后（添加/删除命令）调用以强制刷新"""
        self._whitelist_cache = None
```

`CommandHandler` 中 `_whitelist_add` / `_whitelist_remove` 在执行后调用 `config_manager.invalidate_whitelist_cache()`。

**Why**：白名单是高频读低频写的数据，缓存是最直接的优化手段。`set` 的 `in` 操作是 O(1)，相比每次 `SELECT` 有明显提升。

**How to apply**：
1. 在 `ConfigManager` 中添加白名单缓存
2. 在 `CommandHandler` 的白名单变操作后调用 cache invalidation
3. 可选：将缓存逻辑移到 `StatsManager` 中（保持 ConfigManager 轻薄）
