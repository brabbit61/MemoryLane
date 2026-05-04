# MemoryLane Evaluation Framework

## Eval Categories

| ID | Category | Dataset Size | Key Metrics |
|----|----------|-------------|-------------|
| E1 | Search Quality | 200 queries | Precision@5, Recall@10, MRR, NDCG |
| E2 | Face Clustering | 500 photos | Adjusted Rand Index, cluster purity |
| E3 | Event Detection | 1K photos | Cluster purity, event boundary F1 |
| E4 | Duplicate Detection | 200 groups | Precision, Recall, F1 |
| E5 | Agent Task Completion | 50 scenarios | Success rate, turns to success |
| E6 | DPO Reranker | 60 pairs | Pairwise agreement % |
| E7 | Latency & Cost | Continuous | p95 latency, cost per 1K photos |

## Regression Gates

CI fails if:
- Search Precision@5 drops below 0.75 or > 5% relative
- Face cluster ARI drops > 0.05
- Hallucination rate exceeds 5%

## Infrastructure

- Eval datasets versioned in Git (small) or S3 (large)
- `eval-svc` microservice for execution
- Results stored in Postgres + LangSmith
- Grafana panel for eval-score trends

See the [project document](../MemoryLane_Project_Document.md) section 16 for full details.
