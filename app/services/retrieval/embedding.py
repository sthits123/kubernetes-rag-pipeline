from functools import lru_cache

from app.config import settings


@lru_cache(maxsize=1)
def _embedding_client():
    settings.validate()
    if settings.RAG_PROVIDER == "aws":
        from langchain_aws import BedrockEmbeddings

        return BedrockEmbeddings(
            model_id=settings.BEDROCK_EMBEDDING_MODEL_ID,
            region_name=settings.AWS_REGION,
            dimensions=settings.BEDROCK_EMBEDDING_DIMENSIONS,
        )

    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(
        model=settings.OLLAMA_EMBEDDING_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
    )


def embed_query(query: str) -> list[float]:
    if not query.strip():
        raise ValueError("Cannot embed an empty query.")
    return _embedding_client().embed_query(query)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _embedding_client().embed_documents(texts)
