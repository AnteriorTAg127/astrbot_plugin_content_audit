from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent

    from .admin_manager import AdminManager
    from .config_manager import ConfigManager
    from .stats_manager import StatsManager


class CommandHandler:
    """处理 /文本审核 命令组下的所有子命令"""

    def __init__(
        self,
        config_manager: ConfigManager,
        admin_manager: AdminManager,
        stats_manager: StatsManager,
    ) -> None:
        """构造注入"""
        self._config_manager = config_manager
        self._admin_manager = admin_manager
        self._stats_manager = stats_manager

    async def dispatch(self, event: AstrMessageEvent, subcommand: str, args: list[str]) -> str:
        """根据子命令分发到对应处理方法

        Args:
            event: AstrBot 消息事件
            subcommand: /文本审核 后的第一个词
            args: 剩余参数列表

        Returns:
            回复文本
        """
        group_id = str(event.get_group_id())
        self._config_manager.maybe_reload()
        logger.info(f"收到命令: /文本审核 {subcommand} {' '.join(args)} (群:{group_id})")

        # 管理群网关校验
        if not self._config_manager.is_manage_group(group_id):
            logger.debug(f"非管理群 {group_id} 尝试使用 /文本审核 命令")
            return "⚠️ 此命令仅可在管理群使用"

        if subcommand == "帮助":
            return self._help()
        elif subcommand == "状态":
            return await self._status(event, group_id, args)
        elif subcommand == "日志":
            return await self._log(event, group_id, args)
        elif subcommand == "白名单":
            return await self._whitelist(event, group_id, args)
        elif subcommand == "删除违规":
            return await self._delete_violation(event, group_id, args)
        else:
            return "⚠️ 未知命令。发送 /文本审核 帮助 查看可用命令"

    # ── 帮助 ──────────────────────────────────────────────

    def _help(self) -> str:
        """返回帮助信息"""
        return (
            "📋 文本审核命令列表\n"
            "/文本审核 状态 — 查看审核统计\n"
            "/文本审核 状态 <群号> — 查看指定群的审核统计\n"
            "/文本审核 日志 — 查看最近10条违规记录\n"
            "/文本审核 日志 <页码> — 分页查看违规日志\n"
            "/文本审核 白名单 添加 <QQ号> — 添加白名单用户（管理员）\n"
            "/文本审核 白名单 删除 <QQ号> — 移除白名单用户（管理员）\n"
            "/文本审核 白名单 列表 — 列出所有白名单用户\n"
            "/文本审核 删除违规 <QQ号> — 清除违规记录（管理员）"
        )

    # ── 状态 ──────────────────────────────────────────────

    async def _status(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        if args:
            target_group_id = args[0]
            stats = await self._stats_manager.get_stats(group_id=target_group_id)
            line = self._format_group_stats(target_group_id, stats)
            return f"📊 审核状态\n{line}"
        else:
            managed_groups = self._config_manager.get_managed_group_ids(group_id)
            if not managed_groups:
                return "📊 审核状态\n暂无关联的被管理群"

            lines = []
            for mg_id in managed_groups:
                stats = await self._stats_manager.get_stats(group_id=mg_id)
                lines.append(self._format_group_stats(mg_id, stats))
            return "📊 审核状态\n" + "\n".join(lines)

    @staticmethod
    def _format_group_stats(group_id: str, stats: dict) -> str:
        """格式化单个群的统计信息"""
        return (
            f"群 {group_id}: "
            f"今日审核 {stats['today_audits']} | "
            f"今日违规 {stats['today_violations']} | "
            f"累计违规 {stats['total_violations']}"
        )

    # ── 日志 ──────────────────────────────────────────────

    async def _log(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        page = 1
        if args:
            try:
                page = int(args[0])
                if page < 1:
                    page = 1
            except (ValueError, TypeError):
                return f"⚠️ 无效的页码: {args[0]}"

        page_size = 10
        managed_groups = self._config_manager.get_managed_group_ids(group_id)
        if not managed_groups:
            return "📋 违规日志\n暂无关联的被管理群"

        violations = await self._stats_manager.get_violations_multi_group(
            managed_groups, page=page, page_size=page_size
        )

        if not violations:
            return "📋 违规日志\n暂无违规记录"

        lines = [f"📋 违规日志 (第{page}页)"]
        for idx, v in enumerate(violations, start=1):
            seq = (page - 1) * page_size + idx
            lines.append(
                f"{seq}. [{v['created_at']}] 群{v['group_id']} {v['user_name']}({v['user_id']})\n"
                f"   内容: {v['text_preview']}\n"
                f"   措施: 撤回={v['action_recall']} 禁言={v['action_mute']}s"
            )

        total_hint = f"--- 第{page}页 ---"
        lines.append(total_hint)
        return "\n".join(lines)

    # ── 白名单 ────────────────────────────────────────────

    async def _whitelist(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        """白名单子命令路由: 添加 / 删除 / 列表"""
        if not args:
            return "⚠️ 用法: /文本审核 白名单 添加|删除|列表 [QQ号]"

        action = args[0]

        if action == "添加":
            return await self._whitelist_add(event, group_id, args[1:])
        elif action == "删除":
            return await self._whitelist_remove(event, group_id, args[1:])
        elif action == "列表":
            return await self._whitelist_list()
        else:
            return f"⚠️ 未知的白名单操作: {action}。可用: 添加 / 删除 / 列表"

    async def _whitelist_add(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        """添加白名单用户（管理员操作）"""
        if not args:
            return "⚠️ 用法: /文本审核 白名单 添加 <QQ号>"

        sender_id = str(event.get_sender_id())
        is_admin = await self._admin_manager.is_user_admin(event, group_id, sender_id)
        if not is_admin:
            return "⚠️ 仅管理员可执行此操作"

        target_qq = args[0]
        success = await self._stats_manager.add_whitelist(target_qq)
        if success:
            self._config_manager.invalidate_whitelist_cache()
            return f"✅ 已将用户 {target_qq} 加入白名单"
        else:
            return f"⚠️ 用户 {target_qq} 已在白名单中或操作失败"

    async def _whitelist_remove(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        """移除白名单用户（管理员操作）"""
        if not args:
            return "⚠️ 用法: /文本审核 白名单 删除 <QQ号>"

        sender_id = str(event.get_sender_id())
        is_admin = await self._admin_manager.is_user_admin(event, group_id, sender_id)
        if not is_admin:
            return "⚠️ 仅管理员可执行此操作"

        target_qq = args[0]
        success = await self._stats_manager.remove_whitelist(target_qq)
        if success:
            self._config_manager.invalidate_whitelist_cache()
            return f"✅ 已将用户 {target_qq} 从白名单移除"
        else:
            return f"⚠️ 用户 {target_qq} 不在白名单中"

    async def _whitelist_list(self) -> str:
        """列出所有白名单用户"""
        users = await self._stats_manager.get_whitelist()
        if users is None:
            return "⚠️ 查询白名单失败（数据库错误）"
        if not users:
            return "📋 白名单列表\n暂无白名单用户"

        lines = ["📋 白名单列表"]
        for idx, uid in enumerate(users, start=1):
            lines.append(f"{idx}. {uid}")
        return "\n".join(lines)

    # ── 删除违规 ──────────────────────────────────────────

    async def _delete_violation(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        """清除指定用户在所有关联群中的违规记录（管理员操作）"""
        if not args:
            return "⚠️ 用法: /文本审核 删除违规 <QQ号>"

        sender_id = str(event.get_sender_id())
        is_admin = await self._admin_manager.is_user_admin(event, group_id, sender_id)
        if not is_admin:
            return "⚠️ 仅管理员可执行此操作"

        target_qq = args[0]
        if len(args) < 2 or args[-1] != "确认":
            return f"⚠️ 确认清除用户 {target_qq} 的违规记录？请追加「确认」参数:\n/文本审核 删除违规 {target_qq} 确认"

        managed_groups = self._config_manager.get_managed_group_ids(group_id)
        if not managed_groups:
            return "⚠️ 当前管理群没有关联的被管理群"

        await self._stats_manager.delete_violations(target_qq, managed_groups)
        return f"✅ 已清除用户 {target_qq} 在所有关联群中的违规记录"
