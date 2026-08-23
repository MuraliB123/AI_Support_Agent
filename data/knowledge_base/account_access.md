---
doc_id: kb-account-access-v1
policy_id: ACCOUNT-ACCESS
category: account
scope: global
version: "1.0"
effective_date: 2026-01-01
---

# Account Access Policy

**Policy ID:** `ACCOUNT-ACCESS`  
**Brand:** Nimbus Home

## Account Creation

Customers may create an account at checkout or at `account.nimbushome.example`. Guest checkout is supported; order lookup requires **order number + email** used at purchase.

## Password Reset

**Self-service (preferred):**

1. Go to **Sign In → Forgot Password**
2. Enter account email
3. Reset link expires in **24 hours**
4. Customer sets new password (min 8 characters, 1 number)

**Support-assisted reset** — only when customer cannot access email:

- Verify identity with **2 of 3**: full name on account, billing ZIP, last 4 of card, or recent order number
- Send reset link to **original account email only** — never send to a new email without escalation
- If email is permanently inaccessible, escalate to `ESCALATE-ACCOUNT` (identity verification team)

## Email Change

Email changes require:

1. Login to current account, OR identity verification (same as above)
2. Confirmation link sent to **both** old and new email
3. Change takes effect when **new email** is confirmed

Support agents **cannot** change email manually in OMS without escalation approval.

## Locked / Suspended Accounts

Accounts may be locked after:

- 5 failed login attempts (auto-unlock after 30 minutes)
- Suspected fraud (manual review — do not disclose reason)

For fraud locks, route to `ESCALATE-FRAUD`. Do not unlock in ticket.

## Order History Access

- Logged-in users: all orders on account
- Guest orders: lookup with order number + email at **Track Order**
- Agents may view order details in OMS after verifying customer identity (order number + email + billing ZIP minimum)

## Account Deletion (GDPR / Privacy)

Customers may request account deletion:

1. Verify identity
2. Submit deletion request (processed within **30 days**)
3. Order records retained **7 years** for tax/legal compliance (anonymized where required)
4. Marketing opt-out is immediate; deletion is separate from unsubscribe

## Two-Factor Authentication (2FA)

Optional SMS or authenticator app 2FA available in account settings. Support cannot disable 2FA without identity verification + 24h cooling period.
