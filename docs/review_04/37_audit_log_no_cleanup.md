# Issue 37 — `audit_log` 表无清理机制，长期运行无限膨胀

**严重度**：🟢 Minor  
**涉及文件**：`stats_manager.py`（行 22-32, 59-89）  
**类型**：运维 / 数据管理

## 现象

`audit_log` 表记录了每一条被审核的消息（无论是否违规），但没有任何自动清理或保留策略：

```python
async def init_db(self):
    await conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            user_id TEXT,
            user_name TEXT,
            text_preview TEXT,      -- ← 完整消息文本
            has_violation INTEGER,
            source TEXT,
            request_id TEXT,
            created_at TEXT
        );
    """)
```

对于活跃群聊，每天可能产生数千到数万条审核记录。每条记录包含完整的消息文本。假设平均消息 100 字符，每天 5000 条，一个月就是 15MB+，一年约 180MB。如果多个被管理群同时活跃，增长更快。

## 问题分析

当前没有：
1. 基于时间的自动清理（如保留最近 30 天）
2. 基于条数的上限（如最多保留 10 万条）
3. 手动清理命令（`/文本审核 清理日志`）
4. 按群维度清理

`get_stats()` 方法依赖 `audit_log` 做当日统计（`date(created_at) >= date(?)`），但统计其实只需要计数，不需要保留全部记录。

## 修复方案

**短期**：在 `StatsManager` 中添加基于时间的清理：

```python
async def cleanup_audit_log(self, keep_days: int = 30) -> int:
    """清理超过 keep_days 天的审核日志，返回删除条数"""
    conn = await self._get_conn()
    try:
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        cursor = await conn.execute(
            "DELETE FROM audit_log WHERE created_at < ?", (cutoff,)
        )
        await conn.commit()
        return cursor.rowcount
    except Exception as e:
        logger.error(f"清理审核日志失败: {e}")
        return 0
```

在 `main.py` 的健康检查任务中加入定期清理：

```python
async def _health_check_loop(self, interval: int) -> None:
    try:
        cleanup_counter = 0
        while True:
            await asyncio.sleep(interval)
            # 健康检查
            ...
            # 每 24 小时清理一次旧日志
            cleanup_counter += 1
            if cleanup_counter >= 24 * 3600 // interval:
                deleted = await self._stats_manager.cleanup_audit_log(keep_days=30)
                logger.info(f"审计日志清理完成，删除 {deleted} 条旧记录")
                cleanup_counter = 0
    except asyncio.CancelledError:
        ...

**Why**：SQLite 文件增长没有上限，在嵌入式/长期运行场景是常见问题。设定合理的保留周期（如 30 天）既能满足统计需求，又防止数据库膨胀。

**How to apply**：
1. 在 `StatsManager` 中添加 `cleanup_audit_log()` 方法
2. 在 `main.py` 的后台中周期性调用
3. 可选：添加 `/文本审核 清理日志` 命令
