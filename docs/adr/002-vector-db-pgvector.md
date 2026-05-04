# ADR-002: Use pgvector as Primary Vector Database

**Status:** Accepted
**Date:** 2026-04-30
**Author:** Jenit Jain

## Context

The system needs a vector database for storing CLIP image embeddings (768-dim) and caption embeddings for semantic search. Options evaluated: pgvector on RDS, Pinecone Serverless, Weaviate Cloud, ChromaDB self-hosted.

## Decision

Use **pgvector on RDS Postgres 16** as the primary vector store for v1. Benchmark against Pinecone Serverless during Phase 4 and swap if latency gains justify the cost.

## Consequences

### Positive
- Zero additional infrastructure (reuses existing Postgres)
- Transactional consistency with metadata
- Multi-tenant isolation via tenant_id column + RLS
- Simplest operational model

### Negative
- May be slower than Pinecone at scale (mitigated by HNSW index tuning)
- Manual index tuning required

### Neutral
- Blog post and architecture doc will cover both pgvector and Pinecone to demonstrate breadth
