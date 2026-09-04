"""
The upstream agent VERIDICT sits underneath.

DISPUTE RESPONDER plays the role of Razorpay's own AI evidence-drafting
agent: for each claim type it reads exactly ONE "home" system, cites the
real record it read, and asserts a value directly derived from that
record. It never cross-checks. That is the entire point -- the claims
it writes are always genuinely grounded in the source they cite. Whether
they are also GLOBALLY true depends on whether the world (built in
seed.py) happens to agree, which this module has no way of knowing.

This module never reads ground_truth_contradiction. It only ever sees
the same four system records a real evidence-drafting agent would.
"""
from __future__ import annotations

import uuid

CLAIM_TEMPLATES = {
    "delivery_status": 'The item was delivered to the customer, per {source} record {record}.',
    "delivery_window": 'The order was delivered within the promised delivery window, per {source} record {record}.',
    "amount": 'The customer was charged an amount consistent with the order total, per {source} record {record}.',
    "payment_status": 'Payment for this order was successfully captured, per {source} record {record}.',
    "refund_status": 'No unresolved refund obligation exists on this order, per {source} record {record}.',
    "order_status": 'The order remains active and was fulfilled as placed, per {source} record {record}.',
    "customer_identity": 'The purchasing customer on record matches the disputing party, per {source} record {record}.',
    "service_quality": 'The customer received satisfactory service on this order, per {source} record {record}.',
    "fulfillment_quality": 'The order was fulfilled as expected with no service failure, per {source} record {record}.',
    "customer_request_fulfilled": "The merchant fulfilled the customer's request in full, per {source} record {record}.",
    "delivery_refusal_intent": 'The customer intentionally refused delivery of this shipment, per {source} record {record}.',
}

# claim_type -> (cited_source system, which id field to cite)
HOME_SOURCE = {
    "delivery_status": "shiprocket",
    "delivery_window": "shiprocket",
    "amount": "razorpay",
    "payment_status": "razorpay",
    "refund_status": "razorpay",
    "order_status": "shopify",
    "customer_identity": "shopify",
    "service_quality": "shopify",
    "fulfillment_quality": "shiprocket",
    "customer_request_fulfilled": "shopify",
    "delivery_refusal_intent": "shiprocket",
}


def _record_id_for(source: str, razorpay: dict, shopify: dict, shiprocket: dict) -> str:
    return {
        "razorpay": razorpay["payment_id"],
        "shopify": shopify["order_id"],
        "shiprocket": shiprocket["shipment_id"],
    }[source]


def generate_packet_from_records(dispute: dict, razorpay: dict, shopify: dict,
                                  shiprocket: dict, ledger_rows: list[dict]) -> dict:
    """Pure function: given a dispute descriptor and the already-fetched
    rows for its order, produce the evidence packet a naive single-source
    agent would write. No database access happens in here."""
    claim_type = dispute["claim_type"]
    source = HOME_SOURCE[claim_type]

    # The one seeded identity-mismatch case: the agent cites a record
    # belonging to someone else entirely (still a real record).
    if claim_type == "customer_identity" and dispute.get("cited_order_override"):
        cited_record = dispute["cited_order_override"]
    elif dispute.get("dangling_reference") and claim_type == "refund_status":
        # A record ID that does not exist in any system -- the agent
        # hallucinated (or was handed) a citation with nothing behind it.
        cited_record = f"PAY-{dispute['order_id']}-GHOST"
    else:
        cited_record = _record_id_for(source, razorpay, shopify, shiprocket)

    asserted_value = {
        "delivery_status": "delivered" if shiprocket["status"] == "delivered" else "not_delivered",
        "delivery_window": "delivered_on_time",
        "amount": str(razorpay["amount"]),
        "payment_status": razorpay["status"],
        "refund_status": "no_refund_pending" if razorpay["status"] != "refunded" else "refund_issued",
        "order_status": shopify["order_status"],
        "customer_identity": dispute["customer_id"],
        "service_quality": "satisfactory",
        "fulfillment_quality": "as_expected",
        "customer_request_fulfilled": "fulfilled",
        "delivery_refusal_intent": "refused_by_customer",
    }[claim_type]

    claim = {
        "claim_id": f"CLM-{uuid.uuid4().hex[:8]}",
        "claim_type": claim_type,
        "asserted_value": asserted_value,
        "cited_source": source,
        "cited_record": cited_record,
        "confidence": 0.97 if claim_type == "delivery_window" else round(0.90 + (hash(cited_record) % 8) / 100, 2),
    }

    narrative = CLAIM_TEMPLATES[claim_type].format(source=source.capitalize(), record=cited_record)
    narrative += (f" Order {dispute['order_id']} for customer {dispute['customer_id']} is the subject "
                  f"of this evidence packet, generated automatically ahead of a potential dispute response.")

    return {"dispute_id": dispute["dispute_id"], "narrative": narrative, "claims": [claim]}


def generate_packet(dispute: dict) -> dict:
    """DB-backed convenience wrapper, used only outside of seeding (e.g. a
    future 'regenerate evidence' action) where records must be re-fetched.
    Not used during initial seeding -- see seed.py, which already has the
    rows in memory and calls generate_packet_from_records directly to
    avoid nested database locks."""
    from . import db
    order_id = dispute["order_id"]
    with db.get_conn() as conn:
        razorpay = db.row_to_dict(conn.execute(
            "SELECT * FROM razorpay_payments WHERE order_id = ?", (order_id,)).fetchone())
        shopify = db.row_to_dict(conn.execute(
            "SELECT * FROM shopify_orders WHERE order_id = ?", (order_id,)).fetchone())
        shiprocket = db.row_to_dict(conn.execute(
            "SELECT * FROM shiprocket_shipments WHERE order_id = ?", (order_id,)).fetchone())
        ledger_rows = [db.row_to_dict(r) for r in conn.execute(
            "SELECT * FROM tally_ledger WHERE order_id = ?", (order_id,)).fetchall()]
    return generate_packet_from_records(dispute, razorpay, shopify, shiprocket, ledger_rows)
