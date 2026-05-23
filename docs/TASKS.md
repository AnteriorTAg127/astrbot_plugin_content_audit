# 总任务列表

> 每完成一项，将 `- [ ]` 改为 `- [x]`。批次内部可并行，批次之间严格顺序。
>
> 实现依据：`docs/设计方案.md`（v3）、`AGENT_RULES.md`

---

## 批次 0：基础设施（无依赖，并行）

- [x] **T0.1** — 更新 `_conf_schema.json`：按设计方案 §五 的 6 个配置分组（api / audit / action / notify / group_settings / whitelist）定义完整 JSON Schema。每个字段含 type、default、description。
- [x] **T0.2** — 更新 `requirements.txt`：写入 `aiohttp>=3.9.0`。
- [x] **T0.3** — 更新 `README.md`：写项目简介、功能特性、安装说明、命令列表、配置说明、许可证。参考 `docs/图片审核插件的readme.md` 的结构。
- [x] **T0.4** — 更新 `metadata.yaml`：确保 `type: plugin` 字段存在（如无则添加）。

---

## 批次 1：基础模块（无内部依赖，四文件并行）

- [x] **T1.1** — 创建 `config_manager.py`：实现 `ConfigManager` 类。功能：读取全局配置和群配置、`is_group_enabled()`、`is_manage_group()`、`get_group_config()`、`get_manage_group_id()`、`get_managed_group_ids()`、`is_whitelisted()`、`should_enable_censor()`（三层决策树）。
- [x] **T1.2** — 创建 `stats_manager.py`：实现 `StatsManager` 类。功能：`init_db()` 建表（audit_log / violation_records / whitelist 三表）、增删查接口、`get_stats()` 返回统计汇总。SQLite，路径用 `StarTools.get_data_dir()`。
- [x] **T1.3** — 创建 `admin_manager.py`：实现 `AdminManager` 类。功能：管理员列表缓存（5 分钟 TTL）、`is_user_admin_cached()`（缓存查询）、`is_user_admin()`（精确查询）、`record_admin_message()`、`get_last_admin_time()`。
- [x] **T1.4** — 创建 `audit_client.py`：实现 `AuditResult` 数据类和 `AuditClient` 类。功能：`POST /audit` 调用、`GET /health` 健康检查、指数退避重试（最多 3 次）、超时处理。用 aiohttp。

---

## 批次 2：处置层（依赖 T1.1 + T1.2）

- [x] **T2.1** — 创建 `violation_handler.py`：实现 `ViolationHandler` 类。构造函数注入 config_manager 和 stats_manager。`handle()` 方法：始终执行管理群通报；根据 `auto_recall`/`auto_mute` 开关决定是否撤回和禁言；管理员仅通报不处罚；禁言时长按 `first_mute × multiplier^(N-1)` 递增（上限 max_mute）；通报格式参照设计方案 §二。

---

## 批次 3：编排层（依赖 T1 + T2，二文件并行）

- [x] **T3.1** — 创建 `message_handler.py`：实现 `MessageHandler` 类。构造函数注入四个模块（config / admin / audit / violation）。`handle(event)` 编排完整流程：提取群号和用户 ID → 过滤非文本 → 智能审查决策 → 白名单/管理员豁免 → 调用 audit_client → 违规则调 violation_handler。
- [x] **T3.2** — 创建 `command_handler.py`：实现 `CommandHandler` 类。构造函数注入 config / admin / stats。`dispatch(event, subcommand, args)` 按设计方案 §六 的 7 条命令分发。入口校验 is_manage_group()。权限敏感操作（删除违规）调 is_user_admin() 精确查询。

---

## 批次 4：入口集成（依赖全部）

- [x] **T4.1** — 重写 `main.py`：`@register("content_audit_text", "AnteriorTAg127", "文本内容审核插件", "1.0.0", command_group="文本审核")`。在 `initialize()` 中创建所有模块实例，`on_message` 委托给 message_handler，所有命令注册委托给 command_handler。`terminate()` 关闭 aiohttp session。

---

## 批次 5：收尾

- [x] **T5.1** — 全局检查：所有文件符合 `AGENT_RULES.md` 中的 AstrBot 硬性约束（导入规范、数据路径、日志、异步、上下文管理器、metadata type 字段）。
- [x] **T5.2** — README 终审：确保命令列表、配置说明、安装步骤与实际代码一致。
- [x] **T5.3** — Git 提交推送（等待用户确认）：`git add -A && git commit -m "feat: 文本审核插件完整实现" && git push origin main`。

---

## 依赖图

```
T0(并行) → T1(四文件并行) → T2(一个文件) → T3(二文件并行) → T4(一个文件) → T5
```

