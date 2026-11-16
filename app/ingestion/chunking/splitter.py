from typing import List
import logfire

def chunk_text(text: str, chunk_size: int = 1500) -> List[str]:
    """
    Simple semantic-ish chunker that splits by paragraphs.
    Ensures chunks do not exceed the specified size.
    """
    with logfire.span("✂️ Text Chunking", text_length=len(text)):
        if chunk_size < 1:
            raise ValueError("chunk_size must be greater than zero.")
        if not text.strip(): 
            return []

        chunks = []
        current_parts = []
        current_length = 0

        for paragraph in text.split("\n\n"):
            if not paragraph:
                continue
            fragments = [
                paragraph[index:index + chunk_size]
                for index in range(0, len(paragraph), chunk_size)
            ]
            for fragment in fragments:
                separator_length = 2 if current_parts else 0
                if current_length + separator_length + len(fragment) > chunk_size:
                    chunks.append("\n\n".join(current_parts))
                    current_parts = []
                    current_length = 0
                if current_parts:
                    current_length += 2
                current_parts.append(fragment)
                current_length += len(fragment)

        if current_parts:
            chunks.append("\n\n".join(current_parts))
            
        valid_chunks = [c for c in chunks if c.strip()]
        logfire.info(f"✅ Generated {len(valid_chunks)} chunks")
        return valid_chunks