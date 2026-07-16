"""Dashboard Pages 后端 API for astrbot_plugin_content_audit.

提供 5 类资源的 REST API：
- 概览统计 (stats/overview)
- 违规记录 (violations)
- 审计日志 (audits)
- 白名单 (whitelist)
- 用户档案 (users)

所有路由通过 ``context.register_web_api`` 挂到 AstrBot Dashboard 上，
鉴权由 AstrBot 全局 ``before_request`` 中间件统一处理，本模块不写鉴权逻辑。
响应格式统一为 ``{"code": 0|1, "data": ..., "msg": "..."}``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from quart import jsonify, request

if TYPE_CHECKING:
    from astrbot.api.star import Context

    from .config_manager import ConfigManager
    from .stats_manager import StatsManager


PLUGIN_NAME = "astrbot_plugin_content_audit"

# page_size 上限，防止前端意外打满数据库
_MAX_PAGE_SIZE = 100


def _ok(data: Any = None) -> Any:
    """成功响应。"""
    return jsonify({"code": 0, "data": data, "msg": "ok"})


def _fail(msg: str, code: int = 1, http_status: int = 400) -> Any:
    """失败响应。"""
    return jsonify({"code": code, "data": None, "msg": msg}), http_status


def _current_user() -> str:
    """读取当前登录用户名（用于留痕日志）。"""
    try:
        from quart import g

        user = getattr(g, "username", None)
        if user:
            return str(user)
    except Exception:
        pass
    return "unknown"


def _parse_int(value: Any, default: int) -> int:
    """容错解析整数，失败回退 default。"""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_page(args: Any) -> tuple[int, int]:
    """从 query string 提取 page / page_size，做边界限定。"""
    page = max(1, _parse_int(args.get("page"), 1))
    page_size = _parse_int(args.get("page_size"), 20)
    page_size = max(1, min(_MAX_PAGE_SIZE, page_size))
    return page, page_size


class WebApiHandler:
    """REST API for content_audit Dashboard page."""

    def __init__(
        self,
        stats_manager: StatsManager,
        config_manager: ConfigManager,
    ) -> None:
        self._stats = stats_manager
        self._config = config_manager
        self._context: Context | None = None

    # ------------------------------------------------------------------ #
    # 注册
    # ------------------------------------------------------------------ #

    def register(self, context: Context, plugin_name: str = PLUGIN_NAME) -> None:
        """把所有路由挂到 AstrBot Dashboard 上。"""
        self._context = context
        prefix = f"/{plugin_name}"
        routes: list[tuple[str, Any, list[str], str]] = [
            # 概览
            (f"{prefix}/stats/overview", self.api_stats_overview, ["GET"], "审核概览"),
            # 群列表
            (f"{prefix}/groups", self.api_groups_list, ["GET"], "群列表(含群名)"),
            # 违规记录
            (f"{prefix}/violations", self.api_violations_list, ["GET"], "违规列表"),
            (
                f"{prefix}/violations/batch_delete",
                self.api_violations_batch_delete,
                ["POST"],
                "批量删除违规",
            ),
            (f"{prefix}/violations/<vid>", self.api_violations_get, ["GET"], "违规详情"),
            (f"{prefix}/violations/<vid>/update", self.api_violations_update, ["POST"], "编辑违规"),
            (f"{prefix}/violations/<vid>/delete", self.api_violations_delete, ["POST"], "删除违规"),
            # 审计日志
            (f"{prefix}/audits", self.api_audits_list, ["GET"], "审计列表"),
            (
                f"{prefix}/audits/batch_delete",
                self.api_audits_batch_delete,
                ["POST"],
                "批量删除审计",
            ),
            (f"{prefix}/audits/<aid>", self.api_audits_get, ["GET"], "审计详情"),
            (f"{prefix}/audits/<aid>/delete", self.api_audits_delete, ["POST"], "删除审计"),
            # 白名单
            (f"{prefix}/whitelist", self.api_whitelist_list, ["GET"], "白名单列表"),
            (f"{prefix}/whitelist", self.api_whitelist_create, ["POST"], "添加白名单"),
            (f"{prefix}/whitelist/<wid>/update", self.api_whitelist_update, ["POST"], "更新白名单备注"),
            (f"{prefix}/whitelist/<wid>/delete", self.api_whitelist_delete, ["POST"], "删除白名单"),
            # 用户档案
            (f"{prefix}/users", self.api_users_list, ["GET"], "用户档案列表"),
            (f"{prefix}/users", self.api_users_create, ["POST"], "新增用户档案"),
            (f"{prefix}/users/<user_id>", self.api_users_get, ["GET"], "用户档案详情"),
            (f"{prefix}/users/<user_id>/update", self.api_users_update, ["POST"], "编辑用户档案"),
            (f"{prefix}/users/<user_id>/delete", self.api_users_delete, ["POST"], "删除用户档案"),
        ]
        ok_cnt = 0
        for route, handler, methods, desc in routes:
            try:
                context.register_web_api(route, handler, methods, desc)
                ok_cnt += 1
            except Exception:
                logger.exception(f"[web_api] register failed: {route}")
        logger.info(f"[web_api] {ok_cnt}/{len(routes)} routes registered under {prefix}")

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _id_or_400(raw: str) -> tuple[int | None, Any]:
        """路径参数 -> int；失败时返回错误响应。"""
        try:
            return int(raw), None
        except (TypeError, ValueError):
            return None, _fail("invalid id", 1, 400)

    @staticmethod
    async def _json_body() -> tuple[dict | None, Any]:
        """读取 JSON body；失败时返回错误响应。"""
        body = await request.get_json(silent=True)
        if not isinstance(body, dict):
            return None, _fail("missing or invalid json body", 1, 400)
        return body, None

    # ------------------------------------------------------------------ #
    # 群列表
    # ------------------------------------------------------------------ #

    async def api_groups_list(self) -> Any:
        """GET /groups 返回 [{group_id, group_name}]，群名按 别名->平台->群号 解析。"""
        try:
            configured = self._config.get_group_display_list()  # [{group_id, group_name(alias)}]
            # 平台群名映射
            platform_names: dict[str, str] = {}
            try:
                if self._context is not None:
                    from astrbot.api.platform import PlatformAdapterType

                    platform = self._context.get_platform(PlatformAdapterType.AIOCQHTTP)
                    if platform is not None:
                        bot = platform.get_client()
                        if bot is not None:
                            raw = await bot.call_action(action="get_group_list")
                            for g in raw or []:
                                gid = str(g.get("group_id", ""))
                                gname = g.get("group_name", "") or ""
                                if gid:
                                    platform_names[gid] = gname
            except Exception:
                logger.debug("[web_api] get_group_list failed, fallback to alias/group_id")
            result: list[dict] = []
            for item in configured:
                gid = item.get("group_id", "")
                alias = item.get("group_name", "") or ""
                name = alias or platform_names.get(gid, "") or gid
                result.append({"group_id": gid, "group_name": name})
            return _ok(result)
        except Exception:
            logger.exception("[web_api] api_groups_list failed")
            return _fail("internal error", 1, 500)

    # ------------------------------------------------------------------ #
    # 概览
    # ------------------------------------------------------------------ #

    async def api_stats_overview(self) -> Any:
        """GET /stats/overview"""
        try:
            data = await self._stats.get_overview_stats()
            return _ok(data)
        except Exception:
            logger.exception("[web_api] api_stats_overview failed")
            return _fail("internal error", 1, 500)

    # ------------------------------------------------------------------ #
    # 违规记录
    # ------------------------------------------------------------------ #

    async def api_violations_list(self) -> Any:
        """GET /violations?page=&page_size=&group_id=&user_id=&keyword=&sort_by=&sort_dir=&date_from=&date_to="""
        try:
            page, page_size = _parse_page(request.args)
            group_id = request.args.get("group_id") or None
            user_id = request.args.get("user_id") or None
            keyword = request.args.get("keyword") or None
            sort_by = request.args.get("sort_by") or None
            sort_dir = request.args.get("sort_dir") or None
            date_from = request.args.get("date_from") or None
            date_to = request.args.get("date_to") or None
            items, total = await self._stats.list_violations(
                page=page,
                page_size=page_size,
                group_id=group_id,
                user_id=user_id,
                keyword=keyword,
                sort_by=sort_by,
                sort_dir=sort_dir,
                date_from=date_from,
                date_to=date_to,
            )
            return _ok(
                {
                    "items": items,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
            )
        except Exception:
            logger.exception("[web_api] api_violations_list failed")
            return _fail("internal error", 1, 500)

    async def api_violations_get(self, vid: str) -> Any:
        """GET /violations/<vid>"""
        try:
            vid_int, err = self._id_or_400(vid)
            if err is not None:
                return err
            row = await self._stats.get_violation(vid_int)
            if row is None:
                return _fail("not found", 1, 404)
            return _ok(row)
        except Exception:
            logger.exception("[web_api] api_violations_get failed")
            return _fail("internal error", 1, 500)

    async def api_violations_update(self, vid: str) -> Any:
        """POST /violations/<vid>/update"""
        try:
            vid_int, err = self._id_or_400(vid)
            if err is not None:
                return err
            body, err = await self._json_body()
            if err is not None:
                return err
            # 只允许修改这三个字段
            allowed = {"user_name", "text_preview", "note"}
            fields = {k: v for k, v in body.items() if k in allowed}
            if not fields:
                return _fail("no editable fields provided", 1, 400)
            ok = await self._stats.update_violation(vid_int, fields)
            if not ok:
                return _fail("not found or update failed", 1, 404)
            logger.info(f"[web_api] update_violation by {_current_user()}: id={vid_int} fields={list(fields)}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_violations_update failed")
            return _fail("internal error", 1, 500)

    async def api_violations_delete(self, vid: str) -> Any:
        """POST /violations/<vid>/delete"""
        try:
            vid_int, err = self._id_or_400(vid)
            if err is not None:
                return err
            ok = await self._stats.delete_violation(vid_int)
            if not ok:
                return _fail("not found", 1, 404)
            logger.info(f"[web_api] delete_violation by {_current_user()}: id={vid_int}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_violations_delete failed")
            return _fail("internal error", 1, 500)

    async def api_violations_batch_delete(self) -> Any:
        """POST /violations/batch_delete  body: {ids:[...]}"""
        try:
            body, err = await self._json_body()
            if err is not None:
                return err
            ids_raw = body.get("ids") or []
            if not isinstance(ids_raw, list):
                return _fail("ids must be a list", 1, 400)
            ids: list[int] = []
            for x in ids_raw:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    continue
            if not ids:
                return _fail("no valid ids", 1, 400)
            deleted = await self._stats.delete_violations_batch(ids)
            logger.info(f"[web_api] batch_delete_violations by {_current_user()}: req={len(ids)} deleted={deleted}")
            return _ok({"deleted": deleted})
        except Exception:
            logger.exception("[web_api] api_violations_batch_delete failed")
            return _fail("internal error", 1, 500)

    # ------------------------------------------------------------------ #
    # 审计日志
    # ------------------------------------------------------------------ #

    async def api_audits_list(self) -> Any:
        """GET /audits?page=&page_size=&group_id=&has_violation=&keyword=&sort_by=&sort_dir=&date_from=&date_to="""
        try:
            page, page_size = _parse_page(request.args)
            group_id = request.args.get("group_id") or None
            keyword = request.args.get("keyword") or None
            hv_raw = request.args.get("has_violation")
            has_violation: int | None
            if hv_raw in (None, "", "all"):
                has_violation = None
            elif hv_raw in ("1", "true", "yes"):
                has_violation = 1
            elif hv_raw in ("0", "false", "no"):
                has_violation = 0
            else:
                has_violation = None
            sort_by = request.args.get("sort_by") or None
            sort_dir = request.args.get("sort_dir") or None
            date_from = request.args.get("date_from") or None
            date_to = request.args.get("date_to") or None
            items, total = await self._stats.list_audits(
                page=page,
                page_size=page_size,
                group_id=group_id,
                has_violation=has_violation,
                keyword=keyword,
                sort_by=sort_by,
                sort_dir=sort_dir,
                date_from=date_from,
                date_to=date_to,
            )
            return _ok(
                {
                    "items": items,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
            )
        except Exception:
            logger.exception("[web_api] api_audits_list failed")
            return _fail("internal error", 1, 500)

    async def api_audits_get(self, aid: str) -> Any:
        """GET /audits/<aid>"""
        try:
            aid_int, err = self._id_or_400(aid)
            if err is not None:
                return err
            row = await self._stats.get_audit(aid_int)
            if row is None:
                return _fail("not found", 1, 404)
            return _ok(row)
        except Exception:
            logger.exception("[web_api] api_audits_get failed")
            return _fail("internal error", 1, 500)

    async def api_audits_delete(self, aid: str) -> Any:
        """POST /audits/<aid>/delete"""
        try:
            aid_int, err = self._id_or_400(aid)
            if err is not None:
                return err
            ok = await self._stats.delete_audit(aid_int)
            if not ok:
                return _fail("not found", 1, 404)
            logger.info(f"[web_api] delete_audit by {_current_user()}: id={aid_int}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_audits_delete failed")
            return _fail("internal error", 1, 500)

    async def api_audits_batch_delete(self) -> Any:
        """POST /audits/batch_delete  body: {ids:[...]}"""
        try:
            body, err = await self._json_body()
            if err is not None:
                return err
            ids_raw = body.get("ids") or []
            if not isinstance(ids_raw, list):
                return _fail("ids must be a list", 1, 400)
            ids: list[int] = []
            for x in ids_raw:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    continue
            if not ids:
                return _fail("no valid ids", 1, 400)
            deleted = await self._stats.delete_audits_batch(ids)
            logger.info(f"[web_api] batch_delete_audits by {_current_user()}: req={len(ids)} deleted={deleted}")
            return _ok({"deleted": deleted})
        except Exception:
            logger.exception("[web_api] api_audits_batch_delete failed")
            return _fail("internal error", 1, 500)

    # ------------------------------------------------------------------ #
    # 白名单
    # ------------------------------------------------------------------ #

    async def api_whitelist_list(self) -> Any:
        """GET /whitelist?group_id=&sort_by=&sort_dir="""
        try:
            group_id = request.args.get("group_id") or None
            sort_by = request.args.get("sort_by") or None
            sort_dir = request.args.get("sort_dir") or None
            # group_id 映射为 group_id_filter
            group_id_filter: str | None
            if group_id in (None, "", "all"):
                group_id_filter = None
            elif group_id == "global":
                group_id_filter = "global"
            else:
                group_id_filter = group_id
            items = await self._stats.list_whitelist_detailed(
                group_id_filter=group_id_filter,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
            return _ok({"items": items, "total": len(items)})
        except Exception:
            logger.exception("[web_api] api_whitelist_list failed")
            return _fail("internal error", 1, 500)

    async def api_whitelist_create(self) -> Any:
        """POST /whitelist  body: {user_id, note?, group_id?}"""
        try:
            body, err = await self._json_body()
            if err is not None:
                return err
            user_id = str(body.get("user_id") or "").strip()
            note = str(body.get("note") or "")
            group_id = str(body.get("group_id") or "")
            if not user_id:
                return _fail("user_id is required", 1, 400)
            ok = await self._stats.add_whitelist_with_note(user_id, note, group_id)
            if ok is None:
                return _fail("user already in whitelist or insert failed", 1, 409)
            self._config.invalidate_whitelist_cache()
            logger.info(f"[web_api] add_whitelist by {_current_user()}: user_id={user_id} group_id={group_id}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_whitelist_create failed")
            return _fail("internal error", 1, 500)

    async def api_whitelist_update(self, wid: str) -> Any:
        """POST /whitelist/<wid>/update  body: {note}"""
        try:
            wid_int, err = self._id_or_400(wid)
            if err is not None:
                return err
            body, err = await self._json_body()
            if err is not None:
                return err
            if "note" not in body:
                return _fail("note is required", 1, 400)
            note = str(body.get("note") or "")
            ok = await self._stats.update_whitelist_note(wid_int, note)
            if not ok:
                return _fail("not found", 1, 404)
            logger.info(f"[web_api] update_whitelist by {_current_user()}: id={wid_int}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_whitelist_update failed")
            return _fail("internal error", 1, 500)

    async def api_whitelist_delete(self, wid: str) -> Any:
        """POST /whitelist/<wid>/delete"""
        try:
            wid_int, err = self._id_or_400(wid)
            if err is not None:
                return err
            ok = await self._stats.delete_whitelist_by_id(wid_int)
            if not ok:
                return _fail("not found", 1, 404)
            self._config.invalidate_whitelist_cache()
            logger.info(f"[web_api] delete_whitelist by {_current_user()}: id={wid_int}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_whitelist_delete failed")
            return _fail("internal error", 1, 500)

    # ------------------------------------------------------------------ #
    # 用户档案
    # ------------------------------------------------------------------ #

    async def api_users_list(self) -> Any:
        """GET /users?page=&page_size=&keyword=&status=&sort_by=&sort_dir=..."""
        try:
            page, page_size = _parse_page(request.args)
            keyword = request.args.get("keyword") or None
            status = request.args.get("status") or None
            if status in ("", "all"):
                status = None
            sort_by = request.args.get("sort_by") or None
            sort_dir = request.args.get("sort_dir") or None
            first_seen_from = request.args.get("first_seen_from") or None
            first_seen_to = request.args.get("first_seen_to") or None
            last_seen_from = request.args.get("last_seen_from") or None
            last_seen_to = request.args.get("last_seen_to") or None
            groups_raw = request.args.get("groups") or None
            groups: list[str] | None = None
            if groups_raw:
                groups = [g.strip() for g in groups_raw.split(",") if g.strip()]
            items, total = await self._stats.list_user_profiles(
                page=page,
                page_size=page_size,
                keyword=keyword,
                status=status,
                sort_by=sort_by,
                sort_dir=sort_dir,
                first_seen_from=first_seen_from,
                first_seen_to=first_seen_to,
                last_seen_from=last_seen_from,
                last_seen_to=last_seen_to,
                groups=groups,
            )
            return _ok(
                {
                    "items": items,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
            )
        except Exception:
            logger.exception("[web_api] api_users_list failed")
            return _fail("internal error", 1, 500)

    async def api_users_get(self, user_id: str) -> Any:
        """GET /users/<user_id>"""
        try:
            user_id = str(user_id or "").strip()
            if not user_id:
                return _fail("invalid user_id", 1, 400)
            row = await self._stats.get_user_profile(user_id)
            if row is None:
                return _fail("not found", 1, 404)
            return _ok(row)
        except Exception:
            logger.exception("[web_api] api_users_get failed")
            return _fail("internal error", 1, 500)

    async def api_users_create(self) -> Any:
        """POST /users  body: {user_id, nickname?, note?, status?, group_ids?}"""
        try:
            body, err = await self._json_body()
            if err is not None:
                return err
            user_id = str(body.get("user_id") or "").strip()
            if not user_id:
                return _fail("user_id is required", 1, 400)
            data = {
                "user_id": user_id,
                "nickname": str(body.get("nickname") or ""),
                "note": str(body.get("note") or ""),
                "status": str(body.get("status") or "normal"),
                "group_ids": body.get("group_ids") or [],
            }
            ok = await self._stats.create_user_profile(data)
            if not ok:
                return _fail("user already exists or insert failed", 1, 409)
            logger.info(f"[web_api] create_user_profile by {_current_user()}: user_id={user_id}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_users_create failed")
            return _fail("internal error", 1, 500)

    async def api_users_update(self, user_id: str) -> Any:
        """POST /users/<user_id>/update  body: {nickname?, note?, status?, group_ids?}"""
        try:
            user_id = str(user_id or "").strip()
            if not user_id:
                return _fail("invalid user_id", 1, 400)
            body, err = await self._json_body()
            if err is not None:
                return err
            allowed = {"nickname", "note", "status", "group_ids"}
            fields = {k: v for k, v in body.items() if k in allowed}
            if not fields:
                return _fail("no editable fields provided", 1, 400)
            ok = await self._stats.update_user_profile(user_id, fields)
            if not ok:
                return _fail("not found or update failed", 1, 404)
            logger.info(f"[web_api] update_user_profile by {_current_user()}: user_id={user_id} fields={list(fields)}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_users_update failed")
            return _fail("internal error", 1, 500)

    async def api_users_delete(self, user_id: str) -> Any:
        """POST /users/<user_id>/delete"""
        try:
            user_id = str(user_id or "").strip()
            if not user_id:
                return _fail("invalid user_id", 1, 400)
            ok = await self._stats.delete_user_profile(user_id)
            if not ok:
                return _fail("not found", 1, 404)
            logger.info(f"[web_api] delete_user_profile by {_current_user()}: user_id={user_id}")
            return _ok(None)
        except Exception:
            logger.exception("[web_api] api_users_delete failed")
            return _fail("internal error", 1, 500)
