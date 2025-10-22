"""Validation service for auto-correction and data quality checks.

Performs intelligent validation and auto-fixing of parsed event data.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger(module="validation")


class ValidationService:
    """Service for validating and auto-correcting event data."""

    @staticmethod
    def validate_and_fix_date(
        date_str: str | None,
        event_date: date | None = None,
    ) -> date | None:
        """Validate and auto-correct event date.

        Common fixes:
        - If date is in the past, add 1 year
        - If date is more than 2 years in future, subtract 1 year

        Args:
            date_str: Date string in YYYY-MM-DD format.
            event_date: Parsed date object (if already parsed).

        Returns:
            date | None: Corrected date or None if invalid.
        """
        if not event_date:
            return None

        today = datetime.now().date()
        years_ahead = (event_date - today).days / 365.25

        # If date is in the past (more than 1 day ago)
        if event_date < today - timedelta(days=1):
            # Try adding 1 year
            try:
                corrected = event_date.replace(year=event_date.year + 1)
                logger.info(
                    "validation.date_corrected",
                    original=str(event_date),
                    corrected=str(corrected),
                    reason="date_in_past",
                )
                return corrected
            except ValueError:
                # Handle Feb 29 on non-leap year
                logger.warning("validation.date_correction_failed", date=str(event_date))
                return None

        # If date is more than 2 years in future (likely wrong year)
        if years_ahead > 2:
            try:
                corrected = event_date.replace(year=event_date.year - 1)
                logger.info(
                    "validation.date_corrected",
                    original=str(event_date),
                    corrected=str(corrected),
                    reason="date_too_far_future",
                )
                return corrected
            except ValueError:
                logger.warning("validation.date_correction_failed", date=str(event_date))
                return None

        return event_date

    @staticmethod
    def validate_price_range(
        price_min: int | None,
        price_max: int | None,
    ) -> tuple[int | None, int | None]:
        """Validate and fix price range.

        Fixes:
        - Swap min/max if min > max
        - Set to None if prices are unreasonably high (> 1M rubles)
        - Set to None if prices are negative

        Args:
            price_min: Minimum price in kopecks.
            price_max: Maximum price in kopecks.

        Returns:
            tuple[int | None, int | None]: Corrected (min, max) prices.
        """
        MAX_REASONABLE_PRICE = 100_000_00  # 1M rubles in kopecks

        # Remove negative prices
        if price_min is not None and price_min < 0:
            logger.info("validation.price_invalid", price_min=price_min, reason="negative")
            price_min = None

        if price_max is not None and price_max < 0:
            logger.info("validation.price_invalid", price_max=price_max, reason="negative")
            price_max = None

        # Remove unreasonably high prices
        if price_min is not None and price_min > MAX_REASONABLE_PRICE:
            logger.info("validation.price_invalid", price_min=price_min, reason="too_high")
            price_min = None

        if price_max is not None and price_max > MAX_REASONABLE_PRICE:
            logger.info("validation.price_invalid", price_max=price_max, reason="too_high")
            price_max = None

        # Swap if min > max
        if price_min is not None and price_max is not None and price_min > price_max:
            logger.info(
                "validation.price_swapped",
                original_min=price_min,
                original_max=price_max,
            )
            price_min, price_max = price_max, price_min

        return price_min, price_max

    @staticmethod
    def validate_time_range(
        start_time: dtime | None,
        end_time: dtime | None,
        duration_minutes: int | None = None,
    ) -> tuple[dtime | None, dtime | None, int | None]:
        """Validate and infer missing time information.

        Logic:
        - If end_time < start_time, assume end_time is next day (set to None for simplicity)
        - If duration provided, calculate end_time from start_time
        - If both end_time and duration provided, prefer end_time

        Args:
            start_time: Event start time.
            end_time: Event end time.
            duration_minutes: Event duration in minutes.

        Returns:
            tuple[dtime | None, dtime | None, int | None]: (start, end, duration).
        """
        # If we have start_time and duration but no end_time
        if start_time and duration_minutes and not end_time:
            try:
                start_dt = datetime.combine(date.today(), start_time)
                end_dt = start_dt + timedelta(minutes=duration_minutes)
                end_time = end_dt.time()
                logger.info(
                    "validation.end_time_calculated",
                    start=str(start_time),
                    duration=duration_minutes,
                    end=str(end_time),
                )
            except Exception as e:
                logger.warning("validation.end_time_calculation_failed", error=str(e))

        # If we have start_time and end_time but no duration
        if start_time and end_time and not duration_minutes:
            try:
                start_dt = datetime.combine(date.today(), start_time)
                end_dt = datetime.combine(date.today(), end_time)

                # If end < start, assume it's next day
                if end_dt < start_dt:
                    end_dt = datetime.combine(date.today() + timedelta(days=1), end_time)

                duration = int((end_dt - start_dt).total_seconds() / 60)
                if duration > 0 and duration < 24 * 60:  # Max 24 hours
                    duration_minutes = duration
                    logger.info(
                        "validation.duration_calculated",
                        start=str(start_time),
                        end=str(end_time),
                        duration=duration_minutes,
                    )
            except Exception as e:
                logger.warning("validation.duration_calculation_failed", error=str(e))

        return start_time, end_time, duration_minutes

    @staticmethod
    def validate_capacity(capacity: int | None) -> int | None:
        """Validate venue capacity.

        Args:
            capacity: Venue capacity.

        Returns:
            int | None: Validated capacity or None if invalid.
        """
        if capacity is None:
            return None

        # Capacity must be positive and reasonable (< 1 million)
        if capacity <= 0 or capacity > 1_000_000:
            logger.info("validation.capacity_invalid", capacity=capacity)
            return None

        return capacity

    @staticmethod
    def normalize_address(address: str | None) -> str | None:
        """Normalize address string.

        Fixes:
        - Trim whitespace
        - Remove multiple spaces
        - Standardize "ул." vs "улица"

        Args:
            address: Raw address string.

        Returns:
            str | None: Normalized address.
        """
        if not address:
            return None

        # Trim and normalize whitespace
        normalized = " ".join(address.split())

        # Standardize street abbreviations
        normalized = normalized.replace("улица ", "ул. ")
        normalized = normalized.replace("проспект ", "пр-т ")
        normalized = normalized.replace("переулок ", "пер. ")

        return normalized if normalized else None

    def validate_event_data(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Validate and auto-correct all event fields.

        Args:
            event_data: Raw event data dictionary.

        Returns:
            dict[str, Any]: Validated and corrected event data.
        """
        validated = event_data.copy()

        # Validate date
        if "date" in validated and validated["date"]:
            validated["date"] = self.validate_and_fix_date(
                date_str=None,
                event_date=validated["date"],
            )

        # Validate prices
        if "price_min" in validated or "price_max" in validated:
            price_min, price_max = self.validate_price_range(
                validated.get("price_min"),
                validated.get("price_max"),
            )
            validated["price_min"] = price_min
            validated["price_max"] = price_max

        # Validate time range
        if "time" in validated or "end_time" in validated:
            start_time, end_time, duration = self.validate_time_range(
                validated.get("time"),
                validated.get("end_time"),
                validated.get("duration_minutes"),
            )
            validated["time"] = start_time
            validated["end_time"] = end_time
            validated["duration_minutes"] = duration

        # Validate capacity
        if "capacity" in validated:
            validated["capacity"] = self.validate_capacity(validated.get("capacity"))

        # Normalize address
        if "address" in validated:
            validated["address"] = self.normalize_address(validated.get("address"))

        return validated


# Singleton instance
_validation_service: ValidationService | None = None


def get_validation_service() -> ValidationService:
    """Get singleton validation service instance.

    Returns:
        ValidationService: Shared service instance.
    """
    global _validation_service
    if _validation_service is None:
        _validation_service = ValidationService()
    return _validation_service
