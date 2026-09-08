from client_bot.bot import create_client_dispatcher
from client_bot.handlers import client_router
from worker_bot.bot import create_worker_dispatcher
from worker_bot.handlers import worker_router
from common.config import settings
from run import validate_tokens


def test_client_dispatcher_setup():
    dp = create_client_dispatcher()
    dp.include_router(client_router)
    assert client_router in dp.sub_routers


def test_worker_dispatcher_setup():
    dp = create_worker_dispatcher()
    dp.include_router(worker_router)
    assert worker_router in dp.sub_routers


def test_token_validation_placeholder():
    # With placeholders, validation should return False without crashing
    assert not settings.is_client_token_configured()
    assert not settings.is_worker_token_configured()
    assert validate_tokens() is False

