# Code Review 01 — 问题总览

审查日期：2026-05-23
审查范围：`astrbot_plugin_content_audit` 全部 Python 源文件

---

## 问题分级

| 编号 | 严重度 | 标题 | 涉及文件 |
|------|--------|------|----------|
| 01 | 🔴 Critical | sqlite3 同步库阻塞事件循环 | stats_manager.py, requirements.txt |
| 02 | 🔴 Critical | 白名单数据双轨不一致 | command_handler.py, config_manager.py, stats_manager.py, _conf_schema.json |
| 03 | 🔴 Critical | audit_log 表从未写入 | message_handler.py, stats_manager.py |
| 04 | 🔴 Critical | _log 命令跨管理群泄漏违规数据 | command_handler.py |
| 05 | 🔴 Critical | StarTools.get_data_dir() API 未在文档中确认 | main.py |
| 06 | 🟡 Major | event.get_group_id/get_self_id/get_message_id 未确认存在 | main.py, message_handler.py, violation_handler.py |
| 07 | 🟡 Major | 平台客户端获取方式依赖内部实现 | admin_manager.py, violation_handler.py |
| 08 | 🟡 Major | MessageHandler/ViolationHandler 构造函数缺少类型标注 | message_handler.py, violation_handler.py |
| 09 | 🟡 Major | _conf_schema.json 中 whitelist 配置段与 SQLite 白名单割裂 | _conf_schema.json |
| 10 | 🟡 Major | health_check_interval 配置项未实际实现 | main.py |
| 11 | 🟢 Minor | ruff noqa 抑制歧义 Unicode 字符 | main.py, message_handler.py, violation_handler.py, config_manager.py |
| 12 | 🟢 Minor | audit_client.py 存在不可达 return 语句 | audit_client.py |
| 13 | 🟢 Minor | should_enable_censor 中条件冗余 | config_manager.py |
| 14 | 🟢 Minor | 降级放行无 API 故障统计 | audit_client.py, message_handler.py |
| 15 | 🟢 Minor | cmd_content_audit 方法返回类型缺失 | main.py |

---

## 修复优先级建议

1. **立即修复**：01 (sqlite→aiosqlite)、02 (白名单双轨)、03 (audit_log)、04 (数据泄漏)
2. **本迭代修复**：05-10
3. **下迭代修复**：11-15
