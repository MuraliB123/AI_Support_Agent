"""HITL review node: pause for human agent approve / edit / reject / regenerate / escalate."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.types import interrupt

from src.queue import publish
from src.utils.config import get_routing_rules

HitlStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "escalated",
    "regenerate",
]

HitlAction = Literal[
    "approve",
    "reject",
    "edit",
    "request_regeneration",
    "escalate",
]

# Shown to the customer when an escalate draft is approved — never the internal note.
CUSTOMER_ESCALATION_MESSAGE = (
    "Your request has been escalated. A support engineer will call you within 24 hours."
)


def _low_confidence_threshold() -> float:
    hitl = get_routing_rules().get("hitl") or {}
    return float(hitl.get("low_confidence_threshold", 0.45))


def _is_escalate_route(state: dict[str, Any]) -> bool:
    return (state.get("decision") or state.get("action_type") or "") == "escalate"


def _customer_facing_draft(state: dict[str, Any], draft: str) -> str:
    """Internal escalate notes stay in ``draft``; customers get a fixed message."""
    if _is_escalate_route(state):
        return CUSTOMER_ESCALATION_MESSAGE
    return draft


def _build_interrupt_payload(state: dict[str, Any]) -> dict[str, Any]:
    confidence = float(state.get("confidence") or 0.0)
    hitl_note = (state.get("hitl_note") or "").strip()
    if confidence < _low_confidence_threshold() and "LOW CONFIDENCE" not in hitl_note:
        hitl_note = (
            (hitl_note + " ").strip()
            + "LOW CONFIDENCE: triage was unsure — review carefully before approving."
        ).strip()

    chunks = state.get("retrieved_chunks") or []
    citations = []
    for chunk in chunks[:10]:
        citations.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "policy_id": chunk.get("policy_id"),
                "section_title": chunk.get("section_title"),
                "score": chunk.get("score"),
            }
        )

    return {
        "type": "hitl_review",
        "ticket_id": state.get("ticket_id"),
        "subject": state.get("subject", ""),
        "context_summary": state.get("context_summary", ""),
        "decision": state.get("decision"),
        "action_type": state.get("action_type"),
        "confidence": confidence,
        "decision_rationale": state.get("decision_rationale", ""),
        "escalation_code": state.get("escalation_code", ""),
        "reject_reason": state.get("reject_reason", ""),
        "draft": state.get("draft", ""),
        "draft_summary": state.get("draft_summary", ""),
        "policy_citations": list(state.get("policy_citations") or []),
        "hitl_note": hitl_note,
        "citations": citations,
        "low_confidence": confidence < _low_confidence_threshold(),
        "customer_message_preview": _customer_facing_draft(
            state, state.get("draft", "")
        ),
    }


def hitl_review(state: dict[str, Any]) -> dict[str, Any]:
    """
    Pause for the human-agent UI.

    Resume payload (dict):
      action: approve | reject | edit | request_regeneration | escalate
      edited_draft: optional string (required for a meaningful edit)
    """
    ticket_id = state["ticket_id"]
    payload = _build_interrupt_payload(state)

    publish(
        ticket_id,
        "waiting_hitl",
        "Draft ready — waiting for a human agent to review.",
        dedupe=True,
        decision=payload.get("decision"),
        confidence=payload.get("confidence"),
        low_confidence=payload.get("low_confidence"),
    )

    raw = interrupt(payload)
    response: dict[str, Any]
    if isinstance(raw, dict):
        response = raw
    else:
        response = {"action": "approve"}

    action = str(response.get("action") or "approve").strip().lower()
    if action not in {
        "approve",
        "reject",
        "edit",
        "request_regeneration",
        "escalate",
    }:
        action = "approve"

    if action == "request_regeneration":
        publish(
            ticket_id,
            "hitl_regenerate",
            "Agent requested a new draft.",
        )
        return {
            "hitl_status": "regenerate",
            "hitl_action": "request_regeneration",
        }

    if action == "escalate":
        publish(
            ticket_id,
            "hitl_escalate",
            "Agent routed this ticket to escalation.",
        )
        return {
            "hitl_status": "regenerate",
            "hitl_action": "escalate",
            "decision": "escalate",
        }

    if action == "reject":
        publish(
            ticket_id,
            "hitl_rejected",
            "Agent rejected the draft. Nothing will be shown to the customer.",
        )
        return {
            "hitl_status": "rejected",
            "hitl_action": "reject",
            "approved_draft": "",
        }

    # approve or edit — keep internal draft; customer may get a static escalate message
    draft = state.get("draft", "")
    if action == "edit":
        edited = response.get("edited_draft")
        if isinstance(edited, str) and edited.strip():
            draft = edited.strip()
        publish(
            ticket_id,
            "hitl_edited",
            "Agent edited the draft and approved it.",
        )
    else:
        publish(
            ticket_id,
            "hitl_approved",
            "Agent approved the draft.",
        )

    customer_text = _customer_facing_draft(state, draft)
    return {
        "hitl_status": "approved",
        "hitl_action": action,
        "draft": draft,
        "approved_draft": customer_text,
    }


def route_after_hitl(state: dict[str, Any]) -> str:
    """Send regenerate requests back to an action node; otherwise finish."""
    if state.get("hitl_status") != "regenerate":
        return "done"

    decision = state.get("decision") or "resolution"
    if decision == "escalate":
        return "regenerate_escalate"
    if decision == "reject":
        return "regenerate_reject"
    return "regenerate_resolution"
