# Section 84 (Part 11): Kustomize: Bases, Overlays, Patches

## 1. Definition

**Plain language:** §82–§83 solved multi-environment configuration through templating — Go template logic embedded directly in YAML, driven by a values file. Kustomize solves the same problem a different way: start from plain, valid, unmodified Kubernetes YAML, and layer structural patches on top per environment, with no template syntax anywhere in any file.

**Precise definition:** **Kustomize** is a template-free configuration customization tool, built directly into `kubectl` since 1.14 (`kubectl apply -k`) and also available as a standalone binary. A **base** is a directory of plain Kubernetes manifests plus a `kustomization.yaml` file listing which resources belong to it. An **overlay** is a separate directory, also with its own `kustomization.yaml`, that references a base (via `resources:` pointing at the base directory) and layers environment-specific **patches** on top — using strategic merge patches, JSON 6902 patches, or convenience generators (`configMapGenerator`, `secretGenerator`, `images:`, `replicas:`) — without ever modifying the base files themselves. `kustomize build` (or `kubectl kustomize`) renders a base plus its overlay's patches into final, plain YAML ready to apply — conceptually parallel to `helm template`, but with structural patching instead of template substitution as the underlying mechanism.

## 2. Why This Matters

- **Kustomize requires zero new syntax inside the manifests themselves** — a base is just ordinary, valid Kubernetes YAML that could be `kubectl apply -f`'d directly on its own, which is a materially different mental model from Helm's Go-templated manifests (§83) and a common reason teams already comfortable with raw YAML (§32) reach for it first.
- **The base/overlay separation directly mirrors the dev/staging/production split every real deployment needs**, without requiring a values-file schema to be designed and maintained upfront the way a Helm chart's `values.yaml` does.
- **This section, together with §82–§83, gives §85's decision framework its second half** — Kustomize's patch-based, template-free model is the concrete alternative Helm's package/template/release model gets weighed against.

🔑 **Key Takeaway:** Kustomize customizes plain, un-templated Kubernetes YAML by layering an overlay's strategic-merge or JSON 6902 patches on top of a shared base, rendering final manifests via `kustomize build`/`kubectl apply -k` — achieving the same multi-environment goal as Helm (§82–§83) through structural patching rather than template logic, with no new syntax embedded in the manifests themselves.

## 3. Prerequisites and Dependencies

Builds directly on §83 (Writing Helm Charts) as the point of contrast — understanding Helm's templating approach makes Kustomize's patch-based alternative concrete rather than abstract. Also builds on §32 (YAML manifest authoring, Part 4), since a Kustomize base is exactly the kind of plain manifest that section covers, and on §30 (Labels, Selectors, Annotations, Part 4), since Kustomize's `commonLabels` and label-based patch targeting build directly on that mechanism.

## 4. Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────┐
│                              BASE                                      │
│   base/                                                                │
│     kustomization.yaml     resources: [deployment.yaml, service.yaml]  │
│     deployment.yaml         (plain, valid, un-templated YAML)          │
│     service.yaml                                                       │
└────────────────────────────────┬───────────────────────────────────────┘
                                 │ referenced via resources: [../../base]
                 ┌───────────────┼─────────────────────┐
                 ▼                                     ▼
┌───────────────────────────────┐    ┌───────────────────────────────────┐
│      overlays/staging/        │    │       overlays/production/        │
│  kustomization.yaml           │    │  kustomization.yaml               │
│    resources: [../../base]    │    │    resources: [../../base]        │
│    patches:                   │    │    patches:                       │
│      - replica-patch.yaml     │    │      - replica-patch.yaml         │
│    images:                    │    │    images:                        │
│      - name: myapp            │    │      - name: myapp                │
│        newTag: staging-abc123 │    │        newTag: v2.3.0             │
│    replicas:                  │    │    replicas:                      │
│      - name: myapp            │    │      - name: myapp                │
│        count: 2               │    │        count: 5                   │
└───────────────┬───────────────┘    └───────────────────┬───────────────┘
                │ kustomize build overlays/staging       │ kustomize build overlays/production
                ▼                                        ▼
        Rendered staging manifests                Rendered production manifests
        (base + staging patches merged)            (base + production patches merged)
```

- **The base is never edited per-environment** — every environment-specific change lives entirely in its own overlay directory, so the base remains a single, shared source of truth referenced (not copied) by every overlay.
- **`patches:` (strategic merge, matching by name/kind) and `patchesJson6902` (path-based JSON Patch operations) are the two patch mechanisms** — strategic merge is simpler for most field overrides, JSON 6902 is needed for array element manipulation or removing a field entirely.
- **Generators (`configMapGenerator`, `secretGenerator`) append a content hash to the generated object's name**, and Kustomize automatically updates every reference to that name elsewhere in the rendered output — this is what safely triggers a Pod rollout whenever a ConfigMap's content changes.

## 5. Hands-On

### 5.1 Defining a Base

**Purpose:** Show a minimal, valid base — plain manifests plus the `kustomization.yaml` that groups them.

**Syntax:**

```yaml
# base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
commonLabels:
  app.kubernetes.io/name: myapp
```

```yaml
# base/deployment.yaml (plain, un-templated, directly kubectl-apply-able on its own)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: myapp
  template:
    metadata:
      labels:
        app.kubernetes.io/name: myapp
    spec:
      containers:
        - name: myapp
          image: myapp:latest
```

**Production usage example:** Because a base is valid YAML with no template placeholders, any engineer can `kubectl apply -f base/deployment.yaml` directly during local development without involving Kustomize at all — a genuine advantage over a Helm chart's templates, which cannot be applied meaningfully without first being rendered through `helm template`.

**Common errors:** Forgetting to list a manifest file under `resources:` in `kustomization.yaml` — the file exists in the directory but Kustomize silently omits it from the rendered output, since only explicitly listed resources are included.

### 5.2 Building a Production Overlay with Patches

**Purpose:** Show a realistic overlay layering an image tag, replica count, and a resource-limit patch on top of the shared base.

```yaml
# overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base
namespace: production
images:
  - name: myapp
    newTag: "2.3.0"
replicas:
  - name: myapp
    count: 5
patches:
  - target:
      kind: Deployment
      name: myapp
    patch: |-
      - op: add
        path: /spec/template/spec/containers/0/resources
        value:
          requests: { cpu: "250m", memory: "256Mi" }
          limits: { cpu: "500m", memory: "512Mi" }
```

**Example usage and expected output:**

```bash
$ kustomize build overlays/production | kubectl apply -f -
deployment.apps/myapp created
service/myapp created

$ kustomize build overlays/production | grep -A2 "resources:"
          resources:
            requests: { cpu: "250m", memory: "256Mi" }
            limits: { cpu: "500m", memory: "512Mi" }
```

**Production usage example:** The exact same base renders differently for `overlays/staging` (lower replica count, a `-staging` image tag, no resource limits patch) purely from its own separate `kustomization.yaml` — no base file is ever touched or forked, so a fix to the shared Deployment structure in `base/deployment.yaml` automatically propagates to every overlay's next `kustomize build`.

**Common errors:** Using a strategic-merge `patches:` block to try to remove an array element or replace an entire list (rather than merge into it) — strategic merge patches merge object fields but don't cleanly express "delete this specific array entry"; a JSON 6902 `remove` operation (`patchesJson6902`) is the correct tool for that specific case.

### 5.3 ConfigMap and Secret Generators with Automatic Rollout

**Purpose:** Show Kustomize's generator mechanism and the hash-suffix behavior that safely triggers Pod rollouts on config changes.

```yaml
# overlays/production/kustomization.yaml (excerpt)
configMapGenerator:
  - name: app-config
    literals:
      - LOG_LEVEL=info
      - FEATURE_FLAG_X=enabled
```

```bash
$ kustomize build overlays/production | grep -A3 "kind: ConfigMap"
kind: ConfigMap
metadata:
  name: app-config-8f92kg4d6t   # content-hash suffix appended automatically

$ kustomize build overlays/production | grep "app-config"
      - configMapRef:
          name: app-config-8f92kg4d6t   # every reference updated to match
```

**Production usage example:** Because the generated ConfigMap's name changes whenever its content changes, a Deployment referencing it via `envFrom`/`volumes` is forced into a new Pod template hash on every `kubectl apply` of an updated overlay — triggering a rolling update automatically, solving the classic problem (also relevant to §41, Part 6) of Pods not picking up a ConfigMap change without a manual restart.

**Common errors:** Manually hardcoding a ConfigMap name in a Deployment that Kustomize also generates via `configMapGenerator` — Kustomize only rewrites references it can find and match automatically within the same `kustomize build` output; a name referenced through an external, non-Kustomize-managed mechanism won't be updated and will silently point at a stale or nonexistent object.

## 6. Production Usage Notes

- **`kubectl apply -k <overlay-dir>` and `kustomize build <overlay-dir> | kubectl apply -f -` are functionally equivalent** for straightforward cases, but the standalone `kustomize` binary is typically ahead of the version vendored into `kubectl`, so CI pipelines commonly use the standalone binary directly for access to newer features.
- **Kustomize has no release/revision-history concept at all**, unlike Helm (§82) — rollback in a Kustomize-driven workflow means reverting the overlay/base YAML in Git and reapplying, relying entirely on Git history and the GitOps controller's own reconciliation (§88) rather than any Kustomize-native mechanism.
- **Component reuse across many overlays is handled via `components:`** (a Kustomize feature for composing optional, reusable patch sets across multiple overlays), letting a cross-cutting concern (e.g., a common monitoring sidecar patch) be defined once and included by any overlay that needs it, without duplicating the patch YAML per overlay.

## 7. Security Considerations

- **`secretGenerator` writes generated Secret content directly into the rendered manifest output** — the same plaintext-in-Git risk as a Helm `values.yaml` carrying secrets applies equally here; pair with a secrets-management integration (§80, Part 10) rather than committing literal secret values into any `kustomization.yaml`.
- **Overlay patches can just as easily modify RBAC or SecurityContext fields as any other field** — an overlay that patches `securityContext.privileged: true` for a "quick debugging fix" in one overlay is exactly the kind of drift that a base's intended security posture (§45, Part 6) can be silently undone by, and deserves the same review scrutiny as the base itself.
- **`namespace:` set at the overlay level determines where every resource in the rendered output lands** — a misconfigured or incorrect `namespace:` field in a production overlay's `kustomization.yaml` can misdirect an entire application's resources into the wrong namespace, potentially bypassing the RBAC and NetworkPolicy boundaries (§74, §79, Part 10) intended for that workload.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                       | Cause                                                                                      | Fix                                                                                                        |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| A manifest file in the base directory is missing from rendered output         | The file wasn't listed under `resources:` in that directory's `kustomization.yaml`         | Add the file explicitly to `resources:` — Kustomize only includes explicitly listed files                  |
| A Pod doesn't pick up a ConfigMap content change after `apply`                | The ConfigMap name is hardcoded rather than generated via `configMapGenerator`             | Use `configMapGenerator` so the name-hash changes on content change, forcing a Pod template update         |
| Strategic merge patch fails to remove or reorder a list element               | Strategic merge only merges object fields; it can't express array-element deletion cleanly | Use `patchesJson6902` with an explicit `remove`/`replace` operation targeting the array index by JSON path |
| `kubectl apply -k` behaves differently than the standalone `kustomize` binary | The `kubectl`-vendored Kustomize version lags behind the standalone binary's release       | Use the standalone `kustomize build \| kubectl apply -f -` in CI for consistent, up-to-date behavior       |

## 9. Best Practices

- Keep bases free of any environment-specific value — every difference between dev, staging, and production belongs in an overlay's patches, never in the base itself.
- Use `configMapGenerator`/`secretGenerator` instead of hand-written, statically named ConfigMaps/Secrets, to get automatic rollout-triggering on content change.
- Reach for `patchesJson6902` specifically when a strategic merge patch can't express the needed change (array element removal/reordering); don't force strategic merge into cases it wasn't designed for.
- Run `kustomize build <overlay>` locally (or in CI, piped into a linter like kube-linter, §116) before every apply, mirroring the validate-before-apply discipline from §32.

## 10. Common Anti-Patterns / Mistakes

- **Letting environment-specific values leak into the base** (a hardcoded production image tag, for instance), defeating the entire base/overlay separation and forcing overlays to patch around a base that was never truly environment-neutral.
- **Hardcoding a ConfigMap/Secret name that's also managed by a generator**, breaking Kustomize's automatic reference-rewriting and leaving Pods referencing a stale or nonexistent object name.
- **Reaching for a full strategic-merge patch file to change a single scalar field** (a replica count, an image tag) when the dedicated `replicas:`/`images:` convenience fields in `kustomization.yaml` already express exactly that, more concisely and readably.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a Kustomize base and an overlay?"_
**Model answer:** A base is a directory of plain, valid Kubernetes manifests plus a `kustomization.yaml` listing which files belong to it — it's environment-neutral and could be applied directly with `kubectl apply -f` on its own. An overlay is a separate directory with its own `kustomization.yaml` that references a base via `resources:` and layers environment-specific changes on top — image tags, replica counts, resource limits — using patches or convenience generators, without ever modifying the base's files directly. Multiple overlays (staging, production) typically point at the same shared base.
_What the interviewer is probing for:_ Basic grasp of the reference-not-copy relationship between overlay and base, and that the base itself stays environment-neutral.

**🎯 Intermediate:** _"When would you use `patchesJson6902` instead of a strategic merge patch in Kustomize?"_
**Model answer:** Strategic merge patches work well for merging object fields — setting or overriding a scalar or nested map value — but they can't cleanly express operations like removing a specific array element, reordering a list, or replacing an entire field wholesale rather than merging into it. `patchesJson6902` uses RFC 6902 JSON Patch operations (`add`, `remove`, `replace`, addressed by exact JSON path) which can express any of those precisely. In practice, I default to strategic merge or the convenience fields (`images:`, `replicas:`) for straightforward field overrides, and reach for `patchesJson6902` specifically when I need to delete or reorder something inside an array, which strategic merge has no clean way to express.
_What the interviewer is probing for:_ Understanding that the two patch mechanisms aren't interchangeable and knowing the specific class of change (array manipulation) that requires JSON 6902.

**🎯 Senior:** _"A team's Pods aren't restarting after a ConfigMap change applied through Kustomize. What's the likely cause and fix?"_
**Model answer:** The most likely cause is that the ConfigMap in question was authored as a plain, statically named manifest rather than through `configMapGenerator` — Kustomize's generator mechanism is specifically what appends a content-hash suffix to the generated object's name and rewrites every reference to it within the same build, and it's that name change which forces a new Pod template hash and triggers a rollout. A statically named ConfigMap, by contrast, keeps the exact same name across every `apply`, so Kubernetes has no signal that anything changed from the Deployment's perspective — the ConfigMap's contents get updated in place, but any Pod that already mounted or loaded it doesn't automatically restart. The fix is migrating that ConfigMap definition to `configMapGenerator` in the relevant `kustomization.yaml`, letting Kustomize's own reference-rewriting handle the rollout trigger rather than relying on a separate, manual restart mechanism.
_What the interviewer is probing for:_ Concrete knowledge of exactly why the generator + hash-suffix mechanism exists, tying it to a real, commonly hit operational symptom rather than reciting the feature abstractly.

**🎯 Architect:** _"Design a Kustomize base/overlay structure for an application deployed across dev, staging, and three regional production clusters, each needing slightly different resource limits and replica counts."_
**Model answer:** I'd keep a single, environment-neutral `base/` holding the Deployment, Service, and any other core objects with no environment-specific values baked in at all, and structure overlays hierarchically: a `overlays/production-base/` layer capturing what's common across all three regional production clusters (shared resource-limit floor, shared labels, shared NetworkPolicy references from §79), which each region-specific overlay (`overlays/production-us-east/`, `-eu-west/`, `-ap-south/`) then itself references as its own `resources:` entry, adding only its region-specific replica count and any region-specific image registry mirror via `images:`. This avoids duplicating the shared production configuration three times while still letting each region diverge on the handful of fields that genuinely differ. I'd use `components:` for any genuinely cross-cutting, optional concern (a debug-sidecar patch used only in dev, for instance) so it's defined once and opted into by whichever overlays need it. CI would run `kustomize build` for every overlay on every PR, piping output into a policy/schema linter (§116) as a required check, and actual application to each cluster would flow through a GitOps controller (§88) reconciling each overlay against its target cluster — keeping the human-reviewed diff, not a manually run `kubectl apply -k`, as the actual point of production change.
_What the interviewer is probing for:_ Ability to design a multi-layer overlay hierarchy that avoids duplicating shared configuration across many similar environments, plus integration with CI/CD and GitOps rather than treating Kustomize as a purely local, manually-run tool.

## 12. Common Misconceptions

1. **"Kustomize bases and overlays require some kind of templating syntax, like Helm."** They don't — every file in a base or overlay is plain, valid Kubernetes YAML; customization happens entirely through separate patch and generator directives in `kustomization.yaml`, never through in-manifest template placeholders.
2. **"An overlay copies and modifies the base's files."** It references the base directory via `resources:` and layers patches on top at build time — the base's actual files are never copied or edited by any overlay.
3. **"A hardcoded ConfigMap name works the same as one from `configMapGenerator`."** Only the generator's content-hash suffix and automatic reference-rewriting mechanism triggers a Pod rollout on content change; a statically named ConfigMap updates in place with no rollout signal.
4. **"Kustomize has release/rollback history like Helm."** It doesn't — there's no release object or revision tracking at all; reverting a Kustomize-driven deployment means reverting the tracked YAML in Git and reapplying.

## 13. 🔑 Key Takeaways

- A base is plain, environment-neutral Kubernetes YAML; overlays reference it and layer environment-specific patches/generators on top without ever modifying the base directly.
- Strategic merge patches handle most field overrides; `patchesJson6902` is required specifically for array element removal/reordering that strategic merge can't express.
- `configMapGenerator`/`secretGenerator` append a content-hash suffix and rewrite every reference automatically, which is what actually triggers a Pod rollout on config content changes — a statically named ConfigMap does not.
- Kustomize has no release/revision-history concept at all, unlike Helm (§82) — rollback relies entirely on Git history and reapplication.
- `kubectl apply -k` uses a vendored Kustomize version that can lag the standalone binary; CI pipelines commonly prefer the standalone `kustomize build | kubectl apply -f -` for the newest features.

## 14. Related Concepts & What's Next

This section built on §83's templating model by contrast, showing how Kustomize achieves the same multi-environment customization goal through structural, patch-based overlays on plain YAML rather than embedded Go template logic — and referenced §32's manifest-authoring baseline, §30's label/selector mechanics, and §41 (Part 6)'s ConfigMap rollout problem that generators solve automatically. §85, next, synthesizes §82 through this section into a concrete decision framework — when to reach for Helm, when Kustomize, and when raw manifests remain the right, sufficient choice.

**Next Section:** §85 — `Section-85-Part11-Helm-vs-Kustomize-vs-Raw-Manifests-Decision-Framework.md`
