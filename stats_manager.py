import json
import os
from datetime import date, datetime, timedelta
from typing import Any

import aiosqlite
from astrbot.api import logger

# field allowlist - block out-of-band writes
_VIOLATION_UPDATABLE_FIELDS = {"user_name", "text_preview", "note"}
_USER_PROFILE_UPDATABLE_FIELDS = {"nickname", "note", "status", "group_ids"}


def _escape_like(keyword: str) -> str:
    """转义 LIKE 模式中的转义符 ``\\`` 及通配符 ``%`` / ``_``，配合 ``ESCAPE '\\'`` 使用。"""
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class StatsManager:
    def __init__(self, data_dir: str) -> None:
        self._db_path = os.path.join(data_dir, "content_audit.db")
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def _ensure_column(self, table: str, column: str, type_def: str) -> None:
        """Idempotent migration: ALTER ADD if `table` lacks `column`."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(f"PRAGMA table_info({table})")
            rows = await cursor.fetchall()
            cols = {row["name"] for row in rows}
            if column not in cols:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_def}")
                await conn.commit()
                logger.info(f"[stats_manager] migrated: ADD COLUMN {table}.{column}")
        except Exception as e:
            logger.error(f"_ensure_column({table}.{column}) failed: {e}")

    async def init_db(self) -> None:
        conn = await self._get_conn()
        try:
            await conn.executescript("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    text_preview TEXT,
                    has_violation INTEGER,
                    source TEXT,
                    request_id TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS violation_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    text_preview TEXT,
                    request_id TEXT,
                    action_recall INTEGER,
                    action_mute INTEGER,
                    mute_duration INTEGER,
                    violation_count INTEGER,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS whitelist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    nickname TEXT DEFAULT '',
                    group_ids TEXT DEFAULT '[]',
                    note TEXT DEFAULT '',
                    status TEXT DEFAULT 'normal',
                    violation_count INTEGER DEFAULT 0,
                    first_seen_at TEXT,
                    last_seen_at TEXT,
                    updated_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_user_profiles_status
                    ON user_profiles(status);
                CREATE INDEX IF NOT EXISTS idx_user_profiles_violation_count
                    ON user_profiles(violation_count);
            """)
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to init database: {e}")

        # idempotent migration: v1 legacy whitelist/violation_records add note column
        await self._ensure_column("whitelist", "note", "TEXT DEFAULT ''")
        await self._ensure_column("violation_records", "note", "TEXT DEFAULT ''")

    async def record_audit(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        text_preview: str,
        has_violation: int,
        source: str,
        request_id: str,
    ) -> None:
        conn = await self._get_conn()
        try:
            await conn.execute(
                """INSERT INTO audit_log
                   (group_id, user_id, user_name, text_preview,
                    has_violation, source, request_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    group_id,
                    user_id,
                    user_name,
                    text_preview,
                    has_violation,
                    source,
                    request_id,
                    datetime.now().isoformat(),
                ),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to record audit: {e}")
            # 回滚以解除事务 abort 状态，使后续 upsert 能在干净连接上执行
            try:
                await conn.rollback()
            except Exception:
                pass

        try:
            await self.upsert_user_profile(user_id, user_name, group_id)
        except Exception as e:
            logger.error(f"upsert_user_profile failed: {e}")

    async def record_violation(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        text_preview: str,
        request_id: str,
        action_recall: int,
        action_mute: int,
        mute_duration: int,
    ) -> None:
        conn = await self._get_conn()
        inserted = False
        try:
            await conn.execute(
                """INSERT INTO violation_records
                   (group_id, user_id, user_name, text_preview,
                    request_id, action_recall, action_mute,
                    mute_duration, violation_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                       (SELECT COALESCE(COUNT(*), 0) + 1 FROM violation_records
                        WHERE user_id = ? AND group_id = ?), ?)""",
                (
                    group_id,
                    user_id,
                    user_name,
                    text_preview,
                    request_id,
                    action_recall,
                    action_mute,
                    mute_duration,
                    user_id,
                    group_id,  # for subquery
                    datetime.now().isoformat(),
                ),
            )
            await conn.commit()
            inserted = True
        except Exception as e:
            logger.error(f"Failed to record violation: {e}")
            try:
                await conn.rollback()
            except Exception:
                pass

        try:
            await self.upsert_user_profile(user_id, user_name, group_id)
            # 仅当违规记录实际写入后才递增计数，避免记录失败但计数虚增
            if inserted:
                await self.inc_user_violation_count(user_id)
        except Exception as e:
            logger.error(f"upsert/inc user profile failed: {e}")

    async def get_violation_count(self, user_id: str, group_id: str) -> int:
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                """SELECT COUNT(*) FROM violation_records
                   WHERE user_id = ? AND group_id = ?""",
                (user_id, group_id),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to get violation count: {e}")
            return 0

    async def get_violations(self, group_id: str | None = None, page: int = 1, page_size: int = 10) -> list[dict]:
        conn = await self._get_conn()
        try:
            if group_id is not None:
                cursor = await conn.execute(
                    """SELECT * FROM violation_records
                       WHERE group_id = ?
                       ORDER BY created_at DESC
                       LIMIT ? OFFSET ?""",
                    (group_id, page_size, (page - 1) * page_size),
                )
            else:
                cursor = await conn.execute(
                    """SELECT * FROM violation_records
                       ORDER BY created_at DESC
                       LIMIT ? OFFSET ?""",
                    (page_size, (page - 1) * page_size),
                )
            return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get violations: {e}")
            return []

    async def get_violations_multi_group(self, group_ids: list[str], page: int = 1, page_size: int = 10) -> list[dict]:
        conn = await self._get_conn()
        try:
            placeholders = ",".join("?" for _ in group_ids)
            cursor = await conn.execute(
                f"""SELECT * FROM violation_records
                   WHERE group_id IN ({placeholders})
                   ORDER BY created_at DESC
                   LIMIT ? OFFSET ?""",
                (*group_ids, page_size, (page - 1) * page_size),
            )
            return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get multi-group violations: {e}")
            return []

    async def delete_violations(self, user_id: str, group_ids: list[str]) -> None:
        if not group_ids:
            return
        conn = await self._get_conn()
        try:
            placeholders = ",".join("?" for _ in group_ids)
            await conn.execute(
                f"""DELETE FROM violation_records
                   WHERE user_id = ? AND group_id IN ({placeholders})""",
                (user_id, *group_ids),
            )
            # 重新计算并更新用户的违规计数
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM violation_records WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            remaining = row[0] if row else 0
            await conn.execute(
                "UPDATE user_profiles SET violation_count = ?, updated_at = ? WHERE user_id = ?",
                (remaining, datetime.now().isoformat(), user_id),
            )
            # 重算剩余 violation_records 的序号，避免删除后序号过时/重复
            await self._recalc_violation_records_seq(user_id)
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to delete violations: {e}")

    async def get_stats(self, group_id: str | None = None) -> dict:
        conn = await self._get_conn()
        try:
            today_str = date.today().isoformat()

            if group_id is not None:
                total_audits = (
                    await (
                        await conn.execute(
                            "SELECT COUNT(*) FROM audit_log WHERE group_id = ?",
                            (group_id,),
                        )
                    ).fetchone()
                )[0]
                total_violations = (
                    await (
                        await conn.execute(
                            "SELECT COUNT(*) FROM violation_records WHERE group_id = ?",
                            (group_id,),
                        )
                    ).fetchone()
                )[0]
                today_audits = (
                    await (
                        await conn.execute(
                            """SELECT COUNT(*) FROM audit_log
                       WHERE group_id = ? AND date(created_at) >= date(?)""",
                            (group_id, today_str),
                        )
                    ).fetchone()
                )[0]
                today_violations = (
                    await (
                        await conn.execute(
                            """SELECT COUNT(*) FROM violation_records
                       WHERE group_id = ? AND date(created_at) >= date(?)""",
                            (group_id, today_str),
                        )
                    ).fetchone()
                )[0]
            else:
                total_audits = (await (await conn.execute("SELECT COUNT(*) FROM audit_log")).fetchone())[0]
                total_violations = (await (await conn.execute("SELECT COUNT(*) FROM violation_records")).fetchone())[0]
                today_audits = (
                    await (
                        await conn.execute(
                            "SELECT COUNT(*) FROM audit_log WHERE date(created_at) >= date(?)",
                            (today_str,),
                        )
                    ).fetchone()
                )[0]
                today_violations = (
                    await (
                        await conn.execute(
                            "SELECT COUNT(*) FROM violation_records WHERE date(created_at) >= date(?)",
                            (today_str,),
                        )
                    ).fetchone()
                )[0]

            return {
                "total_audits": total_audits,
                "total_violations": total_violations,
                "today_audits": today_audits,
                "today_violations": today_violations,
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "total_audits": 0,
                "total_violations": 0,
                "today_audits": 0,
                "today_violations": 0,
            }

    async def add_whitelist(self, user_id: str) -> bool:
        conn = await self._get_conn()
        try:
            await conn.execute(
                "INSERT INTO whitelist (user_id, created_at) VALUES (?, ?)",
                (user_id, datetime.now().isoformat()),
            )
            await conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Failed to add whitelist: {e}")
            return False

    async def remove_whitelist(self, user_id: str) -> bool:
        conn = await self._get_conn()
        try:
            cursor = await conn.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to remove whitelist: {e}")
            return False

    async def get_whitelist(self) -> list[str] | None:
        conn = await self._get_conn()
        try:
            cursor = await conn.execute("SELECT user_id FROM whitelist")
            rows = await cursor.fetchall()
            return [row["user_id"] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get whitelist: {e}")
            return None

    async def cleanup_audit_log(self, keep_days: int = 30) -> int:
        conn = await self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
            cursor = await conn.execute("DELETE FROM audit_log WHERE created_at < ?", (cutoff,))
            await conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup audit log: {e}")
            return 0

    # ====================================================================
    # v2.0 new: user profile upsert / counter
    # ====================================================================

    async def upsert_user_profile(self, user_id: str, nickname: str, group_id: str) -> None:
        """Upsert a user_profiles row.

        - first time: INSERT, first_seen_at=now, last_seen_at=now,
          group_ids=[group_id]
        - existing: UPDATE nickname, last_seen_at=now, group_ids merge-dedup
        - violation_count is NOT touched here
        """
        conn = await self._get_conn()
        now_iso = datetime.now().isoformat()
        try:
            cursor = await conn.execute(
                "SELECT group_ids FROM user_profiles WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                group_ids_json = json.dumps([group_id], ensure_ascii=False)
                await conn.execute(
                    """INSERT INTO user_profiles
                       (user_id, nickname, group_ids, note, status,
                        violation_count, first_seen_at, last_seen_at, updated_at)
                       VALUES (?, ?, ?, '', 'normal', 0, ?, ?, ?)""",
                    (user_id, nickname, group_ids_json, now_iso, now_iso, now_iso),
                )
            else:
                try:
                    group_ids: list[str] = json.loads(row["group_ids"] or "[]")
                    if not isinstance(group_ids, list):
                        group_ids = []
                except Exception:
                    group_ids = []
                if group_id and group_id not in group_ids:
                    group_ids.append(group_id)
                group_ids_json = json.dumps(group_ids, ensure_ascii=False)
                await conn.execute(
                    """UPDATE user_profiles
                       SET nickname = ?, group_ids = ?,
                           last_seen_at = ?, updated_at = ?
                       WHERE user_id = ?""",
                    (nickname, group_ids_json, now_iso, now_iso, user_id),
                )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to upsert_user_profile({user_id}): {e}")

    async def inc_user_violation_count(self, user_id: str) -> None:
        """user_profiles.violation_count += 1."""
        conn = await self._get_conn()
        try:
            await conn.execute(
                """UPDATE user_profiles
                   SET violation_count = violation_count + 1,
                       updated_at = ?
                   WHERE user_id = ?""",
                (datetime.now().isoformat(), user_id),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to inc_user_violation_count({user_id}): {e}")

    async def _recalc_violation_records_seq(self, user_id: str) -> None:
        """重算该用户在各群的 violation_records.violation_count 序号（按 created_at 排序）。

        删除违规记录后，剩余行的序号会过时或与后续新插入行重复（新插入基于 COUNT+1），
        此方法按 (group_id, created_at) 重新连续编号。不提交，由调用方 commit。
        """
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "SELECT id, group_id FROM violation_records WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            counters: dict[str, int] = {}
            for row in rows:
                gid = row["group_id"]
                counters[gid] = counters.get(gid, 0) + 1
                await conn.execute(
                    "UPDATE violation_records SET violation_count = ? WHERE id = ?",
                    (counters[gid], row["id"]),
                )
        except Exception as e:
            logger.error(f"Failed to recalc violation_records seq for {user_id}: {e}")

    # ====================================================================
    # v2.0 new: violation records CRUD
    # ====================================================================

    async def list_violations(
        self,
        page: int = 1,
        page_size: int = 20,
        group_id: str | None = None,
        user_id: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated violation query; keyword LIKE-matches user_name or text_preview."""
        conn = await self._get_conn()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        clauses: list[str] = []
        params: list[Any] = []
        if group_id:
            clauses.append("group_id = ?")
            params.append(group_id)
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if keyword:
            escaped = _escape_like(keyword)
            clauses.append("(user_name LIKE ? ESCAPE '\\' OR text_preview LIKE ? ESCAPE '\\')")
            like = f"%{escaped}%"
            params.extend([like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            count_cursor = await conn.execute(
                f"SELECT COUNT(*) FROM violation_records {where}",
                params,
            )
            total_row = await count_cursor.fetchone()
            total = total_row[0] if total_row else 0

            data_cursor = await conn.execute(
                f"""SELECT * FROM violation_records {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                [*params, page_size, (page - 1) * page_size],
            )
            rows = [dict(r) for r in await data_cursor.fetchall()]
            return rows, total
        except Exception as e:
            logger.error(f"Failed to list_violations: {e}")
            return [], 0

    async def get_violation(self, vid: int) -> dict | None:
        """Fetch a single violation row by id."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "SELECT * FROM violation_records WHERE id = ?",
                (vid,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get_violation({vid}): {e}")
            return None

    async def update_violation(self, vid: int, fields: dict) -> bool:
        """Only user_name / text_preview / note are allowed to update."""
        conn = await self._get_conn()
        filtered = {k: v for k, v in fields.items() if k in _VIOLATION_UPDATABLE_FIELDS}
        if not filtered:
            return False
        try:
            set_clause = ", ".join(f"{k} = ?" for k in filtered)
            values = list(filtered.values())
            values.append(vid)
            cursor = await conn.execute(
                f"UPDATE violation_records SET {set_clause} WHERE id = ?",
                values,
            )
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update_violation({vid}): {e}")
            return False

    async def delete_violation(self, vid: int) -> bool:
        """Delete a single violation row and recalc user's violation_count."""
        conn = await self._get_conn()
        try:
            # 先获取 user_id（用于后续重新计算 violation_count）
            cursor = await conn.execute(
                "SELECT user_id FROM violation_records WHERE id = ?",
                (vid,),
            )
            row = await cursor.fetchone()
            if not row:
                return False
            user_id = row["user_id"]

            cursor = await conn.execute(
                "DELETE FROM violation_records WHERE id = ?",
                (vid,),
            )
            deleted = cursor.rowcount > 0

            # 重新计算并更新用户的违规计数
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM violation_records WHERE user_id = ?",
                (user_id,),
            )
            count_row = await cursor.fetchone()
            remaining = count_row[0] if count_row else 0
            await conn.execute(
                "UPDATE user_profiles SET violation_count = ?, updated_at = ? WHERE user_id = ?",
                (remaining, datetime.now().isoformat(), user_id),
            )
            await self._recalc_violation_records_seq(user_id)
            await conn.commit()
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete_violation({vid}): {e}")
            return False

    async def delete_violations_batch(self, ids: list[int]) -> int:
        """Batch-delete violations; returns rows deleted. Also recalculates user violation counts."""
        if not ids:
            return 0
        conn = await self._get_conn()
        try:
            # 先获取所有受影响的 user_id（用于后续重新计算 violation_count）
            affected_cursor = await conn.execute(
                f"SELECT DISTINCT user_id FROM violation_records WHERE id IN ({','.join('?' for _ in ids)})",
                ids,
            )
            affected_users = [row["user_id"] for row in await affected_cursor.fetchall()]

            placeholders = ",".join("?" for _ in ids)
            cursor = await conn.execute(
                f"DELETE FROM violation_records WHERE id IN ({placeholders})",
                ids,
            )
            deleted = cursor.rowcount

            # 重新计算所有受影响用户的违规计数（一条 UPDATE + 子查询）
            now_iso = datetime.now().isoformat()
            if affected_users:
                user_placeholders = ",".join("?" for _ in affected_users)
                await conn.execute(
                    f"""UPDATE user_profiles
                        SET violation_count = (
                                SELECT COUNT(*) FROM violation_records
                                WHERE user_id = user_profiles.user_id
                            ),
                            updated_at = ?
                        WHERE user_id IN ({user_placeholders})""",
                    (now_iso, *affected_users),
                )
            # 重算受影响用户的 violation_records 序号
            for uid in affected_users:
                await self._recalc_violation_records_seq(uid)
            await conn.commit()
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete_violations_batch: {e}")
            return 0

    # ====================================================================
    # v2.0 new: audit log CRUD (no edit)
    # ====================================================================

    async def list_audits(
        self,
        page: int = 1,
        page_size: int = 20,
        group_id: str | None = None,
        has_violation: int | None = None,
        keyword: str | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated audit_log query."""
        conn = await self._get_conn()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        clauses: list[str] = []
        params: list[Any] = []
        if group_id:
            clauses.append("group_id = ?")
            params.append(group_id)
        if has_violation is not None:
            clauses.append("has_violation = ?")
            params.append(has_violation)
        if keyword:
            escaped = _escape_like(keyword)
            clauses.append("(user_name LIKE ? ESCAPE '\\' OR text_preview LIKE ? ESCAPE '\\')")
            like = f"%{escaped}%"
            params.extend([like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            count_cursor = await conn.execute(
                f"SELECT COUNT(*) FROM audit_log {where}",
                params,
            )
            total_row = await count_cursor.fetchone()
            total = total_row[0] if total_row else 0

            data_cursor = await conn.execute(
                f"""SELECT * FROM audit_log {where}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?""",
                [*params, page_size, (page - 1) * page_size],
            )
            rows = [dict(r) for r in await data_cursor.fetchall()]
            return rows, total
        except Exception as e:
            logger.error(f"Failed to list_audits: {e}")
            return [], 0

    async def get_audit(self, aid: int) -> dict | None:
        """Fetch a single audit_log row by id."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "SELECT * FROM audit_log WHERE id = ?",
                (aid,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get_audit({aid}): {e}")
            return None

    async def delete_audit(self, aid: int) -> bool:
        """Delete a single audit_log row."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "DELETE FROM audit_log WHERE id = ?",
                (aid,),
            )
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete_audit({aid}): {e}")
            return False

    async def delete_audits_batch(self, ids: list[int]) -> int:
        """Batch-delete audit_log rows; returns rows deleted."""
        if not ids:
            return 0
        conn = await self._get_conn()
        try:
            placeholders = ",".join("?" for _ in ids)
            cursor = await conn.execute(
                f"DELETE FROM audit_log WHERE id IN ({placeholders})",
                ids,
            )
            await conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to delete_audits_batch: {e}")
            return 0

    # ====================================================================
    # v2.0 new: whitelist detailed CRUD (with note + id)
    # ====================================================================

    async def list_whitelist_detailed(self) -> list[dict]:
        """SELECT id, user_id, note, created_at FROM whitelist ORDER BY created_at DESC."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                """SELECT id, user_id,
                          COALESCE(note, '') AS note,
                          created_at
                   FROM whitelist
                   ORDER BY created_at DESC"""
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list_whitelist_detailed: {e}")
            return []

    async def add_whitelist_with_note(self, user_id: str, note: str = "") -> int | None:
        """Returns new id on success; returns None if user_id already exists."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                """INSERT INTO whitelist (user_id, note, created_at)
                   VALUES (?, ?, ?)""",
                (user_id, note, datetime.now().isoformat()),
            )
            await conn.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return None
        except Exception as e:
            logger.error(f"Failed to add_whitelist_with_note({user_id}): {e}")
            return None

    async def update_whitelist_note(self, wid: int, note: str) -> bool:
        """Update whitelist note."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "UPDATE whitelist SET note = ? WHERE id = ?",
                (note, wid),
            )
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update_whitelist_note({wid}): {e}")
            return False

    async def delete_whitelist_by_id(self, wid: int) -> bool:
        """Delete whitelist row by id."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "DELETE FROM whitelist WHERE id = ?",
                (wid,),
            )
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete_whitelist_by_id({wid}): {e}")
            return False

    # ====================================================================
    # v2.0 new: user_profiles CRUD
    # ====================================================================

    async def list_user_profiles(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict], int]:
        """Paginated user_profiles query; keyword LIKE-matches user_id/nickname/note."""
        conn = await self._get_conn()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        clauses: list[str] = []
        params: list[Any] = []
        if keyword:
            escaped = _escape_like(keyword)
            clauses.append(
                "(user_id LIKE ? ESCAPE '\\' OR nickname LIKE ? ESCAPE '\\' OR note LIKE ? ESCAPE '\\')"
            )
            like = f"%{escaped}%"
            params.extend([like, like, like])
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            count_cursor = await conn.execute(
                f"SELECT COUNT(*) FROM user_profiles {where}",
                params,
            )
            total_row = await count_cursor.fetchone()
            total = total_row[0] if total_row else 0

            data_cursor = await conn.execute(
                f"""SELECT * FROM user_profiles {where}
                    ORDER BY violation_count DESC, last_seen_at DESC
                    LIMIT ? OFFSET ?""",
                [*params, page_size, (page - 1) * page_size],
            )
            rows = [dict(r) for r in await data_cursor.fetchall()]
            return rows, total
        except Exception as e:
            logger.error(f"Failed to list_user_profiles: {e}")
            return [], 0

    async def get_user_profile(self, user_id: str) -> dict | None:
        """Fetch a single user_profile by user_id."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get_user_profile({user_id}): {e}")
            return None

    async def create_user_profile(self, data: dict) -> bool:
        """Manually insert a user_profile; user_id required; duplicate -> False."""
        user_id = data.get("user_id")
        if not user_id:
            return False
        conn = await self._get_conn()
        nickname = data.get("nickname", "") or ""
        note = data.get("note", "") or ""
        status = data.get("status", "normal") or "normal"
        violation_count = int(data.get("violation_count", 0) or 0)
        group_ids_val = data.get("group_ids", [])
        if isinstance(group_ids_val, list):
            try:
                group_ids_json = json.dumps([str(g) for g in group_ids_val], ensure_ascii=False)
            except Exception:
                group_ids_json = "[]"
        elif isinstance(group_ids_val, str):
            group_ids_json = group_ids_val or "[]"
        else:
            group_ids_json = "[]"
        now_iso = datetime.now().isoformat()
        try:
            await conn.execute(
                """INSERT INTO user_profiles
                   (user_id, nickname, group_ids, note, status,
                    violation_count, first_seen_at, last_seen_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    nickname,
                    group_ids_json,
                    note,
                    status,
                    violation_count,
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            await conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Failed to create_user_profile({user_id}): {e}")
            return False

    async def update_user_profile(self, user_id: str, fields: dict) -> bool:
        """Allowed: nickname / note / status / group_ids (list[str] -> JSON)."""
        filtered: dict[str, Any] = {}
        for k, v in fields.items():
            if k not in _USER_PROFILE_UPDATABLE_FIELDS:
                continue
            if k == "group_ids":
                if isinstance(v, list):
                    try:
                        filtered[k] = json.dumps([str(x) for x in v], ensure_ascii=False)
                    except Exception:
                        continue
                elif isinstance(v, str):
                    filtered[k] = v
                else:
                    continue
            else:
                filtered[k] = v
        if not filtered:
            return False
        filtered["updated_at"] = datetime.now().isoformat()
        conn = await self._get_conn()
        try:
            set_clause = ", ".join(f"{k} = ?" for k in filtered)
            values = list(filtered.values())
            values.append(user_id)
            cursor = await conn.execute(
                f"UPDATE user_profiles SET {set_clause} WHERE user_id = ?",
                values,
            )
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update_user_profile({user_id}): {e}")
            return False

    async def delete_user_profile(self, user_id: str) -> bool:
        """Delete a user_profile row."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "DELETE FROM user_profiles WHERE user_id = ?",
                (user_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete_user_profile({user_id}): {e}")
            return False

    # ====================================================================
    # v2.0 new: overview stats
    # ====================================================================

    async def get_overview_stats(self) -> dict:
        """Return dashboard overview data."""
        conn = await self._get_conn()
        empty = {
            "today_audits": 0,
            "today_violations": 0,
            "total_audits": 0,
            "total_violations": 0,
            "whitelist_count": 0,
            "user_profiles_count": 0,
            "trend_7days": [],
            "top_violators": [],
            "group_distribution": [],
        }
        try:
            today_str = date.today().isoformat()

            async def _scalar(sql: str, params: tuple = ()) -> int:
                cursor = await conn.execute(sql, params)
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else 0

            today_audits = await _scalar(
                "SELECT COUNT(*) FROM audit_log WHERE date(created_at) >= date(?)",
                (today_str,),
            )
            today_violations = await _scalar(
                "SELECT COUNT(*) FROM violation_records WHERE date(created_at) >= date(?)",
                (today_str,),
            )
            total_audits = await _scalar("SELECT COUNT(*) FROM audit_log")
            total_violations = await _scalar("SELECT COUNT(*) FROM violation_records")
            whitelist_count = await _scalar("SELECT COUNT(*) FROM whitelist")
            user_profiles_count = await _scalar("SELECT COUNT(*) FROM user_profiles")

            # 7-day trend（2 次 GROUP BY 查询代替 14 次逐天查询）
            today = date.today()
            start_str = (today - timedelta(days=6)).isoformat()
            audit_trend_cursor = await conn.execute(
                "SELECT date(created_at) AS d, COUNT(*) AS c FROM audit_log "
                "WHERE date(created_at) >= date(?) GROUP BY d",
                (start_str,),
            )
            audit_counts = {row["d"]: row["c"] for row in await audit_trend_cursor.fetchall()}
            viol_trend_cursor = await conn.execute(
                "SELECT date(created_at) AS d, COUNT(*) AS c FROM violation_records "
                "WHERE date(created_at) >= date(?) GROUP BY d",
                (start_str,),
            )
            viol_counts = {row["d"]: row["c"] for row in await viol_trend_cursor.fetchall()}
            trend: list[dict] = []
            for i in range(6, -1, -1):
                d_str = (today - timedelta(days=i)).isoformat()
                trend.append(
                    {
                        "date": d_str,
                        "audits": audit_counts.get(d_str, 0),
                        "violations": viol_counts.get(d_str, 0),
                    }
                )

            # Top 10 violators
            top_cursor = await conn.execute(
                """SELECT user_id, nickname, violation_count
                   FROM user_profiles
                   WHERE violation_count > 0
                   ORDER BY violation_count DESC
                   LIMIT 10"""
            )
            top_violators = [dict(r) for r in await top_cursor.fetchall()]

            # group distribution Top 10 (by audits desc)
            dist_cursor = await conn.execute(
                """SELECT
                       a.group_id,
                       COUNT(a.id) AS audits,
                       COALESCE((
                           SELECT COUNT(*) FROM violation_records v
                           WHERE v.group_id = a.group_id
                       ), 0) AS violations
                   FROM audit_log a
                   GROUP BY a.group_id
                   ORDER BY audits DESC
                   LIMIT 10"""
            )
            group_distribution = [dict(r) for r in await dist_cursor.fetchall()]

            return {
                "today_audits": today_audits,
                "today_violations": today_violations,
                "total_audits": total_audits,
                "total_violations": total_violations,
                "whitelist_count": whitelist_count,
                "user_profiles_count": user_profiles_count,
                "trend_7days": trend,
                "top_violators": top_violators,
                "group_distribution": group_distribution,
            }
        except Exception as e:
            logger.error(f"Failed to get_overview_stats: {e}")
            return empty

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
