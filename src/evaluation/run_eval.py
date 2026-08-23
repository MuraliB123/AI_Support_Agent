"""Phase 8: run golden tickets through the eval graph (no HITL) and score routes."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.graph.state import new_state
from src.graph.support_graph import build_eval_graph
from src.utils.config import project_path

GOLDEN_PATH = project_path("data/evaluation/golden_tickets.json")
DEFAULT_OUT_DIR = project_path("outputs/evaluation")


def load_golden(path: Path | None = None) -> list[dict[str, Any]]:
    raw = json.loads((path or GOLDEN_PATH).read_text(encoding="utf-8"))
    tickets = raw.get("tickets") or []
    if not isinstance(tickets, list) or not tickets:
        raise ValueError(f"No tickets in {path or GOLDEN_PATH}")
    return tickets


def _interrupt_value(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None
    value = getattr(interrupts[0], "value", None)
    return value if isinstance(value, dict) else {}


def run_ticket(
    graph: Any,
    ticket: dict[str, Any],
    *,
    max_followups: int = 5,
) -> dict[str, Any]:
    """Invoke eval graph; auto-resume intake follow-ups; never wait on HITL."""
    ticket_id = str(ticket["ticket_id"])
    replies = list(ticket.get("followup_replies") or [])
    reply_idx = 0

    state = new_state(
        ticket_id=ticket_id,
        customer_id=str(ticket.get("customer_id") or f"cust-{ticket_id}"),
        subject=str(ticket.get("subject") or ""),
        message=str(ticket.get("message") or ""),
        priority=str(ticket.get("priority") or "normal"),
    )
    config = {"configurable": {"thread_id": f"eval-{ticket_id}"}}

    payload: Any = state
    followups_used = 0
    last: dict[str, Any] = {}

    for _ in range(max_followups + 3):
        last = graph.invoke(payload, config=config)
        interrupt = _interrupt_value(last)
        if not interrupt:
            break
        itype = interrupt.get("type", "followup_question")
        if itype == "hitl_review":
            # Eval graph should not reach HITL; auto-approve as safety net.
            payload = Command(resume={"action": "approve"})
            continue
        if reply_idx < len(replies):
            answer = replies[reply_idx]
            reply_idx += 1
        else:
            answer = (
                "I do not have more details beyond what I already shared. "
                "Please proceed with the information on the ticket."
            )
        followups_used += 1
        payload = Command(resume=answer)
    else:
        raise RuntimeError(f"{ticket_id}: exceeded follow-up / resume budget")

    if _interrupt_value(last):
        raise RuntimeError(f"{ticket_id}: still interrupted after resumes")

    return {
        "ticket_id": ticket_id,
        "subject": ticket.get("subject"),
        "followups_used": followups_used,
        "decision": last.get("decision"),
        "confidence": last.get("confidence"),
        "decision_rationale": last.get("decision_rationale", ""),
        "escalation_code": last.get("escalation_code", ""),
        "reject_reason": last.get("reject_reason", ""),
        "cited_chunk_ids": list(last.get("cited_chunk_ids") or []),
        "policy_citations": list(last.get("policy_citations") or []),
        "draft": last.get("draft", ""),
        "draft_summary": last.get("draft_summary", ""),
        "retrieved_chunk_count": len(last.get("retrieved_chunks") or []),
        "retrieved_policy_ids": sorted(
            {
                str(c.get("policy_id"))
                for c in (last.get("retrieved_chunks") or [])
                if c.get("policy_id")
            }
        ),
        "context_summary": last.get("context_summary", ""),
        "action_type": last.get("action_type"),
    }


def score_row(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    exp_decision = str(expected.get("decision") or "").strip().lower()
    got_decision = str(actual.get("decision") or "").strip().lower()
    route_ok = bool(exp_decision) and exp_decision == got_decision

    exp_code = str(expected.get("escalation_code") or "").strip()
    got_code = str(actual.get("escalation_code") or "").strip()
    code_ok: bool | None
    if exp_code:
        code_ok = exp_code == got_code
    else:
        code_ok = None

    want_policies = [str(p) for p in (expected.get("policy_ids_any") or []) if p]
    retrieved = set(actual.get("retrieved_policy_ids") or [])
    cited = set(actual.get("policy_citations") or [])
    policy_ok: bool | None
    if want_policies:
        policy_ok = any(p in retrieved or p in cited for p in want_policies)
    else:
        policy_ok = None

    draft_ok = bool(str(actual.get("draft") or "").strip())

    return {
        "route_match": route_ok,
        "escalation_code_match": code_ok,
        "policy_grounding_ok": policy_ok,
        "draft_nonempty": draft_ok,
        "pass": route_ok
        and draft_ok
        and (code_ok is not False)
        and (policy_ok is not False),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    route_hits = sum(1 for r in rows if r["score"]["route_match"])
    draft_hits = sum(1 for r in rows if r["score"]["draft_nonempty"])
    passes = sum(1 for r in rows if r["score"]["pass"])
    policy_scored = [
        r for r in rows if r["score"]["policy_grounding_ok"] is not None
    ]
    policy_hits = sum(
        1 for r in policy_scored if r["score"]["policy_grounding_ok"]
    )
    code_scored = [
        r for r in rows if r["score"]["escalation_code_match"] is not None
    ]
    code_hits = sum(1 for r in code_scored if r["score"]["escalation_code_match"])

    by_expected: dict[str, dict[str, int]] = {}
    for r in rows:
        key = str(r["expected"].get("decision") or "?")
        bucket = by_expected.setdefault(key, {"n": 0, "route_hits": 0})
        bucket["n"] += 1
        if r["score"]["route_match"]:
            bucket["route_hits"] += 1

    return {
        "ticket_count": len(rows),
        "pass_rate": round(passes / n, 4),
        "route_accuracy": round(route_hits / n, 4),
        "draft_nonempty_rate": round(draft_hits / n, 4),
        "policy_grounding_accuracy": (
            round(policy_hits / len(policy_scored), 4) if policy_scored else None
        ),
        "escalation_code_accuracy": (
            round(code_hits / len(code_scored), 4) if code_scored else None
        ),
        "route_accuracy_by_expected": {
            k: {
                "n": v["n"],
                "accuracy": round(v["route_hits"] / v["n"], 4) if v["n"] else 0.0,
            }
            for k, v in sorted(by_expected.items())
        },
        "passed": passes,
        "failed": len(rows) - passes,
    }


def run_suite(
    *,
    golden_path: Path | None = None,
    limit: int | None = None,
    ticket_ids: set[str] | None = None,
) -> dict[str, Any]:
    tickets = load_golden(golden_path)
    if ticket_ids:
        tickets = [t for t in tickets if t.get("ticket_id") in ticket_ids]
    if limit is not None:
        tickets = tickets[:limit]

    graph = build_eval_graph().compile(checkpointer=InMemorySaver())
    rows: list[dict[str, Any]] = []

    for ticket in tickets:
        expected = dict(ticket.get("expected") or {})
        try:
            actual = run_ticket(graph, ticket)
            error = None
        except Exception as exc:  # keep suite going
            actual = {
                "ticket_id": ticket.get("ticket_id"),
                "subject": ticket.get("subject"),
                "decision": None,
                "draft": "",
                "error": str(exc),
            }
            error = str(exc)
        score = score_row(actual, expected)
        if error:
            score["pass"] = False
            score["route_match"] = False
        rows.append(
            {
                "ticket_id": ticket.get("ticket_id"),
                "subject": ticket.get("subject"),
                "expected": expected,
                "actual": actual,
                "score": score,
                "error": error,
            }
        )
        status = "PASS" if score["pass"] else "FAIL"
        print(
            f"[{status}] {ticket.get('ticket_id')}: "
            f"expected={expected.get('decision')} got={actual.get('decision')}"
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "golden_path": str(golden_path or GOLDEN_PATH),
        "hitl": "skipped (build_eval_graph ends after action nodes)",
        "summary": summarize(rows),
        "results": rows,
    }
    return report


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"report_{stamp}.json"
    latest = out_dir / "report_latest.json"
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    json_path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    return json_path, latest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run synthetic golden tickets through the eval graph (no HITL)."
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=None,
        help="Path to golden_tickets.json",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run first N tickets")
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional ticket_id filter, e.g. EVAL-001 EVAL-007",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for JSON reports",
    )
    args = parser.parse_args()

    report = run_suite(
        golden_path=args.golden,
        limit=args.limit,
        ticket_ids=set(args.only) if args.only else None,
    )
    json_path, latest = write_report(report, args.out_dir)
    summary = report["summary"]
    print()
    print(
        f"Route accuracy: {summary['route_accuracy']:.0%} "
        f"({summary['passed']}/{summary['ticket_count']} full pass)"
    )
    print(f"Wrote {json_path}")
    print(f"Latest {latest}")


if __name__ == "__main__":
    main()
