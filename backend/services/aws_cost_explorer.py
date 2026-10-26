from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from botocore.config import Config

from ..config import settings
from ..models.cost import CostAnomaly, CostDataPoint, SpendMetrics
from .cost_analyzer import calculate_spend_metrics

logger = logging.getLogger("cloudcost_sentinel.cost_explorer")


class AWSCostExplorerService:
    """Read-only client for AWS Cost Explorer.

    Safety:
    - Strictly read-only calls (ce:GetCostAndUsage).
    - Disabled by default (AWS_COST_EXPLORER_ENABLED=false).
    - Safe error handling for missing credentials, AccessDeniedException, throttling.
    - Never modifies AWS resources.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        region_name: Optional[str] = None,
    ):
        self.enabled = enabled if enabled is not None else settings.AWS_COST_EXPLORER_ENABLED
        self.region_name = region_name or settings.AWS_REGION

    def get_status(self) -> Dict[str, Any]:
        """Returns non-secret readiness and status information."""
        if not self.enabled:
            return {
                "enabled": False,
                "status": "disabled_by_configuration",
                "message": "AWS Cost Explorer is disabled by default. Set AWS_COST_EXPLORER_ENABLED=true to enable.",
                "region": self.region_name,
            }
        return {
            "enabled": True,
            "status": "configured_unverified",
            "message": "Cost Explorer credentials and read permissions are verified only by an actual cost query.",
            "region": self.region_name,
        }

    def fetch_recent_costs(
        self, days: int = 14, monthly_budget: float = 10000.0
    ) -> Tuple[Optional[CostAnomaly], Optional[str]]:
        """Fetch cost telemetry from AWS Cost Explorer with read-only permissions."""
        if not self.enabled:
            return None, "AWS Cost Explorer is disabled in configuration."

        try:
            client = boto3.client(
                "ce",
                region_name=self.region_name,
                config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"}),
            )
            now_utc = datetime.now(timezone.utc)
            # TimePeriod.End is exclusive in Cost Explorer API.
            # Daily billing metrics typically lag by 24-48 hours.
            end_date = now_utc.date()
            start_date = end_date - timedelta(days=days)

            results_by_time: List[Dict[str, Any]] = []
            next_page_token: Optional[str] = None
            pagination_cap_hit = False

            # Bounded pagination loop (max 5 pages for safety)
            for _ in range(5):
                params: Dict[str, Any] = {
                    "TimePeriod": {
                        "Start": start_date.strftime("%Y-%m-%d"),
                        "End": end_date.strftime("%Y-%m-%d"),
                    },
                    "Granularity": "DAILY",
                    "Metrics": ["UnblendedCost"],
                    "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
                }
                if next_page_token:
                    params["NextPageToken"] = next_page_token

                response = client.get_cost_and_usage(**params)
                results_by_time.extend(response.get("ResultsByTime", []))
                next_page_token = response.get("NextPageToken")
                if not next_page_token:
                    break
            else:
                # Loop exhausted all 5 pages but more data remains
                if next_page_token:
                    pagination_cap_hit = True
                    logger.warning(
                        "AWS Cost Explorer pagination cap (5 pages) reached; "
                        "cost data may be incomplete. Increase days range or reduce granularity."
                    )

            if not results_by_time:
                return None, "No cost data returned by AWS Cost Explorer for specified period."

            # Organize daily totals and per-service breakdown
            daily_totals: Dict[str, float] = {}
            service_cumulative: Dict[str, float] = {}

            for item in results_by_time:
                date_key = item.get("TimePeriod", {}).get("Start", "")
                day_total = 0.0
                for group in item.get("Groups", []):
                    keys = group.get("Keys", [])
                    service_name = keys[0] if keys else "Unknown Service"
                    amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0.0))
                    # Ignore negative adjustments/credits for baseline spend calculations
                    valid_amount = max(0.0, amount)
                    day_total += valid_amount
                    service_cumulative[service_name] = service_cumulative.get(service_name, 0.0) + valid_amount

                daily_totals[date_key] = round(day_total, 2)

            data_points = list(daily_totals.values())
            current_day = now_utc.day
            days_in_current_month = calendar.monthrange(now_utc.year, now_utc.month)[1]

            metrics = calculate_spend_metrics(
                data_points,
                monthly_budget=monthly_budget,
                current_day_of_month=current_day,
                days_in_month=days_in_current_month,
            )

            # Identify top contributing service
            top_service = "All AWS Services"
            if service_cumulative:
                sorted_services = sorted(service_cumulative.items(), key=lambda x: x[1], reverse=True)
                top_service = sorted_services[0][0]

            time_series = [
                CostDataPoint(
                    date=dt,
                    spend=amt,
                    baseline=metrics.baseline_spend,
                    is_anomaly=(amt >= metrics.baseline_spend * 1.2),
                    service=top_service,
                    environment="production",
                )
                for dt, amt in daily_totals.items()
            ]

            anomaly = CostAnomaly(
                anomaly_id=f"ce-live-{end_date.strftime('%Y-%m-%d')}",
                scenario_id="aws_live",
                scenario_name=f"Live AWS Cost Explorer ({top_service})",
                service=top_service,
                environment="production",
                owner="unknown",  # Honestly unassigned; never invent verified owner from CE aggregate
                criticality="high" if metrics.anomaly_detected else "medium",
                metrics=metrics,
                time_series=time_series,
                currency="USD",
                detected_at=now_utc.isoformat(),
                is_simulated=False,
            )

            warning = None
            if pagination_cap_hit:
                warning = (
                    "PARTIAL_DATA: AWS Cost Explorer pagination cap reached (5 pages). "
                    "Returned cost data covers a subset of the requested period. "
                    "Reduce the query window or increase the page cap for complete data."
                )

            return anomaly, warning

        except (NoCredentialsError, PartialCredentialsError) as cred_err:
            return None, "AWS credentials are unavailable to the backend."
        except ClientError as ce:
            err_code = ce.response.get("Error", {}).get("Code", "ClientError")
            return None, f"AWS Cost Explorer request failed ({err_code[:80]})."
        except Exception as exc:
            logger.warning("Cost Explorer request failed (%s).", type(exc).__name__)
            return None, "AWS Cost Explorer is temporarily unavailable."
