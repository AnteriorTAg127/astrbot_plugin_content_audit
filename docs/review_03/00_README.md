# Code Review 03 — 问题总览

审查日期：2026-05-23
审查范围：`astrbot_plugin_content_audit` 全部 Python 源文件 + `_conf_schema.json`（review_01 / review_02 后第三轮）

---

## 与 review_01 / review_02 的关系

本 review 聚焦前两轮（15 + 11 = 26 个问题）**未覆盖**的新问题，重点关注用户测试中发现的 `group_settings` schema 类型问题。所有问题编号从 27 开始延续。

## 触发来源

用户测试反馈：管理群对应配置应使用 `template_list` 类型 schema 创建自增表，部分基础设置可在其中修改。

## 问题分级

| 编号 | 严重度 | 标题 | 涉及文件 |
|------|--------|------|----------|
| 27 | 🟡 Major | `group_settings` 使用 `list` 而非 `template_list` schema | `_conf_schema.json`, `config_manager.py` |
| 28 | 🟡 Major | `ConfigManager._group_configs` 不支持配置热更新 | `config_manager.py`, `main.py` |
| 29 | 🟢 Minor | per-group 配置项与全局配置层级重叠、缺失 per-group 行为覆写 | `_conf_schema.json`, `message_handler.py`, `config_manager.py` |

---

## 修复优先级建议

1. **立即修复**：27（schema 类型升级 → template_list）—— 用户测试反馈
2. **本迭代修复**：28（配置热更新）—— 影响运行时体验
3. **下迭代修复**：29（配置层级重整）—— 架构优化
