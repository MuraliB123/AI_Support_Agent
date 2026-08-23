"""Decision node: escalate | reject | resolution from retrieved policies."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.agents.policy_text import has_escalation_chunks, load_escalation_policy_text
from src.agents.reject_scope import REJECT_SCOPE
from src.queue import publish
from src.utils.config import get_app_config
from src.utils.models import get_chat_model

DecisionAction = Literal["escalate", "reject", "resolution"]

SYSTEM_PROMPT = """You are the triage decision agent for {brand} support.

Choose exactly one action:
- resolution — a published KB policy clearly answers the request; draft can cite it
- escalate — needs a human specialist per the escalation policy (chargeback, legal,
  fraud, VIP, safety injury, no usable policy for a non-trivial issue, etc.)
- reject — matches the REJECT SCOPE below (out of scope, sensitive secrets, scam)
  OR is a clear abuse / refuse case (refund abuse, review threats, etc.)

Rules:
- Never invent policy. Only rely on the RETRIEVED PASSAGES and the injected policies.
- Prefer reject over escalate when REJECT SCOPE matches.
- Prefer escalate over resolution when escalation triggers match or no usable policy
  exists for a non-trivial request.
- Prefer resolution only when citations can ground a customer reply.
- Map refuse / abuse / harassment cases to reject (not escalate), unless a safety
  injury or legal threat also requires escalate — then choose escalate.
- confidence is 0.0–1.0 reflecting how clear the route is.
- cited_chunk_ids must be subset of the retrieved chunk_id values (or empty).

REJECT SCOPE (always in force):
{reject_scope}

ESCALATION POLICY (use when deciding escalate):
{escalation_policy}
"""

HUMAN_PROMPT = """Ticket ID: {ticket_id}
Subject: {subject}
Priority: {priority}

Intake summary:
{context_summary}

Conversation:
{transcript}

Retrieved passages ({chunk_count}):
{passages}

Pick one action: escalate, reject, or resolution."""


class DecisionVerdict(BaseModel):
    """Structured triage decision."""

    action: DecisionAction = Field(
        description="One of escalate, reject, resolution"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How confident you are in this route (0-1)",
    )
    rationale: str = Field(
        description="Two or three sentences explaining the route"
    )
    escalation_code: str = Field(
        default="",
        description="ESCALATE-* code when action is escalate; else empty",
    )
    reject_reason: str = Field(
        default="",
        description="Short reject reason when action is reject; else empty",
    )
    cited_chunk_ids: list[str] = Field(
        default_factory=list,
        description="chunk_ids from retrieval that support the decision",
    )


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
    return "\n".join(lines) if lines else "(no messages)"


def _format_passages(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(no passages retrieved)"
    blocks: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[{i}] chunk_id={chunk.get('chunk_id')} "
            f"policy_id={chunk.get('policy_id')} "
            f"category={chunk.get('category')}\n"
            f"section: {chunk.get('section_title')}\n"
            f"{chunk.get('content', '')}".strip()
        )
    return "\n\n---\n\n".join(blocks)


def _escalation_block(chunks: list[dict[str, Any]]) -> str:
    """Inject full escalation MD when retrieval did not already surface it."""
    if has_escalation_chunks(chunks):
        return (
            "(Escalation passages are already in RETRIEVED PASSAGES above — "
            "use those; do not invent extra criteria.)"
        )
    return load_escalation_policy_text()


def decide_action(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: choose escalate / reject / resolution."""
    ticket_id = state["ticket_id"]
    chunks = list(state.get("retrieved_chunks") or [])

    publish(ticket_id, "deciding", "Choosing how to handle this ticket...")

    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
    )
    chain = prompt | get_chat_model().with_structured_output(DecisionVerdict)
    verdict: DecisionVerdict = chain.invoke(
        {
            "brand": get_app_config()["app"]["brand"],
            "reject_scope": REJECT_SCOPE,
            "escalation_policy": _escalation_block(chunks),
            "ticket_id": ticket_id,
            "subject": state.get("subject", "(no subject)"),
            "priority": state.get("priority", "normal"),
            "context_summary": state.get("context_summary", ""),
            "transcript": _render_transcript(state.get("messages", [])),
            "chunk_count": len(chunks),
            "passages": _format_passages(chunks),
        }
    )

    allowed_ids = {c.get("chunk_id") for c in chunks if c.get("chunk_id")}
    cited = [cid for cid in verdict.cited_chunk_ids if cid in allowed_ids]

    publish(
        ticket_id,
        "decision_ready",
        f"Decision: {verdict.action} (confidence {verdict.confidence:.2f})",
        action=verdict.action,
        confidence=verdict.confidence,
        rationale=verdict.rationale,
        escalation_code=verdict.escalation_code,
        reject_reason=verdict.reject_reason,
    )

    return {
        "decision": verdict.action,
        "confidence": float(verdict.confidence),
        "decision_rationale": verdict.rationale,
        "escalation_code": verdict.escalation_code,
        "reject_reason": verdict.reject_reason,
        "cited_chunk_ids": cited,
    }


def route_after_decision(state: dict[str, Any]) -> str:
    """Conditional edge: pick exactly one action node."""
    action = state.get("decision") or "escalate"
    if action in {"escalate", "reject", "resolution"}:
        return action
    return "escalate"
