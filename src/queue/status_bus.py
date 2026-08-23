"""In-memory per-ticket status queue.

Each ticket gets an append-only event log. Producers (graph nodes) publish
stage updates; consumers (the customer UI) poll with the last sequence number
they have seen, so a slow reader never misses events.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

MAX_EVENTS_PER_TICKET = 500


@dataclass(frozen=True)
class StatusEvent:
    seq: int
    ticket_id: str
    stage: str
    message: str
    created_at: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StatusBus:
    """Thread-safe fan-out of ticket status events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, list[StatusEvent]] = {}
        self._next_seq: dict[str, int] = {}

    def publish(
        self,
        ticket_id: str,
        stage: str,
        message: str,
        *,
        dedupe: bool = False,
        **data: Any,
    ) -> StatusEvent:
        """Append an event.

        ``dedupe`` suppresses a repeat of the previous event. LangGraph re-runs a
        node from the top when a run resumes from ``interrupt()``, so nodes that
        publish before pausing would otherwise emit the same update twice.
        """
        with self._lock:
            log = self._events.setdefault(ticket_id, [])
            if dedupe and log and log[-1].stage == stage and log[-1].message == message:
                return log[-1]

            seq = self._next_seq.get(ticket_id, 0) + 1
            self._next_seq[ticket_id] = seq
            event = StatusEvent(
                seq=seq,
                ticket_id=ticket_id,
                stage=stage,
                message=message,
                created_at=datetime.now(UTC).isoformat(),
                data=data,
            )
            log.append(event)
            if len(log) > MAX_EVENTS_PER_TICKET:
                del log[: len(log) - MAX_EVENTS_PER_TICKET]
            return event

    def events_since(self, ticket_id: str, after_seq: int = 0) -> list[StatusEvent]:
        with self._lock:
            return [e for e in self._events.get(ticket_id, []) if e.seq > after_seq]

    def last_seq(self, ticket_id: str) -> int:
        with self._lock:
            return self._next_seq.get(ticket_id, 0)

    def clear(self, ticket_id: str) -> None:
        with self._lock:
            self._events.pop(ticket_id, None)
            self._next_seq.pop(ticket_id, None)


_bus = StatusBus()


def get_status_bus() -> StatusBus:
    return _bus


def publish(
    ticket_id: str,
    stage: str,
    message: str,
    *,
    dedupe: bool = False,
    **data: Any,
) -> StatusEvent:
    """Convenience publisher used by graph nodes."""
    return _bus.publish(ticket_id, stage, message, dedupe=dedupe, **data)
