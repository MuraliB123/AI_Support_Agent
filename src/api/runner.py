"""Run the support graph off the request thread and track per-ticket run state."""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.types import Command

from src.graph.state import new_state
from src.graph.support_graph import get_compiled_graph
from src.queue import publish

RunPhase = str  # "running" | "waiting_user" | "complete" | "error"


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
            self._set(ticket_id, phase="error", error=detail)
            publish(ticket_id, "error", message, error=detail)
            return

        interrupts = result.get("__interrupt__") or []
        if interrupts:
            question = ""
            value = getattr(interrupts[0], "value", None)
            if isinstance(value, dict):
                question = value.get("question", "")
            self._set(
                ticket_id,
                phase="waiting_user",
                question=question,
                state=result,
            )
            return

        self._set(ticket_id, phase="complete", question="", state=result)
        publish(
            ticket_id,
            "complete",
            "Retrieval complete. Your ticket is ready for the next stage.",
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
        )
        self._pool.submit(self._execute, ticket_id, state)

    def resume(self, ticket_id: str, message: str) -> None:
        self._set(ticket_id, phase="running", question="")
        self._pool.submit(self._execute, ticket_id, Command(resume=message))


_runner = TicketRunner()


def get_runner() -> TicketRunner:
    return _runner
