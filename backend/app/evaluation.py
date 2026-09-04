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
    }
