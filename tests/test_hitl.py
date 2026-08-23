"""Phase 6: HITL interrupt, approve/edit/reject/regenerate routing."""

from __future__ import annotations

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents import actions as actions_module
from src.agents import conversation as conversation_module
from src.agents import decision as decision_module
from src.agents import hitl as hitl_module
from src.agents import retrieval as retrieval_module
from src.agents.actions import ActionDraft
from src.agents.conversation import ContextAssessment
from src.agents.decision import DecisionVerdict
from src.graph.state import new_state
from src.graph.support_graph import build_graph
from src.queue import get_status_bus
from src.retrieval.expand import QueryExpansion


def _stub_upstream_to_hitl(monkeypatch, *, confidence: float = 0.9) -> None:
    class ConvFake:
        def with_structured_output(self, _schema):
            return RunnableLambda(
                lambda _: ContextAssessment(
                    enough_context=True,
                    missing_fields=[],
                    question="",
                    context_summary="Customer asks about the 14-day return window.",
                )
            )

    class DecFake:
        def with_structured_output(self, schema):
            if schema is DecisionVerdict:
                return RunnableLambda(
                    lambda _: DecisionVerdict(
                        action="resolution",
                        confidence=confidence,
                        rationale="Clear REFUND-14DAY match.",
                        escalation_code="",
                        reject_reason="",
                        cited_chunk_ids=["c1"],
                    )
                )
            return RunnableLambda(
                lambda _: ActionDraft(
                    draft="You may return within 14 days under REFUND-14DAY.",
                    summary="return window",
                    policy_citations=["REFUND-14DAY"],
                )
            )

    monkeypatch.setattr(conversation_module, "get_chat_model", lambda: ConvFake())
    monkeypatch.setattr(decision_module, "get_chat_model", lambda: DecFake())
    monkeypatch.setattr(actions_module, "get_chat_model", lambda: DecFake())

    expansion = QueryExpansion(
        search_query="14 day return",
        alternate_queries=[],
        keywords=["return"],
        categories=["refunds"],
        policy_ids=[],
        scopes=["global"],
        rationale="refund",
    )
    monkeypatch.setattr(retrieval_module, "expand_query", lambda **_k: expansion)
    monkeypatch.setattr(
        retrieval_module,
        "multi_query_vector_search",
        lambda *_a, **_k: [
            {
                "chunk_id": "c1",
                "policy_id": "REFUND-14DAY",
                "category": "refunds",
                "section_title": "Overview",
                "content": "14-day return window",
                "score": 0.9,
                "channel": "vector",
            }
        ],
    )
    monkeypatch.setattr(
        retrieval_module,
        "keyword_search",
        lambda **_k: [
            {
                "chunk_id": "c1",
                "policy_id": "REFUND-14DAY",
                "category": "refunds",
                "section_title": "Overview",
                "content": "14-day return window",
                "score": 2.0,
                "channel": "keyword",
            }
        ],
    )


def test_route_after_hitl():
    assert hitl_module.route_after_hitl({"hitl_status": "approved"}) == "done"
    assert (
        hitl_module.route_after_hitl(
            {"hitl_status": "regenerate", "decision": "escalate"}
        )
        == "regenerate_escalate"
    )
    assert (
        hitl_module.route_after_hitl(
            {"hitl_status": "regenerate", "decision": "resolution"}
        )
        == "regenerate_resolution"
    )


def test_hitl_approve_via_interrupt(monkeypatch):
    _stub_upstream_to_hitl(monkeypatch)
    graph = build_graph().compile(checkpointer=InMemorySaver())
    ticket_id = "TKT-HITL01"
    get_status_bus().clear(ticket_id)
    config = {"configurable": {"thread_id": ticket_id}}

    paused = graph.invoke(
        new_state(
            ticket_id=ticket_id,
            customer_id="c1",
            subject="Return window",
            message="How long to return?",
        ),
        config=config,
    )
    interrupts = paused.get("__interrupt__")
    assert interrupts
    assert interrupts[0].value["type"] == "hitl_review"
    assert "REFUND-14DAY" in interrupts[0].value["draft"]

    stages = [e.stage for e in get_status_bus().events_since(ticket_id)]
    assert "waiting_hitl" in stages

    done = graph.invoke(
        Command(resume={"action": "approve"}),
        config=config,
    )
    assert done["hitl_status"] == "approved"
    assert done["approved_draft"]
    assert "__interrupt__" not in done


def test_hitl_edit_saves_edited_draft(monkeypatch):
    _stub_upstream_to_hitl(monkeypatch)
    graph = build_graph().compile(checkpointer=InMemorySaver())
    ticket_id = "TKT-HITL02"
    config = {"configurable": {"thread_id": ticket_id}}
    graph.invoke(
        new_state(
            ticket_id=ticket_id,
            customer_id="c1",
            subject="Return window",
            message="How long to return?",
        ),
        config=config,
    )
    done = graph.invoke(
        Command(
            resume={
                "action": "edit",
                "edited_draft": "Edited: 14 days under REFUND-14DAY.",
            }
        ),
        config=config,
    )
    assert done["hitl_status"] == "approved"
    assert done["approved_draft"].startswith("Edited:")


def test_hitl_regenerate_loops_to_action(monkeypatch):
    _stub_upstream_to_hitl(monkeypatch)
    drafts = [
        ActionDraft(
            draft="First draft REFUND-14DAY.",
            summary="v1",
            policy_citations=["REFUND-14DAY"],
        ),
        ActionDraft(
            draft="Second draft REFUND-14DAY after regenerate.",
            summary="v2",
            policy_citations=["REFUND-14DAY"],
        ),
    ]

    class DraftFake:
        def with_structured_output(self, schema):
            if schema is DecisionVerdict:
                return RunnableLambda(
                    lambda _: DecisionVerdict(
                        action="resolution",
                        confidence=0.9,
                        rationale="ok",
                        cited_chunk_ids=["c1"],
                    )
                )

            def respond(_):
                return drafts.pop(0) if drafts else ActionDraft(
                    draft="fallback", summary="", policy_citations=[]
                )

            return RunnableLambda(respond)

    monkeypatch.setattr(actions_module, "get_chat_model", lambda: DraftFake())
    monkeypatch.setattr(decision_module, "get_chat_model", lambda: DraftFake())

    graph = build_graph().compile(checkpointer=InMemorySaver())
    ticket_id = "TKT-HITL03"
    config = {"configurable": {"thread_id": ticket_id}}

    paused = graph.invoke(
        new_state(
            ticket_id=ticket_id,
            customer_id="c1",
            subject="Return window",
            message="How long?",
        ),
        config=config,
    )
    assert "First draft" in paused["__interrupt__"][0].value["draft"]

    paused2 = graph.invoke(
        Command(resume={"action": "request_regeneration"}),
        config=config,
    )
    assert paused2.get("__interrupt__")
    assert "Second draft" in paused2["__interrupt__"][0].value["draft"]

    done = graph.invoke(Command(resume={"action": "approve"}), config=config)
    assert done["hitl_status"] == "approved"
    assert "Second draft" in done["approved_draft"]


def test_low_confidence_note_in_interrupt(monkeypatch):
    _stub_upstream_to_hitl(monkeypatch, confidence=0.2)
    monkeypatch.setattr(
        actions_module,
        "action_resolution",
        lambda state: {
            "action_type": "resolution",
            "draft": "Uncertain draft.",
            "draft_summary": "uncertain",
            "policy_citations": [],
            "hitl_note": "",
        },
    )
    graph = build_graph().compile(checkpointer=InMemorySaver())
    ticket_id = "TKT-HITL04"
    paused = graph.invoke(
        new_state(
            ticket_id=ticket_id,
            customer_id="c1",
            subject="Vague ask",
            message="Help?",
        ),
        config={"configurable": {"thread_id": ticket_id}},
    )
    note = paused["__interrupt__"][0].value.get("hitl_note", "")
    assert "LOW CONFIDENCE" in note
    assert paused["__interrupt__"][0].value.get("low_confidence") is True


def test_escalate_approve_shows_static_customer_message(monkeypatch):
    """Customer gets a fixed escalation notice; internal draft stays for agents."""
    _stub_upstream_to_hitl(monkeypatch)

    monkeypatch.setattr(
        decision_module,
        "decide_action",
        lambda state: {
            "decision": "escalate",
            "confidence": 0.9,
            "decision_rationale": "Chargeback filed.",
            "escalation_code": "ESCALATE-CHARGEBACK",
            "reject_reason": "",
            "cited_chunk_ids": [],
        },
    )
    monkeypatch.setattr(
        actions_module,
        "action_escalate",
        lambda state: {
            "action_type": "escalate",
            "draft": "INTERNAL: route to billing risk for chargeback NH-1.",
            "draft_summary": "chargeback handoff",
            "policy_citations": ["ESCALATE-GENERAL"],
            "hitl_note": "",
        },
    )

    graph = build_graph().compile(checkpointer=InMemorySaver())
    ticket_id = "TKT-HITL05"
    config = {"configurable": {"thread_id": ticket_id}}
    paused = graph.invoke(
        new_state(
            ticket_id=ticket_id,
            customer_id="c1",
            subject="Chargeback",
            message="I filed a bank dispute.",
        ),
        config=config,
    )
    value = paused["__interrupt__"][0].value
    assert value["decision"] == "escalate"
    assert "INTERNAL" in value["draft"]
    assert "24 hours" in value["customer_message_preview"]

    done = graph.invoke(Command(resume={"action": "approve"}), config=config)
    assert done["draft"].startswith("INTERNAL")
    assert done["approved_draft"] == hitl_module.CUSTOMER_ESCALATION_MESSAGE
    assert "24 hours" in done["approved_draft"]
    assert "INTERNAL" not in done["approved_draft"]
