# Issue 32 — `record_violation()` SELECT-COUNT-then-INSERT 存在竞态，违规次数可能不准

**严重度**：🔴 Critical  
**涉及文件**：`stats_manager.py`（行 91-133）  
**类型**：并发安全 / 数据正确性

## 现象

`record_violation()` 方法通过"先 COUNT 再 INSERT"的方式计算用户的累计违规次数：

```python
async def record_violation(self, group_id, user_id, ...):
    conn = await self._get_conn()
    try:
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM violation_records
               WHERE user_id = ? AND group_id = ?""",
            (user_id, group_id),
        )
        row = await cursor.fetchone()
        violation_count = (row[0] if row else 0) + 1   # ← 第 N 步：COUNT

        await conn.execute(
            """INSERT INTO violation_records
               (..., violation_count, ...)
               VALUES (?, ..., ?, ...)""",
            (..., violation_count, ...),                  # ← 第 N+1 步：INSERT
        )
        await conn.commit()
```

这个"读-改-写"操作不是原子的。当两个消息几乎同时触发违规时：

```
协程 A: SELECT COUNT → 得到 3 → 准备 INSERT violation_count=4
协程 B: SELECT COUNT → 得到 3 → 准备 INSERT violation_count=4  (也是 4！)
协程 A: INSERT (violation_count=4)
协程 B: INSERT (violation_count=4)  ← 两条记录都是 count=4，实际应是 4 和 5
```

这在 `aiosqlite` 的默认模式下是有可能发生的——同一条 SQLite 连接上的操作是序列化的，但 COUNT 和 INSERT 之间可能被其他协程的 INSERT 插入。

## 严重性分析

`violation_count` 字段直接影响禁言时长计算：

```python
# violation_handler.py 行 214
duration = int(first_mute * (multiplier ** (current_count - 1)))
```

如果本应是第 5 次违规但记录为第 4 次，禁言时长可能是 `300 × 2^3 = 2400s` 而非 `300 × 2^4 = 4800s`。对于高并发群聊（如爆群），多个用户同时违规时，次数可能出现偏差。

## 修复方案

在 SQLite 层面做原子计数，而非应用层 COUNT：

```python
async def record_violation(self, group_id, user_id, ...):
    conn = await self._get_conn()
    try:
        # 方案 1: INSERT 后即时 COUNT（对同一连接是原子的）
        await conn.execute(
            """INSERT INTO violation_records
               (group_id, user_id, user_name, text_preview,
                request_id, action_recall, action_mute,
                mute_duration, violation_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (group_id, user_id, user_name, text_preview,
             request_id, action_recall, action_mute,
             mute_duration, datetime.now().isoformat()),
        )
        # 在同一事务中更新 violation_count
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM violation_records
               WHERE user_id = ? AND group_id = ?""",
            (user_id, group_id),
        )
        row = await cursor.fetchone()
        actual_count = row[0]
        await conn.execute(
            """UPDATE violation_records
               SET violation_count = ?
               WHERE rowid = last_insert_rowid()""",
            (actual_count,),
        )
        await conn.commit()
```

或者更简单——使用 SQLite 的 `last_insert_rowid()` + 子查询：

```python
await conn.execute(
    """INSERT INTO violation_records
       (..., violation_count, ...)
       VALUES (
           ...,
           (SELECT COUNT(*) + 1 FROM violation_records
            WHERE user_id = ? AND group_id = ?),
           ...
       )""",
    (..., user_id, group_id, ...),
)
await conn.commit()
```

**Why**：将 COUNT 和 INSERT 合并为单个 SQL 语句，利用 SQLite 的单写者模型保证原子性。SQLite 同一连接上的写操作严格序列化，子查询中的 COUNT 会反映当前连接上已提交的所有 INSERT。

**How to apply**：修改 `stats_manager.py` 的 `record_violation()` 方法，使用子查询替代两步操作。
