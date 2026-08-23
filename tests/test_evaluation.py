"""Unit tests for eval scoring (no live LLM)."""

from __future__ import annotations

from src.evaluation.run_eval import score_row, summarize
from src.graph.support_graph import build_eval_graph


def test_build_eval_graph_skips_hitl():
    g = build_eval_graph()
    compiled = g.compile()
    nodes = set(compiled.get_graph().nodes)
    assert "hitl_review" not in nodes
    assert "decision" in nodes
    assert "action_resolution" in nodes


def test_score_row_route_and_policy():
    actual = {
        "decision": "resolution",
        "escalation_code": "",
        "policy_citations": ["REFUND-14DAY"],
        "retrieved_policy_ids": ["REFUND-14DAY", "SHIP-SLA"],
        "draft": "You are eligible for a return.",
    }
    expected = {
        "decision": "resolution",
        "policy_ids_any": ["REFUND-14DAY"],
    }
    score = score_row(actual, expected)
    assert score["route_match"] is True
    assert score["policy_grounding_ok"] is True
    assert score["pass"] is True


def test_score_row_fail_wrong_route():
    score = score_row(
        {"decision": "reject", "draft": "no", "retrieved_policy_ids": []},
        {"decision": "escalate", "escalation_code": "ESCALATE-LEGAL"},
    )
    assert score["route_match"] is False
    assert score["pass"] is False


def test_summarize_counts():
    rows = [
        {
            "expected": {"decision": "resolution"},
            "score": {
                "route_match": True,
                "escalation_code_match": None,
                "policy_grounding_ok": True,
                "draft_nonempty": True,
                "pass": True,
            },
        },
        {
            "expected": {"decision": "reject"},
            "score": {
                "route_match": False,
                "escalation_code_match": None,
                "policy_grounding_ok": None,
                "draft_nonempty": True,
                "pass": False,
            },
        },
    ]
    summary = summarize(rows)
    assert summary["ticket_count"] == 2
    assert summary["route_accuracy"] == 0.5
    assert summary["passed"] == 1
