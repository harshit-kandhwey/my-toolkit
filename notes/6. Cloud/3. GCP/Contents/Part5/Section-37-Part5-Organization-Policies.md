# Section 37 (Part 5): Organization Policies

## 1. Definition

**Plain language:** Organization Policies are company-wide guardrails that say "this action is not allowed here, no matter who is asking or what IAM role they hold." They don't grant anyone access — they restrict what's possible in the first place.

**Precise:** The **Organization Policy Service** lets administrators define **constraints** — restrictions on specific configurable behaviors of GCP resources (e.g., "VMs may not have external IPs," "resources may only be created in these regions") — and attach them at any node in the resource hierarchy (Section 3). Unlike IAM, which grants permissions, Organization Policies restrict what is _allowed to happen at all_, evaluated independently of and prior to whether a principal's IAM permissions would otherwise permit the action.

## 2. Why It Exists

IAM answers "who can do this," but it has no way to express "this must never happen in this project, period, even for someone with broad IAM permissions." Without a separate restriction mechanism, an administrator would have no way to guarantee, for example, that no VM in a security-sensitive folder ever gets a public IP — anyone with `roles/editor` or `roles/compute.instanceAdmin` could still create one. Organization Policies exist to close this gap: a hard ceiling on resource _configuration and behavior_, set once at a high level in the hierarchy and inherited everywhere below it, that IAM grants cannot bypass.

## 3. Core Concepts

### 3.1 Constraints

A **constraint** is the specific rule being governed — e.g., `compute.vmExternalIpAccess`, `gcp.resourceLocations`, `iam.disableServiceAccountKeyCreation`. Constraints come in two shapes:

| Constraint type        | Behavior                                               | Example                                                  |
| ---------------------- | ------------------------------------------------------ | -------------------------------------------------------- |
| **List constraint**    | Defines an allow-list or deny-list of specific values. | `gcp.resourceLocations` — allow only `in:eu-locations`   |
| **Boolean constraint** | A simple on/off switch.                                | `iam.disableServiceAccountKeyCreation` — enforced or not |

### 3.2 Policies

A **policy** is what's actually attached to a node in the hierarchy: it references a constraint and configures its enforcement (e.g., which values are allowed for a list constraint, or whether a boolean constraint is enforced). A policy can be attached at the Organization, Folder, or Project level.

### 3.3 Inheritance and Overrides

Like IAM, Organization Policies attached at a higher node are inherited by default down to every descendant. Unlike IAM, a lower node **can override** an inherited policy — but only if the policy explicitly permits overrides (`inheritFromParent: true` combined with additional rules at the lower level), rather than replacing the parent's rule outright. A constraint's own definition determines whether it can be overridden at all; some critical constraints are designed to never be relaxed lower in the tree.

> ⚠️ **Interview-relevant nuance:** This override-permitting behavior is the single biggest architectural difference from AWS SCPs, which are always a hard, non-overridable ceiling with no member-account opt-out mechanism. Organization Policies are more flexible but require deliberate design — an administrator must explicitly decide, per constraint, whether lower-level exceptions should be allowed at all.

### 3.4 Common Constraints in Practice

- **`compute.vmExternalIpAccess`** — restricts which VMs (by name pattern or "none") may have external IP addresses, a common guardrail to force all egress through a NAT gateway (Section 24) instead of direct public IPs.
- **`gcp.resourceLocations`** — restricts which regions/multi-regions resources may be created in, enforcing data residency (e.g., `in:eu-locations`).
- **`iam.disableServiceAccountKeyCreation`** — blocks creation of new service account keys org-wide, forcing teams onto short-lived credentials (Section 36).
- **`sql.restrictPublicIp`** — prevents Cloud SQL instances from being assigned a public IP.
- **`iam.allowedPolicyMemberDomains`** — restricts IAM bindings to only principals from specified domains, preventing accidental grants to external Gmail accounts.
- **`compute.requireOsLogin`** — enforces OS Login (IAM-governed SSH access) instead of manually managed SSH keys on VM metadata.

## 4. Architecture Diagram

```
                              ORGANIZATION
                    Policy: gcp.resourceLocations = in:eu-locations
                    Policy: iam.disableServiceAccountKeyCreation = TRUE (not overridable)
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
      FOLDER: "Prod"          FOLDER: "Sandbox"           FOLDER: "Shared-Services"
      (inherits both              Policy override:
       policies as-is)            gcp.resourceLocations =
                                   in:us-locations
                                   (allowed only if constraint
                                    permits override)
              │                        │
              ▼                        ▼
     PROJECT: "payments-prod-01"  PROJECT: "sandbox-test-01"
     Must create resources in    Sandbox override lets devs
     EU only; cannot create      test in a US region for
     SA keys — no exceptions     latency reasons, still bound
                                  by the non-overridable
                                  key-creation constraint
                                  inherited from the Org
```

## 5. Comparison with AWS and Azure

| Concept                         | GCP                                                          | AWS                                               | Azure                                                         |
| ------------------------------- | ------------------------------------------------------------ | ------------------------------------------------- | ------------------------------------------------------------- |
| Mechanism name                  | Organization Policy Service                                  | Service Control Policy (SCP)                      | Azure Policy                                                  |
| What it restricts               | Specific configurable resource behaviors (constraints)       | Any IAM action (ceiling on max permissions)       | Resource configuration, with audit or deny effect             |
| Can grant access?               | No — restriction only                                        | No — restriction only                             | No — restriction/audit only                                   |
| Overridable lower in hierarchy? | Yes, if the constraint permits it                            | No — always a hard ceiling                        | Yes, via policy exemptions                                    |
| Enforcement modes               | Enforce / not enforce; some support dry-run                  | Enforce only (attached or not)                    | Deny, Audit, Append, Modify, DeployIfNotExists, disabled      |
| Granularity                     | Per-constraint (hundreds of specific, pre-built constraints) | Per-IAM-action (broad, expressed via policy JSON) | Per-policy-definition (JSON rule + effect), highly extensible |

## 6. Hands-On Example: Restricting Resource Locations and VM External IPs

**Purpose:** Enforce EU-only resource creation at the Organization level and block external IPs on VMs within a specific Folder — two of the most common enterprise guardrails.

```bash
gcloud org-policies set-policy eu-locations-policy.yaml
```

Where `eu-locations-policy.yaml` contains:

```yaml
name: organizations/123456789012/policies/gcp.resourceLocations
spec:
  rules:
    - values:
        allowedValues:
          - in:eu-locations
```

**Restricting external IPs at a Folder:**

```bash
gcloud resource-manager org-policies enable-enforce \
  compute.vmExternalIpAccess \
  --folder=987654321012
```

**Verifying the effective policy on a project (dry-run/testing before full enforcement):**

```bash
gcloud org-policies describe gcp.resourceLocations \
  --project=my-project-id --effective
```

**Expected output (abbreviated):**

```
spec:
  rules:
  - values:
      allowedValues:
      - in:eu-locations
```

> 💡 **Tip:** Always use `--effective` when troubleshooting "why can't I create this resource" — it shows the final merged policy after inheritance, not just what's attached directly to the project, which is essential since the real restriction may originate several levels up the hierarchy.

## 7. Production & Enterprise Usage

- **Landing zone baseline policies at the Organization root.** Enterprises attach a standard set of non-overridable constraints (no external IPs by default, disable SA key creation, restrict resource locations, require OS Login) at the Organization node as part of the landing zone (Section 59), so every new project inherits secure defaults automatically.
- **Deliberate, documented override points.** Where a Folder genuinely needs an exception (e.g., a public-facing load balancer's VM legitimately needing an external IP), the override is scoped as narrowly as possible and documented, rather than relaxing the constraint broadly at the Organization level.
- **Dry-run before full enforcement.** For constraints with wide potential blast radius, teams enable "dry-run" evaluation first (where supported) or a phased Folder-by-Folder rollout, reviewing Cloud Audit Logs (Section 40) for what _would_ have been blocked, before flipping to full enforcement to avoid unexpectedly breaking existing workloads.

## 8. Common Misconceptions

- **Misconception:** "Organization Policies and IAM Deny policies do the same thing." Organization Policies restrict resource _configuration/behavior_ (e.g., which regions, whether external IPs are allowed) — they are unaware of principals. IAM Deny policies restrict specific _principals_ from specific _permissions_, regardless of resource configuration. They're complementary, not interchangeable.
- **Misconception:** "Every Organization Policy constraint can be overridden lower in the hierarchy." Whether override is even possible is determined by the constraint's own definition — some constraints are explicitly designed to never allow a lower-level exception, precisely for security-critical settings.
- **Misconception:** "Setting an Organization Policy retroactively fixes existing non-compliant resources." Most constraints only prevent _new_ non-compliant configurations from being created; they do not automatically modify or delete resources that were already non-compliant before the policy was enforced — remediation of existing resources is a separate, manual or automated (Section 55) task.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between an IAM policy and an Organization Policy?_
**Model answer:** An IAM policy grants specific principals specific roles (permissions) on a resource — it answers "who can do what." An Organization Policy restricts what actions or configurations are allowed at all on a resource, regardless of any principal's IAM permissions — it answers "what is permitted to exist or happen here," independent of who's asking.

**🎯 Intermediate:** _A Folder needs to allow VMs with external IPs for a specific public-facing project, but the Organization enforces `compute.vmExternalIpAccess` to deny all external IPs. How would you handle this?_
**Model answer:** Check whether the `compute.vmExternalIpAccess` constraint permits override at a lower level; if it does, attach a more permissive policy at the specific Project (or narrowly scoped Folder) that needs the exception, rather than relaxing the Organization-level policy for everyone. This keeps the secure default in place org-wide while allowing a documented, narrowly scoped exception exactly where it's needed.

**🎯 Senior/Architect:** _Design an Organization Policy strategy for a multinational company that must keep EU customer data in the EU, avoid publicly exposed VMs and databases, and still allow a sandbox environment for experimentation with fewer restrictions._
**Model answer:** At the Organization root, I'd enforce `gcp.resourceLocations` restricted to EU locations for the folders holding EU customer-data workloads, `compute.vmExternalIpAccess` denying external IPs by default, `sql.restrictPublicIp` enforced, and `iam.disableServiceAccountKeyCreation` enforced non-overridably, since key hygiene should never be relaxed for any team. I'd structure the hierarchy so a distinct "Sandbox" Folder sits outside the EU-data folders' scope, with its own less restrictive `gcp.resourceLocations` policy (e.g., allowing US regions for lower-latency experimentation) explicitly permitted as an override at that Folder only — while still inheriting the non-overridable constraints like key-creation restriction from the Organization. I'd validate this design with dry-run evaluation before full enforcement, and continuously monitor Cloud Audit Logs for `Policy Denied` events (Section 40) to catch both legitimate exception requests and attempted policy violations.

## 🔑 Key Takeaways

- 🔑 Organization Policies restrict resource configuration/behavior via constraints (list or boolean), independent of and prior to IAM permission checks.
- 🔑 Policies inherit down the resource hierarchy like IAM, but — unlike IAM — can be explicitly overridden lower in the tree if the constraint's definition permits it.
- 🔑 Common enterprise constraints include restricting external IPs, restricting resource locations for data residency, and disabling service account key creation.
- 🔑 GCP's overridable-by-design model contrasts with AWS SCPs (always a hard ceiling) and is closer in spirit to Azure Policy's exemption model.
- 🔑 Organization Policies do not retroactively fix already-existing non-compliant resources — they only prevent new non-compliant configurations going forward.

## Related Concepts

Resource hierarchy and policy inheritance (Section 3), IAM Fundamentals and IAM Deny policies (Section 35), Service Accounts (Section 36), Compliance & Governance / Cloud Audit Logs (Section 40), VPC Service Controls (Section 41), and Landing Zone Architecture / Org Policy Hierarchy Deep Dive (Sections 59–60) all build directly on the Organization Policy model introduced here.
