"""文本内容审核插件入口"""

import asyncio
import os
from collections.abc import AsyncGenerator

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.star import Context, Star, register

from .admin_manager import AdminManager
from .audit_client import AuditClient
from .command_handler import CommandHandler
from .config_manager import ConfigManager
from .context_cache import ContextCache
from .message_handler import MessageHandler
from .stats_manager import StatsManager
from .violation_handler import ViolationHandler
from .web_api import WebApiHandler


@register(
    "astrbot_plugin_content_audit",
    "AnteriorTAg127",
    "基于自用审核API的群聊文本内容审核插件",
    "2.0.0",
)
class ContentAuditPlugin(Star):
    """基于自用审核API的群聊文本内容审核插件"""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)

        # 存储插件专属配置（由 AstrBot 框架传入，不要通过 context.get_config() 读取）
        self._plugin_config: dict = config if config is not None else {}

        # 子模块引用，在 initialize 中初始化
        self._config_manager: ConfigManager | None = None
        self._admin_manager: AdminManager | None = None
        self._audit_client: AuditClient | None = None
        self._context_cache: ContextCache | None = None
        self._stats_manager: StatsManager | None = None
        self._violation_handler: ViolationHandler | None = None
        self._message_handler: MessageHandler | None = None
        self._command_handler: CommandHandler | None = None
        self._health_check_task: asyncio.Task | None = None
        self._web_api: WebApiHandler | None = None

    async def initialize(self) -> None:
        """初始化所有子模块"""
        from pathlib import Path

        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        data_dir = str(Path(get_astrbot_data_path()) / "plugin_data" / "content_audit_text")
        os.makedirs(data_dir, exist_ok=True)

        # 1. 统计管理器（需要 data_dir 用于 SQLite 数据库）
        self._stats_manager = StatsManager(data_dir)
        await self._stats_manager.init_db()

        # 2. 审核客户端（从插件专属配置中读取 API 参数）
        api_config = self._plugin_config.get("api", {})
        base_url = api_config.get("base_url", "http://127.0.0.1:8000")
        api_key = api_config.get("api_key", "")
        timeout = api_config.get("timeout", 10)
        max_retries = api_config.get("max_retries", 3)
        self._audit_client = AuditClient(base_url, api_key, timeout, max_retries)

        # 3. 配置重载回调: 当配置变更时同步更新审核客户端的 base_url
        def _on_config_reload(config: dict) -> None:
            api_cfg = config.get("api", {})
            new_url = api_cfg.get("base_url", "http://127.0.0.1:8000")
            new_key = api_cfg.get("api_key", "")

            def _coerce_int(value, default: int) -> int:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return default

            new_timeout = _coerce_int(api_cfg.get("timeout", 10), 10)
            new_retries = _coerce_int(api_cfg.get("max_retries", 3), 3)
            if self._audit_client is not None:
                self._audit_client.update_base_url(new_url)
                self._audit_client.update_api_key(new_key)
                self._audit_client.update_timeout(new_timeout)
                self._audit_client.update_max_retries(new_retries)

        # 4. 配置管理器（传入 config_getter 回调，而非直接调用 context.get_config()）
        def _config_getter() -> dict:
            return self._plugin_config

        self._config_manager = ConfigManager(_config_getter, self._stats_manager, _on_config_reload)

        # 5. 管理员管理器
        self._admin_manager = AdminManager(self.context)

        # 6. 违规处理器
        self._violation_handler = ViolationHandler(self._config_manager, self._stats_manager, self.context)

        # 7. 消息处理器
        self._context_cache = ContextCache()
        self._message_handler = MessageHandler(
            self._config_manager,
            self._admin_manager,
            self._audit_client,
            self._violation_handler,
            self._stats_manager,
            self._context_cache,
        )

        # 8. 命令处理器
        self._command_handler = CommandHandler(
            self._config_manager,
            self._admin_manager,
            self._stats_manager,
        )

        # 9. 健康检查后台任务
        try:
            health_interval = int(api_config.get("health_check_interval", 60))
        except (ValueError, TypeError):
            health_interval = 60
        if health_interval > 0:
            self._health_check_task = asyncio.create_task(self._health_check_loop(health_interval))

        # 10. 注册 Dashboard Web API
        try:
            self._web_api = WebApiHandler(self._stats_manager, self._config_manager)
            self._web_api.register(self.context, "astrbot_plugin_content_audit")
        except Exception:
            logger.exception("注册 Dashboard Web API 失败，前端页面将不可用")

        logger.info("文本审核插件初始化完成")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> None:
        """处理所有群消息，审核文本内容"""
        try:
            # 仅处理群消息
            group_id = event.message_obj.group_id
            if not group_id:
                return

            await self._message_handler.handle(event)
        except Exception:
            logger.exception("消息处理异常，降级放行")

    @filter.command("文本审核")
    async def cmd_content_audit(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """文本审核命令入口（仅管理群可用）"""
        # 解析子命令: /文本审核 白名单 添加 123456
        message_str = event.message_str.strip()
        parts = message_str.split()

        if len(parts) <= 1:
            subcommand = "帮助"
            args: list[str] = []
        else:
            subcommand = parts[1]
            args = parts[2:]

        reply = await self._command_handler.dispatch(event, subcommand, args)
        yield event.plain_result(reply)

    async def _health_check_loop(self, interval: int) -> None:
        try:
            cleanup_counter = 0
            cleanup_interval = max(1, 24 * 3600 // interval)
            while True:
                await asyncio.sleep(interval)
                try:
                    if self._config_manager is not None:
                        # 配置变更时 maybe_reload 会触发 _on_config_reload 更新 audit_client 全部参数
                        self._config_manager.maybe_reload()
                    elif self._audit_client is not None:
                        # config_manager 不可用时的兜底：直接从 _plugin_config 读 base_url
                        api_config = self._plugin_config.get("api", {})
                        self._audit_client.update_base_url(
                            api_config.get("base_url", "http://127.0.0.1:8000")
                        )
                    if self._audit_client is not None:
                        result = await self._audit_client.health_check()
                        # 记录健康状态汇总（使 health_status 具有消费者）
                        hs = self._audit_client.health_status
                        if hs["fail_count"] > 0:
                            logger.info(f"审核 API 健康状态: ok={hs['ok']}, 累计失败={hs['fail_count']} 次")
                        if result is None:
                            logger.warning("审核 API 健康检查失败")
                    else:
                        result = None
                    cleanup_counter += 1
                    if cleanup_counter >= cleanup_interval and self._stats_manager is not None:
                        deleted = await self._stats_manager.cleanup_audit_log(keep_days=30)
                        logger.info(f"审计日志清理完成，删除 {deleted} 条旧记录")
                        cleanup_counter = 0
                except Exception:
                    logger.exception("健康检查循环内部异常，继续运行")
        except asyncio.CancelledError:
            logger.info("健康检查任务已取消")

    async def terminate(self) -> None:
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except Exception:
                pass
        if self._audit_client:
            await self._audit_client.close()
        if self._stats_manager:
            await self._stats_manager.close()
        logger.info("文本审核插件已卸载")
