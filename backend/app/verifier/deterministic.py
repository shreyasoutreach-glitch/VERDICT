"""
Deterministic verification. This module handles every claim type that
resolves from dates, amounts, statuses and counts -- which is most of
them. Nothing in this file makes a network call or a model call.

Each check function returns either:
  - a verdict dict: {verdict, method, reason, source_records}
  - None, meaning "this claim type is not decidable by code" -- the
    pipeline then routes it to the LLM/demo adjudicator instead.

`source_records` always lists the *exact* fields the decision rested on,
so the audit trail and the UI can show precisely why, without re-deriving
anything.
"""
from __future__ import annotations

from . import temporal

DETERMINISTIC_CLAIM_TYPES = {
    "delivery_status", "delivery_window", "amount", "payment_status",
    "refund_status", "order_status", "customer_identity",
}


def _sr(source, record_id, field, value):
    return {"source": source, "record_id": record_id, "field": field, "value": value}


def check_delivery_window(claim: dict, witnesses: dict) -> dict:
    shopify, shiprocket = witnesses["shopify"], witnesses["shiprocket"]
    result = temporal.check_delivery_window(shopify["promised_delivery_date"], shiprocket["delivered_date"])
    records = [
        _sr("shopify", shopify["order_id"], "promised_delivery_date", shopify["promised_delivery_date"]),
        _sr("shiprocket", shiprocket["shipment_id"], "delivered_date", shiprocket["delivered_date"]),
    ]
    if result["holds"]:
        return {"verdict": "supported", "method": "deterministic_temporal_window",
                "reason": "Delivered on or before the promised delivery date.", "source_records": records}
    return {"verdict": "contradicted", "method": "deterministic_temporal_window",
            "reason": f"Actual delivery occurred {result['late_by_days']} day(s) after the promised "
                      f"delivery date. The cited Shiprocket record correctly shows the item was "
                      f"delivered; it does not show it was delivered on time.",
            "source_records": records}


def check_delivery_status(claim: dict, witnesses: dict) -> dict:
    shiprocket, shopify = witnesses["shiprocket"], witnesses["shopify"]
    delivered = shiprocket["status"] == "delivered"
    records = [_sr("shiprocket", shiprocket["shipment_id"], "status", shiprocket["status"])]

    # Even if delivery itself checks out, a return recorded before the
    # delivery event is a chronology no honest claim can rest on.
    chrono = temporal.check_return_chronology(shopify.get("return_date"), shiprocket.get("delivered_date"))
    if chrono["violated"]:
        records += [
            _sr("shopify", shopify["order_id"], "return_date", shopify["return_date"]),
            _sr("shiprocket", shiprocket["shipment_id"], "delivered_date", shiprocket["delivered_date"]),
        ]
        return {"verdict": "contradicted", "method": "deterministic_temporal_chronology",
                "reason": f"Shopify records a return {chrono['gap_days']} day(s) BEFORE Shiprocket's own "
                          f"record shows the item was delivered. That sequence is not possible; one of "
                          f"these systems is recording an event it did not actually observe correctly.",
                "source_records": records}

    if delivered == (claim["asserted_value"] == "delivered"):
        return {"verdict": "supported", "method": "deterministic_exact_match",
                "reason": "Shiprocket's delivery status matches the claim.", "source_records": records}
    return {"verdict": "contradicted", "method": "deterministic_exact_match",
            "reason": "Shiprocket's delivery status does not match the claim.", "source_records": records}


def check_amount(claim: dict, witnesses: dict) -> dict:
    razorpay, ledger = witnesses["razorpay"], witnesses["tally"]
    sale_entries = [e for e in ledger if e["entry_type"] == "sale"]
    ledger_total = sum(e["amount"] for e in sale_entries)
    records = [_sr("razorpay", razorpay["payment_id"], "amount", razorpay["amount"])]
    records += [_sr("tally", e["entry_id"], "amount", e["amount"]) for e in sale_entries]

    if abs(razorpay["amount"] - ledger_total) < 0.01:
        return {"verdict": "supported", "method": "deterministic_exact_amount",
                "reason": "Razorpay's captured amount matches the ledger's recorded sale total.",
                "source_records": records}
    return {"verdict": "contradicted", "method": "deterministic_exact_amount",
            "reason": f"Razorpay shows \u20b9{razorpay['amount']:.2f} captured, but Tally's ledger records "
                      f"\u20b9{ledger_total:.2f} for this order -- the gateway and the books disagree.",
            "source_records": records}


def check_payment_status(claim: dict, witnesses: dict) -> dict:
    razorpay, ledger = witnesses["razorpay"], witnesses["tally"]
    refund_entries = [e for e in ledger if e["entry_type"] == "refund"]
    records = [_sr("razorpay", razorpay["payment_id"], "status", razorpay["status"])]
    records += [_sr("tally", e["entry_id"], "entry_type/amount", f"refund/{e['amount']}") for e in refund_entries]

    if refund_entries and razorpay["status"] != "refunded":
        return {"verdict": "contradicted", "method": "deterministic_cross_system_status",
                "reason": f"Tally's ledger already contains {len(refund_entries)} refund entry(ies) for "
                          f"this order, but Razorpay's own payment record still shows status "
                          f"'{razorpay['status']}'. The gateway status is stale relative to the books.",
                "source_records": records}
    if not refund_entries and razorpay["status"] == "captured":
        return {"verdict": "supported", "method": "deterministic_cross_system_status",
                "reason": "Payment is captured and the ledger has no refund entries -- consistent.",
                "source_records": records}
    if refund_entries and razorpay["status"] == "refunded":
        return {"verdict": "supported", "method": "deterministic_cross_system_status",
                "reason": "Refunded status is consistent with a matching ledger refund entry.",
                "source_records": records}
    return {"verdict": "supported", "method": "deterministic_cross_system_status",
            "reason": "Payment status is internally consistent with the ledger.", "source_records": records}


def check_refund_status(claim: dict, witnesses: dict) -> dict:
    razorpay, ledger = witnesses["razorpay"], witnesses["tally"]
    refund_entries = [e for e in ledger if e["entry_type"] == "refund"]
    records = [_sr("razorpay", razorpay["payment_id"], "status", razorpay["status"])]
    records += [_sr("tally", e["entry_id"], "amount", e["amount"]) for e in refund_entries]

    if claim["asserted_value"] == "refund_issued":
        if len(refund_entries) == 0:
            return {"verdict": "contradicted", "method": "deterministic_ledger_presence",
                    "reason": "Razorpay shows this payment as refunded, but Tally's ledger has NO "
                              "matching refund entry -- the money movement was never booked.",
                    "source_records": records}
        if len(refund_entries) > 1:
            total = sum(e["amount"] for e in refund_entries)
            return {"verdict": "contradicted", "method": "deterministic_duplicate_consequence",
                    "reason": f"Tally's ledger contains {len(refund_entries)} separate refund entries "
                              f"for this single order, totalling \u20b9{total:.2f} -- a duplicate "
                              f"financial consequence, not one refund.",
                    "source_records": records}
        entry_amount = refund_entries[0]["amount"]
        if abs(entry_amount - razorpay["amount"]) >= 0.01:
            return {"verdict": "contradicted", "method": "deterministic_exact_amount",
                    "reason": f"The ledger refund entry is \u20b9{entry_amount:.2f}, which does not match "
                              f"the original captured amount of \u20b9{razorpay['amount']:.2f}.",
                    "source_records": records}
        return {"verdict": "supported", "method": "deterministic_ledger_presence",
                "reason": "Exactly one ledger refund entry exists and its amount matches the original "
                          "payment.", "source_records": records}

    # asserted "no_refund_pending"
    if refund_entries:
        total = sum(e["amount"] for e in refund_entries)
        return {"verdict": "contradicted", "method": "deterministic_ledger_presence",
                "reason": f"The claim asserts no refund is pending, but Tally's ledger already shows "
                          f"\u20b9{total:.2f} refunded on this order.", "source_records": records}
    return {"verdict": "supported", "method": "deterministic_ledger_presence",
            "reason": "No refund entries exist in the ledger, consistent with the claim.",
            "source_records": records}


def check_order_status(claim: dict, witnesses: dict) -> dict:
    shopify = witnesses["shopify"]
    records = [_sr("shopify", shopify["order_id"], "order_status", shopify["order_status"])]
    if shopify["order_status"] == claim["asserted_value"]:
        return {"verdict": "supported", "method": "deterministic_exact_match",
                "reason": "Order status matches the claim.", "source_records": records}
    return {"verdict": "contradicted", "method": "deterministic_exact_match",
            "reason": "Order status does not match the claim.", "source_records": records}


def check_customer_identity(claim: dict, witnesses: dict, cited_order_record: dict | None) -> dict:
    dispute_customer = claim["_dispute_customer_id"]
    if cited_order_record is None:
        return {"verdict": "contradicted", "method": "deterministic_entity_resolution",
                "reason": "The cited record does not exist in Shopify at all.", "source_records": []}
    records = [_sr("shopify", cited_order_record["order_id"], "customer_id", cited_order_record["customer_id"])]
    if cited_order_record["customer_id"] == dispute_customer:
        return {"verdict": "supported", "method": "deterministic_entity_resolution",
                "reason": "The cited record's customer matches the disputing customer.",
                "source_records": records}
    return {"verdict": "contradicted", "method": "deterministic_entity_resolution",
            "reason": f"The cited record (order {cited_order_record['order_id']}) belongs to customer "
                      f"{cited_order_record['customer_id']}, not the disputing customer "
                      f"{dispute_customer}. Wrong record, not a matching one.",
            "source_records": records}


CHECKERS = {
    "delivery_status": check_delivery_status,
    "delivery_window": check_delivery_window,
    "amount": check_amount,
    "payment_status": check_payment_status,
    "refund_status": check_refund_status,
    "order_status": check_order_status,
    # customer_identity handled specially in pipeline.py (needs the resolved cited order)
}
