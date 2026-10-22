import React from "react";
import { Play, Flame, RotateCcw, AlertCircle } from "lucide-react";
import type { Scenario } from "../types";

interface ScenarioControlsProps {
  scenarios: Scenario[];
  selectedScenarioId: string;
  onSelectScenario: (id: string) => void;
  onRunAnalysis: () => void;
  onSimulateSpike: () => void;
  onReset: () => void;
  loading: boolean;
}

export const ScenarioControls: React.FC<ScenarioControlsProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  onRunAnalysis,
  onSimulateSpike,
  onReset,
  loading,
}) => {
  return (
    <>
      <div className="simulated-banner">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <AlertCircle size={16} color="#f59e0b" />
          <span>
            <strong>SIMULATED DATA / SAFE DEMO ENVIRONMENT:</strong> Telemetry values and scenarios are deterministic for reproducible evaluation.
          </span>
        </div>
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          Tags: #strands-decider-2b #policy
        </span>
      </div>

      <div className="scenario-toolbar">
        <div className="scenario-select-group">
          <label style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-secondary)" }}>
            Scenario:
          </label>
          <select
            className="select-input"
            value={selectedScenarioId}
            onChange={(e) => onSelectScenario(e.target.value)}
            disabled={loading}
          >
            {scenarios.map((sc) => (
              <option key={sc.id} value={sc.id}>
                {sc.name} ({sc.service})
              </option>
            ))}
          </select>
        </div>

        <div className="toolbar-buttons">
          <button
            className="btn btn-spike"
            onClick={onSimulateSpike}
            disabled={loading}
          >
            <Flame size={15} />
            Simulate Compute Spike
          </button>

          <button
            className="btn btn-primary"
            onClick={onRunAnalysis}
            disabled={loading}
          >
            <Play size={15} />
            {loading ? "Analyzing..." : "Re-run Analysis"}
          </button>

          <button
            className="btn btn-secondary"
            onClick={onReset}
            disabled={loading}
          >
            <RotateCcw size={15} />
            Reset Demo
          </button>
        </div>
      </div>
    </>
  );
};
