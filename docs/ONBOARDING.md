# MemoryLane — Developer Onboarding

A complete walkthrough of what is built, what each technology does, and how a request flows end-to-end. Sections are ordered the way the stack is actually invoked.

---

## 1. What this project is

MemoryLane is a multi-tenant SaaS that organizes a user's photo library with AI. A user authorizes their Google Photos account, picks photos via Google's Photos Picker, and the back-end pipeline downloads, stores, and enriches each image with thumbnails, EXIF metadata, and a CLIP vector embedding written to pgvector. Future phases layer semantic search, face/event clustering, and multi-agent (LangGraph + AutoGen) album generation on top.

**Implemented (Phases 0, 1, 1b):** infra-as-code, local dev stack, Google OAuth + Picker ingestion, GPU CLIP enrichment, pgvector writes, S3 Terraform applied, CLIP text encoding, `GET /search` endpoint with pgvector ANN + pre-signed S3 URLs.
**Stubbed:** [src/agent/](src/agent/), [src/ui/](src/ui/) — Phase 3+.

The architectural shape is **microservices on FastAPI + Celery**, deployed on **AWS EKS** in prod and run via **Docker Compose** locally. Each service owns one responsibility (ingest, enrich, gateway, search, agent) and they communicate over Postgres rows and a Redis-backed Celery queue — there are no service-to-service HTTP calls yet.

---

## 2. Docker Compose — local orchestration

### What it is
Docker Compose is a tool for defining a multi-container application in a single YAML file (image, ports, env, volumes, healthchecks, GPU reservations, startup order). A single `docker compose up` brings the whole graph up in dependency order.

### How MemoryLane uses it
[docker-compose.yml](docker-compose.yml) is the canonical "press play" entry point — it provisions five containers that mirror the production topology closely enough to develop against:

| Service | Image | Role |
|---------|-------|------|
| `postgres` | `pgvector/pgvector:pg16` | OLTP store + vector index |
| `redis` | `redis:7-alpine` | Cache + Celery broker |
| `minio` | `minio/minio:latest` | Local S3-compatible object store |
| `api-gateway` | built from `src/api-gateway` | Public HTTP front door (port 8000) |
| `ingestion-svc` | built from `src/ingestion` | OAuth + Picker + S3 upload (port 8001) |
| `search-svc` | built from `src/search` | CLIP text-to-image search (port 8002) |
| `celery-worker` | built from `src/workers` | GPU enrichment consumer |

Compose-specific things to know:

- **`depends_on` with `condition: service_healthy`** keeps app containers from booting before Postgres/Redis/MinIO are ready (each has a `healthcheck` block).
- **Postgres host port is remapped to 5433** because host 5432 is usually occupied by a system Postgres install.
- **`celery-worker` and `search-svc` both reserve an NVIDIA GPU** via `deploy.resources.reservations.devices` — needs `nvidia-container-toolkit` installed on the host. To run CPU-only: set `MEMORYLANE_CLIP_DEVICE=cpu` and remove that block from each service.
- **All config is `MEMORYLANE_*` env vars** with sensible defaults baked in; per-service `config.py` files use `pydantic-settings` with `env_prefix="MEMORYLANE_"` to read them.
- **Secrets and Google creds** come from a gitignored `.env` file you create from [.env.example](.env.example).

---

## 3. Postgres 16 + pgvector — system of record

### What they are
**Postgres** is the relational database that holds every domain entity. **pgvector** is a Postgres extension that adds a `VECTOR(n)` column type and approximate-nearest-neighbor indexes (IVFFlat, HNSW) so similarity search runs inside the same database as the rest of the app data — no separate vector store to operate.

The `pgvector/pgvector:pg16` Docker image is just stock Postgres 16 with the extension preinstalled.

### How MemoryLane uses it
Schema and seed data are applied automatically by mounting [infra/db/init.sql](infra/db/init.sql) into Postgres's `/docker-entrypoint-initdb.d/` (Postgres runs every `.sql` in that directory on first boot). Tables:

- **`tenants`, `users`** — multi-tenant identity. Seeded with a fixed dev tenant + user UUID so curl examples in the README "just work" without signing anyone up.
- **`photos`** — one row per ingested image. Holds `s3_key`, `filename`, `mime_type`, dimensions, EXIF (`taken_at`, lat/lon), `status` (`pending` → `enriched`), `source` (`google_photos`), and an `external_id` (the Google Photos media item id, used for dedupe).
- **`photo_embeddings`** — a 768-dim `VECTOR` column for each photo plus an **HNSW index** with `vector_cosine_ops`. HNSW (Hierarchical Navigable Small World) is a graph-based ANN index — at query time it gives sub-linear nearest-neighbor lookups with ~95–99% recall, which is the right trade-off for image search.
- **`oauth_tokens`** — per-user Google access/refresh token + expiry + last-synced timestamp.

**Multi-tenancy is enforced at two layers:**
1. ORM models carry `tenant_id` on every row and every query.
2. Postgres `ROW LEVEL SECURITY` is enabled on `photos`, `photo_embeddings`, and `oauth_tokens` so a leaked or buggy query can't cross tenants. Concrete policies will be attached when the real auth integration lands.

**Two ORM model files exist intentionally:**
- [src/ingestion/app/models.py](src/ingestion/app/models.py) — **async** SQLAlchemy via `asyncpg`, full set including `User`/`Tenant`/`OAuthToken`. FastAPI is async, so the web layer needs async DB access.
- [src/workers/app/models.py](src/workers/app/models.py) — **sync** SQLAlchemy via `psycopg2`, just `Photo` + `PhotoEmbedding`. Celery tasks run in sync worker processes, so async would just add overhead. The embedding column uses `pgvector.sqlalchemy.Vector(768)` so writing a Python `list[float]` of length 768 transparently goes into the pgvector column.

---

## 4. Redis 7 — cache, OAuth state, and Celery broker

### What it is
Redis is an in-memory key/value store. In this codebase it does two completely different jobs (which is why it has two logical databases):

1. **Short-lived structured cache** — fast `SET key value EX 600` writes with built-in TTLs for ephemeral state.
2. **Message broker** — Celery uses Redis lists as task queues (producers `LPUSH`, workers `BRPOP`).

### How MemoryLane uses it
Two logical DBs (a Redis instance supports DBs 0–15, completely independent keyspaces):

**DB 0 — application cache.** Used by the ingestion service to hold OAuth state across the consent redirect:

- `oauth_state:<token>` — the random state token (proves a callback originated from us).
- `oauth_user:<token>` — the user UUID associated with this OAuth flow.
- `oauth_pkce:<token>` — the **PKCE `code_verifier`** that must be sent to Google's token endpoint to complete the exchange (PKCE = Proof Key for Code Exchange, the modern protection against authorization-code interception).

All three have a 600-second TTL so abandoned OAuth flows clean themselves up. See [src/ingestion/app/services/redis_state.py](src/ingestion/app/services/redis_state.py) and how they're consumed by [src/ingestion/app/routers/oauth.py](src/ingestion/app/routers/oauth.py) (the callback uses `GETDEL` so a state token is single-use atomically).

**DB 1 — Celery broker + result backend.** Deliberately separated so a `FLUSHDB` against the app cache can't lose in-flight enrichment jobs.

---

## 5. MinIO (or real AWS S3) — object store

### What they are
**S3** (Simple Storage Service) is AWS's object store — flat namespace of `(bucket, key) → bytes` with rich metadata, versioning, and lifecycle rules. **MinIO** is an S3-API-compatible server you can run locally. Both expose the exact same HTTP API, so the same `boto3` / `aioboto3` client code works against either — you flip a single endpoint URL.

### How MemoryLane uses it
Photos are stored as raw object bytes, **not** as Postgres `bytea` columns — keeping multi-megabyte binaries out of the database is what makes the system scale.

`minio/minio:latest` exposes an S3-compatible endpoint at `:9000` (console at `:9001`, default `minioadmin`/`minioadmin`). Two services talk to it:

- **Ingestion** ([src/ingestion/app/services/s3.py](src/ingestion/app/services/s3.py)) uses **`aioboto3`** because the FastAPI handlers are async — blocking on a sync S3 upload would stall the event loop.
- **Workers** ([src/workers/app/tasks.py](src/workers/app/tasks.py)) uses sync **`boto3`** because Celery tasks run in their own processes; sync is simpler.

The endpoint URL is environment-controlled: `MEMORYLANE_S3_ENDPOINT_URL=http://minio:9000` for local development, unset/empty to use a real AWS bucket (see [.env.example](.env.example) and the Terraform section in [docs/project-status.md](docs/project-status.md) for switching).

**Key layout** (tenant-scoped, so deleting a tenant could be a single prefix delete):

```
originals/{tenant_id}/{user_id}/{photo_id}
thumbnails/{256|1024}/{tenant_id}/{user_id}/{photo_id}
```

`ensure_bucket_exists()` runs in the ingestion service's FastAPI `lifespan` and idempotently creates the bucket on cold start so MinIO works zero-config out of the box.

---

## 6. Ingestion Service (FastAPI, port 8001)

### What FastAPI is
A modern Python web framework built on Starlette (ASGI) + Pydantic. Two reasons it's used here:

- **Native async/await** — `async def` handlers cooperatively multiplex I/O (DB, HTTP, S3), so a single worker can hold many in-flight Picker downloads at once.
- **Pydantic** request/response models give runtime validation + OpenAPI/Swagger generation for free (`/docs` is auto-generated).

### What this service does
[src/ingestion/](src/ingestion/) is the user-facing entry point today. It's the only service that talks to Google. SQLAlchemy is wired in async mode via `asyncpg`. Two routers attached in [app/main.py](src/ingestion/app/main.py):

### 6a. OAuth router — [routers/oauth.py](src/ingestion/app/routers/oauth.py)

Implements the standard OAuth 2.0 Authorization Code flow with PKCE for connecting a user's Google account:

- **`GET /oauth/google/init?user_id=...`** — verifies the user exists, mints a Redis state token, calls `build_auth_url()` (which uses `google-auth-oauthlib`'s `Flow` to construct a Google consent URL and generate the PKCE `code_verifier`), and stores the verifier in Redis keyed by state. Returns the consent URL for the user to open.
- **`GET /oauth/google/callback?code&state`** — Google redirects here after consent. The handler validates state, atomically `GETDEL`s the PKCE verifier (single-use), exchanges the code for an access + refresh token, and upserts into `oauth_tokens`.

### 6b. Sync router — [routers/sync.py](src/ingestion/app/routers/sync.py)

The Picker API is a **two-step user-driven flow**. The back-end can no longer auto-ingest after OAuth — the user must explicitly pick which photos to share inside Google's hosted UI.

- **`POST /sync/google/{user_id}/start`** — creates a Picker `session` server-side and returns the `pickerUri`. The user opens that URI in their browser, picks photos in Google's UI, clicks Done.
- **`GET /sync/google/{user_id}/session/{session_id}`** — polls `mediaItemsSet` to know when the user finished selecting.
- **`POST /sync/google/{user_id}/ingest/{session_id}`** — schedules a FastAPI `BackgroundTask` (`run_picker_ingest`) that opens its own DB session and walks the picked items.

Per item the background task:
1. Skips duplicates by `(tenant, user, external_id)` — re-ingesting the same session is idempotent.
2. Downloads bytes from `baseUrl + "=d"` (Picker quirk: the `=d` suffix asks for the original file rather than a preview, and the `Authorization: Bearer` header is required).
3. Inserts a `photos` row with `status='pending'` (status acts as a tiny state machine: `pending` → `enriched` → `failed`).
4. Uploads bytes to S3 under `originals/...`.
5. Writes the `s3_key` back to the row.
6. **Dispatches a Celery task**:

   ```python
   celery_app.send_task("workers.tasks.enrich_photo", args=[photo_id], queue="enrichment")
   ```

   No image bytes cross the queue — just the photo UUID. The worker re-fetches from S3.

### 6c. Google Photos Picker API — [src/ingestion/app/services/google_photos.py](src/ingestion/app/services/google_photos.py)

**Critical historical context:** Google's classic **Library API was deprecated for new apps on 2025-03-31**. New integrations must use the **Photos Picker API** (scope `photospicker.mediaitems.readonly`). The user-experience difference is significant — the app cannot read the whole library; the user has to actively pick photos in a Google-hosted picker UI. This is why the sync flow is two-step.

Implementation details:

- `httpx.AsyncClient` is used directly against the REST endpoints (`https://photospicker.googleapis.com/v1/...`) rather than the Google SDK, because the SDK is sync-only.
- `_picker_access_token()` transparently refreshes expired credentials using the stored refresh token. The google-auth library is sync, so it's offloaded to a thread pool with `asyncio.to_thread`.
- `_build_credentials()` includes a subtle workaround for `google-auth`'s naive-UTC `_helpers.utcnow()`: if you hand it a timezone-aware expiry, the `expired` property raises a `TypeError`. The code strips tzinfo before constructing `Credentials`.

---

## 7. Celery + Workers Service — the enrichment pipeline

### What Celery is
Celery is a distributed task queue for Python. Producers (`celery_app.send_task(...)`) push a serialized message to a broker; workers (separate processes, often on different machines) pop and execute. Why it's needed here: CLIP inference on a GPU takes ~50 ms per image and you don't want the user's HTTP request blocking on that — the request returns immediately with `ingest_started` and the heavy lifting runs asynchronously.

### How MemoryLane uses it
[src/workers/](src/workers/) is a Celery consumer with no HTTP surface. Worker config in [app/worker.py](src/workers/app/worker.py):

- **`task_acks_late=True`** — the message is acknowledged only after the task completes successfully. If the worker crashes mid-task, the broker redelivers the message to another worker.
- **`worker_prefetch_multiplier=1`** — each worker holds at most one unacknowledged task at a time. Critical for GPU work: prefetching more would let multiple tasks pile up in front of a single GPU and OOM it.
- **Routing: `workers.tasks.enrich_photo → queue=enrichment`** — having a named queue makes it easy to later add a separate `thumbnails` or `faces` queue with different concurrency settings.

Per task ([app/tasks.py](src/workers/app/tasks.py), the `enrich_photo` Celery task) the worker:

1. **Fetches** the original bytes from S3 by `photo.s3_key`.
2. **Pillow** (PIL fork — the standard Python image library) decodes to RGB, then generates 256px + 1024px JPEG thumbnails using LANCZOS resampling (highest quality of the standard filters), and uploads them under `thumbnails/{size}/...`.
3. **EXIF extraction** via `image.getexif()`:
   - `DateTimeOriginal` (tag 36867) → `taken_at`.
   - GPS IFD (tag 0x8825) — converts the EXIF DMS format (degrees/minutes/seconds tuple plus N/S/E/W reference) to decimal lat/lon.
   - Plus width/height.
   - Everything is wrapped in `contextlib.suppress(Exception)` because malformed EXIF blocks are common in the wild and shouldn't fail a whole enrichment.
4. **CLIP inference** → 768-float L2-normalized vector (see §8).
5. **DB writes**: upserts `photo_embeddings`, updates `photos` with `status='enriched'`, `taken_at`, lat/lon, dimensions.

**Retries:** `max_retries=3, countdown=60` — any exception triggers `self.retry()`, scheduling a re-run after 60 seconds. After 3 failures the task ends in the `FAILURE` state.

> **Known gap** (called out in [docs/project-status.md](docs/project-status.md)): the Picker `baseUrl` download does **not** preserve the original `creationTime` EXIF reliably, so `taken_at` is often null on Picker-sourced photos. Phase 1b will add a fallback call to `sessions.mediaItems.list` to fetch `creationTime` from Google's metadata directly.

---

## 8. CLIP ViT-L/14 (open_clip + PyTorch + CUDA)

### What CLIP is
CLIP (Contrastive Language-Image Pre-training, OpenAI 2021) is a dual-encoder model: one tower encodes images, the other encodes text, and they're trained so that matching image/text pairs land near each other in a shared embedding space. The practical consequence is that "a 768-dim vector for an image" and "a 768-dim vector for the string 'a dog on a beach at sunset'" are directly comparable by cosine similarity — that's the foundation of the future text-to-image search feature.

**`open_clip`** is the open-source reimplementation of CLIP that ships multiple model sizes and lets you pick pretrained weights. **PyTorch** is the deep-learning framework providing tensor ops + CUDA acceleration.

### How MemoryLane uses it
[src/workers/app/clip_model.py](src/workers/app/clip_model.py):

- **Model:** `ViT-L-14` with OpenAI weights — a Vision Transformer with 14×14 image patches. It's a deliberate middle ground: larger than `ViT-B/32` (more accurate), smaller than `ViT-H/14` (faster, fits comfortably on a `g5.xlarge`'s 24 GB GPU).
- **Lazy loading + module-scope cache** (`_model is None` guard) so the ~900 MB weight download happens once per container lifetime, not per task.
- **Device:** `cuda` if `torch.cuda.is_available()`, else falls back to `cpu`. The compose file mounts `HF_HOME` and `TORCH_HOME` to `/app/model_cache` (a volume) so the model survives container restarts and rebuilds.
- **Output:** 768-dim, **L2-normalized**. Normalization is what makes cosine similarity in pgvector equivalent to a dot product, which is why the HNSW index uses `vector_cosine_ops` rather than `vector_l2_ops`.
- **Inference is inside `torch.no_grad()`** — disables autograd so we don't waste memory tracking gradients we never need.
- **Performance budget:** ~50 ms/image on a single g5.xlarge GPU vs ~2–5 s on CPU.

Decision context: [docs/adr/002-vector-db-pgvector.md](docs/adr/002-vector-db-pgvector.md) explains why pgvector beat dedicated vector DBs at this scale. [docs/adr/003-langgraph-over-crewai.md](docs/adr/003-langgraph-over-crewai.md) explains the agent-framework choice — **LangGraph + AutoGen**, CrewAI was evaluated and replaced.

---

## 9. API Gateway (FastAPI, port 8000)

### What an API gateway is
A single HTTP entry point that fans requests out to downstream microservices. Reasons it exists as a separate service from ingestion:

- One public origin to lock down with auth, rate limiting, CORS, request logging.
- The ingestion endpoints are operationally noisy (long-running, OAuth-redirect-y) and shouldn't be the only thing facing the internet.
- Search/agent endpoints will land here without bloating the ingestion service.

### Current state
[src/api-gateway/](src/api-gateway/) is currently a minimal FastAPI app with `/`, `/health`, `/ready`, permissive CORS, and async-SQLAlchemy + pydantic-settings wiring. It's the **planned** front door for the search/agent endpoints — today the ingestion service is hit directly. Treat this service as the place new HTTP surfaces will land in Phase 3.

---

## 10. Search service (FastAPI, port 8002)

[src/search/](src/search/) is now functional. It is a GPU-capable FastAPI service that takes a plain-text query and returns ranked photos via CLIP text encoding + pgvector ANN.

### 10a. CLIP text encoding — [app/clip_text.py](src/search/app/clip_text.py)

Mirrors the image-encoding module in workers ([app/clip_model.py](src/workers/app/clip_model.py)) but for the text tower:

- **Module-level singleton** (`_model`, `_tokenizer`) loaded on first call, cached for container lifetime. Same lazy-load + `_model is None` guard as the image encoder.
- **`encode_text(query: str) -> list[float]`** — tokenizes the query string with `open_clip.get_tokenizer("ViT-L-14")`, runs `model.encode_text(tokens)`, L2-normalizes, and returns a Python `list[float]` of length 768. The same normalization that makes image embeddings comparable by cosine similarity applies here — image and text embeddings land in the same 768-dim space.
- Falls back to `cpu` if `torch.cuda.is_available()` is `False`, so the service starts without a GPU (useful for tests and dev environments).

### 10b. GET /search endpoint — [app/routers/search.py](src/search/app/routers/search.py)

```
GET /search?q=<text>&user_id=<uuid>&limit=20
```

Default limit 20, max 100. Response is a JSON array of `SearchResult`:

```json
[
  {
    "photo_id": "...",
    "filename": "beach.jpg",
    "taken_at": "2024-08-15T19:23:45Z",
    "score": 0.87,
    "url": "https://s3.amazonaws.com/...?X-Amz-Signature=..."
  }
]
```

Internally:
1. `encode_text(q)` → 768-dim query vector.
2. Raw SQL against pgvector using `CAST(:vec AS vector)` to pass the vector as a string — avoids asyncpg type-registration complexity while using the existing HNSW index transparently.
3. `1 - (embedding <=> query_vector)` converts cosine distance to similarity so results are in descending relevance order.
4. `presign_photo_url(s3_key)` ([app/services/s3.py](src/search/app/services/s3.py)) generates a 1-hour pre-signed `GetObject` URL via sync boto3. `endpoint_url=None` → real AWS S3; `endpoint_url=http://minio:9000` → local MinIO — same env-var toggle used by the other services.

### 10c. Agent service — placeholder

[src/agent/app/](src/agent/app/) contains only `__init__.py`. Per the roadmap (Phase 3+):

- **LangGraph** powers a **Search Agent** that decomposes natural-language queries into tool calls (CLIP search, metadata filter, face lookup) and a **Multi-agent Album Generation supervisor graph**.
- **AutoGen** powers the conversational search UX (UserProxy ↔ Assistant loops).
- **LLMs:** Anthropic Claude only — Haiku for routing/classification, Sonnet for reasoning/planning.

---

## 11. Terraform (AWS)

### What Terraform is
Infrastructure-as-Code: you declare cloud resources in HCL (`.tf` files), `terraform plan` computes the diff against current cloud state, `terraform apply` makes it so. State is stored in a remote backend (S3 bucket `memorylane-terraform-state`).

### How MemoryLane uses it
[infra/terraform/](infra/terraform/) currently contains one active module:

| Module | What it provisions | Status |
|--------|-------------------|--------|
| `s3` | Photos bucket + model-artifacts bucket (KMS encrypted, lifecycle to STANDARD_IA after 90 days) | ✅ Deployed |

VPC, EKS, RDS, Cognito, and ECR modules will be added in Phase 2 when cloud deployment begins.

```bash
cd infra/terraform
terraform init
terraform apply -var-file=environments/dev/terraform.tfvars
```

To point running services at the real AWS bucket, set the four `MEMORYLANE_AWS_*` / `MEMORYLANE_S3_*` vars in `.env`. Leaving `MEMORYLANE_S3_ENDPOINT_URL` set to `http://minio:9000` keeps everything local.

> **IAM Identity Center users:** `eval "$(aws configure export-credentials --format env)"` before running Terraform.

---

## 12. GitHub Actions CI

### What it is
A workflow runner that executes YAML-defined jobs on `pull_request` and `push` events. Each job runs on a fresh Ubuntu VM, with optional "service containers" (sidecar Docker containers like Postgres) for integration tests.

### How MemoryLane uses it
**[.github/workflows/on-pr.yml](.github/workflows/on-pr.yml)** — runs on every PR:

- **lint job**: `ruff check`, `ruff format --check`, `mypy src/api-gateway/app`, `bandit -r src/` (bandit = static security scanner for Python — flags `subprocess`, `eval`, hardcoded passwords, etc).
- **test job**: spins up Postgres + Redis service containers and runs `pytest src/api-gateway/tests` and `pytest src/search/tests`.
- **build job**: `docker build` of the api-gateway image, gated on lint + test.

**[.github/workflows/on-main.yml](.github/workflows/on-main.yml)** runs the full per-service test suite (api-gateway, ingestion, search, agent). ECR push will be wired in Phase 2 when the ECR module is provisioned.

**CI quirk every contributor will hit:** all services share `app` as their top-level package name. Running `pytest src/` in one process makes `sys.modules` cache the first service's `app` and break the rest. Tests must therefore be run **per-service in separate Python processes** (`python -m pytest src/<svc>/tests`). Each service also has a root-level `conftest.py` (not inside `tests/`) that prepends its own root to `sys.path` as a fallback. Workers tests are local-only — `torch` is a ~2 GB CUDA wheel and the tests need a physical GPU.

---

## 13. Code conventions

From [CLAUDE.md](CLAUDE.md):

- **Python 3.11+** everywhere.
- **FastAPI + async SQLAlchemy** for HTTP services; sync SQLAlchemy for Celery workers.
- **Pydantic v2** for every request/response and config model.
- **`pydantic-settings`** for config (env-var-driven, validated at startup, single `Settings()` singleton per service).
- **Ruff** (line length 100) handles both linting and formatting — no separate Black.
- **mypy strict** for type checking.
- **pytest + pytest-asyncio** for testing.
- **Multi-tenancy is mandatory**: every domain table carries `tenant_id`, enforced at ORM and Postgres RLS levels — never write a query without filtering by tenant.
- **Service layout**: `src/<name>/{app,tests,pyproject.toml,Dockerfile}` — one directory per service, each independently installable as a package.

---

## 14. End-to-end request flow

```
User browser
  │  (1) GET /oauth/google/init?user_id=…  →  ingestion-svc
  │      ↳ mints Redis state + PKCE verifier, returns Google consent URL
  │  (2) Google consent screen → redirect with ?code&state
  │  (3) GET /oauth/google/callback  →  ingestion-svc
  │      ↳ exchanges code (PKCE) → upserts oauth_tokens (Postgres)
  │  (4) POST /sync/google/{user_id}/start  →  ingestion-svc
  │      ↳ Picker API: create session → returns pickerUri
  │  (5) User opens pickerUri in browser, picks photos in Google's UI
  │  (6) POST /sync/google/{user_id}/ingest/{session_id}  →  ingestion-svc
  │      ↳ BackgroundTask paginates picked items, for each:
  │          • download bytes (baseUrl + "=d") with refreshed access token
  │          • INSERT photos (status=pending)
  │          • PUT object to S3/MinIO (originals/…)
  │          • UPDATE photos.s3_key
  │          • Celery send_task("workers.tasks.enrich_photo", queue="enrichment")
  │
  └── Redis DB1 (Celery broker)
        │
        ▼
   celery-worker  (workers svc, GPU, prefetch=1)
     • GET object from S3
     • Pillow → 256/1024 thumbs → PUT back to S3
     • Pillow.getexif() → taken_at / lat / lon / dims
     • CLIP ViT-L/14 on CUDA → 768-d L2-normalized vector
     • UPSERT photo_embeddings (pgvector HNSW)
     • UPDATE photos SET status='enriched', taken_at, lat, lon, w, h
```

The api-gateway and agent-svc sit downstream of this for future Phase 3 work. The search-svc is already operational:

```
User / client
  │  GET /search?q=beach&user_id=…  →  search-svc (port 8002)
  │      ↳ encode_text("beach") → 768-dim query vector (CLIP ViT-L/14 text tower)
  │      ↳ pgvector ANN query (HNSW cosine, ORDER BY embedding <=> query_vector)
  │      ↳ for each row: presign_photo_url(s3_key) → 1-hour S3 URL
  │      ↳ returns list[SearchResult] sorted by descending cosine similarity
  └── Response: [{photo_id, filename, taken_at, score, url}, ...]
```

---

## 15. Quick start checklist

1. Install Docker, nvidia-container-toolkit (if GPU), Python 3.11.
2. Create a GCP project, enable **Photos Picker API**, add yourself as a test user, create a Web OAuth client with redirect `http://localhost:8001/oauth/google/callback`.
3. `cp .env.example .env`, paste the Google client id/secret.
4. `docker compose up -d --build` — first start pulls the CLIP ViT-L/14 weights (~900 MB).
5. Walk through the 3 curl calls in the [README](README.md) "Ingest photos from Google Photos" section using the seeded user UUID `00000000-0000-0000-0000-000000000002`.
6. Verify enrichment: `psql -h localhost -p 5433 -U memorylane -d memorylane -c "SELECT count(*) FROM photo_embeddings;"`
7. Try semantic search: `curl "http://localhost:8002/search?q=beach&user_id=00000000-0000-0000-0000-000000000002"` — returns ranked photos with pre-signed URLs.
8. For tests: install + run per service (`pip install -e "src/<svc>[dev]" && python -m pytest src/<svc>/tests`). Search tests run without a GPU (CLIP model is mocked).

Roadmap and what's-not-built-yet live in [docs/project-status.md](docs/project-status.md); design rationales in [docs/adr/](docs/adr/).
