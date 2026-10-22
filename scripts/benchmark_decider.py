#!/usr/bin/env python3
"""Reproducible benchmark experiment for Strands Decider 2B and Decision Policy (#strands-decider-2b #policy).

Measures:
- Latency (median, p95, min, max) across multiple trials.
- Decision consistency and output distribution.
- Distinguishes raw model decision latency from full end-to-end orchestration latency.
- Strictly labels mock runs as 'simulated_mock_execution' and requires a real provider run for 'real_model_measurement=true'.
- Outputs machine-readable JSON and CSV results.

Usage:
    python scripts/benchmark_decider.py --trials 20 --warmup 3
"""

import argparse
import asyncio
import csv
import json
import logging
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings
from backend.models.cost import CostAnomaly
from backend.services.cost_analyzer import CostScenarioRegistry
from backend.services.decider_client import DeciderClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("benchmark_decider")


def calculate_p95(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(0.95 * (len(s) - 1)))))
    return round(s[idx], 3)


async def run_benchmark(
    trials: int = 10,
    warmup: int = 2,
    output_dir: str = "scripts/benchmark_results",
    provider: str = None,
) -> Dict[str, Any]:
    if trials <= 0:
        raise ValueError(f"trials must be > 0; got {trials}")
    if warmup < 0:
        raise ValueError(f"warmup must be >= 0; got {warmup}")

    provider_name = provider or settings.DECIDER_PROVIDER
    client = DeciderClient(provider=provider_name)
    scenarios = ["compute_spike", "database_drift", "batch_surge", "stable_baseline", "low_confidence_drift"]

    is_real_provider = (provider_name != "mock")
    reported_model = settings.DECIDER_MODEL_ID if is_real_provider else "demo-policy-evaluator-v1"
    measurement_type = "real_model_inference" if is_real_provider else "simulated_mock_execution"

    logger.info(
        "Initializing Decider benchmark (Provider: %s, Real Model: %s, Trials: %d, Warmup: %d)",
        provider_name,
        is_real_provider,
        trials,
        warmup,
    )

    # 1. Warmup
    if warmup > 0:
        logger.info("Executing %d warmup iterations...", warmup)
        for _ in range(warmup):
            test_anomaly = CostScenarioRegistry.generate_scenario_anomaly("compute_spike")
            await client.decide(test_anomaly)

    # 2. Benchmark execution
    results: List[Dict[str, Any]] = []
    logger.info("Running benchmark measurement trials...")

    for trial_idx in range(1, trials + 1):
        for scenario_id in scenarios:
            anomaly: CostAnomaly = CostScenarioRegistry.generate_scenario_anomaly(scenario_id)

            t0 = time.perf_counter()
            trace = await client.decide(anomaly)
            e2e_latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)

            results.append({
                "trial": trial_idx,
                "scenario_id": scenario_id,
                "service": anomaly.service,
                "provider": trace.provider,
                "model_id": trace.model_id,
                "action": trace.action,
                "confidence": trace.confidence,
                "probabilities": json.dumps(trace.probabilities),
                "decision_latency_ms": trace.latency_ms,
                "e2e_latency_ms": e2e_latency_ms,
                "is_fallback": trace.is_fallback,
                "fallback_reason": trace.fallback_reason or "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    # 3. Statistical summary
    decision_latencies = [r["decision_latency_ms"] for r in results]
    e2e_latencies = [r["e2e_latency_ms"] for r in results]

    summary = {
        "benchmark_metadata": {
            "provider": provider_name,
            "model_id": reported_model,
            "measurement_type": measurement_type,
            "real_model_measurement": is_real_provider,
            "trials_per_scenario": trials,
            "total_evaluations": len(results),
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "runtime_environment": {
                "python_version": platform.python_version(),
                "system": platform.system(),
                "machine": platform.machine(),
            },
        },
        "decision_latency_ms": {
            "min": round(min(decision_latencies), 3),
            "max": round(max(decision_latencies), 3),
            "mean": round(statistics.mean(decision_latencies), 3),
            "median": round(statistics.median(decision_latencies), 3),
            "p95": calculate_p95(decision_latencies),
        },
        "e2e_latency_ms": {
            "min": round(min(e2e_latencies), 3),
            "max": round(max(e2e_latencies), 3),
            "mean": round(statistics.mean(e2e_latencies), 3),
            "median": round(statistics.median(e2e_latencies), 3),
            "p95": calculate_p95(e2e_latencies),
        },
        "action_distribution": {
            action: sum(1 for r in results if r["action"] == action)
            for action in set(r["action"] for r in results)
        },
        "fallback_count": sum(1 for r in results if r["is_fallback"]),
    }

    # 4. Save results to disk
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_file = out_path / f"benchmark_summary_{timestamp_slug}.json"
    csv_file = out_path / f"benchmark_trials_{timestamp_slug}.csv"

    with open(json_file, "w") as f:
        json.dump(summary, f, indent=2)

    if results:
        fieldnames = list(results[0].keys())
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    logger.info("Benchmark complete. Results written to %s and %s", json_file, csv_file)
    print("\n" + "=" * 80)
    print(f"BENCHMARK RESULTS SUMMARY (Provider: {provider_name} | Type: {measurement_type})")
    print("=" * 80)
    print(f"Real Model Measurement:   {is_real_provider}")
    print(f"Total Evaluations:        {summary['benchmark_metadata']['total_evaluations']}")
    print(f"Decision Latency Median: {summary['decision_latency_ms']['median']} ms (p95: {summary['decision_latency_ms']['p95']} ms)")
    print(f"E2E Latency Median:      {summary['e2e_latency_ms']['median']} ms (p95: {summary['e2e_latency_ms']['p95']} ms)")
    print(f"Action Distribution:     {summary['action_distribution']}")
    print(f"Fallback Count:          {summary['fallback_count']}")
    print("=" * 80 + "\n")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strands Decider 2B Benchmark Experiment")
    parser.add_argument("--trials", type=int, default=10, help="Number of trials per scenario")
    parser.add_argument("--warmup", type=int, default=2, help="Number of warmup iterations")
    parser.add_argument("--output", type=str, default="scripts/benchmark_results", help="Output directory")
    parser.add_argument("--provider", type=str, default=None, help="Provider to test (mock, http)")

    args = parser.parse_args()
    asyncio.run(run_benchmark(trials=args.trials, warmup=args.warmup, output_dir=args.output, provider=args.provider))
