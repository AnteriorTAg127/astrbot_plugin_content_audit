from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .audit_client import AuditResult
from .platform_utils import get_platform_client

if TYPE_CHECKING:
    from .config_manager import ConfigManager
    from .stats_manager import StatsManager


class ViolationHandler:
    """违规处理类 - 负责违规通报、消息撤回、用户禁言等功能"""

    def __init__(
        self,
        config_manager: ConfigManager,
        stats_manager: StatsManager,
        context,
    ) -> None:
        """构造注入"""
        self._config_manager = config_manager
        self._stats_manager = stats_manager
        self._context = context

    def _get_action_config(self) -> dict:
        """获取违规处理行为配置（撤回/禁言 开关、时长、倍率等）"""
        return self._config_manager.config.get("action", {})

    def _get_notify_config(self) -> dict:
        """获取通报相关配置（是否显示文本预览、预览最大长度等）"""
        return self._config_manager.config.get("notify", {})

    async def _send_notification(
        self,
        event: AstrMessageEvent,
        manage_group_id: str,
        group_id: str,
        user_id: str,
        user_name: str,
        text_preview: str,
        result: AuditResult,
        measures_summary: str,
    ) -> bool:
        """向管理群发送违规通报，返回是否成功通过客户端发送"""
        notify_config = self._get_notify_config()
        mode = notify_config.get("mode", "violation_only")
        if mode == "none":
            logger.info(f"[通报已关闭] 群{group_id} 用户{user_id} 违规但未通报")
            return True
        show_preview = notify_config.get("show_text_preview", True)
        max_length = notify_config.get("preview_max_length", 100)

        # 构建通报内容
        lines = [
            "【文本违规通知】",
            f"群号: {group_id}",
            f"用户: {user_name} ({user_id})",
        ]
        if show_preview:
            preview = text_preview
            if max_length and len(text_preview) > max_length:
                preview = text_preview[:max_length]
            lines.append(f"违规内容: {preview}")
        lines.append(f"请求ID: {result.request_id}")
        lines.append(f"来源: {result.source}")
        lines.append(f"措施: {measures_summary}")
        notification_text = "\n".join(lines)

        client = get_platform_client(self._context, event)
        try:
            if client and hasattr(client, "send_group_msg"):
                try:
                    await client.send_group_msg(group_id=int(manage_group_id), message=notification_text)
                except (ValueError, TypeError) as e:
                    logger.warning(f"manage_group_id 无法转换为 int: {manage_group_id}, {e}")
                    return False
                return True
            else:
                logger.info(f"[管理群通报] {notification_text}")
                return False
        except Exception as e:
            logger.error(f"发送管理群通报失败: {e}")
            return False

    async def _recall_message(self, event: AstrMessageEvent) -> bool:
        """尝试撤回消息，返回是否成功"""
        client = get_platform_client(self._context, event)
        try:
            if client and hasattr(client, "delete_msg"):
                message_id = event.message_obj.message_id
                await client.delete_msg(message_id=message_id)
                logger.info("消息撤回成功")
                return True
            else:
                logger.warning("客户端不支持撤回消息")
                return False
        except Exception as e:
            logger.warning(f"撤回消息失败: {e}")
            return False

    async def _mute_user(
        self,
        event: AstrMessageEvent,
        group_id: str,
        user_id: str,
        duration: int,
    ) -> bool:
        """尝试禁言用户，返回是否成功"""
        client = get_platform_client(self._context, event)
        try:
            if client and hasattr(client, "set_group_ban"):
                try:
                    await client.set_group_ban(
                        group_id=int(group_id),
                        user_id=int(user_id),
                        duration=duration,
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"group_id/user_id 无法转换为 int: group_id={group_id}, user_id={user_id}, {e}")
                    return False
                logger.info(f"禁言用户 {user_id} 成功，时长 {duration} 秒")
                return True
            else:
                logger.warning("客户端不支持禁言")
                return False
        except Exception as e:
            logger.warning(f"禁言用户失败: {e}")
            return False

    async def handle(
        self,
        event: AstrMessageEvent,
        result: AuditResult,
        group_id: str,
        user_id: str,
        user_name: str,
        is_admin: bool,
        text_preview: str,
    ) -> None:
        """违规主处理流程

        流程:
        1. 获取管理群 ID，无则退出
        2. 若为管理员 → 仅通报不处罚，记录违规后返回
        3. 对普通用户执行撤回/禁言
        4. 通报到管理群
        5. 记录违规统计
        """
        # ===== 第1步：获取管理群 ID =====
        manage_group_id = self._config_manager.get_manage_group_id(group_id)
        if not manage_group_id:
            logger.warning(f"群 {group_id} 未配置管理群，将仅记录违规（无法发送通报）")

        # ===== 第2步：管理员仅通报不处罚 =====
        if is_admin:
            measures_summary = "无（管理员/群主身份，不执行处罚）"
            if manage_group_id:
                await self._send_notification(
                    event,
                    manage_group_id,
                    group_id,
                    user_id,
                    user_name,
                    text_preview,
                    result,
                    measures_summary,
                )
            await self._stats_manager.record_violation(
                group_id=group_id,
                user_id=user_id,
                user_name=user_name,
                text_preview=text_preview,
                request_id=result.request_id,
                action_recall=0,
                action_mute=0,
                mute_duration=0,
            )
            return

        # ===== 第3步：获取违规次数（用于递进禁言计算） =====
        violation_count = await self._stats_manager.get_violation_count(user_id, group_id)

        # ===== 第4步：读取行为配置并执行撤回 =====
        action_config = self._get_action_config()
        auto_recall = self._config_manager.get_effective_config(group_id, "auto_recall", True)
        auto_mute = self._config_manager.get_effective_config(group_id, "auto_mute", True)

        recall_success = False
        if auto_recall:
            recall_success = await self._recall_message(event)

        # ===== 第5步：执行禁言（含递进时长计算） =====
        mute_success = False
        mute_duration = 0
        if auto_mute:
            first_mute = action_config.get("first_mute_duration", 300)
            max_mute = action_config.get("max_mute_duration", 86400)
            multiplier = action_config.get("mute_multiplier", 2.0)

            # 当前违规次数 = 已有次数 + 本次（1）
            current_count = violation_count + 1
            duration = int(first_mute * (multiplier ** (current_count - 1)))
            duration = min(duration, max_mute)

            mute_success = await self._mute_user(event, group_id, user_id, duration)
            mute_duration = duration if mute_success else 0

        # ===== 第6步：构建措施摘要 =====
        parts: list[str] = []
        if auto_recall:
            parts.append(f"撤回{'成功' if recall_success else '失败'}")
        if auto_mute:
            parts.append(f"禁言 {mute_duration}秒 {'成功' if mute_success else '失败'}")
        if not parts:
            parts.append("无措施")
        measures_summary = "  ".join(parts)

        # ===== 第7步：发送通报到管理群 =====
        if manage_group_id:
            await self._send_notification(
                event,
                manage_group_id,
                group_id,
                user_id,
                user_name,
                text_preview,
                result,
                measures_summary,
            )

        # ===== 第8步：记录违规统计 =====
        await self._stats_manager.record_violation(
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            text_preview=text_preview,
            request_id=result.request_id,
            action_recall=1 if recall_success else 0,
            action_mute=1 if mute_success else 0,
            mute_duration=mute_duration,
        )
