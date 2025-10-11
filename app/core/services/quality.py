"""Quality weights for sources and combined quality calculation."""

from __future__ import annotations

from typing import Mapping


_SOURCE_WEIGHTS: Mapping[str, float] = {
    "afisha": 0.9,
    "yandex": 0.8,
    "kudago": 0.7,
    "2gis": 0.6,
}


def source_weight(source: str | None) -> float:
    """Return base quality weight for a given source name.

    Args:
        source: Source identifier (case-insensitive).

    Returns:
        Weight in [0, 1]. Defaults to 0.5 for unknown sources.
    """

    if not source:
        return 0.5
    return _SOURCE_WEIGHTS.get(source.lower(), 0.5)


def combined_quality(source: str | None, quality_score: float | None) -> float:
    """Combine source weight and content quality into a single score.

    Args:
        source: Source identifier.
        quality_score: Optional quality score (expected 0..1).

    Returns:
        Combined score in [0, 1].
    """

    base = source_weight(source)
    qs = 0.0 if quality_score is None else max(0.0, min(1.0, float(quality_score)))
    return 0.5 * base + 0.5 * qs

