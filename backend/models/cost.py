from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class CostDataPoint(BaseModel):
    date: str
    spend: float
    baseline: float
    is_anomaly: bool = False
    service: str
    environment: str


class SpendMetrics(BaseModel):
    current_spend: float
    baseline_spend: float
    delta_amount: float
    delta_percentage: float
    persistence_days: int
    monthly_budget: float
    month_to_date_spend: float
    budget_burn_percentage: float
    forecast_month_end: float
    uncertainty_flag: bool = False
    anomaly_detected: bool = False


class CostAnomaly(BaseModel):
    anomaly_id: str
    scenario_id: str
    scenario_name: str
    service: str
    environment: str  # e.g., "production", "staging", "development"
    owner: str  # e.g., "platform-eng@company.internal", "unknown"
    criticality: Literal["low", "medium", "high", "critical"]
    metrics: SpendMetrics
    time_series: List[CostDataPoint]
    currency: str = "USD"
    detected_at: str
    is_simulated: bool = True
