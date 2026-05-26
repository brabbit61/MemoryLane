# MemoryLane — Project Status & Roadmap

## Phase Overview

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 0** | Foundations: monorepo, docker-compose, Terraform skeleton, API gateway, CI | ✅ Complete |
| **Phase 1** | Google Photos ingestion + CLIP GPU enrichment + pgvector writes | ✅ Complete |
| **Phase 1b** | S3 Terraform applied; search-svc scaffold, CLIP text encoding, GET /search endpoint | ✅ Complete |
| Phase 2 | Face detection, event clustering, duplicate detection | Planned |
| Phase 3 | LangGraph Search Agent, AutoGen Conversational Agent, web UI | 🚧 In Progress |
| Phase 4 | BLIP-2 captions, LangGraph Album Generation Graph (supervisor), DPO data collection | Planned |
| Phase 5 | Deep agent capabilities: plan-and-execute, reflection, HITL, chaos evals | Planned |
| Phase 6 | DPO reranker training pipeline | Planned |
| Phase 7 | Hardening: Grafana, guardrails, adversarial eval, multi-tenancy audit | Planned |
| Phase 8 | Demo library, live URL, blog post, demo video | Planned |

---

## What's Been Built

### Phase 0 — Foundations

- **Monorepo structure**: `src/` (microservices + UI), `infra/` (Terraform + DB), `docs/` (ADRs), `.github/` (CI)
- **docker-compose**: Postgres 16 + pgvector, Redis 7, MinIO (S3-compatible), api-gateway, ingestion-svc, celery-worker with NVIDIA GPU passthrough
- **API Gateway** (`src/api-gateway`): FastAPI hello-world with health + readiness endpoints, async SQLAlchemy, pydantic-settings
- **Database schema**: `tenants`, `users`, `photos`, `photo_embeddings` (HNSW index on 768-dim vector), `oauth_tokens`; Row-Level Security enabled
- **Terraform** — `module.s3` deployed (photos + model-artifacts buckets). VPC, EKS, RDS, Cognito, ECR modules will be added in Phase 2.
- **CI (GitHub Actions)**:
  - PR: ruff lint + format, mypy, bandit security scan, pytest, docker build
  - Main: full test suite (workers excluded — requires GPU)

### Phase 1 — Google Photos Ingestion + CLIP Enrichment

**Ingestion service** (`src/ingestion`, port 8001):
- OAuth 2.0 with PKCE using the Photos Picker API (`photospicker.mediaitems.readonly`)
- Tokens stored in Postgres with refresh support
- Endpoints:
  - `GET /oauth/google/init` — generates Picker OAuth URL, stores PKCE verifier in Redis (TTL 600s)
  - `GET /oauth/google/callback` — exchanges code, upserts `oauth_tokens`
  - `POST /sync/google/{user_id}/start` — creates a Picker session, returns `picker_uri`
  - `POST /sync/google/{user_id}/ingest/{session_id}` — downloads selected photos, uploads to S3, dispatches enrichment tasks

**Enrichment worker** (`src/workers`):
- Celery consumer on `enrichment` queue, `prefetch_multiplier=1` (one task at a time per GPU worker)
- Generates 256px + 1024px thumbnails (Pillow LANCZOS)
- Extracts EXIF metadata (DateTimeOriginal, GPS, dimensions, camera make/model)
- Runs CLIP ViT-L/14 inference on NVIDIA GPU — ~50 ms/image vs ~2–5 s on CPU
- Writes 768-dim L2-normalized embedding to `photo_embeddings` via pgvector

**End-to-end verified locally**: 7 photos ingested → MinIO S3 → CLIP GPU enrichment → pgvector; self-similarity = 1.0000

### Phase 1b — S3 Terraform + Search Service Foundation

AWS S3 buckets were provisioned via Terraform (`module.s3`). A new `search-svc` (port 8002) was built end-to-end: GPU-capable FastAPI scaffold with async SQLAlchemy, a CLIP ViT-L/14 text encoding module (`encode_text(query) -> list[float]`, 768-dim), and a `GET /search` endpoint that encodes the query, runs a pgvector cosine ANN query over `photo_embeddings`, and returns ranked results with 1-hour pre-signed S3 URLs. Pre-signed URL generation uses sync boto3 and switches between MinIO and real AWS S3 via a single env var. The service is covered by unit tests (mocked CLIP model — no GPU in CI) and wired into docker-compose and the CI matrix.

---

## Known Gaps

| Gap | Detail | Planned fix |
|-----|--------|-------------|
| `taken_at` is null | Picker API download URL doesn't include EXIF creation time; requires a separate call to `sessions.mediaItems.list` for `creationTime` | Phase 2 |
| Search not wired through api-gateway | `GET /search` is served directly from search-svc (port 8002); the api-gateway proxy layer is not yet added | Phase 3 |
| No face clustering | Phase 2 | Phase 2 |

---

## Architecture Decisions

| Decision | Choice | ADR |
|----------|--------|-----|
| Agent framework | LangGraph + AutoGen; CrewAI evaluated and replaced | [ADR-003](adr/003-langgraph-over-crewai.md) |
| Vector DB | pgvector on Postgres for v1; benchmark Pinecone in Phase 4 | [ADR-002](adr/002-vector-db-pgvector.md) |
| CLIP model | ViT-L/14 via open_clip, 768-dim | — |
| Google Photos API | Picker API — Library API deprecated March 2025 | — |
| OAuth security | PKCE (code_verifier stored in Redis, TTL 600s) | — |
| Task queue | Celery + Redis DB 1 (separate from app cache on DB 0) | — |
| LLM provider | Anthropic Claude only (Haiku for simple, Sonnet for reasoning) | — |
| Multi-tenancy | `tenant_id` on every row + Row-Level Security at DB level | — |

---

## Terraform AWS Deployment

### Currently Deployed

Only `module.s3` is applied:

```bash
cd infra/terraform
terraform init
terraform apply -var-file=environments/dev/terraform.tfvars
```

This provisions `memorylane-dev-photos` and `memorylane-dev-model-artifacts`. To point the running services at the real buckets, set the four `MEMORYLANE_AWS_*` / `MEMORYLANE_S3_*` vars in `.env` (see [.env.example](../.env.example)) and restart the stack. Leaving `MEMORYLANE_S3_ENDPOINT_URL` unset keeps photos in the local MinIO container.

> **Note for AWS IAM Identity Center users:** export credentials before running Terraform:
> ```bash
> eval "$(aws configure export-credentials --format env)"
> ```

### Phase 2+ — VPC, EKS, RDS, Cognito, ECR

These modules will be added when cloud deployment begins.

---

## CI Notes

### Why tests run per-service

All services share `app` as their top-level package name. Running `pytest src/` in one process causes `sys.modules` to cache the first service's `app`, making subsequent services import the wrong code. Each `python -m pytest src/<svc>/tests` call starts a fresh Python interpreter, eliminating the collision.

Each service directory also has a root-level `conftest.py` (not inside `tests/`) that inserts the service root at `sys.path[0]` as a fallback for environments where multiple services are installed in the same venv.

### Workers tests in CI

The workers service requires `torch` (~2 GB CUDA wheels) and a physical GPU. These tests are excluded from CI and run locally only:
```bash
cd src/workers && pip install -e ".[dev]" && pytest tests -v
```
