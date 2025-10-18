"""Fix events with missing or NULL status in database."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import get_sessionmaker
from app.db.models import Event
import sqlalchemy as sa


async def fix_statuses():
    """Set default status for events without one."""
    ss = get_sessionmaker()
    async with ss() as session:
        # Find events with NULL or empty status
        result = await session.execute(
            sa.select(Event).where(
                sa.or_(
                    Event.status == None,  # noqa: E711
                    Event.status == "",
                )
            )
        )
        events = result.scalars().all()

        if not events:
            print("✅ All events have valid status")
            return

        print(f"Found {len(events)} events without status")

        # Update each event
        now = datetime.now()
        for event in events:
            # Determine appropriate status based on date
            if event.date < now.date():
                event.status = "past"
                print(f"  - {event.title[:50]}: set to 'past' (date: {event.date})")
            elif event.date == now.date() and event.time and event.time < now.time():
                event.status = "past"
                print(f"  - {event.title[:50]}: set to 'past' (time: {event.time})")
            else:
                event.status = "active"
                print(f"  - {event.title[:50]}: set to 'active' (date: {event.date})")

        await session.commit()
        print(f"\n✅ Updated {len(events)} events")

        # Show statistics
        stats = await session.execute(
            sa.select(Event.status, sa.func.count(Event.id))
            .group_by(Event.status)
        )
        print("\nStatus distribution:")
        for status, count in stats:
            print(f"  {status or '(empty)'}: {count}")


if __name__ == "__main__":
    print("🔧 Fixing event statuses...\n")
    asyncio.run(fix_statuses())
