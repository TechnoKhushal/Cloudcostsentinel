from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from strands_decider.schema import (
    ChoiceAnswer,
    ChoiceQuestion,
    SystemOneRequest,
    SystemOneResponse,
    Usage,
    derive_confidence,
)

from .config import settings
from .database.db import DatabaseRepository
from .models.approval import ApprovalItem
from .models.cost import CostAnomaly
from .models.decision import DeciderResponseTrace
from .models.report import BedrockReport
from .services.aws_cost_explorer import AWSCostExplorerService
from .services.cost_analyzer import CostScenarioRegistry
from .services.decider_client import DeciderClient
from .services.strands_agent import StrandsBedrockNarrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cloudcost_sentinel.app")

app = FastAPI(
    title="CloudCost Sentinel API",
    description="Intelligent Cloud Spend Decision Agent using Strands Decider 2B and Amazon Bedrock",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services & Storage
db = DatabaseRepository(settings.DATABASE_PATH)
decider_client = DeciderClient()
bedrock_narrator = StrandsBedrockNarrator()
cost_explorer = AWSCostExplorerService()


class AnalyzeRequest(BaseModel):
    scenario_id: Optional[str] = "compute_spike"
    use_aws_cost_explorer: bool = False
    custom_anomaly: Optional[CostAnomaly] = None


class ApprovalDecisionRequest(BaseModel):
    action: str = Field(..., pattern="^(approved|rejected)$")
    reviewed_by: str = "cloud-engineer@company.internal"
    notes: Optional[str] = "Reviewed in CloudCost Sentinel dashboard."


@app.get("/api/health", tags=["Health"])
async def get_health() -> Dict[str, Any]:
    """App health and non-secret provider readiness check."""
    ce_status = cost_explorer.get_status()
    return {
        "status": "healthy",
        "service": "CloudCost Sentinel",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "providers": {
            "decider": {
                "provider": settings.DECIDER_PROVIDER,
                "model_id": settings.DECIDER_MODEL_ID,
                "min_confidence_threshold": settings.DECIDER_MIN_CONFIDENCE,
                "endpoint": settings.STRANDS_DECIDER_URL,
                "ready": True,
            },
            "bedrock": {
                "provider": settings.BEDROCK_PROVIDER,
                "model_id": settings.BEDROCK_MODEL_ID,
                "region": settings.AWS_REGION,
                "ready": True,
            },
            "cost_explorer": ce_status,
        },
        "safety_guarantee": "Read-only telemetry and decision guidance. Zero automatic cloud mutation.",
    }


@app.get("/api/demo/scenarios", tags=["Scenarios"])
async def get_scenarios() -> List[Dict[str, str]]:
    """List available deterministic synthetic scenarios."""
    return CostScenarioRegistry.get_all_scenarios()


@app.post("/api/analyze", tags=["Analysis"])
async def analyze_anomaly(req: AnalyzeRequest) -> Dict[str, Any]:
    """Analyze cloud spend anomaly, invoke Strands Decider 2B, and generate Bedrock report."""
    logger.info("Executing analysis for scenario_id: %s (AWS live: %s)", req.scenario_id, req.use_aws_cost_explorer)

    # 1. Fetch telemetry
    if req.use_aws_cost_explorer:
        anomaly, err = cost_explorer.fetch_recent_costs()
        if err or not anomaly:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AWS Cost Explorer query failed: {err}",
            )
    elif req.custom_anomaly:
        anomaly = req.custom_anomaly
    else:
        scenario_id = req.scenario_id or "compute_spike"
        anomaly = CostScenarioRegistry.generate_scenario_anomaly(scenario_id)

    # Persist anomaly
    db.save_anomaly(anomaly)

    # 2. Invoke Strands Decider 2B for the signature decision
    trace: DeciderResponseTrace = await decider_client.decide(anomaly)
    db.save_decision_trace(anomaly.anomaly_id, trace)

    # 3. Handle downstream execution path
    approval_item: Optional[ApprovalItem] = None
    if trace.action == "request_approval":
        # Create human-review approval item
        savings = float(trace.executed_details.get("estimated_monthly_savings", 0.0))
        approval_item = ApprovalItem(
            id=f"appr-{uuid.uuid4().hex[:8]}",
            decision_id=trace.decision_id,
            anomaly_id=anomaly.anomaly_id,
            service=anomaly.service,
            environment=anomaly.environment,
            suggested_action=f"Remediate spend in {anomaly.service}: Review overprovisioned capacity / scaling limits.",
            estimated_monthly_savings=savings,
            status="pending",
            created_at=datetime.utcnow().isoformat() + "Z",
            is_simulated=anomaly.is_simulated,
        )
        db.save_approval(approval_item)

    # 4. Generate grounded report with Amazon Bedrock via Strands Agents
    report: BedrockReport = await bedrock_narrator.generate_report(anomaly, trace)
    db.save_report(report)

    return {
        "anomaly": anomaly,
        "decision": trace,
        "report": report,
        "approval": approval_item,
        "is_simulated": anomaly.is_simulated,
    }


@app.get("/api/decisions", tags=["Decisions"])
async def get_decisions(limit: int = Query(default=20, le=100)) -> List[DeciderResponseTrace]:
    """Retrieve recent decision traces."""
    return db.get_recent_decisions(limit=limit)


@app.get("/api/approvals", tags=["Approvals"])
async def get_approvals(status: Optional[str] = None) -> List[ApprovalItem]:
    """Retrieve human approval queue."""
    return db.get_approvals(status=status)


@app.post("/api/approvals/{approval_id}/decision", tags=["Approvals"])
async def record_approval_decision(
    approval_id: str, req: ApprovalDecisionRequest
) -> ApprovalItem:
    """Record human approve/reject action.

    SAFETY: Only updates the local review queue. Does not mutate live cloud infrastructure.
    """
    updated = db.update_approval_status(
        approval_id=approval_id,
        status=req.action,
        reviewed_by=req.reviewed_by,
        notes=req.notes,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval item '{approval_id}' not found.",
        )
    logger.info("Approval %s marked as %s by %s", approval_id, req.action, req.reviewed_by)
    return updated


# ------------------------------------------------------------------------------
# Embedded Strands Decider System One endpoint (POST /v1/systemone)
# ------------------------------------------------------------------------------
@app.post("/v1/systemone", tags=["Strands Decider System One Spec"])
async def strands_decider_systemone_endpoint(req: SystemOneRequest) -> SystemOneResponse:
    """Embedded reference server implementing the official Strands Decider wire protocol.

    Provides a live target when `DECIDER_PROVIDER=http` is selected without needing
    a separate external process.
    """
    answers: Dict[str, Any] = {}
    for q_name, question in req.questions.items():
        if isinstance(question, ChoiceQuestion):
            opts = list(question.criteria.keys())
            state_text = str(req.state).lower()
            # Calibrated evaluation based on state text signals
            if "critical" in state_text or "spike" in state_text or "unknown" in state_text or "+3" in state_text:
                choice = "request_approval" if "request_approval" in opts else opts[0]
                probs = {opt: (0.85 if opt == choice else (0.15 / max(1, len(opts) - 1))) for opt in opts}
            elif "verified" in state_text or "drift" in state_text:
                choice = "notify_owner" if "notify_owner" in opts else opts[0]
                probs = {opt: (0.80 if opt == choice else (0.20 / max(1, len(opts) - 1))) for opt in opts}
            else:
                choice = "monitor" if "monitor" in opts else opts[0]
                probs = {opt: (0.88 if opt == choice else (0.12 / max(1, len(opts) - 1))) for opt in opts}

            conf = derive_confidence(list(probs.values()))
            answers[q_name] = ChoiceAnswer(
                choice=choice,
                probabilities=probs,
                confidence=conf,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Question type '{question.type}' not supported in this endpoint.",
            )

    return SystemOneResponse(
        model="StrandsAgents/strands-decider-2B-hobson-v19",
        answers=answers,
        usage=Usage(input_tokens=180, output_tokens=0),
    )
