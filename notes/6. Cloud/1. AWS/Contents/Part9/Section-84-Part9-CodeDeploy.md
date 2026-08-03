# Part 9, Section 6: AWS CodeDeploy

## 1. Definition

**Plain language:** CodeDeploy is AWS's managed deployment automation service — it takes a built application artifact (from CodeBuild, §83, or elsewhere) and actually gets it running on your EC2 instances, on-premises servers, Lambda functions, or ECS services, following a defined deployment procedure with built-in health checking and automatic rollback if something goes wrong.

**Precise definition:** AWS CodeDeploy is a deployment automation service that coordinates application deployments to Amazon EC2 instances, on-premises servers, AWS Lambda functions, and Amazon ECS services, using a deployment configuration (specifying the deployment strategy — in-place or blue/green, and traffic-shifting behavior) and an application specification (AppSpec) file defining the deployment lifecycle hooks, with automated health-check-driven rollback on failure.

## 2. Why It Exists / Problem It Solves

CodeBuild (§83) produces a built, tested artifact — but getting that artifact actually running in production, replacing whatever version is currently live, is its own distinct, risky operation. Doing this manually (SSH into each server, stop the old version, copy the new files, restart) is slow, error-prone, and doesn't scale to fleets of instances; doing it with a hand-rolled script requires building your own health-checking and rollback logic — and getting that logic wrong is exactly the kind of mistake that turns a routine deployment into a production outage.

CodeDeploy solves this by providing a **battle-tested, declarative deployment engine**: you define the deployment strategy and the specific lifecycle hooks (what to run before/after traffic shifts to the new version), and CodeDeploy handles the actual sequencing, health verification, and — critically — **automatic rollback** if health checks fail partway through, without requiring you to build that safety logic yourself.

## 3. Prerequisites and Dependencies

- **EC2, Lambda, ECS** (Part 3): the compute platforms CodeDeploy deploys to.
- **CodePipeline & CodeBuild** (§83): CodeDeploy is commonly the Deploy-stage action following a CodeBuild Build stage within one CodePipeline pipeline.
- **Deployment Strategies** (§85, next section): CodeDeploy is the AWS-native _mechanism_ implementing the blue/green, canary, and rolling deployment _patterns_ covered conceptually in that section.

## 4. Internal Working

- CodeDeploy targets three distinct **compute platforms**, each with different deployment mechanics: **EC2/On-Premises** (deploying to instances identified individually or via an Auto Scaling group/tag-based deployment group), **Lambda** (shifting traffic between function versions via weighted aliases), and **ECS** (shifting traffic between task set versions behind a load balancer).
- A **deployment group** defines the target set of instances/resources for a given application, along with the deployment configuration (strategy) to use.
- The **AppSpec file** (`appspec.yml`, checked into the deployed artifact) defines **lifecycle event hooks** — for EC2/on-premises deployments, this includes hooks like `BeforeInstall`, `AfterInstall`, `ApplicationStart`, and `ValidateService`, each an opportunity to run a specific script (stop the old application, copy new files, run a smoke test) at the correct point in the deployment sequence; for Lambda, the AppSpec instead defines which function version to shift traffic to and any `BeforeAllowTraffic`/`AfterAllowTraffic` validation hooks.
- For **EC2/on-premises in-place deployments**, CodeDeploy deploys to instances in batches (configurable), running the AppSpec's lifecycle hooks on each batch, and monitoring instance health throughout.
- For **blue/green deployments** (EC2, Lambda, or ECS), CodeDeploy provisions or identifies a completely separate, parallel "green" environment running the new version, validates its health, and then shifts traffic from "blue" (the current live version) to "green" — either all at once, linearly over a defined time period, or in defined canary percentage increments (full depth on these traffic-shifting patterns in §85).
- **Automatic rollback** triggers when a deployment's health checks (CloudWatch alarms, §71, can be directly wired as rollback triggers) fail, or when the deployment lifecycle itself reports a failure — CodeDeploy then reverts to the last known-good deployed revision, without requiring manual intervention to initiate the rollback.

```
CodeBuild artifact ──▶ CodeDeploy Deployment
                              │
              ┌───────────────┼───────────────┐
              ▼                ▼               ▼
         EC2/On-Prem         Lambda            ECS
    (AppSpec lifecycle    (weighted alias    (task set traffic
     hooks: BeforeInstall, traffic shift     shift behind
     AfterInstall,         between versions) load balancer)
     ApplicationStart,
     ValidateService)
              │
    Health check failure ──▶ Automatic Rollback to last known-good revision
```

## 5. Architecture & Components

| Component                    | Explanation                                                                                                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Application**              | The top-level CodeDeploy resource representing what's being deployed.                                                                                      |
| **Deployment Group**         | The target compute resources (EC2 instances/ASG, Lambda function, ECS service) and the deployment configuration to apply.                                  |
| **Deployment Configuration** | The strategy — `AllAtOnce`, `HalfAtATime`, `OneAtATime` (EC2 in-place), or Lambda/ECS's canary/linear/all-at-once traffic-shifting options for blue/green. |
| **AppSpec File**             | Defines lifecycle hooks (EC2/on-prem) or traffic-shift/validation configuration (Lambda/ECS).                                                              |
| **Lifecycle Event Hook**     | A specific point in the deployment sequence (e.g., `BeforeInstall`, `ApplicationStart`) where a custom script runs.                                        |
| **Rollback Trigger**         | A CloudWatch alarm or deployment-failure condition that automatically initiates rollback to the last known-good revision.                                  |

## 6. Lifecycle / Workflow

1. **Define** the CodeDeploy application and deployment group(s), specifying the target compute platform and deployment configuration.
2. **Author** the AppSpec file, checked into the source repository alongside the application code, defining lifecycle hooks or traffic-shift behavior.
3. A **deployment is triggered** — typically as the Deploy stage of a CodePipeline (§83) following a successful build, using the build's output artifact.
4. CodeDeploy **executes the deployment** per its configuration — in-place batch-by-batch for EC2/on-premises, or blue/green traffic-shifting for EC2/Lambda/ECS — running AppSpec lifecycle hooks at each defined point.
5. CodeDeploy **monitors health** throughout (instance health status, configured CloudWatch alarms) and **automatically rolls back** to the last known-good revision if a failure is detected.
6. Deployment status, per-instance/per-hook detail, and history are available for troubleshooting and audit.

## 7. Configuration

| Setting                                                                   | Purpose                                                                                        |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Deployment configuration (`AllAtOnce`/`HalfAtATime`/`OneAtATime`/custom)  | Controls batch size and rollout pace for EC2/on-premises in-place deployments                  |
| Traffic-shifting configuration (Lambda/ECS blue/green)                    | Controls canary percentage/interval or linear shift rate — full depth in §85                   |
| Rollback configuration (`DEPLOYMENT_FAILURE`, `DEPLOYMENT_STOP_ON_ALARM`) | Determines what conditions trigger automatic rollback                                          |
| Associated CloudWatch alarms                                              | Health signals CodeDeploy watches during and after a deployment to decide whether to roll back |
| AppSpec lifecycle hooks                                                   | The specific scripts run at each stage of the deployment                                       |

⚠️ **Warning:** automatic rollback is only as good as the health signals it's watching — a deployment with no CloudWatch alarms configured, or with a `ValidateService`/validation hook that doesn't actually meaningfully check application health (e.g., just checking the process is running, not that it's actually serving correct responses), can "successfully" deploy a broken application with no rollback triggered at all, since CodeDeploy has no independent way to know the deployment is actually unhealthy beyond what it's told to check.

## 8. Commands (Full Documentation)

### `aws deploy create-deployment-group`

- **Purpose:** Defines a deployment group — the target resources and deployment configuration for an application.
- **Syntax:**
  ```
  aws deploy create-deployment-group --application-name <app> --deployment-group-name <name> \
    --deployment-config-name <config> --ec2-tag-filters <filters> --service-role-arn <role>
  ```
- **Practical example:**
  ```
  aws deploy create-deployment-group --application-name order-service \
    --deployment-group-name production \
    --deployment-config-name CodeDeployDefault.OneAtATime \
    --ec2-tag-filters Key=Environment,Value=production,Type=KEY_AND_VALUE \
    --service-role-arn arn:aws:iam::123456789012:role/CodeDeployServiceRole
  ```
  **Expected output:** the created deployment group's configuration detail.
- **Important arguments:** `--ec2-tag-filters` targets instances by tag (directly reusing the same tag-based targeting pattern seen in Systems Manager, §75) rather than a static instance list, so the deployment group automatically includes new instances as they're launched with matching tags.
- **Production usage:** deployment groups are commonly defined via CloudFormation/CDK (§79-81) alongside the rest of the application's infrastructure, so the deployment configuration is versioned and reviewed like any other infrastructure change.
- **Security impact:** the `service-role-arn` needs permission to interact with the target compute platform (EC2, Lambda, or ECS) on CodeDeploy's behalf — scoped to the specific resources this deployment group actually manages.

### `aws deploy create-deployment`

- **Purpose:** Triggers an actual deployment using a specified application revision.
- **Syntax:**
  ```
  aws deploy create-deployment --application-name <app> --deployment-group-name <group> --s3-location <bucket,key,bundleType>
  ```
- **Practical example:**
  ```
  aws deploy create-deployment --application-name order-service \
    --deployment-group-name production \
    --s3-location bucket=my-artifacts-bucket,key=order-service/build-42.zip,bundleType=zip
  ```
  **Expected output:**
  ```json
  { "deploymentId": "d-A1B2C3D4E" }
  ```
- **Production usage:** typically invoked automatically as a CodePipeline Deploy-stage action (§83) rather than run manually, using the artifact produced by the preceding Build stage.
- **Common errors:** a deployment failing at a specific AppSpec lifecycle hook (e.g., `ApplicationStart` failing because the new application version doesn't actually start correctly) is the most common failure mode — CodeDeploy's deployment event log shows exactly which hook failed and why.
- **Security impact:** requires `codedeploy:CreateDeployment`; a sensitive action worth restricting to the pipeline's own service identity rather than granting broadly to individual engineers, per §86's separation-of-duties principle.

### `aws deploy get-deployment`

- **Purpose:** Retrieves the current status and detail of a specific deployment.
- **Syntax:**
  ```
  aws deploy get-deployment --deployment-id <id>
  ```
- **Practical example output:**
  ```json
  {
    "deploymentInfo": {
      "status": "Failed",
      "errorInformation": {
        "code": "HEALTH_CONSTRAINTS",
        "message": "The overall deployment failed because too many individual instances failed deployment."
      }
    }
  }
  ```
- **Production usage:** the primary troubleshooting operation for a failed or in-progress deployment, showing overall status and, for EC2 deployments, per-instance detail via a companion `list-deployment-instances`/`get-deployment-instance` call.

## 9. Hands-On Example — appspec.yml for an EC2 In-Place Deployment

```yaml
version: 0.0
os: linux
files:
  - source: /
    destination: /var/www/order-service
hooks:
  BeforeInstall:
    - location: scripts/stop_application.sh
      timeout: 60
  AfterInstall:
    - location: scripts/install_dependencies.sh
      timeout: 180
  ApplicationStart:
    - location: scripts/start_application.sh
      timeout: 60
  ValidateService:
    - location: scripts/health_check.sh
      timeout: 60
```

This shows the standard EC2/on-premises AppSpec lifecycle: stop the currently running application (`BeforeInstall`), install the new version's dependencies (`AfterInstall`), start the new version (`ApplicationStart`), and then genuinely validate it's healthy (`ValidateService`) — critically, `health_check.sh` here should perform a real functional check (e.g., an HTTP request to a health endpoint expecting a specific response), not merely check that a process ID exists, directly addressing the §7 warning above about rollback only being as good as the health signal it depends on.

## 10. Production & Enterprise Usage

- **Startups** commonly start with simple EC2 in-place deployments (`OneAtATime` or `HalfAtATime`) before adopting blue/green as their availability requirements mature.
- **Enterprises** standardize on blue/green deployments for production-tier services specifically for the near-zero-downtime and fast-rollback characteristics (full trade-off discussion in §85), often with mandatory CloudWatch alarm-based rollback triggers enforced as a platform-level requirement across all deployment groups, not left to individual team discretion.
- CodeDeploy for Lambda is commonly used to safely roll out new function versions using weighted alias traffic shifting, directly building on Lambda's versioning/alias model (§25) to get canary-style safety for serverless deployments without needing a separate blue/green infrastructure concept.
- CodeDeploy integrates natively with **CodePipeline** (§83) as the standard Deploy-stage action, and with **CloudWatch alarms** (§71) as its rollback-trigger mechanism — directly connecting this section to the observability and CI orchestration content covered elsewhere in this roadmap.

## 11. Security Considerations

- The CodeDeploy service role needs platform-specific permissions (EC2 instance management, Lambda alias updates, or ECS task set management) scoped tightly to the specific deployment group's actual target resources.
- AppSpec lifecycle hook scripts run with whatever permissions the target instance/execution environment has — a compromised or malicious hook script is a genuine risk, making source-repository access control (who can modify the AppSpec and its referenced scripts) a meaningful security boundary.
- Deployment triggering (`codedeploy:CreateDeployment`) should be restricted to the pipeline's own service identity in production, not granted to individual engineers directly, consistent with §86's pipeline-discipline principles.

## 12. Performance Considerations

- In-place deployment batch size (`OneAtATime`, `HalfAtATime`, `AllAtOnce`) directly trades deployment speed against availability during the deployment — `OneAtATime` is safest but slowest for large fleets; `AllAtOnce` is fastest but means the entire fleet is briefly unavailable/updating simultaneously.
- Blue/green deployments avoid this trade-off entirely for availability (the old environment keeps serving until the new one is validated) at the cost of requiring double the compute capacity during the transition window — a direct cost/availability trade-off worth being explicit about (§89's Well-Architected framing).

## 13. Monitoring

| Signal                                           | What it tells you                                                                                                |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Deployment status (per deployment)               | Overall success/failure/in-progress state.                                                                       |
| Per-instance deployment status (EC2/on-premises) | Which specific instances succeeded/failed within a fleet-wide deployment.                                        |
| Associated CloudWatch alarms                     | The health signals actively driving automatic rollback decisions.                                                |
| Deployment lifecycle event log                   | Exactly which AppSpec hook succeeded/failed and its output — the primary debugging tool for a failed deployment. |

## 14. Troubleshooting

| Symptom                                                                 | Likely Root Cause                                                                                                                      | Fix                                                                                                                             |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Deployment fails at a specific lifecycle hook                           | The hook's script itself failed or exceeded its timeout                                                                                | Review the specific hook's script output in the deployment event log; verify the script is correct and the timeout is realistic |
| Deployment "succeeds" but the application is actually broken            | `ValidateService`/health-check hook doesn't perform a genuinely meaningful functional check                                            | Strengthen the health check to a real functional test, not just a process-existence check                                       |
| Automatic rollback never triggers despite a genuinely broken deployment | No CloudWatch alarm configured as a rollback trigger, or the alarm doesn't actually reflect the specific failure mode                  | Configure and test rollback-triggering alarms against realistic failure scenarios before relying on them in production          |
| Blue/green deployment stuck, never completing traffic shift             | Health validation on the green environment is failing, or a manual approval step in the traffic-shift configuration is awaiting action | Check green-environment health status and any pending approval step                                                             |

## 15. Best Practices

- Ensure `ValidateService`/health-check hooks perform genuine functional validation, not just superficial process-existence checks.
- Configure CloudWatch alarms as explicit rollback triggers for any production deployment group — don't rely solely on deployment-lifecycle failure detection.
- Prefer blue/green over in-place deployment for production-tier services where the additional compute cost is justified by near-zero-downtime and fast rollback.
- Trigger deployments only through the CI/CD pipeline's own service identity, not individual engineer credentials, consistent with §86.
- Version-control AppSpec files and lifecycle hook scripts alongside application code, subject to the same code review as any other change.

## 16. Anti-Patterns & Common Mistakes

- ❌ Writing a `ValidateService` health check that only confirms a process is running, missing genuinely broken-but-running application states that a real functional check would catch.
- ❌ Deploying without any CloudWatch alarm configured as a rollback trigger, meaning automatic rollback only ever triggers on outright lifecycle-hook failure, not on a "successfully deployed but functionally broken" scenario.
- ❌ Using `AllAtOnce` in-place deployment for a production fleet without understanding it means the entire fleet is briefly simultaneously updating, with no availability buffer if something goes wrong mid-deployment.
- **Common misconception:** "CodeDeploy automatically knows if my application is healthy." False — CodeDeploy only knows what you explicitly tell it to check, via lifecycle hooks and configured CloudWatch alarms; a shallow or missing health check means CodeDeploy has no way to detect a functionally broken deployment.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What does CodeDeploy do, and what are the three compute platforms it supports?"_
**Model answer:** CodeDeploy automates getting a built application artifact actually running in production, coordinating the deployment sequence and automatically rolling back if health checks fail. It supports EC2 instances and on-premises servers (running scripts at defined lifecycle points like stopping the old version and starting the new one), AWS Lambda (shifting traffic between function versions via weighted aliases), and Amazon ECS (shifting traffic between task set versions behind a load balancer).

**🎯 Intermediate:** _"Why is a shallow health check in the ValidateService hook a genuine production risk, even though the deployment itself completes successfully?"_
**Model answer:** CodeDeploy's automatic rollback decision is entirely dependent on the health signals it's told to check — if ValidateService only confirms that a process is running, rather than actually testing that the application is correctly serving requests, then a deployment that starts a process successfully but has a functional bug (say, a broken database connection string) will report as a successful deployment with no rollback triggered, even though the application is actually broken in production. The fix is making the health check a genuine functional test — an actual HTTP request to a health endpoint checking for a correct response — so CodeDeploy's rollback safety net actually covers the failure modes that matter, not just "did the process start."

**🎯 Senior:** _"A blue/green Lambda deployment using canary traffic shifting rolled back automatically partway through, but the team isn't sure why since there was no obvious application error. How would you investigate?"_
**Model answer:** I'd start by checking exactly which CloudWatch alarm was configured as the rollback trigger and pull its state history around the time of the rollback, since the rollback was very likely triggered by that specific alarm crossing its threshold, whether or not the actual application had a functional bug — for example, the alarm might have been watching an error-rate metric that spiked briefly due to something unrelated to the new deployment (a downstream dependency blip happening to coincide with the canary window) rather than the new Lambda version itself being broken. I'd correlate the alarm's exact trigger time against the canary traffic percentage active at that moment, and check whether the errors were actually occurring on requests routed to the new version specifically versus the old version, which would distinguish "this is genuinely the new deployment's fault" from "this was an unrelated, coincidental issue that happened to trip an overly sensitive alarm during the canary window."

**🎯 Architect:** _"Design a CodeDeploy strategy for a payments-processing Lambda function where a bad deployment could directly cause customer-facing financial errors, balancing deployment velocity against the severe cost of a bad release reaching full traffic."_
**Model answer:** I'd use a canary traffic-shifting configuration with a small initial percentage (e.g., 1-5%) and a meaningful observation window before increasing, rather than a fast linear shift or all-at-once cutover, specifically because the cost asymmetry described — a bad payments deployment is far more costly than a slightly slower rollout — justifies erring toward caution here. I'd configure multiple CloudWatch alarms as rollback triggers, not just a generic error-rate alarm: specifically payment-failure-rate and payment-latency-p99 metrics scoped to distinguish traffic hitting the new version from the old version where possible, since a generic aggregate error rate could mask a real problem if the new version's traffic percentage is still small relative to the old version's. I'd also require a genuine, business-logic-aware `ValidateService`-equivalent check before allowing any traffic shift to proceed at all — for a payments system specifically, this might mean processing a synthetic test transaction against the new version in a sandboxed way and verifying the exact expected outcome, not just checking that the Lambda function returns any 200 response. Given the described severity, I'd treat this specific deployment pipeline as warranting more conservative settings than the organization's general default deployment configuration, explicitly documenting why this particular service gets the slower, more cautious treatment.

## 18. Common Misconceptions

- "Blue/green deployments are always strictly better than in-place deployments." Not universally — blue/green requires double the compute capacity during the transition and more complex traffic-management setup; for lower-stakes services, the simpler in-place model with a reasonable batch size may be perfectly adequate and lower-overhead.
- "CodeDeploy handles building and testing the application." False — that's CodeBuild's (§83) job; CodeDeploy specifically handles getting an already-built artifact deployed and running, picking up where CodeBuild leaves off.

## 19. Key Takeaways

🔑 CodeDeploy automates application deployment across EC2/on-premises, Lambda, and ECS, with AppSpec-defined lifecycle hooks and automatic health-check-driven rollback.
🔑 Automatic rollback is only as good as the health signals (CloudWatch alarms, ValidateService checks) it's configured to watch — shallow checks mean shallow safety.
🔑 In-place deployment batch size and blue/green traffic-shifting configuration are direct, tunable trade-offs between deployment speed, availability, and compute cost during the transition.
🔑 CodeDeploy is commonly the Deploy-stage action within a CodePipeline pipeline, immediately following a CodeBuild Build stage.
🔑 Deployment triggering should flow through the CI/CD pipeline's own service identity, not individual engineer credentials, consistent with the broader pipeline-discipline principles in §86.

## 20. Related Concepts

- **AWS CodePipeline & CodeBuild** (the orchestration and build stages preceding a CodeDeploy deployment) → §83.
- **Deployment Strategies** (the conceptual blue/green, canary, and rolling patterns CodeDeploy implements mechanically) → next section, §85.
- **CloudWatch Alarms** (the mechanism behind CodeDeploy's automatic rollback triggers) → §71.
- **Lambda versions and aliases** (the underlying mechanism CodeDeploy uses for Lambda traffic shifting) → §25.
