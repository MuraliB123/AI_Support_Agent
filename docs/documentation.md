# Design documentation

Why this agent is shaped the way it is. Run commands: [README](../README.md). Graph: [support_graph.png](support_graph.png).

## Goals → design

| Goal | Consequence |
| --- | --- |
| No fabricated policy | Cite retrieved passages; missing policy → escalate |
| Never auto-send | Every path ends at HITL; only `approved_draft` is customer-facing |
| Stay in scope | Hard-coded reject scope (secrets / scam / out-of-scope) |
| Inspectable | Status bus for UIs + JSONL audit under `outputs/audit/` |
| Learnable | Explicit LangGraph nodes (decision ≠ actions) |

Stack: LangGraph + DeepSeek structured JSON + local BGE-small (384-d) + Atlas `$vectorSearch` + FastAPI + static UIs.

```
Customer/Agent UI → FastAPI (TicketRunner) → LangGraph (InMemorySaver)
                         │                      ├── DeepSeek
                         └─ StatusBus           └── Atlas (chunks + embedd)
```

## Graph

```
ticket_in → assess_context ⟷ ask_followup → retrieval → decision
  → action_{escalate|reject|resolution} → hitl_review → END
```

- **Decision ≠ actions** so HITL can regenerate a draft without re-triaging (unless agent forces escalate).
- **`InMemorySaver`**, `thread_id = ticket_id` — survives HTTP within one process; restart drops in-flight tickets.
- **Two interrupts:** follow-up (string resume) vs HITL (`{action, edited_draft?}`). Runner phases: `waiting_user` | `waiting_hitl` | `complete` | …

## Intake

Structured `ContextAssessment` (`enough_context`, question, summary). Caps at `max_followups` (5). Never answers policy or asks for secrets. `enough_context` drives the conditional edge.

## Retrieval

```
expand (LLM) → vector ($vectorSearch on embedd) + keyword (metadata + BM25) → RRF → final_top_k
```

| Choice | Why |
| --- | --- |
| Heading-aware MD chunks (~400–800 tok) | Better citations + metadata filters |
| Local BGE-small + Atlas | No embed API; one store for docs + ANN (`vector_index` / field `embedd`) |
| LLM query expansion | Customer phrasing ≠ policy headings |
| Dense recall-first, sparse filtered | Avoid over-constraining ANN; BM25 catches policy ids |
| RRF (`k=60`), no LLM rerank | Cheap, deterministic hybrid |

Defaults: dense/sparse top_k **12**, fuse pool **20**, `final_top_k` **10**.

## Decision & actions

- **Decision:** `escalate` \| `reject` \| `resolution` + confidence + cited chunk ids.
- **Reject scope** lives in code (`reject_scope.py`) — short, safety-critical, must not drift with KB edits.
- **Escalation criteria** live in KB MD, injected when retrieval misses escalation chunks.
- **Actions** draft only (`ActionDraft`). Escalate draft is internal; resolution must ground in passages; empty chunks → forced escalate-style note.
- `routing_rules.yaml` thresholds are mostly **hints**; code enforces HITL, citation filtering, and low-confidence flag (**0.45**).

## HITL

Approve / edit / reject / regenerate / escalate. On escalate **approve**, customers see a fixed message (`CUSTOMER_ESCALATION_MESSAGE`); agents keep the internal note in `draft`.

## Memory & audit

| Store | Persists? |
| --- | --- |
| Checkpointer, runner, status bus | Process only (UIs poll, not SSE) |
| `outputs/audit/{ticket_id}.jsonl` | Disk (best-effort; never breaks tickets) |
| Atlas `documents` | Durable KB |

No cloud tracing. Mongo `ticket_memory` / `audit_logs` in YAML are unused.

## Safety (short)

Draft-only · grounded citations · inline reject scope · intake never answers policy · escalate privacy for customers · audit cannot fail the request path.

## Non-goals (for now)

Durable multi-process checkpoints · cloud eval/tracing · LLM rerank · email/CRM send · hard rules engine replacing the decision LLM.
