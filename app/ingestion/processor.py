import argparse
import tempfile
import uuid
from pathlib import Path, PurePosixPath

import logfire

from app.config import settings
from app.ingestion.chunking.splitter import chunk_text
from app.ingestion.loaders.html import parse_html
from app.ingestion.loaders.office import parse_office
from app.ingestion.loaders.pdf import parse_pdf
from app.ingestion.loaders.text import parse_text
from app.services.retrieval.qdrant_service import index_chunks

SUPPORTED_EXTENSIONS = {".docx", ".html", ".htm", ".md", ".pdf", ".pptx", ".txt"}


def _parse_document(path: Path) -> str:
    extension = path.suffix.lower()
    if extension == ".pdf":
        return parse_pdf(str(path))
    if extension in {".docx", ".pptx"}:
        return parse_office(str(path))
    if extension in {".html", ".htm"}:
        return parse_html(str(path))
    if extension in {".md", ".txt"}:
        return parse_text(str(path))
    return ""


def ingest_directory(directory: str | Path, *, upload_sources: bool = True) -> int:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Document directory does not exist: {root}")

    settings.validate()
    ingested_chunks = 0
    pending_chunks: list[dict[str, str]] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        text = _parse_document(path)
        relative_source = path.relative_to(root).as_posix()
        if settings.RAG_PROVIDER == "aws" and upload_sources:
            import boto3

            object_key = "/".join(
                part.strip("/")
                for part in (settings.S3_DOCUMENT_PREFIX, relative_source)
                if part.strip("/")
            )
            boto3.client("s3", region_name=settings.AWS_REGION).upload_file(
                str(path),
                settings.S3_BUCKET,
                object_key,
            )

        for chunk_index, chunk in enumerate(chunk_text(text)):
            pending_chunks.append(
                {
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{relative_source}:{chunk_index}",
                        )
                    ),
                    "text": chunk,
                    "source": relative_source,
                }
            )
            if len(pending_chunks) == 64:
                ingested_chunks += index_chunks(pending_chunks)
                pending_chunks.clear()

    if pending_chunks:
        ingested_chunks += index_chunks(pending_chunks)

    if not ingested_chunks:
        raise ValueError(
            f"No supported document text found in {root}. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    return ingested_chunks


def ingest_s3_prefix(prefix: str) -> int:
    if settings.RAG_PROVIDER != "aws":
        raise ValueError("S3 ingestion is available only when RAG_PROVIDER=aws.")
    settings.validate()

    import boto3

    normalized_prefix = prefix.strip("/")
    if normalized_prefix:
        normalized_prefix += "/"

    s3 = boto3.client("s3", region_name=settings.AWS_REGION)
    paginator = s3.get_paginator("list_objects_v2")
    with tempfile.TemporaryDirectory(prefix="rag-ingest-") as temp_dir:
        root = Path(temp_dir).resolve()
        downloaded = 0
        for page in paginator.paginate(
            Bucket=settings.S3_BUCKET,
            Prefix=normalized_prefix,
        ):
            for item in page.get("Contents", []):
                key = item["Key"]
                if Path(key).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                relative_key = key[len(normalized_prefix):] if normalized_prefix else key
                relative_path = PurePosixPath(relative_key)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ValueError(f"Unsafe document key in S3: {key!r}")

                local_path = root.joinpath(*relative_path.parts).resolve()
                if root not in local_path.parents:
                    raise ValueError(f"Unsafe document key in S3: {key!r}")
                local_path.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(settings.S3_BUCKET, key, str(local_path))
                downloaded += 1

        if not downloaded:
            raise ValueError(
                f"No supported documents found in s3://{settings.S3_BUCKET}/{normalized_prefix}"
            )
        return ingest_directory(root, upload_sources=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse, embed, and load documents into the configured vector store."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path("data"),
        help="Directory containing documents (default: ./data)",
    )
    parser.add_argument(
        "--s3-prefix",
        help="Ingest supported documents already stored under this S3 bucket prefix.",
    )
    args = parser.parse_args()

    count = (
        ingest_s3_prefix(args.s3_prefix)
        if args.s3_prefix is not None
        else ingest_directory(args.directory)
    )
    if settings.RAG_PROVIDER == "aws":
        logfire.info(
            f"Ingested {count} chunks into OpenSearch index "
            f"{settings.OPENSEARCH_INDEX!r} and uploaded source files to S3."
        )
        print(
            f"Ingested {count} chunks into {settings.OPENSEARCH_INDEX}; "
            f"source documents stored in s3://{settings.S3_BUCKET}/"
        )
    else:
        logfire.info(
            f"Ingested {count} chunks into Qdrant collection "
            f"{settings.QDRANT_COLLECTION!r}."
        )
        print(f"Ingested {count} chunks into {settings.QDRANT_COLLECTION}.")


if __name__ == "__main__":
    main()
