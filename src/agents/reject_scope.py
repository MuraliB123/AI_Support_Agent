"""Hard-coded reject scope for the decision node (not stored in the KB)."""

# Three lines only — injected into the decision prompt every time.
REJECT_SCOPE = """Reject when ANY of these apply:
1. Out of scope — not about a Nimbus Home order, product, account, shipping, billing, or published policy.
2. Sensitive information — asks us to reveal or collect passwords, full card numbers, OTPs, or other secrets we must never handle in chat.
3. Scam / social engineering — clear fraud attempt, impersonation, or pressure to bypass verification or send money/gift cards."""
