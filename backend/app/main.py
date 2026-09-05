from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import chaos, db, evaluation, seed
from .schemas import ChaosInjectRequest, HumanAttestationRequest
from .verifier import pipeline, source_resolver

app = FastAPI(title="VERIDICT", description="Cross-system truth verification for AI-generated financial claims.")

import os

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _bootstrap() -> None:
    db.init_schema()
    with db.get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM disputes").fetchone()["n"]
    if count == 0:
        seed.seed_database()
        pipeline.verify_all()


@app.on_event("startup")
def on_startup() -> None:
    _bootstrap()


def _llm_mode() -> str:
    mode = os.environ.get("LLM_MODE", "").strip().lower()
    if mode in ("openai", "demo"):
        return mode
    return "openai" if os.environ.get("OPENAI_API_KEY", "").strip() else "demo"


@app.get("/api/health")
def health():
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM disputes").fetchone()["n"]
    return {"status": "ok", "disputes_seeded": n, "llm_mode": _llm_mode(),
            "time": datetime.now(timezone.utc).isoformat()}


def _dispute_row_summary(conn, row) -> dict:
    d = db.row_to_dict(row)
    claims = conn.execute("SELECT * FROM claims WHERE dispute_id = ?", (d["dispute_id"],)).fetchall()
    verdicts = conn.execute("SELECT * FROM verdicts WHERE dispute_id = ?", (d["dispute_id"],)).fetchall()
    systems = set()
    contradictions = 0
    for v in verdicts:
        vd = db.row_to_dict(v)
        for sr in db.json_load(vd["source_records"]) or []:
            systems.add(sr["source"])
        if vd["verdict"] == "contradicted":
            contradictions += 1
    primary_claim = db.row_to_dict(claims[0]) if claims else None
    return {
        "dispute_id": d["dispute_id"], "order_id": d["order_id"], "customer_id": d["customer_id"],
        "status": d["status"], "updated_at": d["updated_at"],
        "claim_count": len(claims),
        "claim_summary": primary_claim["asserted_value"] if primary_claim else None,
        "cited_source": primary_claim["cited_source"] if primary_claim else None,
        "contradictions": contradictions,
        "systems_checked": sorted(systems),
    }


@app.get("/api/disputes")
def list_disputes():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM disputes ORDER BY dispute_id").fetchall()
        return [_dispute_row_summary(conn, r) for r in rows]


@app.get("/api/disputes/{dispute_id}")
def get_dispute(dispute_id: str):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM disputes WHERE dispute_id = ?", (dispute_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Dispute {dispute_id} not found")
        d = db.row_to_dict(row)
        claims = [db.row_to_dict(r) for r in
                  conn.execute("SELECT * FROM claims WHERE dispute_id = ?", (dispute_id,)).fetchall()]
        verdicts = [db.row_to_dict(r) for r in
                    conn.execute("SELECT * FROM verdicts WHERE dispute_id = ?", (dispute_id,)).fetchall()]
        attestations = [db.row_to_dict(r) for r in
                         conn.execute("SELECT * FROM human_attestations WHERE dispute_id = ?",
                                      (dispute_id,)).fetchall()]
    for v in verdicts:
        v["source_records"] = db.json_load(v["source_records"])
    d["claims"] = claims
    d["verdicts"] = verdicts
    d["human_attestations"] = attestations
    return d


@app.get("/api/disputes/{dispute_id}/claims")
def get_claims(dispute_id: str):
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM claims WHERE dispute_id = ?", (dispute_id,)).fetchall()
    return [db.row_to_dict(r) for r in rows]


@app.get("/api/disputes/{dispute_id}/witnesses")
def get_witnesses(dispute_id: str):
    with db.get_conn() as conn:
        row = conn.execute("SELECT order_id FROM disputes WHERE dispute_id = ?", (dispute_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Dispute {dispute_id} not found")
        order_id = row["order_id"]
    witnesses = source_resolver.resolve_witnesses(order_id)
    if witnesses["shiprocket"]:
        witnesses["shiprocket"]["scan_events"] = db.json_load(witnesses["shiprocket"]["scan_events"])
    return witnesses


@app.get("/api/disputes/{dispute_id}/audit")
def get_audit(dispute_id: str):
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE dispute_id = ? ORDER BY created_at", (dispute_id,)).fetchall()
    out = []
    for r in rows:
        rd = db.row_to_dict(r)
        rd["source_record_ids"] = db.json_load(rd["source_record_ids"])
        out.append(rd)
    return out


@app.get("/api/metrics")
def metrics():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT status FROM disputes").fetchall()
    counts = {"CLEARED": 0, "BLOCKED": 0, "HUMAN_CONTEXT": 0, "PENDING": 0}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"total": len(rows), **counts}


@app.post("/api/verify/{dispute_id}")
def verify_one(dispute_id: str):
    try:
        return pipeline.verify_dispute(dispute_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/verify-all")
def verify_all_endpoint():
    return {"results": pipeline.verify_all()}


@app.post("/api/chaos/inject-contradiction/{order_id}")
def inject_contradiction(order_id: str, body: ChaosInjectRequest):
    try:
        return chaos.inject(order_id, body.contradiction_type)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/reset-demo")
def reset_demo():
    seed.seed_database()
    pipeline.verify_all()
    return {"reset": True, "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/human-attestation")
def submit_human_attestation(body: HumanAttestationRequest):
    with db.get_conn() as conn:
        dispute = conn.execute("SELECT * FROM disputes WHERE dispute_id = ?", (body.dispute_id,)).fetchone()
        if not dispute:
            raise HTTPException(404, f"Dispute {body.dispute_id} not found")
        verdict_row = conn.execute(
            "SELECT * FROM verdicts WHERE claim_id = ? ORDER BY created_at DESC LIMIT 1",
            (body.claim_id,)).fetchone()
        # Human context can only attach to a claim VERIDICT already marked
        # insufficient_evidence. It can never override a CONTRADICTED
        # verdict -- that would let testimony rewrite a system fact.
        if verdict_row and db.row_to_dict(verdict_row)["verdict"] == "contradicted":
            raise HTTPException(
                409, "This claim was CONTRADICTED by system records, not left ambiguous. Human context "
                     "can explain a contradiction; it cannot overturn one.")

        import uuid
        attestation_id = f"ATT-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO human_attestations (attestation_id, dispute_id, claim_id, question, answer, "
            "note, submitted_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (attestation_id, body.dispute_id, body.claim_id, body.question, body.answer, body.note,
             body.submitted_by, now))
        conn.execute(
            "INSERT INTO audit_log (audit_id, dispute_id, claim_id, action, verdict, reason, "
            "source_record_ids, verification_method, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"AUD-{attestation_id}", body.dispute_id, body.claim_id, "HUMAN_ATTESTATION", "insufficient_evidence",
             f"Human context recorded: \"{body.answer}\" -- this explains the event, it does not modify "
             f"any system record.", "[]", "human_attestation", now))
    return {"attestation_id": attestation_id, "dispute_id": body.dispute_id, "recorded": True}


@app.get("/api/evaluation")
def get_evaluation():
    return evaluation.run_evaluation()


@app.get("/api/config")
def get_config():
    return {"llm_mode": _llm_mode()}

@app.post('/api/reconcile')
def run_reconciliation():
    from .reconciler import run_reconciliation_batch
    batch_id = run_reconciliation_batch()
    return {'batch_id': batch_id}

@app.get('/api/reconciliation/latest')
def get_latest_batch():
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM reconciliation_batches ORDER BY created_at DESC LIMIT 1').fetchone()
    if not row:
        return None
    return db.row_to_dict(row)

@app.get('/api/reconciliation/records')
def get_reconciliation_records(batch_id: str = None):
    with db.get_conn() as conn:
        if not batch_id:
            batch = conn.execute('SELECT batch_id FROM reconciliation_batches ORDER BY created_at DESC LIMIT 1').fetchone()
            if not batch:
                return []
            batch_id = batch[0]
        rows = conn.execute('SELECT * FROM reconciliation_records WHERE batch_id = ?', (batch_id,)).fetchall()
    return [db.row_to_dict(r) for r in rows]

@app.get('/api/reconciliation/exceptions')
def get_reconciliation_exceptions(batch_id: str = None):
    with db.get_conn() as conn:
        if not batch_id:
            batch = conn.execute('SELECT batch_id FROM reconciliation_batches ORDER BY created_at DESC LIMIT 1').fetchone()
            if not batch:
                return []
            batch_id = batch[0]
        rows = conn.execute('SELECT * FROM reconciliation_exceptions WHERE batch_id = ?', (batch_id,)).fetchall()
    return [db.row_to_dict(r) for r in rows]

@app.post('/api/chaos/reconciliation/{mutation_type}')
def inject_reconciliation_chaos(mutation_type: str):
    with db.get_conn() as conn:
        row = conn.execute("SELECT true_target_record_id, source_record_id FROM reconciliation_ground_truth WHERE expected_status = 'MATCHED' LIMIT 1").fetchone()
        if not row:
            raise HTTPException(status_code=400, detail='No matching records available to mutate')
        t_id = row[0]
        
        if mutation_type == 'amount_mismatch':
            conn.execute('UPDATE tally_ledger SET amount = amount + 1500 WHERE entry_id = ?', (t_id,))
            conn.commit()
        elif mutation_type == 'delete':
            conn.execute('DELETE FROM tally_ledger WHERE entry_id = ?', (t_id,))
            conn.commit()
        elif mutation_type == 'duplicate':
            orig = db.row_to_dict(conn.execute('SELECT * FROM tally_ledger WHERE entry_id = ?', (t_id,)).fetchone())
            conn.execute('INSERT INTO tally_ledger (entry_id, order_id, entry_type, amount, entry_date) VALUES (?, ?, ?, ?, ?)',
                         (orig['entry_id'] + '-DUP', orig['order_id'], orig['entry_type'], orig['amount'], orig['entry_date']))
            conn.commit()
        elif mutation_type == 'date_mismatch':
            conn.execute("UPDATE tally_ledger SET entry_date = datetime(entry_date, '+10 days') WHERE entry_id = ?", (t_id,))
            conn.commit()
            
        return {'mutated': True, 'target': t_id}
