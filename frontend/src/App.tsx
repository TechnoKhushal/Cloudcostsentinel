import React, { useEffect, useRef, useState } from "react";
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
  const [toastMessage, setToastMessage] = useState<{ text: string; isError: boolean } | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const showToast = (text: string, isError: boolean = false) => {
    setToastMessage({ text, isError });
    setTimeout(() => {
      if (isMountedRef.current) {
        setToastMessage(null);
      }
    }, 4500);
  };

  const executeAnalysis = async (scenarioId: string) => {
    // Cancel in-flight request to prevent race conditions on fast scenario toggling
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const res = await runAnalysis(scenarioId, false, controller.signal);
      if (!isMountedRef.current) return;
      setAnomaly(res.anomaly);
      setDecision(res.decision);
      setReport(res.report);
      if (res.approval) {
        setApprovals((prev) => [res.approval!, ...prev.filter((a) => a.id !== res.approval!.id)]);
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        return; // Normal cancellation from switching scenarios
      }
      if (isMountedRef.current) {
        setError(err.message || "Analysis failed.");
      }
    } finally {
      if (isMountedRef.current && abortControllerRef.current === controller) {
        setLoading(false);
      }
    }
  };

  // Initial Load
  useEffect(() => {
    async function init() {
      try {
        const [healthResult, scenariosResult, approvalsResult] = await Promise.allSettled([
          fetchHealth(), fetchScenarios(), fetchApprovals(),
        ]);
        if (!isMountedRef.current) return;
        if (healthResult.status === "fulfilled") setHealth(healthResult.value);
        if (scenariosResult.status === "fulfilled") setScenarios(scenariosResult.value);
        if (approvalsResult.status === "fulfilled") setApprovals(approvalsResult.value);
        const failures = [healthResult, scenariosResult, approvalsResult]
          .filter((result): result is PromiseRejectedResult => result.status === "rejected")
          .map((result) => result.reason instanceof Error ? result.reason.message : "A dashboard service could not be loaded.");
        if (failures.length) setError(failures.join(" "));

        // Do not start a demo analysis when the backend could not supply its scenarios.
        if (scenariosResult.status === "fulfilled" && scenariosResult.value.length > 0) {
          await executeAnalysis("compute_spike");
        }
      } catch (err: any) {
        if (isMountedRef.current) {
          setError(err.message || "Failed to initialize application.");
        }
      }
    }
    init();
  }, []);

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
      showToast(`Approval ${id} successfully recorded as ${action.toUpperCase()}.`, false);
    } catch (err: any) {
      showToast(err.message || "Approval decision failed.", true);
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

      {/* Accessible Inline Notification Toast */}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          style={{
            background: toastMessage.isError ? "rgba(239, 68, 68, 0.2)" : "rgba(16, 185, 129, 0.2)",
            border: `1px solid ${toastMessage.isError ? "rgba(239, 68, 68, 0.5)" : "rgba(16, 185, 129, 0.5)"}`,
            padding: "0.6rem 1rem",
            borderRadius: "6px",
            color: toastMessage.isError ? "#fca5a5" : "#6ee7b7",
            fontSize: "0.85rem",
            marginBottom: "1rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{toastMessage.text}</span>
          <button
            onClick={() => setToastMessage(null)}
            style={{
              background: "transparent",
              border: "none",
              color: "inherit",
              cursor: "pointer",
              fontSize: "1rem",
              paddingLeft: "0.5rem",
            }}
          >
            ×
          </button>
        </div>
      )}

      {error && (
        <div
          role="alert"
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
