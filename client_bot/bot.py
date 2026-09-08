from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from common.config import settings

def create_client_bot() -> Bot:
    """Create and configure client bot instance."""
    return Bot(
        token=settings.CLIENT_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

def create_client_dispatcher() -> Dispatcher:
    """Create client bot dispatcher."""
    dp = Dispatcher()
    return dp

