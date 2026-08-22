- Support Ticket Triage and Resolution agent
- The agent works over a synthetic ticket queue and small FAQ knowledge base and decides whether to auto-resolve,escalate,refuse or ask for more information.
- Replies are drafts only and are never auto sent. polices are quoted only from knowledge base. if no policy is found the agent states this and escalates rather than fabricating.

- Problem statemet:
- scenario: customer support - AI support resolution agent
- agent works over a synthetic ticket queue plus a small policy/FAQ knowledge base. For each ticket it decides: Auto-Resolve,Escalate,Refuse,or Ask for More Information, and drafts the reply for human approval.
- Flow: Ticket in -> sentiment and policy check -> RAG answer draft -> langgraph route decision -> confidence re-check loop -> HITL approval -> audit log
- safety mapping: replies are drafts, never auto sent. Policies are quoted only from the KB; if no policy is found, the agent states this and escalates rather than fabricating.Refund-abuse or abussive content requests are refused wiht a polite scripted response.
Lessons convered: RAG,ReACT,HITL approval aget,memory for customer conversation thread,Arize evalaution of answer groundness, langgraph conditional branching for auto resolve,escalate,refuse,ask clsorification routes, langgraph loops for retrival refinement, confidence re-check and human approval cycles.

- Expected agent flow 
- Ticket in -> sentiment policy check -> RAG answer draft -> langgraph route decision -> confidence re-check loop -> HITL approval -> Audit Log

- recommended project structure
- README.md
- requirements.txt
- .env.example
- config/
    - app_config.yaml
    - model_config.yaml
    - routing_rules.yaml
- data
    - tickets/
    - knowledge base
    - evaluation
        - golden_dataset.json
        - expected_routes.json
src
    - main.py
    - graph/
    - agents/
    - retrieval
    - memory
    - HITL
    - safety
    - evaluation
    - logging
    - utils
- notebooks
- tests
- outputs
- docs

- Syntehtic ticket queue
- should create ticket data like below
- ``` {
    "ticket_id": ,
    "customer_id":,
    "subject":
    "message",
    "conversation_history":,
    "priority",
} ```
- knowledge base creation
- HITL approval gate - approve/reject/edit/request regenration/escalate

- final checlist
 - synthetic ticket queue included
 - knowledge base
 - langraph flow
 - RAG
 - route decision
 - HITL
 - customer memory
 - confidence re-check loop
 - audit logs
 - evulation report over test data
 - demo script
 - readme file insturctions
 