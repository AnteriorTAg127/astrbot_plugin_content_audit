# Issue 29 — per-group 配置项与全局配置层级重叠，缺失 per-group 行为覆写

**严重度**：🟢 Minor  
**涉及文件**：`_conf_schema.json`, `message_handler.py`, `config_manager.py`  
**类型**：架构优化

## 现象

当前配置有两层，但职责边界模糊：

**全局层**（对所有群生效）：
```json
"audit": { "enabled": ..., "skip_admin": ..., "skip_llm": ..., "min_text_length": ... }
"action": { "auto_recall": ..., "auto_mute": ..., "first_mute_duration": ..., ... }
"notify": { "show_text_preview": ..., "preview_max_length": ... }
```

**群级层**（`group_settings` 中每群独立配置）：
```json
{
    "enabled": ...,         // ← 与 audit.enabled 功能重叠
    "group_id": ...,
    "manage_group_id": ...,
    "enable_auto_censor": ...,
    "auto_censor_schedule": ...,
    "auto_censor_no_admin_minutes": ...
}
```

问题：
1. `audit.enabled`（全局）与 `group_settings[].enabled`（群级）形成二级开关，语义重叠
2. 群级配置**不能覆写**全局的 `skip_admin`、`skip_llm`、`auto_recall`、`auto_mute` 等行为参数
3. 实际场景中，不同群可能需要不同的行为策略（如群 A 需要自动撤回但不禁言，群 B 需要禁言但不撤回）

## 代码证据

`message_handler.py` 中所有行为参数均从全局 `audit_config` / `action_config` 读取：

```python
# 行 63-64：只读全局 audit 配置
audit_config = self._config_manager.config.get("audit", {})
min_length: int = audit_config.get("min_text_length", 2)

# 行 95：skip_admin 只读全局
skip_admin: bool = audit_config.get("skip_admin", True)

# 行 121：skip_llm 只读全局
skip_llm: bool = audit_config.get("skip_llm", False)

# violation_handler.py 行 196-198：auto_recall / auto_mute 只读全局
action_config = self._get_action_config()
auto_recall = action_config.get("auto_recall", True)
auto_mute = action_config.get("auto_mute", True)
```

群级配置（`group_config`）仅用于：开关、智能审查、管理群绑定。群级无法覆写行为参数。

## 修复建议

**短期**（与 issue 27 一起修复）— 明确两层分工：

- **全局层**保留为"默认值/全局开关"：`audit.enabled` 作为总闸
- **群级层**（`group_settings` 的 `template_list`）支持可选覆写：当群级字段为空/未设置时回退到全局值

在模板中添加**可选**的 per-group 覆写字段：

```json
"templates": {
    "group_config": {
        "name": "群组审核配置",
        "items": {
            "group_id": { ... },
            "manage_group_id": { ... },
            "enabled": { ... },
            "enable_auto_censor": { ... },
            "auto_censor_schedule": { ... },
            "auto_censor_no_admin_minutes": { ... },

            "override_skip_admin": {
                "type": "bool",
                "title": "覆写-跳过管理员",
                "description": "留空则使用全局设置",
                "hint": "勾选 → 该群强制跳过管理员；不勾选 → 该群强制不跳过；留空 → 跟随全局",
                "default": null   // null 表示不覆写，跟随全局
            },
            "override_auto_recall": {
                "type": "bool",
                "title": "覆写-自动撤回",
                "hint": "覆盖全局 action.auto_recall 设置"
            },
            "override_auto_mute": {
                "type": "bool",
                "title": "覆写-自动禁言",
                "hint": "覆盖全局 action.auto_mute 设置"
            }
        }
    }
}
```

对应的 `ConfigManager` 增加 merge 逻辑：

```python
def get_effective_config(self, group_id: str, key: str, default=None):
    """获取群级有效配置：群级覆写 > 全局配置 > default"""
    group_config = self._group_configs.get(group_id, {})
    override_key = f"override_{key}"
    if override_key in group_config and group_config[override_key] is not None:
        return group_config[override_key]
    section_map = {
        "skip_admin": "audit",
        "skip_llm": "audit",
        "auto_recall": "action",
        "auto_mute": "action",
        "min_text_length": "audit",
    }
    section = section_map.get(key, "audit")
    return self.config.get(section, {}).get(key, default)
```

**Why**：双群管理架构下，不同被管理群可能需要不同的处置策略（如测试群只通报不处罚、正式群全量处置）。per-group 覆写使管理员能精细控制各群行为，无需为不同策略部署多个插件实例。

**How to apply**：
1. 在 `template_list` 模板中添加 `override_*` 可选字段（`default: null`，null 表示不覆写）
2. 在 `ConfigManager` 中添加 `get_effective_config()` 方法，实现群级 → 全局 → default 三级回退
3. 修改 `message_handler.py` 和 `violation_handler.py` 中的配置读取，从直接读全局改为通过 `get_effective_config()` 读取
4. 与 issue 27 一起提交，因为都涉及 `_conf_schema.json` 的 `group_settings` 段修改

> **注意**：若短期不计划实现 per-group 覆写，至少应在 issue 27 的模板中添加清晰的 `hint` 说明群级配置与全局配置的关系，避免用户困惑。
