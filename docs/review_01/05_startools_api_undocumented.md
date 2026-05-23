# Issue 05 — StarTools.get_data_dir() API 未在文档中确认

**严重度**: 🔴 Critical
**涉及文件**: `main.py`
**类型**: API 兼容性

## 现象

```python
from astrbot.api.all import StarTools
data_dir = StarTools.get_data_dir()
```

AstrBot 官方文档中：

- `storage.md` 给出的获取数据目录的方式是：
  ```python
  from astrbot.core.utils.astrbot_path import get_astrbot_data_path
  plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name
  ```
- API 索引中没有任何 `StarTools` 类的记录

`StarTools` 可能是一个未文档化的内部类，不保证在版本升级中保持兼容。

## 修复方案

改用文档化的 API：

```python
# main.py, initialize() 中
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# 按文档规范，数据放在 data/plugin_data/{plugin_name}/ 下
plugin_name = "content_audit_text"  # metadata.yaml 中的 name
data_dir = str(Path(get_astrbot_data_path()) / "plugin_data" / plugin_name)
```

或者如果 StarTools 在 AstroBot 中确实可用且有维护者确认稳定，则添加注释说明来源。
