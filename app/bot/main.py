"""Aiogram v3 bot entrypoint with routers, middlewares, FSM."""

from __future__ import annotations

import asyncio
import structlog
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from app.core.config import get_settings
from app.core.logging import setup_logging
from .middlewares.logging_mw import LoggingMiddleware
from .middlewares.throttling import ThrottlingMiddleware
from .middlewares.album import AlbumMiddleware
from .handlers.start import router as start_router
from .handlers.nearby_food import router as food_router
from .handlers.what_to_do import router as wtd_router
from .handlers.poll import router as poll_router
from .handlers.ugc import router as ugc_router
from .handlers.actions import router as actions_router
from .handlers.fallback import router as fallback_router
from .handlers.nav import router as nav_router
from .handlers.change_city import router as change_city_router
from .handlers.gallery import router as gallery_router
from .handlers.ugc_form import router as ugc_form_router
from .handlers.paid_placement import router as paid_placement_router
from .handlers.events_nearby import router as events_nearby_router


settings = get_settings()
setup_logging(settings.log_level)
logger = structlog.get_logger(module="bot")


async def run_bot() -> None:
    token = settings.bot_token
    if not token:
        logger.error("bot.token_missing")
        raise SystemExit("BOT_TOKEN is not configured")

    bot = Bot(token=token)
    storage = RedisStorage.from_url(str(settings.redis_url))
    dp = Dispatcher(storage=storage)

    # Middlewares (order matters!)
    # 1. Album middleware - must be FIRST to collect media groups
    dp.message.middleware(AlbumMiddleware(latency=0.1))
    # 2. Logging
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    # 3. Throttling
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))

    # Routers
    dp.include_router(start_router)
    dp.include_router(food_router)
    dp.include_router(wtd_router)
    dp.include_router(events_nearby_router)  # Events near me
    dp.include_router(poll_router)
    # Register step-by-step UGC form before legacy UGC to take precedence
    dp.include_router(ugc_form_router)
    dp.include_router(paid_placement_router)  # Paid placement flow
    dp.include_router(ugc_router)
    dp.include_router(actions_router)
    dp.include_router(nav_router)
    dp.include_router(change_city_router)
    dp.include_router(gallery_router)
    # Fallback should be last
    dp.include_router(fallback_router)

    # Set commands menu
    try:
        from aiogram.types import BotCommand

        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Старт / выбор города"),
                BotCommand(command="menu", description="Показать меню"),
            ]
        )
    except Exception:
        pass

    logger.info("bot.starting")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("bot.stopped")


if __name__ == "__main__":
    main()
