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
            "/文本审核 状态 [群号|all] — 查看审核统计\n"
            "/文本审核 日志 [群号|all] [页码] — 分页查看违规日志\n"
            "/文本审核 白名单 添加 <QQ号> [群号|all] — 添加白名单用户（管理员）\n"
            "/文本审核 白名单 删除 <QQ号> [群号|all] — 移除白名单用户（管理员）\n"
            "/文本审核 白名单 列表 [群号|all] — 列出白名单用户\n"
            "/文本审核 删除违规 <QQ号> [群号|all] 确认 — 清除违规记录（管理员）\n"
            "说明：单绑定群自动操作，无需群号；多绑定群需指定群号或 all；白名单 all=全局"
        )

    def _resolve_target_groups(self, mgmt_group_id: str, group_arg: str | None) -> tuple[list[str] | None, str]:
        """解析操作目标群列表

        Args:
            mgmt_group_id: 当前管理群 ID
            group_arg: 用户指定的群号参数，None 表示未提供

        Returns:
            (目标群列表, 错误信息)；错误信息非空时表示拒绝操作
        """
        managed = self._config_manager.get_managed_group_ids(mgmt_group_id)
        if not managed:
            return None, "当前管理群没有关联的被管理群"
        if len(managed) == 1:
            return managed, ""
        if not group_arg:
            return None, "本管理群绑定了多个群，请指定群号或 all。绑定群：" + "、".join(managed)
        if group_arg == "all":
            return managed, ""
        if group_arg not in managed:
            return None, f"群 {group_arg} 未绑定到本管理群"
        return [group_arg], ""

    # ── 状态 ──────────────────────────────────────────────

    async def _status(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        group_arg = args[0] if args else None
        targets, err = self._resolve_target_groups(group_id, group_arg)
        if err:
            return f"⚠️ {err}"

        lines = []
        for mg_id in targets:
            stats = await self._stats_manager.get_stats(group_id=mg_id)
            lines.append(self._format_group_stats(mg_id, stats))
        if not lines:
            return "📊 审核状态\n暂无关联的被管理群"
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
        managed = self._config_manager.get_managed_group_ids(group_id)
        if not managed:
            return "📋 违规日志\n暂无关联的被管理群"

        group_arg: str | None = None
        page = 1
        for arg in args:
            if arg == "all" or arg in managed:
                group_arg = arg
            else:
                try:
                    candidate = int(arg)
                    if candidate >= 1:
                        page = candidate
                    else:
                        return "⚠️ 页码必须大于0"
                except (ValueError, TypeError):
                    return f"⚠️ 无效的参数: {arg}"

        targets, err = self._resolve_target_groups(group_id, group_arg)
        if err:
            return f"⚠️ {err}"

        page_size = 10
        if len(targets) == 1:
            violations = await self._stats_manager.get_violations(targets[0], page=page, page_size=page_size)
        else:
            violations = await self._stats_manager.get_violations_multi_group(targets, page=page, page_size=page_size)

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
            return "⚠️ 用法: /文本审核 白名单 添加|删除|列表 [QQ号] [群号|all]"

        action = args[0]

        if action == "添加":
            return await self._whitelist_add(event, group_id, args[1:])
        elif action == "删除":
            return await self._whitelist_remove(event, group_id, args[1:])
        elif action == "列表":
            return await self._whitelist_list(group_id, args[1:])
        else:
            return f"⚠️ 未知的白名单操作: {action}。可用: 添加 / 删除 / 列表"

    async def _whitelist_add(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        """添加白名单用户（管理员操作），支持群级白名单"""
        if not args:
            return "⚠️ 用法: /文本审核 白名单 添加 <QQ号> [群号|all]"

        sender_id = str(event.get_sender_id())
        is_admin = await self._admin_manager.is_user_admin(event, group_id, sender_id)
        if not is_admin:
            return "⚠️ 仅管理员可执行此操作"

        qq = args[0]
        group_arg = args[1] if len(args) > 1 else None
        wl_group = "" if (group_arg in (None, "all")) else group_arg

        # 指定群号时必须绑定到当前管理群
        if group_arg is not None and group_arg != "all":
            managed = self._config_manager.get_managed_group_ids(group_id)
            if group_arg not in managed:
                return f"⚠️ 群 {group_arg} 未绑定到本管理群"

        result = await self._stats_manager.add_whitelist_with_note(qq, "", wl_group)
        if result is not None:
            self._config_manager.invalidate_whitelist_cache()
            if wl_group:
                return f"✅ 已将用户 {qq} 加入群 {wl_group} 的白名单"
            return f"✅ 已将用户 {qq} 加入全局白名单"
        else:
            return f"⚠️ 用户 {qq} 已在白名单中或操作失败"

    async def _whitelist_remove(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        """移除白名单用户（管理员操作），支持群级白名单"""
        if not args:
            return "⚠️ 用法: /文本审核 白名单 删除 <QQ号> [群号|all]"

        sender_id = str(event.get_sender_id())
        is_admin = await self._admin_manager.is_user_admin(event, group_id, sender_id)
        if not is_admin:
            return "⚠️ 仅管理员可执行此操作"

        qq = args[0]
        group_arg = args[1] if len(args) > 1 else None
        wl_group = "" if (group_arg in (None, "all")) else group_arg

        # 指定群号时必须绑定到当前管理群
        if group_arg is not None and group_arg != "all":
            managed = self._config_manager.get_managed_group_ids(group_id)
            if group_arg not in managed:
                return f"⚠️ 群 {group_arg} 未绑定到本管理群"

        success = await self._stats_manager.remove_whitelist(qq, wl_group)
        if success:
            self._config_manager.invalidate_whitelist_cache()
            if wl_group:
                return f"✅ 已将用户 {qq} 从群 {wl_group} 的白名单移除"
            return f"✅ 已将用户 {qq} 从全局白名单移除"
        else:
            return f"⚠️ 用户 {qq} 不在白名单中"

    async def _whitelist_list(self, group_id: str, args: list[str]) -> str:
        """列出白名单用户，支持按群筛选"""
        group_arg = args[0] if args else None
        wl_group = "" if (group_arg in (None, "all")) else group_arg

        # 指定群号时必须绑定到当前管理群
        if group_arg is not None and group_arg != "all":
            managed = self._config_manager.get_managed_group_ids(group_id)
            if group_arg not in managed:
                return f"⚠️ 群 {group_arg} 未绑定到本管理群"

        users = await self._stats_manager.get_whitelist_by_group(wl_group)
        if users is None:
            return "⚠️ 查询白名单失败（数据库错误）"
        if not users:
            label = "全局" if not wl_group else f"群 {wl_group}"
            return f"📋 白名单列表 ({label})\n暂无白名单用户"

        label = "全局" if not wl_group else f"群 {wl_group}"
        lines = [f"📋 白名单列表 ({label})"]
        for idx, uid in enumerate(users, start=1):
            lines.append(f"{idx}. {uid}")
        return "\n".join(lines)

    # ── 删除违规 ──────────────────────────────────────────

    async def _delete_violation(self, event: AstrMessageEvent, group_id: str, args: list[str]) -> str:
        """清除指定用户的违规记录（管理员操作），支持指定群或全绑定群"""
        if not args:
            return "⚠️ 用法: /文本审核 删除违规 <QQ号> [群号|all] 确认"

        sender_id = str(event.get_sender_id())
        is_admin = await self._admin_manager.is_user_admin(event, group_id, sender_id)
        if not is_admin:
            return "⚠️ 仅管理员可执行此操作"

        qq = args[0]
        has_confirm = "确认" in args
        if not has_confirm:
            return f"⚠️ 确认清除用户 {qq} 的违规记录？请追加「确认」参数:\n/文本审核 删除违规 {qq} [群号|all] 确认"

        # 解析 group_arg: args[1] 若存在且不为"确认"则视为 group_arg
        group_arg: str | None = None
        if len(args) > 1 and args[1] != "确认":
            group_arg = args[1]

        targets, err = self._resolve_target_groups(group_id, group_arg)
        if err:
            return f"⚠️ {err}"

        await self._stats_manager.delete_violations(qq, targets)
        group_names = "、".join(targets)
        return f"✅ 已清除用户 {qq} 在群 {group_names} 中的违规记录"
