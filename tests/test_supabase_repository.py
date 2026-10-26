import json
from uuid import uuid4

import httpx
import pytest

from backend.database.supabase import RequestScope, SupabaseRepository, SupabaseStoreError
from backend.models.report import InvestigationReport
from backend.services.cost_analyzer import CostScenarioRegistry
from backend.services.decider_client import DeciderClient


def _repository(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseRepository("https://project.supabase.co", "public-anon-key", client=client)


@pytest.mark.asyncio
async def test_analysis_bundle_uploads_private_report_then_persists_tenant_bundle_atomically():
    org_id, user_id = str(uuid4()), str(uuid4())
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["apikey"] == "public-anon-key"
        assert request.headers["authorization"] == "Bearer verified-user-token"
        if request.url.path.startswith("/storage/v1/object/sentinel-reports/"):
            assert request.headers["content-type"] == "application/json"
            assert json.loads(request.content)["report_id"]
            return httpx.Response(200, json={"Key": "uploaded"})
        assert request.url.path == "/rest/v1/rpc/persist_analysis_bundle"
        body = json.loads(request.content)["p_bundle"]
        assert body["target_org"] == org_id
        assert body["report"]["storage_path"].startswith(f"{org_id}/")
        assert body["analysis"]["id"] == body["decision"]["analysis_id"]
        assert body["decision"]["id"] == body["report"]["decision_id"]
        assert body["approval"] is None or body["approval"]["id"]
        return httpx.Response(204)

    repo = _repository(handler)
    scope_token = repo.set_scope(RequestScope(user_id, org_id, "owner", "verified-user-token"))
    try:
        anomaly = CostScenarioRegistry.generate_scenario_anomaly("stable_baseline")
        trace = await DeciderClient(provider="mock").decide(anomaly)
        report = InvestigationReport(report_id="rpt-safe_001", anomaly_id=anomaly.anomaly_id,
            decision_id=trace.decision_id, title="Grounded", executive_summary="Observed evidence only.", observed_facts=[],
            decider_action_audit="Decision unchanged.", likely_investigation_areas=[], safe_recommendations=[],
            assumptions_and_limitations=[], follow_up_checklist=[], provider="offline", model_id="deterministic-v1",
            is_simulated=True, generated_at="2026-10-26T00:00:00Z")
        repo.save_analysis_bundle(anomaly, "synthetic_scenario", trace, None, report)
    finally:
        repo.reset_scope(scope_token)
        repo.close()
    assert len(seen) == 2


def test_read_query_is_explicitly_tenant_scoped_and_uses_caller_jwt():
    org_id, user_id = str(uuid4()), str(uuid4())
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=[])

    repo = _repository(handler)
    scope_token = repo.set_scope(RequestScope(user_id, org_id, "reader", "caller-token"))
    try:
        assert repo.get_approvals("pending") == []
    finally:
        repo.reset_scope(scope_token)
        repo.close()
    request = seen[0]
    assert request.headers["authorization"] == "Bearer caller-token"
    assert request.url.params["organization_id"] == f"eq.{org_id}"
    assert request.url.params["status"] == "eq.pending"
    assert "service-role" not in request.headers["authorization"]


def test_report_download_requires_tenant_metadata_and_returns_short_lived_signed_url():
    org_id, user_id = str(uuid4()), str(uuid4())
    path = f"{org_id}/rpt-safe_001.json"

    def handler(request):
        if request.url.path == "/rest/v1/investigation_reports":
            assert request.url.params["organization_id"] == f"eq.{org_id}"
            return httpx.Response(200, json=[{"storage_path": path, "storage_status": "ready"}])
        assert request.url.path.endswith(f"/sentinel-reports/{path}")
        assert json.loads(request.content) == {"expiresIn": 90, "download": True}
        return httpx.Response(200, json={"signedURL": f"/object/sign/sentinel-reports/{path}?token=temporary"})

    repo = _repository(handler)
    scope_token = repo.set_scope(RequestScope(user_id, org_id, "reader", "caller-token"))
    try:
        result = repo.create_signed_report_url("rpt-safe_001")
    finally:
        repo.reset_scope(scope_token)
        repo.close()
    assert result["url"].startswith("https://project.supabase.co/storage/v1/object/sign/")
    assert "temporary" in result["url"]
    assert result["expires_in"] == 90


@pytest.mark.asyncio
async def test_failed_bundle_attempts_storage_cleanup_and_does_not_swallow_database_failure():
    org_id, user_id = str(uuid4()), str(uuid4())
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST" and request.url.path.startswith("/storage/v1/object/"):
            return httpx.Response(200, json={"Key": "uploaded"})
        if request.method == "POST":
            return httpx.Response(503, json={"message": "private database details"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"message": "deleted"})
        raise AssertionError("unexpected request")

    repo = _repository(handler)
    token = repo.set_scope(RequestScope(user_id, org_id, "owner", "caller-token"))
    try:
        anomaly = CostScenarioRegistry.generate_scenario_anomaly("stable_baseline")
        trace = await DeciderClient(provider="mock").decide(anomaly)
        report = InvestigationReport(report_id="rpt-cleanup_1", anomaly_id=anomaly.anomaly_id,
            decision_id=trace.decision_id, title="Grounded", executive_summary="Observed evidence only.", observed_facts=[],
            decider_action_audit="Decision unchanged.", likely_investigation_areas=[], safe_recommendations=[],
            assumptions_and_limitations=[], follow_up_checklist=[], provider="offline", model_id="deterministic-v1",
            is_simulated=True, generated_at="2026-10-26T00:00:00Z")
        with pytest.raises(SupabaseStoreError):
            repo.save_analysis_bundle(anomaly, "synthetic_scenario", trace, None, report)
    finally:
        repo.reset_scope(token)
        repo.close()
    assert [request.method for request in requests] == ["POST", "POST", "DELETE"]
