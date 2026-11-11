# Customer data handling policy draft

This describes the application's technical behavior. It is not a legal privacy notice or a substitute for a customer contract. The company identity, contact address, service region, subprocessors, incident notice period, and final retention terms must be supplied and reviewed before commercial launch.

## Data inventory and access

- Account data: Supabase Auth identity and the profile display name.
- Workspace data: AWS account role ARN, external ID, account ID, budget/currency, cost-analysis results, decisions, approvals, generated reports, audit records, and usage/quota counters.
- AWS access is read-only through the customer's role. The application does not store the customer's AWS access keys.
- The browser and API use the user's Supabase token and tenant RLS. The account deletion Edge Function uses Supabase's privileged key only inside the Supabase Function runtime; it is never sent to Vercel or Render.
- Workspace export is restricted to a workspace owner/admin, generated from the caller's authorized workspace, and recorded in the lifecycle audit table. The JSON includes generated report content stored in Postgres and storage paths; it does not include report object bytes separately because those are duplicates of the persisted report JSON.

## Retention and deletion behavior

- The service has no automatic expiration job for workspace cost data, decisions, or generated reports. Records remain until an authorized workspace/account deletion. A separate customer-support deletion workflow is not implemented and must not be promised as an available self-service alternative.
- A user can request a JSON export from account settings. A recent password sign-in and explicit `DELETE` confirmation are required for account deletion.
- Deletion is refused when the user owns a workspace with other members. Non-owner memberships are removed; user-attributed records are deleted by database foreign-key cascades. Personal workspaces and their private report objects are removed. A lifecycle audit row remains with user/workspace identifiers cleared.
- Deletion may require retry if private object cleanup or the Auth admin operation is temporarily unavailable. The Edge Function does not return success until the Auth account deletion succeeds.
- Supabase database backups and point-in-time recovery may retain deleted data until the project's configured backup window expires. The operator must set and disclose the actual project retention window before launch; application deletion cannot erase provider backups immediately.
- Existing SQLite/demo data is not included in customer exports and is not migrated into Supabase.

## Consent and launch gate

The current signup screen does not collect an explicit acceptance of a reviewed privacy notice or customer terms. The service therefore must not be opened for commercial signup until the operator supplies the legal notice/terms, decides the applicable consent basis and retention period, and the acceptance flow records the notice version and timestamp. This gate is deliberately not represented as solved by a checkbox or by the Auth signup event.

## Backup and recovery

Before each schema migration, take a Supabase-supported backup and record the migration. Rehearse restore in an isolated project, including both Postgres rows and the private `sentinel-reports` bucket. Verify deletion behavior against restored data and account for provider backup expiry before promising a deletion deadline. No restore or retention schedule has been verified against the customer's live Supabase plan yet.
