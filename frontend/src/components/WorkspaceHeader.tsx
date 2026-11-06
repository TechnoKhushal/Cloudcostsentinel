import { useState } from "react";
import { Activity, Search, ShieldCheck } from "lucide-react";
import type { HealthInfo } from "../types";

export type WorkspaceScreen =
  | "overview"
  | "costs"
  | "findings"
  | "recommendations"
  | "reports"
  | "integrations"
  | "settings"
  | "landing";

const links: { id: WorkspaceScreen; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "costs", label: "Cost Explorer" },
  { id: "findings", label: "Findings & Anomalies" },
  { id: "recommendations", label: "Recommendations & Approvals" },
  { id: "reports", label: "Reports" },
  { id: "integrations", label: "Integrations" },
  { id: "settings", label: "Settings" },
];

interface WorkspaceHeaderProps {
  active: WorkspaceScreen;
  health: HealthInfo | null;
  query: string;
  onQueryChange: (value: string) => void;
}

export function WorkspaceHeader({ active, health, query, onQueryChange }: WorkspaceHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const mode = health?.environment ?? "checking";

  return (
    <>
      <header className="workspace-header">
        <a className="wordmark" href="#landing" aria-label="CloudCost Sentinel product home">
          <span className="wordmark-symbol"><Activity size={17} strokeWidth={2.5} /></span>
          <span>CLOUDCOST<span className="wordmark-second"> SENTINEL</span></span>
          <span className="version-tag">v2</span>
        </a>
        <nav className={`workspace-nav ${menuOpen ? "is-open" : ""}`} aria-label="Main navigation">
          {links.map((link) => (
            <a
              key={link.id}
              href={`#${link.id}`}
              className={active === link.id ? "active" : ""}
              aria-current={active === link.id ? "page" : undefined}
              onClick={() => setMenuOpen(false)}
            >
              {link.label}
            </a>
          ))}
        </nav>
        <div className="header-tools">
          {["overview", "costs", "findings"].includes(active) && <label className="global-search">
            <Search size={15} aria-hidden="true" />
            <span className="sr-only">Filter current view</span>
            <input id="global-filter" value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Filter current view…" />
            <kbd>⌘ K</kbd>
          </label>}
          <span className="header-mode" title={`Backend environment: ${mode}`}>
            <span className={`mode-dot ${mode === "production" ? "live" : mode === "demo" ? "demo" : ""}`} />
            {mode === "demo" ? "SYNTHETIC DEMO" : mode === "production" ? "PRODUCTION" : mode.toUpperCase()}
          </span>
          <span className="session-indicator" title={health?.auth?.enabled ? "Authentication required" : "Public synthetic demo"}>
            <ShieldCheck size={15} aria-hidden="true" />
            {health?.auth?.enabled ? "AUTHENTICATED" : "PUBLIC"}
          </span>
          <button className="mobile-menu-toggle" type="button" aria-expanded={menuOpen} aria-label={menuOpen ? "Close navigation" : "Open navigation"} onClick={() => setMenuOpen((open) => !open)}>
            {menuOpen ? "×" : "☰"}
          </button>
        </div>
      </header>
      {health?.environment === "demo" && <div className="scope-ribbon"><strong>SYNTHETIC DATA</strong><span>This shared demo uses sample telemetry. No real cloud actions are executed.</span></div>}
    </>
  );
}
