# Part 8, Section 8: Trusted Advisor & AWS Health Dashboard

## 1. Definition

**Plain language:** These are two distinct AWS "am I okay" services, easily confused but answering different questions. Trusted Advisor looks at _your own account's configuration_ and tells you where you're deviating from AWS best practices — an oversized instance, a wide-open security group, an unused Elastic IP. The Health Dashboard tells you about _AWS's own infrastructure status_ — is there a service outage right now, and specifically, is a particular AWS event actually affecting resources in your account.

**Precise definition:** AWS Trusted Advisor is an automated recommendation service that inspects your AWS account against best-practice checks across cost optimization, performance, security, fault tolerance, and service limits, producing prioritized findings. AWS Health Dashboard (comprising the public Service Health Dashboard and the account-specific Personal Health Dashboard) provides visibility into AWS service availability and, specifically for the personal/account-specific view, proactively surfaces events and scheduled changes that affect your specific provisioned resources.

## 2. Why It Exists / Problem It Solves

Two genuinely separate problems, addressed by two genuinely separate tools:

**Trusted Advisor's problem:** across a large, evolving AWS account, configuration drift and simple oversight accumulate — an idle load balancer nobody decommissioned, a security group rule far broader than intended, an S3 bucket with public access nobody meant to leave open. Manually auditing an entire account against every AWS best practice is impractical at any real scale; Trusted Advisor automates exactly this audit, continuously, across the specific dimensions AWS itself has identified as common, high-value checks.

**Health Dashboard's problem:** when something goes wrong during an incident, one of the first diagnostic questions is "is this us, or is this AWS?" — without a reliable, authoritative source for current AWS service status, this becomes guesswork based on social media reports or forum posts. Worse, even when AWS does have an issue, a generic "us-east-1 S3 experiencing elevated error rates" public status page doesn't tell you whether _your specific resources_ are actually affected — the Personal Health Dashboard closes this gap by correlating AWS-wide events against your account's actual resource inventory.

## 3. Prerequisites and Dependencies

- General familiarity with the resource types Trusted Advisor checks (EC2, S3, IAM, security groups) across Parts 2-5.
- **AWS Support Plans** (a Part 1 topic): Trusted Advisor's full check catalog and refresh frequency are tied to your support plan tier — Business and Enterprise Support unlock the complete set of checks; Basic/Developer support sees a more limited subset (primarily service-limit and a handful of core checks).

## 4. Internal Working

- Trusted Advisor runs its checks **periodically** (refresh frequency varies by check and support plan — some checks refresh within minutes on higher support tiers, others on a longer cycle), evaluating live account configuration against each check's specific criteria, and categorizing findings by **status color** (green = no issue, yellow = investigate, red = action recommended) across five categories: **Cost Optimization**, **Performance**, **Security**, **Fault Tolerance**, and **Service Limits**.
- Service Limit checks specifically monitor your account's usage against AWS's default service quotas (e.g., "you're at 85% of your VPC limit for this region"), giving advance warning before you actually hit a limit that could block a needed deployment — directly relevant given how many services throughout this roadmap have specific soft limits mentioned in passing (SQS in-flight messages, Lambda concurrency, EventBridge target counts, and others).
- The **public AWS Service Health Dashboard** shows the current and historical operational status of every AWS service, per region, visible to anyone without needing to be an AWS customer at all — this is AWS's own self-reported status, not derived from your account.
- The **AWS Personal Health Dashboard** (accessible within your account) goes further: it correlates active AWS events (both issues and _planned_ changes, like a scheduled maintenance window for a specific RDS instance) against your account's actual resource inventory, surfacing only the events genuinely relevant to resources you actually have — turning a generic "S3 in us-east-1 has an issue" into a specific "your bucket `my-production-bucket` may be affected."
- Personal Health Dashboard events can be configured to **trigger EventBridge rules** ([§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md)) — directly enabling automated response (a notification, a failover trigger, a ticket creation) the moment AWS itself reports an event affecting your specific resources, rather than requiring someone to notice it in the console.

```
Trusted Advisor: inspects YOUR account's configuration
   → Cost / Performance / Security / Fault Tolerance / Service Limits checks
   → Status: Green / Yellow / Red per check

AWS Health Dashboard:
   Public Service Health Dashboard  → AWS's own service status, region-wide, for anyone
   Personal Health Dashboard        → AWS events correlated against YOUR specific resources
                                        → can trigger EventBridge rules (§62)
```

## 5. Architecture & Components

| Component                                  | Explanation                                                                                                                                                   |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trusted Advisor Check**                  | An individual best-practice evaluation (e.g., "S3 Bucket Permissions," "Low Utilization EC2 Instances"), one of dozens across five categories.                |
| **Check Category**                         | Cost Optimization, Performance, Security, Fault Tolerance, Service Limits — the five groupings Trusted Advisor organizes findings into.                       |
| **Status Indicator**                       | Green/Yellow/Red per check, giving an at-a-glance severity signal.                                                                                            |
| **Service Health Dashboard**               | Public, account-independent AWS service status, per region.                                                                                                   |
| **Personal Health Dashboard (AWS Health)** | Account-specific, resource-correlated event visibility, including both issues and planned changes.                                                            |
| **Health Event**                           | A specific reported occurrence (an outage, a degradation, or a scheduled maintenance/end-of-support notice) with a defined status and affected-resource list. |

## 6. Lifecycle / Workflow

1. Trusted Advisor **continuously evaluates** your account against its check catalog (frequency depending on support plan and check type), surfacing findings in the console with status colors.
2. Operators **review findings periodically** (or via automated export/reporting), prioritizing red/yellow findings, particularly in Security and Fault Tolerance categories.
3. When AWS experiences a service event, it's reported first to the **public Service Health Dashboard**.
4. If the event is relevant to resources in your specific account, it **also appears on your Personal Health Dashboard**, with the specific affected resources identified.
5. Optionally, Personal Health Dashboard events **trigger EventBridge rules**, feeding into the same alerting/automation pipelines covered throughout Part 7 and Part 8.

## 7. Configuration

| Setting                                            | Purpose                                                                                               |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Support plan tier                                  | Determines the full breadth and refresh frequency of Trusted Advisor checks available                 |
| Trusted Advisor notification preferences           | Weekly email digest of check status changes                                                           |
| EventBridge rule on AWS Health events              | Enables automated response to account-specific service events                                         |
| Organizational aggregation (via AWS Organizations) | Consolidates Trusted Advisor findings and Health events across all member accounts into a single view |

⚠️ **Warning:** the _full_ Trusted Advisor check catalog (particularly Security and Fault Tolerance categories beyond a small core set) requires **Business or Enterprise Support** — an account on Basic or Developer support sees only a limited subset of checks, which is a common, easy-to-miss gap when an organization assumes Trusted Advisor is giving comprehensive coverage but hasn't actually verified their support plan tier unlocks the checks they're relying on.

## 8. Commands (Full Documentation)

### `aws support describe-trusted-advisor-checks`

- **Purpose:** Lists all available Trusted Advisor checks (subject to your support plan's access level).
- **Syntax:**
  ```
  aws support describe-trusted-advisor-checks --language en
  ```
- **Practical example output:**
  ```json
  {
    "checks": [
      {
        "id": "Qch7DwouX1",
        "name": "Security Groups - Specific Ports Unrestricted",
        "category": "security"
      }
    ]
  }
  ```
- **Important arguments:** the Support API (which Trusted Advisor's CLI access lives under) generally requires Business or Enterprise Support to call at all — a common early surprise for teams trying to script Trusted Advisor access on a lower support tier.
- **Production usage:** used to programmatically enumerate available checks before pulling specific results, often as the first step in a scripted, scheduled Trusted Advisor reporting pipeline.

### `aws support describe-trusted-advisor-check-result`

- **Purpose:** Retrieves the current result (status and specific flagged resources) for a given check.
- **Syntax:**
  ```
  aws support describe-trusted-advisor-check-result --check-id <id> --language en
  ```
- **Practical example:**
  ```
  aws support describe-trusted-advisor-check-result --check-id Qch7DwouX1
  ```
  **Expected output:**
  ```json
  {
    "result": {
      "status": "warning",
      "flaggedResources": [
        { "metadata": ["us-east-1", "sg-0123456789abcdef0", "22", "0.0.0.0/0"] }
      ]
    }
  }
  ```
- **Production usage:** commonly integrated into a scheduled Lambda ([§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)) that pulls check results periodically and publishes findings to a Slack channel or ticketing system, turning Trusted Advisor into an actively-pushed signal rather than something someone has to remember to check in the console.
- **Common errors:** requesting a check ID not actually available at your support plan tier returns an error rather than a result — a direct symptom of the [§7](../Part1/Section-07-Part1-AWS-Support-Plans-and-Service-Category-Map.md) warning above.

### `aws health describe-events`

- **Purpose:** Retrieves current and recent AWS Health events relevant to your account (Personal Health Dashboard data via API).
- **Syntax:**
  ```
  aws health describe-events --filter '{"eventStatusCodes": ["open", "upcoming"]}'
  ```
- **Practical example output:**
  ```json
  {
    "events": [
      {
        "service": "RDS",
        "eventTypeCode": "AWS_RDS_PLANNED_LIFECYCLE_EVENT",
        "region": "us-east-1",
        "statusCode": "upcoming"
      }
    ]
  }
  ```
- **Important arguments:** `describe-events` (and the underlying `DescribeEvents` API) is part of the **AWS Health API**, which — like Trusted Advisor's Support API — has fuller functionality available on Business/Enterprise Support; basic account/public-status information remains available regardless.
- **Production usage:** commonly wired directly to an EventBridge rule (rather than polled via this API) for real-time reaction, but this API is useful for scripted, periodic health-posture reporting or dashboard-building.
- **Security impact:** requires `health:DescribeEvents`; low sensitivity (read-only operational status), but worth including in any centralized operational dashboard tooling.

## 9. Hands-On Example — Automated Trusted Advisor Reporting and Health Event Response

```python
import boto3

support = boto3.client('support', region_name='us-east-1')  # Support API is only in us-east-1

def check_security_findings():
    checks = support.describe_trusted_advisor_checks(language='en')['checks']
    security_checks = [c for c in checks if c['category'] == 'security']

    findings = []
    for check in security_checks:
        result = support.describe_trusted_advisor_check_result(checkId=check['id'])['result']
        if result['status'] in ('warning', 'error'):
            findings.append({'check': check['name'], 'status': result['status'],
                              'flagged_count': len(result.get('flaggedResources', []))})
    return findings

# Publish findings to SNS (§61) for team notification
```

```bash
# EventBridge rule reacting to a Personal Health Dashboard event automatically
aws events put-rule --name AwsHealthEventAlert --event-pattern '{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"]
}'
aws events put-targets --rule AwsHealthEventAlert --targets '[
  {"Id": "1", "Arn": "arn:aws:sns:us-east-1:123456789012:ops-critical-alerts"}
]'
```

This directly reuses [§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md)'s EventBridge pattern-matching to turn a passive dashboard into an active alerting pipeline — the moment AWS reports an event affecting your specific resources, the team is notified through the exact same SNS/alerting infrastructure used for every other operational signal in this roadmap, rather than requiring someone to remember to check a separate dashboard.

## 10. Production & Enterprise Usage

- **Startups** commonly check Trusted Advisor manually and infrequently, often discovering its value first through a specific cost-optimization finding (an idle load balancer, an underutilized instance) rather than as part of a systematic review practice.
- **Enterprises** integrate Trusted Advisor findings into regular (often weekly or monthly) operational review cadences, frequently aggregated across an entire AWS Organization for centralized visibility, and wire Personal Health Dashboard events directly into incident-response tooling so an AWS-side issue is detected and communicated exactly as fast as an internally-detected one.
- Trusted Advisor's Service Limit checks are commonly integrated into capacity-planning processes, providing advance warning before a limit becomes a genuine deployment blocker — directly relevant given how many services in this roadmap (SQS, Lambda, EventBridge, and others) have specific account-level soft limits.
- Health Dashboard events feeding EventBridge are a common input to **automated failover** decisions in multi-region architectures — an AWS-reported regional degradation event can directly trigger a Step Functions workflow ([§63](../Part7/Section-63-Part7-StepFunctions-Orchestration.md)) initiating failover to a secondary region, rather than waiting for internal monitoring to independently detect the same underlying issue.

## 11. Security Considerations

- Trusted Advisor's Security category findings (open security groups, exposed access keys, S3 bucket permission issues) are directly actionable security signals — treating a red/yellow Security finding with the same urgency as a CloudWatch security alarm ([§71](./Section-71-Part8-CloudWatch-Alarms-Dashboards.md)) is appropriate, not optional.
- Trusted Advisor and Health API access should be scoped via IAM like any other read capability — while low-risk individually, the aggregated findings (a list of exactly which security groups/resources are misconfigured) constitute a meaningful information-disclosure risk if broadly accessible.

## 12. Performance Considerations

- Trusted Advisor check refresh frequency varies — some checks refresh on-demand or within minutes on higher support tiers, others on a longer cycle; don't assume a just-remediated finding will immediately show as resolved without a refresh.
- Health API polling (versus EventBridge-based push) adds unnecessary latency and API call overhead for anything needing near-real-time response — prefer the EventBridge integration for genuine alerting use cases.

## 13. Monitoring

| Signal                                                              | What it tells you                                                                                                |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Trusted Advisor status color distribution (per category, over time) | Overall account health-posture trend — a growing number of red findings signals accumulating configuration debt. |
| AWS Health events (via EventBridge)                                 | Real-time, resource-correlated AWS-side incident/change awareness.                                               |
| Service Limit check proximity-to-threshold trend                    | Advance capacity-planning signal, before a limit actually blocks a deployment.                                   |

## 14. Troubleshooting

| Symptom                                                                       | Likely Root Cause                                                                                                                                                        | Fix                                                                                                                                                                     |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Expected Trusted Advisor checks not visible/available                         | Support plan tier doesn't include the full check catalog                                                                                                                 | Verify current support plan; the core Service Limit checks remain available even on Basic support, but most Security/Fault Tolerance checks require Business/Enterprise |
| Trusted Advisor finding still shows as unresolved after remediation           | Check hasn't refreshed yet                                                                                                                                               | Manually trigger a refresh in the console, or wait for the check's normal refresh cycle                                                                                 |
| Personal Health Dashboard shows no events despite a known public AWS incident | The incident genuinely doesn't affect any resources in your specific account/region, or event correlation hasn't yet processed                                           | Cross-check the public Service Health Dashboard for the region/service in question                                                                                      |
| EventBridge rule on AWS Health events never fires                             | Rule's event pattern doesn't match the actual event structure, or `health:DescribeEvents`-level access isn't available at current support tier for the full event detail | Verify pattern against a real sample event; confirm support plan tier for full Health API functionality                                                                 |

## 15. Best Practices

- Review Trusted Advisor findings on a regular cadence, prioritizing Security and Fault Tolerance categories, not just Cost Optimization.
- Verify your organization's support plan tier actually unlocks the Trusted Advisor checks you're relying on, rather than assuming full coverage by default.
- Wire Personal Health Dashboard events to EventBridge for automated, real-time response rather than relying on someone checking the console.
- Use Service Limit checks proactively in capacity planning, not just reactively after hitting a limit.
- Aggregate Trusted Advisor and Health visibility across an AWS Organization centrally for large multi-account environments.

## 16. Anti-Patterns & Common Mistakes

- ❌ Assuming Trusted Advisor gives comprehensive best-practice coverage without verifying the account's support plan actually includes the full check catalog.
- ❌ Treating the public Service Health Dashboard as sufficient incident-diagnosis visibility, missing the Personal Health Dashboard's more actionable, resource-correlated detail.
- ❌ Checking Trusted Advisor/Health Dashboard only reactively during an incident, rather than as part of regular operational review — by the time you need it reactively, accumulated findings are often numerous and harder to triage under pressure.
- **Common misconception:** "Trusted Advisor and AWS Health are the same kind of tool." False — Trusted Advisor evaluates _your account's configuration_ against best practices; AWS Health reports on _AWS's own infrastructure status_ and its correlation to your resources — genuinely different data sources answering genuinely different questions.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What's the difference between Trusted Advisor and the AWS Health Dashboard?"_
**Model answer:** Trusted Advisor looks at your own account's configuration and flags places where you're deviating from AWS best practices, across categories like cost, security, and fault tolerance — things like an overly permissive security group or an idle resource. The AWS Health Dashboard is about AWS's own service status — is there currently an outage or degradation in a specific AWS service, and importantly, the Personal Health Dashboard specifically tells you whether that issue actually affects resources you have provisioned, rather than just a generic "this service in this region has a problem."

**🎯 Intermediate:** _"Why might a team assume Trusted Advisor gives them full best-practice coverage but actually be missing significant findings?"_
**Model answer:** The full Trusted Advisor check catalog, especially most of the Security and Fault Tolerance category checks, requires Business or Enterprise Support — an account on Basic or Developer support only sees a much smaller subset, mostly limited to core Service Limit checks. A team that's never specifically verified their support plan tier against what checks are actually running could easily believe they have comprehensive coverage when they're actually only seeing a fraction of the available checks, which is a real, common gap worth explicitly verifying rather than assuming.

**🎯 Senior:** _"How would you use AWS Health events to improve incident response time for AWS-side outages, beyond just occasionally checking the dashboard?"_
**Model answer:** I'd configure an EventBridge rule matching AWS Health events, routed to the same alerting pipeline used for internally-detected incidents — an SNS topic feeding the on-call notification system — so that the moment AWS reports an event affecting our specific resources, it reaches the team through the identical channel and urgency as any other production alert, rather than requiring someone to separately remember to check a dashboard. This is particularly valuable for the "is this us or is this AWS" diagnostic question that comes up early in almost every incident — having the Personal Health Dashboard's resource-correlated event arrive automatically, in parallel with our own CloudWatch alarms, immediately tells the responding engineer whether to focus investigation on our own systems or to expect the root cause to be external and outside our direct control, which meaningfully changes the shape of the investigation from the very first minute.

**🎯 Architect:** _"Design an operational-health program for a large enterprise with 200 AWS accounts, ensuring both Trusted Advisor findings and AWS Health events are visible centrally, without requiring each account team to individually monitor their own account."_
**Model answer:** I'd use AWS Organizations' aggregation capabilities to consolidate both Trusted Advisor findings and Health events into a centrally-owned account, so a security/platform team gets one unified view across all 200 accounts rather than needing to check each individually — directly mirroring the same organization-wide aggregation pattern already established for CloudTrail ([§73](./Section-73-Part8-CloudTrail-Audit-Governance.md)) and Config ([§74](./Section-74-Part8-AWS-Config.md)) in this roadmap. I'd ensure the organization is on a support plan tier (Business or Enterprise) that unlocks the full Trusted Advisor check catalog across every member account, since a partial-coverage program provides a false sense of comprehensive review. For Health events specifically, I'd configure EventBridge rules in each account forwarding relevant events to that same central account's event bus, feeding both automated alerting and a centralized incident-response dashboard — giving the central team real-time, resource-correlated AWS-side incident awareness across the full 200-account estate, while individual account teams retain their own local Trusted Advisor/Health visibility for their specific resources without needing to build or maintain any of that centralized tooling themselves.

## 18. Common Misconceptions

- "Trusted Advisor automatically fixes the issues it finds." False — Trusted Advisor is purely a detective/recommendation tool; remediation is a separate, manual (or separately-automated, e.g., via Config remediation actions or Systems Manager Automation, [§74](./Section-74-Part8-AWS-Config.md)-[§75](./Section-75-Part8-Systems-Manager.md)) action.
- "The public Service Health Dashboard tells you if your resources are affected." False — the public dashboard reports AWS's own aggregate service status; only the Personal Health Dashboard correlates events against your specific account's actual resources.

## 19. Key Takeaways

🔑 Trusted Advisor evaluates your account's configuration against AWS best practices across five categories (Cost, Performance, Security, Fault Tolerance, Service Limits); AWS Health reports AWS's own infrastructure status.
🔑 Full Trusted Advisor check coverage requires Business/Enterprise Support — verify this explicitly rather than assuming comprehensive coverage by default.
🔑 The Personal Health Dashboard's resource-correlation (versus the generic public Service Health Dashboard) is what makes it genuinely actionable during incident response.
🔑 Wiring AWS Health events to EventBridge turns a passive dashboard into an active, real-time alerting input, integrated with the same pipelines used for internally-detected incidents.
🔑 Both tools benefit from organization-wide aggregation in multi-account environments, mirroring the same centralization pattern established for CloudTrail and Config.

## 20. Related Concepts

- **AWS Support Plans** (a Part 1 topic determining Trusted Advisor's check coverage) — cross-referenced here as a dependency.
- **EventBridge** (the mechanism for real-time Health event alerting) → [§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md).
- **CloudTrail, AWS Config** (the other centrally-aggregated, organization-wide governance tools this Part covered) → [§73](./Section-73-Part8-CloudTrail-Audit-Governance.md)-[§74](./Section-74-Part8-AWS-Config.md).
- **Observability Architecture — Putting It All Together** (incorporating Trusted Advisor/Health awareness into the broader incident-investigation flow) → next section, [§77](./Section-77-Part8-Observability-Architecture-Together.md).
