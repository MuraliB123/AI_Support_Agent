"""LangGraph wiring for the Nimbus Home support agent.

Phase 3–6:
    ticket_in -> assess_context -> (ask_followup loop) -> retrieval
    -> decision -> (escalate | reject | resolution)
    -> hitl_review -> (regenerate loop | END)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.agents import actions as actions_module
from src.agents import conversation as conversation_module
from src.agents import decision as decision_module
from src.agents import hitl as hitl_module
from src.agents import retrieval as retrieval_module
from src.graph.state import SupportState
from src.queue import publish


def ticket_in(state: SupportState) -> dict[str, Any]:
    """Entry node: acknowledge the ticket and seed counters."""
    publish(
        state["ticket_id"],
        "ticket_received",
        "Ticket received. An assistant is reading it now.",
        subject=state.get("subject", ""),
    )
    return {"followup_count": state.get("followup_count", 0)}


# Thin wrappers so tests can monkeypatch module attributes after compile.
def _assess_context(state: SupportState) -> dict[str, Any]:
    return conversation_module.assess_context(state)


def _ask_followup(state: SupportState) -> dict[str, Any]:
    return conversation_module.ask_followup(state)


def _retrieve(state: SupportState) -> dict[str, Any]:
    return retrieval_module.retrieve_policies(state)


def _decide(state: SupportState) -> dict[str, Any]:
    return decision_module.decide_action(state)


def _action_escalate(state: SupportState) -> dict[str, Any]:
    return actions_module.action_escalate(state)


def _action_reject(state: SupportState) -> dict[str, Any]:
    return actions_module.action_reject(state)


def _action_resolution(state: SupportState) -> dict[str, Any]:
    return actions_module.action_resolution(state)


def _hitl_review(state: SupportState) -> dict[str, Any]:
    return hitl_module.hitl_review(state)


def build_graph() -> StateGraph:
    graph = StateGraph(SupportState)

    graph.add_node("ticket_in", ticket_in)
    graph.add_node("assess_context", _assess_context)
    graph.add_node("ask_followup", _ask_followup)
    graph.add_node("retrieval", _retrieve)
    graph.add_node("decision", _decide)
    graph.add_node("action_escalate", _action_escalate)
    graph.add_node("action_reject", _action_reject)
    graph.add_node("action_resolution", _action_resolution)
    graph.add_node("hitl_review", _hitl_review)

    graph.add_edge(START, "ticket_in")
    graph.add_edge("ticket_in", "assess_context")
    graph.add_conditional_edges(
        "assess_context",
        conversation_module.route_after_assessment,
        {"need_more_info": "ask_followup", "enough_context": "retrieval"},
    )
    graph.add_edge("ask_followup", "assess_context")
    graph.add_edge("retrieval", "decision")
    graph.add_conditional_edges(
        "decision",
        decision_module.route_after_decision,
        {
            "escalate": "action_escalate",
            "reject": "action_reject",
            "resolution": "action_resolution",
        },
    )
    graph.add_edge("action_escalate", "hitl_review")
    graph.add_edge("action_reject", "hitl_review")
    graph.add_edge("action_resolution", "hitl_review")
    graph.add_conditional_edges(
        "hitl_review",
        hitl_module.route_after_hitl,
        {
            "done": END,
            "regenerate_escalate": "action_escalate",
            "regenerate_reject": "action_reject",
            "regenerate_resolution": "action_resolution",
        },
    )

    return graph


@lru_cache(maxsize=1)
def get_compiled_graph():
    """Compile once; InMemorySaver keeps paused runs alive between HTTP calls."""
    return build_graph().compile(checkpointer=InMemorySaver())


def build_eval_graph() -> StateGraph:
    """Same pipeline as production, but action nodes end the run (no HITL)."""
    graph = StateGraph(SupportState)

    graph.add_node("ticket_in", ticket_in)
    graph.add_node("assess_context", _assess_context)
    graph.add_node("ask_followup", _ask_followup)
    graph.add_node("retrieval", _retrieve)
    graph.add_node("decision", _decide)
    graph.add_node("action_escalate", _action_escalate)
    graph.add_node("action_reject", _action_reject)
    graph.add_node("action_resolution", _action_resolution)

    graph.add_edge(START, "ticket_in")
    graph.add_edge("ticket_in", "assess_context")
    graph.add_conditional_edges(
        "assess_context",
        conversation_module.route_after_assessment,
        {"need_more_info": "ask_followup", "enough_context": "retrieval"},
    )
    graph.add_edge("ask_followup", "assess_context")
    graph.add_edge("retrieval", "decision")
    graph.add_conditional_edges(
        "decision",
        decision_module.route_after_decision,
        {
            "escalate": "action_escalate",
            "reject": "action_reject",
            "resolution": "action_resolution",
        },
    )
    graph.add_edge("action_escalate", END)
    graph.add_edge("action_reject", END)
    graph.add_edge("action_resolution", END)

    return graph


def reset_compiled_graph() -> None:
    """Drop the cached graph (useful after code changes in the same process)."""
    get_compiled_graph.cache_clear()
