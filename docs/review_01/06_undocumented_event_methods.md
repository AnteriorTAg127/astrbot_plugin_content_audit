# Issue 06 — event.get_group_id/get_self_id/get_message_id 未确认存在

**严重度**: 🟡 Major
**涉及文件**: `main.py`, `message_handler.py`, `violation_handler.py`
**类型**: API 兼容性

## 现象

代码中多处使用了以下未在 AstrBot 公开文档中出现的方法：

```python
event.get_group_id()      # main.py:88, command_handler.py:42, message_handler.py:36
event.get_self_id()       # message_handler.py:56
event.get_message_id()    # violation_handler.py:85
```

AstrBot 文档中 `AstrMessageEvent` 列出的方法只有 `get_sender_name()`, `get_sender_id()`, `get_platform_name()`, `get_result()`, `send()` 等。群号、自身 ID、消息 ID 的正确访问方式是从 `event.message_obj` 的属性读取：

```python
event.message_obj.group_id    # str
event.message_obj.self_id     # str
event.message_obj.message_id  # str
```

## 修复方案

验证 `get_group_id()` 等方法是否确实存在。如果不存在，统一改用 `event.message_obj.<attr>`：

```python
# main.py:88
group_id = event.message_obj.group_id

# message_handler.py:56
self_id = str(event.message_obj.self_id)

# violation_handler.py:85
message_id = event.message_obj.message_id
```

如果这些方法是某个 AstrBot 版本新增的便捷方法，请确认最低版本要求并在 `metadata.yaml` 中声明 `astrbot_version`。
