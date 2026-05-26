"""
Скрипт для создания Telethon StringSession.

Запуск:
    docker exec -it cuda_worker python scripts/create_tg_session.py

После выполнения скопируй строку сессии в .env:
    TELEGRAM_SESSION=полученная_строка
"""
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")


async def main() -> None:
    if not API_ID or not API_HASH:
        print("Ошибка: TELEGRAM_API_ID и TELEGRAM_API_HASH должны быть заданы в .env")
        return

    print("Создание Telethon сессии...")
    print(f"API_ID: {API_ID}")

    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_string = client.session.save()
        print("\n" + "=" * 60)
        print("TELEGRAM_SESSION=" + session_string)
        print("=" * 60)
        print("\nСкопируй строку выше в файл .env")


if __name__ == "__main__":
    asyncio.run(main())
