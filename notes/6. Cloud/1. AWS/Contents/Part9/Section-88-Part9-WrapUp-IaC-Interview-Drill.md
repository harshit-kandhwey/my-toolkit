# Part 9, Section 10: Part 9 Wrap-Up + IaC Interview Drill

## 1. Part 9 Recap — What Was Covered

Part 9, Developer Tools, CI/CD & Infrastructure as Code, covered how the AWS resources taught throughout this entire roadmap are actually provisioned, deployed, and managed in real production environments — closing a forward reference running since Part 2:

1. **IaC Fundamentals & CloudFormation Basics** (§1) — templates, stacks, change sets, dependency resolution, rollback behavior.
2. **CloudFormation Advanced** (§2) — intrinsic functions, nested stacks, cross-stack references, StackSets, drift detection.
3. **AWS CDK** (§3) — real-programming-language infrastructure authoring, L1/L2/L3 constructs, synthesis to CloudFormation.
4. **Terraform on AWS** (§4) — provider-agnostic, multi-cloud IaC, state file architecture, plan/apply workflow.
5. **AWS CodePipeline & CodeBuild** (§5) — orchestrated, stage-based CI/CD pipelines and managed build/test execution.
6. **AWS CodeDeploy** (§6) — automated application deployment to EC2/on-premises, Lambda, and ECS.
7. **Deployment Strategies** (§7) — blue/green, canary, rolling, and all-at-once deployment patterns and their trade-offs.
8. **CI/CD for Infrastructure** (§8) — validate/plan/review/approve/apply pipeline discipline, GitOps, separation of duties.
9. **Choosing the Right IaC Tool** (§9) — the CloudFormation vs. CDK vs. Terraform decision framework.

## 2. Progressive Hands-On Labs (Beginner → Production-Style)

**Lab 1 (Beginner): First CloudFormation Stack**
Deploy §79's SQS+Lambda template from scratch; deliberately introduce a syntax error to see `validate-template` catch it; deploy successfully; then modify a property that forces resource replacement and review the resulting change set before applying. _Validates: §79._

**Lab 2 (Beginner-Intermediate): Nested Stacks and Drift Detection**
Refactor the Lab 1 template into a parent stack with a nested stack for the IAM role; deploy; manually modify the deployed queue's visibility timeout via the console; run drift detection and confirm it correctly identifies the manual change. _Validates: §80._

**Lab 3 (Intermediate): CDK Rewrite**
Rewrite the same SQS+Lambda pattern in CDK (Python or TypeScript), using the `grant_consume_messages` L2 convenience method; run `cdk synth` and compare the generated template against the hand-written §79 template; run `cdk diff` after a small change. _Validates: §81._

**Lab 4 (Intermediate): Terraform Rewrite with Remote State**
Rewrite the same pattern again in Terraform HCL; configure an S3 backend with DynamoDB locking for remote state; run `terraform plan` and `apply`; deliberately simulate a state lock conflict by attempting two concurrent applies. _Validates: §82._

**Lab 5 (Intermediate): CodePipeline with CodeBuild**
Build a CodePipeline with a source stage (CodeCommit/GitHub), a CodeBuild stage running unit tests and a build, and a manual approval stage before deployment; trigger it via a commit and observe the stage-by-stage execution. _Validates: §83._

**Lab 6 (Intermediate): CodeDeploy Blue/Green to EC2 or Lambda**
Configure CodeDeploy to perform a blue/green deployment of a simple application to either an EC2 Auto Scaling group or a Lambda function alias; deliberately introduce a failing health check and confirm CodeDeploy automatically rolls back. _Validates: §84-85._

**Lab 7 (Intermediate-Advanced): Basic Infrastructure CI/CD Pipeline**
Build a simple pipeline (any CI tool) implementing validate → plan → post-plan-as-PR-comment → manual approval → apply for one of the CloudFormation/CDK/Terraform templates from Labs 1-4; verify that applying uses the exact saved plan artifact, not a freshly recomputed one. _Validates: §86._

**Lab 8 (Production-Style, Capstone): Multi-Environment GitOps Promotion**
Extend Lab 7 into a full dev → staging → production promotion pipeline, with automatic deployment to dev, staging deployment gated on integration tests, and production gated on an explicit, separate human approver (enforcing separation of duties); document the tool choice rationale (CloudFormation, CDK, or Terraform) referencing §87's decision framework, and the deployment strategy rationale (from §7) for the production deployment stage. _Validates: §79-87 in combination._

## 3. Consolidated Key-Takeaways Checklist

- [ ] I can explain why CloudFormation's declarative, desired-state model is fundamentally different from an imperative script running CLI commands in sequence.
- [ ] I can explain what a change set shows and why reviewing it before applying matters, specifically regarding resource replacement.
- [ ] I can explain the difference between nested stacks (lifecycle-bound) and cross-stack references via Fn::ImportValue (fully independent).
- [ ] I can explain what StackSets provide beyond manually running create-stack many times, and the purpose of operation-preference gradual-rollout controls.
- [ ] I can explain why drift detection is on-demand, not continuous, and what it's for.
- [ ] I can explain the three CDK construct levels (L1/L2/L3) and give a concrete example of an L2 convenience method's value.
- [ ] I can explain why CDK is not a replacement for CloudFormation, but an authoring layer on top of it.
- [ ] I can explain Terraform's provider-agnostic architecture and why that's its defining differentiator.
- [ ] I can explain why Terraform's state file is a genuine operational risk CloudFormation/CDK don't share, and how remote backend + locking mitigates it.
- [ ] I can explain the stage-based CodePipeline model and how CodeBuild fits into it.
- [ ] I can explain how CodeDeploy's AppSpec file and deployment groups work together.
- [ ] I can explain the difference between blue/green, canary, and rolling deployments, and when each is appropriate.
- [ ] I can explain the validate → plan → review → approve → apply pipeline pattern and why applying the exact reviewed plan (not a freshly recomputed one) matters.
- [ ] I can explain what GitOps means precisely (repository as deployment trigger and source of truth), not just "using Git."
- [ ] I can explain why separation of duties needs to be technically enforced, not left to informal team norms.
- [ ] I can walk through the CloudFormation vs. CDK vs. Terraform decision tree (§87) from a cold requirement statement without prompting.
- [ ] I can name at least one legitimate hybrid/multi-tool IaC strategy and explain why it makes sense rather than forcing one universal tool choice.

## 4. Related Technologies (Beyond This Roadmap's Current Scope)

- **AWS Service Catalog** — lets organizations publish pre-approved, governed CloudFormation/Terraform templates for self-service provisioning by teams within guardrails, a natural extension for enterprises wanting to combine IaC flexibility with centralized governance.
- **Pulumi** — another real-programming-language IaC tool, conceptually similar to CDK's authoring model but (like Terraform) provider-agnostic and multi-cloud rather than CloudFormation-generating, worth exploring for teams wanting CDK's language-based authoring experience with Terraform's multi-cloud reach.
- **Policy-as-code tools** (AWS CloudFormation Guard, Open Policy Agent/Sentinel for Terraform) — automated policy enforcement integrated into the validate/plan pipeline stage, a natural extension of §86's pre-deployment security scanning discussion.
- **Kubernetes-native IaC and deployment** (Helm, Kustomize, Argo CD, or Terraform's Kubernetes provider) — relevant for organizations running significant workloads on Kubernetes/EKS, a natural extension beyond this roadmap's current AWS-service-centric scope.

## 5. Recommended Next Topics (Learning Path)

Having now completed Parts 7, 8, and 9 — Application Integration & Streaming, Observability & Monitoring, and Developer Tools/CI/CD/Infrastructure as Code — this roadmap has covered the full operational lifecycle of running production systems on AWS: how services communicate (Part 7), how you see what's happening and manage fleets (Part 8), and how you reliably build, deploy, and provision infrastructure (Part 9). Given the roadmap's overall structure and this Part's content specifically:

- **Part 10** (the roadmap's final Part) closes out remaining interview-critical topics — Well-Architected Framework, cost optimization, migration strategy, disaster recovery, application identity (Cognito), graph/ML tie-ins, system design, and final interview preparation — synthesizing the full roadmap into final interview readiness.
- Beyond this roadmap: **AWS Service Catalog and policy-as-code tools** (extending Part 9's governance themes) and **Kubernetes-native IaC/deployment** (for organizations running EKS-based workloads) are natural extensions for anyone specializing further in platform engineering.
