---
doc_id: kb-payments-billing-v1
policy_id: PAY-BILLING
category: payments
scope: global
version: "1.0"
effective_date: 2026-01-01
---

# Payments & Billing Policy

**Policy ID:** `PAY-BILLING`  
**Brand:** Nimbus Home

## Accepted Payment Methods

- Visa, Mastercard, American Express, Discover
- PayPal
- Apple Pay / Google Pay (where supported)
- Nimbus Home gift cards (cannot be purchased with another gift card)

We do **not** accept wire transfer, cryptocurrency, or cash on delivery.

## Authorization & Charges

- Card is **authorized** at checkout; **captured** when the order ships
- Split shipments may result in **multiple captures** for partial ship orders
- Pre-orders: authorized at order; captured on ship date

## Failed Payments

If payment fails at checkout, customer should:

1. Verify card details and billing ZIP match bank records
2. Try alternate payment method
3. Contact their bank if declines persist

If payment fails on a `pending` order retry, hold order **24 hours** then auto-cancel with email notice.

## Duplicate Charges

A duplicate charge may appear when:

- Bank shows pending + posted as separate line items (usually resolves in 3–5 days)
- Split shipment caused multiple captures

**Investigation required:** pull payment ID from OMS. If true duplicate capture (same amount, same timestamp, same auth), escalate to billing team for refund within **3 business days**.

## Invoices & Receipts

- Email receipt sent automatically on order confirmation
- PDF invoice available in **Account → Order History → Download Invoice**
- Business customers may request invoice with tax ID via support (allow **2 business days**)

## Gift Cards

- Gift cards never expire
- Non-refundable except where required by law
- Lost gift card codes: cannot be reissued without proof of purchase (order number + purchaser email)

## Tax

Sales tax calculated at checkout based on ship-to address. Nimbus Home does not provide tax advice.

## Billing Disputes

If customer disputes a charge:

1. Do **not** admit fault or promise refund before review
2. Pull order, shipment, and refund history
3. If error confirmed, process refund per `REFUND-14DAY` timelines
4. If customer mentions **chargeback**, immediately route to `ESCALATE-CHARGEBACK` — do not continue refund negotiation in ticket
