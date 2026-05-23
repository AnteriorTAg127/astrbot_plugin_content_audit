# 16 — `_log` 多群分页逻辑根本性错误

**严重度**：🔴 Critical  
**文件**：`command_handler.py`，`_log` 方法 (行 113–155)

## 问题

当管理群关联多个被管理群时，`_log` 方法的分页逻辑会产生完全不正确的结果。核心问题：它对每个被管理群**独立分页查询**，然后合并取前 N 条。

```python
# 当前错误实现 (行 133-139)
all_violations = []
for mg_id in managed_groups:
    violations = await self._stats_manager.get_violations(
        group_id=mg_id, page=page, page_size=page_size  # 每群独立分页!
    )
    all_violations.extend(violations)

all_violations.sort(key=lambda v: v['created_at'], reverse=True)
violations = all_violations[:page_size]  # 取前10条，其余丢弃
```

## 具体场景

假设管理群关联 3 个被管理群，每群分别有违规记录 50 / 30 / 5 条：

- **第 1 页**：从群 A 取第 1-10 条、群 B 取第 1-10 条、群 C 取全部 5 条 → 共 25 条 → 排序后取前 10 条。群 B 和 C 的第 2-10 条被丢弃，群 C 的 5 条全部参与排序后被截断。**实际上只显示了群 A 的数据**（因为群 A 可能时间更新）。
- **第 2 页**：从群 A 取第 11-20 条、群 B 取第 11-20 条、群 C 无数据 → 共 20 条 → 排序取前 10 条。**丢失了群 A 的第 1-10 条、群 B 的第 1-10 条**，显示的是各群的第 3-4 页数据。

## 修复建议

方案 A（简单，适用于数据量不大）：对每个群取 `page * page_size` 条或全部，合并后排序列用 offset/limit 做真正的分页。

方案 B（更高效）：在 `stats_manager` 中增加多群联合查询：

```python
async def get_violations_multi(
    self, group_ids: list[str], page: int, page_size: int
) -> list[dict]:
    placeholders = ",".join("?" for _ in group_ids)
    cursor = await conn.execute(
        f"""SELECT * FROM violation_records
            WHERE group_id IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?""",
        (*group_ids, page_size, (page - 1) * page_size),
    )
    ...
```

**Why**：分页是用户最直观看到的功能，数据错乱直接影响业务决策（管理员可能漏看或看错违规记录）。

**How to apply**：两种修复方案的选择取决于预期数据规模。如果群数量 < 50 且每个群违规记录 < 1000，方案 A 足够。方案 B 更适合长期运行。
