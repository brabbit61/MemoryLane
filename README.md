# MemoryLane

**An agentic AI photo library organizer.** Multi-tenant SaaS that ingests photo collections from Google Photos, enriches them with CLIP embeddings, BLIP captions, face/event/duplicate clustering, and exposes them through semantic search and conversational refinement agents.

> **Status:** Active development. Phase 0 (foundations) complete. Phase 1 (Google Photos ingestion + CLIP enrichment + pgvector indexing) in progress on `features/1-setup-infrastructure-as-code`.

For the full design rationale, agent architecture, evaluation framework, and roadmap see [`MemoryLane_Project_Document.md`](MemoryLane_Project_Document.md).

---

## Architecture at a glance

```
                Web client (planned)
                       |
                  api-gateway (FastAPI, :8000)
                       |
   ingestion-svc (:8001)   search-svc (planned)   agent-svc (planned)
         |                       |                       |
   Google Photos API +    pgvector similarity      LangGraph + AutoGen
   S3 upload pipeline     + reranker
         |
   Redis broker -> Celery enrichment-worker
                  (CLIP ViT-L/14 on GPU, EXIF, thumbnails)
                       |
                  Postgres (pgvector) + S3/MinIO
```

- **Multi-agent orchestration:** LangGraph (primary) + AutoGen (conversational). CrewAI was evaluated and replaced — see [ADR-003](docs/adr/003-langgraph-over-crewai.md).
- **Vector store:** pgvector on Postgres 16 with HNSW index on 768-dim CLIP embeddings.
- **Multi-tenant:** every row carries `tenant_id`, enforced at ORM + Postgres RLS level.
- **No fine-tuning in v1** — the depth comes from agent design (planning, reflection, HITL, error recovery) instead.

---

## Repository structure

```
services/
  api-gateway/          FastAPI public-facing service (auth, routing, health)
  ingestion/            Google Photos OAuth + sync to S3 + dispatches enrichment
  workers/              Celery enrichment worker (CLIP, thumbnails, EXIF -> pgvector)
  search/  agent/       Skeletons reserved for Phase 3+

infra/
  db/init.sql           Postgres schema (tenants, users, photos, photo_embeddings, oauth_tokens)
  terraform/            VPC, EKS, RDS, S3, Cognito, ECR modules + dev/staging/prod envs
  helm/                 Reserved for Phase 7

docs/
  architecture.md       High-level system design
  agents.md             Per-agent design and framework allocation
  evals.md              Evaluation framework overview
  adr/                  Architectural Decision Records

evals/  ml/  ui/        Reserved for Phase 5/6/7 (eval suites, DPO training, frontend)
.github/workflows/      CI: PR (lint + test + build) and main (full suite + ECR push)
```

---

## Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Python | 3.11+ | All services |
| Docker + Docker Compose | recent | Local Postgres/Redis/MinIO + service containers |
| Terraform | 1.10+ | `use_lockfile` backend support |
| Node.js | 20+ | Future UI work (not needed for backend) |
| NVIDIA Container Toolkit | latest | GPU passthrough for the Celery worker (Phase 1+) |
| `gh` CLI | recent | PR/issue automation |

For Phase 1 specifically you also need a Google Cloud project with the Photos Library API enabled — see [Phase 1 setup](#phase-1-google-photos-ingestion) below.

---

## Quick start (local)

```bash
# 1. Clone and create a virtualenv
git clone <this-repo>
cd MemoryLane
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e "services/api-gateway[dev]"
pip install -e "services/ingestion[dev]"
pip install -e "services/workers[dev]"      # heavy: pulls torch + open_clip

# 2. Create .env at repo root (see Phase 1 below for GCP credentials)
cat > .env <<'EOF'
MEMORYLANE_GOOGLE_CLIENT_ID=
MEMORYLANE_GOOGLE_CLIENT_SECRET=
EOF

# 3. Start the data layer + services
docker compose up -d --build
docker compose ps     # everything should be "healthy"

# 4. Verify
curl http://localhost:8000/health        # api-gateway
curl http://localhost:8001/health        # ingestion-svc
```

### Local service map

| Service | URL / Port | Credentials |
|---------|-----------|-------------|
| API Gateway | http://localhost:8000 | n/a |
| Ingestion | http://localhost:8001 | n/a |
| Postgres (pgvector) | localhost:5432 | `memorylane` / `memorylane` |
| Redis | localhost:6379 | n/a |
| MinIO (S3-compatible) | http://localhost:9000 | `minioadmin` / `minioadmin` |
| MinIO console | http://localhost:9001 | same |

The Postgres database is auto-initialized from [`infra/db/init.sql`](infra/db/init.sql) — pgvector extension, the full schema, and a development tenant + user (UUIDs `00000000-0000-0000-0000-000000000001` and `...002`) are created on first `docker compose up`. **To re-apply schema changes, run `docker compose down -v && docker compose up -d` to wipe and re-init the volume.**

---

## Phase 1: Google Photos ingestion

The ingestion pipeline is gated on Google Cloud OAuth credentials. One-time setup:

1. Create a project at [console.cloud.google.com](https://console.cloud.google.com/) named `memorylane`.
2. **APIs & Services -> Library** -> enable **Photos Library API**.
3. **OAuth consent screen** -> External -> add scope `photoslibrary.readonly` -> add yourself as a test user.
4. **Credentials -> Create OAuth 2.0 Client ID** -> Web application -> add redirect URI `http://localhost:8001/oauth/google/callback`.
5. Copy the Client ID and Client Secret into `.env`:
   ```
   MEMORYLANE_GOOGLE_CLIENT_ID=<paste>
   MEMORYLANE_GOOGLE_CLIENT_SECRET=<paste>
   ```
6. Restart the ingestion service: `docker compose up -d --force-recreate ingestion-svc`.

### Trigger a sync

```bash
# 1. Get the OAuth URL (replace <user_id> with the dev user UUID from init.sql)
curl "http://localhost:8001/oauth/google/init?user_id=00000000-0000-0000-0000-000000000002"
# -> {"auth_url": "https://accounts.google.com/..."}

# 2. Open auth_url in a browser, complete consent.
#    The callback will store tokens and trigger the initial sync automatically.

# 3. Watch progress
docker compose logs -f ingestion-svc celery-worker

# 4. Verify embeddings were written
docker compose exec postgres psql -U memorylane -c "
  SELECT count(*) AS photos, count(pe.embedding) AS embeddings
  FROM photos p LEFT JOIN photo_embeddings pe ON pe.photo_id = p.id;"
```

The Celery worker uses the GPU configured in [`docker-compose.yml`](docker-compose.yml). Verify CUDA is reachable:

```bash
docker compose exec celery-worker python -c \
  "import torch; print('CUDA:', torch.cuda.is_available())"
```

---

## Development workflow

### Per-service install pattern

Each service has its own `pyproject.toml` and a top-level `app/` package. Because the package names collide in `site-packages`, **run tests and tools per-service**, not from the repo root:

```bash
cd services/<service>
pytest tests -v
```

Or loop:

```bash
for svc in api-gateway ingestion workers; do
  (cd services/$svc && pytest tests -v --tb=short) || break
done
```

### Lint, format, type check

These all run from the repo root and operate across all services:

```bash
ruff check .                                  # lint
ruff format --check .                         # formatting
ruff check . --fix && ruff format .           # auto-fix everything fixable

mypy services/api-gateway/app                 # strict type check (per service)
mypy services/ingestion/app
mypy services/workers/app

bandit -r services/ -ll -ii                   # security scan (CI threshold)
```

### Terraform

```bash
cd infra/terraform
terraform init -backend=false                 # local validation only
terraform validate
terraform fmt -check -recursive
```

Real `terraform plan/apply` requires the S3 state bucket `memorylane-terraform-state` to exist (bootstrap is a separate task — see [`infra/terraform/main.tf`](infra/terraform/main.tf)).

### CI

GitHub Actions on pull requests runs lint + format check + mypy + bandit + per-service pytest + Docker build. See [`.github/workflows/on-pr.yml`](.github/workflows/on-pr.yml).

---

## Code conventions

- **Python 3.11+** with strict mypy. New services follow the [`services/api-gateway/`](services/api-gateway/) layout: `app/main.py`, `app/config.py` (`pydantic-settings` with `env_prefix="MEMORYLANE_"`), `app/routers/`, `tests/conftest.py`.
- **FastAPI deps** use the modern `Annotated[..., Depends(...)]` pattern, not default arguments (see [`services/ingestion/app/routers/oauth.py`](services/ingestion/app/routers/oauth.py)).
- **AsyncSession** for FastAPI services (`postgresql+asyncpg`), **sync Session** for Celery workers (`postgresql+psycopg2`). Same database, different drivers per execution model.
- **Multi-tenancy is non-negotiable.** Every query filters by `tenant_id`. Postgres RLS is enabled on the relevant tables; row-level policies will be tightened in Phase 2.

---

## Roadmap

| Phase | Status | Scope |
|-------|--------|-------|
| 0 — Foundations | done | Monorepo, Terraform skeleton, docker-compose, CI |
| 1 — Ingestion + Enrichment | in progress | Google Photos OAuth, S3 upload, CLIP embeddings, pgvector writes |
| 2 — Faces, events, duplicates | next | Face detection/clustering, event clustering, duplicate detection |
| 3 — Agent orchestration v1 | planned | LangGraph search agent, AutoGen conversational agent |
| 4 — Albums, captions, BLIP-2 | planned | Auto-album generation graph (LangGraph supervisor pattern) |
| 5 — Deep agent capabilities | planned | Planning, reflection, HITL, shared memory, chaos eval |
| 6 — DPO reranker | planned | Album cover preference learning |
| 7 — Hardening + observability | planned | Grafana, guardrails, eval-in-CI, security audit |
| 8 — Demo + portfolio | planned | Live demo URL, blog post, video |

---

## Contributing

1. Branch from `main`: `git checkout -b features/<short-description>`.
2. Make changes. Run lint, mypy, and per-service pytest before pushing.
3. Open a PR; CI must be green before merge.
4. For architecture-affecting changes, add an ADR under [`docs/adr/`](docs/adr/) using [`001-template.md`](docs/adr/001-template.md).

---

## License

MIT. See [LICENSE](LICENSE).
