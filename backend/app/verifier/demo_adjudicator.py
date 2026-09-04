"""
Demo-mode adjudicator. Implements the exact same call signature and
return contract as llm_adjudicator.adjudicate() so the pipeline can swap
between them with zero branching logic downstream. This is NOT a fake
"AI response" -- it is openly rule-based, and the verdict field says so.

The rules encode the same restraint the LLM is instructed to have:
intent and subjective quality are never inferred from indirect signals.
"""
from __future__ import annotations


def adjudicate(claim: dict, records: list[dict]) -> dict:
    by_source = {}
    for r in records:
        by_source.setdefault(r["source"], []).append(r["data"])

    claim_type = claim["claim_type"]
    cited_ids = [r["record_id"] for r in records]

    if claim_type == "delivery_refusal_intent":
        # No table anywhere records *why* a delivery attempt failed. This
        # is a structural gap, not a data-quality one -- always defer.
        return {"verdict": "insufficient_evidence", "cited_record_ids": cited_ids,
                "reasoning": "The records show a failed delivery attempt, but no connected system "
                             "records customer intent. This cannot be established from data.",
                "method": "demo_adjudicated"}

    if claim_type in ("service_quality", "fulfillment_quality", "customer_request_fulfilled"):
        shiprocket = (by_source.get("shiprocket") or [{}])[0]
        shopify = (by_source.get("shopify") or [{}])[0]
        razorpay = (by_source.get("razorpay") or [{}])[0]
        delivered_ok = shiprocket.get("status") == "delivered"
        no_return = not shopify.get("return_date")
        paid_ok = razorpay.get("status") in ("captured", "refunded")
        if delivered_ok and no_return and paid_ok:
            return {"verdict": "supported", "cited_record_ids": cited_ids,
                    "reasoning": "Delivery completed, no return on record, and payment settled -- the "
                                 "available records are consistent with the claim.",
                    "method": "demo_adjudicated"}
        return {"verdict": "insufficient_evidence", "cited_record_ids": cited_ids,
                "reasoning": "Records are mixed and do not clearly establish this subjective claim either "
                             "way.", "method": "demo_adjudicated"}

    return {"verdict": "insufficient_evidence", "cited_record_ids": cited_ids,
            "reasoning": "No demo-mode rule covers this claim type.", "method": "demo_adjudicated"}
