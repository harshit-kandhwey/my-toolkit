# Part 9, Section 2: CloudFormation Advanced — Intrinsic Functions, Nested Stacks, StackSets, Drift Detection

## 1. Definition

**Plain language:** This section covers the CloudFormation features that turn basic templates (Part 9 §1) into genuinely production-scale infrastructure tooling: intrinsic functions (built-in template logic beyond static values), nested stacks and cross-stack references (composing reusable modules), StackSets (deploying one template consistently across many accounts/regions), and drift detection (catching manual changes that have silently diverged from the template).

**Precise definition:** These are advanced CloudFormation capabilities layered on the base template/stack model — intrinsic functions (`Ref`, `Fn::GetAtt`, `Fn::Sub`, `Fn::If`, and others) providing dynamic value resolution and conditional logic within templates; nested stacks and `Fn::ImportValue`/exports enabling template composition and cross-stack referencing; StackSets enabling centralized, consistent multi-account/multi-region deployment; and drift detection identifying divergence between a stack's template-defined state and its actual deployed resource state.

## 2. Why It Exists / Problem It Solves

Part 9 §1's basic template model — static resource definitions with simple parameter substitution — works for a single, standalone stack, but real infrastructure has needs the basic model doesn't address: templates need to reference values that only exist at deploy time (an auto-generated ARN, an account ID, a region), templates need to reuse common patterns (the same VPC setup across a dozen different application stacks) without copy-pasting the same resource definitions repeatedly, organizations need to deploy the same baseline infrastructure consistently across many AWS accounts (echoing the same pattern CloudTrail organization trails, Part 8 §5, and Config Conformance Packs, Part 8 §6, solve for their respective domains), and — critically — once infrastructure is IaC-managed, teams need a way to detect if someone has manually modified it outside the template, since that manual modification silently breaks the fundamental IaC guarantee that the template is the authoritative source of truth.

Intrinsic functions, nested stacks, StackSets, and drift detection each solve one of these specific gaps, together turning CloudFormation from "a way to create resources from a static file" into a genuinely composable, organization-scale infrastructure management system.

## 3. Prerequisites and Dependencies

- **Infrastructure as Code Fundamentals & CloudFormation Basics** (Part 9 §1): templates, stacks, change sets, and the SQS+Lambda example are assumed foundational knowledge.
- **AWS Organizations** concepts (referenced in Part 2 §5, Part 8 §5-6): StackSets' organization-wide deployment model directly parallels these previously covered multi-account patterns.

## 4. Internal Working

### Intrinsic Functions

- `!Ref` resolves to a resource's primary identifier (e.g., a queue's URL) or a parameter's value — the most basic and commonly used intrinsic function.
- `!GetAtt` retrieves a specific _attribute_ of a resource beyond its primary identifier (e.g., a queue's ARN, not just its URL) — already used extensively in Part 9 §1's example (`!GetAtt OrderDLQ.Arn`).
- `!Sub` performs string substitution, interpolating parameter/resource references into a larger string (e.g., building a resource name from an environment parameter) — also already used in Part 9 §1's example.
- `!If` (paired with a `Conditions` section) enables conditional resource creation or property values based on parameter values — e.g., "only create a certain resource if `Environment` equals `production`."
- `!ImportValue` retrieves a value another stack has explicitly `Export`-ed in its `Outputs` section — the mechanism behind cross-stack referencing, letting one stack consume a resource created by a completely separate stack (e.g., a shared VPC stack's subnet IDs consumed by many separate application stacks).

### Nested Stacks

- A **nested stack** is a stack created and managed _as a resource within_ a parent stack (`AWS::CloudFormation::Stack` resource type, pointing to another template file/URL) — letting a large infrastructure definition be composed from smaller, independently authored and reusable template modules (e.g., a "standard VPC" nested-stack template reused across many parent stacks) rather than one enormous, monolithic template.
- Nested stacks are still deployed and torn down as part of their parent stack's lifecycle — deleting the parent deletes the nested stacks too, unlike fully independent stacks connected only via `Fn::ImportValue`, which remain independent and must be managed/deleted separately.

### StackSets

- A **StackSet** defines a template deployed as a **consistent set of stack instances** across multiple target accounts and/or regions from a single, centrally managed definition — analogous in spirit to CloudTrail organization trails and Config Conformance Packs (both Part 8), but generalized to _any_ CloudFormation template, not a specific security/compliance-focused artifact.
- **Service-managed permissions** (StackSets integrated with AWS Organizations) allow automatic deployment to every account in an Organizational Unit, including new accounts as they're created — removing the need to manually add each new account to the StackSet's target list.
- StackSet updates propagate the same template change consistently across every target account/region, with configurable deployment concurrency/failure-tolerance settings controlling how aggressively the rollout proceeds and how it handles per-account failures.

### Drift Detection

- CloudFormation can compare a stack's actual, currently deployed resource configuration against what the template _says_ it should be, identifying any resource whose real-world state has diverged — this comparison is triggered on demand (or, in some setups, on a schedule), not continuously automatic.
- Drift is reported per-resource and per-property, showing exactly which specific properties differ between the template-defined and actual values — precise enough to inform whether the fix should be updating the template to match reality (if the manual change was actually correct/intentional) or reverting the resource back to match the template (if the manual change was a mistake).

```
Parent Stack
   |-- AWS::CloudFormation::Stack (Nested: VPC module)
   |-- AWS::CloudFormation::Stack (Nested: Shared IAM roles module)
   `-- Application resources referencing nested stack outputs via !GetAtt

StackSet "baseline-security-config"
   |-- Stack Instance -> Account A, us-east-1
   |-- Stack Instance -> Account B, us-east-1
   |-- Stack Instance -> Account C, eu-west-1
   `-- (new accounts auto-added via Organizations integration)

Drift Detection (on-demand):
   Template says: SecurityGroup ingress = [{port: 443, cidr: 10.0.0.0/8}]
   Actual state:  SecurityGroup ingress = [{port: 443, cidr: 10.0.0.0/8}, {port: 22, cidr: 0.0.0.0/0}]
   -> DRIFTED: unexpected extra ingress rule added manually
```

## 5. Architecture & Components

| Component                 | Explanation                                                                                                                                   |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Intrinsic Function**    | Built-in template functions (`Ref`, `Fn::GetAtt`, `Fn::Sub`, `Fn::If`, `Fn::ImportValue`, and others) for dynamic value resolution and logic. |
| **Condition**             | A named boolean expression (in the `Conditions` section) used with `Fn::If` to control conditional resource creation/properties.              |
| **Nested Stack**          | A stack created as a resource within a parent stack, enabling template composition and reuse.                                                 |
| **Cross-Stack Reference** | A value exported by one stack (`Outputs` + `Export`) and imported by another (`Fn::ImportValue`) — connecting independently managed stacks.   |
| **StackSet**              | A template deployed as consistent stack instances across multiple accounts/regions from one central definition.                               |
| **Stack Instance**        | One specific per-account, per-region deployment managed by a StackSet.                                                                        |
| **Drift Detection**       | The on-demand comparison of actual deployed resource state against template-defined state.                                                    |

## 6. Lifecycle / Workflow

1. **Author** reusable nested-stack template modules for common infrastructure patterns (VPC, shared IAM roles, standard logging setup).
2. **Compose** parent templates referencing these nested stacks, or use `Fn::ImportValue` to consume outputs from fully independent stacks.
3. For organization-wide baseline infrastructure, **define a StackSet** and configure its target accounts/OUs/regions (often via service-managed permissions for automatic new-account coverage).
4. **Deploy/update** the StackSet, with CloudFormation propagating the change across every target stack instance per the configured concurrency/failure-tolerance settings.
5. **Periodically run drift detection** (or trigger it after a suspected manual change) against stacks to identify divergence.
6. **Reconcile** detected drift — either by updating the template to reflect an intentional manual change, or by redeploying the template to revert an unintentional one.

## 7. Configuration

| Setting                         | Purpose                                                                                                                |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `Conditions` section + `Fn::If` | Enables environment-specific or conditional resource creation within a single template                                 |
| Nested stack `TemplateURL`      | Points a parent stack's nested-stack resource to the child template (typically an S3-hosted URL)                       |
| `Export`/`Fn::ImportValue` name | The identifier connecting an exporting stack's output to an importing stack's reference                                |
| StackSet deployment targets     | Specific account IDs, or an Organizational Unit for service-managed, auto-expanding coverage                           |
| StackSet operation preferences  | Max concurrent accounts, failure tolerance percentage — controlling rollout aggressiveness and blast radius on failure |

⚠️ **Warning:** an exported stack output (`Fn::ImportValue` target) **cannot be deleted or have its export removed while any other stack still imports it** — CloudFormation blocks this specifically to prevent breaking a dependent stack, which is a real, occasionally surprising operational constraint when trying to refactor or retire a foundational shared stack that other stacks still depend on.

## 8. Commands (Full Documentation)

### `aws cloudformation create-stack-set`

- **Purpose:** Defines a new StackSet for multi-account/multi-region deployment.
- **Syntax:**
  ```
  aws cloudformation create-stack-set --stack-set-name <name> --template-body file://<path> [--permission-model SERVICE_MANAGED]
  ```
- **Practical example:**
  ```
  aws cloudformation create-stack-set --stack-set-name baseline-security-config \
    --template-body file://baseline-config-rule.yaml \
    --permission-model SERVICE_MANAGED \
    --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false
  ```
  **Expected output:**
  ```json
  { "StackSetId": "baseline-security-config:8f14e45f-1234-..." }
  ```
- **Important arguments:** `--permission-model SERVICE_MANAGED` with `--auto-deployment Enabled=true` is what gives the "new accounts automatically get this baseline" behavior, integrating directly with AWS Organizations rather than requiring manual per-account target management.
- **Production usage:** the foundational mechanism behind organization-wide baseline infrastructure — security guardrails, standard logging/monitoring setup, required tagging enforcement — deployed once, centrally, rather than replicated manually per account.
- **Common errors:** `SERVICE_MANAGED` permission model requires the StackSet to be created from the Organizations management account (or a delegated administrator account) — attempting this from an arbitrary member account fails.
- **Security impact:** StackSets with broad organization-wide deployment scope are high-impact, high-blast-radius resources — the ability to create/modify them should be tightly restricted to a small, trusted set of identities.

### `aws cloudformation create-stack-instances`

- **Purpose:** Deploys (or updates target scope for) stack instances from an existing StackSet to specific accounts/regions.
- **Syntax:**
  ```
  aws cloudformation create-stack-instances --stack-set-name <name> --deployment-targets OrganizationalUnitIds=<ou-id> --regions <region1> <region2>
  ```
- **Practical example:**
  ```
  aws cloudformation create-stack-instances --stack-set-name baseline-security-config \
    --deployment-targets OrganizationalUnitIds=ou-abcd-12345678 \
    --regions us-east-1 eu-west-1 \
    --operation-preferences MaxConcurrentPercentage=25,FailureTolerancePercentage=10
  ```
  **Expected output:**
  ```json
  { "OperationId": "8f14e45f-1234-..." }
  ```
- **Important arguments:** `--operation-preferences` controls rollout safety — `MaxConcurrentPercentage=25` limits how many accounts are updated simultaneously (reducing blast radius if the template has an unexpected issue), while `FailureTolerancePercentage=10` allows a small percentage of per-account failures before halting the overall operation, rather than requiring 100% success or nothing.
- **Production usage:** these operation preferences are a genuine, deliberate safety mechanism for organization-wide changes — deploying to 25% of accounts at a time, verifying success, rather than a single all-at-once rollout across every account simultaneously.
- **Common errors:** insufficient permissions in target accounts (the service-managed permission model handles this automatically for Organizations-integrated StackSets, but self-managed permission models require manually pre-created IAM roles in every target account).

### `aws cloudformation detect-stack-drift` / `describe-stack-resource-drifts`

- **Purpose:** Initiates and retrieves drift detection results for a stack.
- **Syntax:**
  ```
  aws cloudformation detect-stack-drift --stack-name <name>
  aws cloudformation describe-stack-resource-drifts --stack-name <name>
  ```
- **Practical example:**
  ```
  aws cloudformation detect-stack-drift --stack-name order-processing-stack
  # (asynchronous; poll for completion, then:)
  aws cloudformation describe-stack-resource-drifts --stack-name order-processing-stack
  ```
  **Expected output:**
  ```json
  {
    "StackResourceDrifts": [
      {
        "LogicalResourceId": "OrderQueue",
        "StackResourceDriftStatus": "MODIFIED",
        "PropertyDifferences": [
          {
            "PropertyPath": "/VisibilityTimeout",
            "ExpectedValue": "60",
            "ActualValue": "120"
          }
        ]
      }
    ]
  }
  ```
- **Production usage:** run periodically (often scheduled) across an organization's stacks, or triggered specifically after a suspected unauthorized/manual change, as a genuine operational governance practice complementing the "don't manually modify IaC-managed resources" policy with actual verification.
- **Common errors:** drift detection is asynchronous — `detect-stack-drift` returns immediately with a detection ID; results must be polled separately, similar in pattern to CloudWatch Logs Insights' asynchronous query model (Part 8 §2).
- **Troubleshooting tip:** `PropertyDifferences` shows the exact expected-vs-actual values, immediately clarifying whether reconciliation means "update the template to match this intentional change" or "redeploy to revert this unintentional one."

## 9. Hands-On Example — Cross-Stack Reference and Conditional Resource Creation

```yaml
# shared-vpc-stack.yaml (deployed once, independently)
Resources:
  SharedVPC:
    Type: AWS::EC2::VPC
    Properties: {CidrBlock: 10.0.0.0/16}
Outputs:
  VpcId:
    Value: !Ref SharedVPC
    Export: {Name: SharedVpcId}

# application-stack.yaml (deployed separately, consuming the shared VPC)
Parameters:
  Environment:
    Type: String
    AllowedValues: [dev, production]
Conditions:
  IsProduction: !Equals [!Ref Environment, production]
Resources:
  AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      VpcId: !ImportValue SharedVpcId
      GroupDescription: Application security group
  ProductionOnlyBackupVault:
    Type: AWS::Backup::BackupVault
    Condition: IsProduction
    Properties:
      BackupVaultName: production-backups
```

This demonstrates both `Fn::ImportValue` (consuming the shared VPC's ID from a completely independent stack) and `Fn::If`-driven conditional resource creation (the backup vault only gets created at all when `Environment` equals `production`) — two genuinely common production patterns neither achievable with Part 9 §1's basic static-template model alone.

## 10. Production & Enterprise Usage

- **Startups** typically adopt nested stacks or cross-stack references once they notice the same infrastructure pattern (a VPC setup, a standard logging configuration) being copy-pasted across multiple templates — a natural refactoring trigger.
- **Enterprises** build extensive libraries of reusable nested-stack modules maintained by a central platform/infrastructure team, consumed by many product teams' application stacks, and use StackSets extensively for organization-wide security baselines, standard monitoring/alerting setup, and required tagging/governance enforcement — deployed and updated centrally, automatically covering new accounts as the organization grows.
- **Drift detection** is frequently built into scheduled compliance/governance checks (sometimes itself implemented as a Config custom rule or a scheduled Lambda, tying back to Part 8 §6's compliance framework) rather than only run reactively after a suspected issue.
- StackSets' operation-preference safety controls (gradual rollout percentage, failure tolerance) mirror the same "don't change everything at once" discipline seen in Part 7 §2's DLQ redrive throttling and Part 8's broader incident-response caution around aggressive, high-blast-radius changes.

## 11. Security Considerations

- StackSets with organization-wide, service-managed deployment scope represent significant blast radius — access to create/modify them should be as tightly restricted as the CloudTrail organization trail and Config Conformance Pack management discussed in Part 8.
- Cross-stack exports/imports create implicit dependencies between stacks that aren't always obvious from looking at an individual stack in isolation — worth documenting clearly, since an attempt to delete or significantly modify an exporting stack can unexpectedly fail (or, worse, if not properly protected, could break dependent stacks) if the dependency isn't well understood.
- Drift detection results can reveal security-relevant information (e.g., a security group that's drifted to allow broader access than intended) — worth treating drift findings with the same urgency as other security-relevant alerts, not merely as a code-hygiene concern.

## 12. Performance Considerations

- Nested stacks add a small amount of deployment orchestration overhead (each nested stack is itself a full stack operation) but generally improve overall maintainability enough to be well worth this modest cost for genuinely reusable patterns.
- StackSet operation-preference settings directly trade off deployment speed against blast-radius safety — a very low `MaxConcurrentPercentage` is safer but slower to fully roll out across a large number of accounts; tuning this deliberately based on the criticality and risk of the specific template matters.
- Drift detection itself queries live resource state, which has some latency/cost proportional to the number of resources in the stack — running it on a reasonable schedule (not excessively frequently) balances currency of drift information against overhead.

## 13. Monitoring

| Signal                                                             | What it tells you                                                                                                                |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Drift detection status/results (per stack, scheduled or on-demand) | Whether actual infrastructure state has diverged from the template — a genuine governance signal.                                |
| StackSet operation status (per deployment across accounts)         | Progress and per-account success/failure during a multi-account rollout.                                                         |
| CloudFormation stack events (from Part 9 §1)                       | Still the primary per-stack operational signal, applicable identically to nested stacks and individual StackSet stack instances. |

## 14. Troubleshooting

| Symptom                                                | Likely Root Cause                                                                                        | Fix                                                                                                                               |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Cannot delete/modify a stack's export                  | Another stack still imports that value via `Fn::ImportValue`                                             | Identify and update/remove the dependent stack's import first, or use `list-imports` to find all current consumers                |
| StackSet deployment stuck/failed in some accounts only | Target account permissions issue (for self-managed model) or an account-specific resource conflict/limit | Review the StackSet operation's per-account status detail for the specific failure reason                                         |
| Drift detection shows unexpected `MODIFIED` status     | A manual change was made outside the template (intentionally or not)                                     | Investigate via CloudTrail (Part 8 §5) to identify who/what made the change, then decide whether to update the template or revert |
| Nested stack fails to create, parent stack rolls back  | An error within the nested stack's own template/resources                                                | Check the nested stack's own stack events specifically, not just the parent's summary status                                      |

## 15. Best Practices

- Use nested stacks or nested-stack-equivalent modules (also achievable via CDK constructs, Part 9 §3) for genuinely reusable infrastructure patterns, rather than copy-pasting the same resource definitions across multiple templates.
- Use StackSets with service-managed permissions and Organizations integration for any baseline infrastructure that should automatically apply to new accounts.
- Configure StackSet operation preferences deliberately (gradual rollout, reasonable failure tolerance) rather than defaulting to "deploy everywhere immediately."
- Run drift detection on a regular schedule, not only reactively, and treat findings as actionable governance signals.
- Document cross-stack export/import dependencies clearly, since they're not always visible from a single stack's own definition.

## 16. Anti-Patterns & Common Mistakes

- ❌ Copy-pasting the same resource definitions (a VPC setup, a standard IAM role pattern) across many templates instead of extracting them into a reusable nested stack or module.
- ❌ Deploying a StackSet update to 100% of accounts simultaneously without gradual rollout, risking a widespread simultaneous failure if the template has an unexpected issue.
- ❌ Never running drift detection, discovering divergence only accidentally or during an incident, long after it occurred.
- **Common misconception:** "Nested stacks and cross-stack references (via Fn::ImportValue) are basically the same thing." False — nested stacks are lifecycle-bound to their parent (deleted together), while cross-stack references connect fully independent stacks that must each be managed and deleted separately, with CloudFormation actively preventing deletion of an exporting stack's value while dependents still import it.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What's the difference between `Ref` and `Fn::GetAtt` in a CloudFormation template?"_
**Model answer:** Ref returns a resource's primary identifier — for an SQS queue, that's its URL; for many resources, it's the resource's name or ID. Fn::GetAtt retrieves a specific additional attribute of a resource beyond that primary identifier — for an SQS queue, that would be something like its ARN, which Ref alone doesn't give you. So if you need the queue's ARN specifically, like to reference it in an IAM policy, you'd use Fn::GetAtt QueueName.Arn rather than just Ref.

**🎯 Intermediate:** _"Explain the difference between a nested stack and a cross-stack reference via Fn::ImportValue, and when you'd use each."_
**Model answer:** A nested stack is created as a resource within a parent stack and is fully lifecycle-bound to it — when the parent is deleted, the nested stack is deleted too, and they're deployed together as one coordinated operation. A cross-stack reference connects two fully independent stacks, where one exports a value in its Outputs and another imports it via Fn::ImportValue — each stack is still managed and deleted completely separately. Use a nested stack for a reusable component that's genuinely part of one larger, coordinated deployment, like a standard set of IAM roles specific to one application. Use a cross-stack reference for something like a shared VPC that many independent application stacks, deployed and managed by different teams at different times, all need to reference without being coupled to each other's lifecycle.

**🎯 Senior:** _"You need to roll out a new security group rule change via a StackSet across 150 accounts, and the change could plausibly cause issues in some edge-case account configurations you haven't fully tested. How would you approach this deployment?"_
**Model answer:** Use the StackSet operation preferences specifically to control blast radius — setting a low MaxConcurrentPercentage, maybe starting around 5-10%, so only a small number of accounts get the change initially, combined with a reasonable but not overly permissive FailureTolerancePercentage that would halt the rollout if more than a small number of those initial accounts fail. Also consider deploying first to a small, deliberately chosen subset of lower-risk, non-production accounts via explicit account targeting before expanding to the full 150-account, Organizations-wide scope, effectively creating a canary-style rollout on top of the StackSet's built-in gradual-percentage mechanism. Throughout the rollout, actively monitor the per-account operation status, and if any failures do occur in the early batches, pause and investigate the specific failure reason before allowing the rollout to continue to the remaining accounts, rather than letting the automated percentage-based rollout proceed unattended through a change with already-known uncertainty.

**🎯 Architect:** _"Design a system that would have caught a security group's ingress rule being manually broadened (bypassing your CloudFormation-managed configuration) within minutes of it happening, rather than discovering it days later during a routine audit."_
**Model answer:** Scheduled drift detection alone, even run frequently, introduces some inherent detection lag between when it last ran and when the change occurred. For near-real-time detection specifically, combine two things: first, a CloudTrail-based (Part 8 §5) CloudWatch Logs metric filter and alarm specifically on the security-group-modification API call, giving immediate notification the moment the change happens, independent of any CloudFormation-specific mechanism at all. Second, pair that with an AWS Config rule (Part 8 §6) evaluating security group ingress rules against the expected baseline on configuration-change-triggered evaluation, which would flag the resulting non-compliant state within minutes of the change as well, and could be wired to automated remediation to revert the change automatically for well-understood violations. CloudFormation's own drift detection is valuable as a periodic, template-specific reconciliation check, but for the sub-minutes detection speed this scenario is asking for, the CloudTrail-alarm-plus-Config-rule combination — both of which detect the underlying change independent of when CloudFormation's own drift detection happens to next run — is the more directly responsive architecture.

## 18. Common Misconceptions

- "Drift detection runs continuously and automatically." False — it's triggered on demand (or via a scheduled automation you build yourself); CloudFormation doesn't continuously watch for and report drift in real time on its own.
- "StackSets are just a bulk way to run create-stack many times." Partially false — while the effect resembles that, StackSets provide centralized, coordinated update management (gradual rollout controls, unified operation status, automatic new-account coverage via Organizations integration) that manually scripting many individual `create-stack`/`update-stack` calls wouldn't give as a coherent, managed operation.

## 19. Key Takeaways

🔑 Intrinsic functions (`Ref`, `Fn::GetAtt`, `Fn::Sub`, `Fn::If`, `Fn::ImportValue`) provide the dynamic value resolution and conditional logic basic static templates lack.
🔑 Nested stacks compose lifecycle-bound reusable modules; cross-stack references (`Fn::ImportValue`) connect fully independent stacks — a meaningfully different coupling model, not interchangeable terminology.
🔑 StackSets, especially with service-managed Organizations integration, are the mechanism for consistent, centrally-managed infrastructure across many accounts, with deliberate gradual-rollout safety controls.
🔑 Drift detection is on-demand, not automatically continuous — build scheduled or event-triggered automation around it for genuinely proactive governance.
🔑 For near-real-time detection of unauthorized changes, combine CloudTrail-based alarming with Config rules rather than relying on CloudFormation drift detection alone, given its on-demand nature.

## 20. Related Concepts

- **CloudFormation Fundamentals** (templates, stacks, change sets) → Part 9 §1.
- **AWS CDK** (an alternative, code-based way to generate CloudFormation templates, including similar composition patterns via constructs) → next section, Part 9 §3.
- **AWS Organizations, CloudTrail organization trails, Config Conformance Packs** (the same multi-account deployment/governance pattern StackSets generalizes) → Part 2 §5, Part 8 §5-6.
