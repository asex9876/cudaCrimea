from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models.tables import User
from app.db.session import get_sessionmaker

DEFAULT_CITY = "Севастополь"


async def get_user_city(user_id: int) -> str:
    async_session = get_sessionmaker()
    async with async_session() as session:
        result = await session.execute(select(User.city).where(User.tg_id == user_id))
        city = result.scalar_one_or_none()
        return city if city else DEFAULT_CITY


async def set_user_city(user_id: int, city: str) -> None:
    async_session = get_sessionmaker()
    async with async_session() as session:
        stmt = insert(User).values(tg_id=user_id, city=city).on_conflict_do_update(
            index_elements=["tg_id"],
            set_={"city": city},
        )
        await session.execute(stmt)
        await session.commit()


async def has_user_city(user_id: int) -> bool:
    async_session = get_sessionmaker()
    async with async_session() as session:
        result = await session.execute(select(User.tg_id).where(User.tg_id == user_id))
        return result.scalar_one_or_none() is not None
