# Agent 任务执行规则

## 总则

1. **一步一勾**：每个 Agent 执行完分配的任务后，更新 `TASKS.md` 中对应条目的 `- [ ]` 为 `- [x]`。
2. **只做自己批次**：每个 Agent 严格按照 `TASKS.md` 中分配的批次执行，不跨界。
3. **依据设计方案**：所有实现须参照 `docs/设计方案.md` 中的功能描述和配置项定义。
4. **写入正确路径**：所有文件写入 `F:\astrbot\AstrBot\data\plugins\astrbot_plugin_content_audit\`，bash 中对应路径为 `/sessions/modest-compassionate-heisenberg/mnt/astrbot_plugin_content_audit/`。
5. **复用现有文件**：`main.py`、`metadata.yaml`、`README.md`、`.gitignore` 已存在，直接修改，不新建。

## AstrBot 硬性约束

以下约束来自 AstrBot 插件规范，违反则运行时报错：

| 规则 | 说明 |
|------|------|
| 导入规范 | 只用 `from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult` 和 `from astrbot.api.star import Context, Star, register`，禁止从 `astrbot.core` 导入 |
| 数据路径 | 用 `from astrbot.api.all import StarTools` → `StarTools.get_data_dir()` 获取持久化目录，禁止硬编码 `data/` |
| 日志 | `from astrbot.api import logger`，用 `logger.info/warning/error` |
| 事件传播 | 用 `event.stop_propagation()`，不用 `event.stop_event()` |
| 消息组件 | 必要时从 `astrbot.api.message_components import *` 获取 Plain、Image、At 等 |
| 异步 | 网络调用和数据 IO 一律 async/await，不混用同步阻塞方式 |
| 文件操作 | JSON 文件用 `with open() as f` 上下文管理器 |
| metadata.yaml | 必须有 `type: plugin` 字段 |

## 模块间接口约定

所有模块文件创建时，同目录下已有模块可直接 `import`。各模块对外暴露的类名和关键方法签名以下表为准：

| 模块 | 类名 | 关键公开方法 |
|------|------|-------------|
| `config_manager.py` | `ConfigManager` | `__init__(context)`, `is_group_enabled()`, `is_manage_group()`, `get_group_config()`, `get_manage_group_id()`, `get_managed_group_ids()`, `is_whitelisted()`, `should_enable_censor()` |
| `admin_manager.py` | `AdminManager` | `__init__()`, `is_user_admin_cached(event, group_id, user_id)`, `is_user_admin(event, group_id, user_id)`, `record_admin_message(group_id)`, `get_last_admin_time(group_id)` |
| `audit_client.py` | `AuditClient`, `AuditResult` | `__init__(base_url, api_key, timeout, max_retries)`, `audit(text, skip_llm)`, `health_check()` |
| `stats_manager.py` | `StatsManager` | `__init__(data_dir)`, `init_db()`, `record_audit(...)`, `record_violation(...)`, `get_violation_count()`, `get_violations()`, `delete_violations()`, `get_stats()` |
| `violation_handler.py` | `ViolationHandler` | `__init__(config_manager, audit_client, stats_manager)`, `handle(event, result, group_id, user_id, user_name, is_admin, text_preview)` |
| `message_handler.py` | `MessageHandler` | `__init__(config_manager, admin_manager, audit_client, violation_handler)`, `handle(event)` |
| `command_handler.py` | `CommandHandler` | `__init__(config_manager, admin_manager, stats_manager)`, `dispatch(event, subcommand, args)` |

## 代码风格

- Python 3.10+，用类型注解
- 类方法用 `async def` 标注异步
- 注释用中文
- 每个文件不超过 500 行
