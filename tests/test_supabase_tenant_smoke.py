from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts import smoke_test_supabase_tenants as smoke


def test_tenant_smoke_checks_both_sides_of_every_tenant_table():
    with patch.object(smoke, "request_json", return_value=(200, [])):
        checked = smoke.check_cross_tenant_reads(
            "https://project.supabase.co", "public-key", "test-token", "foreign-workspace"
        )
    assert checked == len(smoke.TENANT_TABLES)


def test_tenant_smoke_fails_if_foreign_rows_are_visible():
    with patch.object(smoke, "request_json", return_value=(200, [{"organization_id": "foreign-workspace"}])):
        with pytest.raises(smoke.SmokeCheckError, match="Tenant isolation failure"):
            smoke.check_cross_tenant_reads(
                "https://project.supabase.co", "public-key", "test-token", "foreign-workspace"
            )


def test_existing_workspace_check_requires_exactly_one_membership():
    with patch.object(smoke, "request_json", return_value=(200, [{"organization_id": "own-workspace"}])):
        assert smoke.existing_personal_workspace(
            "https://project.supabase.co", "public-key", "test-token", "user-id"
        ) == "own-workspace"

    with patch.object(smoke, "request_json", return_value=(200, [])):
        with pytest.raises(smoke.SmokeCheckError, match="already have exactly one"):
            smoke.existing_personal_workspace(
                "https://project.supabase.co", "public-key", "test-token", "user-id"
            )


def test_api_profile_requires_authenticated_identity_and_workspace_match():
    profile = {"user_id": "user-id", "organization_id": "workspace-id", "role": "owner"}
    with patch.object(smoke, "request_json", return_value=(200, profile)):
        assert smoke.api_profile(
            "https://api.example.test", "public-key", "test-token", "user-id"
        ) == profile

    with patch.object(smoke, "request_json", return_value=(200, {**profile, "user_id": "other-user"})):
        with pytest.raises(smoke.SmokeCheckError, match="does not match"):
            smoke.api_profile(
                "https://api.example.test", "public-key", "test-token", "user-id"
            )
