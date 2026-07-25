# Section 64 (Part 9): Part 9 Wrap-Up — Landing Zone Synthesis & Interview Drill

## 64.1 Purpose of This Section

Part 9 covered GCP's enterprise landing zone model across five sections: the overall architecture and Enterprise Foundations Blueprint (Section 59), Organization Policy hierarchy design (Section 60), centralized logging and security projects (Section 61), Shared VPC at scale (Section 62), and automated folder/project vending (Section 63). This closing section consolidates that material into one reference architecture, drills the material with tiered interview questions spanning all five sections, and transitions into Part 10's AI/ML coverage.

## 64.2 Part 9 Recap — What Was Covered

| §   | Section                                        | Core Idea                                                                                                                                                                                                                                                                    |
| --- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 59  | Landing Zone Architecture & Blueprints         | GCP has no Control-Tower-equivalent managed product; the landing zone is assembled from existing primitives (folders, Organization Policy, Shared VPC, log sinks) and codified via Google's Enterprise Foundations Blueprint, a self-owned Terraform reference architecture. |
| 60  | Organization Policy Hierarchy Deep Dive        | A single uniform policy set is wrong for an enterprise with genuinely different risk tiers; constraints are layered — a strict org-wide floor, tightened per environment folder, with narrowly scoped, expiring, most-specific-node exceptions.                              |
| 61  | Centralized Logging & Security Projects        | A dedicated logging project (org-level aggregated sink, Bucket-Locked long-term storage) and a separate dedicated security project (Security Command Center, Chronicle export) are kept apart for least-privilege, independent of any workload project's lifecycle.          |
| 62  | Shared VPC at Scale & Multi-Project Networking | Host/service project topology is a deliberate landing-zone decision; subnet-level `compute.networkUser` delegation and Private Service Connect let networking scale to many teams without a central bottleneck or unsegmented reachability.                                  |
| 63  | Folder/Project Vending Automation              | New projects are provisioned via a Terraform project-factory module (or Config Connector), applying a consistent baseline — folder, IAM, network attachment, budget alert, logging inheritance — by construction, removing both manual drift and provisioning latency.       |

## 64.3 The Unifying Architecture: Enterprise Landing Zone Reference Diagram

```
                                             Organization (example.com)
                                                         │
                               Org Policy floor (Section 60): resourceLocations,
                               requireOsLogin, disableServiceAccountKeyCreation,
                               allowedPolicyMemberDomains, skipDefaultNetworkCreation
                                                         │
     ┌─────────────────────┬─────────────────────┬───────┴───────────┬──────────────┬──────────────┐
     ▼                     ▼                     ▼                   ▼              ▼              ▼
fldr:bootstrap         fldr:common           fldr:production     fldr:nonprod   fldr:sandbox   (per-BU folders,
     │                     │                     │                   │              │           Section 60.3.1's
     ▼            ┌────────┴───────┐             │                   │              │           three-tier model)
seed-project      ▼                ▼         + tighter policy     same floor,   relaxed
(Terraform     prj-logging    prj-security        overlay          slight       convenience-only,
state,         (Sec 61:       (Sec 61:            (Sec 60)         relax        security floor intact
CI/CD --       org log        SCC org-scope,                                    (Section 60.3.1)
Sec 63's       sink dest,     Chronicle
pipeline)      Bucket Lock)   export feed,
                              Sec 72)
                                            │                │
                                       host-prod         host-nonprod
                                       (Shared VPC,      (Shared VPC,
                                        Section 62)       Section 62)
                                            │                │
                                    ┌───────┼───────┐        │
                                    ▼       ▼       ▼        ▼
                               svc-projects (vended per Section 63:
                               correct folder + baseline IAM + budget
                               alert + subnet-scoped networkUser,
                               all applied automatically on creation)
```

> 🔑 **The single repeated principle across Part 9:** consistency is achieved **by construction**, not by manual diligence — Organization Policy inheritance (Section 60) guarantees every project under a folder gets that folder's floor automatically; the aggregated log sink (Section 61) guarantees every project's audit trail is captured centrally without per-project setup; and project vending (Section 63) guarantees every new project gets correct baseline IAM, network attachment, and budget alerting the moment it's created. Every section in this Part is a different layer of the same underlying idea: make the correct configuration the automatic default, not a checklist item someone can forget.

## 64.4 Cross-Section Decision Framework

| Question                                                                                                 | Answer                                                                                                                                                             |
| -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Setting up GCP governance from scratch for a new enterprise org?                                         | Deploy the Enterprise Foundations Blueprint (Section 59) in its staged order — bootstrap, org, environments, networking — rather than assembling primitives ad hoc |
| Production folder needs stricter constraints than sandbox, but both need the same data-residency floor?  | Layer folder-level tightening on top of an org-wide floor (Section 60.3.1); never let production and sandbox diverge on genuinely security-critical constraints    |
| A project needs an exception to an org-wide constraint?                                                  | Grant it at the most specific node (the project itself), documented, time-boxed, independently approved (Section 60.3.3)                                           |
| Need to guarantee audit logs survive a project being deleted or compromised?                             | Aggregated org-level log sink to a dedicated logging project, Cloud Storage destination with Bucket Lock (Section 61)                                              |
| A team needs to consume another team's internal service across host projects without VPC peering sprawl? | Private Service Connect with an explicit accept list on the publisher's side (Section 62.5), not peering                                                           |
| Provisioning the two-hundredth project for a new team?                                                   | Automated project vending (Section 63) via the shared factory module — never manual, checklist-driven creation                                                     |
| A guardrail/constraint is generating many one-off exception requests?                                    | Reassess the constraint's tier design itself (Section 60.3.3), not just keep approving individual exceptions                                                       |

## 64.5 Common Mistakes Spanning This Part

- Applying one uniform Organization Policy set everywhere instead of tiering strictness by folder risk profile (Section 60).
- Granting an exception at the folder level to accommodate one outlier project, silently loosening the floor for every other project in that folder (Section 60.3.3).
- Combining the logging and security projects into one "central ops" project, losing the least-privilege separation between log storage administration and security tooling access (Section 61.5).
- Granting `compute.networkUser` at the host project level instead of the specific subnet level, silently expanding a service project's network reachability every time a new subnet is added for another team (Section 62.4).
- Continuing manual, checklist-driven project creation after a vending pipeline exists, reintroducing the drift and latency automation was meant to remove (Section 63.2).
- Describing GCP's landing zone as having "a Control Tower equivalent" rather than correctly framing it as a self-owned, Terraform-codified architecture built from existing primitives (Section 59.6).

## 64.6 Part 9 Interview Drill

### 🎯 Beginner Tier

**Q1:** Does GCP have a single product equivalent to AWS Control Tower for setting up a landing zone?
**A:** No. GCP provides the Enterprise Foundations Blueprint, a Terraform-based reference architecture built from existing primitives — folders, Organization Policy, Shared VPC, and log sinks — that an organization deploys and owns itself, rather than a discrete managed service with its own console wizard the way Control Tower is (Section 59).

**Q2:** Why would production and sandbox folders have different Organization Policy constraints?
**A:** They have very different risk profiles. A strict org-wide floor covers genuinely security-critical constraints (data residency, service-account-key restrictions, domain restrictions) everywhere, including sandbox, while additional strictness is layered onto production specifically, and only convenience-oriented constraints (like external IP restrictions for quick testing) are relaxed in sandbox (Section 60).

**Q3:** Why are logging and security kept as two separate dedicated projects rather than one combined project?
**A:** Least privilege — the team managing log storage and retention doesn't need the elevated visibility into Security Command Center findings and Chronicle detections that a security operations team needs. Separate projects mean separate IAM policies and separate audit trails for each (Section 61.5).

### 🎯 Intermediate Tier

**Q4:** What does "effective policy" mean, and why does granting `compute.networkUser` at the subnet level matter for the same underlying reason?
**A:** Effective policy is the resolved combination of every ancestor node's Organization Policy constraints (org → folder → project); describing a single node's policy in isolation can be misleading (Section 60.3.2). The subnet-level `networkUser` grant matters for an analogous reason: granting it at the project level would let a service project use every subnet in the host project, not just the one it should have access to, so the resolved, effective access must be checked at the specific resource level, not assumed from a broader grant (Section 62.4).

**Q5:** Why is Cloud Storage Bucket Lock specifically important for the centralized logging project?
**A:** It creates an immutable retention policy that cannot be shortened or removed by anyone, including a project owner, once locked. This defends against the scenario where an attacker who has compromised the logging project's own IAM tries to delete audit log evidence to cover their tracks (Section 61.4).

**Q6:** How does automated project vending reduce the Shared VPC networking team's workload without reducing control?
**A:** The project-factory module pre-grants the correct subnet-scoped `compute.networkUser` binding based on which environment/team folder a new project is created under, so teams never file a manual "get network access" ticket. The networking team still retains exclusive control over subnet creation and firewall rules via `compute.networkAdmin`, which stays out of individual teams' hands — self-service is bounded to consuming pre-approved subnets, not administering the network (Section 62.4.1, Section 63.4).

### 🎯 Senior/Architect Tier

**Q7:** Design the landing zone foundation for a multi-business-unit enterprise that needs centralized logging/security but independent per-business-unit networking and policy exceptions. Walk through how Sections 59–63 combine.
**A:** Start with the Enterprise Foundations Blueprint's `0-bootstrap` and `1-org` stages fully centralized and unmodified across business units (Section 59.4) — one bootstrap pipeline, one org-level Organization Policy floor (Section 60), one central logging project receiving the org-level aggregated sink (Section 61), and one central security project running Security Command Center at org scope and feeding Chronicle (Section 61.5, Section 72). Under `production`/`nonproduction`, add a business-unit folder tier, each with its own Shared VPC host project (Section 62) so business units manage their own subnetting and Private Service Connect consumption independently, with business-unit-specific Organization Policy exceptions applied at that folder level, not the org root (Section 60.3.3). Finally, wire the project-factory module (Section 63) to read the requesting folder and apply the correct business-unit-specific baseline — subnet attachment, budget alert, IAM — automatically, so every new project across every business unit is provisioned consistently even though each business unit's network and policy specifics differ.

**Q8:** Six months after this landing zone goes live, an audit finds: three production projects have Organization Policy exceptions with no documented expiry, one service project has `compute.networkUser` bound at the host-project level instead of a specific subnet, and two projects were created manually outside the vending pipeline and are missing budget alerts. What does this pattern indicate, and how do you remediate it?
**A:** This is a signature of governance existing on paper but not being operationally enforced by construction — exactly the gap Part 9's automation-first principle (Section 64.3) exists to close. First, I'd treat each finding as a symptom of a missing guardrail rather than three isolated cleanups: the undocumented exceptions indicate the exception-approval process (Section 60.3.3) isn't actually requiring an expiry field before granting, so I'd fix the process itself, not just backfill expiry dates on these three. Second, the project-level `networkUser` binding indicates either the vending module has a bug or someone bound it manually outside the pipeline (Section 62.4) — I'd correct it to a subnet-scoped binding and add drift detection (Section 63.7) comparing live IAM bindings against what the factory module would produce, so this class of deviation is caught automatically going forward. Third, the two manually created projects indicate the vending pipeline isn't the _only_ practical path to a new project — I'd restrict project-creation IAM at the org level to a small, tightly controlled set of principals (mirroring the Account-Factory-equivalent lesson from AWS, Section 63.9), making the factory module the only sanctioned path for essentially everyone, then backfill the missing budget alerts and required baseline on the two existing projects. Across all three findings, the durable fix is the same: move from "policy exists and people should follow it" to "policy is enforced by the pipeline and drift is automatically detected," which is the throughline of every section in this Part.

## 64.7 Key Takeaways — Part 9 Overall

- 🔑 GCP's landing zone has no single managed equivalent to Control Tower; it is a self-owned Terraform architecture (the Enterprise Foundations Blueprint) built from folders, Organization Policy, Shared VPC, and log sinks (Section 59).
- 🔑 Organization Policy strategy means tiered strictness by folder risk profile with a non-negotiable security-critical floor everywhere, and exceptions granted at the most specific node possible, documented and time-boxed (Section 60).
- 🔑 Centralized logging and security are kept in separate dedicated projects for least-privilege, with the logging destination protected by Bucket Lock against tampering even by a compromised project (Section 61).
- 🔑 Shared VPC scales to many teams through subnet-level `compute.networkUser` delegation and Private Service Connect, never through project-level network grants or unmanaged VPC peering sprawl (Section 62).
- 🔑 Automated project vending is what makes every other Part 9 guarantee — correct policy tier, correct network attachment, correct logging inheritance — actually hold true for every project, by construction, at the two-hundredth project just as reliably as the first (Section 63).

## 64.8 Transition to Part 10

Part 9 established the governed, consistently provisioned foundation an enterprise stands every workload on top of. Part 10 moves up that foundation to GCP's AI/ML and Generative AI platform, starting with **Section 65: Vertex AI Fundamentals** — how GCP's unified machine learning platform trains, tunes, deploys, and serves models, and how the landing-zone guarantees from this Part (project vending's budget alerts and baseline IAM, Shared VPC's Private Service Connect for private model endpoint access, the centralized logging project's audit trail) carry directly into governing AI/ML workloads at the same enterprise scale.

## 64.9 Related Concepts

Resource hierarchy (Section 3), Organization Policy fundamentals (Section 37) and its hierarchy deep dive (Section 60), Shared VPC and Private Service Connect fundamentals (Section 25), Cloud Monitoring/Logging (Section 54), Security Command Center (Section 39), Chronicle SIEM (Section 72), Cloud Build CI/CD underlying the vending pipeline (Section 50), and the GCP vs. AWS vs. Azure comparison (Section 82) all connect to the material synthesized in this section, and Vertex AI (Section 65, next) is where Part 10 begins.
