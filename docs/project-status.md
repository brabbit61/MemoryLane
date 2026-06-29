# MemoryLane — Project Status

## What's Been Built

### Infrastructure & DevOps

- **Monorepo structure**: `src/` (microservices + UI), `infra/` (Terraform + DB), `docs/` (ADRs), `.github/` (CI)
- **docker-compose**: Postgres 16 + pgvector, Redis 7, MinIO (S3-compatible), api-gateway, ingestion-svc, celery-worker with NVIDIA GPU passthrough
- **AWS S3**: `memorylane-dev-photos` and `memorylane-dev-model-artifacts` buckets provisioned via Terraform (`module.s3`)
- **CI (GitHub Actions)**:
  - PR: ruff lint + format check, mypy, bandit security scan, pytest, docker build
  - Main: full test suite (workers excluded — requires GPU)

### Data Layer

- **Postgres schema**: `tenants`, `users`, `photos`, `photo_embeddings` (HNSW index on 768-dim vector), `oauth_tokens`
- **Row-Level Security** enabled on all tables; `tenant_id` mandatory on every query
- **Redis**: app cache on DB 0, Celery task queue on DB 1
- **MinIO**: S3-compatible local object store for photos and thumbnails

### Google Photos Integration

- OAuth 2.0 with PKCE using the Photos Picker API (`photospicker.mediaitems.readonly`)
- Tokens stored in Postgres with refresh support
- Endpoints in `ingestion-svc` (port 8001):
  - `GET /oauth/google/init` — generates Picker OAuth URL, stores PKCE verifier in Redis (TTL 600s)
  - `GET /oauth/google/callback` — exchanges code, upserts `oauth_tokens`
  - `POST /sync/google/{user_id}/start` — creates a Picker session, returns `picker_uri`
  - `POST /sync/google/{user_id}/ingest/{session_id}` — downloads selected photos, uploads to S3, dispatches enrichment tasks

### Photo Enrichment Pipeline

Celery worker (`src/workers`) consumes from the `enrichment` queue (`prefetch_multiplier=1` — one task at a time per GPU worker):

- Generates 256px + 1024px thumbnails (Pillow LANCZOS)
- Extracts EXIF metadata (DateTimeOriginal, GPS, dimensions, camera make/model)
- Runs CLIP ViT-L/14 inference on NVIDIA GPU (~50 ms/image) — falls back to CPU (~2–5 s)
- Writes 768-dim L2-normalized embedding to `photo_embeddings` via pgvector

**End-to-end verified locally**: 7 photos ingested → MinIO S3 → CLIP GPU enrichment → pgvector; self-similarity = 1.0000

### Semantic Search

`search-svc` (port 8002):

- CLIP ViT-L/14 text encoding (`encode_text(query) -> list[float]`, 768-dim)
- `GET /search` — encodes query, runs pgvector cosine ANN over `photo_embeddings`, returns ranked results with 1-hour pre-signed S3 URLs
- Switches between MinIO and real AWS S3 via a single `MEMORYLANE_S3_ENDPOINT_URL` env var
- Unit tests mock the CLIP model — no GPU required in CI

### Conversational Search Agent

`agent-svc` (port 8003):

- LangGraph `StateGraph`: planner → tool_executor → reflector, max 3 iterations
- Tools: `search_photos` hitting `search-svc` over HTTP, with optional date, camera, and location filters
- Claude Sonnet 4.6 for planner reasoning
- MemorySaver checkpointer
- LangSmith tracing wired (project: `memorylane-agent`)

### Streamlit UI

`ui` (port 8501):

- Single-page app with sidebar user_id input (dev-mode auth — no Cognito yet)
- 3-column results grid with pre-signed S3 thumbnails
- "Agent reasoning" expander showing the planner's tool calls and iteration trace

---

## In Progress

| Ticket | Description |
|--------|-------------|
| [#45](https://github.com/brabbit61/MemoryLane/issues/45) | Fix `taken_at` null — call `sessions.mediaItems.list` during ingestion to populate photo timestamps |
| [#46](https://github.com/brabbit61/MemoryLane/issues/46) | Wire search through api-gateway so all clients use a single entry point (port 8000) |
| [#47](https://github.com/brabbit61/MemoryLane/issues/47) | DPO preference collection — `dpo_pairs` table, preference endpoint, Streamlit "Better / Worse" buttons |
| [#48](https://github.com/brabbit61/MemoryLane/issues/48) | Plan-and-Execute agent — restructure search agent from a ReAct loop to a multi-step planning graph |
| [#49](https://github.com/brabbit61/MemoryLane/issues/49) | Critic and reflection node — agent evaluates its own results and revises the query if quality is low |
| [#50](https://github.com/brabbit61/MemoryLane/issues/50) | Cross-agent shared memory — Redis-backed per-user memory persisted across sessions |
| [#51](https://github.com/brabbit61/MemoryLane/issues/51) | LLM-as-Judge eval and chaos suite — 50 LangSmith scenarios judged by Claude Haiku; injected failure tests |
| [#52](https://github.com/brabbit61/MemoryLane/issues/52) | Grafana dashboards and Prometheus metrics — live ops, cost, agent performance, eval score panels |
| [#53](https://github.com/brabbit61/MemoryLane/issues/53) | Guardrails — prompt injection sanitization and per-tenant daily cost cap |
| [#54](https://github.com/brabbit61/MemoryLane/issues/54) | LangSmith fully wired — prompt versioning, A/B experiments, per-tenant cost attribution |
| [#55](https://github.com/brabbit61/MemoryLane/issues/55) | Blog post — long-form technical writeup + adapted LinkedIn version |
| [#56](https://github.com/brabbit61/MemoryLane/issues/56) | Demo video — 3-minute self-contained walkthrough for GitHub README and LinkedIn |

---

## Deferred

| Ticket | Description | Blocked on |
|--------|-------------|------------|
| [#57](https://github.com/brabbit61/MemoryLane/issues/57) | BLIP-2 caption generation — natural-language captions per photo stored in the DB | — |
| [#58](https://github.com/brabbit61/MemoryLane/issues/58) | Album Generation (A3) — LangGraph supervisor graph with curator, theme detector, photo selector, cover designer nodes | #57 |
| [#59](https://github.com/brabbit61/MemoryLane/issues/59) | Agent hardening — structured error recovery (D3), HITL interrupts + PostgresSaver (D4), tool poisoning defense (D7) | #48, #57 |
| [#60](https://github.com/brabbit61/MemoryLane/issues/60) | Cover Picker UI — drag-and-rank interface for collecting album cover preference pairs | #58 |
| [#61](https://github.com/brabbit61/MemoryLane/issues/61) | DPO training pipeline — export preference pairs, train cross-encoder reranker with TRL, version artefact in S3 | #60 (~300 pairs) |
| [#62](https://github.com/brabbit61/MemoryLane/issues/62) | DPO reranker deployment — integrate trained model into album photo selector; E6 pairwise eval | #61, #58 |
| [#63](https://github.com/brabbit61/MemoryLane/issues/63) | Adversarial eval suite — 20+ hostile input scenarios covering cross-tenant attempts, jailbreaks, resource exhaustion | #53, #59 |
| [#64](https://github.com/brabbit61/MemoryLane/issues/64) | CI smoke checks — deterministic agent gate on every PR (mocked LLM, 5 canonical queries, no API spend) | #48 |
| — | Face detection, event clustering, duplicate detection | Not required for core agentic demo |
| — | AutoGen A5 — conversational multi-turn search agent | Not required for core agentic demo |
| — | Live demo URL — full cloud deployment (EKS, RDS, ECR via Terraform) | Out of scope for this stage |

---

## Architecture Decisions

| Decision | Choice | ADR |
|----------|--------|-----|
| Agent framework | LangGraph for stateful agents; AutoGen reserved for conversational multi-turn (deferred); CrewAI evaluated and replaced | [ADR-003](adr/003-langgraph-over-crewai.md) |
| Vector DB | pgvector on Postgres | [ADR-002](adr/002-vector-db-pgvector.md) |
| CLIP model | ViT-L/14 via open_clip, 768-dim | — |
| Google Photos API | Picker API — Library API deprecated March 2025 | — |
| OAuth security | PKCE (code_verifier stored in Redis, TTL 600s) | — |
| Task queue | Celery + Redis DB 1 (separate from app cache on DB 0) | — |
| LLM provider | Anthropic Claude only (Haiku for simple tasks, Sonnet for reasoning) | — |
| Multi-tenancy | `tenant_id` on every row + Row-Level Security at DB level | — |
| Guardrails | Custom sanitization for injection defense; no external guardrails library | — |
| Shared memory | Redis-backed per-user flat namespace (`mem:{user_id}:`) | — |

---

## Running Locally

```bash
docker compose up -d          # Start Postgres, Redis, MinIO, api-gateway
docker compose logs -f        # Watch logs
```

| Service | Port |
|---------|------|
| API Gateway | 8000 |
| Ingestion | 8001 |
| Search | 8002 |
| Agent | 8003 |
| Streamlit UI | 8501 |
| Postgres (pgvector) | 5432 |
| Redis | 6379 |
| MinIO (S3) | 9000 (console: 9001) |

### AWS S3 (optional)

Set `MEMORYLANE_AWS_*` / `MEMORYLANE_S3_*` vars in `.env` (see [.env.example](../.env.example)) and restart the stack. Leaving `MEMORYLANE_S3_ENDPOINT_URL` unset keeps photos in the local MinIO container.

> **AWS IAM Identity Center users:** export credentials before running Terraform:
> ```bash
> eval "$(aws configure export-credentials --format env)"
> ```

---

## CI Notes

### Why tests run per-service

All services share `app` as their top-level package name. Running `pytest src/` in one process causes `sys.modules` to cache the first service's `app`, making subsequent services import the wrong code. Each `python -m pytest src/<svc>/tests` call starts a fresh Python interpreter, eliminating the collision.

Each service directory has a root-level `conftest.py` that inserts the service root at `sys.path[0]` as a fallback for environments where multiple services are installed in the same venv.

### Workers tests

The workers service requires `torch` (~2 GB CUDA wheels) and a physical GPU. Run locally only:

```bash
cd src/workers && pip install -e ".[dev]" && pytest tests -v
```
