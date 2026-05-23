# Issue 02 — 白名单数据双轨不一致

**严重度**: 🔴 Critical
**涉及文件**: `command_handler.py`, `config_manager.py`, `stats_manager.py`, `_conf_schema.json`
**类型**: 数据一致性问题

## 现象

白名单存在两套完全独立的存储和读取路径：

| 路径 | 写入 | 读取 |
|------|------|------|
| SQLite (`stats_manager.whitelist` 表) | `command_handler._whitelist_add()` / `_whitelist_remove()` | 无人读取 |
| JSON 配置 (`config.whitelist.user_ids`) | 用户手动改配置面板 | `config_manager.is_whitelisted()` → `message_handler` 检查 |

结果：用户用指令 `/文本审核 白名单 添加 <QQ>` 添加的白名单用户永远不会被审核跳过，因为 `message_handler` 读的是 JSON 配置里的空数组。

## 修复方案

**方案 A（推荐）**：统一走 SQLite，`config_manager.is_whitelisted()` 改为调 `stats_manager.get_whitelist()`。

- `config_manager` 注入或获取 `stats_manager` 引用
- `is_whitelisted()` 改为 `async`，从 SQLite 查
- `_conf_schema.json` 中删除 `whitelist.user_ids` 配置项（保留 `whitelist.enabled`）
- `message_handler` 调用改为 `await self._config_manager.is_whitelisted(user_id)`

```python
# config_manager.py
async def is_whitelisted(self, user_id: str) -> bool:
    whitelist = self.config.get("whitelist", {})
    if not whitelist.get("enabled", False):
        return False
    users = await self._stats_manager.get_whitelist()
    return user_id in users
```

**方案 B**：统一走 JSON 配置，删除 SQLite `whitelist` 表，`command_handler` 改操作 `_conf_schema.json` 对应的运行时 config（需要 `config.save_config()`）。
