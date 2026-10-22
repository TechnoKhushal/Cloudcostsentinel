from __future__ import annotations

import pytest
from patterns.threshold_aware_anomaly_response.policy_pattern import (
    AnomalyState,
    ThresholdAwareAnomalyPolicy,
)


@pytest.fixture
def policy():
    return ThresholdAwareAnomalyPolicy(min_confidence=0.65, use_mock_fallback=True)


@pytest.mark.asyncio
async def test_pattern_request_approval(policy):
    state = AnomalyState(
        entity_id="ec2-prod",
        category="Amazon EC2",
        criticality="critical",
        assigned_owner="unknown",
        current_value=1200.0,
        baseline_value=300.0,
        delta_amount=900.0,
        delta_percentage=300.0,
        persistence_count=3,
        threshold_limit=10000.0,
        burn_percentage=220.0,
        uncertainty_flag=False,
    )
    result = await policy.evaluate(state)
    assert result.action == "request_approval"
    assert result.confidence >= 0.65
    assert result.is_fallback is False


@pytest.mark.asyncio
async def test_pattern_notify_owner(policy):
    state = AnomalyState(
        entity_id="rds-prod",
        category="Amazon Aurora RDS",
        criticality="high",
        assigned_owner="db-team@corp.internal",
        current_value=600.0,
        baseline_value=450.0,
        delta_amount=150.0,
        delta_percentage=33.3,
        persistence_count=2,
        threshold_limit=15000.0,
        burn_percentage=95.0,
        uncertainty_flag=False,
    )
    result = await policy.evaluate(state)
    assert result.action == "notify_owner"
    assert result.confidence >= 0.65
    assert result.is_fallback is False


@pytest.mark.asyncio
async def test_pattern_monitor(policy):
    state = AnomalyState(
        entity_id="ecs-app",
        category="Amazon ECS",
        criticality="low",
        assigned_owner="app-team@corp.internal",
        current_value=105.0,
        baseline_value=100.0,
        delta_amount=5.0,
        delta_percentage=5.0,
        persistence_count=0,
        threshold_limit=5000.0,
        burn_percentage=45.0,
        uncertainty_flag=False,
    )
    result = await policy.evaluate(state)
    assert result.action == "monitor"
    assert result.confidence >= 0.65
    assert result.is_fallback is False


@pytest.mark.asyncio
async def test_pattern_low_confidence_fallback():
    policy = ThresholdAwareAnomalyPolicy(min_confidence=0.70, use_mock_fallback=True)
    # Uncertainty flag causes low confidence
    state = AnomalyState(
        entity_id="s3-glacier",
        category="Amazon S3 Glacier",
        criticality="medium",
        assigned_owner="unknown",
        current_value=250.0,
        baseline_value=100.0,
        delta_amount=150.0,
        delta_percentage=150.0,
        persistence_count=1,
        threshold_limit=3000.0,
        burn_percentage=70.0,
        uncertainty_flag=True,  # sparse telemetry
    )
    result = await policy.evaluate(state)
    assert result.action == "request_approval"
    assert result.is_fallback is True
    assert "below minimum calibrated threshold" in result.fallback_reason


@pytest.mark.asyncio
async def test_pattern_unreachable_server_without_mock():
    # If mock fallback disabled and server unreachable, conservative escalation
    policy = ThresholdAwareAnomalyPolicy(
        endpoint_url="http://127.0.0.1:54321/unreachable",
        use_mock_fallback=False,
    )
    state = AnomalyState(
        entity_id="ecs-app",
        category="Amazon ECS",
        criticality="low",
        assigned_owner="app-team@corp.internal",
        current_value=105.0,
        baseline_value=100.0,
        delta_amount=5.0,
        delta_percentage=5.0,
        persistence_count=0,
        threshold_limit=5000.0,
        burn_percentage=45.0,
        uncertainty_flag=False,
    )
    result = await policy.evaluate(state)
    assert result.action == "request_approval"
    assert result.is_fallback is True
    assert "failed" in result.fallback_reason.lower()
