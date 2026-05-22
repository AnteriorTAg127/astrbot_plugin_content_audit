# 文本内容审核插件 / Text Content Audit Plugin

[![License](https://img.shields.io/badge/license-AGPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-v1.0.0-blue)](metadata.yaml)
[![AstrBot](https://img.shields.io/badge/AstrBot-plugin-orange)](https://github.com/AstrBotDevs/AstrBot)

> 这是一个为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 提供文本内容审核功能的插件。
>
> 监听被管理群中所有文本消息，调用本地审核 API（端口 8000）进行违规检测，支持自动撤回、递增禁言、管理群通报等处置措施。

---

## 功能特性

- **文本违规内容实时检测与处置** — 调用本地审核 API 检测违规文本并自动处置
- **双群管理模式（被管理群 + 管理群分离）** — 被管理群干活，管理群看报告 + 下指令
- **智能审查模式（基于管理员在线状态自动开关）** — 管理员在线时暂停审查，离线后自动补漏，夜间强制审查
- **违规通报与处置（撤回/禁言，可独立开关）** — 撤回和禁言可配置关闭，但通报始终生效（或选择静默模式）
- **管理员/群主豁免** — 仅通报管理群，不执行处罚
- **递增禁言时长（按违规次数递增）** — 支持自定义倍率和上限
- **用户白名单系统** — 白名单用户的消息不受审核
- **审核日志与统计** — 记录违规日志，支持分页查询和统计
- **健康检查与自动恢复** — 定时检测审核 API 状态，异常时降级放行
- **审计日志自动清理** — 自动清理 30 天前的日志，防止数据库膨胀
- **每群独立覆盖配置** — 支持为每个被管理群独立覆盖全局的跳过管理员、跳过 LLM、自动撤回、自动禁言、最短审核长度等设置

---

## 架构概览

插件由 8 个模块组成：

| 模块 | 文件 | 职责 |
|------|------|------|
| **入口** | `main.py` | 插件注册、消息/命令路由、模块初始化、健康检查循环 |
| **配置管理** | `config_manager.py` | 配置读写、热重载、智能审查决策、白名单查询、每群覆盖配置解析 |
| **权限管理** | `admin_manager.py` | 管理员检测与缓存、群主识别、管理员发言时间追踪 |
| **审核客户端** | `audit_client.py` | 审核 API HTTP 客户端（`POST /audit`, `GET /health`），指数退避重试 |
| **消息编排** | `message_handler.py` | 消息处理主流程：过滤 → 决策 → 豁免 → 审核 → 处置 |
| **违规处置** | `violation_handler.py` | 管理群通报、消息撤回、递增禁言 |
| **统计存储** | `stats_manager.py` | SQLite 数据库管理（审计日志、违规记录、白名单）、查询与清理 |
| **命令处理** | `command_handler.py` | `/文本审核` 命令组的分发与执行 |

### 审核流程

```
群文本消息到达
  │
  ├─ 消息来源是否为被管理群？否则忽略
  ├─ 是否包含纯文本？否则忽略
  ├─ 发送者是否为机器人自身？是则忽略
  │
  ▼
【智能审查决策】
  │
  ├─ 不应审查 → 跳过
  │
  └─ 应审查
       │
       ├─ 白名单用户 → 放行
       ├─ 管理员/群主（skip_admin 开启）→ 放行
       │
       ▼
  调用 POST /audit（审核 API）
       │
       ├─ 正常 → 放行
       │
       └─ 违规
            ├─ 【管理群通报】（始终执行）
            ├─ 管理员/群主 → 仅通报，不处罚
            └─ 普通成员：
                 ├─ 撤回消息（可关闭）
                 └─ 禁言用户（可关闭，时长递增）
```

---

## 安装说明

### 方式一：通过 AstrBot 插件市场安装

在 AstrBot 管理面板的插件市场搜索 "文本审核" 并安装。

### 方式二：手动安装

```bash
# 克隆插件仓库
git clone https://github.com/AnteriorTAg127/astrbot_plugin_content_audit.git

# 复制到 AstrBot 插件目录
cp -r astrbot_plugin_content_audit <astrbot_plugins_path>/

# 安装依赖
cd <astrbot_plugins_path>/astrbot_plugin_content_audit
pip install -r requirements.txt
```

### 数据存储

插件运行时数据存储在 AstrBot 数据目录下：

```
<astrbot_data>/plugin_data/content_audit_text/
└── audit.db              # SQLite 数据库（审计日志、违规记录、白名单）
```

---

## 配置说明

插件配置在 AstrBot 管理面板或 `_conf_schema.json` 中进行，分为以下分组：

### API 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `api.base_url` | string | `http://127.0.0.1:8000` | 审核 API 地址 |
| `api.api_key` | string | `""` | API Key（standard 分组即可） |
| `api.timeout` | int | `10` | HTTP 请求超时（秒） |
| `api.max_retries` | int | `3` | 失败最大重试次数 |
| `api.health_check_interval` | int | `60` | 健康检查间隔（秒），0=关闭 |

### 审核行为

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `audit.enabled` | bool | `true` | 总开关，关闭后完全不审查 |
| `audit.skip_admin` | bool | `true` | 是否跳过管理员/群主的消息 |
| `audit.skip_llm` | bool | `false` | 是否跳过 LLM 复核（仅用关键词+语义） |
| `audit.min_text_length` | int | `2` | 最短审核文本长度 |

### 违规行为（可独立关闭）

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `action.auto_recall` | bool | `true` | 是否自动撤回违规消息 |
| `action.auto_mute` | bool | `true` | 是否自动禁言违规用户 |
| `action.first_mute_duration` | int | `300` | 首次禁言时长（秒） |
| `action.max_mute_duration` | int | `86400` | 最大禁言时长（秒） |
| `action.mute_multiplier` | float | `2.0` | 禁言时长递增倍率 |

### 通报配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `notify.mode` | enum | `violation_only` | 通报模式：`violation_only`（仅违规时通报），`none`（静默，不通报） |
| `notify.show_text_preview` | bool | `true` | 是否在通报中显示违规文本片段 |
| `notify.preview_max_length` | int | `100` | 文本预览最大字符数 |

### 群管理配置（`group_settings`，数组）

每个条目定义一个被管理群到管理群的绑定：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `group_id` | string | — | 被管理群号 |
| `manage_group_id` | string | — | 管理群号（接收通报 + 执行命令） |
| `enabled` | bool | `true` | 该群是否启用审核 |
| `enable_auto_censor` | bool | `false` | 是否启用智能审查模式 |
| `auto_censor_schedule` | string | `""` | 强制审查时间段，格式 `hh:mm-hh:mm` |
| `auto_censor_no_admin_minutes` | int | `0` | 管理员离线检测窗口（分钟），0=关闭 |

#### 每群独立覆盖配置

以下配置项可为每个被管理群独立覆盖全局设置（设为 `null` 则跟随全局）：

| 覆盖项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `override_skip_admin` | bool | `null` | 覆盖全局「跳过管理员」 |
| `override_skip_llm` | bool | `null` | 覆盖全局「跳过 LLM 复核」 |
| `override_auto_recall` | bool | `null` | 覆盖全局「自动撤回」 |
| `override_auto_mute` | bool | `null` | 覆盖全局「自动禁言」 |
| `override_min_text_length` | int | `null` | 覆盖全局「最短审核文本长度」 |

> 详细配置项说明请参考 `_conf_schema.json`。

---

## 命令列表

所有命令仅可在管理群使用。

| 命令 | 说明 | 权限 |
|------|------|------|
| `/文本审核 帮助` | 显示所有子命令及说明 | 无 |
| `/文本审核 状态` | 汇总该管理群下所有被管理群的审核统计 | 无 |
| `/文本审核 状态 <群号>` | 查看指定被管理群的审核统计 | 无 |
| `/文本审核 日志` | 查看最近 10 条违规记录 | 无 |
| `/文本审核 日志 <页码>` | 分页查看违规日志 | 无 |
| `/文本审核 白名单 添加 <QQ号>` | 添加用户到白名单 | 管理员 |
| `/文本审核 白名单 删除 <QQ号>` | 从白名单移除用户 | 管理员 |
| `/文本审核 白名单 列表` | 列出所有白名单用户 | 无 |
| `/文本审核 删除违规 <QQ号>` | 清除指定用户在所有关联被管理群中的违规记录 | 管理员 |

---

## 智能审查模式

启用 `enable_auto_censor: true` 后，插件会根据时间段和管理员在线状态智能决定是否审查。核心思路：被动式在线推断 —— "管理员在 N 分钟内发了消息" 视为在线，不依赖平台 API。

**安全优先**：任何异常（无记录、配置缺失、获取身份失败）均回退到"开启审查"。

```
1. enable_auto_censor == false?  → 全量审查（始终开启）
2. 当前时间在 auto_censor_schedule 内?  → 强制开启
3. last_admin_time 不存在?  → 开启（无记录，安全兜底）
4. elapsed >= auto_censor_no_admin_minutes?  → 开启（管理离线）
5. 否则 → 暂停审查（管理在线）
```

**典型配置**：夜间 23:00-09:00 强制审查，白天管理员 30 分钟内有发言则暂停审查。

---

## 禁言时长计算

- 首次违规禁言 = `first_mute_duration`
- 第 N 次违规 = `first_mute_duration` × `mute_multiplier`^(N-1)
- 结果不超过 `max_mute_duration`

示例：首次 300 秒，倍率 2.0，上限 86400 秒：

| 违规次数 | 禁言时长 |
|----------|----------|
| 第 1 次 | 300 秒（5 分钟） |
| 第 2 次 | 600 秒（10 分钟） |
| 第 3 次 | 1,200 秒（20 分钟） |
| 第 4 次 | 2,400 秒（40 分钟） |
| 第 5 次 | 4,800 秒（80 分钟） |
| 第 6 次 | 9,600 秒（160 分钟） |
| 第 7 次 | 19,200 秒（~5.3 小时） |
| 第 8 次 | 38,400 秒（~10.6 小时） |
| 第 9 次 | 76,800 秒（~21.3 小时） |
| 第 10 次 | 86,400 秒（24 小时，已达上限） |

---

## 错误处理策略

| 场景 | 策略 |
|------|------|
| 审核 API 不可用 | 降级放行，日志告警，不阻塞群聊 |
| 撤回失败（机器人无权限） | 通报管理群时标注"撤回失败" |
| 禁言失败 | 通报标注"禁言失败" |
| 网络超时 | 重试 N 次（指数退避），仍失败则放行 |
| 数据库错误 | 降级为仅通报不记录 |
| 配置缺失 | 回退到默认值，日志告警 |

---

## 依赖

```txt
aiohttp>=3.9.0
aiosqlite>=0.20.0
```

其余功能依赖 AstrBot 内置或 Python 标准库。

---

## 项目结构

```
astrbot_plugin_content_audit/
├── main.py                  # 插件入口
├── config_manager.py        # 配置管理 + 智能审查决策
├── admin_manager.py         # 管理员检测与缓存
├── audit_client.py          # 审核 API HTTP 客户端
├── message_handler.py       # 消息处理编排
├── violation_handler.py     # 违规处置（通报/撤回/禁言）
├── stats_manager.py         # SQLite 数据持久化
├── command_handler.py       # /文本审核 命令组
├── platform_utils.py        # 平台工具函数
├── metadata.yaml            # 插件元信息
├── _conf_schema.json        # 配置项定义
├── requirements.txt         # 依赖
├── pyproject.toml           # Ruff 配置
├── README.md
├── LICENSE
├── .gitignore
└── docs/                    # 设计文档与审查报告（已 gitignore）
```

---

## 许可证

本项目基于 [GNU Affero General Public License v3.0 (AGPLv3)](LICENSE) 开源。

---

## 相关链接

- [AstrBot 仓库](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 文档](https://docs.astrbot.app)
- [AGPLv3 许可证](https://www.gnu.org/licenses/agpl-3.0.html)
