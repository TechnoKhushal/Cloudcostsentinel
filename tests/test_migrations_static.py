from pathlib import Path


MIGRATION_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def test_ordered_migrations_define_private_tenant_storage_and_runtime_rls():
    migrations = sorted(MIGRATION_DIR.glob("*.sql"))
    assert [path.name for path in migrations] == [
        "202610260001_initial_tenant_schema.sql",
        "202610260002_api_runtime.sql",
        "202610260003_membership_role_and_storage_cleanup.sql",
        "202611070001_tenant_aws_role_connections.sql",
        "202611070002_production_schema_readiness.sql",
        "202611080001_persist_analysis_quality_metadata.sql",
        "202611120001_shared_api_rate_limits.sql",
    ]
    base, runtime, upgrade, customer_aws, readiness, quality_metadata, rate_limits = (path.read_text(encoding="utf-8").lower() for path in migrations)
    for sql in (base, runtime, upgrade, customer_aws, readiness, quality_metadata, rate_limits):
        assert sql.lstrip().startswith("--")
        assert "begin;" in sql
        assert sql.rstrip().endswith("commit;")
    for table in ("profiles", "organizations", "organization_members", "audit_events"):
        assert f"alter table public.{table} enable row level security" in base
    assert "unique (organization_id, id)" in base.split("create table if not exists public.scans", 1)[1].split("create index", 1)[0]
    for table in ("cost_analyses", "decision_traces", "approval_queue", "investigation_reports"):
        assert f"alter table public.{table} enable row level security" in runtime
    assert "values ('sentinel-reports', 'sentinel-reports', false" in base
    assert "report_objects_member_select" in base
    assert "report_objects_writer_insert" in base
    assert "revoke update, delete on public.audit_events" in base
    assert "grant execute on function public.persist_analysis_bundle(jsonb) to authenticated" in runtime
    assert "organization_members_role_check" in upgrade
    assert "report_objects_owner_delete" in upgrade
    assert "alter table public.aws_account_connections enable row level security" in customer_aws
    assert "aws_connections_admin_insert" in customer_aws
    assert "aws_connections_admin_update" in customer_aws
    assert "cloudcostsentinelreadonly" in customer_aws
    assert "unique" in customer_aws and "external_id" in customer_aws
    assert "reserve_aws_cost_query" in customer_aws
    assert "workspace_finops_settings" in customer_aws
    assert "aws_cost_query_usage" in customer_aws
    assert "least(public.aws_cost_query_usage.request_count + 1, p_daily_limit + 1)" in customer_aws
    assert "cloudcost_sentinel_schema_version" in readiness
    assert "grant execute on function public.cloudcost_sentinel_schema_version() to anon" in readiness
    assert "notify pgrst, 'reload schema'" in readiness
    assert "data_warnings jsonb" in quality_metadata
    assert "partial_data boolean" in quality_metadata
    assert "cloudcost-sentinel-v6" in quality_metadata
    assert "api_request_counters" in rate_limits
    assert "alter table public.api_request_counters enable row level security" in rate_limits
    assert "public.admit_api_request(text)" in rate_limits
    assert "cloudcost-sentinel-v7" in rate_limits
    assert "p_limit" not in rate_limits and "p_window_seconds" not in rate_limits
    assert "service_role" not in customer_aws
    assert "service_role" not in base + runtime + upgrade + customer_aws + readiness + quality_metadata + rate_limits
