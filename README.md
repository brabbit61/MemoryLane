# MemoryLane

An agentic AI photo library organizer. Connect your Google Photos library and a multi-agent AI system handles semantic indexing, face clustering, event detection, duplicate cleanup, and conversational search — no manual tagging required.

**Tech stack:** Python 3.11 · FastAPI · SQLAlchemy · Celery · CLIP ViT-L/14 · pgvector · Redis · MinIO/S3 · Docker · Terraform (AWS) · GitHub Actions

See [docs/project-status.md](docs/project-status.md) for the full roadmap, architecture decisions, and implementation progress.

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

Create `.env` at the repo root (gitignored):

```env
MEMORYLANE_GOOGLE_CLIENT_ID=<your-client-id>
MEMORYLANE_GOOGLE_CLIENT_SECRET=<your-client-secret>
```

---

### 3. Start the stack

```bash
docker compose up -d --build
docker compose ps   # all services should be healthy
```

**Port map:**

| Service | URL |
|---------|-----|
| API Gateway | http://localhost:8000 |
| Ingestion Service | http://localhost:8001 |
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

### 5. Ingest photos from Google Photos

```bash
# Step 1 — Start OAuth. Open the returned auth_url in your browser.
curl "http://localhost:8001/oauth/google/init?user_id=00000000-0000-0000-0000-000000000002"

# Step 2 — Create a Picker session
curl -X POST "http://localhost:8001/sync/google/00000000-0000-0000-0000-000000000002/start"
# Returns picker_uri — open it in your browser, select photos, click Done

# Step 3 — Trigger ingestion
curl -X POST "http://localhost:8001/sync/google/00000000-0000-0000-0000-000000000002/ingest/<session_id>"

# Watch enrichment
docker compose logs -f celery-worker

# Verify
psql -h localhost -p 5433 -U memorylane -d memorylane \
  -c "SELECT count(*) FROM photo_embeddings;"
```

---

### Running without a GPU

Set `MEMORYLANE_CLIP_DEVICE=cpu` in `docker-compose.yml` and remove the `deploy.resources.reservations` block from the `celery-worker` service. CLIP inference will be ~40–100× slower (~2–5 s/image vs ~50 ms on GPU).

---

## Running Tests

All services share `app` as their top-level package name, so tests must run per-service in separate processes to avoid `sys.modules` collisions:

```bash
pip install -e "services/api-gateway[dev]"
python -m pytest services/api-gateway/tests -v

pip install -e "services/ingestion[dev]"
python -m pytest services/ingestion/tests -v

# Workers (requires torch locally):
cd services/workers && pip install -e ".[dev]" && pytest tests -v
```

---

## Repository Structure

```
MemoryLane/
├── services/
│   ├── api-gateway/     # FastAPI, port 8000
│   ├── ingestion/       # FastAPI, port 8001 — OAuth, Picker, S3 upload
│   ├── workers/         # Celery — CLIP enrichment, thumbnails, EXIF
│   ├── search/          # Planned (Phase 3)
│   └── agent/           # Planned (Phase 3)
├── infra/
│   ├── db/init.sql      # Schema + seed data
│   └── terraform/       # VPC, EKS, RDS, S3, Cognito, ECR modules
├── docs/
│   ├── project-status.md  # Roadmap, phases, design decisions
│   ├── architecture.md
│   ├── agents.md
│   └── adr/
├── .github/workflows/
│   ├── on-pr.yml        # Lint, type check, security, test, docker build
│   └── on-main.yml      # Full test suite + ECR push (gated)
├── docker-compose.yml
└── pyproject.toml
```
