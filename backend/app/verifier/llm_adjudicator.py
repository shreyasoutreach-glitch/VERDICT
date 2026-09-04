"""
LLM adjudication -- used ONLY for claim types that deterministic.py
cannot resolve (see SOFT_CLAIM_TYPES below). The model is never asked to
compare dates or amounts; that would be, in this product's own words,
"terrible AI judgment."

The model is given a fixed, pre-fetched set of witness records (it
cannot query anything itself) and MUST return structured JSON. Any
citation to a record_id outside the set it was actually given is
rejected by the backend before the verdict is trusted -- see
validate_citations() -- and rejection always falls back to
insufficient_evidence, never to a guessed verdict.
"""
from __future__ import annotations

import json
import os

SOFT_CLAIM_TYPES = {
    "service_quality", "fulfillment_quality", "customer_request_fulfilled", "delivery_refusal_intent",
}

SYSTEM_PROMPT = """You are a claim adjudicator inside a financial evidence verification system.

You will be given:
1. A claim asserted by an AI evidence-drafting agent.
2. A fixed set of records, each with a record_id, pulled from the merchant's
   connected systems (Razorpay, Shopify, Shiprocket, Tally).

Your job is to decide whether the SUPPLIED records support, contradict, or are
insufficient to establish the claim. You may reason across multiple records,
including simple date arithmetic. You must not use any knowledge, assumption,
or record that was not explicitly supplied to you.

If the records do not establish intent, motivation, or a subjective quality that
no supplied record actually speaks to, you MUST return "insufficient_evidence".
Do not guess. Do not infer intent from indirect signals like a failed delivery
attempt alone.

Respond with ONLY a JSON object of this exact shape, nothing else:
{"verdict": "supported" | "contradicted" | "insufficient_evidence",
 "cited_record_ids": ["<one or more record_ids from the supplied set, or empty>"],
 "reasoning": "<one or two sentences>"}
"""


def _build_user_prompt(claim: dict, records: list[dict]) -> str:
    lines = [f"CLAIM: \"{claim['asserted_value']}\" (type: {claim['claim_type']})",
              f"Cited by the evidence agent: {claim['cited_source']} / {claim['cited_record']}",
              "", "SUPPLIED RECORDS:"]
    for r in records:
        lines.append(f"- record_id={r['record_id']} source={r['source']} data={json.dumps(r['data'])}")
    return "\n".join(lines)


def validate_citations(cited_ids: list[str], allowed_ids: set[str]) -> bool:
    return all(cid in allowed_ids for cid in cited_ids)


def adjudicate(claim: dict, records: list[dict]) -> dict:
    """records: [{record_id, source, data}, ...] -- exactly what the model
    is allowed to see and cite. Returns {verdict, cited_record_ids, reasoning,
    method}. Never raises on a bad model response; falls back safely."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("adjudicate() called with no OPENAI_API_KEY; caller should use demo_adjudicator instead")

    allowed_ids = {r["record_id"] for r in records}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.environ.get("VERIDICT_OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(claim, records)},
            ],
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)

        verdict = parsed.get("verdict")
        cited = parsed.get("cited_record_ids", []) or []
        reasoning = parsed.get("reasoning", "")

        if verdict not in ("supported", "contradicted", "insufficient_evidence"):
            return {"verdict": "insufficient_evidence", "cited_record_ids": [],
                    "reasoning": "Model returned an invalid verdict value; routed to human context rather "
                                 "than guessed.", "method": "llm_adjudicated_rejected"}

        if not validate_citations(cited, allowed_ids):
            return {"verdict": "insufficient_evidence", "cited_record_ids": [],
                    "reasoning": "Model cited a record it was not supplied. Rejected -- a model cannot "
                                 "invent evidence.", "method": "llm_adjudicated_rejected"}

        return {"verdict": verdict, "cited_record_ids": cited, "reasoning": reasoning,
                "method": "llm_adjudicated"}

    except Exception as exc:  # noqa: BLE001 -- any failure fails SAFE, not silently
        return {"verdict": "insufficient_evidence", "cited_record_ids": [],
                "reasoning": f"LLM adjudication failed ({exc.__class__.__name__}); routed to human "
                             f"context rather than guessed.", "method": "llm_adjudication_error"}
