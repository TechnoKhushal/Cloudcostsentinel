import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { ApiError, fetchHealth } from "../api";
import { supabase } from "../supabase";

type AuthMode = "sign_in" | "sign_up" | "reset" | "recovery";
type GateState = "checking" | "demo" | "signed_out" | "signed_in" | "needs_setup" | "error";

export function AuthGate({ children }: { children: ReactNode }) {
  const authClient = supabase;
  const [state, setState] = useState<GateState>("checking");
  const [error, setError] = useState("");
  const [recovery, setRecovery] = useState(window.location.hash.includes("type=recovery"));

  useEffect(() => {
    let active = true;
    if (authClient) {
      void authClient.auth.getSession().then(({ data, error: sessionError }) => {
        if (!active) return;
        if (sessionError) { setError("Session could not be restored. Sign in again."); setState("signed_out"); return; }
        setState(data.session ? "signed_in" : "signed_out");
      });
      const { data: { subscription } } = authClient.auth.onAuthStateChange((event, session) => {
        if (!active) return;
        if (event === "PASSWORD_RECOVERY") setRecovery(true);
        if (event === "SIGNED_OUT") { setRecovery(false); setState("signed_out"); }
        else if (session) setState("signed_in");
      });
      return () => { active = false; subscription.unsubscribe(); };
    }
    void fetchHealth().then((health) => {
      if (!active) return;
      if (health.environment === "demo" || import.meta.env.DEV) setState("demo");
      else setState("needs_setup");
    }).catch((reason: unknown) => {
      if (!active) return;
      setError(reason instanceof ApiError ? reason.message : "Could not verify the server mode.");
      setState("error");
    });
    return () => { active = false; };
  }, [authClient]);

  if (state === "checking") return <main className="auth-shell"><div className="auth-card"><span className="auth-mark"><ShieldCheck /></span><h1>Checking secure access</h1><p>Restoring your workspace session…</p></div></main>;
  if (state === "signed_out") return <AuthForm initialError={error} recoveryMode={recovery} />;
  if (state === "needs_setup") return <main className="auth-shell"><div className="auth-card"><span className="auth-mark"><ShieldCheck /></span><p className="auth-kicker">PRODUCTION SIGN IN</p><h1>Authentication is not configured</h1><p>This deployment is not in demo mode, but no public Supabase Auth configuration was provided. Contact the workspace administrator.</p></div></main>;
  if (state === "error") return <main className="auth-shell"><div className="auth-card"><p className="auth-kicker">SERVICE CHECK</p><h1>Could not verify access</h1><p>{error}</p><button className="auth-primary" onClick={() => window.location.reload()}>Retry</button></div></main>;
  if (state === "signed_in" && recovery) return <AuthForm initialError="" recoveryMode />;
  return <>{state === "demo" && <div className="demo-auth-banner">Public synthetic demo · no account session</div>}{state === "signed_in" && authClient && <div className="session-strip"><span>Signed in · Supabase Auth</span><button onClick={() => void authClient.auth.signOut()}>Sign out</button></div>}{children}</>;
}

function AuthForm({ initialError, recoveryMode }: { initialError: string; recoveryMode: boolean }) {
  const [mode, setMode] = useState<AuthMode>(recoveryMode ? "recovery" : "sign_in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const client = supabase;
      if (!client) return;
      if (mode === "sign_in") {
        const { error: authError } = await client.auth.signInWithPassword({ email, password });
        if (authError) throw authError;
      } else if (mode === "sign_up") {
        const { data, error: authError } = await client.auth.signUp({ email, password, options: { emailRedirectTo: window.location.origin } });
        if (authError) throw authError;
        if (!data.session) setMessage("If registration is available, check your email for a verification link before signing in.");
      } else if (mode === "reset") {
        const { error: authError } = await client.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
        if (authError) throw authError;
        setMessage("If an account matches this address, a recovery link has been sent.");
      } else {
        const { error: authError } = await client.auth.updateUser({ password });
        if (authError) throw authError;
        window.location.replace(window.location.pathname);
      }
    } catch {
      setError(mode === "sign_in" ? "Sign in failed. Check your details or use password recovery." : "The request could not be completed. Try again shortly.");
    } finally { setBusy(false); }
  };

  const title = mode === "sign_in" ? "Welcome back" : mode === "sign_up" ? "Create your account" : mode === "reset" ? "Reset your password" : "Choose a new password";
  return <main className="auth-shell"><section className="auth-card" aria-labelledby="auth-title">
    <span className="auth-mark"><ShieldCheck size={22} /></span><p className="auth-kicker">CLOUDCOST SENTINEL · SECURE WORKSPACE</p>
    <h1 id="auth-title">{title}</h1><p className="auth-intro">Cost evidence and decisions stay inside your verified workspace.</p>
    <form onSubmit={(event) => void submit(event)}>
      {mode !== "recovery" && <label>Email address<input type="email" value={email} autoComplete="email" required maxLength={254} onChange={(event) => setEmail(event.target.value)} /></label>}
      {mode !== "reset" && <label>{mode === "recovery" ? "New password" : "Password"}<input type="password" value={password} autoComplete={mode === "sign_in" ? "current-password" : "new-password"} minLength={8} required onChange={(event) => setPassword(event.target.value)} /></label>}
      {error && <p className="auth-error" role="alert">{error}</p>}{message && <p className="auth-success" role="status">{message}</p>}
      <button className="auth-primary" disabled={busy}>{busy ? "Working…" : mode === "sign_in" ? "Sign in" : mode === "sign_up" ? "Create account" : mode === "reset" ? "Send recovery email" : "Update password"}<span aria-hidden="true"> →</span></button>
    </form>
    {!recoveryMode && <div className="auth-links">{mode === "sign_in" ? <><button onClick={() => setMode("reset")}>Forgot password?</button><button onClick={() => setMode("sign_up")}>Create account</button></> : mode !== "recovery" && <button onClick={() => setMode("sign_in")}>Back to sign in</button>}</div>}
    <p className="auth-footnote">Email verification and password recovery are handled by Supabase Auth. Workspace access is checked again by the API.</p>
  </section></main>;
}
