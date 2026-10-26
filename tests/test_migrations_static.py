from pathlib import Path


MIGRATION_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def test_ordered_migrations_define_private_tenant_storage_and_runtime_rls():
    migrations = sorted(MIGRATION_DIR.glob("*.sql"))
    assert [path.name for path in migrations] == [
        "202610260001_initial_tenant_schema.sql",
        "202610260002_api_runtime.sql",
        "202610260003_membership_role_and_storage_cleanup.sql",
    ]
    base, runtime, upgrade = (path.read_text(encoding="utf-8").lower() for path in migrations)
    for sql in (base, runtime, upgrade):
        assert sql.lstrip().startswith("--")
        assert "begin;" in sql
        assert sql.rstrip().endswith("commit;")
    for table in ("profiles", "organizations", "organization_members", "audit_events"):
        assert f"alter table public.{table} enable row level security" in base
    for table in ("cost_analyses", "decision_traces", "approval_queue", "investigation_reports"):
        assert f"alter table public.{table} enable row level security" in runtime
    assert "values ('sentinel-reports', 'sentinel-reports', false" in base
    assert "report_objects_member_select" in base
    assert "report_objects_writer_insert" in base
    assert "revoke update, delete on public.audit_events" in base
    assert "grant execute on function public.persist_analysis_bundle(jsonb) to authenticated" in runtime
    assert "organization_members_role_check" in upgrade
    assert "report_objects_owner_delete" in upgrade
    assert "service_role" not in base + runtime + upgrade
