# Evaluation report

Phase 8 offline eval: synthetic tickets run through the **eval graph** (HITL skipped). Expected routes come from `data/evaluation/golden_tickets.json`. Machine-readable output: `outputs/evaluation/report_latest.json`.

## Method

| Piece | Detail |
| --- | --- |
| Queue | 12 synthetic tickets (`data/tickets/synthetic_queue.json` + golden file) |
| Graph | `build_eval_graph()` — same intake → retrieval → decision → action path as production |
| HITL | **Skipped** — action nodes edge to `END` (no `hitl_review` interrupt) |
| Follow-ups | Auto-resumed from `followup_replies` when intake still asks; otherwise a generic “proceed” answer |
| Models | Live DeepSeek chat + Atlas hybrid retrieval (BGE / BM25 / RRF) |
| Pass rule | Route matches **and** draft non-empty **and** (if specified) escalation code + any expected `policy_ids_any` found in citations or retrieval |

```powershell
.\.venv\Scripts\Activate.ps1
python -m src.evaluation.run_eval
# optional: --only EVAL-001 EVAL-007  |  --limit 3
```

## Headline results

Run timestamp: **2026-08-23T20:56:26Z**

| Metric | Value |
| --- | --- |
| Tickets | 12 |
| Full pass rate | **100%** (12/12) |
| Route accuracy | **100%** |
| Draft non-empty | **100%** |
| Policy grounding (when expected) | **100%** |
| Escalation code accuracy (when expected) | **100%** |

### Route accuracy by expected class

| Expected route | n | Accuracy |
| --- | --- | --- |
| `resolution` | 4 | 100% |
| `reject` | 4 | 100% |
| `escalate` | 4 | 100% |

## Expected vs actual

| Ticket | Expected | Actual | Conf | Escalation code | Policy citations (sample) | Pass |
| --- | --- | --- | --- | --- | --- | --- |
| EVAL-001 | resolution | resolution | 0.95 | — | REFUND-14DAY | yes |
| EVAL-002 | resolution | resolution | 0.97 | — | SHIP-SLA, FAQ-GENERAL | yes |
| EVAL-003 | resolution | resolution | 0.95 | — | SHIP-SLA | yes |
| EVAL-004 | reject | reject | 0.98 | — | REFUSE-SCRIPTS | yes |
| EVAL-005 | reject | reject | 0.95 | — | ACCOUNT-ACCESS, REFUSE-SCRIPTS | yes |
| EVAL-006 | reject | reject | 0.98 | — | REFUSE-SCRIPTS | yes |
| EVAL-007 | escalate | escalate | 0.98 | ESCALATE-CHARGEBACK | ESCALATE-GENERAL, PAY-BILLING | yes |
| EVAL-008 | escalate | escalate | 0.98 | ESCALATE-LEGAL | ESCALATE-GENERAL, REFUND-14DAY | yes |
| EVAL-009 | escalate | escalate | 0.98 | ESCALATE-SAFETY | ESCALATE-GENERAL | yes |
| EVAL-010 | escalate | escalate | 0.95 | ESCALATE-VIP | ESCALATE-GENERAL, REFUND-14DAY | yes |
| EVAL-011 | reject | reject | 0.90 | — | REFUND-14DAY | yes |
| EVAL-012 | resolution | resolution | 0.85 | — | WARRANTY-DAMAGE | yes |

## Case coverage

| ID | Intent | Why it is in the set |
| --- | --- | --- |
| EVAL-001 | In-window sealed return | Classic grounded **resolution** |
| EVAL-002 / 003 | Shipping SLA / tracking | FAQ-style **resolution** on `SHIP-SLA` |
| EVAL-004 | Cooking recipe | **Reject** out of scope |
| EVAL-005 | Password / card ask | **Reject** sensitive info |
| EVAL-006 | Gift-card scam | **Reject** social engineering |
| EVAL-007 | Bank chargeback | **Escalate** `ESCALATE-CHARGEBACK` |
| EVAL-008 | Lawsuit / AG | **Escalate** `ESCALATE-LEGAL` |
| EVAL-009 | Injury / spark | **Escalate** `ESCALATE-SAFETY` |
| EVAL-010 | $2,450 VIP order | **Escalate** `ESCALATE-VIP` |
| EVAL-011 | Review threat + late refund | **Reject** / refuse path |
| EVAL-012 | Damaged-on-arrival lamp | **Resolution** on warranty/damage KB |

## Observations

- Balanced 4/4/4 split across resolution / reject / escalate held at **100%** route accuracy on this run.
- Escalation codes matched the golden codes for all four escalate tickets.
- Reject cases stayed on `reject` (not escalate), including abuse/review-threat EVAL-011.
- Drafts were produced for every ticket; confidence stayed high (0.85–0.98).
- This eval does **not** score prose quality, citation faithfulness line-by-line, or HITL edit behavior — only routing / grounding / draft presence under auto intake.

## Artifacts

| Path | Role |
| --- | --- |
| `data/evaluation/golden_tickets.json` | Expected decisions + optional follow-up replies |
| `data/tickets/synthetic_queue.json` | Same queue in ticket-queue shape |
| `src/graph/support_graph.py` → `build_eval_graph` | HITL-free graph |
| `src/evaluation/run_eval.py` | Runner + scoring |
| `outputs/evaluation/report_latest.json` | Latest full results |
| `tests/test_evaluation.py` | Scoring / graph wiring unit tests |

## Limits

- Live LLM + retrieval → scores can drift across model/KB changes; re-run before claiming regressions.
- Process needs `DEEPSEEK_API_KEY` and Atlas vectors already embedded.
- Follow-up auto-answers are fixture-driven; they are not a substitute for conversation-quality eval.
- Production HITL is intentionally out of scope here (see [demo.md](demo.md) for the human gate).
