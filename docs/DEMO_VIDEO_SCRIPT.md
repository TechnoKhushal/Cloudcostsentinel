# CloudCost Sentinel — 3-Minute Demo Video Script

**Target Duration:** 2 minutes 45 seconds
**Theme:** Crisp technical walkthrough, high contrast dark UI, honest demonstration.
**Tags:** `#strands-decider-2b` `#policy`

---

## [0:00 - 0:30] Introduction & The Problem

**Visual:**
Open on the CloudCost Sentinel Command Center dashboard. Show the dark theme with glowing telemetry cards, active anomaly graph, and the top status banner indicating `SIMULATED / DEMO MODE`.

**Spoken Audio:**
> "Hi everyone. Welcome to CloudCost Sentinel — an autonomous cloud spending decision agent built with Strands Decider 2B and Amazon Bedrock.
>
> Cloud cost anomalies present a critical dilemma: alert too often and engineers experience alert fatigue; alert too slowly and budgets blow out; automate remediation without guards and you risk shutting down production.
>
> CloudCost Sentinel solves this by decoupling the decision from the explanation: Strands Decider 2B chooses the operational response in milliseconds, and Amazon Bedrock drafts the grounded investigation report."

---

## [0:30 - 1:15] The Signature Decision: Compute Spike Walkthrough

**Visual:**
Click the **"Simulate Compute Spike"** button. The dashboard updates instantaneously:
- The Recharts curve surges from a $320 baseline to $1,340/day.
- Delta metric updates to `+318.7%` with 3 days persistence.
- The **Strands Decider 2B Panel** highlights `REQUEST_APPROVAL` in red with `76.0%` calibrated confidence.

**Spoken Audio:**
> "Let’s simulate a runaway EC2 compute spike in production.
>
> Notice what happens: our mathematical engine calculates the baseline, delta, and persistence. It packages this into a compact, normalized state and passes it to Strands Decider 2B.
>
> Decider evaluates the exact choice question: should the agent monitor, notify_owner, or request_approval?
>
> Because ownership is unassigned, criticality is production, and budget burn exceeds 200%, Decider 2B selects `request_approval` with 76% confidence.
>
> Notice that this decision is on the real execution path: it automatically creates a human review item in our approval queue with an estimated monthly savings of $22,875."

---

## [1:15 - 1:55] Inspecting the Decider 2B Wire Trace & Safety Fallback

**Visual:**
Click the collapsible **"Inspect Decider 2B Wire Trace"** accordion. Show the exact typed `ChoiceQuestion` JSON and the compact normalized state string. Next, switch the scenario selector to **"Sparse Telemetry & High Variance Drift"**. Show Decider's confidence drop below the `0.65` threshold, triggering the prominent red **Conservative Safety Fallback** badge.

**Spoken Audio:**
> "Let's inspect the wire trace. Here you can see the exact typed `ChoiceQuestion` specification, its criteria definitions, and the compact state string sent to Decider.
>
> Now watch what happens when telemetry is noisy. When we select the Sparse Telemetry scenario, data is ambiguous and Decider's calibrated confidence drops to 1%.
>
> Instead of guessing, CloudCost Sentinel enforces our safety policy: any decision below the 0.65 threshold safely escalates to human review, with an explicit fallback audit tag."

---

## [1:55 - 2:30] Amazon Bedrock Grounded Narrative Report

**Visual:**
Scroll down to the **Amazon Bedrock Grounded Cost Investigation** panel. Highlight the executive summary, observed facts, Decider choice audit, and CloudWatch investigation checklist.

**Spoken Audio:**
> "While Decider 2B handles the fast operational choice, Amazon Bedrock provides the generative depth.
>
> Using the Strands Agents SDK, Bedrock analyzes the telemetry and drafts a grounded investigation report. It explains exactly which metrics changed, audits Decider’s choice without secretly modifying it, and provides safe, non-destructive investigation steps.
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
