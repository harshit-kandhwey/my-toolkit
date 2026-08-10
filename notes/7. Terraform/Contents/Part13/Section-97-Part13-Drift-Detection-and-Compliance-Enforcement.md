# Section 97 (Part 13): Drift Detection and Compliance Enforcement

## 1. Definition

**Plain language:** Static analysis ([§96](./Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) checks whether your Terraform files _describe_ something secure. Drift detection checks whether what's _actually running_ still matches those files — because infrastructure can change outside Terraform entirely: a manual console edit, another automation tool, an incident-response action that opened a port and never closed it. Compliance enforcement takes this further, continuously checking real infrastructure against security policy, independent of whether Terraform's own state even agrees with reality.

**Precise definition:** **Drift** is any divergence between Terraform's recorded state and the actual configuration of real infrastructure — caused by changes made outside Terraform's own `apply` workflow. **Drift detection** is the practice of proactively and regularly identifying this divergence, most simply via scheduled `terraform plan` runs (which report drift as a proposed change even when no configuration was edited) and more robustly via provider-side drift detection features in Terraform Cloud/Enterprise or third-party continuous compliance tooling. **Compliance enforcement** is the broader practice of continuously validating that real, deployed infrastructure — not just Terraform configuration — satisfies security and regulatory policy, typically via policy-as-code (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)/[§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) evaluated against `plan` output, or via dedicated cloud security posture management (CSPM) tooling that scans live infrastructure directly via provider APIs, independent of Terraform's state entirely.

> 💡 **Tip:** A `terraform plan` showing "0 changes" tells you Terraform's state matches its configuration. It does NOT tell you the real infrastructure matches Terraform's state, unless that plan involved a fresh refresh against real infrastructure — and even then, it only proves alignment at that instant. Drift can and does reappear between scheduled checks; treat drift detection as a sampling process, not a continuous guarantee.

## 2. Why This Matters

- **Closes the exact gap left by static analysis ([§96](./Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md))**: a scanner can certify that configuration is secure, but a manually-opened security group rule made in the console an hour after `apply` is invisible to any tool that only reads `.tf` files.
- **Manual "just this once" console changes are extremely common during incidents** — an engineer opens a port to debug something at 2 a.m., fixes the immediate problem, and forgets to revert it or reflect the change back into Terraform configuration; drift detection is often the only mechanism that later surfaces this.
- **Compliance frameworks (SOC 2, PCI-DSS, HIPAA, FedRAMP) generally require continuous, not point-in-time, control validation** — a one-time security review at launch doesn't satisfy an auditor asking "how do you know your infrastructure is still compliant today."
- **State can become stale in ways that mask real risk** — if state says a bucket is private and the bucket was later made public outside Terraform, every static scan and every human reading the `.tf` file sees "private," while reality says otherwise, until drift detection or an actual `refresh` surfaces it.
- **Drift left unresolved compounds** — an unreflected manual change can conflict with a future legitimate `apply`, causing confusing plan output, unexpected resource replacement, or an `apply` that silently reverts a change someone made for a real (if undocumented) reason.

## 3. Prerequisites and Dependencies

This section directly follows [§96](./Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) (static analysis) as the "after deployment" counterpart to that section's "before deployment" scanning — read together, they cover the full security-validation lifecycle. [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) (handling state drift and `terraform refresh`) is a direct prerequisite, covering the base mechanics of what drift is and how `refresh` surfaces it; this section covers drift specifically through a security/compliance lens and at an organizational, ongoing-process scale rather than a single ad hoc `refresh`. [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) (Sentinel and OPA policy-as-code) and [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) (policy testing in CI) are closely related — this section's compliance-enforcement half is where those policy engines are actually applied against real or planned infrastructure state.

## 4. Architecture / Conceptual Diagram

```text
   DRIFT DETECTION AND COMPLIANCE ENFORCEMENT CYCLE

   ┌─────────────────────────┐
   │  Terraform State        │   "what Terraform believes
   │  (last known-applied)   │    is true"
   └─────────────────────────┘
              │
     scheduled/periodic
     terraform plan (refresh-only
     or full) — e.g. nightly cron,
     Terraform Cloud drift detection
              │
              ▼
   ┌─────────────────────────┐        compare against
   │  Real Infrastructure    │◀──── actual cloud API state
   │  (actual cloud state)   │
   └─────────────────────────┘
              │
      divergence found?
       ┌──────┴──────┐
       ▼             ▼
     NO DRIFT      DRIFT DETECTED
   (plan: 0        (plan proposes changes
    changes)        even though nobody
                     edited .tf files)
                          │
                          ▼
              ┌────────────────────────────┐
              │  Triage: was this a        │
              │  legitimate emergency      │
              │  change, or unauthorized/  │
              │  accidental?               │
              └────────────────────────────┘
                          │
                ┌─────────┴─────────┐
                ▼                   ▼
        Reflect the change    Re-apply Terraform's
        back into .tf          config to REVERT the
        config (codify it)     drift back to declared
                                state

   COMPLIANCE ENFORCEMENT (parallel, broader check):
   Policy engine (Sentinel/OPA) evaluates plan output OR
   a CSPM tool scans live infra directly via cloud APIs —
   checks against POLICY (encryption required, no public
   buckets, tagging standards) independent of whether
   Terraform's own state matches reality at all.
```

- Drift detection answers "does reality match what Terraform _thinks_ it created." Compliance enforcement answers a different, broader question: "does reality — regardless of Terraform's state — satisfy policy." A resource can be drift-free (state matches reality) while still being non-compliant (if the _original_ configuration itself was insecure and never caught by [§96](./Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)'s static scan).
- Terraform Cloud/Enterprise offers built-in scheduled drift detection as a platform feature ([§84](../Part12/Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)); the same effect is achievable in open-source Terraform via a scheduled CI job running `terraform plan` on a cadence and alerting on non-empty diffs.
- CSPM (cloud security posture management) tools operate independently of Terraform state entirely, scanning live cloud APIs directly — valuable because they also catch resources never managed by Terraform at all, which drift detection (inherently state-relative) cannot see.

## 5. Hands-On

### 5.1 Scheduled Drift Detection via CI-Triggered `terraform plan`

**Purpose:** Surface drift on a recurring cadence without requiring a human to remember to check.

**Syntax:**

```yaml
# .github/workflows/drift-detection.yml
name: Drift Detection
on:
  schedule:
    - cron: "0 6 * * *" # daily at 06:00 UTC
jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform init
      - run: terraform plan -detailed-exitcode
        # exit code 2 = changes present (drift detected)
```

**Example usage and expected output:**

```bash
$ terraform plan -detailed-exitcode
  # aws_security_group_rule.ssh will be updated in-place
  ~ cidr_blocks = [
      - "10.0.0.0/8",
      + "0.0.0.0/0",     # <-- drift: someone widened this manually
    ]
Plan: 0 to add, 1 to change, 0 to destroy.

$ echo $?
2   # detailed-exitcode: 2 means changes detected — CI alerts on this
```

**Production usage example:** A non-zero drift-check result typically triggers a Slack/PagerDuty alert to the owning team rather than an automatic `apply` — drift usually warrants human triage (was this intentional?) before deciding whether to revert or codify it.

**Common errors:** Treating every scheduled drift-check failure as an incident and auto-reverting — legitimate emergency changes made outside Terraform (a genuine incident-response action) will show up identically to unauthorized drift; blind auto-revert can undo a deliberate fix.

### 5.2 Compliance Enforcement with a Sentinel Policy Against Plan Output

**Purpose:** Enforce a compliance rule (e.g., "no unencrypted S3 buckets") against every plan, independent of whether the plan represents drift or a fresh change.

**Syntax:**

```python
# sentinel policy: require-s3-encryption.sentinel
import "tfplan/v2" as tfplan

s3_buckets = filter tfplan.resource_changes as _, rc {
  rc.type is "aws_s3_bucket" and
  (rc.change.actions contains "create" or rc.change.actions contains "update")
}

main = rule {
  all s3_buckets as _, bucket {
    bucket.change.after.server_side_encryption_configuration is not null
  }
}
```

**Example usage and expected output:**

```bash
$ terraform plan
...
Sentinel Result: false

require-s3-encryption.sentinel:
  Result: false
    FAIL - main
      FAIL - all s3_buckets as _, bucket { ... }
        bucket "aws_s3_bucket.uploads" FAILED: server_side_encryption_configuration is null

Policy check failed — run blocked.
```

**Production usage example:** Policies like this run automatically on every Terraform Cloud/Enterprise plan ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), blocking `apply` regardless of whether the change originates from a normal PR or is proposed to reconcile detected drift — compliance enforcement applies uniformly, not just to new changes.

**Common errors:** A policy written against an older provider schema version failing to find the expected attribute path after a provider upgrade changed the resource's attribute structure — Sentinel/OPA policies require maintenance in step with provider version changes ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)).

## 6. Production Usage Notes

- **Drift detection cadence is a trade-off** — too infrequent (weekly) leaves a long window where drift goes unnoticed; too frequent can generate alert fatigue or unnecessary cost (API calls, compute) for large state files; nightly is a common default, tuned per environment's risk profile.
- **Not all drift should be auto-reverted, and not all drift should be silently codified** — a scheduled process should route detected drift to human review by default, since both "revert everything automatically" and "just update the config to match whatever's out there" carry risk without knowing _why_ the drift occurred.
- **Compliance enforcement via policy-as-code catches issues even in configuration that was never touched by drift** — a resource created two years ago, before a compliance rule existed, will fail a newly-added policy on its next plan even with zero drift, which is a feature (retroactive enforcement), not a bug.
- **CSPM tools that scan live cloud state directly (independent of Terraform) catch a category drift detection structurally cannot: resources never managed by Terraform at all** — genuinely unmanaged, shadow-IT infrastructure is invisible to any Terraform-state-relative process.

## 7. Security Considerations

- **Drift is a first-class security signal, not just an operational nuisance** — a widened security group, a bucket flipped to public, or an IAM policy manually broadened are exactly the kind of changes drift detection is positioned to catch quickly, often faster than a scheduled manual audit would.
- **The routing/triage step after drift is detected is itself a security control point** — an organization needs a defined process (who's alerted, how quickly, what the default action is) or detection capability without a response process provides limited real protection.
- **Compliance enforcement via plan-time policy (Sentinel/OPA) only catches new/changing resources at the moment of `apply`** — it does not retroactively flag already-existing non-compliant resources that nobody has re-applied since the policy was introduced; combining plan-time enforcement with periodic full-account CSPM scanning covers both the "going forward" and "already exists" cases.
- **Alert fatigue is a genuine risk that undermines the control** — a drift-detection pipeline that fires noisy, low-signal alerts (e.g., flagging expected/approved provider-computed attribute changes as "drift") trains responders to ignore it, defeating the purpose entirely; tuning to reduce false positives is a security investment, not just an operational nicety.
- **Drift detection and compliance enforcement should themselves run under a properly scoped, least-privilege credential ([§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md))** — a drift-checking pipeline typically only needs read/describe permissions, not write/create/delete, since it's evaluating state, not changing it.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                            | Likely Cause                                                                                                                          | Resolution Path                                                                                                                                                                                                          |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Scheduled drift check reports changes every single run, even with no manual edits                  | A provider-computed or eventually-consistent attribute (e.g., a tag applied by another AWS service) legitimately differs each refresh | Use `ignore_changes` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) for attributes expected to be managed outside Terraform, distinct from genuine drift |
| Compliance policy blocks an apply that reconciles a legitimate emergency change                    | Policy correctly enforces standard rules without an exception path for incident-driven changes                                        | Establish a documented break-glass/exception process for policy overrides during active incidents, with follow-up review                                                                                                 |
| Drift detected but nobody knows who made the manual change or why                                  | No change-attribution/audit trail captured at the time of the manual change                                                           | Enable cloud provider audit logging (CloudTrail, Activity Log, Cloud Audit Logs) and correlate timestamps with drift detection findings                                                                                  |
| A resource created before a new compliance policy existed keeps failing checks silently, unnoticed | Plan-time policy enforcement doesn't retroactively surface already-existing non-compliant resources unless re-applied                 | Run periodic full-account CSPM/compliance scans independent of Terraform's own plan cycle to catch pre-existing non-compliant resources                                                                                  |

## 9. Best Practices

- Schedule automated drift-detection runs (nightly or more frequent for high-sensitivity environments) rather than relying on ad hoc manual `plan` checks.
- Route every detected drift finding through a defined triage process rather than auto-reverting or auto-codifying by default.
- Layer plan-time policy-as-code (Sentinel/OPA) for new/changing resources with periodic CSPM-style scanning of live infrastructure for full coverage, including resources never touched by a recent apply.
- Use `ignore_changes` deliberately and narrowly for genuinely expected out-of-band attribute changes, to keep drift-detection signal-to-noise high.
- Maintain cloud audit logging (CloudTrail/Activity Log/Cloud Audit Logs) so detected drift can be attributed to a specific actor and change, supporting both security investigation and process improvement.

## 10. Common Anti-Patterns / Mistakes

- **Treating a clean `terraform plan` as proof infrastructure is compliant**, when it only proves alignment with Terraform's own (possibly outdated or never-security-reviewed) configuration.
- **Auto-reverting all detected drift without triage**, silently undoing legitimate emergency changes and potentially reintroducing an incident that was just resolved.
- **Running drift detection so infrequently that the response time to a real security-relevant drift event (widened security group, public bucket) is measured in weeks.**
- **Relying exclusively on Terraform-relative drift detection and skipping independent CSPM/live-infrastructure scanning**, leaving unmanaged/shadow infrastructure entirely outside any compliance visibility.

## 11. Interview Questions

**🎯 Beginner:** _"What is infrastructure drift?"_
**Model answer:** Drift is when real, deployed infrastructure no longer matches what Terraform's state file records — usually because someone changed something manually (via the console, another tool, or a script) outside of the normal Terraform `apply` workflow. `terraform plan` surfaces drift as a proposed change even though nobody edited the `.tf` configuration.
_What the interviewer is probing for:_ Basic conceptual understanding, connecting drift to out-of-band changes specifically.

**🎯 Intermediate:** _"How is compliance enforcement different from drift detection?"_
**Model answer:** Drift detection compares real infrastructure against Terraform's own recorded state — it answers "does reality match what Terraform believes it created." Compliance enforcement compares real (or planned) infrastructure against external policy — encryption requirements, public-access restrictions, tagging standards — independent of whether Terraform's state agrees with reality. A resource can have zero drift (state matches reality perfectly) while still failing compliance, if the original configuration itself was never policy-compliant to begin with.
_What the interviewer is probing for:_ Whether the candidate sees these as related but genuinely distinct checks, not synonyms.

**🎯 Senior:** _"Your team's nightly drift-detection job has been reporting 'drift' on the same three resources every night for months, and everyone has started ignoring the Slack alert. What's actually wrong here, and how do you fix it?"_
**Model answer:** This is a textbook alert-fatigue failure mode, and the underlying cause is almost certainly that the "drift" being reported isn't real unauthorized drift — it's most likely provider-computed or externally-managed attributes (auto-applied tags, an eventually-consistent field, a value another system legitimately updates) that Terraform's plan is flagging as a diff on every refresh. The fix is diagnostic, not procedural: identify exactly which attributes are triggering the diff, confirm they're genuinely expected to be managed outside Terraform, and apply `ignore_changes` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) scoped narrowly to those specific attributes so the drift-detection signal returns to reflecting only genuine, unexpected changes. Simply telling the team to "pay attention to the alerts" without fixing the false-positive source won't work — the alert has already lost credibility and needs to earn it back by becoming reliably meaningful again.
_What the interviewer is probing for:_ Recognizing alert fatigue as a security-relevant failure (a desensitized team will miss the real alert) and diagnosing the root cause (noisy false positives) rather than proposing a process fix that doesn't address it.

**🎯 Architect:** _"Design a drift detection and compliance enforcement strategy for an organization where roughly 30% of cloud infrastructure predates Terraform adoption and is still unmanaged (created manually, never imported)."_
**Model answer:** Terraform-state-relative drift detection is structurally blind to that 30% — it can only compare reality against resources it already knows about. So the strategy needs two complementary layers: (1) standard scheduled drift detection (`plan`-based or Terraform Cloud's built-in feature) for the 70% already under management, catching out-of-band changes to known resources; (2) independent CSPM-style scanning that queries cloud provider APIs directly for the entire account/subscription/project, covering both managed and unmanaged resources, to catch compliance violations and security misconfigurations in the unmanaged 30% that drift detection alone can never see. In parallel, prioritize importing ([§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)) the unmanaged 30% into Terraform state over time, starting with the highest-risk resources (public-facing, IAM-related, data stores), since bringing a resource under Terraform management is what enables the stronger, plan-time enforcement layer (policy-as-code, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)/[§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) to apply to it going forward. The CSPM layer isn't a temporary stopgap to be removed once import is complete, though — it remains valuable permanently as an independent check that doesn't depend on Terraform's own state being accurate, catching both new shadow-IT resources and any gaps in what Terraform believes it manages.
_What the interviewer is probing for:_ Recognition that Terraform-relative tooling has a structural blind spot for unmanaged infrastructure, and the layered design (import roadmap + permanent independent CSPM scanning) needed to actually close that gap rather than assuming drift detection alone provides full coverage.

## 12. Common Misconceptions

1. **"Zero drift means the infrastructure is secure and compliant."** Zero drift only means reality matches Terraform's own state/configuration — if that configuration itself was never security-reviewed, drift-free infrastructure can still be fully non-compliant.
2. **"Drift detection covers everything in the cloud account."** It's inherently relative to what Terraform's state already knows about — resources never brought under Terraform management are structurally invisible to state-relative drift detection.
3. **"All detected drift should be immediately reverted to match Terraform's configuration."** Some drift represents a legitimate, necessary emergency change; blind auto-revert can undo a deliberate fix and potentially reintroduce the problem it solved.
4. **"Policy-as-code enforcement at plan time is sufficient for ongoing compliance."** It only evaluates resources that are actually being created or changed in a given plan — already-existing, unchanged resources aren't re-evaluated against newly added policies unless something triggers a fresh plan/apply against them.

## 13. 🔑 Key Takeaways

- Drift is divergence between Terraform's recorded state and real infrastructure, typically caused by out-of-band manual or automated changes outside the normal `apply` workflow.
- Drift detection (state-vs-reality) and compliance enforcement (reality-vs-policy) are related but distinct checks — a resource can be drift-free while still non-compliant if its original configuration was never policy-reviewed.
- Scheduled `terraform plan` runs (locally, in CI, or via Terraform Cloud/Enterprise's built-in feature) are the standard drift-detection mechanism; detected drift should route to human triage, not automatic revert or automatic codification.
- Policy-as-code (Sentinel/OPA) enforces compliance at plan time for new/changing resources; independent CSPM-style scanning of live infrastructure is needed to catch already-existing or entirely unmanaged resources that plan-time enforcement structurally can't reach.
- Alert fatigue from noisy, false-positive drift signals is itself a security risk — tuning detection to genuine, actionable drift is necessary for the control to remain effective over time.

## 14. Related Concepts & What's Next

[§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md), the final section of this Part, covers securing the backend that state itself lives in — a natural close to this Part's arc from "secrets shouldn't be in state" ([§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) through detecting when reality no longer matches that state (this section) to protecting the state file's storage layer directly. [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) and [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) cover the Sentinel/OPA policy-as-code mechanics referenced here in more depth. [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) remains the reference for the base `terraform refresh` mechanics this section builds an organizational process around.

**Next Section:** [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md) — `Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md`
