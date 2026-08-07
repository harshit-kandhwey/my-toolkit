# Part 8, Section 6: AWS Config — Resource Compliance & Configuration History

## 1. Definition

**Plain language:** AWS Config answers yet another distinct question from what's covered so far: not "who did what" (CloudTrail) or "is my application healthy" (CloudWatch) or "why was this specific request slow" (X-Ray), but "what does my resource actually look like right now, how did it get that way, and does it comply with the rules I've defined?" Config continuously tracks the configuration state of your AWS resources over time and can automatically evaluate whether they comply with rules you define — like "every S3 bucket must have encryption enabled" — flagging violations as they occur.

**Precise definition:** AWS Config is a service that continuously records the configuration state of supported AWS resources, maintains a historical timeline of configuration changes for each resource, and evaluates resource configurations against defined compliance rules (managed or custom), providing both point-in-time and time-series visibility into resource configuration and compliance status across an account or organization.

## 2. Why It Exists / Problem It Solves

CloudTrail ([§73](./Section-73-Part8-CloudTrail-Audit-Governance.md)) tells you _that_ an API call happened — `ModifySecurityGroupRule` was called by user X at time Y. It does not, on its own, easily answer "what did the security group actually look like before and after that change" or "is this security group currently compliant with our 'no unrestricted inbound SSH' policy" — reconstructing configuration state from a sequence of API calls, and evaluating current state against a policy, are both meaningfully different problems than knowing an API call occurred.

AWS Config solves this by maintaining an actual **configuration snapshot timeline** per resource — not just "an API call happened" but "here is exactly what this resource's configuration looked like at this point in time, and here's what changed between this snapshot and the previous one" — plus a **rules engine** that continuously evaluates current (and, for some rule types, historical) configuration against defined compliance requirements, flagging non-compliant resources automatically rather than requiring someone to manually audit configurations.

**What existed before it (conceptually):** manual, periodic configuration audits (inherently point-in-time and quickly stale) or custom scripts polling resource APIs and diffing state — both far more labor-intensive and less reliable than Config's continuous, automatic tracking.

## 3. Prerequisites and Dependencies

- **CloudTrail** ([§73](./Section-73-Part8-CloudTrail-Audit-Governance.md)): complementary but distinct — Config is frequently discussed alongside CloudTrail specifically because they're commonly confused; understanding the "activity record" vs. "configuration state" distinction is foundational here.
- General familiarity with common AWS resource types (S3, EC2, security groups, IAM) whose configuration Config tracks, assumed from earlier Parts.
- **IAM** ([§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)): Config rules frequently evaluate IAM-related configuration (e.g., "no IAM user has console access without MFA") and Config itself operates via an IAM service role.

## 4. Internal Working

- Config maintains a **configuration item** for each tracked resource — a point-in-time snapshot capturing that resource's full configuration attributes, its relationships to other resources (e.g., an EC2 instance's relationship to its security groups and subnet), and relevant metadata.
- Whenever a tracked resource's configuration changes, Config records a **new configuration item**, building a chronological **configuration history** for that resource — letting you query "what did this security group look like on this specific date" or "show me every configuration change to this S3 bucket over the past six months."
- **Config Rules** are the compliance-evaluation mechanism — either **AWS Managed Rules** (a large library of pre-built, common compliance checks AWS maintains, like "s3-bucket-server-side-encryption-enabled" or "restricted-ssh") or **custom rules** (backed by a Lambda function containing your own organization-specific compliance logic) — each rule evaluates matching resources and marks them `COMPLIANT` or `NON_COMPLIANT`.
- Rules can be evaluated in different modes: **periodically** (on a defined schedule, regardless of whether anything changed) or **configuration-change-triggered** (re-evaluated automatically whenever the relevant resource's configuration actually changes) — the latter providing much faster detection of newly introduced non-compliance.
- **Conformance Packs** bundle a collection of related Config rules (plus, optionally, automated remediation actions) into a single deployable unit, often representing a specific compliance framework's requirements (e.g., a CIS benchmark conformance pack) — deployable consistently across many accounts.
- **Remediation actions** can be attached to a rule, letting Config not just detect non-compliance but automatically trigger a corrective action (often via Systems Manager Automation documents) — for example, automatically re-enabling encryption on a bucket found to have it disabled, closing the loop from detection to correction without requiring manual intervention.

```
Resource Configuration Change (e.g., security group rule modified)
              |
              v
    Config records new Configuration Item --> Configuration History (timeline, queryable)
              |
              v
    Config Rule Evaluation (Managed or Custom/Lambda-backed)
              |
      +-------+-------+
      v               v
  COMPLIANT      NON_COMPLIANT --> (optional) Automated Remediation Action
```

## 5. Architecture & Components

| Component                  | Explanation                                                                                                                                             |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Configuration Item**     | A point-in-time snapshot of one resource's configuration, attributes, and relationships.                                                                |
| **Configuration History**  | The chronological sequence of configuration items for a resource, enabling "what did this look like at time X" queries.                                 |
| **Configuration Recorder** | The Config component actively watching for and recording configuration changes across supported resource types in the account.                          |
| **Config Rule**            | A compliance check (AWS Managed or custom Lambda-backed) evaluating resources as `COMPLIANT`/`NON_COMPLIANT`.                                           |
| **Conformance Pack**       | A bundled, deployable collection of related Config rules (and optional remediations), often mapping to a specific compliance framework.                 |
| **Remediation Action**     | An automated corrective action (via Systems Manager Automation) triggered on `NON_COMPLIANT` findings.                                                  |
| **Aggregator**             | Combines Config data across multiple accounts/regions into a single, centralized view — the Config analogue to CloudTrail's organization trail concept. |

## 6. Lifecycle / Workflow

1. **Enable** the Config configuration recorder, specifying which resource types to track (or "all supported resource types," the common broad-coverage choice).
2. Config **continuously records** configuration items as tracked resources are created, modified, or deleted, building each resource's configuration history.
3. **Define/enable Config Rules** (Managed or custom) relevant to your compliance requirements.
4. Config **evaluates** resources against rules, either periodically or on configuration change, marking `COMPLIANT`/`NON_COMPLIANT`.
5. Non-compliant findings are surfaced via the Config dashboard, and optionally trigger **notifications** (via EventBridge, [§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md), which natively receives Config compliance change events) or **automated remediation**.
6. Engineers/auditors **query configuration history** for point-in-time or change-over-time investigation, independent of whether any rule violation was involved.

## 7. Configuration

| Setting                                                          | Purpose                                                                        |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Configuration Recorder resource-type scope                       | Which resource types are tracked — "all supported" is the common broad default |
| Config Rule selection (Managed/custom)                           | Which specific compliance checks are active                                    |
| Rule evaluation trigger (periodic vs. configuration-change)      | How quickly non-compliance is detected after it's introduced                   |
| Remediation action association                                   | Whether/how a rule's non-compliant findings trigger automatic correction       |
| Aggregator configuration                                         | Cross-account/region centralized visibility                                    |
| Delivery channel (S3 bucket for configuration snapshots/history) | Durable long-term storage of configuration data                                |

⚠️ **Warning:** Config Rules detect and report non-compliance — they do not, by themselves, _prevent_ a non-compliant configuration from being created in the first place (that's the domain of preventive controls like IAM policy conditions or Service Control Policies, generally covered under broader governance topics beyond this section). Config is fundamentally a **detective** control; pairing it with genuinely preventive controls is necessary for defense-in-depth, not an either/or substitute.

## 8. Commands (Full Documentation)

### `aws configservice put-configuration-recorder` / `start-configuration-recorder`

- **Purpose:** Sets up and starts Config's core resource-tracking capability.
- **Syntax:**
  ```
  aws configservice put-configuration-recorder --configuration-recorder <JSON>
  aws configservice start-configuration-recorder --configuration-recorder-name <name>
  ```
- **Practical example:**
  ```
  aws configservice put-configuration-recorder --configuration-recorder '{
    "name": "default",
    "roleARN": "arn:aws:iam::123456789012:role/ConfigRole",
    "recordingGroup": {"allSupported": true, "includeGlobalResourceTypes": true}
  }'
  aws configservice start-configuration-recorder --configuration-recorder-name default
  ```
  **Expected output:** (empty on success for both)
- **Important arguments:** `allSupported: true` tracks every resource type Config supports, the common broad-coverage default; `includeGlobalResourceTypes: true` ensures global resources like IAM (which aren't region-specific) are tracked, typically enabled in only one region per account to avoid redundant duplicate tracking.
- **Production usage:** set up once per account (or centrally via an organization-wide Config setup, analogous to CloudTrail's organization trail) as foundational governance infrastructure, typically via CloudFormation/Terraform.
- **Common errors:** the specified `roleARN` needs specific Config-related permissions (commonly via the AWS-managed `AWS_ConfigRole` policy) — an under-permissioned role prevents Config from actually reading resource configurations.
- **Security impact:** Config's own service role needs broad read access across many resource types to do its job — a legitimate, expected permission scope for this specific service role, distinct from over-permissioning a typical application role.

### `aws configservice put-config-rule`

- **Purpose:** Creates or updates a compliance rule.
- **Syntax:**
  ```
  aws configservice put-config-rule --config-rule <JSON>
  ```
- **Practical example (AWS Managed Rule):**
  ```
  aws configservice put-config-rule --config-rule '{
    "ConfigRuleName": "s3-bucket-encryption-enabled",
    "Source": {"Owner": "AWS", "SourceIdentifier": "S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED"}
  }'
  ```
  **Expected output:** (empty on success)
- **Production usage:** enterprises typically deploy a curated set of Managed Rules (or a full Conformance Pack) covering their specific compliance framework requirements, plus custom Lambda-backed rules for organization-specific policies AWS's managed library doesn't cover (e.g., "every resource must have a specific set of required cost-allocation tags").
- **Common errors:** custom rules backed by a Lambda function require that Lambda to correctly implement Config's expected evaluation-result response format — a malformed response leaves the rule perpetually showing no evaluation result rather than a clear pass/fail.
- **Security impact:** requires `config:PutConfigRule`; a low-risk administrative action, though the resulting compliance data itself (revealing which resources violate policy) is worth scoping read access to appropriately.

### `aws configservice get-resource-config-history`

- **Purpose:** Retrieves the configuration history timeline for a specific resource — the primary "what did this look like over time" investigative operation.
- **Syntax:**
  ```
  aws configservice get-resource-config-history --resource-type <type> --resource-id <id>
  ```
- **Practical example:**
  ```
  aws configservice get-resource-config-history --resource-type AWS::EC2::SecurityGroup --resource-id sg-0123456789abcdef0
  ```
  **Expected output:**
  ```json
  {
    "configurationItems": [
      {
        "configurationItemCaptureTime": "2026-07-19T14:22:00Z",
        "configuration": {
          "ipPermissions": [
            {
              "fromPort": 22,
              "toPort": 22,
              "ipRanges": [{ "cidrIp": "0.0.0.0/0" }]
            }
          ]
        }
      }
    ]
  }
  ```
- **Production usage:** the standard operation for reconstructing "what did this resource's configuration look like before/after a specific change" during an incident investigation or audit, frequently used alongside a corresponding CloudTrail lookup for the _identity_ that made the change (Config shows _what_ changed; CloudTrail shows _who_ changed it — genuinely complementary, not overlapping).
- **Common errors:** querying a resource type/ID combination that either isn't tracked (not in the recorder's scope) or never existed under Config's tracking window returns empty/no history.

## 9. Hands-On Example — Combining Config History with CloudTrail for Full Investigation

```bash
# Step 1: Config shows exactly what the security group's configuration was before and after a change
aws configservice get-resource-config-history \
  --resource-type AWS::EC2::SecurityGroup --resource-id sg-0123456789abcdef0

# Step 2: CloudTrail shows exactly who made that specific change and from where
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=sg-0123456789abcdef0 \
  --start-time 2026-07-19T00:00:00Z --end-time 2026-07-20T00:00:00Z
```

This two-step pattern — Config for "what changed" (the before/after configuration state), CloudTrail for "who changed it" (the actor, source, and exact API call) — is the standard, complementary investigative combination referenced throughout both sections; neither service alone gives the complete picture.

**Custom Config Rule example (Lambda-backed, checking for a required tag):**

```python
import boto3
import json

def lambda_handler(event, context):
    config_client = boto3.client('config')
    invoking_event = json.loads(event['invokingEvent'])
    configuration_item = invoking_event['configurationItem']

    tags = configuration_item.get('tags', {})
    compliance_type = 'COMPLIANT' if 'CostCenter' in tags else 'NON_COMPLIANT'

    config_client.put_evaluations(
        Evaluations=[{
            'ComplianceResourceType': configuration_item['resourceType'],
            'ComplianceResourceId': configuration_item['resourceId'],
            'ComplianceType': compliance_type,
            'OrderingTimestamp': configuration_item['configurationItemCaptureTime']
        }],
        ResultToken=event['resultToken']
    )
```

This demonstrates the custom-rule pattern for an organization-specific policy (every resource requires a `CostCenter` tag) that no AWS Managed Rule would cover, since it's specific to this organization's own governance requirements rather than a general AWS best practice.

## 10. Production & Enterprise Usage

- **Startups** rarely invest heavily in Config initially, though enabling it broadly with a handful of high-value Managed Rules (encryption enabled, no public S3 buckets, no unrestricted security group ingress) is a low-effort, high-value early security baseline.
- **Enterprises** deploy Conformance Packs mapping directly to required compliance frameworks (CIS AWS Foundations Benchmark, PCI-DSS, HIPAA-related controls), often via an organization-wide Config setup with a central Aggregator providing unified compliance visibility across every account, and pair non-compliance detection with automated remediation for well-understood, safe-to-auto-correct violations.
- Config data is a common input to security posture/compliance dashboards and to periodic formal compliance audits, where "show me evidence that encryption has been continuously enabled on this resource for the audit period" is directly answerable via Config's configuration history rather than requiring a point-in-time manual check that can't speak to the historical period.
- **Change management/troubleshooting**: beyond pure compliance, Config's configuration history is a genuinely valuable operational troubleshooting tool independent of any compliance rule — "this resource started behaving unexpectedly Tuesday, show me every configuration change around that time" is a direct, common use case.

## 11. Security Considerations

- Config itself requires broad read access across many resource types to function — this is expected and legitimate for Config's service role specifically, but worth understanding as a deliberate, scoped exception to general least-privilege guidance for application roles.
- Config compliance data reveals which resources are currently non-compliant with security policies — genuinely sensitive information from an attacker's perspective (a roadmap of exploitable misconfigurations) — access should be scoped appropriately, not broadly granted.
- Automated remediation actions, while valuable, carry their own risk if misconfigured (an overly aggressive auto-remediation could disrupt a legitimate, intentional configuration) — remediation logic should be reviewed and tested carefully, particularly for anything beyond clearly safe, narrow corrections.

## 12. Performance Considerations

- Tracking "all supported resource types" across a very large, resource-dense account generates a correspondingly large volume of configuration items and associated cost — worth being aware of at significant scale, though generally a reasonable default starting point.
- Configuration-change-triggered rule evaluation (versus periodic) provides faster non-compliance detection but evaluates more frequently — a minor, generally acceptable overhead trade-off for the detection-speed benefit.

## 13. Monitoring

| Signal                                                  | What it tells you                                                                                                                                                                                                                                |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Config Rule compliance summary (per rule, per resource) | The current, real-time compliance posture across tracked resources — the primary Config dashboard view.                                                                                                                                          |
| EventBridge Config compliance change events             | Real-time notification when a resource's compliance status changes (native EventBridge integration, [§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md)), enabling immediate alerting or automated remediation triggering. |
| Configuration Recorder status                           | Whether Config is actively recording — analogous to CloudTrail's `IsLogging` health check, worth monitoring for the same "is my governance tooling actually working" reason.                                                                     |

## 14. Troubleshooting

| Symptom                                                           | Likely Root Cause                                                                                                 | Fix                                                                                                                       |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| A resource shows no configuration history                         | Resource type not in the recorder's tracked scope, or resource existed before Config was enabled                  | Verify recorder scope includes the resource type; historical data before Config enablement is unrecoverable               |
| Custom rule shows no evaluation result                            | Lambda function's response doesn't match Config's expected evaluation format, or the function is erroring         | Review the Lambda's CloudWatch Logs ([§70](./Section-70-Part8-CloudWatch-Logs.md)) for the custom rule's execution errors |
| Compliance status not updating after a known configuration change | Rule configured for periodic (not configuration-change-triggered) evaluation, so the update simply hasn't run yet | Switch to configuration-change-triggered evaluation for faster detection, or wait for the next periodic cycle             |
| Aggregator missing data from some accounts                        | Those accounts' Config wasn't properly authorized to share data with the aggregator account                       | Verify aggregator authorization is correctly configured in each source account                                            |

## 15. Best Practices

- Enable Config broadly ("all supported resource types") as a low-effort, high-value baseline, even before investing heavily in custom rules.
- Deploy Conformance Packs aligned with your actual required compliance framework(s) rather than building rule sets entirely from scratch.
- Use configuration-change-triggered evaluation for rules where fast non-compliance detection genuinely matters.
- Pair Config's detective capability with genuinely preventive controls (IAM conditions, Service Control Policies) rather than treating detection alone as sufficient governance.
- Use Config configuration history alongside CloudTrail during investigations — Config for "what changed," CloudTrail for "who changed it."

## 16. Anti-Patterns & Common Mistakes

- ❌ Treating Config Rules as preventive controls that stop non-compliant configurations from being created — they detect and report after the fact, not before.
- ❌ Enabling automated remediation broadly and aggressively without careful review, risking disruption of legitimate, intentional configurations that happen to trip a rule.
- ❌ Investigating "what changed" using only CloudTrail (which shows the API call) without also checking Config (which shows the actual resulting configuration state), missing the complementary half of the picture.
- **Common misconception:** "AWS Config and CloudTrail do the same thing." False — CloudTrail records that an API call happened and who made it; Config records what a resource's configuration actually looked like at any point in time and evaluates it against compliance rules. They're frequently used together specifically because they answer genuinely different, complementary questions.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What does AWS Config do, and how is it different from CloudTrail?"_
**Model answer:** AWS Config continuously tracks the actual configuration state of your AWS resources over time, letting you see exactly what a resource looked like at any past point and what changed between snapshots, and it can evaluate resources against compliance rules to flag violations automatically. CloudTrail, by contrast, records that specific API calls happened and who made them. The key difference is that CloudTrail tells you an action occurred, while Config tells you what a resource's configuration actually was as a result — they're complementary, and investigations often use both together: CloudTrail to find who made a change, Config to see exactly what that change resulted in.

**🎯 Intermediate:** _"Explain the difference between periodic and configuration-change-triggered Config Rule evaluation, and when you'd choose each."_
**Model answer:** Configuration-change-triggered evaluation re-checks a rule automatically whenever the relevant resource's configuration actually changes, giving fast detection of newly introduced non-compliance, often within minutes. Periodic evaluation instead runs on a fixed schedule regardless of whether anything changed, which is useful for rules that need to check something not strictly tied to a specific configuration change event, or where near-real-time detection isn't critical. For most security-sensitive rules — like detecting a newly opened, overly permissive security group rule — configuration-change-triggered evaluation is the better choice specifically because it minimizes the window between a non-compliant change being introduced and it being detected.

**🎯 Senior:** _"A Config rule flags an S3 bucket as non-compliant for missing encryption, but the team insists encryption was enabled last week and nobody disabled it. How would you investigate?"_
**Model answer:** Start by pulling that bucket's Config configuration history specifically around the time encryption is claimed to have been enabled, and trace forward to see exactly when, in the recorded configuration timeline, the encryption setting actually changed to disabled — Config's history should show the precise configuration item where that transition occurred, if it genuinely did occur. Once armed with that specific timestamp, cross-reference it against CloudTrail to identify exactly which API call and which identity made that change, since Config shows the what and CloudTrail shows the who. It's entirely possible the team is right that they didn't manually disable it — the change could have come from an automated process, a misconfigured IaC deployment that reset the setting, or a third-party integration with unexpected permissions — and this combined Config-plus-CloudTrail investigation is exactly how you'd distinguish between those possibilities with actual evidence rather than relying on anyone's memory of what they did or didn't do.

**🎯 Architect:** _"Design a governance architecture for a 200-account AWS Organization ensuring every account maintains baseline security compliance (encryption enabled, no public S3 buckets, MFA required for console access), with centralized visibility and where feasible, automatic correction of drift."_
**Model answer:** Deploy a Conformance Pack containing the relevant Managed Rules (S3 encryption, public-bucket restriction, MFA enforcement, and similar) across every account in the Organization, most practically via an organization-wide Config deployment mechanism so new accounts automatically inherit the same baseline rule set without manual per-account setup. Configure a central Aggregator in a dedicated governance/security account, pulling compliance data from every member account into one unified dashboard, giving centralized visibility without needing to check 200 accounts individually. For automatic correction specifically, be selective — rules with clearly safe, well-understood, low-risk remediation (like automatically re-enabling default encryption on a bucket found without it) would get automated remediation actions attached, while anything with a higher risk of disrupting a legitimate, intentional configuration would instead trigger a notification (via the native EventBridge compliance-change integration) to the responsible team for manual review, rather than blindly auto-correcting a configuration that might have been deliberately set that way for a business reason. This detective/corrective architecture should also be paired with preventive controls like Service Control Policies where feasible, since Config alone only detects after the fact — genuine defense-in-depth needs both layers working together.

## 18. Common Misconceptions

- "Config prevents non-compliant resources from being created." False — Config is a detective control, identifying non-compliance after the fact; preventing it in the first place requires separate preventive controls.
- "Config and CloudTrail are redundant; you only need one." False — they answer genuinely different questions (configuration state and history vs. API activity and identity) and are most powerful used together during investigations.

## 19. Key Takeaways

🔑 AWS Config tracks actual resource configuration state over time and evaluates it against compliance rules — a fundamentally different, complementary capability to CloudTrail's API-activity record.
🔑 Config Rules are detective, not preventive — they flag non-compliance after it occurs, and should be paired with genuinely preventive controls for real defense-in-depth.
🔑 Configuration-change-triggered evaluation provides much faster non-compliance detection than periodic evaluation, at minor additional evaluation overhead.
🔑 Config's configuration history plus CloudTrail's activity record together answer "what changed" and "who changed it" — the standard combined investigative pattern.
🔑 Conformance Packs and organization-wide deployment provide consistent, centrally-visible compliance baselines across large multi-account organizations.

## 20. Related Concepts

- **CloudTrail** (the complementary API-activity record, distinct from Config's configuration-state focus) → [§73](./Section-73-Part8-CloudTrail-Audit-Governance.md).
- **EventBridge** (native integration for real-time compliance-change notifications and automated remediation triggering) → [§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md).
- **IAM / Service Control Policies** (the preventive-control counterpart to Config's detective capability) — referenced here as a natural extension beyond this roadmap's current depth.
- **Systems Manager Automation** (the mechanism underlying Config's automated remediation actions) — a natural extension topic for anyone building out automated remediation.
