#!/usr/bin/env python3
"""Standalone runnable example demonstrating the Threshold-Aware Anomaly Response Policy Pattern.

Run:
    python standalone_example.py
"""

import asyncio
from policy_pattern import AnomalyState, ThresholdAwareAnomalyPolicy


async def main():
    print("=" * 80)
    print("Threshold-Aware Anomaly Response Pattern (#strands-decider-2b #policy)")
    print("=" * 80)

    policy = ThresholdAwareAnomalyPolicy(min_confidence=0.65, use_mock_fallback=True)

    # 1. High-severity compute runaway
    runaway_state = AnomalyState(
        entity_id="i-worker-autoscaling-group",
        category="Amazon EC2",
        criticality="critical",
        assigned_owner="unknown",
        current_value=1340.0,
        baseline_value=320.0,
        delta_amount=1020.0,
        delta_percentage=318.7,
        persistence_count=3,
        threshold_limit=12000.0,
        burn_percentage=237.8,
        uncertainty_flag=False,
    )

    print("\n[Case 1: Critical Runaway Compute Spike]")
    res1 = await policy.evaluate(runaway_state)
    print(f"Decider Choice: {res1.action.upper()}")
    print(f"Confidence:     {res1.confidence:.4f}")
    print(f"Probabilities:  {res1.probabilities}")
    print(f"Provider:       {res1.provider}")
    print(f"Fallback?:      {res1.is_fallback} ({res1.fallback_reason})")

    # 2. Database drift with known owner
    db_state = AnomalyState(
        entity_id="aurora-cluster-prod-db",
        category="Amazon Aurora RDS",
        criticality="high",
        assigned_owner="db-eng@company.internal",
        current_value=640.0,
        baseline_value=450.0,
        delta_amount=190.0,
        delta_percentage=42.2,
        persistence_count=3,
        threshold_limit=18000.0,
        burn_percentage=106.0,
        uncertainty_flag=False,
    )

    print("\n[Case 2: Known Owner Database IOPS Drift]")
    res2 = await policy.evaluate(db_state)
    print(f"Decider Choice: {res2.action.upper()}")
    print(f"Confidence:     {res2.confidence:.4f}")
    print(f"Probabilities:  {res2.probabilities}")

    # 3. Low-confidence sparse data
    sparse_state = AnomalyState(
        entity_id="glacier-vault-archive",
        category="Amazon S3 Glacier",
        criticality="medium",
        assigned_owner="unknown",
        current_value=450.0,
        baseline_value=150.0,
        delta_amount=300.0,
        delta_percentage=200.0,
        persistence_count=1,
        threshold_limit=5000.0,
        burn_percentage=85.0,
        uncertainty_flag=True,  # Sparse data
    )

    print("\n[Case 3: Sparse Telemetry / Low-Confidence Fallback]")
    res3 = await policy.evaluate(sparse_state)
    print(f"Decider Choice: {res3.action.upper()}")
    print(f"Confidence:     {res3.confidence:.4f} (Safety threshold: {policy.min_confidence})")
    print(f"Fallback?:      {res3.is_fallback}")
    print(f"Reason:         {res3.fallback_reason}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
