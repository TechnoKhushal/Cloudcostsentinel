# Stitch export inventory and implementation checklist

Source of visual reference: `C:\Users\HP\Downloads\stitch_cloudcost_sentinel_ui_platform.zip` (1.77 MB), inspected without modifying the archive; extracted under ignored `.tmp/stitch-inspect-20261027/`.

## Export format and assets

- ZIP root: `stitch_cloudcost_sentinel_ui_platform/`
- Four directories contain a `code.html` and full-page `screen.png`: marketing/landing, overview dashboard, findings/anomalies, and cost explorer.
- `editorial_finops_observability/DESIGN.md` supplies the complete color, typography, spacing, shape, semantic color, table, and responsive design guidance.
- HTML screens are standalone generated mockups using inline HTML/CSS, Tailwind CDN, Google Fonts (Geist and JetBrains Mono), and Material Symbols. There is no Vite/React code, package manifest, reusable component source, local image/font asset, design token JSON, or additional JS interaction implementation. The only local imagery is four reference screenshots. The landing screen also references a remote stock portrait.
- Navigation links use `#`; inspected buttons have no application handlers. Displayed account IDs, costs, finding counts, ledger events, efficiency/savings, cryptographic hashes, and Terraform snippets are example content and are not connected to this repository's API.

## Screen and component mapping

| Export screen | Intended structure | Existing data/API support | Implementation status |
|---|---|---|---|
| Intelligent FinOps platform (landing) | Editorial hero, preview, principles, workflow, security, comparison, CTA | Public demo/health and API status only; no trial/deployment/signup service | Implemented with live status and workspace links; false trial/deployment and customer-quote claims omitted. |
| Overview dashboard | Scope/status strip, spend/forecast/budget summary, spend chart, recommendations, risk, service ledger, decisions | Current analysis metrics, time series, decision, report, approval queue, and provider health | Implemented with current API values only; no invented service breakdown, risk count, savings aggregate, ledger hash, or executed infrastructure claims. |
| Findings & anomalies | Status totals, filters, finding list, selected finding, spend profile, diagnostic report, approval actions | Current analysis + decision/report; approval queue. No findings list/status mutation, audit log, or Terraform operations endpoint | Implemented as current-analysis detail plus real approval queue. Missing history is explicit; unsafe/unbacked remediation actions are omitted. |
| Cost Explorer & variance topology | Date horizon, granularity/grouping/filters, trend, allocation table and exports | Production supports verified customer-owned AWS roles scoped to each personal workspace and returns a bounded daily cost series. The current request is ungrouped; multi-service allocation and arbitrary date-range queries are not available. | Implemented time-range/search/sort and CSV over returned points; service-level allocation is explicitly unavailable. AWS access requires a verified role, saved workspace budget and currency, and platform credentials. |

## Shared design components

- Header: product wordmark, navigation, account/integration status, search and notification indicators. Search and integration controls will only be shown when connected to working behavior.
- Editorial typography: Geist for interface copy, JetBrains Mono for measured values/IDs, uppercase compact monospace labels.
- Warm chalk canvas, white ledgers, deep ink, signal-lime accents, mineral green/amber/terracotta semantics, fine borders, 4–8px corners, no decorative shadow/glass.
- Metric panels, range selector, chart legend/tooltips, filter controls, findings rows, diagnostic steps, recommendation/actions, decision ledger, provenance tags, footers.
- 390–412px narrow layouts collapse to one column; tables become readable, horizontally scrollable or summary rows. Keyboard and reduced-motion support are required.

## Safe implementation guardrails

The reference's “Deploy Engine”, “Review & Stage PR”, “Draft Terraform PR”, “Assign Tags via Terraform”, “Suppression”, fabricated savings, trial signup, sample identity, and cryptographic audit-proof interactions are not backed by the current API. The implementation must not claim these occurred. Human approvals continue to change only the internal approval record. All financial values shown must come from existing API responses or be absent with an explanatory empty state.
