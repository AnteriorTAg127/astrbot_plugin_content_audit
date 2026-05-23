# 22 — `audit_log` 与通报的文本预览长度不一致

**严重度**：🟡 Major  
**文件**：`message_handler.py` (行 121, 行 134-137)

## 问题

同一段消息文本在两处被截断到不同长度，且来源不同：

```python
# audit_log 写入 - 硬编码 200 字符 (行 121)
await self._stats_manager.record_audit(
    ...
    text_preview=message_str[:200],
    ...
)

# 通报消息 - 使用配置项 preview_max_length，默认 100 (行 134-137)
notify_config = self._config_manager.config.get("notify", {})
max_preview_len: int = notify_config.get("preview_max_length", 100)
text_preview = message_str[:max_preview_len] if show_preview else ""
```

数据库存了 200 字符，但用户通过 `/文本审核 日志` 查看时显示的也是数据库中的 200 字符。而管理群通报只显示 100 字符。用户看到日志和通报中的文本预览长度不同，可能误以为数据不一致。

## 修复建议

统一两者长度来源：

选择 A：都从配置读取，`audit_log` 也使用 `preview_max_length`（但可能需要独立配置项）。

选择 B：`audit_log` 存储完整消息文本（不做截断），仅在显示和通报时截断。这样保留了完整数据用于追溯。

选择 B 更合理——`audit_log` 本身就是存储原始审核输入的地方，200 字符截断已经丢失信息。

**Why**：长度不一致不是 bug 但会在运维场景中引起困惑（"为什么通报里只看到 100 字，日志里却有 200 字？"）。

**How to apply**：建议将 `audit_log.text_preview` 改为存储完整文本（或至少增大到 500+ 字符），通报时的截断保持可配置。
