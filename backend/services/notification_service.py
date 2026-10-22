from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from ..config import settings
from ..models.cost import CostAnomaly

logger = logging.getLogger("cloudcost_sentinel.notifications")

# RFC 5322 simplified email regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class NotificationResult(BaseModel):
    status: str = Field(description="'delivered' | 'queued_simulated' | 'disabled' | 'failed'")
    provider: str
    recipient: str
    is_simulated: bool
    details: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class NotificationService:
    """Notification dispatch service supporting 'disabled', 'mock', and 'sns'."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or settings.NOTIFICATION_PROVIDER

    def is_valid_recipient(self, recipient: str) -> bool:
        if not recipient or recipient in ("unknown", "unassigned"):
            return False
        # Disallow synthetic test domains for live notifications
        if recipient.endswith(".internal") or recipient.endswith(".example") or recipient.endswith("@company.internal"):
            return False
        return bool(EMAIL_REGEX.match(recipient)) or recipient.startswith("arn:aws:sns:")

    def dispatch_anomaly_notification(
        self,
        anomaly: CostAnomaly,
        recipient: str,
        subject: Optional[str] = None,
    ) -> NotificationResult:
        """Dispatch notification to verified service owner."""
        subject = subject or f"[CloudCost Sentinel] Spend Anomaly in {anomaly.service} ({anomaly.environment})"
        body = (
            f"Alert: Spend anomaly detected for service '{anomaly.service}' ({anomaly.environment}).\n"
            f"Spend Delta: +${anomaly.metrics.delta_amount:,.2f}/day (+{anomaly.metrics.delta_percentage:.1f}%)\n"
            f"Baseline: ${anomaly.metrics.baseline_spend:,.2f}/day | Current: ${anomaly.metrics.current_spend:,.2f}/day\n"
            f"Persistence: {anomaly.metrics.persistence_days} days | Monthly Budget: ${anomaly.metrics.monthly_budget:,.2f}\n"
            f"Action: Owner notification dispatched by CloudCost Sentinel. Please review recent workload changes."
        )

        if self.provider == "disabled":
            return NotificationResult(
                status="disabled",
                provider="disabled",
                recipient=recipient,
                is_simulated=True,
                details={"reason": "NOTIFICATION_PROVIDER=disabled"},
            )

        if self.provider == "mock":
            # Deterministic simulated delivery for demos/testing
            logger.info("Mock notification queued for %s: %s", recipient, subject)
            return NotificationResult(
                status="queued_simulated",
                provider="mock-simulated",
                recipient=recipient,
                is_simulated=True,
                details={"subject": subject, "body_preview": body[:120] + "..."},
            )

        if self.provider == "sns":
            # Live AWS SNS delivery
            if not self.is_valid_recipient(recipient) and not settings.NOTIFICATION_SNS_TOPIC_ARN:
                logger.warning("Refusing to send SNS notification to invalid or internal placeholder: %s", recipient)
                return NotificationResult(
                    status="failed",
                    provider="aws-sns",
                    recipient=recipient,
                    is_simulated=False,
                    error="Refused live dispatch: recipient is a placeholder or invalid address.",
                )

            try:
                import boto3
                client = boto3.client("sns", region_name=settings.AWS_REGION)
                topic_arn = settings.NOTIFICATION_SNS_TOPIC_ARN
                if topic_arn:
                    response = client.publish(
                        TopicArn=topic_arn,
                        Subject=subject[:100],  # SNS subject max length 100
                        Message=body,
                    )
                    return NotificationResult(
                        status="delivered",
                        provider="aws-sns",
                        recipient=topic_arn,
                        is_simulated=False,
                        details={"message_id": response.get("MessageId")},
                    )
                else:
                    return NotificationResult(
                        status="failed",
                        provider="aws-sns",
                        recipient=recipient,
                        is_simulated=False,
                        error="NOTIFICATION_SNS_TOPIC_ARN is not configured.",
                    )
            except Exception as exc:
                logger.error("SNS publish failed: %s", exc)
                return NotificationResult(
                    status="failed",
                    provider="aws-sns",
                    recipient=recipient,
                    is_simulated=False,
                    error=str(exc),
                )

        return NotificationResult(
            status="failed",
            provider=self.provider,
            recipient=recipient,
            is_simulated=True,
            error=f"Unknown notification provider: {self.provider}",
        )
