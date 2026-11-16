FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RAG_PROVIDER=aws \
    AWS_REGION=us-east-1 \
    HOST=0.0.0.0

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY ui ./ui

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000 8501

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
