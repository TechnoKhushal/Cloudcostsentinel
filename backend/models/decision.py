from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

DeciderAction = Literal["monitor", "notify_owner", "request_approval"]


class DeciderQuestionSpec(BaseModel):
    type: Literal["choice"] = "choice"
    instructions: str = (
        "Given the spend anomaly, budget pressure, persistence, service criticality "
        "and known ownership, should the agent monitor, notify_owner, or request_approval for remediation?"
    )
    criteria: Dict[str, str] = Field(
        default_factory=lambda: {
            "monitor": "Observe and re-evaluate without alerting. Appropriate for small fluctuations, low budget impact, or non-critical environments.",
            "notify_owner": "Notify the verified resource owner directly. Appropriate for known service owners with moderate budget pressure or early-stage anomalies.",
            "request_approval": "Escalate to human cloud platform engineer for remediation sign-off. Appropriate for high spend spikes, runaway budget burn, unassigned owners, or critical production environments.",
        }
    )


class DeciderNormalizedState(BaseModel):
    service: str
    environment: str
    criticality: str
    known_owner: str
    current_daily_spend: float
    baseline_daily_spend: float
    spend_delta_amount: float
    spend_delta_percentage: float
    persistence_days: int
    monthly_budget: float
    budget_burn_percentage: float
    forecast_month_end: float
    uncertainty_flag: bool

    def to_compact_str(self) -> str:
        owner_status = f"verified ({self.known_owner})" if self.known_owner and self.known_owner != "unknown" else "unassigned / unknown"
        return (
            f"Service: {self.service} | Environment: {self.environment} (Criticality: {self.criticality.upper()})\n"
            f"Spend Delta: +${self.spend_delta_amount:,.2f}/day (+{self.spend_delta_percentage:.1f}%) above baseline ${self.baseline_daily_spend:,.2f}\n"
            f"Current Daily Spend: ${self.current_daily_spend:,.2f} | Persistence: {self.persistence_days} consecutive days\n"
            f"Budget Utilization: {self.budget_burn_percentage:.1f}% consumed of ${self.monthly_budget:,.2f} monthly budget | Forecast: ${self.forecast_month_end:,.2f}\n"
            f"Owner: {owner_status} | Measurement Uncertainty: {'HIGH' if self.uncertainty_flag else 'LOW'}"
        )


class DeciderResponseTrace(BaseModel):
    decision_id: str
    timestamp: str
    action: DeciderAction  # effective action (may differ from raw_model_action when safety fallback applied)
    confidence: float       # effective confidence
    probabilities: Dict[str, float]
    latency_ms: float
    model_id: str
    provider: str  # "strands-decider-2b-http" | "strands-decider-2b-inprocess" | "mock-simulated"
    is_fallback: bool = False
    fallback_reason: Optional[str] = None
    # Raw model output — preserved separately so the audit log never conflates model output with policy override
    raw_model_action: Optional[DeciderAction] = None    # what the model actually chose
    raw_model_confidence: Optional[float] = None        # what the model actually returned
    question: DeciderQuestionSpec
    normalized_state: str
    executed_action: str
    executed_details: Dict[str, Any] = Field(default_factory=dict)
