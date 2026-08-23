"""Local JSONL audit helper."""

from __future__ import annotations

import json

from src.logging.audit import append_audit


def test_append_audit_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.logging.audit._audit_dir",
        lambda: tmp_path,
    )
    append_audit("TKT-AUD01", "ticket_started", subject="Test")
    append_audit("TKT-AUD01", "complete", hitl_status="approved")

    path = tmp_path / "TKT-AUD01.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["ticket_id"] == "TKT-AUD01"
    assert first["event"] == "ticket_started"
    assert first["subject"] == "Test"
