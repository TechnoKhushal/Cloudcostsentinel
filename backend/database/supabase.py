from __future__ import annotations

import contextvars
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..config import settings
from ..models.approval import ApprovalItem
from ..models.cost import CostAnomaly
from ..models.decision import DeciderResponseTrace
from ..models.report import InvestigationReport
from .db import ApprovalConflictError


@dataclass(frozen=True)
class RequestScope:
    user_id: str
    organization_id: str
    role: str
    access_token: str


_scope: contextvars.ContextVar[Optional[RequestScope]] = contextvars.ContextVar("supabase_request_scope", default=None)
logger = logging.getLogger("cloudcost_sentinel.supabase")
REPORT_BUCKET = "sentinel-reports"


class SupabaseStoreError(RuntimeError):
    """Sanitized persistence error; never includes provider bodies or credentials."""

    def __init__(self, status_code: int = 503):
        super().__init__("Supabase persistence request failed.")
        self.status_code = status_code


class SupabaseRepository:
    """User-token PostgREST repository; RLS is enforced on every tenant query."""

    def __init__(self, url: str, anon_key: str, *, client: Optional[httpx.Client] = None):
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self._client = client or httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0))

    def initialize(self) -> None:
        if not self.url or not self.anon_key:
            raise SupabaseStoreError()

    def close(self) -> None:
        self._client.close()

    def _headers(self, token: Optional[str] = None, *, prefer: Optional[str] = None) -> dict[str, str]:
        headers = {"apikey": self.anon_key, "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method: str, path: str, *, params: Optional[dict[str, str]] = None,
                 body: Any = None, token: Optional[str] = None, prefer: Optional[str] = None) -> Any:
        try:
            response = self._client.request(method, f"{self.url}/rest/v1/{path}", params=params,
                                            json=body, headers=self._headers(token, prefer=prefer))
        except httpx.HTTPError:
            raise SupabaseStoreError() from None
        if response.status_code >= 400:
            raise SupabaseStoreError(response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise SupabaseStoreError() from None

    def resolve_scope(self, user_id: str, access_token: str) -> RequestScope:
        """Provision/read a personal workspace and fetch the role using caller JWT/RLS."""
        org_id = self._request("POST", "rpc/get_or_create_my_org", token=access_token, body={}, prefer="return=representation")
        if isinstance(org_id, list):
            org_id = org_id[0] if org_id else None
        if isinstance(org_id, dict):
            org_id = org_id.get("get_or_create_my_org")
        if not isinstance(org_id, str):
            raise SupabaseStoreError()
        role = self._request("POST", "rpc/get_my_org_role", token=access_token, body={"target_org": org_id}, prefer="return=representation")
        if isinstance(role, list):
            role = role[0] if role else None
        if isinstance(role, dict):
            role = role.get("get_my_org_role")
        if role not in {"owner", "admin", "member", "reviewer", "reader"}:
            raise SupabaseStoreError(403)
        return RequestScope(user_id=user_id, organization_id=org_id, role=role, access_token=access_token)

    def set_scope(self, scope: RequestScope):
        return _scope.set(scope)

    @staticmethod
    def reset_scope(token: contextvars.Token) -> None:
        _scope.reset(token)

    def _current_scope(self) -> RequestScope:
        scope = _scope.get()
        if scope is None:
            raise SupabaseStoreError(401)
        return scope

    def check_ready(self) -> bool:
        try:
            response = self._client.post(
                f"{self.url}/rest/v1/rpc/cloudcost_sentinel_schema_version",
                json={},
                headers={"apikey": self.anon_key, "Accept": "application/json"},
                timeout=httpx.Timeout(3.0, connect=2.0),
            )
            return response.status_code == 200 and response.json() == "cloudcost-sentinel-v6"
        except (httpx.HTTPError, ValueError):
            return False

    def save_analysis_bundle(self, anomaly: CostAnomaly, source: str, trace: DeciderResponseTrace,
                             approval: Optional[ApprovalItem], report: InvestigationReport,
                             *, partial_data: bool = False, data_warnings: Optional[list[str]] = None) -> None:
        scope = self._current_scope()
        storage_path = f"{scope.organization_id}/{report.report_id}.json"
        report_bytes = json.dumps(report.model_dump(mode="json"), separators=(",", ":")).encode("utf-8")
        if len(report_bytes) > 1_000_000 or not report_bytes.startswith(b"{"):
            raise SupabaseStoreError(413)
        self._storage_upload(scope, storage_path, report_bytes)
        bundle = {
            "target_org": scope.organization_id,
            "analysis": {"id": anomaly.anomaly_id, "source": source, "anomaly": anomaly.model_dump(mode="json"),
                         "partial_data": partial_data, "data_warnings": data_warnings or []},
            "decision": {"id": trace.decision_id, "analysis_id": anomaly.anomaly_id, "trace": trace.model_dump(mode="json")},
            "approval": ({"id": approval.id, "analysis_id": approval.anomaly_id, "decision_id": approval.decision_id,
                          "service": approval.service, "environment": approval.environment,
                          "suggested_action": approval.suggested_action,
                          "estimated_monthly_savings": approval.estimated_monthly_savings,
                          "is_simulated": approval.is_simulated, "created_at": approval.created_at} if approval else None),
            "report": {"id": report.report_id, "analysis_id": report.anomaly_id, "decision_id": report.decision_id,
                       "report": report.model_dump(mode="json"), "storage_path": storage_path},
        }
        try:
            self._request("POST", "rpc/persist_analysis_bundle", token=scope.access_token, body={"p_bundle": bundle})
        except SupabaseStoreError:
            self._storage_delete(scope, storage_path)
            raise

    def _storage_upload(self, scope: RequestScope, path: str, contents: bytes) -> None:
        try:
            response = self._client.post(f"{self.url}/storage/v1/object/{REPORT_BUCKET}/{path}", content=contents,
                headers={**self._headers(scope.access_token), "Content-Type": "application/json", "x-upsert": "false"})
        except httpx.HTTPError:
            raise SupabaseStoreError() from None
        if response.status_code >= 400:
            raise SupabaseStoreError(response.status_code)

    def _storage_delete(self, scope: RequestScope, path: str) -> None:
        try:
            response = self._client.delete(f"{self.url}/storage/v1/object/{REPORT_BUCKET}/{path}",
                headers=self._headers(scope.access_token))
            if response.status_code >= 400:
                logger.warning("Could not clean up a failed report upload (HTTP %s).", response.status_code)
        except httpx.HTTPError as exc:
            logger.warning("Could not clean up a failed report upload (%s).", type(exc).__name__)

    def create_signed_report_url(self, report_id: str, expires_in: int = 90) -> dict[str, Any]:
        scope = self._current_scope()
        rows = self._request("GET", "investigation_reports", token=scope.access_token,
            params={"select": "storage_path,storage_status", "id": f"eq.{report_id}",
                    "organization_id": f"eq.{scope.organization_id}", "limit": "1"}) or []
        if not rows or rows[0].get("storage_status") != "ready" or not rows[0].get("storage_path"):
            return {}
        path = rows[0]["storage_path"]
        expected_prefix = f"{scope.organization_id}/"
        if not path.startswith(expected_prefix) or ".." in path.split("/"):
            raise SupabaseStoreError(403)
        try:
            response = self._client.post(f"{self.url}/storage/v1/object/sign/{REPORT_BUCKET}/{path}",
                json={"expiresIn": max(30, min(expires_in, 300)), "download": True},
                headers=self._headers(scope.access_token))
        except httpx.HTTPError:
            raise SupabaseStoreError() from None
        if response.status_code >= 400:
            raise SupabaseStoreError(response.status_code)
        try:
            signed_path = response.json().get("signedURL") or response.json().get("signedUrl")
        except (ValueError, AttributeError):
            raise SupabaseStoreError() from None
        if not isinstance(signed_path, str) or not signed_path.startswith("/"):
            raise SupabaseStoreError()
        return {"url": f"{self.url}/storage/v1{signed_path.removeprefix('/storage/v1')}", "expires_in": max(30, min(expires_in, 300))}

    def get_recent_decisions(self, limit: int = 20) -> list[DeciderResponseTrace]:
        scope = self._current_scope()
        rows = self._request("GET", "decision_traces", token=scope.access_token,
                             params={"select": "trace", "organization_id": f"eq.{scope.organization_id}",
                                     "order": "created_at.desc,id.desc", "limit": str(max(1, min(limit, 100)))} ) or []
        return [DeciderResponseTrace.model_validate(row["trace"]) for row in rows]

    def get_latest_analysis(self) -> Optional[dict[str, Any]]:
        """Restore the newest persisted tenant analysis using only the caller JWT/RLS."""
        scope = self._current_scope()
        analyses = self._request("GET", "cost_analyses", token=scope.access_token,
            params={"select": "id,source,anomaly,partial_data,data_warnings",
                    "organization_id": f"eq.{scope.organization_id}",
                    "order": "created_at.desc,id.desc", "limit": "1"}) or []
        if not analyses:
            return None
        row = analyses[0]
        analysis_id = row.get("id")
        if not isinstance(analysis_id, str):
            raise SupabaseStoreError()
        decisions = self._request("GET", "decision_traces", token=scope.access_token,
            params={"select": "trace", "organization_id": f"eq.{scope.organization_id}",
                    "analysis_id": f"eq.{analysis_id}", "order": "created_at.desc,id.desc", "limit": "1"}) or []
        if not decisions:
            logger.warning("Latest persisted analysis %s is missing its decision record.", analysis_id)
            return None
        decision = DeciderResponseTrace.model_validate(decisions[0]["trace"])
        reports = self._request("GET", "investigation_reports", token=scope.access_token,
            params={"select": "report", "organization_id": f"eq.{scope.organization_id}",
                    "decision_id": f"eq.{decision.decision_id}",
                    "order": "created_at.desc,id.desc", "limit": "1"}) or []
        if not reports:
            logger.warning("Latest persisted analysis %s is missing its report record.", analysis_id)
            return None
        approvals = self._request("GET", "approval_queue", token=scope.access_token,
            params={"select": "*", "organization_id": f"eq.{scope.organization_id}",
                    "decision_id": f"eq.{decision.decision_id}",
                    "order": "created_at.desc,id.desc", "limit": "1"}) or []
        approval = None
        if approvals:
            approval_row = approvals[0]
            approval = ApprovalItem(id=approval_row["id"], decision_id=approval_row["decision_id"],
                anomaly_id=approval_row["analysis_id"], service=approval_row["service"],
                environment=approval_row["environment"], suggested_action=approval_row["suggested_action"],
                estimated_monthly_savings=float(approval_row["estimated_monthly_savings"]), status=approval_row["status"],
                reviewed_by=approval_row.get("reviewed_by"), reviewed_at=approval_row.get("reviewed_at"),
                notes=approval_row.get("notes"), created_at=approval_row["created_at"],
                is_simulated=approval_row["is_simulated"])
        warnings = row.get("data_warnings")
        if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
            warnings = []
        anomaly = CostAnomaly.model_validate(row["anomaly"])
        return {
            "anomaly": anomaly,
            "decision": decision,
            "report": InvestigationReport.model_validate(reports[0]["report"]),
            "approval": approval,
            "is_simulated": anomaly.is_simulated,
            "cost_data_source": row["source"],
            "partial_data": bool(row.get("partial_data", False)),
            "data_warnings": warnings,
        }

    def get_profile(self) -> dict[str, Any]:
        scope = self._current_scope()
        rows = self._request("GET", "profiles", token=scope.access_token,
            params={"select": "user_id,display_name,created_at,updated_at", "user_id": f"eq.{scope.user_id}", "limit": "1"}) or []
        if rows:
            return {**rows[0], "organization_id": scope.organization_id, "role": scope.role}
        return {"user_id": scope.user_id, "display_name": None, "organization_id": scope.organization_id,
                "role": scope.role, "created_at": None, "updated_at": None}

    def get_aws_account_connection(self) -> Optional[dict[str, Any]]:
        scope = self._current_scope()
        rows = self._request("GET", "aws_account_connections",
            params={"select": "organization_id,role_arn,external_id,account_id,status,verified_at,updated_at",
                    "organization_id": f"eq.{scope.organization_id}", "limit": "1"}, token=scope.access_token) or []
        return rows[0] if rows else None

    def save_aws_account_connection(self, role_arn: str, external_id: str, account_id: str) -> dict[str, Any]:
        scope = self._current_scope()
        rows = self._request("POST", "aws_account_connections",
            params={"on_conflict": "organization_id", "select": "organization_id,role_arn,external_id,account_id,status,verified_at,updated_at"},
            body={"organization_id": scope.organization_id, "role_arn": role_arn, "external_id": external_id,
                  "account_id": account_id, "status": "pending", "verified_at": None, "updated_by": scope.user_id},
            token=scope.access_token, prefer="resolution=merge-duplicates,return=representation") or []
        if not rows:
            raise SupabaseStoreError()
        return rows[0]

    def set_aws_account_connection_status(self, status: str, *, verified_at: Optional[str] = None) -> None:
        scope = self._current_scope()
        self._request("PATCH", "aws_account_connections",
            params={"organization_id": f"eq.{scope.organization_id}"},
            body={"status": status, "verified_at": verified_at, "updated_by": scope.user_id}, token=scope.access_token,
            prefer="return=minimal")

    def delete_aws_account_connection(self) -> None:
        scope = self._current_scope()
        self._request("DELETE", "aws_account_connections",
            params={"organization_id": f"eq.{scope.organization_id}"}, token=scope.access_token,
            prefer="return=minimal")

    def reserve_aws_cost_query(self, daily_limit: int) -> bool:
        scope = self._current_scope()
        result = self._request("POST", "rpc/reserve_aws_cost_query", token=scope.access_token,
            body={"p_organization_id": scope.organization_id, "p_daily_limit": daily_limit})
        if not isinstance(result, bool):
            raise SupabaseStoreError()
        return result

    def get_workspace_finops_settings(self) -> Optional[dict[str, Any]]:
        scope = self._current_scope()
        rows = self._request("GET", "workspace_finops_settings",
            params={"select": "monthly_budget,currency,updated_at", "organization_id": f"eq.{scope.organization_id}", "limit": "1"},
            token=scope.access_token) or []
        return rows[0] if rows else None

    def update_workspace_finops_settings(self, monthly_budget: float, currency: str) -> dict[str, Any]:
        scope = self._current_scope()
        rows = self._request("POST", "workspace_finops_settings",
            params={"on_conflict": "organization_id", "select": "monthly_budget,currency,updated_at"},
            body={"organization_id": scope.organization_id, "monthly_budget": monthly_budget,
                  "currency": currency, "updated_by": scope.user_id}, token=scope.access_token,
            prefer="resolution=merge-duplicates,return=representation") or []
        if not rows:
            raise SupabaseStoreError()
        return rows[0]

    def update_profile(self, display_name: Optional[str]) -> dict[str, Any]:
        scope = self._current_scope()
        rows = self._request("POST", "profiles", token=scope.access_token,
            params={"on_conflict": "user_id", "select": "user_id,display_name,created_at,updated_at"},
            body={"user_id": scope.user_id, "display_name": display_name},
            prefer="resolution=merge-duplicates,return=representation") or []
        if not rows:
            raise SupabaseStoreError()
        return {**rows[0], "organization_id": scope.organization_id, "role": scope.role}

    def get_approvals(self, status: Optional[str] = None) -> list[ApprovalItem]:
        scope = self._current_scope()
        params = {"select": "*", "organization_id": f"eq.{scope.organization_id}", "order": "created_at.desc,id.desc", "limit": "100"}
        if status:
            params["status"] = f"eq.{status}"
        rows = self._request("GET", "approval_queue", token=scope.access_token, params=params) or []
        return [ApprovalItem(id=row["id"], decision_id=row["decision_id"], anomaly_id=row["analysis_id"],
            service=row["service"], environment=row["environment"], suggested_action=row["suggested_action"],
            estimated_monthly_savings=float(row["estimated_monthly_savings"]), status=row["status"],
            reviewed_by=row.get("reviewed_by"), reviewed_at=row.get("reviewed_at"), notes=row.get("notes"),
            created_at=row["created_at"], is_simulated=row["is_simulated"]) for row in rows]

    def update_approval_status(self, approval_id: str, status: str, reviewed_by: str,
                               notes: Optional[str] = None) -> Optional[ApprovalItem]:
        scope = self._current_scope()
        now = datetime.now(timezone.utc).isoformat()
        changed = self._request("PATCH", "approval_queue", token=scope.access_token,
            params={"id": f"eq.{approval_id}", "organization_id": f"eq.{scope.organization_id}", "status": "eq.pending", "select": "*"},
            body={"status": status, "reviewed_by": scope.user_id, "reviewed_at": now, "notes": notes},
            prefer="return=representation") or []
        if changed:
            row = changed[0]
            return ApprovalItem(id=row["id"], decision_id=row["decision_id"], anomaly_id=row["analysis_id"],
                service=row["service"], environment=row["environment"], suggested_action=row["suggested_action"],
                estimated_monthly_savings=float(row["estimated_monthly_savings"]), status=row["status"],
                reviewed_by=reviewed_by, reviewed_at=row.get("reviewed_at"), notes=row.get("notes"),
                created_at=row["created_at"], is_simulated=row["is_simulated"])
        existing = self._request("GET", "approval_queue", token=scope.access_token,
            params={"select": "status", "id": f"eq.{approval_id}", "organization_id": f"eq.{scope.organization_id}", "limit": "1"}) or []
        if not existing:
            return None
        raise ApprovalConflictError(f"Approval item '{approval_id}' has already been reviewed.")

    def get_latest_report_for_anomaly(self, anomaly_id: str) -> Optional[InvestigationReport]:
        scope = self._current_scope()
        rows = self._request("GET", "investigation_reports", token=scope.access_token,
            params={"select": "report", "organization_id": f"eq.{scope.organization_id}",
                    "analysis_id": f"eq.{anomaly_id}", "order": "created_at.desc", "limit": "1"}) or []
        return InvestigationReport.model_validate(rows[0]["report"]) if rows else None


supabase_repository = SupabaseRepository(settings.SUPABASE_URL or "", settings.SUPABASE_ANON_KEY or "")
