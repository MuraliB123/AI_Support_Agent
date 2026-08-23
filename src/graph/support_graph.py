"""LangGraph wiring for the Nimbus Home support agent.

Phase 3–4:
    ticket_in -> assess_context -> (ask_followup loop) -> retrieval
Decision / action / HITL nodes arrive in later phases.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.agents.conversation import ask_followup, assess_context, route_after_assessment
from src.agents.retrieval import retrieve_policies
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


def build_graph() -> StateGraph:
    graph = StateGraph(SupportState)

    graph.add_node("ticket_in", ticket_in)
    graph.add_node("assess_context", assess_context)
    graph.add_node("ask_followup", ask_followup)
    graph.add_node("retrieval", retrieve_policies)

    graph.add_edge(START, "ticket_in")
    graph.add_edge("ticket_in", "assess_context")
    graph.add_conditional_edges(
        "assess_context",
        route_after_assessment,
        {"need_more_info": "ask_followup", "enough_context": "retrieval"},
    )
    graph.add_edge("ask_followup", "assess_context")
    graph.add_edge("retrieval", END)

    return graph


@lru_cache(maxsize=1)
def get_compiled_graph():
    """Compile once; InMemorySaver keeps paused runs alive between HTTP calls."""
    return build_graph().compile(checkpointer=InMemorySaver())
