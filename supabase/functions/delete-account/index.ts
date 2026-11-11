import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";

const allowedOrigins = (Deno.env.get("CLOUDCOST_ALLOWED_ORIGINS") ?? "")
  .split(",").map((origin) => origin.trim()).filter(Boolean);
function configuredKey(name: string, jsonName: string): string | undefined {
  const legacy = Deno.env.get(name);
  if (legacy) return legacy;
  try {
    const keys = JSON.parse(Deno.env.get(jsonName) ?? "{}") as Record<string, string>;
    return keys.default ?? Object.values(keys)[0];
  } catch { return undefined; }
}
const corsHeaders = (origin: string | null): Record<string, string> => ({
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Origin": origin && allowedOrigins.includes(origin) ? origin : "null",
  "Vary": "Origin",
});

function response(status: number, body: Record<string, string>, origin: string | null): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(origin), "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

async function listObjectPaths(
  admin: SupabaseClient,
  folder: string,
): Promise<string[]> {
  const bucket = admin.storage.from("sentinel-reports");
  const files: string[] = [];
  for (let offset = 0; ; offset += 1000) {
    const { data, error } = await bucket.list(folder, { limit: 1000, offset, sortBy: { column: "name", order: "asc" } });
    if (error) throw new Error("storage_list_failed");
    for (const entry of data) {
      const path = folder ? `${folder}/${entry.name}` : entry.name;
      if (entry.id === null) files.push(...await listObjectPaths(admin, path));
      else files.push(path);
    }
    if (data.length < 1000) break;
    if (offset >= 10_000) throw new Error("storage_object_limit");
  }
  return files;
}

Deno.serve(async (request: Request) => {
  const origin = request.headers.get("origin");
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(origin) });
  if (request.method !== "POST") return response(405, { error: "method_not_allowed" }, origin);
  if (!origin || !allowedOrigins.includes(origin)) return response(403, { error: "origin_not_allowed" }, origin);

  const authorization = request.headers.get("authorization");
  const projectUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = configuredKey("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEYS");
  const serviceKey = configuredKey("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEYS");
  if (!authorization?.startsWith("Bearer ") || !projectUrl || !anonKey || !serviceKey || allowedOrigins.length === 0) {
    return response(503, { error: "account_deletion_not_configured" }, origin);
  }

  let confirmation: unknown;
  try { confirmation = (await request.json()).confirmation; } catch { return response(400, { error: "invalid_request" }, origin); }
  if (confirmation !== "DELETE") return response(400, { error: "confirmation_required" }, origin);

  const accessToken = authorization.slice("Bearer ".length);
  const caller = createClient(projectUrl, anonKey, { auth: { persistSession: false, autoRefreshToken: false } });
  const { data: userData, error: userError } = await caller.auth.getUser(accessToken);
  if (userError || !userData.user) return response(401, { error: "authentication_required" }, origin);

  const admin = createClient(projectUrl, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
  const userId = userData.user.id;
  const { data: claimsData, error: claimsError } = await caller.auth.getClaims(accessToken);
  const authTime = Number(claimsData?.claims?.auth_time);
  const authAge = Math.floor(Date.now() / 1000) - authTime;
  if (claimsError || !Number.isFinite(authTime) || authAge < 0 || authAge > 300) {
    return response(401, { error: "recent_password_sign_in_required" }, origin);
  }
  const { data: memberships, error: membershipError } = await admin
    .from("organization_members").select("organization_id,role").eq("user_id", userId);
  if (membershipError) return response(503, { error: "workspace_access_unavailable" }, origin);

  const ownedWorkspaceIds: string[] = [];
  const leaveWorkspaceIds: string[] = [];
  const sharedReportPaths: string[] = [];
  for (const membership of memberships ?? []) {
    const organizationId = String(membership.organization_id);
    const [{ data: organization, error: organizationError }, { data: members, error: membersError }] = await Promise.all([
      admin.from("organizations").select("id,created_by").eq("id", organizationId).maybeSingle(),
      admin.from("organization_members").select("user_id,role").eq("organization_id", organizationId),
    ]);
    if (organizationError || membersError) return response(503, { error: "workspace_access_unavailable" }, origin);
    if (!organization || !members?.some((member) => member.user_id === userId)) {
      return response(409, { error: "workspace_membership_changed_retry" }, origin);
    }
    if (organization.created_by === userId) {
      if (members.length !== 1 || members[0].user_id !== userId) {
        return response(409, { error: "transfer_workspace_ownership_before_deleting_account" }, origin);
      }
      ownedWorkspaceIds.push(organizationId);
    } else {
      if (membership.role === "owner") return response(409, { error: "transfer_workspace_ownership_before_deleting_account" }, origin);
      leaveWorkspaceIds.push(organizationId);
      const [{ data: investigationReports, error: investigationError }, { data: reports, error: reportsError }] = await Promise.all([
        admin.from("investigation_reports").select("storage_path").eq("organization_id", organizationId).eq("user_id", userId),
        admin.from("reports").select("storage_path").eq("organization_id", organizationId).eq("created_by", userId),
      ]);
      if (investigationError || reportsError) return response(503, { error: "workspace_report_cleanup_unavailable" }, origin);
      for (const path of [...(investigationReports ?? []), ...(reports ?? [])].map((item) => item.storage_path)) {
        if (typeof path === "string" && path.startsWith(`${organizationId}/`)) sharedReportPaths.push(path);
      }
    }
  }

  const { data: audit, error: auditError } = await admin.from("account_lifecycle_events")
    .insert({ user_id: userId, action: "account.deletion_requested" }).select("id").single();
  if (auditError || !audit) return response(503, { error: "deletion_audit_unavailable" }, origin);

  try {
    const objectPaths = [...new Set([...sharedReportPaths, ...(await Promise.all(ownedWorkspaceIds.map((id) => listObjectPaths(admin, id)))).flat()])];
    for (let index = 0; index < objectPaths.length; index += 100) {
      const { error } = await admin.storage.from("sentinel-reports").remove(objectPaths.slice(index, index + 100));
      if (error) throw new Error("storage_delete_failed");
    }
  } catch {
    return response(503, { error: "report_cleanup_pending_retry_deletion" }, origin);
  }

  for (const organizationId of leaveWorkspaceIds) {
    const { error } = await admin.from("organization_members").delete().eq("organization_id", organizationId).eq("user_id", userId);
    if (error) return response(503, { error: "workspace_membership_removal_failed_retry" }, origin);
  }

  const { error: deletionError } = await admin.auth.admin.deleteUser(userId);
  if (deletionError) return response(503, { error: "account_deletion_failed_retry" }, origin);
  const { error: auditUpdateError } = await admin.from("account_lifecycle_events")
    .update({ action: "account.deletion_completed", user_id: null, organization_id: null }).eq("id", audit.id);
  if (auditUpdateError) return response(200, { status: "deleted", audit_status: "completion_record_pending" }, origin);
  return response(200, { status: "deleted", audit_status: "recorded" }, origin);
});
