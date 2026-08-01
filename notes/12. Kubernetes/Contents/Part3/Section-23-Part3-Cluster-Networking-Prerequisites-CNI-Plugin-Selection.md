# Section 23 (Part 3): Cluster Networking Prerequisites and CNI Plugin Selection at Install Time

## 1. Definition

**Plain language:** A freshly bootstrapped Kubernetes control plane, on its own, cannot actually let Pods talk to each other — something has to wire up the actual networking, and that something must be chosen and installed before the cluster is usable, not as an afterthought.

**Precise definition:** Before a Kubernetes cluster can schedule working Pods, the operator must satisfy a set of **networking prerequisites** — unique node/Pod IP ranges, required kernel modules and sysctl settings, and open ports between control-plane and node components — and install a **Container Network Interface (CNI)** plugin, the pluggable component responsible for actually assigning Pod IP addresses and implementing pod-to-pod connectivity across nodes. Without a CNI plugin installed, nodes remain in `NotReady` state indefinitely, because the kubelet cannot report a node as ready until its Pod networking is functional. This section covers only what must be decided and configured **at install time**; the full comparison of CNI plugins (Calico, Flannel, Cilium, Weave) and their internal mechanics is covered in depth in §49 (Part 7).

## 2. Why This Matters

- **A cluster that never leaves `NotReady` is one of the single most common first-cluster failures**, and it is almost always a missing or misconfigured CNI plugin, not a control-plane problem — recognizing this early saves enormous debugging time (§97, Part 13 covers node-level troubleshooting in general; this specific failure mode is squarely a networking prerequisite issue).
- **CNI plugin choice at install time has consequences that are expensive to reverse later** — Pod CIDR ranges, NetworkPolicy enforcement capability, and encryption support are often locked in by the initial choice, meaning the decision deserves real evaluation before `kubeadm init`, not a default accepted without thought (§49, Part 7 covers the full plugin trade-off comparison this section only sets up).
- **Getting the Pod CIDR and node-to-node network prerequisites right the first time avoids painful re-bootstrapping** — a cluster initialized with a Pod CIDR that later collides with existing corporate network ranges typically requires a full cluster rebuild to fix, not a simple reconfiguration (§16, Part 3 covers the `kubeadm init` flags where this CIDR is set).

🔑 **Key Takeaway:** Kubernetes deliberately ships without a built-in networking implementation — a CNI plugin must be explicitly chosen and installed before any cluster is functional, and getting the install-time prerequisites (IP ranges, kernel settings, plugin choice) right up front avoids the single most common cause of a stuck, `NotReady` first cluster.

## 3. Prerequisites and Dependencies

Builds directly on §16 (kubeadm cluster bootstrapping, where the Pod CIDR is first specified) and §9 (kube-proxy, which works alongside whatever CNI plugin is chosen to implement Service networking). References forward extensively to §48–§56 (Part 7's full networking depth).

## 4. Architecture: Where the CNI Plugin Fits

```text
┌──────────────────────────────────────────────────────────────────────┐
│                         kubeadm init / join                          │
│         (control plane comes up; nodes join; NO Pod networking yet)  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
                    kubectl get nodes  →  STATUS: NotReady
                    (kubelet is waiting on CNI to report ready)
                                 │
                                 ▼
                 kubectl apply -f <cni-plugin-manifest.yaml>
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
   ┌────────────────────┐               ┌─────────────────────────┐
   │   CNI plugin agent │               │   CNI plugin agent      │
   │  (DaemonSet, e.g.  │               │  (DaemonSet, e.g.       │
   │   calico-node)     │◄─────────────►│   calico-node)          │
   │  on Node 1         │  overlay/BGP  │  on Node 2              │
   └────────────────────┘   routing     └─────────────────────────┘
              │                                      │
              ▼                                      ▼
        Pod IPs assigned                     Pod IPs assigned
        from Node 1's slice                  from Node 2's slice
        of the cluster Pod CIDR              of the cluster Pod CIDR
                                 │
                                 ▼
                    kubectl get nodes  →  STATUS: Ready
```

- **The kubelet explicitly gates node readiness on CNI plugin health** — this is by design, not a bug, since a node that can't network Pods correctly shouldn't be advertised as schedulable.
- **CNI plugins install as a DaemonSet** (§34, Part 5) running one agent Pod per node, which is why `kubectl get pods -n kube-system` after a CNI install shows one plugin Pod per node.
- **The Pod CIDR is a cluster-wide resource carved into per-node slices** — each node receives a subset of the overall Pod IP range to assign to its own Pods, which is why the CIDR must be sized generously enough up front for the cluster's expected maximum node and Pod count.

## 5. Hands-On: Satisfying Prerequisites and Installing a CNI Plugin

### 5.1 Kernel and Network Prerequisites Before Bootstrapping

**Purpose:** Ensure every node has the kernel modules, sysctl settings, and port access Kubernetes networking requires, before running `kubeadm init`.

**Syntax:**

```bash
# Required kernel modules
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
sudo modprobe overlay
sudo modprobe br_netfilter

# Required sysctl settings (allow bridged traffic to be seen by iptables)
cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sudo sysctl --system
```

**Example usage and expected output:**

```bash
$ sudo sysctl --system
* Applying /etc/sysctl.d/k8s.conf ...
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
```

**Production usage example:** These exact settings are baked into every production kubeadm pre-flight checklist and configuration-management playbook (Ansible roles, Terraform user-data scripts) that provisions Kubernetes nodes — skipping them is the single most common reason `kubeadm init`'s preflight checks fail before the control plane even attempts to start.

**Common errors:** Forgetting `net.ipv4.ip_forward=1` results in nodes that appear to join successfully but where cross-node Pod traffic silently fails to route — a symptom easily mistaken for a CNI plugin bug when the actual cause is a missing kernel-level prerequisite.

### 5.2 Choosing and Setting the Pod CIDR at Bootstrap Time

**Purpose:** Reserve a non-overlapping IP range for Pod networking before initializing the control plane — this choice is expensive to change after the fact.

**Syntax:**

```bash
kubeadm init --pod-network-cidr=<CIDR>
```

**Example usage and expected output:**

```bash
$ kubeadm init --pod-network-cidr=192.168.0.0/16
[init] Using Kubernetes version: v1.30.2
[preflight] Running pre-flight checks
...
Your Kubernetes control-plane has initialized successfully!
...
You should now deploy a pod network to the cluster.
Run "kubectl apply -f [podnetwork].yaml" with one of the options listed at:
  https://kubernetes.io/docs/concepts/cluster-administration/addons/
```

**Production usage example:** Platform teams standardize a single Pod CIDR convention across every cluster in an organization (e.g., always `10.244.0.0/16` for cluster A, `10.245.0.0/16` for cluster B) specifically so that, if clusters are ever peered or migrated, Pod IP ranges never collide — a decision made once, deliberately, at this exact bootstrap step.

**Common errors:** Choosing a Pod CIDR that overlaps with the corporate network's existing address space (e.g., `10.0.0.0/8` when the office VPN already uses part of that range) causes silent, hard-to-diagnose routing conflicts for any traffic that needs to traverse both networks — this must be checked against existing network allocations before running `kubeadm init`, not discovered afterward.

### 5.3 Installing a CNI Plugin (Example: Calico)

**Purpose:** Apply the chosen CNI plugin's manifest immediately after control-plane initialization, which is the step that actually moves nodes from `NotReady` to `Ready`.

**Syntax:**

```bash
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.28.0/manifests/calico.yaml
```

**Example usage and expected output:**

```bash
$ kubectl apply -f calico.yaml
poddisruptionbudget.policy/calico-kube-controllers created
serviceaccount/calico-kube-controllers created
serviceaccount/calico-node created
configmap/calico-config created
daemonset.apps/calico-node created
deployment.apps/calico-kube-controllers created
...

$ kubectl get nodes
NAME           STATUS   ROLES           AGE   VERSION
control-1      Ready    control-plane   3m    v1.30.2
worker-1       Ready    <none>          2m    v1.30.2

$ kubectl get pods -n kube-system -l k8s-app=calico-node
NAME                READY   STATUS    RESTARTS   AGE
calico-node-4f8h2    1/1     Running   0          90s
calico-node-p9x7q    1/1     Running   0          90s
```

**Production usage example:** This is the exact step where install-time plugin selection (Calico vs. Flannel vs. Cilium — full comparison in §49) becomes concrete: swapping the manifest URL applied here is effectively the entire decision point, though each plugin's manifest may require matching its own expected Pod CIDR convention to what was set in `kubeadm init --pod-network-cidr`.

**Common errors:** Applying a CNI manifest whose expected Pod CIDR (often hardcoded or defaulted inside the manifest, e.g., Flannel's default `10.244.0.0/16`) doesn't match what was passed to `kubeadm init --pod-network-cidr` results in Pods that get scheduled but never receive working network connectivity — the two values must agree exactly.

## 6. Production Usage Notes

- **CNI plugin choice at install time is frequently driven by feature requirements the team already knows it needs**, not benchmarked from scratch each time — e.g., choosing Calico or Cilium specifically because NetworkPolicy enforcement (§79, Part 10) is a known requirement, since Flannel alone provides no NetworkPolicy support.
- **A cluster's Pod CIDR size must account for maximum expected node count and per-node Pod density**, both set via `--pod-network-cidr` and the CNI plugin's own per-node block size configuration — undersizing this at install time is a common cause of clusters unexpectedly running out of assignable Pod IPs as they scale.
- **Managed cloud offerings (EKS, AKS, GKE) often pre-select or heavily default the CNI plugin** (e.g., EKS defaults to the AWS VPC CNI, which assigns Pods real VPC-routable IPs rather than an overlay network) — the install-time decision described in this section applies most directly to self-managed kubeadm and lightweight distributions (§22), since managed offerings frequently make this choice for the operator.

## 7. Security Considerations

- A cluster with no CNI plugin installed has no working NetworkPolicy enforcement even after Pods can communicate — some plugins (Flannel) never support NetworkPolicy at all, which is a security-relevant fact that belongs in the install-time decision, not discovered later when writing a policy that silently has no effect (§79, Part 10).
- Overly broad Pod CIDR ranges accepted without review can inadvertently overlap with existing internal network ranges, creating a routing ambiguity that is itself a security concern (traffic intended for internal corporate systems being misrouted toward Pod IPs, or vice versa).
- Kernel-level prerequisites like `net.bridge.bridge-nf-call-iptables` affect whether NetworkPolicy rules relying on iptables are even enforced correctly — an unmet prerequisite can silently produce a cluster that appears to have working NetworkPolicies but doesn't actually enforce them.

## 8. Common Troubleshooting Scenarios

| Symptom                                                | Likely Cause                                                                   | Resolution Path                                                                                        |
| ------------------------------------------------------ | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| All nodes stuck `NotReady` after `kubeadm init`/`join` | No CNI plugin installed yet, or its DaemonSet Pods are failing                 | `kubectl get pods -n kube-system`; install/re-check the CNI plugin manifest                            |
| Pods scheduled but cannot reach Pods on other nodes    | Pod CIDR mismatch between `kubeadm init` flag and the CNI plugin's expectation | Confirm both values match exactly; reinstall CNI plugin with corrected CIDR if not                     |
| `kubeadm init` preflight check fails before completing | Missing kernel modules (`br_netfilter`) or sysctl settings not applied         | Apply the required `modprobe`/`sysctl` prerequisites from section 5.1 above and rerun preflight checks |

## 9. Best Practices

- Decide the Pod CIDR and CNI plugin deliberately before running `kubeadm init` — treat both as install-time architectural decisions, not defaults to accept unreviewed, since both are expensive to change after Pods and Services already depend on them.
- Verify kernel prerequisites (`br_netfilter`, `ip_forward`, bridge-nf sysctls) are applied via configuration management on every node image, so they're never a manual, easily-skipped step during scaling events.
- Confirm the chosen CNI plugin's Pod CIDR default or configuration explicitly matches the value passed to `kubeadm init --pod-network-cidr` before considering the install complete — this single mismatch is responsible for a large share of "Pods can't reach each other" first-cluster issues.

## 10. Common Anti-Patterns / Mistakes

- **Running `kubeadm init` and then being confused why nodes stay `NotReady`**, without realizing that installing a CNI plugin is a separate, required step Kubernetes deliberately does not perform automatically.
- **Accepting a CNI plugin's default Pod CIDR without checking it against the value passed to `kubeadm init`**, producing a cluster where networking looks installed but doesn't actually function correctly.
- **Choosing a Pod CIDR range without checking for overlap against existing corporate/VPC network ranges**, discovering the collision only once cross-network traffic starts behaving unpredictably.

## 11. Interview Questions

**🎯 Beginner:** _"Why does a node stay `NotReady` right after `kubeadm init` completes successfully?"_
**Model answer:** Kubernetes deliberately ships without a built-in Pod networking implementation — the control plane can initialize successfully, but the kubelet won't report a node as `Ready` until a CNI plugin is installed and functioning, since without one Pods can't actually get working network connectivity. This is expected behavior, not a failure, and is resolved by applying a CNI plugin's manifest right after `kubeadm init`.
_What the interviewer is probing for:_ Basic understanding that Kubernetes networking is pluggable and requires an explicit install step, rather than assuming networking "just works" out of the box.

**🎯 Intermediate:** _"What's the significance of the `--pod-network-cidr` flag, and why is getting it right at install time important?"_
**Model answer:** `--pod-network-cidr` reserves the IP address range the cluster will carve up and assign to Pods across all nodes; it must be set consistently with whatever the chosen CNI plugin expects, or Pods will be scheduled but fail to communicate correctly across nodes. Getting it right at install time matters because changing it after the cluster is running and has active workloads generally requires a full cluster rebuild rather than a simple reconfiguration, and because it must be sized generously enough up front to accommodate the cluster's eventual maximum node and Pod count without running out of assignable addresses.
_What the interviewer is probing for:_ Understanding that this is a genuine architectural decision made once at bootstrap time, with real downstream consequences, not just a required-but-arbitrary flag.

**🎯 Senior:** _"A newly bootstrapped cluster has all nodes `Ready` and the CNI plugin's DaemonSet Pods all `Running`, but Pods on different nodes still can't reach each other. How would you investigate?"_
**Model answer:** Since the plugin is installed and nodes are `Ready`, I'd first suspect a configuration mismatch rather than a missing-install problem — specifically checking whether the Pod CIDR the CNI plugin was configured to expect actually matches what was passed to `kubeadm init --pod-network-cidr`; a mismatch here is a very common cause of exactly this symptom. I'd also verify the kernel-level prerequisites (`net.ipv4.ip_forward`, `bridge-nf-call-iptables`) are actually applied on every node, not just the one I happen to be checking, since configuration drift between nodes provisioned at different times is a realistic cause. Only after ruling out both of those would I move to plugin-specific debugging (checking `calico-node` or equivalent logs for BGP/overlay-specific errors), since the CIDR mismatch and missing kernel prerequisites account for the large majority of this exact symptom in practice.
_What the interviewer is probing for:_ A structured approach that checks the most common, simplest causes (CIDR mismatch, missing kernel prerequisites) before escalating to plugin-internals debugging.

**🎯 Architect:** _"You're setting a platform-wide standard for CNI plugin selection across dozens of self-managed kubeadm clusters in different regions and business units. What do you standardize on at install time, and why?"_
**Model answer:** I'd standardize on a single CNI plugin choice (commonly Calico or Cilium specifically for their mature NetworkPolicy enforcement, rather than Flannel which lacks it) across the entire fleet, and mandate a documented, non-overlapping Pod CIDR allocation scheme per cluster — for example, deriving each cluster's `/16` from a shared registry so no two clusters in the organization can ever collide if they're later peered, migrated, or need cross-cluster connectivity. I'd bake the required kernel prerequisites (`br_netfilter`, sysctls) into the base node image or configuration-management baseline so they're never a manually-applied, skippable step during scaling events. The goal is to eliminate exactly the two failure modes covered in this section — CIDR mismatches and missing kernel prerequisites — as sources of incidents across a fleet, by making the correct configuration the path of least resistance rather than something each cluster's operator has to remember independently.
_What the interviewer is probing for:_ Ability to turn a single-cluster install-time decision into a consistent, collision-free, low-toil fleet-wide standard.

## 12. Common Misconceptions

1. **"Kubernetes has built-in Pod networking."** It deliberately does not — a CNI plugin is a required, separate install step, and the kubelet gates node readiness on it explicitly.
2. **"Any CNI plugin's default Pod CIDR will just work."** Defaults must be explicitly reconciled against whatever CIDR was passed to `kubeadm init --pod-network-cidr`; mismatches cause silent connectivity failures, not errors.
3. **"CNI plugin choice is purely a networking-performance decision."** It also determines NetworkPolicy enforcement capability, encryption support, and IP-per-Pod vs. overlay networking model — a security- and architecture-relevant decision, not just a performance one.
4. **"Changing the Pod CIDR later is a simple reconfiguration."** In practice, changing it on a cluster with active workloads generally requires a full rebuild, which is why it must be decided carefully at install time.

## 13. 🔑 Key Takeaways

- Kubernetes ships with no built-in Pod networking; a CNI plugin must be explicitly installed before nodes report `Ready`, by design.
- Install-time prerequisites — kernel modules (`br_netfilter`), sysctl settings (`ip_forward`, bridge-nf), and the Pod CIDR — must all be satisfied and consistent before or immediately after `kubeadm init`.
- The Pod CIDR passed to `kubeadm init` and the CNI plugin's own expected CIDR must match exactly; mismatches are a leading cause of "Pods scheduled but can't communicate" symptoms.
- CNI plugin choice at install time has downstream consequences (NetworkPolicy support, encryption, IP model) that are expensive to change later — it deserves deliberate evaluation, not a default accepted unreviewed.
- Managed cloud offerings often pre-select or default the CNI plugin choice, meaning this install-time decision applies most directly to self-managed kubeadm and lightweight distributions.

## 14. Related Concepts & What's Next

§16 covers the full `kubeadm init` bootstrapping flow this section's Pod CIDR flag belongs to, and §9 covers kube-proxy, which works alongside whatever CNI plugin is installed here. §48–§56 (Part 7) return to networking in full depth, with §49 specifically providing the complete Calico/Flannel/Cilium/Weave comparison this section only referenced for install-time decision-making, and §54 covering NetworkPolicies built on top of whatever plugin is chosen here. This is the final section of Part 3 — Part 4 begins immediately with the Pod itself, the object all of this networking and bootstrapping work exists to support.

**Next Section:** §24 — `Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md`
