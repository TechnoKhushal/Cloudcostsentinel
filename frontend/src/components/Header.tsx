import React from "react";
import { ShieldAlert, Cpu, Sparkles, Cloud, Lock } from "lucide-react";
import type { HealthInfo } from "../types";

interface HeaderProps {
  health: HealthInfo | null;
  isSimulated: boolean;
}

export const Header: React.FC<HeaderProps> = ({ health, isSimulated }) => {
  return (
    <header className="app-header">
      <div className="brand-section">
        <div className="brand-icon-wrapper">
          <ShieldAlert size={26} color="#ffffff" />
        </div>
        <div>
          <div className="brand-title">CloudCost Sentinel</div>
          <div className="brand-subtitle">
            Cloud Spend Decision Support & FinOps Review
          </div>
        </div>
      </div>

      <div className="header-status-pills">
        {/* Mode pill */}
        <span className={`status-pill ${isSimulated ? "pill-amber" : "pill-emerald"}`}>
          <span className="dot">●</span>
          {isSimulated ? "SIMULATED COST DATA" : "LIVE COST DATA"}
        </span>

        <span className={`status-pill ${health?.status === "ready" || health?.status === "healthy" || health?.status === "simulated" ? "pill-emerald" : "pill-amber"}`}>
          Backend: {health?.environment === "demo" ? "SIMULATED DEMO" : health?.status ?? "OFFLINE"}
        </span>

        {/* Decider Model Pill */}
        <span className={`status-pill ${health?.providers.decider.provider === "http" ? "pill-cyan" : "pill-amber"}`}>
          <Cpu size={14} />
          Decider: {health?.providers.decider.provider === "mock" ? "Simulated" : health?.providers.decider.state === "connected" ? "Connected" : "Configured, unverified"}
        </span>

        {/* Bedrock Model Pill */}
        <span className={`status-pill ${health?.providers.bedrock.provider === "bedrock" ? "pill-purple" : "pill-amber"}`}>
          <Sparkles size={14} />
          Bedrock: {health?.providers.bedrock.provider === "mock" ? "Simulated narrator" : health?.providers.bedrock.state === "connected" ? "Connected" : "Configured, unverified"}
        </span>

        {/* AWS Cost Explorer Status */}
        <span className="status-pill">
          <Cloud size={14} />
          Cost Explorer: {health?.providers.cost_explorer.enabled ? "Configured, unverified" : "Off (Safe)"}
        </span>

        {/* Safety Lock Pill */}
        <span className="status-pill">
          <Lock size={14} />
          Zero Mutation Sandbox
        </span>
      </div>
    </header>
  );
};
