from __future__ import annotations

import calendar
import logging
import uuid
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
                "message": "AWS Cost Explorer is disabled until customer-owned, read-only role connections are enabled.",
                "region": self.region_name,
            }
        return {
            "enabled": True,
            "status": "configured_unverified",
            "message": "Customer-owned IAM role connections use temporary credentials; verify each workspace before ingestion.",
            "region": self.region_name,
            "daily_query_limit": settings.AWS_COST_EXPLORER_DAILY_QUERY_LIMIT,
        }

    @staticmethod
    def _assume_customer_role(role_arn: str, external_id: str):
        """Assume a customer-owned role; the platform identity only needs sts:AssumeRole."""
        base_sts = boto3.client("sts", region_name="us-east-1",
            config=Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 1, "mode": "standard"}))
        result = base_sts.assume_role(RoleArn=role_arn, RoleSessionName="CloudCostSentinelReadOnly", ExternalId=external_id, DurationSeconds=900)
        credentials = result["Credentials"]
        session = boto3.Session(aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"], aws_session_token=credentials["SessionToken"])
        identity = session.client("sts", region_name="us-east-1",
            config=Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 1, "mode": "standard"})).get_caller_identity()
        return session, identity

    @staticmethod
    def get_platform_principal_arn() -> Optional[str]:
        try:
            return boto3.client("sts", region_name="us-east-1",
                config=Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 1, "mode": "standard"})).get_caller_identity().get("Arn")
        except Exception as exc:
            logger.warning("AWS platform identity check failed (%s).", type(exc).__name__)
            return None

    def verify_connection(self, role_arn: str, external_id: str, expected_account_id: str) -> tuple[bool, Optional[str]]:
        """Verify the external ID, role trust, account identity, and CE read permission."""
        if not self.enabled:
            return False, "AWS Cost Explorer ingestion is disabled by platform configuration."
        try:
            session, identity = self._assume_customer_role(role_arn, external_id)
            if identity.get("Account") != expected_account_id:
                return False, "The assumed AWS role belongs to a different account than the configured role ARN."
            end_date = datetime.now(timezone.utc).date()
            start_date = end_date - timedelta(days=1)
            session.client("ce", region_name=self.region_name,
                config=Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 1, "mode": "standard"})).get_cost_and_usage(
                    TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
                    Granularity="DAILY", Metrics=["UnblendedCost"])
            return True, None
        except (NoCredentialsError, PartialCredentialsError):
            return False, "The platform AWS AssumeRole identity is not configured."
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "AWSAccessError")
            return False, f"AWS role verification failed ({str(code)[:80]}). Check the role trust and read-only Cost Explorer policy."
        except Exception as exc:
            logger.warning("AWS role verification failed (%s).", type(exc).__name__)
            return False, "AWS role verification is temporarily unavailable."

    def fetch_recent_costs(
        self, days: int = 14, monthly_budget: float = 10000.0,
        role_arn: Optional[str] = None, external_id: Optional[str] = None,
        expected_account_id: Optional[str] = None, budget_currency: Optional[str] = None,
    ) -> Tuple[Optional[CostAnomaly], Optional[str]]:
        """Fetch a bounded daily account-total series through a tenant's read-only role.

        The query deliberately avoids service-level grouping and pagination so one
        explicit analysis incurs at most one paid Cost Explorer API request.
        """
        if not self.enabled:
            return None, "AWS Cost Explorer is disabled in configuration."
        if not role_arn or not external_id or not expected_account_id:
            return None, "This workspace has no complete AWS role connection. Configure and verify it first."

        try:
            session, identity = self._assume_customer_role(role_arn, external_id)
            if identity.get("Account") != expected_account_id:
                return None, "The connected AWS role account could not be verified. Reconnect the customer role."
            client = session.client("ce", region_name=self.region_name,
                config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 1, "mode": "standard"}))
            now_utc = datetime.now(timezone.utc)
            # TimePeriod.End is exclusive in Cost Explorer API.
            # Daily billing metrics typically lag by 24-48 hours.
            end_date = now_utc.date()
            start_date = end_date - timedelta(days=days)

            response = client.get_cost_and_usage(TimePeriod={"Start": start_date.isoformat(), "End": end_date.isoformat()},
                Granularity="DAILY", Metrics=["UnblendedCost"])
            results_by_time = response.get("ResultsByTime", [])
            pagination_cap_hit = bool(response.get("NextPageToken"))

            if not results_by_time:
                return None, "No cost data returned by AWS Cost Explorer for specified period."

            # Account-level daily totals. Service grouping would paginate and
            # create additional billable API requests; keep this bounded.
            daily_totals: Dict[str, float] = {}
            currency = "USD"

            for item in results_by_time:
                date_key = item.get("TimePeriod", {}).get("Start", "")
                metric = item.get("Total", {}).get("UnblendedCost", {})
                currency = metric.get("Unit", currency)
                daily_totals[date_key] = round(max(0.0, float(metric.get("Amount", 0.0))), 2)

            if budget_currency and currency.upper() != budget_currency.upper():
                return None, f"AWS billing currency {currency} does not match the workspace budget currency {budget_currency}. Update the workspace budget currency before analysis."

            data_points = list(daily_totals.values())
            current_day = now_utc.day
            days_in_current_month = calendar.monthrange(now_utc.year, now_utc.month)[1]

            metrics = calculate_spend_metrics(
                data_points,
                monthly_budget=monthly_budget,
                current_day_of_month=current_day,
                days_in_month=days_in_current_month,
            )

            account_label = f"AWS account {expected_account_id}"

            time_series = [
                CostDataPoint(
                    date=dt,
                    spend=amt,
                    baseline=metrics.baseline_spend,
                    is_anomaly=(amt >= metrics.baseline_spend * 1.2),
                    service=account_label,
                    environment="production",
                )
                for dt, amt in daily_totals.items()
            ]

            anomaly = CostAnomaly(
                anomaly_id=f"ce-live-{end_date.strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:12]}",
                scenario_id="aws_live",
                scenario_name=f"Live AWS Cost Explorer ({expected_account_id})",
                service=account_label,
                environment="production",
                owner="unknown",  # Honestly unassigned; never invent verified owner from CE aggregate
                criticality="high" if metrics.anomaly_detected else "medium",
                metrics=metrics,
                time_series=time_series,
                currency=currency,
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
