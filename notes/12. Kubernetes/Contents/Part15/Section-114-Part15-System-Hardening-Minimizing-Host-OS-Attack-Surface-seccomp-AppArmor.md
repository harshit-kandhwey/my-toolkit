# Section 114 (Part 15): System Hardening — Minimizing Host OS Attack Surface (seccomp, AppArmor)

## 1. Definition

**Plain language:** [§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) established that Cluster Setup hardening is about configuring Kubernetes components correctly — flags, file permissions, RBAC. But even a perfectly configured control plane sits on top of a Linux kernel shared by every container scheduled on that node, and a compromised container's process is still, fundamentally, a Linux process talking to that same kernel. System Hardening asks a narrower, more paranoid question: even if an attacker gets code execution inside a container, what can that process's underlying syscalls and file-access patterns actually do to the host?

**Precise definition:** **System Hardening**, the CKS exam's second domain (15% weight), covers restricting a container's interaction with the host kernel using two complementary Linux security mechanisms enforced at the container-runtime level. **seccomp** (secure computing mode) is a kernel feature that filters which **system calls** a process is permitted to invoke, using a profile (a JSON allow/deny list or set of default actions) attached via a Pod or container's `securityContext.seccompProfile`. **AppArmor** is a Linux Security Module (LSM) that restricts a process's **capabilities per-program** — file paths it can read/write/execute, network access, and specific capabilities — via a named profile loaded into the kernel on each node and referenced from a Pod's annotation or (in modern Kubernetes) its `securityContext.appArmorProfile` field. Together they shrink the "host OS attack surface" a compromised container process can reach, independent of anything the container image itself declares.

## 2. Why This Matters

- **A container escape or privilege-escalation exploit almost always routes through a specific syscall** (`mount`, `ptrace`, `keyctl`, kernel module loading) that a well-scoped seccomp profile simply refuses to let the process invoke — seccomp turns entire CVE classes into no-ops before they can execute, regardless of what the vulnerable application code inside the container does.
- **The default container runtime seccomp profile blocks roughly 44 of ~300+ Linux syscalls known to be dangerous or irrelevant to normal container workloads**, meaning `RuntimeDefault` alone is a meaningfully higher bar than `Unconfined`, at zero extra authoring cost — the single highest-leverage, lowest-effort hardening step in this entire domain.
- **AppArmor and seccomp are complementary, not redundant** — seccomp restricts _which syscalls_ run, AppArmor restricts _what those syscalls can touch_ (paths, capabilities); a process can be permitted to call `open()` by seccomp while AppArmor still denies it access to `/etc/shadow` specifically.

🔑 **Key Takeaway:** seccomp filters which syscalls a containerized process may invoke, AppArmor restricts what those permitted syscalls may actually touch on the host, and applying both — starting from the free, built-in `RuntimeDefault` seccomp profile — is the concrete, checkable mechanism behind reducing host OS attack surface below what cluster-level configuration hardening ([§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)) alone can achieve.

## 3. Prerequisites and Dependencies

This section builds on [§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)'s CIS Benchmark and kube-bench foundation, applying that same "verify against a concrete standard" mindset one layer deeper, into host-kernel-level controls. It assumes familiarity with SecurityContext fields from Part 6 ([§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)) at a basic level, though this section covers `seccompProfile` and AppArmor annotations in depth rather than assuming prior exposure. It also assumes the container runtime (containerd, CRI-O) architecture from Part 2 ([§43](../Part6/Section-43-Part6-Encrypting-Secrets-At-Rest-EncryptionConfiguration.md)-adjacent), since seccomp and AppArmor are enforced by the runtime and the underlying Linux kernel, not by the Kubernetes API server itself. Forward-references [§115](./Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md), which moves from host-kernel-level restriction into pod-and-container-level SecurityContext hardening and sandboxed runtimes.

## 4. Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────┐
│  Node (Linux host)                                                     │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Container process (PID namespace)                              │   │
│  │    issues syscall: open("/etc/shadow", O_RDONLY)                │   │
│  └───────────────────────────┬─────────────────────────────────────┘   │
│                              │                                         │
│                              ▼                                         │
│              ┌───────────────────────────────┐                         │
│              │  seccomp filter (BPF program) │   Is `open` an allowed  │
│              │  attached at container start  │   syscall for this      │
│              │  (RuntimeDefault / Localhost) │   profile?              │
│              └───────────────┬───────────────┘                         │
│                     ALLOWED  │ BLOCKED → SIGSYS / EPERM, process killed│
│                              ▼                                         │
│              ┌───────────────────────────────┐                         │
│              │  AppArmor LSM hook            │   Does this profile     │
│              │  (profile loaded at node boot │   permit read on        │
│              │  via apparmor_parser)         │   /etc/shadow?          │
│              └───────────────┬───────────────┘                         │
│                     ALLOWED  │   DENIED → EACCES, logged to audit      │
│                              ▼                                         │
│                    Linux kernel executes the actual                    │
│                    file-read / network / capability operation          │
└────────────────────────────────────────────────────────────────────────┘

     Pod spec references BOTH layers independently:
       securityContext.seccompProfile.type: RuntimeDefault | Localhost
       securityContext.appArmorProfile.type: RuntimeDefault | Localhost
     Localhost profiles must exist on EVERY node the Pod can schedule to.
```

- **Both mechanisms are enforced below the Kubernetes API layer entirely, at the container-runtime-and-kernel boundary** — a Pod spec merely selects which profile to attach; the actual enforcement decision happens per-syscall (seccomp) or per-resource-access (AppArmor) inside the kernel itself, meaning neither can be bypassed by anything happening at the Kubernetes object level once the container is running.
- **`Localhost` profiles are node-local files, not cluster objects** — a custom seccomp JSON file must exist at the same path (`/var/lib/kubelet/seccomp/profiles/`) on every node the Pod might be scheduled to, or the Pod fails to start on any node missing it; this is a common multi-node rollout gap.
- **AppArmor profile availability is reported as a node label/annotation** (`kubernetes.io/apparmor.profile-<name>` historically, or via node capability reporting in modern versions) — scheduling a Pod requiring an AppArmor profile not loaded on a candidate node fails at admission or leaves the Pod stuck in `Blocked`/`CreateContainerConfigError`.

## 5. Hands-On

### 5.1 Applying the Built-In RuntimeDefault seccomp Profile

**Purpose:** Enable the container runtime's default seccomp filtering, which blocks a well-known set of dangerous syscalls, at zero authoring cost.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: hardened-web
spec:
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: web
      image: nginx:1.27
      securityContext:
        allowPrivilegeEscalation: false
```

```bash
kubectl apply -f hardened-web.yaml
```

**Production usage example:** As of Kubernetes v1.25+, `RuntimeDefault` is applied automatically cluster-wide when the `SeccompDefault` feature (kubelet flag `--seccomp-default`) is enabled — many production platform teams enable this flag fleet-wide via node configuration so that every Pod gets baseline seccomp filtering even if individual manifest authors never set `seccompProfile` themselves, treating it as a floor rather than an opt-in.

**Common errors:** Assuming `RuntimeDefault` alone satisfies the CKS "Restricted" Pod Security Standard ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) — it satisfies the seccomp portion, but Restricted also requires `runAsNonRoot`, dropped capabilities, and `allowPrivilegeEscalation: false` independently; seccomp is one necessary field among several, not a substitute for the rest.

### 5.2 Writing and Loading a Custom Localhost seccomp Profile

**Purpose:** Restrict a container to an explicit allow-list of syscalls narrower than `RuntimeDefault`, for a workload whose exact syscall footprint is known.

**Syntax:**

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": [
        "accept4",
        "bind",
        "brk",
        "close",
        "epoll_wait",
        "exit_group",
        "fstat",
        "futex",
        "listen",
        "mmap",
        "read",
        "recvfrom",
        "sendto",
        "socket",
        "write"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

```bash
# Place the profile on EVERY candidate node under the kubelet's seccomp root
sudo mkdir -p /var/lib/kubelet/seccomp/profiles
sudo cp narrow-web.json /var/lib/kubelet/seccomp/profiles/narrow-web.json
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: narrow-web
spec:
  securityContext:
    seccompProfile:
      type: Localhost
      localhostProfile: profiles/narrow-web.json
  containers:
    - name: web
      image: hardened-web:2.0
```

**Production usage example:** Teams typically generate the initial allow-list not by hand but by running the workload once under a permissive/audit-mode profile with a tool like `strace` or the `oci-seccomp-bpf-hook`, capturing the real syscall set exercised in normal operation, then locking that exact list down — hand-authoring a syscall allow-list from documentation alone routinely misses syscalls only exercised in edge-case code paths (DNS retry logic, TLS renegotiation), causing production-only failures.

**Common errors:** Deploying a `Localhost` profile that exists on the control-plane node used for testing but was never copied to worker nodes — the Pod schedules successfully to a node lacking the file and fails with `CreateContainerError: cannot load seccomp profile`, a failure mode that only appears once the scheduler happens to place the Pod on an un-provisioned node.

### 5.3 Loading and Applying an AppArmor Profile

**Purpose:** Restrict a container's file-path and capability access using a named AppArmor profile loaded into the node's kernel.

**Syntax:**

```text
#include <tunables/global>

profile k8s-narrow-web flags=(attach_disconnected) {
  #include <abstractions/base>

  network inet tcp,
  network inet udp,

  /usr/sbin/nginx mr,
  /var/log/nginx/** w,
  /etc/nginx/** r,

  deny /etc/shadow r,
  deny /root/** rwx,
  deny mount,
}
```

```bash
# Load the profile into the kernel on each candidate node
sudo apparmor_parser -q -r k8s-narrow-web.profile
sudo aa-status | grep k8s-narrow-web
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: apparmor-web
spec:
  containers:
    - name: web
      image: nginx:1.27
      securityContext:
        appArmorProfile:
          type: Localhost
          localhostProfile: k8s-narrow-web
```

**Production usage example:** Ubuntu- and Debian-based node images ship AppArmor enabled by default, but many other distributions (most RHEL/CentOS-derived images) use SELinux instead — a platform team standardizing on AppArmor profiles must verify every node's base OS actually supports it, since `aa-status` simply doesn't exist on a non-AppArmor kernel and the profile silently has no effect.

**Common errors:** Writing an AppArmor profile that denies a path the application legitimately needs at startup (a cache directory, a PID file location) — the container doesn't fail immediately at admission the way a missing seccomp profile does; instead it crash-loops with a permission-denied error from inside the application, which is slower to diagnose since the failure surfaces from the app's own logs rather than a clear Kubernetes-level event.

## 6. Production Usage Notes

- **Enabling `--seccomp-default` at the kubelet level (fleet-wide `RuntimeDefault`) is the highest-leverage, lowest-risk hardening change in this domain** — it requires no per-manifest authoring and has near-zero compatibility risk, since `RuntimeDefault` is deliberately conservative about what it blocks.
- **Custom `Localhost` seccomp and AppArmor profiles require node-level file distribution as part of the node provisioning pipeline** (bootstrapping scripts, Ansible, a DaemonSet-based profile-loader) — treating profile files as application-layer config that ships with the Pod manifest alone is a frequent rollout mistake, since the files must exist on the node before the Pod schedules there.
- **Both mechanisms should be tested first with `warn`/audit-equivalent tooling before hard enforcement** — for seccomp, tools like the `oci-seccomp-bpf-hook` can generate an audit trail without blocking; for AppArmor, `complain` mode (instead of `enforce`) logs violations without denying them, mirroring PSA's `warn`/`audit` staged-rollout pattern from [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md).

## 7. Security Considerations

- **Who can author or modify seccomp/AppArmor profile files at the node level is a distinct, host-level security boundary from Kubernetes RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md))** — anyone with SSH or config-management access to a node can alter a `Localhost` profile's contents directly, silently weakening enforcement for every Pod referencing it, without touching a single Kubernetes object or leaving an audit trail in the Kubernetes API server's own logs.
- **A misconfigured profile fails in one of two very different directions, and both are dangerous in their own way** — an overly permissive profile provides no real protection while giving a false sense of hardening (the manifest "has" a seccomp field, so it looks compliant), while an overly restrictive profile causes application-level crash-loops that teams under pressure sometimes "fix" by reverting to `Unconfined` entirely rather than diagnosing the specific denied syscall or path — silently erasing the hardening rather than tuning it.
- **Because profile enforcement lives outside the Kubernetes API entirely, standard Kubernetes auditing ([§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md), Part 12) does not capture seccomp/AppArmor denials** — those events land in host-level logs (`dmesg`, `journalctl`, AppArmor's own audit log) that must be shipped into the same observability pipeline as Kubernetes audit logs, or a real attack blocked at the kernel level goes completely invisible to the platform team.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Cause                                                                                                                                                             | Fix                                                                                                                       |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Pod stuck in `CreateContainerError: cannot load seccomp profile`           | `Localhost` profile file missing on the node the Pod scheduled to                                                                                                 | Distribute the profile file to every candidate node via the provisioning pipeline before referencing it in a Pod spec     |
| Application crash-loops with permission-denied errors only in production   | AppArmor profile denies a path or capability the app needs under a real workload pattern not seen during profile authoring                                        | Run the profile in `complain` mode against real traffic first, review the AppArmor audit log, then tighten to `enforce`   |
| `aa-status` command not found on a worker node                             | Node's base OS uses SELinux (or no LSM) instead of AppArmor                                                                                                       | Verify OS compatibility before standardizing on AppArmor; use SELinux-equivalent controls or seccomp alone on those nodes |
| Kernel-level denials never show up in cluster observability dashboards     | Kubernetes audit logging ([§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)) does not capture host-level seccomp/AppArmor events | Ship `dmesg`/`journalctl`/AppArmor audit logs into the same log pipeline as Kubernetes audit data                         |
| Team reverts a Pod to `seccompProfile.type: Unconfined` after a crash-loop | Under time pressure, disabling the profile was faster than diagnosing the specific denied syscall                                                                 | Diagnose via `strace`/audit log first; treat reverting to Unconfined as a last resort requiring explicit sign-off         |

## 9. Best Practices

- Enable `RuntimeDefault` seccomp fleet-wide via the kubelet's `--seccomp-default` flag as a zero-cost baseline before authoring any custom profiles.
- Generate custom `Localhost` seccomp allow-lists from observed real-workload syscall traces (`strace`, `oci-seccomp-bpf-hook`), not from hand-written guesses.
- Distribute `Localhost` seccomp and AppArmor profile files through the same node provisioning pipeline (Ansible, DaemonSet, golden image) used for other node-level configuration, never as a manual one-off copy.
- Stage AppArmor rollouts through `complain` mode and seccomp rollouts through audit tooling before hard enforcement, mirroring the PSA `warn`/`audit`/`enforce` pattern from [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md).
- Ship host-level seccomp and AppArmor denial logs into the same observability pipeline as Kubernetes audit logs so kernel-level enforcement events remain visible.

## 10. Common Anti-Patterns / Mistakes

- **Treating the presence of a `seccompProfile` field as sufficient hardening**, without verifying whether it's `RuntimeDefault`, a meaningfully narrow `Localhost` profile, or an effectively no-op custom profile.
- **Authoring custom seccomp allow-lists by hand from documentation** rather than from observed real syscall traces, routinely missing edge-case syscalls and causing production-only failures.
- **Reverting to `Unconfined` under crash-loop pressure** instead of diagnosing the specific denied syscall or path, silently erasing hardening work.
- **Distributing `Localhost` profiles inconsistently across nodes**, so Pod scheduling success becomes dependent on which node the scheduler happens to pick.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between seccomp and AppArmor in Kubernetes?"_
**Model answer:** seccomp filters which system calls a containerized process is allowed to invoke — it operates at the syscall level, blocking things like `mount` or `ptrace` outright regardless of arguments. AppArmor is a Linux Security Module that restricts what a process can actually do with the syscalls it's allowed to make — which file paths it can read or write, which capabilities it holds, what network access it has. They're complementary: seccomp says "you may call open()," AppArmor says "but only on these specific paths."
_What the interviewer is probing for:_ Basic conceptual separation between the two mechanisms rather than treating them as interchangeable "container hardening" buzzwords.

**🎯 Intermediate:** _"Why would you write a custom `Localhost` seccomp profile instead of just using `RuntimeDefault` everywhere?"_
**Model answer:** `RuntimeDefault` is a broad, conservative profile designed to be compatible across nearly all container workloads, so it only blocks syscalls that are almost never legitimately needed. A workload with a narrow, well-understood syscall footprint — say, a single-purpose network proxy — can be hardened further with a custom allow-list that blocks everything except the specific syscalls that workload actually exercises, closing off far more of the kernel attack surface than the generic default. The trade-off is authoring and maintenance cost: a custom profile has to be generated from real traffic (not guessed), tested for compatibility across code paths, and distributed to every node the Pod might schedule to.
_What the interviewer is probing for:_ Understanding that generic and custom profiles serve different points on a compatibility-versus-restriction trade-off curve, not just "custom is always better."

**🎯 Senior:** _"A team reports their AppArmor-hardened Pod crash-loops intermittently, only under production traffic, never in staging. How do you approach it?"_
**Model answer:** Intermittent, traffic-dependent AppArmor denials usually mean the profile was authored against a code path the application doesn't exercise in staging — a retry path, a rare error-handling branch that touches a different file, a background compaction job. I'd first switch the profile to `complain` mode temporarily (logs violations without denying them) and replay realistic production traffic patterns against it, then mine the AppArmor audit log for every denied access during that window rather than guessing. I'd add each legitimately-needed path or capability back into the profile incrementally, re-testing after each change, rather than widening the profile broadly to "make it stop." I'd also push to reproduce the traffic pattern in staging going forward, since the gap between staging and production traffic diversity is the actual root cause, not just this one profile.
_What the interviewer is probing for:_ A systematic diagnose-before-widen approach using the tool's own audit capability, and recognition that the underlying gap is staging/production traffic parity, not just this one incident.

**🎯 Architect:** _"Design a fleet-wide rollout of both seccomp and AppArmor hardening across a heterogeneous 300-node cluster with mixed Ubuntu and RHEL-derived nodes."_
**Model answer:** I'd start by partitioning the fleet by LSM support, since AppArmor isn't universally available — Ubuntu/Debian nodes get AppArmor profiles, RHEL-derived nodes need an equivalent SELinux policy or fall back to seccomp-only hardening, and that partition has to be tracked explicitly rather than assumed. For seccomp, I'd enable `RuntimeDefault` fleet-wide via the kubelet `--seccomp-default` flag first, as the zero-risk universal floor, rolled through the same node-provisioning pipeline (golden images or Ansible) that manages other kubelet flags. For workloads warranting tighter custom profiles, I'd build a per-workload profile-generation pipeline: capture real syscall traces in a staging environment under production-representative traffic, generate a candidate `Localhost` profile, run it in audit/complain mode against a canary slice of real production traffic for a full workload cycle, then promote to enforcement — the same staged pattern as PSA's `warn`/`audit`/`enforce` from [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md). Profile files themselves get distributed via the node-provisioning pipeline (not manual copy), version-controlled alongside the workload's own manifests so a profile update ships atomically with the code change it corresponds to. Finally, I'd ensure host-level seccomp/AppArmor denial logs are shipped into the same centralized observability pipeline as Kubernetes audit logs ([§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)), since kernel-level enforcement is otherwise invisible to the platform team monitoring the cluster through Kubernetes-native tooling alone.
_What the interviewer is probing for:_ Fleet-scale thinking about heterogeneous OS/LSM support, a concrete staged-rollout methodology reusing the audit-before-enforce pattern, and awareness that profile distribution and observability are first-class parts of the design, not afterthoughts.

## 12. Common Misconceptions

1. **"seccomp and AppArmor are redundant — pick one."** They restrict different things (syscall identity versus resource access) and are designed to be layered together, not chosen between.
2. **"Setting `seccompProfile: RuntimeDefault` satisfies the Restricted Pod Security Standard on its own."** Restricted ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) also requires `runAsNonRoot`, dropped capabilities, and `allowPrivilegeEscalation: false` independently.
3. **"A `Localhost` profile referenced in a Pod manifest travels with the Pod like an image does."** It's a node-local file that must be pre-distributed to every candidate node; the Pod spec only references it by name/path.
4. **"AppArmor works the same way on every Linux distribution."** Several major distributions (RHEL and derivatives) use SELinux instead and lack AppArmor entirely; profile portability across a heterogeneous fleet cannot be assumed.

## 13. 🔑 Key Takeaways

- seccomp filters which syscalls a container process may invoke; AppArmor restricts what those permitted syscalls can actually access — complementary, not redundant, kernel-level controls.
- `RuntimeDefault` seccomp, enabled fleet-wide via the kubelet's `--seccomp-default` flag, is the highest-leverage, lowest-effort hardening step in this domain.
- Custom `Localhost` profiles must be generated from real observed syscall/access traces, not hand-authored guesses, and distributed to every node a Pod might schedule to.
- Both mechanisms enforce below the Kubernetes API layer, meaning host-level access control and host-level audit logging are the real security boundary and visibility mechanism — Kubernetes RBAC and audit logs alone don't cover them.
- Stage rollouts through audit/complain modes before hard enforcement, mirroring the same `warn`/`audit`/`enforce` pattern already established by Pod Security Admission ([§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)).

## 14. Related Concepts & What's Next

This section moved one layer beneath [§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)'s cluster-configuration hardening into the host operating system itself, covering how seccomp and AppArmor profiles restrict a containerized process's actual kernel-level reach. [§115](./Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md), next, moves back up to the Pod and container specification layer, covering SecurityContext hardening in depth (building on [§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md) and [§78](../Part10/Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) and introducing sandboxed container runtimes like gVisor and Kata Containers — an alternative approach to host isolation that intercepts syscalls in userspace entirely, rather than filtering them via seccomp against the shared host kernel.

**Next Section:** [§115](./Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md) — `Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md`
