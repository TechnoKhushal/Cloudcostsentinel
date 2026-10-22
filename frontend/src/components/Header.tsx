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
            Autonomous Cloud Spend Decision Agent & FinOps Guardian
          </div>
        </div>
      </div>

      <div className="header-status-pills">
        {/* Mode pill */}
        <span className={`status-pill ${isSimulated ? "pill-amber" : "pill-emerald"}`}>
          <span className="dot">●</span>
          {isSimulated ? "SIMULATED / DEMO MODE" : "LIVE AWS ACTIVE"}
        </span>

        {/* Decider Model Pill */}
        <span className={`status-pill ${health?.providers.decider.provider === "http" ? "pill-cyan" : "pill-amber"}`}>
          <Cpu size={14} />
          Decider 2B: {health?.providers.decider.provider === "http" ? "Live HTTP" : "Simulated Mock"}
        </span>

        {/* Bedrock Model Pill */}
        <span className={`status-pill ${health?.providers.bedrock.provider === "bedrock" ? "pill-purple" : "pill-amber"}`}>
          <Sparkles size={14} />
          Bedrock: {health?.providers.bedrock.provider === "bedrock" ? "Claude 3.7 Sonnet (Live)" : "Demo Narrator (Simulated)"}
        </span>

        {/* AWS Cost Explorer Status */}
        <span className="status-pill">
          <Cloud size={14} />
          Cost Explorer: {health?.providers.cost_explorer.enabled ? "Enabled" : "Off (Safe)"}
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
