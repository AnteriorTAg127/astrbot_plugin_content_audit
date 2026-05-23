# 25 — `get_stats` 日期过滤依赖字符串比较

**严重度**：🟢 Minor  
**文件**：`stats_manager.py` (行 195-233)

## 问题

`get_stats()` 的"今日"统计使用字符串比较：

```python
today_str = date.today().isoformat()  # "2026-05-23"
cursor = await conn.execute(
    "SELECT COUNT(*) FROM audit_log WHERE created_at >= ?",
    (today_str,),
)
```

这在 SQLite 中之所以能工作，是因为 ISO 8601 格式的字符串与日期比较恰好一致：`"2026-05-23T14:30:00" >= "2026-05-23"` 为 `True`。

但这是**依赖字符串排序特性**而非数据库日期语义。如果有人错误地修改了 `created_at` 的格式（例如改为 `"23/05/2026"`），字符串比较将失效且不会报错。

## 修复建议

使用 SQLite 的日期函数：

```python
cursor = await conn.execute(
    "SELECT COUNT(*) FROM audit_log WHERE date(created_at) >= date(?)",
    (today_str,),
)
```

或使用 `DATE()` 函数提取日期部分进行比较。但需要注意如果 `created_at` 是 ISO 8601 格式，`date(created_at)` 可以正常工作。

如果担心性能（`date()` 函数可能影响索引使用），当前方式在格式稳定的前提下是可接受的。但至少应添加注释说明为什么字符串比较可行。

**Why**：当前方式不会出错，但属于隐性假设，未来代码修改者可能不知情。

**How to apply**：如果追求严谨，改用 `date()` 函数；如果保持现状，添加注释说明依赖 ISO 格式的字符串排序特性。
