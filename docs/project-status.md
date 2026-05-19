# MemoryLane — Project Status & Roadmap

## Phase Overview

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 0** | Foundations: monorepo, docker-compose, Terraform skeleton, API gateway, CI | ✅ Complete |
| **Phase 1** | Google Photos ingestion + CLIP GPU enrichment + pgvector writes | ✅ Complete |
| Phase 2 | Face detection, event clustering, duplicate detection | Planned |
| Phase 3 | LangGraph Search Agent, AutoGen Conversational Agent, web UI | Planned |
| Phase 4 | BLIP-2 captions, LangGraph Album Generation Graph (supervisor), DPO data collection | Planned |
| Phase 5 | Deep agent capabilities: plan-and-execute, reflection, HITL, chaos evals | Planned |
| Phase 6 | DPO reranker training pipeline | Planned |
| Phase 7 | Hardening: Grafana, guardrails, adversarial eval, multi-tenancy audit | Planned |
| Phase 8 | Demo library, live URL, blog post, demo video | Planned |

---

## What's Been Built

### Phase 0 — Foundations

- **Monorepo structure**: `services/` (microservices), `infra/` (Terraform + DB), `docs/` (ADRs), `.github/` (CI)
- **docker-compose**: Postgres 16 + pgvector, Redis 7, MinIO (S3-compatible), api-gateway, ingestion-svc, celery-worker with NVIDIA GPU passthrough
- **API Gateway** (`services/api-gateway`): FastAPI hello-world with health + readiness endpoints, async SQLAlchemy, pydantic-settings
- **Database schema**: `tenants`, `users`, `photos`, `photo_embeddings` (HNSW index on 768-dim vector), `oauth_tokens`; Row-Level Security enabled
- **Terraform modules** — written and validated, not yet applied to AWS:

  | Module | Resources |
  |--------|-----------|
  | `vpc` | VPC, 3 public + 3 private subnets, IGW, NAT, route tables |
  | `eks` | EKS cluster, CPU node group (t3.medium ×2), GPU node group (g5.xlarge, scales to 0) |
  | `rds` | RDS Postgres 16 (db.t3.medium), Secrets Manager password |
  | `s3` | Photos bucket + model artifacts bucket, lifecycle rules |
  | `cognito` | User pool + web client |
  | `ecr` | One ECR repository per service (api-gateway, ingestion, workers) |

- **CI (GitHub Actions)**:
  - PR: ruff lint + format, mypy, bandit security scan, pytest, docker build
  - Main: full test suite (api-gateway + ingestion); build-and-push to ECR gated until Terraform is applied

### Phase 1 — Google Photos Ingestion + CLIP Enrichment

**Ingestion service** (`services/ingestion`, port 8001):
- OAuth 2.0 with PKCE using the Photos Picker API (`photospicker.mediaitems.readonly`)
- Tokens stored in Postgres with refresh support
- Endpoints:
  - `GET /oauth/google/init` — generates Picker OAuth URL, stores PKCE verifier in Redis (TTL 600s)
  - `GET /oauth/google/callback` — exchanges code, upserts `oauth_tokens`
  - `POST /sync/google/{user_id}/start` — creates a Picker session, returns `picker_uri`
  - `POST /sync/google/{user_id}/ingest/{session_id}` — downloads selected photos, uploads to S3, dispatches enrichment tasks

**Enrichment worker** (`services/workers`):
- Celery consumer on `enrichment` queue, `prefetch_multiplier=1` (one task at a time per GPU worker)
- Generates 256px + 1024px thumbnails (Pillow LANCZOS)
- Extracts EXIF metadata (DateTimeOriginal, GPS, dimensions, camera make/model)
- Runs CLIP ViT-L/14 inference on NVIDIA GPU — ~50 ms/image vs ~2–5 s on CPU
- Writes 768-dim L2-normalized embedding to `photo_embeddings` via pgvector

**End-to-end verified locally**: 7 photos ingested → MinIO S3 → CLIP GPU enrichment → pgvector; self-similarity = 1.0000

---

## Known Gaps

| Gap | Detail | Planned fix |
|-----|--------|-------------|
| `taken_at` is null | Picker API download URL doesn't include EXIF creation time; requires a separate call to `sessions.mediaItems.list` for `creationTime` | Phase 1b |
| No text-to-image search | Embeddings are written; search endpoint not yet built | Phase 3 |
| No face clustering | Phase 2 | Phase 2 |
| AWS not deployed | Terraform written and validated; `terraform apply` not yet run | Phase 2+ |

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

## Terraform AWS Deployment (Phase 2+)

### Prerequisites

AWS CLI configured with a user/role that has `AdministratorAccess`.

### Bootstrap (one-time — before `terraform init`)

The S3 backend and DynamoDB lock table must exist before Terraform can manage state:

```bash
# State bucket
aws s3api create-bucket --bucket memorylane-terraform-state --region us-east-1
aws s3api put-bucket-versioning \
  --bucket memorylane-terraform-state \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
  --bucket memorylane-terraform-state \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block \
  --bucket memorylane-terraform-state \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Lock table
aws dynamodb create-table \
  --table-name memorylane-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### Apply

For a full environment build-out:

```bash
cd infra/terraform
terraform init
terraform plan -var-file=environments/dev/terraform.tfvars -out=tfplan.dev
terraform apply tfplan.dev
```

To bring up only the S3 buckets (the minimum needed for ingestion + search against real AWS):

```bash
terraform apply -target=module.s3 -var-file=environments/dev/terraform.tfvars
```

This provisions `memorylane-dev-photos` and `memorylane-dev-model-artifacts`. To point the running services at the real buckets, set the four `MEMORYLANE_AWS_*` / `MEMORYLANE_S3_*` vars in `.env` (see [.env.example](../.env.example)) and restart the stack. Leaving `MEMORYLANE_S3_ENDPOINT_URL` unset keeps photos in the local MinIO container.

### Enable ECR push in CI (after apply)

1. Remove `if: false` from the `build-and-push` job in `.github/workflows/on-main.yml`
2. Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to **GitHub → Settings → Secrets → Actions**

---

## CI Notes

### Why tests run per-service

All services share `app` as their top-level package name. Running `pytest services/` in one process causes `sys.modules` to cache the first service's `app`, making subsequent services import the wrong code. Each `python -m pytest services/<svc>/tests` call starts a fresh Python interpreter, eliminating the collision.

Each service directory also has a root-level `conftest.py` (not inside `tests/`) that inserts the service root at `sys.path[0]` as a fallback for environments where multiple services are installed in the same venv.

### Workers tests in CI

The workers service requires `torch` (~2 GB CUDA wheels) and a physical GPU. These tests are excluded from CI and run locally only:
```bash
cd services/workers && pip install -e ".[dev]" && pytest tests -v
```
