import { lazy, Suspense, useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { CostAnomaly } from "../types";

const SpendChart = lazy(() => import("./SpendChart").then(({ SpendChart }) => ({ default: SpendChart })));
type Range = "7" | "30" | "all";
type SortKey = "date" | "spend";
const EMPTY_POINTS: CostAnomaly["time_series"] = [];

function csvCell(value: string | number | boolean): string {
  const raw = String(value);
  const safe = /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function CostExplorerPage({ anomaly, query }: { anomaly: CostAnomaly | null; query: string }) {
  const [range, setRange] = useState<Range>("all");
  const [sortBy, setSortBy] = useState<SortKey>("date");
  const points = anomaly?.time_series ?? EMPTY_POINTS;
  const filtered = useMemo(() => {
    const latest = Math.max(0, ...points.map((point) => Date.parse(point.date) || 0));
    const minDate = range === "all" ? 0 : latest - (Number(range) - 1) * 86_400_000;
    return points.filter((point) =>
      (Date.parse(point.date) || 0) >= minDate
      && (!query || `${point.date} ${point.service} ${point.environment}`.toLowerCase().includes(query.toLowerCase())),
    );
  }, [points, query, range]);
  const visible = useMemo(() => [...filtered].sort((a, b) => sortBy === "date" ? a.date.localeCompare(b.date) : a.spend - b.spend), [filtered, sortBy]);
  const chartPoints = useMemo(() => [...filtered].sort((a, b) => a.date.localeCompare(b.date)), [filtered]);
  const total = visible.reduce((sum, point) => sum + point.spend, 0);
  const latestPoint = chartPoints.at(-1);
  const latestSpend = latestPoint?.spend;
  const exportRows = () => {
    if (visible.length === 0) return;
    const body = [["date", "service", "environment", "observed_spend", "baseline", "anomaly"], ...visible.map((point) => [
      point.date, point.service, point.environment, point.spend, point.baseline, point.is_anomaly,
    ])].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([body], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "cloudcost-sentinel-cost-series.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="page-content cost-page">
      <div className="page-heading-row">
        <div><p className="eyebrow">FINOPS TELEMETRY LEDGER</p><h1>Cost Explorer <em>&amp; variance</em></h1><p className="page-lede">Explore the actual time-series points returned by the current analysis.</p></div>
        <div className="page-actions"><span className="provenance observed">API DATA</span><button type="button" className="action-secondary compact-action" onClick={exportRows} disabled={!visible.length}><span aria-hidden="true">↓</span>Export visible rows</button></div>
      </div>
      {!anomaly ? <section className="empty-state"><span className="eyebrow">NO COST SERIES</span><h2>There is no analysis to explore yet.</h2><p>Run an analysis in Overview. This screen only displays time-series points returned by the API.</p><a className="action-primary" href="#overview">Go to Overview</a></section> : <>
        <div className="explorer-toolbar">
          <div className="scope-summary"><span className="scope-light">CURRENT ANALYSIS</span><strong>{anomaly.service}</strong><span>{anomaly.environment} · {anomaly.currency} · {anomaly.is_simulated ? "Synthetic telemetry" : "Non-simulated telemetry"}</span></div>
          <div className="range-control" role="group" aria-label="Filter time range">
            {([{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "all", label: "All points" }] as const).map((option) => <button key={option.value} type="button" aria-pressed={range === option.value} className={range === option.value ? "selected" : ""} onClick={() => setRange(option.value)}>{option.label}</button>)}
          </div>
          <label className="select-control"><span aria-hidden="true">≡</span><span>Sort</span><select value={sortBy} onChange={(event) => setSortBy(event.target.value as SortKey)}><option value="date">Date</option><option value="spend">Observed spend</option></select></label>
        </div>
        <div className="explorer-summary-grid">
          <article className="ledger-metric"><span>VISIBLE POINTS</span><strong>{visible.length}</strong><small>of {points.length} returned</small></article>
          <article className="ledger-metric"><span>SUM OF VISIBLE VALUES</span><strong>{anomaly.currency} {total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong><small>Sum of the selected daily observations</small></article>
          <article className="ledger-metric"><span>LAST VISIBLE OBSERVATION</span><strong>{latestSpend === undefined ? "—" : `${anomaly.currency} ${latestSpend.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</strong><small>{latestPoint?.date ?? "No matching date"}</small></article>
        </div>
        {chartPoints.length ? <Suspense fallback={<section className="chart-loading">Loading time-series chart…</section>}><SpendChart data={chartPoints} baseline={anomaly.metrics.baseline_spend} service={anomaly.service} /></Suspense> : <section className="empty-state compact-empty"><h2>No points match these filters.</h2><p>Clear the filter or select a wider date range.</p></section>}
        <section className="ledger-panel">
          <div className="ledger-panel-heading"><div><span className="eyebrow">OBSERVATION RECORDS</span><h2>Daily spend series</h2></div><label className="inline-search"><Search size={14} /><span>{query ? `Filtered by “${query}”` : "Use the global filter to search this series"}</span></label></div>
          <div className="table-scroll"><table className="ledger-table"><thead><tr><th>DATE</th><th>SERVICE</th><th>ENVIRONMENT</th><th>OBSERVED SPEND</th><th>BASELINE</th><th>DELTA</th><th>FLAG</th></tr></thead><tbody>
            {visible.map((point) => <tr key={`${point.date}-${point.service}`}><td className="mono-cell">{point.date}</td><td>{point.service}</td><td>{point.environment}</td><td className="money-cell">{anomaly.currency} {point.spend.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td><td className="money-cell muted-cell">{anomaly.currency} {point.baseline.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td><td className={point.spend > point.baseline ? "delta-negative" : "delta-positive"}>{point.baseline ? `${((point.spend - point.baseline) / point.baseline * 100).toFixed(1)}%` : "—"}</td><td><span className={`provenance ${point.is_anomaly ? "critical" : "observed"}`}>{point.is_anomaly ? "ANOMALY" : "OBSERVED"}</span></td></tr>)}
          </tbody></table></div>
          {!visible.length && <p className="table-empty">No cost points were returned for this range.</p>}
          <div className="ledger-table-foot">Showing {visible.length} of {points.length} API-provided observations · No service allocation is inferred.</div>
        </section>
      </>}
    </main>
  );
}
