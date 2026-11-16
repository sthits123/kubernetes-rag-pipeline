import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime settings shared by local development and the ECS task role."""

    RAG_PROVIDER: str = os.getenv("RAG_PROVIDER", "local").strip().lower()
    AWS_REGION: str = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    BEDROCK_CHAT_MODEL_ID: str = os.getenv(
        "BEDROCK_CHAT_MODEL_ID", "amazon.nova-lite-v1:0"
    )
    BEDROCK_GUARDRAIL_MODEL_ID: str = os.getenv(
        "BEDROCK_GUARDRAIL_MODEL_ID", "amazon.nova-lite-v1:0"
    )
    BEDROCK_EMBEDDING_MODEL_ID: str = os.getenv(
        "BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
    )
    BEDROCK_EMBEDDING_DIMENSIONS: int = int(
        os.getenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024")
    )
    OPENSEARCH_ENDPOINT: str = os.getenv("OPENSEARCH_ENDPOINT", "")
    OPENSEARCH_INDEX: str = os.getenv("OPENSEARCH_INDEX", "kubernetes-rag")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_DOCUMENT_PREFIX: str = os.getenv("S3_DOCUMENT_PREFIX", "documents")

    # Explicit local-only adapters. They are installed through the `local` extra.
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_CHAT_MODEL: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")
    OLLAMA_GUARDRAIL_MODEL: str = os.getenv(
        "OLLAMA_GUARDRAIL_MODEL", os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")
    )
    OLLAMA_EMBEDDING_MODEL: str = os.getenv(
        "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"
    )
    QDRANT_URL: str = os.getenv(
        "QDRANT_URL",
        os.getenv("QDRANT_CLUSTER_ENDPOINT", "http://localhost:6333"),
    )
    QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "kubernetes_rag")

    USE_SEMANTIC_CACHE: bool = _env_bool("USE_SEMANTIC_CACHE")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    LOGFIRE_TOKEN: str | None = os.getenv("LOGFIRE_TOKEN")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    RELOAD: bool = _env_bool("RELOAD")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

    def validate(self) -> None:
        if self.RAG_PROVIDER not in {"local", "aws"}:
            raise ValueError("RAG_PROVIDER must be either 'local' or 'aws'.")
        if self.RAG_PROVIDER == "aws":
            missing = [
                name
                for name, value in (
                    ("OPENSEARCH_ENDPOINT", self.OPENSEARCH_ENDPOINT),
                    ("S3_BUCKET", self.S3_BUCKET),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "AWS mode requires " + ", ".join(missing) + "."
                )
        if self.BEDROCK_EMBEDDING_DIMENSIONS < 1:
            raise ValueError("BEDROCK_EMBEDDING_DIMENSIONS must be positive.")


settings = Settings()
