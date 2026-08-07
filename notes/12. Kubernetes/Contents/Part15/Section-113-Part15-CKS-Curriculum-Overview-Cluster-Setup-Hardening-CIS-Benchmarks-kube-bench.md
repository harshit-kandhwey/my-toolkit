# Section 113 (Part 15): CKS Curriculum Overview and Cluster Setup Hardening (CIS Benchmarks, kube-bench)

## 1. Definition

**Plain language:** [§81](../Part10/Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md) closed Part 10 with a four-layer checklist synthesizing identity, admission policy, network containment, and credential hygiene into a single hardening review. That checklist assumed a CKA-level familiarity with each mechanism. CKS starts from a different premise: it assumes you already hold an active CKA, already know RBAC, NetworkPolicy, and Pod Security Admission cold, and instead tests whether you can harden a cluster against a determined attacker who has already found a foothold — a compromised container, a leaked credential, a malicious image — not just configure controls correctly on a clean slate.

**Precise definition:** The **Certified Kubernetes Security Specialist (CKS)** exam is a 2-hour, entirely performance-based Linux Foundation certification (requiring an active CKA as a prerequisite) organized around six official domains: **Cluster Setup** (10%), **Cluster Hardening** (15%), **System Hardening** (15%), **Minimize Microservice Vulnerabilities** (20%), **Supply Chain Security** (20%), and **Monitoring, Logging and Runtime Security** (20%). This section covers the first domain's core tooling: the **CIS (Center for Internet Security) Kubernetes Benchmark**, a versioned, publicly maintained document specifying hundreds of concrete, numbered configuration checks (file permissions, flag settings, TLS configuration) across every control-plane and node component, and **kube-bench**, an open-source Go tool by Aqua Security that automates running those exact checks against a live cluster and reports pass/fail/warn per benchmark item.

## 2. Why This Matters

- **CKS is the only one of the three Linux Foundation Kubernetes certifications that requires another certification (active CKA) as a hard prerequisite** — the exam writers deliberately assume baseline mechanism fluency ([§73](../Part10/Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md)–[§81](../Part10/Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md)) and spend the entire allotted time on adversarial, attacker-perspective scenarios instead.
- **The CIS Benchmark is not Kubernetes-specific trivia — it is the same document real compliance audits (SOC 2, PCI-DSS, FedRAMP) reference when asking "is this cluster hardened to a recognized standard"**, meaning kube-bench fluency is directly transferable to production compliance work, not just exam preparation.
- **Cluster Setup is the lowest-weighted CKS domain (10%) but is disproportionately fast to verify in the exam's tight time budget** — a `kube-bench run` and reading its output is a five-minute investment that reliably captures easy points other candidates skip under time pressure.

🔑 **Key Takeaway:** CKS builds on CKA-level mechanism knowledge (Part 10) to test cluster hardening from an attacker's perspective across six weighted domains; the CIS Kubernetes Benchmark and its automation tool kube-bench are the concrete, checkable standard behind the lowest-effort, highest-return portion of that hardening work — Cluster Setup.

## 3. Prerequisites and Dependencies

This section assumes completion of Part 10 in full ([§73](../Part10/Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md)–[§81](../Part10/Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md)), particularly [§81](../Part10/Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md)'s layered checklist, which this Part now extends with attacker-focused, exam-specific depth. It also assumes the CKA-level cluster architecture knowledge from Part 2 (control plane and node components) and Part 3 (kubeadm bootstrapping), since CIS Benchmark checks target exactly those components' configuration files and flags. Forward-references [§114](./Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md), which moves from cluster-level configuration hardening into host-OS-level attack surface reduction.

## 4. Architecture: Where kube-bench Fits in the Hardening Workflow

```text
┌───────────────────────────────────────────────────────────────────────┐
│  CIS Kubernetes Benchmark (versioned PDF/spec, e.g. v1.24)            │
│    Section 1: Control Plane Components (API server, etcd, scheduler)  │
│    Section 2: etcd                                                    │
│    Section 3: Control Plane Configuration                             │
│    Section 4: Worker Nodes (kubelet, kube-proxy)                      │
│    Section 5: Kubernetes Policies (RBAC, Pod Security, NetworkPolicy) │
└────────────────────────────────┬──────────────────────────────────────┘
                                 │  encoded as
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  kube-bench (Go binary or Job/DaemonSet)                              │
│    Reads target-specific YAML check definitions (cfg/<version>/)      │
│    Executes each check: file perms, process flags, config values      │
└────────────────────────────────┬──────────────────────────────────────┘
                                 │  runs AS a Job on each node type
                                 ▼
        ┌────────────────────────┬────────────────────────┐
        ▼                        ▼                        ▼
  Control-plane node        Worker node               etcd node
  (--targets master)   (--targets node)          (--targets etcd)
        │                        │                        │
        ▼                        ▼                        ▼
   [PASS] [FAIL] [WARN] per numbered check, with remediation text printed
                                 │
                                 ▼
              Manual or scripted remediation → re-run to confirm
```

- **kube-bench ships versioned check definitions matched to specific Kubernetes releases** (`cfg/cis-1.24/`, `cfg/eks-1.2.0/`, etc.) — running the wrong version's checks against a cluster produces false positives and false negatives, since flag names and defaults shift across CIS Benchmark revisions.
- **kube-bench must run with access to the actual node filesystem and process list to check things like file permissions on `/etc/kubernetes/manifests/kube-apiserver.yaml`** — this is why it's typically deployed as a Job with `hostPID` and specific `hostPath` volume mounts, not a normal application Pod, which is itself a security-relevant exception worth noting.
- **Managed Kubernetes offerings (EKS, AKS, GKE) hide or fully manage the control-plane node**, so kube-bench ships separate `eks-1.2.0`/`gke-1.2.0` profiles that skip checks against components the cloud provider controls and the customer cannot remediate anyway.

## 5. Hands-On: Running and Interpreting kube-bench

### 5.1 Running kube-bench as a Job Against Control-Plane and Worker Nodes

**Purpose:** Execute the CIS Benchmark checks against a kubeadm-bootstrapped cluster and retrieve results.

**Syntax:**

```bash
# Download and apply the official Job manifest (auto-detects node role via nodeSelector)
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job.yaml

# For a control-plane node specifically
kubectl apply -f https://raw.githubusercontent.com/aquasecurity/kube-bench/main/job-master.yaml
```

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: kube-bench-master
spec:
  template:
    spec:
      hostPID: true
      containers:
        - name: kube-bench
          image: aquasec/kube-bench:v0.7.2
          command: ["kube-bench", "run", "--targets", "master"]
          volumeMounts:
            - name: var-lib-etcd
              mountPath: /var/lib/etcd
              readOnly: true
            - name: etc-kubernetes
              mountPath: /etc/kubernetes
              readOnly: true
      restartPolicy: Never
      volumes:
        - name: var-lib-etcd
          hostPath:
            path: /var/lib/etcd
        - name: etc-kubernetes
          hostPath:
            path: /etc/kubernetes
```

**Example usage and expected output:**

```bash
$ kubectl logs job/kube-bench-master
[INFO] 1 Control Plane Security Configuration
[PASS] 1.1.1 Ensure that the API server pod specification file permissions are set to 600 or more restrictive
[FAIL] 1.2.7 Ensure that the --authorization-mode argument includes Node
[WARN] 1.2.16 Ensure that the admission control plugin PodSecurityPolicy is set (Manual)

== Summary ==
41 checks PASS
3 checks FAIL
7 checks WARN
0 checks INFO
```

**Production usage example:** A `WARN` result for a deprecated check (like `PodSecurityPolicy`, removed in v1.25 and superseded by PSA, [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) is expected and should be documented as intentionally not applicable, not chased as a real finding — kube-bench's check definitions don't always keep pace with deprecations, so blindly remediating every WARN can waste real hardening effort on a non-issue.

**Common errors:** Running kube-bench with the default (unversioned) target detection against a cluster running a Kubernetes minor version the installed kube-bench release doesn't recognize — it silently falls back to the closest matching profile, which can produce checks against flags that don't exist in your actual version. Always pin `--version` or a specific `cfg` directory explicitly in production audits.

### 5.2 Remediating a Failed CIS Check

**Purpose:** Fix a real `FAIL` result — an overly permissive API server authorization mode.

**Syntax:**

```bash
# Locate the static Pod manifest (§17-adjacent: static Pods, Part 3)
sudo vi /etc/kubernetes/manifests/kube-apiserver.yaml
```

```yaml
# Before (fails 1.2.7)
- --authorization-mode=AlwaysAllow

# After (passes 1.2.7)
- --authorization-mode=Node,RBAC
```

**Example usage and expected output:**

```bash
$ sudo systemctl status kubelet   # kubelet watches the manifest directory and restarts the static Pod automatically
$ kubectl get pods -n kube-system kube-apiserver-controlplane01
NAME                            READY   STATUS    RESTARTS   AGE
kube-apiserver-controlplane01   1/1     Running   1          12s
# Re-run kube-bench; 1.2.7 now shows PASS
```

**Production usage example:** Editing a static Pod manifest in place is exactly how kube-bench remediations are applied on kubeadm clusters — no `kubectl apply` involved, since the kubelet ([§17](../Part3/Section-17-Part3-Static-Pods-Kubelet-Configuration.md)-adjacent, Part 3) watches the manifest directory directly and restarts the Pod on any file change.

**Common errors:** Editing the manifest with a typo and leaving the cluster with no functioning API server at all, since a malformed static Pod spec simply fails to start with no `kubectl` available to diagnose it (the API server itself is down) — always keep a manifest backup (`cp kube-apiserver.yaml kube-apiserver.yaml.bak`) before editing, and validate YAML syntax offline first.

## 6. Production Usage Notes

- **kube-bench should run on a recurring schedule (as a CronJob, [§36](../Part5/Section-36-Part5-CronJobs-Scheduled-Job-Execution.md), Part 5) in production, not just once during initial hardening** — control-plane flags and file permissions can drift after an upgrade ([§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md), Part 14) reintroduces a default that had been previously hardened away.
- **On managed Kubernetes (EKS/AKS/GKE), most Section 1–3 (control plane) checks are inapplicable** since the cloud provider owns that infrastructure — kube-bench's cloud-specific profiles (`eks-1.2.0`, etc.) scope checks down to what the customer actually controls (worker nodes, RBAC, Pod policies), and running the generic profile against a managed cluster produces a flood of irrelevant FAILs.
- **kube-bench output should feed into the same observability pipeline referenced in [§81](../Part10/Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md)** (Part 12's stack) so hardening drift is caught the same way RBAC and NetworkPolicy drift is — as continuous monitoring, not a point-in-time exam-style pass.

## 7. Security Considerations

- **Who is allowed to modify static Pod manifests and kubelet configuration is itself a critical security boundary** — anyone with SSH/filesystem access to a control-plane node can alter `--authorization-mode` or any other hardened flag directly, bypassing RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) entirely; host-level access control (SSH keys, sudoers, bastion hosts) is a prerequisite this section's kube-bench checks cannot themselves enforce.
- **A misconfigured or bypassed hardening check is worse than an unrun one, because it creates false confidence** — a team that ran kube-bench once, fixed the reported FAILs, and never re-ran it after subsequent cluster changes believes it is compliant while actually having silently regressed; treat a single clean kube-bench run as a snapshot, not a permanent certification.
- **kube-bench itself requires elevated access (hostPID, hostPath mounts to `/etc/kubernetes` and `/var/lib/etcd`) to function**, meaning the tool doing the hardening check is itself a high-privilege workload that must be tightly scoped (run as a one-shot Job, not a long-lived Deployment) and its own RBAC/image provenance ([§116](./Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)) verified before being trusted in a production cluster.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Cause                                                                           | Fix                                                                                                                                                                             |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| kube-bench reports checks for flags that don't exist in this version | Wrong or auto-detected CIS profile version mismatched to actual cluster version | Pin `--version` explicitly or select the matching `cfg/cis-<version>/` directory                                                                                                |
| Large number of unexpected FAILs on a managed cluster (EKS/AKS/GKE)  | Running the generic CIS profile instead of the cloud-specific one               | Use the vendor profile (`--benchmark eks-1.2.0`, etc.) which scopes out provider-managed checks                                                                                 |
| API server fails to start after editing its static Pod manifest      | YAML syntax error or invalid flag combination introduced during remediation     | Restore from a pre-edit manifest backup; validate YAML offline before re-applying                                                                                               |
| WARN results for PodSecurityPolicy-related checks                    | kube-bench's check definitions reference deprecated PSP (removed in v1.25)      | Document as not applicable; verify equivalent coverage via Pod Security Admission ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) instead |

## 9. Best Practices

- Pin kube-bench's version and CIS profile explicitly to match the cluster's actual Kubernetes version rather than relying on auto-detection.
- Run kube-bench on a recurring CronJob schedule ([§36](../Part5/Section-36-Part5-CronJobs-Scheduled-Job-Execution.md)) and pipe results into the same observability stack ([§81](../Part10/Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md)) used for other drift detection.
- Always back up a static Pod manifest before editing it as part of remediation, given the API server's own availability depends on that same file being valid.
- On managed Kubernetes, use the provider-specific kube-bench profile and treat control-plane-owned checks as informational only, not actionable.

## 10. Common Anti-Patterns / Mistakes

- **Running kube-bench once during initial setup and treating a clean result as permanent**, missing drift introduced by later upgrades or manual configuration changes.
- **Chasing every WARN as if it were a hard FAIL**, including deprecated checks (like PodSecurityPolicy) that no longer reflect current Kubernetes best practice.
- **Running the generic CIS profile against a managed Kubernetes cluster** and wasting remediation effort on control-plane components the customer doesn't actually control.

## 11. Interview Questions

**🎯 Beginner:** _"What is kube-bench, and what does it check?"_
**Model answer:** kube-bench is an open-source tool that automates running the CIS Kubernetes Benchmark's checks against a live cluster — things like file permissions on control-plane manifests, whether specific insecure flags are set on the API server or kubelet, and whether RBAC and Pod Security policies meet baseline recommendations. It reports each numbered check as PASS, FAIL, or WARN with remediation guidance.
_What the interviewer is probing for:_ Basic recall of what the tool does and its relationship to the CIS Benchmark as the underlying standard.

**🎯 Intermediate:** _"Why does kube-bench need `hostPID` and hostPath mounts, and what's the security implication of that?"_
**Model answer:** Many CIS checks require inspecting actual file permissions on the host filesystem (like `/etc/kubernetes/manifests/kube-apiserver.yaml`) and process-level flags that aren't visible from inside a normal, isolated container — hostPID and hostPath mounts to directories like `/etc/kubernetes` and `/var/lib/etcd` give kube-bench that visibility. The security implication is that the auditing tool itself becomes a high-privilege workload, so it should run as a short-lived, one-shot Job rather than a persistent Deployment, and its image provenance should be verified like any other high-trust component.
_What the interviewer is probing for:_ Understanding that security tooling itself carries risk and must be scoped carefully, not treated as automatically trustworthy because its purpose is defensive.

**🎯 Senior:** _"A team ran kube-bench once during cluster setup, fixed all FAILs, and considers the cluster 'CIS-compliant.' What's wrong with that claim, and how would you fix the process?"_
**Model answer:** A single clean run is a point-in-time snapshot, not a durable compliance state — subsequent cluster upgrades ([§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) can reset flags to new defaults, manual `kubectl edit` or SSH access to control-plane nodes can silently reintroduce a previously-fixed misconfiguration, and new worker nodes joined later may never have been checked at all. I'd convert this into a recurring CronJob ([§36](../Part5/Section-36-Part5-CronJobs-Scheduled-Job-Execution.md)) running kube-bench on a schedule, with results piped into the observability/alerting stack ([§81](../Part10/Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md)) so any regression is caught within a day, not discovered at the next annual audit. I'd also gate infrastructure-as-code changes to control-plane configuration through review so kube-bench findings map back to a specific change, not an untraceable manual edit.
_What the interviewer is probing for:_ Recognition that compliance is a continuous property, not a one-time event, and the ability to design drift detection rather than accept a single audit as sufficient.

**🎯 Architect:** _"Design a CIS-compliance program across a 50-cluster fleet spanning self-managed kubeadm clusters and multiple managed cloud providers."_
**Model answer:** I'd first partition the fleet by control-plane ownership model, since kube-bench's applicable check set differs materially: self-managed kubeadm clusters get the full generic CIS profile, while EKS/AKS/GKE clusters get their respective vendor profiles that correctly scope out provider-managed control-plane checks. I'd deploy kube-bench as a recurring CronJob on every cluster, aggregating results centrally (rather than per-cluster dashboards) into a fleet-wide compliance view categorized by check severity and cluster type, so a single team can prioritize remediation without needing 50 separate reviews. For any FAIL that requires a static Pod manifest edit on self-managed clusters, I'd push the fix through the same infrastructure-as-code pipeline that provisions the cluster (kubeadm config, Ansible, or equivalent) rather than allowing ad hoc SSH-based edits, ensuring the fix is reproducible and doesn't silently regress on the next node rebuild. For managed clusters, I'd track provider-side compliance separately (since those checks require the cloud vendor's own attestations, not something kube-bench itself can remediate) and document that scoping explicitly for the compliance audit. Finally, I'd version-pin kube-bench and its CIS profile per cluster's actual Kubernetes minor version, updating that mapping as part of the same upgrade runbook ([§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) that handles version skew, so an upgrade never silently causes kube-bench to check the wrong profile.
_What the interviewer is probing for:_ Fleet-scale thinking about heterogeneous infrastructure ownership models, correct scoping of what's actually remediable per platform, and integrating compliance checking into existing infrastructure-as-code and upgrade processes rather than treating it as a bolt-on audit.

## 12. Common Misconceptions

1. **"CKS can be attempted without holding CKA."** CKS requires an active CKA certification as a hard prerequisite — it is not an independent, standalone exam.
2. **"kube-bench's WARN results are all real findings that must be fixed."** Many WARN results reference manual-verification-only or deprecated checks (like PodSecurityPolicy); they require human judgment, not blind remediation.
3. **"Running kube-bench once is equivalent to being permanently CIS-compliant."** Compliance drifts continuously as clusters are upgraded and manually modified; kube-bench must run on a recurring schedule to remain meaningful.
4. **"The generic CIS Kubernetes Benchmark applies identically to managed cloud clusters."** EKS/AKS/GKE require their own vendor-specific kube-bench profiles, since the customer doesn't control (and can't remediate) the cloud provider's control-plane components.

## 13. 🔑 Key Takeaways

- CKS requires an active CKA and shifts focus from mechanism knowledge to attacker-perspective cluster hardening across six weighted domains.
- The CIS Kubernetes Benchmark is the concrete, versioned standard behind real compliance audits, not exam-only trivia.
- kube-bench automates CIS checks as a Job requiring hostPID/hostPath access — itself a high-privilege tool that must be scoped carefully.
- Remediation on kubeadm clusters typically means editing static Pod manifests directly, with the kubelet auto-restarting the affected component.
- Compliance is continuous, not a one-time pass — recurring kube-bench runs feeding an observability pipeline are what keep a cluster genuinely hardened over time.

## 14. Related Concepts & What's Next

This section opened Part 15 by framing CKS's relationship to CKA-level Part 10 knowledge and introduced the CIS Kubernetes Benchmark and kube-bench as the concrete tooling behind the Cluster Setup domain. [§114](./Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md), next, moves one layer down the stack — from cluster-level configuration hardening into the host operating system itself, covering how seccomp and AppArmor profiles restrict what a container's underlying process can actually do at the kernel level, minimizing host OS attack surface beyond what cluster configuration alone can address.

**Next Section:** [§114](./Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md) — `Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md`
