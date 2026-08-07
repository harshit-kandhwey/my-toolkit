# Section 136 (Part 17): CKS-Style Scenario Question Bank

## 1. Definition

**Plain language:** [§134](./Section-134-Part17-CKA-Style-Scenario-Question-Bank.md) drilled operator scenarios and [§135](./Section-135-Part17-CKAD-Style-Scenario-Question-Bank.md) drilled developer scenarios; this section drills the third lens entirely — attacker-minded, security-first scenarios where the "correct" answer is frequently the most restrictive configuration that still lets the workload function, not the one that merely makes an error message disappear.

**Precise definition:** This section is a **scenario question bank** modeled on the CKS's actual performance-based task format, weighted toward its six official domains — Cluster Setup, Cluster Hardening, System Hardening, Minimize Microservice Vulnerabilities, Supply Chain Security, and Monitoring/Logging/Runtime Security. Each scenario states the exam-style prompt, a worked solution, and the specific hardening or detection skill it validates. The CKS assumes an active CKA, so scenarios below build on [§134](./Section-134-Part17-CKA-Style-Scenario-Question-Bank.md)'s cluster-operator competence rather than re-teaching it.

## 2. Why This Matters

- **The CKS is the only one of the three exams where "it works" and "it passes" can genuinely diverge** — a Pod that runs successfully as root with a mounted host path is functionally fine but fails a CKS-style hardening check; this bank trains evaluating configurations against a security bar, not just a functional one.
- **Every CKS domain maps to a concrete Part 15 subsection**, meaning scenario fluency here is a direct measure of whether that Part's material (kube-bench, AppArmor/seccomp, image scanning, Falco) has been internalized as muscle memory or only read once.
- **Supply chain and runtime security scenarios (image scanning, admission control, Falco rules) are newer additions to the certification landscape than RBAC/NetworkPolicy** and are consistently the weakest-prepared area for candidates coming from a pure CKA background — this bank weights toward exactly that gap.

🔑 **Key Takeaway:** CKS scenarios reward choosing the most restrictive configuration that still satisfies the stated functional requirement — when in doubt between two valid-looking answers, the more locked-down one is almost always the intended one.

## 3. Prerequisites and Dependencies

Requires CKA-level competence ([§134](./Section-134-Part17-CKA-Style-Scenario-Question-Bank.md)) and builds directly on Part 15's CKS deep dive: cluster setup hardening and kube-bench ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)), system hardening with seccomp/AppArmor ([§114](../Part15/Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md)), microservice vulnerability minimization and SecurityContext hardening ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)), supply chain security — image scanning and signing ([§116](../Part15/Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)), static manifest analysis ([§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)), runtime security with Falco ([§118](../Part15/Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)), network security and mTLS ([§119](../Part15/Section-119-Part15-Network-Security-Deep-Dive-mTLS-Service-Mesh-Security.md)), secrets encryption ([§120](../Part15/Section-120-Part15-Secrets-Encryption-External-Secret-Stores-Deep-Dive.md)), and monitoring/logging for security ([§121](../Part15/Section-121-Part15-Monitoring-Logging-Runtime-Threat-Detection-CKS-Exam.md)). Also assumes RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) and Pod Security Admission ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) from Part 10.

## 4. Architecture Diagram: Scenario Category Breakdown

```text
   CKS Exam Domain Weight → This Question Bank's Scenario Mix

   Minimize Microservice Vulns (20%)   ████████████████████████████  Scenario 2, 5
   Supply Chain Security (20%)         ████████████████████████████  Scenario 3
   Monitoring/Logging/Runtime Sec (20%) ████████████████████████████  Scenario 6, 7
   System Hardening (15%)              █████████████████████           Scenario 4
   Cluster Hardening (15%)             █████████████████████           Scenario 1
   Cluster Setup (10%)                 ██████████████                    Scenario 1 (setup half)

   CKS decision heuristic when two fixes both "work":
   ┌──────────────────────────────────────────────────────────────┐
   │ Does it run as non-root?               → prefer yes          │
   │ Does it need the capability it has?    → drop what's unused  │
   │ Is the image from a scanned, signed,    │                    │
   │  pinned-digest source?                  → prefer yes         │
   │ Is the NetworkPolicy default-deny first,│                    │
   │  then explicitly allowed?               → prefer yes         │
   │ Would an admission controller have      │                    │
   │  caught this before it ran?              → prefer yes        │
   └──────────────────────────────────────────────────────────────┘
```

- **The exam consistently prefers "prevent" over "detect" and "detect" over "allow and hope"** — an admission-time block beats a Falco alert after the fact, which beats no control at all; scenarios below are ordered to reflect that hierarchy.
- **Every scenario category maps 1:1 to a named Part 15 subsection**, reinforcing that this bank is a direct fitness check on that Part's depth, not new material.

## 5. Hands-On: The Scenario Question Bank

### Scenario 1 — Running kube-bench and Remediating a Failed Check (7 minutes)

**Prompt as seen on exam:**

> Context: `kubectl config use-context k8s-c1`. Run `kube-bench` against the control-plane node and remediate the first `FAIL` result related to the API server's `--anonymous-auth` setting.

**Solution:**

```bash
kubectl config use-context k8s-c1
kube-bench run --targets master
# Example FAIL: 1.2.1 Ensure that the --anonymous-auth argument is set to false
ssh controlplane-1
sudo vi /etc/kubernetes/manifests/kube-apiserver.yaml
# add or correct: --anonymous-auth=false
# kubelet watches this static pod path; apiserver restarts automatically
exit
kubectl get pods -n kube-system | grep apiserver
kube-bench run --targets master
```

**What it's testing:** Direct kube-bench workflow and remediation of a static-pod-manifest flag ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)), and understanding that editing a static Pod manifest triggers an automatic kubelet-driven restart rather than requiring `kubectl apply`.

### Scenario 2 — Hardening a Pod's SecurityContext to the Restricted Baseline (6 minutes)

**Prompt as seen on exam:**

> Namespace `apps`. Deployment `api-gateway` currently runs its container as root with all default Linux capabilities and a writable root filesystem. Harden it to run as non-root, drop all capabilities, and use a read-only root filesystem, without breaking the running application (which writes only to `/tmp`).

**Solution:**

```yaml
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: api-gateway
          image: myregistry/api-gateway:4.2
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
```

```bash
kubectl -n apps apply -f api-gateway-hardened.yaml
kubectl -n apps rollout status deployment api-gateway
kubectl -n apps exec deploy/api-gateway -- touch /tmp/test-write
```

**What it's testing:** SecurityContext hardening exactly ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)) — `runAsNonRoot`, dropping all capabilities, `readOnlyRootFilesystem` — combined with recognizing that "writes only to /tmp" requires an `emptyDir` volume mounted at `/tmp` specifically so the read-only root filesystem doesn't break the one legitimate write path the application needs.

### Scenario 3 — Blocking Unscanned Images With an Admission Controller (8 minutes)

**Prompt as seen on exam:**

> A `ValidatingAdmissionPolicy` (or webhook, depending on cluster version) is partially configured in namespace `production` to reject any Pod whose image is not from the trusted registry `registry.internal.corp`. Complete the policy so it correctly blocks `docker.io/library/nginx:latest` but allows `registry.internal.corp/nginx:1.25`.

**Solution:**

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: trusted-registry-only
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE"]
        resources: ["pods"]
  validations:
    - expression: >
        object.spec.containers.all(c,
          c.image.startsWith("registry.internal.corp/"))
      message: "Only images from registry.internal.corp are permitted"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: trusted-registry-only-binding
spec:
  policyName: trusted-registry-only
  validationActions: ["Deny"]
  matchResources:
    namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: production
```

```bash
kubectl apply -f trusted-registry-policy.yaml
kubectl -n production run test-bad --image=docker.io/library/nginx:latest
# expect: denied
kubectl -n production run test-good --image=registry.internal.corp/nginx:1.25
# expect: created
```

**What it's testing:** Supply chain enforcement at admission time ([§116](../Part15/Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)) using a CEL-based `ValidatingAdmissionPolicy`, and correctly scoping the binding to a single namespace via `namespaceSelector` rather than accidentally applying a registry restriction cluster-wide where it could break unrelated system namespaces.

### Scenario 4 — Restricting a Container's Syscalls With a seccomp Profile (7 minutes)

**Prompt as seen on exam:**

> Namespace `sandbox`. Pod `untrusted-workload` must run with a seccomp profile that blocks dangerous syscalls beyond the container runtime default. Apply the `RuntimeDefault` seccomp profile, then demonstrate applying a stricter custom profile as an alternative.

**Solution:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: untrusted-workload
  namespace: sandbox
spec:
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: workload
      image: myregistry/untrusted-workload:1.0
```

```yaml
# Alternative: custom profile referencing a file staged on every node
# at /var/lib/kubelet/seccomp/profiles/custom-restrictive.json
securityContext:
  seccompProfile:
    type: Localhost
    localhostProfile: profiles/custom-restrictive.json
```

```bash
kubectl apply -f untrusted-workload.yaml
kubectl -n sandbox get pod untrusted-workload -o jsonpath='{.spec.securityContext.seccompProfile}'
```

**What it's testing:** seccomp profile types exactly ([§114](../Part15/Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md)) — `RuntimeDefault` versus `Localhost` with a `localhostProfile` path — and the operational reality that a `Localhost` profile requires the JSON file to already be staged identically on every node the Pod could schedule to, or the Pod fails to start with an unhelpfully generic error.

### Scenario 5 — Detecting and Removing an Unnecessary hostPath Mount and Privileged Flag (5 minutes)

**Prompt as seen on exam:**

> Namespace `legacy`. Pod spec `legacy-agent.yaml` (provided) runs `privileged: true` and mounts `/` from the host at `/host`. The application only actually needs read access to `/var/log` on the host. Correct the manifest to the minimum required access.

**Solution:**

```yaml
# before (as provided) — privileged: true, hostPath: /
# after:
apiVersion: v1
kind: Pod
metadata:
  name: legacy-agent
  namespace: legacy
spec:
  containers:
    - name: agent
      image: myregistry/legacy-agent:1.0
      securityContext:
        privileged: false
        allowPrivilegeEscalation: false
      volumeMounts:
        - name: hostlogs
          mountPath: /host/var/log
          readOnly: true
  volumes:
    - name: hostlogs
      hostPath:
        path: /var/log
        type: Directory
```

```bash
kubectl -n legacy apply -f legacy-agent.yaml
kubectl -n legacy exec legacy-agent -- ls /host/var/log
```

**What it's testing:** The core "minimize microservice vulnerabilities" instinct ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)) of narrowing both the `privileged` flag and the `hostPath` scope to exactly what's functionally required — a full-root hostPath mount plus `privileged: true` is one of the most common CKS anti-patterns, effectively equivalent to handing the container root on the underlying node.

### Scenario 6 — Writing a Falco Rule to Detect Shell Spawned Inside a Container (6 minutes)

**Prompt as seen on exam:**

> Falco is already installed and running as a DaemonSet. Add a custom rule that alerts whenever a shell (`bash`, `sh`) is spawned inside any container in namespace `production`, since these containers should never need an interactive shell at runtime.

**Solution:**

```yaml
# /etc/falco/rules.d/no-shell-in-production.yaml
- rule: Unexpected Shell in Production Container
  desc: Detect shell spawned inside a container in the production namespace
  condition: >
    spawned_process and
    container and
    k8s.ns.name = "production" and
    proc.name in (bash, sh)
  output: >
    Shell spawned in production container
    (user=%user.name container=%container.name pod=%k8s.pod.name
    namespace=%k8s.ns.name command=%proc.cmdline)
  priority: WARNING
  tags: [container, shell, mitre_execution]
```

```bash
kubectl -n falco-system rollout restart daemonset falco
kubectl -n production exec <some-pod> -- sh -c "echo test"
kubectl -n falco-system logs -l app=falco --tail=20
```

**What it's testing:** Custom Falco rule authoring against real Sysdig filter fields ([§118](../Part15/Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)) — `k8s.ns.name`, `proc.name`, `spawned_process` — and recognizing that an interactive shell inside a production container is itself a runtime security signal worth alerting on, independent of whatever the shell command actually did.

### Scenario 7 — Enabling Audit Logging to Capture Secret Access Events (7 minutes)

**Prompt as seen on exam:**

> Configure the API server's audit policy so that every `get`/`list` request against `Secret` objects in any namespace is logged at the `Metadata` level (not `RequestResponse`, to avoid logging Secret contents themselves), writing to `/var/log/kubernetes/audit.log`.

**Solution:**

```yaml
# /etc/kubernetes/audit-policy.yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: Metadata
    resources:
      - group: ""
        resources: ["secrets"]
    verbs: ["get", "list"]
  - level: None
    resources:
      - group: ""
        resources: ["events"]
  - level: Metadata
    omitStages: ["RequestReceived"]
```

```yaml
# add to /etc/kubernetes/manifests/kube-apiserver.yaml
- --audit-policy-file=/etc/kubernetes/audit-policy.yaml
- --audit-log-path=/var/log/kubernetes/audit.log
- --audit-log-maxage=7
- --audit-log-maxbackup=3
```

```bash
kubectl get secret -n default
tail -20 /var/log/kubernetes/audit.log | grep secrets
```

**What it's testing:** API server audit policy authoring ([§121](../Part15/Section-121-Part15-Monitoring-Logging-Runtime-Threat-Detection-CKS-Exam.md)), and the crucial `Metadata` versus `RequestResponse` distinction — logging Secret access at `Metadata` level captures who accessed what and when without ever writing the Secret's actual decoded contents into the audit log itself, which would otherwise create a second, less-guarded copy of sensitive data.

## 6. Production Usage Notes: Practicing Under Real Exam Time Pressure

- **Keep a mental (or actual, in early practice) checklist of the CKS hardening heuristic** — non-root, dropped capabilities, read-only root filesystem, scanned/pinned images, default-deny NetworkPolicy — and run every scenario's provided manifest against it before assuming the task is only asking for the one thing explicitly named.
- **Practice reading `kube-bench` output for the specific remediation text it provides**, not just the pass/fail line — the tool's own output usually names the exact flag or file to change, and re-deriving it from memory instead wastes time.
- **Rehearse Falco rule syntax against the actual field reference, not from memory** — `k8s.ns.name`, `proc.name`, `container.id` and similar fields are easy to misremember under pressure, and a syntactically-invalid rule fails silently rather than erroring loudly in some Falco versions.
- **Time audit-policy tasks generously in practice** — the YAML nesting (`rules`, `resources`, `verbs`, `level`) is easy to get subtly wrong, and a broken audit policy can prevent the API server from starting at all, which is a much larger recovery cost than a typo in a Pod spec.

## 7. Security Considerations

Every scenario in this section is itself a security consideration by construction, but three cross-cutting points deserve emphasis: first, an audit policy misconfiguration (Scenario 7) can crash-loop the API server if the policy file is malformed or the referenced path doesn't exist — always validate the YAML and confirm the file is readable by the API server's process before restarting it, since a broken control plane is a worse outcome than the unaudited Secret access it was meant to catch. Second, admission-time blocking (Scenario 3) is strictly preferable to runtime detection (Scenario 6) wherever both are possible — Falco tells you a bad shell was spawned after it happened, while a `ValidatingAdmissionPolicy` prevents the bad image from ever running in the first place; design defense in depth with prevention as the first layer, not the only layer. Third, `hostPath` plus `privileged: true` (Scenario 5) is functionally equivalent to granting root on the underlying node — treat any manifest combining both as an automatic hardening failure regardless of what else it does correctly.

## 8. Common Troubleshooting Scenarios

| Symptom During Practice                                                   | Cause                                                                     | Fix                                                                                                                  |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| API server won't come back up after an audit-policy edit                  | Malformed YAML or a referenced file path that doesn't exist on the node   | Validate the policy YAML locally first; check `/var/log/pods/.../kube-apiserver/*.log` for the parse error           |
| Pod with `readOnlyRootFilesystem: true` crashes on startup                | Application writes somewhere outside the one path it was expected to use  | Add an `emptyDir` volume mount at the specific path the app actually writes to, not the whole root                   |
| `Localhost` seccomp profile Pod fails with a vague `CreateContainerError` | The profile JSON file isn't present on the node the Pod scheduled to      | Confirm the file is staged identically at `/var/lib/kubelet/seccomp/profiles/` on every node                         |
| ValidatingAdmissionPolicy doesn't block the expected Pod                  | Binding's `namespaceSelector` doesn't match the target namespace's labels | `kubectl get ns --show-labels` to confirm the actual label the selector needs to match                               |
| Falco rule never fires despite the triggering action happening            | Rule file not loaded (missing restart) or field name typo                 | Restart the Falco DaemonSet after adding rule files; validate field names against the current Falco version's schema |

## 9. Best Practices

- Apply the "most restrictive that still functions" heuristic by default across every scenario, and only loosen a control when the prompt's stated functional requirement genuinely can't be met otherwise.
- Prefer admission-time prevention over runtime detection wherever the cluster supports it, treating Falco-style detection as the second layer of defense in depth, not the primary control.
- Validate any control-plane-affecting change (audit policy, API server flags) for syntax correctness before applying, since a broken control plane is a categorically worse failure mode than the misconfiguration it was meant to fix.

## 10. Common Anti-Patterns / Mistakes

- **Setting `privileged: true` or mounting `/` via `hostPath` "to be safe" when a narrower path and non-privileged mode would work** — broader access is not safer, it's the opposite of the CKS's entire premise.
- **Logging Secret access at `RequestResponse` level "to see everything," inadvertently writing decoded Secret contents into the audit log itself** — a second, less-protected copy of the exact data the control was meant to protect.
- **Treating Falco alerts as sufficient security control on their own**, without any admission-time prevention layer — detection after the fact is valuable but is not a substitute for blocking the bad configuration from running at all.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `RuntimeDefault` and a custom `Localhost` seccomp profile, and when would you use each?"_
**Model answer:** `RuntimeDefault` uses the container runtime's built-in seccomp profile, which already blocks a broad set of dangerous syscalls and is a safe baseline for nearly every workload with zero extra staging effort. A `Localhost` profile references a custom JSON file staged on the node, letting you restrict (or in rare cases permit) syscalls more precisely than the runtime default — used when a workload's threat model calls for tighter restriction than the default provides, at the cost of having to author, test, and distribute that profile file to every node the Pod could land on.
_What the interviewer is probing for:_ Correctly identifying that `Localhost` requires node-side file staging, a detail many candidates miss until they hit the "file not found" failure mode in practice.

**🎯 Intermediate:** _"Why is `Metadata`-level audit logging preferred over `RequestResponse` for Secret access, specifically?"_
**Model answer:** `Metadata` level logs who did what and when — user, verb, resource, timestamp — without capturing the request or response bodies. `RequestResponse` would additionally log the full response body, which for a `get` on a Secret means the decoded Secret contents themselves get written into the audit log. That creates a second, often less access-controlled copy of the exact sensitive data the audit trail was supposed to help protect, effectively undermining the control it's meant to support.
_What the interviewer is probing for:_ Understanding that audit logging itself can become an attack surface if configured too verbosely, not just recall of the two level names.

**🎯 Senior:** _"You've hardened a Pod's SecurityContext (non-root, dropped capabilities, read-only root filesystem) and it now fails to start. How do you triage without simply reverting the hardening?"_
**Model answer:** First check `kubectl describe pod` and container logs for the specific failure — commonly a permission-denied write to a path the app assumed was writable, or a capability the app genuinely needs (e.g., binding to a privileged port below 1024 needs `NET_BIND_SERVICE` even as non-root). Rather than reverting wholesale, I'd add back the minimum needed: an `emptyDir` mount at the specific path that needs to be writable, or restore only the one specific capability the app requires instead of restoring the whole default set. The goal is diagnosing exactly which piece of the hardened baseline the app genuinely depends on and restoring only that piece, keeping everything else locked down — reverting all the way back to permissive defaults because one specific requirement was missed is treating the symptom as the whole problem.
_What the interviewer is probing for:_ A surgical debugging mindset for hardening regressions, versus the common shortcut of abandoning the hardening entirely when the first attempt breaks something.

**🎯 Architect:** _"Design a defense-in-depth strategy for a multi-tenant cluster running untrusted third-party workloads, combining admission control, runtime detection, and audit logging so that no single layer's failure fully exposes the cluster."_
**Model answer:** At admission time, I'd enforce Pod Security Admission at the `restricted` level ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) plus a supply-chain `ValidatingAdmissionPolicy` requiring images from a scanned, signed registry with pinned digests (never `:latest`), rejecting anything privileged or using `hostPath` outright for tenant workloads — this is the first layer, preventing the worst configurations from ever running. As a second layer assuming something still gets through (a supply-chain compromise of an otherwise-trusted image, for instance), Falco rules watching for shell spawns, unexpected outbound connections, and sensitive file reads inside tenant namespaces provide runtime detection independent of whether the workload passed admission cleanly. As a third layer, audit logging at `Metadata` level across Secret and RBAC-object access gives a forensic trail if the first two layers are bypassed, letting incident response reconstruct exactly what a compromised workload touched — critically, none of these three layers assumes the others are working, so a gap in admission control doesn't leave the cluster fully blind, and a missed Falco alert doesn't leave zero record of what happened. I'd also isolate tenants with dedicated namespaces plus default-deny NetworkPolicies (Part 7) and, if genuinely mutually-distrusting tenants share nodes, consider gVisor/Kata Containers ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)) for stronger kernel-level isolation than SecurityContext hardening alone provides.
_What the interviewer is probing for:_ Genuine defense-in-depth reasoning — each layer assumed to eventually fail on its own, with the next layer compensating — rather than treating any single control (even a well-configured one) as sufficient.

## 12. Common Misconceptions

1. **"Falco monitoring means I don't need strict admission control."** Detection after the fact is not a substitute for prevention; a compromised container can do damage in the window between the Falco alert firing and a human responding.
2. **"`privileged: true` is sometimes just the easy fix to get a stubborn workload running."** It's almost always a sign the actual required capability or mount hasn't been identified precisely — the CKS consistently expects the narrower, correctly-scoped fix instead.
3. **"Audit logging everything at maximum verbosity is always the safest choice."** Logging response bodies for sensitive resources like Secrets can itself create an exposure the control was meant to prevent; log level should match sensitivity, not default to maximum everywhere.
4. **"A `Localhost` seccomp profile is just a config field, no different operationally from `RuntimeDefault`."** It requires the profile file to be staged identically on every node the Pod might schedule to, an operational dependency `RuntimeDefault` doesn't have.

## 13. 🔑 Key Takeaways

- CKS scenarios consistently reward the most restrictive configuration that still satisfies the stated functional requirement — when uncertain between two options, choose the tighter one.
- Admission-time prevention (Pod Security Admission, ValidatingAdmissionPolicy, image-trust policies) should be the first layer of defense; runtime detection (Falco) and audit logging are subsequent layers, not substitutes for prevention.
- `privileged: true` combined with a broad `hostPath` mount is functionally equivalent to node root and should be treated as an automatic hardening failure in any scenario.
- Audit logging Secret access at `Metadata` (not `RequestResponse`) level avoids creating a second, less-protected copy of the exact sensitive data the audit trail exists to protect.
- Hardening regressions (a Pod that stops starting after SecurityContext changes) should be triaged surgically — restore only the specific capability or writable path genuinely needed, not the whole permissive baseline.

## 14. Related Concepts & What's Next

This section drew its scenario material directly from Part 15's CKS deep dive — cluster setup and kube-bench ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)), system hardening ([§114](../Part15/Section-114-Part15-System-Hardening-Minimizing-Host-OS-Attack-Surface-seccomp-AppArmor.md)), SecurityContext hardening ([§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)), supply chain security ([§116](../Part15/Section-116-Part15-Supply-Chain-Security-Image-Scanning-Trivy-Signing-Cosign-Sigstore-SBOM.md)–[§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)), runtime security with Falco ([§118](../Part15/Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)), and audit logging ([§121](../Part15/Section-121-Part15-Monitoring-Logging-Runtime-Threat-Detection-CKS-Exam.md)) — and assumed CKA-level operator competence from [§134](./Section-134-Part17-CKA-Style-Scenario-Question-Bank.md) as a baseline. [§137](./Section-137-Part17-Architect-Level-Behavioral-Technical-Crossover-Questions.md), the capstone of Part 17, moves up a level from certification-specific scenarios to architect-level and behavioral-technical crossover questions, synthesizing this entire exam-prep Part alongside senior-level concepts from across the whole knowledge base.

**Next Section:** [§137](./Section-137-Part17-Architect-Level-Behavioral-Technical-Crossover-Questions.md) — `Section-137-Part17-Architect-Level-Behavioral-Technical-Crossover-Questions.md`
