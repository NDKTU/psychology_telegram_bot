import pytest
import aiosqlite
import tempfile
import os
from common.database import Database


@pytest.mark.asyncio
async def test_database_init_and_client_upsert():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = Database(db_url="", db_path=db_path)
        await db.init_db()

        # Test upsert client
        await db.upsert_client(
            user_id=123456,
            username="test_client",
            first_name="Alice",
            last_name="Smith"
        )

        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM clients WHERE user_id = 123456")
            row = await cursor.fetchone()
            assert row is not None
            assert row["username"] == "test_client"
            assert row["first_name"] == "Alice"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_worker_registration_auth_and_logout():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = Database(db_url="", db_path=db_path)
        await db.init_db()

        # Initially not a worker
        assert not await db.is_worker(999)

        # Register worker (login)
        await db.register_worker(user_id=999, username="psy_doc", first_name="Dr. House")
        assert await db.is_worker(999)

        workers = await db.get_active_workers()
        assert 999 in workers

        # Logout worker
        await db.logout_worker(999)
        assert not await db.is_worker(999)
        active_workers = await db.get_active_workers()
        assert 999 not in active_workers
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_message_status_lifecycle():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db = Database(db_url="", db_path=db_path)
        await db.init_db()

        # 1. Upsert client
        await db.upsert_client(user_id=777, username="client777", first_name="Bob")

        # 2. Client sends message
        msg_id = await db.save_client_message(
            client_user_id=777,
            client_message_id=10,
            message_type="text",
            content="I need counseling advice"
        )
        assert msg_id is not None

        # 3. Link worker message
        await db.link_worker_message(
            db_message_id=msg_id,
            worker_chat_id=-100555,
            worker_message_id=20,
            client_user_id=777,
            client_message_id=10
        )

        # 4. Check unanswered queue
        unanswered = await db.get_unanswered_messages(limit=10)
        assert len(unanswered) == 1
        assert unanswered[0]["content"] == "I need counseling advice"

        # 5. Worker replies to this message
        await db.mark_message_answered(
            worker_user_id=888,
            answer_text="We are here for you. Tell us more.",
            db_message_id=msg_id,
            client_user_id=777
        )

        # 6. Check that unanswered queue is now empty
        unanswered_after = await db.get_unanswered_messages(limit=10)
        assert len(unanswered_after) == 0

        # 7. Direct inspection of database row
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
            row = await cursor.fetchone()
            assert row["status"] == "answered"
            assert row["answered_by"] == 888
            assert row["answer_text"] == "We are here for you. Tell us more."
            assert row["answered_at"] is not None

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
