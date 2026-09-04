"""
EVIDENCE PACKET -> CLAIM EXTRACTOR -> SOURCE RESOLVER -> DETERMINISTIC
VERIFICATION -> TEMPORAL/BUSINESS RULES -> LLM ADJUDICATOR (only if
required) -> VERDICT -> SUBMISSION GATE -> AUDIT RECORD.

This module is the only place that decides CLEARED / BLOCKED /
HUMAN_CONTEXT. Every other module produces evidence; this one turns
evidence into a gate decision and writes the paper trail.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from .. import db
from . import claim_extractor, deterministic, source_resolver
from . import llm_adjudicator, demo_adjudicator

VERDICT_TO_STATUS = {
    "supported": "CLEARED",
    "contradicted": "BLOCKED",
    "insufficient_evidence": "HUMAN_CONTEXT",
}


def _llm_mode() -> str:
    mode = os.environ.get("LLM_MODE", "").strip().lower()
    if mode in ("openai", "demo"):
        return mode
    return "openai" if os.environ.get("OPENAI_API_KEY", "").strip() else "demo"


def _adjudicate_soft_claim(claim: dict, witnesses: dict) -> dict:
    """Builds the fixed, pre-fetched record set the adjudicator is allowed
    to see and cite, then dispatches to the real or demo adjudicator."""
    records = []
    if witnesses["razorpay"]:
        records.append({"record_id": witnesses["razorpay"]["payment_id"], "source": "razorpay",
                         "data": witnesses["razorpay"]})
    if witnesses["shopify"]:
        records.append({"record_id": witnesses["shopify"]["order_id"], "source": "shopify",
                         "data": witnesses["shopify"]})
    if witnesses["shiprocket"]:
        records.append({"record_id": witnesses["shiprocket"]["shipment_id"], "source": "shiprocket",
                         "data": witnesses["shiprocket"]})
    for e in witnesses["tally"]:
        records.append({"record_id": e["entry_id"], "source": "tally", "data": e})

    mode = _llm_mode()
    if mode == "openai":
        result = llm_adjudicator.adjudicate(claim, records)
    else:
        result = demo_adjudicator.adjudicate(claim, records)

    by_id = {r["record_id"]: r for r in records}
    source_records = []
    for rid in result["cited_record_ids"]:
        rec = by_id.get(rid)
        if rec:
            source_records.append({"source": rec["source"], "record_id": rid, "field": "*", "value": None})

    return {"verdict": result["verdict"], "method": result["method"],
            "reason": result["reasoning"], "source_records": source_records}


def verify_dispute(dispute_id: str, actor: str = "system") -> dict:
    claims = claim_extractor.extract_claims(dispute_id)
    if not claims:
        raise ValueError(f"No claims found for dispute {dispute_id}")

    with db.get_conn() as conn:
        conn.execute("DELETE FROM verdicts WHERE dispute_id = ?", (dispute_id,))

    final_status = "CLEARED"
    now = datetime.now(timezone.utc).isoformat()

    for claim in claims:
        order_id = _order_id_for_dispute(dispute_id)
        witnesses = source_resolver.resolve_witnesses(order_id)

        # STEP: does the cited record even exist IN THIS ORDER'S witness
        # set? Skipped for customer_identity claims -- there, the cited
        # record is expected to sometimes belong to a *different* order
        # entirely, which is exactly the contradiction check_customer_identity
        # exists to catch, via its own global lookup.
        exists = (claim["claim_type"] == "customer_identity"
                  or source_resolver.citation_exists(claim["cited_source"], claim["cited_record"], witnesses))

        if not exists:
            result = {"verdict": "insufficient_evidence", "method": "citation_not_found",
                       "reason": f"The evidence agent cited {claim['cited_source']}/{claim['cited_record']}, "
                                 f"but no such record exists in that system. The claim cannot be verified "
                                 f"against a citation that does not exist.",
                       "source_records": []}
        elif claim["claim_type"] == "customer_identity":
            cited_order = witnesses["shopify"]
            if claim["cited_record"] != (witnesses["shopify"]["order_id"] if witnesses["shopify"] else None):
                cited_order = source_resolver.resolve_by_order_id(claim["cited_record"])
            claim_for_check = dict(claim, _dispute_customer_id=_customer_id_for_dispute(dispute_id))
            result = deterministic.check_customer_identity(claim_for_check, witnesses, cited_order)
        elif claim["claim_type"] in deterministic.DETERMINISTIC_CLAIM_TYPES:
            result = deterministic.CHECKERS[claim["claim_type"]](claim, witnesses)
        else:
            result = _adjudicate_soft_claim(claim, witnesses)

        verdict_id = f"VRD-{uuid.uuid4().hex[:10]}"
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO verdicts (verdict_id, dispute_id, claim_id, verdict, verification_method, "
                "reason, source_records, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (verdict_id, dispute_id, claim["claim_id"], result["verdict"], result["method"],
                 result["reason"], db.json_dump(result["source_records"]), now))
            conn.execute(
                "INSERT INTO audit_log (audit_id, dispute_id, claim_id, action, verdict, reason, "
                "source_record_ids, verification_method, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (f"AUD-{uuid.uuid4().hex[:10]}", dispute_id, claim["claim_id"], "VERIFY",
                 result["verdict"], result["reason"],
                 db.json_dump([r["record_id"] for r in result["source_records"]]), result["method"], now))

        status = VERDICT_TO_STATUS[result["verdict"]]
        # A single material contradiction is enough to block the whole packet.
        if status == "BLOCKED":
            final_status = "BLOCKED"
        elif status == "HUMAN_CONTEXT" and final_status != "BLOCKED":
            final_status = "HUMAN_CONTEXT"

    with db.get_conn() as conn:
        conn.execute("UPDATE disputes SET status = ?, updated_at = ? WHERE dispute_id = ?",
                      (final_status, now, dispute_id))
        conn.execute(
            "INSERT INTO audit_log (audit_id, dispute_id, claim_id, action, verdict, reason, "
            "source_record_ids, verification_method, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"AUD-{uuid.uuid4().hex[:10]}", dispute_id, None, "GATE_DECISION", final_status,
             f"Final gate decision after evaluating {len(claims)} claim(s).", "[]", "gate", now))

    return {"dispute_id": dispute_id, "status": final_status}


def verify_all(actor: str = "system") -> list[dict]:
    with db.get_conn() as conn:
        ids = [r["dispute_id"] for r in conn.execute("SELECT dispute_id FROM disputes").fetchall()]
    return [verify_dispute(d, actor) for d in ids]


def _order_id_for_dispute(dispute_id: str) -> str:
    with db.get_conn() as conn:
        row = conn.execute("SELECT order_id FROM disputes WHERE dispute_id = ?", (dispute_id,)).fetchone()
    if not row:
        raise ValueError(f"Unknown dispute {dispute_id}")
    return row["order_id"]


def _customer_id_for_dispute(dispute_id: str) -> str:
    with db.get_conn() as conn:
        row = conn.execute("SELECT customer_id FROM disputes WHERE dispute_id = ?", (dispute_id,)).fetchone()
    return row["customer_id"]
