"""
Chaos injection. Every call here does a real SQLite write, then a real
re-run of the verification pipeline. There is no scripted "before/after"
-- the row that changes on screen changed because this code changed the
database underneath it.

Idempotent by construction: calling the same injection twice on the same
order produces the same end state, not a compounding one (see the fixed
entry_id used for payment_status, and the fixed target values used for
delivery_window / amount_mismatch rather than relative deltas).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import uuid

from . import db
from . import evidence_generator
from .verifier import pipeline

INJECTION_TYPES = {"delivery_window", "amount_mismatch", "payment_status"}

# chaos injection type -> the claim_type the regenerated evidence packet
# should assert, so the injected contradiction actually surfaces in a
# claim the pipeline will check.
INJECTION_CLAIM_TYPE = {
    "delivery_window": "delivery_window",
    "amount_mismatch": "amount",
    "payment_status": "payment_status",
}


def _dispute_for_order(order_id: str) -> dict | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM disputes WHERE order_id = ?", (order_id,)).fetchone()
    return db.row_to_dict(row) if row else None


def _regenerate_claim(dispute: dict, claim_type: str) -> None:
    """Replace this dispute's claim with a freshly generated one of the
    given type, so the injected contradiction actually surfaces in a
    claim that will be checked against it."""
    dispute = dict(dispute, claim_type=claim_type)
    packet = evidence_generator.generate_packet(dispute)
    now_claims = packet["claims"]
    with db.get_conn() as conn:
        conn.execute("DELETE FROM verdicts WHERE dispute_id = ?", (dispute["dispute_id"],))
        conn.execute("DELETE FROM claims WHERE dispute_id = ?", (dispute["dispute_id"],))
        for c in now_claims:
            conn.execute(
                "INSERT INTO claims (claim_id, dispute_id, claim_type, asserted_value, cited_source, "
                "cited_record, confidence) VALUES (?,?,?,?,?,?,?)",
                (c["claim_id"], dispute["dispute_id"], c["claim_type"], c["asserted_value"],
                 c["cited_source"], c["cited_record"], c["confidence"]))
        conn.execute("UPDATE disputes SET narrative = ? WHERE dispute_id = ?",
                      (packet["narrative"], dispute["dispute_id"]))


def inject(order_id: str, contradiction_type: str) -> dict:
    if contradiction_type not in INJECTION_TYPES:
        raise ValueError(f"Unknown contradiction_type '{contradiction_type}'. "
                          f"Must be one of {sorted(INJECTION_TYPES)}.")

    dispute = _dispute_for_order(order_id)
    if dispute is None:
        raise ValueError(f"No dispute found for order_id '{order_id}'.")

    steps = ["DATABASE_MUTATION"]

    if contradiction_type == "delivery_window":
        with db.get_conn() as conn:
            shopify = db.row_to_dict(conn.execute(
                "SELECT * FROM shopify_orders WHERE order_id = ?", (order_id,)).fetchone())
            promised = date.fromisoformat(shopify["promised_delivery_date"])
            late = (promised + timedelta(days=4)).isoformat()
            conn.execute("UPDATE shiprocket_shipments SET delivered_date = ?, status = 'delivered' "
                         "WHERE order_id = ?", (late, order_id))

    elif contradiction_type == "amount_mismatch":
        with db.get_conn() as conn:
            razorpay = db.row_to_dict(conn.execute(
                "SELECT * FROM razorpay_payments WHERE order_id = ?", (order_id,)).fetchone())
            corrupted = round(razorpay["amount"] * 0.8, 2)
            conn.execute("UPDATE tally_ledger SET amount = ? WHERE order_id = ? AND entry_type = 'sale'",
                          (corrupted, order_id))

    elif contradiction_type == "payment_status":
        with db.get_conn() as conn:
            razorpay = db.row_to_dict(conn.execute(
                "SELECT * FROM razorpay_payments WHERE order_id = ?", (order_id,)).fetchone())
            conn.execute(
                "INSERT INTO tally_ledger (entry_id, order_id, entry_type, amount, entry_date) "
                "VALUES (?,?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET amount = excluded.amount",
                (f"CHAOS-REFUND-{order_id}", order_id, "refund", razorpay["amount"], date.today().isoformat()))
            # razorpay.status deliberately left stale -- that IS the injected contradiction

    steps.append("EVIDENCE_REGENERATED")
    _regenerate_claim(dispute, INJECTION_CLAIM_TYPE[contradiction_type])

    steps.append("CLAIMS_VERIFIED")
    result = pipeline.verify_dispute(dispute["dispute_id"], actor="chaos_lab")
    steps.append("CONTRADICTION_FOUND" if result["status"] == "BLOCKED" else "VERDICT_UPDATED")
    steps.append("VERDICT_UPDATED")

    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (audit_id, dispute_id, claim_id, action, verdict, reason, "
            "source_record_ids, verification_method, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"AUD-CHAOS-{uuid.uuid4().hex[:10]}",
             dispute["dispute_id"], None, "INJECT", result["status"],
             f"Chaos Lab injected a '{contradiction_type}' contradiction into order {order_id}.",
             "[]", "chaos", datetime.now(timezone.utc).isoformat()))

    return {"order_id": order_id, "dispute_id": dispute["dispute_id"], "contradiction_type": contradiction_type,
            "steps": steps, "new_status": result["status"]}
