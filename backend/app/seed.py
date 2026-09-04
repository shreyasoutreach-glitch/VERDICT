"""
Deterministic seed generator for VERIDICT.

Fixed seed => same 60 disputes, same 12 contradictions, every run and every
judge who clones the repo. Ground truth (whether a dispute's underlying
multi-system data was deliberately made inconsistent) is written to
disputes.ground_truth_contradiction / contradiction_class and is used ONLY
by the evaluation endpoint. The verification pipeline never reads those
two columns -- see app/verifier/pipeline.py, which selects explicitly
excludes them from the row it is given.

Design: this module writes the underlying "world state" (what really
happened, across four systems that don't talk to each other). It does
NOT write claims -- app/evidence_generator.py plays the role of the
naive upstream "Dispute Responder" agent that reads ONE system per claim
and asserts confidently. Contradictions are a property of the world
this module builds, not something bolted on afterwards.
"""
from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta, timezone

from . import db

SEED = 1729
random.seed(SEED)

SKUS = ["SKU-KURTA-BLU", "SKU-SNEAKER-42", "SKU-MIXER-750W", "SKU-BACKPACK-GRY",
        "SKU-LAMP-LED", "SKU-BOTTLE-1L", "SKU-HEADPHONE-BT", "SKU-WATCH-SPT"]
COURIERS = ["Delhivery", "Bluedart", "Shiprocket Logistics", "Ekart"]

CONTRADICTION_PLAN = (
    ["delivery_window"] * 3
    + ["amount_mismatch"] * 2
    + ["payment_status"] * 2
    + ["return_chronology"] * 1
    + ["refund_amount"] * 1
    + ["missing_ledger_entry"] * 1
    + ["duplicate_refund"] * 1
    + ["customer_order_mismatch"] * 1
)  # exactly 12

assert len(CONTRADICTION_PLAN) == 12


def _iso_date(d: date) -> str:
    return d.isoformat()


def _iso_dt(d: date, h: int, m: int = 0) -> str:
    return datetime(d.year, d.month, d.day, h, m).isoformat()


def _new_customer(i: int) -> str:
    return f"CUST-{1000 + i:04d}"


def _base_records(order_id: str, shipment_id: str, payment_id: str, entry_id: str,
                   customer_id: str, sku: str, amount: float,
                   order_date: date):
    """A perfectly consistent, clean quadruple of records: on-time delivery,
    correct amounts everywhere, no return, no refund. Contradiction builders
    below start from this and deliberately break one relationship."""
    promised = order_date + timedelta(days=6)
    dispatched = order_date + timedelta(days=1)
    delivered = order_date + timedelta(days=5)  # inside window

    scan_events = [
        {"timestamp": _iso_dt(dispatched, 9), "event": "PICKED_UP"},
        {"timestamp": _iso_dt(dispatched + timedelta(days=1), 14), "event": "IN_TRANSIT"},
        {"timestamp": _iso_dt(delivered, 10), "event": "OUT_FOR_DELIVERY"},
        {"timestamp": _iso_dt(delivered, 16), "event": "DELIVERED"},
    ]

    razorpay = dict(payment_id=payment_id, order_id=order_id, customer_id=customer_id,
                     amount=amount, status="captured", method=random.choice(["upi", "card", "netbanking"]),
                     created_at=_iso_dt(order_date, 12))
    shopify = dict(order_id=order_id, customer_id=customer_id, sku=sku, qty=random.choice([1, 1, 1, 2]),
                    order_status="fulfilled", promised_delivery_date=_iso_date(promised),
                    return_date=None, return_reason=None)
    shiprocket = dict(shipment_id=shipment_id, order_id=order_id, courier=random.choice(COURIERS),
                       dispatch_date=_iso_date(dispatched), delivered_date=_iso_date(delivered),
                       status="delivered", scan_events=db.json_dump(scan_events))
    ledger = [dict(entry_id=entry_id, order_id=order_id, entry_type="sale", amount=amount,
                    entry_date=_iso_date(order_date))]
    return razorpay, shopify, shiprocket, ledger, dict(promised=promised, dispatched=dispatched, delivered=delivered)


def _apply_contradiction(cls: str, razorpay: dict, shopify: dict, shiprocket: dict,
                          ledger: list, dates: dict, order_id: str, entry_seq: int,
                          other_customer_id: str | None, other_order_id: str | None):
    """Mutates the clean quadruple to deliberately introduce exactly one
    class of cross-system contradiction. Returns which claim_type the
    (naive) evidence generator should be steered toward, so the flaw
    actually surfaces in the packet it writes."""
    if cls == "delivery_window":
        # Courier genuinely delivered, but four days late. Shiprocket
        # itself is 100% accurate -- it just isn't the whole story.
        late = dates["promised"] + timedelta(days=4)
        shiprocket["delivered_date"] = _iso_date(late)
        events = db.json_load(shiprocket["scan_events"])
        events.append({"timestamp": _iso_dt(late, 11), "event": "DELIVERY_ATTEMPT_FAILED"})
        events.append({"timestamp": _iso_dt(late, 16), "event": "DELIVERED"})
        shiprocket["scan_events"] = db.json_dump(events)
        shiprocket["status"] = "delivered"
        return "delivery_window"

    if cls == "amount_mismatch":
        # Gateway and books disagree on how much actually changed hands.
        ledger[0]["amount"] = round(razorpay["amount"] * random.choice([0.7, 1.25]), 2)
        return "amount"

    if cls == "payment_status":
        # Tally recorded a refund; Razorpay's own status field never
        # got updated -- a stale-sync bug, not a lie.
        ledger.append(dict(entry_id=f"TALLY-{order_id}-{entry_seq}", order_id=order_id,
                            entry_type="refund", amount=razorpay["amount"],
                            entry_date=_iso_date(dates["delivered"] + timedelta(days=2))))
        razorpay["status"] = "captured"  # should be "refunded" given the ledger
        return "payment_status"

    if cls == "return_chronology":
        # The order was "returned" before the courier's own record shows
        # it was ever delivered. Impossible sequence, not a value clash.
        shopify["order_status"] = "returned"
        shopify["return_date"] = _iso_date(dates["delivered"] - timedelta(days=2))
        shopify["return_reason"] = "Wrong item received"
        return "delivery_status"

    if cls == "refund_amount":
        original = razorpay["amount"]
        partial = round(original * 0.5, 2)
        ledger.append(dict(entry_id=f"TALLY-{order_id}-{entry_seq}", order_id=order_id,
                            entry_type="refund", amount=partial,
                            entry_date=_iso_date(dates["delivered"] + timedelta(days=3))))
        razorpay["status"] = "refunded"
        shopify["order_status"] = "returned"
        shopify["return_date"] = _iso_date(dates["delivered"] + timedelta(days=1))
        shopify["return_reason"] = "Size issue"
        return "refund_status"

    if cls == "missing_ledger_entry":
        # Razorpay says refunded. Tally has no matching entry at all --
        # the money movement was never booked.
        razorpay["status"] = "refunded"
        shopify["order_status"] = "returned"
        shopify["return_date"] = _iso_date(dates["delivered"] + timedelta(days=1))
        shopify["return_reason"] = "Changed mind"
        return "refund_status"

    if cls == "duplicate_refund":
        razorpay["status"] = "refunded"
        shopify["order_status"] = "returned"
        shopify["return_date"] = _iso_date(dates["delivered"] + timedelta(days=1))
        shopify["return_reason"] = "Defective"
        ledger.append(dict(entry_id=f"TALLY-{order_id}-{entry_seq}", order_id=order_id,
                            entry_type="refund", amount=razorpay["amount"],
                            entry_date=_iso_date(dates["delivered"] + timedelta(days=2))))
        ledger.append(dict(entry_id=f"TALLY-{order_id}-{entry_seq}-dup", order_id=order_id,
                            entry_type="refund", amount=razorpay["amount"],
                            entry_date=_iso_date(dates["delivered"] + timedelta(days=4))))
        return "refund_status"

    if cls == "customer_order_mismatch":
        # The claim's cited record is swapped, by the caller, for the
        # fixed decoy order (a real record -- just the wrong one).
        return "customer_identity"

    raise ValueError(cls)


def _flagship():
    """CASE-VERIDICT-001, exactly as specified: cited source (Shiprocket)
    genuinely supports delivery; it does not support delivery WITHIN THE
    PROMISED WINDOW, because Shopify's promise and Shiprocket's actual
    date disagree by four days. A failed-attempt scan makes the delay
    a believable logistics story, not just a bare date flip."""
    order_id, shipment_id, payment_id = "ORDER-4821", "SHIP-4821", "PAY-4821"
    customer_id = "CUST-4821"
    order_date = date(2026, 8, 4)
    promised = date(2026, 8, 10)
    dispatched = date(2026, 8, 5)
    delivered = date(2026, 8, 14)

    scan_events = [
        {"timestamp": _iso_dt(dispatched, 9), "event": "PICKED_UP"},
        {"timestamp": _iso_dt(dispatched + timedelta(days=1), 15), "event": "IN_TRANSIT"},
        {"timestamp": _iso_dt(promised, 11), "event": "OUT_FOR_DELIVERY"},
        {"timestamp": _iso_dt(promised, 18), "event": "DELIVERY_ATTEMPT_FAILED"},
        {"timestamp": _iso_dt(delivered, 10), "event": "OUT_FOR_DELIVERY"},
        {"timestamp": _iso_dt(delivered, 16, 30), "event": "DELIVERED"},
    ]

    razorpay = dict(payment_id=payment_id, order_id=order_id, customer_id=customer_id,
                     amount=3499.0, status="captured", method="upi",
                     created_at=_iso_dt(order_date, 12))
    shopify = dict(order_id=order_id, customer_id=customer_id, sku="SKU-HEADPHONE-BT", qty=1,
                    order_status="fulfilled", promised_delivery_date=_iso_date(promised),
                    return_date=None, return_reason=None)
    shiprocket = dict(shipment_id=shipment_id, order_id=order_id, courier="Delhivery",
                       dispatch_date=_iso_date(dispatched), delivered_date=_iso_date(delivered),
                       status="delivered", scan_events=db.json_dump(scan_events))
    ledger = [dict(entry_id="TALLY-4821-1", order_id=order_id, entry_type="sale", amount=3499.0,
                    entry_date=_iso_date(order_date))]
    return dict(order_id=order_id, shipment_id=shipment_id, customer_id=customer_id,
                razorpay=razorpay, shopify=shopify, shiprocket=shiprocket, ledger=ledger,
                claim_type="delivery_window", dispute_id="VER-001")


def build_world():
    """Returns (disputes, razorpay_rows, shopify_rows, shiprocket_rows, ledger_rows)."""
    disputes, rp_rows, shop_rows, ship_rows, ledger_rows = [], [], [], [], []

    plan = CONTRADICTION_PLAN[:]
    random.shuffle(plan)
    # Reserve slot 0 for the flagship's own class so it's guaranteed present.
    plan = ["delivery_window"] + [c for c in plan if True][:11]
    # (11 remaining classes chosen from the shuffled 12 minus one delivery_window,
    #  since the flagship itself supplies one of the three delivery_window cases)
    remaining_pool = CONTRADICTION_PLAN[:]
    remaining_pool.remove("delivery_window")
    random.shuffle(remaining_pool)
    plan = ["FLAGSHIP"] + remaining_pool  # 1 flagship + 11 other contradictions = 12 total

    n_total = 60
    n_contra = len(plan)  # 12
    clean_needed = n_total - n_contra  # 48

    order_seq = 1000
    entry_seq = 1

    # ---- fixed decoy order: a real record belonging to a real, different
    # customer, that the customer_order_mismatch case can be pointed at.
    # It is never itself the subject of a dispute. ----
    decoy_razorpay, decoy_shopify, decoy_shiprocket, decoy_ledger, _ = _base_records(
        "ORDER-9999", "SHIP-9999", "PAY-9999", "TALLY-9999-1", "CUST-9999",
        "SKU-BOTTLE-1L", 599.0, date(2026, 7, 3))
    rp_rows.append(decoy_razorpay); shop_rows.append(decoy_shopify)
    ship_rows.append(decoy_shiprocket); ledger_rows.extend(decoy_ledger)

    # ---- flagship first ----
    fs = _flagship()
    disputes.append(dict(
        dispute_id=fs["dispute_id"], order_id=fs["order_id"], customer_id=fs["customer_id"],
        ground_truth_contradiction=1, contradiction_class="delivery_window", claim_type=fs["claim_type"],
        cited_customer_override=None,
    ))
    rp_rows.append(fs["razorpay"]); shop_rows.append(fs["shopify"])
    ship_rows.append(fs["shiprocket"]); ledger_rows.extend(fs["ledger"])

    # ---- remaining 11 contradictions ----
    for cls in remaining_pool:
        order_seq += 1
        order_id = f"ORDER-{order_seq}"
        shipment_id = f"SHIP-{order_seq}"
        payment_id = f"PAY-{order_seq}"
        entry_id = f"TALLY-{order_id}-1"
        entry_seq += 1
        customer_id = _new_customer(order_seq)
        sku = random.choice(SKUS)
        amount = round(random.uniform(499, 8999), 2)
        order_date = date(2026, 7, 1) + timedelta(days=random.randint(0, 45))

        razorpay, shopify, shiprocket, ledger, dates = _base_records(
            order_id, shipment_id, payment_id, entry_id, customer_id, sku, amount, order_date)

        other_customer_id, other_order_id = None, None
        if cls == "customer_order_mismatch":
            other_customer_id, other_order_id = "CUST-9999", "ORDER-9999"

        claim_type = _apply_contradiction(cls, razorpay, shopify, shiprocket, ledger, dates,
                                           order_id, entry_seq, other_customer_id, other_order_id)

        disputes.append(dict(
            dispute_id=f"VER-{order_seq}", order_id=order_id, customer_id=customer_id,
            ground_truth_contradiction=1, contradiction_class=cls, claim_type=claim_type,
            cited_customer_override=other_customer_id, cited_order_override=other_order_id,
        ))
        rp_rows.append(razorpay); shop_rows.append(shopify)
        ship_rows.append(shiprocket); ledger_rows.extend(ledger)

    # ---- 48 clean disputes, mix of hard + soft claim types ----
    hard_claim_types = ["delivery_window", "amount", "payment_status", "delivery_status", "order_status"]
    soft_claim_types = ["service_quality", "fulfillment_quality", "customer_request_fulfilled"]
    # No table in any system records *why* a delivery attempt failed, or
    # what a customer intended. These are not missing data VERIDICT could
    # look harder for -- they are structurally unknowable from records,
    # by design, regardless of how complete the data is.
    unknowable_claim_type = "delivery_refusal_intent"

    for k in range(clean_needed):
        order_seq += 1
        order_id = f"ORDER-{order_seq}"
        shipment_id = f"SHIP-{order_seq}"
        payment_id = f"PAY-{order_seq}"
        entry_id = f"TALLY-{order_id}-1"
        customer_id = _new_customer(order_seq)
        sku = random.choice(SKUS)
        amount = round(random.uniform(499, 8999), 2)
        order_date = date(2026, 7, 1) + timedelta(days=random.randint(0, 45))

        razorpay, shopify, shiprocket, ledger, dates = _base_records(
            order_id, shipment_id, payment_id, entry_id, customer_id, sku, amount, order_date)

        # 2 of the clean cases: cite a record field that doesn't exist ->
        # exercises HUMAN_CONTEXT via a broken citation (a data-quality gap).
        dangling = k in (3, 27)
        # 4 of the clean cases: a failed delivery attempt with no recorded
        # reason -> exercises HUMAN_CONTEXT via genuine, structural
        # unknowability (an epistemic gap, not a data-quality gap).
        unknowable = k in (7, 15, 33, 41)

        if unknowable:
            claim_type = unknowable_claim_type
            failed_at = dates["delivered"] - timedelta(days=1)
            events = db.json_load(shiprocket["scan_events"])
            events.insert(-1, {"timestamp": _iso_dt(failed_at, 13), "event": "DELIVERY_ATTEMPT_FAILED"})
            shiprocket["scan_events"] = db.json_dump(events)
        elif dangling:
            claim_type = "refund_status"
        elif k % 4 == 0:
            claim_type = random.choice(soft_claim_types)
        else:
            claim_type = random.choice(hard_claim_types)

        disputes.append(dict(
            dispute_id=f"VER-{order_seq}", order_id=order_id, customer_id=customer_id,
            ground_truth_contradiction=0, contradiction_class=None, claim_type=claim_type,
            cited_customer_override=None, dangling_reference=dangling, unknowable=unknowable,
        ))
        rp_rows.append(razorpay); shop_rows.append(shopify)
        ship_rows.append(shiprocket); ledger_rows.extend(ledger)

    assert len(disputes) == 60
    assert sum(d["ground_truth_contradiction"] for d in disputes) == 12
    return disputes, rp_rows, shop_rows, ship_rows, ledger_rows


def seed_database() -> None:
    db.wipe_all_tables()
    disputes, rp_rows, shop_rows, ship_rows, ledger_rows = build_world()

    with db.get_conn() as conn:
        for r in rp_rows:
            conn.execute(
                "INSERT INTO razorpay_payments (payment_id, order_id, customer_id, amount, status, method, created_at) "
                "VALUES (:payment_id,:order_id,:customer_id,:amount,:status,:method,:created_at)", r)
        for r in shop_rows:
            conn.execute(
                "INSERT INTO shopify_orders (order_id, customer_id, sku, qty, order_status, promised_delivery_date, return_date, return_reason) "
                "VALUES (:order_id,:customer_id,:sku,:qty,:order_status,:promised_delivery_date,:return_date,:return_reason)", r)
        for r in ship_rows:
            conn.execute(
                "INSERT INTO shiprocket_shipments (shipment_id, order_id, courier, dispatch_date, delivered_date, status, scan_events) "
                "VALUES (:shipment_id,:order_id,:courier,:dispatch_date,:delivered_date,:status,:scan_events)", r)
        for r in ledger_rows:
            conn.execute(
                "INSERT INTO tally_ledger (entry_id, order_id, entry_type, amount, entry_date) "
                "VALUES (:entry_id,:order_id,:entry_type,:amount,:entry_date)", r)

    # Now generate evidence packets (claims) via the naive upstream agent,
    # using the rows already in memory (no nested DB access / lock).
    from . import evidence_generator
    rp_by_order = {r["order_id"]: r for r in rp_rows}
    shop_by_order = {r["order_id"]: r for r in shop_rows}
    ship_by_order = {r["order_id"]: r for r in ship_rows}
    ledger_by_order: dict[str, list] = {}
    for r in ledger_rows:
        ledger_by_order.setdefault(r["order_id"], []).append(r)

    now = datetime.now(timezone.utc).isoformat()
    with db.get_conn() as conn:
        for d in disputes:
            packet = evidence_generator.generate_packet_from_records(
                d, rp_by_order[d["order_id"]], shop_by_order[d["order_id"]],
                ship_by_order[d["order_id"]], ledger_by_order.get(d["order_id"], []))
            needs_context = int(bool(d.get("dangling_reference") or d.get("unknowable")))
            conn.execute(
                "INSERT INTO disputes (dispute_id, order_id, customer_id, narrative, status, created_at, updated_at, "
                "ground_truth_contradiction, contradiction_class, ground_truth_needs_context) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (d["dispute_id"], d["order_id"], d["customer_id"], packet["narrative"], "PENDING",
                 now, now, d["ground_truth_contradiction"], d["contradiction_class"], needs_context))
            for c in packet["claims"]:
                conn.execute(
                    "INSERT INTO claims (claim_id, dispute_id, claim_type, asserted_value, cited_source, cited_record, confidence) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (c["claim_id"], d["dispute_id"], c["claim_type"], c["asserted_value"],
                     c["cited_source"], c["cited_record"], c["confidence"]))


if __name__ == "__main__":
    db.init_schema()
    seed_database()
    print("Seeded 60 disputes (12 contradictory, 48 clean).")
