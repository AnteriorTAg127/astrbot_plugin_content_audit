# Issue 38 — 设计方案中的 `notify.mode` 配置未实现

**严重度**：🟢 Minor  
**涉及文件**：`_conf_schema.json`、`violation_handler.py`  
**类型**：设计-实现差距

## 现象

设计方案 §五.4 定义了 `notify.mode` 配置项：

> | `notify.mode` | enum | `violation_only` | 通报模式：`violation_only`（仅违规时）、`none`（不通报）。注意：没有"all"模式，文本审核不通报"通过"的消息。 |

但当前的 `_conf_schema.json` 中 `notify` 段只包含两个字段：

```json
"notify": {
    "items": {
        "show_text_preview": { ... },
        "preview_max_length": { ... }
    }
}
```

`notify.mode` 没有被实现。而且，即使 `notify.mode` 设为 `"none"`，`violation_handler.handle()` 中也没有任何检查——通报总是会发送。

## 问题分析

按照设计文档的原则"主动群管可关闭、通报不可关闭"，通报本应始终生效。但设计方案又定义了 `mode: "none"` 可关闭通报，这两者存在矛盾。

回顾设计文档 §一的核心原则：
> 主动群管动作（撤回/禁言）可独立关闭，但违规发生后的管理群通报始终生效。

如果 `notify.mode` 设为 `"none"`，通报被关闭，则违背了"始终生效"的原则。**设计方案本身存在矛盾**，需要在实现前澄清。

## 修复建议

**推荐方案**：移除 `notify.mode` 的设计，在 `_conf_schema.json` 中也不添加此字段。通报始终开启，符合核心安全原则。如果未来确实需要静默模式，可以在 `group_settings` 模板中添加 `override_notify_silent` per-group 覆写。

**备选方案**：在 `_conf_schema.json` 添加 `notify.mode`，在 `violation_handler._send_notification()` 入口检查：

```python
async def _send_notification(self, ...):
    notify_config = self._get_notify_config()
    mode = notify_config.get("mode", "violation_only")
    if mode == "none":
        logger.info(f"[通报已关闭] 群{group_id} 用户{user_id} 违规但未通报")
        return True
    # ... 原有逻辑
```

**Why**：通报不可关闭是安全底线，防止管理员因疏忽关闭通报后无法发现违规。如果确实需要静默场景（如测试群），应通过 per-group override 实现而非全局开关。

**How to apply**：
1. 确认设计意图：通报是否允许关闭
2. 若允许关闭：在 `_conf_schema.json` 添加 `notify.mode` 字段，在 `violation_handler.py` 添加检查
3. 若不允关闭：从设计方案中移除 `notify.mode`，在 scheama 中添加 hint 说明通报不可关闭
