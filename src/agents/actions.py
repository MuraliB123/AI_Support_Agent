"""Action nodes: draft escalate / reject / resolution payloads (draft-only)."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.agents.policy_text import load_escalation_policy_text
from src.agents.reject_scope import REJECT_SCOPE
from src.queue import publish
from src.utils.config import get_app_config
from src.utils.models import get_chat_model

ActionType = Literal["escalate", "reject", "resolution"]


class ActionDraft(BaseModel):
    """Customer-facing or internal draft produced by an action node."""

    draft: str = Field(description="Full draft text for HITL review")
    summary: str = Field(
        default="",
        description="One-line summary of what this draft does",
    )
    policy_citations: list[str] = Field(
        default_factory=list,
        description="policy_id values cited in the draft",
    )


def _brand() -> str:
    return get_app_config()["app"]["brand"]


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


def _selected_chunks(state: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = list(state.get("retrieved_chunks") or [])
    cited = set(state.get("cited_chunk_ids") or [])
    if not cited:
        return chunks
    selected = [c for c in chunks if c.get("chunk_id") in cited]
    return selected or chunks


def _invoke_draft(system: str, human: str, variables: dict[str, Any]) -> ActionDraft:
    prompt = ChatPromptTemplate.from_messages(
        [("system", system), ("human", human)]
    )
    chain = prompt | get_chat_model().with_structured_output(ActionDraft)
    return chain.invoke(variables)


def action_escalate(state: dict[str, Any]) -> dict[str, Any]:
    """Draft an internal escalation / handoff note."""
    ticket_id = state["ticket_id"]
    publish(ticket_id, "drafting_escalate", "Drafting escalation handoff note...")

    system = """You draft INTERNAL escalation notes for {brand} support (not emailed yet).

Use the escalation policy and retrieved passages only. Do not invent facts.
Include: ticket id, escalation code (if given), order details from the transcript,
policies already consulted, customer sentiment, and recommended next step.
Tone: concise, factual, for a human specialist.
This is draft-only — a human must approve before anything is sent."""

    human = """Ticket ID: {ticket_id}
Escalation code hint: {escalation_code}
Decision rationale: {rationale}
Confidence: {confidence}

Intake summary:
{context_summary}

Conversation:
{transcript}

Escalation policy:
{escalation_policy}

Retrieved passages:
{passages}

Write the internal escalation note."""

    draft = _invoke_draft(
        system,
        human,
        {
            "brand": _brand(),
            "ticket_id": ticket_id,
            "escalation_code": state.get("escalation_code") or "(choose best ESCALATE-* code)",
            "rationale": state.get("decision_rationale", ""),
            "confidence": state.get("confidence", 0.0),
            "context_summary": state.get("context_summary", ""),
            "transcript": _render_transcript(state.get("messages", [])),
            "escalation_policy": load_escalation_policy_text(),
            "passages": _format_passages(_selected_chunks(state)),
        },
    )

    return _finish(state, "escalate", draft)


def action_reject(state: dict[str, Any]) -> dict[str, Any]:
    """Draft a polite reject / refuse reply for HITL."""
    ticket_id = state["ticket_id"]
    publish(ticket_id, "drafting_reject", "Drafting a polite rejection reply...")

    system = """You draft CUSTOMER-FACING rejection replies for {brand} (draft only).

REJECT SCOPE (must honor):
{reject_scope}

If retrieved passages include REFUSE-SCRIPTS or related refusal text, adapt that
script. Otherwise write a short, calm refusal that:
- does not invent policy exceptions
- does not collect or reveal secrets
- does not argue with a scammer
- stays respectful

Never promise refunds or outcomes outside policy. Human approval required."""

    human = """Ticket ID: {ticket_id}
Reject reason hint: {reject_reason}
Decision rationale: {rationale}

Intake summary:
{context_summary}

Conversation:
{transcript}

Retrieved passages (may include refuse scripts):
{passages}

Write the customer-facing rejection draft."""

    draft = _invoke_draft(
        system,
        human,
        {
            "brand": _brand(),
            "reject_scope": REJECT_SCOPE,
            "ticket_id": ticket_id,
            "reject_reason": state.get("reject_reason") or "(see rationale)",
            "rationale": state.get("decision_rationale", ""),
            "context_summary": state.get("context_summary", ""),
            "transcript": _render_transcript(state.get("messages", [])),
            "passages": _format_passages(_selected_chunks(state)),
        },
    )

    return _finish(state, "reject", draft)


def action_resolution(state: dict[str, Any]) -> dict[str, Any]:
    """Draft a grounded customer resolution citing retrieved policy only."""
    ticket_id = state["ticket_id"]
    chunks = _selected_chunks(state)
    publish(ticket_id, "drafting_resolution", "Drafting a policy-grounded reply...")

    if not chunks:
        # Never invent — fall back to an escalate-style note for HITL.
        publish(
            ticket_id,
            "drafting_resolution",
            "No policy passages available; drafting escalate-style note instead.",
        )
        fallback = ActionDraft(
            draft=(
                f"INTERNAL NOTE: No usable KB passages were retrieved for ticket "
                f"{ticket_id}. Do not send a policy answer. Please escalate to a "
                f"human specialist and consult escalation criteria."
            ),
            summary="Missing policy — escalate instead of resolving",
            policy_citations=[],
        )
        return _finish(state, "resolution", fallback, forced_missing_policy=True)

    system = """You draft CUSTOMER-FACING resolution replies for {brand} (draft only).

Rules:
- Quote / paraphrase ONLY from the retrieved passages.
- Cite policy_id values explicitly in the draft (e.g. REFUND-14DAY).
- If passages are insufficient, say a specialist must review — do NOT invent rules.
- Be clear, helpful, and concise. No promises beyond the cited policy.
- Human approval is required before send."""

    human = """Ticket ID: {ticket_id}
Decision rationale: {rationale}
Confidence: {confidence}

Intake summary:
{context_summary}

Conversation:
{transcript}

Retrieved passages (ONLY source of policy):
{passages}

Write the customer-facing resolution draft with policy citations."""

    draft = _invoke_draft(
        system,
        human,
        {
            "brand": _brand(),
            "ticket_id": ticket_id,
            "rationale": state.get("decision_rationale", ""),
            "confidence": state.get("confidence", 0.0),
            "context_summary": state.get("context_summary", ""),
            "transcript": _render_transcript(state.get("messages", [])),
            "passages": _format_passages(chunks),
        },
    )

    return _finish(state, "resolution", draft)


def _finish(
    state: dict[str, Any],
    action: ActionType,
    draft: ActionDraft,
    *,
    forced_missing_policy: bool = False,
) -> dict[str, Any]:
    ticket_id = state["ticket_id"]
    low = float(state.get("confidence") or 0.0) < 0.45
    note = ""
    if low:
        note = (
            "LOW CONFIDENCE: the triage model was unsure about this route. "
            "Please review carefully before approving."
        )
    if forced_missing_policy:
        note = (
            (note + " ") if note else ""
        ) + "MISSING POLICY: resolution was requested but no KB passages were available."

    publish(
        ticket_id,
        "action_done",
        f"Draft ready ({action}).",
        action=action,
        summary=draft.summary,
        citations=draft.policy_citations,
        low_confidence=low,
    )

    return {
        "action_type": action,
        "draft": draft.draft,
        "draft_summary": draft.summary,
        "policy_citations": draft.policy_citations,
        "hitl_note": note.strip(),
    }
