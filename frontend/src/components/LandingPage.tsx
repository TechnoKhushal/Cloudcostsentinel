
import type { HealthInfo } from "../types";

export function LandingPage({ health, hasAnalysis }: { health: HealthInfo | null; hasAnalysis: boolean }) {
  return (
    <main className="landing-page">
      <section className="landing-hero">
        <div className="landing-copy">
          <p className="eyebrow"><span className="eyebrow-mark" /> COST EVIDENCE, CLEARLY REASONED</p>
          <h1>Know what your cloud costs.<br /><em>Understand what to change.</em></h1>
          <p className="hero-summary">CloudCost Sentinel turns cost signals into explainable decisions. Inspect the evidence, understand the trade-offs, and keep a human in control of every consequential action.</p>
          <div className="hero-actions">
            <a className="action-primary" href="#overview">Open the workspace <span aria-hidden="true">→</span></a>
            <a className="action-secondary" href="#principles"><span aria-hidden="true">▣</span>How decisions are made</a>
          </div>
          <p className="hero-caption"><span className={`mode-dot ${health?.environment === "production" ? "live" : "demo"}`} />{health?.environment === "production" ? "Authenticated workspace" : "Public synthetic demonstration"} · No automatic infrastructure changes</p>
        </div>
        <div className="landing-preview" aria-label="Preview of the live analysis workspace">
          <div className="preview-topline"><span>WORKSPACE SNAPSHOT</span><span>{hasAnalysis ? "CURRENT API RESULT" : "WAITING FOR API DATA"}</span></div>
          <div className="preview-grid">
            <div className="preview-metric"><span>DATA MODE</span><strong>{health?.environment === "production" ? "Verified account" : "Synthetic"}</strong><small>Reported by the API</small></div>
            <div className="preview-metric"><span>POLICY ENGINE</span><strong>{health?.providers.decider.state ?? "Checking"}</strong><small>{health?.providers.decider.provider ?? "Provider status"}</small></div>
            <div className="preview-metric preview-dark"><span>DECISION BOUNDARY</span><strong>Human approval stays human.</strong><small>Recommendations never mutate cloud resources.</small></div>
          </div>
          <div className="preview-signal">
            <span className="preview-signal-icon">{hasAnalysis ? "↗" : "?"}</span>
            <div><strong>{hasAnalysis ? "Analysis is available" : "No analysis loaded yet"}</strong><p>{hasAnalysis ? "Current evidence is available in the overview and findings views." : "Open the workspace to load only data returned by this API."}</p></div>
            <a href="#overview" aria-label="Open overview"><span aria-hidden="true">→</span></a>
          </div>
        </div>
        <div className="hero-index" aria-hidden="true">01 / FINOPS LEDGER</div>
      </section>

      <section className="landing-principles" id="principles">
        <div className="section-heading">
          <p className="eyebrow">THE DECISION STANDARD</p>
          <h2>Every alert should answer<br /><em>three questions.</em></h2>
          <p>Keep observed telemetry, computed estimates, and policy recommendations visually distinct.</p>
        </div>
        <div className="principle-grid">
          <article className="principle-card"><span className="principle-number">01</span><h3>What happened?</h3><p>See the values and time series that triggered an analysis, with their source and uncertainty clearly labeled.</p><span className="provenance observed">OBSERVED EVIDENCE</span></article>
          <article className="principle-card"><span className="principle-number">02</span><h3>Why does it matter?</h3><p>Understand the relationship between spend movement, the recorded baseline, and the budget in the current response.</p><span className="provenance estimated">COMPUTED FROM EVIDENCE</span></article>
          <article className="principle-card"><span className="principle-number">03</span><h3>What should we do?</h3><p>Review a deterministic policy recommendation and its explanation. Approval records do not execute cloud changes.</p><span className="provenance recommendation">HUMAN REVIEW</span></article>
        </div>
      </section>

      <section className="landing-security">
        <div className="security-intro"><p className="eyebrow">BUILT FOR FINANCIAL OPERATIONS</p><h2>Evidence first.<br /><em>Actions by people.</em></h2><p>Use the workspace to review API-backed cost analysis, policy traces, and approvals without implying a cloud operation happened.</p><a className="text-link" href="#overview">Review the workspace <span aria-hidden="true">→</span></a></div>
        <div className="security-ledger">
          <div className="security-ledger-head"><span aria-hidden="true">✓</span><span>SAFETY BOUNDARIES</span><span className="ledger-check">API REPORTED</span></div>
          <div className="security-row"><span>Cloud mutations</span><strong>Not performed by this app</strong><span aria-hidden="true">↘</span></div>
          <div className="security-row"><span>Policy outcome</span><strong>Recommendation only</strong><span aria-hidden="true">→</span></div>
          <div className="security-row"><span>Report downloads</span><strong>Private link when available</strong><span aria-hidden="true">✓</span></div>
          <div className="security-foot">Actual providers and persistence mode appear in the workspace status strip.</div>
        </div>
      </section>

      <section className="landing-cta">
        <p className="eyebrow">CLOUD COST DECISION SUPPORT</p>
        <h2>Start with the evidence<br /><em>you can verify.</em></h2>
        <a className="action-primary" href="#overview">Enter CloudCost Sentinel <span aria-hidden="true">→</span></a>
      </section>
    </main>
  );
}
