import React, { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { ScenarioControls } from "./components/ScenarioControls";
import { OverviewCards } from "./components/OverviewCards";
import { SpendChart } from "./components/SpendChart";
import { DecisionPanel } from "./components/DecisionPanel";
import { BedrockReportPanel } from "./components/BedrockReportPanel";
import { ApprovalsFeed } from "./components/ApprovalsFeed";
import type {
  ApprovalItem,
  CostAnomaly,
  DeciderResponseTrace,
  BedrockReport,
  HealthInfo,
  Scenario,
} from "./types";
import {
  fetchHealth,
  fetchScenarios,
  runAnalysis,
  fetchApprovals,
  submitApprovalDecision,
} from "./api";

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("compute_spike");
  const [anomaly, setAnomaly] = useState<CostAnomaly | null>(null);
  const [decision, setDecision] = useState<DeciderResponseTrace | null>(null);
  const [report, setReport] = useState<BedrockReport | null>(null);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Initial Load
  useEffect(() => {
    async function init() {
      try {
        const [healthData, scenariosData, approvalsData] = await Promise.all([
          fetchHealth().catch(() => null),
          fetchScenarios().catch(() => []),
          fetchApprovals().catch(() => []),
        ]);
        setHealth(healthData);
        setScenarios(scenariosData);
        setApprovals(approvalsData);

        // Run initial analysis on default scenario
        await executeAnalysis("compute_spike");
      } catch (err: any) {
        setError(err.message || "Failed to initialize application.");
      }
    }
    init();
  }, []);

  const executeAnalysis = async (scenarioId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await runAnalysis(scenarioId);
      setAnomaly(res.anomaly);
      setDecision(res.decision);
      setReport(res.report);
      if (res.approval) {
        setApprovals((prev) => [res.approval!, ...prev.filter((a) => a.id !== res.approval!.id)]);
      }
    } catch (err: any) {
      setError(err.message || "Analysis failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectScenario = (id: string) => {
    setSelectedScenarioId(id);
    executeAnalysis(id);
  };

  const handleSimulateSpike = () => {
    setSelectedScenarioId("compute_spike");
    executeAnalysis("compute_spike");
  };

  const handleResetDemo = () => {
    setSelectedScenarioId("stable_baseline");
    executeAnalysis("stable_baseline");
  };

  const handleApprovalDecision = async (id: string, action: "approved" | "rejected") => {
    try {
      const updated = await submitApprovalDecision(id, action);
      setApprovals((prev) => prev.map((a) => (a.id === id ? updated : a)));
    } catch (err: any) {
      alert(`Approval error: ${err.message}`);
    }
  };

  return (
    <div>
      <Header health={health} isSimulated={anomaly?.is_simulated ?? true} />

      <ScenarioControls
        scenarios={scenarios}
        selectedScenarioId={selectedScenarioId}
        onSelectScenario={handleSelectScenario}
        onRunAnalysis={() => executeAnalysis(selectedScenarioId)}
        onSimulateSpike={handleSimulateSpike}
        onReset={handleResetDemo}
        loading={loading}
      />

      {error && (
        <div
          style={{
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid rgba(239, 68, 68, 0.4)",
            padding: "0.75rem 1rem",
            borderRadius: "8px",
            color: "#fca5a5",
            fontSize: "0.85rem",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      {anomaly && (
        <OverviewCards
          metrics={anomaly.metrics}
          service={anomaly.service}
          environment={anomaly.environment}
        />
      )}

      <div className="dashboard-grid">
        {/* Left Column: Spend Telemetry Chart + Bedrock Report */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {anomaly && (
            <SpendChart
              data={anomaly.time_series}
              baseline={anomaly.metrics.baseline_spend}
              service={anomaly.service}
            />
          )}

          <BedrockReportPanel report={report} />
        </div>

        {/* Right Column: Strands Decider 2B Decision + Approvals Queue */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <DecisionPanel decision={decision} />

          <ApprovalsFeed approvals={approvals} onDecide={handleApprovalDecision} />
        </div>
      </div>
    </div>
  );
};

export default App;
