from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChaosInjectRequest(BaseModel):
    contradiction_type: str = Field(..., description="One of: delivery_window, amount_mismatch, payment_status")


class HumanAttestationRequest(BaseModel):
    dispute_id: str
    claim_id: str
    question: str
    answer: str
    note: Optional[str] = None
    submitted_by: Optional[str] = "demo_user"
