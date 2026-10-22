# Hackathon Submission Checklist — CloudCost Sentinel

**Required Tags:** `#strands-decider-2b` `#policy`

| Requirement | Status | Evidence / Location |
| :--- | :---: | :--- |
| **Target Public Repository** | ✅ Verified | [GitHub Repository](https://github.com/TechnoKhushal/Cloudcostsentinel) |
| **OSI-Approved License** | ✅ Verified | [MIT License](LICENSE) (Copyright 2026 TechnoKhushal) |
| **Genuinely Working Agent** | ✅ Verified | FastAPI backend (`backend/`), React Vite UI (`frontend/`), SQLite persistence |
| **Strands Decider 2B in Main Path** | ✅ Verified | Evaluates `monitor` / `notify_owner` / `request_approval` via typed `ChoiceQuestion` (`backend/services/decider_client.py`) |
| **Strands Agents Intervention Integration** | ✅ Verified | `ThresholdAwareAnomalyIntervention` (`backend/interventions/anomaly_policy.py`) |
| **Amazon Bedrock Generative Narrative** | ✅ Verified | Bedrock Claude 3.7 Sonnet narrative layer via Strands Agents SDK (`backend/services/strands_agent.py`) |
| **Low-Confidence Safety Fallback** | ✅ Verified | Fallback to `request_approval` when confidence < 0.65 or on provider error |
| **Zero Mutation AWS Safety** | ✅ Verified | Read-only telemetry, no cloud destruction permissions, safe approval sandbox |
| **Deterministic Synthetic Scenarios** | ✅ Verified | 5 reproducible scenarios with explicit seeds & reset controls |
| **Reusable Decision Pattern** | ✅ Verified | [`patterns/threshold_aware_anomaly_response/`](patterns/threshold_aware_anomaly_response/) |
| **Performance Benchmark Experiment** | ✅ Verified | Reproducible benchmark script [`scripts/benchmark_decider.py`](scripts/benchmark_decider.py) |
| **Builder Center Article Draft** | ✅ Verified | [`docs/BUILDER_CENTER_ARTICLE.md`](docs/BUILDER_CENTER_ARTICLE.md) |
| **3-Minute Demo Video Script** | ✅ Verified | [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md) |
| **Architecture Documentation** | ✅ Verified | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Automated Test Suite (15/15 Pass)** | ✅ Verified | Pytest backend & pattern test suites (`tests/test_backend.py`) |
| **Public Video Link** | ⏳ Pending Recording | *Recorded following [`docs/DEMO_VIDEO_SCRIPT.md`](docs/DEMO_VIDEO_SCRIPT.md)* |
