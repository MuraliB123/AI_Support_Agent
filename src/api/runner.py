"""Run the support graph off the request thread and track per-ticket run state."""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.types import Command

from src.logging.audit import append_audit
from src.graph.state import new_state
from src.graph.support_graph import get_compiled_graph
from src.queue import publish

# running | waiting_user | waiting_hitl | complete | error
RunPhase = str


class TicketRunner:
    """Starts and resumes graph runs; the UI polls status events meanwhile."""

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}

    # -- run bookkeeping -------------------------------------------------

    def _set(self, ticket_id: str, **fields: Any) -> None:
        with self._lock:
            self._runs.setdefault(ticket_id, {}).update(fields)

    def get_run(self, ticket_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(ticket_id)
            return dict(run) if run else None

    def exists(self, ticket_id: str) -> bool:
        with self._lock:
            return ticket_id in self._runs

    def list_runs(self, *, phase: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            out: list[dict[str, Any]] = []
            for ticket_id, run in self._runs.items():
                if phase and run.get("phase") != phase:
                    continue
                row = {"ticket_id": ticket_id, **dict(run)}
                out.append(row)
            return out

    # -- graph execution -------------------------------------------------

    def _config(self, ticket_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": ticket_id}}

    def _execute(self, ticket_id: str, payload: Any) -> None:
        try:
            result = get_compiled_graph().invoke(payload, config=self._config(ticket_id))
        except Exception as exc:  # surface failures to the UI instead of hanging
            traceback.print_exc()
            detail = str(exc)
            lowered = detail.lower()
            is_auth = (
                "401" in detail
                or "authentication" in lowered
                or "deepseek_api_key" in lowered
            )
            message = (
                "The assistant is not configured yet: check DEEPSEEK_API_KEY in .env."
                if is_auth
                else "Something went wrong while processing this ticket."
            )
            self._set(ticket_id, phase="error", error=detail, interrupt=None)
            publish(ticket_id, "error", message, error=detail)
            append_audit(ticket_id, "error", error=detail)
            return

        interrupts = result.get("__interrupt__") or []
        if interrupts:
            value = getattr(interrupts[0], "value", None)
            if not isinstance(value, dict):
                value = {}
            interrupt_type = value.get("type", "followup_question")
            if interrupt_type == "hitl_review":
                self._set(
                    ticket_id,
                    phase="waiting_hitl",
                    question="",
                    interrupt=value,
                    state=result,
                )
                append_audit(
                    ticket_id,
                    "waiting_hitl",
                    decision=value.get("decision"),
                    confidence=value.get("confidence"),
                    draft_summary=value.get("draft_summary"),
                )
            else:
                self._set(
                    ticket_id,
                    phase="waiting_user",
                    question=value.get("question", ""),
                    interrupt=value,
                    state=result,
                )
                append_audit(
                    ticket_id,
                    "waiting_user",
                    question=value.get("question", ""),
                )
            return

        self._set(
            ticket_id,
            phase="complete",
            question="",
            interrupt=None,
            state=result,
        )
        hitl_status = result.get("hitl_status", "")
        if hitl_status == "approved":
            message = "An agent approved a draft reply for your ticket."
        elif hitl_status == "rejected":
            message = "An agent closed this draft without sending a reply."
        else:
            message = "Ticket processing finished."
        publish(
            ticket_id,
            "complete",
            message,
            decision=result.get("decision"),
            action_type=result.get("action_type"),
            hitl_status=hitl_status,
        )
        append_audit(
            ticket_id,
            "complete",
            decision=result.get("decision"),
            action_type=result.get("action_type"),
            hitl_status=hitl_status,
            hitl_action=result.get("hitl_action"),
            confidence=result.get("confidence"),
            policy_citations=result.get("policy_citations"),
        )

    def start(
        self,
        *,
        ticket_id: str,
        customer_id: str,
        subject: str,
        message: str,
        priority: str = "normal",
    ) -> None:
        state = new_state(
            ticket_id=ticket_id,
            customer_id=customer_id,
            subject=subject,
            message=message,
            priority=priority,
        )
        self._set(
            ticket_id,
            phase="running",
            question="",
            subject=subject,
            customer_id=customer_id,
            interrupt=None,
        )
        append_audit(
            ticket_id,
            "ticket_started",
            subject=subject,
            customer_id=customer_id,
            priority=priority,
        )
        self._pool.submit(self._execute, ticket_id, state)

    def resume(self, ticket_id: str, message: str) -> None:
        """Resume a customer follow-up interrupt with a plain string answer."""
        self._set(ticket_id, phase="running", question="", interrupt=None)
        append_audit(ticket_id, "customer_reply")
        self._pool.submit(self._execute, ticket_id, Command(resume=message))

    def resume_hitl(self, ticket_id: str, decision: dict[str, Any]) -> None:
        """Resume a HITL interrupt with an agent decision dict."""
        self._set(ticket_id, phase="running", question="", interrupt=None)
        append_audit(
            ticket_id,
            "hitl_decision",
            action=decision.get("action"),
        )
        self._pool.submit(self._execute, ticket_id, Command(resume=decision))


_runner = TicketRunner()


def get_runner() -> TicketRunner:
    return _runner
