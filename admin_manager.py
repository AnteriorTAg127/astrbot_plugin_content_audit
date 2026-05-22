from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from astrbot.api import logger

from .platform_utils import get_platform_client

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent


class AdminManager:
    """群管理员缓存与权限管理"""

    def __init__(self, context):
        self._context = context
        # 管理员列表缓存: {group_id: {"admins": set[str], "expires_at": datetime}}
        self._admin_cache: dict[str, dict] = {}
        self._admin_cache_ttl: int = 300  # 5 分钟过期

        # 每个群最近一次管理员发言时间: {group_id: datetime}
        self._last_admin_message_time: dict[str, datetime] = {}

    async def _fetch_admins(self, event: AstrMessageEvent, group_id: str) -> set[str]:
        """获取群管理员/群主列表"""
        admins: set[str] = set()
        try:
            client = get_platform_client(self._context, event)

            if client is None:
                logger.warning(f"无法获取群 {group_id} 的平台客户端, 无法拉取管理员列表")
                return admins

            for method_name in ("get_group_member_list", "get_group_members", "get_member_list"):
                if hasattr(client, method_name):
                    method = getattr(client, method_name)
                    members = await method(group_id=int(group_id))
                    for member in members:
                        role = member.get("role", "") if isinstance(member, dict) else getattr(member, "role", "")
                        uid = member.get("user_id", "") if isinstance(member, dict) else getattr(member, "user_id", "")
                        if role in ("owner", "admin") and uid:
                            admins.add(str(uid))
                    break
        except Exception as e:
            logger.warning(f"获取群 {group_id} 管理员列表失败: {e}")
        return admins

    async def is_user_admin_cached(self, event: AstrMessageEvent, group_id: str, user_id: str) -> bool:
        """带缓存的管理员检查: 缓存命中且未过期则直接返回, 否则拉取并缓存"""
        now = datetime.now()
        cache_entry = self._admin_cache.get(group_id)
        if cache_entry is not None and cache_entry.get("expires_at", now) > now:
            return user_id in cache_entry["admins"]

        # 缓存失效或不存在, 重新拉取
        admins = await self._fetch_admins(event, group_id)
        self._admin_cache[group_id] = {
            "admins": admins,
            "expires_at": now + timedelta(seconds=self._admin_cache_ttl),
        }
        return user_id in admins

    async def is_user_admin(self, event: AstrMessageEvent, group_id: str, user_id: str) -> bool:
        """绕过缓存, 实时检查是否为管理员(用于敏感操作)"""
        admins = await self._fetch_admins(event, group_id)
        return user_id in admins

    def record_admin_message(self, group_id: str) -> None:
        """记录该群最近一次管理员发言时间"""
        self._last_admin_message_time[group_id] = datetime.now()

    def get_last_admin_time(self, group_id: str) -> datetime | None:
        """获取该群最近一次管理员发言时间, 无记录返回 None"""
        return self._last_admin_message_time.get(group_id)

    def clear_cache(self, group_id: str | None = None) -> None:
        """清除管理员缓存; 不传 group_id 则清除全部"""
        if group_id is None:
            self._admin_cache.clear()
        else:
            self._admin_cache.pop(group_id, None)
