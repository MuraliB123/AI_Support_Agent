# Nimbus Home — AI Support Agent

Learning project: ecommerce support ticket triage & resolution with **DeepSeek** (chat), local **BGE** embeddings, **MongoDB Atlas** vectors, **LCEL** RAG, and **LangGraph** routing.

Replies are **drafts only** (never auto-sent). Policies are quoted from the Markdown KB; missing policy → escalate, never fabricate.

## Stack (Phase 0)

| Concern | Choice |
| --- | --- |
| Chat / agents | DeepSeek via `langchain-deepseek` |
| Embeddings | `BAAI/bge-small-en-v1.5` (384-dim, local) |
| Vectors / memory | MongoDB Atlas (`MONGODB_URI`) |
| Orchestration | LangChain LCEL + LangGraph (later phases) |

## Setup

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env: set DEEPSEEK_API_KEY and MONGODB_URI
```

Smoke checks:

```powershell
python test-connection.py
python -m src.main --show-config
```

## Run the customer chat UI

```powershell
python -m src.main --serve
```

Then open http://127.0.0.1:8000/. The intake assistant needs a real
`DEEPSEEK_API_KEY` in `.env`; without one the UI reports a configuration error.

Knowledge base commands:

```powershell
python -m src.retrieval.ingest --dry-run   # preview chunks
python -m src.retrieval.ingest             # chunk -> MongoDB
python -m src.retrieval.embed              # add embedd vectors
python -m src.retrieval.vector_search "How long do I have to return an item?"
python -m src.retrieval.run_pipeline       # expand → vector + keyword → RRF
```

## Layout

```
config/           # app, model, routing YAML
data/             # tickets, knowledge_base, evaluation
src/              # graph, agents, retrieval, memory, hitl, safety, ...
notebooks/ tests/ outputs/ docs/
```

## Build phases

0. Scaffold — done
1. Ecommerce MD KB + chunking — done
2. Embed + Atlas vector index — done
3. Ticket intake + conversation node + chat UI + status queue — done
4. Retrieval node (query expansion, Atlas search, metadata filter, rerank) — done
5. Decision node + escalate / reject / resolution actions
6. HITL agent UI
7. Ticket memory + audit logs
8. Synthetic tickets, eval, demo

## Spec

See [project_specifications.md](project_specifications.md).
