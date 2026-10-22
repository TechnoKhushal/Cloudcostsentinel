"""Reusable Decision Pattern: Threshold-Aware Anomaly Response (#strands-decider-2b #policy).

Pattern Category: Policy Decision Pattern
Domain Demonstrator: CloudCost Sentinel (Cloud Spending Anomaly Triage)
Upstream Engine: Strands Decider 2B (StrandsAgents/strands-decider-2B-hobson-v19)

This module encapsulates the generic, typed decision pattern:
Given:
- A telemetry anomaly (metric delta amount, percentage, duration/persistence, environment criticality)
- Contextual state (budget burn, verified owner, uncertainty flags)
Decider 2B evaluates:
- monitor: passive observation, re-evaluate next cycle.
- notify_owner: verified owner alert, fast triage without operational disruption.
- request_approval: escalation to human reviewer for mutation/remediation sign-off.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from strands_decider.schema import (
    ChoiceAnswer,
    ChoiceQuestion,
    SystemOneRequest,
    SystemOneResponse,
    derive_confidence,
)

logger = logging.getLogger("patterns.threshold_aware_anomaly_response")

PolicyAction = Literal["monitor", "notify_owner", "request_approval"]


@dataclass
class AnomalyState:
    """Generic normalized state representation for the Policy pattern."""

    entity_id: str
    category: str
    criticality: str  # e.g., "low", "medium", "high", "critical"
    assigned_owner: str
    current_value: float
    baseline_value: float
    delta_amount: float
    delta_percentage: float
    persistence_count: int
    threshold_limit: float
    burn_percentage: float
    uncertainty_flag: bool

    def to_compact_str(self) -> str:
        owner_status = f"verified ({self.assigned_owner})" if self.assigned_owner and self.assigned_owner != "unknown" else "unassigned / unknown"
        return (
            f"Entity: {self.entity_id} | Category: {self.category} | Criticality: {self.criticality.upper()}\n"
            f"Observed Delta: +{self.delta_amount:,.2f} (+{self.delta_percentage:.1f}%) above baseline {self.baseline_value:,.2f}\n"
            f"Current Value: {self.current_value:,.2f} | Persistence: {self.persistence_count} cycles\n"
            f"Threshold Utilization: {self.burn_percentage:.1f}% of limit {self.threshold_limit:,.2f}\n"
            f"Ownership: {owner_status} | Measurement Uncertainty: {'HIGH' if self.uncertainty_flag else 'LOW'}"
        )


@dataclass
class PolicyDecisionResult:
    action: PolicyAction
    confidence: float
    probabilities: Dict[str, float]
    model_id: str
    provider: str
    latency_ms: float
    is_fallback: bool
    fallback_reason: Optional[str] = None
    normalized_state_str: str = ""


class ThresholdAwareAnomalyPolicy:
    """Generic, reusable evaluator implementing the Policy pattern with Strands Decider 2B."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:8000/v1/systemone",
        model_id: str = "StrandsAgents/strands-decider-2B-hobson-v19",
        min_confidence: float = 0.65,
        use_mock_fallback: bool = True,
    ):
        self.endpoint_url = endpoint_url
        self.model_id = model_id
        self.min_confidence = min_confidence
        self.use_mock_fallback = use_mock_fallback

    def build_question(self) -> ChoiceQuestion:
        """Constructs the official typed Strands Decider ChoiceQuestion."""
        return ChoiceQuestion(
            type="choice",
            instructions=(
                "Given the spend anomaly, budget pressure, persistence, service criticality "
                "and known ownership, should the agent monitor, notify_owner, or request_approval for remediation?"
            ),
            criteria={
                "monitor": "Observe and re-evaluate without alerting. Appropriate for small fluctuations, low budget impact, or non-critical environments.",
                "notify_owner": "Notify the verified resource owner directly. Appropriate for known service owners with moderate budget pressure or early-stage anomalies.",
                "request_approval": "Escalate to human cloud platform engineer for remediation sign-off. Appropriate for high spend spikes, runaway budget burn, unassigned owners, or critical production environments.",
            },
        )

    async def evaluate(self, state: AnomalyState) -> PolicyDecisionResult:
        """Evaluates state against Decider 2B with strict low-confidence safety handling."""
        state_str = state.to_compact_str()
        question = self.build_question()
        start = time.perf_counter()

        action: PolicyAction = "request_approval"
        probabilities: Dict[str, float] = {}
        confidence: float = 0.0
        model_used = self.model_id
        provider_used = "strands-decider-2b-live"
        is_fallback = False
        fallback_reason = None

        try:
            req = SystemOneRequest(
                state=state_str,
                model=self.model_id,
                questions={"policy_response": question},
            )
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    self.endpoint_url,
                    json=req.model_dump(),
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                parsed = SystemOneResponse.model_validate(data)
                answer = parsed.answers.get("policy_response")
                if isinstance(answer, ChoiceAnswer):
                    action = answer.choice  # type: ignore
                    probabilities = answer.probabilities
                    confidence = answer.confidence
                    model_used = parsed.model
                else:
                    raise ValueError("Unexpected answer format from Decider.")
        except Exception as exc:
            logger.warning("Decider service invocation failed: %s", exc)
            if self.use_mock_fallback:
                action, probabilities, confidence, model_used, provider_used = self._mock_evaluate(state)
            else:
                is_fallback = True
                fallback_reason = f"Decider invocation failed ({exc}); conservatively escalating to request_approval."
                action = "request_approval"

        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)

        # Safety Fallback: Confidence below minimum calibrated threshold
        if not is_fallback and confidence < self.min_confidence:
            is_fallback = True
            action = "request_approval"
            fallback_reason = (
                f"Decider confidence {confidence:.3f} is below minimum calibrated threshold {self.min_confidence:.3f}. "
                f"Conservatively escalating to human approval for safety."
            )

        return PolicyDecisionResult(
            action=action,
            confidence=round(confidence, 4),
            probabilities={k: round(v, 4) for k, v in probabilities.items()},
            model_id=model_used,
            provider=provider_used,
            latency_ms=latency_ms,
            is_fallback=is_fallback,
            fallback_reason=fallback_reason,
            normalized_state_str=state_str,
        )

    def _mock_evaluate(
        self, state: AnomalyState
    ) -> Tuple[PolicyAction, Dict[str, float], float, str, str]:
        """Calibrated mock evaluator when offline, explicitly labeled SIMULATED."""
        if state.uncertainty_flag:
            probs = {"monitor": 0.34, "notify_owner": 0.33, "request_approval": 0.33}
            conf = derive_confidence(list(probs.values()))
            return "request_approval", probs, conf, "demo-policy-evaluator-v1", "mock-simulated"

        if (state.criticality in ("critical", "high") and (state.delta_percentage > 50 or state.delta_amount > 400)) or state.assigned_owner == "unknown":
            probs = {"monitor": 0.04, "notify_owner": 0.12, "request_approval": 0.84}
            choice: PolicyAction = "request_approval"
        elif state.delta_percentage >= 20.0 and state.assigned_owner != "unknown":
            probs = {"monitor": 0.08, "notify_owner": 0.81, "request_approval": 0.11}
            choice = "notify_owner"
        else:
            probs = {"monitor": 0.86, "notify_owner": 0.10, "request_approval": 0.04}
            choice = "monitor"

        conf = derive_confidence(list(probs.values()))
        return choice, probs, conf, "demo-policy-evaluator-v1", "mock-simulated"
