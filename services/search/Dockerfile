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
# any >=2.x constraint and skip reinstalling. All other deps (fastapi, uvicorn,
# sqlalchemy, asyncpg) get installed here.
RUN pip install --no-cache-dir . && pip cache purge

COPY app/ app/

ENV HF_HOME=/app/model_cache

USER appuser

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
