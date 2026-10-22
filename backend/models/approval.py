from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class ApprovalItem(BaseModel):
    id: str
    decision_id: str
    anomaly_id: str
    service: str
    environment: str
    suggested_action: str
    estimated_monthly_savings: float
    status: Literal["pending", "approved", "rejected"] = "pending"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    is_simulated: bool = True  # Always explicit that demo approval does NOT mutate live AWS resources
