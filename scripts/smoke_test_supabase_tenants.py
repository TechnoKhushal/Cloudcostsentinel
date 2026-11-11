"""Read-only, two-account Supabase/API tenant-isolation smoke check.

Run from the repository root after configuring a dedicated Supabase project and
two existing test accounts in the local .env. This script never creates users,
changes workspace data, or invokes AWS.
"""

from __future__ import annotations

import os
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


TENANT_TABLES = (
    "organizations",
    "organization_members",
    "scans",
    "findings",
    "approvals",
    "audit_events",
    "reports",
    "ai_usage_events",
    "cost_analyses",
    "decision_traces",
    "approval_queue",
    "investigation_reports",
    "aws_account_connections",
    "aws_cost_query_usage",
    "workspace_finops_settings",
)


class SmokeCheckError(RuntimeError):
    pass


def request_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None,
                 payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except HTTPError as error:
        # Never echo provider bodies: Auth responses may contain sensitive data.
        body = error.read()
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            parsed = None
        return error.code, parsed


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SmokeCheckError(f"Missing required local test setting: {name}")
    return value


def sign_in(supabase_url: str, anon_key: str, email: str, password: str) -> tuple[str, str]:
    status, body = request_json(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        method="POST",
        headers={"apikey": anon_key},
        payload={"email": email, "password": password},
    )
    if status != 200 or not isinstance(body, dict):
        raise SmokeCheckError(f"Supabase password sign-in failed (HTTP {status}); check the test account and Auth setup.")
    token, user = body.get("access_token"), body.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(token, str) or not isinstance(user_id, str):
        raise SmokeCheckError("Supabase returned an incomplete test session.")
    return token, user_id


def api_profile(api_origin: str, anon_key: str, token: str, expected_user_id: str) -> dict:
    status, body = request_json(
        f"{api_origin}/api/account/profile",
        headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
    )
    if status != 200 or not isinstance(body, dict):
        raise SmokeCheckError(f"Authenticated API profile request failed (HTTP {status}).")
    if body.get("user_id") != expected_user_id:
        raise SmokeCheckError("Backend identity does not match the signed-in Supabase user.")
    org_id = body.get("organization_id")
    if not isinstance(org_id, str) or not org_id:
        raise SmokeCheckError("API profile has no provisioned workspace; check migrations and readiness.")
    return body


def existing_personal_workspace(supabase_url: str, anon_key: str, token: str, user_id: str) -> str:
    query = urlencode({"select": "organization_id", "user_id": f"eq.{user_id}", "limit": "2"})
    status, body = request_json(
        f"{supabase_url}/rest/v1/organization_members?{query}",
        headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
    )
    if status != 200 or not isinstance(body, list):
        raise SmokeCheckError(f"Could not verify an existing personal workspace (HTTP {status}).")
    if len(body) != 1 or not isinstance(body[0].get("organization_id"), str):
        raise SmokeCheckError("Each test account must already have exactly one personal workspace; provision accounts before this read-only check.")
    return body[0]["organization_id"]


def check_cross_tenant_reads(supabase_url: str, anon_key: str, token: str, foreign_org_id: str) -> int:
    checked = 0
    for table in TENANT_TABLES:
        query = urlencode({
            "select": "organization_id" if table != "organizations" else "id",
            "organization_id" if table != "organizations" else "id": f"eq.{foreign_org_id}",
            "limit": "1",
        })
        status, body = request_json(
            f"{supabase_url}/rest/v1/{table}?{query}",
            headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
        )
        if status in (401, 403):
            checked += 1  # An explicit permission denial is safe.
            continue
        if status != 200 or not isinstance(body, list):
            raise SmokeCheckError(f"Could not verify RLS on {table} (HTTP {status}); check migration/readiness.")
        if body:
            raise SmokeCheckError(f"Tenant isolation failure: the other account read rows from {table}.")
        checked += 1
    return checked


def main() -> int:
    load_dotenv()
    try:
        supabase_url = require_env("SUPABASE_URL").rstrip("/")
        anon_key = require_env("SUPABASE_ANON_KEY")
        api_origin = require_env("VITE_API_BASE_URL").rstrip("/")
        user_a_email = require_env("SUPABASE_SMOKE_USER_A_EMAIL")
        user_a_password = require_env("SUPABASE_SMOKE_USER_A_PASSWORD")
        user_b_email = require_env("SUPABASE_SMOKE_USER_B_EMAIL")
        user_b_password = require_env("SUPABASE_SMOKE_USER_B_PASSWORD")
        if user_a_email.casefold() == user_b_email.casefold():
            raise SmokeCheckError("The two smoke-test accounts must be different users.")

        status, _ = request_json(f"{api_origin}/api/account/profile", headers={"apikey": anon_key})
        if status != 401:
            raise SmokeCheckError(f"Unauthenticated account API should return HTTP 401, got {status}.")

        token_a, user_a_id = sign_in(supabase_url, anon_key, user_a_email, user_a_password)
        token_b, user_b_id = sign_in(supabase_url, anon_key, user_b_email, user_b_password)
        if user_a_id == user_b_id:
            raise SmokeCheckError("Supabase resolved both test logins to the same user.")

        org_a = existing_personal_workspace(supabase_url, anon_key, token_a, user_a_id)
        org_b = existing_personal_workspace(supabase_url, anon_key, token_b, user_b_id)
        profile_a = api_profile(api_origin, anon_key, token_a, user_a_id)
        profile_b = api_profile(api_origin, anon_key, token_b, user_b_id)
        if profile_a["organization_id"] != org_a or profile_b["organization_id"] != org_b:
            raise SmokeCheckError("Backend workspace resolution does not match each account's existing membership.")
        if org_a == org_b:
            raise SmokeCheckError("The test accounts share a workspace; use isolated personal test workspaces.")

        checked = check_cross_tenant_reads(supabase_url, anon_key, token_a, org_b)
        checked += check_cross_tenant_reads(supabase_url, anon_key, token_b, org_a)
    except SmokeCheckError as error:
        print(f"Supabase tenant smoke check failed: {error}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, ValueError) as error:
        # Do not print URLs, account identifiers, or provider response bodies.
        print(f"Supabase tenant smoke check failed: network or response error ({type(error).__name__}).", file=sys.stderr)
        return 1

    print(f"Supabase tenant smoke check passed: unauthenticated API rejected; two identities verified; {checked} cross-tenant table reads denied by RLS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
