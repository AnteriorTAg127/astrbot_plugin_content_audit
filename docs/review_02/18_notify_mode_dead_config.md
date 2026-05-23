# 18 — `notify.mode` 配置项完全未生效

**严重度**：🔴 Critical  
**文件**：`_conf_schema.json` (行 119-127)，`violation_handler.py`，`message_handler.py`

## 问题

`_conf_schema.json` 中定义了 `notify.mode` 配置项，包含两个枚举值：

- `violation_only`：仅违规时通报（默认值）
- `none`：不通报

但在整个代码库中，**没有任何地方读取 `notify.mode` 的值**。无论配置为何值，违规通报始终执行。

这与设计文档 §一的核心原则矛盾：设计文档明确说 "主动群管可关闭，通报不可关闭"，但 schema 却给了 `none` 选项暗示可以关闭通报。

## 操作

有两个选择，取决于设计意图：

**选择 A**（符合设计文档）：从 schema 中删除 `notify.mode` 配置项。通报始终生效，不可配置关闭。

**选择 B**（实现 schema 的承诺）：在 `violation_handler.py` 中读取 `notify.mode`，当值为 `none` 时跳过通报但仍记录违规。

推荐**选择 A**，因为：
1. 设计文档明确表示"通报不可关闭"
2. 对安全合规场景，丢失通报比丢失处置更危险
3. 减少无意义的配置复杂度

如果选择 A，需同步更新 `_conf_schema.json`，移除 `notify.mode` 字段。

**Why**：用户配置了 `notify.mode: none` 后仍然收到通报，属于"配置不生效"类问题，会严重损害对插件可控性的信任。

**How to apply**：无论选择 A 还是 B，都应立即决策并同步修改 schema 和代码，确保一致。
