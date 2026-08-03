# Part 3 · Section 5 — Auto Scaling Groups

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** An Auto Scaling Group keeps a specified number of EC2 instances running, automatically launching new ones if some fail or demand rises, and terminating extras when demand falls — using a Launch Template as the blueprint.

**Precise:** **Amazon EC2 Auto Scaling** manages a collection of EC2 instances (an ASG) as a single unit, automatically launching, terminating, and replacing instances per defined capacity settings and scaling policies, using a Launch Template for instance configuration.

---

## 2. Why It Exists

- The literal mechanism delivering elasticity (§1) for EC2 — without ASGs, "elastic" compute requires a human watching dashboards.
- Solves two problems: **availability** (replacing failed instances automatically) and **cost-efficient scaling** (matching real demand instead of provisioning for a guessed peak — §6).
- **Self-healing:** continuously monitors actual vs desired instance count, auto-launches replacements for failed/terminated instances.

---

## 3. Core Configuration — Three Capacity Numbers

- **Minimum size** — never fewer than this.
- **Maximum size** — never more than this (cost/blast-radius ceiling).
- **Desired capacity** — the number actively maintained right now, between min and max.

> 🔑 Scaling actions **change desired capacity**; the ASG's own reconciliation loop then launches/terminates to match it. A scaling policy doesn't launch instances directly — this distinction is genuinely important.

---

## 4. How ASGs Determine Placement

- Configured with one or more subnets (typically one per AZ) — automatically **distributes instances across specified AZs**, implementing "spread across ≥2 AZs" (§2) automatically.
- Balancing logic keeps instance count roughly even across AZs, factoring AZ balance into scale-in decisions too.

---

## 5. Scaling Policies

### 5.1 Manual Scaling

Direct desired-capacity edit — for known, planned changes; not responsive on its own.

### 5.2 Scheduled Scaling

Actions at specific times (scale up weekday mornings, down at night) — for predictable, recurring demand.

### 5.3 Dynamic — Target Tracking (modern default)

Specify a target metric value (often average CPU); ASG auto-calculates adjustments to converge, like a thermostat. Least manual tuning — the recommended default.

### 5.4 Dynamic — Step Scaling

Specific adjustments tied to CloudWatch Alarm thresholds (CPU>70%→+2, CPU>90%→+4) — more granular control, more manual tuning. Choose for non-linear scaling needs.

### 5.5 Predictive Scaling

ML analyzes historical patterns, proactively scales ahead of anticipated demand rather than reacting after a threshold crosses — best for recurring-but-imperfectly-regular patterns.

> 🎯 Scheduled = calendar-predictable; target tracking = general reactive default; step scaling = non-linear threshold control; predictive = ahead of a recurring pattern reactive scaling would lag behind.

---

## 6. Health Checks

- **EC2 status checks (default)** — hardware/hypervisor-level, not application-aware.
- **ELB health checks (recommended, full depth Section 6)** — application-aware (HTTP request expecting 200) — catches process crashes EC2 checks miss.
- **Health check grace period** — configurable delay after launch before checks count, avoiding premature termination during boot/warm-up.

> 🔑 Relying only on EC2 status checks is a common real gap — ELB health checks actually verify the application works.

---

## 7. Instance Termination Policies

Default order when scaling in:

1. **AZ balance** — prefer terminating from the AZ with the most instances.
2. **Oldest Launch Template version** — naturally cycles the fleet toward the current version (connects to golden-image rollout, Section 4 §6.2).
3. **Closest to next billing hour** — legacy consideration, less impactful with per-second billing.
4. **Random** among remaining ties.

Custom termination policies can override this (e.g., prioritize Spot termination first).

---

## 8. Mixed Instances Policies

- A single ASG can launch across **multiple instance types** and **multiple purchase options** (On-Demand + Spot) — the actual mechanism behind Section 3 §5.4's Spot diversification advice.
- **Instance type flexibility** — list of acceptable types, ASG draws from whichever has capacity.
- **On-Demand/Spot split** — base On-Demand floor (guaranteed) + percentage split (e.g., 70% Spot/30% On-Demand) for capacity above the base — implements Section 3's mixing pattern as a configurable feature.

---

## 9. Lifecycle Hooks

- Pause an instance in `Pending` or `Terminating` state for custom actions — e.g., final registration before in-service, or draining connections/extracting logs before termination.
- Without a hook, a terminating instance might be killed mid-request or before logs ship — the hook creates a deliberate pause to avoid this.

---

## 10. Production & Enterprise Usage

- **Target tracking is the standard default**; step scaling reserved for demonstrated non-linear needs.
- **Mixed instances with base On-Demand floor** — standard cost-optimized production pattern for fault-tolerant workloads.
- **ASGs underlie ECS/EKS-on-EC2** (Section 8) — container platforms on EC2 still rely on an ASG for underlying compute scaling.
- **Warm pools** — pre-initialized stopped/running instances ready for quick service, reducing launch-to-ready latency when boot time itself is the bottleneck.

---

## 11. Security Considerations

- Every launched instance inherits the Launch Template's IAM profile, security groups, IMDSv2 settings — a Launch Template misconfiguration is automatically replicated across every future instance, a high-leverage control point.
- Lifecycle-hook log extraction before termination should ship to a durable, access-controlled destination (S3, encrypted, §14/Part 5) rather than losing logs on destruction.

---

## 12. Performance Considerations

- Scaling reaction isn't instantaneous — boot + bootstrapping + grace period lag; set thresholds with headroom, not tuned to the exact edge of current capacity.
- Predictive scaling directly addresses this lag for sufficiently regular-pattern workloads.

---

## 13. Troubleshooting

| Symptom                                                          | Cause                                                              | Fix                                                                  |
| ---------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------- |
| ASG keeps terminating/relaunching a new instance                 | Grace period too short, or ELB health check genuinely failing      | Increase grace period; investigate why health check fails            |
| ASG not scaling out despite high load                            | At max size, or tracked metric doesn't reflect the real bottleneck | Check max-size constraint; verify metric correlates with real demand |
| Instances terminate mid-request                                  | No lifecycle hook/ELB connection draining configured               | Add termination lifecycle hook and/or ELB deregistration delay       |
| New instances use outdated config despite Launch Template update | ASG still pointed at an older version, not "$Latest"               | Update ASG to reference new version or use "$Latest"                 |

---

## 14. Best Practices & Anti-Patterns

**Best practices:** default to target tracking; use ELB health checks for real applications; use mixed instances with a base On-Demand floor for cost-optimized fault-tolerant workloads; configure lifecycle hooks for graceful termination; spread across multiple AZs always.

**Anti-patterns:** relying only on EC2 status checks; scaling thresholds with no launch-lag headroom; manually editing individual ASG-launched instances instead of updating the Launch Template; single-AZ ASGs for production.

---

## 15. Common Misconceptions

- "A scaling policy directly launches/terminates instances." → Not quite — it adjusts desired capacity; the ASG's reconciliation loop does the actual work.
- "EC2 status checks are sufficient for application health." → False — infrastructure-level only; ELB checks verify application health.
- "ASG instances are individually managed like standalone EC2." → False in practice — disposable, identical, replaceable units defined by the Launch Template; manual per-instance changes get overwritten/lost.
- "Mixed instances policies mean giving up cost/availability control." → False — base floor + percentage split gives precise deliberate control.

---

## 16. Interview Questions (with model answers)

**🟢 Relationship between min size, max size, desired capacity?** Min/max are the floor/ceiling; desired capacity is what the ASG actively maintains, always between them. Scaling policies adjust desired capacity; the ASG's reconciliation loop launches/terminates to match it — the policy doesn't launch instances directly.

**🟢 Why use ELB health checks instead of just EC2 status checks?** EC2 status checks only verify infrastructure health — wouldn't catch a running instance whose app process crashed. ELB health checks are application-aware (HTTP request expecting success), catching app-level failures EC2 checks miss entirely.

**🟡 When would you choose step scaling over target tracking?** Target tracking is the general-purpose default, automatic scaling math. Step scaling fits non-linear needs — e.g., add 1 instance at CPU>70%, 4 instances at CPU>90% — where the response rate itself should change at different severity levels, not expressible in one target-tracking curve.

**🟡 How does a mixed instances policy with base On-Demand work?** Define a guaranteed base number of On-Demand instances always running (reliability floor); capacity above that splits by percentage between On-Demand and Spot (e.g., 30/70). Base guarantees minimum reliability even if Spot is unavailable; percentage split captures Spot savings for elastic demand above the floor.

**🔴 ASG scales out during spikes but users see errors for the first minute or two — diagnose and fix?** Scaling reaction lag — launching isn't instantaneous (boot + bootstrap + grace period). Check threshold headroom (may already be overwhelmed before scale-out triggers). Check if boot time itself is the bottleneck — golden image with more pre-baked config, or a warm pool, reduces lag. If demand pattern is at all regular, predictive scaling gets ahead of the spike rather than reacting.

**🔴 Design Auto Scaling for e-commerce with daily pattern, flash-sale spikes, zero dropped requests on scale-in?** Predictive scaling as base layer for the recurring daily pattern; target tracking as reactive safety net for anything unanticipated including flash sales; scheduled scaling for calendar-announced sale start times as an extra proactive boost. Mixed instances policy with On-Demand base sized to daily-minimum traffic + Spot for elastic capacity (stateless fault-tolerant web tier). Zero dropped requests: termination lifecycle hook + ELB connection draining before removal; ELB health checks (not just EC2 status) throughout.

---

## 🔑 Key Takeaways

1. ASGs are the mechanical realization of elasticity — self-healing plus cost-efficient scaling, built on the Launch Template.
2. Scaling policies adjust desired capacity; the ASG's reconciliation loop does the actual launching/terminating.
3. Four scaling approaches: scheduled (calendar-predictable), target tracking (general default), step scaling (non-linear control), predictive (ML, ahead of recurring patterns).
4. ELB health checks catch application-level failures EC2 status checks miss entirely — essential for real applications.
5. Mixed instances policies operationalize Section 3's purchasing framework — base On-Demand floor + Spot percentage for deliberate availability/cost control.

## 🌐 Related Concepts (forward links)

- Elastic Load Balancing — health checks, connection draining, traffic distribution → §24
- CloudWatch metrics/alarms underlying dynamic scaling → Part 8
- ECS/EKS scaling built on ASG concepts → §26
