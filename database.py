"""Minimal SQLite layer: users plus a key/value state table.

The state table is what poll loops use to remember "what did I already see" and
"how far did I get last time" across restarts — without it, every restart either
re-sends old items or loses its place.
"""
import time

import aiosqlite

from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id        INTEGER PRIMARY KEY,
    username       TEXT,
    created_at     INTEGER NOT NULL,
    -- On by default: someone who starts a price bot wants the price alerts.
    alerts_enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Dedupe ledger. A UNIQUE insert is the cheapest idempotency guard there is:
-- two independent code paths can both try to handle the same item and only the
-- first one wins, with no locking and no bookkeeping.
CREATE TABLE IF NOT EXISTS seen (
    item_id TEXT PRIMARY KEY,
    seen_at INTEGER NOT NULL
);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def add_user(chat_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (chat_id, username, created_at) VALUES (?, ?, ?)",
            (chat_id, username, int(time.time())),
        )
        await db.commit()


async def all_users() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT chat_id FROM users")
        return [row[0] for row in await cur.fetchall()]


async def get_state(key: str) -> str | None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT value FROM state WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None


async def set_state(key: str, value: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


async def mark_seen(item_id: str) -> bool:
    """True if this is the first time we've seen item_id, False if already handled."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO seen (item_id, seen_at) VALUES (?, ?)", (item_id, int(time.time()))
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def set_alerts(chat_id: int, enabled: bool) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # A user can hit /alerts before /start, so make sure the row exists.
        await db.execute(
            "INSERT OR IGNORE INTO users (chat_id, username, created_at) VALUES (?, NULL, ?)",
            (chat_id, int(time.time())),
        )
        await db.execute("UPDATE users SET alerts_enabled = ? WHERE chat_id = ?", (int(enabled), chat_id))
        await db.commit()


async def alerts_enabled(chat_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT alerts_enabled FROM users WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        return bool(row[0]) if row else True


async def alert_subscribers() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT chat_id FROM users WHERE alerts_enabled = 1")
        return [row[0] for row in await cur.fetchall()]
