"""
Album (Media Group) Middleware for Aiogram 3

This middleware collects all photos from a media group (album) and passes them
as a single event to the handler, ensuring all photos are processed together.

Based on the fact that Telegram sends all media group updates sequentially
without other messages in between.
"""

from typing import Any, Awaitable, Callable, Dict, List
import asyncio
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class AlbumMiddleware(BaseMiddleware):
    """
    Middleware to handle Telegram albums (media groups).

    Collects all messages with the same media_group_id and passes them
    as a list to the handler after a small delay to ensure all photos arrived.
    """

    album_data: Dict[str, Dict[str, Any]] = {}

    def __init__(self, latency: float = 0.1):
        """
        :param latency: Time in seconds to wait for all photos in album (default 0.1s = 100ms)
        """
        super().__init__()
        self.latency = latency

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        """Process the event"""

        # Only process messages with photos
        if not event.photo:
            return await handler(event, data)

        # If no media_group_id, it's a single photo - process normally
        if not event.media_group_id:
            return await handler(event, data)

        # This is part of a media group (album)
        media_group_id = event.media_group_id

        # Try to get existing album data
        try:
            # Add this message to the album collection
            if media_group_id not in self.album_data:
                self.album_data[media_group_id] = {
                    "messages": [],
                    "lock": asyncio.Lock(),
                    "task": None,
                }

            album_info = self.album_data[media_group_id]

            async with album_info["lock"]:
                # Add message to collection
                album_info["messages"].append(event)

                # Cancel previous task if exists
                if album_info["task"] and not album_info["task"].done():
                    album_info["task"].cancel()

                # Create new task to process after delay
                album_info["task"] = asyncio.create_task(
                    self._process_album(media_group_id, handler, data)
                )

            # Return None to prevent this individual message from being processed
            return None

        except Exception as e:
            # If anything goes wrong, process message normally
            return await handler(event, data)

    async def _process_album(
        self,
        media_group_id: str,
        handler: Callable,
        data: Dict[str, Any],
    ) -> None:
        """Process collected album after delay"""

        # Wait for all photos to arrive
        await asyncio.sleep(self.latency)

        # Get album data
        album_info = self.album_data.get(media_group_id)
        if not album_info:
            return

        messages = album_info["messages"]

        if not messages:
            return

        try:
            # Add album flag and messages list to data
            data["album"] = messages

            # Process with the first message as main event, but include all in data
            await handler(messages[0], data)

        finally:
            # Cleanup
            if media_group_id in self.album_data:
                del self.album_data[media_group_id]
