# Issue 11 — ruff noqa 抑制歧义 Unicode 字符

**严重度**: 🟢 Minor
**涉及文件**: `main.py`, `message_handler.py`, `violation_handler.py`, `config_manager.py`
**类型**: 代码质量

## 现象

四个文件顶部有 `# ruff: noqa: RUF001, RUF002, RUF003` 抑制：

- RUF001: 字符串中包含歧义的 Unicode 字符（如混淆拉丁字母的 Cyrillic）
- RUF002: 文档字符串中包含歧义 Unicode
- RUF003: 注释中包含歧义 Unicode

这说明源文件中存在容易与 ASCII 字符混淆的 Unicode 内容（例如全角空格、中文引号等被误判、或确实有可疑字符）。

## 修复方案

1. 运行 `ruff check --select RUF001,RUF002,RUF003` 定位具体行
2. 如果是必要的合法中文字段（如文档、注释中的中文标点），用更精确的 `# noqa: RUF001` 加在具体行而非文件级抑制
3. 如果是确实有问题的字符（如代码中混入全角空格），替换为 ASCII

```bash
ruff check --select RUF001,RUF002,RUF003 *.py
```
