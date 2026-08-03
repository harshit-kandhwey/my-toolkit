# Part 2 · Section 8 — Threat Detection & Compliance: GuardDuty, Security Hub, Config, Inspector

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** Preventive controls are locks on doors; detective controls are the cameras and alarms that notice if someone got in anyway, or a door was left unlocked. This section covers AWS's cameras and alarms.

**Precise:** AWS's **detective and compliance services** — **GuardDuty** (threat detection), **Security Hub** (findings aggregation), **AWS Config** (configuration compliance/drift), **Inspector** (vulnerability scanning) — continuously monitor accounts/resources, generating actionable findings.

---

## 2. Why This Category Exists

- Preventive controls (Sections 1–7) can fail or be incomplete — misconfiguration happens, credentials get compromised despite good design.
- Core principle: you can't prevent 100% of problems, so you must **detect** what gets through, near-real-time, and **respond** before damage compounds — the "detect and respond" half of a complete program.
- At scale, manual review doesn't work — hundreds of accounts (Section 5) generating constant activity require automated, centrally-aggregated monitoring.

---

## 3. Amazon GuardDuty — Threat Detection

### 3.1 Definition

Managed threat detection service continuously analyzing account activity, network traffic, DNS logs using ML/anomaly detection/threat intelligence — no scanning infrastructure to deploy.

### 3.2 What It Analyzes

- **CloudTrail logs** — API activity (unusual location, disabling security tools, unusual AssumeRole patterns).
- **VPC Flow Logs** — network traffic metadata (known-malicious IPs, port scanning, exfiltration patterns).
- **DNS logs** — queries to command-and-control domains.
- **S3 data event logs (optional)** — unusual access patterns suggesting exfiltration.
- **EKS audit logs (optional)** — Kubernetes-specific threat detection.

> 🔑 GuardDuty is passive — no agents, consumes logs AWS already produces, applies threat intelligence/anomaly detection on top. Enabling it is a toggle, not an infrastructure project.

### 3.3 Findings

- Severity score (Low/Medium/High) + structured finding type (`UnauthorizedAccess:EC2/SSHBruteForce`) indicating category/resource/behavior.
- Can trigger automated response via EventBridge (e.g., auto-isolating a compromised EC2's security group).

### 3.4 Production/Enterprise Usage

- **Organization-wide via delegated administrator** — enable once, covers every member account automatically (Section 5 §8 pattern).
- **Protection plans:** S3, EKS, RDS, Lambda, Malware Protection — expanded beyond original EC2/network focus.

---

## 4. AWS Security Hub — Centralized Aggregation

### 4.1 Definition

Aggregates, normalizes, prioritizes findings from GuardDuty, Inspector, Config, IAM Access Analyzer, Macie, third-party tools into a single dashboard/standardized format (ASFF), plus runs its own automated compliance checks.

### 4.2 Why It Exists

Without it, findings scatter across many consoles/formats — hard to get a single "how secure are we" answer. Security Hub ingests into ASFF so wildly different tools can be viewed/filtered/prioritized together.

### 4.3 Security Standards

- **AWS Foundational Security Best Practices (FSBP)** — AWS's own baseline.
- **CIS AWS Foundations Benchmark** — industry-standard (Center for Internet Security).
- **PCI DSS** — for payment card data handlers.
- Others by region/availability.

> 🎯 Checks against both an AWS-specific baseline AND industry-standard external benchmarks — genuinely mapped to what auditors recognize.

### 4.4 Production/Enterprise Usage

- Delegated administrator model — single pane of glass across an Organization.
- Automated remediation via EventBridge → Lambda for well-understood findings.

---

## 5. AWS Config — Configuration Compliance & Drift Detection

### 5.1 Definition

Continuously records the configuration state of resources, evaluates against rules, flags noncompliant resources — operationalizes "configuration drift" (§5).

### 5.2 Core Capabilities

- **Configuration history/timeline** — records every change; useful for incident investigation ("what changed right before this broke").
- **Config Rules** — evaluate resources against a condition, mark Compliant/Noncompliant (e.g., "every S3 bucket must have encryption enabled").
- **Conformance Packs** — bundled Config Rules + remediation, deployable as one unit, often implementing a specific regulation.
- **Automatic remediation** — Noncompliant finding triggers an SSM Automation document to fix the issue (e.g., auto-enabling encryption).

### 5.3 Config vs GuardDuty vs Security Hub

| Service      | Watches                                  | Core question                                         |
| ------------ | ---------------------------------------- | ----------------------------------------------------- |
| Config       | Resource configuration state over time   | "Is this configured correctly, now and historically?" |
| GuardDuty    | Behavioral/activity signals              | "Is something actively malicious happening?"          |
| Security Hub | Aggregation of findings from all sources | "What's my overall security posture, in one place?"   |

> 🔑 Config = state, GuardDuty = behavior, Security Hub = aggregation. Complementary, not overlapping.

---

## 6. Amazon Inspector — Vulnerability Scanning

### 6.1 Definition

Automated vulnerability management scanning EC2 instances, ECR container images, and Lambda functions for known software vulnerabilities (CVEs) and network reachability issues — no manual scan scheduling.

### 6.2 What It Finds

- **Known CVEs** — scans installed packages against vulnerability databases.
- **Network reachability** — identifies unintended internet-exposure paths (Part 4 networking, from a detection angle).
- **Continuous** — re-evaluates automatically on new CVE publication or resource change, no manual re-scan needed.

### 6.3 Distinction from Config/GuardDuty

Config = "is this configured correctly." GuardDuty = "is something bad happening." Inspector = "does this contain a known exploitable weakness" — the software supply-chain/vulnerability question.

---

## 7. IAM Access Analyzer (revisited)

- Identifies resources shared with entities **outside** your account/Organization (S3 bucket, IAM role, KMS key) that may be unintended, and generates least-privilege policies from observed CloudTrail access patterns.
- Integrates with Security Hub; distinct focus on **access-boundary correctness** vs threats/drift/vulnerabilities.

---

## 8. How These Services Work Together

```
                    AWS Security Hub
        (aggregation + compliance: FSBP, CIS, PCI DSS)
                          │
    ┌──────────┬──────────┼──────────┬──────────────┬────────────┐
GuardDuty   Inspector   Config   Access Analyzer   3rd-party
(behavior)  (vuln scan) (config  (access           tools
                         state)   boundaries)
                          │
              Findings can trigger
                          │
              EventBridge → Lambda/SSM
              Automated remediation
```

> 🔑 Four specialized tools answering distinct questions, feeding one aggregated view (Security Hub), with findings triggering automated remediation — detection as a closed loop, not "someone eventually notices."

---

## 9. Production & Enterprise Usage

- **Delegated administration is standard** for all four services — a dedicated Security account manages/views findings org-wide.
- **Compliance evidence generation:** Security Hub's standards checks + Config's historical record together generate actual auditor evidence (operationalizing §3's "compliance inheritance has limits").
- **SOAR-style automation:** EventBridge-triggered playbooks — auto-quarantine compromised instances, revoke compromised sessions, open tickets — reducing MTTR from hours to seconds for well-understood findings.

---

## 10. Security Considerations

- **Protect the detective services themselves** — SCP denying disabling of GuardDuty/Config/Security Hub is standard, since a sophisticated attacker's first move is often disabling detection.
- **Finding fatigue is real** — enabling every check without prioritization/triage produces overwhelming volume that gets ignored; Security Hub prioritization + automated remediation combat this.
- **Detective controls aren't a substitute for preventive controls** — they tell you after the fact; preventive controls remain the first line of defense.

---

## 11. Troubleshooting

| Symptom                                                 | Cause                                                                                     | Fix                                                              |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| GuardDuty shows no findings despite suspicious activity | Optional protection plans not enabled, or log source unavailable                          | Verify enabled protection plans/data sources                     |
| Security Hub missing findings from a service            | That service's Security Hub integration not enabled                                       | Turn on the specific integration                                 |
| Config marks a resource noncompliant but it looks fine  | Rule logic mismatches actual intent                                                       | Review/refine the Config Rule                                    |
| Inspector misses a known vulnerability                  | Resource type out of scope (e.g., missing SSM Agent), or very new CVE not yet in database | Verify agent connectivity/eligibility; allow time for DB updates |

---

## 12. Best Practices & Anti-Patterns

**Best practices:** enable all four Organization-wide via delegated administration from day one; use SCPs to prevent disabling detective controls; wire high-confidence findings to automated remediation; use Security Hub as the single dashboard.

**Anti-patterns:** enabling services but never reviewing/acting on findings (compliance theater); treating detective controls as sufficient alone; unfiltered findings causing alert fatigue; not protecting detective services from being disabled.

---

## 13. Common Misconceptions

- "GuardDuty, Config, and Security Hub all do the same thing." → False — state vs behavior vs aggregation, complementary.
- "Enabling these requires deploying scanning infrastructure." → Mostly false — GuardDuty/Config consume existing logs/state; Inspector needs some connectivity but is largely automated.
- "100% Security Hub compliance pass = fully compliant/secure." → False — covers only automated, codified checks; process-level compliance still needs separate evidence.
- "Detective controls make preventive controls unnecessary." → False — complementary; preventing is strictly better than detecting after the fact.

---

## 14. Interview Questions (with model answers)

**🟢 Config vs GuardDuty?** Config tracks configuration state against rules ("is this set up correctly" — encryption enabled, SG too open). GuardDuty analyzes behavioral signals (API activity, network traffic) for active malicious behavior ("is something bad happening"). Complementary — static correctness vs dynamic threat behavior.

**🟢 What does Security Hub do?** Aggregates findings from GuardDuty, Config, Inspector, Access Analyzer, third-party tools into one standardized format/dashboard, and runs automated compliance checks (FSBP, CIS). The "one place to see posture" layer over the individual detective services.

**🟡 Prevent a compromised admin credential from disabling GuardDuty?** Same SCP principle — an in-account IAM policy, even an admin's, can't override an Organization-level SCP. Apply an SCP denying GuardDuty-disabling actions at the OU level, so even a compromised admin can't turn off detection.

**🟡 Inspector vs Config — what's the difference?** Config checks configuration matches a rule (encryption enabled, SG too open). Inspector looks for known CVEs in installed packages/container images plus network reachability. Config = configuration correctness broadly; Inspector = vulnerability/software supply-chain specifically — a resource can pass Config's rules and still run vulnerable software Inspector flags.

**🔴 Design detective-control strategy for a 60-account Organization?** Enable GuardDuty, Security Hub, Config, Inspector org-wide via delegated administration from a Security account; management account stays minimal. Security Hub as central dashboard (FSBP + CIS), aggregating others + Access Analyzer. High-confidence findings (public S3 bucket, highest-severity GuardDuty) route via EventBridge to automated Lambda remediation; ambiguous findings route to a ticketing system for human triage. SCPs across the Org deny disabling any of the four services. Use Config's history during incident investigations.

**🔴 Security Hub CIS check shows 100% pass — fully compliant/secure?** No. 100% means every automated check in that benchmark currently passes — valuable, continuously-verified, but only covers what's technically checkable. Doesn't cover process-level requirements (staff training, incident-response adherence) an auditor separately verifies — echoes Shared Responsibility Model's compliance-inheritance limits. Also only reflects the moment of evaluation — new noncompliant resources could appear tomorrow, which is why it must be continuous monitoring, not a one-time report. Present as strong automated evidence, not a complete guarantee.

---

## 🔑 Key Takeaways

1. These four services are detective controls complementing Sections 1–7's preventive controls — detect what prevention doesn't catch, near-real-time.
2. Each answers a distinct question: GuardDuty (behavior/threats), Config (state/configuration), Inspector (vulnerabilities/software supply chain), Security Hub (aggregation/posture). Complementary, not redundant.
3. Security Hub checks both AWS-specific (FSBP) and industry-standard external benchmarks (CIS, PCI DSS) — genuinely mapped to auditor-recognized standards.
4. All four support delegated administration (Section 5 pattern) — enable org-wide from a dedicated Security account.
5. Findings can trigger automated remediation via EventBridge, and the detective services themselves should be SCP-protected from being disabled — a closed-loop, self-defending system.

## 🌐 Related Concepts (forward links)

- CloudTrail and VPC Flow Logs as underlying GuardDuty data sources → Part 8
- EventBridge-driven automated remediation in full depth → Part 7
- Network-layer edge security (WAF, Shield) → §17 (next)
