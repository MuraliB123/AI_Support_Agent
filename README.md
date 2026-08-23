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

## Layout

```
config/           # app, model, routing YAML
data/             # tickets, knowledge_base, evaluation
src/              # graph, agents, retrieval, memory, hitl, safety, ...
notebooks/ tests/ outputs/ docs/
```

## Build phases

0. Scaffold (current)
1. Ecommerce MD KB + chunking
2. Embed + Atlas vector index
3. Hybrid retrieve + rerank
4. LCEL grounded draft + safety
5. Customer/ticket memory
6. LangGraph routes + confidence loop
7. HITL + audit logs
8. Synthetic tickets, eval, demo

## Spec

See [project_specifications.md](project_specifications.md).
