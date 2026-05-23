# Issue 28 — `ConfigManager._group_configs` 不支持配置热更新

**严重度**：🟡 Major  
**涉及文件**：`config_manager.py`, `main.py`  
**类型**：运行时行为缺陷

## 现象

`ConfigManager` 在构造函数中调用 `_parse_group_settings()` 构建 `_group_configs` 字典，此后该字典**永不再刷新**：

```python
class ConfigManager:
    def __init__(self, context: Context, stats_manager: StatsManager):
        self.config = self.context.get_config()
        self._group_configs: dict[str, dict] = {}
        self._parse_group_settings()  # 仅执行一次

    def _parse_group_settings(self):
        group_settings: list[dict] = self.config.get("group_settings", [])
        for gs in group_settings:
            group_id = gs.get("group_id", "")
            if not group_id:
                continue
            config_copy = dict(gs)
            schedule_str = config_copy.get("auto_censor_schedule", "")
            config_copy["schedule_parsed"] = self._parse_schedule(schedule_str)
            self._group_configs[group_id] = config_copy
```

当用户在 AstrBot 管理面板中修改 `group_settings` 配置后，AstrBot 框架会将新配置写入 `data/config/content_audit_text_config.json`。但插件的 `ConfigManager._group_configs` 字典**不会自动更新**——新增/修改/删除的群组配置不会在运行时生效，必须**重启插件**。

## 问题分析

AstrBot 的配置模型是"框架管理配置持久化，插件通过 `context.get_config()` 读取"。框架在配置变更后会更新内部状态，但不会主动通知插件。插件需要自行处理配置热更新。

具体影响场景：

1. **新增群组配置**：用户添加新群 → `_group_configs` 中无此条目 → `is_group_enabled()` 返回 `False` → 消息被跳过，直到重启
2. **修改管理群绑定**：用户更改 `manage_group_id` → `_group_configs` 中仍是旧值 → 通报仍发到旧管理群，命令仍校验旧管理群
3. **禁用某群**：用户将 `enabled` 设为 `false` → 仍在审核（因为旧条目 cached 为 `true`）
4. **修改智能审查参数**：`schedule_parsed` 不更新 → 审查行为不符预期

## 修复建议

在 `ConfigManager` 中增加 `reload()` 方法，并在 `CommandHandler.dispatch()` 或每次消息处理前检查配置是否需要刷新：

**方案 A（推荐）— 惰性热加载 + 显式 reload**：

```python
class ConfigManager:
    def __init__(self, context: Context, stats_manager: StatsManager):
        self.context = context
        self._stats_manager = stats_manager
        self.config = self.context.get_config()
        self._group_configs: dict[str, dict] = {}
        self._config_version: int = 0
        self._parse_group_settings()

    def reload(self) -> None:
        """重新加载配置（从 AstrBot 配置系统获取最新值）"""
        self.config = self.context.get_config()
        self._group_configs.clear()
        self._parse_group_settings()
        self._config_version += 1
        logger.info(f"配置已重新加载 (version={self._config_version})")

    def maybe_reload(self) -> bool:
        """检测配置是否变更并自动重载，返回是否已重载"""
        new_config = self.context.get_config()
        new_settings = new_config.get("group_settings", [])
        current_settings = self.config.get("group_settings", [])
        if new_settings != current_settings:
            self.config = new_config
            self._group_configs.clear()
            self._parse_group_settings()
            self._config_version += 1
            logger.info(f"检测到配置变更，已自动重载 (version={self._config_version})")
            return True
        return False
```

在 `CommandHandler.dispatch()` 入口调用 `maybe_reload()`，因为命令处理是低频操作、对性能不敏感，且用户通常在修改配置后会立即通过命令验证。

```python
async def dispatch(self, event, subcommand, args):
    self._config_manager.maybe_reload()  # 每次命令前检查配置变更
    # ... 原有逻辑
```

**Why**：管理面板修改配置后，命令是最直接的验证入口。在命令入口做配置刷新，既保证了大批量消息处理的性能（不每次检查），又覆盖了"改完配置→发命令验证"的核心场景。`maybe_reload()` 仅在检测到变更时才重建字典，开销可控。

**How to apply**：
1. 在 `ConfigManager` 中添加 `reload()` 和 `maybe_reload()` 方法
2. 在 `CommandHandler.dispatch()` 开头调用 `self._config_manager.maybe_reload()`
3. 可选：在 `main.py` 中对外暴露 reload 接口，供框架层调用
