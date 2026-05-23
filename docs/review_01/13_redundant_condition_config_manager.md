# Issue 13 — should_enable_censor 中条件冗余

**严重度**: 🟢 Minor
**涉及文件**: `config_manager.py`
**类型**: 代码质量

## 现象

```python
# config_manager.py:129
no_admin_minutes = config.get("auto_censor_no_admin_minutes", 0)
if not no_admin_minutes or no_admin_minutes == 0:
    return (True, "智能审查-非强制时间段")
```

`not no_admin_minutes` 在 `no_admin_minutes` 为 `0`、`None`、空字符串时都为 `True`。后面的 `no_admin_minutes == 0` 完全被前者覆盖，是冗余条件。

## 修复方案

```python
if no_admin_minutes is None or no_admin_minutes == 0:
    return (True, "智能审查-非强制时间段")
```

或者更简洁：

```python
no_admin_minutes = config.get("auto_censor_no_admin_minutes", 0) or 0
if no_admin_minutes == 0:
    return (True, "智能审查-非强制时间段")
```
