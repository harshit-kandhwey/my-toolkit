# Section 11 (Part 2): API Server Deep Dive: API Groups, Versioning, the Request Lifecycle and Admission Chain

## 1. Definition

**Plain language:** Every single thing you do in Kubernetes — creating a Deployment, reading a Secret, scaling a ReplicaSet — is really just an HTTP request to one web API, structured the same predictable way every time. Understanding that structure demystifies almost everything that feels "magic" about how `kubectl` works.

**Precise definition:** The **kube-apiserver** exposes a versioned, RESTful HTTP API organized into **API groups** (e.g., the core/legacy group, `apps`, `batch`, `networking.k8s.io`), each with independently evolving **API versions** (alpha → beta → stable, e.g., `v1alpha1` → `v1beta1` → `v1`). Every request that reaches the api-server passes through a defined **request lifecycle**: authentication, authorization, and a chain of **admission controllers** (mutating, then validating) before the object is persisted to etcd — the same pipeline described conceptually in §8, now covered at the mechanical level that CKA and CKS both test directly.

## 2. Why This Matters

- **Every manifest's `apiVersion` field is a direct reference to this system.** `apiVersion: apps/v1` means "the `apps` API group, version `v1`" — understanding groups and versioning turns a previously memorized string into something legible and predictable across new resource types.
- **The admission chain is where policy gets enforced, not just validated.** Features like Pod Security Admission (§79, Part 10), resource quota enforcement, and custom policy engines (OPA Gatekeeper, Kyverno) all plug into this chain — understanding exactly where admission sits in the request lifecycle is foundational to both CKA's architecture domain and CKS's cluster-hardening domain.
- **API deprecation and version graduation directly affects upgrade planning.** A manifest using a `v1beta1` API that later gets removed will break on upgrade if not updated — this is a very concrete, exam-relevant, and real-production consequence of the versioning model covered here.

🔑 **Key Takeaway:** Every Kubernetes API resource lives in a group and a version, and every request to change cluster state passes through authentication, authorization, and a mutating-then-validating admission chain before ever reaching etcd — this pipeline is where nearly all of Kubernetes' extensibility and policy enforcement actually happens.

## 3. Prerequisites and Dependencies

Builds on §8 (kube-apiserver's role as the sole entry point). No new external prerequisites, though full authentication/authorization mechanics are covered in depth later (§73–§74, Part 10).

## 4. Architecture Diagram: The Full Request Lifecycle

```text
   kubectl / any client
          │
          ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                     kube-apiserver                           │
   │                                                              │
   │  1. AUTHENTICATION   — who are you? (cert, token, OIDC)      │
   │           │                                                  │
   │           ▼                                                  │
   │  2. AUTHORIZATION    — are you allowed to do this? (RBAC)    │
   │           │                                                  │
   │           ▼                                                  │
   │  3. ADMISSION CONTROL (MUTATING)  — can modify the request   │
   │           │            e.g., inject a sidecar, set defaults  │
   │           ▼                                                  │
   │  4. SCHEMA VALIDATION — does the object match its API schema?│
   │           │                                                  │
   │           ▼                                                  │
   │  5. ADMISSION CONTROL (VALIDATING) — can only accept/reject  │
   │           │            e.g., Pod Security Admission, quotas  │
   │           ▼                                                  │
   │  6. PERSISTED TO ETCD                                        │
   └──────────────────────────────────────────────────────────────┘
```

- **Mutating admission runs before validating admission, always.** This ordering is deliberate: any defaults or modifications injected by mutating webhooks must themselves still pass validation afterward — validating admission always sees the final, fully-mutated object.
- **A request rejected at any stage never proceeds further** — an authentication failure never reaches authorization; an authorization failure never reaches admission; a rejected admission never reaches etcd.

## 5. API Groups and Versioning

### 5.1 API Groups

**Purpose:** Organize Kubernetes' API surface into logical namespaces, allowing different parts of the API to evolve independently.

| Group                        | Example Resources                                  | Notes                                                     |
| ---------------------------- | -------------------------------------------------- | --------------------------------------------------------- |
| Core (legacy, unnamed group) | Pod, Service, ConfigMap, Secret, Namespace         | Referenced as just `v1` in `apiVersion` (no group prefix) |
| `apps`                       | Deployment, StatefulSet, DaemonSet, ReplicaSet     | The most commonly authored resources beyond core          |
| `batch`                      | Job, CronJob                                       |                                                           |
| `networking.k8s.io`          | Ingress, NetworkPolicy                             |                                                           |
| `rbac.authorization.k8s.io`  | Role, ClusterRole, RoleBinding, ClusterRoleBinding | Covered fully in Part 10 (§75)                            |
| `storage.k8s.io`             | StorageClass, VolumeAttachment                     | Covered fully in Part 8                                   |

### 5.2 API Versioning: Alpha → Beta → Stable

**Purpose:** Signal a feature's maturity and stability guarantees.

| Stage       | Naming Convention | Stability Guarantee                                                            |
| ----------- | ----------------- | ------------------------------------------------------------------------------ |
| Alpha       | `v1alpha1`        | May be buggy, disabled by default, can be dropped entirely without notice      |
| Beta        | `v1beta1`         | Well-tested, enabled by default, but the schema can still change before stable |
| Stable (GA) | `v1`              | Long-term supported; changes only via a new version, never breaking in place   |

**Production usage example:** A team writing manifests against a `v1beta1` API should expect that field names or defaults could still change before that resource graduates to `v1` — a real, recurring source of upgrade-time breakage that careful version tracking (§106, Part 14) is meant to catch ahead of time.

## 6. Hands-On: Exploring the API Surface Directly

### 6.1 `kubectl api-resources` — List Every Available Resource Type

**Purpose:** See every resource type the cluster's api-server currently supports, along with its group and whether it's namespaced.

**Syntax:**

```bash
kubectl api-resources
```

**Example usage and expected output:**

```bash
$ kubectl api-resources
NAME          SHORTNAMES   APIVERSION   NAMESPACED   KIND
pods          po           v1           true         Pod
deployments   deploy       apps/v1      true         Deployment
ingresses     ing          networking.k8s.io/v1   true   Ingress
```

**Production usage example:** This is the fastest way to discover the exact `apiVersion` a resource requires when writing a manifest from scratch, without needing to consult external documentation — especially useful for cluster-specific or custom resources (CRDs, §84, Part 11) not covered by generic tutorials.

### 6.2 `kubectl api-versions` — List Every Supported Group/Version Combination

**Syntax:**

```bash
kubectl api-versions
```

**Example usage and expected output:**

```bash
$ kubectl api-versions
apps/v1
batch/v1
networking.k8s.io/v1
v1
```

### 6.3 `kubectl explain` — Inspect a Resource's Full Schema

**Purpose:** Directly query the api-server's own schema documentation for any field on any resource — genuinely useful during manifest authoring, and a much faster reference than an external browser search.

**Syntax:**

```bash
kubectl explain deployment.spec.strategy
```

**Example usage and expected output:**

```bash
$ kubectl explain deployment.spec.strategy
KIND:     Deployment
VERSION:  apps/v1

FIELD:    strategy <DeploymentStrategy>

DESCRIPTION:
     The deployment strategy to use to replace existing pods with new ones.
```

**Production usage example:** During the CKA/CKAD/CKS exams specifically, `kubectl explain` is one of the very few permitted references beyond the official docs site — fast, offline, and always matches the exact API version the exam cluster is actually running, unlike a possibly-mismatched external tutorial.

## 7. Production Usage Notes: Where Admission Control Shows Up in Practice

- **Pod Security Admission** (§79, Part 10) is a built-in validating admission plugin enforcing Pod security standards per namespace — a direct, concrete instance of the validating-admission stage in this section's lifecycle diagram.
- **ResourceQuota and LimitRange enforcement** happens at admission time — a Pod exceeding a namespace's quota is rejected here, before ever being persisted, which is why quota violations appear as an immediate `kubectl apply` error rather than a delayed scheduling failure.
- **Custom policy engines (OPA Gatekeeper, Kyverno)** register as external validating (and sometimes mutating) admission webhooks — this is the exact mechanism that lets organizations enforce custom policy ("all Pods must have a `team` label," "no `:latest` image tags") without modifying Kubernetes' own code (§76, Part 10 covers admission webhooks in full).

## 8. Security Considerations

- The admission chain is a primary security enforcement point — misconfigured or missing admission control (e.g., no Pod Security Admission policy applied) is a common cluster-hardening gap directly tested in CKS (§113, Part 15).
- Authentication and authorization happen _before_ admission — meaning a request that fails RBAC never reaches admission-based policy checks at all; both layers matter independently and neither substitutes for the other.

## 9. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                               | Resolution Path                                                                            |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| `kubectl apply` rejected with an admission-related error      | A validating admission controller (quota, Pod Security, custom policy) rejected the object | Read the specific error message; it names which admission check failed (§76, Part 10)      |
| A manifest that worked on an old cluster fails on a newer one | The API version used has since been deprecated or removed after graduating                 | Check `kubectl api-versions` on the new cluster and update `apiVersion` accordingly (§106) |
| `kubectl explain` shows no result for a field from a tutorial | Tutorial targets a different API version than the cluster is running                       | Re-check the resource's current `apiVersion` via `kubectl api-resources`                   |

## 10. Best Practices

- Use `kubectl explain` and `kubectl api-resources` as first-line references during manifest authoring, since they always match the cluster's actual, current API surface.
- Track any `v1alpha1`/`v1beta1` API usage in manifests deliberately, since these are the ones most likely to require updates before a future cluster upgrade.
- When diagnosing a rejected `apply`, read the actual admission error message carefully — it identifies exactly which stage (quota, Pod Security, a specific webhook) rejected the request, rather than guessing.

## 11. Common Anti-Patterns / Mistakes

- **Treating all API versions as equally stable** — `v1beta1` resources can and do change before reaching `v1`, and manifests relying on them should be tracked for eventual migration.
- **Assuming a rejected `apply` is a syntax error** without reading whether it's actually an admission-policy rejection (quota, security policy, custom webhook) — these produce different error messages requiring different fixes.
- **Ignoring API deprecation warnings** until a cluster upgrade actually breaks, rather than proactively migrating manifests off soon-to-be-removed versions ahead of time.

## 12. Interview Questions

**🎯 Beginner:** _"What does `apiVersion: apps/v1` in a manifest actually mean?"_
**Model answer:** It specifies that the resource belongs to the `apps` API group, at version `v1` (stable/GA). Kubernetes organizes its API into groups so different parts of the API can evolve independently, and each group has its own versioning (alpha, beta, stable) reflecting how mature and stable that specific API is.
_What the interviewer is probing for:_ Basic literacy in reading and understanding the `apiVersion` field rather than treating it as a magic string to copy from examples.

**🎯 Intermediate:** _"Explain the order of the admission chain — why does mutating admission run before validating admission, and not the reverse?"_
**Model answer:** Mutating admission webhooks can modify the incoming object (injecting sidecars, setting defaults, adding labels), and validating admission needs to make its accept/reject decision against the _final_ version of the object, not an intermediate one — so mutation has to complete first. If validation ran first, a mutating webhook could still introduce a policy violation afterward that was never actually checked, defeating the purpose of validation as the last gate before persistence.
_What the interviewer is probing for:_ Real understanding of why this ordering is a deliberate design choice, not an arbitrary implementation detail.

**🎯 Senior:** _"A `kubectl apply` is failing with a rejection that doesn't look like a YAML syntax error. How would you determine exactly why it's being rejected?"_
**Model answer:** I'd read the full error message closely first — Kubernetes' admission rejections typically name the specific admission controller or webhook that rejected the request (e.g., a ResourceQuota exceeded message, a Pod Security Admission violation, or a named custom webhook like an OPA Gatekeeper constraint). If the message isn't immediately clear, I'd check `kubectl get events` in the relevant namespace and, for custom policy engines, look at the specific webhook's own logs, since third-party admission controllers often log more detail than what's surfaced directly in the `kubectl` error. The key is treating "rejected" and "syntax error" as different failure classes from the start, since the diagnostic path diverges immediately.
_What the interviewer is probing for:_ A structured approach to distinguishing schema/syntax failures from policy-driven admission rejections, which require entirely different fixes.

**🎯 Architect:** _"You're designing a policy-enforcement strategy for a multi-team Kubernetes platform — enforcing things like 'every Pod must have resource limits' and 'no privileged containers.' How does the admission chain shape your implementation approach?"_
**Model answer:** I'd implement this via validating admission webhooks (using a policy engine like OPA Gatekeeper or Kyverno) rather than trying to enforce these rules through documentation or code review alone, since admission control is the one enforcement point that applies uniformly and automatically to every request regardless of which team or tool submitted it — CI pipeline, `kubectl apply`, or a GitOps controller. I'd also consider whether some rules are better implemented as mutating admission (auto-injecting sensible resource-limit defaults rather than just rejecting Pods that lack them) versus purely validating (hard-rejecting privileged containers with no auto-fix), since the mutating-then-validating order lets me combine "fix it automatically where safe" with "hard block where it isn't." The core architectural insight is that admission control is the single choke point every request passes through, making it the right layer for organization-wide policy rather than relying on convention or manual review.
_What the interviewer is probing for:_ Whether the candidate understands admission control as the correct architectural layer for platform-wide policy enforcement, and can reason about mutating vs. validating admission's different roles.

## 13. Common Misconceptions

1. **"All Kubernetes APIs are equally stable once they exist."** Alpha and beta APIs can change or be removed before reaching stable (`v1`) — this is a real, documented risk for manifests relying on them.
2. **"Admission control is just extra validation, redundant with RBAC."** RBAC (authorization) answers "is this identity allowed to do this action at all"; admission control answers "does this specific object satisfy cluster policy" — they're different, complementary checks at different stages.
3. **"Validating and mutating admission run in no particular order."** Mutating admission always completes before validating admission runs, specifically so validation sees the final, fully-mutated object.

## 14. 🔑 Key Takeaways

- Every Kubernetes API resource belongs to a group (core, `apps`, `batch`, etc.) and a version (alpha/beta/stable) that evolves independently.
- Every request passes through authentication, authorization, mutating admission, schema validation, and validating admission — in that order — before being persisted to etcd.
- `kubectl api-resources`, `kubectl api-versions`, and `kubectl explain` are the fastest, most accurate references for a cluster's actual current API surface — genuinely useful both operationally and during exams.
- Admission control is where cluster-wide policy enforcement (quotas, Pod Security, custom policy engines) actually happens — understanding its position in the pipeline is essential for both troubleshooting rejections and designing platform policy.
- API version tracking (avoiding reliance on alpha/beta APIs where possible) is a real, concrete concern for smooth cluster upgrades.

## 15. Related Concepts & What's Next

§8 introduced kube-apiserver's role at a summary level; this section delivered its internal request-lifecycle mechanics in full. §73–§74 (Part 10) cover authentication and authorization — the first two stages of this section's lifecycle diagram — in complete depth. §76–§79 (Part 10) cover admission controllers, webhooks, and Pod Security Admission fully. §84 (Part 11) covers Custom Resource Definitions, which extend this same API-group-and-versioning model to user-defined resource types.

**Next Section:** §12 — `Section-12-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md`
