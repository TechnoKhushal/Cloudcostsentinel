from pathlib import Path


FUNCTION = Path(__file__).resolve().parents[1] / "supabase" / "functions" / "delete-account" / "index.ts"


def test_account_deletion_function_keeps_privileged_actions_behind_user_and_origin_checks():
    source = FUNCTION.read_text(encoding="utf-8")
    assert 'allowedOrigins.includes(origin)' in source
    assert 'caller.auth.getUser(accessToken)' in source
    assert 'caller.auth.getClaims(accessToken)' in source
    assert 'authAge > 300' in source
    assert 'confirmation !== "DELETE"' in source
    assert 'transfer_workspace_ownership_before_deleting_account' in source
    assert 'bucket("sentinel-reports")' in source or 'from("sentinel-reports")' in source
    assert 'admin.auth.admin.deleteUser(userId)' in source
    assert 'account.deletion_completed' in source
