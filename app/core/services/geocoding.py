"""Geocoding service using Nominatim (OpenStreetMap).

Provides address geocoding with caching to respect rate limits.
Uses free Nominatim API with 1 request/second limit.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tables import GeocodingCache

logger = structlog.get_logger()


class GeocodingService:
    """Service for geocoding addresses using Nominatim with caching."""

    # Rate limiting: 1 request per second for public Nominatim
    _last_request_time: float = 0
    _rate_limit_delay: float = 1.0

    def __init__(self, session: AsyncSession):
        """Initialize geocoding service.

        Args:
            session: Database session for caching.
        """
        self.session = session

    @classmethod
    async def _rate_limit(cls) -> None:
        """Ensure we don't exceed Nominatim rate limit (1 req/sec)."""
        current_time = time.time()
        elapsed = current_time - cls._last_request_time
        if elapsed < cls._rate_limit_delay:
            await asyncio.sleep(cls._rate_limit_delay - elapsed)
        cls._last_request_time = time.time()

    async def geocode_address(
        self,
        address: str,
        city: str | None = None,
    ) -> tuple[float, float, str | None] | None:
        """Geocode an address to coordinates and district.

        Args:
            address: Address to geocode (e.g., "ул. Ленина, 10").
            city: City name for better accuracy (e.g., "Севастополь").

        Returns:
            Tuple of (latitude, longitude, district) or None if not found.
        """
        # Build full query
        query_parts = [address]
        if city:
            query_parts.append(city)
        query_parts.append("Крым")
        full_query = ", ".join(query_parts)

        # Check cache first
        cache_key = full_query.lower().strip()
        cached = await self.session.execute(
            select(GeocodingCache).where(GeocodingCache.query == cache_key)
        )
        cached_result = cached.scalar_one_or_none()

        if cached_result:
            logger.info("geocoding.cache_hit", query=cache_key)
            return (
                float(cached_result.lat),
                float(cached_result.lon),
                cached_result.district,
            )

        # Not in cache - call Nominatim
        logger.info("geocoding.api_call", query=full_query)
        await self._rate_limit()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Use Nominatim API
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    "q": full_query,
                    "format": "json",
                    "addressdetails": "1",
                    "limit": "1",
                }
                headers = {
                    "User-Agent": "CudaCrimea/1.0 (Event aggregator bot)",
                }

                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                if not data or len(data) == 0:
                    logger.warning("geocoding.not_found", query=full_query)
                    return None

                result = data[0]
                lat = float(result["lat"])
                lon = float(result["lon"])

                # Extract district from address details
                address_details = result.get("address", {})
                district = (
                    address_details.get("suburb")
                    or address_details.get("neighbourhood")
                    or address_details.get("district")
                    or address_details.get("quarter")
                )

                # Cache the result
                cache_entry = GeocodingCache(
                    query=cache_key,
                    lat=lat,
                    lon=lon,
                    district=district,
                    raw_response=result,
                )
                self.session.add(cache_entry)
                await self.session.commit()

                logger.info(
                    "geocoding.success",
                    query=full_query,
                    lat=lat,
                    lon=lon,
                    district=district,
                )

                return (lat, lon, district)

        except Exception as e:
            logger.error("geocoding.error", query=full_query, error=str(e))
            return None

    async def reverse_geocode(
        self, lat: float, lon: float
    ) -> dict[str, str | None] | None:
        """Reverse geocode coordinates to address details.

        Args:
            lat: Latitude.
            lon: Longitude.

        Returns:
            Dictionary with address components or None.
        """
        logger.info("reverse_geocoding.api_call", lat=lat, lon=lon)
        await self._rate_limit()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = "https://nominatim.openstreetmap.org/reverse"
                params = {
                    "lat": str(lat),
                    "lon": str(lon),
                    "format": "json",
                    "addressdetails": "1",
                }
                headers = {
                    "User-Agent": "CudaCrimea/1.0 (Event aggregator bot)",
                }

                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                address = data.get("address", {})
                return {
                    "city": address.get("city") or address.get("town"),
                    "district": (
                        address.get("suburb")
                        or address.get("neighbourhood")
                        or address.get("district")
                        or address.get("quarter")
                    ),
                    "road": address.get("road"),
                    "house_number": address.get("house_number"),
                }

        except Exception as e:
            logger.error("reverse_geocoding.error", lat=lat, lon=lon, error=str(e))
            return None
