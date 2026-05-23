# AstrBot 插件开发指南 —— API 索引

> 基于 `F:\\astrbot\\guides\\` 目录下所有文档整理。  
> 版本参考: v3.4.15 \~ v4.23.1+

\---

## 一、目录文件总览（资源文件在./references/下）

|#|源文件名|主题|简介|
|-|-|-|-|
|1|`plugin-new.md`|插件开发入门|从模板创建项目、环境搭建、开发原则、完整 API 索引|
|2|`simple.md`|最小实例|最简插件代码骨架 (`main.py`)|
|3|`env.md`|开发环境准备|插件模板获取、Clone、调试、依赖管理|
|4|`plugin.md`|旧版开发指南|旧版完整指南（内容与新指南重叠，v4.5.7 后已归档）|
|5|`plugin-config.md`|插件配置|`\_conf\_schema.json` 格式、类型、\_special、使用配置|
|6|`listen-message-event.md`|消息事件处理|指令、指令组、事件钩子、优先级、事件传播控制|
|7|`send-message.md`|消息发送|被动/主动消息、富媒体、文件/语音/视频/表情/合并转发|
|8|`session-control.md`|会话控制|`session\_waiter`、`SessionController`、自定义 SessionFilter|
|9|`ai.md`|AI / LLM|LLM 调用、Tool 定义、Agent、Multi-Agent、对话/人格管理|
|10|`html-to-pic.md`|文转图|`text\_to\_image`、`html\_render`（HTML+Jinja2）、渲染选项|
|11|`storage.md`|插件存储|KV 存储 (`put\_kv\_data`等)、大文件存储路径规范|
|12|`other.md`|杂项|获取平台实例、调用 CQHTTP API、获取插件/平台列表|
|13|`plugin-publish.md`|发布插件|提交插件到插件市场 (plugins.astrbot.app)|

\---

## 二、核心模块索引

### 2.1 插件入口与基类

|模块/函数/类|源文件|简介|
|-|-|-|
|`Star`|`simple.md`, `plugin-new.md`, `plugin.md`|插件基类，所有插件须继承|
|`Context`|`simple.md`, `plugin-new.md`|插件与 AstrBot Core 交互的上下文对象|
|`register`|`simple.md`|插件注册装饰器|
|`terminate()`|`simple.md`, `plugin-new.md`|可选方法，插件卸载/停用时调用|
|`AstrBotConfig`|`plugin-config.md`, `plugin-new.md`|配置类，继承自 `Dict`，提供 `save\_config()`|

\---

### 2.2 消息事件（`astrbot.api.event`）

#### 2.2.1 消息与事件对象

|模块/函数/类|源文件|简介|
|-|-|-|
|`AstrMessageEvent`|`listen-message-event.md`, `simple.md`, `plugin-new.md`|消息事件对象，含发送者、消息内容等|
|`AstrBotMessage`|`listen-message-event.md`, `plugin-new.md`|消息对象，存储消息平台下发的具体内容|
|`MessageType`|`listen-message-event.md`|消息类型枚举|
|`MessageMember`|`listen-message-event.md`|消息发送者对象|
|`BaseMessageComponent`|`listen-message-event.md`, `plugin-new.md`|消息段基类，消息链由它组成|
|`MessageChain`|`send-message.md`, `plugin-new.md`|消息链构建工具|
|`MessageEventResult`|`simple.md`, `plugin-new.md`|消息事件返回结果|

#### 2.2.2 AstrBotMessage 字段

|字段|源文件|简介|
|-|-|-|
|`type`|`listen-message-event.md`, `plugin-new.md`|消息类型|
|`self\_id`|同上|机器人识别 ID|
|`session\_id`|同上|会话 ID|
|`message\_id`|同上|消息 ID|
|`group\_id`|同上|群组 ID（私聊为空）|
|`sender`|同上|发送者 (`MessageMember`)|
|`message`|同上|消息链 (`List\[BaseMessageComponent]`)|
|`message\_str`|同上|纯文本消息字符串|
|`raw\_message`|同上|平台适配器原始消息对象|
|`timestamp`|同上|消息时间戳|

#### 2.2.3 消息段类型（`astrbot.api.message\_components`）

|组件类|源文件|简介|
|-|-|-|
|`Plain`|`listen-message-event.md`, `plugin-new.md`|文本消息|
|`At`|同上|@提及|
|`Image`|同上|图片 (`.fromURL()`, `.fromFileSystem()`)|
|`Record`|同上|语音|
|`Video`|同上|视频 (`.fromURL()`, `.fromFileSystem()`)|
|`File`|同上|文件|
|`Face`|同上|QQ 表情|
|`Node`|同上|合并转发节点|
|`Nodes`|同上|合并转发多节点|
|`Poke`|同上|戳一戳|
|`Reply`|`plugin-new.md`|回复消息|
|`Forward`|`plugin-new.md`|转发消息|
|`Music`|`plugin-new.md`|音乐分享|

\---

### 2.3 指令与过滤器（`astrbot.api.event.filter`）

#### 2.3.1 指令注册装饰器

|装饰器|源文件|简介|
|-|-|-|
|`@filter.command(name, alias, priority)`|`listen-message-event.md`, `simple.md`, `plugin-new.md`|注册指令|
|`@filter.command\_group(name)`|`listen-message-event.md`, `plugin-new.md`|注册指令组|
|`@group.command(name)`|同上|在指令组内注册子指令|
|`@group.group(name)`|`listen-message-event.md`, `plugin-new.md`|在指令组内嵌套子组（无限嵌套）|

#### 2.3.2 事件过滤装饰器

|装饰器|源文件|简介|
|-|-|-|
|`@filter.event\_message\_type(type)`|`listen-message-event.md`, `plugin-new.md`|按消息类型过滤 (`EventMessageType.ALL` / `PRIVATE\_MESSAGE` / `GROUP\_MESSAGE`)|
|`@filter.platform\_adapter\_type(type)`|同上|按消息平台过滤 (`PlatformAdapterType.AIOCQHTTP` / `QQOFFICIAL` / `GEWECHAT` / `ALL`)|
|`@filter.permission\_type(type)`|同上|按权限过滤 (`PermissionType.ADMIN`)|

#### 2.3.3 事件钩子装饰器

|装饰器|源文件|简介|
|-|-|-|
|`@filter.on\_astrbot\_loaded()`|`listen-message-event.md`, `plugin-new.md`|Bot 初始化完成时触发|
|`@filter.on\_waiting\_llm\_request()`|`listen-message-event.md`|等待 LLM 请求时触发|
|`@filter.on\_llm\_request()`|`listen-message-event.md`, `plugin-new.md`|LLM 请求前触发，可修改 `ProviderRequest`|
|`@filter.on\_llm\_response()`|同上|LLM 请求完成后触发，可修改 `LLMResponse`|
|`@filter.on\_agent\_begin()`|`listen-message-event.md`, `plugin-new.md`|Agent 开始运行时触发|
|`@filter.on\_using\_llm\_tool()`|同上|LLM 工具调用前触发|
|`@filter.on\_llm\_tool\_respond()`|同上|LLM 工具调用完成后触发|
|`@filter.on\_agent\_done()`|同上|Agent 运行完成时触发|
|`@filter.on\_decorating\_result()`|同上|发送消息前触发，可装饰消息链|
|`@filter.after\_message\_sent()`|同上|发送消息后触发|

#### 2.3.4 工具注册装饰器

|装饰器|源文件|简介|
|-|-|-|
|`@filter.llm\_tool(name)`|`listen-message-event.md`, `plugin-new.md`, `ai.md`|将函数注册为 LLM 可调用的 Tool|

#### 2.3.5 事件控制

|方法|源文件|简介|
|-|-|-|
|`event.stop\_event()`|`listen-message-event.md`, `plugin-new.md`|停止事件传播|
|`priority` 参数|`listen-message-event.md`, `plugin-new.md`|设置指令/钩子优先级（默认 0）|

\---

### 2.4 消息发送 API

|方法|源文件|简介|
|-|-|-|
|`event.plain\_result(text)`|`send-message.md`, `simple.md`, `plugin-new.md`|发送纯文本消息|
|`event.image\_result(path/url)`|同上|发送图片消息|
|`event.chain\_result(chain)`|同上|发送消息链（富媒体）|
|`event.make\_result()`|`session-control.md`, `plugin-new.md`|创建 `MessageEventResult` 对象|
|`event.send(result)`|`listen-message-event.md`, `plugin-new.md`|直接发送（钩子内使用，不支持 yield）|
|`self.context.send\_message(umo, chain)`|`send-message.md`, `plugin-new.md`|主动推送消息|
|`event.get\_result()`|`listen-message-event.md`|获取当前结果对象|
|`event.get\_sender\_name()`|`simple.md`, `plugin-new.md`|获取发送者名称|
|`event.get\_sender\_id()`|`plugin-new.md`|获取发送者 ID|
|`event.get\_platform\_name()`|`other.md`, `plugin-new.md`|获取平台名称|
|`event.unified\_msg\_origin`|`send-message.md`, `plugin-new.md`|会话唯一标识字符串|
|`event.message\_str`|`simple.md`, `plugin-new.md`|消息纯文本内容|

\---

### 2.5 LLM / AI 模块（`ai.md`）

#### 2.5.1 LLM 调用

|函数/方法|源文件|简介|
|-|-|-|
|`self.context.get\_current\_chat\_provider\_id(umo)`|`ai.md`|获取当前会话使用的聊天模型 ID|
|`self.context.llm\_generate(chat\_provider\_id, prompt, contexts)`|`ai.md`|调用大模型生成回复|
|`self.context.get\_using\_provider(umo)`|`plugin-new.md`|获取当前使用的 LLM 提供商|
|`self.context.get\_provider\_by\_id(id)`|`plugin-new.md`|根据 ID 获取 LLM 提供商|
|`self.context.get\_all\_providers()`|`plugin-new.md`|获取所有 LLM 提供商|
|`provider.text\_chat(prompt, context, system\_prompt, ...)`|`plugin-new.md`|请求 LLM 文本对话|

#### 2.5.2 Tool / LLM 工具

|类/装饰器|源文件|简介|
|-|-|-|
|`FunctionTool`|`ai.md`, `plugin-new.md`|函数工具基类（推荐以 `@dataclass` 定义）|
|`ToolSet`|`ai.md`|工具集合，传递给 Agent 或 `text\_chat`|
|`ToolExecResult`|`ai.md`|工具执行结果|
|`@filter.llm\_tool(name)`|`ai.md`, `plugin-new.md`|装饰器方式注册 Tool|
|`self.context.add\_llm\_tools(\*tools)`|`ai.md`|注册 Tool（>= v4.5.1）|
|`self.context.get\_llm\_tool\_manager()`|`plugin-new.md`|获取 LLM Tool Manager|

#### 2.5.3 Agent

|函数/方法|源文件|简介|
|-|-|-|
|`self.context.tool\_loop\_agent(event, chat\_provider\_id, prompt, tools, max\_steps, tool\_call\_timeout, system\_prompt)`|`ai.md`|调用 Agent（自动循环处理工具调用）|
|`ContextWrapper`|`ai.md`|Agent 运行时上下文包装器|
|`AstrAgentContext`|`ai.md`|Agent 上下文类型|
|Multi-Agent (`agent-as-tool`)|`ai.md`|多智能体模式，子 Agent 作为 Tool 注册|

#### 2.5.4 LLMResponse

|属性/方法|源文件|简介|
|-|-|-|
|`role`|`plugin-new.md`|角色 (`assistant` / `tool` / `err`)|
|`completion\_text`|同上|返回的文本（已过时，推荐 `result\_chain`）|
|`result\_chain`|同上|返回的消息链|
|`tools\_call\_args`|同上|工具调用参数列表|
|`tools\_call\_name`|同上|工具调用名称列表|
|`tools\_call\_ids`|同上|工具调用 ID 列表|
|`to\_openai\_tool\_calls()`|同上|转 OpenAI 格式|
|`is\_chunk`|同上|是否为流式输出 Chunk|

#### 2.5.5 LLMResponse 相关 Provider 类型

|类|源文件|简介|
|-|-|-|
|`ProviderRequest`|`listen-message-event.md`|LLM 请求对象|
|`LLMResponse`|`listen-message-event.md`, `plugin-new.md`|LLM 响应对象|
|`TTSProvider`|`plugin-new.md`|语音合成提供商抽象基类|
|`STTProvider`|`plugin-new.md`|语音识别提供商抽象基类|
|`EmbeddingProvider`|`plugin-new.md`|嵌入提供商抽象基类|
|`get\_audio(text)`|`plugin-new.md`|TTS: 文本转音频|
|`get\_text(audio\_url)`|`plugin-new.md`|STT: 音频转文本|
|`get\_embedding(text)`|`plugin-new.md`|获取文本向量|
|`get\_embeddings(texts)`|`plugin-new.md`|批量获取文本向量|
|`get\_dim()`|`plugin-new.md`|获取向量维度|
|`self.context.get\_using\_stt\_provider(umo)`|`plugin-new.md`|获取当前 STT 提供商|
|`self.context.get\_using\_tts\_provider(umo)`|`plugin-new.md`|获取当前 TTS 提供商|
|`self.context.get\_all\_stt\_providers()`|`plugin-new.md`|获取所有 STT 提供商|
|`self.context.get\_all\_tts\_providers()`|`plugin-new.md`|获取所有 TTS 提供商|
|`self.context.get\_all\_embedding\_providers()`|`plugin-new.md`|获取所有 Embedding 提供商|

\---

### 2.6 对话管理（`ai.md`, `plugin-new.md`）

#### 2.6.1 ConversationManager（`self.context.conversation\_manager`）

|方法|源文件|简介|
|-|-|-|
|`get\_curr\_conversation\_id(umo)`|`ai.md`, `plugin-new.md`|获取当前对话 ID|
|`get\_conversation(umo, cid, create\_if\_not\_exists)`|同上|获取指定对话对象|
|`get\_conversations(umo, platform\_id)`|同上|获取全部对话列表|
|`get\_filtered\_conversations(page, page\_size, ...)`|`plugin-new.md`|分页+搜索对话|
|`new\_conversation(umo, ...)`|同上|新建对话|
|`switch\_conversation(umo, cid)`|同上|切换对话|
|`delete\_conversation(umo, cid)`|同上|删除对话|
|`update\_conversation(umo, cid, ...)`|同上|更新对话|
|`add\_message\_pair(cid, user\_message, assistant\_message)`|`ai.md`|快速添加 LLM 记录到对话|
|`get\_human\_readable\_context(umo, cid, ...)`|`plugin-new.md`|生成人类可读对话上下文|

#### 2.6.2 Conversation 模型

|字段|源文件|简介|
|-|-|-|
|`platform\_id`|`ai.md`, `plugin-new.md`|平台 ID|
|`user\_id`|同上|用户 ID|
|`cid`|同上|对话 UUID|
|`history`|同上|历史记录字符串|
|`title`|同上|对话标题|
|`persona\_id`|同上|绑定的人格 ID|
|`created\_at`|同上|创建时间戳|
|`updated\_at`|同上|更新时间戳|

\---

### 2.7 人格管理（`ai.md`, `plugin-new.md`）

#### 2.7.1 PersonaManager（`self.context.persona\_manager`）

|方法|源文件|简介|
|-|-|-|
|`get\_persona(persona\_id)`|`ai.md`, `plugin-new.md`|按 ID 获取人格|
|`get\_all\_personas()`|同上|获取所有人格|
|`create\_persona(persona\_id, system\_prompt, ...)`|同上|创建新人格|
|`update\_persona(persona\_id, ...)`|同上|更新人格|
|`delete\_persona(persona\_id)`|同上|删除人格|
|`get\_default\_persona\_v3(umo)`|同上|获取默认人格（v3 格式）|

#### 2.7.2 Persona / Personality 模型

|类|源文件|简介|
|-|-|-|
|`Persona` (SQLModel)|`ai.md`, `plugin-new.md`|人格数据库模型（ORM），字段: `id`, `persona\_id`, `system\_prompt`, `begin\_dialogs`, `tools`, `created\_at`, `updated\_at`|
|`Personality` (TypedDict)|同上|旧版人格格式，字段: `prompt`, `name`, `begin\_dialogs`, `mood\_imitation\_dialogs`, `tools`|

\---

### 2.8 会话控制（`session-control.md`, `plugin-new.md`）

|类/函数/方法|源文件|简介|
|-|-|-|
|`session\_waiter(timeout, record\_history\_chains)`|`session-control.md`, `plugin-new.md`|会话控制器装饰器|
|`SessionController`|同上|会话控制器实例|
|`controller.keep(timeout, reset\_timeout)`|同上|保持会话|
|`controller.stop()`|同上|结束会话|
|`controller.get\_history\_chains()`|同上|获取历史消息链|
|`SessionFilter`|同上|自定义会话 ID 算子基类|
|`CustomFilter.filter(event)`|同上|返回自定义会话 ID 字符串|

\---

### 2.9 插件配置（`plugin-config.md`）

#### 2.9.1 `\_conf\_schema.json` 支持的字段类型

|类型|源文件|简介|
|-|-|-|
|`string`|`plugin-config.md`|字符串|
|`text`|同上|大文本（textarea）|
|`int`|同上|整数|
|`float`|同上|浮点数|
|`bool`|同上|布尔值|
|`object`|同上|嵌套对象|
|`list`|同上|列表|
|`dict`|同上|字典（可配合 `template\_schema`）|
|`template\_list`|同上|模板列表（>= v4.10.4）|
|`file`|同上|文件上传（>= v4.13.0）|

#### 2.9.2 Schema 字段属性

|属性|源文件|简介|
|-|-|-|
|`type` (必填)|`plugin-config.md`|配置值的类型|
|`description`|同上|配置描述|
|`hint`|同上|提示信息（问号按钮）|
|`obvious\_hint`|同上|醒目提示|
|`default`|同上|默认值|
|`items`|同上|object 类型的子 Schema|
|`invisible`|同上|是否隐藏（默认 false）|
|`options`|同上|下拉列表可选项|
|`editor\_mode`|同上|代码编辑器模式|
|`editor\_language`|同上|代码编辑器语言|
|`editor\_theme`|同上|代码编辑器主题|
|`\_special`|同上|可视化提供商/人格/知识库选取|
|`file\_types`|同上|文件上传允许的类型（file 类型）|
|`slider`|同上|滑块配置（dict 类型 template\_schema）|
|`template\_schema`|同上|dict 类型的快速编辑模板|

#### 2.9.3 `\_special` 可选值

|值|源文件|简介|
|-|-|-|
|`select\_provider`|`plugin-config.md`|选取 LLM 提供商|
|`select\_provider\_tts`|同上|选取 TTS 提供商|
|`select\_provider\_stt`|同上|选取 STT 提供商|
|`select\_persona`|同上|选取人格|
|`select\_knowledgebase`|同上|选取知识库（返回 list）|

\---

### 2.10 文转图（`html-to-pic.md`）

|方法|源文件|简介|
|-|-|-|
|`self.text\_to\_image(text, return\_url=True)`|`html-to-pic.md`|文字转图片|
|`self.html\_render(template, data, options)`|同上|HTML+Jinja2 模板渲染图片|

#### 渲染选项

|选项|源文件|简介|
|-|-|-|
|`timeout`|`html-to-pic.md`|截图超时时间|
|`type`|同上|截图图片类型 (`jpeg` / `png`)|
|`quality`|同上|截图质量（仅 JPEG）|
|`omit\_background`|同上|透明背景（仅 PNG）|
|`full\_page`|同上|全页截图（默认 True）|
|`clip`|同上|裁切区域|
|`animations`|同上|CSS 动画 (`allow` / `disabled`)|
|`caret`|同上|文本插入符号 (`hide` / `initial`)|
|`scale`|同上|页面缩放 (`css` / `device`)|

\---

### 2.11 插件存储（`storage.md`）

|方法|源文件|简介|
|-|-|-|
|`self.put\_kv\_data(key, value)`|`storage.md`|写入 KV 存储（>= v4.9.2）|
|`self.get\_kv\_data(key, default)`|同上|读取 KV 存储|
|`self.delete\_kv\_data(key)`|同上|删除 KV 存储|
|`get\_astrbot\_data\_path()`|同上|获取 AstrBot 数据根目录|
|大文件路径: `data/plugin\_data/{plugin\_name}/`|同上|大文件存储规范|

\---

### 2.12 杂项工具（`other.md`, `plugin-new.md`）

|函数/方法|源文件|简介|
|-|-|-|
|`self.context.get\_platform(adapter\_type)`|`other.md`, `plugin-new.md`|获取消息平台实例|
|`self.context.get\_all\_stars()`|同上|获取所有载入的插件 (`StarMetadata`)|
|`self.context.platform\_manager.get\_insts()`|同上|获取所有加载的平台|
|`self.context.get\_config(umo=None)`|`plugin-new.md`|获取配置（umo 不为 None 时获取会话级配置）|
|`asyncio.create\_task(self.my\_task())`|`plugin-new.md`|注册异步任务|
|`event.bot.api.call\_action(action, \*\*payloads)`|`other.md`, `plugin-new.md`|调用 QQ 协议端 API|
|`from astrbot.api import logger`|`simple.md`, `plugin-new.md`|AstrBot 日志接口|

\---

### 2.13 插件发布（`plugin-publish.md`）

|流程/概念|源文件|简介|
|-|-|-|
|提交到 [plugins.astrbot.app](https://plugins.astrbot.app)|`plugin-publish.md`|填写表单后跳转 GitHub Issue 完成发布|
|`metadata.yaml`|`plugin-new.md`, `env.md`|插件元数据（名称、作者、版本等）|
|`support\_platforms`|`plugin-new.md`|声明支持的平台（如 telegram, discord 等）|
|`astrbot\_version`|`plugin-new.md`|声明要求的 AstrBot 版本范围（PEP 440）|
|`display\_name`|`plugin-new.md`|插件展示名|
|`logo.png`|`plugin-new.md`|插件 Logo（256x256, 1:1）|
|`requirements.txt`|`env.md`, `plugin-new.md`|第三方依赖管理|

\---

## 三、过滤器组合使用示例速查

|场景|装饰器组合|源文件|
|-|-|-|
|私聊指令|`@filter.command("xx")` + `@filter.event\_message\_type(PRIVATE\_MESSAGE)`|`listen-message-event.md`|
|管理员指令|`@filter.command("xx")` + `@filter.permission\_type(ADMIN)`|同上|
|指定平台|`@filter.command("xx")` + `@filter.platform\_adapter\_type(AIOCQHTTP)`|同上|
|多平台监听|`@filter.platform\_adapter\_type(AIOCQHTTP \| QQOFFICIAL)`|同上|
|监听所有事件|`@filter.event\_message\_type(EventMessageType.ALL)`|同上|

\---

## 四、版本演进标记速查

|版本节点|新增特性|源文件|
|-|-|-|
|v3.4.15|插件配置 Schema 支持|`plugin.md`|
|v3.4.21|优先级支持|`plugin.md`|
|v3.4.28|指令别名|`plugin-new.md`, `plugin.md`|
|v3.4.34|`on\_astrbot\_loaded` 钩子、获取平台实例|`plugin-new.md`|
|v3.4.36|会话控制|`plugin-new.md`|
|v3.5.10|代码编辑器模式|`plugin-config.md`|
|v4.0.0|`\_special` 字段、Persona、会话级配置|`plugin-config.md`, `plugin-new.md`|
|v4.5.0|插件 Logo、展示名|`plugin-new.md`|
|v4.5.1|`self.context.add\_llm\_tools()`|`ai.md`|
|v4.5.7|新版 LLM 调用 API、`tool\_loop\_agent`、Multi-Agent|`ai.md`|
|v4.9.2|KV 存储 (`put\_kv\_data` 等)|`storage.md`|
|v4.10.4|`template\_list` 类型|`plugin-config.md`|
|v4.13.0|`file` 类型 schema|`plugin-config.md`|
|v4.23.1|`on\_agent\_begin`, `on\_using\_llm\_tool`, `on\_llm\_tool\_respond`, `on\_agent\_done` 钩子|`listen-message-event.md`|

\---

> 本文档由 `F:\\astrbot\\guides\\` 目录下 13 个 Markdown 文件自动整理生成。

