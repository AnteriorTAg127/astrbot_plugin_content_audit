---
name: astrbot-plugin-dev
description: AstrBot 插件开发全流程技能。读取 helloworld-master/ 示例代码和 references/ 参考文档，完成 AstrBot 插件开发任务。
---

# AstrBot 插件开发技能

读取本目录下的子文件夹作为参考材料：

| 路径 | 内容 |
|---|---|
| `helloworld-master/` | 完整插件示例项目（main.py、metadata.yaml、README.md），展示入口、注册、指令、生命周期 |
| `references/` | 官方开发文档合集（AI、配置、消息发送、会话控制、存储、发布等） |
| `AstrBot-Dev-Index.md` | 全部 API 速查总表 |

## 工作流程

当你收到 AstrBot 插件开发需求时：

### 1. 读取示例代码

首先阅读 `helloworld-master/main.py` 和 `metadata.yaml`，理解基础项目结构和插件注册方式。

### 2. 查询参考文档

根据具体需求查阅 `references/` 下的对应文档：
- **新建插件** → `plugin-new.md`
- **AI / LLM 调用** → `ai.md`
- **配置 Schema** → `plugin-config.md`
- **消息发送** → `send-message.md`
- **事件监听** → `listen-message-event.md`
- **会话控制** → `session-control.md`
- **存储** → `storage.md`
- **发布** → `plugin-publish.md`
- **HTML 渲染/文转图** → `html-to-pic.md`
- **环境配置 / 运行时** → `env.md`
- **其他高级用法** → `other.md`

### 3. 查阅 API 索引

`AstrBot-Dev-Index.md` 包含完整的过滤器、钩子、Context API 等速查表。如有需要，联系使用它的 API。

### 4. 开发原则

- 功能需经过测试
- 包含良好的注释
- 持久化数据请存储于 `data` 目录下，而非插件自身目录
- 良好的错误处理机制，不要让插件因一个错误而崩溃
- 提交前使用 `ruff` 格式化代码（先测试后格式化）
- 使用 `aiohttp`、`httpx` 等异步网络请求库，不使用 `requests`
- 如果是对某个插件进行功能扩增，优先给原插件提 PR 而非另写一个
- AstrBot 采用运行时注入插件机制，代码异步执行
- 测试由用户亲自完成，结果会反馈给你
- 事件钩子内不能使用 `yield` 发送消息，请使用 `event.send()`
- `requirements.txt` 必须填写第三方依赖，防止 Module Not Found

### 5. 输出要求

- 提供完整可用的 Python 文件
- 包含必要的导包语句和类型标注
- 遵循上述项目结构和命名规范（目录以 `astrbot_plugin_` 开头）
- 配置项定义在 `_conf_schema.json` 中
