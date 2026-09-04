from __future__ import annotations

import os
import tempfile

TMP_DB = os.path.join(tempfile.gettempdir(), "veridict_test_api.db")
os.environ["VERIDICT_DB_PATH"] = TMP_DB
os.environ["LLM_MODE"] = "demo"

for suffix in ("", "-wal", "-shm"):
    p = TMP_DB + suffix
    if os.path.exists(p):
        os.remove(p)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app, _bootstrap  # noqa: E402

_bootstrap()  # explicit, so tests don't depend on TestClient triggering lifespan events
client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["disputes_seeded"] == 60
    assert body["llm_mode"] in ("demo", "openai")


def test_docket_lists_60():
    r = client.get("/api/disputes")
    assert r.status_code == 200
    assert len(r.json()) == 60


def test_flagship_detail():
    r = client.get("/api/disputes/VER-001")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "BLOCKED"
    assert body["verdicts"][0]["verification_method"] == "deterministic_temporal_window"


def test_witnesses_endpoint():
    r = client.get("/api/disputes/VER-001/witnesses")
    assert r.status_code == 200
    w = r.json()
    assert w["shopify"]["promised_delivery_date"] == "2026-08-10"
    assert w["shiprocket"]["delivered_date"] == "2026-08-14"


def test_evaluation_endpoint():
    r = client.get("/api/evaluation")
    assert r.status_code == 200
    body = r.json()
    assert body["dataset"]["total"] == 60


def test_inject_and_reset_integration():
    """The exact integration test the spec asks for: inject -> verify ->
    CLEARED becomes BLOCKED -- over real HTTP, against the real app."""
    disputes = client.get("/api/disputes").json()
    clean = next(d for d in disputes if d["status"] == "CLEARED")
    order_id = clean["order_id"]

    r = client.post(f"/api/chaos/inject-contradiction/{order_id}", json={"contradiction_type": "amount_mismatch"})
    assert r.status_code == 200
    assert r.json()["new_status"] == "BLOCKED"

    detail = client.get(f"/api/disputes/{clean['dispute_id']}").json()
    assert detail["status"] == "BLOCKED"

    reset = client.post("/api/reset-demo")
    assert reset.status_code == 200
    after_reset = client.get(f"/api/disputes/{clean['dispute_id']}").json()
    assert after_reset["status"] == "CLEARED"


def test_human_attestation_cannot_override_contradiction():
    detail = client.get("/api/disputes/VER-001").json()
    claim_id = detail["claims"][0]["claim_id"]
    r = client.post("/api/human-attestation", json={
        "dispute_id": "VER-001", "claim_id": claim_id,
        "question": "Why was this late?", "answer": "Courier delay", "note": "test",
    })
    assert r.status_code == 409


def test_human_attestation_accepted_for_ambiguous_case():
    disputes = client.get("/api/disputes").json()
    ambiguous = next(d for d in disputes if d["status"] == "HUMAN_CONTEXT")
    detail = client.get(f"/api/disputes/{ambiguous['dispute_id']}").json()
    claim_id = detail["claims"][0]["claim_id"]
    r = client.post("/api/human-attestation", json={
        "dispute_id": ambiguous["dispute_id"], "claim_id": claim_id,
        "question": "Why was delivery not completed?", "answer": "Courier delay", "note": "test",
    })
    assert r.status_code == 200
    assert r.json()["recorded"] is True

    audit = client.get(f"/api/disputes/{ambiguous['dispute_id']}/audit").json()
    assert any(a["action"] == "HUMAN_ATTESTATION" for a in audit)
