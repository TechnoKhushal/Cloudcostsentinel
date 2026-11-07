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


def test_production_readiness_requires_the_expected_complete_schema_version():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/cloudcost_sentinel_schema_version"
        assert request.headers["apikey"] == "public-anon-key"
        assert "authorization" not in request.headers
        assert json.loads(request.content) == {}
        return httpx.Response(200, json="cloudcost-sentinel-v6")

    repo = _repository(handler)
    try:
        assert repo.check_ready() is True
    finally:
        repo.close()
    assert len(requests) == 1


@pytest.mark.parametrize("response", [
    httpx.Response(404, json={"message": "function not found"}),
    httpx.Response(200, json="incomplete"),
    httpx.Response(200, json={"version": "cloudcost-sentinel-v6"}),
])
def test_production_readiness_fails_if_schema_probe_is_missing_or_mismatched(response):
    repo = _repository(lambda _request: response)
    try:
        assert repo.check_ready() is False
    finally:
        repo.close()


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
        assert body["analysis"]["partial_data"] is True
        assert body["analysis"]["data_warnings"] == ["PARTIAL_DATA: test fixture"]
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
        repo.save_analysis_bundle(anomaly, "aws_cost_explorer", trace, None, report,
                                  partial_data=True, data_warnings=["PARTIAL_DATA: test fixture"])
    finally:
        repo.reset_scope(scope_token)
        repo.close()
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_latest_analysis_restore_is_bounded_to_current_tenant_and_preserves_quality_metadata():
    org_id, user_id = str(uuid4()), str(uuid4())
    anomaly = CostScenarioRegistry.generate_scenario_anomaly("stable_baseline")
    trace = await DeciderClient(provider="mock").decide(anomaly)
    report = InvestigationReport(report_id="rpt-history_001", anomaly_id=anomaly.anomaly_id,
        decision_id=trace.decision_id, title="Persisted", executive_summary="Stored analysis.", observed_facts=[],
        decider_action_audit="Decision unchanged.", likely_investigation_areas=[], safe_recommendations=[],
        assumptions_and_limitations=[], follow_up_checklist=[], provider="offline", model_id="deterministic-v1",
        is_simulated=True, generated_at="2026-11-08T00:00:00Z")
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer caller-token"
        assert request.url.params["organization_id"] == f"eq.{org_id}"
        if request.url.path.endswith("/cost_analyses"):
            assert request.url.params["limit"] == "1"
            return httpx.Response(200, json=[{"id": anomaly.anomaly_id, "source": "aws_cost_explorer",
                "anomaly": anomaly.model_dump(mode="json"), "partial_data": True,
                "data_warnings": ["PARTIAL_DATA: test fixture"]}])
        if request.url.path.endswith("/decision_traces"):
            assert request.url.params["analysis_id"] == f"eq.{anomaly.anomaly_id}"
            return httpx.Response(200, json=[{"trace": trace.model_dump(mode="json")}])
        if request.url.path.endswith("/investigation_reports"):
            assert request.url.params["decision_id"] == f"eq.{trace.decision_id}"
            return httpx.Response(200, json=[{"report": report.model_dump(mode="json")}])
        if request.url.path.endswith("/approval_queue"):
            assert request.url.params["decision_id"] == f"eq.{trace.decision_id}"
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected request: {request.url}")

    repo = _repository(handler)
    token = repo.set_scope(RequestScope(user_id, org_id, "reader", "caller-token"))
    try:
        result = repo.get_latest_analysis()
    finally:
        repo.reset_scope(token)
        repo.close()
    assert result is not None
    assert result["anomaly"].anomaly_id == anomaly.anomaly_id
    assert result["decision"].decision_id == trace.decision_id
    assert result["report"].report_id == report.report_id
    assert result["cost_data_source"] == "aws_cost_explorer"
    assert result["partial_data"] is True
    assert result["data_warnings"] == ["PARTIAL_DATA: test fixture"]
    assert len(seen) == 4


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


def test_aws_connection_upsert_is_bound_to_the_current_workspace_and_token():
    org_id, user_id = str(uuid4()), str(uuid4())
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer caller-token"
        assert request.url.path == "/rest/v1/aws_account_connections"
        assert request.url.params["on_conflict"] == "organization_id"
        body = json.loads(request.content)
        assert body["organization_id"] == org_id
        assert body["updated_by"] == user_id
        return httpx.Response(201, json=[{"organization_id": org_id, "account_id": "123456789012", "status": "pending"}])

    repo = _repository(handler)
    token = repo.set_scope(RequestScope(user_id, org_id, "owner", "caller-token"))
    try:
        row = repo.save_aws_account_connection("arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly", "a" * 32, "123456789012")
    finally:
        repo.reset_scope(token)
        repo.close()
    assert row["status"] == "pending"
    assert len(requests) == 1


def test_durable_aws_api_budget_calls_atomic_workspace_rpc():
    org_id, user_id = str(uuid4()), str(uuid4())

    def handler(request):
        assert request.headers["authorization"] == "Bearer caller-token"
        assert request.url.path == "/rest/v1/rpc/reserve_aws_cost_query"
        assert json.loads(request.content) == {"p_organization_id": org_id, "p_daily_limit": 20}
        return httpx.Response(200, json=True)

    repo = _repository(handler)
    token = repo.set_scope(RequestScope(user_id, org_id, "owner", "caller-token"))
    try:
        assert repo.reserve_aws_cost_query(20) is True
    finally:
        repo.reset_scope(token)
        repo.close()


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
