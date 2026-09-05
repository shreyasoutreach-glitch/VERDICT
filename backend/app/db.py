"""
VERIDICT database layer.

Deliberately raw sqlite3, not an ORM. The whole point of this product is
that four systems don't share a schema or a connection — an ORM that
quietly unified them would undermine the thing being demonstrated.

Four "merchant systems" (razorpay_payments, shopify_orders,
shiprocket_shipments, tally_ledger) are just tables here for demo
convenience, but the verification pipeline treats them as if they were
separate services: it never joins across them in SQL, it always resolves
each one independently the way a real cross-system client would.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(os.environ.get("VERIDICT_DB_PATH", Path(__file__).resolve().parent.parent / "veridict.db"))

_lock = threading.Lock()

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- SYSTEM 1: Razorpay (the payment record of truth)
-- ============================================================
CREATE TABLE IF NOT EXISTS razorpay_payments (
    payment_id   TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    customer_id  TEXT NOT NULL,
    amount       REAL NOT NULL,
    status       TEXT NOT NULL,          -- captured | refunded | failed | disputed
    method       TEXT NOT NULL,          -- upi | card | netbanking
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_order ON razorpay_payments(order_id);

-- ============================================================
-- SYSTEM 2: Shopify (the commerce record of truth)
-- ============================================================
CREATE TABLE IF NOT EXISTS shopify_orders (
    order_id               TEXT PRIMARY KEY,
    customer_id            TEXT NOT NULL,
    sku                    TEXT NOT NULL,
    qty                    INTEGER NOT NULL,
    order_status           TEXT NOT NULL,   -- fulfilled | returned | cancelled
    promised_delivery_date TEXT NOT NULL,
    return_date            TEXT,
    return_reason          TEXT
);

-- ============================================================
-- SYSTEM 3: Shiprocket (the fulfillment record of truth)
-- ============================================================
CREATE TABLE IF NOT EXISTS shiprocket_shipments (
    shipment_id    TEXT PRIMARY KEY,
    order_id       TEXT NOT NULL,
    courier        TEXT NOT NULL,
    dispatch_date  TEXT NOT NULL,
    delivered_date TEXT,
    status         TEXT NOT NULL,   -- in_transit | delivered | returned_to_origin
    scan_events    TEXT NOT NULL    -- JSON array [{timestamp, event}]
);
CREATE INDEX IF NOT EXISTS idx_shipments_order ON shiprocket_shipments(order_id);

-- ============================================================
-- SYSTEM 4: Tally (the accounting ledger of truth)
-- ============================================================
CREATE TABLE IF NOT EXISTS tally_ledger (
    entry_id    TEXT PRIMARY KEY,
    order_id    TEXT NOT NULL,
    entry_type  TEXT NOT NULL,   -- sale | refund | chargeback_reserve
    amount      REAL NOT NULL,
    entry_date  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_order ON tally_ledger(order_id);

-- ============================================================
-- VERIDICT's own state: disputes, evidence, claims, verdicts, audit
-- ============================================================

-- SYSTEM 5: Reconciliation
CREATE TABLE IF NOT EXISTS reconciliation_batches (
    batch_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    total_records INTEGER NOT NULL,
    resolved_count INTEGER NOT NULL,
    exact_match_count INTEGER NOT NULL,
    normalized_match_count INTEGER NOT NULL,
    ambiguous_count INTEGER NOT NULL,
    mismatch_count INTEGER NOT NULL,
    missing_count INTEGER NOT NULL,
    duplicate_count INTEGER NOT NULL,
    unresolved_count INTEGER NOT NULL,
    resolution_rate REAL NOT NULL,
    exact_match_rate REAL NOT NULL,
    processing_time_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_records (
    reconciliation_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    target_system TEXT NOT NULL,
    target_record_id TEXT,
    match_status TEXT NOT NULL,
    match_type TEXT NOT NULL,
    confidence REAL,
    amount_difference REAL,
    date_difference INTEGER,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_exceptions (
    exception_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    exception_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    explanation TEXT NOT NULL,
    candidate_matches TEXT NOT NULL,
    status TEXT NOT NULL,
    human_resolution TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_ground_truth (
    source_record_id TEXT PRIMARY KEY,
    true_target_record_id TEXT,
    expected_status TEXT NOT NULL,
    scenario_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disputes
 (
    dispute_id   TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    customer_id  TEXT NOT NULL,
    narrative    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|CLEARED|BLOCKED|HUMAN_CONTEXT
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    -- ground truth is stored but never read by the verifier, only by /api/evaluation
    ground_truth_contradiction INTEGER NOT NULL DEFAULT 0,
    contradiction_class TEXT,
    -- true for cases deliberately built to be genuinely unresolvable from
    -- records (dangling citation, or a structurally unknowable intent claim)
    ground_truth_needs_context INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    dispute_id    TEXT NOT NULL REFERENCES disputes(dispute_id),
    claim_type    TEXT NOT NULL,
    asserted_value TEXT NOT NULL,
    cited_source  TEXT NOT NULL,
    cited_record  TEXT NOT NULL,
    confidence    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_dispute ON claims(dispute_id);

CREATE TABLE IF NOT EXISTS verdicts (
    verdict_id          TEXT PRIMARY KEY,
    dispute_id          TEXT NOT NULL REFERENCES disputes(dispute_id),
    claim_id            TEXT NOT NULL REFERENCES claims(claim_id),
    verdict             TEXT NOT NULL,   -- supported | contradicted | insufficient_evidence
    verification_method TEXT NOT NULL,   -- deterministic_temporal | deterministic_exact | llm_adjudicated | demo_adjudicated
    reason               TEXT NOT NULL,
    source_records       TEXT NOT NULL,  -- JSON list of {source, record_id, field, value}
    created_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verdicts_dispute ON verdicts(dispute_id);

-- Human context is testimony, never a rewrite of system fact. It can only
-- attach to a claim VERIDICT already marked insufficient_evidence; it can
-- never flip a CONTRADICTED verdict, and the API layer enforces that.
CREATE TABLE IF NOT EXISTS human_attestations (
    attestation_id TEXT PRIMARY KEY,
    dispute_id     TEXT NOT NULL,
    claim_id       TEXT NOT NULL,
    question       TEXT NOT NULL,
    answer         TEXT NOT NULL,
    note           TEXT,
    submitted_by   TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attestations_dispute ON human_attestations(dispute_id);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id           TEXT PRIMARY KEY,
    dispute_id         TEXT NOT NULL,
    claim_id           TEXT,
    action             TEXT NOT NULL,   -- VERIFY | INJECT | RESET | GATE_DECISION
    verdict             TEXT,
    reason              TEXT NOT NULL,
    source_record_ids   TEXT NOT NULL,  -- JSON list
    verification_method TEXT,
    created_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_dispute ON audit_log(dispute_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Serialize writes with a process-wide lock; SQLite + FastAPI's default
    threadpool otherwise risks 'database is locked' under concurrent chaos
    injection + polling reads during the demo."""
    with _lock:
        conn = connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_schema() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def wipe_all_tables() -> None:
    tables = [
        "audit_log", "human_attestations", "verdicts", "claims", "disputes",
        "reconciliation_ground_truth", "reconciliation_exceptions", "reconciliation_records", "reconciliation_batches", "tally_ledger", "shiprocket_shipments", "shopify_orders", "razorpay_payments",
    ]
    with get_conn() as conn:
        for t in tables:
            conn.execute(f"DELETE FROM {t}")


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def json_dump(obj) -> str:
    return json.dumps(obj, default=str)


def json_load(s: str):
    return json.loads(s) if s else None
