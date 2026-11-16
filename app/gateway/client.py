from functools import lru_cache

from app.config import settings


@lru_cache(maxsize=3)
def get_langchain_llm(feature: str = "rag"):
    """Create the configured model client; AWS credentials come from the SDK chain."""
    settings.validate()
    if settings.RAG_PROVIDER == "aws":
        from langchain_aws import ChatBedrockConverse

        model_id = (
            settings.BEDROCK_GUARDRAIL_MODEL_ID
            if feature == "guardrails"
            else settings.BEDROCK_CHAT_MODEL_ID
        )
        return ChatBedrockConverse(
            model=model_id,
            region_name=settings.AWS_REGION,
            temperature=0,
        )

    from langchain_ollama import ChatOllama

    model = (
        settings.OLLAMA_GUARDRAIL_MODEL
        if feature == "guardrails"
        else settings.OLLAMA_CHAT_MODEL
    )
    return ChatOllama(
        model=model,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
    )
