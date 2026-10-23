# Hackathon Submission Checklist — CloudCost Sentinel

**Required Tags:** `#strands-decider-2b` `#policy`

| Requirement | Status | Evidence / Location |
| :--- | :---: | :--- |
| **Target Public Repository** | ✅ Verified | [GitHub Repository](https://github.com/TechnoKhushal/Cloudcostsentinel) |
| **OSI-Approved License** | ✅ Verified | [MIT License](LICENSE) (Copyright 2026 TechnoKhushal) |
| **Genuinely Working Agent** | ⏳ Runtime verification pending | FastAPI backend (`backend/`), React Vite UI (`frontend/`), SQLite repository are present; current live deployment could not be reached |
| **Strands Decider 2B in Main Path** | ⏳ Live inference unverified | Default provider is a simulated policy evaluator; optional HTTP integration is in source |
| **Strands Agents Intervention Integration** | ⏳ Runtime verification pending | `ThresholdAwareAnomalyIntervention` (`backend/interventions/anomaly_policy.py`) |
| **Amazon Bedrock Generative Narrative** | ⏳ Live invocation unverified | Default narrative provider is simulated; optional Bedrock integration is in source |
| **Low-Confidence Safety Fallback** | ⏳ Test rerun pending | Conservative fallback is implemented in source |
| **Zero Mutation AWS Safety** | ⏳ Runtime verification pending | Source provides read-only guidance and internal approval records |
| **Deterministic Synthetic Scenarios** | ⏳ Test rerun pending | Scenario fixtures are present in source |
| **Reusable Decision Pattern** | ⏳ Test rerun pending | [`patterns/threshold_aware_anomaly_response/`](patterns/threshold_aware_anomaly_response/) |
| **Performance Benchmark Experiment** | ⏳ Reproduction pending | Script exists; no current benchmark run is claimed |
| **Builder Center Article Draft** | ⏳ Draft only | [`docs/BUILDER_CENTER_ARTICLE.md`](docs/BUILDER_CENTER_ARTICLE.md) |
| **Demo Video Script** | ⏳ Recording pending | [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md) uses simulated-only narration |
| **Architecture Documentation** | ⏳ Source review pending | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Automated Test Suite** | ⏳ Current run blocked | pytest was unavailable in this execution environment; run backend and pattern suites in CI |
| **Public Video Link** | ⏳ Pending Recording | *Recorded following [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md)* |
