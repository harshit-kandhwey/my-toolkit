# Section 104 (Part 14): System Design Questions Involving Containers

## 1. Definition

**Plain language:** A container system-design question asks you to design (or evolve) a real platform: "containerize this monolith", "design a CI/CD pipeline for 50 services", "run a multi-tenant build farm", "make our deploys zero-downtime". There is no single right answer; the interviewer scores how you gather requirements, choose components, justify trade-offs, and handle failure.

**Precise definition:** A containers-focused design answer follows a repeatable arc: **requirements** (functional, scale, availability, compliance, team skills), **constraints and assumptions** stated aloud, **high-level architecture** (build, registry, runtime, networking, storage, observability), **deep dives** on two or three risky components, **failure modes and recovery**, **security**, **cost**, and **evolution** (what you would change at 10x). Docker-specific depth means knowing when a single Docker host plus Compose is enough, when Swarm fits, and when to move to Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

> 💡 **Tip:** Spend the first five minutes on questions and numbers. "How many requests per second, how stateful, what RTO/RPO, who operates it?" often decides the entire architecture.

## 2. Why This Matters

- Senior and architect interviews are dominated by design rounds; containers are the default substrate for nearly every modern design.
- It tests judgment: the best answer is often the simplest platform that meets the requirements, not the most fashionable.
- Design questions integrate every earlier Part: images and registries, networking, storage, security, CI/CD and operations.
- Real design work uses the same method as the interview: write the assumptions down, decide, and record trade-offs (an ADR).

## 3. Prerequisites and Dependencies

You need the whole stack at overview level: engine internals ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), networking ([§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md), [§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)), state ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)), security ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), registries ([§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](../Part9/Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)), pipelines ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)), and operations ([§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md), [§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md), [§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). Platform-choice reasoning is in [§97](../Part13/Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md).

## 4. Architecture / Conceptual Diagram

```text
              ANSWER FRAMEWORK (time-boxed to roughly 45 minutes)

  1. Clarify (5)   ──► users, RPS, data size, state, SLO, RTO/RPO, compliance, team
  2. Sketch (10)   ──► boxes: client ► edge ► services ► data;  build ► registry ► runtime
  3. Deep dive (15)──► pick 2-3: deploys, state, networking, scaling, security
  4. Failure (8)   ──► host dies, registry down, bad image, noisy neighbor, region loss
  5. Evolve (5)    ──► 10x load, multi-region, compliance, cost
  6. Summarize (2) ──► decisions + trade-offs + what you would measure

  Reference platform (generic containerized web system)

   dev ──git push──► CI ──build/scan/sign──► Registry (immutable tags + digests)
                       │                          │
                       │ tests in ephemeral       │ pull by digest
                       │ containers               ▼
                       ▼                   ┌───────────────────────────────┐
                 promote tag ──GitOps──►   │ Runtime hosts / cluster       │
                                           │  ┌───────┐  ┌───────┐         │
   Users ──► LB / CDN ──► Reverse proxy ──►│  │ api   │  │ web   │ ...     │
                          (TLS, routing)   │  └───┬───┘  └───────┘         │
                                           │      │ private network        │
                                           │  ┌───▼────┐  ┌───────────┐    │
                                           │  │ worker │  │ cache     │    │
                                           │  └───┬────┘  └───────────┘    │
                                           └──────┼────────────────────────┘
                                                  ▼
                              Managed DB / queue / object store  (state OUTSIDE containers)

   Cross-cutting:  logs ► central store    metrics ► Prometheus    traces ► collector
                   secrets ► vault/secret store    policy ► admission/scan gates
```

- State lives outside the container fleet (managed services or dedicated replicated stores); containers stay replaceable.
- Images are built once, promoted by digest across environments, never rebuilt per environment ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)).
- A reverse proxy or load balancer fronts everything and enables rolling or blue-green rollouts.

## 5. Hands-On

Each design below gives the requirements to extract, the recommended architecture, and the trade-off discussion. The small commands show how you would prototype the key mechanism.

### 5.1 Design 1: Containerize a Legacy Three-Tier Monolith

**Requirements to extract:** Is the app stateless? Does it write local files? Config via files or environment? Session handling? Start-up time? Compliance? Can it be split later?

**Approach:** "Lift, harden, then split."

1. **Containerize as-is** with a multi-stage Dockerfile, non-root user, health endpoint, and config from environment variables ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)).
2. **Externalize state:** sessions to Redis, uploads to object storage, database to a managed service; any remaining local data on a named volume with a documented backup ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md), [§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).
3. **Run two or more replicas** behind a proxy for availability; verify they tolerate being restarted at any time.
4. **Strangle gradually:** peel off bounded contexts (auth, reporting) into separate images only when there is team or scaling pressure.

```bash
# prototype: two replicas behind a proxy on one host
docker compose up -d --scale app=2
docker compose ps
curl -s localhost:8080/healthz
```

**Trade-offs:** Containerizing a monolith improves reproducibility and deploy speed immediately but does not by itself deliver microservice benefits; avoid splitting before the operational platform exists.

### 5.2 Design 2: Zero-Downtime Deployments for a Stateless API

**Requirements:** SLO 99.95 percent, deploys several times a day, rollback in under 2 minutes, database schema evolves.

**Architecture:** Rolling or blue-green behind a load balancer with health-gated promotion ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).

- New version starts alongside the old; the proxy shifts traffic only after the readiness probe passes.
- Graceful shutdown: SIGTERM handler drains in-flight requests, `stop_grace_period` exceeds the longest request, deregistration from the proxy happens before termination ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).
- **Expand/contract migrations:** add columns first (backward compatible), deploy, then remove old columns in a later release so old and new versions can coexist.
- Rollback is "point back at the previous digest", which is only possible if tags are immutable and old images are retained ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).

```bash
docker service update --image registry.example.com/api@sha256:... \
  --update-order start-first --update-failure-action rollback \
  --update-delay 10s api          # Swarm example: start-first, auto-rollback
```

### 5.3 Design 3: CI/CD Pipeline for 50 Services

**Requirements:** build under 10 minutes, supply-chain assurance, promotion dev to staging to prod, audit trail.

**Pipeline:**

```text
PR ► lint (hadolint, build --check) ► unit tests ► build (BuildKit, registry cache)
   ► integration tests in ephemeral Compose ► scan (Trivy) ► SBOM + sign (cosign)
   ► push :sha-<commit> ► [merge] ► GitOps repo PR bumps digest ► deploy dev
   ► automated smoke ► promote same digest to staging ► approval ► prod
```

- **Builders:** ephemeral rootless BuildKit runners or a remote `buildx` builder; avoid mounting the host Docker socket into untrusted jobs ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **Caching:** registry-backed cache (`--cache-to type=registry`) and dependency cache mounts ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)).
- **Registry:** immutable tags, per-environment repositories or promotion by retagging the same digest, retention rules, Hub mirror for base images ([§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)).
- **Governance:** admission policy that only runs signed images from the approved registry ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Monorepo scaling:** path filters so only changed services build; shared base images rebuilt on a schedule.


### 5.4 Design 4: Multi-Tenant Build or Code-Execution Platform

**Requirements:** run untrusted user code in containers, isolation between tenants, abuse resistance, fair resource sharing.

**Key insight:** containers are not a strong security boundary against hostile code on a shared kernel ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)). Layer defenses:

- **Stronger isolation runtimes:** gVisor (`runsc`) or Kata Containers/microVMs, selected per workload via `--runtime`.
- **Hardening:** rootless engine or user namespaces, `--cap-drop=ALL`, default or tighter seccomp, `--read-only`, `--network none` or egress allow-list, `no-new-privileges` ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§60](../Part8/Section-60-Part8-Seccomp-Profiles.md)).
- **Resource fairness:** hard `--memory`, `--cpus`, `--pids-limit`, disk quotas on the writable layer, wall-clock timeouts ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)).
- **Lifecycle:** one-shot containers, destroyed after each job; separate hosts per trust tier; ephemeral volumes only.

```bash
docker run --rm --runtime=runsc --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --memory 256m --cpus 0.5 --pids-limit 128 --tmpfs /tmp:rw,size=64m \
  --user 65534:65534 runner:pinned run-job
```

## 6. Production Usage Notes

- **Choose the smallest platform that works:** a handful of services on one or two hosts is well served by Compose plus a reverse proxy and systemd; Swarm adds simple multi-host scheduling; Kubernetes pays off with many teams, autoscaling and a rich ecosystem ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md), [§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).
- **Capacity planning:** size from measured per-container requests/limits, keep 20 to 30 percent headroom, and plan for N+1 host failure ([§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)).
- **Disaster recovery:** define RTO and RPO per tier, back up registries (or replicate), volumes and infrastructure-as-code, and test restores ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)).
- **Network design:** one user-defined network per trust zone, only the proxy publishes ports, east-west traffic restricted by network membership or policy ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).

## 7. Security Considerations

- **Threat-model each design** with trust boundaries: internet to proxy, proxy to services, services to data, CI to registry, registry to hosts.
- **Supply chain:** pinned and scanned bases, SBOMs, signatures verified at deploy time, restricted push rights ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Secrets:** delivered at runtime from a secret manager or file mounts, short-lived credentials, rotation process; never baked into images or Compose files in git ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Host and daemon:** protect `/var/run/docker.sock` (it is root), keep the daemon on a minimal hardened OS, enable rootless where feasible, and patch the kernel and runc promptly ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Least privilege by default:** non-root, dropped capabilities, read-only root filesystem, no host namespaces, no privileged containers.

## 8. Common Troubleshooting Scenarios

Design questions often include a twist; these are the follow-ups and the architectural response.

| Twist from interviewer | What it exposes | Response |
|---|---|---|
| "The registry goes down during a deploy" | Single point of failure | Hosts keep running (images are local); use pull-through caches, registry HA or replication; pre-pull before the deploy window |
| "A bad image reached production" | No gate or rollback | Health-gated rollout with auto-rollback, canary metrics, signed-image admission, keep prior digests |
| "Docker Hub rate-limits CI" | External dependency | Authenticated pulls, mirror/pull-through cache, vendor base images into private registry ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)) |
| "Logs filled the disk and took the host down" | Default `json-file` unbounded | Rotation in `daemon.json`, central shipping, disk alerts |
| "A CVE is announced in your base image" | Patch workflow | Inventory via SBOM, rebuild all dependents from updated base, staged rollout, SLA by severity |

## 9. Best Practices

- State assumptions and trade-offs explicitly; keep state out of containers; build once and promote by digest; define health, limits and shutdown for every service; design for failure; prefer managed services for undifferentiated work; plan the evolution path; close with SLO-style metrics.

## 10. Common Anti-Patterns / Mistakes

- Jumping to Kubernetes for a three-service app with one operator.
- Designing the happy path only; no failure, rollback or capacity discussion.
- Running databases in containers on a single node with no backup test and calling it HA.
- Rebuilding images per environment so production runs untested bits.
- Mounting the Docker socket into CI jobs and tenant workloads.
- Treating containers as a security boundary for hostile code with no sandbox runtime.
- Using `latest` or mutable tags as the deploy reference.
- Putting secrets in environment variables of images or in the Compose file under version control.
- Not asking about team size and skills; the best architecture is one the team can operate.

## 11. Interview Questions

**🎯 Beginner:** _"Explain how you would run a small web application with a database using containers for a startup with one developer."_
**Model answer:** I would write a Compose file with the app, a reverse proxy for TLS, and either a managed database or a Postgres container on a named volume with nightly backups to object storage. Only the proxy publishes ports; the app and database share a private user-defined network. The app image is built in CI with a multi-stage Dockerfile, pushed to a registry with a commit-SHA tag, and deployed by pulling that tag and running `docker compose up -d`. I add restart policies, health checks, log rotation, and secrets from files rather than the repository. This keeps the platform simple enough for one person to operate, with a clear path to a managed database or an orchestrator later.
_What the interviewer is probing for:_ Right-sized choices, network and port hygiene, and basic operational habits (backups, health, secrets).

**🎯 Intermediate:** _"Design the deployment strategy for an API that must never drop requests during releases."_
**Model answer:** I would run at least two replicas behind a load balancer or proxy with readiness checks, and deploy by starting new containers first, waiting for readiness, shifting traffic, then draining the old ones. The application handles SIGTERM by finishing in-flight requests, and the stop grace period exceeds the longest request. Database changes follow expand/contract so old and new versions run together. Releases reference immutable image digests, so rollback is redeploying the previous digest, and I automate rollback when error rate or latency crosses a threshold during the rollout. For higher risk, I add a canary that takes 5 percent of traffic first. I would test the process by killing containers during load in staging.
_What the interviewer is probing for:_ Connection draining, backward-compatible schema changes, immutable references and automated rollback.

**🎯 Senior:** _"You are asked to build a platform that executes customers' untrusted code in containers. Walk through your isolation and abuse-prevention design."_
**Model answer:** I start from the premise that a shared kernel is a weak boundary against hostile code, so I use a sandboxed runtime (gVisor or Kata microVMs) on dedicated hosts that hold no other workloads or credentials. Each job runs as a one-shot rootless container with all capabilities dropped, `no-new-privileges`, a tight seccomp profile, a read-only root, a small tmpfs, no network by default and an egress allow-list when needed, and strict memory, CPU, PID and wall-clock limits. Metadata endpoints are blocked, the Docker socket is never exposed, and images are curated or scanned. Orchestration is separate from execution: a control plane enqueues jobs and workers pull them. I add per-tenant quotas, anomaly detection on CPU and network, and kill switches. Blast radius is limited by tenant-tiered host pools and short host lifetimes, and I run periodic escape-testing and keep the kernel and runtime patched.
_What the interviewer is probing for:_ Understanding the limits of container isolation, defense in depth, and operating-model controls beyond flags.

**🎯 Architect:** _"A company with 40 teams wants a standard container platform. Some want Docker Compose on VMs, some want Kubernetes. How do you decide and roll it out?"_
**Model answer:** I would start with the data: workload types, scale, statefulness, compliance, team skills and existing cloud commitments. The unifying standard is the artifact, not the runtime: OCI images built from golden Dockerfiles, signed and stored in one registry, with a shared contract for health, logging, config and shutdown. On top, I would offer tiers: a simple path (managed container service or Compose on hardened VMs) for small stateless apps, and a Kubernetes-based platform with paved-road templates for teams needing autoscaling, multi-service dependencies or advanced traffic control. Teams choose the simple path by default and graduate with a documented checklist, so the migration cost is limited to deployment manifests. I would fund a platform team with SLOs, self-service pipelines, policy-as-code gates, cost visibility and a deprecation policy, and measure adoption, deploy frequency, change-failure rate and platform toil. A pilot with two representative teams precedes the broad rollout, and ADRs capture the decisions and revisit triggers.
_What the interviewer is probing for:_ Organizational thinking: standardize artifacts and contracts, offer tiers, avoid forcing one tool, and measure outcomes.

## 12. Common Misconceptions

- "Containers always mean microservices." A containerized monolith is valid and often wise.
- "Kubernetes is the default answer." It is one option with a high operating cost.
- "Containers give VM-level isolation." They share the host kernel.
- "Stateful workloads cannot run in containers." They can, with careful storage and replication; the question is whether you should self-host.
- "More replicas mean high availability." Replicas on one host share its failure; spread them and remove shared single points of failure.

## 13. 🔑 Key Takeaways

- Follow an arc: clarify, sketch, deep dive, failure, evolve, summarize.
- Pick the smallest platform that meets the requirements; justify moving up.
- Keep state out of containers, build once and promote by digest.
- Zero downtime needs readiness gates, graceful drain, expand/contract schemas and immutable rollbacks.
- Untrusted code needs sandboxed runtimes plus hardening plus limits, not Docker flags alone.
- Always cover failure modes, security, cost and an evolution path.
- Name the trade-off in every decision.

## 14. Related Concepts & What's Next

Related: orchestration path ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)), when Docker is the wrong tool ([§97](../Part13/Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md)), zero-downtime patterns ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)), GitOps promotion ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)), and resource management at scale ([§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)). Next, [§105](Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank.md) provides a bank of hands-on whiteboard and live-coding exercises to practice the same skills under time pressure.

**Next Section:** [§105](Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank.md) — `Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank.md`
