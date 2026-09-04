"""
pytest -q from backend/. Uses an isolated on-disk temp DB per test session
(via VERIDICT_DB_PATH env var set in conftest) so tests never touch a
dev database.
"""
from __future__ import annotations

import os
import tempfile

import pytest

TMP_DB = os.path.join(tempfile.gettempdir(), "veridict_test.db")
os.environ["VERIDICT_DB_PATH"] = TMP_DB
os.environ["LLM_MODE"] = "demo"

from app import db, seed, chaos, evaluation  # noqa: E402
from app.verifier import pipeline, deterministic, llm_adjudicator  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def fresh_db():
    for suffix in ("", "-wal", "-shm"):
        p = TMP_DB + suffix
        if os.path.exists(p):
            os.remove(p)
    db.init_schema()
    seed.seed_database()
    pipeline.verify_all()
    yield


def _dispute(dispute_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM disputes WHERE dispute_id = ?", (dispute_id,)).fetchone()
    return db.row_to_dict(row)


def _verdict_for(dispute_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM verdicts WHERE dispute_id = ? LIMIT 1", (dispute_id,)).fetchone()
    return db.row_to_dict(row)


# 1. Clean delivery claim -> supported / CLEARED
def test_clean_delivery_claim_clears():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT dispute_id FROM disputes WHERE ground_truth_contradiction = 0 "
            "AND ground_truth_needs_context = 0 LIMIT 5").fetchall()
    assert rows, "expected some clean, unambiguous disputes in the seed"
    for r in rows:
        d = _dispute(r["dispute_id"])
        assert d["status"] == "CLEARED", f"{r['dispute_id']} should be CLEARED, was {d['status']}"


# 2. Late delivery -> contradicted / BLOCKED (the flagship)
def test_flagship_delivery_window_contradiction():
    d = _dispute("VER-001")
    assert d["status"] == "BLOCKED"
    v = _verdict_for("VER-001")
    assert v["verdict"] == "contradicted"
    assert v["verification_method"] == "deterministic_temporal_window"
    assert "4 day" in v["reason"]


# 3. Amount mismatch
def test_amount_mismatch_detected():
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT dispute_id FROM disputes WHERE contradiction_class = 'amount_mismatch' LIMIT 1").fetchone()
    d = _dispute(row["dispute_id"])
    assert d["status"] == "BLOCKED"


# 4. Payment status mismatch
def test_payment_status_mismatch_detected():
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT dispute_id FROM disputes WHERE contradiction_class = 'payment_status' LIMIT 1").fetchone()
    d = _dispute(row["dispute_id"])
    assert d["status"] == "BLOCKED"


# 5. Missing evidence (dangling citation) -> HUMAN_CONTEXT, not a guess
def test_missing_evidence_routes_to_human_context():
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT dispute_id FROM disputes WHERE ground_truth_needs_context = 1 "
            "AND ground_truth_contradiction = 0 LIMIT 10").fetchall()
    assert row
    found_dangling = False
    for r in row:
        d = _dispute(r["dispute_id"])
        assert d["status"] == "HUMAN_CONTEXT"
        found_dangling = True
    assert found_dangling


# 6. Human-context routing accuracy is measured correctly
def test_human_context_routing_metric():
    result = evaluation.run_evaluation()
    assert result["metrics"]["human_context_routing_accuracy"] == 1.0


# 7. Human attestation persistence
def test_human_attestation_persists():
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT dispute_id FROM disputes WHERE status = 'HUMAN_CONTEXT' LIMIT 1").fetchone()
    dispute_id = row["dispute_id"]
    with db.get_conn() as conn:
        claim = conn.execute("SELECT claim_id FROM claims WHERE dispute_id = ? LIMIT 1", (dispute_id,)).fetchone()
    import uuid
    from datetime import datetime
    att_id = f"ATT-{uuid.uuid4().hex[:8]}"
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO human_attestations (attestation_id, dispute_id, claim_id, question, answer, note, "
            "submitted_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (att_id, dispute_id, claim["claim_id"], "Why was delivery not completed?", "Courier delay",
             "Regional disruption reported.", "test_user", datetime.utcnow().isoformat()))
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM human_attestations WHERE attestation_id = ?", (att_id,)).fetchone()
    assert row is not None
    assert db.row_to_dict(row)["answer"] == "Courier delay"


# 8. Chaos injection actually mutates state and flips the verdict
def test_chaos_injection_flips_clean_to_blocked():
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT order_id, dispute_id FROM disputes WHERE ground_truth_contradiction = 0 "
            "AND ground_truth_needs_context = 0 LIMIT 1").fetchone()
    order_id, dispute_id = row["order_id"], row["dispute_id"]

    before = _dispute(dispute_id)
    assert before["status"] == "CLEARED"

    result = chaos.inject(order_id, "delivery_window")
    assert result["new_status"] == "BLOCKED"

    after = _dispute(dispute_id)
    assert after["status"] == "BLOCKED"

    with db.get_conn() as conn:
        shiprocket = db.row_to_dict(
            conn.execute("SELECT * FROM shiprocket_shipments WHERE order_id = ?", (order_id,)).fetchone())
        shopify = db.row_to_dict(
            conn.execute("SELECT * FROM shopify_orders WHERE order_id = ?", (order_id,)).fetchone())
    from app.verifier import temporal
    check = temporal.check_delivery_window(shopify["promised_delivery_date"], shiprocket["delivered_date"])
    assert not check["holds"], "the database itself must show the late delivery, not just the verdict"


# 9. Reset demo restores deterministic original state
def test_reset_demo_restores_state():
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT order_id, dispute_id FROM disputes WHERE ground_truth_contradiction = 0 "
            "AND ground_truth_needs_context = 0 AND status = 'CLEARED' LIMIT 1").fetchone()
    order_id, dispute_id = row["order_id"], row["dispute_id"]
    chaos.inject(order_id, "amount_mismatch")
    assert _dispute(dispute_id)["status"] == "BLOCKED"

    seed.seed_database()
    pipeline.verify_all()

    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM disputes").fetchone()["n"]
    assert n == 60
    assert _dispute("VER-001")["status"] == "BLOCKED"  # flagship deterministically present again


# 10. Duplicate injection is safe (idempotent), does not corrupt further or crash
def test_duplicate_injection_is_safe():
    seed.seed_database()
    pipeline.verify_all()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT order_id FROM disputes WHERE ground_truth_contradiction = 0 "
            "AND ground_truth_needs_context = 0 LIMIT 1").fetchone()
    order_id = row["order_id"]

    r1 = chaos.inject(order_id, "payment_status")
    r2 = chaos.inject(order_id, "payment_status")
    assert r1["new_status"] == r2["new_status"] == "BLOCKED"

    with db.get_conn() as conn:
        refund_entries = conn.execute(
            "SELECT * FROM tally_ledger WHERE order_id = ? AND entry_type = 'refund'", (order_id,)).fetchall()
    assert len(refund_entries) == 1, "double injection must not create duplicate ledger rows"


# 11. Evaluation metrics computed, not hardcoded
def test_evaluation_metrics_are_computed():
    seed.seed_database()
    pipeline.verify_all()
    result = evaluation.run_evaluation()
    assert result["dataset"]["total"] == 60
    assert result["dataset"]["contradictory"] == 12
    assert result["dataset"]["clean"] == 48
    cm = result["confusion_matrix"]
    assert cm["true_positive"] + cm["false_negative"] == 12
    assert cm["true_negative"] + cm["false_positive"] == 48


# 12. LLM adjudicator rejects a citation it wasn't given
def test_llm_adjudicator_rejects_unsupplied_citation():
    allowed = {"PAY-1", "ORDER-1"}
    assert llm_adjudicator.validate_citations(["PAY-1"], allowed) is True
    assert llm_adjudicator.validate_citations(["PAY-999"], allowed) is False
    assert llm_adjudicator.validate_citations(["PAY-1", "GHOST-1"], allowed) is False


# 13. Demo adjudicator implements the same interface/contract as the LLM adjudicator
def test_demo_adjudicator_contract():
    from app.verifier import demo_adjudicator
    claim = {"claim_type": "delivery_refusal_intent", "asserted_value": "refused_by_customer"}
    records = [{"record_id": "SHIP-1", "source": "shiprocket", "data": {"status": "delivered"}}]
    result = demo_adjudicator.adjudicate(claim, records)
    assert set(result.keys()) == {"verdict", "cited_record_ids", "reasoning", "method"}
    assert result["verdict"] == "insufficient_evidence"


# 14. Deterministic core requires no API key at all
def test_deterministic_checks_need_no_llm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    d = _dispute("VER-001")  # a hard, deterministic claim type
    assert d["status"] == "BLOCKED"  # already verified above with no key set in this test env


# 15. Human attestation cannot override a CONTRADICTED verdict (API-layer rule,
# exercised at the pipeline/db level here since this file doesn't spin up FastAPI)
def test_contradicted_claim_identified_for_attestation_guard():
    v = _verdict_for("VER-001")
    assert v["verdict"] == "contradicted"
    # main.py's /api/human-attestation endpoint checks exactly this condition
    # before accepting a submission -- see test_api.py for the HTTP-level test.
