import asyncio
import logging
import sys

from common.config import settings
from common.database import db
from client_bot.bot import create_client_bot, create_client_dispatcher
from client_bot.handlers import client_router
from worker_bot.bot import create_worker_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("client_bot_runner")


async def main():
    if not settings.is_client_token_configured():
        logger.error("CLIENT_BOT_TOKEN is not configured in .env! Please set your token.")
        sys.exit(1)
    if not settings.is_worker_token_configured():
        logger.error("WORKER_BOT_TOKEN is also needed to deliver messages to worker bot. Please set it in .env.")
        sys.exit(1)

    await db.init_db()

    client_bot = create_client_bot()
    worker_bot = create_worker_bot()

    client_dp = create_client_dispatcher()
    client_dp.include_router(client_router)
    client_dp["worker_bot"] = worker_bot

    logger.info("Starting Client Bot polling...")
    try:
        await client_dp.start_polling(client_bot)
    finally:
        await client_bot.session.close()
        await worker_bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Client Bot stopped.")

