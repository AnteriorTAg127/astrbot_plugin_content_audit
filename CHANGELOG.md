# Changelog

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
