import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Vector DB (Qdrant) ---
    QDRANT_URL = os.getenv("QDRANT_URL") or os.getenv(
        "QDRANT_CLUSTER_ENDPOINT", "http://localhost:6333"
    )
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kubernetes_rag")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_FALLBACK_API_KEY = os.getenv("GROQ_FALLBACK_API_KEY")
    GROQ_MODEL = "llama-3.3-70b-versatile"

    PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")
    PORTKEY_CONFIG_ID = os.getenv("PORTKEY_CONFIG_ID")
    GROQ_SLUG = "rag"     # primary virtual key: @rag/llama-3.3-70b-versatile
    GROQ_SLUG_2 = "brag"  # fallback virtual key: @brag/llama-3.1-8b-instant

    # --- Guardrails (NVIDIA) ---
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

    # --- Postgres Memory ---
    DB_HOST = os.getenv("DB_HOST")                # /cloudsql/... (Cloud Run) or hostname (local)
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_NAME = os.getenv("DB_NAME", "rag_memory")
    LOCAL_MODE = os.getenv("LOCAL_MODE", "true").lower() == "true"

    # --- Redis Semantic Cache ---
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    USE_SEMANTIC_CACHE = os.getenv("USE_SEMANTIC_CACHE", "false").lower() == "true"

    



settings = Settings()