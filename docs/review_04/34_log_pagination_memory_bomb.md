# Issue 34 — `_log()` 分页逻辑 O(n×m) 膨胀，多群大数据量时内存爆炸

**严重度**：🟡 Major  
**涉及文件**：`command_handler.py`（行 114-158）  
**类型**：性能 / 内存

## 现象

`_log()` 方法的分页实现：遍历所有被管理群，对每个群拉取 `page × page_size` 条违规记录，在内存中合并排序后再切片：

```python
async def _log(self, event, group_id, args):
    page = int(args[0]) if args else 1
    page_size = 10
    managed_groups = self._config_manager.get_managed_group_ids(group_id)

    fetch_size = page * page_size           # 第 N 页 → 每群拉 N×10 条
    all_violations = []
    for mg_id in managed_groups:
        violations = await self._stats_manager.get_violations(
            group_id=mg_id, page=1, page_size=fetch_size
        )
        all_violations.extend(violations)

    all_violations.sort(key=lambda v: v['created_at'], reverse=True)
    offset = (page - 1) * page_size
    violations = all_violations[offset:offset + page_size]
```

**数据量增长**：假设 5 个被管理群，每群 1000 条违规记录：

| 页码 | 每群拉取 | 总拉取 | 实际需要 |
|------|---------|--------|---------|
| 1 | 10 | 50 | 10 |
| 10 | 100 | 500 | 10 |
| 100 | 1000 | 5000 | 10 |

第 100 页时，为了显示 10 条记录，从数据库拉取了 5000 条，在内存中排序后丢弃了 4990 条。

## 问题分析

根因在于：现有 `StatsManager.get_violations()` 的 SQL 只支持单群分页，不支持跨群 UNION + 统一排序 + 分页。因此在 Python 层做了"全量拉取再排序"的兜底。

对于日常使用（查看最近几页），影响不大。但如果：
- 管理群关联了很多被管理群
- 某个群违规记录积累到数千条
- 用户尝试翻到较后的页码

内存占用和数据库 IO 会线性膨胀。

## 修复方案

**方案 A（推荐）— 修改 SQL 支持跨群查询**：

在 `StatsManager` 中增加一个跨群查询方法：

```python
async def get_violations_multi_group(
    self, group_ids: list[str], page: int = 1, page_size: int = 10
) -> list[dict]:
    conn = await self._get_conn()
    try:
        placeholders = ",".join("?" for _ in group_ids)
        cursor = await conn.execute(
            f"""SELECT * FROM violation_records
               WHERE group_id IN ({placeholders})
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (*group_ids, page_size, (page - 1) * page_size),
        )
        return [dict(row) for row in await cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get multi-group violations: {e}")
        return []
```

然后在 `_log()` 中直接调用一次：

```python
async def _log(self, event, group_id, args):
    page = int(args[0]) if args else 1
    page_size = 10
    managed_groups = self._config_manager.get_managed_group_ids(group_id)
    if not managed_groups:
        return "..."

    violations = await self._stats_manager.get_violations_multi_group(
        managed_groups, page=page, page_size=page_size
    )
    # ... 格式化输出
```

**方案 B（短期）— 限制最大获取量**：

不改 SQL，在 Python 层加硬上限：

```python
max_fetch = min(page * page_size, 500)  # 最多拉 500 条
```

**Why**：方案 A 将排序和分页推到数据库层，利用 SQLite 的索引和 LIMIT 机制，一次查询返回正好 10 条。避免了 Python 层的大量内存分配和排序开销。

**How to apply**：
1. 在 `StatsManager` 中添加 `get_violations_multi_group()` 方法
2. 修改 `CommandHandler._log()` 使用新方法
