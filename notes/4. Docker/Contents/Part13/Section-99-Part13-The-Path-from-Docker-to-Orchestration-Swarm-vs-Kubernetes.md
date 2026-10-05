# Section 99 (Part 13): The Path from Docker to Orchestration (Swarm vs. Kubernetes)

## 1. Definition

**Plain language:** Docker runs containers on one machine. An **orchestrator** runs them across many machines: it decides where each container goes, restarts the ones that die, rolls out new versions, wires up networking and load balancing, and keeps the real state matching the state you declared. Docker Swarm and Kubernetes are the two orchestrators most people compare.

**Precise definition:** Orchestration is a **reconciliation loop** over declared desired state. You submit a specification (a Swarm stack file or Kubernetes manifests); a control plane stores it in a consistent store (Raft-replicated in both systems; Kubernetes uses etcd), schedulers place tasks or Pods onto nodes, and agents on each node (the Swarm worker agent, the kubelet) drive the local runtime (containerd and runc, see [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)) until observed state equals desired state. Swarm mode is built into `dockerd`; Kubernetes is a separate, extensible platform that talks to runtimes through the CRI ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).

> 💡 **Tip:** Treat the move to orchestration as a change of mental model, not of tools: from "run this container" to "keep N copies of this workload healthy, reachable and current".

## 2. Why This Matters

- A single Docker host (even with Compose, [§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)) is a single point of failure and a hard capacity ceiling.
- The industry default for production containers is Kubernetes, usually managed (EKS, AKS, GKE). Docker skills transfer directly, but the vocabulary changes.
- Swarm is still examined in the DCA ([§100](../Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)) and remains a pragmatic choice for small estates.
- Knowing where the Docker boundary ends (image, registry, runtime) and where orchestration starts (scheduling, service discovery, rollout) prevents both premature adoption and painful bolt-on solutions.

## 3. Prerequisites and Dependencies

Solid grounding in images and registries ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md), [§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)), Compose ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), overlay networking ([§46](../Part6/Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), health checks and self-healing ([§88](../Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), and zero-downtime deployment ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)). The Swarm primer is [§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md).

## 4. Architecture / Conceptual Diagram

```text
   Docker Swarm (built into dockerd)              Kubernetes (separate platform)
  ┌───────────────────────────────┐        ┌────────────────────────────────────────┐
  │ Managers (Raft, 3 or 5)       │        │ Control plane                          │
  │  orchestrator, allocator,     │        │  kube-apiserver ◄──► etcd              │
  │  scheduler, dispatcher        │        │  scheduler, controller-manager         │
  └──────────────┬────────────────┘        └──────────────────┬─────────────────────┘
                 │ tasks (gRPC, mTLS)                         │ watch/list (HTTPS)
        ┌────────▼────────┐                       ┌───────────▼───────────┐
        │ Worker: dockerd │                       │ Node: kubelet         │
        │  └ containerd   │                       │  └ containerd / CRI-O │
        │     └ runc      │                       │     └ runc            │
        └─────────────────┘                       │ kube-proxy + CNI      │
                                                  └───────────────────────┘

  Vocabulary map
  ┌───────────────────────┬──────────────────────────────────────────────┐
  │ Swarm                 │ Kubernetes                                   │
  ├───────────────────────┼──────────────────────────────────────────────┤
  │ service (replicated)  │ Deployment + ReplicaSet                      │
  │ service (global)      │ DaemonSet                                    │
  │ task                  │ Pod (one or more containers)                 │
  │ stack file (Compose)  │ manifests / Helm chart / Kustomize           │
  │ docker secret/config  │ Secret / ConfigMap                           │
  │ routing mesh (ingress)│ Service (NodePort/LoadBalancer) + Ingress    │
  │ overlay network       │ CNI plugin (Calico, Cilium, Flannel ...)     │
  │ update_config         │ rollingUpdate strategy                       │
  │ placement constraints │ nodeSelector, affinity, taints/tolerations   │
  └───────────────────────┴──────────────────────────────────────────────┘
```

- **Swarm** optimizes for simplicity: one binary, one command to form a cluster, Compose-compatible files.
- **Kubernetes** optimizes for extensibility: the API is a platform on which operators, CRDs, policy engines and service meshes are built.
- Both are declarative and self-healing; the difference is breadth of the ecosystem and the amount you must learn.

## 5. Hands-On

### 5.1 A Three-Node Swarm in Minutes

```bash
docker swarm init --advertise-addr 10.0.0.10
docker swarm join-token worker       # prints the join command for workers
docker node ls
```

```text
ID              HOSTNAME   STATUS   AVAILABILITY   MANAGER STATUS
x1k...  *       node1      Ready    Active         Leader
q8p...          node2      Ready    Active
```

Run `docker swarm join --token <token> 10.0.0.10:2377` on the other hosts. Ports required between nodes: 2377/tcp (management), 7946/tcp+udp (gossip), 4789/udp (VXLAN data plane).

### 5.2 Deploy a Compose File as a Stack

```yaml
# stack.yml
services:
  web:
    image: nginx:1.27
    ports: ["8080:80"]
    deploy:
      replicas: 3
      update_config: { parallelism: 1, delay: 10s, order: start-first, failure_action: rollback }
      resources:
        limits: { cpus: "0.50", memory: 128M }
      restart_policy: { condition: on-failure }
```

```bash
docker stack deploy -c stack.yml demo
docker service ls
docker service ps demo_web
docker service update --image nginx:1.27.1 demo_web
```

Swarm honors the `deploy:` key; plain `docker compose up` mostly ignores it. Reaching port 8080 on any node works because of the routing mesh.

### 5.3 The Same Workload in Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: web }
spec:
  replicas: 3
  selector: { matchLabels: { app: web } }
  strategy:
    type: RollingUpdate
    rollingUpdate: { maxSurge: 1, maxUnavailable: 0 }
  template:
    metadata: { labels: { app: web } }
    spec:
      containers:
        - name: web
          image: nginx:1.27
          ports: [{ containerPort: 80 }]
          resources: { limits: { cpu: 500m, memory: 128Mi } }
          readinessProbe: { httpGet: { path: /, port: 80 } }
---
apiVersion: v1
kind: Service
metadata: { name: web }
spec:
  selector: { app: web }
  ports: [{ port: 80, targetPort: 80 }]
```

```bash
kubectl apply -f web.yaml
kubectl rollout status deployment/web
kubectl set image deployment/web web=nginx:1.27.1
kubectl rollout undo deployment/web
```

Note the extra concepts you must now own: a separate Service object, probes, label selectors, and an Ingress or Gateway for HTTP routing.

### 5.4 Translate Compose Intent Without Rewriting by Hand

```bash
docker compose config > resolved.yml     # fully interpolated Compose model
# Conversion tools (kompose, Compose Bridge in Docker Desktop) produce a first draft
kompose convert -f resolved.yml -o k8s/
```

Treat the output as a draft: you will still add probes, resource requests, security contexts, PersistentVolumeClaims and an Ingress.

### 5.5 Local Kubernetes for Practice

```bash
kind create cluster --name lab          # nodes are Docker containers
kubectl get nodes
docker ps --filter name=lab-control-plane
```

Docker Desktop's built-in Kubernetes, minikube and k3d are alternatives; `kind` makes the "nodes are containers" idea concrete.

## 6. Production Usage Notes

- **Swarm** suits small teams, one to a few dozen nodes, simple stateless services, and on-prem estates where Kubernetes operations would be disproportionate. Keep 3 or 5 managers for quorum (tolerates 1 or 2 failures); never an even number.
- **Kubernetes** suits multi-team platforms, heterogeneous workloads (batch, stateful, GPU), strict policy needs, and anything that benefits from its ecosystem (cert-manager, ExternalDNS, Argo CD, Prometheus Operator).
- **Prefer managed control planes** (EKS, AKS, GKE) unless you have a specific reason to run your own; the control plane is the part that is expensive to operate.
- **Runtime change:** since Kubernetes 1.24 the dockershim is gone; nodes use containerd or CRI-O. Images built with Docker run unchanged because they are OCI images ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). Only workloads that mount `/var/run/docker.sock` on nodes break.
- **Migration path that works:** harden images first, add health endpoints and graceful shutdown, externalize config and secrets, make logs go to stdout, then containerize state concerns. Applications that already follow twelve-factor rules migrate with little change.
- **Delivery changes:** push images by immutable tag or digest and let GitOps tooling apply manifests ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)).
- **Swarm status:** Swarm mode is maintained inside Moby and still ships with Docker Engine, but new feature development is limited and community mindshare is small. Choose it knowing the ecosystem is thin; do not pick it for a long-lived platform with many teams.

## 7. Security Considerations

- **Swarm** gives sensible defaults: mutual TLS between nodes, automatic certificate rotation (90-day default), encrypted Raft logs with an optional autolock key, and secrets delivered to containers as in-memory files. Overlay data-plane encryption is opt-in (`--opt encrypted`).
- **Kubernetes** is open by default: Secrets are base64 in etcd unless encryption at rest is configured, all Pods can talk to all Pods until NetworkPolicy is applied, and RBAC, Pod Security Admission, admission controllers and audit logging are your responsibility.
- **API server exposure** is the new crown jewel: whoever can create Pods can usually become node root unless Pod Security Standards forbid privileged Pods, host mounts and host namespaces.
- Carry over container hardening ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md) to [§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)): non-root users, dropped capabilities, seccomp, read-only root filesystems map to `securityContext` fields.
- Protect the Swarm manager port 2377 and the Docker API socket; never expose 2375 unauthenticated.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `docker swarm init` fails with multiple interfaces | Ambiguous advertise address | Pass `--advertise-addr <ip>` |
| Swarm manager unreachable, "no leader" | Lost Raft quorum (majority of managers down) | Restore managers; last resort `docker swarm init --force-new-cluster` on a survivor |
| Service stuck `Pending` in Swarm | Constraint or resource reservation unsatisfiable | `docker service ps --no-trunc svc`; relax constraints |
| Cross-node container traffic fails | 4789/udp or 7946 blocked | Open firewall ports between nodes |
| Pod `ImagePullBackOff` | Wrong tag, missing registry credentials | `kubectl describe pod`; create `imagePullSecrets` |
| Pod `CrashLoopBackOff` | App exits or fails liveness probe | `kubectl logs --previous`; check probes and exit code |
| Pod `OOMKilled` | Memory limit too low | Raise limit, fix leak ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) |
| Pod `Pending` | No node fits requests, taints, unbound PVC | `kubectl describe pod` events |
| Service has no endpoints | Selector does not match labels or readiness failing | `kubectl get endpointslices` |
| Stack file ignores `build:` | Swarm cannot build | Build and push images first |

## 9. Best Practices

- Decide by requirements: team size, workload variety, compliance, ecosystem needs, and operational skill, not by hype.
- Make images portable first: one image, many environments, configuration injected at run time.
- Always define health checks (Docker `HEALTHCHECK`, Kubernetes readiness/liveness/startup probes) and handle SIGTERM for graceful shutdown ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).
- Set resource requests and limits on every workload; in Swarm use `reservations` and `limits`.
- Use declarative, version-controlled definitions; avoid imperative `docker service create` and `kubectl run` in production.
- Run `kind` or `k3d` locally and the same manifests in CI before touching shared clusters.
- Adopt Kubernetes incrementally: start with a managed cluster, stateless services, and Helm or Kustomize, then add policy, autoscaling and service mesh only when needed.

## 10. Common Anti-Patterns / Mistakes

- Adopting Kubernetes for two containers on one VM.
- Staying on a single Docker host with `restart: always` and calling it high availability.
- Using even numbers of Swarm managers, or running workloads on managers in large clusters.
- Baking environment-specific config into images, which blocks promotion across environments.
- Treating Pods as pets: SSH-ing in, editing files, relying on local state.
- Mounting the Docker socket into workloads on a Kubernetes node.
- Copying a Compose file to a stack and expecting `depends_on`, `build`, and `container_name` to behave identically.
- Using `latest` tags with `imagePullPolicy` assumptions, producing non-reproducible rollouts.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does an orchestrator solve that Docker alone does not?"_
**Model answer:** Docker starts containers on one host. An orchestrator manages many hosts as one pool: it schedules containers onto nodes with enough resources, restarts or reschedules failed ones, spreads replicas for availability, provides service discovery and load balancing, performs rolling updates and rollbacks, and distributes configuration and secrets. You describe the desired state, such as "three replicas of this image on port 80", and a control loop keeps reality matching it. Docker Swarm and Kubernetes are the two common choices.
_What the interviewer is probing for:_ A clear separation between running containers and managing them at scale, and awareness of declarative desired state.

**🎯 Intermediate:** _"Compare Docker Swarm and Kubernetes. When would you still choose Swarm?"_
**Model answer:** Swarm is built into Docker Engine, forms a cluster with `docker swarm init`, uses Compose-style stack files, includes mutual TLS, secrets and a routing mesh out of the box, and has a small conceptual surface (service, task, node, stack). Kubernetes has a far larger API (Pods, Deployments, StatefulSets, Services, Ingress, CRDs), pluggable networking and storage, RBAC, autoscaling, and a huge ecosystem, at the cost of operational and learning overhead. I would pick Swarm for a small team with a handful of stateless services on a few nodes, where simplicity beats features, and I would accept limited ecosystem and slow feature development. For multi-team platforms, stateful or batch workloads, policy requirements, or cloud-managed convenience, Kubernetes is the standard choice.
_What the interviewer is probing for:_ Balanced trade-offs rather than "Kubernetes always wins", and accurate knowledge of Swarm's built-ins.

**🎯 Senior:** _"You must migrate twelve Compose-based services to Kubernetes without downtime. Walk me through the plan."_
**Model answer:** First audit portability: config via environment or files, logs to stdout, SIGTERM handling, health endpoints, no reliance on host paths or the Docker socket, and images pushed to a registry by digest. Convert Compose to manifests (a tool gives a draft), then add what Compose lacks: resource requests and limits, readiness, liveness and startup probes, PodDisruptionBudgets, securityContext, NetworkPolicies, and PersistentVolumeClaims for state. Stand up a managed cluster and ingress, deploy services in dependency order starting with stateless leaf services, and run old and new side by side behind a weighted DNS or load-balancer split, shifting traffic gradually with rollback ready. Migrate databases last, or keep them outside the cluster. Automate with GitOps, add observability before cutover, and rehearse rollback.
_What the interviewer is probing for:_ A staged, risk-aware migration that identifies the gaps Compose hides and keeps a rollback path.

**🎯 Architect:** _"Leadership asks whether to standardize on Kubernetes for 40 teams or let teams run Docker and Swarm. Make the recommendation."_
**Model answer:** Standardize on managed Kubernetes as a platform with guardrails, because 40 teams need multi-tenancy (namespaces, quotas, RBAC), policy as code, a shared ingress and observability stack, and a hiring market and tooling ecosystem that Swarm cannot match. Mitigate complexity by offering a paved road: golden base images, Helm or Kustomize templates, a CI pipeline that signs images and produces SBOMs, admission policies enforcing non-root and resource limits, and a platform team owning cluster upgrades. Keep a documented exception path (for example Cloud Run or ECS for simple workloads, or a small Swarm or plain Docker host at edge sites) with exit criteria, and measure cost, deployment frequency and incident rates to revisit the decision. The Docker image contract stays constant, so the choice of runtime platform remains reversible.
_What the interviewer is probing for:_ Organizational judgement: platform thinking, guardrails, exceptions, and reversibility rather than tool loyalty.

## 12. Common Misconceptions

- "Kubernetes replaced Docker." Kubernetes dropped the dockershim; Docker-built OCI images run on containerd and CRI-O unchanged.
- "Swarm is dead and cannot be used." It is supported and works; it is simply niche and slow-moving.
- "Docker Compose is production orchestration." It is single-host; Swarm stacks or Kubernetes provide cluster behavior.
- "Orchestration makes stateful apps easy." Scheduling is easy; data replication, backup and failover remain your problem.
- "More replicas means high availability." Only if they spread across failure domains and health checks gate traffic.

## 13. 🔑 Key Takeaways

- Orchestration is declarative desired state plus a reconciliation loop across many nodes.
- Swarm: simple, built in, Compose-like, mTLS and secrets by default, small ecosystem.
- Kubernetes: extensible, dominant, more to learn and secure; prefer managed control planes.
- OCI images are portable between Docker, Swarm and Kubernetes; the dockershim removal did not change that.
- Health probes, resource limits, graceful shutdown and externalized config are the real migration work.
- Keep an odd number of managers for Raft quorum.

## 14. Related Concepts & What's Next

Related: Swarm primer ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)), containerd and CRI ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)), resource management at scale ([§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)), when Docker is the wrong tool ([§97](Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md)), Docker versus Podman and containerd ([§96](Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md)). Part 14 turns this knowledge into exam and interview readiness, beginning with the Docker Certified Associate domain breakdown in [§100](../Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md).

**Next Section:** [§100](../Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md) — `Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md`
