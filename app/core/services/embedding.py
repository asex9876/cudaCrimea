"""Embedding service for semantic search and deduplication.

Uses OpenAI text-embedding-3-small for generating vector representations
of events for similarity matching.
"""

from __future__ import annotations

import math
from typing import Any

import structlog
from openai import OpenAI

from app.core.config import get_settings

logger = structlog.get_logger(module="embedding")


class EmbeddingService:
    """Service for generating embeddings and computing similarity."""

    def __init__(self):
        """Initialize embedding service with OpenAI client."""
        settings = get_settings()

        # Use AI Mediator if configured, otherwise use OpenAI
        if settings.ai_mediator_base_url and settings.ai_mediator_api_key:
            self.client = OpenAI(
                base_url=settings.ai_mediator_base_url,
                api_key=settings.ai_mediator_api_key,
            )
            logger.info("embedding.using_ai_mediator")
        elif settings.openai_api_key:
            self.client = OpenAI(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
            )
            logger.info("embedding.using_openai")
        else:
            raise ValueError("No embedding API configured (need AI Mediator or OpenAI)")

        self.model = "text-embedding-3-small"  # 1536 dimensions, cost-effective

    def generate_event_embedding(
        self,
        title: str,
        date: str | None = None,
        venue: str | None = None,
        description: str | None = None,
    ) -> list[float]:
        """Generate embedding vector for an event.

        Combines key event fields into a text representation for embedding.

        Args:
            title: Event title (required).
            date: Event date in YYYY-MM-DD format.
            venue: Venue name.
            description: Event description.

        Returns:
            list[float]: Embedding vector (1536 dimensions).
        """
        # Build text representation
        parts = [f"Событие: {title}"]
        if date:
            parts.append(f"Дата: {date}")
        if venue:
            parts.append(f"Место: {venue}")
        if description:
            # Truncate long descriptions to avoid token limits
            desc_truncated = description[:500] if len(description) > 500 else description
            parts.append(f"Описание: {desc_truncated}")

        text = " | ".join(parts)

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            embedding = response.data[0].embedding
            logger.info("embedding.generated", text_length=len(text), vector_dim=len(embedding))
            return embedding
        except Exception as e:
            logger.error("embedding.generation_failed", error=str(e), text=text[:100])
            raise

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec_a: First vector.
            vec_b: Second vector.

        Returns:
            float: Similarity score from -1 to 1 (1 = identical, 0 = orthogonal, -1 = opposite).
        """
        if len(vec_a) != len(vec_b):
            raise ValueError(f"Vector dimensions must match: {len(vec_a)} != {len(vec_b)}")

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = math.sqrt(sum(a * a for a in vec_a))
        magnitude_b = math.sqrt(sum(b * b for b in vec_b))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def find_similar_events_simple(
        self,
        query_embedding: list[float],
        candidate_embeddings: list[tuple[Any, list[float]]],
        threshold: float = 0.85,
        limit: int = 5,
    ) -> list[tuple[Any, float]]:
        """Find similar events by comparing embeddings.

        Simple in-memory search for small datasets. For large datasets,
        use PostgreSQL pgvector or external vector DB.

        Args:
            query_embedding: Query event embedding.
            candidate_embeddings: List of (event_id, embedding) tuples.
            threshold: Minimum similarity score (0-1).
            limit: Maximum number of results.

        Returns:
            list[tuple[event_id, similarity_score]]: Similar events sorted by score (descending).
        """
        similarities = []
        for event_id, candidate_emb in candidate_embeddings:
            similarity = self.cosine_similarity(query_embedding, candidate_emb)
            if similarity >= threshold:
                similarities.append((event_id, similarity))

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get singleton embedding service instance.

    Returns:
        EmbeddingService: Shared service instance.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
