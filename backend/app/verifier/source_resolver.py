"""
Fetches, for a given order, the record from every connected system --
not just the one the claim happens to cite. This is the mechanism that
makes "the cited source is never automatically trusted" real: every
claim gets the full set of witnesses, every time, and the deterministic
layer decides which ones are relevant.
"""
from __future__ import annotations

from .. import db


def resolve_witnesses(order_id: str) -> dict:
    with db.get_conn() as conn:
        razorpay = conn.execute(
            "SELECT * FROM razorpay_payments WHERE order_id = ?", (order_id,)).fetchone()
        shopify = conn.execute(
            "SELECT * FROM shopify_orders WHERE order_id = ?", (order_id,)).fetchone()
        shiprocket = conn.execute(
            "SELECT * FROM shiprocket_shipments WHERE order_id = ?", (order_id,)).fetchone()
        ledger = conn.execute(
            "SELECT * FROM tally_ledger WHERE order_id = ? ORDER BY entry_date", (order_id,)).fetchall()

    return {
        "razorpay": db.row_to_dict(razorpay) if razorpay else None,
        "shopify": db.row_to_dict(shopify) if shopify else None,
        "shiprocket": db.row_to_dict(shiprocket) if shiprocket else None,
        "tally": [db.row_to_dict(r) for r in ledger],
    }


def citation_exists(cited_source: str, cited_record: str, witnesses: dict) -> bool:
    """Does the record the AI cited actually exist in that system, at all?
    A dangling citation is caught here, before any semantic check runs."""
    if cited_source == "razorpay":
        rec = witnesses["razorpay"]
        return bool(rec and rec["payment_id"] == cited_record)
    if cited_source == "shopify":
        rec = witnesses["shopify"]
        return bool(rec and rec["order_id"] == cited_record)
    if cited_source == "shiprocket":
        rec = witnesses["shiprocket"]
        return bool(rec and rec["shipment_id"] == cited_record)
    return False


def resolve_by_order_id(order_id: str) -> dict | None:
    """Look up whichever order a citation actually points to, when that
    citation belongs to a DIFFERENT order than the dispute under review
    (the customer_order_mismatch case)."""
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM shopify_orders WHERE order_id = ?", (order_id,)).fetchone()
    return db.row_to_dict(row) if row else None
