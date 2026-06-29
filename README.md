# MemoryLane

[![CI](https://github.com/brabbit61/MemoryLane/actions/workflows/on-pr.yml/badge.svg)](https://github.com/brabbit61/MemoryLane/actions/workflows/on-pr.yml)
![Python](https://img.shields.io/badge/python-3.11+-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

An agentic AI photo library organizer. Connect your Google Photos library and a multi-agent AI system handles semantic indexing, face clustering, event detection, duplicate cleanup, and conversational search — no manual tagging required.

**Tech stack:** Python 3.11 · FastAPI · SQLAlchemy · Celery · CLIP ViT-L/14 · pgvector · Redis · MinIO/S3 · Docker · Terraform (AWS) · GitHub Actions

See [docs/architecture.md](docs/architecture.md) for a detailed breakdown of services, data flows, and the LangGraph agent design. See [docs/project-status.md](docs/project-status.md) for the full roadmap and implementation progress.

---

## Features

- **Semantic search** — natural-language queries over your photo library via CLIP ViT-L/14 text-to-image embeddings and pgvector HNSW ANN search
- **Multi-turn agent** — LangGraph agent backed by Claude Sonnet that reasons across multiple search passes, applying date, location, and camera filters automatically
- **Google Photos ingestion** — OAuth 2.0 PKCE + Picker API; no full-library access required
- **GPU enrichment pipeline** — Celery workers run CLIP image encoding (~50 ms/image on GPU), thumbnail generation, and EXIF extraction asynchronously
- **Multi-tenant isolation** — `tenant_id` enforced at ORM level and Postgres Row-Level Security on every query
- **Local-first storage** — MinIO (S3-compatible) out of the box; swap to AWS S3 with one env-var change

---

## Local Setup

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker + Docker Compose | 24+ | |
| Python | 3.11+ | |
| NVIDIA GPU + driver | 535+ | CUDA 12.x; see [Running without a GPU](#running-without-a-gpu) |
| nvidia-container-toolkit | Latest | GPU passthrough into Docker |

**Install nvidia-container-toolkit:**
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

---

### 1. GCP — Enable the Photos Picker API

1. [console.cloud.google.com](https://console.cloud.google.com) → create a project
2. **APIs & Services → Library** → enable **Photos Picker API**
3. **OAuth consent screen** → External · add your Gmail as a test user · scope: `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`
4. **Credentials → Create OAuth 2.0 Client ID** → Web application · redirect URI: `http://localhost:8001/oauth/google/callback`
5. Copy the **Client ID** and **Client Secret**

> **Note:** Use the Picker API, not the Library API. The Library API was deprecated for new apps in March 2025.

---

### 2. Environment file

Copy [.env.example](.env.example) to `.env` (gitignored) and fill in the Google OAuth credentials.

```env
MEMORYLANE_GOOGLE_CLIENT_ID=<your-client-id>
MEMORYLANE_GOOGLE_CLIENT_SECRET=<your-client-secret>
```

By default the stack stores photos in the local **MinIO** container. To store them in a real **AWS S3** bucket instead, uncomment the `MEMORYLANE_S3_*` / `MEMORYLANE_AWS_*` block in `.env.example`. See [docs/project-status.md](docs/project-status.md#terraform-aws-deployment-phase-2) for the Terraform-managed setup.

---

### 3. Start the stack

```bash
docker compose up -d --build
docker compose ps   # all services should be healthy
```

**Port map:**

| Service | URL |
|---------|-----|
| **UI (Streamlit)** | **http://localhost:8501** |
| API Gateway | http://localhost:8000 |
| Ingestion Service | http://localhost:8001 |
| Search Service | http://localhost:8002 |
| Agent Service | http://localhost:8003 |
| MinIO Console | http://localhost:9001 (`minioadmin` / `minioadmin`) |
| Postgres | localhost:**5433** |
| Redis | localhost:6379 |

> **First-run note:** The celery-worker downloads the CLIP ViT-L/14 model (~900 MB) on first start. Subsequent starts use the Docker volume cache.

> **Port 5433:** The container's Postgres is mapped to host port 5433 to avoid conflicting with a system Postgres on 5432.

---

### 4. Seed data

The schema and a dev user are applied automatically on first start:

| | Value |
|-|-------|
| Tenant ID | `00000000-0000-0000-0000-000000000001` |
| User ID | `00000000-0000-0000-0000-000000000002` |

To reset: `docker compose down -v && docker compose up -d`

---

### 5. Use the app

Open **http://localhost:8501** in your browser.

1. Sign in with the dev user ID (`00000000-0000-0000-0000-000000000002`) and tenant ID (`00000000-0000-0000-0000-000000000001`)
2. Go to the **Photos** tab → click **Connect Google Photos** → select photos in the Picker → click Done
3. The UI polls ingestion automatically and shows live progress as photos are enriched
4. Switch to the **Search** tab and type a natural-language query — the LangGraph agent returns semantically matched results

To watch GPU enrichment in the background:
```bash
docker compose logs -f celery-worker
```

---

### Running without a GPU

Set `MEMORYLANE_CLIP_DEVICE=cpu` in `docker-compose.yml` and remove the `deploy.resources.reservations` block from the `celery-worker` service. CLIP inference will be ~40–100× slower (~2–5 s/image vs ~50 ms on GPU).

---

## Running Tests

All services share `app` as their top-level package name, so tests must run per-service in separate processes to avoid `sys.modules` collisions:

```bash
pip install -e "src/api-gateway[dev]"
python -m pytest src/api-gateway/tests -v

pip install -e "src/ingestion[dev]"
python -m pytest src/ingestion/tests -v

# Workers (requires torch locally):
cd src/workers && pip install -e ".[dev]" && pytest tests -v
```

---

## Repository Structure

```
MemoryLane/
├── src/
│   ├── api-gateway/     # FastAPI, port 8000
│   ├── ingestion/       # FastAPI, port 8001 — OAuth, Picker, S3 upload
│   ├── workers/         # Celery — CLIP enrichment, thumbnails, EXIF
│   ├── search/          # FastAPI, port 8002 — CLIP text-to-image search
│   ├── agent/           # FastAPI, port 8003 — LangGraph agent (Phase 3)
│   └── ui/              # Streamlit frontend — search + Google Photos ingest
├── infra/
│   ├── db/init.sql      # Schema + seed data
│   └── terraform/       # S3 deployed; VPC/EKS/RDS/Cognito/ECR in Phase 2
├── docs/
│   ├── project-status.md  # Roadmap, phases, design decisions
│   ├── architecture.md
│   ├── agents.md
│   └── adr/
├── .github/workflows/
│   ├── on-pr.yml        # Lint, type check, security, test, docker build
│   └── on-main.yml      # Full test suite
├── docker-compose.yml
└── pyproject.toml
```
