FROM python:3.11-slim AS base

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser && \
    mkdir -p /app/model_cache && chown -R appuser:appgroup /app/model_cache

COPY pyproject.toml .
# open-clip-torch pulls in torch (CPU build from PyPI). Text encoding via CLIP
# ViT-L/14 runs adequately on CPU — a single text query is <50 ms. The GPU is
# reserved exclusively for the celery-worker image-encoding path.
RUN pip install --no-cache-dir . && pip cache purge

COPY app/ app/

ENV HF_HOME=/app/model_cache

USER appuser

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
