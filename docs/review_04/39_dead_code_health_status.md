# Issue 39 — `health_status` 属性 / `_health_fail_count` 字段为死代码

**严重度**：🟢 Minor  
**涉及文件**：`audit_client.py`（行 36-37, 109-121）  
**类型**：死代码 / 代码整洁

## 现象

`AuditClient` 中维护了健康检查状态的两个字段和一个属性，但从未被外部使用：

```python
class AuditClient:
    def __init__(self, ...):
        ...
        self._last_health_ok: bool = True       # ← 只在 health_check 中写入
        self._last_health_time: float = 0.0     # ← 只在 health_check 中写入
        self._health_fail_count: int = 0        # ← 单调递增，从不重置

    @property
    def health_status(self) -> dict:            # ← 定义了属性，但全局搜索无调用
        return {
            "ok": self._last_health_ok,
            "last_check_time": self._last_health_time,
            "fail_count": self._health_fail_count,
        }
```

全局搜索所有 Python 文件，`health_status` 从未被导入或调用。`_health_fail_count` 在 `health_check()` 中递增但从不重置——临时故障后计数器永久偏高，即使后续健康检查持续成功。

## 问题分析

设计文档 §六中的 `/文本审核 状态` 命令描述包括：
> 汇总该管理群下所有被管理群的审核统计（当日/累计违规数、通过数、缓存命中率、API 健康状态）

但实际 `_status()` 实现（`command_handler.py` 行 80-100）只显示了统计数字，没有 API 健康状态。这意味着 `health_status` 的消费者从未被实现。

## 修复建议

**方案 A（推荐）— 连接到状态命令**：

在 `command_handler._format_group_stats()` 或状态输出中加入 API 健康信息：

```python
# main.py 或 command_handler.py 中暴露
health = self._audit_client.health_status
status_text = f"API 状态: {'正常' if health['ok'] else '异常'} (失败{health['fail_count']}次)"
```

在 `audit_client.py` 中添加重置方法：

```python
def reset_health_fail_count(self) -> None:
    """健康检查连续成功 N 次后重置失败计数"""
    self._health_fail_count = 0

async def health_check(self) -> dict | None:
    ...
    except ...:
        self._last_health_ok = False
        self._health_fail_count += 1
    else:
        self._last_health_ok = True
        self._health_fail_count = 0    # ← 成功后重置
```

**方案 B — 彻底移除死代码**：

如果暂时不需要健康状态报告，删除 `_last_health_ok`、`_last_health_time`、`_health_fail_count` 三个字段和 `health_status` 属性。保留 `health_check()` 方法仅用于日志告警。

**Why**：死代码增加维护负担，且 `_health_fail_count` 的单调递增行为本身就暗示这是一个未完成的特性。要么完成它（连到状态命令），要么移除它。

**How to apply**：按方案 A 实施，在状态命令中显示 API 健康，并添加失败计数重置逻辑。
