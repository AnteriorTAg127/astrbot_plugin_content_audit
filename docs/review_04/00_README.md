# Code Review 04 — 问题总览

审查日期：2026-05-23
审查范围：`astrbot_plugin_content_audit` 全部 Python 源文件（review_01 / review_02 / review_03 后第四轮）

---

## 与前三轮的关系

本 review 聚焦前三轮（15 + 11 + 3 = 29 个问题）**未覆盖**的新问题。review_03 的三个问题（27-29）已在当前代码中修复，本轮不再重复。

重点审查方向：
- 并发安全（race condition、资源泄露）
- 边界条件与异常处理
- 设计文档与实现之间的差距
- 死代码与未实现功能
- 性能热点（分页、缓存）

## 问题分级

| 编号 | 严重度 | 标题 | 涉及文件 |
|------|--------|------|----------|
| 30 | 🔴 Critical | `terminate()` 健康检查任务取消后未 await，关闭 session 时存在竞态 | `main.py` |
| 31 | 🔴 Critical | `update_base_url()` 丢弃旧 session 而不关闭，造成连接泄露 | `audit_client.py` |
| 32 | 🔴 Critical | `record_violation()` SELECT-COUNT-then-INSERT 存在竞态，违次数可能不准 | `stats_manager.py` |
| 33 | 🟡 Major | `maybe_reload()` 仅检测 group_settings/api 变更，遗漏其他配置段 | `config_manager.py` |
| 34 | 🟡 Major | `_log()` 分页逻辑 O(n×m) 膨胀，多群大数据量时内存爆炸 | `command_handler.py` |
| 35 | 🟡 Major | `_get_client()` 在 AdminManager / ViolationHandler 中重复实现 | `admin_manager.py`, `violation_handler.py` |
| 36 | 🟡 Major | string→int 转换无 try/except，含非数字 ID 时 crash | `violation_handler.py` |
| 37 | 🟢 Minor | `audit_log` 表无清理机制，长期运行无限膨胀 | `stats_manager.py` |
| 38 | 🟢 Minor | 设计方案中的 `notify.mode` 配置未实现 | `_conf_schema.json`, `violation_handler.py` |
| 39 | 🟢 Minor | `health_status` 属性 / `_health_fail_count` 字段为死代码 | `audit_client.py` |
| 40 | 🟢 Minor | `is_whitelisted()` 每次消息都查 DB，无内存缓存 | `config_manager.py` |
| 41 | 🟢 Minor | 重复 group_id 配置条目被静默覆盖，无警告 | `config_manager.py` |

---

## 修复优先级建议

1. **立即修复**：30, 31, 32（竞态与资源泄露）
2. **本迭代修复**：33, 34, 35, 36（功能正确性与性能）
3. **下迭代修复**：37-41（运维与体验优化）
