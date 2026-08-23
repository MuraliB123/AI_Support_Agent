"""Shared LangGraph state for the support agent."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

ConversationStatus = Literal["need_more_info", "enough_context"]


class SupportState(TypedDict, total=False):
    """State threaded through every node of the support graph."""

    ticket_id: str
    customer_id: str
    subject: str
    priority: str

    # Full customer/agent transcript; add_messages appends instead of replacing
    messages: Annotated[list[Any], add_messages]

    # Conversation node output
    conversation_status: ConversationStatus
    followup_count: int
    pending_question: str
    missing_fields: list[str]
    context_summary: str

    # Retrieval node output (Phase 4)
    query_expansion: dict[str, Any]
    retrieved_chunks: list[dict[str, Any]]
    dense_hit_count: int
    sparse_hit_count: int

    # Filled by later phases (decision, actions)
    decision: str
    confidence: float
    draft: str


def new_state(
    *,
    ticket_id: str,
    customer_id: str,
    subject: str,
    message: str,
    priority: str = "normal",
) -> SupportState:
    return {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "subject": subject,
        "priority": priority,
        "messages": [{"role": "user", "content": message}],
        "followup_count": 0,
        "missing_fields": [],
        "context_summary": "",
    }
