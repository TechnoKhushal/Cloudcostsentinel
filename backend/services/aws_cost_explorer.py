from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

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

        try:
            session = boto3.Session(region_name=self.region_name)
            credentials = session.get_credentials()
            if not credentials:
                return {
                    "enabled": True,
                    "status": "missing_credentials",
                    "message": "AWS credentials not detected in standard credential chain (~/.aws/credentials or environment).",
                    "region": self.region_name,
                }

            # Non-mutative STS caller identity check
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            account_masked = f"***{identity.get('Account', '')[-4:]}"

            return {
                "enabled": True,
                "status": "connected",
                "message": f"Connected to AWS Account {account_masked} in {self.region_name}",
                "account_masked": account_masked,
                "region": self.region_name,
            }
        except (NoCredentialsError, PartialCredentialsError):
            return {
                "enabled": True,
                "status": "missing_credentials",
                "message": "AWS credentials missing or incomplete.",
                "region": self.region_name,
            }
        except ClientError as ce:
            code = ce.response.get("Error", {}).get("Code", "ClientError")
            return {
                "enabled": True,
                "status": f"permission_denied_{code}",
                "message": f"AWS error ({code}): verify ce:GetCostAndUsage and sts:GetCallerIdentity permissions.",
                "region": self.region_name,
            }
        except Exception as exc:
            return {
                "enabled": True,
                "status": "connection_error",
                "message": f"Unable to connect to AWS: {str(exc)}",
                "region": self.region_name,
            }

    def fetch_recent_costs(
        self, days: int = 14, monthly_budget: float = 10000.0
    ) -> Tuple[Optional[CostAnomaly], Optional[str]]:
        """Fetch cost telemetry from AWS Cost Explorer with read-only permissions."""
        if not self.enabled:
            return None, "AWS Cost Explorer is disabled in configuration."

        try:
            client = boto3.client("ce", region_name=self.region_name)
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=days)

            response = client.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            # Parse results
            results_by_time = response.get("ResultsByTime", [])
            if not results_by_time:
                return None, "No cost data returned by AWS Cost Explorer for specified period."

            daily_totals: Dict[str, float] = {}
            for item in results_by_time:
                date_key = item.get("TimePeriod", {}).get("Start", "")
                total = sum(
                    float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0.0))
                    for group in item.get("Groups", [])
                )
                daily_totals[date_key] = round(total, 2)

            data_points = list(daily_totals.values())
            metrics = calculate_spend_metrics(data_points, monthly_budget=monthly_budget)

            time_series = [
                CostDataPoint(
                    date=dt,
                    spend=amt,
                    baseline=metrics.baseline_spend,
                    is_anomaly=(amt >= metrics.baseline_spend * 1.2),
                    service="All AWS Services (Aggregated)",
                    environment="production",
                )
                for dt, amt in daily_totals.items()
            ]

            anomaly = CostAnomaly(
                anomaly_id=f"ce-live-{end_date.strftime('%Y-%m-%d')}",
                scenario_id="aws_live",
                scenario_name="Live AWS Cost Explorer Telemetry",
                service="Aggregated AWS Account",
                environment="production",
                owner="aws-account-admin",
                criticality="high" if metrics.anomaly_detected else "medium",
                metrics=metrics,
                time_series=time_series,
                currency="USD",
                detected_at=datetime.utcnow().isoformat() + "Z",
                is_simulated=False,
            )

            return anomaly, None

        except (NoCredentialsError, PartialCredentialsError) as cred_err:
            return None, f"AWS Credentials not configured: {cred_err}"
        except ClientError as ce:
            err_code = ce.response.get("Error", {}).get("Code", "ClientError")
            err_msg = ce.response.get("Error", {}).get("Message", str(ce))
            return None, f"AWS Cost Explorer Error [{err_code}]: {err_msg}"
        except Exception as exc:
            return None, f"Unexpected error querying AWS Cost Explorer: {str(exc)}"
