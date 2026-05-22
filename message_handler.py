from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

if TYPE_CHECKING:
    from .admin_manager import AdminManager
    from .audit_client import AuditClient
    from .config_manager import ConfigManager
    from .stats_manager import StatsManager
    from .violation_handler import ViolationHandler


class MessageHandler:
    """消息处理类 - 串联配置、管理员、审核客户端与违规处理四个模块"""

    def __init__(
        self,
        config_manager: ConfigManager,
        admin_manager: AdminManager,
        audit_client: AuditClient,
        violation_handler: ViolationHandler,
        stats_manager: StatsManager,
    ) -> None:
        """构造注入"""
        self._config_manager = config_manager
        self._admin_manager = admin_manager
        self._audit_client = audit_client
        self._violation_handler = violation_handler
        self._stats_manager = stats_manager

    async def handle(self, event: AstrMessageEvent) -> None:
        """群消息审核主流水线（来自设计文档 §二）

        流程:
        1. 提取群号与用户信息
        2. 检查群是否启用审核
        3. 提取并校验文本长度
        4. 跳过 bot 自身消息
        5. 检查全局审核开关
        6. 智能审查决策（时间段 / 管理员在线检测）
        7. 白名单校验
        8. 管理员跳过（skip_admin）
        9. 调用审核 API
        10. 分发违规处理
        """
        try:
            # ===== 第1步：提取群号与用户信息 =====
            group_id = str(event.message_obj.group_id)
            user_id = str(event.get_sender_id())
            user_name = event.get_sender_name()
            logger.debug(f"收到消息: group={group_id}, user={user_id}, name={user_name}")

            # ===== 第2步：检查群是否启用审核 =====
            if not self._config_manager.is_group_enabled(group_id):
                logger.debug(f"群 {group_id} 未启用审核，跳过")
                return

            # ===== 第3步：提取文本并校验长度 =====
            message_str = event.message_str
            audit_config = self._config_manager.config.get("audit", {})
            min_length: int = self._config_manager.get_effective_config(group_id, "min_text_length", 2)
            if not message_str or len(message_str) < min_length:
                logger.debug(f"消息文本过短或为空: len={len(message_str) if message_str else 0}, min={min_length}")
                return

            # ===== 第4步：跳过 bot 自身消息 =====
            try:
                self_id = str(event.message_obj.self_id)
                if user_id == self_id:
                    logger.debug("跳过 bot 自身消息")
                    return
            except Exception:
                pass

            # ===== 第5步：检查全局审核开关 =====
            if not audit_config.get("enabled", True):
                logger.debug("全局审核开关已关闭")
                return

            # ===== 第6步：智能审查决策 =====
            group_config = self._config_manager.get_group_config(group_id)
            need_admin_check = False
            if group_config:
                auto_censor_no_admin_minutes = group_config.get("auto_censor_no_admin_minutes", 0)
                enable_auto_censor = group_config.get("enable_auto_censor", False)
                if enable_auto_censor and auto_censor_no_admin_minutes > 0:
                    need_admin_check = True
            else:
                auto_censor_no_admin_minutes = 0
                enable_auto_censor = False

            skip_admin: bool = self._config_manager.get_effective_config(group_id, "skip_admin", True)
            if need_admin_check or skip_admin:
                is_admin = await self._admin_manager.is_user_admin_cached(event, group_id, user_id)
                if need_admin_check and is_admin:
                    self._admin_manager.record_admin_message(group_id)
                    logger.debug(f"群 {group_id} 管理员 {user_id} 发言，记录活跃时间")
                if skip_admin and is_admin:
                    logger.debug(f"管理员/群主 {user_id} 跳过审核 (skip_admin 已启用)")
                    return
            else:
                is_admin = False

            last_admin_time = self._admin_manager.get_last_admin_time(group_id)
            should_enable, reason = self._config_manager.should_enable_censor(group_id, last_admin_time)
            if not should_enable:
                logger.debug(f"智能审查决策: 跳过审核 (原因: {reason})")
                return
            logger.debug(f"智能审查决策: 启用审核 (原因: {reason})")

            # ===== 第7步：白名单校验 =====
            whitelist_config = self._config_manager.config.get("whitelist", {})
            if whitelist_config.get("enabled", False) and await self._config_manager.is_whitelisted(user_id):
                logger.debug(f"用户 {user_id} 在白名单中，跳过审核")
                return

            # ===== 第9步：调用审核 API =====
            skip_llm: bool = self._config_manager.get_effective_config(group_id, "skip_llm", False)
            result = await self._audit_client.audit(message_str, skip_llm=skip_llm)

            await self._stats_manager.record_audit(
                group_id=group_id,
                user_id=user_id,
                user_name=user_name,
                text_preview=message_str,
                has_violation=1 if result.has_violation else 0,
                source=result.source,
                request_id=result.request_id,
            )

            if result.error:
                logger.warning(f"审核 API 不可用，降级放行: group={group_id}, user={user_id}, error={result.error}")
                return

            # ===== 第10步：分发违规处理 =====
            if result.has_violation:
                notify_config = self._config_manager.config.get("notify", {})
                show_preview: bool = notify_config.get("show_text_preview", True)
                max_preview_len: int = notify_config.get("preview_max_length", 100)

                text_preview = message_str[:max_preview_len] if show_preview else ""

                await self._violation_handler.handle(
                    event=event,
                    result=result,
                    group_id=group_id,
                    user_id=user_id,
                    user_name=user_name,
                    is_admin=is_admin,
                    text_preview=text_preview,
                )
            else:
                logger.debug(f"文本审核通过: group={group_id}, user={user_id}")

        except Exception:
            logger.exception("消息审核流水线异常，降级放行")
            return
