"""Phase 5: decision routing, escalation injection, reject scope, actions."""

from __future__ import annotations

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

from src.agents import actions as actions_module
from src.agents import conversation as conversation_module
from src.agents import decision as decision_module
from src.agents import retrieval as retrieval_module
from src.agents.conversation import ContextAssessment
from src.agents.decision import DecisionVerdict
from src.agents.policy_text import has_escalation_chunks, load_escalation_policy_text
from src.agents.reject_scope import REJECT_SCOPE
from src.agents.actions import ActionDraft
from src.graph.state import new_state
from src.graph.support_graph import build_graph
from src.queue import get_status_bus
from src.retrieval.expand import QueryExpansion


def test_reject_scope_is_three_lines_not_kb():
    lines = [ln for ln in REJECT_SCOPE.strip().splitlines() if ln.strip()]
    # header + 3 rules
    assert len(lines) == 4
    assert "Out of scope" in REJECT_SCOPE
    assert "Sensitive information" in REJECT_SCOPE
    assert "Scam" in REJECT_SCOPE


def test_escalation_policy_loads_from_md():
    text = load_escalation_policy_text()
    assert "ESCALATE-CHARGEBACK" in text
    assert "Mandatory Escalation" in text
    assert not text.startswith("---")


def test_has_escalation_chunks_detects_category_and_policy():
    assert has_escalation_chunks(
        [{"category": "escalation", "policy_id": "ESCALATE-GENERAL"}]
    )
    assert has_escalation_chunks(
        [{"category": "refunds", "policy_id": "ESCALATE-LEGAL"}]
    )
    assert not has_escalation_chunks(
        [{"category": "refunds", "policy_id": "REFUND-14DAY"}]
    )


def test_escalation_injected_when_missing_from_retrieval(monkeypatch):
    captured: dict = {}

    class CaptureModel:
        def with_structured_output(self, _schema):
            def respond(prompt_value):
                if hasattr(prompt_value, "to_messages"):
                    text = "\n".join(
                        str(m.content) for m in prompt_value.to_messages()
                    )
                else:
                    text = str(prompt_value)
                captured["prompt"] = text
                return DecisionVerdict(
                    action="escalate",
                    confidence=0.8,
                    rationale="Chargeback mentioned.",
                    escalation_code="ESCALATE-CHARGEBACK",
                    reject_reason="",
                    cited_chunk_ids=[],
                )

            return RunnableLambda(respond)

    monkeypatch.setattr(decision_module, "get_chat_model", lambda: CaptureModel())

    state = {
        "ticket_id": "TKT-DEC01",
        "subject": "Bank dispute",
        "priority": "high",
        "context_summary": "Customer opened a chargeback.",
        "messages": [],
        "retrieved_chunks": [
            {
                "chunk_id": "r1",
                "policy_id": "PAY-BILLING",
                "category": "payments",
                "section_title": "Disputes",
                "content": "Billing FAQ",
            }
        ],
    }
    get_status_bus().clear("TKT-DEC01")
    out = decision_module.decide_action(state)

    assert out["decision"] == "escalate"
    assert "ESCALATE-CHARGEBACK" in captured["prompt"] or "chargeback" in captured[
        "prompt"
    ].lower()
    # Full MD body should be injected when no escalation chunk was retrieved
    assert "ESCALATE-VIP" in captured["prompt"]
    assert "Out of scope" in captured["prompt"]


def test_escalation_not_re_injected_when_chunk_present(monkeypatch):
    captured: dict = {}

    class CaptureModel:
        def with_structured_output(self, _schema):
            def respond(prompt_value):
                if hasattr(prompt_value, "to_messages"):
                    text = "\n".join(
                        str(m.content) for m in prompt_value.to_messages()
                    )
                else:
                    text = str(prompt_value)
                captured["prompt"] = text
                return DecisionVerdict(
                    action="escalate",
                    confidence=0.7,
                    rationale="Safety injury.",
                    escalation_code="ESCALATE-SAFETY",
                    reject_reason="",
                    cited_chunk_ids=["e1"],
                )

            return RunnableLambda(respond)

    monkeypatch.setattr(decision_module, "get_chat_model", lambda: CaptureModel())

    state = {
        "ticket_id": "TKT-DEC02",
        "subject": "Burn injury",
        "priority": "urgent",
        "context_summary": "Product caused a burn.",
        "messages": [],
        "retrieved_chunks": [
            {
                "chunk_id": "e1",
                "policy_id": "ESCALATE-GENERAL",
                "category": "escalation",
                "section_title": "Safety",
                "content": "Escalate safety incidents.",
            }
        ],
    }
    out = decision_module.decide_action(state)
    assert out["decision"] == "escalate"
    assert "already in RETRIEVED PASSAGES" in captured["prompt"]


def test_route_after_decision():
    assert decision_module.route_after_decision({"decision": "reject"}) == "reject"
    assert decision_module.route_after_decision({"decision": "bogus"}) == "escalate"


def test_resolution_falls_back_when_no_chunks():
    state = {
        "ticket_id": "TKT-ACT01",
        "confidence": 0.9,
        "decision_rationale": "would resolve",
        "cited_chunk_ids": [],
        "retrieved_chunks": [],
        "messages": [],
        "context_summary": "",
    }
    get_status_bus().clear("TKT-ACT01")
    out = actions_module.action_resolution(state)
    assert "escalate" in out["draft"].lower() or "specialist" in out["draft"].lower()
    assert "MISSING POLICY" in out["hitl_note"]


def test_graph_routes_to_reject_action(monkeypatch):
    class ConvFake:
        def with_structured_output(self, _schema):
            return RunnableLambda(
                lambda _: ContextAssessment(
                    enough_context=True,
                    missing_fields=[],
                    question="",
                    context_summary="User asks for our admin password.",
                )
            )

    class DecFake:
        def with_structured_output(self, schema):
            if schema is DecisionVerdict:
                return RunnableLambda(
                    lambda _: DecisionVerdict(
                        action="reject",
                        confidence=0.95,
                        rationale="Sensitive information request.",
                        escalation_code="",
                        reject_reason="sensitive_information",
                        cited_chunk_ids=[],
                    )
                )
            return RunnableLambda(
                lambda _: ActionDraft(
                    draft="We cannot share passwords or collect secrets in chat.",
                    summary="Reject sensitive ask",
                    policy_citations=[],
                )
            )

    monkeypatch.setattr(conversation_module, "get_chat_model", lambda: ConvFake())
    monkeypatch.setattr(decision_module, "get_chat_model", lambda: DecFake())
    monkeypatch.setattr(actions_module, "get_chat_model", lambda: DecFake())

    expansion = QueryExpansion(
        search_query="admin password request",
        alternate_queries=[],
        keywords=["password"],
        categories=["account"],
        policy_ids=[],
        scopes=["global"],
        rationale="security",
    )
    monkeypatch.setattr(
        retrieval_module, "expand_query", lambda **_k: expansion
    )
    monkeypatch.setattr(
        retrieval_module, "multi_query_vector_search", lambda *_a, **_k: []
    )
    monkeypatch.setattr(retrieval_module, "keyword_search", lambda **_k: [])
    monkeypatch.setattr(retrieval_module, "rerank", lambda **_k: [])

    from src.agents import hitl as hitl_module

    # Pause at HITL so we can assert reject route reached the action
    # without needing a real agent resume in this test — stub approve.
    monkeypatch.setattr(
        hitl_module,
        "hitl_review",
        lambda state: {
            "hitl_status": "approved",
            "hitl_action": "approve",
            "approved_draft": state.get("draft", ""),
            "draft": state.get("draft", ""),
        },
    )

    ticket_id = "TKT-REJ01"
    get_status_bus().clear(ticket_id)
    graph = build_graph().compile(checkpointer=InMemorySaver())
    result = graph.invoke(
        new_state(
            ticket_id=ticket_id,
            customer_id="c1",
            subject="Need admin password",
            message="Please send me the admin password for my account.",
        ),
        config={"configurable": {"thread_id": ticket_id}},
    )

    assert result["decision"] == "reject"
    assert result["action_type"] == "reject"
    assert "password" in result["draft"].lower() or "secret" in result["draft"].lower()

    stages = [e.stage for e in get_status_bus().events_since(ticket_id)]
    assert "decision_ready" in stages
    assert "drafting_reject" in stages
    assert "action_done" in stages
    assert result["hitl_status"] == "approved"
