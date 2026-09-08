import asyncio
import logging
import sys

from common.config import settings
from common.database import db
from client_bot.bot import create_client_bot
from worker_bot.bot import create_worker_bot, create_worker_dispatcher
from worker_bot.handlers import worker_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("worker_bot_runner")


async def main():
    if not settings.is_worker_token_configured():
        logger.error("WORKER_BOT_TOKEN is not configured in .env! Please set your token.")
        sys.exit(1)
    if not settings.is_client_token_configured():
        logger.error("CLIENT_BOT_TOKEN is needed so worker can send replies back to clients. Please set it in .env.")
        sys.exit(1)

    await db.init_db()

    client_bot = create_client_bot()
    worker_bot = create_worker_bot()

    worker_dp = create_worker_dispatcher()
    worker_dp.include_router(worker_router)
    worker_dp["client_bot"] = client_bot

    logger.info("Starting Worker Bot polling...")
    try:
        await worker_dp.start_polling(worker_bot)
    finally:
        await client_bot.session.close()
        await worker_bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker Bot stopped.")

