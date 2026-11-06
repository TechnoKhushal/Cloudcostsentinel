import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Shield } from "lucide-react";
import { fetchAccountProfile, updateAccountProfile, type AccountProfile } from "../api";
import type { HealthInfo } from "../types";

export function IntegrationsPage({ health }: { health: HealthInfo | null }) {
  const integrations = [
    { title: "Cost analysis policy", symbol: "POL", provider: health?.providers.decider.provider, state: health?.providers.decider.state, detail: health?.providers.decider.model_id ?? "Waiting for backend health." },
    { title: "Narrative reports", symbol: "AI", provider: health?.providers.narrator.provider, state: health?.providers.narrator.state, detail: health?.providers.narrator.model_id ?? "Waiting for backend health." },
    { title: "AWS Cost Explorer", symbol: "AWS", provider: "aws_cost_explorer", state: health?.providers.cost_explorer.enabled ? health.providers.cost_explorer.status : "disabled", detail: health?.providers.cost_explorer.message ?? "Status will be available after the API responds." },
    { title: "Persistent storage", symbol: "DB", provider: health?.persistence?.provider, state: health?.persistence?.state, detail: health?.persistence ? `Persistence: ${health.persistence.provider}.` : "Waiting for backend health." },
  ];
  return <main className="page-content"><div className="page-heading-row"><div><p className="eyebrow">CONNECTIVITY &amp; PROVENANCE</p><h1>Integration <em>status</em></h1><p className="page-lede">Provider states are reported by the API. This page does not imply that an integration is configured when it is disabled.</p></div></div>
    <div className="integration-grid">{integrations.map(({ title, symbol, provider, state, detail }) => <article className="integration-card" key={title}><div className="integration-card-top"><span className="integration-icon">{symbol}</span><span className={`integration-state state-${state === "connected" || state === "available" ? "ready" : state === "simulated" ? "demo" : state === "disabled" || state === "disabled_by_configuration" ? "off" : "unknown"}`}><i />{state ? state.replaceAll("_", " ") : "checking"}</span></div><h2>{title}</h2><p className="integration-provider">{provider ?? "Not reported"}</p><p>{detail}</p></article>)}</div>
    <div className="security-note"><Shield size={18} /><div><strong>Current safety boundary</strong><p>{health?.safety_guarantee ?? "Safety status is unavailable until the backend responds."} Production blocks shared AWS credentials because tenant-specific cloud accounts are not implemented.</p></div></div>
  </main>;
}

export function AccountSettingsPage({ enabled }: { enabled: boolean }) {
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [status, setStatus] = useState("");
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

  return <main className="page-content"><div className="page-heading-row"><div><p className="eyebrow">ACCOUNT &amp; SECURITY</p><h1>Workspace <em>settings</em></h1><p className="page-lede">Manage the profile fields currently supported by this API.</p></div></div>
    {!enabled ? <section className="empty-state"><h2>Account settings require an authenticated Supabase workspace.</h2><p>The public synthetic demo does not have persistent user profiles.</p></section> : <div className="settings-layout"><section className="settings-card"><div className="settings-card-heading"><span className="eyebrow">PERSONAL PROFILE</span>{profile && <span className="role-chip">{profile.role}</span>}</div>
      {loading ? <p className="loading-copy" role="status">Loading account profile…</p> : <form className="profile-form" onSubmit={(event) => void save(event)}><label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={120} autoComplete="name" /></label><button className="action-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button></form>}
      {profile && <dl className="account-facts"><div><dt>USER ID</dt><dd>{profile.user_id}</dd></div><div><dt>WORKSPACE ID</dt><dd>{profile.organization_id ?? "Not assigned"}</dd></div></dl>}
      {error && <p role="alert" className="form-error">{error}</p>}{status && <p role="status" className="form-success"><CheckCircle2 size={15} />{status}</p>}
    </section><section className="settings-card settings-security"><Shield size={19} /><h2>Sign-in &amp; recovery</h2><p>Email verification, password recovery, session refresh, and logout are handled by Supabase Auth. Workspace permissions are checked again by the API.</p><p>MFA, invitations, member administration, and organization switching are not available in this release.</p></section></div>}
  </main>;
}
