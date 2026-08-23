---
doc_id: kb-escalation-criteria-v1
policy_id: ESCALATE-GENERAL
category: escalation
scope: global
version: "1.0"
effective_date: 2026-01-01
---

# Escalation Criteria

**Policy ID:** `ESCALATE-GENERAL`  
**Brand:** Nimbus Home  
**Route:** `escalate` (human specialist required)

Escalate when the issue **cannot be resolved** with standard KB policies or requires **supervisor / legal / fraud** involvement.

## Mandatory Escalation Triggers

| Code | Trigger | Escalate to |
| --- | --- | --- |
| `ESCALATE-CHARGEBACK` | Customer mentions chargeback, bank dispute, or payment processor claim | Billing / Risk team |
| `ESCALATE-LEGAL` | Lawyer, lawsuit, regulatory agency (BBB, AG), or media threat | Legal liaison |
| `ESCALATE-FRAUD` | Suspected fraud, stolen card, account takeover | Fraud team |
| `ESCALATE-ACCOUNT` | Email inaccessible, identity dispute, merge accounts | Identity verification |
| `ESCALATE-VIP` | Order or lifetime value **> $2,000** OR customer tagged VIP in CRM | Senior support |
| `ESCALATE-SAFETY` | Product safety injury, fire, electrical hazard | Safety + Legal (urgent) |

## Conditional Escalation

Escalate when **any** apply:

- No matching KB policy and customer issue is non-trivial (not simple FAQ)
- Customer has had **3+ contacts** on same issue without resolution
- Agent discretion limit exceeded (refund authority cap **$150** per ticket)
- Policy conflict between two KB documents (flag for KB owner; escalate to senior)
- Request for exception to `REFUND-14DAY` with documented delivery failure and order value **> $500**

## Chargeback Handling

**Do not:**

- Promise refund to prevent chargeback once dispute is filed
- Admit company fault in writing without approval
- Share internal investigation details

**Do:**

- Acknowledge receipt of concern
- State that billing team will review
- Provide timeline: **2 business days** for specialist response
- Route `ESCALATE-CHARGEBACK` immediately


## Safety Incidents

If customer reports injury or property damage from product:

1. Express concern (no admission of liability)
2. Collect: product SKU, serial, date of incident, photos if available
3. **Immediately** route `ESCALATE-SAFETY`
4. Do not continue standard troubleshooting

## When NOT to Escalate

- Simple tracking lookup (use `SHIP-SLA`)
- Standard return within policy (`REFUND-14DAY`)
- Password reset with successful identity check (`ACCOUNT-ACCESS`)
- Promo code questions with clear answer (`PROMO-CODES`)

## Escalation Note Template

When escalating, internal note must include:

- Ticket ID and order number
- Escalation code (from table above)
- KB policies already cited
- Customer sentiment summary
- Recommended next action (if any)
