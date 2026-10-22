from __future__ import annotations

import logging
from typing import Any, Optional

from strands.interventions.actions import Confirm, Guide, InterventionAction, Proceed
from strands.interventions.handler import InterventionHandler
from strands.hooks.events import BeforeToolCallEvent

from ..models.cost import CostAnomaly
from ..services.decider_client import DeciderClient

logger = logging.getLogger("cloudcost_sentinel.interventions")


class ThresholdAwareAnomalyIntervention(InterventionHandler):
    """Strands InterventionHandler implementing the Policy decision pattern.

    Maps Strands Decider 2B choices to typed Strands intervention actions:
    - 'monitor'          -> Proceed()
    - 'notify_owner'     -> Guide(feedback="Notify resource owner of active spend drift.")
    - 'request_approval' -> Confirm(prompt="Remediation approval required for spend anomaly.")
    """

    name = "threshold-aware-anomaly-response"

    def __init__(
        self,
        decider_client: Optional[DeciderClient] = None,
        current_anomaly: Optional[CostAnomaly] = None,
    ):
        super().__init__()
        self.decider_client = decider_client or DeciderClient()
        self.current_anomaly = current_anomaly

    def set_anomaly(self, anomaly: CostAnomaly) -> None:
        self.current_anomaly = anomaly

    async def before_tool_call(self, event: BeforeToolCallEvent) -> InterventionAction:
        """Evaluates spend policy before allowing an operational or remediation tool call."""
        if not self.current_anomaly:
            return Proceed(reason="No active anomaly telemetry present; proceeding.")

        # Invoke Decider on the real decision boundary
        trace = await self.decider_client.decide(self.current_anomaly)
        logger.info(
            "Strands Intervention evaluated Decider choice: %s (confidence: %.2f)",
            trace.action,
            trace.confidence,
        )

        if trace.action == "monitor":
            return Proceed(reason=f"Decider chose monitor (confidence {trace.confidence:.2f}). Passive observation.")
        elif trace.action == "notify_owner":
            return Guide(
                feedback=f"Spend anomaly (+{self.current_anomaly.metrics.delta_percentage:.1f}%) requires notifying owner {self.current_anomaly.owner} before mutative operations.",
                reason="Owner notification policy trigger",
            )
        else:  # "request_approval"
            return Confirm(
                prompt=f"Spend spike on {self.current_anomaly.service} (+${self.current_anomaly.metrics.delta_amount:.2f}/day) requires human review and sign-off.",
                reason=f"Decider {trace.action} policy escalation",
            )
