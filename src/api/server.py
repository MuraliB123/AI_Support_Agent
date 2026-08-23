"""FastAPI app serving customer chat, agent HITL UI, and ticket endpoints."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api.runner import get_runner
from src.queue import get_status_bus
from src.utils.config import get_app_config, project_path

FRONTEND_DIR = project_path("frontend")

app = FastAPI(title="Nimbus Home Support Agent", version="0.6.0")

HitlActionName = Literal[
    "approve",
    "reject",
    "edit",
    "request_regeneration",
    "escalate",
]


class CreateTicketRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    customer_id: str = Field(default="cust-demo", max_length=64)
    priority: str = Field(default="normal", max_length=32)


class ReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class HitlDecisionRequest(BaseModel):
    action: HitlActionName
    edited_draft: str | None = Field(default=None, max_length=20000)


def _ticket_payload(ticket_id: str, run: dict[str, Any]) -> dict[str, Any]:
    state = run.get("state") or {}
    interrupt = run.get("interrupt") or {}
    return {
        "ticket_id": ticket_id,
        "phase": run.get("phase", "running"),
        "subject": run.get("subject", "") or state.get("subject", ""),
        "customer_id": run.get("customer_id", ""),
        "question": run.get("question", ""),
        "context_summary": state.get("context_summary", ""),
        "missing_fields": state.get("missing_fields", []),
        "followup_count": state.get("followup_count", 0),
        "query_expansion": state.get("query_expansion") or {},
        "retrieved_chunks": state.get("retrieved_chunks") or [],
        "dense_hit_count": state.get("dense_hit_count", 0),
        "sparse_hit_count": state.get("sparse_hit_count", 0),
        "decision": state.get("decision") or interrupt.get("decision"),
        "confidence": state.get("confidence", interrupt.get("confidence")),
        "decision_rationale": state.get("decision_rationale")
        or interrupt.get("decision_rationale", ""),
        "escalation_code": state.get("escalation_code")
        or interrupt.get("escalation_code", ""),
        "reject_reason": state.get("reject_reason")
        or interrupt.get("reject_reason", ""),
        "action_type": state.get("action_type") or interrupt.get("action_type"),
        "draft": state.get("draft") or interrupt.get("draft", ""),
        "draft_summary": state.get("draft_summary")
        or interrupt.get("draft_summary", ""),
        "policy_citations": state.get("policy_citations")
        or interrupt.get("policy_citations")
        or [],
        "hitl_note": state.get("hitl_note") or interrupt.get("hitl_note", ""),
        "hitl_status": state.get("hitl_status", ""),
        "hitl_action": state.get("hitl_action", ""),
        "approved_draft": state.get("approved_draft", ""),
        "citations": interrupt.get("citations") or [],
        "low_confidence": bool(interrupt.get("low_confidence")),
        "customer_message_preview": interrupt.get("customer_message_preview")
        or state.get("approved_draft", ""),
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    app_cfg = get_app_config()["app"]
    return {"status": "ok", "brand": app_cfg["brand"], "draft_only": app_cfg["draft_only"]}


@app.post("/api/tickets")
def create_ticket(payload: CreateTicketRequest) -> dict[str, str]:
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    get_runner().start(
        ticket_id=ticket_id,
        customer_id=payload.customer_id,
        subject=payload.subject,
        message=payload.message,
        priority=payload.priority,
    )
    return {"ticket_id": ticket_id}


@app.post("/api/tickets/{ticket_id}/reply")
def reply_to_ticket(ticket_id: str, payload: ReplyRequest) -> dict[str, str]:
    runner = get_runner()
    run = runner.get_run(ticket_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown ticket")
    if run.get("phase") != "waiting_user":
        raise HTTPException(status_code=409, detail="Ticket is not awaiting a reply")

    runner.resume(ticket_id, payload.message)
    return {"status": "accepted"}


@app.post("/api/tickets/{ticket_id}/hitl")
def hitl_decision(ticket_id: str, payload: HitlDecisionRequest) -> dict[str, str]:
    runner = get_runner()
    run = runner.get_run(ticket_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown ticket")
    if run.get("phase") != "waiting_hitl":
        raise HTTPException(status_code=409, detail="Ticket is not awaiting HITL review")

    if payload.action == "edit" and not (payload.edited_draft or "").strip():
        raise HTTPException(
            status_code=400, detail="edited_draft is required when action is edit"
        )

    runner.resume_hitl(
        ticket_id,
        {
            "action": payload.action,
            "edited_draft": payload.edited_draft,
        },
    )
    return {"status": "accepted", "action": payload.action}


@app.get("/api/hitl/queue")
def hitl_queue() -> dict[str, Any]:
    """Tickets currently paused for human-agent review."""
    runs = get_runner().list_runs(phase="waiting_hitl")
    tickets = []
    for run in runs:
        ticket_id = run["ticket_id"]
        tickets.append(
            {
                "ticket_id": ticket_id,
                "subject": run.get("subject", ""),
                "decision": (run.get("interrupt") or {}).get("decision")
                or (run.get("state") or {}).get("decision"),
                "confidence": (run.get("interrupt") or {}).get("confidence")
                or (run.get("state") or {}).get("confidence"),
                "low_confidence": bool(
                    (run.get("interrupt") or {}).get("low_confidence")
                ),
                "draft_summary": (run.get("interrupt") or {}).get("draft_summary")
                or (run.get("state") or {}).get("draft_summary", ""),
            }
        )
    return {"tickets": tickets, "count": len(tickets)}


@app.get("/api/tickets/{ticket_id}/events")
def get_events(ticket_id: str, after: int = 0) -> dict[str, Any]:
    runner = get_runner()
    run = runner.get_run(ticket_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown ticket")

    bus = get_status_bus()
    events = [event.to_dict() for event in bus.events_since(ticket_id, after)]
    return {
        "ticket_id": ticket_id,
        "phase": run.get("phase", "running"),
        "question": run.get("question", ""),
        "events": events,
        "last_seq": bus.last_seq(ticket_id),
        "approved_draft": (run.get("state") or {}).get("approved_draft", ""),
        "hitl_status": (run.get("state") or {}).get("hitl_status", ""),
        "decision": (run.get("state") or {}).get("decision")
        or (run.get("interrupt") or {}).get("decision"),
    }


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict[str, Any]:
    run = get_runner().get_run(ticket_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown ticket")
    return _ticket_payload(ticket_id, run)


@app.get("/")
def customer_ui() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "customer" / "index.html")


@app.get("/agent")
def agent_ui() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "agent" / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
