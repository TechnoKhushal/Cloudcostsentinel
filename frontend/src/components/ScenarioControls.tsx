import { AlertCircle, Flame, Play, RotateCcw } from "lucide-react";
import type { Scenario } from "../types";

interface ScenarioControlsProps {
  scenarios: Scenario[];
  selectedScenarioId: string;
  onSelectScenario: (id: string) => void;
  onRunAnalysis: () => void;
  onSimulateSpike: () => void;
  onReset: () => void;
  loading: boolean;
  scenariosError?: string | null;
  onRetryScenarios?: () => void;
}

export const ScenarioControls = ({ scenarios, selectedScenarioId, onSelectScenario, onRunAnalysis, onSimulateSpike, onReset, loading, scenariosError, onRetryScenarios }: ScenarioControlsProps) => (
  <>
    <div className="simulated-banner"><div><AlertCircle size={16} aria-hidden="true" /><span><strong>SYNTHETIC SCENARIOS</strong> · Reproducible sample telemetry. No real cloud operations run.</span></div><span className="banner-meta">#finops · #policy-review</span></div>
    <section className="scenario-toolbar" aria-label="Scenario analysis controls">
      <div className="scenario-select-group">
        <label htmlFor="scenario-select">Scenario</label>
        <select id="scenario-select" className="select-input" value={selectedScenarioId} onChange={(event) => onSelectScenario(event.target.value)} disabled={loading || scenarios.length === 0} aria-describedby={scenariosError ? "scenario-error" : undefined}>
          {scenarios.length === 0 ? <option value="">{loading ? "Loading scenarios…" : "Scenarios unavailable"}</option> : scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name} · {scenario.service}</option>)}
        </select>
      </div>
      <div className="toolbar-buttons">
        <button type="button" className="btn btn-spike" onClick={onSimulateSpike} disabled={loading || !scenarios.some((scenario) => scenario.id === "compute_spike")}><Flame size={15} aria-hidden="true" />Compute spike</button>
        <button type="button" className="btn btn-primary" onClick={onRunAnalysis} disabled={loading || scenarios.length === 0}><Play size={15} aria-hidden="true" />{loading ? "Analyzing…" : "Run analysis"}</button>
        <button type="button" className="btn btn-secondary" onClick={onReset} disabled={loading || !scenarios.some((scenario) => scenario.id === "stable_baseline")}><RotateCcw size={15} aria-hidden="true" />Stable baseline</button>
      </div>
      {scenariosError && <div id="scenario-error" className="scenario-error" role="alert"><span>Scenarios could not be loaded: {scenariosError}</span><button type="button" className="btn btn-secondary btn-sm" onClick={onRetryScenarios} disabled={loading}>Retry scenario list</button></div>}
    </section>
  </>
);
