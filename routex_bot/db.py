"""SQLite storage utilities for RouteX VPN bot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import aiosqlite


@dataclass(slots=True)
class Schedule:
    id: int
    name: str
    type: str
    spec: str
    text: str
    segment: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    next_run_at: Optional[datetime]


class Database:
    """Async wrapper over aiosqlite for the bot."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database connection is not initialized")
        return self._conn

    async def connect(self) -> None:
        """Open the database connection and ensure directory exists."""

        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON;")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init_models(self) -> None:
        """Create tables if they do not exist."""

        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                key TEXT,
                is_subscribed INTEGER NOT NULL DEFAULT 1,
                is_donor INTEGER NOT NULL DEFAULT 0,
                last_activity_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('cron','interval')),
                spec TEXT NOT NULL,
                text TEXT NOT NULL,
                segment TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                next_run_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER REFERENCES schedules(id) ON DELETE SET NULL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK(status IN ('queued','sent','failed')),
                error TEXT,
                sent_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actor_tg_id INTEGER,
                action TEXT NOT NULL,
                meta_json TEXT
            );
            """
        )
        await self.conn.commit()

    async def get_user(self, tg_id: int) -> Optional[aiosqlite.Row]:
        cursor = await self.conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        return await cursor.fetchone()

    async def ensure_user(self, tg_id: int, username: str | None = None) -> aiosqlite.Row:
        user = await self.get_user(tg_id)
        if user:
            if username and user["username"] != username:
                await self.update_username(tg_id, username)
                user = await self.get_user(tg_id)
            return user
        await self.conn.execute(
            "INSERT INTO users (tg_id, username, last_activity_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (tg_id, username),
        )
        await self.conn.commit()
        cursor = await self.conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        return await cursor.fetchone()

    async def update_username(self, tg_id: int, username: str | None) -> None:
        await self.conn.execute(
            "UPDATE users SET username = ?, updated_at = CURRENT_TIMESTAMP WHERE tg_id = ?",
            (username, tg_id),
        )
        await self.conn.commit()

    async def update_user_key(self, tg_id: int, key: str) -> None:
        await self.conn.execute(
            "UPDATE users SET key = ?, last_activity_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE tg_id = ?",
            (key, tg_id),
        )
        await self.conn.commit()

    async def clear_user_key(self, tg_id: int) -> None:
        await self.conn.execute(
            "UPDATE users SET key = NULL, last_activity_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE tg_id = ?",
            (tg_id,),
        )
        await self.conn.commit()

    async def update_subscription(self, tg_id: int, subscribed: bool) -> None:
        await self.conn.execute(
            "UPDATE users SET is_subscribed = ?, last_activity_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE tg_id = ?",
            (1 if subscribed else 0, tg_id),
        )
        await self.conn.commit()

    async def mark_donor(self, tg_id: int) -> None:
        await self.conn.execute(
            "UPDATE users SET is_donor = 1, last_activity_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE tg_id = ?",
            (tg_id,),
        )
        await self.conn.commit()

    async def touch_activity(self, tg_id: int) -> None:
        await self.conn.execute(
            "UPDATE users SET last_activity_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE tg_id = ?",
            (tg_id,),
        )
        await self.conn.commit()

    async def add_schedule(
        self,
        name: str,
        schedule_type: str,
        spec: str,
        text: str,
        segment: Dict[str, Any],
        enabled: bool = True,
    ) -> int:
        segment_json = json.dumps(segment, ensure_ascii=False)
        cursor = await self.conn.execute(
            """
            INSERT INTO schedules (name, type, spec, text, segment, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, schedule_type, spec, text, segment_json, 1 if enabled else 0),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def list_schedules(self) -> List[Schedule]:
        cursor = await self.conn.execute(
            "SELECT * FROM schedules ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._schedule_from_row(row) for row in rows]

    async def get_schedule(self, schedule_id: int) -> Optional[Schedule]:
        cursor = await self.conn.execute(
            "SELECT * FROM schedules WHERE id = ?",
            (schedule_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._schedule_from_row(row)

    async def set_schedule_enabled(self, schedule_id: int, enabled: bool) -> None:
        await self.conn.execute(
            "UPDATE schedules SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if enabled else 0, schedule_id),
        )
        await self.conn.commit()

    async def delete_schedule(self, schedule_id: int) -> None:
        await self.conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        await self.conn.commit()

    async def update_schedule_next_run(self, schedule_id: int, next_run: datetime | None) -> None:
        await self.conn.execute(
            "UPDATE schedules SET next_run_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (next_run.isoformat() if next_run else None, schedule_id),
        )
        await self.conn.commit()

    async def enqueue_delivery(
        self, schedule_id: Optional[int], user_id: int, status: str = "queued"
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO deliveries (schedule_id, user_id, status)
            VALUES (?, ?, ?)
            """,
            (schedule_id, user_id, status),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def has_recent_delivery(
        self, schedule_id: int, user_id: int, within_hours: int = 24
    ) -> bool:
        cursor = await self.conn.execute(
            """
            SELECT 1 FROM deliveries
            WHERE schedule_id = ? AND user_id = ?
              AND sent_at >= datetime('now', ?)
            LIMIT 1
            """,
            (schedule_id, user_id, f"-{within_hours} hours"),
        )
        return await cursor.fetchone() is not None

    async def update_delivery(
        self,
        delivery_id: int,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        await self.conn.execute(
            "UPDATE deliveries SET status = ?, error = ?, sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, error, delivery_id),
        )
        await self.conn.commit()

    async def list_users_for_segment(self, segment: Dict[str, Any]) -> List[aiosqlite.Row]:
        sql = "SELECT * FROM users WHERE 1=1"
        params: List[Any] = []
        seg_type = segment.get("type", "all_subscribed")

        if seg_type != "custom_sql":
            sql += " AND is_subscribed = 1"

        if seg_type == "no_key":
            sql += " AND key IS NULL"
        elif seg_type == "inactive_30d":
            sql += " AND (last_activity_at IS NULL OR last_activity_at < ?)"
            params.append((datetime.utcnow() - timedelta(days=30)).isoformat(sep=" "))
        elif seg_type == "donors":
            sql += " AND is_donor = 1"
        elif seg_type == "custom_sql":
            where_clause = segment.get("where")
            if not where_clause or "--" in where_clause:
                raise ValueError("Некорректный custom_sql сегмент")
            sql += f" AND {where_clause}"
        else:
            # default all_subscribed
            pass

        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchall()

    async def get_stats(self) -> Dict[str, Any]:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN is_subscribed=1 THEN 1 ELSE 0 END) AS subscribed,"
            " SUM(CASE WHEN is_subscribed=0 THEN 1 ELSE 0 END) AS unsubscribed,"
            " SUM(CASE WHEN is_donor=1 THEN 1 ELSE 0 END) AS donors"
            " FROM users"
        )
        row = await cursor.fetchone()
        totals = dict(row) if row else {}

        cursor = await self.conn.execute(
            "SELECT schedule_id, SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS sent,"
            " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed"
            " FROM deliveries WHERE schedule_id IS NOT NULL"
            " GROUP BY schedule_id ORDER BY schedule_id DESC LIMIT 5"
        )
        deliveries = [dict(r) for r in await cursor.fetchall()]
        return {"totals": totals, "deliveries": deliveries}

    async def write_audit(self, actor_tg_id: int | None, action: str, meta: Dict[str, Any]) -> None:
        await self.conn.execute(
            "INSERT INTO audit_log (actor_tg_id, action, meta_json) VALUES (?, ?, ?)",
            (actor_tg_id, action, json.dumps(meta, ensure_ascii=False)),
        )
        await self.conn.commit()

    async def get_setting(self, key: str) -> str | None:
        cursor = await self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()

    def _schedule_from_row(self, row: aiosqlite.Row) -> Schedule:
        return Schedule(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            spec=row["spec"],
            text=row["text"],
            segment=row["segment"],
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=
            datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.fromisoformat(row["created_at"]),
            next_run_at=datetime.fromisoformat(row["next_run_at"]) if row["next_run_at"] else None,
        )


__all__ = ["Database", "Schedule"]
