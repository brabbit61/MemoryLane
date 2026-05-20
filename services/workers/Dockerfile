FROM python:3.11-slim AS base

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser && \
    mkdir -p /app/model_cache && chown -R appuser:appgroup /app/model_cache

# Pin torch to a cu121 wheel compatible with NVIDIA driver 535+ (CUDA 12.2).
# Newer torch wheels (cu130) require driver 550+, which not all dev hosts have.
# Bundles its own CUDA runtime; host provides libcuda.so.1 via nvidia-container-toolkit.
RUN pip install --no-cache-dir \
    "torch==2.5.1" \
    --index-url https://download.pytorch.org/whl/cu121 \
    && pip cache purge

COPY pyproject.toml .
# torch is already installed from the CUDA wheel above; pip will see it satisfies
# the >=2.2.0 constraint and skip reinstalling. All other deps (celery, sqlalchemy,
# psycopg2, boto3, open-clip, pgvector, Pillow) get installed here.
RUN pip install --no-cache-dir . && pip cache purge

COPY app/ app/

USER appuser

# --concurrency=1: CLIP ViT-L/14 loads its own ~1.5 GB on the GPU per worker
# process. Forking 16 of them OOMs anything smaller than a 24 GB card.
CMD ["celery", "-A", "app.worker", "worker", "--loglevel=info", "-Q", "enrichment", "--concurrency=1"]
