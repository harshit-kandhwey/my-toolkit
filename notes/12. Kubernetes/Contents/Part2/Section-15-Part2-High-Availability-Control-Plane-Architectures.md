# Section 15 (Part 2): High-Availability Control Plane Architectures (stacked vs. external etcd topologies)

## 1. Definition

**Plain language:** A single control-plane node is a single point of failure — if that one machine goes down, nothing can be created, updated, or scheduled anywhere in the cluster, even if every worker node and every running Pod is perfectly healthy. Making the control plane highly available means running enough copies of each control-plane component, wired together correctly, that losing any one control-plane node doesn't take the cluster's brain down with it.

**Precise definition:** A **highly available (HA) control plane** runs multiple control-plane nodes, each hosting kube-apiserver, kube-scheduler, kube-controller-manager, and an etcd member (or a client to an external etcd cluster), fronted by a load balancer for api-server traffic, with the two competing topology choices being **stacked etcd** (each control-plane node runs its own local etcd member, co-located with that node's other control-plane components) and **external etcd** (etcd runs as an entirely separate cluster of dedicated nodes, with control-plane nodes running only kube-apiserver, kube-scheduler, and kube-controller-manager, connecting to the external etcd cluster over the network).

## 2. Why HA Topology Choice Matters

- **It's the direct, practical payoff of understanding each control-plane component's distinct failure characteristics from §8.** A naive "just run three of everything identically" design ignores that etcd (Raft-quorum-based, latency-sensitive) and kube-apiserver (stateless, trivially horizontally scalable) have fundamentally different HA requirements — this section is where that distinction becomes a concrete architectural decision.
- **CKA candidates are expected to reason about kubeadm's HA bootstrap flags and topology tradeoffs directly** — Part 3's kubeadm walkthrough (§16) assumes this section's stacked-vs-external framing, and etcd backup/restore procedures in Part 14 (§107) differ meaningfully depending on which topology was chosen at bring-up time.
- **Choosing wrong is expensive to unwind later.** Migrating from a stacked-etcd topology to an external one after a cluster is already in production is a nontrivial, high-risk operation — this decision is effectively made once, at cluster-bootstrap time, making it worth understanding thoroughly before ever running `kubeadm init`.

🔑 **Key Takeaway:** Stacked etcd is simpler to operate and sufficient for most clusters; external etcd trades operational complexity for a stronger failure-isolation guarantee — losing a control-plane node in a stacked topology risks etcd quorum directly, while external etcd decouples that risk entirely, at the cost of managing a second cluster.

## 3. Prerequisites and Dependencies

Builds directly on §8 (the five control-plane components and their individually distinct failure/scaling characteristics) and §10 (etcd's Raft consensus and quorum mechanics, which is what makes etcd's HA requirements different from the other components'). §16 (kubeadm bootstrapping) applies this section's topology choice in practice.

## 4. Architecture Diagram: Stacked vs. External etcd

```text
STACKED ETCD TOPOLOGY (etcd co-located on each control-plane node)

              ┌────────────────────────┐
   clients──► │     Load Balancer       │
              └───────────┬─────────────┘
                          │
     ┌────────────────────┼────────────────────┐
     ▼                    ▼                    ▼
┌───────────┐        ┌───────────┐        ┌───────────┐
│ CP Node 1 │        │ CP Node 2 │        │ CP Node 3 │
│ apiserver │        │ apiserver │        │ apiserver │
│ scheduler │        │ scheduler │        │ scheduler │
│ ctrl-mgr  │        │ ctrl-mgr  │        │ ctrl-mgr  │
│ etcd (1)  │◄──────►│ etcd (2)  │◄──────►│ etcd (3)  │
└───────────┘  Raft  └───────────┘  Raft  └───────────┘
   Losing CP Node 1 = losing one control-plane replica
   AND one etcd member simultaneously (same blast radius).


EXTERNAL ETCD TOPOLOGY (etcd is a fully separate cluster)

              ┌─────────────────────────┐
   clients──► │     Load Balancer       │
              └───────────┬─────────────┘
                          │
     ┌────────────────────┼────────────────────┐
     ▼                    ▼                    ▼
┌───────────┐        ┌───────────┐        ┌───────────┐
│ CP Node 1 │        │ CP Node 2 │        │ CP Node 3 │
│ apiserver │        │ apiserver │        │ apiserver │
│ scheduler │        │ scheduler │        │ scheduler │
│ ctrl-mgr  │        │ ctrl-mgr  │        │ ctrl-mgr  │
└─────┬─────┘        └─────┬─────┘        └─────┬─────┘
      │                    │                    │
      └────────────────────┼────────────────────┘
                           │  (network calls to a
                           │   separate etcd cluster)
                ┌──────────┴──────────┐
                ▼          ▼          ▼
           ┌────────┐  ┌────────┐  ┌────────┐
           │ etcd 1 │◄►│ etcd 2 │◄►│ etcd 3 │   (dedicated nodes,
           └────────┘  └────────┘  └────────┘    separately scaled/failed)
   Losing CP Node 1 = losing one control-plane replica ONLY;
   etcd's quorum is entirely unaffected.
```

- **In stacked topology, a control-plane node failure is simultaneously an etcd member failure** — the two failure domains are collapsed into one, which is simpler to operate (fewer machines total) but means a control-plane-node-level incident (bad kernel update, hardware failure) directly threatens etcd quorum as a side effect.
- **In external topology, the two failure domains are fully decoupled** — a control-plane node can be rebuilt, resized, or lost entirely without any direct effect on etcd's quorum, at the cost of managing and securing an additional, dedicated cluster of machines.
- **A load balancer in front of kube-apiserver is required in both topologies** — this is what makes the api-server's inherent statelessness (§8) actually pay off operationally, since clients (including kubelet on every node) connect to the load balancer's address, not to any individual control-plane node.

## 5. Hands-On: Reasoning About and Inspecting HA Topology

### 5.1 Identifying Topology on an Existing kubeadm Cluster

**Purpose:** Determine whether a running cluster uses stacked or external etcd, since this affects backup/restore procedure (§107) and upgrade ordering (§106).

**Syntax:** `kubectl get pods -n kube-system`

```bash
$ kubectl get pods -n kube-system -o wide | grep etcd
etcd-cp-node-1   1/1   Running   0   30d   10.0.1.10   cp-node-1
etcd-cp-node-2   1/1   Running   0   30d   10.0.1.11   cp-node-2
etcd-cp-node-3   1/1   Running   0   30d   10.0.1.12   cp-node-3
```

**Interpretation:** etcd static Pods (§17) running with names matching each control-plane node indicate a **stacked** topology. On an **external** topology, no `etcd-*` static Pods appear in `kube-system` at all on control-plane nodes — instead, `kubectl -n kube-system get configmap kubeadm-config -o yaml` shows an `etcd.external` block pointing at separately managed endpoints.

**Production usage example:** This check is the fastest way to confirm topology before performing any etcd-related maintenance on an unfamiliar cluster inherited from another team — assuming the wrong topology when planning an etcd snapshot restore can mean backing up or restoring the wrong set of machines entirely.

### 5.2 Inspecting the kubeadm ClusterConfiguration for the Chosen etcd Block

**Purpose:** See exactly how kubeadm records the topology decision made at `kubeadm init` time.

```bash
$ kubectl -n kube-system get configmap kubeadm-config -o jsonpath='{.data.ClusterConfiguration}' | grep -A4 etcd
etcd:
  local:
    dataDir: /var/lib/etcd
    imageRepository: registry.k8s.io
```

**Production usage example:** A `local` block (as shown) confirms stacked etcd, managed directly by kubeadm as a static Pod on each control-plane node; an `external` block instead lists `endpoints`, `caFile`, `certFile`, and `keyFile` pointing at an independently operated etcd cluster — the exact fields covered when §16 walks through `kubeadm init --config`.

**Common errors:** Assuming every production cluster uses external etcd because it "sounds more enterprise" — stacked etcd is the kubeadm default, is explicitly supported for production use, and is the right choice for the majority of self-managed clusters that don't have a dedicated etcd-operations team; external etcd is a deliberate tradeoff, not a strictly superior default.

## 6. Production Usage Notes

- **Stacked etcd is kubeadm's default and is entirely production-appropriate for most organizations** — it requires managing one set of machines instead of two, and the shared-failure-domain tradeoff is acceptable when control-plane nodes themselves are already reasonably reliable (proper disk, network, and hardware) and quorum is sized correctly (3 or 5 members).
- **External etcd is typically chosen when etcd's operational profile genuinely diverges from the control plane's** — e.g., etcd needs different, more aggressive disk/network SLAs than the api-server nodes, or an organization already runs shared etcd infrastructure for other purposes and wants to reuse that operational expertise.
- **Managed Kubernetes offerings (EKS, AKS, GKE) abstract this entire decision away** — the cloud provider operates etcd (in practice, always as a variant of the external model) and customers never see or choose a topology; this section's decision applies specifically to self-managed, kubeadm-bootstrapped clusters (§21 covers managed-offering differences).
- **Quorum math applies identically regardless of topology** — a 3-member etcd cluster (stacked or external) tolerates exactly 1 member loss before losing write availability; a 5-member cluster tolerates 2. This is why HA control planes almost always use exactly 3 or 5 control-plane nodes, never an even number.

## 7. Security Considerations

- **In stacked topology, compromising a single control-plane node exposes both an api-server instance and an etcd member simultaneously** — the blast radius of a single node compromise is strictly larger than in external topology, a relevant factor in threat-modeling exercises for CKS-level cluster hardening (§113).
- **External etcd requires securing an additional network path and an additional set of mTLS certificates** (control-plane nodes to etcd cluster) beyond what stacked etcd needs, meaning it introduces its own additional attack surface even as it reduces per-node blast radius — there is no topology that is simply "more secure" in every dimension.
- **Regardless of topology, etcd access must be restricted to kube-apiserver alone** (§8) — network policies or firewall rules should block any other component or external client from reaching etcd's client port directly, since etcd access is equivalent to full cluster read/write access if unencrypted, or full cluster compromise if it also permits unauthenticated writes.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                               | Resolution Path                                                                                    |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Losing one control-plane node also drops etcd below quorum                 | Stacked topology with too few members (e.g., only 2 control-plane nodes total)             | Confirm 3 or 5 total members are running; stacked topology needs the same node count as etcd needs |
| `kubectl` works intermittently depending on which node handles the request | Load balancer misconfigured or not health-checking api-server instances properly           | Verify load balancer health checks target api-server's actual health endpoint on all replicas      |
| etcd backup/restore runbook doesn't match the actual cluster               | Runbook assumes the wrong topology (stacked vs. external) for this cluster                 | Confirm topology first via the checks above before executing any etcd maintenance procedure        |
| Adding a 4th control-plane node doesn't improve fault tolerance            | Even-numbered etcd membership doesn't improve quorum tolerance over the odd count below it | Always size etcd membership at odd numbers (3, 5, not 4, 6) for genuine quorum improvement         |

## 9. Best Practices

- Default to stacked etcd unless there is a specific, articulated reason (differing SLA needs, existing dedicated etcd expertise) to take on the added operational surface of external etcd.
- Always size etcd membership (in either topology) at an odd number — 3 for most production clusters, 5 for larger or more fault-tolerant requirements — since even-numbered clusters gain no quorum-tolerance benefit over the next-lowest odd number while adding cost.
- Place a real, health-checked load balancer in front of kube-apiserver in any HA topology; pointing kubelets or `kubectl` configs at a single control-plane node's IP defeats the purpose of running multiple api-server replicas at all.

## 10. Common Anti-Patterns / Mistakes

- **Running an even number of control-plane/etcd nodes** (e.g., 2 or 4) under the mistaken belief that more members always means more tolerance — quorum math means an even-numbered cluster is strictly worse than the next-lowest odd number for the same node count.
- **Choosing external etcd purely because it "sounds more robust"** without a concrete operational reason, taking on a second cluster's worth of operational burden and an additional attack surface for no corresponding benefit.
- **Pointing client configuration (kubeconfig, kubelet) directly at one control-plane node's IP instead of the load balancer**, silently reintroducing a single point of failure into an otherwise properly built HA cluster.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between stacked and external etcd topology?"_
**Model answer:** In stacked etcd, each control-plane node runs its own etcd member locally, alongside the api-server, scheduler, and controller-manager — the same machine that hosts one control-plane replica also hosts one etcd replica. In external etcd, etcd runs on an entirely separate set of dedicated machines, and control-plane nodes connect to that separate etcd cluster over the network instead of running etcd locally.
_What the interviewer is probing for:_ Basic recall of the two topology names and their defining structural difference.

**🎯 Intermediate:** _"Why would a team choose external etcd over the simpler stacked default?"_
**Model answer:** The main reason is failure-domain isolation — in stacked etcd, losing a control-plane node simultaneously costs you one control-plane replica and one etcd member, since they're the same machine; in external etcd those are two completely independent failure domains, so a control-plane node can be rebuilt or replaced without touching etcd quorum at all. Teams also choose external etcd when etcd's actual operational needs (very low-latency dedicated disks, specific network isolation) genuinely differ from what the api-server/scheduler/controller-manager need, or when they already operate shared etcd infrastructure elsewhere. The tradeoff is managing an entire second cluster of machines and its own security surface, so it's a deliberate choice, not a strictly better default.
_What the interviewer is probing for:_ Understanding that this is a genuine tradeoff decision, not "external is always more advanced/correct."

**🎯 Senior:** _"Both topologies still typically use 3 or 5 nodes. Why is that specific number range the norm regardless of which topology is chosen?"_
**Model answer:** It comes down to etcd's Raft consensus quorum math (§10), which is topology-independent — a cluster of N etcd members needs a strict majority (floor(N/2)+1) to remain available for writes, and can tolerate floor((N-1)/2) member failures before losing that majority. With 3 members you tolerate 1 failure; with 5, you tolerate 2; but with an even number like 4, you still only tolerate 1 failure (since losing 2 of 4 already breaks majority) while paying for an extra machine that adds no tolerance improvement over 3. This quorum math is identical whether those etcd members happen to be co-located with control-plane nodes (stacked) or running on their own dedicated machines (external) — the topology decision changes where etcd runs and what else shares its failure domain, but not the underlying arithmetic governing how many members you need for a given fault-tolerance target.
_What the interviewer is probing for:_ Whether the candidate understands that node-count sizing is a Raft-quorum property independent of topology choice, rather than an arbitrary convention.

**🎯 Architect:** _"You're designing the control-plane topology for a regulated environment where etcd (holding Secrets and full cluster state) must be demonstrably isolated from general control-plane compute for audit purposes, but the organization has limited etcd operational expertise. How do you resolve that tension?"_
**Model answer:** The audit/isolation requirement pushes toward external etcd — a genuinely separate failure and network domain is a much easier isolation story to demonstrate to an auditor than "etcd happens to run as a co-located process on the same machine as the api-server," even if stacked etcd is technically secured well. But the limited operational expertise is a real, legitimate constraint against taking on a fully self-managed external etcd cluster cold. I'd resolve this by treating external etcd as non-negotiable for the compliance requirement, but investing deliberately in etcd operational readiness before going to production: dedicated runbooks for snapshot/restore (§107) rehearsed in a non-production environment first, encryption at rest configured on etcd from day one (§74, Part 10) rather than retrofitted later, and monitoring/alerting on etcd-specific health signals (Raft leader changes, disk fsync latency, quorum member health) separate from general control-plane monitoring. The architectural decision (external etcd) and the operational-readiness investment are two separate deliverables, and skipping the second while implementing the first would just trade a stacked-topology risk for an under-operated-external-etcd risk — not a genuine improvement.
_What the interviewer is probing for:_ Ability to resolve a real tension between a compliance-driven architectural requirement and genuine organizational capability constraints, rather than picking the "textbook correct" answer without addressing the operational readiness gap it creates.

## 12. Common Misconceptions

1. **"External etcd is always the more secure/robust choice."** It trades one risk (shared control-plane/etcd failure domain) for another (a second cluster and network path to secure and operate) — it is not a strict improvement in every dimension.
2. **"More etcd members always means more fault tolerance."** Only odd-number increases actually improve quorum tolerance; going from 3 to 4 members adds cost without adding tolerance.
3. **"Managed Kubernetes offerings (EKS/AKS/GKE) let you choose this topology."** The cloud provider makes this decision invisibly on the customer's behalf; this choice applies specifically to self-managed, kubeadm-bootstrapped clusters.
4. **"Stacked etcd is a lesser, non-production-grade option."** It's kubeadm's default and is fully production-appropriate for the majority of self-managed clusters; external etcd is a deliberate additional-complexity tradeoff for specific needs, not a maturity upgrade every serious cluster should make.

## 13. 🔑 Key Takeaways

- Stacked etcd co-locates one etcd member per control-plane node (kubeadm's default, simpler, production-appropriate for most); external etcd runs etcd as a fully separate cluster (stronger failure isolation, higher operational overhead).
- Losing a control-plane node in stacked topology risks etcd quorum directly, since the two are the same machine; external topology fully decouples that risk.
- Etcd membership should always be sized at an odd number (3 or 5) regardless of topology, since quorum math gives even-numbered clusters no tolerance benefit over the next-lowest odd count.
- A health-checked load balancer in front of kube-apiserver is required in either topology to actually realize the benefit of running multiple stateless api-server replicas.
- This decision is effectively made once at cluster-bootstrap time (§16) and is expensive to reverse afterward, making it worth deliberate evaluation rather than defaulting reflexively in either direction.

## 14. Related Concepts & What's Next

§8 established each control-plane component's individually distinct failure characteristics, which this section turned into a concrete topology decision. §10's Raft quorum mechanics underpin the odd-node-count sizing rule used here. §16 (next, opening Part 3) walks through `kubeadm init` and shows exactly how this topology choice is expressed as bootstrap configuration in practice. §107 (Part 14) covers etcd backup/restore procedures, which differ by topology. §113 (Part 15) revisits control-plane hardening and blast-radius reasoning at full CKS depth.

**Next Section:** §16 — `Section-16-Part3-Kubeadm-Cluster-Bootstrapping-Step-By-Step.md`
