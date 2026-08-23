---
doc_id: kb-refuse-scripts-v1
policy_id: REFUSE-SCRIPTS
category: safety
scope: global
version: "1.0"
effective_date: 2026-01-01
---

# Refusal Scripts — Abuse & Policy Violations

**Policy ID:** `REFUSE-SCRIPTS`  
**Brand:** Nimbus Home  
**Route:** `refuse` (draft only — human approval required)

Use these scripts when the request violates policy and **no KB exception applies**. Do not negotiate beyond the script. Do not fabricate alternative policies.

## REFUSE-ABUSE — Refund / Promo Abuse

**Triggers:**

- Customer demands refund outside `REFUND-14DAY` with no qualifying exception
- Repeated courtesy credits already issued (3+ in 90 days)
- Threats to leave bad reviews in exchange for refund or promo
- False claims of never receiving item when tracking shows delivered and signed

**Script:**

> Thank you for contacting Nimbus Home. We've reviewed your order against our return policy (REFUND-14DAY). Unfortunately, this request doesn't meet the eligibility criteria for a refund or store credit at this time.
>
> If you have new information — such as a carrier investigation reference or proof of defect — please reply with those details and we can re-review your case.
>
> We appreciate your understanding.

**Agent actions:** set route to `refuse`; cite `REFUND-14DAY` or `REFUSE-SCRIPTS`; do not offer discretionary refund in same thread.

## REFUSE-LANGUAGE — Abusive or Threatening Language

**Triggers:**

- Profanity directed at agent
- Threats of violence or self-harm (also escalate per internal safety protocol)
- Discriminatory language
- Harassment (repeated messages after refusal)

**Script:**

> We're here to help with your Nimbus Home order. To continue assisting you, we'll need the conversation to remain respectful.
>
> Please restate your question about your order, and we'll do our best to help within our published policies.
>
> If you need further assistance after this, you may reply to this ticket.

**Agent actions:** set route to `refuse`; if threats of violence → escalate to supervisor immediately (do not continue automated draft). Second offense in same thread → close ticket with note; escalate.

## REFUSE-IMPERSONATION — Cannot Verify Identity

**Triggers:**

- Caller cannot verify order number + email + minimum identity fields
- Request to change account email or payment without verification
- Third party claims to act for customer without authorization

**Script:**

> To protect your account security, we need to verify your identity before making changes. Please provide your order number, the email used at checkout, and the billing ZIP code.
>
> If you no longer have access to your email, our account verification team can help through a separate secure process.

**Agent actions:** route `refuse` or `ask_clarification` if partial info; route `escalate` to `ESCALATE-ACCOUNT` if legitimate lockout.

## REFUSE-OUT-OF-SCOPE — Not a Support Matter

**Triggers:**

- Legal advice requests
- Requests to break policy because "other companies do it"
- Wholesale / partnership pitches in support queue

**Script:**

> Thank you for reaching out. This request falls outside what our support team can approve. For partnership inquiries, please contact partners@nimbushome.example.
>
> For order-related questions, we're happy to help within our published policies.

## Important

- **Never** invent policy exceptions to de-escalate
- **Never** promise outcomes that require supervisor approval in a refuse script
- All refuse drafts require **HITL approval** before any customer-facing send
