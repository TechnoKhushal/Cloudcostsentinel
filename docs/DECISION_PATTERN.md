# Decision Pattern: Threshold-Aware Anomaly Response

**Tags:** `#strands-decider-2b` `#policy`

---

## Pattern Overview

The **Threshold-Aware Anomaly Response** pattern is a canonical **Policy Decision Pattern** designed for high-stakes operational systems. Instead of using brittle `if/else` threshold matrices or unpredictable text-generating LLMs, this pattern uses a dedicated pointer-decision model—**Strands Decider 2B**—to evaluate multi-variable telemetry and select an operational action.

For full code, test suites, and standalone examples, see the dedicated pattern directory:
👉 [`patterns/threshold_aware_anomaly_response/`](../patterns/threshold_aware_anomaly_response/)

---

## 1. Typed Decider 2B Wire Specification

### Question (`ChoiceQuestion`)

```python
from strands_decider.schema import ChoiceQuestion

question = ChoiceQuestion(
    type="choice",
    instructions=(
        "Given the spend anomaly, budget pressure, persistence, service criticality "
        "and known ownership, should the agent monitor, notify_owner, or request_approval for remediation?"
    ),
    criteria={
        "monitor": (
            "Observe and re-evaluate without alerting. Appropriate for small fluctuations, "
            "low budget impact, or non-critical environments."
        ),
        "notify_owner": (
            "Notify the verified resource owner directly. Appropriate for known service owners "
            "with moderate budget pressure or early-stage anomalies."
        ),
        "request_approval": (
            "Escalate to human cloud platform engineer for remediation sign-off. Appropriate for high spend spikes, "
            "runaway budget burn, unassigned owners, or critical production environments."
        ),
    },
)
```

---

## 2. Decision State Serialization

The normalized state is formatted compactly so Decider evaluates critical signals without distraction:

```text
Service: Amazon EC2 | Environment: production (Criticality: CRITICAL)
Spend Delta: +$897.08/day (+202.5%) above baseline $442.92
Current Daily Spend: $1,340.00 | Persistence: 3 consecutive days
Budget Utilization: 237.8% consumed of $12,000.00 monthly budget | Forecast: $28,538.00
Owner: unassigned / unknown | Measurement Uncertainty: LOW
```

---

## 3. Calibrated Confidence & Fallback Guarantee

Strands Decider 2B returns calibrated confidence computed across all $N$ options:
$$\text{confidence} = \frac{N \times p_{\max} - 1}{N - 1}$$

- $0.0$: Uniform distribution (maximum doubt).
- $1.0$: Absolute certainty on a single option.

### Safe Fallback Mechanism
If $\text{confidence} < \text{DECIDER\_MIN\_CONFIDENCE}$ (0.65) or if an invocation failure occurs:
- The system flags `is_fallback = True`.
- The operational choice is conservatively forced to `request_approval`.
- A clear reason is logged and presented on the dashboard.

```python
if confidence < self.min_confidence:
    is_fallback = True
    action = "request_approval"
    fallback_reason = f"Confidence {confidence:.3f} below safety threshold {self.min_confidence:.3f}. Escalating to human."
```
