# Part 9, Section 5: AWS CodePipeline & CodeBuild

## 1. Definition

**Plain language:** CodePipeline is AWS's native CI/CD orchestration service — it defines the stages a change goes through (source → build → test → deploy) and runs them automatically whenever new code arrives. CodeBuild is the managed service that actually compiles, tests, and packages your code within one of those stages, without you needing to run and maintain your own Jenkins server or build fleet.

**Precise definition:** AWS CodePipeline is a continuous delivery orchestration service that models a release process as a series of stages and actions, automatically triggering and sequencing them (source retrieval, build, test, deploy, manual approval) whenever a change occurs, with each stage's specific work delegated to purpose-built actions or other AWS/third-party services. AWS CodeBuild is a fully managed build service that compiles source code, runs tests, and produces deployable artifacts, using ephemeral, on-demand build environments defined via a `buildspec.yml` file, without requiring you to provision or manage build servers.

## 2. Why It Exists / Problem It Solves

[§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)–[§4](../Part1/Section-04-Part1-AWS-Accounts-Root-User-Identity-Basics.md) established _what_ gets deployed (CloudFormation/CDK/Terraform templates) and [§86](./Section-86-Part9-CICD-Infrastructure-GitOps.md) (later in this Part) establishes the _discipline_ around deploying infrastructure changes safely. But before any of that, there's a more basic, universal problem: application code itself needs to be built, tested, and packaged reliably and repeatably every time it changes — and traditionally, this meant standing up and maintaining your own build infrastructure (a Jenkins server, a build agent fleet), which is itself an operational burden requiring patching, scaling, and security hardening, similar in spirit to the burden SQS eliminated for message queuing ([§59](../Part7/Section-59-Part7-SQS-Fundamentals.md)) or RDS eliminates for database administration.

CodePipeline and CodeBuild solve this the AWS-native way: CodePipeline provides the orchestration (what happens in what order, triggered by what), and CodeBuild provides the actual, ephemeral compute for building and testing, with AWS managing all the underlying build-server infrastructure — you define _what_ to build, not how to keep a build server patched and available.

## 3. Prerequisites and Dependencies

- **IAM** ([§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)): CodePipeline and CodeBuild both operate via IAM service roles, exactly like every other AWS service execution role covered in this roadmap.
- **CloudFormation/CDK/Terraform** ([§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](./Section-82-Part9-Terraform-on-AWS.md)): the artifacts CodePipeline ultimately deploys are frequently these IaC templates, or application code that IaC-managed infrastructure runs.
- General familiarity with source control (Git) concepts, since CodePipeline's source stage typically integrates with CodeCommit, GitHub, Bitbucket, or a similar Git-based system.

## 4. Internal Working

- A CodePipeline **pipeline** is composed of an ordered sequence of **stages** (e.g., Source, Build, Test, Deploy), each containing one or more **actions** — an action is a specific unit of work (pull from a Git repo, run a CodeBuild project, deploy a CloudFormation change set, wait for manual approval).
- Stages execute **sequentially**; actions _within_ a stage can execute in **parallel** if there's no dependency between them — letting a pipeline run independent checks (e.g., a unit-test build and a separate security-scan build) concurrently within one stage rather than serially.
- **Artifacts** (the output of one stage, e.g., a compiled build) are passed between stages via S3, automatically managed by CodePipeline — each stage's actions declare their input and output artifacts, and CodePipeline handles the storage/retrieval plumbing.
- A pipeline is **triggered** automatically on a change to its configured source (a new commit to a branch, a new object in an S3 bucket, or on a schedule) — this event-driven triggering directly reuses the same EventBridge integration pattern covered in [§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md), since CodePipeline state changes and source triggers are themselves EventBridge-integrated events.
- **CodeBuild** executes within an ephemeral, containerized build environment (a specified base image, e.g., a standard AWS-managed Amazon Linux image with common language runtimes pre-installed, or a custom Docker image) that's provisioned fresh for each build and torn down afterward — no persistent build server to patch or maintain, and naturally parallel-scalable since AWS provisions as many concurrent build environments as needed.
- CodeBuild's behavior is defined by a **buildspec.yml** file (checked into the source repository, alongside the application code itself) specifying phases (`install`, `pre_build`, `build`, `post_build`) and the commands to run in each — directly analogous in spirit to a CI configuration file in any other CI system (GitHub Actions YAML, GitLab CI YAML), but AWS-native.

```
Source Change (Git commit) ──► EventBridge trigger ──► CodePipeline
                                                              │
                        ┌─────────────────────────────────────┼─────────────────────────────────────┐
                        ▼                                     ▼                                     ▼
                 Stage: Source                         Stage: Build                           Stage: Deploy
                 (pull from CodeCommit/                (CodeBuild runs buildspec.yml:          (CodeDeploy, CloudFormation,
                  GitHub/Bitbucket)                     install → pre_build → build →           or other deploy action —
                                                         post_build; produces artifact)          §84)
```

## 5. Architecture & Components

| Component                  | Explanation                                                                                                                                                                                                                                                               |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pipeline**               | The overall, ordered definition of stages a change flows through.                                                                                                                                                                                                         |
| **Stage**                  | A named phase (Source, Build, Test, Deploy) containing one or more actions, executed sequentially relative to other stages.                                                                                                                                               |
| **Action**                 | A specific unit of work within a stage — source pull, CodeBuild invocation, deployment, manual approval, and many others (including third-party integrations).                                                                                                            |
| **Artifact**               | The input/output data passed between stages, stored in S3 and managed automatically by CodePipeline.                                                                                                                                                                      |
| **CodeBuild Project**      | A reusable CodeBuild configuration (build environment image, buildspec source, compute size) that a pipeline's Build action invokes.                                                                                                                                      |
| **buildspec.yml**          | The file defining CodeBuild's build phases and commands, checked into the source repository.                                                                                                                                                                              |
| **Manual Approval Action** | A pipeline action that pauses execution until a designated approver explicitly approves (or rejects) continuation — the CodePipeline-native implementation of the approval-gate pattern discussed generically in [§86](./Section-86-Part9-CICD-Infrastructure-GitOps.md). |

## 6. Lifecycle / Workflow

1. **Define** the pipeline's stages and actions (via console, CloudFormation/CDK/Terraform — pipelines are themselves commonly IaC-managed, directly tying back to [§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](./Section-82-Part9-Terraform-on-AWS.md)).
2. A **source change** occurs (a commit, a new artifact), triggering the pipeline automatically via its configured source action's change-detection mechanism.
3. The **Source stage** retrieves the changed code/configuration.
4. The **Build stage** invokes a CodeBuild project, which provisions an ephemeral build environment, executes the buildspec's phases, and produces an output artifact (or fails, halting the pipeline).
5. Optional **Test stages** run additional validation (integration tests, security scans) against the build artifact.
6. Optional **Manual Approval actions** pause the pipeline for explicit human sign-off before proceeding, particularly before production deployment.
7. The **Deploy stage** executes the actual deployment (via CodeDeploy, CloudFormation, ECS, or another deploy action — [§84](./Section-84-Part9-CodeDeploy.md)-[§85](./Section-85-Part9-Deployment-Strategies.md) cover deployment specifically).
8. Pipeline execution status, per-stage/action detail, and history are available via the console/API for troubleshooting and audit.

## 7. Configuration

| Setting                                                                           | Purpose                                                                             |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Source action provider (CodeCommit, GitHub, S3, etc.) and change-detection method | What triggers the pipeline and how the trigger is detected (webhook vs. polling)    |
| CodeBuild environment image and compute size                                      | The build environment's base OS/runtime and CPU/memory allocation                   |
| buildspec.yml phases                                                              | The actual build/test commands executed                                             |
| Stage/action ordering and parallelism                                             | How the release process is structured                                               |
| Manual approval SNS notification                                                  | Alerts the designated approver when a pipeline execution is awaiting their sign-off |

⚠️ **Warning:** a CodeBuild project's IAM service role determines what the _build process itself_ can access — a build script that needs to pull a private dependency, write to a specific S3 bucket, or read a Parameter Store value ([§75](../Part8/Section-75-Part8-Systems-Manager.md)) needs that access explicitly granted to the CodeBuild role, and over-broad grants here are a genuine, easily overlooked security risk, since build scripts execute third-party dependency code (via package managers) that isn't necessarily fully trusted.

## 8. Commands (Full Documentation)

### `aws codepipeline create-pipeline`

- **Purpose:** Creates a new pipeline from a JSON pipeline definition.
- **Syntax:**
  ```
  aws codepipeline create-pipeline --cli-input-json file://pipeline-definition.json
  ```
- **Practical example (abbreviated definition):**
  ```json
  {
    "pipeline": {
      "name": "order-service-pipeline",
      "roleArn": "arn:aws:iam::123456789012:role/CodePipelineServiceRole",
      "stages": [
        {
          "name": "Source",
          "actions": [
            {
              "name": "Source",
              "actionTypeId": {
                "category": "Source",
                "provider": "CodeStarSourceConnection"
              },
              "outputArtifacts": [{ "name": "SourceOutput" }]
            }
          ]
        },
        {
          "name": "Build",
          "actions": [
            {
              "name": "Build",
              "actionTypeId": { "category": "Build", "provider": "CodeBuild" },
              "inputArtifacts": [{ "name": "SourceOutput" }],
              "outputArtifacts": [{ "name": "BuildOutput" }]
            }
          ]
        }
      ],
      "artifactStore": {
        "type": "S3",
        "location": "my-pipeline-artifacts-bucket"
      }
    }
  }
  ```
  **Expected output:** the created pipeline's full definition, confirming stage/action configuration.
- **Production usage:** pipelines are almost universally defined via CloudFormation/CDK/Terraform ([§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](./Section-82-Part9-Terraform-on-AWS.md)) rather than this raw CLI form, so the pipeline's own definition is itself version-controlled and reviewable — a direct, recursive application of this Part's own IaC principles to the CI/CD tooling itself.
- **Common errors:** the `roleArn` service role needs permissions for every action type the pipeline uses (S3 artifact access, CodeBuild invocation, deployment permissions) — an incomplete role produces action-level failures at the specific stage needing the missing permission, not an upfront validation error.

### `aws codebuild create-project`

- **Purpose:** Defines a reusable CodeBuild project (build environment configuration).
- **Syntax:**
  ```
  aws codebuild create-project --name <name> --source <JSON> --environment <JSON> --service-role <role-arn>
  ```
- **Practical example:**
  ```
  aws codebuild create-project --name order-service-build \
    --source '{"type": "CODEPIPELINE", "buildspec": "buildspec.yml"}' \
    --environment '{"type": "LINUX_CONTAINER", "image": "aws/codebuild/standard:7.0", "computeType": "BUILD_GENERAL1_SMALL"}' \
    --service-role arn:aws:iam::123456789012:role/CodeBuildServiceRole \
    --artifacts '{"type": "CODEPIPELINE"}'
  ```
  **Expected output:** the created project's configuration detail.
- **Important arguments:** `computeType` scales the build environment's CPU/memory — larger compute types reduce build time for resource-intensive builds (large compilations, extensive test suites) at proportionally higher per-minute cost, a direct, tunable cost/speed trade-off.
- **Production usage:** typically one CodeBuild project per distinct build/test workflow (unit tests, integration tests, security scanning might each be a separate project invoked from different pipeline stages), rather than one monolithic project doing everything.
- **Common errors:** a `buildspec.yml` with a syntax error, or referencing a phase command that fails, causes the build (and therefore that pipeline execution) to fail at the Build stage — CodeBuild's own logs (streamed to CloudWatch Logs, [§70](../Part8/Section-70-Part8-CloudWatch-Logs.md)) are the primary debugging tool for a failed build.
- **Security impact:** the `service-role` determines exactly what the build process can access; scope it narrowly to what the specific build genuinely needs (e.g., read access to a specific artifact bucket, not broad account-wide S3 access).

### `aws codepipeline start-pipeline-execution`

- **Purpose:** Manually triggers a pipeline execution (outside its normal automatic source-triggered flow).
- **Syntax:**
  ```
  aws codepipeline start-pipeline-execution --name <pipeline-name>
  ```
- **Production usage:** useful for re-running a pipeline against the current source state without requiring a new commit — for example, retrying after fixing a transient infrastructure issue unrelated to the code itself.
- **Common errors:** starting a new execution while a previous execution is still in progress on certain pipeline configurations can queue or supersede depending on the pipeline's execution mode settings — worth understanding your pipeline's specific concurrency configuration before assuming sequential, one-at-a-time behavior.

## 9. Hands-On Example — buildspec.yml for a Node.js Service with Tests

```yaml
version: 0.2

phases:
  install:
    runtime-versions:
      nodejs: 20
    commands:
      - npm ci
  pre_build:
    commands:
      - npm run lint
  build:
    commands:
      - npm run build
      - npm test
  post_build:
    commands:
      - echo "Build completed on $(date)"

artifacts:
  files:
    - "**/*"
  base-directory: dist
```

This buildspec demonstrates the standard phase progression: `install` sets up the runtime and dependencies, `pre_build` runs fast checks (linting) that should fail the build quickly if there's an obvious problem, `build` does the actual compilation and runs the test suite (a failing test here fails the entire build, halting the pipeline before any deployment is attempted), and `post_build` runs any final steps. The `artifacts` section tells CodeBuild what to package as output for the next pipeline stage — directly feeding into a subsequent Deploy stage ([§84](./Section-84-Part9-CodeDeploy.md)).

## 10. Production & Enterprise Usage

- **Startups** often adopt CodePipeline/CodeBuild specifically to avoid the operational overhead of self-hosting Jenkins or a similar CI system, particularly valuable for small teams without dedicated DevOps capacity.
- **Enterprises** build standardized, reusable pipeline templates (defined via CloudFormation/CDK, directly tying to [§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](./Section-82-Part9-Terraform-on-AWS.md)) that many teams' individual pipelines are instantiated from, ensuring consistent stage structure (mandatory security scanning, mandatory approval gates for production) across the organization — the same governance pattern discussed generically in [§86](./Section-86-Part9-CICD-Infrastructure-GitOps.md).
- CodeBuild is frequently used not just for application builds but for **infrastructure pipeline stages** themselves — running `cdk synth`, `terraform plan`, or `cloudformation validate-template` ([§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](./Section-82-Part9-Terraform-on-AWS.md)) as CodeBuild build steps within a broader CodePipeline orchestrating the full validate→plan→review→apply flow.
- Organizations already invested in third-party CI tools (GitHub Actions, GitLab CI, Jenkins) sometimes use those instead of CodePipeline/CodeBuild for the build/test portion while still using CodeDeploy ([§84](./Section-84-Part9-CodeDeploy.md)) for the AWS-native deployment portion — these AWS services are commonly composed with, not exclusively instead of, other CI/CD tooling.

## 11. Security Considerations

- CodeBuild's service role is a genuine security boundary — build scripts execute arbitrary code (including third-party dependencies pulled via package managers), so scoping this role tightly, and being aware that a compromised dependency could abuse whatever access the build role has, matters as much as scoping any other execution role in this roadmap.
- Manual approval actions should notify via SNS ([§61](../Part7/Section-61-Part7-SNS-PubSub-Messaging.md)) to an appropriately restricted group, and the IAM permission to actually approve/reject should be scoped to intended approvers only — directly implementing the separation-of-duties principle from [§86](./Section-86-Part9-CICD-Infrastructure-GitOps.md).
- Pipeline and CodeBuild execution history/logs may contain sensitive build output (though secrets should never be logged directly) — access to pipeline execution detail should be scoped appropriately.

## 12. Performance Considerations

- CodeBuild's ephemeral, on-demand environments mean build concurrency scales naturally — many pipeline executions (or many parallel actions within one pipeline) can each get their own build environment without manual capacity planning, unlike a fixed-size self-hosted build agent pool.
- Compute type selection is a direct build-speed/cost trade-off; profiling actual build resource usage (CPU/memory) and right-sizing the compute type is a legitimate cost-optimization lever ([§90](../Part10/Section-90-Part10-Cost-Optimization-FinOps.md)) for high-frequency build pipelines.
- Caching dependencies (via CodeBuild's built-in caching options, or artifact reuse between phases) meaningfully reduces build time for large dependency trees, avoiding a full fresh `npm ci`/`pip install` on every single build.

## 13. Monitoring

| Signal                                                                                                               | What it tells you                                                                     |
| -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Pipeline execution status/history                                                                                    | Success/failure per stage, the primary "did this release actually complete" signal.   |
| CodeBuild build logs (CloudWatch Logs, [§70](../Part8/Section-70-Part8-CloudWatch-Logs.md))                          | Detailed build/test output, the primary debugging tool for a failed build.            |
| EventBridge pipeline state-change events ([§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md)) | Real-time notification/automation on pipeline success, failure, or stage transitions. |

## 14. Troubleshooting

| Symptom                                              | Likely Root Cause                                                                                                                                                | Fix                                                                                                     |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Pipeline doesn't trigger on a new commit             | Source action's webhook/polling configuration isn't correctly connected to the repository                                                                        | Verify the source connection status and webhook configuration in the console                            |
| Build fails immediately                              | buildspec.yml syntax error, or a missing runtime/dependency in the specified build image                                                                         | Review CodeBuild logs in CloudWatch Logs for the specific failing command                               |
| Build succeeds locally but fails in CodeBuild        | Environment difference (missing environment variable, different runtime version, network access assumption that doesn't hold in the ephemeral build environment) | Compare the CodeBuild environment image/configuration against local development environment assumptions |
| Pipeline stuck awaiting manual approval indefinitely | Approver notification didn't reach the intended person, or nobody has the required approval IAM permission                                                       | Verify SNS notification delivery and approver IAM permissions                                           |

## 15. Best Practices

- Define pipelines as IaC (CloudFormation/CDK/Terraform) rather than manually via console, applying this Part's own IaC principles recursively to the CI/CD tooling itself.
- Scope CodeBuild service roles narrowly to what each specific build genuinely needs.
- Fail fast — order buildspec phases so cheap, quick checks (linting) run before expensive ones (full test suites, builds).
- Use manual approval actions specifically before production deployment stages, notifying via SNS to an appropriately scoped approver group.
- Right-size CodeBuild compute type based on actual profiled resource usage, not a default guess.

## 16. Anti-Patterns & Common Mistakes

- ❌ Granting an overly broad CodeBuild service role "to avoid permission errors," creating a meaningful security risk given build scripts execute third-party dependency code.
- ❌ Defining pipelines manually through the console without version-controlling the definition, losing the same review/audit benefits IaC provides for every other AWS resource in this roadmap.
- ❌ Running expensive test suites before cheap linting/syntax checks, wasting build minutes on builds that would have failed quickly anyway.
- **Common misconception:** "CodePipeline and CodeBuild are the same thing." False — CodePipeline is the orchestrator (defining stages and sequencing); CodeBuild is one specific action type (managed build/test compute) that a pipeline's Build stage commonly invokes, but a pipeline can also include entirely different action types (deployment, manual approval, third-party integrations) that have nothing to do with CodeBuild.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What's the difference between CodePipeline and CodeBuild?"_
**Model answer:** CodePipeline is the overall orchestration service — it defines the stages a release goes through, like source, build, test, and deploy, and automatically triggers and sequences them whenever a change occurs. CodeBuild is a specific managed service for compiling code and running tests, typically invoked as one action within CodePipeline's Build stage. CodePipeline doesn't do the actual building itself — it coordinates the process and delegates the actual build work to CodeBuild (or deployment work to CodeDeploy, and so on).

**🎯 Intermediate:** _"Why is CodeBuild's ephemeral build environment model considered an advantage over a traditional, persistent build server?"_
**Model answer:** A persistent build server needs to be patched, secured, and capacity-planned like any other piece of infrastructure, and if multiple builds need to run concurrently, you need to either queue them or maintain a whole fleet of build agents yourself. CodeBuild provisions a fresh, isolated build environment for each build and tears it down afterward, so there's no persistent server to maintain, no risk of one build's leftover state contaminating the next build, and concurrency scales automatically since AWS provisions as many parallel environments as needed rather than being limited by a fixed agent pool size.

**🎯 Senior:** _"A team's CodeBuild builds are passing consistently in isolation but occasionally failing when many pipelines run concurrently, with errors suggesting resource contention. How would you investigate?"_
**Model answer:** Since each CodeBuild build gets its own isolated, ephemeral environment, true resource contention between separate builds shouldn't happen at the compute level — so I'd first look at whether the builds are actually contending for something shared outside CodeBuild's own isolated environments, like a shared external resource (a rate-limited package registry, a shared test database, a shared S3 bucket being written to concurrently by multiple builds in a way that causes conflicts). I'd also check whether the account or specific CodeBuild projects have concurrent-build limits being hit, which would cause some builds to queue or throttle rather than genuinely fail, and I'd review the specific error messages from the failing builds' CloudWatch logs to distinguish between an actual external contention issue and a build-limit throttling issue, since the fix differs meaningfully between those two root causes.

**🎯 Architect:** _"Design a build/test pipeline architecture for an organization with 40 microservices, each with its own repository, ensuring consistent build standards across all of them without requiring each team to independently configure their own CodeBuild setup from scratch."_
**Model answer:** I'd build a small set of standardized, reusable CodeBuild project templates (defined via CDK or CloudFormation, [§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§81](./Section-81-Part9-AWS-CDK.md)) — likely one per major language/runtime the organization uses — encoding the organization's standard build environment image, common phases (install, lint, test, security scan), and default compute sizing, published as a shared, versioned module. Each of the 40 microservice teams' own pipeline definitions would then instantiate this shared module with their service-specific parameters (repository, any service-specific build commands) rather than hand-authoring their own CodeBuild configuration from scratch — directly mirroring the same shared-construct-library pattern discussed for CDK in [§81](./Section-81-Part9-AWS-CDK.md), applied here to CI/CD tooling rather than application infrastructure. I'd version the shared templates so improvements (a new mandatory security-scanning phase, an updated base image) roll out to all 40 teams through a controlled, trackable update to the shared module, and I'd keep the actual buildspec commands specific to each service's own repository, since the exact test/build commands genuinely do vary per service even while the surrounding structure (environment, phases, standards) stays consistent.

## 18. Common Misconceptions

- "CodeBuild requires you to manage its own compute infrastructure." False — this is precisely what CodeBuild eliminates; build environments are fully ephemeral and AWS-managed.
- "A pipeline can only have one action per stage." False — a stage can contain multiple actions, which run in parallel if there's no declared dependency between them via their input/output artifacts.

## 19. Key Takeaways

🔑 CodePipeline orchestrates a release process as ordered stages of actions; CodeBuild is one specific managed action type providing ephemeral, on-demand build/test compute.
🔑 buildspec.yml defines CodeBuild's phases (install, pre_build, build, post_build) — checked into the source repository alongside application code, exactly like any other CI configuration file.
🔑 Pipelines and CodeBuild projects should themselves be IaC-managed ([§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](./Section-82-Part9-Terraform-on-AWS.md)), applying this Part's own version-control and review discipline recursively to the CI/CD tooling.
🔑 CodeBuild's service role is a genuine security boundary, since build scripts execute third-party dependency code — scope it narrowly, as with any execution role.
🔑 Fail-fast phase ordering (cheap checks before expensive ones) and appropriate compute-type sizing are direct, practical build-pipeline optimization levers.

## 20. Related Concepts

- **CloudFormation, CDK, Terraform** (commonly both the artifacts a pipeline deploys, and the tools used to define the pipeline itself) → [§79](./Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](./Section-82-Part9-Terraform-on-AWS.md).
- **AWS CodeDeploy** (the deployment-stage action type most commonly following a CodeBuild build) → next section, [§84](./Section-84-Part9-CodeDeploy.md).
- **EventBridge** (the mechanism behind pipeline triggering and state-change notification) → [§62](../Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md).
- **CI/CD for Infrastructure** (the broader validate/plan/review/approve/apply discipline this section's pipeline mechanics implement) → [§86](./Section-86-Part9-CICD-Infrastructure-GitOps.md).
