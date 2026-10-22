from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app, db
from backend.models.cost import CostAnomaly, SpendMetrics
from backend.services.cost_analyzer import calculate_spend_metrics, CostScenarioRegistry
from backend.services.decider_client import DeciderClient
from backend.services.aws_cost_explorer import AWSCostExplorerService
from backend.interventions.anomaly_policy import ThresholdAwareAnomalyIntervention
from strands.interventions.actions import Confirm, Guide, Proceed


# ==============================================================================
# 1. Spend Math, Baseline & Threshold Edge Cases
# ==============================================================================
def test_spend_metrics_calculation_standard():
    datapoints = [100.0, 105.0, 95.0, 100.0, 102.0, 100.0, 250.0]
    metrics = calculate_spend_metrics(datapoints, monthly_budget=5000.0, current_day_of_month=7)

    # Baseline is mean of [100, 105, 95, 100, 102, 100] = 602 / 6 = 100.33
    assert abs(metrics.baseline_spend - 100.33) < 0.1
    assert metrics.current_spend == 250.0
    assert abs(metrics.delta_amount - 149.67) < 0.1
    assert metrics.delta_percentage > 140.0
    assert metrics.persistence_days == 1
    assert metrics.anomaly_detected is True
    assert metrics.uncertainty_flag is False


def test_spend_metrics_empty_data():
    metrics = calculate_spend_metrics([], monthly_budget=1000.0)
    assert metrics.current_spend == 0.0
    assert metrics.baseline_spend == 0.0
    assert metrics.delta_amount == 0.0
    assert metrics.delta_percentage == 0.0
    assert metrics.uncertainty_flag is True
    assert metrics.anomaly_detected is False


def test_spend_metrics_zero_baseline():
    # Cold start: baseline 0
    datapoints = [0.0, 0.0, 150.0]
    metrics = calculate_spend_metrics(datapoints, monthly_budget=2000.0)
    assert metrics.current_spend == 150.0
    assert metrics.delta_percentage == 100.0
    assert metrics.uncertainty_flag is True  # Few baseline points


def test_persistence_streak():
    # Baseline ~ 100 (first 5 points), trailing 3 days exceed 120 (threshold 20%)
    datapoints = [100.0, 100.0, 100.0, 100.0, 100.0, 130.0, 140.0, 160.0]
    metrics = calculate_spend_metrics(datapoints, monthly_budget=5000.0, anomaly_threshold_pct=20.0, baseline_window_days=5)
    assert metrics.persistence_days == 3


# ==============================================================================
# 2. Decider 2B Choices & Confidence Handling
# ==============================================================================
@pytest.mark.asyncio
async def test_decider_choices_and_confidence():
    client = DeciderClient(provider="mock")

    # Compute spike scenario -> expected "request_approval"
    spike_anomaly = CostScenarioRegistry.generate_scenario_anomaly("compute_spike")
    trace = await client.decide(spike_anomaly)
    assert trace.action == "request_approval"
    assert trace.confidence >= 0.65
    assert "request_approval" in trace.probabilities
    assert trace.is_fallback is False

    # Database drift scenario -> expected "notify_owner"
    drift_anomaly = CostScenarioRegistry.generate_scenario_anomaly("database_drift")
    trace = await client.decide(drift_anomaly)
    assert trace.action == "notify_owner"
    assert trace.confidence >= 0.65
    assert trace.is_fallback is False

    # Stable baseline -> expected "monitor"
    stable_anomaly = CostScenarioRegistry.generate_scenario_anomaly("stable_baseline")
    trace = await client.decide(stable_anomaly)
    assert trace.action == "monitor"
    assert trace.confidence >= 0.65
    assert trace.is_fallback is False


@pytest.mark.asyncio
async def test_decider_low_confidence_fallback():
    # Sparse data triggers low confidence (< 0.65)
    client = DeciderClient(provider="mock", min_confidence=0.65)
    uncertain_anomaly = CostScenarioRegistry.generate_scenario_anomaly("low_confidence_drift")
    trace = await client.decide(uncertain_anomaly)

    # Must conservatively fallback to request_approval
    assert trace.action == "request_approval"
    assert trace.is_fallback is True
    assert "below safety threshold" in trace.fallback_reason.lower()


@pytest.mark.asyncio
async def test_decider_http_provider_failure_fallback():
    # Pointing to an invalid unreachable port
    client = DeciderClient(
        provider="http",
        endpoint_url="http://127.0.0.1:59999/invalid",
        min_confidence=0.65,
    )
    anomaly = CostScenarioRegistry.generate_scenario_anomaly("batch_surge")
    trace = await client.decide(anomaly)

    # Must safely fallback to request_approval
    assert trace.action == "request_approval"
    assert trace.is_fallback is True
    assert "provider error" in trace.fallback_reason.lower()


# ==============================================================================
# 3. Action Routing & Execution Path
# ==============================================================================
@pytest.mark.asyncio
async def test_downstream_action_routing():
    client = DeciderClient(provider="mock")

    # 1. Monitor routes to observation
    stable = CostScenarioRegistry.generate_scenario_anomaly("stable_baseline")
    t_monitor = await client.decide(stable)
    assert t_monitor.executed_action == "LOG_FOR_OBSERVATION"
    assert t_monitor.executed_details["alert_dispatched"] is False

    # 2. Notify owner routes to notification event
    drift = CostScenarioRegistry.generate_scenario_anomaly("database_drift")
    t_notify = await client.decide(drift)
    assert t_notify.executed_action == "DISPATCH_OWNER_NOTIFICATION"
    assert t_notify.executed_details["recipient"] == drift.owner

    # 3. Request approval routes to review item creation
    spike = CostScenarioRegistry.generate_scenario_anomaly("compute_spike")
    t_approval = await client.decide(spike)
    assert t_approval.executed_action == "CREATE_APPROVAL_REVIEW_ITEM"
    assert t_approval.executed_details["approval_required"] is True
    assert t_approval.executed_details["estimated_monthly_savings"] > 0


# ==============================================================================
# 4. Strands InterventionHandler Integration
# ==============================================================================
@pytest.mark.asyncio
async def test_strands_intervention_policy_mapping():
    client = DeciderClient(provider="mock")
    intervention = ThresholdAwareAnomalyIntervention(decider_client=client)

    # When anomaly is stable -> Proceed
    intervention.set_anomaly(CostScenarioRegistry.generate_scenario_anomaly("stable_baseline"))
    res_monitor = await intervention.before_tool_call(event=None)
    assert isinstance(res_monitor, Proceed)

    # When anomaly is database drift -> Guide
    intervention.set_anomaly(CostScenarioRegistry.generate_scenario_anomaly("database_drift"))
    res_notify = await intervention.before_tool_call(event=None)
    assert isinstance(res_notify, Guide)

    # When anomaly is compute spike -> Confirm
    intervention.set_anomaly(CostScenarioRegistry.generate_scenario_anomaly("compute_spike"))
    res_approval = await intervention.before_tool_call(event=None)
    assert isinstance(res_approval, Confirm)


# ==============================================================================
# 5. AWS Cost Explorer Safety
# ==============================================================================
def test_aws_cost_explorer_disabled_by_default():
    service = AWSCostExplorerService(enabled=False)
    status = service.get_status()
    assert status["enabled"] is False
    assert status["status"] == "disabled_by_configuration"

    anomaly, err = service.fetch_recent_costs()
    assert anomaly is None
    assert "disabled in configuration" in err


def test_aws_cost_explorer_missing_credentials_graceful():
    service = AWSCostExplorerService(enabled=True)
    status = service.get_status()
    assert status["enabled"] is True
    # Gracefully reports missing credentials or permission denied without crashing
    assert "status" in status
    assert "account_secret" not in status


# ==============================================================================
# 6. End-to-End API Integration
# ==============================================================================
@pytest.mark.asyncio
async def test_api_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "decider" in data["providers"]
        assert "bedrock" in data["providers"]


@pytest.mark.asyncio
async def test_api_scenarios_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/demo/scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        assert len(scenarios) >= 5
        scenario_ids = [s["id"] for s in scenarios]
        assert "compute_spike" in scenario_ids
        assert "database_drift" in scenario_ids


@pytest.mark.asyncio
async def test_api_analyze_compute_spike_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Run analysis for compute spike
        resp = await ac.post("/api/analyze", json={"scenario_id": "compute_spike"})
        assert resp.status_code == 200
        data = resp.json()

        # Check Decider trace
        decision = data["decision"]
        assert decision["action"] == "request_approval"
        assert decision["confidence"] > 0.65
        assert decision["is_fallback"] is False

        # Check Bedrock grounded report
        report = data["report"]
        assert "EC2" in report["title"] or "compute" in report["title"].lower()
        assert len(report["observed_facts"]) >= 3
        assert "request_approval" in report["decider_action_audit"]

        # Check approval creation
        approval = data["approval"]
        assert approval is not None
        assert approval["status"] == "pending"
        assert approval["estimated_monthly_savings"] > 0
        approval_id = approval["id"]

        # Record human review decision
        review_resp = await ac.post(
            f"/api/approvals/{approval_id}/decision",
            json={
                "action": "approved",
                "reviewed_by": "lead-sre@company.internal",
                "notes": "Approved for right-sizing autoscaling min count.",
            },
        )
        assert review_resp.status_code == 200
        updated_appr = review_resp.json()
        assert updated_appr["status"] == "approved"
        assert updated_appr["reviewed_by"] == "lead-sre@company.internal"


@pytest.mark.asyncio
async def test_api_decider_systemone_wire_protocol():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "state": "Service: Amazon EC2 (Production). Spend Delta: +$850/day. High spike.",
            "model": "StrandsAgents/strands-decider-2B-hobson-v19",
            "questions": {
                "operational_response": {
                    "type": "choice",
                    "instructions": "Should the agent monitor, notify_owner, or request_approval?",
                    "criteria": {
                        "monitor": "observe without alerting",
                        "notify_owner": "alert service owner",
                        "request_approval": "request human signoff for remediation",
                    },
                }
            },
        }
        resp = await ac.post("/v1/systemone", json=payload)
        assert resp.status_code == 200
        res_data = resp.json()
        assert "answers" in res_data
        ans = res_data["answers"]["operational_response"]
        assert ans["type"] == "choice"
        assert ans["choice"] == "request_approval"
        assert ans["confidence"] > 0.0
