# Section 98 — Designing Chaos Experiments & Steady-State Hypotheses

**Part 18: Resilience Testing & Chaos Engineering | [Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md) of 100**
**Prerequisites:** [Section 97](./Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md) (Azure Chaos Studio Fundamentals — targets, capabilities, experiments), [Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md) (HA/DR Patterns, RTO/RPO), [Section 37](../Part7/Section-37-Part7-AKS-Networking-Scaling-Security.md).4.4 (Pod Disruption Budgets)
**Leads into:** [Section 99](./Section-99-Part18-Continuous-DR-Validation-Game-Days.md) (Continuous DR Validation & Game Days)

---

## 1. Introduction and Scope

[Section 97](./Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md) established _what_ Azure Chaos Studio is and _how_ it mechanically injects faults. This section addresses the more important, more frequently mis-executed question: how to design a chaos experiment that actually produces useful, trustworthy information rather than either (a) causing an unintended, uncontrolled outage, or (b) running "successfully" without teaching anyone anything. This is the scientific-method core of chaos engineering as a discipline, independent of any specific tool — the same steady-state hypothesis, blast-radius control, and experiment-branch structure applies whether the tooling is Azure Chaos Studio, AWS Fault Injection Service, or a hand-rolled internal tool; this section covers the discipline in Azure Chaos Studio's specific terms.

🔑 **Key Takeaway:** A chaos experiment that isn't built around an explicit, falsifiable hypothesis isn't really an experiment — it's just "turning something off and seeing what happens," which produces anecdotes, not evidence. The discipline covered in this section is what separates rigorous chaos engineering practice from unstructured fault injection that happens to use the same tooling.

## 2. The Steady-State Hypothesis

### 2.1 Definition

**Plain language:** before breaking anything, you first write down, in specific and measurable terms, what "the system is working normally" actually looks like — then you break something, and check whether that same "working normally" state still holds. If it does, the hypothesis is confirmed (the system is resilient to that specific failure); if it doesn't, you've just found a real gap, safely, on your own terms.

**Precise definition:** a steady-state hypothesis is a specific, measurable, falsifiable statement about a system's expected behavior (typically expressed as a business or user-facing metric — request success rate, p99 latency, order-completion rate — rather than a low-level infrastructure metric alone) that is expected to remain true both _before_ and _during_ a chaos experiment's fault injection, if the system's resilience design genuinely works as claimed.

### 2.2 Why the Metric Choice Matters

⚠️ **Warning:** a steady-state hypothesis defined purely in infrastructure terms ("the VM is running") is a weak, often misleading choice — a VM can be "running" while the application it hosts is unresponsive, deadlocked, or serving errors. A well-designed hypothesis is defined as close to the actual user/business-facing outcome as practical — e.g., "checkout success rate remains above 99.5%" (directly reusing the revenue-critical checkout-service framing already established in [Section 49](../Part9/Section-49-Part9-CICD-Pipeline-Patterns-GitHub-Actions.md) and [Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md)'s own architect scenario) is a far stronger steady-state hypothesis than "the checkout VM's CPU is below 80%," because it's the metric that actually matters to the business, and it's much harder for a subtle failure mode to hide behind.

### 2.3 Example Hypothesis Statements

| Weak Hypothesis (Avoid)                | Strong Hypothesis (Prefer)                                                                                                                                                                                                                                                       |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "The VM stays up during the fault."    | "Checkout order-completion rate stays above 99.5% during the fault, measured via Application Insights ([Section 52](../Part10/Section-52-Part10-Application-Insights.md))."                                                                                                      |
| "The AKS pod gets rescheduled."        | "API p99 latency for `/checkout` stays under 800ms throughout the pod-kill experiment, and error rate stays under 0.1%."                                                                                                                                                         |
| "Failover to the DR region completes." | "The application is reachable and processing new orders within the defined RTO ([Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md).2.3) of the failover being initiated, verified end-to-end rather than merely confirming VM boot completion." |

## 3. Blast-Radius Control

### 3.1 Definition

**Plain language:** blast-radius control means deliberately limiting how much of the system a given experiment can affect — testing on one instance, one zone, or a small percentage of traffic, rather than the entire production estate at once — so that even if the hypothesis turns out to be wrong (a real gap exists), the consequence is contained and recoverable rather than a full-scale customer-facing outage.

**Precise definition:** blast-radius control is the deliberate scoping of a chaos experiment's target set, fault duration, and traffic percentage affected, calibrated to be just large enough to produce a meaningful, statistically credible result while minimizing the potential customer/business impact if the underlying hypothesis proves false.

### 3.2 Practical Blast-Radius Techniques on Azure

- **Target scoping:** an experiment's target list ([Section 97](./Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md).4.1) can reference a small, specific subset of a resource fleet (e.g., one VM out of twenty behind a Load Balancer, [Section 24](../Part5/Section-24-Part5-Load-Balancer-vs-Application-Gateway.md)) rather than the entire pool — validating the resilience mechanism (traffic correctly redirected away from the affected instance) without ever risking total capacity loss.
- **Duration limits:** every experiment step has a defined duration; keeping this as short as is sufficient to observe the relevant behavior (rather than an extended, open-ended fault window) limits the total exposure time if something behaves worse than expected.
- **Environment progression:** as introduced in [Section 97](./Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md).9, blast radius is also controlled temporally across a program's maturity — new experiment designs are proven first in non-production, then against a narrow production slice, before being scaled to the full claim being validated (e.g., an entire zone, as in [Section 97](./Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md).13's senior scenario).
- **Percentage-based targeting for AKS:** pod-kill and network-fault experiments can be scoped to affect only a percentage of matching pods (e.g., 20% of a Deployment's replicas) rather than the entire Deployment, directly testing whether Pod Disruption Budgets ([Section 37](../Part7/Section-37-Part7-AKS-Networking-Scaling-Security.md).4.4) and replica count genuinely absorb a partial loss.

### 3.3 The Trade-off

🎯 **Interview Tip:** a frequently-tested nuance is that blast-radius control is itself a trade-off, not a free safety net — an experiment scoped too narrowly may fail to actually exercise the failure mode being tested (e.g., killing one pod out of fifty tells you little about whether the system tolerates losing an entire zone's worth of capacity simultaneously, since Kubernetes' scheduler has trivial slack to absorb a single pod loss regardless of any deeper resilience gap). The skill is calibrating blast radius to be **just large enough to genuinely test the claim**, not simply "as small as possible" — an interview answer that treats blast-radius minimization as an unconditional goal, rather than a balance against experiment validity, is missing this nuance.

## 4. Experiment Structure: Steps, Branches, and Actions

### 4.1 The Structural Hierarchy

A Chaos Studio experiment is composed of **steps** (executed sequentially), each containing one or more **branches** (executed in parallel within a step), each branch containing one or more **actions** — either fault actions (the actual injected failure) or wait/delay actions (allowing time for an effect to manifest or for monitoring to capture data before the next step proceeds).

```json
{
  "steps": [
    {
      "name": "Step 1 - Baseline observation",
      "branches": [
        {
          "name": "wait-branch",
          "actions": [{ "type": "delay", "duration": "PT2M" }]
        }
      ]
    },
    {
      "name": "Step 2 - Inject fault",
      "branches": [
        {
          "name": "zone-a-pod-kill",
          "actions": [
            {
              "type": "continuous",
              "selectorId": "zone-a-pods",
              "duration": "PT5M",
              "parameters": [{ "key": "namespace", "value": "checkout" }]
            }
          ]
        }
      ]
    },
    {
      "name": "Step 3 - Recovery observation",
      "branches": [
        {
          "name": "wait-branch",
          "actions": [{ "type": "delay", "duration": "PT5M" }]
        }
      ]
    }
  ]
}
```

- The explicit **baseline observation** and **recovery observation** steps are a deliberate design choice, not boilerplate — they give the team a "before" and "after" window to compare against the "during" window, making it possible to distinguish "the metric dipped because of the injected fault" from "the metric was already degraded for an unrelated reason."

### 4.2 Rollback and Safety Mechanisms

⚠️ **Warning:** every well-designed experiment needs an explicit answer to "how do we stop this immediately if it goes worse than expected" — this is not automatic just because a fault has a defined duration. Chaos Studio experiments can be manually cancelled mid-run, and most fault types are designed to be self-reverting once their defined duration elapses (e.g., a network-latency fault stops adding latency once its duration ends, rather than requiring a separate explicit "undo" action) — but a team should confirm this expectation for each specific fault type being used, and have a documented, rehearsed manual-abort procedure (who has permission to cancel the experiment, and how) as a standing safety mechanism, rather than assuming the automated self-reversion alone is sufficient for every conceivable failure mode the experiment might trigger.

### 4.3 Pre-Flight Safety Checklist

- [ ] A specific, measurable steady-state hypothesis is defined ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).2), expressed in business/user-facing terms wherever practical.
- [ ] Blast radius (target scope, duration, traffic percentage) is calibrated to genuinely test the hypothesis without risking uncontained impact ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).3).
- [ ] A named person has explicit authority and access to manually abort the experiment mid-run.
- [ ] Monitoring dashboards (Azure Monitor, Application Insights — [Section 50](../Part10/Section-50-Part10-Azure-Monitor-Fundamentals.md), [Section 52](../Part10/Section-52-Part10-Application-Insights.md)) relevant to the steady-state metric are open and actively watched throughout the run, not reviewed only afterward.
- [ ] Stakeholders likely to be paged by any resulting alert are informed in advance that a scheduled experiment is underway, to avoid an unnecessary, confusing incident-response escalation for an intentional, controlled event.

## 5. How This Complements Part 12's HA/DR Design

🔑 **Key Takeaway, directly synthesizing Part 12 and Part 18:** [Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md) established the HA/DR design vocabulary (Availability Sets/Zones, RTO/RPO) and [Section 62](../Part12/Section-62-Part12-Azure-Site-Recovery-Backup.md) established the concrete implementation mechanisms (Azure Site Recovery, Azure Backup). Neither section's material, on its own, tells you whether a _specific_ deployed system actually achieves its claimed RTO/RPO or actually survives a zone loss — only a genuinely executed chaos experiment, with a clear steady-state hypothesis tied to the claimed RTO/RPO, does that. Concretely: if a workload's documented DR strategy claims a 15-minute RPO ([Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md).2.3), the corresponding chaos experiment's steady-state hypothesis should be framed to actually validate that number — e.g., "after inducing a simulated primary-region failure, data loss measured at the recovery point is under 15 minutes" — rather than a vaguer, unfalsifiable "failover works." This turns [Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md).7.2's warning about untested DR procedures from a general admonition into a specific, repeatable validation practice.

## 6. Comparison: Chaos Experiment Design vs. Traditional DR Drill

| Aspect           | Traditional Manual DR Drill                                                   | Chaos Studio Experiment                                                                                                                    |
| ---------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Frequency        | Typically infrequent (annual/semi-annual), given manual coordination overhead | Can be run frequently, even continuously ([Section 99](./Section-99-Part18-Continuous-DR-Validation-Game-Days.md)), since it's automatable |
| Blast radius     | Often all-or-nothing (a full failover drill)                                  | Granularly controllable (single instance, percentage of pods, single zone)                                                                 |
| Hypothesis rigor | Often informal ("let's see if failover works")                                | Structured around an explicit, falsifiable steady-state hypothesis                                                                         |
| Repeatability    | Manual runbook execution, prone to variance between runs                      | Defined as versioned, reusable experiment JSON — identical execution every time                                                            |
| Rollback         | Manual, often improvised under time pressure                                  | Built-in duration-bounded, self-reverting fault actions plus explicit abort capability                                                     |

## 7. Architecture Diagram

```
   Define Steady-State Hypothesis
   ("checkout success rate stays > 99.5%")
                │
                ▼
   Calibrate Blast Radius
   (1 zone's pods, 5-minute duration, non-peak window)
                │
                ▼
   ┌─────────────────────────────────────────┐
   │  Experiment: Steps → Branches → Actions   │
   │  Step 1: Baseline observation (2 min)      │
   │  Step 2: Inject fault (pod kill, 5 min)     │
   │  Step 3: Recovery observation (5 min)        │
   └─────────────────────────────────────────┘
                │
        ┌───────┴────────┐
        ▼                 ▼
  Hypothesis HOLDS    Hypothesis FAILS
  (resilience claim   (real gap found —
   confirmed)          e.g. missing PDB,
        │              missing topology
        │              spread constraint)
        ▼                 ▼
  Document & repeat   Fix the gap, then
  periodically         re-run to confirm
  (Section 99)          the fix (Section 99)
```

## 8. Configuration & Hands-On Example

**Creating and starting an experiment via `az rest` against the Chaos Studio experiments API:**

```bash
# Create the experiment (references the JSON structure from Section 98.4.1)
az rest --method put \
  --uri "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/rg-prod/providers/Microsoft.Chaos/experiments/exp-checkout-zone-a-podkill?api-version=2024-01-01" \
  --body @experiment-checkout-zone-a-podkill.json

# Start the experiment
az rest --method post \
  --uri "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/rg-prod/providers/Microsoft.Chaos/experiments/exp-checkout-zone-a-podkill/start?api-version=2024-01-01"

# Check experiment execution status
az rest --method get \
  --uri "https://management.azure.com/subscriptions/{sub-id}/resourceGroups/rg-prod/providers/Microsoft.Chaos/experiments/exp-checkout-zone-a-podkill/executions?api-version=2024-01-01"
```

- **Purpose:** creates a named, reusable experiment resource from a version-controlled JSON definition, then triggers an on-demand run and allows polling for its execution status — the same pattern is later invoked on a schedule for continuous validation ([Section 99](./Section-99-Part18-Continuous-DR-Validation-Game-Days.md)).
- **Important arguments explained individually:**
  - `--body @experiment-checkout-zone-a-podkill.json` — referencing an external, version-controlled file (rather than an inline JSON string) treats the experiment definition itself as a source-controlled artifact, consistent with the Infrastructure-as-Code discipline established in [Section 46](../Part9/Section-46-Part9-ARM-Templates.md)-[Section 48](../Part9/Section-48-Part9-Terraform-on-Azure.md); the experiment definition should be reviewed and versioned exactly like any other infrastructure configuration, not authored ad hoc in the Portal.
  - `/start` — a distinct action from experiment creation; creating an experiment resource only registers its definition, it does not execute it — a common point of confusion for those expecting `put` alone to trigger a run.
  - `/executions` — Chaos Studio retains a history of individual experiment runs (executions) separately from the experiment definition itself, allowing comparison of results across multiple runs of the same experiment over time (directly feeding [Section 99](./Section-99-Part18-Continuous-DR-Validation-Game-Days.md)'s continuous-validation practice).
- **Common error:** starting an experiment whose managed identity ([Section 97](./Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md).9) lacks the required role assignment on one of its target resources causes that specific branch/action to fail mid-run rather than the whole experiment being rejected up front — reinforcing why the pre-flight checklist ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).4.3) and monitoring during the run matter, since a partial, silent failure of one action within a larger experiment can otherwise go unnoticed.

## 9. Production & Enterprise Usage

Mature chaos engineering practices maintain a **library of versioned experiment definitions**, one per validated resilience claim, stored alongside application infrastructure code (the same repositories housing the Bicep/Terraform definitions from [Section 46](../Part9/Section-46-Part9-ARM-Templates.md)-[Section 48](../Part9/Section-48-Part9-Terraform-on-Azure.md)) — treating "what failure modes have we proven this system tolerates" as a living, auditable artifact rather than tribal knowledge. Enterprises typically start their chaos program on non-customer-facing or lower-criticality workloads (directly following [Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md).7.1's tiered-investment framing — a workload judged low-criticality enough to accept a relaxed RTO/RPO is also a reasonable, lower-stakes place to first practice chaos experiment design), building organizational confidence and refining safety practices before extending the practice to the revenue-critical workloads where the validation is most valuable.

## 10. Security Considerations

- Experiment definitions often encode precise knowledge of which specific failure modes a system has and hasn't been proven resilient against — this is genuinely sensitive operational information (an attacker who obtained a company's chaos experiment library would have a curated list of candidate weaknesses) and should be access-controlled at a level consistent with other sensitive architecture documentation, not left broadly readable.
- The managed identity's RBAC scope ([Section 97](./Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md).9) should be re-reviewed whenever an experiment's target list changes — a common configuration drift risk is an experiment definition being edited to target a new, additional resource without a corresponding role-assignment update, which will simply fail at runtime, but a broader risk is over-scoping the identity's permissions preemptively "to avoid this problem," which violates least-privilege for no real benefit.

## 11. Performance Considerations

The primary performance consideration in experiment design is timing: experiments should generally be scheduled during genuinely low-traffic windows for early runs of a new experiment design (to limit the customer-facing consequence of an unexpectedly severe result) before being run during representative, realistic traffic conditions once the experiment design and expected impact are well understood — a fault injected only ever during near-zero-traffic windows may never actually exercise the concurrency, contention, or load-related failure modes that matter most in a genuine production incident.

## 12. Monitoring

The steady-state hypothesis metric ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).2) must be genuinely observable in real time via Azure Monitor/Application Insights ([Section 50](../Part10/Section-50-Part10-Azure-Monitor-Fundamentals.md), [Section 52](../Part10/Section-52-Part10-Application-Insights.md)) for the experiment to produce a meaningful result — if the metric can only be computed after the fact from a batch report, the team cannot make a live abort decision ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).4.2) during the experiment window, undermining the safety model. Dashboards should be pre-built and validated _before_ the first experiment run referencing them, not built reactively during the run itself.

## 13. Troubleshooting

| Symptom                                                                           | Likely Cause                                                                                                                                                            | Fix                                                                                                                               |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Experiment "succeeds" (no errors reported) but the team learns nothing useful     | Steady-state hypothesis was too vague or infrastructure-focused rather than business/user-facing ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).2.2) | Redefine the hypothesis around a concrete, monitorable business/user-facing metric before re-running                              |
| Experiment causes a larger customer-facing impact than intended                   | Blast radius scoped too broadly relative to the team's confidence in the hypothesis ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).3.3)              | Reduce target scope/duration/traffic percentage for the next iteration; escalate blast radius only gradually as confidence builds |
| Experiment fails to reveal a known, previously-diagnosed gap (a "false negative") | Blast radius scoped too narrowly to actually exercise the failure mode (e.g., single-pod kill against a large, slack-heavy Deployment)                                  | Re-scope the experiment to match the actual claim being tested (e.g., an entire zone's worth of capacity, not a single pod)       |
| No one can decide whether to abort mid-run                                        | No named owner with abort authority was designated in the pre-flight checklist                                                                                          | Always assign and communicate a specific abort-authority owner before starting any production experiment                          |

## 14. Interview Questions — [Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md)

### 🎯 Intermediate

**Q: What is a steady-state hypothesis in chaos engineering, and why is a business-facing metric generally a better choice for one than a low-level infrastructure metric?**

_Model answer:_ a steady-state hypothesis is a specific, falsifiable statement about how a system is expected to behave, checked both before and during a chaos experiment's fault injection — if it still holds during the fault, the system's resilience design is validated for that failure mode; if it doesn't, a real gap has been found. A business-facing metric (like checkout success rate or API error rate) is generally the better choice over a low-level infrastructure metric (like "the VM is running") because infrastructure health doesn't necessarily imply application health — a VM can report as healthy while the application it hosts is deadlocked, timing out, or silently failing requests. A hypothesis tied to the actual user-facing outcome is much harder for a subtle, real failure mode to hide behind, and directly reflects what actually matters to the business rather than an infrastructure proxy for it.

_What the interviewer is probing:_ whether the candidate understands chaos engineering as a genuinely scientific, hypothesis-driven discipline rather than an unstructured "turn things off and see what happens" activity, and specifically whether they'd default to a meaningful, business-anchored metric rather than a superficial infrastructure-uptime check.

### 🎯 Senior/Architect

**Q: Your organization wants to validate that its documented 15-minute RPO ([Section 61](../Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md).2.3) for a critical database is actually achievable, using chaos engineering rather than a traditional manual DR drill. How would you design this experiment, and what would make you trust — or distrust — the result?**

_Model answer:_ I'd start by translating the RPO claim into a concrete, falsifiable steady-state hypothesis specific to data loss, not just "failover completes" — e.g., "after simulating a primary-region failure, the maximum data-loss window measured at the recovery point is under 15 minutes, verified by comparing timestamps of the last committed transaction on the primary against the most recent replicated state at the secondary." I'd calibrate blast radius carefully here: since this experiment fundamentally involves simulating a regional-scale event rather than a single-instance fault, I'd first validate the experiment design and expected behavior in a non-production environment closely mirroring production's replication topology, then run the production version during a low-traffic window with a specific, named person holding abort authority, and with the database's own replication-lag metrics and Azure Monitor dashboards actively watched throughout — not just checked after the fact. I would distrust a "passing" result if the experiment only validated that failover completed structurally (the secondary came online) without actually measuring the real data-loss window against the 15-minute claim — that would be the same "weak hypothesis" mistake from [Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).2.2, testing infrastructure behavior instead of the actual business commitment. I'd also want to repeat the experiment more than once, ideally under somewhat different load conditions, before fully trusting the result, since a single successful run under favorable, low-traffic conditions doesn't prove the RPO holds under the higher-replication-lag conditions more likely during genuine peak-load failure scenarios — and I'd want this validation to become a recurring, scheduled practice ([Section 99](./Section-99-Part18-Continuous-DR-Validation-Game-Days.md)) rather than a one-time proof, since infrastructure and code both change over time in ways that can silently invalidate a previously-confirmed RPO.

_What the interviewer is probing:_ the ability to translate an abstract DR metric (RPO) into a concrete, measurable chaos-experiment hypothesis, genuine understanding of blast-radius calibration for a regional-scale claim, healthy skepticism about what a single passing run actually proves, and forward connection to the need for repeated/scheduled validation rather than one-off testing — cumulative, cross-section reasoning rather than isolated recall.

## 15. Common Misconceptions

- **"A chaos experiment that completes without errors is a successful validation."** False — an experiment can complete cleanly while proving nothing, if its steady-state hypothesis was too vague, too infrastructure-focused, or its blast radius too narrow to genuinely exercise the claim being tested ([Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).2.2, [Section 98](./Section-98-Part18-Designing-Chaos-Experiments.md).3.3).
- **"Smaller blast radius is always safer and therefore always better."** False — blast radius is a genuine trade-off; too narrow a scope can produce a false-negative result that fails to exercise the actual failure mode being validated, giving unwarranted confidence.
- **"Running the DR failover once successfully proves the RPO/RTO commitment permanently."** False — infrastructure, code, and traffic patterns change continuously; a single passing experiment is a point-in-time result, not a permanent guarantee, which is precisely why [Section 99](./Section-99-Part18-Continuous-DR-Validation-Game-Days.md) treats this as a recurring practice rather than a one-time milestone.

## 16. Key Takeaways

- 🔑 A rigorous chaos experiment starts from an explicit, falsifiable steady-state hypothesis, ideally expressed in business/user-facing terms rather than raw infrastructure metrics.
- 🔑 Blast-radius control is a genuine trade-off — too broad risks uncontained impact, too narrow risks a false-negative result that never actually exercises the claim under test.
- 🔑 Experiments are structured as steps → branches → actions, with explicit baseline and recovery observation windows that make the "during-fault" effect measurable against a clear before/after comparison.
- 🔑 Every production experiment needs a documented, rehearsed manual-abort mechanism and a named owner with the authority to use it — self-reverting fault durations are a floor, not a substitute for this.
- 🔑 Chaos experiments are how Part 12's HA/DR design claims (Availability Zones, RTO/RPO, Site Recovery) become evidenced facts rather than assumptions — the experiment's hypothesis should map directly onto the specific claim (e.g., a specific RPO number) being validated.

## 17. Related Concepts (Next Up)

[Section 99](./Section-99-Part18-Continuous-DR-Validation-Game-Days.md) takes this experiment-design discipline and makes it a recurring, scheduled practice — integrating chaos experiments into CI/CD pipelines ([Section 9](../Part2/Section-09-Part2-Managed-Identities-and-Service-Principals.md)'s Part, specifically [Section 49](../Part9/Section-49-Part9-CICD-Pipeline-Patterns-GitHub-Actions.md)), organizing broader multi-team game-day exercises, and tying the whole practice back to Azure Site Recovery failover testing ([Section 62](../Part12/Section-62-Part12-Azure-Site-Recovery-Backup.md)) as a continuous validation program rather than a series of one-off experiments.
