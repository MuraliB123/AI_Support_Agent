"""Phase 3: conversation follow-up loop, interrupt/resume, and status events."""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents import conversation as conversation_module
from src.agents import retrieval as retrieval_module
from src.agents.conversation import ContextAssessment
from src.graph.state import new_state
from src.graph.support_graph import build_graph
from src.queue import get_status_bus


def _stub_retrieval(monkeypatch) -> None:
    """Phase 3 tests should not hit DeepSeek expansion or Mongo."""
    from src.retrieval.expand import QueryExpansion

    expansion = QueryExpansion(
        search_query="stub",
        alternate_queries=[],
        keywords=[],
        categories=[],
        policy_ids=[],
        scopes=["global"],
        rationale="stub",
    )
    monkeypatch.setattr(
        retrieval_module, "expand_query", lambda **_kwargs: expansion
    )
    monkeypatch.setattr(
        retrieval_module, "multi_query_vector_search", lambda *_a, **_k: []
    )
    monkeypatch.setattr(retrieval_module, "keyword_search", lambda **_k: [])
    monkeypatch.setattr(
        retrieval_module, "rerank", lambda **_k: []
    )


class FakeChatModel:
    """Stands in for ChatDeepSeek; returns queued assessments in order."""

    def __init__(self, assessments: list[ContextAssessment]) -> None:
        self._assessments = list(assessments)
        self.calls = 0

    def with_structured_output(self, _schema):
        def respond(_prompt_value) -> ContextAssessment:
            self.calls += 1
            if len(self._assessments) > 1:
                return self._assessments.pop(0)
            return self._assessments[0]

        return RunnableLambda(respond)


@pytest.fixture
def graph():
    return build_graph().compile(checkpointer=InMemorySaver())


def _run(graph, ticket_id: str):
    state = new_state(
        ticket_id=ticket_id,
        customer_id="cust-test",
        subject="Refund for damaged kettle",
        message="My kettle arrived cracked.",
    )
    config = {"configurable": {"thread_id": ticket_id}}
    return graph.invoke(state, config=config), config


def test_asks_followup_then_completes(graph, monkeypatch):
    _stub_retrieval(monkeypatch)
    fake = FakeChatModel(
        [
            ContextAssessment(
                enough_context=False,
                missing_fields=["order_number"],
                question="What is your order number?",
                context_summary="Customer reports a cracked kettle.",
            ),
            ContextAssessment(
                enough_context=True,
                missing_fields=[],
                question="",
                context_summary="Cracked kettle on order NH-1234.",
            ),
        ]
    )
    monkeypatch.setattr(conversation_module, "get_chat_model", lambda: fake)

    ticket_id = "TKT-TEST01"
    get_status_bus().clear(ticket_id)
    result, config = _run(graph, ticket_id)

    interrupts = result.get("__interrupt__")
    assert interrupts, "graph should pause to ask a follow-up"
    assert interrupts[0].value["question"] == "What is your order number?"

    resumed = graph.invoke(Command(resume="Order NH-1234"), config=config)

    assert resumed["conversation_status"] == "enough_context"
    assert resumed["followup_count"] == 1
    assert "NH-1234" in resumed["context_summary"]

    stages = [e.stage for e in get_status_bus().events_since(ticket_id)]
    assert stages[0] == "ticket_received"
    assert "info_complete" in stages
    assert stages[-1] == "retrieval_done"

    # Resuming re-runs ask_followup from the top, so the question must not
    # be published a second time.
    assert stages.count("waiting_user") == 1


def test_skips_followup_when_context_is_complete(graph, monkeypatch):
    _stub_retrieval(monkeypatch)
    fake = FakeChatModel(
        [
            ContextAssessment(
                enough_context=True,
                missing_fields=[],
                question="",
                context_summary="Customer wants return window for order NH-9.",
            )
        ]
    )
    monkeypatch.setattr(conversation_module, "get_chat_model", lambda: fake)

    ticket_id = "TKT-TEST02"
    result, _ = _run(graph, ticket_id)

    assert "__interrupt__" not in result
    assert result["conversation_status"] == "enough_context"
    assert result["followup_count"] == 0
    assert fake.calls == 1


def test_followup_budget_is_capped(graph, monkeypatch):
    """The node stops asking once max_followups is reached."""
    _stub_retrieval(monkeypatch)
    fake = FakeChatModel(
        [
            ContextAssessment(
                enough_context=False,
                missing_fields=["order_number"],
                question="Could you share your order number?",
                context_summary="Customer reports a cracked kettle.",
            )
        ]
    )
    monkeypatch.setattr(conversation_module, "get_chat_model", lambda: fake)
    monkeypatch.setattr(conversation_module, "_max_followups", lambda: 2)

    ticket_id = "TKT-TEST03"
    result, config = _run(graph, ticket_id)

    for _ in range(2):
        assert result.get("__interrupt__"), "expected another follow-up"
        result = graph.invoke(Command(resume="I don't have it"), config=config)

    assert "__interrupt__" not in result
    assert result["conversation_status"] == "enough_context"
    assert result["followup_count"] == 2
