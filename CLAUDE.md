# CLAUDE.md — MemoryLane Project Conventions

## Project Overview

MemoryLane is an agentic AI photo library organizer — a multi-tenant SaaS built with FastAPI microservices, multi-agent AI (LangGraph + AutoGen), and deployed on AWS (S3/Terraform).

## Repository Structure

```
src/               # FastAPI microservices + UI placeholder
  api-gateway/     #   REST entrypoint, health/readiness endpoints
  ingestion/       #   Google Photos OAuth + sync
  search/          #   CLIP text-to-image search, pgvector ANN
  agent/           #   LangGraph conversational agent
  workers/         #   Celery + CLIP GPU enrichment
  ui/              #   Next.js frontend (Phase 3)
infra/
  terraform/       #   AWS S3 (deployed); VPC/EKS/RDS/ECR added in Phase 2+
  db/              #   Postgres init script (pgvector schema, RLS)
docs/              # Architecture docs + ADRs
.github/workflows/ # CI/CD pipelines
```

## Development Setup

```bash
docker compose up -d          # Start Postgres, Redis, MinIO, api-gateway
docker compose logs -f        # Watch logs
```

- Postgres (pgvector): localhost:5432 (user: memorylane, pass: memorylane)
- Redis: localhost:6379
- MinIO (S3): localhost:9000 (console: localhost:9001, user: minioadmin)
- API Gateway: localhost:8000

## Code Conventions

- **Python 3.11+** — all services
- **FastAPI** with async handlers, Pydantic models for all schemas
- **Ruff** for linting + formatting (line-length 100)
- **mypy** strict mode for type checking
- **pytest** with pytest-asyncio for testing

## Service Pattern

Each service follows this structure:
```
src/<name>/
  app/
    __init__.py
    main.py       # FastAPI app
    config.py     # pydantic-settings
  tests/
    __init__.py
    conftest.py
    test_*.py
  pyproject.toml
  Dockerfile
```

## Key Decisions

- **LLM Provider:** Anthropic Claude only (Haiku for simple, Sonnet for reasoning)
- **Vector DB:** pgvector on Postgres (benchmarking Pinecone in Phase 4)
- **Multi-tenant:** tenant_id mandatory on all queries, enforced at ORM + RLS level

## Running Tests

```bash
cd src/api-gateway && pip install -e ".[dev]" && pytest tests/ -v
```

Each service gets its own Python process to avoid `sys.modules` collisions (all services share the `app` package name).

## CI

- PR: ruff lint + format check, mypy, bandit, pytest, docker build
- Main: full test suite (workers excluded — requires GPU)
