# DEPRECATED: Click model removed in migration 0007, replaced by AdInteraction
# This file is kept for reference only and should not be imported

# from __future__ import annotations
#
# import uuid as _uuid
# from datetime import datetime
#
# import structlog
# from sqlalchemy import insert
# import sqlalchemy as sa
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from app.db.models import Click
#
#
# logger = structlog.get_logger(module="dao.clicks")
#
#
# async def log_click(session: AsyncSession, *, user_tg: int, item_type: str, item_id: str, action: str) -> None:
#     try:
#         await session.execute(
#             insert(Click).values(
#                 {
#                     "id": _uuid.uuid4(),
#                     "user_tg": sa.literal(user_tg, sa.BigInteger()),
#                     "item_type": item_type,
#                     "item_id": _uuid.UUID(item_id),
#                     "action": action,
#                     "ts": datetime.utcnow(),
#                 }
#             )
#         )
#         await session.commit()
#         logger.info("click.logged", user=user_tg, item_type=item_type, action=action)
#     except Exception as e:
#         # Avoid breaking user flow on analytics write errors (e.g., int32 overflow)
#         await session.rollback()
#         logger.warning("click.log_failed", error=str(e))

# TODO: Migrate to AdInteraction model for tracking views, clicks, and conversions
