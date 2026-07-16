# Changelog

## [2.2.0] - 2026-07-16

### Added
- Dashboard 4 个表格列表（违规记录/审计日志/白名单/用户档案）支持点击表头排序：服务端 `ORDER BY` + 列白名单防 SQL 注入 + localStorage 持久化排序状态
- 违规/审计列表的群筛改为下拉框（显示"群名 (群号)"），群名按 配置别名 -> 平台 `get_group_list` -> 群号 三级回退；新增 `GET /groups` 端点
- 违规/审计按 `created_at` 时间区间过滤；用户档案按首次/末次出现时间区间过滤
- 用户档案"选区查询"：按群多选过滤（在所选任一群出现过的用户）；新增"加群数"列与排序
- `group_config` 配置新增可选 `group_name` 别名字段（仅用于下拉展示）

### Changed
- 白名单改为分群白名单：`whitelist` 表新增 `group_id` 列（空=全局），唯一键改为 `UNIQUE(user_id, group_id)`，幂等迁移旧数据 `group_id=''`；消息审核白名单检查改为"全局 OR 当前群"
- 多群管理命令优化：管理群仅绑定 1 个被管理群时命令直接作用该群（无需群号）；绑定多个时需带 `<群号|all>`，群号必须绑定到当前管理群。适用 `状态`/`日志`/`白名单`/`删除违规`
- 白名单命令支持群级：`/文本审核 白名单 添加|删除 <QQ号> [群号|all]`、`列表 [群号|all]`（all/缺省=全局）
- 升级版本号至 v2.2.0

## [2.1.0] - 2026-07-16

### Fixed
- 修复 Web 管理面板"修改备注/编辑/删除"等操作报 `bridge does not support method PATCH`：AstrBot 插件页桥（`window.AstrBotPluginPage`）仅支持 GET/POST，将违规/审计/白名单/用户档案的更新与删除路由由 PATCH/DELETE 改为 POST 动作后缀（`<id>/update`、`<id>/delete`），前端 `api()` 同步精简为 GET/POST 并改用 `apiPost`
- 随带修复同一根因的删除操作（`bridge does not support method DELETE`）

### Changed
- 升级版本号至 v2.1.0

## [2.0.0] - 2026-06-26

### Added
- QQ 号智能清洗：送审前自动剔除 @昵称(QQ号) 中的 QQ 号（支持半角/全角括号，上下文缓存同步清洗）
- Dashboard 管理面板：5 个 Tab（概览/违规记录/审计日志/白名单/用户档案），支持增删改查
- 后端 REST API（19 条路由）：概览统计、违规/审计/白名单/用户档案 CRUD，复用 AstrBot 鉴权
- 用户档案表（user_profiles）：自动追踪 QQ 号、昵称、所在群、违规次数、首末次出现时间
- 数据库迁移：whitelist 和 violation_records 新增 note 字段（幂等 ALTER）

### Changed
- 配置项新增 `audit.strip_qq_in_at`（bool，默认 true），控制 QQ 号清洗开关
- 升级版本号至 v2.0.0

## [1.0.0] - 2026-05-24

### Added
- 初始版本
- 文本违规内容实时检测与处置
- 双群管理模式（被管理群 + 管理群分离）
- 智能审查模式（基于管理员在线状态自动开关）
- 违规通报与处置（撤回/禁言，可独立开关）
- 管理员/群主豁免
- 递增禁言时长（按违规次数递增）
- 用户白名单系统
- 审核日志与统计
- 上下文注入（最近 K 条消息）
- 健康检查与自动恢复
- 审计日志自动清理
- 每群独立配置
