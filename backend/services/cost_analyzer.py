from __future__ import annotations

import calendar
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from ..models.cost import CostAnomaly, CostDataPoint, SpendMetrics


def calculate_spend_metrics(
    datapoints: List[float],
    monthly_budget: float,
    current_day_of_month: Optional[int] = None,
    days_in_month: Optional[int] = None,
    anomaly_threshold_pct: float = 20.0,
    baseline_window_days: int = 7,
) -> SpendMetrics:
    """Deterministic formula-based calculation of spend anomaly metrics.

    Formulas:
    1. Baseline Spend: Mean of stable baseline window (prior to recent spike).
    2. Delta Amount: current_spend - baseline
    3. Delta Percentage: (delta_amount / baseline) * 100
    4. Persistence: Trailing consecutive days exceeding baseline * (1 + threshold/100).
    5. Forecast Month-End: MTD + (days_remaining * current_spend)
    6. Budget Burn: (forecast_month_end / monthly_budget) * 100
    7. Uncertainty Flag: True if baseline sample size < 5 or stable variance > 0.4.
    """
    now = datetime.now(timezone.utc)
    if current_day_of_month is None:
        current_day_of_month = now.day
    if days_in_month is None:
        days_in_month = calendar.monthrange(now.year, now.month)[1]
    if not datapoints:
        return SpendMetrics(
            current_spend=0.0,
            baseline_spend=0.0,
            delta_amount=0.0,
            delta_percentage=0.0,
            persistence_days=0,
            monthly_budget=monthly_budget,
            month_to_date_spend=0.0,
            budget_burn_percentage=0.0,
            forecast_month_end=0.0,
            uncertainty_flag=True,
            anomaly_detected=False,
        )

    current_spend = datapoints[-1]

    # Use pre-anomaly window for baseline if series is long enough, else all prior points
    if len(datapoints) > 4:
        # Candidate baseline window: prior stable points
        window_size = min(baseline_window_days, len(datapoints) - 1)
        stable_window = datapoints[:window_size]
    else:
        stable_window = datapoints[:-1] if len(datapoints) > 1 else [current_spend]

    if not stable_window:
        baseline_spend = current_spend
        uncertainty_flag = True
    else:
        baseline_spend = sum(stable_window) / len(stable_window)
        if len(stable_window) >= 3 and baseline_spend > 0:
            variance = sum((x - baseline_spend) ** 2 for x in stable_window) / len(stable_window)
            std_dev = math.sqrt(variance)
            cv = std_dev / baseline_spend
            uncertainty_flag = (len(stable_window) < 5) or (cv > 0.4)
        else:
            uncertainty_flag = True

    # Delta
    delta_amount = current_spend - baseline_spend
    if baseline_spend > 0.001:
        delta_percentage = (delta_amount / baseline_spend) * 100.0
    else:
        delta_percentage = 100.0 if delta_amount > 0 else 0.0

    # Persistence: trailing consecutive days exceeding baseline threshold
    threshold_val = baseline_spend * (1.0 + (anomaly_threshold_pct / 100.0))
    persistence = 0
    for val in reversed(datapoints):
        if val >= threshold_val:
            persistence += 1
        else:
            break

    # Month to date and forecast
    days_passed = max(1, min(current_day_of_month, days_in_month))
    days_remaining = max(0, days_in_month - days_passed)
    mtd_spend = sum(datapoints[-days_passed:]) if len(datapoints) >= days_passed else sum(datapoints)
    forecast_month_end = mtd_spend + (days_remaining * current_spend)
    budget_burn_pct = (forecast_month_end / monthly_budget) * 100.0 if monthly_budget > 0 else 100.0
    anomaly_detected = (delta_percentage >= anomaly_threshold_pct) and (current_spend > 50.0)

    return SpendMetrics(
        current_spend=round(current_spend, 2),
        baseline_spend=round(baseline_spend, 2),
        delta_amount=round(delta_amount, 2),
        delta_percentage=round(delta_percentage, 1),
        persistence_days=persistence,
        monthly_budget=round(monthly_budget, 2),
        month_to_date_spend=round(mtd_spend, 2),
        budget_burn_percentage=round(budget_burn_pct, 1),
        forecast_month_end=round(forecast_month_end, 2),
        uncertainty_flag=uncertainty_flag,
        anomaly_detected=anomaly_detected,
    )


class CostScenarioRegistry:
    """Deterministic synthetic scenarios for honest, reproducible testing and demos."""

    @staticmethod
    def get_all_scenarios() -> List[Dict[str, str]]:
        return [
            {
                "id": "compute_spike",
                "name": "Production EC2 AutoScaling Runaway",
                "description": "Sudden 315% compute spike across unreserved c5.4xlarge instances; runaway batch worker queue with unassigned ownership.",
                "expected_response": "request_approval",
                "service": "Amazon EC2",
                "environment": "production",
            },
            {
                "id": "database_drift",
                "name": "RDS Aurora Multi-AZ IOPS Drift",
                "description": "Sustained 42% provisioned IOPS spend increase over 3 days; verified database team ownership and moderate budget headroom.",
                "expected_response": "notify_owner",
                "service": "Amazon Aurora RDS",
                "environment": "production",
            },
            {
                "id": "batch_surge",
                "name": "Staging EMR Cluster Spot Interruption",
                "description": "Temporary 18% bump in staging EMR spend during nightly test run; low budget impact in non-critical tier.",
                "expected_response": "monitor",
                "service": "Amazon EMR",
                "environment": "staging",
            },
            {
                "id": "stable_baseline",
                "name": "Steady-State Workload",
                "description": "Normal -2% daily variance within healthy production baseline; under monthly budget limits.",
                "expected_response": "monitor",
                "service": "Amazon ECS",
                "environment": "production",
            },
            {
                "id": "low_confidence_drift",
                "name": "Sparse Telemetry & High Variance Drift",
                "description": "Ambiguous 28% spend fluctuation with sparse baseline (2 days) and high variance. Demonstrates Decider low-confidence conservative fallback.",
                "expected_response": "request_approval (fallback)",
                "service": "Amazon S3 Glacier",
                "environment": "development",
            },
        ]

    @staticmethod
    def generate_scenario_anomaly(scenario_id: str) -> CostAnomaly:
        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")

        if scenario_id == "compute_spike":
            # 10 days of stable baseline ~ $320/day, followed by 3 days of spike
            base_curve = [310.0, 325.0, 318.0, 322.0, 330.0, 315.0, 320.0, 324.0, 319.0, 325.0, 950.0, 1280.0, 1340.0]
            budget = 12000.0
            metrics = calculate_spend_metrics(base_curve, monthly_budget=budget, current_day_of_month=14, anomaly_threshold_pct=25.0, baseline_window_days=10)
            metrics.uncertainty_flag = False
            service = "Amazon EC2"
            environment = "production"
            criticality = "critical"
            owner = "unknown"
            name = "Production EC2 AutoScaling Runaway"

        elif scenario_id == "database_drift":
            # 10 days of stable baseline ~ $450/day, followed by 3 days of drift (+42%)
            base_curve = [440.0, 452.0, 448.0, 455.0, 450.0, 460.0, 458.0, 462.0, 455.0, 460.0, 580.0, 620.0, 640.0]
            budget = 18000.0
            metrics = calculate_spend_metrics(base_curve, monthly_budget=budget, current_day_of_month=13, anomaly_threshold_pct=20.0, baseline_window_days=10)
            metrics.uncertainty_flag = False
            service = "Amazon Aurora RDS"
            environment = "production"
            criticality = "high"
            owner = "db-platform@company.internal"
            name = "RDS Aurora Multi-AZ IOPS Drift"

        elif scenario_id == "batch_surge":
            # Stable baseline ~ $180/day, minor bump to $212.0 (+17.7%)
            base_curve = [175.0, 182.0, 178.0, 180.0, 185.0, 179.0, 181.0, 184.0, 180.0, 183.0, 212.0]
            budget = 8000.0
            metrics = calculate_spend_metrics(base_curve, monthly_budget=budget, current_day_of_month=12, anomaly_threshold_pct=20.0, baseline_window_days=10)
            metrics.uncertainty_flag = False
            service = "Amazon EMR"
            environment = "staging"
            criticality = "low"
            owner = "data-eng@company.internal"
            name = "Staging EMR Cluster Spot Interruption"

        elif scenario_id == "stable_baseline":
            # Baseline ~ $500/day, today is $492 (-1.6%)
            base_curve = [502.0, 498.0, 505.0, 501.0, 495.0, 500.0, 504.0, 499.0, 502.0, 497.0, 492.0]
            budget = 20000.0
            metrics = calculate_spend_metrics(base_curve, monthly_budget=budget, current_day_of_month=11, anomaly_threshold_pct=20.0, baseline_window_days=10)
            metrics.uncertainty_flag = False
            service = "Amazon ECS"
            environment = "production"
            criticality = "medium"
            owner = "app-sre@company.internal"
            name = "Steady-State Workload"

        else:  # "low_confidence_drift"
            # Sparse data (only 3 points: 150, 450, 210) with extreme relative variance
            base_curve = [150.0, 450.0, 210.0]
            budget = 5000.0
            metrics = calculate_spend_metrics(base_curve, monthly_budget=budget, current_day_of_month=3, anomaly_threshold_pct=15.0)
            metrics.uncertainty_flag = True
            service = "Amazon S3 Glacier"
            environment = "development"
            criticality = "medium"
            owner = "unknown"
            name = "Sparse Telemetry & High Variance Drift"

        # Build full date series
        time_series: List[CostDataPoint] = []
        num_points = len(base_curve)
        for i, val in enumerate(base_curve):
            point_date = (now - timedelta(days=num_points - 1 - i)).strftime("%Y-%m-%d")
            is_pt_anom = val >= (metrics.baseline_spend * 1.25) and i >= (num_points - metrics.persistence_days)
            time_series.append(
                CostDataPoint(
                    date=point_date,
                    spend=round(val, 2),
                    baseline=round(metrics.baseline_spend, 2),
                    is_anomaly=is_pt_anom,
                    service=service,
                    environment=environment,
                )
            )

        anomaly_id = f"anom-{scenario_id}-{today_str}"

        return CostAnomaly(
            anomaly_id=anomaly_id,
            scenario_id=scenario_id,
            scenario_name=name,
            service=service,
            environment=environment,
            owner=owner,
            criticality=criticality,
            metrics=metrics,
            time_series=time_series,
            currency="USD",
            detected_at=now.isoformat() + "Z",
            is_simulated=True,
        )
