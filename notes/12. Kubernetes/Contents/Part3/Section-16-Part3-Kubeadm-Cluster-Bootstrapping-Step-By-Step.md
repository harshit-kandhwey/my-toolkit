# Section 16 (Part 3): kubeadm: Cluster Bootstrapping Step by Step

## 1. Definition

**Plain language:** Everything discussed so far — the five control-plane components, their HA topology options — has to actually get installed and wired together on real machines somehow. kubeadm is the standard tool that does exactly that: it takes a set of bare Linux machines and turns them into a working Kubernetes cluster, running the right components in the right order with the right certificates already in place.

**Precise definition:** **kubeadm** is the official Kubernetes project tool for bootstrapping a minimum-viable, best-practice cluster: it generates the PKI (Part 3's [§18](./Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md) covers this in depth), renders the control-plane components as **static Pods** ([§17](./Section-17-Part3-Static-Pods-Kubelet-Configuration.md)) on each control-plane node, initializes (or joins) etcd according to the chosen topology ([§15](../Part2/Section-15-Part2-High-Availability-Control-Plane-Architectures.md)), configures the kubelet, and produces a `kubeconfig` ([§20](./Section-20-Part3-Kubeconfig-Files-Contexts-Multi-Cluster-Switching.md)) for administrative access — all driven by two primary subcommands, `kubeadm init` (first control-plane node) and `kubeadm join` (every subsequent node, control-plane or worker).

## 2. Why This Matters

- **It's the concrete, hands-on realization of everything Part 2 covered abstractly.** The five control-plane components ([§8](../Part2/Section-08-Part2-Control-Plane-Components.md)), etcd's Raft mechanics ([§10](../Part2/Section-10-Part2-etcd-Deep-Dive-Data-Model-Raft-Consensus.md)), and the stacked-vs-external HA decision ([§15](../Part2/Section-15-Part2-High-Availability-Control-Plane-Architectures.md)) all become real, inspectable artifacts the moment `kubeadm init` completes — this section is where theory becomes a running cluster.
- **kubeadm is the substrate for CKA's "Cluster Architecture, Installation & Configuration" domain**, the exam's highest-weighted single domain area, and is also how most self-managed on-premises and lab clusters are actually built in practice, distinct from managed offerings ([§21](./Section-21-Part3-Managed-Kubernetes-Bootstrap-Differences-EKS-AKS-GKE.md)) that hide this process entirely.
- **Understanding kubeadm's bootstrap sequence directly explains cluster upgrade ordering later** ([§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) — upgrading a kubeadm cluster is, at its core, re-running a controlled version of the same bootstrap logic control-plane-node by control-plane-node, so the mental model built here transfers directly.

🔑 **Key Takeaway:** `kubeadm init` on the first control-plane node and `kubeadm join` on every other node are the only two commands doing the real work — everything else (certificates, static Pod manifests, kubeconfig generation) is kubeadm automating steps that were historically done by hand.

## 3. Prerequisites and Dependencies

Builds directly on [§8](../Part2/Section-08-Part2-Control-Plane-Components.md) (the five control-plane components kubeadm installs), [§15](../Part2/Section-15-Part2-High-Availability-Control-Plane-Architectures.md) (the stacked-vs-external etcd topology decision made at `kubeadm init` time), and [§1](../Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md) (the declarative model kubeadm's own `ClusterConfiguration` object follows). [§17](./Section-17-Part3-Static-Pods-Kubelet-Configuration.md) (next) covers the static Pod mechanism kubeadm uses to run control-plane components; [§18](./Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md)–[§20](./Section-20-Part3-Kubeconfig-Files-Contexts-Multi-Cluster-Switching.md) cover certificates, node-joining, and kubeconfig in the depth only summarized here.

## 4. Timeline: The kubeadm Bootstrap Sequence

```text
   PHASE 0: Pre-flight (on every node, before any kubeadm command)
   ─────────────────────────────────────────────────────────────
   - Install container runtime (containerd, §11)
   - Install kubeadm, kubelet, kubectl at matching versions
   - Disable swap; load required kernel modules; set sysctls
   - Ensure unique hostname, MAC address, product_uuid per node

   PHASE 1: kubeadm init (first control-plane node ONLY)
   ─────────────────────────────────────────────────────────────
   1. Pre-flight checks (ports free, swap off, runtime reachable)
   2. Generate PKI: CA + all component certificates (§18)
   3. Generate kubeconfig files (admin.conf, kubelet.conf, etc.) (§20)
   4. Render static Pod manifests for apiserver, scheduler,
      controller-manager, etcd (if stacked topology, §15) (§17)
   5. kubelet picks up static manifests from disk, starts them
   6. Wait for control plane to become healthy (self-hosted bootstrap)
   7. Install cluster DNS (CoreDNS) and kube-proxy as Deployments/DaemonSets
   8. Print the `kubeadm join` command (with bootstrap token) for
      every subsequent node to use

   PHASE 2: CNI installation (manual step, cluster-admin driven)
   ─────────────────────────────────────────────────────────────
   - Apply a CNI plugin manifest (Calico, Cilium, Flannel — §49)
   - Nodes remain NotReady until a CNI is installed

   PHASE 3: kubeadm join (every additional node)
   ─────────────────────────────────────────────────────────────
   - Worker nodes: joins as a data-plane-only node
   - Additional control-plane nodes: joins with --control-plane flag,
     replicating certs and static Pod manifests, extending etcd
     membership if stacked (§15)
```

- **kubeadm never installs a CNI plugin itself** — this is a deliberate design boundary; CNI choice is left entirely to the cluster operator, and nodes stay `NotReady` until one is applied ([§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) covers CNI selection criteria).
- **The `kubeadm join` command printed at the end of `init` embeds a short-lived bootstrap token and a CA certificate hash** — this is the trust-establishment mechanism covered fully in [§19](./Section-19-Part3-Joining-Nodes-Bootstrap-Tokens.md).

## 5. Hands-On: Bootstrapping a Minimal Cluster

### 5.1 Initializing the First Control-Plane Node

**Purpose:** Stand up the control plane on the first node using a specific, explicit configuration rather than relying entirely on flag defaults.

**Syntax:** `kubeadm init [--pod-network-cidr=<cidr>] [--control-plane-endpoint=<host:port>] [--upload-certs]`

```bash
$ sudo kubeadm init \
    --pod-network-cidr=10.244.0.0/16 \
    --control-plane-endpoint="cp-lb.internal:6443" \
    --upload-certs

[init] Using Kubernetes version: v1.30.2
[preflight] Running pre-flight checks
[certs] Generating "ca" certificate and key
[certs] Generating "apiserver" certificate and key
...
[control-plane] Creating static Pod manifest for "kube-apiserver"
[control-plane] Creating static Pod manifest for "kube-controller-manager"
[control-plane] Creating static Pod manifest for "kube-scheduler"
[etcd] Creating static Pod manifest for "etcd"
[wait-control-plane] Waiting for the kubelet to boot up the control
plane as static Pods from directory "/etc/kubernetes/manifests"
[apiclient] All control plane components are healthy

Your Kubernetes control-plane has initialized successfully!

To start using your cluster, run:
  mkdir -p $HOME/.kube
  cp -i /etc/kubernetes/admin.conf $HOME/.kube/config

Then you can join any number of worker nodes by running:
  kubeadm join cp-lb.internal:6443 --token abcdef.0123456789abcdef \
      --discovery-token-ca-cert-hash sha256:1234...
```

**Production usage example:** `--control-plane-endpoint` pointing at a load balancer's stable DNS name (not any individual node's IP) is what makes adding further control-plane replicas later possible without reconfiguring every existing client's kubeconfig — omitting it forces a painful migration later if HA is ever added retroactively, so it's set on `kubeadm init` even for an initially single-control-plane-node cluster.

**Common errors:** Running `kubeadm init` without disabling swap first fails pre-flight checks outright (`swap is enabled`) — the kubelet historically refused to start with swap enabled since Kubernetes' resource accounting model assumes it is off; this is one of the most common first-attempt bootstrap failures.

### 5.2 Applying a CNI Plugin (Cluster Remains NotReady Until This Step)

**Purpose:** Satisfy the deliberate gap kubeadm leaves open — Pod networking.

```bash
$ kubectl get nodes
NAME       STATUS     ROLES           AGE   VERSION
cp-node-1  NotReady   control-plane   3m    v1.30.2

$ kubectl apply -f https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml
namespace/kube-flannel created
...

$ kubectl get nodes
NAME       STATUS   ROLES           AGE   VERSION
cp-node-1  Ready    control-plane   4m    v1.30.2
```

**Production usage example:** Confirming `NotReady` is expected and CNI-related (rather than a deeper control-plane fault) is a very common early troubleshooting checkpoint — `kubectl describe node` at this stage typically shows a `NetworkNotReady` or CNI-plugin-not-initialized condition, distinguishable from actual kubelet or container-runtime failures.

### 5.3 Joining a Worker Node

**Purpose:** Extend the cluster's data plane using the token printed by `kubeadm init`.

**Syntax:** `kubeadm join <endpoint> --token <token> --discovery-token-ca-cert-hash sha256:<hash>`

```bash
$ sudo kubeadm join cp-lb.internal:6443 \
    --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:1234567890abcdef...

[preflight] Running pre-flight checks
[kubelet-start] Starting the kubelet
[kubelet-check] Initial timeout of 40s passed
This node has joined the cluster:
* Certificate signing request was sent to apiserver and approved
* The Kubelet was informed of the new secure connection details
```

**Production usage example:** Bootstrap tokens expire after 24 hours by default — joining additional nodes well after initial cluster creation (e.g., scaling out weeks later) requires generating a fresh token with `kubeadm token create --print-join-command` rather than reusing the original `init` output, a frequent point of confusion during later cluster scale-out ([§19](./Section-19-Part3-Joining-Nodes-Bootstrap-Tokens.md) covers token lifecycle in full).

## 6. Production Usage Notes

- **`kubeadm init` phases can be run individually** (`kubeadm init phase certs all`, `kubeadm init phase control-plane all`, etc.) — this granularity is invaluable for troubleshooting a partially failed bootstrap or for advanced customization (e.g., pre-generating certs offline before running the full init), rather than needing to restart the entire process from scratch on any single-phase failure.
- **kubeadm deliberately produces a "minimum viable" cluster, not a fully hardened production one** — sensible production deployment still requires layering on CNI choice, ingress, storage classes, monitoring, and the security hardening covered across Parts 10 and 15; kubeadm's job ends at "a correctly wired, working control plane and data plane."
- **`kubeadm upgrade` reuses this exact bootstrap machinery** to move a cluster to a new version, control-plane-node by control-plane-node, in the ordering covered fully in [§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) — the mental model of "kubeadm renders static Pod manifests and manages certs" is the same one that upgrade builds on.

## 7. Security Considerations

- **The bootstrap token is a live credential** capable of joining new nodes to the cluster during its validity window — treating the `kubeadm join` command (and its embedded token) as sensitive, not something to paste into shared chat channels or long-lived scripts, matters even though tokens are short-lived by default.
- **`--upload-certs` uploads control-plane certificates to a Secret in the cluster temporarily** so additional control-plane nodes can retrieve them during their own `kubeadm join --control-plane` — this Secret is time-limited (2 hours by default) specifically to reduce the exposure window, and should never be extended casually.
- **kubeadm's default configuration is a reasonable baseline, not a CKS-hardened one** — RBAC, admission control, Pod Security Admission, and network policy (Parts 10 and 15) all need to be layered on deliberately after bootstrap; a freshly `kubeadm init`'d cluster is functional but not yet production-hardened.

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                               | Resolution Path                                                                                                                               |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `kubeadm init` fails pre-flight with "swap is enabled"            | Swap not disabled on the node before bootstrapping                         | Disable swap (`swapoff -a` and remove the fstab entry), then retry                                                                            |
| Nodes stuck `NotReady` after successful `kubeadm init`            | No CNI plugin installed yet — expected, not a fault                        | Apply a CNI manifest (see above; full CNI comparison in [§49](../Part7/Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) |
| `kubeadm join` fails with a token/hash mismatch                   | Bootstrap token expired (default 24h) or was mistyped                      | Generate a fresh token with `kubeadm token create --print-join-command` on a control-plane node                                               |
| Additional control-plane node join fails to retrieve certificates | `--upload-certs` Secret expired (default 2h) or `init` didn't use the flag | Re-upload certs manually (`kubeadm init phase upload-certs --upload-certs`) or re-run with the flag                                           |

## 9. Best Practices

- Always set `--control-plane-endpoint` to a load-balanced DNS name at initial `kubeadm init` time, even for a single-control-plane-node cluster, since retrofitting HA onto a cluster bootstrapped without it is significantly harder than starting with it.
- Pin the container runtime, kubeadm, kubelet, and kubectl to matching, deliberately chosen versions before bootstrapping, rather than allowing package managers to install whatever is latest — version skew between these at install time is a common source of hard-to-diagnose early failures.
- Treat the printed `kubeadm join` command (and any `--upload-certs` certificate key) as short-lived secrets — regenerate them on demand for later scale-out rather than storing the original output indefinitely.

## 10. Common Anti-Patterns / Mistakes

- **Skipping `--control-plane-endpoint` on a "just for now, single control-plane node" cluster** that later needs to become HA, forcing a much harder retroactive migration than planning for it from the start.
- **Treating a freshly bootstrapped kubeadm cluster as production-ready** without layering on CNI hardening, RBAC review, admission control, and the other security work covered in Parts 10 and 15.
- **Reusing an old, expired `kubeadm join` command from documentation or a wiki page** instead of generating a fresh token, leading to confusing "token not found" or hash-mismatch failures during later scale-out.

## 11. Interview Questions

**🎯 Beginner:** _"What do `kubeadm init` and `kubeadm join` each do?"_
**Model answer:** `kubeadm init` bootstraps the very first control-plane node — it generates the cluster's certificates, renders static Pod manifests for the control-plane components, sets up etcd, and produces the admin kubeconfig, ending with a `kubeadm join` command to print for other nodes. `kubeadm join` is run on every subsequent node (worker or additional control-plane) to securely register it into the already-existing cluster using a bootstrap token and CA certificate hash for trust establishment.
_What the interviewer is probing for:_ Clear, correct separation of the two core commands' distinct responsibilities.

**🎯 Intermediate:** _"Right after `kubeadm init` finishes successfully, `kubectl get nodes` shows the control-plane node as `NotReady`. Is something broken?"_
**Model answer:** Not necessarily — this is the expected state immediately after `kubeadm init`, because kubeadm deliberately does not install a CNI plugin itself; Pod networking has to be applied as a separate, explicit step. I'd confirm this is the cause by checking `kubectl describe node` for a network-not-ready condition, then apply a CNI manifest (Flannel, Calico, or Cilium) and expect the node to transition to `Ready` shortly after.
_What the interviewer is probing for:_ Awareness that kubeadm's scope deliberately excludes CNI installation, rather than assuming any post-init `NotReady` state signals a bootstrap failure.

**🎯 Senior:** _"Why does kubeadm use short-lived bootstrap tokens and a time-limited `--upload-certs` Secret instead of simply leaving a long-lived join credential available?"_
**Model answer:** Both mechanisms exist to minimize the exposure window of highly privileged bootstrap material. A `kubeadm join` token grants the ability to register a new node into the cluster and receive an approved kubelet client certificate — a long-lived version of that credential sitting around indefinitely would be a standing risk if leaked (in logs, chat history, automation scripts). Similarly, `--upload-certs` has to temporarily place the actual control-plane CA and other certificates into a cluster Secret so a joining control-plane node can retrieve them, and leaving that Secret around indefinitely would mean anyone with read access to that namespace effectively holds the cluster's root certificates. Time-limiting both (24h for tokens by default, 2h for the upload-certs Secret) forces operators to regenerate fresh, tightly scoped credentials for legitimate later scale-out, rather than depending on a single credential minted once at cluster creation and never rotated.
_What the interviewer is probing for:_ Understanding of the underlying security rationale (minimizing standing privileged credential exposure) rather than simply knowing the default expiry numbers.

**🎯 Architect:** _"You're designing the bootstrap process for a fleet of kubeadm clusters that will be created and torn down frequently via automation. What kubeadm-specific design decisions matter most for that use case?"_
**Model answer:** I'd lean heavily on kubeadm's `ClusterConfiguration`/`InitConfiguration` YAML files (`kubeadm init --config=...`) rather than long flag lists, since a fully declarative, version-controlled config is what makes repeatable, automated bootstrap actually reliable and reviewable — this also lets me pre-pin exact component versions, the pod/service CIDR, and the etcd topology ([§15](../Part2/Section-15-Part2-High-Availability-Control-Plane-Architectures.md)) consistently across every cluster the automation creates. I'd also use kubeadm's phase subcommands (`kubeadm init phase certs all`, etc.) where the automation needs to inject externally-generated certificates or integrate with an external CA, rather than fighting the all-in-one `init` flow. For the join side, I'd have the automation mint fresh, narrowly-scoped bootstrap tokens per cluster creation via the Kubernetes API directly (rather than shelling out to parse `kubeadm init`'s printed output), since that's more reliable for a fully automated pipeline than screen-scraping CLI output. Finally, since these clusters are short-lived, I'd deliberately keep the CNI and any post-bootstrap hardening steps in the same automated pipeline immediately after `kubeadm init` completes, since a transient cluster that's momentarily unhardened is still a real, if brief, exposure window.
_What the interviewer is probing for:_ Ability to translate kubeadm's building blocks (declarative config, phase subcommands, token API) into a genuinely automation-friendly, repeatable design, rather than assuming interactive, flag-driven `kubeadm init` usage scales to a fleet context unchanged.

## 12. Common Misconceptions

1. **"kubeadm installs a complete, production-ready cluster out of the box."** It deliberately produces a minimum-viable cluster; CNI installation, security hardening, storage, and observability are all separate, deliberate follow-on steps.
2. **"kubeadm installs the CNI plugin automatically."** It never does — this is a deliberate design boundary, and nodes remain `NotReady` until an operator applies a CNI manifest explicitly.
3. **"The `kubeadm join` command printed at `init` time is valid indefinitely."** Its embedded bootstrap token expires (24 hours by default) — later node additions require generating a fresh token.
4. **"Control-plane components are installed as regular Deployments by kubeadm."** They're rendered as static Pods ([§17](./Section-17-Part3-Static-Pods-Kubelet-Configuration.md)) managed directly by the kubelet from local manifest files, not as scheduler-managed Deployments — a distinction with real operational consequences covered fully next.

## 13. 🔑 Key Takeaways

- `kubeadm init` bootstraps the first control-plane node (certs, static Pod manifests, etcd, kubeconfig); `kubeadm join` (with a bootstrap token) adds every subsequent node, worker or control-plane.
- kubeadm deliberately excludes CNI plugin installation — nodes stay `NotReady` until an operator applies one explicitly.
- Setting `--control-plane-endpoint` to a load-balanced address at initial bootstrap time, even for a single-node control plane, avoids a much harder retroactive HA migration later.
- Bootstrap tokens and `--upload-certs` Secrets are deliberately short-lived credentials — treat them as sensitive and regenerate them for later scale-out rather than reusing old ones.
- A freshly bootstrapped kubeadm cluster is functional but not yet production-hardened — CNI selection, RBAC, admission control, and CKS-level hardening are all necessary follow-on work.

## 14. Related Concepts & What's Next

[§8](../Part2/Section-08-Part2-Control-Plane-Components.md) and [§15](../Part2/Section-15-Part2-High-Availability-Control-Plane-Architectures.md) covered the components and topology this section actually installs. [§1](../Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md)'s declarative model underlies kubeadm's own `ClusterConfiguration` object. [§17](./Section-17-Part3-Static-Pods-Kubelet-Configuration.md) (next) covers static Pods in depth — the exact mechanism kubeadm uses to run every control-plane component. [§18](./Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md) covers the PKI/certificate management kubeadm generates during `init`. [§19](./Section-19-Part3-Joining-Nodes-Bootstrap-Tokens.md) covers bootstrap tokens and node-joining trust establishment in full depth. [§20](./Section-20-Part3-Kubeconfig-Files-Contexts-Multi-Cluster-Switching.md) covers kubeconfig files and multi-cluster context switching. [§21](./Section-21-Part3-Managed-Kubernetes-Bootstrap-Differences-EKS-AKS-GKE.md) contrasts this entire self-managed flow against managed offerings (EKS/AKS/GKE). [§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) covers `kubeadm upgrade`, which reuses this section's bootstrap machinery.

**Next Section:** [§17](./Section-17-Part3-Static-Pods-Kubelet-Configuration.md) — `Section-17-Part3-Static-Pods-Kubelet-Configuration.md`
