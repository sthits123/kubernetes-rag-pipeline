import hashlib
import json
import os
from typing import Optional

import numpy as np
import redis
import logfire

from app.services.retrieval.embedding import embed_query


# ---------------------------------------------------------
# Redis configuration
# ---------------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

CACHE_TTL = int(
    os.getenv("SEMANTIC_CACHE_TTL", "3600")
)

SIMILARITY_THRESHOLD = float(
    os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92")
)

CACHE_PREFIX = "semantic_cache:"


redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _cosine_similarity(
    a: list[float],
    b: list[float],
) -> float:
    """
    Calculate cosine similarity between two vectors.
    """

    a_vec = np.array(a, dtype=np.float32)
    b_vec = np.array(b, dtype=np.float32)

    denominator = (
        np.linalg.norm(a_vec)
        * np.linalg.norm(b_vec)
    )

    if denominator == 0:
        return 0.0

    return float(
        np.dot(a_vec, b_vec) / denominator
    )


def _cache_key(query: str) -> str:
    """
    Generate a deterministic Redis key for a query.
    """

    query_hash = hashlib.sha256(
        query.strip().lower().encode()
    ).hexdigest()

    return f"{CACHE_PREFIX}{query_hash}"


# ---------------------------------------------------------
# Cache lookup
# ---------------------------------------------------------

def check_cache(query: str) -> Optional[str]:
    """
    Check Redis for a semantically similar cached query.

    Returns:
        Cached answer if similarity >= threshold.
        None otherwise.
    """

    try:
        query_embedding = embed_query(query)

        keys = redis_client.scan_iter(
            match=f"{CACHE_PREFIX}*"
        )

        best_score = 0.0
        best_answer = None

        for key in keys:
            raw = redis_client.get(key)

            if not raw:
                continue

            try:
                cached = json.loads(raw)

                cached_embedding = cached["embedding"]
                cached_answer = cached["answer"]

                similarity = _cosine_similarity(
                    query_embedding,
                    cached_embedding,
                )

                if similarity > best_score:
                    best_score = similarity
                    best_answer = cached_answer

            except (json.JSONDecodeError, KeyError):
                continue

        logfire.info(
            f"🧠 Semantic cache similarity: {best_score:.4f}"
        )

        if best_score >= SIMILARITY_THRESHOLD:
            logfire.info(
                f"⚡ Semantic cache HIT "
                f"(similarity={best_score:.4f})"
            )

            return best_answer

        logfire.info(
            f"❌ Semantic cache MISS "
            f"(similarity={best_score:.4f})"
        )

        return None

    except Exception as e:
        logfire.warning(
            f"⚠️ Semantic cache lookup failed: {e}"
        )

        return None


# ---------------------------------------------------------
# Store cache
# ---------------------------------------------------------

def set_cache(
    query: str,
    answer: str,
) -> None:
    """
    Store a query, its embedding and answer in Redis.
    """

    try:
        embedding = embed_query(query)

        key = _cache_key(query)

        value = {
            "query": query,
            "embedding": embedding,
            "answer": answer,
        }

        redis_client.setex(
            key,
            CACHE_TTL,
            json.dumps(value),
        )

        logfire.info(
            f"💾 Semantic cache stored | "
            f"ttl={CACHE_TTL}s"
        )

    except Exception as e:
        logfire.warning(
            f"⚠️ Failed to store semantic cache: {e}"
        )