# Section 116 (Part 16): Scenario-Based Infrastructure Design Questions

## 1. Definition

**Plain language:** This section is a set of larger, open-ended design questions — the kind asked in a system-design-style interview round, where you're given a realistic business situation and asked to design a Terraform-based solution, defend your choices, and respond to follow-up pressure on the trade-offs.

**Precise definition:** A **scenario-based infrastructure design question** presents a realistic organizational or technical constraint (team size, compliance requirement, multi-cloud footprint, migration timeline) and asks the candidate to propose and justify a Terraform architecture, rather than testing a single isolated fact or mechanism. Unlike [§113](./Section-113-Part16-Common-Exam-Style-Scenario-Questions-Worked-Through.md)'s exam-style questions (single correct multiple-choice answer) or [§115](./Section-115-Part16-General-Terraform-Interview-Question-Bank.md)'s conceptual interview questions (explain/evaluate a concept), these questions have multiple defensible answers and are evaluated on the coherence and completeness of the design and its trade-off reasoning — closer to a real system-design interview than either an exam or a standard Q&A interview round.

> 💡 **Tip:** In a live design-question interview, the strongest opening move is almost never to start proposing a solution — it's to ask 1-2 clarifying questions about scale, team structure, or constraints that materially change the right answer (how many environments, how many teams, is Terraform Cloud already in use, is there a compliance requirement). Interviewers consistently read this as senior-level instinct, since jumping straight to a solution before understanding constraints is a common junior-level tell.

## 2. Why This Matters

- Senior and staff-level Terraform interviews (Platform Engineering, SRE, Infrastructure Architect roles) weight this exact question format heavily — often as the single highest-weighted portion of the interview loop — because it's the closest proxy available for how a candidate will actually behave designing real infrastructure.
- Unlike [§113](./Section-113-Part16-Common-Exam-Style-Scenario-Questions-Worked-Through.md)'s exam questions, these have no single graded-correct answer, which means practicing the _reasoning process_ (clarify constraints, propose a design, articulate trade-offs, respond to pushback) matters more than memorizing any specific answer below.
- These questions synthesize material across nearly the entire roadmap (state topology from Part 7, modules from Part 8, workspaces from Part 10, multi-cloud from Part 11, Terraform Cloud from Part 12, security from Part 13, CI/CD from Part 14) — working through them is a genuine cross-roadmap review exercise, not just Part 16 content in isolation.

## 3. Prerequisites and Dependencies

Assumes substantial completion of the full roadmap through Part 15, since these scenarios deliberately draw on state management, modules, workspaces, multi-cloud patterns, Terraform Cloud, and security/CI-CD material together. [§115](./Section-115-Part16-General-Terraform-Interview-Question-Bank.md) (the preceding section) is a natural warm-up, since its Architect-tier questions are a smaller-scale preview of this section's format.

## 4. Architecture / Conceptual Diagram

```text
   THE DESIGN-QUESTION RESPONSE STRUCTURE

   1. CLARIFY                 Ask about scale, team structure, existing
                               tooling, compliance constraints BEFORE
                               proposing anything
            │
            ▼
   2. STATE THE CORE           Name the 1-2 constraints that most
      TRADE-OFF                 shape the design (e.g. "blast radius
                                vs. reuse" or "velocity vs. governance")
            │
            ▼
   3. PROPOSE A CONCRETE        State topology, module boundaries,
      DESIGN                    environment strategy, CI/CD shape —
                                specific enough to be defensible
            │
            ▼
   4. NAME WHAT IT DOESN'T      Explicitly state what your design does
      SOLVE                     NOT address or what it trades away —
                                signals senior-level self-awareness
            │
            ▼
   5. RESPOND TO PUSHBACK       "What if team count doubles?" "What if
                                compliance requires X?" — adapt the
                                design without abandoning its core logic
```

## 5. Scenario Design Questions

### 5.1 Scaling from 3 Engineers to 40 Across 6 Teams

**Purpose:** Test state-topology and module-boundary design judgment as an organization scales.

**Scenario:** _"A startup began with 3 engineers and a single Terraform root module managing everything in one AWS account with local state. They've grown to 40 engineers across 6 product teams, still on that same single root module and now-remote-but-still-single state file. Applies routinely take 15+ minutes, engineers frequently hit state lock contention, and a bad apply from one team recently took down infrastructure another team owned. Design the migration path."_

**Model answer:** The core trade-off here is blast radius and lock contention (everything shares one state) versus the coordination overhead of splitting it. I'd design toward per-team state isolation, likely one state per team per environment, with shared foundational infrastructure (VPC, core networking, IAM boundaries) split into its own separately-owned state consumed by teams via remote state data sources or explicit outputs rather than each team managing shared resources themselves. Concretely: extract the foundational/shared layer first (lowest risk, changes rarely, highest blast radius if broken), validate it as its own state with a clean `plan` showing no changes post-migration, then incrementally extract each team's owned resources into their own state one team at a time using `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) or a backend-and-import approach, validating after each extraction. Module boundaries should mirror the resulting state boundaries — a team's root module calling shared modules for common patterns (a standard service module, for instance) rather than each team hand-rolling similar resources. What this design does NOT solve on its own: it doesn't prevent a team from making a bad apply within their own state — `plan` review discipline and, ideally, a required-approval CI gate ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md), [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) still have to be layered on top, since state isolation only bounds blast radius, it doesn't prevent mistakes.

**What the interviewer is probing for:** Whether the candidate can propose a concrete, incremental, low-risk migration path (not a risky big-bang rewrite) and correctly identify that state splitting bounds blast radius but doesn't by itself fix apply-review discipline.

### 5.2 Multi-Cloud Disaster Recovery Requirement

**Purpose:** Test multi-cloud provisioning pattern design under a genuine business constraint.

**Scenario:** _"A financial services company runs entirely on AWS today, all provisioned via Terraform. A new regulatory requirement mandates the ability to fail over core customer-facing services to Azure within 4 hours in the event of an extended AWS regional outage. Design the Terraform approach."_

**Model answer:** First clarifying question: does "fail over" mean warm standby (infrastructure already running, just needs traffic redirected) or cold standby (infrastructure provisioned on demand during the incident)? A genuine 4-hour RTO strongly favors warm or at least pre-provisioned-but-scaled-down standby, since `terraform apply` for a full production-equivalent Azure footprint from zero — even with mature configuration — realistically risks blowing the 4-hour window on API rate limits, provider quirks, and DNS propagation alone, not to mention the operational chaos of doing it for the first time under incident pressure. I'd design a cross-provider shared-module pattern ([§78](../Part11/Section-78-Part11-Cross-Provider-Patterns-Shared-Modules-Across-Clouds.md)): the customer-facing service's core shape (compute, networking topology, data layer replication target) expressed as provider-agnostic module inputs where feasible, with AWS-specific and Azure-specific implementations underneath, kept running as low-capacity warm standby on Azure continuously rather than provisioned on demand — Terraform then only needs to scale the standby environment up and repoint DNS/traffic management during an actual failover, which is a far smaller, faster, well-rehearsed operation than a cold `apply` from nothing. This also requires the two providers' state to be managed as genuinely separate root modules/state (not shared), since the failure domains are supposed to be independent by design — coupling their state would undermine the entire point. What this design does NOT solve: application-layer data consistency and failover (session state, database replication lag) is a separate, harder problem Terraform alone doesn't address — the regulatory requirement likely needs an application/data-architecture answer in addition to the infrastructure-provisioning one.

**What the interviewer is probing for:** Whether the candidate asks the right clarifying question (warm vs. cold standby) before designing, correctly reasons that a strict RTO rules out cold-provisioning-from-scratch as the primary path, and recognizes the boundary between what Terraform can and can't solve for a DR requirement.

### 5.3 Compliance-Driven Policy Enforcement Across All Applies

**Purpose:** Test knowledge of policy-as-code and governance tooling under a real compliance constraint.

**Scenario:** _"A healthcare company must guarantee, and prove to auditors, that no S3 bucket or storage resource provisioned via Terraform can ever be created without encryption at rest enabled, across every team and every environment, with no exceptions and no reliance on individual engineers remembering to set the flag. Design the enforcement mechanism."_

**Model answer:** The requirement — no reliance on individual memory, provable to auditors — rules out documentation/code-review-only enforcement immediately, since that's exactly the "relies on someone remembering" failure mode the requirement is designed to eliminate. The correct layer is automated policy-as-code enforced at plan/apply time, not just a linter engineers can skip. If the org is on Terraform Cloud/Enterprise, Sentinel ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) is the natural fit — a mandatory policy set attached at the organization level (not per-workspace, to guarantee no team can opt out) that inspects the plan's proposed resource changes and hard-fails any apply proposing an S3 bucket (or equivalent storage resource across other providers, since "storage resource" implies more than just S3) without the required encryption configuration present. If the org isn't on Terraform Cloud, the equivalent is OPA (Open Policy Agent) evaluated against `terraform show -json` plan output as a required, non-bypassable CI gate ([§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) — critically, this has to run server-side in CI, not as a local pre-commit hook alone, since a pre-commit hook is trivially skippable and doesn't produce an audit trail. For the audit-proof requirement specifically, I'd also ensure policy evaluation results are logged and retained (Sentinel's run history in TFC, or CI job logs with retention, exported to wherever the compliance team needs them) since "we have a policy" is not the same as "we can prove the policy was actually evaluated on every historical apply" when an auditor asks. What this doesn't solve: resources created manually outside Terraform entirely bypass this control completely — the compliance requirement likely also needs a complementary cloud-native detective control (AWS Config rules or equivalent, [§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) to catch non-Terraform-provisioned violations, since policy-as-code only governs what goes through the Terraform pipeline.

**What the interviewer is probing for:** Whether the candidate picks the right enforcement layer (org-mandatory policy-as-code, not opt-in linting) for a "no exceptions, provable" requirement, correctly distinguishes Sentinel vs. OPA based on whether TFC is in play, and recognizes that Terraform-side policy enforcement has a real gap (out-of-band manual changes) that needs a separate, complementary control.

## 6. Production Usage Notes

- All three scenarios above are deliberately modeled on real, recurring organizational situations (state-splitting as teams grow, multi-cloud DR under regulatory pressure, provable policy enforcement in regulated industries) rather than artificial exam trivia — working through them is directly transferable to real architecture decisions, not just interview performance.
- The "what this design does NOT solve" step in each model answer is not filler — in real design reviews, explicitly naming a design's boundaries and remaining gaps is exactly what separates a reviewed-and-trusted proposal from one that gets picked apart in the room for gaps the author didn't anticipate.

## 7. Security Considerations

- §5.3 is itself a security/compliance-architecture question — the broader principle it illustrates (automated, non-bypassable, auditable enforcement beats "please remember to" documentation) generalizes far past encryption-at-rest to essentially any hard compliance requirement (network isolation, tagging for cost allocation, mandatory logging configuration).
- §5.2's DR design highlights that infrastructure failover and data/application failover are separate problems — a common security/resilience-review mistake is treating a Terraform-provisioned standby environment as sufficient DR coverage on its own without addressing data consistency and application-layer failover separately.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                         | Resolution Path                                                                                                                                                                                                         |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Jumping straight into a proposed design without clarifying constraints      | Treating the scenario as a trivia question rather than an open design problem                        | Practice explicitly asking 1-2 clarifying questions before proposing anything, per [§4](../Part1/Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md)'s structure                          |
| Proposing a technically sound design but getting picked apart on follow-ups | Design wasn't checked against edge cases (team count doubling, compliance changes) before presenting | Practice the "name what it doesn't solve" step explicitly, anticipating the interviewer's pushback                                                                                                                      |
| Struggling to structure a coherent answer to an open-ended prompt           | No repeatable response framework, improvising each answer from scratch                               | Internalize and practice the 5-step structure in [§4](../Part1/Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md) (clarify, name the trade-off, propose, name gaps, respond to pushback) |

## 9. Best Practices

- Always open with 1-2 clarifying questions before proposing a design in a live scenario-question interview — this is consistently read as a senior-level signal and often changes what the right answer actually is.
- Explicitly state the core trade-off your design is making, and what it deliberately does not solve — both build credibility and preempt the most likely follow-up pushback.
- Practice these scenarios out loud, not just by reading the model answers silently — verbal fluency under a live, back-and-forth interview format is a distinct skill from written comprehension.

## 10. Common Anti-Patterns / Mistakes

- **Proposing a single, rigid "correct" design without acknowledging trade-offs.** Design questions are evaluated on trade-off reasoning; an answer that presents one option as objectively correct with no acknowledged downside reads as inexperience, not confidence.
- **Skipping the clarifying-questions step to seem decisive.** Jumping to a solution before understanding scale, team structure, or constraints is a common and easily-avoided junior-level tell.
- **Designing for the stated scenario only, with no resilience to the interviewer's natural follow-up pressure.** A design that collapses the moment the interviewer asks "what if team count doubles again" signals the design wasn't actually load-bearing, just recited.

## 11. Interview Questions

The three worked scenario questions in §5.1-§5.3 constitute this section's Interview Questions content in full, in place of a separate four-tier Beginner-through-Architect set — consistent with this Part's emphasis on substantive, worked scenario material over a fixed question template for the sections most central to exam and interview payoff.

## 12. Common Misconceptions

1. **"Scenario design questions have one graded-correct answer, like exam questions do."** They're evaluated on the coherence and completeness of trade-off reasoning; multiple designs can be equally strong if well-justified.
2. **"The best move is to propose a solution as fast as possible to show confidence."** Interviewers consistently read premature solutioning, without clarifying constraints first, as a junior-level signal rather than confidence.
3. **"A good design has no acknowledged weaknesses."** Explicitly naming what a design does not solve is a strength signal, not an admission of failure — it shows the candidate understands the design's actual boundaries.
4. **"Terraform-side controls (like Sentinel policy) alone are sufficient for compliance enforcement."** They only govern what goes through the Terraform pipeline; out-of-band manual changes require a separate, complementary detective control.

## 13. 🔑 Key Takeaways

- Scenario-based design questions are evaluated on trade-off reasoning and design coherence, not convergence on one "correct" answer — this distinguishes them from both exam questions ([§113](./Section-113-Part16-Common-Exam-Style-Scenario-Questions-Worked-Through.md)) and standard conceptual interview questions ([§115](./Section-115-Part16-General-Terraform-Interview-Question-Bank.md)).
- The strongest response structure: clarify constraints first, name the core trade-off, propose a concrete design, explicitly state what it doesn't solve, and be ready to adapt under follow-up pressure.
- State-splitting as an organization scales should be incremental and risk-ordered (shared/foundational layer first, then per-team extraction), never a big-bang rewrite.
- A strict RTO for disaster recovery generally rules out cold-provisioning-from-scratch as the primary failover path — warm standby with a fast cutover is usually the realistic design.
- Compliance requirements demanding "no exceptions, provably enforced" call for mandatory, org-level policy-as-code (Sentinel or OPA) evaluated at plan/apply time, not code review or documentation alone — and even then, out-of-band manual changes need a separate detective control.

## 14. Related Concepts & What's Next

This section closes out Part 16's interview and exam-preparation content. Part 17 begins the roadmap's final wrap-up: progressive hands-on labs that move from beginner exercises through production-style, exam-simulation labs, giving a practical venue to apply the domain knowledge, exam techniques, and interview reasoning built across [§112](./Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)-[§116](./Section-116-Part16-Scenario-Based-Infrastructure-Design-Questions.md).

**Next Section:** [§117](../Part17/Section-117-Part17-Progressive-Hands-On-Labs-Beginner-to-Production-Exam-Simulation.md) — `Section-117-Part17-Progressive-Hands-On-Labs-Beginner-to-Production-Exam-Simulation.md`
