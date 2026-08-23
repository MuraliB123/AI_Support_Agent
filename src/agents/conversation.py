"""Conversation node: collect enough ticket context before retrieval runs."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.queue import publish
from src.utils.config import get_app_config
from src.utils.models import get_chat_model

SYSTEM_PROMPT = """You are the intake assistant for {brand}, an online home-goods store.

Your only job is to decide whether a support ticket contains enough information
for a policy specialist to act on it. You never answer the customer's question,
never quote policy, and never promise refunds or outcomes.

Useful details depend on the topic, for example:
- Orders / shipping: order number, item, delivery date, tracking status
- Refunds / returns: order number, delivery date, item condition, reason
- Damage / warranty: item, what is wrong, whether photos exist, delivery date
- Payments: order number, amount, payment method, what the customer sees
- Account: account email, what the customer already tried

Rules:
- If the customer has already given enough to route and research the issue, stop asking.
- Ask about at most two missing details at a time, in one short friendly question.
- Never ask for full card numbers, passwords, or other sensitive credentials.
- If the customer refuses or cannot provide details, treat the context as complete.
"""

HUMAN_PROMPT = """Ticket subject: {subject}
Follow-up questions asked so far: {followup_count} (maximum {max_followups})

Conversation so far:
{transcript}

Decide whether there is enough context to hand this ticket to the policy specialist."""


class ContextAssessment(BaseModel):
    """Structured verdict from the conversation node."""

    enough_context: bool = Field(
        description="True when the specialist can act without more customer input"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Short names of details still missing, e.g. ['order_number']",
    )
    question: str = Field(
        default="",
        description="One short follow-up question; empty when enough_context is true",
    )
    context_summary: str = Field(
        default="",
        description="Two or three sentences summarising the customer's request",
    )


def _max_followups() -> int:
    return int(get_app_config().get("conversation", {}).get("max_followups", 3))


def _render_transcript(messages: list[Any]) -> str:
    lines: list[str] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            role = "Customer"
        elif isinstance(message, AIMessage):
            role = "Agent"
        else:
            role = getattr(message, "type", "unknown").capitalize()
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines) if lines else "(no messages yet)"


def assess_context(state: dict[str, Any]) -> dict[str, Any]:
    """Judge whether the ticket has enough detail; produce a follow-up if not."""
    ticket_id = state["ticket_id"]
    followup_count = state.get("followup_count", 0)
    max_followups = _max_followups()

    publish(ticket_id, "collecting_info", "Reviewing your request...")

    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
    )
    chain = prompt | get_chat_model().with_structured_output(ContextAssessment)
    assessment: ContextAssessment = chain.invoke(
        {
            "brand": get_app_config()["app"]["brand"],
            "subject": state.get("subject", "(no subject)"),
            "followup_count": followup_count,
            "max_followups": max_followups,
            "transcript": _render_transcript(state.get("messages", [])),
        }
    )

    budget_exhausted = followup_count >= max_followups
    done = assessment.enough_context or budget_exhausted or not assessment.question

    if done:
        reason = (
            "Follow-up limit reached, continuing with available details."
            if budget_exhausted and not assessment.enough_context
            else "Got what we need. Looking into your request now."
        )
        publish(
            ticket_id,
            "info_complete",
            reason,
            summary=assessment.context_summary,
        )
        return {
            "conversation_status": "enough_context",
            "context_summary": assessment.context_summary,
            "missing_fields": assessment.missing_fields,
            "pending_question": "",
        }

    return {
        "conversation_status": "need_more_info",
        "context_summary": assessment.context_summary,
        "missing_fields": assessment.missing_fields,
        "pending_question": assessment.question,
    }


def ask_followup(state: dict[str, Any]) -> dict[str, Any]:
    """Pause the graph, ask the customer one question, and record the answer."""
    ticket_id = state["ticket_id"]
    question = state.get("pending_question", "").strip()

    publish(ticket_id, "waiting_user", question, dedupe=True, question=question)

    # Execution stops here until the API resumes the run with the reply.
    answer = interrupt({"type": "followup_question", "question": question})
    answer_text = answer if isinstance(answer, str) else str(answer)

    publish(ticket_id, "collecting_info", "Thanks, got it.")

    return {
        "messages": [
            {"role": "assistant", "content": question},
            {"role": "user", "content": answer_text},
        ],
        "followup_count": state.get("followup_count", 0) + 1,
        "pending_question": "",
    }


def route_after_assessment(state: dict[str, Any]) -> str:
    """Conditional edge: loop for more info, or move on to retrieval."""
    if state.get("conversation_status") == "need_more_info":
        return "need_more_info"
    return "enough_context"
