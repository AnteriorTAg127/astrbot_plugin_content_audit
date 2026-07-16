from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .text_sanitizer import strip_qq_in_at

if TYPE_CHECKING:
    from .admin_manager import AdminManager
    from .audit_client import AuditClient
    from .config_manager import ConfigManager
    from .context_cache import ContextCache
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
        context_cache: ContextCache,
    ) -> None:
        """构造注入"""
        self._config_manager = config_manager
        self._admin_manager = admin_manager
        self._audit_client = audit_client
        self._violation_handler = violation_handler
        self._stats_manager = stats_manager
        self._context_cache = context_cache

    async def handle(self, event: AstrMessageEvent) -> None:
        """群消息审核主流水线

        流程:
        1. 提取群号与用户信息
        2. 检查群是否启用审核
        3. 提取文本
        4. 跳过 bot 自身消息
        5. 获取上下文（在管理员/白名单跳过之前拉取，在实际审核之前缓存当前消息）
        6. 提前查询管理员身份并记录活跃时间（确保短消息更新在线计时器）
        7. 校验文本长度
        8. 检查全局审核开关
        9. 智能审查决策 + 管理员跳过（skip_admin）
        10. 白名单校验
        11. 缓存当前消息到上下文（在跳过检查之后，防泄漏）
        12. 调用审核 API（附带上下文）
        13. 分发违规处理
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

            # ===== 第3步：提取文本 =====
            message_str = event.message_str
            audit_config = self._config_manager.config.get("audit", {})
            strip_qq_enabled = audit_config.get("strip_qq_in_at", True)
            sanitized_message_str = (
                strip_qq_in_at(message_str) if (strip_qq_enabled and message_str) else (message_str or "")
            )

            # ===== 第4步：跳过 bot 自身消息 =====
            try:
                self_id = str(event.message_obj.self_id)
            except AttributeError:
                self_id = None
            if self_id is not None and user_id == self_id:
                logger.debug("跳过 bot 自身消息")
                return

            # ===== 第5步：获取上下文（在当前消息加入缓存之前） =====
            context_enabled: bool = self._config_manager.get_effective_config(group_id, "context_enabled", True)
            context_k: int = self._config_manager.get_effective_config(group_id, "context_max_messages", 5)
            audit_context = ""
            if context_enabled and context_k > 0 and message_str:
                audit_context = self._context_cache.get_context(group_id, context_k)

            # ===== 第6步：提前查询管理员身份并记录活跃时间 =====
            # 在文本长度校验之前执行，确保管理员短消息也能更新在线计时器
            group_config = self._config_manager.get_group_config(group_id)
            need_admin_check = False
            if group_config:
                enable_auto_censor = self._config_manager.get_effective_config(group_id, "enable_auto_censor", False)
                no_admin_minutes = self._config_manager.get_effective_config(
                    group_id, "auto_censor_no_admin_minutes", 0
                )
                if enable_auto_censor and (no_admin_minutes or 0) > 0:
                    need_admin_check = True
            is_admin = await self._admin_manager.is_user_admin_cached(event, group_id, user_id)
            if need_admin_check and is_admin:
                self._admin_manager.record_admin_message(group_id)
                logger.debug(f"群 {group_id} 管理员 {user_id} 发言，记录活跃时间")

            # ===== 第7步：校验文本长度 =====
            min_length: int = self._config_manager.get_effective_config(group_id, "min_text_length", 2)
            if not sanitized_message_str or len(sanitized_message_str) < min_length:
                # 短消息仍缓存为未来上下文（原设计保证），但排除管理员防止未审核消息
                # 泄漏到审核 API 上下文（bug#7）。白名单短消息（< min_text_length，通常 1 字符）
                # 泄漏风险极低，且白名单检查在第 10 步、此处尚未执行。
                if context_enabled and context_k > 0 and message_str and not is_admin:
                    self._context_cache.add(group_id, user_name, sanitized_message_str, context_k)
                logger.debug(f"消息文本过短或为空(清洗后): len={len(sanitized_message_str)}, min={min_length}")
                return

            # ===== 第8步：检查全局审核开关 =====
            if not audit_config.get("enabled", True):
                logger.debug("全局审核开关已关闭")
                return

            # ===== 第9步：智能审查决策 + 管理员跳过 =====
            skip_admin: bool = self._config_manager.get_effective_config(group_id, "skip_admin", True)
            if skip_admin and is_admin:
                logger.debug(f"管理员/群主 {user_id} 跳过审核 (skip_admin 已启用)")
                return

            last_admin_time = self._admin_manager.get_last_admin_time(group_id)
            should_enable, reason = self._config_manager.should_enable_censor(group_id, last_admin_time)
            if not should_enable:
                logger.debug(f"智能审查决策: 跳过审核 (原因: {reason})")
                return
            logger.debug(f"智能审查决策: 启用审核 (原因: {reason})")

            # ===== 第10步：白名单校验 =====
            whitelist_config = self._config_manager.config.get("whitelist", {})
            if whitelist_config.get("enabled", False) and await self._config_manager.is_whitelisted(user_id, group_id):
                logger.debug(f"用户 {user_id} 在白名单中，跳过审核")
                return

            # ===== 第11步：缓存当前消息到上下文 =====
            # 在管理员/白名单跳过检查之后执行，确保被跳过的消息不会泄漏到审核 API 上下文中
            if context_enabled and context_k > 0 and message_str:
                self._context_cache.add(group_id, user_name, sanitized_message_str, context_k)
                logger.debug(f"上下文已缓存: group={group_id}, k={context_k}")

            # ===== 第12步：调用审核 API =====
            skip_llm: bool = self._config_manager.get_effective_config(group_id, "skip_llm", False)
            result = await self._audit_client.audit(
                sanitized_message_str,
                skip_llm=skip_llm,
                context=audit_context,
            )

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

            # ===== 第13步：分发违规处理 =====
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
