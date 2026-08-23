---
doc_id: kb-order-changes-v1
policy_id: ORDER-MODIFY
category: orders
scope: global
version: "1.0"
effective_date: 2026-01-01
---

# Order Changes & Cancellation Policy

**Policy ID:** `ORDER-MODIFY`  
**Brand:** Nimbus Home

## Order Status Definitions

| Status | Meaning | Can cancel? | Can edit address/items? |
| --- | --- | --- | --- |
| `pending` | Payment authorized, not yet picked | Yes | Yes |
| `processing` | Warehouse picking | Maybe (agent check) | Address only |
| `shipped` | Label created / in transit | No | No |
| `delivered` | Completed | No | Use returns (`REFUND-14DAY`) |

## Cancellation

Customers may **cancel for a full refund** when order status is `pending`.

For `processing` orders:

- Cancellation allowed if warehouse confirms item not yet packed (usually within **1 hour** of order)
- If already packed, cancellation is denied — customer may refuse delivery or use return policy after receipt

**How to cancel:** verify order number, confirm status, process cancellation in OMS. Refund timeline follows `REFUND-14DAY` payment table.

## Item Changes

Adding or removing items is only possible on `pending` orders:

- **Add item:** customer must place a new order OR agent cancels and asks customer to reorder (avoid manual payment handling)
- **Remove item:** partial cancellation + partial refund on `pending` orders only
- **Change quantity:** allowed on `pending` only

## Address Changes

- **Before ship:** update shipping address in OMS at no charge
- **After ship:** provide carrier intercept link; Nimbus Home does not guarantee success. Customer may pay redirect fee ($5–$15) if carrier allows

## Order Holds

Place order on hold (max **48 hours**) when:

- Customer requests delay for travel / gift timing
- Fraud review flagged (do not disclose fraud flag to customer)

## Duplicate Orders

If customer accidentally placed duplicate orders within **30 minutes**:

- Cancel duplicate `pending` orders with full refund
- If both shipped, accept return on duplicate under `REFUND-14DAY` with **waived restocking fee**

## Cannot Fulfill (Out of Stock)

If an item goes out of stock after order:

1. Notify customer within **24 hours**
2. Offer: wait for restock (ETA), substitute SKU (with approval), or full refund for affected line item
3. Offer **$15 store credit** for inconvenience if wait exceeds **14 days**
