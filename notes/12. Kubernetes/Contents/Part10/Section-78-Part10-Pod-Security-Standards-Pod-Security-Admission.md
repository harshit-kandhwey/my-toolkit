# Section 78 (Part 10): Pod Security Standards: Privileged, Baseline, and Restricted; Pod Security Admission

## 1. Definition

**Plain language:** §77 established that admission control is where policy actually gets enforced against real object content, beyond what RBAC's coarse verb/resource model can express. But writing a custom validating webhook every time an organization wants to say "no privileged Pods" is a lot of infrastructure for a need nearly every cluster shares. Pod Security Standards are Kubernetes' own opinionated answer to exactly that common need — a small, named set of security policy tiers, enforced natively without any custom webhook at all.

**Precise definition:** **Pod Security Standards (PSS)** are three built-in, upstream-defined policy levels — **Privileged** (unrestricted, allows everything including host namespaces and privileged containers), **Baseline** (blocks known privilege-escalation vectors while remaining broadly compatible with common workloads), and **Restricted** (enforces current Pod hardening best practice, including mandatory non-root execution and a fully dropped Linux capability set) — each defined as a fixed checklist of SecurityContext (§45) and Pod-spec constraints. **Pod Security Admission (PSA)** is the built-in admission controller (successor to the deprecated PodSecurityPolicy, removed in Kubernetes v1.25) that enforces these standards, configured entirely through **namespace labels** rather than a separate policy object — a label like `pod-security.kubernetes.io/enforce: restricted` on a namespace is sufficient to activate enforcement, with no webhook, no CRD, and no additional controller to deploy.

## 2. Why This Matters

- **PSA replaced PodSecurityPolicy (PSP), a mechanism that was deprecated in v1.21 and fully removed in v1.25** — any organization or exam candidate encountering PSP references in older material needs to recognize it as legacy, with PSA as the current, supported native mechanism for the same problem space.
- **PSA is configured purely through namespace labels, not a bespoke API object**, meaning the entire enforcement surface for a namespace is visible in a single `kubectl get namespace <ns> --show-labels` — a deliberate simplicity trade-off, sacrificing PSP's fine-grained per-workload exemption flexibility for something every cluster operator can reason about at a glance.
- **PSA supports three independent modes per namespace (`enforce`, `audit`, `warn`) at potentially different policy levels simultaneously**, letting teams run a stricter level in `warn` mode to observe what would break before ever flipping it to `enforce` — a built-in, zero-infrastructure rollout safety net that a hand-rolled validating webhook (§77) would have to be deliberately engineered to replicate.

🔑 **Key Takeaway:** Pod Security Admission is a built-in admission controller (the direct successor to the deprecated PodSecurityPolicy) that enforces one of three fixed policy tiers — Privileged, Baseline, Restricted — purely through namespace labels, with independent `enforce`/`audit`/`warn` modes providing a native, zero-webhook rollout path from observation to enforcement.

## 3. Prerequisites and Dependencies

Builds directly on §77 (Admission Controllers — PSA is implemented as exactly the built-in admission controller mechanism that section describes) and §45 (SecurityContext, Part 6, whose specific fields — `runAsNonRoot`, `allowPrivilegeEscalation`, `capabilities.drop`, `privileged` — are precisely what each Pod Security Standard tier checks). Forward-references §79, which revisits NetworkPolicy (§55, Part 7) as a complementary, network-layer security boundary that PSA does not itself address.

## 4. Architecture: Namespace Labels Driving the Three Tiers

```text
┌─────────────────────────────────────────────────────────────────────┐
│  Namespace: payments                                                │
│  labels:                                                            │
│    pod-security.kubernetes.io/enforce: restricted                   │
│    pod-security.kubernetes.io/enforce-version: v1.29                │
│    pod-security.kubernetes.io/warn: restricted                      │
│    pod-security.kubernetes.io/audit: restricted                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
                  kubectl apply -f pod.yaml  (Pod creation request)
                                │
                                ▼
        ┌────────────────────────────────────────────────────────┐
        │  Pod Security Admission (built-in admission ctrl)      │
        │                                                        │
        │  Checks Pod spec against the RESTRICTED checklist:     │
        │    - runAsNonRoot: true                                │
        │    - allowPrivilegeEscalation: false                   │
        │    - capabilities.drop: ["ALL"]                        │
        │    - seccompProfile.type: RuntimeDefault or Localhost  │
        │    - no hostNetwork / hostPID / hostIPC                │
        │    - privileged: false                                 │
        └───────────────┬──────────────────────┬─────────────────┘
                        │ PASS                 │ FAIL
                        ▼                      ▼
              Pod admitted, created      enforce: rejected outright
                                          warn: admitted + client warning
                                          audit: admitted + audit log entry

           Privileged  ◄───────────  Baseline  ◄───────────  Restricted
        (no restriction)      (blocks known escalation)   (current hardening
                                                             best practice)
```

- **The three PSA modes are independent and can target different policy levels at once** — a namespace commonly runs `enforce: baseline` (a hard floor) alongside `warn: restricted` and `audit: restricted` (visibility into what would break under the stricter tier), letting teams observe a migration path before ever tightening `enforce` itself.
- **The `enforce-version` label pins which Kubernetes version's definition of a policy level applies**, since the Baseline and Restricted checklists are occasionally refined across releases — omitting it defaults to the current cluster version's definition, which can shift policy behavior silently across an upgrade if not pinned deliberately.
- **The three tiers are strictly ordered (Privileged ⊃ Baseline ⊃ Restricted)** — Restricted is a strict superset of Baseline's constraints plus additional hardening, never an alternate, unrelated rule set.

## 5. Hands-On: Applying and Testing Pod Security Standards

### 5.1 Labeling a Namespace for Enforcement

**Purpose:** Activate PSA at the `baseline` level for a namespace, with `restricted` running in observe-only mode first.

**Syntax:**

```bash
kubectl label --overwrite namespace payments \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/enforce-version=v1.29 \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/audit=restricted
```

**Example usage and expected output:**

```bash
$ kubectl label --overwrite namespace payments pod-security.kubernetes.io/enforce=baseline
namespace/payments labeled

$ kubectl get namespace payments --show-labels
NAME       STATUS   AGE   LABELS
payments   Active   40d   pod-security.kubernetes.io/enforce=baseline,...
```

**Production usage example:** This label-only approach means PSA can be rolled out cluster-wide via GitOps (§88) as ordinary namespace manifests, no separate controller deployment or CRD installation required — a materially lower operational bar than PSP ever had, and part of why PSA was designed this way after PSP's removal.

**Common errors:** Applying `enforce: restricted` directly to a namespace already running long-lived Pods without first checking compatibility in `warn`/`audit` mode — existing Pods are not retroactively affected (PSA only evaluates at admission time), but any subsequent rolling update, scale event, or redeploy of those same workloads will suddenly fail, often surprising teams who assume a namespace label change is inert until they push their next unrelated change.

### 5.2 A Pod That Violates the Restricted Standard

**Purpose:** Show PSA rejecting a non-compliant Pod at admission time, with the exact violation reported.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: legacy-app
  namespace: payments
spec:
  containers:
    - name: app
      image: legacy-app:1.4
      securityContext:
        privileged: true
```

**Example usage and expected output:**

```bash
$ kubectl apply -f legacy-app.yaml
Error from server (Forbidden): error when creating "legacy-app.yaml":
pods "legacy-app" is forbidden: violates PodSecurity "restricted:v1.29":
privileged (container "app" must not set securityContext.privileged=true),
allowPrivilegeEscalation != false (container "app" must set
securityContext.allowPrivilegeEscalation=false), unrestricted capabilities
(container "app" must set securityContext.capabilities.drop=["ALL"]),
runAsNonRoot != true (pod or container "app" must set
securityContext.runAsNonRoot=true)
```

**Production usage example:** PSA's rejection message enumerates every violated rule in one response, unlike a typical custom validating webhook (§77) that might only report the first failure it encounters — this makes PSA notably better for iterative fixing, since a developer sees the full remediation list in a single `kubectl apply` attempt rather than fixing one field at a time across repeated tries.

**Common errors:** Reading only the first line of a multi-violation PSA error and fixing just that one field, then re-applying and being surprised by a second, third, and fourth rejection — the full message already lists every violation; read it completely before the first fix attempt.

### 5.3 A Compliant Restricted-Tier Pod

**Purpose:** Show the minimum SecurityContext (§45) fields required to satisfy the Restricted standard.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: hardened-app
  namespace: payments
spec:
  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: hardened-app:2.1
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
```

**Example usage and expected output:**

```bash
$ kubectl apply -f hardened-app.yaml
pod/hardened-app created
```

**Production usage example:** This exact field set is the practical checklist teams migrate toward when a platform team mandates `enforce: restricted` cluster-wide — it's deliberately the same SecurityContext fields covered in §45's baseline, meaning teams that already followed §45's guidance often pass Restricted with no changes at all.

**Common errors:** Setting `runAsNonRoot: true` at the Pod level but forgetting the image itself still defaults to a root user with no `USER` directive in its Dockerfile — Restricted enforcement will reject the Pod at admission with a runtime-agnostic error, but the actual fix requires rebuilding the image, not just adjusting the manifest.

## 6. Production Usage Notes

- **A phased `warn`/`audit` → `enforce` rollout, using PSA's independent per-mode labels, is the standard safe migration path** for tightening an existing namespace's policy level — running the target level in `warn` mode surfaces violations to `kubectl apply` callers immediately, while `audit` mode logs violations to the API server audit log (§96) for retrospective analysis without disrupting any client.
- **PSA operates purely on the Pod spec at admission time and has zero runtime enforcement** — a Pod admitted under Restricted at creation time that later has its image swapped via a mutable tag to a version that behaves differently at runtime is entirely outside PSA's visibility; runtime security (Falco, §117, Part 15) covers that separate concern.
- **PSA cannot express organization-specific policy beyond its three fixed tiers** (mandatory labels, specific registries, image signature checks) — for anything beyond the built-in checklist, a policy engine like OPA Gatekeeper or Kyverno, layered on top of the same webhook mechanism from §77, remains necessary alongside PSA, not instead of it.

## 7. Security Considerations

- **Restricted is the appropriate default enforcement tier for any namespace running untrusted or externally-facing workloads** — it closes the most impactful privilege-escalation vectors (privileged mode, host namespace access, unrestricted Linux capabilities, root execution) with a single namespace label, no custom tooling required.
- **The `kube-system` namespace and other control-plane-adjacent namespaces frequently cannot run under Restricted**, since some system components legitimately require host access or elevated capabilities — applying Restricted cluster-wide, including to `kube-system`, without exemption is a common cause of a self-inflicted control-plane outage; PSA has no namespace-exemption concept beyond simply not labeling that namespace as strictly.
- **PSA enforcement can be bypassed entirely by anyone with permission to edit namespace labels** — RBAC (§75) controlling who can modify a namespace's `pod-security.kubernetes.io/*` labels is itself a meaningful, easy-to-overlook security boundary; without it, a policy-enforcing label is only as durable as the weakest RBAC grant touching namespace objects.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                            | Cause                                                                                                    | Fix                                                                                                                 |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Pod creation rejected with a `violates PodSecurity` error                          | Pod spec fails one or more checks for the namespace's `enforce` level                                    | Read the full rejection message (lists every violation), adjust SecurityContext fields (§45) accordingly            |
| Existing Pods keep running after tightening `enforce`, but the next redeploy fails | PSA only evaluates at admission time — labeling a namespace does not retroactively re-check running Pods | Expected behavior; test the new policy level in `warn`/`audit` mode against real workloads before setting `enforce` |
| `kube-system` Pods fail to (re)schedule after a cluster-wide Restricted rollout    | Restricted applied indiscriminately to namespaces running privileged system components                   | Exempt system-adjacent namespaces; only apply Restricted to workload namespaces that don't need host-level access   |
| A `kubectl apply` succeeds but a warning about policy violation is printed         | Namespace has `warn` mode set at a stricter level than `enforce`                                         | Expected — the object was still admitted; use the warning as a rollout signal to fix before ever raising `enforce`  |

## 9. Best Practices

- Roll out policy tightening in stages: `audit` and `warn` at the target level first, observe for a real workload cycle, then flip `enforce`.
- Default new workload namespaces to `enforce: baseline` at minimum, with `restricted` as the target for anything externally facing or handling sensitive data.
- Pin `enforce-version` explicitly so a cluster upgrade cannot silently change what a given policy level actually checks for.
- Treat RBAC control over namespace label edits as part of the policy's actual security boundary, not an afterthought.

## 10. Common Anti-Patterns / Mistakes

- **Applying `enforce: restricted` cluster-wide, including to `kube-system`**, breaking legitimate system components that require host-level access.
- **Skipping the `warn`/`audit` observation phase and jumping straight to `enforce`** on a namespace with existing, non-compliant workloads, causing avoidable redeploy failures.
- **Treating PSA as a full replacement for a policy engine** when organization-specific requirements (mandatory labels, registry allowlists, signature verification) exceed its three fixed tiers.

## 11. Interview Questions

**🎯 Beginner:** _"What are the three Pod Security Standards levels, and how are they enforced?"_
**Model answer:** The three levels are Privileged (no restriction), Baseline (blocks well-known privilege-escalation vectors while staying broadly compatible), and Restricted (enforces current Pod hardening best practice, including mandatory non-root execution and a fully dropped capability set). They're enforced by Pod Security Admission, a built-in admission controller configured entirely through namespace labels — no separate policy object or webhook is required.
_What the interviewer is probing for:_ Basic recall of the three tiers and the label-based, webhook-free enforcement mechanism.

**🎯 Intermediate:** _"A namespace has `enforce: baseline` but a team says a Pod violating what looks like a Restricted-only rule was still rejected. What might explain that?"_
**Model answer:** I'd first check whether `enforce-version` is pinned or defaulting to the cluster's current version, since Baseline's exact checklist can shift slightly across Kubernetes releases. More likely, though, I'd re-verify the rejected rule is genuinely Baseline-tier and not something the team mistakenly believed was Restricted-only — Baseline already blocks privileged containers and host namespace access, which are commonly (and incorrectly) assumed to be Restricted-exclusive checks.
_What the interviewer is probing for:_ Precise knowledge of what's actually in Baseline versus Restricted, rather than treating the two as vaguely "loose" and "strict."

**🎯 Senior:** _"Why does PSA operate on namespace labels instead of a dedicated policy object like PodSecurityPolicy did, and what trade-off does that represent?"_
**Model answer:** PSP's per-workload, RBAC-bindable policy objects offered fine-grained, per-team exemption flexibility, but that flexibility came at a real operational cost — PSP was notoriously difficult to reason about, since which policy applied to a given Pod depended on an opaque RBAC-binding resolution order that was a frequent source of production incidents and was a major factor in its deprecation. PSA's namespace-label design trades that granularity for radical simplicity and auditability: the entire enforcement posture for a namespace is visible in one label list, with no separate binding resolution to reason about. The cost is that PSA can't express "this one workload in this namespace gets an exemption others don't" — that granularity now has to come from a policy engine (OPA Gatekeeper, Kyverno) layered on top if an organization genuinely needs it.
_What the interviewer is probing for:_ Understanding of the actual historical motivation behind PSP's removal and the deliberate simplicity-for-granularity trade-off PSA represents, not just "PSP was deprecated, PSA replaced it."

**🎯 Architect:** _"Design the Pod Security Standards rollout strategy for a 200-namespace cluster migrating off unrestricted PodSecurityPolicy-free defaults."_
**Model answer:** I'd start by applying `audit` and `warn` at `restricted` cluster-wide via a namespace-labeling GitOps policy (§88), with `enforce` initially left at `baseline` as a hard floor everywhere except explicitly exempted system namespaces (`kube-system` and any legitimately privileged infrastructure namespaces). I'd mine the resulting audit logs (§96, Part 12) over a full workload cycle — covering CronJobs and any infrequent batch workloads, not just always-on Deployments — to build a per-namespace inventory of exactly which Restricted-tier violations exist. For namespaces with zero violations, I'd flip `enforce` to `restricted` immediately; for the remainder, I'd work with owning teams on a per-namespace remediation backlog (typically SecurityContext fixes from §45, or in the worst case an image rebuild to drop a root-user default), tracked with a target enforcement date. Throughout, RBAC (§75) would restrict who can edit `pod-security.kubernetes.io/*` labels to the platform team, so the migration's progress can't be silently undone by an individual team relabeling their own namespace back to a looser tier. Finally, for anything Restricted can't express — mandatory labeling, registry allowlisting, image signature verification (§118, Part 15) — I'd layer OPA Gatekeeper or Kyverno on top rather than trying to stretch PSA beyond its designed scope.
_What the interviewer is probing for:_ Ability to design a large-scale, staged, observable rollout using PSA's native audit/warn/enforce mechanism, awareness of RBAC as part of the actual policy boundary, and correct scoping of what PSA can and cannot express relative to a full policy engine.

## 12. Common Misconceptions

1. **"PodSecurityPolicy is still the current mechanism for this."** PSP was deprecated in v1.21 and fully removed in v1.25; Pod Security Admission, configured via namespace labels, is the current built-in replacement.
2. **"Labeling a namespace with a stricter `enforce` level retroactively re-evaluates already-running Pods."** It does not — PSA only evaluates at admission time; existing Pods are unaffected until their next create/update event.
3. **"Restricted and Baseline are unrelated, alternate policy sets."** They're strictly ordered — Restricted is a superset of Baseline's constraints plus additional hardening, not a separate checklist.
4. **"PSA alone is sufficient organizational security policy."** It enforces only its three fixed tiers; requirements like mandatory labeling or image provenance checks still require a policy engine layered on top.

## 13. 🔑 Key Takeaways

- Pod Security Standards define three ordered tiers — Privileged, Baseline, Restricted — each a fixed SecurityContext (§45) checklist, with Restricted a strict superset of Baseline.
- Pod Security Admission is the built-in admission controller (§77's mechanism) enforcing these tiers, configured entirely via namespace labels, with no webhook or CRD required.
- The independent `enforce`/`audit`/`warn` modes provide a native, zero-infrastructure staged rollout path from observation to enforcement.
- PSA replaced the deprecated-and-removed PodSecurityPolicy, trading PSP's fine-grained per-workload exemptions for namespace-label simplicity and auditability.
- PSA covers only its three fixed tiers — organization-specific policy beyond that scope still requires a policy engine (OPA Gatekeeper, Kyverno) built on the webhook mechanism from §77.

## 14. Related Concepts & What's Next

This section built directly on §77's admission controller mechanism (PSA is a built-in admission controller using exactly that pipeline stage) and §45's SecurityContext fields (Part 6), which are precisely what each Pod Security Standard tier checks against. §79, next, returns to NetworkPolicy (§55, Part 7) through a security lens — while PSA governs what a Pod's own spec is allowed to declare, NetworkPolicy governs what that Pod is allowed to talk to over the network, a complementary and equally essential security boundary PSA does not itself address.

**Next Section:** §79 — `Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md`
