import ollama

def embed_query(query: str) -> list[float]:
    response = ollama.embeddings(
        model="nomic-embed-text",
        prompt=query
    )
    return response["embedding"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [embed_query(text) for text in texts]