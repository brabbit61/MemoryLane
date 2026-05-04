# MemoryLane Agent Design

## Framework Allocation

| Framework | Use Case | Why |
|-----------|----------|-----|
| **LangGraph** | Primary orchestrator for all 5 stateful agents (A1–A4, A6) including the Album Generation supervisor graph | Stateful workflows, checkpointing, native LangSmith tracing, HITL at any node boundary |
| **AutoGen** | Conversational Search Agent (A5) | Multi-turn refinement with internal UserProxy↔Assistant dialog |

> **Note:** CrewAI was considered for Album Generation but replaced by LangGraph's multi-agent supervisor pattern. See [ADR-003](adr/003-langgraph-over-crewai.md) for the rationale.

## Agent Catalog

### A1. Ingestion Coordinator (LangGraph)
Coordinates per-photo enrichment pipeline with ReAct loop and self-correction.

### A2. Event Detector (LangGraph)
Clusters photos into events/trips using time, GPS, and visual similarity.

### A3. Album Generation Graph (LangGraph multi-agent supervisor)
A `StateGraph` with a supervisor node that routes `Command` objects to four worker nodes:
- **curator** — decides which events warrant albums
- **theme_detector** — infers album themes from captions
- **photo_selector** — picks photos using the reranker + DPO model
- **cover_designer** — selects cover photo and generates album title

Checkpointed via Postgres; HITL interrupts are supported at every node boundary.

### A4. Search Agent (LangGraph)
One-shot semantic search with tool use (vector search, metadata filter, reranker, face filter).

### A5. Conversational Search Agent (AutoGen)
Multi-turn refinement with UserProxy, SearchAssistant, and Critic agents.

### A6. Duplicate & Bad-Shot Detector (LangGraph)
Finds duplicates, near-duplicates, and bad shots using pHash + CLIP + blur detection.

## Deep Agent Capabilities

- D1: Multi-step planning (Plan-and-Execute pattern)
- D2: Reflection & self-correction loops
- D3: Tool error recovery
- D4: Human-in-the-loop interrupts
- D5: Cross-agent shared memory
- D6: LLM-as-Judge eval
- D7: Tool poisoning defense

See the [project document](../MemoryLane_Project_Document.md) sections 7 and 9 for full details.
