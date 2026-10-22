from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
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

from .auth import AuthenticatedPrincipal, require_reviewer, require_viewer
from .config import settings
from .database.db import ApprovalConflictError, DatabaseRepository
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate startup settings strictly to prevent unsafe production configurations."""
    settings.validate_startup()
    logger.info(
        "CloudCost Sentinel starting in environment='%s', auth_enabled=%s, decider_provider='%s', bedrock_provider='%s'",
        settings.ENVIRONMENT,
        settings.AUTH_ENABLED,
        settings.DECIDER_PROVIDER,
        settings.BEDROCK_PROVIDER,
    )
    yield


app = FastAPI(
    title="CloudCost Sentinel API",
    description="Intelligent Cloud Spend Decision Agent using Strands Decider 2B and Amazon Bedrock",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["http://localhost:5173"],
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
    reviewed_by: Optional[str] = Field(default=None, description="Ignored if authenticated; server uses token principal.")
    notes: Optional[str] = Field(default="Reviewed in CloudCost Sentinel dashboard.", max_length=1000)


# ------------------------------------------------------------------------------
# Health & Readiness Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/health/live", tags=["Health"])
async def get_health_live() -> Dict[str, str]:
    """Cheap, bounded liveness probe (zero external I/O). Suitable for k8s/ECS liveness."""
    return {"status": "ok"}


@app.get("/api/health", tags=["Health"])
@app.get("/api/health/ready", tags=["Health"])
async def get_health() -> Dict[str, Any]:
    """Granular non-secret provider readiness and configuration status.

    Truthfully distinguishes 'simulated', 'configured_unverified', 'connected', and 'disabled'.
    Never returns fake 'ready: true' or leaks secret keys/passwords.
    """
    ce_status = cost_explorer.get_status()

    # Determine truthful Decider status
    if settings.DECIDER_PROVIDER == "mock":
        decider_state = "simulated"
        reported_model = "demo-policy-evaluator-v1"
    elif settings.DECIDER_PROVIDER == "http":
        decider_state = "configured_unverified"
        reported_model = settings.DECIDER_MODEL_ID
    else:
        decider_state = "disabled"
        reported_model = "none"

    # Determine truthful Bedrock status
    if settings.BEDROCK_PROVIDER == "mock":
        bedrock_state = "simulated"
        bedrock_model = "grounded-template-narrator-v1"
    else:
        bedrock_state = "configured_unverified"
        bedrock_model = settings.BEDROCK_MODEL_ID

    return {
        "status": "healthy",
        "service": "CloudCost Sentinel",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "auth": {
            "enabled": settings.AUTH_ENABLED,
            "mode": "jwt_bearer" if settings.AUTH_ENABLED else "development_bypass",
            "warning": (
                "Authentication is disabled: development principal active."
                if not settings.AUTH_ENABLED
                else None
            ),
        },
        "providers": {
            "decider": {
                "provider": settings.DECIDER_PROVIDER,
                "state": decider_state,
                "model_id": reported_model,
                "min_confidence_threshold": settings.DECIDER_MIN_CONFIDENCE,
                "endpoint": settings.STRANDS_DECIDER_URL,
            },
            "bedrock": {
                "provider": settings.BEDROCK_PROVIDER,
                "state": bedrock_state,
                "model_id": bedrock_model,
                "region": settings.AWS_REGION,
            },
            "cost_explorer": ce_status,
            "notifications": {
                "provider": settings.NOTIFICATION_PROVIDER,
                "state": "simulated" if settings.NOTIFICATION_PROVIDER == "mock" else (
                    "disabled" if settings.NOTIFICATION_PROVIDER == "disabled" else "configured"
                ),
            },
        },
        "safety_guarantee": "Read-only telemetry and decision guidance. Zero automatic cloud mutation.",
    }


# ------------------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------------------
@app.get("/api/demo/scenarios", tags=["Scenarios"])
async def get_scenarios(
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> List[Dict[str, str]]:
    """List available deterministic synthetic scenarios."""
    return CostScenarioRegistry.get_all_scenarios()


# ------------------------------------------------------------------------------
# Anomaly Analysis Flow
# ------------------------------------------------------------------------------
@app.post("/api/analyze", tags=["Analysis"])
async def analyze_anomaly(
    req: AnalyzeRequest,
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> Dict[str, Any]:
    """Analyze cloud spend anomaly, invoke Strands Decider 2B, and generate Bedrock report."""
    logger.info(
        "Executing analysis requested by %s for scenario_id: %s (AWS live: %s)",
        principal.email,
        req.scenario_id,
        req.use_aws_cost_explorer,
    )

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
        valid_ids = [s["id"] for s in CostScenarioRegistry.get_all_scenarios()]
        if scenario_id not in valid_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY if hasattr(status, "HTTP_422_UNPROCESSABLE_CONTENT") else 422,
                detail=f"Invalid scenario_id '{scenario_id}'. Available scenarios: {valid_ids}",
            )
        anomaly = CostScenarioRegistry.generate_scenario_anomaly(scenario_id)

    # Persist anomaly
    db.save_anomaly(anomaly)

    # 2. Invoke Strands Decider 2B for signature decision
    trace: DeciderResponseTrace = await decider_client.decide(anomaly)
    db.save_decision_trace(anomaly.anomaly_id, trace)

    # 3. Handle downstream execution path
    approval_item: Optional[ApprovalItem] = None
    if trace.action == "request_approval":
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
            created_at=datetime.now(timezone.utc).isoformat(),
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


# ------------------------------------------------------------------------------
# Decisions and Approvals
# ------------------------------------------------------------------------------
@app.get("/api/decisions", tags=["Decisions"])
async def get_decisions(
    limit: int = Query(default=20, ge=1, le=100),
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> List[DeciderResponseTrace]:
    """Retrieve recent decision traces with bounded limit."""
    return db.get_recent_decisions(limit=limit)


@app.get("/api/approvals", tags=["Approvals"])
async def get_approvals(
    status: Optional[str] = Query(default=None, pattern="^(pending|approved|rejected)$"),
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> List[ApprovalItem]:
    """Retrieve human approval queue."""
    return db.get_approvals(status=status)


@app.post("/api/approvals/{approval_id}/decision", tags=["Approvals"])
async def record_approval_decision(
    approval_id: str,
    req: ApprovalDecisionRequest,
    principal: AuthenticatedPrincipal = Depends(require_reviewer),
) -> ApprovalItem:
    """Record human approve/reject action.

    SAFETY:
    - Reviewer identity is derived strictly from the authenticated principal token.
    - Transitions from pending to approved/rejected exactly once (409 Conflict on replay).
    - Only updates local review queue. Never mutates live cloud resources.
    """
    reviewer_identity = principal.email or principal.sub
    try:
        updated = db.update_approval_status(
            approval_id=approval_id,
            status=req.action,
            reviewed_by=reviewer_identity,
            notes=req.notes,
        )
    except ApprovalConflictError as conflict_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(conflict_err),
        )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval item '{approval_id}' not found.",
        )

    logger.info("Approval %s marked as %s by verified reviewer %s", approval_id, req.action, reviewer_identity)
    return updated


# ------------------------------------------------------------------------------
# Test-Fixture / Protocol Reference endpoint (POST /v1/systemone)
# ------------------------------------------------------------------------------
@app.post("/v1/systemone", tags=["Strands Decider System One Spec"])
async def strands_decider_systemone_endpoint(
    req: SystemOneRequest,
    response: Response,
) -> SystemOneResponse:
    """Reference server implementing the official Strands Decider wire protocol.

    Provides a test-fixture for protocol validation and local tests.
    Responses are tagged with X-Sentinel-Test-Fixture: true.
    """
    response.headers["X-Sentinel-Test-Fixture"] = "true"
    answers: Dict[str, Any] = {}
    for q_name, question in req.questions.items():
        if isinstance(question, ChoiceQuestion):
            opts = list(question.criteria.keys())
            state_text = str(req.state).lower()
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


# ------------------------------------------------------------------------------
# Static Frontend Serving (Single-Container Production & Demo Builds)
# ------------------------------------------------------------------------------
import os
from fastapi.staticfiles import StaticFiles

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
