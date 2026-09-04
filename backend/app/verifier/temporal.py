"""
Explicit temporal business rules. Per spec: do not blindly flag every
timestamp anomaly -- name the specific ordering invariant being checked
and why it matters financially.
"""
from __future__ import annotations

from datetime import date, datetime


def parse_date(s: str) -> date:
    return datetime.fromisoformat(s).date() if "T" in s else date.fromisoformat(s)


def days_between(later: str, earlier: str) -> int:
    return (parse_date(later) - parse_date(earlier)).days


RULES = {
    "promised_before_delivered": "A promised delivery date must not fall after the actual delivery date "
                                  "for the claim 'delivered within window' to hold.",
    "delivered_before_returned": "A return cannot be initiated before the courier's own record shows the "
                                  "item was delivered.",
}


def check_delivery_window(promised_delivery_date: str, delivered_date: str) -> dict:
    """Rule: delivered_date must be <= promised_delivery_date for an
    'on time' claim to hold."""
    on_time = parse_date(delivered_date) <= parse_date(promised_delivery_date)
    late_by = max(0, days_between(delivered_date, promised_delivery_date))
    return {"holds": on_time, "late_by_days": late_by, "rule": RULES["promised_before_delivered"]}


def check_return_chronology(return_date: str | None, delivered_date: str | None) -> dict:
    """Rule: a return event cannot precede the delivery event it's
    supposedly a return OF."""
    if not return_date or not delivered_date:
        return {"violated": False, "rule": RULES["delivered_before_returned"]}
    violated = parse_date(return_date) < parse_date(delivered_date)
    gap_days = days_between(delivered_date, return_date) if violated else 0
    return {"violated": violated, "gap_days": gap_days, "rule": RULES["delivered_before_returned"]}
