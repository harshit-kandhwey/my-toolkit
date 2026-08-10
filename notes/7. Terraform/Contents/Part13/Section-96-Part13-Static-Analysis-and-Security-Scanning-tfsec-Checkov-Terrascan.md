# Section 96 (Part 13): Static Analysis and Security Scanning (tfsec, Checkov, Terrascan)

## 1. Definition

**Plain language:** Static analysis and security scanning tools read Terraform configuration files — without ever running `plan` or `apply`, without ever touching real cloud infrastructure — and flag patterns known to be security risks: a publicly readable S3 bucket, a security group open to `0.0.0.0/0` on port 22, an unencrypted database, an overly permissive IAM policy. Running these tools before `apply` catches misconfigurations while they're still a diff in a pull request, not a live vulnerability.

**Precise definition:** **Static analysis / security scanning for Terraform** is the practice of running purpose-built tools — **tfsec**, **Checkov**, and **Terrascan** are the three most widely adopted — against `.tf` configuration files (and, for some tools, against `plan` JSON output) to detect security misconfigurations, compliance violations, and best-practice deviations using a library of predefined rules, without provisioning any real infrastructure. Each tool matches configuration against a rule set (tfsec and Terrascan use built-in rule engines with some custom-rule support; Checkov additionally supports custom policies in Python or a YAML-based policy DSL) and reports findings with a severity level, an affected resource/line, and typically a remediation link. These tools operate entirely at the configuration-file layer, distinct from `terraform validate` ([§27](../Part4/Section-27-Part4-terraform-validate-and-terraform-fmt.md), which checks syntax and internal consistency, not security posture) and from runtime compliance tools ([§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md), which check what's actually deployed against policy after the fact).

> 💡 **Tip:** Static analysis catches what the configuration _says_ to build, not what's actually running — a scan that passes cleanly on `.tf` files says nothing about resources that already exist with drifted, non-compliant configuration outside Terraform's current management. Pair static analysis (this section) with drift/compliance detection ([§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) for coverage of both "before it's built" and "after it's built and possibly changed."

## 2. Why This Matters

- **Shifts security review to the cheapest possible point in the lifecycle** — a misconfiguration caught in a pull request costs a comment and a fix; the same misconfiguration caught after `apply` costs an incident, a rotation, and possibly a breach.
- **Codifies security knowledge that shouldn't depend on every engineer remembering every rule** — "security groups shouldn't allow unrestricted ingress on port 22" is a rule the scanner enforces consistently, rather than relying on every reviewer to catch it in every PR by eye.
- **Directly catches several of the risks this Part covers elsewhere** — hardcoded secrets in configuration (relevant to [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)), overly permissive IAM policies (relevant to [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), unencrypted storage/backends (relevant to [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) — making it a practical enforcement mechanism for the principles the rest of Part 13 explains conceptually.
- **Integrates naturally into CI/CD as a required check** ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), turning "security review" from a manual, inconsistent gate into an automated, consistent one that blocks merges on high-severity findings.
- **Widely expected tooling knowledge in DevOps/platform engineering roles** — familiarity with at least one of these three tools is a common practical interview and on-the-job expectation.

## 3. Prerequisites and Dependencies

This section assumes basic familiarity with `terraform validate` ([§27](../Part4/Section-27-Part4-terraform-validate-and-terraform-fmt.md)) as a point of contrast — validate confirms configuration is internally consistent and syntactically correct; these tools assess whether internally-valid configuration is nonetheless a security risk, an entirely different question. [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) (pre-commit hooks and linting with tflint) covers a related but distinct tool aimed primarily at code quality/correctness rather than security. [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) (CI/CD pipeline integration) is where these scanners are typically wired in as an automated gate — this section covers the tools themselves; [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) covers the pipeline plumbing around them.

## 4. Architecture / Conceptual Diagram

```text
   WHERE STATIC ANALYSIS SITS IN THE PIPELINE

   Engineer writes/modifies .tf files
              │
              ▼
   ┌─────────────────────────┐
   │  terraform fmt/validate │  syntax + internal consistency only —
   │  (§27)                  │  NOT security-aware
   └─────────────────────────┘
              │
              ▼
   ┌─────────────────────────────────────────────────────┐
   │  tfsec / Checkov / Terrascan                        │
   │  Static security scan of .tf (and/or plan JSON)     │
   │  - Public S3 bucket?           FLAG                 │
   │  - SG open 0.0.0.0/0:22?       FLAG                 │
   │  - Unencrypted EBS/RDS?        FLAG                 │
   │  - Hardcoded secret literal?   FLAG                 │
   │  - Overly broad IAM policy?    FLAG                 │
   └─────────────────────────────────────────────────────┘
              │
       ┌──────┴──────┐
       ▼             ▼
   PASS clean    FAIL (findings above threshold)
       │             │
       ▼             ▼
   PR can merge   CI blocks merge — engineer fixes or
   → terraform    explicitly suppresses w/ justification
     plan/apply       comment, then re-scans
       │
       ▼
   (deployed infrastructure — now covered by
   drift/compliance detection instead, §97)
```

- Static analysis is a **pre-apply, configuration-layer** gate — it never touches cloud APIs or real resources, which makes it fast, safe to run on every commit, and blind to anything not expressed in the `.tf` files themselves (e.g., manual console changes, which is exactly what [§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)'s drift detection covers instead).
- All three tools can typically run against a `plan` JSON export as well as raw `.tf` files, which lets them evaluate the _fully resolved_ configuration (with variables/modules expanded) rather than just the static text.
- Findings carry a severity (commonly Critical/High/Medium/Low, naming varies by tool) that CI pipelines use to decide pass/fail thresholds — a common pattern blocks merges on High/Critical findings while allowing Medium/Low to be tracked but non-blocking.

## 5. Hands-On

### 5.1 tfsec

**Purpose:** Fast, Terraform-specific security scanner with a large built-in rule set covering AWS, Azure, and GCP.

**Syntax:**

```bash
tfsec .
tfsec . --minimum-severity HIGH
tfsec . --format json --out results.json
```

**Example usage and expected output:**

```bash
$ tfsec .
Result #1 HIGH Security group rule allows egress to multiple public internet addresses.
────────────────────────────────────────────────────────────────────────────
  main.tf:12
────────────────────────────────────────────────────────────────────────────
   12    ingress {
   13      from_port   = 22
   14      to_port     = 22
   15      cidr_blocks = ["0.0.0.0/0"]
   16    }
────────────────────────────────────────────────────────────────────────────
  ID            aws-vpc-no-public-ingress-sgr
  Impact        The port is exposed for ingress from the internet
  Resolution    Set a more restrictive CIDR range

  timings       --------------------------------
  parse:        22ms
  adaptation:   4ms
  checks:       11ms
  results:      1

  results       --------------------------------
  1 potential problem(s) detected.
```

**Production usage example:** tfsec is commonly run as a fast pre-commit hook ([§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) and again as a required CI check, since its scan speed makes it viable to run on every local commit without meaningfully slowing developer feedback loops.

**Common errors:** A finding on a resource the team has deliberately accepted risk on (e.g., an intentionally public S3 bucket for static website hosting) — resolved with an inline suppression comment (`#tfsec:ignore:aws-s3-enable-bucket-encryption`) that documents the accepted exception rather than silently disabling the check globally.

### 5.2 Checkov

**Purpose:** Broader policy-as-code scanner covering Terraform plus other IaC formats (CloudFormation, Kubernetes manifests, Dockerfiles), with custom policy support.

**Syntax:**

```bash
checkov -d .
checkov -d . --framework terraform --compact
checkov -d . --check CKV_AWS_20   # run a single specific check
```

**Example usage and expected output:**

```bash
$ checkov -d . --compact
Check: CKV_AWS_20: "S3 Bucket has an ACL defined which allows public access"
        FAILED for resource: aws_s3_bucket.data
        File: /main.tf:5-9

Check: CKV_AWS_23: "Ensure every security group rule has a description"
        PASSED for resource: aws_security_group.web

Passed checks: 42, Failed checks: 1, Skipped checks: 0
```

**Production usage example:** Checkov's broader IaC-format coverage makes it a common choice for organizations running mixed IaC (Terraform alongside Kubernetes manifests or CloudFormation for legacy stacks), consolidating security scanning under one tool and one report format rather than one scanner per IaC format.

**Common errors:** A high failed-check count on first run against an existing, previously unscanned codebase — expected when adopting Checkov retroactively; the practical remediation path is triaging and either fixing or explicitly suppressing (`--skip-check`) findings incrementally rather than treating the first scan as a merge-blocking gate.

### 5.3 Terrascan

**Purpose:** Policy-as-code scanner built on Open Policy Agent (OPA)/Rego, oriented toward custom, organization-specific compliance policies in addition to built-in rules.

**Syntax:**

```bash
terrascan scan -i terraform -d .
terrascan scan -i terraform -d . --severity high
```

**Example usage and expected output:**

```bash
$ terrascan scan -i terraform -d .
Violation Details -

	Description    : S3 bucket does not have server side encryption enabled
	File            : main.tf
	Line            : 5
	Severity        : HIGH
	Resource Name   : data
	Resource Type   : aws_s3_bucket
	Rule Name       : awsS3BucketEncryption

Scan Summary -

	File/Folder         : .
	Rego Policies Path  : /usr/local/share/terrascan/pkg/policies/opa
	Low                 : 0
	Medium              : 2
	High                : 1
	Total Policies      : 45
	Total Violations    : 3
```

**Production usage example:** Terrascan's OPA/Rego foundation makes it a natural fit for organizations that already use OPA for other policy-as-code needs (e.g., Kubernetes admission control, or Sentinel/OPA policy testing in CI, [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) — one policy language across multiple enforcement points.

**Common errors:** Custom Rego policies failing to load due to package/path mismatches — Terrascan's custom policy discovery is sensitive to Rego package naming conventions matching its expected directory structure.

## 6. Production Usage Notes

- **No single tool has universal superset coverage** — teams often run more than one (commonly tfsec for speed at pre-commit/local, plus Checkov or Terrascan for broader coverage in CI) rather than treating any one as sufficient alone.
- **Suppression mechanisms must be used deliberately and visibly** — every tool supports inline or config-level suppression of specific findings; a suppression without a documented justification is functionally identical to never having scanned that resource at all, and audits should specifically review suppression comments for staleness.
- **Scanning `plan` JSON output rather than raw `.tf` catches issues only visible after variable/module resolution** (e.g., a variable default that happens to be insecure, only apparent once resolved) — raw-file scanning is faster and sufficient for most rules, but plan-based scanning is a meaningful complement for dynamic configurations.
- **Rule sets update over time as new services/misconfiguration patterns emerge** — pinning a scanner to an old version silently stops catching newly added checks; keeping scanner versions current is itself a maintenance responsibility, not a one-time setup task.

## 7. Security Considerations

- **Static analysis catches known, codified misconfiguration patterns — it does not catch novel or context-specific risks** the rule authors didn't anticipate; it's a strong baseline floor, not a substitute for human security review on sensitive changes.
- **These tools commonly flag exactly the issues this Part discusses elsewhere**: hardcoded secret-looking string literals (relevant to [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)'s "don't put static secrets in configuration"), IAM policies with wildcard actions/resources (relevant to [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)'s least-privilege execution-role guidance), and unencrypted or publicly accessible backend storage (relevant to [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) — running one of these scanners is a concrete, automatable way to enforce those principles rather than relying on manual review discipline alone.
- **A clean scan result is not the same as "secure infrastructure"** — it means the configuration doesn't match any known-bad pattern in the rule set; a genuinely novel misconfiguration, or a risk arising from the _combination_ of several individually-compliant resources, can still slip through.
- **Suppression comments accumulate risk silently over time if not periodically re-reviewed** — an accepted exception from eighteen months ago, written against a different threat model or compliance requirement, may no longer be an acceptable risk today.
- **CI-integrated scanning should fail the build on high-severity findings by default**, not merely report them — a scanner whose findings are advisory-only in practice provides far weaker protection than one wired as an actual merge gate.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                             | Likely Cause                                                                            | Resolution Path                                                                                                                 |
| --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Scanner reports dozens of findings on first run against an existing codebase                        | Retroactive adoption against previously unscanned configuration                         | Triage by severity, fix or explicitly (and visibly) suppress incrementally rather than blocking all merges immediately          |
| A known, deliberately-accepted risk keeps failing CI on every PR                                    | No suppression applied, or suppression scoped incorrectly (wrong resource/check ID)     | Add a scoped, justified inline suppression comment referencing the specific check ID and the accepted-risk rationale            |
| Scanner passes cleanly but a real misconfiguration was found later via manual review or an incident | The specific pattern wasn't covered by the rule set in use (novel or org-specific risk) | Author a custom policy/check (Checkov Python/YAML policy, Terrascan Rego policy) codifying the newly discovered pattern         |
| Different scanners disagree on whether the same resource is a finding                               | Different rule sets and severity models across tools — expected, not a bug              | Treat findings as complementary rather than contradictory; investigate the underlying resource on its merits, not by vote count |

## 9. Best Practices

- Wire at least one scanner into CI/CD as a required, blocking check on High/Critical findings ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), not just a manual/optional step.
- Run a fast scanner (tfsec is commonly chosen for this) at pre-commit ([§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) for immediate local feedback, complemented by a broader scan in CI.
- Require a visible, reviewed justification comment for every suppression, and periodically re-audit suppressions for staleness.
- Author custom policies for organization-specific requirements the built-in rule sets don't cover (internal naming/tagging standards, org-specific compliance mandates).
- Keep scanner tool versions current so newly published rules are actually being applied, not silently missing from an outdated ruleset.

## 10. Common Anti-Patterns / Mistakes

- **Running a scanner only manually/occasionally rather than as an automated, required CI gate** — inconsistent enforcement that depends on someone remembering to run it.
- **Suppressing findings without a documented justification**, effectively disabling the check silently with no audit trail of why.
- **Treating a clean scan as proof of security**, skipping human review entirely on sensitive changes (IAM policy changes, backend configuration changes) that deserve judgment beyond pattern matching.
- **Adopting a scanner retroactively and blocking all merges immediately on the full backlog of pre-existing findings**, which tends to produce either a stalled pipeline or a culture of blanket suppression rather than genuine remediation.

## 11. Interview Questions

**🎯 Beginner:** _"Name two tools commonly used to statically scan Terraform configuration for security issues."_
**Model answer:** tfsec, Checkov, and Terrascan are the three most widely used — any two of them, e.g., "tfsec and Checkov scan `.tf` files for misconfigurations like public S3 buckets or overly permissive security groups, without needing to actually apply the configuration."
_What the interviewer is probing for:_ Basic tooling awareness and understanding that these operate pre-apply, on configuration files.

**🎯 Intermediate:** _"How is static security scanning different from `terraform validate`?"_
**Model answer:** `terraform validate` checks that configuration is syntactically correct and internally consistent — valid HCL, correctly-typed arguments, resolvable references — but has no concept of security best practice; a security group open to the entire internet on port 22 validates cleanly. Static security scanners like tfsec/Checkov/Terrascan check the same configuration against a library of known-bad security patterns, a completely different and additional layer of analysis that `validate` doesn't perform.
_What the interviewer is probing for:_ Clarity that "valid" and "secure" are unrelated properties of configuration — a common point of confusion for engineers new to these tools.

**🎯 Senior:** _"A team's CI pipeline has tfsec wired in as a required check, and it's been passing cleanly for a year. A security audit still finds a serious misconfiguration in their deployed infrastructure. How is that possible, and what would you add to their process?"_
**Model answer:** Several possibilities: the misconfiguration might not be expressible in the current `.tf` configuration at all — it could be drift from a manual change made outside Terraform, which static scanning of configuration files can never detect since it's blind to actual deployed state (this is exactly the gap [§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)'s drift/compliance detection is meant to close). Alternatively, the specific misconfiguration pattern might simply not be covered by tfsec's built-in rule set — no scanner has universal coverage, and a genuinely novel or org-specific risk pattern requires a custom rule to catch. I'd add: (1) drift/compliance scanning of actual deployed infrastructure, not just configuration, (2) a second scanner with a different rule set for broader coverage, (3) periodic manual security review supplementing automated scanning, especially for IAM and networking changes.
_What the interviewer is probing for:_ Recognition that static analysis has a specific, limited scope (configuration files, known rule patterns) and doesn't substitute for drift detection or human review — a sophisticated understanding of the tool's boundaries, not just its existence.

**🎯 Architect:** _"Design the static-analysis strategy for an organization migrating 200+ existing Terraform repositories to a mandatory security-scanning requirement, without stalling all in-flight development."_
**Model answer:** Roll out incrementally rather than as a single big-bang gate: first, run scanners in report-only (non-blocking) mode across all 200+ repos to establish a baseline inventory of existing findings, categorized by severity and repo. Second, make new/changed code in every PR subject to a blocking gate immediately (no new High/Critical findings allowed on the diff), which stops the problem from growing without requiring the entire existing backlog to be fixed first. Third, set a phased remediation timeline for the pre-existing backlog, prioritized by severity and by which repos manage the most sensitive infrastructure (production, IAM, networking) first. Fourth, require documented, reviewed suppressions for any finding the team decides to formally accept rather than fix, with an expiry/re-review date rather than a permanent silent exception. Fifth, standardize on a small number of scanners (not all three of tfsec/Checkov/Terrascan everywhere) to keep tooling maintenance and rule-set currency manageable at 200-repo scale, choosing based on the org's existing IaC format diversity and whether OPA/Rego is already in use elsewhere. This sequencing avoids both extremes — neither stalling all development waiting for a perfect backlog fix, nor adopting scanning in name only with no actual enforcement teeth on new work.
_What the interviewer is probing for:_ Organizational rollout judgment — balancing enforcement rigor against development velocity at scale, and specifically the insight that gating new/changed code immediately while phasing in backlog remediation is the practical middle path.

## 12. Common Misconceptions

1. **"A clean tfsec/Checkov/Terrascan scan means the infrastructure is secure."** It means the configuration matches no known-bad pattern in that tool's rule set — novel risks, org-specific risks, and drift from actual deployed state are all outside what a clean scan can attest to.
2. **"These tools are interchangeable — any one is as good as the others."** They have meaningfully different rule set coverage, extensibility models (Checkov's Python/YAML policies vs. Terrascan's Rego), and IaC-format breadth (Checkov covers more than just Terraform) — the right choice depends on the organization's specific needs.
3. **"Static analysis replaces the need for drift detection."** Static analysis only ever sees what's written in configuration files — it has no visibility into what's actually deployed, including manual changes made outside Terraform, which is precisely what [§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md) addresses instead.
4. **"Suppressing a finding is equivalent to fixing it."** A suppression without genuine remediation just stops the tool from reporting the risk — the underlying misconfiguration, if real, remains exactly as present in the deployed infrastructure as before.

## 13. 🔑 Key Takeaways

- tfsec, Checkov, and Terrascan statically scan Terraform configuration (and, for some, resolved `plan` JSON) against libraries of known security misconfiguration patterns, entirely before any `apply` touches real infrastructure.
- This is a distinct layer from `terraform validate` (syntax/consistency) and from drift/compliance detection ([§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md), which checks actual deployed state) — all three are complementary, not substitutes for one another.
- These scanners are a concrete, automatable enforcement mechanism for principles covered elsewhere in this Part: no hardcoded secrets ([§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)), no overly permissive IAM ([§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), encrypted/access-controlled backend storage ([§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)).
- Suppressions must be documented, justified, and periodically re-reviewed — an undocumented suppression is functionally the same as never having scanned that resource.
- A clean scan is a floor, not a ceiling — it rules out known-bad patterns, not novel risks or the combined effect of several individually-compliant resources.

## 14. Related Concepts & What's Next

[§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md), next, extends this Part's security coverage from configuration-time scanning to post-deployment drift detection and compliance enforcement — the "after it's built" counterpart to this section's "before it's built" scanning. [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) covers Sentinel/OPA policy testing in CI, a related but distinct policy-as-code layer often used alongside these scanners. [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) covers pre-commit hooks and linting generally, the mechanism by which fast scanners like tfsec are commonly wired into a developer's local workflow.

**Next Section:** [§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md) — `Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md`
