from __future__ import annotations

import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.config import Settings, parse_cors_origins, settings
from backend.database.db import DatabaseRepository, ApprovalConflictError
from backend.main import app, db
from backend.models.approval import ApprovalItem
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
    metrics = calculate_spend_metrics(datapoints, monthly_budget=5000.0, current_day_of_month=7, days_in_month=30)

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
    assert trace.raw_model_action == "request_approval"

    # Database drift scenario -> expected "notify_owner"
    drift_anomaly = CostScenarioRegistry.generate_scenario_anomaly("database_drift")
    trace = await client.decide(drift_anomaly)
    assert trace.action == "notify_owner"
    assert trace.confidence >= 0.65
    assert trace.is_fallback is False
    assert trace.raw_model_action == "notify_owner"

    # Stable baseline -> expected "monitor"
    stable_anomaly = CostScenarioRegistry.generate_scenario_anomaly("stable_baseline")
    trace = await client.decide(stable_anomaly)
    assert trace.action == "monitor"
    assert trace.confidence >= 0.65
    assert trace.is_fallback is False
    assert trace.raw_model_action == "monitor"


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
    # Raw model choice should be preserved
    assert trace.raw_model_action is not None


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
    assert "savings_model_assumptions" in t_approval.executed_details


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
        assert "state" in data["providers"]["decider"]
        assert "bedrock" in data["providers"]
        assert "auth" in data


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
                "notes": "Approved for right-sizing autoscaling min count.",
            },
        )
        assert review_resp.status_code == 200
        updated_appr = review_resp.json()
        assert updated_appr["status"] == "approved"
        # Server extracts identity from authenticated principal, never blindly trusts client body
        assert updated_appr["reviewed_by"] is not None
        assert "@" in updated_appr["reviewed_by"]


@pytest.mark.asyncio
async def test_api_decider_systemone_wire_protocol():
    """Test fixture endpoint must be disabled by default (returns 404).
    When ENABLE_TEST_FIXTURE_ENDPOINT=true, it should serve valid Strands wire-protocol responses.
    This test validates the disabled case.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Default (ENABLE_TEST_FIXTURE_ENDPOINT=false) → 404
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
        assert resp.status_code == 404
        assert "disabled" in resp.json()["detail"].lower()


# ==============================================================================
# 7. Production Hardening: Security, Replay, Boundaries & Validation
# ==============================================================================
@pytest.mark.asyncio
async def test_approval_replay_returns_conflict_409():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Run analysis to create pending approval
        resp = await ac.post("/api/analyze", json={"scenario_id": "compute_spike"})
        approval_id = resp.json()["approval"]["id"]

        # First review: succeeds
        r1 = await ac.post(
            f"/api/approvals/{approval_id}/decision",
            json={"action": "approved", "notes": "First review"},
        )
        assert r1.status_code == 200

        # Second review on already decided item: must return 409 Conflict
        r2 = await ac.post(
            f"/api/approvals/{approval_id}/decision",
            json={"action": "rejected", "notes": "Attempt replay"},
        )
        assert r2.status_code == 409
        assert "already reviewed" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_decisions_limit_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # limit=0 or negative is rejected by ge=1
        r_zero = await ac.get("/api/decisions?limit=0")
        assert r_zero.status_code == 422

        r_neg = await ac.get("/api/decisions?limit=-5")
        assert r_neg.status_code == 422

        # valid limit succeeds
        r_ok = await ac.get("/api/decisions?limit=10")
        assert r_ok.status_code == 200


@pytest.mark.asyncio
async def test_invalid_scenario_id_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/analyze", json={"scenario_id": "nonexistent_fake_scenario"})
        assert resp.status_code == 422
        assert "Invalid scenario_id" in resp.json()["detail"]


def test_cors_origins_parsing():
    # JSON-like format from .env.example
    json_cors = '["http://localhost:5173", "http://127.0.0.1:5173"]'
    parsed = parse_cors_origins(json_cors)
    assert "http://localhost:5173" in parsed
    assert "http://127.0.0.1:5173" in parsed

    # Comma-separated format
    csv_cors = "http://localhost:5173,http://127.0.0.1:5173,https://app.example.internal"
    parsed_csv = parse_cors_origins(csv_cors)
    assert len(parsed_csv) == 3
    assert "https://app.example.internal" in parsed_csv


def test_database_is_simulated_preservation(tmp_path):
    test_db_path = str(tmp_path / "test_sentinel.db")
    repo = DatabaseRepository(test_db_path)

    # Save a live (non-simulated) approval
    live_approval = ApprovalItem(
        id="appr-live-001",
        decision_id="dec-live-001",
        anomaly_id="anom-live-001",
        service="Amazon RDS",
        environment="production",
        suggested_action="Rightsize provisioned IOPS",
        estimated_monthly_savings=450.0,
        status="pending",
        created_at="2026-10-23T00:00:00Z",
        is_simulated=False,
    )
    repo.save_approval(live_approval)

    # Retrieve and verify is_simulated is preserved as False
    items = repo.get_approvals()
    assert len(items) == 1
    assert items[0].is_simulated is False

    # Review it and verify is_simulated remains False
    updated = repo.update_approval_status("appr-live-001", "approved", "admin@company.internal")
    assert updated is not None
    assert updated.is_simulated is False


def test_startup_validation_rules():
    # Confidence threshold out of bounds
    with pytest.raises(ValueError, match="DECIDER_MIN_CONFIDENCE"):
        Settings(DECIDER_MIN_CONFIDENCE=1.5).validate_startup()

    # Unknown decider provider
    with pytest.raises(ValueError, match="Invalid DECIDER_PROVIDER"):
        Settings(DECIDER_PROVIDER="unknown_provider_xyz").validate_startup()

    # 'inprocess' provider removed from allowed set
    with pytest.raises(ValueError, match="Invalid DECIDER_PROVIDER"):
        Settings(DECIDER_PROVIDER="inprocess").validate_startup()

    # Production refuses wildcard CORS
    with pytest.raises(ValueError, match="Wildcard"):
        Settings(
            ENVIRONMENT="production",
            CORS_ORIGINS=["*"],
            AUTH_ENABLED=True,
            AUTH_JWKS_URL="https://example.com/.well-known/jwks.json",
            AUTH_ISSUER="https://example.com",
            AUTH_AUDIENCE="api://sentinel",
            DECIDER_PROVIDER="http",
            BEDROCK_PROVIDER="bedrock",
        ).validate_startup()

    # Production refuses AUTH_ENABLED=False (escape hatch removed)
    with pytest.raises(ValueError, match="AUTH_ENABLED must be True"):
        Settings(
            ENVIRONMENT="production",
            CORS_ORIGINS=["https://sentinel.internal"],
            AUTH_ENABLED=False,
        ).validate_startup()

    # Production with AUTH_ENABLED=True requires OIDC config
    with pytest.raises(ValueError, match="AUTH_ENABLED=true requires"):
        Settings(
            ENVIRONMENT="production",
            CORS_ORIGINS=["https://sentinel.internal"],
            AUTH_ENABLED=True,
            AUTH_JWKS_URL=None,
            AUTH_ISSUER=None,
            AUTH_AUDIENCE=None,
            DECIDER_PROVIDER="mock",
            BEDROCK_PROVIDER="mock",
            ALLOW_MOCK_IN_PRODUCTION=True,
        ).validate_startup()

    # Production refuses ENABLE_TEST_FIXTURE_ENDPOINT=true
    with pytest.raises(ValueError, match="ENABLE_TEST_FIXTURE_ENDPOINT must be false"):
        Settings(
            ENVIRONMENT="production",
            CORS_ORIGINS=["https://sentinel.internal"],
            AUTH_ENABLED=True,
            AUTH_JWKS_URL="https://example.com/.well-known/jwks.json",
            AUTH_ISSUER="https://example.com",
            AUTH_AUDIENCE="api://sentinel",
            DECIDER_PROVIDER="mock",
            BEDROCK_PROVIDER="mock",
            ALLOW_MOCK_IN_PRODUCTION=True,
            ENABLE_TEST_FIXTURE_ENDPOINT=True,
        ).validate_startup()

    # HTTP decider cannot self-reference app's own port
    with pytest.raises(ValueError, match="points to the application's own HTTP port"):
        Settings(
            PORT=8000,
            DECIDER_PROVIDER="http",
            STRANDS_DECIDER_URL="http://127.0.0.1:8000/v1/systemone",
        ).validate_startup()


@pytest.mark.asyncio
async def test_real_http_decider_mock_transport_success():
    """Test HTTP Decider provider with valid SystemOne wire protocol response via mocked transport."""
    import httpx

    # Mock handler that simulates the official strands-decider serve process on port 8080
    def mock_server_handler(request: httpx.Request):
        content = {
            "model": "StrandsAgents/strands-decider-2B-hobson-v19",
            "answers": {
                "operational_response": {
                    "type": "choice",
                    "choice": "notify_owner",
                    "probabilities": {"monitor": 0.1, "notify_owner": 0.85, "request_approval": 0.05},
                    "confidence": 0.775,
                }
            },
            "usage": {"input_tokens": 150, "output_tokens": 0},
        }
        import json
        return httpx.Response(200, json=content)

    client = DeciderClient(
        provider="http",
        endpoint_url="http://127.0.0.1:8080/v1/systemone",
        model_id="StrandsAgents/strands-decider-2B-hobson-v19",
    )

    # Monkeypatch AsyncClient to use mock_server_handler
    mock_transport = httpx.MockTransport(mock_server_handler)
    orig_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return orig_async_client(*args, **kwargs)

    import unittest.mock
    with unittest.mock.patch("httpx.AsyncClient", side_effect=patched_client):
        anomaly = CostScenarioRegistry.generate_scenario_anomaly("database_drift")
        trace = await client.decide(anomaly)

        assert trace.action == "notify_owner"
        assert trace.provider == "strands-decider-2b-http"
        assert trace.model_id == "StrandsAgents/strands-decider-2B-hobson-v19"
        assert trace.confidence == 0.775
        assert trace.probabilities["notify_owner"] == 0.85
        assert trace.is_fallback is False



# ==============================================================================
# 9. Auth Hardening — P0 Regression Tests
# ==============================================================================

def test_auth_requires_oidc_when_enabled():
    """When AUTH_ENABLED=True, startup should require JWKS + issuer + audience in production."""
    # Missing all three OIDC fields in production context
    with pytest.raises(ValueError, match="AUTH_ENABLED=true requires"):
        Settings(
            ENVIRONMENT="production",
            CORS_ORIGINS=["https://sentinel.internal"],
            AUTH_ENABLED=True,
            AUTH_JWKS_URL=None,
            AUTH_ISSUER=None,
            AUTH_AUDIENCE=None,
            DECIDER_PROVIDER="mock",
            BEDROCK_PROVIDER="mock",
            ALLOW_MOCK_IN_PRODUCTION=True,
        ).validate_startup()


def test_inprocess_provider_rejected():
    """'inprocess' provider must be rejected — it raises NotImplementedError at runtime."""
    with pytest.raises(ValueError, match="Invalid DECIDER_PROVIDER"):
        Settings(DECIDER_PROVIDER="inprocess").validate_startup()


def test_fixture_endpoint_rejected_in_production():
    """ENABLE_TEST_FIXTURE_ENDPOINT=true must be rejected in production."""
    with pytest.raises(ValueError, match="ENABLE_TEST_FIXTURE_ENDPOINT must be false"):
        Settings(
            ENVIRONMENT="production",
            CORS_ORIGINS=["https://sentinel.internal"],
            AUTH_ENABLED=True,
            AUTH_JWKS_URL="https://example.com/.well-known/jwks.json",
            AUTH_ISSUER="https://example.com",
            AUTH_AUDIENCE="api://sentinel",
            DECIDER_PROVIDER="mock",
            BEDROCK_PROVIDER="mock",
            ALLOW_MOCK_IN_PRODUCTION=True,
            ENABLE_TEST_FIXTURE_ENDPOINT=True,
        ).validate_startup()


@pytest.mark.asyncio
async def test_auth_enabled_rejects_missing_token():
    """When AUTH_ENABLED=True, missing Bearer token returns 401."""
    import unittest.mock
    # Temporarily set AUTH_ENABLED=True on the app's settings singleton
    with unittest.mock.patch.object(settings, "AUTH_ENABLED", True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/demo/scenarios")
            # With AUTH_ENABLED=True but no token provided → 401
            assert resp.status_code == 401
            assert "Missing Authorization Bearer token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_enabled_rejects_malformed_token():
    """When AUTH_ENABLED=True, a malformed/forged JWT returns 401."""
    import unittest.mock
    with unittest.mock.patch.object(settings, "AUTH_ENABLED", True):
        # Patch _get_jwks_client to raise PyJWKClient would normally need a network call;
        # instead we test that a garbage token fails decode gracefully.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/demo/scenarios",
                headers={"Authorization": "Bearer not.a.real.jwt"},
            )
            assert resp.status_code == 401


@pytest.mark.asyncio
async def test_fixture_endpoint_disabled_by_default():
    """The /v1/systemone endpoint must return 404 when ENABLE_TEST_FIXTURE_ENDPOINT=false (default)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "state": "test",
            "model": "StrandsAgents/strands-decider-2B-hobson-v19",
            "questions": {
                "q": {
                    "type": "choice",
                    "instructions": "test",
                    "criteria": {"monitor": "m", "notify_owner": "n", "request_approval": "r"},
                }
            },
        }
        resp = await ac.post("/v1/systemone", json=payload)
        assert resp.status_code == 404
        assert "disabled" in resp.json()["detail"].lower()
