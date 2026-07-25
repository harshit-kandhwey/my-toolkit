# Section 60 (Part 9): Organization Policy Hierarchy Deep Dive

## 60.1 Definition

**Plain language:** Section 37 introduced Organization Policy as the mechanism for setting hard resource-configuration constraints (like "no external IPs on VMs") across an org. This section is about the harder, more realistic problem: how do you design a _coherent set_ of these constraints across dozens of folders representing production, non-production, and sandbox environments, so each gets exactly the right level of strictness without engineers fighting the policy engine every day?

**Precise:** An Organization Policy _hierarchy strategy_ is the deliberate design of which constraints are set at the organization root (an unconditional floor for every resource in the org), which are set at intermediate folders (tailored to that folder's risk profile), and which are deliberately left more permissive or explicitly excepted at specific folders or projects — combined with a documented process for requesting and reviewing exceptions.

## 60.2 Why It Exists / Problem It Solves

- Section 37 established _what_ an Organization Policy constraint is and _how_ inheritance and enforcement work mechanically. It did not address the organizational design problem: a single, uniform policy set applied identically everywhere is either too loose (production ends up as permissive as sandbox) or too strict (sandbox experimentation becomes as locked-down as production, killing developer velocity).
- Enterprises solve this by mapping their folder structure (Section 3, Section 59) to distinct risk tiers — typically production, non-production, and sandbox — and deliberately setting different constraint values, or different constraint _presence_, at each tier.
- Getting this wrong in either direction has a real cost: overly strict sandbox policy drives engineers to work around the sanctioned environment entirely (shadow IT within the same org); overly loose production policy leaves genuine security gaps that only surface during an incident or audit.

## 60.3 Designing a Multi-Tier Policy Strategy

### 60.3.1 The Standard Three-Tier Folder Model

| Folder                              | Typical Risk Posture                                                     | Policy Philosophy                                                                                                                                                       |
| ----------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Production**                      | Highest — customer data, revenue-generating systems, compliance scope    | Strictest constraints, minimal exceptions, exceptions require documented, time-boxed approval                                                                           |
| **Non-production** (staging/QA/dev) | Moderate — realistic data volumes but typically synthetic or masked data | Constraints close to production, with a few explicitly loosened for testing convenience (e.g., allowing broader machine type selection)                                 |
| **Sandbox**                         | Lowest — individual experimentation, no production data, cost-capped     | Deliberately more permissive on convenience constraints, but never on data-exfiltration-relevant constraints (e.g., public bucket access remains restricted everywhere) |

### 60.3.2 Inheritance and the "Effective Policy"

- Constraints set at the organization node apply to every folder and project beneath it by default (Section 37). A constraint set again at a lower folder either **merges** with the parent value (for `listConstraint` types, if merge is allowed) or **overrides** it, depending on the constraint's configured inheritance behavior.
- The **effective policy** for any given project is the union of every constraint set at every ancestor node (org → folder → sub-folder → project), resolved according to each constraint's merge/override rules — this is why designing policy top-down, one layer at a time, and testing the _effective_ policy at the leaf project is essential; reasoning about any single node's policy file in isolation is not sufficient.
- A small number of constraints support `inheritFromParent: false` combined with an explicit reset, letting a folder deliberately start from a clean slate rather than merging with its parent — used sparingly, since it breaks the "floor never gets weaker going down the tree" guarantee that most enterprises want to preserve.

### 60.3.3 Exceptions in Large Enterprises

- Real enterprises are never able to apply a single constraint set with zero exceptions across hundreds of projects. A workable exception process needs: (1) a narrow scope (an exception applies to one project or a small, explicitly listed group, never a broad folder), (2) a documented business justification, (3) an expiry or periodic re-review, and (4) an approver who is not the same person requesting the exception.
- Exceptions should be implemented at the **most specific node possible** — directly on the project needing it — rather than by loosening the parent folder's policy for every project in that folder to accommodate one outlier.

## 60.4 Common Enterprise-Scale Constraints

| Constraint                             | Purpose                                                                                                                                           | Typical Tier Applied                                                                       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `compute.vmExternalIpAccess`           | Restrict which VMs (by resource, or deny all) may have external IPs, forcing traffic through NAT/load balancers/VPN instead.                      | Org-wide floor; production denies all, sandbox may allow a short explicit list.            |
| `gcp.resourceLocations`                | Restrict which regions/multi-regions resources may be created in, enforcing data residency.                                                       | Org-wide floor, near-universal.                                                            |
| `compute.requireOsLogin`               | Require OS Login (Section 42-adjacent identity-based SSH access) rather than metadata-based SSH keys, centralizing SSH access through IAM.        | Org-wide floor.                                                                            |
| `iam.disableServiceAccountKeyCreation` | Block creation of long-lived, downloadable service account keys, pushing teams toward Workload Identity and short-lived credentials (Section 36). | Org-wide floor, with narrow, time-boxed exceptions for legacy workloads.                   |
| `compute.restrictSharedVpcSubnetworks` | Limit which Shared VPC subnets a service project may attach to (Section 62).                                                                      | Set per-folder, aligned to which host project/subnet a business unit is authorized to use. |
| `iam.allowedPolicyMemberDomains`       | Restrict IAM bindings to principals from approved domains/organizations, preventing accidental grants to external Gmail accounts.                 | Org-wide floor.                                                                            |
| `compute.skipDefaultNetworkCreation`   | Prevent the legacy auto-mode default VPC from being created in new projects, forcing deliberate Shared VPC attachment instead.                    | Org-wide floor, essential in a landing zone using Shared VPC exclusively.                  |

## 60.5 Architecture Diagram: Policy Strictness by Folder Tier

```
Organization root
  constraints: resourceLocations=[us, eu], requireOsLogin=TRUE,
               disableServiceAccountKeyCreation=TRUE,
               allowedPolicyMemberDomains=[example.com]
       │
       ├── folder: production
       │      + vmExternalIpAccess = DENY ALL
       │      + restrictSharedVpcSubnetworks = [prod-subnets only]
       │      (strictest -- inherits org floor, adds production-only tightening)
       │
       ├── folder: nonproduction
       │      + vmExternalIpAccess = DENY ALL
       │      + restrictSharedVpcSubnetworks = [nonprod-subnets only]
       │      (same floor as prod, slightly relaxed elsewhere e.g. machine types)
       │
       └── folder: sandbox
              + vmExternalIpAccess = ALLOW listed test VMs only
              (org floor still applies -- resourceLocations, OS Login,
               key creation block, domain restriction all still enforced)
```

> ⚠️ **Interview-relevant nuance:** Sandbox being "more permissive" never means abandoning security-critical constraints like data residency or service-account-key restrictions — it means relaxing _convenience_ constraints (external IPs for quick testing, broader machine type choice) while keeping the security floor intact. Interviewers probing this topic are usually checking whether the candidate conflates "developer convenience" with "security exception."

## 60.6 Hands-On Example: Auditing Effective Policy Across Folders

**Purpose:** Confirm what constraint value actually applies to a specific project, accounting for inheritance.

```bash
gcloud resource-manager org-policies describe \
  compute.vmExternalIpAccess \
  --project=prj-payments-prod-8f3a \
  --effective
```

**Expected output:**

```
constraint: constraints/compute.vmExternalIpAccess
listPolicy:
  deniedValues:
  - "*"
```

**Purpose:** Set a stricter, folder-specific constraint on the production folder.

```bash
gcloud resource-manager org-policies set-policy \
  policy-production-external-ip.yaml \
  --folder=333333333333
```

**Expected output:**

```
constraint: constraints/compute.vmExternalIpAccess
listPolicy:
  deniedValues:
  - "*"
updateTime: '2026-07-25T10:00:00Z'
```

> 💡 **Tip:** Always audit with `--effective` when validating a leaf project's actual enforced policy — describing the policy at a single node without `--effective` only shows what was explicitly set _there_, not the resolved outcome after inheritance from every ancestor.

## 60.7 Production & Enterprise Usage

- Enterprises typically version-control every Organization Policy as YAML alongside the landing zone Terraform (Section 59), applying changes through the same CI/CD pipeline as any other infrastructure change, with policy changes at the org or production-folder level requiring an additional security-team review step.
- A periodic (commonly quarterly) audit of every active exception — checking whether its documented expiry has passed and whether its justification still holds — is standard practice at organizations with mature governance; stale, forgotten exceptions are one of the most common real-world audit findings.
- Policy Analyzer (part of Cloud Asset Inventory) is commonly used to answer "which constraint values actually apply to project X and why" across a large hierarchy, complementing the CLI-based `--effective` check shown above for ad hoc investigation.

## 60.8 Common Misconceptions

- **Misconception:** "Setting a constraint at the organization node is enough; folder-level policy is optional." False for any enterprise with genuinely different risk tiers — an org-wide-only policy set forces a single strictness level onto every folder, which is exactly the problem this section's tiered model solves.
- **Misconception:** "An exception granted to one project in a folder should just be applied to the whole folder to save effort." This defeats the purpose of folder-level tiering by silently loosening the floor for every other project in that folder; exceptions belong at the most specific node possible.
- **Misconception:** "Sandbox folders don't need any Organization Policy constraints since nothing there is production." False — constraints preventing data exfiltration, external domain grants, and data residency violations should remain org-wide floors that apply even in sandbox; only convenience-oriented constraints should differ by tier.

## 60.9 Interview Questions

**🎯 Beginner:** _Why would an enterprise apply different Organization Policy constraints to its production folder versus its sandbox folder?_
**Model answer:** Production and sandbox environments have very different risk profiles — production holds real customer data and revenue-critical systems, while sandbox is for individual experimentation with no production data. Applying identical, maximally strict constraints everywhere makes sandbox experimentation painfully slow for no real security benefit, while applying identical, permissive constraints everywhere leaves production under-protected. The standard approach sets a strict, non-negotiable floor at the organization level for genuinely security-critical constraints (data residency, key creation restrictions, domain restrictions), then layers additional strictness onto the production folder specifically, while allowing sandbox to relax only the convenience-oriented constraints.

**🎯 Intermediate:** _What does "effective policy" mean in the context of Organization Policy inheritance, and why is `gcloud resource-manager org-policies describe --effective` important?_
**Model answer:** A project's effective policy is the resolved outcome of every constraint set at every ancestor node — organization, intermediate folders, and the project itself — combined according to each constraint's merge or override rules. Describing a policy at a single node without `--effective` only shows what was explicitly configured at that node, which can be misleading, since a stricter or looser value set higher or lower in the hierarchy may actually be what's enforced. Using `--effective` against the actual project in question is the only reliable way to confirm what constraint value genuinely applies before troubleshooting a blocked deployment or auditing compliance.

**🎯 Senior/Architect:** _An enterprise has production, non-production, and sandbox folders with a shared organization-wide policy floor, but one production project genuinely needs an exception to allow a specific VM to have an external IP for a legacy partner integration. How would you grant this without weakening production's overall posture?_
**Model answer:** I would set the exception directly on that one project's Organization Policy node — not on the production folder — using a `listPolicy` that denies external IPs organization/folder-wide but explicitly allows the specific VM resource (or a narrowly scoped condition) at the project level, so every other project under the production folder remains at the strict floor. I'd pair this with a documented business justification, an explicit expiry or scheduled re-review date, and require approval from someone other than the requesting team, following the standard exception-governance process — and I'd flag it in the periodic policy audit so it doesn't silently become permanent once the legacy integration is eventually decommissioned. I would also evaluate whether a Cloud NAT or load-balancer-fronted alternative could eliminate the need for the external IP entirely, since the exception should be a last resort, not the default response to this kind of request.

## 60.10 Key Takeaways

- 🔑 Organization Policy strategy at enterprise scale means designing tiered strictness across folders (production, non-production, sandbox), not applying one uniform constraint set everywhere.
- 🔑 A project's effective policy is the resolved combination of every ancestor's constraints; always audit with `--effective` before trusting a single node's configuration.
- 🔑 Exceptions belong at the most specific node possible, with a documented justification, an expiry, and independent approval — never as a folder-wide loosening to accommodate one outlier project.
- 🔑 Security-critical constraints (data residency, service-account-key restrictions, domain restrictions) should remain an org-wide floor even in sandbox; only convenience constraints should vary by tier.

## 60.11 Related Concepts

Organization Policy fundamentals (Section 37), resource hierarchy design (Section 3), the broader landing zone this policy strategy is embedded in (Section 59), Shared VPC subnet restriction (Sections 25, 62), service account key restrictions (Section 36), and Cloud Asset Inventory / Policy Analyzer (touched on in Section 40) all connect directly to the concepts in this section.
