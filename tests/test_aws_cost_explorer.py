from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from backend.services.aws_cost_explorer import AWSCostExplorerService


class _Sts:
    def __init__(self, account: str):
        self.account = account
        self.assume_calls = []

    def assume_role(self, **kwargs):
        self.assume_calls.append(kwargs)
        return {"Credentials": {"AccessKeyId": "temporary", "SecretAccessKey": "temporary-secret", "SessionToken": "temporary-token"}}

    def get_caller_identity(self):
        return {"Account": self.account, "Arn": f"arn:aws:sts::{self.account}:assumed-role/CloudCostSentinelReadOnly/session"}


class _CostExplorer:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get_cost_and_usage(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _Session:
    def __init__(self, cost_explorer, account="123456789012"):
        self.cost_explorer = cost_explorer
        self.account = account

    def client(self, service, **_kwargs):
        if service == "sts":
            return _Sts(self.account)
        assert service == "ce"
        return self.cost_explorer


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 7, tzinfo=tz or timezone.utc)


def _cost_response(today=date(2026, 11, 7)):
    points = [
        {"TimePeriod": {"Start": (today - timedelta(days=day)).isoformat()},
         "Total": {"UnblendedCost": {"Amount": "100.00", "Unit": "USD"}}}
        for day in range(14, 0, -1)
    ]
    return {"ResultsByTime": points}


def test_customer_role_analysis_is_tenant_scoped_and_uses_one_billed_query():
    sts = _Sts("123456789012")
    ce = _CostExplorer(_cost_response())
    with patch("backend.services.aws_cost_explorer.boto3.client", return_value=sts), \
         patch("backend.services.aws_cost_explorer.boto3.Session", return_value=_Session(ce)), \
         patch("backend.services.aws_cost_explorer.datetime", _FrozenDateTime):
        anomaly, warning = AWSCostExplorerService(enabled=True).fetch_recent_costs(
            role_arn="arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly",
            external_id="a" * 32,
            expected_account_id="123456789012",
        )
    assert anomaly is not None
    assert anomaly.is_simulated is False
    assert anomaly.service == "AWS account 123456789012"
    assert warning is None
    assert sts.assume_calls[0]["ExternalId"] == "a" * 32
    assert sts.assume_calls[0]["DurationSeconds"] == 900
    assert len(ce.calls) == 1
    assert "GroupBy" not in ce.calls[0]
    assert ce.calls[0]["Metrics"] == ["UnblendedCost"]
    assert ce.calls[0]["TimePeriod"] == {"Start": "2026-10-24", "End": "2026-11-07"}
    assert anomaly.metrics.month_to_date_spend == 600
    assert len(anomaly.time_series) == 6


def test_cost_explorer_uses_full_month_to_date_and_recent_baseline_for_forecast():
    today = date(2026, 11, 7)
    start = date(2026, 10, 24)
    points = []
    current = start
    while current < today:
        amount = 300.0 if current == date(2026, 11, 6) else 100.0 if current.month == 11 else 200.0
        points.append({"TimePeriod": {"Start": current.isoformat()},
            "Total": {"UnblendedCost": {"Amount": str(amount), "Unit": "USD"}}})
        current += timedelta(days=1)
    ce = _CostExplorer({"ResultsByTime": points})
    with patch("backend.services.aws_cost_explorer.boto3.client", return_value=_Sts("123456789012")), \
         patch("backend.services.aws_cost_explorer.boto3.Session", return_value=_Session(ce)), \
         patch("backend.services.aws_cost_explorer.datetime", _FrozenDateTime):
        anomaly, warning = AWSCostExplorerService(enabled=True).fetch_recent_costs(
            monthly_budget=10000,
            role_arn="arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly",
            external_id="c" * 32,
            expected_account_id="123456789012",
        )
    assert anomaly is not None
    assert warning is None
    assert anomaly.metrics.current_spend == 300
    assert anomaly.metrics.baseline_spend == round((200 + 200 + 5 * 100) / 7, 2)
    assert anomaly.metrics.month_to_date_spend == 800
    assert anomaly.metrics.forecast_month_end == 8000
    assert anomaly.metrics.anomaly_detected is True


def test_cost_explorer_surfaces_stale_or_paginated_data_without_extra_requests():
    response = _cost_response(today=date(2026, 11, 4))
    response["NextPageToken"] = "more-data"
    ce = _CostExplorer(response)
    with patch("backend.services.aws_cost_explorer.boto3.client", return_value=_Sts("123456789012")), \
         patch("backend.services.aws_cost_explorer.boto3.Session", return_value=_Session(ce)), \
         patch("backend.services.aws_cost_explorer.datetime", _FrozenDateTime):
        anomaly, warning = AWSCostExplorerService(enabled=True).fetch_recent_costs(
            role_arn="arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly",
            external_id="d" * 32,
            expected_account_id="123456789012",
        )
    assert anomaly is not None
    assert warning is not None
    assert "DATA_FRESHNESS:" in warning
    assert "PARTIAL_DATA:" in warning
    assert len(ce.calls) == 1


def test_cost_explorer_blocks_forecasts_until_current_month_data_exists():
    response = _cost_response(today=date(2026, 10, 31))
    ce = _CostExplorer(response)
    with patch("backend.services.aws_cost_explorer.boto3.client", return_value=_Sts("123456789012")), \
         patch("backend.services.aws_cost_explorer.boto3.Session", return_value=_Session(ce)), \
         patch("backend.services.aws_cost_explorer.datetime", _FrozenDateTime):
        anomaly, error = AWSCostExplorerService(enabled=True).fetch_recent_costs(
            role_arn="arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly",
            external_id="e" * 32,
            expected_account_id="123456789012",
        )
    assert anomaly is None
    assert error and "current-month cost data" in error


def test_role_verification_rejects_wrong_account_before_billing_query():
    sts = _Sts("999999999999")
    ce = _CostExplorer(_cost_response())
    with patch("backend.services.aws_cost_explorer.boto3.client", return_value=sts), \
         patch("backend.services.aws_cost_explorer.boto3.Session", return_value=_Session(ce, "999999999999")):
        verified, error = AWSCostExplorerService(enabled=True).verify_connection(
            "arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly", "b" * 32, "123456789012")
    assert verified is False
    assert error == "The assumed AWS role belongs to a different account than the configured role ARN."
    assert not ce.calls
