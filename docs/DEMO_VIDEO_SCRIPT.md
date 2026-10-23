# CloudCost Sentinel — 3-Minute Demo Video Script

**Target Duration:** 2 minutes 45 seconds
**Theme:** Crisp walkthrough of the explicitly simulated demo; do not claim live model/provider use.
**Tags:** `#strands-decider-2b` `#policy`

**Verification note:** The default providers are simulated. Use simulated wording unless a live Decider/Bedrock invocation is performed and evidenced during recording.

---

## [0:00 - 0:30] Introduction & The Problem

**Visual:**
Open on the CloudCost Sentinel Command Center dashboard. Show the dark theme with glowing telemetry cards, active anomaly graph, and the top status banner indicating `SIMULATED / DEMO MODE`.

**Spoken Audio:**
> "Hi everyone. Welcome to CloudCost Sentinel — a cloud cost decision-support demo. This run uses synthetic data and simulated decision/report providers; it does not call AWS or execute cloud changes.
>
> Cloud cost anomalies present a critical dilemma: alert too often and engineers experience alert fatigue; alert too slowly and budgets blow out; automate remediation without guards and you risk shutting down production.
>
> The design separates a policy decision from an investigation report. In this demo, both are produced by clearly labeled local simulated adapters."

---

## [0:30 - 1:15] The Signature Decision: Compute Spike Walkthrough

**Visual:**
Click the **"Simulate Compute Spike"** button. The dashboard updates instantaneously:
- The Recharts curve surges from a $320 baseline to $1,340/day.
- Delta metric updates to `+318.7%` with 3 days persistence.
- The **Simulated Policy Decision** panel highlights `REQUEST_APPROVAL` with the fixture's confidence.

**Spoken Audio:**
> "Let’s simulate a runaway EC2 compute spike in production.
>
> Notice what happens: our mathematical engine calculates the baseline, delta, and persistence. It packages a compact state for the simulated policy evaluator.
>
> The evaluator applies the same typed policy choices: monitor, notify_owner, or request_approval.
>
> The synthetic scenario selects `request_approval` with the confidence shown on screen.
>
> This creates a shared demo review record with synthetic savings. It does not trigger infrastructure changes."

---

## [1:15 - 1:55] Inspecting the Simulated Policy Trace & Safety Fallback

**Visual:**
Click the collapsible policy trace. Show the typed `ChoiceQuestion` JSON and compact synthetic state. Switch to **"Sparse Telemetry & High Variance Drift"** and show the configured conservative fallback.

**Spoken Audio:**
> "Let's inspect the trace. Here you can see the typed `ChoiceQuestion` and compact state used by this simulated run.
>
> Now watch what happens when telemetry is noisy. The synthetic scenario triggers the fallback threshold.
>
> Instead of guessing, CloudCost Sentinel enforces our safety policy: any decision below the 0.65 threshold safely escalates to human review, with an explicit fallback audit tag."

---

## [1:55 - 2:30] Simulated Investigation Report

**Visual:**
Scroll down to the simulated investigation panel. Highlight the executive summary, observed facts, policy audit, and investigation checklist.

**Spoken Audio:**
> "The report panel is simulated in this run; it uses a grounded template rather than an Amazon Bedrock call.
>
> It summarizes the synthetic metrics, audits the policy choice, and provides safe investigation steps.
>
> Crucially, Bedrock is strictly grounded: it never invents fictitious resource IDs or untracked pricing."

---

## [2:30 - 2:45] Human Sign-off & The Reusable Policy Pattern

**Visual:**
Click **"Approve"** on the pending approval card. Show the badge transition to green `APPROVED`. Quickly show the `patterns/threshold_aware_anomaly_response/` directory in the code editor.

**Spoken Audio:**
> "Finally, the cloud engineer reviews the recommendation and approves it in the safety sandbox.
>
> We’ve packaged this entire architecture into an open, reusable Policy pattern that any developer can clone and adapt. Check out the repository on GitHub.
>
> Thank you!"
