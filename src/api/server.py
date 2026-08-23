"""FastAPI app serving the customer chat UI and the ticket endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api.runner import get_runner
from src.queue import get_status_bus
from src.utils.config import get_app_config, project_path

FRONTEND_DIR = project_path("frontend")

app = FastAPI(title="Nimbus Home Support Agent", version="0.3.0")


class CreateTicketRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    customer_id: str = Field(default="cust-demo", max_length=64)
    priority: str = Field(default="normal", max_length=32)


class ReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


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
    }


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict[str, Any]:
    run = get_runner().get_run(ticket_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown ticket")

    state = run.get("state") or {}
    return {
        "ticket_id": ticket_id,
        "phase": run.get("phase", "running"),
        "subject": run.get("subject", ""),
        "question": run.get("question", ""),
        "context_summary": state.get("context_summary", ""),
        "missing_fields": state.get("missing_fields", []),
        "followup_count": state.get("followup_count", 0),
        "query_expansion": state.get("query_expansion") or {},
        "retrieved_chunks": state.get("retrieved_chunks") or [],
        "dense_hit_count": state.get("dense_hit_count", 0),
        "sparse_hit_count": state.get("sparse_hit_count", 0),
    }


@app.get("/")
def customer_ui() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "customer" / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
