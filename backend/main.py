from __future__ import annotations

import logging
import os
import re
import sqlite3
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from .auth import AuthenticatedPrincipal, require_reviewer, require_viewer
from .config import settings
from .database.db import ApprovalConflictError, DatabaseRepository
from .database.supabase import SupabaseRepository, SupabaseStoreError, supabase_repository
from .models.approval import ApprovalItem
from .models.cost import CostAnomaly
from .models.decision import DeciderResponseTrace
from .models.report import InvestigationReport
from .services.aws_cost_explorer import AWSCostExplorerService
from .services.cost_analyzer import CostScenarioRegistry
from .services.confidence import mock_confidence
from .services.decider_client import DeciderClient
from .services.narrator import OpenRouterNarrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cloudcost_sentinel.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate startup settings strictly to prevent unsafe production configurations."""
    settings.validate_startup()
    try:
        db.initialize()
        if settings.ENVIRONMENT == "production" and not await run_in_threadpool(db.check_ready):
            raise RuntimeError("Supabase readiness check failed.")
    except (OSError, sqlite3.Error, SupabaseStoreError, RuntimeError) as exc:
        if isinstance(db, SupabaseRepository):
            logger.error("Supabase startup check failed (%s).", type(exc).__name__)
            raise RuntimeError("Supabase is unavailable or not configured; production startup is blocked.") from None
        database_dir = Path(settings.DATABASE_PATH).expanduser().resolve().parent
        logger.exception("SQLite initialization failed for directory %s", database_dir)
        raise RuntimeError(
            f"SQLite could not initialize directory '{database_dir}': {exc}. Confirm it exists and is writable. "
            "For an ephemeral Render demo without a mounted disk, set DATABASE_PATH=/tmp/cloudcost-sentinel.db; "
            "for persistent data, attach a writable disk and set DATABASE_PATH to its mount."
        ) from None
    if isinstance(db, DatabaseRepository):
        db_file = Path(settings.DATABASE_PATH).expanduser().resolve()
        temporary_dir = Path(tempfile.gettempdir()).resolve()
        if settings.ENVIRONMENT == "demo" and db_file.is_relative_to(temporary_dir):
            logger.warning("Demo SQLite database uses ephemeral temporary storage; records may disappear after restart.")
    logger.info(
        "CloudCost Sentinel starting in environment='%s', auth_enabled=%s, decider_provider='%s', narrator_provider='%s'",
        settings.ENVIRONMENT,
        settings.AUTH_ENABLED,
        settings.DECIDER_PROVIDER,
        "openrouter" if settings.OPENROUTER_API_KEY else "offline",
    )
    yield


app = FastAPI(
    title="CloudCost Sentinel API",
    description="Read-only Cloud Cost Decision Support using deterministic analysis and optional OpenRouter explanations",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(SupabaseStoreError)
async def handle_supabase_store_error(request: Request, exc: SupabaseStoreError) -> JSONResponse:
    if exc.status_code in {401, 403}:
        return JSONResponse(status_code=403, content={"detail": "Workspace access denied."})
    if exc.status_code == 409:
        return JSONResponse(status_code=409, content={"detail": "The requested record conflicts with its current state."})
    logger.warning("Supabase operation failed with status class %s.", str(exc.status_code)[:3])
    return JSONResponse(status_code=503, content={"detail": "Persistent storage is temporarily unavailable. Retry shortly."})


@app.get("/", tags=["Health"], include_in_schema=False)
async def get_root() -> Dict[str, str]:
    """Give operators a harmless pointer to the liveness endpoint at the service root."""
    return {"service": "CloudCost Sentinel API", "health": "/api/health/live"}

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    max_age=600,
)

# Production never constructs or falls back to SQLite. SQLite remains a local/demo
# adapter; production uses PostgREST with the caller's JWT and database RLS.
db: DatabaseRepository | SupabaseRepository = (
    supabase_repository if settings.ENVIRONMENT == "production" else DatabaseRepository(settings.DATABASE_PATH)
)
decider_client = DeciderClient()
narrator = OpenRouterNarrator()
cost_explorer = AWSCostExplorerService()


class AnalyzeRequest(BaseModel):
    scenario_id: Optional[str] = "compute_spike"
    use_aws_cost_explorer: bool = False
    custom_anomaly: Optional[CostAnomaly] = None


_request_hits: Dict[tuple[str, str], List[float]] = {}


@app.middleware("http")
async def request_safety_limits(request: Request, call_next):
    """Bound JSON payloads and public demo request rates per process and client IP."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 65_536:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds 64 KiB."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})

    if settings.ENVIRONMENT == "demo" and request.method == "POST":
        if len(_request_hits) > 10_000:
            now = time.monotonic()
            for stale_key in list(_request_hits):
                remaining = [hit for hit in _request_hits[stale_key] if now - hit < 60]
                if remaining:
                    _request_hits[stale_key] = remaining
                else:
                    del _request_hits[stale_key]
            if len(_request_hits) > 10_000:
                return JSONResponse(status_code=429, content={"detail": "Demo request limiter is at capacity. Try again later."})
        path = request.url.path
        limit = 10 if path == "/api/analyze" else 30 if path.startswith("/api/approvals/") else None
        if limit:
            client = request.client.host if request.client else "unknown"
            key = (client, path)
            now = time.monotonic()
            recent = [hit for hit in _request_hits.get(key, []) if now - hit < 60]
            if len(recent) >= limit:
                return JSONResponse(status_code=429, content={"detail": "Demo request limit reached. Try again in one minute."})
            recent.append(now)
            _request_hits[key] = recent
    return await call_next(request)


class ApprovalDecisionRequest(BaseModel):
    action: str = Field(..., pattern="^(approved|rejected)$")
    reviewed_by: Optional[str] = Field(default=None, description="Ignored if authenticated; server uses token principal.")
    notes: Optional[str] = Field(default="Reviewed in CloudCost Sentinel dashboard.", max_length=1000)


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


# ------------------------------------------------------------------------------
# Health & Readiness Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/health/live", tags=["Health"])
async def get_health_live() -> Dict[str, str]:
    """Cheap, bounded liveness probe (zero external I/O). Suitable for k8s/ECS liveness."""
    return {"status": "ok"}


@app.get("/api/health", tags=["Health"])
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
    elif settings.DECIDER_PROVIDER == "rules":
        decider_state = "available"
        reported_model = "cloud-cost-policy-rules-v1"
    elif settings.DECIDER_PROVIDER == "http":
        decider_state = "configured_unverified"
        reported_model = settings.DECIDER_MODEL_ID
    else:
        decider_state = "disabled"
        reported_model = "none"

    # AI is optional: no key means deterministic offline explanations.
    narrator_state = "configured_unverified" if settings.OPENROUTER_API_KEY else "offline"
    narrator_model = settings.OPENROUTER_MODEL or "none"

    provider_unverified = decider_state == "configured_unverified" or narrator_state == "configured_unverified"
    return {
        "status": "simulated" if settings.ENVIRONMENT == "demo" else ("degraded" if provider_unverified else "healthy"),
        "service": "CloudCost Sentinel",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "auth": {
            "enabled": settings.AUTH_ENABLED,
            "mode": "jwt_bearer" if settings.AUTH_ENABLED else ("explicit_demo" if settings.ENVIRONMENT == "demo" else "development_bypass"),
            "warning": (
                "Shared public demo: approvals and records are synthetic."
                if settings.ENVIRONMENT == "demo"
                else "Authentication is disabled: development principal active."
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
            },
            "narrator": {
                "provider": "openrouter" if settings.OPENROUTER_API_KEY else "offline",
                "state": narrator_state,
                "model_id": narrator_model,
            },
            "cost_explorer": ce_status,
            "notifications": {
                "provider": settings.NOTIFICATION_PROVIDER,
                "state": "simulated" if settings.NOTIFICATION_PROVIDER == "mock" else (
                    "disabled" if settings.NOTIFICATION_PROVIDER == "disabled" else "configured"
                ),
            },
        },
        "persistence": {
            "provider": "supabase" if isinstance(db, SupabaseRepository) else "sqlite",
            "state": "configured_unverified" if isinstance(db, SupabaseRepository) else "demo_or_local",
        },
        "safety_guarantee": "Read-only telemetry and decision guidance. Zero automatic cloud mutation.",
    }


@app.get("/api/health/ready", tags=["Health"])
async def get_health_ready(response: Response) -> Dict[str, Any]:
    """Readiness reflects local storage and required production provider state."""
    database_ready = await run_in_threadpool(db.check_ready)
    decider_state = "simulated" if settings.DECIDER_PROVIDER == "mock" else "available" if settings.DECIDER_PROVIDER == "rules" else "configured_unverified"
    narrator_state = "configured_unverified" if settings.OPENROUTER_API_KEY else "offline"
    providers_ready = settings.ENVIRONMENT == "demo" or (
        decider_state in {"connected", "available"}
    )
    ready = database_ready and providers_ready
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "environment": settings.ENVIRONMENT,
        "checks": {
            "database": "connected" if database_ready else "unavailable",
            "persistence_provider": "supabase" if isinstance(db, SupabaseRepository) else "sqlite",
            "decider": decider_state,
            "narrator": narrator_state,
        },
    }


# ------------------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------------------
@app.get("/api/demo/scenarios", tags=["Scenarios"])
async def get_scenarios(
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> List[Dict[str, str]]:
    """List available deterministic synthetic scenarios."""
    if settings.ENVIRONMENT == "production":
        return []
    return CostScenarioRegistry.get_all_scenarios()


@app.get("/api/account/profile", tags=["Account"])
async def get_account_profile(principal: AuthenticatedPrincipal = Depends(require_viewer)) -> Dict[str, Any]:
    if isinstance(db, SupabaseRepository):
        return await run_in_threadpool(db.get_profile)
    return {"user_id": principal.sub, "display_name": None, "organization_id": None, "role": principal.roles[0]}


@app.put("/api/account/profile", tags=["Account"])
async def update_account_profile(
    req: ProfileUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> Dict[str, Any]:
    if not isinstance(db, SupabaseRepository):
        raise HTTPException(status_code=503, detail="Profile persistence requires the production Supabase workspace.")
    return await run_in_threadpool(db.update_profile, req.display_name)


# ------------------------------------------------------------------------------
# Anomaly Analysis Flow
# ------------------------------------------------------------------------------
@app.post("/api/analyze", tags=["Analysis"])
async def analyze_anomaly(
    req: AnalyzeRequest,
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> Dict[str, Any]:
    """Analyze cloud spend anomaly, invoke Strands Decider 2B, and generate investigation report."""
    logger.info(
        "Executing analysis for authenticated user %s (AWS live: %s)",
        principal.sub[:8],
        req.use_aws_cost_explorer,
    )

    if settings.ENVIRONMENT == "demo" and (req.use_aws_cost_explorer or req.custom_anomaly is not None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public demo accepts synthetic scenario IDs only; live or custom cost data is disabled.",
        )

    # 1. Fetch telemetry
    cost_data_source = "synthetic_scenario"
    data_warnings: List[str] = []
    if req.use_aws_cost_explorer:
        anomaly, err = cost_explorer.fetch_recent_costs()
        cost_data_source = "aws_cost_explorer"
        if err and err.startswith("PARTIAL_DATA:") and anomaly is not None:
            data_warnings.append(err)
            anomaly.metrics.uncertainty_flag = True
        elif err or not anomaly:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AWS Cost Explorer query failed: {err}",
            )
    elif req.custom_anomaly:
        cost_data_source = "custom_supplied"
        anomaly = req.custom_anomaly
    else:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=400, detail="Synthetic scenarios are disabled in production. Connect Cost Explorer or submit validated cost telemetry.")
        scenario_id = req.scenario_id or "compute_spike"
        valid_ids = [s["id"] for s in CostScenarioRegistry.get_all_scenarios()]
        if scenario_id not in valid_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid scenario_id '{scenario_id}'. Available scenarios: {valid_ids}",
            )
        anomaly = CostScenarioRegistry.generate_scenario_anomaly(scenario_id)

    # 2. Invoke Strands Decider 2B for signature decision
    trace: DeciderResponseTrace = await decider_client.decide(anomaly)

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

    # 4. Generate a grounded report with OpenRouter or the deterministic offline fallback
    report: InvestigationReport = await narrator.generate_report(anomaly, trace)
    if isinstance(db, SupabaseRepository):
        await run_in_threadpool(db.save_analysis_bundle, anomaly, cost_data_source, trace, approval_item, report)
    else:
        await run_in_threadpool(db.save_anomaly, anomaly)
        await run_in_threadpool(db.save_decision_trace, anomaly.anomaly_id, trace)
        if approval_item:
            await run_in_threadpool(db.save_approval, approval_item)
        await run_in_threadpool(db.save_report, report)

    return {
        "anomaly": anomaly,
        "decision": trace,
        "report": report,
        "approval": approval_item,
        "is_simulated": anomaly.is_simulated,
        "cost_data_source": cost_data_source,
        "partial_data": bool(data_warnings),
        "data_warnings": data_warnings,
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
    return await run_in_threadpool(db.get_recent_decisions, limit=limit)


@app.get("/api/approvals", tags=["Approvals"])
async def get_approvals(
    status: Optional[str] = Query(default=None, pattern="^(pending|approved|rejected)$"),
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> List[ApprovalItem]:
    """Retrieve human approval queue."""
    return await run_in_threadpool(db.get_approvals, status=status)


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
    reviewer_identity = principal.sub
    try:
        updated = await run_in_threadpool(
            db.update_approval_status,
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

    logger.info("Approval %s marked as %s by verified reviewer %s", approval_id, req.action, principal.sub[:8])
    return updated


@app.get("/api/reports/{report_id}/download", tags=["Reports"])
async def create_report_download(
    report_id: str,
    principal: AuthenticatedPrincipal = Depends(require_viewer),
) -> Dict[str, Any]:
    """Return a short-lived private Storage URL after a tenant-scoped ownership check."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", report_id):
        raise HTTPException(status_code=422, detail="Invalid report identifier.")
    if not isinstance(db, SupabaseRepository):
        raise HTTPException(status_code=503, detail="Private report downloads are unavailable in local/demo storage.")
    result = await run_in_threadpool(db.create_signed_report_url, report_id, 90)
    if not result:
        raise HTTPException(status_code=404, detail="Report not found.")
    return result


# ------------------------------------------------------------------------------
# Test-Fixture / Protocol Reference endpoint (POST /v1/systemone)
# Disabled by default. Enable only with ENABLE_TEST_FIXTURE_ENDPOINT=true
# in non-production environments (startup validation blocks production use).
# ------------------------------------------------------------------------------
if settings.ENABLE_TEST_FIXTURE_ENDPOINT:
    @app.post("/v1/systemone", tags=["Strands Decider System One Spec"])
    async def strands_decider_systemone_endpoint(
        req: Dict[str, Any],
        response: Response,
    ) -> Dict[str, Any]:
        """Reference server implementing the official Strands Decider wire protocol.

        Provides a test-fixture for protocol validation and local tests.
        Responses are tagged with X-Sentinel-Test-Fixture: true.
        Only active when ENABLE_TEST_FIXTURE_ENDPOINT=true (never in production).
        """
        response.headers["X-Sentinel-Test-Fixture"] = "true"
        questions = req.get("questions")
        if not isinstance(questions, dict) or not isinstance(req.get("state"), str):
            raise HTTPException(status_code=422, detail="Request must include string state and questions object.")
        answers: Dict[str, Any] = {}
        for q_name, question in questions.items():
            if isinstance(question, dict) and question.get("type") == "choice" and isinstance(question.get("criteria"), dict):
                opts = list(question["criteria"].keys())
                if not opts:
                    raise HTTPException(status_code=422, detail="Choice question criteria must not be empty.")
                state_text = str(req["state"]).lower()
                if "critical" in state_text or "spike" in state_text or "unknown" in state_text or "+3" in state_text:
                    choice = "request_approval" if "request_approval" in opts else opts[0]
                    probs = {opt: (0.85 if opt == choice else (0.15 / max(1, len(opts) - 1))) for opt in opts}
                elif "verified" in state_text or "drift" in state_text:
                    choice = "notify_owner" if "notify_owner" in opts else opts[0]
                    probs = {opt: (0.80 if opt == choice else (0.20 / max(1, len(opts) - 1))) for opt in opts}
                else:
                    choice = "monitor" if "monitor" in opts else opts[0]
                    probs = {opt: (0.88 if opt == choice else (0.12 / max(1, len(opts) - 1))) for opt in opts}

                conf = mock_confidence(probs.values())
                answers[q_name] = {
                    "type": "choice",
                    "choice": choice,
                    "probabilities": probs,
                    "confidence": conf,
                }
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question type '{question.get('type') if isinstance(question, dict) else 'unknown'}' not supported in this endpoint.",
                )

        return {
            "model": str(req.get("model", "StrandsAgents/strands-decider-2B-hobson-v19")),
            "answers": answers,
            "usage": {"input_tokens": 180, "output_tokens": 0},
        }
else:
    # Register a stub that returns 404 so tests targeting the disabled endpoint get a clear error.
    @app.post("/v1/systemone", include_in_schema=False)
    async def strands_decider_systemone_disabled() -> None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "The /v1/systemone test-fixture endpoint is disabled. "
                "Set ENABLE_TEST_FIXTURE_ENDPOINT=true to activate it in non-production environments."
            ),
        )


# ------------------------------------------------------------------------------
# Static Frontend Serving (Single-Container Production & Demo Builds)
# ------------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
