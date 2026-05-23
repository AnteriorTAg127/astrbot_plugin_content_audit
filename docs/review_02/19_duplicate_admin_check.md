# 19 — `message_handler` 中对同一用户重复拉取管理员身份

**严重度**：🟡 Major  
**文件**：`message_handler.py` (行 86-88, 行 107-111)

## 问题

`handle()` 方法在**同一个请求**中对同一用户执行了两次管理员身份查询：

```python
# 第 1 次：智能审查 - 记录管理员发言时间 (行 86-88)
if group_config and group_config.get("auto_censor_no_admin_minutes", 0) > 0:
    is_admin_cached = await self._admin_manager.is_user_admin_cached(event, group_id, user_id)
    if is_admin_cached:
        self._admin_manager.record_admin_message(group_id)

# 第 2 次：跳过管理员检查 (行 107-111)
skip_admin: bool = audit_config.get("skip_admin", True)
if skip_admin:
    is_admin = await self._admin_manager.is_user_admin_cached(event, group_id, user_id)
```

`is_user_admin_cached` 在缓存命中时开销很小（字典查找），但缓存未命中时需要调用 `_fetch_admins`，这是一个**平台 API 调用**（拉取群成员列表）。两次调用在同一个 `handle()` 调用中是浪费，尤其在缓存 TTL 内首次调用已写入缓存的情况下，第二次调用是纯冗余。

## 场景

当 `enable_auto_censor=false` 且 `skip_admin=true` 时，流程为：
1. 跳过第一次 admin 检查（因为 `auto_censor_no_admin_minutes == 0`）
2. 执行第二次 admin 检查

当 `enable_auto_censor=true` 且 `auto_censor_no_admin_minutes > 0` 且 `skip_admin=true` 时：
1. 执行第一次 admin 检查（缓存未命中则拉取）
2. 执行第二次 admin 检查（缓存已命中，但仍是浪费）

## 修复建议

将管理员查询提前到流程开始，结果复用：

```python
is_admin: bool = False
need_admin_check = (
    group_config.get("auto_censor_no_admin_minutes", 0) > 0
    or audit_config.get("skip_admin", True)
)
if need_admin_check:
    is_admin = await self._admin_manager.is_user_admin_cached(event, group_id, user_id)
    if is_admin:
        self._admin_manager.record_admin_message(group_id)

# ... 后续使用 is_admin 变量
```

**Why**：每次冗余调用在缓存失效时都触发平台 API，产生不必要的延迟（尤其在群成员多的群）。

**How to apply**：提升 `is_admin` 变量作用域，在需要管理员检查的路径中统一查询一次。
