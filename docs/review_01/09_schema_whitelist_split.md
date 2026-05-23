# Issue 09 — _conf_schema.json 中 whitelist 配置段与 SQLite 白名单割裂

**严重度**: 🟡 Major
**涉及文件**: `_conf_schema.json`, `config_manager.py`, `command_handler.py`, `stats_manager.py`
**类型**: 架构问题

## 现象

`_conf_schema.json` 定义了：

```json
"whitelist": {
    "properties": {
        "enabled": { "type": "boolean", "default": false },
        "user_ids": { "type": "array", "items": { "type": "string" }, "default": [] }
    }
}
```

但 `command_handler` 的白名单增删操作全部写入 SQLite `whitelist` 表，从不修改 JSON 配置。`message_handler` 的白名单检查又只读 JSON 配置。两条路径在架构上完全割裂。

## 修复方案

配合 Issue 02 修复：

**如果采用方案 A（推荐）**：
- 从 `_conf_schema.json` 中删除 `whitelist.user_ids` 字段
- 保留 `whitelist.enabled` 作为总开关
- `config_manager.is_whitelisted()` 改为查 `stats_manager.get_whitelist()`

修改后的 schema：
```json
"whitelist": {
    "type": "object",
    "title": "白名单",
    "properties": {
        "enabled": {
            "type": "boolean",
            "title": "启用白名单",
            "default": false
        }
    }
}
```

**如果采用方案 B**：
- 删除 `stats_manager` 中的 `whitelist` 表
- `command_handler` 改为直接操作 `self._config_manager.config["whitelist"]["user_ids"]` 并调用 `config.save_config()`
