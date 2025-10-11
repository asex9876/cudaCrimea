"""Interest and budget matching utilities.

Interprets user preferences (from JSONB) to compute match scores
for events and places. Scores are in [0, 1].
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


def _get_list(pref: Mapping[str, Any], key: str) -> list[str]:
    v = pref.get(key)
    if isinstance(v, list):
        return [str(x).lower() for x in v]
    if isinstance(v, str):
        return [v.lower()]
    return []


def _budget_ok(prefs: Mapping[str, Any], price_min: Optional[int], price_max: Optional[int]) -> float:
    max_budget = prefs.get("budget_max")
    if max_budget is None:
        return 1.0
    try:
        max_budget_f = float(max_budget)
    except (TypeError, ValueError):
        return 1.0

    if price_min is None and price_max is None:
        return 1.0
    price = float(price_min if price_min is not None else price_max)  # type: ignore[union-attr]
    return 1.0 if price <= max_budget_f else 0.0


def event_match(prefs: Mapping[str, Any], category: str, price_min: Optional[int], price_max: Optional[int]) -> float:
    """Compute event interest match score.

    Args:
        prefs: User preferences mapping.
        category: Event category.
        price_min: Minimal price if known.
        price_max: Maximal price if known.

    Returns:
        Score in [0, 1].
    """

    categories = _get_list(prefs, "event_categories")
    cat_ok = 1.0 if (not categories or category.lower() in categories) else 0.0
    budget = _budget_ok(prefs, price_min, price_max)
    return 0.7 * cat_ok + 0.3 * budget


def place_match(prefs: Mapping[str, Any], category: str, price_level: Optional[int], rating: Optional[float]) -> float:
    """Compute place interest match score.

    Args:
        prefs: User preferences mapping.
        category: Place category.
        price_level: Place price level (0..5 typical).
        rating: Optional rating (0..5).

    Returns:
        Score in [0, 1].
    """

    categories = _get_list(prefs, "place_categories")
    cat_ok = 1.0 if (not categories or category.lower() in categories) else 0.0

    max_price = prefs.get("price_level_max")
    if max_price is None or price_level is None:
        price_ok = 1.0
    else:
        try:
            price_ok = 1.0 if int(price_level) <= int(max_price) else 0.0
        except (TypeError, ValueError):
            price_ok = 1.0

    # light preference for higher ratings if provided
    rating_norm = 0.0 if rating is None else max(0.0, min(1.0, float(rating) / 5.0))
    return 0.6 * cat_ok + 0.3 * price_ok + 0.1 * rating_norm

