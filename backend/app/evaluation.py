"""
Evaluation. Reads disputes.ground_truth_contradiction and
ground_truth_needs_context -- columns the verification pipeline
(app/verifier/pipeline.py) never queries -- and compares them against
the status the pipeline actually produced. Nothing here is hardcoded;
every number is recomputed from the current database state, so it
changes honestly after a chaos injection or a reset.
"""
from __future__ import annotations

import time

from . import db


def run_evaluation() -> dict:
    t0 = time.perf_counter()
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT dispute_id, status, ground_truth_contradiction, ground_truth_needs_context, "
            "contradiction_class FROM disputes").fetchall()
    elapsed = time.perf_counter() - t0

    rows = [db.row_to_dict(r) for r in rows]
    total = len(rows)

    tp = fp = tn = fn = 0
    missed = []
    for r in rows:
        gt_positive = bool(r["ground_truth_contradiction"])
        predicted_positive = r["status"] == "BLOCKED"
        if gt_positive and predicted_positive:
            tp += 1
        elif gt_positive and not predicted_positive:
            fn += 1
            missed.append({"dispute_id": r["dispute_id"], "expected": "BLOCKED", "actual": r["status"],
                            "contradiction_class": r["contradiction_class"],
                            "reason": "A genuine contradiction was not blocked."})
        elif not gt_positive and predicted_positive:
            fp += 1
            missed.append({"dispute_id": r["dispute_id"], "expected": "not BLOCKED", "actual": r["status"],
                            "contradiction_class": None,
                            "reason": "A clean dispute was incorrectly blocked."})
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0

    context_rows = [r for r in rows if r["ground_truth_needs_context"]]
    context_correct = sum(1 for r in context_rows if r["status"] == "HUMAN_CONTEXT")
    context_routing_accuracy = (context_correct / len(context_rows)) if context_rows else None

    # False automatic-clear rate: of everything that should NOT have been
    # cleared automatically (genuine contradictions OR genuinely ambiguous
    # cases), how much slipped through as CLEARED anyway?
    should_not_clear = [r for r in rows if r["ground_truth_contradiction"] or r["ground_truth_needs_context"]]
    wrongly_cleared = [r for r in should_not_clear if r["status"] == "CLEARED"]
    false_auto_clear_rate = (len(wrongly_cleared) / len(should_not_clear)) if should_not_clear else 0.0

    status_counts = {"CLEARED": 0, "BLOCKED": 0, "HUMAN_CONTEXT": 0, "PENDING": 0}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    # ==========================================
    # RECONCILIATION EVALUATION
    # ==========================================
    with db.get_conn() as conn:
        latest_batch = conn.execute("SELECT * FROM reconciliation_batches ORDER BY created_at DESC LIMIT 1").fetchone()
        
        recon_metrics = None
        if latest_batch:
            latest_batch = db.row_to_dict(latest_batch)
            b_id = latest_batch["batch_id"]
            
            # Fetch ground truth and actual predictions
            rec_rows = conn.execute("SELECT source_record_id, match_status, match_type FROM reconciliation_records WHERE batch_id = ?", (b_id,)).fetchall()
            gt_rows = conn.execute("SELECT source_record_id, true_target_record_id, expected_status, scenario_type FROM reconciliation_ground_truth").fetchall()
            
            gt_map = {r["source_record_id"]: db.row_to_dict(r) for r in gt_rows}
            rec_map = {r["source_record_id"]: db.row_to_dict(r) for r in rec_rows}
            
            rtp = rfp = rtn = rfn = 0
            
            for s_id, gt in gt_map.items():
                pred = rec_map.get(s_id)
                if not pred:
                    continue
                
                # We define "Positive" as an EXCEPTION (Mismatch, Missing, Duplicate, etc.)
                # and "Negative" as RESOLVED (Matched, Matched after normalization)
                gt_is_exception = gt["expected_status"] not in ("MATCHED", "MATCHED_AFTER_NORMALIZATION")
                pred_is_exception = pred["match_status"] not in ("MATCHED", "MATCHED_AFTER_NORMALIZATION")
                
                if gt_is_exception and pred_is_exception:
                    rtp += 1
                elif gt_is_exception and not pred_is_exception:
                    rfn += 1
                elif not gt_is_exception and pred_is_exception:
                    rfp += 1
                else:
                    rtn += 1
                    
            r_precision = rtp / (rtp + rfp) if (rtp + rfp) else 0.0
            r_recall = rtp / (rtp + rfn) if (rtp + rfn) else 0.0
            r_f1 = (2 * r_precision * r_recall / (r_precision + r_recall)) if (r_precision + r_recall) else 0.0
            
            recon_metrics = {
                "batch_id": b_id,
                "total_records": latest_batch["total_records"],
                "resolved_count": latest_batch["resolved_count"],
                "exact_match_count": latest_batch["exact_match_count"],
                "ambiguous_count": latest_batch["ambiguous_count"],
                "mismatch_count": latest_batch["mismatch_count"],
                "missing_count": latest_batch["missing_count"],
                "duplicate_count": latest_batch["duplicate_count"],
                "unresolved_count": latest_batch["unresolved_count"],
                "resolution_rate": latest_batch["resolution_rate"],
                "exact_match_rate": latest_batch["exact_match_rate"],
                "processing_time_ms": latest_batch["processing_time_ms"],
                "throughput": round(latest_batch["total_records"] / (latest_batch["processing_time_ms"] / 1000.0), 1) if latest_batch["processing_time_ms"] > 0 else 0,
                "precision": round(r_precision, 4),
                "recall": round(r_recall, 4),
                "f1": round(r_f1, 4),
                "false_positives": rfp,
                "false_negatives": rfn
            }

    return {
        "dataset": {"total": total, "contradictory": sum(1 for r in rows if r["ground_truth_contradiction"]),
                     "clean": sum(1 for r in rows if not r["ground_truth_contradiction"])},
        "confusion_matrix": {"true_positive": tp, "true_negative": tn, "false_positive": fp, "false_negative": fn},
        "metrics": {
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "automatic_decision_accuracy": round(accuracy, 4),
            "false_positive_rate": round(false_positive_rate, 4),
            "false_positive_count": fp, "false_negative_count": fn,
            "human_context_routing_accuracy": round(context_routing_accuracy, 4) if context_routing_accuracy is not None else None,
            "false_automatic_clear_rate": round(false_auto_clear_rate, 4),
        },
        "status_counts": status_counts,
        "missed_cases": missed,
        "performance": {"seconds": round(elapsed, 4),
                         "disputes_per_second": round(total / elapsed, 1) if elapsed > 0 else None},
        "reconciliation": recon_metrics
    }
