# Building CloudCost Sentinel: Taming Cloud Spend Anomalies with Strands Decider 2B and Amazon Bedrock

**Tags:** `#strands-decider-2b` `#policy`
*Draft article for AWS Builder Center / Strands Developer Community (Unpublished)*

---

## The Autonomous Cloud Dilemma

Every cloud engineer knows the feeling of opening the AWS Billing console at the end of the month only to discover an unpredicted spend spike. Perhaps a test Kubernetes worker pool forgot its autoscaling down-threshold, an EMR batch process fell back from Spot to on-demand instances, or an unindexed database query caused provisioned IOPS to surge.

Engineering teams usually attempt to solve this in one of two ways:
1. **Static threshold alerts:** Alerts trigger constantly when spending crosses a flat line, creating notification fatigue. Eventually, engineers route them to a muted Slack channel.
2. **Generative LLM agents:** Builders hook a chatbot up to AWS Cost Explorer. However, general-purpose LLMs are non-deterministic token decoders. Asking a generative model "Should we terminate this cluster?" introduces hallucination risk, high latency, and unpredictable JSON parsing errors.

We built **CloudCost Sentinel** to solve this using an architectural split:
- **Strands Decider 2B** acts as the deterministic **System 1 Decision Engine**, evaluating multi-dimensional telemetry in milliseconds to choose between three typed policies: `monitor`, `notify_owner`, or `request_approval`.
- **Amazon Bedrock (Claude 3.7 Sonnet via Strands Agents SDK)** acts as the **System 2 Generative Investigator**, compiling grounded investigation reports, timelines, and remediation steps strictly from observed metrics.

---

## The Signature Decision: Decider 2B on the Main Path

Rather than treating Strands Decider 2B as a decorative tool, it sits squarely on the real execution path. The application's downstream behavior changes completely based on what Decider selects.

### The Signature Question

```python
from strands_decider.schema import ChoiceQuestion

question = ChoiceQuestion(
    type="choice",
    instructions=(
        "Given the spend anomaly, budget pressure, persistence, service criticality "
        "and known ownership, should the agent monitor, notify_owner, or request_approval for remediation?"
    ),
    criteria={
        "monitor": "Observe and re-evaluate without alerting. Appropriate for small fluctuations or non-critical environments.",
        "notify_owner": "Notify the verified resource owner directly. Appropriate for known service owners with moderate budget pressure.",
        "request_approval": "Escalate to human cloud platform engineer for remediation sign-off. Appropriate for high spend spikes, runaway budget burn, or critical environments.",
    },
)
```

### Why Decider 2B Excels Here
1. **Single Forward Pass:** Decider drops the generative text head in favor of a pointer head over the choice options.
2. **Statistically Calibrated Confidence:** The model emits calibrated probabilities and a normalized confidence score:
   $$\text{confidence} = \frac{N \times p_{\max} - 1}{N - 1}$$
3. **Safety Fallback:** If telemetry is noisy or data is sparse, Decider's confidence drops below the configured `0.65` threshold. CloudCost Sentinel catches this and conservatively routes to `request_approval` rather than guessing.

---

## Where Amazon Bedrock Fits

Once Decider selects the operational response, Amazon Bedrock performs the generative heavy lifting:
- It explains *why* the metrics changed, citing exact dollar deltas and persistence days.
- It provides a grounded audit of Decider's choice without altering it.
- It outlines safe, non-destructive investigation steps (e.g. checking CloudWatch CPU utilization or autoscaling cooldowns).
- It generates a follow-up checklist for FinOps hygiene.

Crucially, **Bedrock is constrained to observed telemetry facts**—it never invents AWS resource IDs, imaginary savings, or fictitious team owners.

---

## Live Walkthrough: The Runaway Compute Spike

1. **Telemetry Ingestion:** A production batch queue surges from a $320/day baseline to $1,340/day (+318.7% spike) across unreserved EC2 instances. The anomaly persists for 3 consecutive days, pushing projected monthly spend to 237% of the budget.
2. **Normalized State:** The engine normalizes the metrics into a compact prompt string including ownership, criticality, and persistence.
3. **Decider 2B Invocation:** Decider selects `request_approval` with 76% confidence ($P(\text{request\_approval}) = 0.84$).
4. **Execution Routing:** The system queues an approval review item for the cloud operations team with an estimated monthly savings of $22,875.
5. **Bedrock Report Generation:** Amazon Bedrock drafts the structured incident report, auditing Decider's decision and providing CloudWatch verification commands.
6. **Human Sign-Off:** The engineer reviews the evidence on the dashboard and signs off with a click.

---

## The Reusable Pattern: Threshold-Aware Anomaly Response

We packaged this architecture into an open, reusable Policy pattern located at:
`patterns/threshold_aware_anomaly_response/`

Any cloud platform engineer can adapt this pattern to container autoscaling, database read-replica management, or API rate limiting.

### Honest Limitations
- **Experimental Decider Model:** Strands Decider 2B is an experimental model under active development by Strands Labs; production deployments should enforce conservative confidence thresholds.
- **Human-in-the-Loop Safeguard:** CloudCost Sentinel deliberately avoids automated instance termination. All mutative operational changes require human verification.
