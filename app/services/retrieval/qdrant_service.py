import logfire
from qdrant_client import QdrantClient

from app.config import settings
from app.services.retrieval.embedding import embed_query


# Initialize Qdrant client
client = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY,
)


def search_enterprise_knowledge(
    query: str,
    limit: int = 8,
):
    """
    Search the enterprise knowledge base using vector similarity.
    """
    try:
        # Convert query into embedding
        query_vector = embed_query(query)

        # Search Qdrant
        response = client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )

        results = []

        for res in response.points:
            payload = res.payload or {}

            results.append({
                "content": payload.get("text", ""),
                "source": payload.get("source", "Unknown"),
                "score": res.score,
            })

        return results

    except Exception as e:
        logfire.error(f"Qdrant search failed: {e}")
        return []