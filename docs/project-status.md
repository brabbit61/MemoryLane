# MemoryLane — Project Status & Roadmap

## Phase Overview

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 0** | Foundations: monorepo, docker-compose, Terraform skeleton, API gateway, CI | ✅ Complete |
| **Phase 1** | Google Photos ingestion + CLIP GPU enrichment + pgvector writes | ✅ Complete |
| **Phase 1b** | S3 Terraform applied; search-svc scaffold, CLIP text encoding, GET /search endpoint | ✅ Complete |
| **Phase 3** | LangGraph Search Agent (A4) + Streamlit UI | ✅ Partial |
| **Phase 4** | Fix taken_at, wire search through api-gateway, DPO data collection | 🚧 Active |
| **Phase 5** | Plan-and-Execute (D1), Critic/Reflection (D2), Shared Memory (D5), LLM-as-Judge eval (D6) | 🚧 Active |
| **Phase 7** | Grafana dashboards, Guardrails, LangSmith fully wired | 🚧 Active |
| **Phase 8** | Blog post, Demo video | 🚧 Active |

### Deferred Phases

| Phase | Description | Reason |
|-------|-------------|--------|
| Phase 2 | Face detection, event clustering, duplicate detection | Not required for core agentic demo |
| Phase 6 | DPO reranker training pipeline | Depends on Album Generation (A3) which is deferred |

---

## What's Been Built

### Phase 0 — Foundations

- **Monorepo structure**: `src/` (microservices + UI), `infra/` (Terraform + DB), `docs/` (ADRs), `.github/` (CI)
- **docker-compose**: Postgres 16 + pgvector, Redis 7, MinIO (S3-compatible), api-gateway, ingestion-svc, celery-worker with NVIDIA GPU passthrough
- **API Gateway** (`src/api-gateway`): FastAPI hello-world with health + readiness endpoints, async SQLAlchemy, pydantic-settings
- **Database schema**: `tenants`, `users`, `photos`, `photo_embeddings` (HNSW index on 768-dim vector), `oauth_tokens`; Row-Level Security enabled
- **Terraform** — `module.s3` deployed (photos + model-artifacts buckets). VPC, EKS, RDS, Cognito, ECR modules deferred.
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

### Phase 3 (partial) — LangGraph Search Agent + Streamlit UI

**Agent service** (`src/agent`, port 8003):
- LangGraph StateGraph: planner → tool_executor → reflector, max 3 iterations
- Tools: semantic_search, date_filter_search, metadata_filter_search (all hit search-svc over HTTP)
- Claude Sonnet 4.6 for planner reasoning
- MemorySaver checkpointer (will graduate to PostgresSaver when D4 is undeferred)
- LangSmith tracing wired (project: memorylane-agent)

**UI** (`src/ui/`, port 8501):
- Streamlit single-page app
- Sidebar user_id input (dev-mode auth — no Cognito yet)
- 3-column results grid with pre-signed S3 thumbnails
- "Agent reasoning" expander showing the planner's tool calls

---

## Active Roadmap

All active tickets are tracked on GitHub. Milestones map to phases.

### Phase 4 — Carry-overs

| # | Ticket | Description |
|---|--------|-------------|
| [#45](https://github.com/brabbit61/MemoryLane/issues/45) | Fix `taken_at` null field | Call `sessions.mediaItems.list` during ingestion to populate photo creation timestamps |
| [#46](https://github.com/brabbit61/MemoryLane/issues/46) | Wire search through API-gateway | Add reverse-proxy route in api-gateway so all clients use port 8000 |
| [#47](https://github.com/brabbit61/MemoryLane/issues/47) | DPO data collection | `dpo_pairs` table + preference endpoint + Streamlit "Better / Worse" buttons |

### Phase 5 — Deep Agent Capabilities

| # | Ticket | Depends on |
|---|--------|------------|
| [#48](https://github.com/brabbit61/MemoryLane/issues/48) | D1 — Plan-and-Execute agent graph | — (replaces current ReAct loop) |
| [#49](https://github.com/brabbit61/MemoryLane/issues/49) | D2 — Critic and reflection node | #48 |
| [#50](https://github.com/brabbit61/MemoryLane/issues/50) | D5 — Cross-agent shared memory via Redis | #48 |
| [#51](https://github.com/brabbit61/MemoryLane/issues/51) | D6 — LLM-as-Judge eval and chaos suite | #48, #49 |

### Phase 7 — Observability & Guardrails

| # | Ticket | Depends on |
|---|--------|------------|
| [#52](https://github.com/brabbit61/MemoryLane/issues/52) | Grafana dashboards and Prometheus metrics | — |
| [#53](https://github.com/brabbit61/MemoryLane/issues/53) | Guardrails — injection defense + cost runaway | #48 |
| [#54](https://github.com/brabbit61/MemoryLane/issues/54) | LangSmith fully wired | #51 |

### Phase 8 — Demo & Portfolio

| # | Ticket | Depends on |
|---|--------|------------|
| [#55](https://github.com/brabbit61/MemoryLane/issues/55) | Blog post | All Phase 5 + Phase 7 tickets complete |
| [#56](https://github.com/brabbit61/MemoryLane/issues/56) | Demo video | All Phase 5 + Phase 7 tickets complete |

---

## Deferred Backlog

These items have GitHub tickets under the "Backlog — Deferred" milestone. Pick up when prior phases are complete or priorities change.

| # | Ticket | Key dependency |
|---|--------|----------------|
| [#57](https://github.com/brabbit61/MemoryLane/issues/57) | BLIP-2 caption generation in workers | — |
| [#58](https://github.com/brabbit61/MemoryLane/issues/58) | Album Generation Graph (A3) | #57, #48 |
| [#59](https://github.com/brabbit61/MemoryLane/issues/59) | Agent hardening — D3 + D4 + D7 | #48, #57 |
| [#60](https://github.com/brabbit61/MemoryLane/issues/60) | Phase 6a — Cover Picker UI + DPO data collection | #58 |
| [#61](https://github.com/brabbit61/MemoryLane/issues/61) | Phase 6b — DPO training pipeline + model artefact | #60 (~300 pairs collected) |
| [#62](https://github.com/brabbit61/MemoryLane/issues/62) | Phase 6c — DPO reranker deployment + eval | #61, #58 |
| [#63](https://github.com/brabbit61/MemoryLane/issues/63) | Adversarial eval suite | #53, #59, #51 |
| [#64](https://github.com/brabbit61/MemoryLane/issues/64) | Eval regression gates in CI | #48, #51 |

Items dropped from scope entirely: Phase 2 (face detection, event clustering, duplicate detection), AutoGen A5 (conversational multi-turn agent), live demo URL + cloud deployment, demo library curation, multi-tenancy security audit.

---

## Architecture Decisions

| Decision | Choice | ADR |
|----------|--------|-----|
| Agent framework | LangGraph + AutoGen; CrewAI evaluated and replaced | [ADR-003](adr/003-langgraph-over-crewai.md) |
| Vector DB | pgvector on Postgres for v1 | [ADR-002](adr/002-vector-db-pgvector.md) |
| CLIP model | ViT-L/14 via open_clip, 768-dim | — |
| Google Photos API | Picker API — Library API deprecated March 2025 | — |
| OAuth security | PKCE (code_verifier stored in Redis, TTL 600s) | — |
| Task queue | Celery + Redis DB 1 (separate from app cache on DB 0) | — |
| LLM provider | Anthropic Claude only (Haiku for simple, Sonnet for reasoning) | — |
| Multi-tenancy | `tenant_id` on every row + Row-Level Security at DB level | — |
| Guardrails | Custom sanitization for injection defense; no external guardrails library | — |
| Shared memory | Redis-backed per-user flat namespace (`mem:{user_id}:`) | — |

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

### Cloud Deployment (Deferred)

VPC, EKS, RDS, Cognito, and ECR Terraform modules are deferred. They will be added if a live demo URL becomes a priority.

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
