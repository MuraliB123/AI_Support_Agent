"""Append-only local audit log (JSONL) for ticket lifecycle events."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.utils.config import get_app_config, project_path

_lock = threading.Lock()


def _audit_dir() -> Path:
    cfg = get_app_config()
    rel = cfg.get("paths", {}).get("audit") or "outputs/audit"
    path = project_path(rel)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _audit_file(ticket_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in ticket_id)
    return _audit_dir() / f"{safe}.jsonl"


def append_audit(
    ticket_id: str,
    event: str,
    **payload: Any,
) -> None:
    """Append one JSON line; never raises into the request path."""
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "ticket_id": ticket_id,
        "event": event,
        **payload,
    }
    try:
        line = json.dumps(record, default=str, ensure_ascii=False)
        with _lock:
            with _audit_file(ticket_id).open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # Audit must not break ticket processing
        pass
