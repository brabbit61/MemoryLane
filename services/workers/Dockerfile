FROM python:3.11-slim AS base

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# CUDA 12.1 torch — separate layer for Docker cache; bundles its own CUDA runtime
# Host provides libcuda.so.1 via nvidia-container-toolkit
RUN pip install --no-cache-dir \
    "torch>=2.2.0" \
    --index-url https://download.pytorch.org/whl/cu121 \
    && pip cache purge

COPY pyproject.toml .
RUN pip install --no-cache-dir --no-deps . && pip cache purge

COPY app/ app/

USER appuser

CMD ["celery", "-A", "app.worker", "worker", "--loglevel=info", "-Q", "enrichment"]
