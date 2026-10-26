from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class InvestigationReport(BaseModel):
    report_id: str
    anomaly_id: str
    decision_id: str
    title: str
    executive_summary: str
    observed_facts: List[str]
    decider_action_audit: str
    likely_investigation_areas: List[str]
    safe_recommendations: List[str]
    assumptions_and_limitations: List[str]
    follow_up_checklist: List[str]
    provider: str
    model_id: str
    is_simulated: bool = False
    generated_at: str


# Compatibility alias for persisted SQLite JSON and clients compiled against
# the previous provider-specific name. New code should use InvestigationReport.
BedrockReport = InvestigationReport
