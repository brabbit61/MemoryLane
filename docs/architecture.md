# MemoryLane Architecture

## Overview

MemoryLane is a multi-tenant, agentic AI photo library organizer built as a set of FastAPI microservices orchestrated by multi-agent AI systems (LangGraph, CrewAI, AutoGen).

## High-Level Components

```
Web Client (Next.js)
    │
API Gateway (FastAPI on EKS)
    │
    ├── Ingestion Service
    ├── Search Service
    ├── Agent Orchestrator (LangGraph + CrewAI)
    └── Admin / Eval Service
    │
Tool Layer (CLIP, BLIP-2, RetinaFace, ArcFace, Reranker)
    │
Data Layer (S3, RDS Postgres + pgvector, Redis)
    │
Async Workers (Celery on EKS)
```

## Data Flow

### Ingestion
1. Upload/connect source -> S3
2. Per-photo task to SQS
3. Workers: thumbnail -> CLIP embedding -> BLIP caption -> face detection
4. Event clustering (DBSCAN)
5. Auto-album generation

### Search
1. Query -> Search Service
2. Agent decides: semantic vs. multi-turn vs. tool-augmented
3. CLIP text-to-image search -> reranker -> metadata filter
4. Results with attribution

## Infrastructure

- **Cloud:** AWS (EKS, RDS, S3, Cognito, SQS)
- **IaC:** Terraform + Helm
- **CI/CD:** GitHub Actions
- **Observability:** LangSmith + Prometheus/Grafana + OpenTelemetry

See the [project document](../MemoryLane_Project_Document.md) for full details.
