"""
Monetization service: calculates placement prices using dynamic formula.

Formula: Price = ((x * r) * y) * Q

Where:
- x = cost_per_lead (configurable setting)
- r = audience_size (total users / filtered by city / by zone)
- y = conversion_rate (configurable %, depends on targeting precision)
- Q = time_coefficient (urgency multiplier, 3.0 to 1.0 based on time until event)
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tables import MonetizationSettings, User


PlacementType = Literal["broadcast_all", "broadcast_city", "broadcast_zone", "hot"]


class MonetizationService:
    """Service for calculating placement prices and managing monetization settings."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_setting(self, key: str) -> Decimal:
        """Get monetization setting value by key."""
        result = await self.session.execute(
            select(MonetizationSettings.setting_value).where(
                MonetizationSettings.setting_key == key
            )
        )
        value = result.scalar_one_or_none()
        if value is None:
            raise ValueError(f"Monetization setting '{key}' not found")
        return Decimal(str(value))

    async def get_all_settings(self) -> dict[str, Decimal]:
        """Get all monetization settings as a dictionary."""
        result = await self.session.execute(
            select(MonetizationSettings.setting_key, MonetizationSettings.setting_value)
        )
        return {key: Decimal(str(value)) for key, value in result.all()}

    async def update_setting(self, key: str, value: float, updated_by: Optional[str] = None) -> None:
        """Update monetization setting value."""
        result = await self.session.execute(
            select(MonetizationSettings).where(MonetizationSettings.setting_key == key)
        )
        setting = result.scalar_one_or_none()
        if setting is None:
            raise ValueError(f"Monetization setting '{key}' not found")

        setting.setting_value = Decimal(str(value))
        setting.updated_at = datetime.now(timezone.utc)
        if updated_by:
            setting.updated_by = updated_by

        await self.session.commit()

    async def get_audience_size(
        self,
        placement_type: PlacementType,
        target_city: Optional[str] = None,
        target_zone: Optional[str] = None,
    ) -> int:
        """
        Calculate audience size (r) based on placement type and targeting.

        Args:
            placement_type: Type of placement (broadcast_all, broadcast_city, broadcast_zone, hot)
            target_city: City for targeting (required for broadcast_city and broadcast_zone)
            target_zone: Zone/district for targeting (required for broadcast_zone)

        Returns:
            Number of users that will receive the broadcast
        """
        query = select(func.count(User.tg_id))

        if placement_type == "broadcast_all":
            # All active users
            pass
        elif placement_type == "broadcast_city":
            if not target_city:
                raise ValueError("target_city is required for broadcast_city placement")
            query = query.where(User.city == target_city)
        elif placement_type == "broadcast_zone":
            if not target_city or not target_zone:
                raise ValueError("target_city and target_zone are required for broadcast_zone placement")
            query = query.where(User.city == target_city, User.zone == target_zone)
        elif placement_type == "hot":
            # For "hot" placements, we broadcast to all users
            pass

        result = await self.session.execute(query)
        return result.scalar_one() or 0

    def get_time_coefficient(
        self,
        event_datetime: datetime,
        placement_type: PlacementType,
        settings: dict[str, Decimal],
    ) -> Decimal:
        """
        Calculate time coefficient (Q) based on time until event.

        Time ranges (from event start):
        - less_2h: < 2 hours → Q = 3.0
        - 2h_6h: 2-6 hours → Q = 2.7
        - 6h_12h: 6-12 hours → Q = 2.2
        - 12h_24h: 12-24 hours → Q = 2.0
        - 24h_30h: 24-30 hours → Q = 1.8
        - 30h_36h: 30-36 hours → Q = 1.5
        - 36h_48h: 36-48 hours → Q = 1.3
        - more_48h: > 48 hours → Q = 1.0
        - hot: Special "hot" placement → Q = 1.0 (fixed)

        Args:
            event_datetime: When the event starts
            placement_type: Type of placement
            settings: All monetization settings

        Returns:
            Time coefficient Q
        """
        # "Hot" placements always have Q = 1.0
        if placement_type == "hot":
            return settings["q_hot"]

        # Calculate time delta in hours
        now = datetime.now(timezone.utc)
        if event_datetime.tzinfo is None:
            # Assume UTC if no timezone
            event_datetime = event_datetime.replace(tzinfo=timezone.utc)

        hours_until_event = (event_datetime - now).total_seconds() / 3600

        # Determine Q coefficient based on time range
        if hours_until_event < 2:
            return settings["q_less_2h"]
        elif hours_until_event < 6:
            return settings["q_2h_6h"]
        elif hours_until_event < 12:
            return settings["q_6h_12h"]
        elif hours_until_event < 24:
            return settings["q_12h_24h"]
        elif hours_until_event < 30:
            return settings["q_24h_30h"]
        elif hours_until_event < 36:
            return settings["q_30h_36h"]
        elif hours_until_event < 48:
            return settings["q_36h_48h"]
        else:
            return settings["q_more_48h"]

    def get_conversion_rate(
        self,
        placement_type: PlacementType,
        settings: dict[str, Decimal],
    ) -> Decimal:
        """
        Get conversion rate (y) based on placement type.

        Args:
            placement_type: Type of placement
            settings: All monetization settings

        Returns:
            Conversion rate as decimal (e.g., 3.00 for 3%)
        """
        if placement_type == "broadcast_all" or placement_type == "hot":
            return settings["conversion_general"]
        elif placement_type == "broadcast_city":
            return settings["conversion_city"]
        elif placement_type == "broadcast_zone":
            return settings["conversion_zone"]
        else:
            return settings["conversion_general"]

    async def calculate_placement_price(
        self,
        placement_type: PlacementType,
        event_datetime: datetime,
        target_city: Optional[str] = None,
        target_zone: Optional[str] = None,
    ) -> dict:
        """
        Calculate placement price using formula: Price = ((x * r) * y) * Q

        Args:
            placement_type: Type of placement
            event_datetime: When the event starts
            target_city: Target city (for city/zone broadcasts)
            target_zone: Target zone (for zone broadcasts)

        Returns:
            Dictionary with:
            - price: Final calculated price (rubles)
            - cost_per_lead: x (setting)
            - audience_size: r (calculated)
            - conversion_rate: y (setting, %)
            - time_coefficient: Q (calculated)
            - breakdown: Human-readable formula breakdown
        """
        # Get all settings
        settings = await self.get_all_settings()

        # Get components
        x = settings["cost_per_lead"]  # Cost per lead (rubles)
        r = await self.get_audience_size(placement_type, target_city, target_zone)  # Audience size
        y = self.get_conversion_rate(placement_type, settings)  # Conversion rate (%)
        Q = self.get_time_coefficient(event_datetime, placement_type, settings)  # Time coefficient

        # Calculate price: ((x * r) * y) * Q
        # y is in percent, so divide by 100
        y_decimal = y / Decimal("100")
        price = ((x * Decimal(str(r))) * y_decimal) * Q

        # Round to 2 decimal places
        price = price.quantize(Decimal("0.01"))

        return {
            "price": float(price),
            "cost_per_lead": float(x),
            "audience_size": r,
            "conversion_rate": float(y),
            "time_coefficient": float(Q),
            "breakdown": (
                f"Price = ((x * r) * y) * Q\n"
                f"Price = (({x} * {r}) * {y}%) * {Q}\n"
                f"Price = {price} руб."
            ),
        }
