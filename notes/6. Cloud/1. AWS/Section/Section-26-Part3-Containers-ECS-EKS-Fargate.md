# Part 3 · Section 8 — Containers: ECS, EKS & Fargate

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** A container packages an application and everything it needs into one portable unit that runs identically anywhere. AWS offers two ways to orchestrate many containers (ECS, or Kubernetes via EKS) and two ways to host them (your own EC2 instances, or Fargate's serverless container compute).

**Precise:** **ECS** and **EKS** are container orchestration platforms — they schedule, scale, manage containerized applications. **Fargate** is a serverless compute engine for containers, usable with either ECS or EKS, removing the need to provision/manage underlying EC2 instances.

---

## 2. Why This Category Exists

- **Containers solve portability/consistency** — "works on my machine" failures happen because runtime environments differ; a container bundles everything together — a more granular evolution of golden-image consistency (Section 2), for applications not whole servers.
- **Orchestration solves "now I have hundreds of containers"** — reliably running many across hosts, restarting failures, load balancing, rolling updates — what ASG (Section 5) does for instances, at the container level with more sophisticated placement.
- **Fargate solves "I don't want to manage the EC2 instances underneath"** — extends Section 7's serverless philosophy to containers.

---

## 3. Containers vs Virtual Machines

- A **VM** virtualizes the entire hardware/OS stack — own full kernel, heavyweight but strongly isolated.
- A **container** virtualizes at the OS level — shares the host's kernel, own isolated filesystem/process/network namespace — far lighter (seconds to start) but weaker isolation than a VM (kernel is shared).
- ECS/EKS containers ultimately run on **EC2 instances you manage** (multiple containers share one instance's kernel, denser packing) or **Fargate** (AWS manages the host entirely).

---

## 4. Amazon ECS

### 4.1 Definition

AWS's own proprietary container orchestration service — simpler and more tightly AWS-integrated than Kubernetes, but AWS-specific.

### 4.2 Core Concepts

- **Task Definition** — JSON blueprint (analogous to a Launch Template, Section 4 §6) specifying image(s), CPU/memory, networking mode, IAM roles, config.
- **Task** — a running instance of a Task Definition (can contain multiple tightly-coupled containers).
- **Service** — maintains N running tasks, replaces failures, integrates with a load balancer — analogous to an ASG (Section 5) but for tasks.
- **Cluster** — logical grouping of infrastructure (EC2 or Fargate) tasks run on.

### 4.3 ECS Launch Types

- **EC2 launch type** — tasks on your own provisioned/managed EC2 instances (via an underlying ASG) — more control, often lower steady-state cost, you manage instances.
- **Fargate launch type** — tasks on AWS-managed infrastructure, no EC2 to provision/patch — specify CPU/memory per task, trade control for zero infra management.

---

## 5. Amazon EKS — Managed Kubernetes

### 5.1 Definition

AWS's managed Kubernetes — the industry-standard, open-source, portable orchestration platform; EKS runs the control plane while integrating AWS-native services (IAM, VPC, load balancers).

### 5.2 EKS vs ECS

- **Portability** — Kubernetes is far more portable across clouds/on-prem than ECS's AWS-specific model.
- **Ecosystem** — massive mature open-source ecosystem (tools, operators, community, existing expertise).
- **Complexity trade-off:** Kubernetes is genuinely more complex (Pods, Deployments, Services, Ingress, more) — steeper learning curve. AWS guidance: teams with existing Kubernetes investment/multi-cloud need should use EKS; teams without it often find ECS's simpler model sufficient.

### 5.3 EKS Compute Options

- EC2-based worker nodes (self-managed or **EKS Managed Node Groups**) or **Fargate** — same host-management choice as ECS.

> 🎯 ECS: simpler, AWS-integrated, proprietary. EKS: Kubernetes, complex, portable, ecosystem-backed. Choose EKS for portability/multi-cloud/existing investment; ECS for AWS-committed simplicity.

---

## 6. AWS Fargate — Serverless Containers

### 6.1 Definition

Serverless compute engine for containers (ECS or EKS) — removes provisioning/patching/scaling of underlying EC2 instances; specify CPU/memory per task/pod.

### 6.2 Why It Exists

- Extends Section 7's "not managing servers" value to containers — a middle ground between Lambda's function-level abstraction and EC2-based ECS/EKS's instance-level control.
- **Trade-off (parallel to Provisioned Concurrency, Section 7 §3.3):** Fargate typically costs more per unit of compute than equivalent EC2 capacity, in exchange for eliminated instance management — the recurring "pay more for less operational burden" pattern from Part 1 §5.

### 6.3 Fargate vs EC2-Based Containers

- **Fargate:** variable/unpredictable workloads, minimize operational overhead, cost premium justified by reduced burden.
- **EC2-based:** steady-state, high-density, cost-sensitive workloads, or needing specific instance-level control (GPUs, placement groups) Fargate doesn't expose.

---

## 7. Container Registries — Amazon ECR

- **ECR** — AWS's managed container image registry, storing/versioning images pulled at task/pod launch — analogous to AMIs (Section 2) but for container images.
- **Image scanning** — integrates with vulnerability scanning (Part 2 §8 Inspector), extending supply-chain-security to the container image layer.
- **Private by default**, IAM-based access control; a repository resource-based policy can grant cross-account pull access — same pattern as S3/KMS/Secrets Manager sharing (Part 2).

---

## 8. Task/Pod Networking and IAM

- **Task-level IAM roles (ECS)** — each task can have its own role, distinct from the EC2 instance's role, meaning multiple tasks on one instance can have different scoped permissions — finer-grained than a single instance-wide role.
- **IRSA (EKS)** — Kubernetes service accounts mapped to IAM roles, giving individual pods scoped AWS permissions rather than sharing the node's role.
- **`awsvpc` networking mode (ECS)** — each task gets its own ENI (Section 4 §3), own private IP and security group — security groups scoped per task, not just per instance.

---

## 9. Production & Enterprise Usage

- **ECS + Fargate** — common starting point for teams adopting containers without deep Kubernetes investment — production-grade, operationally simpler than EKS.
- **EKS for multi-cloud strategy/existing Kubernetes expertise** — often chosen by platform teams building shared internal platforms leveraging Kubernetes' ecosystem (Helm, operators, service mesh).
- **Mixed EC2/Fargate within one cluster** — both ECS and EKS support this, letting cost-sensitive steady-state workloads run on EC2 and bursty ones on Fargate — mirrors Section 3's mixed-purchasing philosophy at the orchestration layer.
- **CI/CD → ECR → ECS/EKS deployment** — standard containerized delivery pipeline (full depth Part 9).

---

## 10. Security Considerations

- **Task/pod-level least privilege** (§8) is meaningfully more granular than instance-level IAM — default for multi-tenant clusters with varied permission needs.
- **ECR scanning should gate deployment** — block deployment of images with unresolved critical/high vulnerabilities, connecting Part 2 §8's Inspector theme to the deployment pipeline.
- **Fargate's shared-nothing-per-task isolation** generally offers stronger isolation than co-locating many containers on one self-managed instance's shared kernel — a security consideration alongside the cost/control trade-off.

---

## 11. Performance Considerations

- **Container startup (seconds)** is meaningfully faster than EC2 instance boot, though slower than a warm Lambda invocation — a real middle ground on the cold-start-latency spectrum.
- **EC2-based density** — packing containers onto fewer larger instances can achieve better utilization/lower cost than Fargate's per-task billing for steady workloads — connects to Section 2 §9's right-sizing, now at "containers per instance" granularity.

---

## 12. Troubleshooting

| Symptom                                                         | Cause                                                                                           | Fix                                                                                                |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| ECS task stuck in PENDING                                       | Insufficient cluster capacity (EC2), or task definition references an unpullable image/resource | Check cluster capacity; verify ECR image URI and pull permissions                                  |
| Task starts then immediately stops                              | App crashes on startup, or missing/misconfigured env var/secret                                 | Check CloudWatch Logs for the actual application error                                             |
| Containers on the same instance access resources they shouldn't | Instance-wide role too broad, not using task-level roles                                        | Configure per-task IAM roles                                                                       |
| ECS vs EKS decision causing analysis paralysis                  | Over-indexing on Kubernetes reputation without an actual portability need                       | Default to ECS unless a concrete reason (existing investment, real multi-cloud need) justifies EKS |

---

## 13. Best Practices & Anti-Patterns

**Best practices:** use task/pod-level IAM roles for genuine least privilege; scan ECR images and gate deployment on results; default to ECS for AWS-committed teams without Kubernetes investment; mix Fargate and EC2 capacity to match cost-sensitivity to workload predictability; use `awsvpc` mode for per-task network isolation.

**Anti-patterns:** defaulting to EKS "because it's the industry standard" without a real requirement; relying solely on instance-wide IAM roles in multi-tenant clusters; deploying unscanned images to production; treating Fargate as strictly better/worse rather than a per-workload trade-off.

---

## 14. Common Misconceptions

- "Containers and VMs provide the same isolation." → False — containers share the host kernel, generally weaker isolation than a full VM.
- "Fargate is always more expensive, so EC2-based is always better." → Oversimplified — Fargate's premium buys eliminated operational overhead, a genuine trade depending on predictability and team capacity.
- "ECS and EKS are the same thing with different names." → False — proprietary/simpler vs managed Kubernetes/portable/complex, a real architectural choice.
- "Containers on one instance automatically share permissions." → False if task-level IAM (ECS) or IRSA (EKS) is used — each can have distinct scoped permissions despite sharing the host.

---

## 15. Interview Questions (with model answers)

**🟢 Container vs virtual machine?** VM virtualizes the entire hardware/OS stack with its own kernel — heavyweight, strongly isolated. Container virtualizes at the OS level, sharing the host kernel with its own isolated filesystem/process space — lighter, faster to start, somewhat weaker isolation since the kernel is shared.

**🟢 What does Fargate actually do?** Serverless compute engine for containers (ECS or EKS), removing the need to provision/manage underlying EC2 instances. Specify CPU/memory per task/pod; Fargate handles infrastructure — extends Lambda's "don't manage servers" idea to containers.

**🟡 When would you choose EKS over ECS?** Portability matters (genuine multi-cloud/on-prem need, since Kubernetes is far more portable than ECS's proprietary model), or existing Kubernetes expertise/ecosystem leverage. Without a concrete reason, ECS's simpler model is the better default for AWS-committed teams, given Kubernetes' real added complexity.

**🟡 How does task-level IAM in ECS improve on instance-level roles?** Instance-level roles mean every container on that instance shares the same permissions regardless of actual need — broad blast radius. Task-level roles let each task have distinct scoped permissions even sharing one instance — least privilege applied at finer grain, important for multi-tenant clusters.

**🔴 Design a container platform for a monolith-to-microservices migration, considering cost, operational overhead, and future portability?** Default to ECS (no existing Kubernetes investment/multi-cloud requirement), using Fargate initially for most services to minimize operational burden while learning the model and refining boundaries — accepting the cost premium during the less-predictable transition. As services stabilize into steady high-density traffic, evaluate moving those to EC2-based ECS for cost efficiency, keeping bursty services on Fargate — mixed capacity, not all-or-nothing. Use task-level IAM roles from day one (harder to retrofit later). Revisit EKS only if a genuine future portability requirement emerges, rather than pre-optimizing for a non-existent need.

**🔴 Enforce no critical-vulnerability image ever reaches production across dozens of ECS microservices?** Enable ECR scanning on every repo; CI/CD pipeline explicitly checks scan results before deploying, auto-failing on unresolved critical/high vulnerabilities rather than manual dashboard checks. Centralize as a shared pipeline template/reusable component across all services, not per-team discretion. Feed ECR scan findings into Security Hub for an aggregated ongoing view — catching newly-disclosed CVEs in already-deployed images that a deploy-time-only gate would miss.

---

## 🔑 Key Takeaways

1. Containers share the host OS kernel (unlike VMs' full-OS-per-instance) — lighter/faster but weaker isolation, relevant to multi-tenant security decisions.
2. ECS (proprietary, simpler) and EKS (managed Kubernetes, portable, complex) are a real architectural choice — default to ECS without a concrete portability/expertise reason for EKS.
3. Fargate extends Lambda's "don't manage servers" philosophy to containers — usable with either ECS or EKS, trading cost premium for eliminated instance management, evaluated per workload.
4. Task/pod-level IAM (ECS task roles, EKS IRSA) provides finer-grained least privilege than instance-wide roles — essential for multi-tenant clusters.
5. ECR scanning should gate deployment, and findings should feed ongoing detection (Security Hub) — a one-time scan doesn't catch vulnerabilities disclosed after deployment.

## 🌐 Related Concepts (forward links)

- Elastic Beanstalk, Batch, Lightsail — higher-abstraction/specialized compute → Part 3, Section 9 (next)
- CI/CD pipelines building/deploying container images → Part 9
- VPC networking for ECS/EKS (awsvpc mode, private subnets) → Part 4
- Step Functions and event-driven patterns triggering ECS tasks → Part 7
