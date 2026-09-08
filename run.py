import asyncio
import logging
import sys

from common.config import settings
from common.database import db
from client_bot.bot import create_client_bot, create_client_dispatcher
from client_bot.handlers import client_router
from worker_bot.bot import create_worker_bot, create_worker_dispatcher
from worker_bot.handlers import worker_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("main_runner")


def validate_tokens() -> bool:
    """Validate that bot tokens have been provided by the user."""
    missing = []
    if not settings.is_client_token_configured():
        missing.append("CLIENT_BOT_TOKEN")
    if not settings.is_worker_token_configured():
        missing.append("WORKER_BOT_TOKEN")

    if missing:
        print("\n" + "=" * 65)
        print("⚠️  ACTION REQUIRED: TELEGRAM BOT TOKENS NOT CONFIGURED")
        print("=" * 65)
        print("Please edit the .env file in this directory and replace the placeholders:")
        for var in missing:
            print(f"  • {var}=YOUR_ACTUAL_TOKEN_HERE")
        print("\nTo get bot tokens:")
        print("  1. Open Telegram and search for @BotFather.")
        print("  2. Send /newbot to create client_bot and copy the API token.")
        print("  3. Send /newbot again to create worker_bot and copy the API token.")
        print("  4. Paste both tokens into .env and restart.")
        print("=" * 65 + "\n")
        return False
    return True


async def main():
    logger.info("Initializing database...")
    await db.init_db()
    logger.info("Database initialized successfully.")

    if not validate_tokens():
        logger.warning("Bot polling cannot start until real tokens are supplied in .env.")
        sys.exit(1)

    client_bot = create_client_bot()
    client_dp = create_client_dispatcher()
    client_dp.include_router(client_router)

    worker_bot = create_worker_bot()
    worker_dp = create_worker_dispatcher()
    worker_dp.include_router(worker_router)

    # Cross-reference bots in dispatchers for message relaying
    client_dp["worker_bot"] = worker_bot
    worker_dp["client_bot"] = client_bot

    logger.info("Starting polling for Client Bot and Worker Bot...")
    try:
        await asyncio.gather(
            client_dp.start_polling(client_bot, allowed_updates=client_dp.resolve_used_update_types()),
            worker_dp.start_polling(worker_bot, allowed_updates=worker_dp.resolve_used_update_types()),
        )
    finally:
        logger.info("Closing bot sessions...")
        await client_bot.session.close()
        await worker_bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bots stopped.")

