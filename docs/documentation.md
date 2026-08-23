# Design documentation

This document explains **why** the Nimbus Home support agent is shaped the way it is: product constraints, LangGraph topology, hybrid retrieval, triage, HITL, memory boundaries, and safety. For run commands see the [README](../README.md). For a screenshot tour see [demo.md](demo.md). Graph diagram: [support_graph.png](support_graph.png).

---

## 1. Product goals that drove the design

The agent triages ecommerce support tickets and **drafts** replies. It does not replace a human for sending mail, and it must not invent policy.

| Goal | Design consequence |
| --- | --- |
| Never fabricate policy | Resolution drafts cite retrieved passages; missing usable policy → escalate |
| Never auto-send | Every path ends at HITL (`interrupt`); only `approved_draft` is customer-facing |
| Stay in scope | Hard-coded reject scope (out-of-scope / secrets / scam), not editable KB text |
| Be inspectable | Live status bus for UIs + append-only JSONL audit per ticket |
| Be learnable / testable | Explicit LangGraph nodes; decision separate from action drafting |

Brand and product identity come from `config/app_config.yaml` (`Nimbus Home` / `nimbus-support-agent`). `draft_only: true` is a product flag surfaced on `/api/health`.

**Stack summary:** LangGraph orchestration, DeepSeek chat with structured JSON outputs, local `BAAI/bge-small-en-v1.5` embeddings (384-d), MongoDB Atlas `$vectorSearch`, FastAPI + static HTML/CSS/JS UIs.

---

## 2. High-level architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│ Customer UI │────▶│ FastAPI          │────▶│ LangGraph                │
│ /           │     │ TicketRunner     │     │ InMemorySaver            │
└─────────────┘     │ + status poll    │     │ thread_id = ticket_id    │
┌─────────────┐     └────────┬─────────┘     └────────────┬─────────────┘
│ Agent UI    │◀─────────────┤                            │
│ /agent      │  HITL queue  │                            ├── DeepSeek (structured)
└─────────────┘              │                            └── Atlas (chunks + embedd)
                             ▼
                      StatusBus (in-process)
                      Audit JSONL (disk)
```

| Layer | Path | Responsibility |
| --- | --- | --- |
| Graph | `src/graph/` | Topology, `SupportState`, compile + checkpointer |
| Agents | `src/agents/` | Conversation, retrieval node, decision, actions, HITL |
| Retrieval | `src/retrieval/` | Ingest, embed, expand, vector/keyword search, RRF |
| API | `src/api/` | HTTP routes, `TicketRunner` start/resume |
| Queue | `src/queue/` | In-process status events (UI polling) |
| Audit | `src/logging/audit.py` | Disk JSONL lifecycle events |
| Config | `config/*.yaml` | App, models, routing hints |
| KB | `data/knowledge_base/` | Policy Markdown |

### Why LangGraph (not a single agent loop)

Conditional edges, two interrupt kinds (customer follow-up vs HITL), and regenerate loops are first-class. Each node maps to a module that can be unit-tested with monkeypatches. A monolithic “ReAct until done” loop would blur intake, retrieval, triage, and drafting — harder to demo and harder to constrain for safety.

### Why FastAPI + static UIs

The learning surface is the agent graph and retrieval pipeline, not a SPA framework. Customer (`/`) and agent (`/agent`) share one process and the same status bus / runner. UIs poll HTTP (`~1.2s` customer, `~2s` agent queue), which is enough for a local demo without WebSocket complexity.

---

## 3. LangGraph design

### 3.1 Topology

Implemented in `src/graph/support_graph.py`:

```
START → ticket_in → assess_context ⟷ ask_followup
                  → retrieval → decision
                  → action_{escalate|reject|resolution} → hitl_review
                  → END
                     └── regenerate_* loops back to the matching action_*
```

| Node | Implementation | Role |
| --- | --- | --- |
| `ticket_in` | `support_graph.ticket_in` | Seed counters; publish `ticket_received` |
| `assess_context` | `conversation.assess_context` | Structured enough-context verdict |
| `ask_followup` | `conversation.ask_followup` | Interrupt until customer replies |
| `retrieval` | `retrieval.retrieve_policies` | Expand → dense + sparse → RRF |
| `decision` | `decision.decide_action` | Choose route + confidence + citations |
| `action_*` | `actions.action_*` | Draft text for that route |
| `hitl_review` | `hitl.hitl_review` | Interrupt for human decision |

**Routers**

- `route_after_assessment` → `need_more_info` | `enough_context`
- `route_after_decision` → `escalate` | `reject` | `resolution` (unknown → escalate)
- `route_after_hitl` → `done` | `regenerate_escalate` | `regenerate_reject` | `regenerate_resolution`

### 3.2 Decision separate from actions

Triage produces a `DecisionVerdict` (route + rationale + confidence). Drafting produces an `ActionDraft` (wording + policy citations). Keeping them as **separate nodes** means:

- HITL “request regeneration” can re-run only the action node without re-deciding.
- HITL “escalate” can force the escalate route and regenerate via `action_escalate`.
- Unit tests can assert routing independently of prose quality.

### 3.3 State (`SupportState`)

Defined in `src/graph/state.py`. Important groups:

| Group | Fields (examples) |
| --- | --- |
| Ticket | `ticket_id`, `customer_id`, `subject`, `priority` |
| Transcript | `messages` (`add_messages` reducer) |
| Intake | `conversation_status`, `followup_count`, `context_summary`, `missing_fields` |
| Retrieval | `query_expansion`, `retrieved_chunks`, dense/sparse hit counts |
| Decision | `decision`, `confidence`, `decision_rationale`, `escalation_code`, `reject_reason`, `cited_chunk_ids` |
| Action | `action_type`, `draft`, `draft_summary`, `policy_citations`, `hitl_note` |
| HITL | `hitl_status`, `hitl_action`, `approved_draft` |

### 3.4 Checkpointer and thread identity

`get_compiled_graph()` compiles once with `InMemorySaver` (`lru_cache`). Config uses `thread_id = ticket_id`, so paused interrupts survive across HTTP requests **inside one server process**.

**Choice: in-memory only.** No Postgres/Redis checkpointer. Restart drops paused tickets, runner state, and the status bus. Durable pieces that remain: Atlas KB and JSONL audit. That matches a learning/demo deployment without operating a checkpoint database.

### 3.5 Two interrupt kinds

| Kind | Node | Resume payload | Runner phase |
| --- | --- | --- | --- |
| Customer follow-up | `ask_followup` | Plain string → `TicketRunner.resume` | `waiting_user` |
| HITL review | `hitl_review` | `{action, edited_draft?}` → `TicketRunner.resume_hitl` | `waiting_hitl` |

Runner phases overall: `running` | `waiting_user` | `waiting_hitl` | `complete` | `error`.

Distinguishing phases prevents a customer reply from being treated as an HITL decision (and the reverse). Follow-up interrupts carry `{type: "followup_question", ...}`; HITL carries `{type: "hitl_review", ...}`.

### 3.6 TicketRunner

`src/api/runner.py` runs graph `invoke` on a thread pool so HTTP handlers return quickly. On interrupt it stores the interrupt payload for the agent UI / reply endpoints. On completion it records `approved_draft` (if any) and publishes terminal status events. Auth-style DeepSeek failures surface a clear customer-facing error rather than hanging the UI.

---

## 4. Intake (conversation)

Module: `src/agents/conversation.py`.

DeepSeek returns structured `ContextAssessment`:

- `enough_context` (bool) — drives the conditional edge
- `missing_fields` — short labels for what is still needed
- `question` — at most one short follow-up (≤2 missing details)
- `context_summary` — handed to retrieval and decision

**Prompt rules**

- Never answer the customer’s policy question at intake
- Never ask for passwords, full card numbers, or OTPs
- Cap loops with `conversation.max_followups` (**5** in `app_config.yaml`; code fallback 3)
- Treat “customer cannot / will not provide more” as enough context

When more info is needed, `ask_followup` calls LangGraph `interrupt()`. The customer UI shows the question; the reply resumes the same checkpointer thread and increments `followup_count`.

**Choice: structured output for routing.** A free-form chat classifier would be harder to test and easier to loop forever. The boolean `enough_context` is the contract the graph relies on.

---

## 5. Retrieval design

### 5.1 Pipeline overview

Graph node: `retrieve_policies` (`src/agents/retrieval.py`). Standalone CLI: `src/retrieval/pipeline.py` / `run_pipeline`.

```
subject + context_summary + messages
              │
              ▼
     expand_query (LLM → QueryExpansion)
              │
       ┌──────┴──────┐
       ▼             ▼
 multi_query     keyword_search
 $vectorSearch   metadata filter + BM25
 on field embedd
       │             │
       └──────┬──────┘
              ▼
   reciprocal_rank_fusion (RRF)
              ▼
     final_top_k → retrieved_chunks
     (+ citation_view for HITL)
```

Status stages published along the way: `expanding_query` → `searching` → `reranking` → `retrieval_done`.

### 5.2 Knowledge base and chunking

- **Source:** Markdown under `data/knowledge_base/` (returns, shipping, payments, warranty, account, promotions, FAQ, escalation criteria, refuse scripts, …).
- **Ingest:** Heading-aware split (`MarkdownHeaderTextSplitter` on `#` / `##` / `###`) then `RecursiveCharacterTextSplitter`.
- **Targets** (`chunking` in `app_config.yaml`): ~400–800 tokens, `overlap_ratio: 0.12`.
- **IDs:** `chunk_id = "{doc_id}::{index}"`.
- **Store:** MongoDB database `AI_KB` (env `DATABASE`), collection `documents` (env `COLLECTION`), with indexes on `chunk_id`, `policy_id`, `category`, `scope`, `doc_id`.

**Choice: heading-aware chunks.** Policy docs are sectioned. Preserving `section_title`, `policy_id`, `category`, and `scope` improves citation quality and keyword/metadata filters.

### 5.3 Embeddings and Atlas

| Setting | Value |
| --- | --- |
| Model | Local `BAAI/bge-small-en-v1.5` |
| Dimensions | **384**, normalized |
| Document field | **`embedd`** (must match Atlas index path) |
| Index name | **`vector_index`** |

**Choice: local BGE-small.** No per-query embedding API cost after ingest; dims stay fixed and must match the Atlas index. Small model is enough for a focused policy corpus.

**Choice: MongoDB Atlas `$vectorSearch`.** One store for document text/metadata + ANN. Avoids running a separate vector DB for this project. `numCandidates` is scaled from the requested limit (typically `max(limit * 10, dense_top_k)`).

### 5.4 Query expansion

`expand_query` (`src/retrieval/expand.py`) returns structured `QueryExpansion`:

- `search_query` — primary natural-language query for vectors
- `alternate_queries` — up to two paraphrases
- `keywords` — lexical terms
- `categories` — constrained to KB taxonomy (`refunds`, `shipping`, `orders`, `payments`, `warranty`, `account`, `promotions`, `faq`, `escalation`, `safety`)
- `policy_ids` — only if the ticket clearly names them
- `scopes` — prefer `global` unless tenant-specific

**Choice: LLM expansion before search.** Customer language (“box arrived smashed”) often mismatches policy headings (“damaged on delivery”). Alternates improve dense recall; categories/policy ids feed the sparse channel.

### 5.5 Dense vs sparse channels

| Channel | Mechanism | Filtering |
| --- | --- | --- |
| **Dense** | `$vectorSearch` on `embedd`; multi-query merge keeping best score per `chunk_id` | Graph path is **recall-first** (no metadata filter on vectors) |
| **Sparse** | Mongo metadata filter (`category`, `policy_id` / `policy_ids_mentioned`, `scope`) then BM25 over `section_title + policy_id + content` | Filter with **unfiltered fallback** if the filter returns empty |

**Choice: hybrid with asymmetric filtering.** Vectors catch paraphrases. BM25 + metadata catch exact policy ids and category hits. Putting hard filters only on the sparse channel avoids over-constraining ANN recall when the expansion guesses a wrong category.

### 5.6 Fusion (RRF)

`reciprocal_rank_fusion` in `src/retrieval/rerank.py` uses constant **`RRF_K = 60`** (Cormack-style):

```
score(d) = Σ_i  1 / (k + rank_i(d))
```

Fuse a pool of `rerank_top_n` (**20**), then cut to `final_top_k` (**10**). Output keeps `rrf_score`, per-channel `rrf_ranks`, and `channel="fused"`.

**Choice: RRF instead of LLM / cross-encoder rerank.** Deterministic, cheap, no extra model call on the hot path. `model_config.rerank.llm_rerank: false` leaves room to add a reranker later without redesigning the two channels.

### 5.7 Tunables

| Key | Default | Effect |
| --- | --- | --- |
| `retrieval.dense_top_k` | 12 | Vector hits |
| `retrieval.sparse_top_k` | 12 | Keyword hits |
| `retrieval.rerank_top_n` | 20 | Fusion pool before cut |
| `retrieval.final_top_k` | 10 | Chunks on state / HITL citations |
| `retrieval.default_scope` | `global` | When expansion omits scopes |

---

## 6. Decision and actions

### 6.1 Decision node

`decide_action` → structured `DecisionVerdict`:

- `action`: `escalate` | `reject` | `resolution`
- `confidence` (0–1)
- `rationale`
- `escalation_code`, `reject_reason`
- `cited_chunk_ids` (filtered in code to retrieved ids only)

**Prompt always injects** inline `REJECT_SCOPE` from `src/agents/reject_scope.py` (three hard rules: out of scope, sensitive information, scam / social engineering).

**Escalation policy text** comes from `data/knowledge_base/escalation_criteria.md` when retrieval did not already return escalation chunks (`policy_text.has_escalation_chunks` / `load_escalation_policy_text`). If escalation chunks are already present, the prompt says so instead of duplicating the full file.

**Prefer ordering encoded in the prompt**

1. Reject when REJECT SCOPE matches (or clear abuse / refuse cases)
2. Escalate when escalation triggers fire or no usable policy exists for a non-trivial request
3. Resolve only when citations can ground a customer reply

Safety injury / legal threats prefer escalate over reject.

### 6.2 Why reject scope is code, escalation is KB

| Concern | Placement | Reason |
| --- | --- | --- |
| Reject scope | Python constant | Short, safety-critical; must not drift because someone edited a Markdown chunk |
| Escalation criteria | KB Markdown (`ESCALATE-*`) | Longer, operational, belongs with other policies; can be retrieved like any doc |

### 6.3 Action nodes

Three nodes, each producing `ActionDraft` (`draft`, `summary`, `policy_citations`):

| Node | Audience | Behavior |
| --- | --- | --- |
| `action_resolution` | Customer | Ground in retrieved passages; cite `policy_id`s |
| `action_reject` | Customer | Refuse / out-of-scope tone; may adapt refuse scripts |
| `action_escalate` | **Internal** | Specialist note — not shown as-is to the customer |

If resolution is chosen but chunks are empty, the action path forces an escalate-style note (`forced_missing_policy`) rather than inventing an answer.

**Choice: draft-only actions.** There is no send/email tool in the graph. Actions only prepare text for HITL.

### 6.4 Routing YAML vs runtime enforcement

`config/routing_rules.yaml` documents intended thresholds (`min_confidence: 0.55`, `when_confidence_below: 0.45`, `require_citation`, HITL action list). Triage itself is **LLM-structured**, not a separate deterministic rules engine.

**What code actually enforces**

- HITL on the path for escalate, reject, and resolution
- `hitl.low_confidence_threshold` (default **0.45**) for UI notes / flags
- Citation id filtering to retrieved chunks
- Reject / escalation text injection as above

Treat most YAML route numbers as **hints aligned with prompt behavior**, not as a second router.

---

## 7. Human-in-the-loop (HITL)

Module: `src/agents/hitl.py`. UI: `frontend/agent/`.

### 7.1 Interrupt payload

Built by `_build_interrupt_payload`. Includes ticket metadata, decision fields, draft, policy citations, up to **10** chunk citations (id, policy, section, score), `low_confidence`, `hitl_note`, and `customer_message_preview`.

Low confidence appends a `LOW CONFIDENCE` note when `confidence < low_confidence_threshold`.

### 7.2 Agent actions

| Action | Effect |
| --- | --- |
| `approve` | `approved_draft` = customer-facing text; end |
| `edit` | Requires `edited_draft`; that becomes `approved_draft` |
| `reject` | No customer reply (`approved_draft` empty); end |
| `request_regeneration` | `hitl_status=regenerate` → same `action_*` node |
| `escalate` | Force `decision=escalate`, regenerate via `action_escalate` |

API returns 400 if `edit` is missing `edited_draft`.

### 7.3 Customer-facing escalate message

On approve of an escalate ticket, the customer does **not** see the internal specialist note. They see a fixed string:

> Your request has been escalated. A support engineer will call you within 24 hours.

Constant: `CUSTOMER_ESCALATION_MESSAGE`. Internal detail stays in `draft` for the agent UI; `customer_message_preview` / `approved_draft` use the fixed copy.

**Choice: fixed escalate copy.** Avoids leaking internal triage language and keeps the public message consistent.

---

## 8. Memory, status, and audit

| Mechanism | Persistence | Purpose |
| --- | --- | --- |
| `InMemorySaver` | Process only | Graph checkpoints / interrupts |
| `TicketRunner._runs` | Process only | Phase, interrupt snapshot, completion fields |
| `StatusBus` | Process only | UI timeline; capped at `MAX_EVENTS_PER_TICKET` (500); supports `dedupe` on resume re-entry |
| `outputs/audit/{ticket_id}.jsonl` | Disk | Append-only lifecycle events |
| Atlas `documents` | Durable | KB chunks + embeddings |

**Status bus vs “SSE”.** Producers publish stages; the customer UI polls `GET /api/tickets/{id}/events?after=`. That is simpler and reliable for a single-process demo. `dedupe=True` avoids duplicate “waiting” events when LangGraph re-enters a node after `interrupt()`.

**Audit events (examples):** `ticket_started`, `waiting_user`, `customer_reply`, `waiting_hitl`, `hitl_decision`, `complete`, `error`. Writes are best-effort (`append_audit` swallows exceptions) so logging never fails a ticket.

**YAML placeholders:** `mongodb.collections.ticket_memory` and `audit_logs` are declared but **not** wired as the runtime memory/audit path. Durable operational trail is JSONL; durable knowledge is Atlas.

**Choice: no Phoenix / Arize / OTEL.** Observability is intentional and local: status events for UX + JSONL for postmortems.

---

## 9. Model and stack choices

| Concern | Choice | Rationale |
| --- | --- | --- |
| Chat / structured JSON | DeepSeek `deepseek-chat` via `langchain-deepseek` | Structured-output capable (prefer over reasoner-only); `temperature: 0.0`, `max_tokens: 2048`, retries/timeout in `model_config.yaml` |
| Embeddings | Local BGE-small 384-d | Free at query time after ingest; dims match Atlas |
| Orchestration | LangGraph + LangChain prompts | Explicit edges, interrupts, regenerate loops |
| Vectors | Atlas `$vectorSearch` | Managed ANN beside document metadata |
| Fusion | Reciprocal Rank Fusion | Simple hybrid without a cross-encoder |
| API | FastAPI + uvicorn | Thin runner around the graph |
| UI | Static HTML/CSS/JS | Minimal customer + agent demos |

Env for a full path: `DEEPSEEK_API_KEY`, `MONGODB_URI`. Optional: `DATABASE`, `COLLECTION`, `DEEPSEEK_MODEL`.

---

## 10. API surface

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness + brand + `draft_only` |
| `POST` | `/api/tickets` | Create (`TKT-` + 8 hex), start graph |
| `POST` | `/api/tickets/{id}/reply` | Resume follow-up (`waiting_user`) |
| `POST` | `/api/tickets/{id}/hitl` | Resume HITL |
| `GET` | `/api/hitl/queue` | Tickets in `waiting_hitl` |
| `GET` | `/api/tickets/{id}/events` | Status bus poll (`after` cursor) |
| `GET` | `/api/tickets/{id}` | Ticket / run snapshot |
| `GET` | `/` , `/agent` | Customer and agent UIs |
| mount | `/ui` | Static `frontend/` |

---

## 11. Safety and grounding

1. **Draft-only** — no auto-send path; HITL required for escalate, reject, and resolution.
2. **Grounded resolution** — cite retrieved `policy_id` / passages; empty evidence forces escalate-style handling.
3. **Inline reject scope** — out of scope, secrets, scam always in the decision prompt.
4. **Escalation criteria** — KB Markdown injected when not already retrieved.
5. **Intake isolation** — conversation node does not answer policy or collect secrets.
6. **Cited chunk ids** — constrained to retrieval results.
7. **Escalate privacy** — customers get a fixed message; agents keep the internal note.
8. **Audit isolation** — audit failures do not break the request path.

---

## 12. Intentional non-goals (current)

- Durable multi-process checkpoints or shared ticket memory across servers
- Cloud tracing / evaluation dashboards
- LLM cross-encoder rerank on the hot path
- Auto-email or CRM writeback
- Hard rules engine replacing the decision LLM (YAML thresholds are mostly declarative)

These can be layered later without changing the graph’s public shape: same nodes, stronger stores or eval hooks behind them.

---

## 13. Related files

| Topic | Start here |
| --- | --- |
| Graph wiring | `src/graph/support_graph.py` |
| State schema | `src/graph/state.py` |
| Retrieval node | `src/agents/retrieval.py` |
| Expand / vector / keyword / RRF | `src/retrieval/` |
| Decision / actions / HITL | `src/agents/decision.py`, `actions.py`, `hitl.py` |
| Reject scope | `src/agents/reject_scope.py` |
| Runner | `src/api/runner.py` |
| Status bus | `src/queue/status_bus.py` |
| Config | `config/app_config.yaml`, `model_config.yaml`, `routing_rules.yaml` |
| Demo screenshots | [demo.md](demo.md) |
| Product checklist | `project_specifications.md` |
