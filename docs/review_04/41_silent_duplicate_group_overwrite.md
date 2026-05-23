# Issue 41 — 重复 group_id 配置条目被静默覆盖，无警告

**严重度**：🟢 Minor  
**涉及文件**：`config_manager.py`（行 28-39）  
**类型**：数据完整性 / 用户体验

## 现象

`_parse_group_settings()` 遍历 `group_settings` 列表时，以 `group_id` 为键存入字典。如果配置中存在两条 `group_id` 相同的条目，后者静默覆盖前者：

```python
def _parse_group_settings(self):
    group_settings = self.config.get("group_settings", [])
    for gs in group_settings:
        group_id = gs.get("group_id", "")
        if not group_id:
            continue
        config_copy = dict(gs)
        ...
        self._group_configs[group_id] = config_copy   # ← 后者覆盖前者
```

没有任何日志或警告提示用户存在重复配置。这在以下场景中会发生：
- 用户通过 `template_list` 界面不小心添加了两个同群号的条目
- 配置迁移/复制粘贴时产生重复
- 多人协作管理时配置冲突

## 问题分析

虽然 `template_list` UI 会为每行生成唯一的标识（`__template_key`），但底层数据仍是数组，无法在结构层面阻止重复 `group_id`。重复条目的后果：
- 只有最后一条生效（前一条的配置完全丢失）
- 用户可能困惑：为什么改了配置不生效？（因为改的是被覆盖的那条）
- `is_manage_group()` 仍能检测到（因为两条的 `manage_group_id` 相同），但行为配置来自后一条

## 修复方案

在 `_parse_group_settings()` 中添加重复检测和警告：

```python
def _parse_group_settings(self):
    group_settings = self.config.get("group_settings", [])
    seen: set[str] = set()
    for gs in group_settings:
        group_id = gs.get("group_id", "")
        if not group_id:
            continue
        if group_id in seen:
            logger.warning(
                f"group_settings 中存在重复的 group_id={group_id}, "
                f"后出现的条目将覆盖先前的配置"
            )
        seen.add(group_id)
        config_copy = dict(gs)
        schedule_str = config_copy.get("auto_censor_schedule", "")
        config_copy["schedule_parsed"] = self._parse_schedule(schedule_str)
        self._group_configs[group_id] = config_copy
```

**Why**：重复配置是用户操作失误的常见表现。一条警告日志可以帮助用户快速定位"配置不生效"的原因，避免浪费大量时间排查。

**How to apply**：在 `config_manager.py` 的 `_parse_group_settings()` 中添加 `seen` 集合和 `logger.warning`。
