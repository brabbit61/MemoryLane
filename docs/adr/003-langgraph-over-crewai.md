# ADR-003: Replace CrewAI with LangGraph Multi-Agent Supervisor for Album Generation

**Status:** Accepted
**Date:** 2026-05-03
**Author:** Jenit Jain

## Context

The original design (see project document §7) allocated three agent frameworks across distinct use cases:

- **LangGraph** — primary orchestrator for 4 of 6 agents
- **CrewAI** — Album Generation Crew (Curator → Theme Detector → Photo Selector → Cover Designer)
- **AutoGen** — Conversational Search Agent

The Album Generation Crew was assigned to CrewAI because its `Agent(role=..., goal=..., backstory=...)` abstraction maps naturally to the crew metaphor, and the project document targeted a JD that explicitly named CrewAI as a required skill.

After implementation planning, three concrete problems emerged with this allocation:

1. **Observability fragmentation.** The project commits to 100% LangSmith trace coverage as a hard success metric (§16, E7). CrewAI has its own tracing model that does not integrate natively with LangSmith. Bridging them requires manual `@traceable` wrapping of every CrewAI callback — a maintenance surface that grows with every CrewAI version bump.

2. **Dependency collision risk.** CrewAI pins its own version of LangChain core. Running both CrewAI and LangGraph in the same `agent-svc` process creates a tight version coupling that has historically caused `pip` resolution failures on LangChain patch upgrades.

3. **LangGraph already covers the pattern.** LangGraph's [multi-agent supervisor](https://langchain-ai.github.io/langgraph/concepts/multi_agent/) pattern — a top-level `StateGraph` with a `supervisor` node that routes `Command` objects to worker subgraphs — implements the same hierarchical delegation that CrewAI provides, with native LangSmith tracing, checkpointing, and HITL support.

## Decision

Remove CrewAI as a dependency. Implement the Album Generation Crew as a **LangGraph multi-agent supervisor graph**:

```
AlbumGenerationGraph (StateGraph)
    │
    └── supervisor_node  (routes via Command)
            ├── curator_node        → decides which events become albums
            ├── theme_detector_node → infers album themes from captions
            ├── photo_selector_node → picks photos via reranker + DPO model
            └── cover_designer_node → selects cover photo + generates title
```

Each worker node is a standard LangGraph node. The supervisor is a Claude Sonnet call that reads the current `AlbumState` and returns a `Command(goto=<next_worker>)`. The graph terminates when the supervisor returns `Command(goto=END)`.

State is persisted via LangGraph's built-in `checkpointer` (Postgres), giving free HITL interrupt support at every node boundary.

## Consequences

### Positive
- Single agent framework → single trace tree in LangSmith per album generation run
- No cross-framework dependency version conflicts
- LangGraph checkpointing applies uniformly to all 6 agents (HITL can interrupt album generation at any node, not just at the CrewAI task level)
- Simpler `agent-svc` container: one fewer heavy dependency (~50MB image reduction)
- The hierarchical multi-agent capability is still clearly demonstrated and is architecturally richer (custom routing logic, parallel subgraph execution via `Send`)

### Negative
- Loses CrewAI's declarative `role/goal/backstory` semantics — the crew structure must be expressed in code and prompts rather than framework primitives
- The JD row "CrewAI" in the coverage matrix (§23) is removed; addressed in the portfolio narrative by explaining the trade-off as a deliberate engineering decision (ADR-003)

### Neutral
- AutoGen usage is unchanged — it remains the right fit for multi-turn conversational agents where the UserProxy↔Assistant dialog loop is the primary pattern
- The "three frameworks" portfolio angle is preserved via LangGraph + AutoGen, with CrewAI discussed as evaluated-and-replaced in the blog post
