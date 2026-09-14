# Part 8, Section 7: AWS Systems Manager

## 1. Definition

**Plain language:** Systems Manager is AWS's operational control plane for fleets of resources — instead of SSHing into individual EC2 instances one at a time to run a command, patch them, or check a configuration value, Systems Manager lets you do all of that centrally, across hundreds or thousands of instances at once, without ever opening an inbound SSH port.

**Precise definition:** AWS Systems Manager (SSM) is a management service providing a unified operational interface for viewing and controlling infrastructure on AWS and on-premises, comprising capabilities including Session Manager (browser/CLI-based shell access without SSH/bastion hosts), Run Command (ad hoc remote command execution at scale), Patch Manager (automated OS/software patching), State Manager (continuous configuration-state enforcement), Parameter Store (hierarchical configuration/secrets storage), and Automation (runbook-style orchestrated operational workflows).

## 2. Why It Exists / Problem It Solves

Managing a fleet of EC2 instances (or hybrid on-premises servers) the traditional way — SSH keys distributed to every engineer, bastion hosts as a single point of both access and risk, manually running the same patch command on every server one at a time, configuration drift because nobody has a systematic way to verify every instance still matches its intended state — is both operationally painful at any real scale and a persistent security liability (every open SSH port and distributed key is an attack surface).

Systems Manager solves this by providing **centralized, auditable, agent-based management** — an SSM Agent running on each managed instance communicates outbound to the Systems Manager service (no inbound ports needed at all), letting AWS-authenticated, IAM-permissioned operators run commands, check compliance, retrieve configuration, and patch software across an entire fleet from one console/API, with every action recorded (and visible in CloudTrail, [§73](./Section-73-Part8-CloudTrail-Audit-Governance.md)) rather than happening invisibly through an SSH session with no built-in audit trail.

## 3. Prerequisites and Dependencies

- **EC2** (Part 3): the primary managed-resource type; instances need the SSM Agent installed (present by default on most modern AMIs) and an IAM instance profile granting SSM permissions.
- **IAM** ([§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)): every SSM capability is IAM-governed — who can run commands, on which instances, is controlled by policy exactly like any other AWS action.
- **CloudTrail** ([§73](./Section-73-Part8-CloudTrail-Audit-Governance.md)): every SSM action is itself a recorded API call, directly reusable for auditing exactly what commands were run against which instances, by whom.

## 4. Internal Working

- The **SSM Agent**, installed on each managed instance, establishes an **outbound-only** connection to the Systems Manager service — this is the core architectural reason SSM eliminates the need for inbound SSH access or a bastion host: the instance calls out to AWS, rather than AWS (or an operator) calling in.
- **Session Manager** uses this same outbound channel to provide an interactive shell session directly in the browser console or via the AWS CLI, with every session's full command history optionally logged to S3/CloudWatch Logs — giving both the operational convenience of shell access and a complete audit trail neither raw SSH nor a bastion host provides by default.
- **Run Command** executes a specified command (or a pre-built or custom **SSM Document**, a JSON/YAML-defined action) against a targeted set of instances — targeting by explicit instance ID, or more powerfully, by **tags** (e.g., "run this against every instance tagged `environment=production`"), letting operational actions scale to fleets without per-instance manual work.
- **Patch Manager** automates OS and software patch scanning and installation, against **patch baselines** (rules defining which patches are approved, and after what delay following release — a common pattern: auto-approve security patches after 7 days, giving a window to catch any patch quality issues via AWS/vendor community reports before wide rollout) and **maintenance windows** (scheduled time periods when patching is permitted to run, avoiding patching during peak business hours).
- **State Manager** continuously (on a defined schedule) enforces a desired configuration state across managed instances — conceptually the EC2-instance-level analogue of CloudFormation's desired-state model ([§79](../Part9/Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)), but for the _contents/configuration_ of a running instance (e.g., "this specific software package must always be installed and this specific version") rather than the AWS resource itself.
- **Parameter Store** is a hierarchical key-value store for configuration data and secrets, supporting plain-text and KMS-encrypted **SecureString** parameters — a lighter-weight alternative to Secrets Manager for configuration values (with fewer built-in secret-rotation features but no additional service cost for standard parameters), commonly used for application configuration, feature flags, and simple credentials referenced by name from application code or other AWS services (including directly from CloudFormation/CDK/Terraform templates, Part 9).
- **Automation** runs **SSM Automation runbooks** — multi-step, potentially cross-service operational workflows (e.g., "create an AMI from this instance, launch a replacement, verify health, terminate the old instance") — the mechanism underlying many of AWS Config's automated remediation actions ([§74](./Section-74-Part8-AWS-Config.md)) referenced earlier in this Part.

```
Managed EC2 Instance (SSM Agent, outbound-only connection)
        │
        ▼
Systems Manager Service ──► Session Manager (interactive shell, no SSH/bastion)
        │              ──► Run Command (ad hoc commands/documents, fleet-wide via tags)
        │              ──► Patch Manager (baseline-driven patching, maintenance windows)
        │              ──► State Manager (continuous desired-state enforcement)
        │              ──► Automation (multi-step runbooks)
        │
Parameter Store (hierarchical config/secrets, referenced by name from anywhere)
```

## 5. Architecture & Components

| Component                                               | Explanation                                                                                                   |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **SSM Agent**                                           | Software running on each managed instance, maintaining the outbound connection to the SSM service.            |
| **Managed Instance**                                    | Any EC2 instance (or on-premises/hybrid server) with the SSM Agent installed and appropriate IAM permissions. |
| **Session Manager**                                     | Browser/CLI interactive shell access with no inbound ports and optional full session logging.                 |
| **Run Command**                                         | Ad hoc or scheduled remote command/document execution against tag- or ID-targeted instance sets.              |
| **SSM Document**                                        | A JSON/YAML-defined action (AWS-provided or custom) that Run Command, State Manager, or Automation executes.  |
| **Patch Manager / Patch Baseline / Maintenance Window** | Automated patching engine, its approval-rule configuration, and its scheduled execution window.               |
| **State Manager**                                       | Continuous, scheduled desired-configuration-state enforcement.                                                |
| **Parameter Store**                                     | Hierarchical configuration/secrets store, with plain-text and KMS-encrypted SecureString parameter types.     |
| **Automation Runbook**                                  | A multi-step, potentially cross-service orchestrated operational workflow.                                    |

## 6. Lifecycle / Workflow

1. **Ensure the SSM Agent** is present (default on most modern AMIs) and attach an IAM instance profile granting the managed instance the necessary SSM permissions (commonly via the AWS-managed `AmazonSSMManagedInstanceCore` policy).
2. The instance **registers** with Systems Manager and appears as a managed instance in the console/API.
3. Operators use **Session Manager** for interactive access, **Run Command** for one-off or scheduled fleet-wide actions, **Patch Manager** for patch compliance, and **State Manager** for ongoing configuration enforcement — each targeting instances by ID or tag.
4. **Parameter Store** values are created once and referenced by name from application code, other AWS services, or IaC templates wherever needed.
5. **Automation runbooks** are invoked (manually, on a schedule, or triggered by another service like Config's remediation actions) for multi-step operational workflows.
6. Every action is recorded in **CloudTrail**, and Session Manager sessions can additionally be logged in full to S3/CloudWatch Logs for detailed audit.

## 7. Configuration

| Setting                                                                    | Purpose                                                            |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| IAM instance profile (`AmazonSSMManagedInstanceCore` or scoped equivalent) | Grants the instance permission to communicate with the SSM service |
| Patch baseline approval rules                                              | Defines which patches are auto-approved and after what delay       |
| Maintenance window schedule                                                | When patching/automation is permitted to execute                   |
| Session Manager logging destination (S3/CloudWatch Logs)                   | Where full interactive session transcripts are stored for audit    |
| Parameter Store parameter type (`String`, `StringList`, `SecureString`)    | Determines whether the value is encrypted at rest via KMS          |

⚠️ **Warning:** Session Manager access is governed entirely by IAM — a role with `ssm:StartSession` permission on a target instance can open a shell on it, so this permission is exactly as sensitive as SSH key distribution was in the traditional model, and should be scoped and reviewed with the same rigor, not treated as inherently safer just because it doesn't require managing SSH keys.

## 8. Commands (Full Documentation)

### `aws ssm start-session`

- **Purpose:** Opens an interactive Session Manager shell session to a managed instance.
- **Syntax:**
  ```
  aws ssm start-session --target <instance-id>
  ```
- **Practical example:**
  ```
  aws ssm start-session --target i-0123456789abcdef0
  ```
  **Expected output:** an interactive shell session opens directly in the terminal, functioning like an SSH session but requiring no open inbound port, no SSH key, and no bastion host.
- **Production usage:** the standard, recommended replacement for SSH/bastion-host access in modern AWS environments, particularly valuable for instances in fully private subnets with no direct network path for SSH at all.
- **Common errors:** `TargetNotConnected` if the SSM Agent isn't running or the instance lacks the required IAM instance profile — the most common Session Manager troubleshooting step is verifying the instance actually appears as "Managed" in the Systems Manager console first.
- **Security impact:** requires `ssm:StartSession`, scoped ideally to specific instances/tags via IAM conditions rather than granted broadly; session logging (S3/CloudWatch Logs) should be enabled for any environment with audit requirements.

### `aws ssm send-command`

- **Purpose:** Executes a command or SSM Document against one or more targeted instances.
- **Syntax:**
  ```
  aws ssm send-command --document-name <document> --targets Key=tag:<key>,Values=<value> --parameters <JSON>
  ```
- **Practical example:**
  ```
  aws ssm send-command --document-name "AWS-RunShellScript" \
    --targets Key=tag:Environment,Values=production \
    --parameters commands=["df -h"]
  ```
  **Expected output:**
  ```json
  { "Command": { "CommandId": "8f14e45f-1234-...", "Status": "Pending" } }
  ```
- **Important arguments:** `--targets` using `Key=tag:...` rather than explicit instance IDs is what enables true fleet-wide, scale-independent operations — the same command runs against every currently-tagged instance regardless of how many there are.
- **Production usage:** commonly used for fleet-wide diagnostic commands, ad hoc operational tasks, and as the execution mechanism behind many custom automation scripts; results per-instance are retrievable via `get-command-invocation`.
- **Common errors:** a command succeeding on some targeted instances and failing on others is normal at scale (one instance might be temporarily disconnected) — always check per-instance invocation status rather than assuming a single overall success/failure.
- **Security impact:** requires `ssm:SendCommand`; the command itself runs with whatever OS-level permissions the SSM Agent process has (typically root/admin), so `ssm:SendCommand` permission is highly sensitive and should be tightly scoped.

### `aws ssm put-parameter`

- **Purpose:** Creates or updates a Parameter Store value.
- **Syntax:**
  ```
  aws ssm put-parameter --name <name> --value <value> --type <String|StringList|SecureString> [--key-id <kms-key-id>]
  ```
- **Practical example:**
  ```
  aws ssm put-parameter --name /myapp/production/db-connection-string \
    --value "postgres://..." --type SecureString
  ```
  **Expected output:**
  ```json
  { "Version": 1, "Tier": "Standard" }
  ```
- **Important arguments:** hierarchical naming (`/myapp/production/...`) is a widely-used convention enabling path-based retrieval of related parameters together (`get-parameters-by-path`), and enabling IAM policies scoped to a specific path prefix rather than individual parameter names.
- **Production usage:** frequently referenced directly from CloudFormation/CDK/Terraform templates (Part 9) as a dynamic parameter source, and from application startup code retrieving configuration at runtime rather than hardcoding values.
- **Common errors:** exceeding Parameter Store's Standard-tier size/throughput limits without upgrading to Advanced tier for larger-scale usage.
- **Security impact:** `SecureString` parameters are encrypted via KMS; access requires both `ssm:GetParameter` and `kms:Decrypt` permission on the associated key, giving genuine layered access control.

## 9. Hands-On Example — Fleet-Wide Patch Compliance Check and Remediation

```bash
# Define a patch baseline auto-approving security patches after a 7-day delay
aws ssm create-patch-baseline --name "ProductionBaseline" \
  --approval-rules 'PatchRules=[{PatchFilterGroup={PatchFilters=[{Key=CLASSIFICATION,Values=[SecurityUpdates]}]},ApproveAfterDays=7}]'

# Scan (report-only) patch compliance across all production instances
aws ssm send-command --document-name "AWS-RunPatchBaseline" \
  --targets Key=tag:Environment,Values=production \
  --parameters Operation=Scan

# Install missing patches during a defined maintenance window (executed automatically by the window's schedule)
aws ssm create-maintenance-window --name "WeeklyPatchWindow" \
  --schedule "cron(0 2 ? * SUN *)" --duration 3 --cutoff 1

# Retrieve a securely stored configuration value at application runtime
aws ssm get-parameter --name /myapp/production/db-connection-string --with-decryption
```

This demonstrates the standard pattern: define an approval policy once (the baseline), scan fleet-wide for compliance without yet making changes, then apply patches within a controlled, scheduled window — directly avoiding the anti-pattern of patching production instances at unpredictable times with no governing policy.

## 10. Production & Enterprise Usage

- **Startups** commonly adopt Session Manager early specifically to eliminate bastion-host operational overhead and SSH key management, even before adopting the more advanced patch/state-management capabilities.
- **Enterprises** build extensive Patch Manager and State Manager governance across large EC2 fleets, often tied directly into Config Rules ([§74](./Section-74-Part8-AWS-Config.md)) that check patch compliance status, and into the same organization-wide deployment patterns (StackSets, [§80](../Part9/Section-80-Part9-CloudFormation-Advanced.md)) for consistent baseline configuration across many accounts.
- Parameter Store is frequently the **lower-cost default** for application configuration, with Secrets Manager reserved specifically for credentials genuinely needing automatic rotation — a real, common cost/feature trade-off decision.
- SSM Automation runbooks are the underlying mechanism for many AWS Config automated remediation actions ([§74](./Section-74-Part8-AWS-Config.md)), directly connecting this section's content to that Part's compliance-automation discussion.

## 11. Security Considerations

- Session Manager's elimination of inbound SSH ports is a genuine security improvement (reduced network attack surface), but `ssm:StartSession` IAM permission itself becomes the new access-control boundary requiring the same careful scoping SSH key distribution once required.
- Session logging to S3/CloudWatch Logs provides audit visibility SSH sessions traditionally lack, directly supporting the same investigative patterns covered in [§73](./Section-73-Part8-CloudTrail-Audit-Governance.md) (CloudTrail) and [§75](./Section-75-Part8-Systems-Manager.md)'s own action logging.
- SecureString Parameter Store values require both SSM read permission and KMS decrypt permission — a genuine layered access control, but one that must be deliberately configured (defaulting to plain `String` type provides no encryption at all).

## 12. Performance Considerations

- Run Command and Patch Manager operations scale naturally to large fleets via tag-based targeting, with AWS managing the underlying fan-out — no custom scripting needed to iterate across hundreds of instances.
- Maintenance windows should be sized with realistic patch-installation duration in mind; an undersized window can leave patching incomplete across a large fleet, silently rolling over compliance gaps to the next scheduled window.

## 13. Monitoring

| Signal                                        | What it tells you                                                                                                                                          |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Managed instance "Ping Status"                | Whether an instance's SSM Agent is actively communicating — a "ConnectionLost" status is the first sign of an instance that's become unmanageable via SSM. |
| Patch compliance summary (per instance/fleet) | Current patch state versus the defined baseline — directly feeds Config Rules or dashboards tracking fleet-wide patch posture.                             |
| Run Command / Automation execution history    | Per-invocation success/failure detail, the primary troubleshooting signal for a specific failed fleet-wide operation.                                      |

## 14. Troubleshooting

| Symptom                                                              | Likely Root Cause                                                                                                          | Fix                                                                                                            |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Instance doesn't appear as "Managed"                                 | Missing/misconfigured IAM instance profile, or SSM Agent not running/outdated                                              | Verify the instance profile grants SSM permissions and the agent is running; update the agent if very outdated |
| Session Manager connection fails                                     | Instance not registered, or required VPC endpoint/internet path for SSM communication missing in a private-subnet instance | Verify managed status; for fully private subnets with no NAT, ensure SSM VPC endpoints are configured          |
| Run Command succeeds on some instances, fails on others              | Normal at scale — transient connectivity, instance-specific state differences                                              | Check per-instance invocation detail rather than assuming a uniform fleet-wide result                          |
| Patch Manager reports non-compliance that manual inspection disputes | Patch baseline scan is stale, or baseline approval rules don't match the actual expected patch set                         | Re-run a scan; review baseline approval-rule configuration against actual policy intent                        |

## 15. Best Practices

- Adopt Session Manager as the default EC2 access method, retiring bastion hosts and broadly-distributed SSH keys where feasible.
- Scope `ssm:StartSession` and `ssm:SendCommand` IAM permissions tightly, per environment/tag, exactly as sensitively as SSH access was once treated.
- Enable Session Manager logging for any environment with audit or compliance requirements.
- Use tag-based targeting for Run Command/Patch Manager/State Manager operations rather than maintaining manual instance-ID lists.
- Use Parameter Store as the default for general configuration, reserving Secrets Manager specifically for credentials needing automatic rotation.

## 16. Anti-Patterns & Common Mistakes

- ❌ Granting broad, unscoped `ssm:StartSession`/`ssm:SendCommand` permissions, treating SSM access as inherently safer than SSH simply because it doesn't require key management — the IAM permission itself is the equivalent sensitive boundary.
- ❌ Running Patch Manager installations with no defined maintenance window, risking mid-business-hours disruption from an unplanned patch/reboot cycle.
- ❌ Storing genuinely sensitive credentials as plain `String` Parameter Store values instead of `SecureString`, leaving them unencrypted and visible to anyone with basic read permission.
- **Common misconception:** "Systems Manager is just for patching." False — patching (Patch Manager) is one of several distinct capabilities; Session Manager (access), Run Command (ad hoc fleet operations), State Manager (configuration enforcement), Parameter Store (configuration/secrets), and Automation (orchestrated runbooks) are each independently valuable.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What is AWS Systems Manager, and what problem does Session Manager specifically solve?"_
**Model answer:** Systems Manager is AWS's operational management service for fleets of EC2 (and hybrid) instances — running commands, patching, enforcing configuration, and storing configuration data centrally rather than doing it manually per instance. Session Manager specifically solves the problem of needing SSH access without opening inbound SSH ports or managing bastion hosts and distributed SSH keys — it uses the SSM Agent's outbound-only connection to give an interactive shell directly through the AWS console or CLI, with the option to fully log every session for audit purposes.

**🎯 Intermediate:** _"Explain how tag-based targeting in Run Command lets an operational action scale independently of fleet size."_
**Model answer:** Instead of specifying a list of explicit instance IDs, which would need to be manually updated every time instances are added or removed, Run Command can target instances by tag — for example, every instance tagged Environment=production. This means the same command definition automatically applies to however many instances currently carry that tag, whether that's five or five thousand, without any change to the command itself. It also means routine fleet growth doesn't require remembering to update some separate operational target list, since the tag is the only thing that needs to be correctly applied when an instance is created.

**🎯 Senior:** _"Your organization wants to move away from SSH-key-based EC2 access to Session Manager, but the security team is concerned this could actually reduce auditability compared to traditional SSH with a bastion host's own logging. How would you address this?"_
**Model answer:** The concern is addressable but requires deliberate configuration, not just flipping to Session Manager by default — Session Manager supports full session logging to S3 and/or CloudWatch Logs, capturing the complete command history of every interactive session, which in practice is often more complete and centrally queryable than typical bastion-host SSH logging, which frequently only captures connection metadata rather than the actual commands run inside the session. I'd configure session logging as a mandatory requirement before rolling out Session Manager broadly, verify the logs are actually being captured correctly during a pilot phase, and demonstrate to the security team specifically how a Session Manager transcript compares favorably in completeness to what SSH logging was actually providing — addressing the concern with concrete evidence rather than just asserting Session Manager is more secure.

**🎯 Architect:** _"Design a patching strategy for a 2,000-instance fleet spanning multiple environments (dev, staging, production), balancing patch currency (security) against deployment risk (accidental service disruption from an unexpected patch side effect)."_
**Model answer:** I'd use separate patch baselines per environment with different approval-delay windows — dev might auto-approve security patches almost immediately to surface any patch-quality issues as early as possible, staging with a moderate delay (a few days) acting as a genuine pre-production canary, and production with the longest delay (a week or more), specifically so any patch-quality problems have already surfaced and been caught in dev/staging before reaching production. I'd define maintenance windows scoped to each environment's actual low-traffic period, and use tag-based targeting so the fleet's environment tag alone determines which baseline and window applies, requiring no manual per-instance patch-list maintenance as the fleet grows or changes. I'd also integrate Patch Manager's compliance reporting with a Config Rule ([§74](./Section-74-Part8-AWS-Config.md)) alerting when instances fall meaningfully behind their baseline's expected patch level, giving an independent, automated check that the patching pipeline itself is actually working as intended, rather than only trusting Patch Manager's own self-reported success.

## 18. Common Misconceptions

- "Systems Manager requires you to install something separately from what's already on your instances." Mostly false — the SSM Agent is pre-installed on most modern Amazon-provided AMIs; the main additional requirement is the correct IAM instance profile.
- "Parameter Store and Secrets Manager are redundant, just pick one." False — Parameter Store is a lower-cost general configuration store; Secrets Manager adds automatic credential rotation and tighter secrets-specific integrations. Many organizations use both, for different purposes.

## 19. Key Takeaways

🔑 Systems Manager's SSM Agent uses an outbound-only connection, eliminating the need for inbound SSH ports or bastion hosts for instance access and management.
🔑 Session Manager, Run Command, Patch Manager, State Manager, Parameter Store, and Automation are distinct capabilities — SSM is not just a patching tool.
🔑 Tag-based targeting lets operational actions scale independently of fleet size, without manual instance-list maintenance.
🔑 `ssm:StartSession`/`ssm:SendCommand` IAM permissions are exactly as security-sensitive as SSH key distribution was, and should be scoped and monitored with equal rigor.
🔑 SSM Automation runbooks are the orchestration mechanism underlying many AWS Config automated remediation actions ([§74](./Section-74-Part8-AWS-Config.md)).

## 20. Related Concepts

- **EC2** (the primary managed-resource type) → Part 3.
- **IAM** (the permission model governing every SSM capability) → [§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md).
- **AWS Config** (remediation actions frequently implemented as SSM Automation runbooks) → [§74](./Section-74-Part8-AWS-Config.md).
- **Trusted Advisor & AWS Health Dashboard** (complementary operational-awareness tooling) → next section, [§76](./Section-76-Part8-TrustedAdvisor-HealthDashboard.md).
