"""Delete all events from the database."""

import asyncio
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.session import get_sessionmaker
from app.db.models import Event
import sqlalchemy as sa


async def delete_all_events():
    """Delete all events from database."""
    ss = get_sessionmaker()
    async with ss() as session:
        # Get statistics before deletion
        print("📊 Current database statistics:\n")

        stats = await session.execute(
            sa.select(Event.status, sa.func.count(Event.id))
            .group_by(Event.status)
        )

        total = 0
        for status, count in stats:
            print(f"  {status or '(no status)'}: {count} events")
            total += count

        print(f"\n  TOTAL: {total} events")

        if total == 0:
            print("\n✅ Database is already empty - no events to delete")
            return

        # Confirm deletion
        print(f"\n⚠️  WARNING: This will DELETE ALL {total} events!")
        confirm = input("Type 'DELETE ALL' to confirm: ")

        if confirm != "DELETE ALL":
            print("\n❌ Deletion cancelled")
            return

        # Delete all events
        print(f"\n🗑️  Deleting {total} events...")

        result = await session.execute(sa.delete(Event))
        await session.commit()

        deleted_count = result.rowcount

        print(f"\n✅ Successfully deleted {deleted_count} events")
        print("Database is now empty")


if __name__ == "__main__":
    print("🗑️  DELETE ALL EVENTS\n")
    print("=" * 60)
    asyncio.run(delete_all_events())
