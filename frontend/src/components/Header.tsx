import { Cloud, Cpu, Lock, ShieldAlert, Sparkles } from "lucide-react";
import type { HealthInfo } from "../types";

interface HeaderProps {
  health: HealthInfo | null;
  isSimulated: boolean | null;
}

function providerLabel(provider: string | undefined, state: string | undefined): string {
  if (!provider || !state) return "Checking";
  if (state === "simulated" || provider === "mock") return "Simulated";
  if (state === "disabled" || provider === "disabled") return "Off";
  if (state === "connected") return "Connected";
  if (state === "configured_unverified") return "Configured · unverified";
  if (state === "offline") return "Offline · deterministic";
  return state.replaceAll("_", " ");
}

export const Header = ({ health, isSimulated }: HeaderProps) => (
  <header className="app-header">
    <a className="brand-section" href="#page-title" aria-label="CloudCost Sentinel home">
      <span className="brand-icon-wrapper"><ShieldAlert size={24} aria-hidden="true" /></span>
      <span className="brand-copy"><span className="brand-title">CloudCost Sentinel</span><span className="brand-subtitle">Cloud spend decision support</span></span>
    </a>
    <div className="header-status-pills" aria-label="Backend and provider status">
      <span className={`status-pill ${health?.environment === "demo" ? "pill-amber" : ""}`}>{health?.environment ? `Mode · ${health.environment}` : "Mode · checking"}</span>
      <span className={`status-pill ${isSimulated === null ? "" : isSimulated ? "pill-amber" : "pill-emerald"}`}>{isSimulated === null ? "Cost data · not analyzed" : isSimulated ? "Cost data · simulated" : "Cost data · non-simulated"}</span>
      <span className="status-pill"><Cpu size={14} aria-hidden="true" />Decider · {providerLabel(health?.providers.decider.provider, health?.providers.decider.state)}</span>
      <span className="status-pill"><Sparkles size={14} aria-hidden="true" />Narrator · {providerLabel(health?.providers.narrator.provider, health?.providers.narrator.state)}</span>
      <span className="status-pill"><Cloud size={14} aria-hidden="true" />Cost Explorer · {health ? health.providers.cost_explorer.enabled ? "Enabled · unverified" : "Off" : "Checking"}</span>
      <span className="status-pill"><Lock size={14} aria-hidden="true" />No automatic cloud changes</span>
    </div>
  </header>
);
