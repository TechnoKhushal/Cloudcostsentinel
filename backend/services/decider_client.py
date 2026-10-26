from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx

from ..config import settings
from ..models.cost import CostAnomaly
from ..models.decision import (
    DeciderAction,
    DeciderNormalizedState,
    DeciderQuestionSpec,
    DeciderResponseTrace,
)
from .confidence import mock_confidence

logger = logging.getLogger("cloudcost_sentinel.decider")


class DeciderClient:
    """Client for Strands Decider 2B model.

    Supports:
    1. "http" - Live HTTP call to Strands Decider System One endpoint (POST /v1/systemone).
    2. "inprocess" - In-process execution with PyTorch StrandsDeciderModel when weights are loaded.
    3. "mock" - Deterministic simulated adapter for tests/demos lacking GPU or local server.
       IMPORTANT: All mock responses are prominently marked with provider="mock-simulated"
       and model_id="demo-policy-evaluator-v1". They are never mislabeled as real Decider 2B.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        model_id: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ):
        self.provider = provider or settings.DECIDER_PROVIDER
        self.endpoint_url = endpoint_url or settings.STRANDS_DECIDER_URL
        self.model_id = model_id or settings.DECIDER_MODEL_ID
        self.min_confidence = min_confidence if min_confidence is not None else settings.DECIDER_MIN_CONFIDENCE

    def build_normalized_state(self, anomaly: CostAnomaly) -> DeciderNormalizedState:
        """Create a compact, normalized state representation for Decider 2B."""
        return DeciderNormalizedState(
            service=anomaly.service,
            environment=anomaly.environment,
            criticality=anomaly.criticality,
            known_owner=anomaly.owner,
            current_daily_spend=anomaly.metrics.current_spend,
            baseline_daily_spend=anomaly.metrics.baseline_spend,
            spend_delta_amount=anomaly.metrics.delta_amount,
            spend_delta_percentage=anomaly.metrics.delta_percentage,
            persistence_days=anomaly.metrics.persistence_days,
            monthly_budget=anomaly.metrics.monthly_budget,
            budget_burn_percentage=anomaly.metrics.budget_burn_percentage,
            forecast_month_end=anomaly.metrics.forecast_month_end,
            uncertainty_flag=anomaly.metrics.uncertainty_flag,
        )

    def build_question(self) -> Dict[str, Any]:
        """Build the public HTTP wire representation for a choice question."""
        spec = DeciderQuestionSpec()
        return {
            "type": "choice",
            "instructions": spec.instructions,
            "criteria": spec.criteria,
        }

    async def decide(self, anomaly: CostAnomaly) -> DeciderResponseTrace:
        """Execute the signature decision on the main execution path.

        Evaluates:
        Given spend anomaly, budget pressure, persistence, criticality and ownership,
        should the agent:
          - 'monitor'
          - 'notify_owner'
          - 'request_approval'
        """
        decision_id = f"dec-{uuid.uuid4().hex[:10]}"
        timestamp = datetime.utcnow().isoformat() + "Z"
        normalized_state = self.build_normalized_state(anomaly)
        compact_state_str = normalized_state.to_compact_str()
        question = self.build_question()
        question_spec = DeciderQuestionSpec()

        start_time = time.perf_counter()

        # Route to configured provider
        if self.provider == "http":
            choice, probs, confidence, model_name, is_err, err_msg = await self._call_http_decider(
                compact_state_str, question
            )
            provider_label = "strands-decider-2b-http"
        elif self.provider == "inprocess":
            # Disabled — raises NotImplementedError; caught as provider error below
            try:
                choice, probs, confidence, model_name, is_err, err_msg = self._call_inprocess_decider(
                    compact_state_str, question
                )
            except NotImplementedError as exc:
                choice, probs, confidence, model_name = "request_approval", {}, 0.0, self.model_id
                is_err, err_msg = True, str(exc)
            provider_label = "strands-decider-2b-inprocess"
        else:
            choice, probs, confidence, model_name, is_err, err_msg = self._call_mock_decider(
                anomaly, normalized_state
            )
            if self.provider == "rules":
                provider_label = "deterministic-policy-rules"
                model_name = "cloud-cost-policy-rules-v1"
            else:
                provider_label = "mock-simulated"

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # Preserve raw model output before any policy override
        raw_model_action: Optional[str] = choice if not is_err else None
        raw_model_confidence: Optional[float] = round(confidence, 4) if not is_err else None

        # Configurable low-confidence & safety fallback check
        is_fallback = False
        fallback_reason = None
        final_action = choice

        if is_err:
            is_fallback = True
            final_action = "request_approval"
            fallback_reason = f"Provider error: {err_msg}. Safely defaulting to human review."
            logger.warning("Decider provider error, fallback applied: %s", fallback_reason)
        elif confidence < self.min_confidence:
            is_fallback = True
            final_action = "request_approval"
            fallback_reason = (
                f"Decider confidence {confidence:.3f} is below safety threshold {self.min_confidence:.3f}. "
                f"Conservatively escalating to request_approval for safety."
            )
            logger.info("Decider confidence below threshold (%.3f < %.3f). Fallback to request_approval.", confidence, self.min_confidence)

        # Determine executed action details based on final choice
        executed_action, executed_details = self._route_operational_response(
            final_action, anomaly, is_fallback, fallback_reason
        )

        trace = DeciderResponseTrace(
            decision_id=decision_id,
            timestamp=timestamp,
            action=final_action,
            confidence=round(confidence, 4),
            raw_model_action=raw_model_action,
            raw_model_confidence=raw_model_confidence,
            probabilities={k: round(v, 4) for k, v in probs.items()},
            latency_ms=latency_ms,
            model_id=model_name,
            provider=provider_label,
            is_fallback=is_fallback,
            fallback_reason=fallback_reason,
            question=question_spec,
            normalized_state=compact_state_str,
            executed_action=executed_action,
            executed_details=executed_details,
        )

        return trace

    async def _call_http_decider(
        self, state_str: str, question: Dict[str, Any]
    ) -> Tuple[DeciderAction, Dict[str, float], float, str, bool, Optional[str]]:
        """Call real Strands Decider 2B served over HTTP with strict response validation."""
        import math

        ALLOWED_ACTIONS: set = {"monitor", "notify_owner", "request_approval"}
        request_payload = {
            "state": state_str,
            "model": self.model_id,
            "questions": {"operational_response": question},
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.endpoint_url,
                    json=request_payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("model"), str)
                    or not isinstance(data.get("answers"), dict)
                    or not isinstance(data.get("usage"), dict)
                ):
                    return "request_approval", {}, 0.0, self.model_id, True, "Decider returned an invalid System One response"
                usage = data["usage"]
                if any(
                    not isinstance(usage.get(field), int) or usage[field] < 0
                    for field in ("input_tokens", "output_tokens")
                ):
                    return "request_approval", {}, 0.0, self.model_id, True, "Decider returned invalid token usage"
                answer = data["answers"].get("operational_response")
                if not isinstance(answer, dict) or answer.get("type") != "choice":
                    return "request_approval", {}, 0.0, self.model_id, True, "Unexpected answer type from Decider"

                # --- Strict validation of model response ---
                action = answer.get("choice")
                if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
                    return "request_approval", {}, 0.0, self.model_id, True, (
                        f"Decider returned unrecognised action '{action}'; must be one of {ALLOWED_ACTIONS}"
                    )

                probs = answer.get("probabilities")
                if not isinstance(probs, dict) or not probs:
                    return "request_approval", {}, 0.0, self.model_id, True, "Decider returned empty/invalid probabilities"

                for k, v in probs.items():
                    if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v) or not (0.0 <= v <= 1.0):
                        return "request_approval", {}, 0.0, self.model_id, True, (
                            f"Decider probability for '{k}' is out of range or non-finite: {v}"
                        )

                prob_sum = sum(probs.values())
                if abs(prob_sum - 1.0) > 0.05:
                    return "request_approval", {}, 0.0, self.model_id, True, (
                        f"Decider probabilities do not sum to 1.0 (sum={prob_sum:.4f})"
                    )

                conf = answer.get("confidence")
                if not isinstance(conf, (int, float)):
                    return "request_approval", {}, 0.0, self.model_id, True, "Decider confidence is missing or invalid"
                if math.isnan(conf) or math.isinf(conf) or not (0.0 <= conf <= 1.0):
                    return "request_approval", {}, 0.0, self.model_id, True, (
                        f"Decider confidence is out of range or non-finite: {conf}"
                    )

                return (
                    action,  # type: ignore[return-value]
                    probs,
                    conf,
                    data["model"],
                    False,
                    None,
                )
        except Exception as exc:
            logger.error("HTTP Decider invocation failed: %s", exc)
            return "request_approval", {"monitor": 0.33, "notify_owner": 0.33, "request_approval": 0.34}, 0.0, self.model_id, True, str(exc)

    def _call_inprocess_decider(
        self, state_str: str, question: Dict[str, Any]
    ) -> Tuple[DeciderAction, Dict[str, float], float, str, bool, Optional[str]]:
        """In-process Strands Decider path — NOT a real inference path.

        This method exists as a stub. The in-process provider is disabled because
        returning hard-coded probabilities here would misrepresent them as real
        model inference.  To use the real Strands Decider 2B, run:

            strands-decider serve --model StrandsAgents/strands-decider-2B-hobson-v19

        then set DECIDER_PROVIDER=http and STRANDS_DECIDER_URL=http://127.0.0.1:8080/v1/systemone.
        """
        raise NotImplementedError(
            "The 'inprocess' provider is disabled. It cannot perform real model inference without "
            "loaded weights and PyTorch. Use DECIDER_PROVIDER=http and point STRANDS_DECIDER_URL "
            "to a running 'strands-decider serve' instance instead."
        )

    def _call_mock_decider(
        self, anomaly: CostAnomaly, state: DeciderNormalizedState
    ) -> Tuple[DeciderAction, Dict[str, float], float, str, bool, Optional[str]]:
        """Deterministic, calibrated mock evaluator for tests and credential-free demos.

        Labels: provider="mock-simulated", model="demo-policy-evaluator-v1".
        Calibrated probabilities use a normalized top-choice score relative to a uniform
        distribution: (N * p_max - 1) / (N - 1).
        """
        # If measurement is uncertain or sparse data, create low confidence distribution below safety threshold
        if state.uncertainty_flag:
            probs = {"monitor": 0.34, "notify_owner": 0.33, "request_approval": 0.33}
            conf = mock_confidence(probs.values())  # 0.34, below the 0.65 threshold
            return "request_approval", probs, conf, "demo-policy-evaluator-v1", False, None

        # Critical service with high spend spike (+50% or +$400/day) or unassigned owner -> request_approval
        if (state.criticality in ("critical", "high") and (state.spend_delta_percentage > 50 or state.spend_delta_amount > 400)) or state.known_owner == "unknown":
            probs = {"monitor": 0.04, "notify_owner": 0.12, "request_approval": 0.84}
            choice: DeciderAction = "request_approval"

        # Known owner with moderate spike and active persistence -> notify_owner
        elif state.spend_delta_percentage >= 20.0 and state.known_owner != "unknown":
            probs = {"monitor": 0.08, "notify_owner": 0.81, "request_approval": 0.11}
            choice = "notify_owner"

        # Minor fluctuation or normal baseline -> monitor
        else:
            probs = {"monitor": 0.86, "notify_owner": 0.10, "request_approval": 0.04}
            choice = "monitor"

        conf = mock_confidence(probs.values())
        return choice, probs, conf, "demo-policy-evaluator-v1", False, None

    def _route_operational_response(
        self,
        action: DeciderAction,
        anomaly: CostAnomaly,
        is_fallback: bool,
        fallback_reason: Optional[str],
    ) -> Tuple[str, Dict[str, Any]]:
        """Downstream routing strictly governed by Decider choice."""
        if action == "monitor":
            return (
                "LOG_FOR_OBSERVATION",
                {
                    "message": f"Service {anomaly.service} marked for observation. Next evaluation in 24 hours.",
                    "alert_dispatched": False,
                    "remediation_blocked": False,
                },
            )
        elif action == "notify_owner":
            recipient = anomaly.owner if anomaly.owner != "unknown" else "cloud-ops-triage@company.internal"
            from .notification_service import NotificationService
            notif_service = NotificationService()
            notif_res = notif_service.dispatch_anomaly_notification(anomaly, recipient)
            return (
                "DISPATCH_OWNER_NOTIFICATION",
                {
                    "recipient": recipient,
                    "subject": f"[CloudCost Sentinel] Spend Anomaly in {anomaly.service} ({anomaly.environment})",
                    "delta_amount": anomaly.metrics.delta_amount,
                    "delta_percentage": anomaly.metrics.delta_percentage,
                    "notification_status": notif_res.status,
                    "notification_provider": notif_res.provider,
                    "requires_manual_approval": False,
                },
            )
        else:  # "request_approval"
            # Rough modelled estimate based on 30 days and 85% remediation efficiency
            daily_excess = max(0.0, anomaly.metrics.delta_amount)
            est_monthly_savings = round(daily_excess * 30.0 * 0.85, 2)  # 85% remediation efficiency
            return (
                "CREATE_APPROVAL_REVIEW_ITEM",
                {
                    "approval_required": True,
                    "service": anomaly.service,
                    "environment": anomaly.environment,
                    "estimated_monthly_savings": est_monthly_savings,
                    "savings_model_assumptions": "Rough modelled estimate based on 30-day projected excess spend at 85% remediation efficiency.",
                    "safety_override": is_fallback,
                    "override_reason": fallback_reason,
                    "remediation_type": "SCALE_OR_RIGHTSIZE_RESOURCES",
                },
            )
