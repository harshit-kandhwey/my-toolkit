# Section 17 (Part 3): Static Pods and the Kubelet Configuration

## 1. Definition

**Plain language:** Every Pod discussed so far is created through the api-server and scheduled onto a node by kube-scheduler. Static Pods break that rule entirely: they're Pods a specific kubelet runs directly, from files sitting on that node's local disk, with no scheduler and no controller involved at all. This oddity is exactly how kubeadm runs the control plane itself — the control plane bootstraps itself using the same kubelet that runs every other workload.

**Precise definition:** A **static Pod** is a Pod managed directly by an individual node's **kubelet**, defined by a manifest file placed in a watched local directory (`/etc/kubernetes/manifests` by default on kubeadm clusters), rather than by any api-server object a scheduler assigns. The kubelet itself monitors this directory, starts/restarts/stops Pods to match the manifests found there, and — critically — creates a **mirror Pod** object on the api-server for each static Pod purely for visibility via `kubectl`, even though that mirror object cannot be edited or deleted through the normal API to affect the real Pod.

## 2. Why This Matters

- **It's the actual mechanism behind kubeadm's control-plane bootstrap** (§16) — kube-apiserver, kube-scheduler, kube-controller-manager, and (in stacked topology, §15) etcd are themselves static Pods, which resolves the apparent chicken-and-egg problem of "how does the control plane start before there's a scheduler to schedule it."
- **Recognizing a mirror Pod versus a real, api-server-owned Pod changes troubleshooting entirely** — `kubectl delete pod` on a static Pod's mirror only deletes the mirror momentarily; the kubelet recreates it immediately from the manifest still on disk, which is confusing without understanding this section's model (§99, Part 13 depends on this distinction directly).
- **It clarifies exactly what the kubelet does versus what the rest of the control plane does**, sharpening the data-plane/control-plane split first introduced in §3 and the component breakdown in §8 — the kubelet is capable of running workloads entirely independently of the api-server when necessary, which is precisely why it's the right component to bootstrap the control plane itself.

🔑 **Key Takeaway:** Static Pods are managed directly by a node's local kubelet from on-disk manifest files, completely bypassing the scheduler and controller-manager — this is the exact mechanism kubeadm uses to run the control plane's own components, and the api-server's visible "copy" of a static Pod (the mirror Pod) cannot be deleted or edited away by normal API operations.

## 3. Prerequisites and Dependencies

Builds directly on §8 (control-plane components, which static Pods are used to run), §9 (the kubelet's role among node components), and §16 (kubeadm's bootstrap sequence, which relies entirely on this mechanism). §18 (certificates) and §106 (Part 14, cluster upgrades) both depend on understanding exactly how these manifests are managed.

## 4. Architecture Diagram: Static Pod Lifecycle

```text
   Control-plane node's local filesystem
   ┌───────────────────────────────────────────┐
   │  /etc/kubernetes/manifests/               │
   │    ├── kube-apiserver.yaml                │
   │    ├── kube-scheduler.yaml                │
   │    ├── kube-controller-manager.yaml       │
   │    └── etcd.yaml   (stacked topology only)│
   └───────────────────┬───────────────────────┘
                       │  kubelet watches this
                       │  directory continuously
                       ▼
              ┌────────────────────────┐
              │        kubelet         │
              │  (this node's kubelet, │
              │   config below)        │
              └──────────┬─────────────┘
                         │  starts/restarts Pods
                         │  directly via container
                         │  runtime — NO scheduler,
                         │  NO controller-manager
                         │  involved at any point
                         ▼
              ┌────────────────────────┐
              │  Running container(s)  │
              └──────────┬─────────────┘
                         │  kubelet ALSO reports a
                         │  "mirror Pod" to the
                         │  api-server, purely for
                         │  kubectl visibility
                         ▼
              ┌─────────────────────────┐
              │  kube-apiserver         │
              │  (mirror Pod object —   │
              │   visible via kubectl,  │
              │   but NOT authoritative;│
              │   deleting it via the   │
              │   API doesn't stop the  │
              │   real static Pod)      │
              └─────────────────────────┘
```

- **The manifest directory is the single source of truth for a static Pod** — editing the file directly (add, change, remove) is what changes the running Pod; deleting the mirror Pod via `kubectl delete` has no lasting effect since the kubelet simply recreates the mirror from the manifest still present on disk.
- **The kubelet's own configuration (not a manifest file) tells it which directory to watch** — this is set via `staticPodPath` in the kubelet's configuration file, covered next.

## 5. Hands-On: Working With Static Pods and Kubelet Config

### 5.1 Locating and Modifying a Control-Plane Static Pod

**Purpose:** Directly observe that editing the manifest file — not any `kubectl` command — is what changes a static Pod.

**Syntax:** edit the manifest file in place; the kubelet detects the change automatically (typically within seconds).

```bash
$ ls /etc/kubernetes/manifests/
etcd.yaml  kube-apiserver.yaml  kube-controller-manager.yaml  kube-scheduler.yaml

$ kubectl get pods -n kube-system -o wide | grep apiserver
kube-apiserver-cp-node-1   1/1   Running   0   30d   10.0.1.10   cp-node-1

$ sudo vi /etc/kubernetes/manifests/kube-apiserver.yaml
# (e.g., adjust --audit-log-maxage, a flag under spec.containers[0].command)

$ kubectl get pods -n kube-system -w | grep apiserver
kube-apiserver-cp-node-1   1/1   Terminating   0   30d   10.0.1.10   cp-node-1
kube-apiserver-cp-node-1   0/1   Pending       0   1s    <none>      cp-node-1
kube-apiserver-cp-node-1   1/1   Running       0   4s    10.0.1.10   cp-node-1
```

**Production usage example:** This is precisely how kubeadm-managed clusters apply control-plane flag changes in practice — e.g., enabling audit logging or adjusting admission plugin flags on kube-apiserver means editing this manifest file directly on each control-plane node, not submitting any `kubectl` change, since these are exactly the components running as static Pods.

**Common errors:** Attempting `kubectl edit pod kube-apiserver-cp-node-1` and expecting the change to persist — edits to the mirror Pod object are not propagated back to the manifest file and are overwritten the moment the kubelet next reconciles against the actual file on disk.

### 5.2 Inspecting and Changing the Kubelet's Own Configuration

**Purpose:** See where `staticPodPath` and other node-level kubelet behavior (its own log level, resource reservation, eviction thresholds) are actually configured.

**Syntax:** kubelet configuration file, typically `/var/lib/kubelet/config.yaml` on kubeadm clusters, referenced by `--config` in the kubelet's systemd unit.

```bash
$ cat /var/lib/kubelet/config.yaml
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
staticPodPath: /etc/kubernetes/manifests
cgroupDriver: systemd
evictionHard:
  memory.available: "100Mi"
  nodefs.available: "10%"

$ systemctl status kubelet | grep -A2 "Drop-In"
   Drop-In: /etc/systemd/system/kubelet.service.d
           └─10-kubeadm.conf
```

**Production usage example:** `cgroupDriver` mismatches between the kubelet's configuration and the container runtime's own cgroup driver setting are one of the most common causes of a kubelet that fails to start cleanly after a manual OS-level change (e.g., an OS upgrade that alters the default cgroup driver) — matching this value in both places is a standard first check during node-level bootstrap troubleshooting.

**Common errors:** Editing `/var/lib/kubelet/config.yaml` and expecting changes to apply without a kubelet restart — unlike static Pod manifests (which the kubelet actively watches), its own configuration file is read once at kubelet startup, requiring `systemctl restart kubelet` to take effect.

### 5.3 Distinguishing a Static Pod From a Regular Pod at a Glance

**Purpose:** Build the quick-recognition skill needed during an incident, since static Pods and regular Pods otherwise look identical in `kubectl get pods` output.

```bash
$ kubectl get pod kube-apiserver-cp-node-1 -n kube-system -o jsonpath='{.metadata.ownerReferences}'
[{"apiVersion":"v1","kind":"Node","name":"cp-node-1","uid":"..."}]
```

**Interpretation:** A static Pod's mirror object has an `ownerReference` pointing to a **Node**, never to a ReplicaSet, DaemonSet, or other controller — this is the definitive, scriptable signal distinguishing it from any controller-managed Pod, and also explains why deleting it via the API is futile: there's no controller to "notice" and act on the deletion the way a ReplicaSet would.

**Production usage example:** Automated tooling that audits "is this workload managed the normal way" (e.g., a policy engine flagging unexpected static Pods outside `kube-system` as a potential security concern, §113) relies on exactly this `ownerReference` check rather than the Pod's naming convention alone, since names alone can be spoofed by any regular Pod.

## 6. Production Usage Notes

- **Static Pods are also occasionally used deliberately outside the control plane** — e.g., a node-local monitoring agent that must run even if the api-server is entirely unreachable, though DaemonSets (§34, Part 5) are strongly preferred for that use case whenever api-server connectivity can be assumed, since DaemonSets are visible and manageable the normal way.
- **The kubelet's `--config` flag (pointing at `config.yaml`) superseded a long deprecated era of purely command-line kubelet flags** — modern kubeadm clusters manage almost all kubelet behavior through this file plus a small kubeadm-managed systemd drop-in, rather than a long flag list in the unit file itself.
- **Static Pod manifest changes on one control-plane node do not propagate to others** — in a multi-control-plane-node HA cluster (§15), a flag change intended cluster-wide (e.g., an audit policy update) must be applied to every control-plane node's manifest individually; there's no built-in mechanism to fan a manifest change out automatically.

## 7. Security Considerations

- **Filesystem access to `/etc/kubernetes/manifests` on a control-plane node is equivalent to control-plane compromise** — anyone able to write a manifest there can run arbitrary privileged workloads outside the api-server's normal authentication/authorization/admission pipeline entirely, since static Pods bypass that pipeline by design; this makes node-level filesystem access control a top-tier control-plane hardening concern (§113, Part 15).
- **Static Pods are not subject to admission controllers** (§77) the way normal api-server-created Pods are, since they never go through the api-server's creation path at all — this is precisely why control-plane node access itself must be treated as a privileged security boundary, not something admission policy can compensate for.
- **The kubelet's own configuration file and client certificates on disk are high-value targets** — compromising a node's kubelet identity can allow an attacker to masquerade as that node when communicating with the api-server, a scenario covered in the Node authorization mode discussion in Part 10 (§73–§74).

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                             | Resolution Path                                                                                           |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Editing a static Pod's mirror via `kubectl edit` doesn't persist   | Expected behavior — mirror Pods aren't authoritative                     | Edit the manifest file directly in `/etc/kubernetes/manifests` on that node instead                       |
| `kubectl delete pod kube-apiserver-...` doesn't actually remove it | Expected behavior — kubelet recreates it from the manifest still on disk | Remove or move the manifest file itself if the Pod should genuinely stop running                          |
| Kubelet won't start after an OS-level change                       | `cgroupDriver` mismatch between kubelet config and container runtime     | Align `cgroupDriver` in `/var/lib/kubelet/config.yaml` with the runtime's configured driver, then restart |
| Static Pod manifest edited but the Pod never picks up the change   | Typo/YAML syntax error in the manifest, silently ignored by the kubelet  | Validate YAML syntax carefully; check kubelet logs (`journalctl -u kubelet`) for parse errors             |

## 9. Best Practices

- Always edit control-plane static Pod manifests directly on the relevant node's filesystem, never attempt the change via `kubectl`, and remember to replicate the same manifest change across every control-plane node in an HA cluster (§15).
- Keep `evictionHard` and other kubelet-level thresholds in `config.yaml` deliberately tuned per node class rather than left at defaults, since default eviction thresholds are conservative generic values, not tuned for every workload profile.
- Reserve static Pods for genuinely node-local, bootstrap-relevant, or api-server-independent use cases; prefer DaemonSets for anything that can assume normal api-server availability, since DaemonSets remain visible and manageable the ordinary way.

## 10. Common Anti-Patterns / Mistakes

- **Trying to manage or "fix" a misbehaving control-plane component through `kubectl` alone** (edit, delete, patch) without realizing it's a static Pod and that the manifest file on disk is the actual source of truth.
- **Forgetting that a multi-control-plane-node HA cluster requires manifest edits on every node individually** — assuming a single edited manifest propagates cluster-wide the way a Deployment update would.
- **Using static Pods for ordinary application workloads** instead of Deployments or DaemonSets, losing scheduler placement logic, controller-driven self-healing across node loss, and normal admission-control enforcement for no real benefit.

## 11. Interview Questions

**🎯 Beginner:** _"What is a static Pod, and how is it different from a normal Pod?"_
**Model answer:** A static Pod is managed directly by a single node's kubelet, based on a manifest file sitting on that node's local disk, rather than being created through the api-server and scheduled by kube-scheduler like a normal Pod. The kubelet also reports a "mirror Pod" to the api-server so it's visible via `kubectl`, but that mirror can't be edited or deleted through the API to actually change the real Pod — only editing the manifest file itself does that.
_What the interviewer is probing for:_ Basic grasp of the local-manifest mechanism and the mirror-Pod visibility-only concept.

**🎯 Intermediate:** _"Why does kubeadm run the control plane's own components as static Pods instead of as regular Deployments?"_
**Model answer:** It resolves a bootstrapping paradox — a Deployment needs a working scheduler and controller-manager to be created and kept running, but the scheduler and controller-manager are themselves part of the control plane being bootstrapped. Static Pods sidestep this entirely because the kubelet can start them directly from a local manifest file with zero dependency on any other control-plane component being up yet — the kubelet is the one component that can run workloads completely independently, which makes it the right tool for bringing the rest of the control plane to life.
_What the interviewer is probing for:_ Understanding of the actual bootstrapping problem static Pods solve, not just the mechanical definition.

**🎯 Senior:** _"You need to change an admission-plugin flag on kube-apiserver across a 3-control-plane-node HA cluster. Walk through exactly what you'd do and why `kubectl` alone can't do it."_
**Model answer:** Since kube-apiserver runs as a static Pod on each control-plane node, I'd edit `/etc/kubernetes/manifests/kube-apiserver.yaml` directly on each of the three control-plane nodes individually, adding or adjusting the relevant `--enable-admission-plugins` flag under the container command. `kubectl` can't do this because the mirror Pod object visible via the API isn't authoritative — the kubelet on each node is watching that node's local manifest directory and will simply recreate the Pod from the file on disk if I try to patch or delete the mirror instead. I'd also make the change on one node first, confirm the api-server restarts cleanly and stays healthy (checking `kubectl get pods -n kube-system` and the component's own logs) before repeating it on the other two, to avoid taking all three api-server replicas down simultaneously with a bad flag value.
_What the interviewer is probing for:_ Practical, correct procedure grounded in genuinely understanding why the static-Pod/mirror-Pod split makes `kubectl`-only approaches ineffective, plus sound operational sequencing across an HA topology.

**🎯 Architect:** _"Your organization wants a lightweight node-local agent that must keep running and reporting even during an extended api-server outage. Static Pods look tempting since they don't depend on the api-server at all — what's your actual recommendation and why?"_
**Model answer:** I'd recommend against a static Pod for this despite the surface-level appeal, and instead design around a DaemonSet with appropriate tolerations, understanding that the DaemonSet controller itself does depend on api-server availability to reconcile — but the already-running Pods it created keep running locally on each node's kubelet regardless of api-server availability, since the kubelet doesn't need the api-server to keep an already-scheduled Pod's containers alive. The static-Pod route would work for the "keeps running during an outage" requirement, but it sacrifices everything else that makes a fleet-wide agent operationally sane: no normal visibility or lifecycle management through the api-server for anything beyond the mirror Pod, no admission-control enforcement, no easy fleet-wide rollout of an updated agent version without editing files on every node's disk individually, and no ownerReference-based tooling compatibility (as described above). If there's a genuinely bootstrap-level requirement — the agent must run before any api-server exists at all, which is not the case here — static Pods would be justified; for "must survive a temporary outage of an already-bootstrapped cluster," a DaemonSet already satisfies that without giving up the operational benefits of being a normal, api-server-visible workload.
_What the interviewer is probing for:_ Ability to correctly separate "must survive an outage of an existing cluster" (DaemonSet handles this fine) from "must exist before the control plane itself exists" (the actual static-Pod use case), rather than reflexively reaching for static Pods whenever api-server independence sounds appealing.

## 12. Common Misconceptions

1. **"You can delete or edit a static Pod through `kubectl` like any other Pod."** The visible object is a non-authoritative mirror; only editing the manifest file on the node's disk actually changes the real Pod.
2. **"Static Pods are scheduled by kube-scheduler like normal Pods."** They're never scheduled at all — the kubelet on the specific node hosting the manifest file runs them directly, with no scheduler involvement.
3. **"Editing the kubelet's own `config.yaml` takes effect immediately, the same way editing a static Pod manifest does."** It doesn't — the kubelet only reads its own configuration file at startup, requiring an explicit kubelet restart for changes to apply.
4. **"Static Pods are a legacy or deprecated mechanism."** They remain the current, actively used, and correct mechanism kubeadm relies on today to bootstrap the control plane — not a holdover awaiting replacement.

## 13. 🔑 Key Takeaways

- Static Pods are managed directly by a node's local kubelet from on-disk manifest files (default `/etc/kubernetes/manifests`), completely bypassing kube-scheduler and kube-controller-manager.
- The api-server's visible copy of a static Pod is a non-authoritative mirror Pod — deleting or editing it via `kubectl` has no lasting effect; the manifest file on disk is the real source of truth.
- This mechanism is exactly how kubeadm resolves the bootstrapping paradox of running a control plane that itself needs a working control plane to be scheduled.
- A static Pod's mirror object always has an `ownerReference` pointing to a Node, never a controller — the definitive, scriptable way to distinguish it from a normal Pod.
- The kubelet's own configuration file (`config.yaml`, including `staticPodPath`) is read only at kubelet startup and requires a restart to apply changes, unlike the actively-watched static Pod manifest directory.

## 14. Related Concepts & What's Next

§8 covered the control-plane components this section's mechanism actually runs; §9 covered the kubelet's broader role among node components. §16 relied on this exact static-Pod mechanism during `kubeadm init`. §18 (next) covers the certificates and PKI kubeadm generates, much of which is referenced directly inside these same static Pod manifests as certificate file paths. §34 (Part 5) covers DaemonSets, the strongly preferred alternative for node-local workloads that can assume api-server availability. §73–§74 (Part 10) cover Node authorization and kubelet identity security in depth. §106 (Part 14) covers cluster upgrades, which manipulate these same static Pod manifests under kubeadm's automated control.

**Next Section:** §18 — `Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md`
