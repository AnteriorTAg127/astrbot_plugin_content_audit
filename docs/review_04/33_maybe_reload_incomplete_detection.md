# Issue 33 — `maybe_reload()` 仅检测 group_settings / api 变更，遗漏 audit / action / notify / whitelist

**严重度**：🟡 Major  
**涉及文件**：`config_manager.py`（行 165-179）  
**类型**：功能缺陷 / 配置热更新

## 现象

`maybe_reload()` 方法通过比较新旧配置来判断是否需要重载：

```python
def maybe_reload(self) -> bool:
    new_config = self.context.get_config()
    new_settings = new_config.get("group_settings", [])
    current_settings = self.config.get("group_settings", [])
    new_api = new_config.get("api", {})
    current_api = self.config.get("api", {})
    if new_settings != current_settings or new_api != current_api:
        self.config = new_config    # ← 只有这两段变化时才更新 self.config
        self._group_configs.clear()
        self._parse_group_settings()
        ...
        return True
    return False
```

它只比较了 `group_settings` 和 `api` 两段。如果用户通过 AstrBot 管理面板修改了：

- `audit.enabled`（总开关）
- `audit.skip_admin`
- `audit.skip_llm`
- `action.auto_recall` / `action.auto_mute`
- `notify.show_text_preview`
- `whitelist.enabled`

——`maybe_reload()` 检测不到这些变更，`self.config` 不会更新。由于 `message_handler.py` 和 `violation_handler.py` 通过 `self._config_manager.config.get("audit", {})` 直接读 `self.config`，这些修改**不会在运行时生效**，直到下次显式 `reload()` 或重启。

## 问题分析

触发场景：

```
用户在管理面板修改 audit.skip_admin: true → false
→ 框架将新值写入配置文件
→ 用户期望管理员消息现在也被审查
→ 发送命令 /文本审核 状态 → maybe_reload() 检测
→ group_settings 未变, api 未变 → 不重载
→ self.config 仍是旧值，skip_admin 仍是 true
→ 管理员消息仍然跳过审查
```

这与 issue 28 修复的意图矛盾——issue 28 的目标是实现配置热更新，但实现不完整。

## 修复方案

将比较逻辑扩展为覆盖所有配置段，或者更简洁的方案：比较整个配置字典：

```python
def maybe_reload(self) -> bool:
    new_config = self.context.get_config()
    # 直接比较整个配置字典（排除不影响运行时行为的元数据字段）
    if new_config != self.config:
        self.config = new_config
        self._group_configs.clear()
        self._parse_group_settings()
        self._config_version += 1
        logger.info(f"检测到配置变更，已自动重载 (version={self._config_version})")
        self._notify_reload()
        return True
    return False
```

或者如果担心 `context.get_config()` 返回的对象每次都不同（含时间戳等元数据），则显式列出所有需追踪的段：

```python
def maybe_reload(self) -> bool:
    new_config = self.context.get_config()
    tracked_sections = ["api", "audit", "action", "notify", "whitelist", "group_settings"]
    for section in tracked_sections:
        if new_config.get(section) != self.config.get(section):
            self.config = new_config
            self._group_configs.clear()
            self._parse_group_settings()
            self._config_version += 1
            logger.info(f"检测到配置变更({section})，已自动重载 (version={self._config_version})")
            self._notify_reload()
            return True
    return False
```

**Why**：配置热更新是 issue 28 的核心目标。当前实现只覆盖了部分配置段，破坏了这个功能的完整性。完整比较确保任何配置变更都能在命令触发时生效。

**How to apply**：修改 `config_manager.py` 的 `maybe_reload()` 方法，扩展变更检测范围。
