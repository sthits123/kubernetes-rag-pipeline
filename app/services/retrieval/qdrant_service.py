from functools import lru_cache
from urllib.parse import urlparse

import logfire

from app.config import settings
from app.services.retrieval.embedding import embed_query, embed_texts


@lru_cache(maxsize=1)
def _get_local_client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)


@lru_cache(maxsize=1)
def _get_opensearch_client():
    from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

    import boto3

    endpoint = urlparse(settings.OPENSEARCH_ENDPOINT)
    if endpoint.scheme != "https" or not endpoint.hostname:
        raise ValueError("OPENSEARCH_ENDPOINT must be a complete https URL.")

    credentials = boto3.Session(region_name=settings.AWS_REGION).get_credentials()
    if credentials is None:
        raise RuntimeError("AWS credentials were not found in the SDK credential chain.")

    auth = AWSV4SignerAuth(credentials, settings.AWS_REGION, "aoss")
    return OpenSearch(
        hosts=[{"host": endpoint.hostname, "port": endpoint.port or 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30,
        max_retries=3,
        retry_on_timeout=True,
    )


def _ensure_opensearch_index(vector_size: int) -> None:
    client = _get_opensearch_client()
    if client.indices.exists(index=settings.OPENSEARCH_INDEX):
        return

    client.indices.create(
        index=settings.OPENSEARCH_INDEX,
        body={
            "settings": {"index": {"knn": True}},
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": vector_size,
                        "method": {
                            "name": "hnsw",
                            "engine": "faiss",
                            "space_type": "cosinesimil",
                        },
                    },
                    "text": {"type": "text"},
                    "source": {"type": "keyword"},
                }
            },
        },
    )


def index_chunks(chunks: list[dict[str, str]]) -> int:
    if not chunks:
        return 0

    vectors = embed_texts([chunk["text"] for chunk in chunks])
    if settings.RAG_PROVIDER == "aws":
        from opensearchpy import helpers

        _ensure_opensearch_index(len(vectors[0]))
        actions = [
            {
                "_op_type": "index",
                "_index": settings.OPENSEARCH_INDEX,
                "_id": chunk["id"],
                "_source": {
                    "text": chunk["text"],
                    "source": chunk["source"],
                    "embedding": vector,
                },
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        helpers.bulk(_get_opensearch_client(), actions, request_timeout=60)
        return len(actions)

    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = _get_local_client()
    if not client.collection_exists(settings.QDRANT_COLLECTION):
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
        )

    client.upsert(
        collection_name=settings.QDRANT_COLLECTION,
        points=[
            PointStruct(
                id=chunk["id"],
                vector=vector,
                payload={"text": chunk["text"], "source": chunk["source"]},
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    )
    return len(chunks)


def search_enterprise_knowledge(
    query: str,
    limit: int = 8,
):
    """
    Search the enterprise knowledge base using vector similarity.
    """
    query_vector = embed_query(query)

    try:
        if settings.RAG_PROVIDER == "aws":
            response = _get_opensearch_client().search(
                index=settings.OPENSEARCH_INDEX,
                body={
                    "size": limit,
                    "query": {
                        "knn": {
                            "embedding": {
                                "vector": query_vector,
                                "k": limit,
                            }
                        }
                    },
                },
            )
            hits = response["hits"]["hits"]
            return [
                {
                    "content": hit["_source"].get("text", ""),
                    "source": hit["_source"].get("source", "Unknown"),
                    "score": hit.get("_score"),
                }
                for hit in hits
            ]

        response = _get_local_client().query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )
    except Exception as e:
        logfire.error(f"Vector search failed: {e}")
        raise

    results = []

    for res in response.points:
        payload = res.payload or {}

        results.append({
            "content": payload.get("text", ""),
            "source": payload.get("source", "Unknown"),
            "score": res.score,
        })

    return results