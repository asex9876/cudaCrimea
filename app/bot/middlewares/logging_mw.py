from __future__ import annotations

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from typing import Any, Awaitable, Callable, Dict


logger = structlog.get_logger(module="bot.middleware.logging")


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            logger.info("bot.msg", user_id=event.from_user.id if event.from_user else None, text=event.text)
        else:
            logger.info("bot.cb", user_id=event.from_user.id if event.from_user else None, data=event.data)
        return await handler(event, data)

