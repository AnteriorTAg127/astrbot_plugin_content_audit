# Issue 12 — audit_client.py 存在不可达 return 语句

**严重度**: 🟢 Minor
**涉及文件**: `audit_client.py`
**类型**: 代码质量

## 现象

```python
async def audit(self, text: str, skip_llm: bool = False) -> AuditResult:
    for attempt in range(self._max_retries + 1):
        try:
            ...
            return AuditResult(...)  # 成功则返回
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < self._max_retries:
                ...
            else:
                ...
                return AuditResult(has_violation=False, error=str(e))

    # 第 82-83 行
    return AuditResult(has_violation=False, error="未知错误")  # 永远不会执行
```

`for` 循环覆盖了 `0..max_retries` 次迭代，"最后一次失败"分支也写了 `return`。循环外还有一处 `return`，理论上永远达不到。类型检查器（mypy/pyright）也会警告。

## 修复方案

直接删除第 82-83 行。`else` 分支已经返回了：
```python
else:
    logger.error(f"审核请求失败, 已达最大重试次数: {e}")
    return AuditResult(has_violation=False, error=str(e))
```
