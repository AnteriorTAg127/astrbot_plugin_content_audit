import os
from datetime import date, datetime, timedelta

import aiosqlite
from astrbot.api import logger


class StatsManager:
    def __init__(self, data_dir: str) -> None:
        self._db_path = os.path.join(data_dir, "content_audit.db")
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

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
            """)
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to init database: {e}")

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
                    group_id, user_id, user_name, text_preview,
                    request_id, action_recall, action_mute,
                    mute_duration,
                    user_id, group_id,  # for subquery
                    datetime.now().isoformat(),
                ),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to record violation: {e}")

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

    async def get_violations_multi_group(
        self, group_ids: list[str], page: int = 1, page_size: int = 10
    ) -> list[dict]:
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
        conn = await self._get_conn()
        try:
            placeholders = ",".join("?" for _ in group_ids)
            await conn.execute(
                f"""DELETE FROM violation_records
                   WHERE user_id = ? AND group_id IN ({placeholders})""",
                (user_id, *group_ids),
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to delete violations: {e}")

    async def get_stats(self, group_id: str | None = None) -> dict:
        conn = await self._get_conn()
        try:
            today_str = date.today().isoformat()

            if group_id is not None:
                total_audits = (await (await conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE group_id = ?",
                    (group_id,),
                )).fetchone())[0]
                total_violations = (await (await conn.execute(
                    "SELECT COUNT(*) FROM violation_records WHERE group_id = ?",
                    (group_id,),
                )).fetchone())[0]
                today_audits = (await (await conn.execute(
                    """SELECT COUNT(*) FROM audit_log
                       WHERE group_id = ? AND date(created_at) >= date(?)""",
                    (group_id, today_str),
                )).fetchone())[0]
                today_violations = (await (await conn.execute(
                    """SELECT COUNT(*) FROM violation_records
                       WHERE group_id = ? AND date(created_at) >= date(?)""",
                    (group_id, today_str),
                )).fetchone())[0]
            else:
                total_audits = (await (await conn.execute(
                    "SELECT COUNT(*) FROM audit_log"
                )).fetchone())[0]
                total_violations = (await (await conn.execute(
                    "SELECT COUNT(*) FROM violation_records"
                )).fetchone())[0]
                today_audits = (await (await conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE date(created_at) >= date(?)",
                    (today_str,),
                )).fetchone())[0]
                today_violations = (await (await conn.execute(
                    "SELECT COUNT(*) FROM violation_records WHERE date(created_at) >= date(?)",
                    (today_str,),
                )).fetchone())[0]

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

    async def get_whitelist(self) -> list[str]:
        conn = await self._get_conn()
        try:
            cursor = await conn.execute("SELECT user_id FROM whitelist")
            rows = await cursor.fetchall()
            return [row["user_id"] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get whitelist: {e}")
            return []

    async def cleanup_audit_log(self, keep_days: int = 30) -> int:
        conn = await self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
            cursor = await conn.execute(
                "DELETE FROM audit_log WHERE created_at < ?", (cutoff,)
            )
            await conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup audit log: {e}")
            return 0

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
