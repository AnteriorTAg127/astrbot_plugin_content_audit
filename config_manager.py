from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from astrbot.api import logger

if TYPE_CHECKING:
    from .stats_manager import StatsManager


class ConfigManager:
    """从 _conf_schema.json 定义的配置项中读取和管理配置"""

    @staticmethod
    def _safe_copy_config(config: dict) -> dict:
        """安全地深度复制配置字典。

        copy.deepcopy 可能因框架配置中含不支持深复制的对象而失败，
        此方法手动递归复制 dict/list，其他类型直接引用（配置中不会有可变对象）。
        """
        result: dict = {}
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = ConfigManager._safe_copy_config(value)
            elif isinstance(value, list):
                result[key] = [ConfigManager._safe_copy_config(v) if isinstance(v, dict) else v for v in value]
            else:
                result[key] = value
        return result

    def __init__(
        self,
        config_getter: Callable[[], dict],
        stats_manager: StatsManager,
        on_reload: Callable[[dict], None] | None = None,
    ):
        self._config_getter = config_getter
        self._stats_manager = stats_manager
        self._on_reload = on_reload
        self.config = self._config_getter()
        # _config_snapshot: 用于检测配置变更的深拷贝锚点
        # maybe_reload() 将当前配置与此快照比较，而非与 self.config 比较
        # （因为 _config_getter 和 self.config 指向同一 dict 对象）
        self._config_snapshot = self._safe_copy_config(self.config)
        # 将 group_settings 解析为以 group_id 为键的字典，方便快速查找
        self._group_configs: dict[str, dict] = {}
        self._config_version: int = 0
        self._whitelist_cache: set[str] | None = None
        self._whitelist_cache_time: float = 0.0
        self._whitelist_cache_ttl: int = 60
        self._parse_group_settings()
        logger.info("ConfigManager 初始化完成")

    def _parse_group_settings(self):
        group_settings: list[dict] = self.config.get("group_settings", [])
        seen: set[str] = set()
        for gs in group_settings:
            group_id = gs.get("group_id", "")
            if not group_id:
                continue
            if group_id in seen:
                logger.warning(f"group_settings 中存在重复的 group_id={group_id}, 后出现的条目将覆盖先前的配置")
            seen.add(group_id)
            config_copy = dict(gs)
            config_copy.setdefault("group_name", "")
            schedule_str = config_copy.get("auto_censor_schedule", "")
            config_copy["schedule_parsed"] = self._parse_schedule(schedule_str)
            self._group_configs[group_id] = config_copy

    def _parse_schedule(self, schedule_str: str) -> tuple[int, int, int, int] | None:
        """将 "hh:mm-hh:mm" 格式字符串解析为 (start_h, start_m, end_h, end_m) 元组"""
        if not schedule_str:
            return None
        try:
            parts = schedule_str.strip().split("-")
            if len(parts) != 2:
                return None
            start_str, end_str = parts[0].strip(), parts[1].strip()
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            return (sh, sm, eh, em)
        except (ValueError, AttributeError, IndexError):
            logger.warning(f"无法解析 schedule 字符串: {schedule_str}")
            return None

    def _is_in_schedule(self, schedule: tuple[int, int, int, int]) -> bool:
        """判断当前时间是否在给定时间段内，支持跨午夜时间段"""
        sh, sm, eh, em = schedule
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        start_minutes = sh * 60 + sm
        end_minutes = eh * 60 + em

        if start_minutes <= end_minutes:
            # 普通时间段，如 09:00-18:00
            return start_minutes <= current_minutes < end_minutes
        else:
            # 跨午夜时间段，如 23:00-09:00
            return current_minutes >= start_minutes or current_minutes < end_minutes

    def is_group_enabled(self, group_id: str) -> bool:
        """检查指定 group_id 是否在 group_settings 中且 enabled 为 true"""
        config = self._group_configs.get(group_id)
        if config is None:
            return False
        return config.get("enabled", False)

    def is_manage_group(self, group_id: str) -> bool:
        """检查 group_id 是否作为任意群组配置的 manage_group_id 出现"""
        return any(config.get("manage_group_id", "") == group_id for config in self._group_configs.values())

    def get_group_config(self, group_id: str) -> dict | None:
        """返回指定 group_id 的完整配置字典，包含已解析的 schedule"""
        return self._group_configs.get(group_id)

    def get_manage_group_id(self, group_id: str) -> str | None:
        """给定被管理群 ID，返回其关联的管理群 ID"""
        config = self._group_configs.get(group_id)
        if config is None:
            return None
        mg_id = config.get("manage_group_id", "")
        return mg_id if mg_id else None

    def get_managed_group_ids(self, manage_group_id: str) -> list[str]:
        """反向查找：给定管理群 ID，返回所有将其设为 manage_group_id 的群 ID 列表"""
        result: list[str] = []
        for group_id, config in self._group_configs.items():
            if config.get("manage_group_id", "") == manage_group_id:
                result.append(group_id)
        return result

    def get_group_display_list(self) -> list[dict]:
        """返回所有已配置被管理群的显示列表，用于 Dashboard 下拉框

        Returns:
            每个元素为 {"group_id": ..., "group_name": ...}，group_name 可为空
        """
        result: list[dict] = []
        for group_id, config in self._group_configs.items():
            if group_id:
                result.append(
                    {
                        "group_id": group_id,
                        "group_name": config.get("group_name", ""),
                    }
                )
        return result

    async def is_whitelisted(self, user_id: str, group_id: str = "") -> bool:
        """检查用户是否在白名单中（全局或指定群）

        Args:
            user_id: 用户 QQ 号
            group_id: 群号（空=仅检查全局白名单）；传入具体群号时同时检查全局和群级

        Returns:
            True 表示在白名单中
        """
        whitelist = self.config.get("whitelist", {})
        if not whitelist.get("enabled", False):
            return False
        # 刷新全局缓存
        now = asyncio.get_event_loop().time()
        if self._whitelist_cache is None or now - self._whitelist_cache_time > self._whitelist_cache_ttl:
            users = await self._stats_manager.get_whitelist()
            if users is not None:
                self._whitelist_cache = set(users)
                self._whitelist_cache_time = now
        # 全局缓存快速路径
        if user_id in (self._whitelist_cache or set()):
            return True
        # 群级检查委托 stats_manager（同时检查全局 OR 群级）
        if group_id:
            return await self._stats_manager.is_whitelisted(user_id, group_id)
        return False

    def invalidate_whitelist_cache(self) -> None:
        self._whitelist_cache = None

    def should_enable_censor(self, group_id: str, last_admin_time: datetime | None = None) -> tuple[bool, str]:
        """三层决策判断是否启用审查，返回 (是否审查, 决策原因)

        决策树：
        1. enable_auto_censor == false → 全量审查模式
        2. 当前时间在 auto_censor_schedule 内 → 智能审查-强制时间段
        3. auto_censor_no_admin_minutes 为 0 或未设置 → 智能审查-非强制时间段
        4. last_admin_time 为 None → 智能审查-管理不在线(无记录)
        5. 已超时 → 智能审查-管理不在线
        6. 其他 → 智能审查-管理在线
        """
        config = self.get_group_config(group_id)
        if config is None:
            return (False, "未配置")

        # 第一层：未启用智能审查 → 全量审查
        # 走 get_effective_config 以应用 _coerce_type，避免字符串配置导致语义反转
        enable_auto_censor = self.get_effective_config(group_id, "enable_auto_censor", False)
        if not enable_auto_censor:
            return (True, "全量审查模式")

        # 第二层：当前时间在强制审查时间段内
        schedule_parsed = config.get("schedule_parsed")
        if schedule_parsed is not None and self._is_in_schedule(schedule_parsed):
            return (True, "智能审查-强制时间段")

        # 第三层：管理员在线检测
        no_admin_minutes = self.get_effective_config(group_id, "auto_censor_no_admin_minutes", 0)
        if no_admin_minutes == 0:
            return (True, "智能审查-非强制时间段")

        if last_admin_time is None:
            return (True, "智能审查-管理不在线(无记录)")

        elapsed = (datetime.now() - last_admin_time).total_seconds() / 60.0
        if elapsed >= no_admin_minutes:
            return (True, "智能审查-管理不在线")

        return (False, "智能审查-管理在线")

    def _notify_reload(self) -> None:
        """通知外部模块配置已重载"""
        if self._on_reload is not None:
            try:
                self._on_reload(self.config)
            except Exception:
                logger.exception("配置重载回调执行异常")

    def reload(self) -> None:
        self.config = self._config_getter()
        self._config_snapshot = self._safe_copy_config(self.config)
        self._group_configs.clear()
        self._parse_group_settings()
        self._config_version += 1
        logger.info(f"配置已重新加载 (version={self._config_version})")
        self._notify_reload()

    def maybe_reload(self) -> bool:
        new_config = self._config_getter()
        tracked_sections = ["api", "audit", "action", "notify", "whitelist", "group_settings"]
        for section in tracked_sections:
            if new_config.get(section) != self._config_snapshot.get(section):
                # 先建立新快照，成功后再替换 config，避免 _safe_copy_config 异常时
                # self.config 已指向新配置而 _config_snapshot 仍为旧值的不一致状态
                new_snapshot = self._safe_copy_config(new_config)
                self.config = new_config
                self._config_snapshot = new_snapshot
                self._group_configs.clear()
                self._parse_group_settings()
                self._config_version += 1
                logger.info(f"检测到配置变更({section})，已自动重载 (version={self._config_version})")
                self._notify_reload()
                return True
        return False

    # 群级直读配置的默认值（不再依赖全局 section 回退）
    _DEFAULTS: ClassVar[dict[str, object]] = {
        "skip_admin": True,
        "skip_llm": False,
        "min_text_length": 2,
        "auto_recall": True,
        "auto_mute": True,
        "context_enabled": True,
        "context_max_messages": 5,
    }

    # 配置项类型期望（用于防御性类型强制转换）
    _TYPE_MAP: ClassVar[dict[str, type]] = {
        "skip_admin": bool,
        "skip_llm": bool,
        "min_text_length": int,
        "auto_recall": bool,
        "auto_mute": bool,
        "context_enabled": bool,
        "context_max_messages": int,
        "enable_auto_censor": bool,
        "auto_censor_no_admin_minutes": int,
    }

    def _coerce_type(self, key: str, value: object, default: object = None) -> object:
        """将配置值强制转换为期望类型，失败时使用默认值"""
        expected = self._TYPE_MAP.get(key)
        if expected is None or value is None:
            return value
        if expected is bool:
            # bool 是 int 的子类，需优先处理
            if isinstance(value, str):
                return value.lower() not in ("0", "false", "no", "")
            return bool(value)
        if isinstance(value, expected):
            # bool 是 int 子类：对 int 期望需把 bool 转为真正的 int，避免类型不纯
            if expected is int and isinstance(value, bool):
                return int(value)
            return value
        try:
            return expected(value)
        except (ValueError, TypeError):
            logger.warning(f"配置项 {key} 类型错误: {value!r} (期望 {expected.__name__})，使用默认值")
            if key in self._DEFAULTS:
                return self._DEFAULTS[key]
            return default

    def get_effective_config(self, group_id: str, key: str, default=None):
        """从群设置中读取配置值。

        查找顺序（兼容旧版 override_* 键）：
        1. group_config[key] 直接命中（新版扁平字段）
        2. override_{key}（旧版兼容，仅当扁平字段不存在时）
        3. 内置默认值
        4. 调用方传入的 default
        """
        group_config = self._group_configs.get(group_id, {})
        raw = None
        if key in group_config and group_config[key] is not None:
            raw = group_config[key]
        if raw is None:
            override_key = f"override_{key}"
            if override_key in group_config and group_config[override_key] is not None:
                raw = group_config[override_key]
        if raw is None and key in self._DEFAULTS:
            raw = self._DEFAULTS[key]
        if raw is not None:
            return self._coerce_type(key, raw, default)
        return default
