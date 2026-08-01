# Section 115 (Part 15): Minimizing Microservice Vulnerabilities — SecurityContext Hardening, gVisor/Kata Containers

## 1. Definition

**Plain language:** §114 hardened the host kernel boundary — seccomp and AppArmor decide what a container process can do once it's running. But most of that same protection can be undermined at a much simpler layer: if a container is allowed to run as root with every Linux capability intact, seccomp and AppArmor are restricting an attacker who already holds most of the keys. Minimizing Microservice Vulnerabilities, the CKS domain worth the most exam weight (20%), starts one layer up — at the Pod and container spec itself — and then asks a further question: what if the shared-kernel assumption behind containers is itself the risk you can't accept for a given workload?

**Precise definition:** This domain covers two distinct but complementary techniques. **SecurityContext hardening** is the disciplined application of the Pod- and container-level `securityContext` fields — `runAsNonRoot`, `runAsUser`, `readOnlyRootFilesystem`, `capabilities.drop`/`add`, `allowPrivilegeEscalation`, `privileged` — to minimize what a container is permitted to do even before seccomp/AppArmor are considered, directly implementing the same checklist Pod Security Admission's Restricted tier (§78) enforces. **Sandboxed container runtimes** — **gVisor** (a userspace kernel written in Go that intercepts syscalls before they reach the host kernel, implemented as the `runsc` OCI-compatible runtime) and **Kata Containers** (which runs each container inside a lightweight, hardware-virtualized micro-VM with its own kernel) — address a different threat model entirely: workloads that must run genuinely **untrusted code** (multi-tenant SaaS, third-party plugin execution) where even a fully seccomp/AppArmor-restricted shared kernel is an unacceptable blast radius if a kernel-level zero-day is exploited.

## 2. Why This Matters

- **SecurityContext hardening is free and universal — it requires no additional runtime, no extra infrastructure, and applies to every container on every node** — unlike sandboxed runtimes, which require specific node provisioning, the fields covered here (`runAsNonRoot`, `capabilities.drop: ["ALL"]`, `readOnlyRootFilesystem`) are available on any Kubernetes cluster today and directly close the most commonly exploited privilege-escalation vectors.
- **The Linux capability model is far more granular than "root versus non-root," and most container images request far more capability than they use** — a typical web application container needs zero of the ~40 Linux capabilities beyond what dropping to `ALL` and adding back only `NET_BIND_SERVICE` (for binding to a privileged port) provides, meaning the default of running with the full capability set is almost always over-provisioned.
- **gVisor and Kata exist because seccomp/AppArmor still share one kernel across every container on a node** — a kernel-level zero-day (a class of vulnerability that recurs regularly) bypasses syscall filtering and LSM policy entirely; sandboxed runtimes change the actual isolation boundary from "shared kernel with restricted access" to "no shared kernel at all" for the highest-risk workloads.

🔑 **Key Takeaway:** SecurityContext hardening — non-root execution, a fully dropped and selectively re-added capability set, and a read-only root filesystem — is the free, universal first line of defense for every container, while gVisor and Kata Containers change the isolation model itself for workloads whose threat model (untrusted, multi-tenant, or third-party code) makes even a fully restricted shared kernel an unacceptable risk.

## 3. Prerequisites and Dependencies

This section builds directly on §114's kernel-level hardening (seccomp/AppArmor), moving one layer up to the Pod spec itself, and assumes §45's SecurityContext fields (Part 6) and §78's Pod Security Standards (Part 10) as its core foundation — this section extends both into CKS-exam depth and adds the sandboxed-runtime dimension neither prior section covered. It also assumes basic familiarity with the container runtime and RuntimeClass mechanism from Part 2, since gVisor and Kata are selected per-Pod via `spec.runtimeClassName`. Forward-references §116, which addresses supply chain security — a complementary concern, since a hardened SecurityContext and a sandboxed runtime both reduce blast radius, but neither prevents a vulnerable or malicious image from being deployed in the first place.

## 4. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 1: SecurityContext hardening (applies to EVERY container)            │
│    runAsNonRoot: true          → no root UID inside the container           │
│    capabilities.drop: ["ALL"]  → zero Linux capabilities by default         │
│    capabilities.add: [minimal] → only what's strictly required re-added     │
│    readOnlyRootFilesystem: true→ no writable root fs (mutation surface gone)│
│    allowPrivilegeEscalation: false → no setuid/setgid escalation path       │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │  reduces what a compromised process CAN DO
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 2: Runtime isolation choice (per-Pod, via RuntimeClass)              │
│                                                                             │
│   Standard runtime (runc)          gVisor (runsc)        Kata Containers    │
│   ┌─────────────┐                 ┌─────────────┐       ┌─────────────┐     │
│   │  Container  │                 │  Container  │       │  Container  │     │
│   │  process    │                 │  process    │       │  process    │     │
│   └──────┬──────┘                 └──────┬──────┘       └──────┬──────┘     │
│          │ direct syscalls               │ intercepted         │ own kernel │
│          ▼                               ▼                     ▼            │
│   Shared HOST kernel           gVisor userspace kernel     Hardware-isolated│
│   (namespaces + cgroups         (Sentry process, Go)       micro-VM, own    │
│    only isolation)             re-implements syscalls      kernel (QEMU/    │
│                                safely, then makes          Firecracker)     │
│                                minimal real syscalls                        │
│                                to host kernel                               │
└─────────────────────────────────────────────────────────────────────────────┘
       ← weakest isolation, fastest, most compatible                 strongest
                                                          isolation, most overhead →
```

- **SecurityContext fields and runtime sandboxing address orthogonal risks and stack together** — a Pod can (and for genuinely untrusted workloads, should) run under `runtimeClassName: gvisor` _and_ have a fully hardened SecurityContext simultaneously; sandboxing is not a substitute for basic hardening.
- **gVisor's Sentry process re-implements a large subset of the Linux syscall surface in userspace (Go), making far fewer real syscalls to the actual host kernel than the container process itself issues** — this is what shrinks the exploitable kernel surface, at the cost of imperfect syscall-compatibility for some workloads and measurable I/O/network overhead.
- **Kata Containers uses actual hardware virtualization (via a lightweight VMM like QEMU or Firecracker) to give each Pod's containers a genuinely separate kernel**, offering the strongest isolation of the two but with higher per-Pod resource and startup-latency overhead than gVisor, which stays process-based.

## 5. Hands-On

### 5.1 A Fully Hardened SecurityContext

**Purpose:** Apply the complete set of Pod- and container-level SecurityContext fields that minimize what a compromised container process can do, matching (and extending slightly beyond) the Restricted Pod Security Standard.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: hardened-microservice
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: hardened-microservice:3.2
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
          add: ["NET_BIND_SERVICE"]
      volumeMounts:
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: tmp
      emptyDir: {}
```

**Production usage example:** The `emptyDir` mounted at `/tmp` alongside `readOnlyRootFilesystem: true` is a standard pairing — most applications assume a writable `/tmp` exists even when the rest of the filesystem is legitimately read-only, and without an explicit writable volume for it, the container fails at runtime with permission errors the moment any code path attempts a temp-file write.

**Common errors:** Setting `capabilities.drop: ["ALL"]` without testing whether the application genuinely needs zero re-added capabilities — a process binding to port 80 or 443 directly (rather than behind a Service/Ingress that remaps to a non-privileged port) requires `NET_BIND_SERVICE` added back, and omitting it produces a runtime bind failure that looks unrelated to capabilities unless the error is read carefully.

### 5.2 Running an Untrusted Workload Under gVisor

**Purpose:** Sandbox a Pod that executes third-party or otherwise untrusted code, using gVisor's userspace kernel instead of the shared host kernel.

**Syntax:**

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc
---
apiVersion: v1
kind: Pod
metadata:
  name: untrusted-plugin-executor
spec:
  runtimeClassName: gvisor
  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: plugin-runner
      image: plugin-sandbox:1.0
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
```

```bash
# On the node (prerequisite, done once during node provisioning):
# containerd config.toml registers runsc as a runtime handler
containerd config dump | grep -A3 'runtimes.runsc'
kubectl apply -f gvisor-runtimeclass.yaml
kubectl apply -f untrusted-plugin-executor.yaml
kubectl get pod untrusted-plugin-executor -o jsonpath='{.spec.runtimeClassName}'
```

**Production usage example:** Multi-tenant SaaS platforms that let customers upload and execute arbitrary code (serverless function platforms, CI runner services) commonly schedule that specific workload class onto a dedicated node pool pre-provisioned with the `runsc` containerd handler, using a taint/toleration pair alongside `runtimeClassName` so untrusted-code Pods are both sandboxed and physically isolated from the rest of the fleet's trusted workloads.

**Common errors:** Assuming gVisor is a drop-in replacement with zero compatibility cost — some syscalls and `/proc` filesystem behaviors aren't fully emulated, so workloads relying on niche syscalls (certain io_uring patterns, some ptrace-based debugging or profiling tools) can fail or behave differently under `runsc` than under `runc`; test compatibility before mandating gVisor broadly rather than assuming universal transparency.

### 5.3 Running a Workload Under Kata Containers for Hardware-Level Isolation

**Purpose:** Provide the strongest available isolation — a separate kernel per Pod via lightweight VM — for the highest-risk workload class.

**Syntax:**

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata
handler: kata
---
apiVersion: v1
kind: Pod
metadata:
  name: high-risk-multi-tenant-job
spec:
  runtimeClassName: kata
  containers:
    - name: job-runner
      image: tenant-job-runner:1.4
      resources:
        limits:
          cpu: "2"
          memory: 4Gi
```

```bash
$ kubectl describe pod high-risk-multi-tenant-job | grep -A2 Runtime
Runtime Class Name:  kata
$ kubectl get events --field-selector involvedObject.name=high-risk-multi-tenant-job
```

**Production usage example:** Kata's per-Pod micro-VM startup adds meaningful latency (typically hundreds of milliseconds versus tens for a standard container), so it's generally reserved for longer-running, genuinely high-risk workloads rather than latency-sensitive, high-churn microservices — a platform team choosing between gVisor and Kata for a given workload class is trading gVisor's lower overhead against Kata's stronger, hardware-backed isolation boundary.

**Common errors:** Deploying Kata on infrastructure without nested-virtualization support (a common gap on some cloud VM instance types or already-virtualized bare-metal setups) — the Pod fails to start with an opaque VMM-launch error, since Kata fundamentally depends on hardware virtualization extensions being available to the node itself.

## 6. Production Usage Notes

- **SecurityContext hardening should be the default posture for every workload namespace, enforced via Pod Security Admission's Restricted tier (§78) as the baseline, with sandboxed runtimes reserved for a specific, identified risk tier** — treating gVisor/Kata as a blanket cluster-wide default is usually unnecessary overhead; they're targeted controls for workloads whose threat model specifically involves untrusted or third-party code execution.
- **RuntimeClass selection should be paired with node-pool segregation (taints/tolerations, or dedicated node groups)** in production, so gVisor/Kata-designated nodes have the required runtime handlers pre-provisioned and untrusted workloads are physically, not just logically, separated from trusted ones.
- **Capability minimization (`drop: ["ALL"]` plus a minimal `add` list) requires per-image validation, not a copy-pasted universal template** — different application runtimes and frameworks have genuinely different minimal capability requirements, and a blanket policy applied without per-workload testing produces either under-restriction (unused capabilities left granted) or runtime failures (a genuinely needed capability dropped).

## 7. Security Considerations

- **Who can grant an exception to mandatory SecurityContext hardening (an `allowPrivilegeEscalation: true` override, a `privileged: true` grant) must be a tightly scoped RBAC and policy-engine (OPA Gatekeeper/Kyverno, layered per §78) decision, not something any developer can self-serve into a manifest** — a single unreviewed exception in a shared cluster undermines the hardening baseline for that entire namespace's trust assumptions.
- **A workload misclassified as "trusted" when it should have been sandboxed under gVisor/Kata is a real and recurring production mistake** — the classification decision (does this workload execute third-party or otherwise untrusted code) needs an explicit review step during workload onboarding, not an assumption made once and never revisited as a service's responsibilities evolve (e.g., a previously internal-only service later exposed to accept user-uploaded plugins).
- **Sandboxed runtimes reduce blast radius from a kernel-level exploit but do not eliminate the value of SecurityContext hardening within the sandbox itself** — treating gVisor/Kata as sufficient on their own, and skipping capability-dropping or non-root enforcement inside the sandboxed container, still leaves an attacker who compromises the _application_ itself (rather than the kernel boundary) with more reach than necessary within that sandbox.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                   | Cause                                                                                                    | Fix                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Container fails at startup with a bind/permission error despite `runAsNonRoot` being the intended posture | Application defaults to binding a privileged port (<1024) without `NET_BIND_SERVICE` capability re-added | Add back only the specific capability needed (`capabilities.add: ["NET_BIND_SERVICE"]`) rather than reverting to a broad capability set                                                     |
| Application crashes writing to a temp/cache path after enabling `readOnlyRootFilesystem`                  | No writable volume provided for paths the app assumes are writable                                       | Mount an `emptyDir` (or similar) at the specific paths (`/tmp`, cache directories) the application needs to write to                                                                        |
| Pod with `runtimeClassName: gvisor` fails or behaves inconsistently for a specific workload               | Workload exercises a syscall or `/proc` behavior gVisor's Sentry doesn't fully emulate                   | Test compatibility before mandating gVisor broadly; fall back to standard runtime with strong SecurityContext hardening plus seccomp/AppArmor for workloads with incompatible syscall needs |
| Pod with `runtimeClassName: kata` fails to start with an opaque VMM error                                 | Node lacks nested-virtualization / hardware virtualization support                                       | Verify virtualization extension support on candidate node pools before designating them for Kata workloads                                                                                  |
| Pod using a custom RuntimeClass never schedules                                                           | RuntimeClass handler not registered in the container runtime config on any available node                | Verify containerd/CRI-O config registers the handler, and that node-pool taints/tolerations correctly target the right nodes                                                                |

## 9. Best Practices

- Default every workload namespace to a fully hardened SecurityContext (`runAsNonRoot`, `capabilities.drop: ["ALL"]`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`) as the baseline, enforced via Pod Security Admission's Restricted tier (§78).
- Add capabilities back individually and only after confirming the specific requirement (e.g., `NET_BIND_SERVICE` for privileged port binding); never leave the full default capability set intact "to be safe."
- Reserve gVisor and Kata Containers for workloads with an explicitly identified untrusted-code threat model, not as a blanket cluster-wide default given their compatibility and performance trade-offs.
- Pair RuntimeClass-based sandboxing with node-pool segregation (taints/tolerations) so untrusted workloads are physically isolated, not merely logically flagged.
- Re-review a workload's trust classification (does it execute untrusted third-party code) at onboarding and whenever its responsibilities materially change.

## 10. Common Anti-Patterns / Mistakes

- **Copy-pasting a "hardened" SecurityContext template across every workload without validating it against that specific application's actual capability needs**, producing either silent over-restriction failures or, worse, unnecessary capabilities left granted because nobody actually tested the minimal set.
- **Treating gVisor or Kata as a substitute for SecurityContext hardening within the sandbox**, leaving an attacker who compromises the application itself with more reach inside the sandbox than necessary.
- **Deploying sandboxed runtimes cluster-wide as a default posture**, absorbing meaningful performance and compatibility overhead for workloads that never actually needed the stronger isolation boundary.
- **Never revisiting a workload's trust classification after initial onboarding**, missing the point at which a previously internal-only service starts accepting genuinely untrusted input or code.

## 11. Interview Questions

**🎯 Beginner:** _"What does `capabilities.drop: ["ALL"]` combined with `capabilities.add: ["NET_BIND_SERVICE"]` actually achieve?"_
**Model answer:** It removes every Linux capability the container would otherwise hold by default — things like the ability to change file ownership, load kernel modules, or trace other processes — and then re-grants exactly one narrow capability, the ability to bind to a privileged network port below 1024. The result is a container that can do the one specific privileged thing it actually needs (bind port 80, for instance) while having none of the roughly forty other capabilities a default container would otherwise carry.
_What the interviewer is probing for:_ Understanding that capabilities are granular, not a binary root/non-root switch, and that the drop-then-selectively-add pattern is the standard hardening approach.

**🎯 Intermediate:** _"When would you choose gVisor over Kata Containers, or vice versa, for a given workload?"_
**Model answer:** gVisor intercepts syscalls in a userspace process (the Sentry) and makes a much smaller set of real syscalls to the host kernel, giving good isolation with lower overhead and faster startup, but with some syscall/`/proc` compatibility gaps for unusual workloads. Kata gives each Pod its own kernel via lightweight hardware virtualization — a stronger, more complete isolation boundary, but with meaningfully higher per-Pod resource cost and startup latency. I'd choose gVisor for higher-churn, latency-sensitive untrusted workloads (short-lived function executions) where the syscall compatibility has been validated, and Kata for longer-running, higher-risk workloads where the strongest available isolation justifies the overhead — genuinely adversarial multi-tenant code execution, for instance.
_What the interviewer is probing for:_ Concrete understanding of the actual isolation mechanism difference between the two, not just "they're both sandboxes."

**🎯 Senior:** _"A team wants to apply `readOnlyRootFilesystem: true` cluster-wide but several legacy applications immediately start crash-looping. How do you approach the rollout?"_
**Model answer:** I'd treat this the same way as any other staged hardening rollout — never a blanket flag-day change. First, I'd identify which applications are actually failing and why, typically by checking what paths they're attempting to write to at runtime (temp directories, local caches, occasionally logs written directly to a local path instead of stdout). For each, I'd add a targeted writable volume (`emptyDir` or a small persistent volume) mounted at exactly the paths the application needs, rather than reverting `readOnlyRootFilesystem` for the whole container. For applications where the writable-path requirement is extensive or poorly understood, I'd stage the change per-namespace, validating in a lower environment first, and treat any case requiring broad filesystem write access as a signal that the application itself may need remediation (writing to a proper cache service instead of local disk) rather than permanently carving out an exception. I'd track exceptions explicitly rather than let `readOnlyRootFilesystem: false` silently become the norm for "the legacy apps" indefinitely.
_What the interviewer is probing for:_ A staged, diagnostic rollout methodology rather than an all-or-nothing mandate, and recognition that exceptions need to be tracked and revisited, not permanently grandfathered in.

**🎯 Architect:** _"Design the workload-isolation tiering strategy for a platform hosting both internal microservices and a customer-facing 'run your own plugin code' feature."_
**Model answer:** I'd define at least three isolation tiers mapped to actual threat models rather than applying one policy universally. Tier one — internal, fully trusted microservices — runs on the standard runtime with mandatory SecurityContext hardening (non-root, dropped capabilities, read-only root filesystem) enforced via Pod Security Admission's Restricted tier (§78) as a namespace-wide floor, plus RuntimeDefault seccomp and a baseline AppArmor profile (§114). Tier two — workloads handling less-trusted but not fully adversarial input (third-party webhook processors, for instance) — adds gVisor via RuntimeClass, accepting its modest overhead in exchange for meaningfully reduced kernel attack surface, still layered with full SecurityContext hardening. Tier three — the customer-uploaded plugin execution feature itself — runs under Kata Containers specifically, on a dedicated, taint-isolated node pool physically separated from the rest of the fleet, since this is the workload class genuinely facing adversarial, untrusted code and justifying the strongest and most expensive isolation boundary available. I'd formalize the trust-tier assignment as an explicit, reviewed decision recorded per workload (not an assumption), with a defined re-review trigger whenever a service's responsibilities change — e.g., an internal service later exposed to accept user-submitted content moves from tier one to tier two or three. Finally, I'd ensure the platform's onboarding process for new workloads requires this tiering decision up front, rather than defaulting every new service to the standard runtime and relying on someone noticing later that it should have been sandboxed.
_What the interviewer is probing for:_ Ability to design a tiered, threat-model-driven isolation strategy rather than a single blanket policy, and recognition that tier assignment must be an explicit, reviewed, and re-visitable decision embedded in the platform's operational process.

## 12. Common Misconceptions

1. **"SecurityContext hardening and sandboxed runtimes are alternative approaches — pick one."** They address different layers (what a process is allowed to do versus what kernel it shares) and are meant to be combined, not chosen between.
2. **"gVisor and Kata Containers are interchangeable 'sandboxing' options with no meaningful difference."** gVisor intercepts syscalls in userspace with lower overhead and some compatibility gaps; Kata provides a full separate kernel per Pod via hardware virtualization with materially higher overhead — the choice depends on the specific workload's risk and performance requirements.
3. **"Dropping all capabilities and running as non-root is enough hardening on its own, no runtime sandboxing needed."** That's true for trusted, internal workloads, but a workload executing genuinely untrusted or adversarial code still shares the host kernel unless a sandboxed runtime is used — SecurityContext hardening alone doesn't change that shared-kernel exposure.
4. **"A workload's trust classification, once decided, never needs revisiting."** Services' responsibilities evolve — an internal-only service later exposed to accept user-generated content or third-party plugins needs its isolation tier re-evaluated, not grandfathered at its original classification indefinitely.

## 13. 🔑 Key Takeaways

- SecurityContext hardening (non-root execution, dropped-then-selectively-added capabilities, read-only root filesystem) is free, universal, and should be the default baseline for every workload, enforced via Pod Security Admission's Restricted tier (§78).
- gVisor and Kata Containers change the isolation model itself — from a shared, restricted kernel to a userspace-intercepted or fully separate kernel — for workloads whose threat model specifically involves untrusted or adversarial code execution.
- gVisor trades some syscall compatibility for lower overhead via userspace syscall interception; Kata trades higher resource/startup cost for a genuinely separate kernel via hardware virtualization.
- SecurityContext hardening and sandboxed runtimes are complementary layers meant to be combined, not alternative choices — a sandboxed workload still benefits from a minimized capability set within the sandbox.
- A workload's trust/isolation tier assignment must be an explicit, reviewed, and periodically re-evaluated decision, not a one-time assumption made at onboarding.

## 14. Related Concepts & What's Next

This section moved from §114's kernel-syscall-and-resource-access restriction (seccomp, AppArmor) up to the Pod specification layer itself, covering how disciplined SecurityContext hardening (building on §45 and §78) minimizes what a container is permitted to do, and how gVisor and Kata Containers change the underlying isolation model entirely for workloads facing genuinely untrusted code. §116, next, shifts focus from runtime and spec-level hardening to a different point in the lifecycle entirely — supply chain security, covering how image scanning (Trivy), signing (Cosign/Sigstore), and SBOMs ensure the workload being hardened was trustworthy before it was ever deployed in the first place.

**Next Section:** §116 — `Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md`
