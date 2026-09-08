import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import aiosqlite

try:
    import asyncpg
except ImportError:
    asyncpg = None

from common.config import settings

logger = logging.getLogger(__name__)


class Database:
    """
    Unified database manager supporting both PostgreSQL (via asyncpg)
    and SQLite (via aiosqlite) as a fallback.
    """

    def __init__(self, db_url: Optional[str] = None, db_path: Optional[str] = None):
        if db_url is not None:
            self.db_url = db_url
        else:
            self.db_url = settings.DATABASE_URL

        self.db_path = db_path if db_path is not None else settings.DATABASE_PATH
        self.is_postgres = bool(
            self.db_url and (
                self.db_url.startswith("postgresql://") or 
                self.db_url.startswith("postgres://")
            )
        )
        self.pg_pool: Optional[asyncpg.Pool] = None

        if not self.is_postgres:
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

    async def get_pg_pool(self) -> asyncpg.Pool:
        if self.pg_pool is None:
            self.pg_pool = await asyncpg.create_pool(
                self.db_url,
                min_size=2,
                max_size=10
            )
        return self.pg_pool

    async def close(self) -> None:
        if self.pg_pool is not None:
            await self.pg_pool.close()
            self.pg_pool = None

    async def init_db(self) -> None:
        """Create tables in PostgreSQL or SQLite."""
        if self.is_postgres:
            try:
                pool = await self.get_pg_pool()
                async with pool.acquire() as conn:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS clients (
                            user_id BIGINT PRIMARY KEY,
                            username TEXT,
                            first_name TEXT,
                            last_name TEXT,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            last_seen_at TIMESTAMPTZ DEFAULT NOW(),
                            status TEXT DEFAULT 'active'
                        );

                        CREATE TABLE IF NOT EXISTS workers (
                            user_id BIGINT PRIMARY KEY,
                            username TEXT,
                            first_name TEXT,
                            is_active INT DEFAULT 1,
                            registered_at TIMESTAMPTZ DEFAULT NOW()
                        );

                        CREATE TABLE IF NOT EXISTS messages (
                            id BIGSERIAL PRIMARY KEY,
                            client_user_id BIGINT NOT NULL,
                            client_message_id INT NOT NULL,
                            worker_chat_id BIGINT,
                            worker_message_id INT,
                            message_type VARCHAR(32) NOT NULL,
                            content TEXT,
                            status VARCHAR(32) NOT NULL DEFAULT 'not_answered',
                            answered_by BIGINT,
                            answer_text TEXT,
                            answered_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        );

                        CREATE INDEX IF NOT EXISTS idx_pg_msg_status 
                        ON messages (status, created_at);

                        CREATE TABLE IF NOT EXISTS message_mappings (
                            id BIGSERIAL PRIMARY KEY,
                            db_message_id BIGINT REFERENCES messages(id) ON DELETE CASCADE,
                            worker_chat_id BIGINT NOT NULL,
                            worker_message_id INT NOT NULL,
                            client_user_id BIGINT NOT NULL,
                            client_message_id INT NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        );

                        CREATE INDEX IF NOT EXISTS idx_pg_worker_msg 
                        ON message_mappings (worker_chat_id, worker_message_id);

                        CREATE TABLE IF NOT EXISTS active_sessions (
                            worker_chat_id BIGINT PRIMARY KEY,
                            client_user_id BIGINT NOT NULL,
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        );
                    """)
                logger.info("Connected to PostgreSQL and initialized tables.")
                return
            except Exception as e:
                logger.warning(
                    f"Could not connect to PostgreSQL ({e}). Falling back to SQLite at {self.db_path}."
                )
                self.is_postgres = False
                if self.pg_pool is not None:
                    await self.pg_pool.close()
                    self.pg_pool = None

        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA busy_timeout=5000;")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS workers (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    is_active INTEGER DEFAULT 1,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_user_id INTEGER NOT NULL,
                    client_message_id INTEGER NOT NULL,
                    worker_chat_id INTEGER,
                    worker_message_id INTEGER,
                    message_type TEXT NOT NULL,
                    content TEXT,
                    status TEXT NOT NULL DEFAULT 'not_answered',
                    answered_by INTEGER,
                    answer_text TEXT,
                    answered_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_msg_status 
                ON messages (status, created_at)
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS message_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    db_message_id INTEGER,
                    worker_chat_id INTEGER NOT NULL,
                    worker_message_id INTEGER NOT NULL,
                    client_user_id INTEGER NOT NULL,
                    client_message_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_worker_msg 
                ON message_mappings (worker_chat_id, worker_message_id)
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS active_sessions (
                    worker_chat_id INTEGER PRIMARY KEY,
                    client_user_id INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def upsert_client(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> None:
        """Add or update client information."""
        now = datetime.now(timezone.utc).isoformat()
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO clients (user_id, username, first_name, last_name, last_seen_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        last_seen_at = NOW();
                """, user_id, username, first_name, last_name)
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO clients (user_id, username, first_name, last_name, created_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        last_name = excluded.last_name,
                        last_seen_at = excluded.last_seen_at
                """, (user_id, username, first_name, last_name, now, now))
                await db.commit()

    async def register_worker(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> None:
        """Register an authorized worker (logs them in)."""
        now = datetime.now(timezone.utc).isoformat()
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO workers (user_id, username, first_name, is_active)
                    VALUES ($1, $2, $3, 1)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        is_active = 1;
                """, user_id, username, first_name)
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO workers (user_id, username, first_name, is_active, registered_at)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        is_active = 1
                """, (user_id, username, first_name, now))
                await db.commit()

    async def logout_worker(self, user_id: int) -> None:
        """Log out an authorized worker."""
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE workers SET is_active = 0 WHERE user_id = $1;",
                    user_id
                )
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE workers SET is_active = 0 WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()

    async def is_worker(self, user_id: int) -> bool:
        """Check if a user is an authorized active worker."""
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT 1 FROM workers WHERE user_id = $1 AND is_active = 1",
                    user_id
                )
                return row is not None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT 1 FROM workers WHERE user_id = ? AND is_active = 1",
                    (user_id,)
                )
                row = await cursor.fetchone()
                return row is not None

    async def get_active_workers(self) -> List[int]:
        """Return a list of user IDs for all logged-in active workers."""
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id FROM workers WHERE is_active = 1")
                return [row["user_id"] for row in rows]
        else:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT user_id FROM workers WHERE is_active = 1")
                rows = await cursor.fetchall()
                return [row["user_id"] for row in rows]

    async def save_client_message(
        self,
        client_user_id: int,
        client_message_id: int,
        message_type: str,
        content: Optional[str] = None,
    ) -> int:
        """
        Record incoming client message with status = 'not_answered'.
        Returns the inserted message ID.
        """
        now = datetime.now(timezone.utc).isoformat()
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    INSERT INTO messages (
                        client_user_id, client_message_id, message_type, content, status
                    )
                    VALUES ($1, $2, $3, $4, 'not_answered')
                    RETURNING id;
                """, client_user_id, client_message_id, message_type, content)
                return row["id"]
        else:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    INSERT INTO messages (
                        client_user_id, client_message_id, message_type, content, status, created_at
                    )
                    VALUES (?, ?, ?, ?, 'not_answered', ?)
                """, (client_user_id, client_message_id, message_type, content, now))
                await db.commit()
                return cursor.lastrowid

    async def link_worker_message(
        self,
        db_message_id: int,
        worker_chat_id: int,
        worker_message_id: int,
        client_user_id: int,
        client_message_id: int,
    ) -> None:
        """
        Link a message in worker_bot to the database record and active session.
        """
        now = datetime.now(timezone.utc).isoformat()
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE messages 
                    SET worker_chat_id = $1, worker_message_id = $2
                    WHERE id = $3;
                """, worker_chat_id, worker_message_id, db_message_id)

                await conn.execute("""
                    INSERT INTO message_mappings (
                        db_message_id, worker_chat_id, worker_message_id, client_user_id, client_message_id
                    )
                    VALUES ($1, $2, $3, $4, $5);
                """, db_message_id, worker_chat_id, worker_message_id, client_user_id, client_message_id)

                await conn.execute("""
                    INSERT INTO active_sessions (worker_chat_id, client_user_id, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT(worker_chat_id) DO UPDATE SET
                        client_user_id = EXCLUDED.client_user_id,
                        updated_at = NOW();
                """, worker_chat_id, client_user_id)
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE messages 
                    SET worker_chat_id = ?, worker_message_id = ?
                    WHERE id = ?
                """, (worker_chat_id, worker_message_id, db_message_id))

                await db.execute("""
                    INSERT INTO message_mappings (
                        db_message_id, worker_chat_id, worker_message_id, client_user_id, client_message_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (db_message_id, worker_chat_id, worker_message_id, client_user_id, client_message_id, now))

                await db.execute("""
                    INSERT INTO active_sessions (worker_chat_id, client_user_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(worker_chat_id) DO UPDATE SET
                        client_user_id = excluded.client_user_id,
                        updated_at = excluded.updated_at
                """, (worker_chat_id, client_user_id, now))

                await db.commit()

    async def get_client_by_worker_message(
        self,
        worker_chat_id: int,
        worker_message_id: int,
    ) -> Optional[Tuple[int, int, Optional[int]]]:
        """
        Find (client_user_id, client_message_id, db_message_id) by worker message.
        """
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT client_user_id, client_message_id, db_message_id
                    FROM message_mappings
                    WHERE worker_chat_id = $1 AND worker_message_id = $2
                    ORDER BY id DESC LIMIT 1;
                """, worker_chat_id, worker_message_id)
                if row:
                    return (row["client_user_id"], row["client_message_id"], row["db_message_id"])
                return None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT client_user_id, client_message_id, db_message_id
                    FROM message_mappings
                    WHERE worker_chat_id = ? AND worker_message_id = ?
                    ORDER BY id DESC LIMIT 1
                """, (worker_chat_id, worker_message_id))
                row = await cursor.fetchone()
                if row:
                    return (row["client_user_id"], row["client_message_id"], row["db_message_id"])
                return None

    async def mark_message_answered(
        self,
        worker_user_id: int,
        answer_text: str,
        db_message_id: Optional[int] = None,
        client_user_id: Optional[int] = None,
    ) -> None:
        """
        Transition message status from 'not_answered' to 'answered'.
        Records specialist user ID, answer text, and timestamp.
        """
        now = datetime.now(timezone.utc).isoformat()
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                if db_message_id:
                    await conn.execute("""
                        UPDATE messages 
                        SET status = 'answered',
                            answered_by = $1,
                            answer_text = $2,
                            answered_at = NOW()
                        WHERE id = $3;
                    """, worker_user_id, answer_text, db_message_id)
                elif client_user_id:
                    await conn.execute("""
                        UPDATE messages 
                        SET status = 'answered',
                            answered_by = $1,
                            answer_text = $2,
                            answered_at = NOW()
                        WHERE id = (
                            SELECT id FROM messages 
                            WHERE client_user_id = $3 AND status = 'not_answered' 
                            ORDER BY id DESC LIMIT 1
                        );
                    """, worker_user_id, answer_text, client_user_id)
        else:
            async with aiosqlite.connect(self.db_path) as db:
                if db_message_id:
                    await db.execute("""
                        UPDATE messages 
                        SET status = 'answered',
                            answered_by = ?,
                            answer_text = ?,
                            answered_at = ?
                        WHERE id = ?
                    """, (worker_user_id, answer_text, now, db_message_id))
                elif client_user_id:
                    await db.execute("""
                        UPDATE messages 
                        SET status = 'answered',
                            answered_by = ?,
                            answer_text = ?,
                            answered_at = ?
                        WHERE id = (
                            SELECT id FROM messages 
                            WHERE client_user_id = ? AND status = 'not_answered' 
                            ORDER BY id DESC LIMIT 1
                        )
                    """, (worker_user_id, answer_text, now, client_user_id))
                await db.commit()

    async def get_unanswered_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve inquiries that have not been answered yet.
        """
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT m.id, m.client_user_id, m.message_type, m.content, m.created_at,
                           c.first_name, c.username
                    FROM messages m
                    LEFT JOIN clients c ON m.client_user_id = c.user_id
                    WHERE m.status = 'not_answered'
                    ORDER BY m.created_at ASC
                    LIMIT $1;
                """, limit)
                return [dict(row) for row in rows]
        else:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT m.id, m.client_user_id, m.message_type, m.content, m.created_at,
                           c.first_name, c.username
                    FROM messages m
                    LEFT JOIN clients c ON m.client_user_id = c.user_id
                    WHERE m.status = 'not_answered'
                    ORDER BY m.created_at ASC
                    LIMIT ?
                """, (limit,))
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_active_client_for_worker(self, worker_chat_id: int) -> Optional[int]:
        """Get the client_user_id from the latest active session for this worker chat."""
        if self.is_postgres:
            pool = await self.get_pg_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT client_user_id FROM active_sessions
                    WHERE worker_chat_id = $1;
                """, worker_chat_id)
                if row:
                    return row["client_user_id"]
                return None
        else:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT client_user_id FROM active_sessions
                    WHERE worker_chat_id = ?
                """, (worker_chat_id,))
                row = await cursor.fetchone()
                if row:
                    return row["client_user_id"]
                return None


# Global database instance
db = Database()
