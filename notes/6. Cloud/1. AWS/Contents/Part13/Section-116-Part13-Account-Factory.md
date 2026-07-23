# Part 13, Section 2: Account Factory & Automated Account Vending

## 1. Definition

**Plain language:** Part 13 §1 established that Control Tower's guardrails apply consistently to every account in a landing zone — but that consistency guarantee only holds if new accounts are actually created in a way that correctly applies those guardrails from day one. Account Factory is the specific Control Tower component that provisions new AWS accounts, baked from the start with the correct OU placement, guardrails, and baseline configuration, rather than accounts being created ad hoc and potentially inconsistently.

**Precise definition:** Account Factory is a Control Tower capability that automates the provisioning of new AWS accounts within a governed landing zone — applying a defined account **blueprint** (baseline network configuration, IAM Identity Center access assignments, and OU placement determining which guardrails apply) consistently to every new account, and optionally exposing this provisioning capability as a **self-service** request mechanism so authorized teams can request new, properly-governed accounts without requiring a central cloud team to manually build each one.

## 2. Why It Exists / Problem It Solves

- Part 13 §1 established that OU-level guardrails automatically apply to any account within that OU — but an account still has to actually be _created_ correctly: placed in the right OU, given appropriate baseline network configuration, and connected to the organization's identity federation (Part 2 §4) — and doing this manually, account by account, reintroduces exactly the consistency risk and manual-effort burden Control Tower otherwise exists to remove.
- Before automated account vending, provisioning a new AWS account for a team commonly meant a manual request to a central cloud/platform team, who would then manually create the account, configure its network, apply the intended guardrails, and set up access — a genuinely slow process (creating friction for teams needing a new account quickly) and one where manual, repeated execution of the same setup steps introduces exactly the inconsistency risk this Part has repeatedly flagged as a core multi-account governance problem.
- Account Factory removes both problems: a defined blueprint captures "what a properly-configured new account looks like" once, and either the central team or, via self-service, individual authorized requesters can provision a new account that automatically and consistently matches that blueprint — turning account creation from a slow, manual, error-prone process into a fast, consistent, largely automated one.
- 🔑 **Key takeaway:** Account Factory applies the exact same "define once, apply consistently and repeatably" principle established for CloudFormation/CDK/Terraform (Part 9 §1-4) and CI/CD pipelines (Part 9 §8), here specifically applied to the account-provisioning process itself — a genuinely different artifact (an AWS account, not application infrastructure) but the identical underlying discipline.

## 3. Prerequisites and Dependencies

- **AWS Control Tower and landing zone structure** (Part 13 §1): Account Factory is a Control Tower capability, provisioning accounts into the OU structure and guardrail model established there.
- **IAM Identity Center** (Part 2 §4): account blueprints commonly include identity federation configuration, determining who gets access to a newly-provisioned account and with what permissions.
- **VPC networking fundamentals** (Part 4 §1-2): account blueprints commonly include baseline VPC configuration, provisioned automatically as part of account creation.

## 4. Internal Working / Architecture & Components

### 4.1 Account Blueprints

- A **blueprint** defines the baseline configuration applied to every account provisioned through it — commonly including default VPC/subnet configuration (following the public/private subnet patterns from Part 4 §2), default IAM Identity Center permission set assignments (who gets access and at what privilege level), and the target OU (determining which Control Tower guardrails, Part 13 §1 §4.2, apply).
- Organizations can define multiple blueprints for different account purposes — a "standard workload account" blueprint versus a "sandbox account" blueprint versus a specialized blueprint for a particular compliance-sensitive business unit — each encoding the appropriate baseline configuration for that specific account category, directly mirroring the differentiated-guardrails-per-OU principle established in Part 13 §1's Architect answer.

### 4.2 Self-Service Provisioning

- Account Factory can expose account provisioning as a **self-service catalog item** (commonly via AWS Service Catalog, which Control Tower integrates with under the hood) — an authorized requester (a team lead, or an individual developer for a sandbox account) can request a new account through a defined, governed workflow, without needing a central cloud team to manually execute the creation themselves.
- This self-service model directly addresses the "slow, centrally-bottlenecked account creation" problem named in §2 — while still ensuring every self-service-provisioned account inherits the correct blueprint's baseline configuration and guardrails automatically, meaning self-service doesn't trade away governance consistency for speed; it achieves both simultaneously, precisely because the blueprint (not the requester) determines the resulting account's configuration.
- ⚠️ **Warning:** self-service account provisioning still warrants access control over _who_ can request accounts and _which blueprints_ they're authorized to use — an organization typically wouldn't want an arbitrary individual contributor able to self-service-provision a production-OU account with elevated guardrail exemptions; the self-service mechanism's own access control is itself a governance decision, not something to leave unrestricted by default.

### 4.3 Account Lifecycle Management

- Account Factory also supports ongoing account lifecycle operations beyond initial creation — updating an existing account's configuration if its blueprint changes, and (a genuinely more consequential operation) closing/decommissioning accounts that are no longer needed, following a defined process rather than an account simply being abandoned and left running (and potentially still incurring cost or representing an unmonitored security surface).
- 🔑 **Key takeaway:** treating account closure with the same deliberateness as account creation matters — an abandoned, forgotten AWS account is a genuine governance gap (nobody actively monitoring it, but it still exists and could still be a target), directly analogous to the "orphaned resource" risk pattern this course has touched on for individual AWS resources, now applied at the account level.

### 4.4 The General-Purpose Mechanisms Underneath — AWS Service Catalog and AWS Resource Access Manager

Account Factory's self-service capability (§4.2) is a specific, purpose-built application of two more general AWS governance services worth understanding in their own right, since both extend well beyond account provisioning specifically.

- **AWS Service Catalog** is a general-purpose service for creating and managing a catalog of approved, self-service-provisionable "products" — pre-approved CloudFormation templates (Part 9 §1) for anything an organization wants to offer as a governed, self-service option, not only new accounts. A platform team can publish products for standard resource patterns (a pre-configured VPC, a standard RDS instance sizing, a compliant S3 bucket configuration) alongside the Account Factory product Control Tower itself publishes, giving requesters one consistent self-service experience across many different kinds of pre-approved infrastructure, not just accounts. Service Catalog's own access control (which users/roles can launch which products) is the same genuine governance decision §4.2's warning describes for account blueprints specifically — here generalized to any catalog product.
- **AWS Resource Access Manager (RAM)** is a distinct, complementary service for securely **sharing** AWS resources that already exist in one account with other accounts in an Organization, without duplicating those resources — a Transit Gateway (Part 4 §4), a subnet, a Lattice Service Network (Part 4 §6a), or a Lake Formation-governed Glue Catalog table (Part 11 §1-2) can each be shared via RAM to specific accounts or an entire OU, letting those accounts use the shared resource directly rather than each account provisioning and paying for its own separate copy.
- 🔑 **Key distinction:** Service Catalog governs _provisioning new instances_ of approved resource patterns (each requester gets their own new resource, created from a template); RAM governs _sharing already-existing_ resources across account boundaries (requesters use the _same_ underlying resource, not a new copy). Both are genuine self-service/governance mechanisms, but they solve opposite halves of the "how do multiple accounts get access to infrastructure without a central team manually provisioning or connecting everything by hand" problem — provisioning new (Service Catalog) versus reusing existing (RAM).
- Practical example tying both together: a central networking team provisions one Transit Gateway in a dedicated networking account, then uses **RAM** to share specific Transit Gateway attachments with every VPC-owning account across the Organization (avoiding N separate Transit Gateways) — while that same networking team could separately use **Service Catalog** to publish a "standard compliant VPC" product, letting application teams self-service-provision new, correctly-configured VPCs that then attach to the shared Transit Gateway. One resource is shared (the Transit Gateway, via RAM); the other is provisioned fresh per request (the VPC, via Service Catalog) — both governed, both self-service, solving genuinely different problems.

## 5. Lifecycle / Workflow

1. A central cloud/platform team defines one or more account blueprints, encoding baseline network configuration, identity access assignments, and target OU per account category.
2. Account Factory's self-service catalog is configured, specifying which blueprints are available and to which authorized requesters.
3. An authorized requester (a team, or an individual for a sandbox account) submits a request for a new account, selecting the appropriate blueprint for their need.
4. Account Factory provisions the new account automatically — creating it within AWS Organizations, placing it in the blueprint's target OU (immediately inheriting that OU's Control Tower guardrails, Part 13 §1), applying the baseline network configuration, and setting up identity access per the blueprint.
5. The requester receives access to a fully-configured, appropriately-governed account, typically within minutes rather than the days a manual process might have taken.
6. Over the account's lifecycle, its blueprint's baseline configuration can be updated to reflect evolving standards, and eventually, if no longer needed, the account is formally closed following a defined decommissioning process (§4.3).

## 6. Configuration

| Setting                                 | Purpose                                                                                                                                                                             |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Blueprint definitions                   | The baseline network, identity, and OU-placement configuration applied to accounts provisioned from a given blueprint.                                                              |
| Self-service catalog access permissions | Who is authorized to request new accounts, and which specific blueprints they can request from — a genuine access-control decision (§4.2's warning).                                |
| Account naming/tagging conventions      | Standardized identification of provisioned accounts, supporting the same cost-attribution and organizational-clarity goals established for resource tagging throughout this course. |

## 7. Commands / API (Full Documentation)

### 7.1 Provisioning a New Account via Account Factory

- **Purpose:** Create a new, blueprint-configured AWS account within the landing zone.
- **Syntax (via Service Catalog, which underlies Account Factory's self-service mechanism):**

```bash
aws servicecatalog provision-product \
  --product-name "AWS Control Tower Account Factory" \
  --provisioning-artifact-name "AWS Control Tower Account Factory" \
  --provisioned-product-name "payments-team-dev-account" \
  --provisioning-parameters Key=AccountEmail,Value=payments-dev@example.com \
                              Key=AccountName,Value=payments-team-dev \
                              Key=ManagedOrganizationalUnit,Value="Non-Production"
```

- **Important arguments:** `ManagedOrganizationalUnit` determines the account's OU placement — and therefore, per Part 13 §1 §4.2, which guardrails automatically apply. `AccountEmail`/`AccountName` follow standard AWS account creation requirements, now issued through this governed, blueprint-driven workflow rather than manual account creation.
- **Common errors:** requesting an OU placement the requester isn't actually authorized for (§4.2's warning) — this should be prevented by the self-service catalog's own access control, not merely by convention; specifying an account email already in use elsewhere (a standard AWS account-creation constraint, unrelated to Control Tower specifically).
- **Production usage:** in practice, most organizations expose this underlying API through a simpler internal request form or a chat-based workflow (Part 9 §8's GitOps/pipeline-triggered patterns are a reasonable analog) rather than requiring requesters to construct this API call directly — the API itself is more commonly what a platform team's own tooling calls under the hood.

## 8. Hands-On Example — Self-Service Sandbox Provisioning

```text
1. New engineer joins the payments team, needs a personal sandbox
   account for experimentation

2. Engineer requests a "Sandbox" blueprint account via the internal
   self-service portal (built on Account Factory / Service Catalog)

3. Account Factory automatically:
   - Creates a new AWS account
   - Places it in the Sandbox OU (Part 13 §1 §8's example structure) --
     inheriting permissive-but-isolated, cost-capped guardrails
   - Configures baseline VPC/subnet setup
   - Grants the engineer's IAM Identity Center identity appropriate
     access to this specific new account

4. Within minutes, the engineer has a working, appropriately-governed
   sandbox account -- no manual cloud-team involvement required, and
   no risk of the account being misconfigured relative to every other
   Sandbox OU account, since the same blueprint governs all of them
```

This demonstrates directly how self-service provisioning (§4.2) resolves the exact "slow, centrally-bottlenecked, inconsistency-risking manual process" problem named in §2 — fast for the requester, and consistently governed by construction, not by manual diligence.

## 9. Production and Enterprise Usage

- Organizations with Control Tower landing zones commonly define a small number of standard blueprints (e.g., "standard production workload account," "standard non-production account," "sandbox account") covering the large majority of account requests, reserving custom, one-off account configuration for genuinely unusual cases rather than a bespoke blueprint per team.
- Self-service account provisioning is a common enabler of platform-team scaling — as an organization grows, a central cloud team manually provisioning every new account for every team becomes an increasingly unsustainable bottleneck; self-service (with appropriate access control, §4.2) lets that team's capacity scale with the organization rather than becoming a hard constraint on how quickly new teams/projects can get properly-governed AWS access.
- Account decommissioning (§4.3) is an increasingly emphasized part of mature account-lifecycle management, given how easily a temporary or project-specific account can otherwise be forgotten and left running indefinitely, representing both unnecessary cost and an unmonitored security surface.

## 10. Security Considerations

- Self-service catalog access control (§4.2's warning) is the primary security lever specific to this section — restricting who can provision accounts, and via which blueprints, prevents self-service from becoming an unintended path to bypassing intended governance (e.g., an unauthorized requester somehow provisioning a production-OU account with weaker controls than intended).
- Because every account provisioned through Account Factory automatically inherits its target OU's guardrails (Part 13 §1), the security guarantee established there — including preventive SCP-based guardrails' unbypassable-ceiling property — extends automatically to every newly self-service-provisioned account, without depending on the requester (who may not be a security specialist) to correctly configure security controls themselves.
- Abandoned, non-decommissioned accounts (§4.3) represent a genuine, easily-overlooked security surface — periodic account inventory review (similar in spirit to the periodic IAM access reviews established in Part 2 §1) should include checking for accounts that are no longer actively used and should be formally closed.

## 11. Performance Considerations

- Account provisioning time (from request to a usable, fully-configured account) is the primary "performance" metric relevant to this section — self-service automation typically reduces this from a multi-day manual process to minutes, directly improving developer/team velocity for legitimate new-account needs.
- Blueprint complexity (how much baseline configuration a blueprint applies) trades off against provisioning speed — a blueprint provisioning extensive baseline infrastructure takes longer to complete than a minimal one, a genuine design consideration when defining blueprints for different account categories.

## 12. Monitoring

- Control Tower's landing-zone-wide compliance dashboard (Part 13 §1 §12) extends naturally to newly-provisioned accounts, since they inherit guardrails immediately upon creation — no separate monitoring setup is needed specifically for Account-Factory-provisioned accounts beyond the landing zone's existing compliance visibility.
- Account provisioning activity itself (who requested which blueprint, when, and for what OU) should be logged and periodically reviewed — CloudTrail (Part 8 §5) captures the underlying Service Catalog/Control Tower API activity, providing this audit trail.

## 13. Troubleshooting

| Symptom                                                                      | Cause                                                                                                                  | Fix                                                                                                             |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Self-service account request fails                                           | Requester lacks Service Catalog access to the requested blueprint, or a naming/email conflict with an existing account | Verify the requester's self-service catalog permissions; check for account-identifier conflicts                 |
| Newly-provisioned account is missing expected baseline configuration         | Blueprint definition doesn't include the expected configuration, or an outdated blueprint version was used             | Review and update the blueprint definition; verify which blueprint version was actually applied                 |
| An account exists in the landing zone that nobody seems to be actively using | Account wasn't formally decommissioned after its original purpose ended                                                | Investigate ownership and usage; follow the formal account-closure process (§4.3) if genuinely no longer needed |

## 14. Best Practices

- Define a small number of standard, well-scoped blueprints covering the majority of account needs, reserving custom configuration for genuinely unusual cases.
- Restrict self-service catalog access deliberately — not every requester should be authorized for every blueprint/OU combination.
- Periodically review the landing zone's account inventory for abandoned, no-longer-needed accounts, and formally decommission them rather than leaving them running indefinitely.
- Version and update blueprints as organizational baseline standards evolve, applying updates to existing accounts where feasible rather than only new provisions.

## 15. Anti-Patterns and Common Mistakes

- ❌ Continuing to provision new accounts manually even after Control Tower/Account Factory is available, reintroducing exactly the consistency risk and manual-effort burden the service exists to remove.
- ❌ Granting broad, unrestricted self-service provisioning access to every requester regardless of blueprint/OU sensitivity, undermining the governance guarantees the blueprint mechanism is meant to provide.
- ❌ Leaving temporary or project-specific accounts running indefinitely after their original purpose has ended, rather than following a formal decommissioning process.
- ❌ Defining an excessive number of highly-customized, one-off blueprints rather than a small, well-designed standard set — undermining the consistency and simplicity benefit blueprints are meant to provide.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"What does Account Factory actually automate?"_
**Model answer:** It automates the process of creating a new AWS account within a Control Tower-managed landing zone — applying a defined blueprint's baseline network configuration, identity access setup, and OU placement automatically, so every new account is consistently configured and immediately governed by its OU's guardrails, rather than someone manually setting all of that up by hand for every new account.

**🎯 Intermediate:** _"Why does self-service account provisioning still need access control, rather than being open to any authorized employee?"_
**Model answer:** Self-service provisioning determines an account's resulting configuration entirely through whichever blueprint is used — but different blueprints can target different OUs with meaningfully different guardrail strictness, for example a Sandbox OU's permissive guardrails versus a Production OU's much stricter ones. Without access control over who can request which blueprint, an unauthorized requester could potentially provision an account into a sensitive OU, or with a blueprint intended for a different purpose than theirs — self-service should make legitimate requests fast and consistent, not remove the underlying governance decision of who's actually authorized to create what kind of account.

**🎯 Senior:** _"Your organization's central platform team has become a bottleneck — new account requests take two weeks to fulfill, and teams are increasingly frustrated. How would Account Factory address this, and what would you need to set up first?"_
**Model answer:** Account Factory's self-service model directly targets this exact bottleneck — instead of every request requiring the platform team's manual, individual attention, teams can request accounts against pre-defined, pre-approved blueprints and get a fully-configured account within minutes. Before enabling this, though, I'd need the platform team to actually define the blueprints covering the common account request patterns they're currently fulfilling manually — reviewing what a "typical" account request looks like today and encoding that as one or a small number of standard blueprints — and establish the self-service catalog's access control, deciding which teams/roles are authorized to request which blueprints. This shifts the platform team's ongoing work from manually fulfilling every individual request to maintaining and evolving a smaller set of well-designed blueprints and access policies — a more scalable model as the organization continues to grow, directly addressing the bottleneck without sacrificing the governance consistency the platform team's manual process was presumably also providing.

**🎯 Architect:** _"Design an account-lifecycle governance process for a large organization using self-service Account Factory extensively, ensuring accounts don't accumulate indefinitely as 'zombie' accounts long after their original purpose has ended."_
**Model answer:** Establish a mandatory account-metadata requirement at provisioning time — every self-service account request must specify an owning team, a stated purpose, and, for genuinely temporary-purpose accounts (a time-boxed project, a proof-of-concept), an expected end date — captured as account tags following this course's established tagging-discipline principles. Implement a recurring (e.g., quarterly) automated review process — likely a Lambda function or Step Functions workflow (Part 7) querying account metadata/tags across the Organization — flagging any account past its stated expected end date, or any account showing minimal actual usage/activity (via CloudTrail activity levels or billing data) despite no formal end date, for owner confirmation: still needed, or ready for decommissioning. For accounts confirmed as no longer needed, follow the formal Account Factory closure process (§4.3) rather than simply leaving them dormant. For accounts an owner fails to respond about after a defined escalation period (a genuine organizational-process design point, not purely technical), escalate to the account's OU-level owner or the central platform team for a final decision — ensuring the review process has a defined resolution path rather than indefinitely accumulating unconfirmed accounts in limbo. This directly prevents the "zombie account" accumulation risk that scaling self-service provisioning (without a corresponding lifecycle-management discipline) would otherwise create, since making account _creation_ fast and easy, without an equally deliberate process for account _retirement_, predictably leads to exactly this problem over time.

## 17. Common Misconceptions

- "Self-service account provisioning means giving up governance control." False — as this section establishes, blueprints ensure every self-service-provisioned account is exactly as governed as a manually-provisioned one; the speed benefit doesn't trade away consistency, provided the self-service catalog's own access control is itself properly configured.
- "Account Factory only matters for very large organizations." Understated as a limitation — even a moderately-sized organization benefits from the consistency guarantee blueprints provide, since manual account setup inconsistency risk isn't purely a function of organization size, though the bottleneck-relief benefit (§9, Senior answer) does scale with request volume specifically.
- "Once an account is provisioned correctly, ongoing lifecycle management doesn't matter." False — as §4.3 and the Architect answer establish, account decommissioning is an equally important, often under-emphasized part of account lifecycle governance, not a one-time-setup-and-forget concern.

## 18. Key Takeaways

🔑 Account Factory automates account provisioning via defined blueprints, ensuring every new account — however it's requested — consistently inherits correct baseline configuration and OU-level guardrails (Part 13 §1).
🔑 Self-service provisioning resolves the manual-process bottleneck and consistency risk of ad hoc account creation simultaneously, provided the self-service catalog's own access control (who can request which blueprints) is deliberately configured.
🔑 Account blueprints encode baseline network, identity, and OU-placement configuration once, applied repeatably — the same "define once, apply consistently" discipline established for infrastructure as code (Part 9 §1-4) and CI/CD (Part 9 §8), now applied to account provisioning itself.
🔑 Account decommissioning deserves the same deliberateness as account creation — an abandoned, non-decommissioned account is a genuine, easily-overlooked cost and security surface.
🔑 A small number of well-designed standard blueprints, covering the majority of account needs, is preferable to a large number of highly-customized, one-off blueprints.

## 19. Related Concepts

- **AWS Control Tower and landing zone structure** (Part 13 §1) — the OU/guardrail foundation Account Factory provisions accounts into.
- **AWS Service Catalog and AWS Resource Access Manager** (see §4.4 above) — the general-purpose provisioning and resource-sharing mechanisms underlying Account Factory's self-service model, applicable well beyond account provisioning.
- **IAM Identity Center** (Part 2 §4) — the identity federation mechanism blueprints commonly configure for newly-provisioned accounts.
- **CI/CD for Infrastructure** (Part 9 §8) — the directly analogous "define once, apply consistently, self-service where appropriate" discipline this section applies to account provisioning specifically.
- **Centralized Logging & Audit Account Architecture** (Part 13 §3, next section) — the Log Archive/Audit account pattern every blueprint-provisioned account's logs ultimately feed into.
