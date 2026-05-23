# Issue 27 — `group_settings` 使用 `list` 而非 `template_list` schema

**严重度**：🟡 Major  
**涉及文件**：`_conf_schema.json`, `config_manager.py`  
**类型**：架构 / 用户体验  
**来源**：用户测试反馈

## 现象

当前 `_conf_schema.json` 中 `group_settings` 配置段使用 `"type": "list"` 类型：

```json
"group_settings": {
    "type": "list",
    "title": "群组设置",
    "description": "各群组的审核设置",
    "default": [],
    "items": {
        "type": "object",
        "title": "群组配置项",
        "description": "单个群组的审核配置",
        "items": {
            "enabled": { "type": "bool", ... },
            "group_id": { "type": "string", ... },
            "manage_group_id": { "type": "string", ... },
            "enable_auto_censor": { "type": "bool", ... },
            "auto_censor_schedule": { "type": "string", ... },
            "auto_censor_no_admin_minutes": { "type": "int", ... }
        }
    }
}
```

`list` 类型在 AstrBot 管理面板中呈现为**原始 JSON 编辑器**，用户需手动编写 JSON 数组，UI 体验差、易出错。没有逐行增删改的表格式交互，也没有字段校验。

## 问题分析

AstrBot v4.10.4 引入了 `template_list` 类型（详见 `references/plugin-config.md`），专为此类场景设计：

- **模板驱动**：按预设模板创建条目，字段类型与默认值由 schema 约束
- **自增表格 UI**：管理面板呈现可交互的表格，支持逐行添加/删除/编辑
- **字段级校验**：每个字段按 schema 定义的类型和默认值校验，减少配置错误
- **`__template_key`**：每个条目自动附加模板标识，不影响代码解析

当前 `list` 方式的痛点：

1. 用户需手动输入完整 JSON（含所有字段），对非技术人员极不友好
2. 字段缺失时无提示，依赖 AstrBot 默认值回填（用户不自知）
3. 多群配置时列表很长，JSON 编辑器的可读性差
4. 无法直观地看到"共有多少群组已配置"

## 修复方案

将 `group_settings` 从 `list` 改为 `template_list`，定义单个模板 `group_config`：

```json
"group_settings": {
    "type": "template_list",
    "title": "群组设置",
    "description": "各群组的审核设置（点击添加行配置每个被管理群）",
    "default": [],
    "templates": {
        "group_config": {
            "name": "群组审核配置",
            "hint": "绑定被管理群与管理群，配置该群的审核行为",
            "items": {
                "group_id": {
                    "type": "string",
                    "title": "被管理群号",
                    "description": "需要审核消息的群号",
                    "hint": "审核对象群，该群的消息会被审核",
                    "default": ""
                },
                "manage_group_id": {
                    "type": "string",
                    "title": "管理群号",
                    "description": "接收违规通报和管理命令的群号",
                    "hint": "管理群可执行 /文本审核 命令，接收违规通知",
                    "default": ""
                },
                "enabled": {
                    "type": "bool",
                    "title": "启用审核",
                    "description": "是否对该群启用文本审核",
                    "default": true
                },
                "enable_auto_censor": {
                    "type": "bool",
                    "title": "智能审查",
                    "description": "是否启用智能审查模式（基于时间段和管理员在线状态动态调整）",
                    "hint": "关闭时为全量审查模式",
                    "default": false
                },
                "auto_censor_schedule": {
                    "type": "string",
                    "title": "强制审查时间段",
                    "description": "在此期间始终审查，格式 hh:mm-hh:mm（如 23:00-09:00）",
                    "hint": "留空表示不启用强制时间段",
                    "default": ""
                },
                "auto_censor_no_admin_minutes": {
                    "type": "int",
                    "title": "管理员离线检测窗口（分钟）",
                    "description": "管理员超过此分钟数未发言则自动开启审查，0=关闭检测",
                    "hint": "仅在智能审查模式开启时生效",
                    "default": 0
                }
            }
        }
    }
}
```

### 保存后的 config 格式变化

**变更前**（`list`）：
```json
"group_settings": [
    {
        "enabled": true,
        "group_id": "123456",
        "manage_group_id": "789012",
        "enable_auto_censor": false,
        "auto_censor_schedule": "",
        "auto_censor_no_admin_minutes": 0
    }
]
```

**变更后**（`template_list`）：
```json
"group_settings": [
    {
        "__template_key": "group_config",
        "enabled": true,
        "group_id": "123456",
        "manage_group_id": "789012",
        "enable_auto_censor": false,
        "auto_censor_schedule": "",
        "auto_censor_no_admin_minutes": 0
    }
]
```

唯一差异是多了一个 `__template_key` 字段，`config_manager.py` 现有的 `_parse_group_settings()` 方法**完全兼容**——它按字段名读取（`gs.get("group_id", "")`），不依赖条目结构，`__template_key` 会被安全忽略。

### 代码变更范围

1. **`_conf_schema.json`**：`group_settings` 段重写，`list` → `template_list`（见上方完整 schema）
2. **`config_manager.py`**：**无需修改**。`_parse_group_settings()`、`is_group_enabled()`、`is_manage_group()`、`get_group_config()` 等方法均按字段名读取，与 `__template_key` 无冲突
3. 其余文件：**无需修改**

### 兼容性说明

- `template_list` 需 AstrBot **≥ v4.10.4**（低版本降级为普通 list 显示）
- `__template_key` 仅用于管理面板识别模板，运行时无副作用
- 已有 `group_settings` 数据可直接迁移：在管理面板中打开配置后，AstrBot 会自动将旧 list 数据补上 `__template_key`

**Why**：`template_list` 是 AstrBot 为此类"一对多配置表"场景设计的标准 schema 类型，提供良好的编辑体验和字段校验，且对现有代码零侵入。

**How to apply**：仅修改 `_conf_schema.json`，将 `group_settings` 从 `list` 改为 `template_list`，添加 `templates.group_config` 模板定义。代码零改动。
