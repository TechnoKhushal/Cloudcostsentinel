import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CheckCircle2, Shield } from "lucide-react";
import { connectAwsIntegration, disconnectAwsIntegration, fetchAccountProfile, fetchAwsIntegration, fetchWorkspaceFinOpsSettings, updateAccountProfile, updateWorkspaceFinOpsSettings, verifyAwsIntegration, type AccountProfile, type AwsIntegration } from "../api";
import type { HealthInfo } from "../types";

export function IntegrationsPage({ health }: { health: HealthInfo | null }) {
  const productionWorkspace = Boolean(health?.auth?.enabled && health.persistence?.provider === "supabase");
  const [aws, setAws] = useState<AwsIntegration | null>(null);
  const [roleArn, setRoleArn] = useState("");
  const [awsError, setAwsError] = useState("");
  const [awsNotice, setAwsNotice] = useState("");
  const [awsBusy, setAwsBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!productionWorkspace) return;
    const controller = new AbortController();
    void fetchAwsIntegration(controller.signal).then((result) => {
      setAws(result);
      setRoleArn(result.connection?.role_arn ?? "");
      setAwsError("");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setAwsError(reason instanceof Error ? reason.message : "AWS integration could not be loaded.");
    });
    return () => controller.abort();
  }, [productionWorkspace]);

  const trustPolicy = useMemo(() => {
    const connection = aws?.connection;
    const principal = aws?.platform_principal_arn;
    return connection && principal ? JSON.stringify({ Version: "2012-10-17", Statement: [{ Effect: "Allow", Principal: { AWS: principal }, Action: "sts:AssumeRole", Condition: { StringEquals: { "sts:ExternalId": connection.external_id } } }] }, null, 2) : "";
  }, [aws]);
  const costReadPolicy = useMemo(() => JSON.stringify({ Version: "2012-10-17", Statement: [{ Effect: "Allow", Action: ["ce:GetCostAndUsage"], Resource: "*" }] }, null, 2), []);

  const saveRole = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setAwsBusy(true); setAwsError(""); setAwsNotice("");
    try {
      const result = await connectAwsIntegration(roleArn);
      setAws((previous) => ({ enabled: true, daily_query_limit: previous?.daily_query_limit ?? 20, connection: result.connection, platform_principal_arn: result.platform_principal_arn ?? previous?.platform_principal_arn ?? null }));
      setAwsNotice("Role saved. Add the trust policy in your AWS account, attach the read-only Cost Explorer policy, then verify.");
    } catch (reason) { setAwsError(reason instanceof Error ? reason.message : "AWS role could not be saved."); }
    finally { setAwsBusy(false); }
  };
  const verifyRole = async () => {
    setAwsBusy(true); setAwsError(""); setAwsNotice("");
    try {
      const result = await verifyAwsIntegration();
      setAws((current) => current?.connection ? { ...current, connection: { ...current.connection, status: "connected", verified_at: result.verified_at } } : current);
      setAwsNotice(`AWS account ${result.account_id} verified. Cost Explorer read access is active.`);
    } catch (reason) { setAwsError(reason instanceof Error ? reason.message : "AWS verification failed."); }
    finally { setAwsBusy(false); }
  };
  const disconnectRole = async () => {
    setAwsBusy(true); setAwsError(""); setAwsNotice("");
    try { await disconnectAwsIntegration(); setAws((current) => current ? { ...current, connection: null } : current); setRoleArn(""); setAwsNotice("AWS role disconnected from this workspace. Remove CloudCost Sentinel from the role trust policy in AWS to revoke its access."); }
    catch (reason) { setAwsError(reason instanceof Error ? reason.message : "AWS role could not be disconnected."); }
    finally { setAwsBusy(false); }
  };
  const copyTrustPolicy = async () => {
    try { await navigator.clipboard.writeText(trustPolicy); setCopied(true); window.setTimeout(() => setCopied(false), 1800); }
    catch { setAwsError("Clipboard access is unavailable. Select and copy the trust policy text."); }
  };
  const integrations = [
    { title: "Cost analysis policy", symbol: "POL", provider: health?.providers.decider.provider, state: health?.providers.decider.state, detail: health?.providers.decider.model_id ?? "Waiting for backend health." },
    { title: "Narrative reports", symbol: "AI", provider: health?.providers.narrator.provider, state: health?.providers.narrator.state, detail: health?.providers.narrator.model_id ?? "Waiting for backend health." },
    { title: "AWS Cost Explorer", symbol: "AWS", provider: "aws_cost_explorer", state: aws?.connection?.status ?? (productionWorkspace ? aws?.enabled ? "not_connected" : "disabled" : "not_configured"), detail: aws?.connection ? `Customer role for account ${aws.connection.account_id}. Status: ${aws.connection.status}.` : health?.providers.cost_explorer.message ?? "AWS Cost Explorer status is unavailable." },
    { title: "Persistent storage", symbol: "DB", provider: health?.persistence?.provider, state: health?.persistence?.state, detail: health?.persistence ? `Persistence: ${health.persistence.provider}.` : "Waiting for backend health." },
  ];
  return <main className="page-content"><div className="page-heading-row"><div><p className="eyebrow">CONNECTIVITY &amp; PROVENANCE</p><h1>Integration <em>status</em></h1><p className="page-lede">Provider states are reported by the API. This page does not imply that an integration is configured when it is disabled.</p></div></div>
    <div className="integration-grid">{integrations.map(({ title, symbol, provider, state, detail }) => <article className="integration-card" key={title}><div className="integration-card-top"><span className="integration-icon">{symbol}</span><span className={`integration-state state-${state === "connected" || state === "available" ? "ready" : state === "simulated" ? "demo" : state === "disabled" || state === "disabled_by_configuration" ? "off" : "unknown"}`}><i />{state ? state.replaceAll("_", " ") : "checking"}</span></div><h2>{title}</h2><p className="integration-provider">{provider ?? "Not reported"}</p><p>{detail}</p></article>)}</div>
    {productionWorkspace && <section className="aws-connection-card"><div className="ledger-panel-heading"><div><span className="eyebrow">CUSTOMER-OWNED IAM ROLE</span><h2>Connect an AWS billing account</h2></div><span className={`provenance ${aws?.connection?.status === "connected" ? "observed" : "review"}`}>{aws?.connection?.status ?? (aws?.enabled ? "NOT CONNECTED" : "PLATFORM DISABLED")}</span></div>
      <p className="page-lede">CloudCost Sentinel assumes a role in your AWS account with temporary credentials and calls only the billing read API. It never receives your account keys and cannot change cloud resources.</p>
      {!aws?.enabled && <p className="inline-error">AWS integration is disabled by the platform administrator. No AWS analysis is available.</p>}
      {aws?.enabled && <form className="aws-connect-form" onSubmit={(event) => void saveRole(event)}><label htmlFor="aws-role-arn">AWS IAM role ARN</label><div className="aws-connect-row"><input id="aws-role-arn" value={roleArn} onChange={(event) => setRoleArn(event.target.value)} placeholder="arn:aws:iam::123456789012:role/CloudCostSentinelReadOnly" required maxLength={2048} autoComplete="off"/><button className="action-primary" type="submit" disabled={awsBusy}>{awsBusy ? "Saving…" : "Save role"}</button></div></form>}
      {aws?.connection && <><div className="aws-account-meta"><span>ACCOUNT <strong>{aws.connection.account_id}</strong></span><span>STATUS <strong>{aws.connection.status}</strong></span>{aws.connection.verified_at && <span>VERIFIED <strong>{new Date(aws.connection.verified_at).toLocaleString()}</strong></span>}</div>
        {trustPolicy && <div className="aws-trust-policy"><div><strong>1 · Add this trust relationship in the customer role</strong><button type="button" className="action-secondary compact-action" onClick={() => void copyTrustPolicy()}>{copied ? "Copied" : "Copy policy"}</button></div><pre>{trustPolicy}</pre><p>Attach an identity policy that allows only <code>ce:GetCostAndUsage</code>. The platform identity must be restricted to <code>sts:AssumeRole</code>.</p></div>}
        <div className="aws-trust-policy"><div><strong>Read-only permissions for the customer role</strong></div><pre>{costReadPolicy}</pre><p>Create the role as <code>CloudCostSentinelReadOnly</code>; do not attach write or resource-management permissions.</p></div>
        <div className="aws-connection-actions"><button type="button" className="action-primary" onClick={() => void verifyRole()} disabled={awsBusy || !aws.enabled}>{awsBusy ? "Checking…" : "2 · Verify AWS connection"}</button><button type="button" className="action-secondary compact-action" onClick={() => void disconnectRole()} disabled={awsBusy}>Disconnect workspace</button><small>Verification makes one AWS Cost Explorer API request; AWS charges $0.01 per request. Analysis is user-triggered, limited to one Cost Explorer request, and capped at {aws.daily_query_limit} queries per workspace per UTC day.</small></div>
      </>}
      {awsError && <p role="alert" className="form-error">{awsError}</p>}{awsNotice && <p role="status" className="form-success">{awsNotice}</p>}
    </section>}
    <div className="security-note"><Shield size={18} /><div><strong>Current safety boundary</strong><p>{health?.safety_guarantee ?? "Safety status is unavailable until the backend responds."} Customer AWS access is isolated by a unique external ID and a role belonging to that customer's account.</p></div></div>
  </main>;
}

export function AccountSettingsPage({ enabled }: { enabled: boolean }) {
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [status, setStatus] = useState("");
  const [budgetAmount, setBudgetAmount] = useState("");
  const [budgetCurrency, setBudgetCurrency] = useState("USD");
  const [budgetStatus, setBudgetStatus] = useState("");
  const [budgetError, setBudgetError] = useState("");
  const [budgetSaving, setBudgetSaving] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    void fetchAccountProfile(controller.signal).then((data) => {
      setProfile(data);
      setDisplayName(data.display_name ?? "");
      setError("");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Profile could not be loaded.");
    });
    void fetchWorkspaceFinOpsSettings(controller.signal).then((result) => {
      if (result.budget) {
        setBudgetAmount(String(result.budget.monthly_budget));
        setBudgetCurrency(result.budget.currency);
      }
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setBudgetError(reason instanceof Error ? reason.message : "Workspace budget could not be loaded.");
    });
    return () => controller.abort();
  }, [enabled]);

  const loading = enabled && !profile && !error;

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true); setError(""); setStatus("");
    try {
      const next = await updateAccountProfile(displayName);
      setProfile(next); setDisplayName(next.display_name ?? ""); setStatus("Profile saved.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Profile could not be saved.");
    } finally { setSaving(false); }
  };

  const saveBudget = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBudgetSaving(true); setBudgetError(""); setBudgetStatus("");
    try {
      const result = await updateWorkspaceFinOpsSettings(Number(budgetAmount), budgetCurrency);
      setBudgetAmount(String(result.budget?.monthly_budget ?? budgetAmount));
      setBudgetCurrency(result.budget?.currency ?? budgetCurrency);
      setBudgetStatus("Workspace budget saved.");
    } catch (reason) { setBudgetError(reason instanceof Error ? reason.message : "Workspace budget could not be saved."); }
    finally { setBudgetSaving(false); }
  };

  return <main className="page-content"><div className="page-heading-row"><div><p className="eyebrow">ACCOUNT &amp; SECURITY</p><h1>Workspace <em>settings</em></h1><p className="page-lede">Manage the profile fields currently supported by this API.</p></div></div>
    {!enabled ? <section className="empty-state"><h2>Account settings require an authenticated Supabase workspace.</h2><p>The public synthetic demo does not have persistent user profiles.</p></section> : <div className="settings-layout"><section className="settings-card"><div className="settings-card-heading"><span className="eyebrow">PERSONAL PROFILE</span>{profile && <span className="role-chip">{profile.role}</span>}</div>
      {loading ? <p className="loading-copy" role="status">Loading account profile…</p> : <form className="profile-form" onSubmit={(event) => void save(event)}><label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={120} autoComplete="name" /></label><button className="action-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button></form>}
      {profile && <dl className="account-facts"><div><dt>USER ID</dt><dd>{profile.user_id}</dd></div><div><dt>WORKSPACE ID</dt><dd>{profile.organization_id ?? "Not assigned"}</dd></div></dl>}
      {error && <p role="alert" className="form-error">{error}</p>}{status && <p role="status" className="form-success"><CheckCircle2 size={15} />{status}</p>}
    </section><section className="settings-card"><div className="settings-card-heading"><span className="eyebrow">COST GOVERNANCE</span><span className="provenance observed">WORKSPACE</span></div><h2>Monthly cloud budget</h2><p className="settings-help">This target is used for forecast and budget-burn calculations. Choose the same currency AWS Cost Explorer returns for your payer account.</p><form className="profile-form" onSubmit={(event) => void saveBudget(event)}><label htmlFor="workspace-budget">Budget amount<input id="workspace-budget" type="number" min="0.01" max="1000000000000" step="0.01" value={budgetAmount} onChange={(event) => setBudgetAmount(event.target.value)} required /></label><label htmlFor="budget-currency">Three-letter currency code<input id="budget-currency" value={budgetCurrency} onChange={(event) => setBudgetCurrency(event.target.value.toUpperCase().slice(0, 3))} minLength={3} maxLength={3} pattern="[A-Za-z]{3}" required /></label><button className="action-primary" type="submit" disabled={budgetSaving || !enabled}>{budgetSaving ? "Saving…" : "Save workspace budget"}</button></form>{budgetError && <p role="alert" className="form-error">{budgetError}</p>}{budgetStatus && <p role="status" className="form-success">{budgetStatus}</p>}</section><section className="settings-card settings-security"><Shield size={19} /><h2>Sign-in &amp; recovery</h2><p>Email verification, password recovery, session refresh, and logout are handled by Supabase Auth. Workspace permissions are checked again by the API.</p><p>MFA, invitations, member administration, and organization switching are not available in this release.</p></section></div>}
  </main>;
}
