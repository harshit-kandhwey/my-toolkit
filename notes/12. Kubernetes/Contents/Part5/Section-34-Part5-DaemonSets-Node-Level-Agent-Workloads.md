# Section 34 (Part 5): DaemonSets: Node-Level Agent Workloads

## 1. Definition

**Plain language:** Some workloads aren't "run N copies somewhere in the cluster" but "run exactly one copy on every node" — a log collector, a metrics agent, a network plugin's node agent. A DaemonSet is the controller purpose-built for that "one per node" shape, rather than an arbitrary replica count.

**Precise definition:** A **DaemonSet** is a controller that ensures a copy of a Pod runs on every node in the cluster (or on a filtered subset of nodes matching a **node selector** or **affinity** rule), automatically adding a Pod when a new node joins and removing that Pod when a node is removed — with no `replicas` field at all, since the desired count is implicitly "one per matching node," not a fixed number. DaemonSets are the standard mechanism behind node-level infrastructure agents: `kube-proxy` ([§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md)) itself typically runs as a DaemonSet, alongside CNI node agents, log-shipping sidecars like Fluent Bit, and node-level metrics exporters like `node-exporter`.

## 2. Why This Matters

- **`kube-proxy` is a concrete example already covered.** [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) introduced `kube-proxy` as a node component responsible for Service traffic routing on every node; in most cluster distributions it's deployed as a DaemonSet in `kube-system`, which is the clearest possible real-world proof that "one Pod per node, automatically" is a genuinely necessary workload shape, not an edge case.
- **Observability and log-collection agents depend entirely on this pattern.** A log shipper or metrics agent needs to read node-local files or the local container runtime's socket on every single node without exception — a Deployment cannot guarantee "one on every node," but a DaemonSet guarantees it structurally, including automatically extending coverage to newly added nodes with zero manual intervention.
- **DaemonSets interact directly with scheduling exceptions that other workloads don't get.** DaemonSet Pods bypass the default scheduler's normal placement logic in relevant ways and tolerate the control-plane node taint by default in many setups, since infrastructure agents typically need to run even on nodes that are otherwise off-limits to regular workloads — a nuance that becomes fully concrete once taints and tolerations are covered in Part 9.

🔑 **Key Takeaway:** Reach for a DaemonSet whenever the requirement is "exactly one Pod per (all or matching) node," not "some fixed number of Pods somewhere in the cluster" — the canonical uses are node-level infrastructure like `kube-proxy` ([§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md)), CNI agents, and observability collectors that must observe every node without exception.

## 3. Prerequisites and Dependencies

Builds on [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) (kube-proxy and node components, the running real-world example of a DaemonSet) and [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (Pod spec anatomy); the taint/toleration mechanics that let DaemonSet Pods schedule onto otherwise-restricted nodes are covered fully in Part 9.

## 4. Architecture Diagram

```text
                     DaemonSet "node-agent"
                              │
              observes: current Node objects in the cluster
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   Node A (worker)      Node B (worker)       Node C (control-plane,
        │                     │                tainted)
   node-agent Pod        node-agent Pod             │
                                              node-agent Pod
                                          (scheduled anyway, via
                                           an explicit toleration
                                           for the control-plane taint)

  New Node D joins the cluster
        │
        ▼
  node-agent Pod created automatically on Node D — no manual action

  Node B is drained/removed
        │
        ▼
  node-agent Pod on Node B terminated — no replacement created elsewhere
  (there is nowhere else for a "one per node" Pod to go)
```

- **There is no `replicas` field in a DaemonSet spec at all** — the desired Pod count is implicitly derived from the number of nodes matching `spec.template.spec.nodeSelector`/affinity rules, updated automatically as nodes join or leave.
- **`kubectl scale` does not apply to DaemonSets** — you cannot manually change how many Pods exist; the only levers are the node-matching criteria (selector/affinity) and the actual set of nodes in the cluster.
- **DaemonSet Pods commonly carry explicit tolerations** for taints like `node-role.kubernetes.io/control-plane:NoSchedule`, deliberately opting back in to nodes that regular workloads are excluded from by default (full mechanics in Part 9).

## 5. Hands-On: Deploying and Managing a DaemonSet

### 5.1 Defining a Cluster-Wide DaemonSet

**Purpose:** Deploy a log-collector-style agent to every node in the cluster, the most common real-world DaemonSet use case.

```yaml
# fluentbit-daemonset.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluent-bit
  namespace: logging
spec:
  selector:
    matchLabels:
      app: fluent-bit
  template:
    metadata:
      labels:
        app: fluent-bit
    spec:
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
      containers:
        - name: fluent-bit
          image: fluent/fluent-bit:2.2
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 200m
              memory: 256Mi
          volumeMounts:
            - name: varlog
              mountPath: /var/log
              readOnly: true
      volumes:
        - name: varlog
          hostPath:
            path: /var/log
```

```bash
$ kubectl apply -f fluentbit-daemonset.yaml
daemonset.apps/fluent-bit created

$ kubectl get daemonset -n logging
NAME         DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
fluent-bit   4         4         4       4            4           <none>          22s

$ kubectl get pods -n logging -o wide
NAME               READY   STATUS    RESTARTS   AGE   NODE
fluent-bit-2jv9k   1/1     Running   0          22s   node-1
fluent-bit-8qz1m   1/1     Running   0          22s   node-2
fluent-bit-c5t7w   1/1     Running   0          22s   node-3 (control-plane)
fluent-bit-p3n0x   1/1     Running   0          22s   node-4
```

**Common errors:** Forgetting the toleration for the control-plane taint means `DESIRED` will show one fewer than the actual node count — a very common gap between "I expected this on every node" and reality, easy to miss without checking `kubectl get nodes` alongside `kubectl get daemonset`.

### 5.2 Restricting a DaemonSet to a Subset of Nodes

**Purpose:** Run an agent only on nodes with a specific label — e.g., a GPU-monitoring agent that only needs to exist on GPU-equipped nodes.

```yaml
# gpu-monitor-daemonset.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-monitor
spec:
  selector:
    matchLabels:
      app: gpu-monitor
  template:
    metadata:
      labels:
        app: gpu-monitor
    spec:
      nodeSelector:
        hardware: gpu
      containers:
        - name: gpu-monitor
          image: myregistry/gpu-monitor:1.4
```

```bash
$ kubectl label node node-4 hardware=gpu
node/node-4 labeled

$ kubectl apply -f gpu-monitor-daemonset.yaml
daemonset.apps/gpu-monitor created

$ kubectl get daemonset gpu-monitor
NAME          DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR      AGE
gpu-monitor   1         1         1       1            1           hardware=gpu       9s
```

**Production usage example:** This selective-targeting pattern is exactly how CNI plugins and storage-node agents avoid deploying onto nodes that structurally don't need them — reducing resource footprint on nodes where the agent would do nothing useful.

### 5.3 Rolling Update and Rollback of a DaemonSet

**Purpose:** Show that DaemonSets support the same `RollingUpdate` mechanics as Deployments, node by node instead of Pod-count-batch by batch.

```bash
$ kubectl set image daemonset/fluent-bit fluent-bit=fluent/fluent-bit:2.2.1 -n logging
daemonset.apps/fluent-bit image updated

$ kubectl rollout status daemonset/fluent-bit -n logging
Waiting for daemon set "fluent-bit" rollout to finish: 2 out of 4 new pods have been updated...
daemon set "fluent-bit" successfully rolled out

$ kubectl rollout undo daemonset/fluent-bit -n logging
daemonset.apps/fluent-bit rolled back
```

**Common errors:** The default `updateStrategy` for a DaemonSet is `RollingUpdate` with `maxUnavailable: 1`, meaning only one node's Pod is updated at a time by default — on a very large cluster this can make a full rollout noticeably slow, and `maxUnavailable` may need tuning upward for faster propagation on non-critical agents.

## 6. Production Usage Notes

- **DaemonSets are the standard mechanism behind almost every "cluster add-on" you install** — CNI plugins (Calico, Cilium), CSI node plugins, `node-exporter`, and log shippers are all typically DaemonSets under the hood, often installed via a Helm chart (Part 11) that abstracts the raw manifest.
- **Resource requests/limits on DaemonSet Pods matter disproportionately** because they run on every node unconditionally — an oversized request on a DaemonSet Pod reserves that capacity cluster-wide, directly reducing schedulable capacity for actual workloads on every single node.
- **`kubectl get daemonset` output (`DESIRED`/`CURRENT`/`READY`) is a fast cluster-health signal** — a `DESIRED` count that doesn't match the actual node count (accounting for node selectors) often reveals a taint/toleration mismatch before it shows up as a harder-to-diagnose missing-agent incident.

## 7. Security Considerations

- DaemonSet Pods that mount `hostPath` volumes (as in the log-collector example) or run with elevated `SecurityContext` privileges have node-level blast radius by construction — a compromised DaemonSet Pod potentially affects every node it's scheduled on, making these manifests a priority target for security review ([§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md); Part 15).
- Because DaemonSets often need to tolerate control-plane taints to observe every node, review each toleration deliberately — a broad, unnecessary toleration on a DaemonSet is a common way for a workload to end up running somewhere it shouldn't, including control-plane nodes.

## 8. Common Troubleshooting Scenarios

| Symptom                                          | Likely Cause                                                                                                     | Resolution Path                                                                                    |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `DESIRED` count lower than total node count      | Missing toleration for a tainted node (commonly control-plane), or an active `nodeSelector` excluding some nodes | `kubectl describe daemonset` and compare against `kubectl get nodes --show-labels` / taints        |
| DaemonSet Pod stuck `Pending` on a specific node | Node lacks resources to satisfy the Pod's requests, or a node-level scheduling constraint conflicts              | `kubectl describe pod` on the affected Pod; check node capacity and any conflicting affinity rules |
| Rollout appears frozen partway through           | Default `maxUnavailable: 1` combined with a new-version Pod failing readiness on one node                        | Fix the failing Pod's root cause; rollout resumes automatically once that node's Pod becomes Ready |
| New node doesn't get the DaemonSet Pod           | Node's labels/taints don't satisfy the DaemonSet's `nodeSelector`/tolerations                                    | Confirm the new node's labels/taints match what the DaemonSet expects                              |

## 9. Best Practices

- Set conservative, well-tested resource requests/limits on every DaemonSet Pod, since any oversizing is multiplied across the entire node fleet rather than a handful of replicas.
- Use `nodeSelector` or affinity rules to scope specialized agents (GPU monitoring, storage-specific plugins) only to the nodes that actually need them, rather than running them cluster-wide unconditionally.
- Monitor `kubectl get daemonset` output as part of standard cluster health checks — a mismatch between `DESIRED` and the real node count is an early, cheap signal of a scheduling or taint misconfiguration.

## 10. Common Anti-Patterns / Mistakes

- **Using a DaemonSet when a Deployment with anti-affinity would suffice**, adding unnecessary "one per node" rigidity to a workload that doesn't actually need node-level coverage.
- **Granting a DaemonSet Pod broad, unreviewed `hostPath` access or elevated privileges** "because it's infrastructure," without applying the same SecurityContext scrutiny ([§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)) given to application workloads — despite its node-wide blast radius being larger, not smaller.
- **Forgetting that DaemonSets have no `replicas` field and no `kubectl scale` support**, then being confused when scaling commands silently fail or do nothing meaningful against a DaemonSet.

## 11. Interview Questions

**🎯 Beginner:** _"What is a DaemonSet, and how is its Pod count determined?"_
**Model answer:** A DaemonSet ensures one Pod runs on every node matching its node selector/affinity rules — there's no `replicas` field; the desired count is implicitly the number of matching nodes, and it's kept in sync automatically as nodes join or leave the cluster.
_What the interviewer is probing for:_ Understanding that DaemonSet Pod count is derived from cluster topology, not a static number the operator sets.

**🎯 Intermediate:** _"Give a real Kubernetes component that runs as a DaemonSet, and explain why that's the right shape for it."_
**Model answer:** `kube-proxy` ([§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md)) is a canonical example — it needs to run on literally every node to program that node's Service routing rules (iptables or IPVS), so a Deployment's "some number of interchangeable replicas somewhere" model doesn't fit; the requirement is specifically "exactly one per node, including new nodes automatically," which is the DaemonSet's entire purpose.
_What the interviewer is probing for:_ Whether the candidate connects the abstract controller definition to a concrete, already-known real-world instance rather than only reciting textbook use cases.

**🎯 Senior:** _"Your log-collector DaemonSet shows `DESIRED: 5` but the cluster has 6 nodes. How do you investigate?"_
**Model answer:** I'd first run `kubectl get nodes --show-labels` and `kubectl describe node` on the missing node to check its taints, then compare against the DaemonSet's `nodeSelector` and `tolerations`. The most common cause is a taint on that one node (control-plane, a dedicated-workload taint, or a `NoSchedule` taint applied during maintenance) that the DaemonSet's Pod spec doesn't tolerate — the fix is either adding the appropriate toleration if that node genuinely needs the agent, or confirming the exclusion is intentional if it doesn't.
_What the interviewer is probing for:_ A concrete, ordered diagnostic path connecting DaemonSet coverage gaps to taints/tolerations rather than vague troubleshooting.

**🎯 Architect:** _"How would you think about resource governance for DaemonSets across a large, heterogeneous cluster with mixed node sizes?"_
**Model answer:** Because a DaemonSet's resource requests are multiplied across every matching node regardless of that node's total capacity, I'd size requests/limits based on the actual steady-state need of the agent, not generously, and I'd consider whether uniform requests are even appropriate — a node-size-aware approach (e.g., separate DaemonSets or VerticalPodAutoscaler in recommendation mode) may be warranted if node sizes vary widely enough that a one-size-fits-all request either wastes capacity on small nodes or under-provisions on large ones. I'd also track aggregate DaemonSet resource consumption as a distinct line item in capacity planning, since it's overhead present on every node before any actual application workload is scheduled, and it directly reduces the schedulable capacity every other workload sees.
_What the interviewer is probing for:_ Systems-level thinking about DaemonSets as a cluster-wide tax on capacity, not just a per-Pod configuration question.

## 12. Common Misconceptions

1. **"DaemonSets can be scaled like Deployments."** There's no `replicas` field and no `kubectl scale` support — Pod count is entirely a function of matching nodes.
2. **"A DaemonSet automatically runs on control-plane nodes."** It doesn't, unless the Pod spec includes an explicit toleration for the relevant control-plane taint — by default those nodes are excluded like any other tainted node.
3. **"DaemonSets don't support rolling updates."** They do, via the same `RollingUpdate` strategy concept as Deployments, governed by `updateStrategy.rollingUpdate.maxUnavailable`, just applied per-node instead of per-replica-batch.
4. **"A DaemonSet Pod is inherently lower-risk than an application Pod because it's 'just infrastructure.'"** Its node-wide footprint and frequent need for `hostPath` access or elevated privileges typically make it a higher-risk object to misconfigure, not a lower one.

## 13. 🔑 Key Takeaways

- A DaemonSet runs exactly one Pod per node matching its selector/affinity criteria, with Pod count derived from cluster topology rather than a fixed `replicas` value.
- `kube-proxy` ([§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md)) is a concrete, already-covered real-world example of the DaemonSet pattern in action.
- DaemonSet Pods often need explicit tolerations to schedule onto tainted nodes, including the control-plane, since they're otherwise excluded by default like any workload.
- Resource requests on DaemonSet Pods are effectively multiplied across the entire matching node fleet, making sizing discipline more consequential than for typical Deployments.
- Observability and log-collection agents (Fluent Bit, node-exporter) are the most common production DaemonSet use case, alongside CNI and CSI node-level plugins.

## 14. Related Concepts & What's Next

[§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) supplied the concrete `kube-proxy` example this section built on to explain the DaemonSet pattern's real necessity, and [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)'s Pod spec anatomy underlies every DaemonSet template. The taint/toleration mechanics referenced throughout for control-plane scheduling are covered in full depth in Part 9. [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md) moves from "always-running, one-per-node" workloads to the opposite shape: workloads designed to run to completion and then stop.

**Next Section:** [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md) — `Section-35-Part5-Jobs-Run-To-Completion-Workloads.md`
