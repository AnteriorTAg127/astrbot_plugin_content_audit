# Issue 36 — string→int 转换无 try/except，含非数字 ID 时 crash

**严重度**：🟡 Major  
**涉及文件**：`violation_handler.py`（行 91, 106, 129）  
**类型**：边界条件 / 异常处理

## 现象

违规处理中有三处将字符串 ID 转换为 int，均未做异常保护：

**`_send_notification()` 行 91**：
```python
await client.send_group_msg(group_id=int(manage_group_id), message=notification_text)
```

**`_recall_message()` 行 106**：
```python
message_id = event.message_obj.message_id
await client.delete_msg(message_id=message_id)
```
> 这里虽然没有显式 `int()`，但 `event.message_obj.message_id` 的类型未文档化，如果 AstrBot 框架返回字符串而非 int，`delete_msg()` 可能因类型不匹配失败。

**`_mute_user()` 行 128-129**：
```python
await client.set_group_ban(
    group_id=int(group_id),
    user_id=int(user_id),
    duration=duration,
)
```

虽然 QQ 群号和 QQ 号在正常场景下都是纯数字，但如果某个平台的群 ID 采用非数字格式（如 Telegram 的负数 ID 或字符串 ID），`int()` 会抛出 `ValueError`，导致违规处理流程中断，通报也无法发出。

## 问题分析

当前异常处理只在 `violation_handler.handle()` 的最外层有一个 try/except？实际上没有！`handle()` 方法内没有任何 try/except，所有异常会传播到 `message_handler.handle()` 的 catch-all：

```python
# message_handler.py 行 158-160
except Exception:
    logger.exception("消息审核流水线异常，降级放行")
    return
```

但由于 `handle()` 是在多个 `await` 之后才到 `_mute_user`，如果前面的通报已发送、撤回已完成，禁言时 `int()` 崩溃会导致：
1. 通报已发出（无法撤回通报）
2. 撤回已完成（消息已消失）
3. 禁言未执行（但用户以为被禁言了）
4. 违规记录未写入数据库

这造成了不一致的状态。

## 修复方案

在 `violation_handler.py` 的三个方法中添加 try/except 保护：

```python
async def _send_notification(self, event, manage_group_id, ...):
    client = self._get_client(event)
    try:
        if client and hasattr(client, "send_group_msg"):
            await client.send_group_msg(
                group_id=int(manage_group_id), message=notification_text
            )
            return True
    except (ValueError, TypeError) as e:
        logger.warning(f"manage_group_id 无法转换为 int: {manage_group_id}, {e}")
    except Exception as e:
        logger.error(f"发送管理群通报失败: {e}")
    return False

async def _recall_message(self, event):
    client = self._get_client(event)
    try:
        if client and hasattr(client, "delete_msg"):
            message_id = event.message_obj.message_id
            await client.delete_msg(message_id=message_id)
            return True
    except Exception as e:
        logger.warning(f"撤回消息失败: {e}")
    return False
```

或者更优雅：在 `_send_notification`/`_mute_user` 入口做一次类型校验，非纯数字 ID 直接跳过对应的操作并记录日志。这样通报仍然能通过日志输出（`_send_notification` 行 96 的日志降级）。

**Why**：`int()` 在非数字输入上抛 `ValueError`，是 Python 中最常见的运行时崩溃原因之一。虽然 QQ 生态中群号/QQ 号是纯数字，但做防守性编程可以防止未来平台扩展时的崩溃。

**How to apply**：在 `_send_notification()`、`_mute_user()` 中添加 try/except ValueError。
