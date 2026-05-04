# CLAUDE.md — MemoryLane Project Conventions

## Project Overview

MemoryLane is an agentic AI photo library organizer — a multi-tenant SaaS built with FastAPI microservices, multi-agent AI (LangGraph, CrewAI, AutoGen), and deployed on AWS (EKS/Terraform).

## Repository Structure

```
services/          # FastAPI microservices (api-gateway, ingestion, search, agent, workers)
infra/             # Terraform modules + Helm charts + DB init scripts
docs/              # Architecture docs + ADRs
ml/                # DPO training pipeline + eval datasets
evals/             # Evaluation framework
ui/                # Next.js frontend
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
services/<name>/
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
- **No fine-tuning in v1** — compensated by deeper agentic patterns
- **DPO:** Real preferences only, ~300 pairs, album cover selection task
- **Multi-tenant:** tenant_id mandatory on all queries, enforced at ORM + RLS level

## Running Tests

```bash
cd services/api-gateway && pip install -e ".[dev]" && pytest tests/ -v
```

## CI

- PR: ruff lint + format check, mypy, bandit, pytest, docker build
- Main: full test suite, build + push to ECR, deploy to staging
