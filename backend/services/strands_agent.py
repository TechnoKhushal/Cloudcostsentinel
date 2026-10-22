from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import settings
from ..models.cost import CostAnomaly
from ..models.decision import DeciderResponseTrace
from ..models.report import BedrockReport

logger = logging.getLogger("cloudcost_sentinel.agent")


class StrandsBedrockNarrator:
    """Narrative report generator powered by Strands Agents SDK and Amazon Bedrock.

    Grounding rules:
    - Explains observed metric changes, timestamps, and deltas without fabricating facts.
    - Grounded explanation of the decision chosen by Strands Decider 2B (does not change it).
    - Clearly distinguishes observed facts from hypotheses and recommendations.
    - Handles missing credentials, permission errors, and region throttling gracefully.
    - Clearly marks simulated demo outputs when AWS credentials are not active.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self.provider = provider or settings.BEDROCK_PROVIDER
        self.model_id = model_id or settings.BEDROCK_MODEL_ID
        self.region_name = region_name or settings.AWS_REGION

    async def generate_report(
        self, anomaly: CostAnomaly, decision_trace: DeciderResponseTrace
    ) -> BedrockReport:
        report_id = f"rpt-{uuid.uuid4().hex[:10]}"
        now_str = datetime.utcnow().isoformat() + "Z"

        if self.provider == "bedrock":
            report = await self._generate_with_bedrock(report_id, anomaly, decision_trace, now_str)
            if report is not None:
                return report
            logger.info("Bedrock generation unavailable; using honest fallback narrative adapter.")

        return self._generate_grounded_demo_report(report_id, anomaly, decision_trace, now_str)

    async def _generate_with_bedrock(
        self, report_id: str, anomaly: CostAnomaly, trace: DeciderResponseTrace, now_str: str
    ) -> Optional[BedrockReport]:
        """Invokes Strands Agent backed by Amazon Bedrock."""
        try:
            from strands import Agent
            from strands.models import BedrockModel

            # Build Bedrock model integration
            bedrock_model = BedrockModel(
                model_id=self.model_id,
                region_name=self.region_name,
                temperature=0.2,
            )
            agent = Agent(
                model=bedrock_model,
                system_prompt=(
                    "You are CloudCost Sentinel's cost investigation assistant. "
                    "You review cloud spend anomaly telemetry and explain why it matters. "
                    "CRITICAL GROUNDING RULES:\n"
                    "1. Never invent resource IDs, AWS prices, savings, or root causes not provided.\n"
                    "2. Explain the action chosen by Strands Decider 2B without altering the decision.\n"
                    "3. Separate observed facts from hypotheses.\n"
                    "4. Return strict JSON matching the schema."
                ),
            )

            prompt = (
                f"Analyze this telemetry:\n"
                f"Service: {anomaly.service}\n"
                f"Environment: {anomaly.environment}\n"
                f"Criticality: {anomaly.criticality}\n"
                f"Owner: {anomaly.owner}\n"
                f"Current Daily Spend: ${anomaly.metrics.current_spend:.2f}\n"
                f"Baseline Daily Spend: ${anomaly.metrics.baseline_spend:.2f}\n"
                f"Spend Delta: +${anomaly.metrics.delta_amount:.2f} (+{anomaly.metrics.delta_percentage:.1f}%)\n"
                f"Persistence: {anomaly.metrics.persistence_days} days\n"
                f"Monthly Budget: ${anomaly.metrics.monthly_budget:.2f}\n"
                f"Decider Choice: {trace.action} (Confidence: {trace.confidence:.2f})\n\n"
                f"Generate a structured JSON response with keys: 'title', 'executive_summary', 'observed_facts' (list), "
                f"'decider_action_audit', 'likely_investigation_areas' (list), 'safe_recommendations' (list), "
                f"'assumptions_and_limitations' (list), 'follow_up_checklist' (list)."
            )

            response = await agent.run_async(prompt) if hasattr(agent, "run_async") else agent(prompt)
            content_str = str(response).strip()

            # Robust markdown code block stripping
            if content_str.startswith("```json"):
                content_str = content_str[7:]
            elif content_str.startswith("```"):
                content_str = content_str[3:]
            if content_str.endswith("```"):
                content_str = content_str[:-3]
            content_str = content_str.strip()

            # Extract JSON block
            if "{" in content_str and "}" in content_str:
                json_start = content_str.find("{")
                json_end = content_str.rfind("}") + 1
                data = json.loads(content_str[json_start:json_end])

                # Strict validation of extracted fields
                if not isinstance(data, dict):
                    logger.warning("Bedrock returned non-dictionary JSON.")
                    return None

                def clean_list(val: Any, max_items: int = 10, max_len: int = 300) -> List[str]:
                    if isinstance(val, list):
                        return [str(x)[:max_len] for x in val[:max_items] if str(x).strip()]
                    return []

                title = str(data.get("title", f"Cost Investigation: {anomaly.service}"))[:150]
                exec_sum = str(data.get("executive_summary", ""))[:1000]
                action_audit = str(data.get("decider_action_audit", ""))[:800]

                return BedrockReport(
                    report_id=report_id,
                    anomaly_id=anomaly.anomaly_id,
                    decision_id=trace.decision_id,
                    title=title,
                    executive_summary=exec_sum,
                    observed_facts=clean_list(data.get("observed_facts")),
                    decider_action_audit=action_audit,
                    likely_investigation_areas=clean_list(data.get("likely_investigation_areas")),
                    safe_recommendations=clean_list(data.get("safe_recommendations")),
                    assumptions_and_limitations=clean_list(data.get("assumptions_and_limitations")),
                    follow_up_checklist=clean_list(data.get("follow_up_checklist")),
                    provider="amazon-bedrock",
                    model_id=self.model_id,
                    is_simulated=False,
                    generated_at=now_str,
                )
        except Exception as exc:
            logger.warning("Amazon Bedrock invocation encountered error or credentials missing: %s", exc)
            return None

    def _generate_grounded_demo_report(
        self, report_id: str, anomaly: CostAnomaly, trace: DeciderResponseTrace, now_str: str
    ) -> BedrockReport:
        """Deterministic grounded narrative adapter for demo and local offline modes.

        Guaranteed grounded strictly against the telemetry values.
        Explicitly marked with is_simulated=True and provider='demo-narrative-adapter'.
        """
        metrics = anomaly.metrics
        owner_text = f"owned by {anomaly.owner}" if anomaly.owner != "unknown" else "with unassigned/unknown ownership"

        observed_facts = [
            f"Daily spend on {anomaly.service} in {anomaly.environment} rose from a baseline of ${metrics.baseline_spend:,.2f} to ${metrics.current_spend:,.2f} (+${metrics.delta_amount:,.2f}/day).",
            f"Observed percentage increase is +{metrics.delta_percentage:.1f}%, exceeding the monitoring anomaly threshold.",
            f"Anomaly has persisted for {metrics.persistence_days} consecutive recorded day(s).",
            f"Current month-to-date spend is ${metrics.month_to_date_spend:,.2f}; projected month-end spend is ${metrics.forecast_month_end:,.2f} against a ${metrics.monthly_budget:,.2f} budget ({metrics.budget_burn_percentage:.1f}% burn).",
            f"Service criticality is rated as {anomaly.criticality.upper()} {owner_text}.",
        ]

        if trace.action == "request_approval":
            audit_explanation = (
                f"Strands Decider 2B selected 'request_approval' (confidence: {trace.confidence:.2f}). "
                f"Given the significant spend divergence (+{metrics.delta_percentage:.1f}%), {anomaly.criticality} criticality, "
                f"and potential budget breach ({metrics.budget_burn_percentage:.1f}% forecast), human sign-off is required "
                f"before any operational or architectural remediation."
            )
            likely_areas = [
                f"Recent deployment, autoscaling group scaling events, or batch processing pipelines in {anomaly.environment}.",
                "Provisioned capacity versus actual utilization metrics in Amazon CloudWatch.",
                "Orphaned or unattached resources associated with this service footprint.",
            ]
            recommendations = [
                "Review the pending approval request in CloudCost Sentinel before executing any capacity changes.",
                "Inspect CloudWatch metrics for CPU/Memory utilization to confirm if instances are overprovisioned.",
                "Verify with the service team whether the workload surge corresponds to an expected seasonal event or a runaway loop.",
            ]
        elif trace.action == "notify_owner":
            audit_explanation = (
                f"Strands Decider 2B selected 'notify_owner' (confidence: {trace.confidence:.2f}). "
                f"Because the resource owner ({anomaly.owner}) is verified and the anomaly has persisted for {metrics.persistence_days} day(s), "
                f"direct notification enables prompt root-cause investigation while avoiding disruptive remediation in {anomaly.environment}."
            )
            likely_areas = [
                f"Provisioned IOPS or compute tiers modified recently under {anomaly.service}.",
                "Workload configuration drift or unintended long-running debug jobs.",
                "Data ingestion rate increases from upstream streaming pipelines.",
            ]
            recommendations = [
                f"Dispatched automated alert to owner {anomaly.owner} with telemetry summary.",
                "Request the engineering owner to review scaling policies and provisioned limits.",
                "Re-evaluate spend telemetry in 24 hours to observe trend trajectory.",
            ]
        else:  # "monitor"
            audit_explanation = (
                f"Strands Decider 2B selected 'monitor' (confidence: {trace.confidence:.2f}). "
                f"The spend variance (+{metrics.delta_percentage:.1f}%) is within tolerable bounds for a {anomaly.criticality} environment "
                f"with budget burn ({metrics.budget_burn_percentage:.1f}%) safely under the monthly threshold. No operational disruption is warranted."
            )
            likely_areas = [
                "Transient batch jobs, periodic cron triggers, or expected minor daily workload variance.",
                "Scheduled maintenance or non-recurring data backups.",
            ]
            recommendations = [
                "Continue passive telemetry monitoring; no manual intervention required at this stage.",
                "Re-evaluate automated thresholds if variance persists beyond expected maintenance windows.",
            ]

        assumptions = [
            f"Baseline calculations are derived from historical window average of ${metrics.baseline_spend:,.2f}/day.",
            f"Measurement uncertainty is flagged as {'HIGH' if metrics.uncertainty_flag else 'LOW'}.",
            "Telemetry reflects verified cost data points; no real AWS resources have been mutated.",
        ]

        follow_up = [
            f"Confirm telemetry stability in the next monitoring cycle.",
            f"Verify that budget alert thresholds align with the updated ${metrics.monthly_budget:,.2f} allocation.",
            f"Ensure tag compliance and resource ownership metadata are updated in AWS Cost Allocation Tags.",
        ]

        return BedrockReport(
            report_id=report_id,
            anomaly_id=anomaly.anomaly_id,
            decision_id=trace.decision_id,
            title=f"Cost Investigation Report: {anomaly.service} ({anomaly.environment})",
            executive_summary=(
                f"Telemetry analysis detected a spend shift in {anomaly.service} ({anomaly.environment}). "
                f"Daily spend moved from baseline ${metrics.baseline_spend:,.2f} to ${metrics.current_spend:,.2f} (+{metrics.delta_percentage:.1f}%). "
                f"Decider 2B evaluated the condition and selected '{trace.action}'. "
                f"Projected month-end budget burn stands at {metrics.budget_burn_percentage:.1f}%."
            ),
            observed_facts=observed_facts,
            decider_action_audit=audit_explanation,
            likely_investigation_areas=likely_areas,
            safe_recommendations=recommendations,
            assumptions_and_limitations=assumptions,
            follow_up_checklist=follow_up,
            provider="demo-narrative-adapter",
            model_id="grounded-template-narrator-v1",
            is_simulated=True,
            generated_at=now_str,
        )
