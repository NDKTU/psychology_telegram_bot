from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from common.config import settings

def create_worker_bot() -> Bot:
    """Create and configure worker bot instance."""
    return Bot(
        token=settings.WORKER_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

def create_worker_dispatcher() -> Dispatcher:
    """Create worker bot dispatcher."""
    dp = Dispatcher()
    return dp

