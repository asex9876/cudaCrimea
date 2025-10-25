"""APScheduler worker to run ingestors periodically."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from redis import asyncio as aioredis

from app.core import runtime_config as rc
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import get_sessionmaker
from app.ingestors import afisha_goroda, kassa24, yandex_afisha, kudago
from app.ingestors.tg_channels import enqueue_posts, fetch_posts
from app.db.models import Event
import sqlalchemy as sa


logger = structlog.get_logger(module="worker")


async def job_yandex(city: str) -> None:
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        await yandex_afisha.ingest(city, session)


async def job_afisha_goroda(city: str) -> None:
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        await afisha_goroda.ingest(city, session)


async def job_kassa24() -> None:
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        await kassa24.ingest(session)


async def job_kudago(city: str) -> None:
    """KudaGo parser - самый надёжный источник с API."""
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        await kudago.ingest(city, session)


async def job_tg() -> None:
    posts = await fetch_posts(limit=50)
    if posts:
        await enqueue_posts(posts)


async def job_archive_past_events() -> None:
    """Архивация событий по дате начала (date) или дате окончания (end_date).

    Логика:
    - Если есть end_date: архивировать когда end_date + end_time < сейчас
    - Если нет end_date: архивировать когда date + time < сейчас
    """
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        try:
            now = datetime.now()

            # 1. События без end_date - архивируем по дате начала
            stmt_past = (
                sa.update(Event)
                .where(Event.status == "active")
                .where(Event.end_date.is_(None))
                .where(Event.date < now.date())
                .values(status="past")
            )
            result = await session.execute(stmt_past)
            await session.commit()
            if result.rowcount > 0:
                logger.info("worker.archive.past_date", count=result.rowcount)

            # Сегодняшние события без end_date, время прошло
            stmt_today = (
                sa.update(Event)
                .where(Event.status == "active")
                .where(Event.end_date.is_(None))
                .where(Event.date == now.date())
                .where(Event.time.isnot(None))
                .where(Event.time < now.time())
                .values(status="past")
            )
            result = await session.execute(stmt_today)
            await session.commit()
            if result.rowcount > 0:
                logger.info("worker.archive.today", count=result.rowcount)

            # 2. Многодневные события (с end_date) - по дате окончания
            stmt_multi_past = (
                sa.update(Event)
                .where(Event.status == "active")
                .where(Event.end_date.isnot(None))
                .where(Event.end_date < now.date())
                .values(status="past")
            )
            result = await session.execute(stmt_multi_past)
            await session.commit()
            if result.rowcount > 0:
                logger.info("worker.archive.multiday_past", count=result.rowcount)

            # Многодневные события, конец сегодня, время прошло
            stmt_multi_today = (
                sa.update(Event)
                .where(Event.status == "active")
                .where(Event.end_date == now.date())
                .where(Event.end_time.isnot(None))
                .where(Event.end_time < now.time())
                .values(status="past")
            )
            result = await session.execute(stmt_multi_today)
            await session.commit()
            if result.rowcount > 0:
                logger.info("worker.archive.multiday_today", count=result.rowcount)

        except Exception as e:
            logger.error("worker.archive.error", error=str(e))
            await session.rollback()


async def job_cleanup_old_archive() -> None:
    """Удаление архивных событий старше 1 месяца для экономии места."""
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        try:
            # Удаляем события старше 1 месяца (30 дней)
            cutoff_date = datetime.now().date() - timedelta(days=30)

            stmt = (
                sa.delete(Event)
                .where(Event.status == "past")
                .where(Event.date < cutoff_date)
            )
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                logger.info("worker.cleanup_archive", deleted_count=result.rowcount, cutoff_date=str(cutoff_date))

        except Exception as e:
            logger.error("worker.cleanup_archive.error", error=str(e))
            await session.rollback()


async def job_universal_parser() -> None:
    """Universal AI parser - парсит все активные источники."""
    from app.ingestors.universal_parser import process_all_active_sources

    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        try:
            result = await process_all_active_sources(session)
            logger.info(
                "worker.universal_parser.completed",
                sources=result["total_sources"],
                events=result["total_events"],
            )
        except Exception as e:
            logger.error("worker.universal_parser.error", error=str(e))


async def run_queue(stop_event: asyncio.Event) -> None:
    s = get_settings()
    redis = aioredis.from_url(str(s.redis_url), decode_responses=True)
    logger.info("worker.queue.start")
    try:
        while not stop_event.is_set():
            item = None
            try:
                # BRPOP with timeout 10s to allow graceful shutdown
                res = await redis.brpop("ingest:queue", timeout=10)
                if res is None:
                    continue
                _, item = res
                data: dict[str, Any] = json.loads(item)
                kind = data.get("kind")
                if kind == "yandex" and data.get("city"):
                    await job_yandex(str(data["city"]))
                elif kind == "goroda" and data.get("city"):
                    await job_afisha_goroda(str(data["city"]))
                elif kind == "kassa24":
                    await job_kassa24()
                elif kind == "tg":
                    await job_tg()
                else:
                    logger.warning("worker.queue.unknown", item=item)
            except Exception as e:  # noqa: BLE001
                logger.warning("worker.queue.error", error=str(e), item=item)
    finally:
        await redis.aclose()


def _schedule_jobs(scheduler: AsyncIOScheduler) -> None:
    # Remove existing ingest jobs
    for job in list(scheduler.get_jobs()):
        if job.id not in {"reload"}:
            scheduler.remove_job(job.id)

    # Read dynamic config
    y_enabled = bool(rc.get("ingest_yandex_enabled", True))
    g_enabled = bool(rc.get("ingest_goroda_enabled", True))
    k_enabled = bool(rc.get("ingest_kassa_enabled", True))
    t_enabled = bool(rc.get("ingest_tg_enabled", True))
    kudago_enabled = bool(rc.get("ingest_kudago_enabled", True))  # NEW!

    y_hours = float(rc.get("ingest_yandex_hours", 4))
    g_hours = float(rc.get("ingest_goroda_hours", 4))
    k_hours = float(rc.get("ingest_kassa_hours", 4))
    t_minutes = float(rc.get("ingest_tg_minutes", 45))
    kudago_hours = float(rc.get("ingest_kudago_hours", 6))  # NEW!

    y_cities = rc.get("ingest_yandex_cities", ["Севастополь", "Симферополь"]) or [
        "Севастополь",
        "Симферополь",
    ]
    g_cities = rc.get("ingest_goroda_cities", ["Севастополь", "Симферополь"]) or [
        "Севастополь",
        "Симферополь",
    ]
    kudago_cities = rc.get("ingest_kudago_cities", ["Севастополь", "Симферополь", "Ялта"]) or [
        "Севастополь",
        "Симферополь",
        "Ялта",
    ]

    if y_enabled:
        for c in y_cities:
            scheduler.add_job(
                job_yandex,
                IntervalTrigger(hours=max(1, int(y_hours)), jitter=7200),
                id=f"yandex_{c}",
                args=[c],
                replace_existing=True,
            )
    if g_enabled:
        for c in g_cities:
            scheduler.add_job(
                job_afisha_goroda,
                IntervalTrigger(hours=max(1, int(g_hours)), jitter=7200),
                id=f"goroda_{c}",
                args=[c],
                replace_existing=True,
            )
    if k_enabled:
        scheduler.add_job(job_kassa24, IntervalTrigger(hours=max(1, int(k_hours)), jitter=7200), id="kassa24", replace_existing=True)
    if t_enabled:
        scheduler.add_job(job_tg, IntervalTrigger(minutes=max(5, int(t_minutes)), jitter=900), id="tg", replace_existing=True)

    # KudaGo - самый надёжный источник с API
    if kudago_enabled:
        for c in kudago_cities:
            scheduler.add_job(
                job_kudago,
                IntervalTrigger(hours=max(1, int(kudago_hours)), jitter=3600),
                id=f"kudago_{c}",
                args=[c],
                replace_existing=True,
            )
        logger.info("worker.schedule.kudago", cities=kudago_cities, hours=kudago_hours)

    # Архивация прошедших событий каждые 30 минут
    scheduler.add_job(
        job_archive_past_events,
        IntervalTrigger(minutes=30),
        id="archive_past_events",
        replace_existing=True,
    )
    logger.info("worker.schedule.archive_past_events", interval_minutes=30)

    # Cleanup старых архивных событий каждые 24 часа (в 03:00)
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        job_cleanup_old_archive,
        CronTrigger(hour=3, minute=0),  # Каждый день в 3:00
        id="cleanup_old_archive",
        replace_existing=True,
    )
    logger.info("worker.schedule.cleanup_archive", schedule="daily_03:00")

    # Universal AI parser - парсит все активные источники каждые 30 минут
    universal_parser_enabled = bool(rc.get("ingest_universal_parser_enabled", True))
    universal_parser_minutes = float(rc.get("ingest_universal_parser_minutes", 30))

    if universal_parser_enabled:
        scheduler.add_job(
            job_universal_parser,
            IntervalTrigger(minutes=max(5, int(universal_parser_minutes)), jitter=300),
            id="universal_parser",
            replace_existing=True,
        )
        logger.info("worker.schedule.universal_parser", interval_minutes=universal_parser_minutes)


async def main_async() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    scheduler = AsyncIOScheduler()
    _schedule_jobs(scheduler)
    # Reload schedule every 5 minutes to apply admin changes
    scheduler.add_job(lambda: _schedule_jobs(scheduler), IntervalTrigger(minutes=5), id="reload", replace_existing=True)
    scheduler.start()
    logger.info("worker.started")
    stop_event = asyncio.Event()
    queue_task = asyncio.create_task(run_queue(stop_event))
    try:
        # Run forever
        await asyncio.Event().wait()
    finally:
        stop_event.set()
        await queue_task


if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("worker.stopped")
