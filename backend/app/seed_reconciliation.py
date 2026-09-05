import json
import uuid
from datetime import datetime, timedelta
import random
from . import db

def generate_reconciliation_batch(conn, base_date: datetime):
    # We need 60 records exactly:
    # 40 EXACT MATCH
    # 6 MATCHED_AFTER_NORMALIZATION
    # 4 AMOUNT_MISMATCH
    # 3 MISSING_RECORD
    # 3 DUPLICATE
    # 2 AMBIGUOUS
    # 2 DATE_MISMATCH
    
    # We will insert into razorpay_payments and tally_ledger
    # and reconciliation_ground_truth
    
    scenarios = (
        ["EXACT"] * 40 +
        ["NORMALIZED"] * 6 +
        ["AMOUNT_MISMATCH"] * 4 +
        ["MISSING"] * 3 +
        ["DUPLICATE"] * 3 +
        ["AMBIGUOUS"] * 2 +
        ["DATE_MISMATCH"] * 2
    )
    
    for i, scenario in enumerate(scenarios):
        pay_id = f"pay_REC{i:04d}"
        order_id = f"ORD-REC-{i:04d}"
        cust_id = f"CUST-REC-{i:03d}"
        
        # Base amounts
        base_amt = round(random.uniform(100.0, 5000.0), 2)
        base_dt = base_date + timedelta(days=i % 10, hours=random.randint(0, 23))
        
        # Razorpay Payment (Source)
        rp = {
            "payment_id": pay_id,
            "order_id": order_id,
            "customer_id": cust_id,
            "amount": base_amt,
            "status": "captured",
            "method": "upi",
            "created_at": base_dt.isoformat() + "Z"
        }
        
        conn.execute(
            "INSERT INTO razorpay_payments (payment_id, order_id, customer_id, amount, status, method, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rp["payment_id"], rp["order_id"], rp["customer_id"], rp["amount"], rp["status"], rp["method"], rp["created_at"])
        )
        
        # Tally Ledger (Target) variables
        target_records = []
        expected_status = "MATCHED"
        true_target_id = None
        
        if scenario == "EXACT":
            t_id = f"LED-REC-{i:04d}"
            target_records.append({
                "entry_id": t_id,
                "order_id": order_id,
                "entry_type": "sale",
                "amount": base_amt,
                "entry_date": base_dt.isoformat() + "Z"
            })
            true_target_id = t_id
            expected_status = "MATCHED"
            
        elif scenario == "NORMALIZED":
            t_id = f"LED-REC-{i:04d}"
            # Mangled order_id (e.g. lowercase, spaces, or completely missing prefix)
            mangled_id = f"ord rec {i:04d}" if i % 2 == 0 else f"{i:04d}"
            target_records.append({
                "entry_id": t_id,
                "order_id": mangled_id,
                "entry_type": "sale",
                "amount": base_amt,
                "entry_date": base_dt.isoformat() + "Z"
            })
            true_target_id = t_id
            expected_status = "MATCHED_AFTER_NORMALIZATION"
            
        elif scenario == "AMOUNT_MISMATCH":
            t_id = f"LED-REC-{i:04d}"
            target_records.append({
                "entry_id": t_id,
                "order_id": order_id,
                "entry_type": "sale",
                "amount": base_amt + (10.0 if i % 2 == 0 else -50.0), # slight mismatch
                "entry_date": base_dt.isoformat() + "Z"
            })
            true_target_id = t_id
            expected_status = "AMOUNT_MISMATCH"
            
        elif scenario == "MISSING":
            true_target_id = None
            expected_status = "MISSING_RECORD"
            
        elif scenario == "DUPLICATE":
            t_id1 = f"LED-REC-{i:04d}-A"
            t_id2 = f"LED-REC-{i:04d}-B"
            target_records.append({
                "entry_id": t_id1,
                "order_id": order_id,
                "entry_type": "sale",
                "amount": base_amt,
                "entry_date": base_dt.isoformat() + "Z"
            })
            target_records.append({
                "entry_id": t_id2,
                "order_id": order_id,
                "entry_type": "sale",
                "amount": base_amt,
                "entry_date": base_dt.isoformat() + "Z"
            })
            true_target_id = None # Cannot uniquely resolve
            expected_status = "DUPLICATE"
            
        elif scenario == "AMBIGUOUS":
            t_id1 = f"LED-REC-{i:04d}-A"
            t_id2 = f"LED-REC-{i:04d}-B"
            # Missing order IDs entirely, but identical amounts. Needs human or AI context.
            # We'll make one closer in time, but the engine won't be certain.
            target_records.append({
                "entry_id": t_id1,
                "order_id": "UNKNOWN",
                "entry_type": "sale",
                "amount": base_amt,
                "entry_date": base_dt.isoformat() + "Z"
            })
            target_records.append({
                "entry_id": t_id2,
                "order_id": "UNKNOWN",
                "entry_type": "sale",
                "amount": base_amt,
                "entry_date": (base_dt + timedelta(hours=1)).isoformat() + "Z"
            })
            true_target_id = t_id1 # Ground truth says A is correct
            expected_status = "AMBIGUOUS"
            
        elif scenario == "DATE_MISMATCH":
            t_id = f"LED-REC-{i:04d}"
            target_records.append({
                "entry_id": t_id,
                "order_id": order_id,
                "entry_type": "sale",
                "amount": base_amt,
                "entry_date": (base_dt + timedelta(days=6)).isoformat() + "Z" # 6 days off
            })
            true_target_id = t_id
            expected_status = "DATE_MISMATCH"
            
        for t in target_records:
            conn.execute(
                "INSERT INTO tally_ledger (entry_id, order_id, entry_type, amount, entry_date) VALUES (?, ?, ?, ?, ?)",
                (t["entry_id"], t["order_id"], t["entry_type"], t["amount"], t["entry_date"])
            )
            
        # Insert Ground Truth
        conn.execute(
            "INSERT INTO reconciliation_ground_truth (source_record_id, true_target_record_id, expected_status, scenario_type) VALUES (?, ?, ?, ?)",
            (pay_id, true_target_id, expected_status, scenario)
        )
