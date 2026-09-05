import time
import uuid
import json
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from . import db

# Minimal LLM client usage for fallback AI reconciliation
try:
    from google import genai
    from google.genai import types
except ImportError:
    pass

class AIReconciliationDecision(BaseModel):
    decision: str = Field(description="One of: match, ambiguous, no_match")
    selected_record_id: Optional[str] = Field(description="The ID of the target record if matched, else null")
    reasoning: str = Field(description="Explanation for the decision")
    evidence_fields: List[str] = Field(description="Fields that led to this decision, e.g., ['amount', 'date']")

def _call_llm_for_ambiguity(payment: dict, candidates: list) -> dict:
    import os
    # Fallback deterministic resolution if no API key
    if not os.environ.get("GEMINI_API_KEY"):
        return {
            "decision": "ambiguous",
            "selected_record_id": None,
            "reasoning": "No API key configured for AI resolution",
            "evidence_fields": []
        }
    
    try:
        client = genai.Client()
        prompt = f"""
        You are a financial reconciliation AI. 
        You must match a source payment to one of the candidate ledger records.
        
        Source Payment:
        ID: {payment['payment_id']}
        Amount: {payment['amount']}
        Date: {payment['created_at']}
        Customer: {payment['customer_id']}
        Order ID: {payment['order_id']}
        
        Candidates:
        {json.dumps(candidates, indent=2)}
        
        Is there exactly one candidate that is highly likely to be the match despite minor normalization differences?
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AIReconciliationDecision,
                temperature=0.0
            )
        )
        return json.loads(response.text)
    except Exception as e:
        return {
            "decision": "ambiguous",
            "selected_record_id": None,
            "reasoning": f"AI error: {str(e)}",
            "evidence_fields": []
        }

def run_reconciliation_batch() -> str:
    start_time = time.time()
    batch_id = f"BATCH-{str(uuid.uuid4())[:8].upper()}"
    
    with db.get_conn() as conn:
        payments = [db.row_to_dict(r) for r in conn.execute("SELECT * FROM razorpay_payments")]
        ledgers = [db.row_to_dict(r) for r in conn.execute("SELECT * FROM tally_ledger")]
        
    records = []
    exceptions = []
    
    stats = {
        "total": len(payments),
        "resolved": 0, "exact_match": 0, "normalized_match": 0,
        "ambiguous": 0,
        "mismatch": 0,
        "missing": 0,
        "duplicate": 0,
        "unresolved": 0
    }
    
    # Pre-index ledger by order_id for O(1) exact lookups
    ledger_by_order = {}
    for l in ledgers:
        oid = l['order_id']
        if oid not in ledger_by_order:
            ledger_by_order[oid] = []
        ledger_by_order[oid].append(l)

    for p in payments:
        pid = p['payment_id']
        p_oid = p['order_id']
        p_amt = float(p['amount'])
        
        candidates = ledger_by_order.get(p_oid, [])
        
        status = "UNRESOLVED"
        match_type = "NONE"
        target_id = None
        reason = ""
        amount_diff = 0.0
        
        if len(candidates) == 0:
            # Try matching by exact amount and date (normalization)
            amount_matches = [l for l in ledgers if float(l['amount']) == p_amt and p['created_at'][:10] == l['entry_date'][:10]]
            if len(amount_matches) == 1:
                status = "MATCHED_AFTER_NORMALIZATION"
                match_type = "STRONG"
                target_id = amount_matches[0]['entry_id']
                reason = "Matched via amount and date despite missing Order ID"
                stats['resolved'] += 1
                stats['normalized_match'] += 1
            elif len(amount_matches) > 1:
                # Call AI for ambiguity
                ai_decision = _call_llm_for_ambiguity(p, amount_matches)
                if ai_decision.get('decision') == 'match':
                    status = "MATCHED_AFTER_NORMALIZATION"
                    match_type = "AI_RESOLVED"
                    target_id = ai_decision.get('selected_record_id')
                    reason = f"AI matched: {ai_decision.get('reasoning')}"
                    stats['resolved'] += 1
                    stats['normalized_match'] += 1
                else:
                    status = "AMBIGUOUS"
                    match_type = "CONFLICT"
                    reason = "Multiple potential matches by amount"
                    stats['ambiguous'] += 1
            else:
                status = "MISSING_RECORD"
                match_type = "NO_TARGET"
                reason = "No ledger entry found"
                stats['missing'] += 1
                
        elif len(candidates) == 1:
            target = candidates[0]
            target_id = target['entry_id']
            t_amt = float(target['amount'])
            if t_amt == p_amt:
                status = "MATCHED"
                match_type = "EXACT"
                reason = "Exact order and amount match"
                stats['resolved'] += 1
                stats['exact_match'] += 1
            else:
                status = "AMOUNT_MISMATCH"
                match_type = "CONFLICT"
                amount_diff = t_amt - p_amt
                reason = f"Amount differs by {amount_diff}"
                stats['mismatch'] += 1
                
        else:
            status = "DUPLICATE"
            match_type = "MULTIPLE_TARGETS"
            reason = f"{len(candidates)} ledger entries found for same order"
            stats['duplicate'] += 1

        rec_id = f"REC-{str(uuid.uuid4())[:8]}"
        records.append({
            "reconciliation_id": rec_id,
            "batch_id": batch_id,
            "source_system": "Razorpay",
            "source_record_id": pid,
            "target_system": "Tally",
            "target_record_id": target_id,
            "match_status": status,
            "match_type": match_type,
            "confidence": 1.0 if match_type == "EXACT" else 0.8,
            "amount_difference": amount_diff,
            "date_difference": 0,
            "reason": reason,
            "created_at": datetime.utcnow().isoformat() + "Z"
        })
        
        # Exceptions
        if status not in ("MATCHED", "MATCHED_AFTER_NORMALIZATION"):
            exc_type = status
            stats['unresolved'] += 1
            exceptions.append({
                "exception_id": f"EXC-{str(uuid.uuid4())[:8]}",
                "batch_id": batch_id,
                "source_record_id": pid,
                "exception_type": exc_type,
                "severity": "HIGH",
                "explanation": reason,
                "candidate_matches": json.dumps(candidates if candidates else []),
                "status": "OPEN",
                "human_resolution": None,
                "created_at": datetime.utcnow().isoformat() + "Z"
            })

    processing_time_ms = int((time.time() - start_time) * 1000)
    resolution_rate = (stats['resolved'] / stats['total']) * 100.0 if stats['total'] > 0 else 0.0
    exact_match_rate = (stats['exact_match'] / stats['total']) * 100.0 if stats['total'] > 0 else 0.0
    
    with db.get_conn() as conn:
        conn.execute("""
            INSERT INTO reconciliation_batches 
            (batch_id, created_at, total_records, resolved_count, exact_match_count, normalized_match_count, ambiguous_count, mismatch_count, missing_count, duplicate_count, unresolved_count, resolution_rate, exact_match_rate, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, datetime.utcnow().isoformat() + "Z", stats['total'], stats['resolved'], stats['exact_match'], stats['normalized_match'], stats['ambiguous'], stats['mismatch'], stats['missing'], stats['duplicate'], stats['unresolved'], resolution_rate, exact_match_rate, processing_time_ms))
        
        for r in records:
            conn.execute("""
                INSERT INTO reconciliation_records
                (reconciliation_id, batch_id, source_system, source_record_id, target_system, target_record_id, match_status, match_type, confidence, amount_difference, date_difference, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r['reconciliation_id'], r['batch_id'], r['source_system'], r['source_record_id'], r['target_system'], r['target_record_id'], r['match_status'], r['match_type'], r['confidence'], r['amount_difference'], r['date_difference'], r['reason'], r['created_at']))
            
        for e in exceptions:
            conn.execute("""
                INSERT INTO reconciliation_exceptions
                (exception_id, batch_id, source_record_id, exception_type, severity, explanation, candidate_matches, status, human_resolution, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (e['exception_id'], e['batch_id'], e['source_record_id'], e['exception_type'], e['severity'], e['explanation'], e['candidate_matches'], e['status'], e['human_resolution'], e['created_at']))
            
    return batch_id
