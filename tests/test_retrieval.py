"""Phase 4: RRF, metadata filters, and retrieval node wiring (mocked I/O)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

from src.agents import conversation as conversation_module
from src.agents import retrieval as retrieval_module
from src.agents.conversation import ContextAssessment
from src.graph.state import new_state
from src.graph.support_graph import build_graph
from src.queue import get_status_bus
from src.retrieval.expand import QueryExpansion
from src.retrieval.keyword_search import build_metadata_filter
from src.retrieval.pipeline import RetrievalResult, run_retrieval_pipeline
from src.retrieval.rerank import reciprocal_rank_fusion, rerank


def test_build_metadata_filter_combines_fields():
    filt = build_metadata_filter(
        categories=["refunds"],
        policy_ids=["REFUND-14DAY"],
        scopes=["global"],
    )
    assert "$and" in filt
    assert {"category": {"$in": ["refunds"]}} in filt["$and"]


def test_rrf_prefers_docs_in_both_lists():
    dense = [
        {"chunk_id": "a", "score": 0.9, "channel": "vector", "content": "A"},
        {"chunk_id": "b", "score": 0.8, "channel": "vector", "content": "B"},
    ]
    sparse = [
        {"chunk_id": "b", "score": 4.0, "channel": "keyword", "content": "B"},
        {"chunk_id": "c", "score": 3.0, "channel": "keyword", "content": "C"},
    ]
    fused = reciprocal_rank_fusion([dense, sparse], limit=3)
    assert fused[0]["chunk_id"] == "b"
    assert "vector" in fused[0]["rrf_ranks"]
    assert "keyword" in fused[0]["rrf_ranks"]
    assert {d["chunk_id"] for d in fused} == {"a", "b", "c"}


def test_rerank_respects_final_top_k(monkeypatch):
    monkeypatch.setattr(
        "src.retrieval.rerank.get_app_config",
        lambda: {
            "retrieval": {
                "rerank_top_n": 20,
                "final_top_k": 2,
            }
        },
    )
    monkeypatch.setattr(
        "src.retrieval.rerank.get_model_config",
        lambda: {"rerank": {"strategy": "reciprocal_rank_fusion"}},
    )
    dense = [
        {"chunk_id": f"d{i}", "score": 1.0 - i * 0.1, "channel": "vector"}
        for i in range(5)
    ]
    sparse = [
        {"chunk_id": f"s{i}", "score": 5 - i, "channel": "keyword"} for i in range(5)
    ]
    out = rerank(dense_results=dense, sparse_results=sparse)
    assert len(out) == 2


def test_pipeline_calls_expand_vector_keyword_rerank(monkeypatch):
    calls: dict[str, Any] = {}

    expansion = QueryExpansion(
        search_query="14 day return window damaged kettle",
        alternate_queries=["return cracked kettle policy"],
        keywords=["return", "refund", "kettle"],
        categories=["refunds", "warranty"],
        policy_ids=[],
        scopes=["global"],
        rationale="Refund + warranty overlap",
    )

    monkeypatch.setattr(
        "src.retrieval.pipeline.expand_query",
        lambda **kwargs: expansion,
    )

    def fake_vector(queries, **kwargs):
        calls["vector_queries"] = queries
        return [
            {
                "chunk_id": "refund-1",
                "policy_id": "REFUND-14DAY",
                "category": "refunds",
                "section_title": "Eligibility",
                "content": "14-day return window",
                "score": 0.91,
                "channel": "vector",
            }
        ]

    def fake_keyword(**kwargs):
        calls["keyword_kwargs"] = kwargs
        return [
            {
                "chunk_id": "warranty-1",
                "policy_id": "WARRANTY-DAMAGE",
                "category": "warranty",
                "section_title": "Transit damage",
                "content": "Damaged on arrival",
                "score": 3.2,
                "channel": "keyword",
            },
            {
                "chunk_id": "refund-1",
                "policy_id": "REFUND-14DAY",
                "category": "refunds",
                "section_title": "Eligibility",
                "content": "14-day return window",
                "score": 2.1,
                "channel": "keyword",
            },
        ]

    monkeypatch.setattr(
        "src.retrieval.pipeline.multi_query_vector_search", fake_vector
    )
    monkeypatch.setattr("src.retrieval.pipeline.keyword_search", fake_keyword)

    result = run_retrieval_pipeline(
        subject="Damaged kettle",
        context_summary="Cracked kettle on NH-1, wants return.",
    )

    assert calls["vector_queries"][0] == expansion.search_query
    assert calls["keyword_kwargs"]["categories"] == ["refunds", "warranty"]
    assert calls["keyword_kwargs"]["use_metadata_filter"] is True
    assert isinstance(result, RetrievalResult)
    assert result.chunks[0]["chunk_id"] == "refund-1"
    assert result.expansion["search_query"] == expansion.search_query


class FakeChatModel:
    def __init__(self, assessments: list[ContextAssessment]) -> None:
        self._assessments = list(assessments)

    def with_structured_output(self, _schema):
        def respond(_prompt_value) -> ContextAssessment:
            if len(self._assessments) > 1:
                return self._assessments.pop(0)
            return self._assessments[0]

        return RunnableLambda(respond)


@pytest.fixture
def graph():
    return build_graph().compile(checkpointer=InMemorySaver())


def test_graph_retrieval_node_publishes_status(graph, monkeypatch):
    from src.agents import actions as actions_module
    from src.agents import decision as decision_module
    from src.agents import hitl as hitl_module

    fake = FakeChatModel(
        [
            ContextAssessment(
                enough_context=True,
                missing_fields=[],
                question="",
                context_summary="Customer wants the return window for NH-9.",
            )
        ]
    )
    monkeypatch.setattr(conversation_module, "get_chat_model", lambda: fake)

    expansion = QueryExpansion(
        search_query="return window policy",
        alternate_queries=[],
        keywords=["return"],
        categories=["refunds"],
        policy_ids=[],
        scopes=["global"],
        rationale="refund intent",
    )
    monkeypatch.setattr(
        retrieval_module, "expand_query", lambda **_kwargs: expansion
    )
    monkeypatch.setattr(
        retrieval_module,
        "multi_query_vector_search",
        lambda *_a, **_k: [
            {
                "chunk_id": "c1",
                "policy_id": "REFUND-14DAY",
                "section_title": "Overview",
                "content": "14-day returns",
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
                "section_title": "Overview",
                "content": "14-day returns",
                "score": 2.0,
                "channel": "keyword",
            }
        ],
    )

    monkeypatch.setattr(
        decision_module,
        "decide_action",
        lambda state: {
            "decision": "resolution",
            "confidence": 0.9,
            "decision_rationale": "stub",
            "escalation_code": "",
            "reject_reason": "",
            "cited_chunk_ids": ["c1"],
        },
    )
    monkeypatch.setattr(
        actions_module,
        "action_resolution",
        lambda state: {
            "action_type": "resolution",
            "draft": "You have 14 days per REFUND-14DAY.",
            "draft_summary": "return window",
            "policy_citations": ["REFUND-14DAY"],
            "hitl_note": "",
        },
    )
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

    ticket_id = "TKT-RET01"
    get_status_bus().clear(ticket_id)
    state = new_state(
        ticket_id=ticket_id,
        customer_id="cust-test",
        subject="Return window",
        message="How long do I have to return?",
    )
    result = graph.invoke(state, config={"configurable": {"thread_id": ticket_id}})

    assert result["retrieved_chunks"][0]["policy_id"] == "REFUND-14DAY"
    assert result["query_expansion"]["search_query"] == "return window policy"
    assert result["decision"] == "resolution"
    assert "REFUND-14DAY" in result["draft"]

    stages = [e.stage for e in get_status_bus().events_since(ticket_id)]
    assert stages[0] == "ticket_received"
    assert "expanding_query" in stages
    assert "searching" in stages
    assert "reranking" in stages
    assert "retrieval_done" in stages
