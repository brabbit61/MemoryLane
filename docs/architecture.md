# MemoryLane Architecture

## Overview

MemoryLane is a multi-tenant AI photo library organizer built as FastAPI microservices with a Streamlit UI. Users connect their Google Photos library; a Celery worker runs CLIP ViT-L/14 GPU inference to produce 768-dim embeddings stored in pgvector, and a LangGraph agent backed by Claude Sonnet orchestrates natural-language search against those embeddings.

---

## System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     User (Browser)                       │
└────────────────────────┬────────────────────────────────┘
                         │
                    Streamlit UI  :8501
                         │
           ┌─────────────┴──────────────┐
           │                            │
      ingestion-svc :8001         agent-svc :8003
           │                            │
           │  Google Photos         LangGraph
           │  Picker API         (planner → tool_executor → reflector)
           │                            │
           │                      search-svc :8002
           │                            │
           │              CLIP text encoding + pgvector HNSW
           │                            │
     ┌─────┴────────────────────────────┴──────┐
     │          Data Layer                       │
     │  Postgres + pgvector  |  S3 / MinIO       │
     └─────────────┬─────────────────────────────┘
                   │
            celery-worker
         CLIP image encoding (GPU)
         EXIF extraction, thumbnails
```

---

## Services

| Service | Port | Role |
|---------|------|------|
| **ui** | 8501 | Streamlit frontend — search tab + Google Photos picker tab |
| **ingestion-svc** | 8001 | Google OAuth PKCE, Picker API session management, S3 upload, Celery task dispatch |
| **search-svc** | 8002 | CLIP text-to-embedding, pgvector HNSW ANN search, metadata filters, pre-signed S3 URLs |
| **agent-svc** | 8003 | LangGraph conversational agent — multi-turn reasoning over search results |
| **celery-worker** | — | GPU worker — CLIP image encoding, EXIF extraction, thumbnail generation, pgvector writes |
| **api-gateway** | 8000 | Health/readiness endpoints (routing layer planned) |

Infrastructure: **Postgres + pgvector** (port 5433), **Redis** (port 6379, Celery broker), **MinIO** (port 9000, S3-compatible local storage).

---

## Data Flow: Ingestion

```
1. User clicks "Connect Google Photos" in UI
2. ingestion-svc initiates Google OAuth 2.0 PKCE flow
3. User selects photos in Google Picker (session polled until mediaItemsSet=true)
4. ingestion-svc downloads photos → uploads originals to S3/MinIO → inserts rows in photos table (status=pending)
5. ingestion-svc dispatches enrich_photo Celery task per photo
6. celery-worker downloads from S3 → generates thumbnails → extracts EXIF → runs CLIP ViT-L/14 (GPU) → writes 768-dim embedding to photo_embeddings (status=enriched)
```

---

## Data Flow: Search

```
1. User types natural-language query in UI search tab
2. UI calls POST /agent/search on agent-svc
3. LangGraph planner node (Claude Sonnet) generates tool call: search_photos(query, filters...)
4. tool_executor node HTTP-calls GET /search on search-svc
5. search-svc encodes query text with CLIP ViT-L/14 (CPU) → runs pgvector HNSW cosine ANN → applies metadata filters → returns pre-signed S3 thumbnail URLs
6. reflector node deduplicates and trims results; if empty and iterations < 3, loops back to planner
7. Final results + reasoning trace returned to UI
```

---

## LangGraph Agent

The agent is a `StateGraph` with three nodes and a conditional edge:

```
planner ──► tool_executor ──► reflector ──► [done | planner]
```

- **planner** — Claude Sonnet generates a `search_photos` tool call with optional filters (date range, camera make, geolocation)
- **tool_executor** — executes the tool call via HTTP to search-svc
- **reflector** — deduplicates and sorts results; routes to `done` if results found or 3 iterations reached, otherwise loops back
- **Checkpointing** — in-memory `MemorySaver` (thread-scoped state)
- **Tracing** — optional LangSmith integration via `LANGCHAIN_API_KEY`

---

## Database Schema

All tables have `tenant_id` enforced at both ORM level and Postgres Row-Level Security (RLS) via `SET LOCAL app.current_tenant_id`.

| Table | Purpose |
|-------|---------|
| `tenants` | Multi-tenancy root — id, name |
| `users` | Per-tenant users — id, tenant_id, email, display_name |
| `photos` | Core photo metadata — s3_key, filename, EXIF fields, GPS, status (pending/enriched) |
| `photo_embeddings` | 768-dim CLIP vectors — HNSW index (cosine), RLS enabled |
| `oauth_tokens` | Google OAuth tokens — access_token, refresh_token, token_expiry, last_synced_at |

`photo_embeddings.embedding` has an HNSW index (`m=16, ef_construction=64`) for approximate nearest-neighbor search.

---

## Infrastructure

| Layer | Technology |
|-------|-----------|
| Local dev | Docker Compose (all services + Postgres, Redis, MinIO) |
| Photo storage (prod) | AWS S3 via Terraform — `memorylane-{env}-photos` bucket (versioned, KMS, IA lifecycle at 90d) |
| Model artifacts (prod) | AWS S3 — `memorylane-{env}-model-artifacts` bucket |
| CI/CD | GitHub Actions — ruff, mypy, bandit, pytest, docker build on every PR |
