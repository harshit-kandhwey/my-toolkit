# Section 45 (Part 6): SecurityContext at Pod and Container Level

## 1. Definition

**Plain language:** By default, a container in Kubernetes runs with far more privilege than almost any real application needs — often as root, with a writable filesystem, and with a broad set of Linux capabilities available. SecurityContext is the set of Pod-spec fields that dial that default down to what's actually necessary, turning "runs, and could do almost anything on the host if compromised" into "runs, and structurally cannot do most of the things an attacker would want."

**Precise definition:** **SecurityContext** is a set of fields, settable at both the **Pod level** (`spec.securityContext`, applying as a default to every container in the Pod) and the **container level** (`spec.containers[].securityContext`, overriding the Pod-level default for that one container), that constrain the Linux-level privilege and identity a container's process runs with. Key fields include `runAsUser`/`runAsGroup` (the UID/GID the process runs as), `runAsNonRoot` (a boolean assertion, enforced at admission, that the container must not run as UID 0), `readOnlyRootFilesystem` (mounts the container's root filesystem read-only, forcing any writes to go through explicitly mounted volumes), `allowPrivilegeEscalation` (blocks a process from gaining more privileges than its parent, e.g. via setuid binaries), and `capabilities.drop`/`capabilities.add` (fine-grained control over which specific Linux kernel capabilities — like `NET_BIND_SERVICE` or `SYS_ADMIN` — the container's process actually holds, rather than the broad default set). Container-level settings always win over Pod-level settings for the same field on that specific container.

## 2. Why This Matters

- **SecurityContext is the direct, hands-on enforcement mechanism for nearly every hardening principle in this roadmap's security material.** The Pod spec anatomy in [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) already showed `runAsNonRoot`, `allowPrivilegeEscalation`, and `readOnlyRootFilesystem` used inline — this section is the full, dedicated treatment of exactly how those fields behave, interact, and fail.
- **Pod Security Admission and Pod Security Standards enforce SecurityContext fields as policy**, meaning a cluster's Restricted profile ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) will reject Pods that don't set these fields correctly — understanding SecurityContext here is the direct prerequisite for not having Pods rejected at admission time in a hardened cluster.
- **This section's baseline is exactly what Part 15's CKS material builds on for full exam-level depth** — seccomp profiles, AppArmor, and gVisor/Kata Container runtime isolation ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)–[§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)) all layer additional hardening on top of the SecurityContext fields covered here, not instead of them.

🔑 **Key Takeaway:** SecurityContext exists at both Pod and container level, with container-level settings overriding Pod-level defaults per field; `runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, and capability dropping together form the practical baseline every production container should set explicitly rather than trusting Kubernetes' permissive defaults.

## 3. Prerequisites and Dependencies

Builds directly on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (Pod spec anatomy, where `securityContext` first appeared at both Pod and container level inline in the full example manifest) and assumes basic familiarity with Linux user/group/capability concepts from the Linux track.

## 4. Architecture: Pod-Level Defaults vs. Container-Level Overrides

```text
┌───────────────────────────────────────────────────────────────────────┐
│ spec.securityContext (Pod-level — applies as DEFAULT to all           │
│   containers unless overridden individually)                          │
│   runAsNonRoot: true                                                  │
│   runAsUser: 1000                                                     │
│   fsGroup: 2000        ◄── only meaningful at Pod level (volume own.) │
└───────────────────────┬───────────────────────────────────────────────┘
                         │ inherited by every container, unless overridden
        ┌────────────────┴────────────────┐
        ▼                                 ▼
┌───────────────────────────────┐   ┌───────────────────────────────────┐
│ Container: app                │   │ Container: sidecar                │
│ securityContext:              │   │ securityContext:                  │
│   allowPrivilegeEscalation:   │   │   runAsUser: 1000    (redundant,  │
│     false                     │   │     matches Pod default)          │
│   readOnlyRootFilesystem:     │   │   readOnlyRootFilesystem: false   │
│     true                      │   │     ◄── OVERRIDES Pod's implicit  │
│   capabilities:               │   │     default for THIS container    │
│     drop: ["ALL"]             │   │     only                          │
│     add: ["NET_BIND_SERVICE"] │   └───────────────────────────────────┘
└───────────────────────────────┘
        │                                  │
        ▼                                  ▼
 Runs as UID 1000, non-root,       Runs as UID 1000 (inherited),
 read-only rootfs, no extra          but WRITABLE rootfs
 privileges, minimal capabilities    (container-level override)
```

- **`fsGroup` only makes sense at the Pod level** — it controls the group ownership applied to mounted volumes so every container in the Pod (running as different UIDs, potentially) can share group-level access to the same volume data.
- **Container-level `securityContext` fields override the Pod-level default field-by-field**, not wholesale — a container that only sets `readOnlyRootFilesystem: false` still inherits `runAsUser: 1000` from the Pod level if it doesn't also override that field.
- **`capabilities.drop: ["ALL"]` followed by a narrow `add` list** is the recommended pattern — start from zero Linux capabilities and add back only the specific one a container genuinely needs (like `NET_BIND_SERVICE` for binding to a privileged port below 1024), rather than starting from the broad container-runtime default set and trying to remove risky ones individually.

## 5. Hands-On: Setting and Verifying SecurityContext

### 5.1 A Hardened Pod-Level and Container-Level SecurityContext

**Purpose:** Show a realistic, production-grade SecurityContext combining Pod-level identity defaults with container-level filesystem and capability hardening.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: hardened-app
spec:
  securityContext: # Pod-level defaults
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 3000
    fsGroup: 2000
    seccompProfile: # baseline seccomp (full depth in §115)
      type: RuntimeDefault
  containers:
    - name: app
      image: myregistry.example.com/app:2.1.0
      securityContext: # container-level, more specific
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
          add: ["NET_BIND_SERVICE"] # only if binding to a port <1024
      volumeMounts:
        - name: tmp-vol # required if the app needs ANY writable path
          mountPath: /tmp
  volumes:
    - name: tmp-vol
      emptyDir: {}
```

**Example usage and expected output:**

```bash
$ kubectl apply -f hardened-app.yaml
pod/hardened-app created

$ kubectl exec hardened-app -- id
uid=1000 gid=3000 groups=3000,2000

$ kubectl exec hardened-app -- touch /etc/test
touch: /etc/test: Read-only file system
```

**Production usage example:** The `tmp-vol` `emptyDir` mounted at `/tmp` is a common necessity alongside `readOnlyRootFilesystem: true` — many applications and their underlying language runtimes (JVM temp files, Python's `tempfile` module) expect _some_ writable path to exist even when the rest of the filesystem is locked down, so a small writable `emptyDir` scoped to exactly the paths that need it is the standard pairing.

**Common errors:** Setting `readOnlyRootFilesystem: true` without providing any writable volume for paths the application actually needs (log files, temp files, a cache directory) causes the application to crash on startup with permission-denied errors that look like an application bug but are actually a missing volume mount.

### 5.2 `runAsNonRoot` as an Admission-Time Assertion

**Purpose:** Show that `runAsNonRoot: true` is not merely descriptive — it's actively enforced, and a Pod that violates it is rejected or fails to start, not silently allowed to run as root anyway.

**Syntax:**

```yaml
spec:
  securityContext:
    runAsNonRoot: true # asserts the container MUST NOT run as UID 0
  containers:
    - name: app
      image: some-legacy-image-that-runs-as-root:1.0 # no USER directive
```

**Example usage and expected output:**

```bash
$ kubectl apply -f bad-pod.yaml
pod/legacy-app created

$ kubectl get pod legacy-app
NAME         READY   STATUS                       RESTARTS   AGE
legacy-app   0/1     CreateContainerConfigError    0          5s

$ kubectl describe pod legacy-app | grep -A2 Events
  Warning  Failed     5s   kubelet   Error: container has runAsNonRoot and image
                                     will run as root (pod: "legacy-app", container: "app")
```

**Production usage example:** This is exactly why `runAsUser` is often explicitly set alongside `runAsNonRoot: true` — rather than relying on the image's own default user (which may or may not be non-root, and can change silently across image updates), explicitly forcing a specific non-root UID removes the ambiguity and guarantees consistent behavior across image versions.

**Common errors:** Setting `runAsNonRoot: true` against a container image that has no non-root user baked in (no `USER` directive in its Dockerfile) and no explicit `runAsUser` override — the Pod fails at container creation, not at the scheduling stage, so it initially appears scheduled successfully before failing.

### 5.3 Container-Level Override of a Pod-Level Default

**Purpose:** Demonstrate the override relationship directly — one container in a multi-container Pod deliberately diverging from the Pod-level default.

**Syntax:**

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000 # Pod-level default for all containers
  containers:
    - name: app
      image: myregistry.example.com/app:2.1.0
      # inherits runAsUser: 1000 from Pod level — no override needed
    - name: legacy-sidecar
      image: vendor-sidecar-needing-root:3.2
      securityContext:
        runAsUser: 0 # container-level override — ONLY valid if runAsNonRoot
        runAsNonRoot: false # is also explicitly overridden to false here
```

**Example usage and expected output:**

```bash
$ kubectl exec multi-container-pod -c app -- id
uid=1000 gid=0
$ kubectl exec multi-container-pod -c legacy-sidecar -- id
uid=0 gid=0
```

**Production usage example:** This pattern is common when integrating a third-party sidecar (a legacy monitoring agent, for instance) that genuinely requires root while the primary application container is fully hardened — but it should be treated as a flagged exception requiring explicit justification and review, never a casual default.

**Common errors:** Overriding `runAsUser: 0` at the container level without also overriding `runAsNonRoot: false` for that same container — the Pod-level `runAsNonRoot: true` still applies and the container fails to start with the same `CreateContainerConfigError` shown in the earlier example, since the container-level override didn't fully counteract the inherited assertion.

## 6. Production Usage Notes

- **`readOnlyRootFilesystem: true` is one of the single highest-value hardening settings available**, and its main practical cost is simply identifying every path the application actually needs to write to and mounting a scoped `emptyDir` or volume there — this is usually a short, one-time discovery effort per application, not an ongoing burden.
- **`capabilities.drop: ["ALL"]` should be the default starting point for essentially every container**, with specific capabilities added back only when a concrete, identified need exists (binding a privileged port, manipulating network interfaces) — most application containers need zero additional capabilities beyond the drop-all baseline.
- **Pod Security Admission's Restricted profile ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) codifies most of this section's recommendations as enforced policy** — in a cluster where that profile is active on a namespace, Pods violating these SecurityContext expectations are rejected outright at admission time rather than merely flagged.

## 7. Security Considerations

- **`allowPrivilegeEscalation: false` blocks a specific, well-known escalation vector** — setuid/setgid binaries and certain capability-granting mechanisms that would otherwise let a process gain more privilege than the one it started with — and should be set explicitly on essentially every production container; it is not the default.
- **A Pod-level `runAsNonRoot: true` doesn't automatically protect every container** in a multi-container Pod if any individual container overrides it back to `false` — always audit every container's _effective_ (Pod default merged with container override) SecurityContext, not just the Pod-level block.
- **This section's fields are the SecurityContext baseline; genuine defense-in-depth requires layering seccomp profiles, AppArmor profiles, and potentially a hardened runtime (gVisor/Kata) on top**, all covered at full CKS depth in [§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)–[§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md) — SecurityContext alone reduces risk substantially but is not a complete container-escape mitigation on its own.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                              | Resolution Path                                                                          |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Pod stuck in `CreateContainerConfigError`, event mentions `runAsNonRoot` | Image has no non-root default user, and no explicit `runAsUser` override was set                          | Add `runAsUser: <uid>` explicitly, or rebuild the image with a non-root `USER` directive |
| Application crashes immediately with permission-denied writing to a path | `readOnlyRootFilesystem: true` set without a writable volume mounted for that specific path               | Identify the exact paths the app writes to, mount scoped `emptyDir`/volumes there        |
| Container-level override of `runAsUser: 0` still fails to start          | Pod-level `runAsNonRoot: true` still applies since it wasn't also overridden to `false` on that container | Explicitly set `runAsNonRoot: false` at the container level alongside `runAsUser: 0`     |

## 9. Best Practices

- Set `runAsNonRoot: true`, an explicit `runAsUser`, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, and `capabilities.drop: ["ALL"]` as the default template for every new workload, adding back only what's specifically justified.
- Treat any container needing `runAsUser: 0` or additional capabilities as a flagged, reviewed exception with a documented justification, not a routine configuration choice.
- Audit multi-container Pods' _effective_ SecurityContext per container (Pod default merged with any container-level override), not just the Pod-level block, since one permissive sidecar undermines the hardening of the rest of the Pod.

## 10. Common Anti-Patterns / Mistakes

- **Leaving SecurityContext entirely unset "to keep things simple,"** inheriting the container runtime's permissive defaults (often root, broad capabilities, writable filesystem) with no active justification.
- **Setting `readOnlyRootFilesystem: true` without first identifying every path the application writes to**, causing preventable startup crashes that get misdiagnosed as application bugs.
- **Assuming a Pod-level `runAsNonRoot: true` protects every container in a multi-container Pod** without checking whether any individual container has overridden it back to permissive settings.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between setting SecurityContext at the Pod level versus the container level?"_
**Model answer:** Pod-level SecurityContext (`spec.securityContext`) sets defaults that apply to every container in the Pod unless a specific container overrides them. Container-level SecurityContext (`spec.containers[].securityContext`) applies only to that one container and takes precedence over the Pod-level default for any field it explicitly sets. Some fields, like `fsGroup`, only make sense at the Pod level because they affect shared volume ownership across all containers, not a single container's process identity.
_What the interviewer is probing for:_ Basic understanding of the override relationship and that it's field-by-field, not all-or-nothing.

**🎯 Intermediate:** _"A Pod with `readOnlyRootFilesystem: true` crashes on startup with permission-denied errors. What's the likely cause and fix?"_
**Model answer:** The application almost certainly needs to write to some path — temp files, a cache directory, log files — that now sits on the read-only root filesystem. The fix isn't to remove `readOnlyRootFilesystem`, since that gives up real hardening value; instead, identify exactly which paths the application needs write access to (often just `/tmp`, or a specific cache or log directory) and mount a scoped writable volume, typically an `emptyDir`, at precisely that path. This keeps the vast majority of the filesystem locked down while still giving the application the narrow writable surface it actually requires.
_What the interviewer is probing for:_ Practical debugging instinct — diagnosing the root cause correctly and fixing it without abandoning the hardening setting.

**🎯 Senior:** _"Why is `capabilities.drop: ['ALL']` followed by a narrow `add` list considered better practice than starting from the default capability set and removing specific risky ones?"_
**Model answer:** Starting from `drop: ["ALL"]` establishes a genuine zero-trust baseline — the container has no Linux capabilities beyond what's explicitly granted back, so any capability the application doesn't specifically need is guaranteed absent. Starting from the container runtime's default capability set and trying to remove specific risky ones (an allow-list-by-omission approach) is fragile: it depends on someone correctly enumerating every capability that could be dangerous, and any capability not thought of stays granted by default. It also doesn't age well — the default capability set can change across container runtime versions, silently reintroducing capabilities a manifest's original author never considered. Dropping everything and adding back only what's concretely justified (like `NET_BIND_SERVICE` for a service binding to a privileged port) is a much more defensible, auditable security posture, and it's exactly the pattern Pod Security Admission's Restricted profile effectively expects.
_What the interviewer is probing for:_ Understanding of allow-list versus deny-list security reasoning, applied to a concrete Kubernetes mechanism.

**🎯 Architect:** _"Design the SecurityContext policy you'd enforce platform-wide across a large organization's Kubernetes workloads, and how you'd actually enforce it rather than just document it."_
**Model answer:** I'd define a baseline template requiring `runAsNonRoot: true` with an explicit `runAsUser`, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities.drop: ["ALL"]` with only justified additions, and a `seccompProfile.type: RuntimeDefault` at minimum — essentially codifying this section's baseline as the organizational default. Enforcement, though, can't rely on teams remembering to copy the template correctly; I'd apply the Pod Security Standards' Restricted profile ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) via Pod Security Admission at the namespace level for any namespace running production workloads, so non-compliant Pods are rejected outright at admission time rather than merely flagged in a review. For legitimate exceptions (a legacy vendor sidecar genuinely requiring root, for instance), I'd require those to run in a separately labeled namespace with a lower enforcement profile and an explicit, time-bound, reviewed exception ticket, rather than allowing the Restricted profile to be silently disabled wherever it's inconvenient. I'd also wire static manifest linting (kube-linter or Kubesec, [§114](../Part15/Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md)) into CI so violations are caught before a PR merges, not just at cluster admission time — catching a violation in CI is a faster, cheaper feedback loop for the developer than a rejected `kubectl apply` in a shared cluster.
_What the interviewer is probing for:_ Ability to translate a SecurityContext baseline into layered, actually-enforced governance (admission control plus CI linting plus an exception process), not just a written standard teams are expected to follow voluntarily.

## 12. Common Misconceptions

1. **"Setting SecurityContext fields is optional hardening, not something that affects whether a Pod runs at all."** `runAsNonRoot: true` is actively enforced at container creation — a violating image causes `CreateContainerConfigError`, not a warning.
2. **"A Pod-level SecurityContext setting guarantees the same behavior for every container in the Pod."** Any container can override a Pod-level default field-by-field; a hardened Pod-level block doesn't protect against one permissively-configured container.
3. **"`readOnlyRootFilesystem: true` means the application can't write anything anywhere."** It only locks the root filesystem; explicitly mounted volumes remain writable unless separately marked read-only, which is exactly how applications needing scratch space are accommodated.
4. **"SecurityContext alone is sufficient container hardening."** It's the essential baseline, but genuine defense-in-depth requires layering seccomp, AppArmor, and potentially a hardened runtime on top, covered at CKS depth in [§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)–[§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md).

## 13. 🔑 Key Takeaways

- SecurityContext exists at both Pod level (default for all containers) and container level (overrides the default per field for one container), never wholesale replacement of the other.
- `runAsNonRoot: true` is an actively enforced assertion at container start, not descriptive metadata — a violating image fails with `CreateContainerConfigError`.
- `readOnlyRootFilesystem: true` combined with a narrowly scoped writable volume for actual write paths is the standard, high-value production pairing.
- `capabilities.drop: ["ALL"]` plus a narrow, justified `add` list is a stronger, more auditable posture than trying to remove specific capabilities from a permissive default set.
- This section's fields are the essential baseline that Pod Security Admission's Restricted profile ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) enforces as policy, and that CKS-level material ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)–[§121](../Part15/Section-121-Part15-Monitoring-Logging-Runtime-Threat-Detection-CKS-Exam.md)) builds further hardening on top of.

## 14. Related Concepts & What's Next

This section builds directly on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)'s Pod spec anatomy, where SecurityContext fields first appeared inline, and connects forward to [§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md) (Part 10, Pod Security Standards and Pod Security Admission, which enforces much of this section's baseline as active policy) and to Part 15's CKS-level hardening material ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)–[§121](../Part15/Section-121-Part15-Monitoring-Logging-Runtime-Threat-Detection-CKS-Exam.md)), which layers seccomp, AppArmor, and hardened container runtimes on top of the SecurityContext foundation established here. [§46](./Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md), next, moves from security posture to resource governance — requests, limits, and Quality-of-Service classes.

**Next Section:** [§46](./Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md) — `Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md`
