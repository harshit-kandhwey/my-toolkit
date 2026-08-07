# Section 41 (Part 6): ConfigMaps: Creation and Consumption (env vars, volume mounts, command-line args)

## 1. Definition

**Plain language:** Application code shouldn't have database hostnames, feature flags, or log levels baked into its container image — otherwise every environment (dev, staging, production) needs its own rebuilt image just to change a setting. A ConfigMap is Kubernetes' answer: a small, separately-managed bucket of configuration data that gets attached to a Pod at runtime, so the same image can run anywhere with different config.

**Precise definition:** A **ConfigMap** is a non-secret, namespaced Kubernetes API object that stores configuration data as a set of **key-value pairs**, where values can be short strings or entire file contents (via the `data` field for UTF-8 text, or `binaryData` for base64-encoded binary content). A ConfigMap is not itself consumed directly by a container process — it is injected into a Pod through one of three mechanisms: as individual **environment variables**, as a full environment variable set via `envFrom`, as **mounted files** in a volume, or as **command-line arguments** via environment variable substitution. ConfigMaps hold no confidentiality guarantees whatsoever — they are stored and transmitted identically to any other API object, which is precisely why Secrets ([§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)) exist as a parallel, distinct object type for sensitive values.

## 2. Why This Matters

- **Decoupling configuration from the container image is the single biggest reason ConfigMaps exist.** The full Pod spec anatomy covered in [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) shows `envFrom` and `configMap` volume references directly inside `spec.containers` — this section expands on exactly how those fields work end to end.
- **ConfigMap changes propagate differently depending on consumption method, which is a frequent source of confusion.** Volume-mounted ConfigMaps update in place (with a propagation delay) when the source object changes, while environment-variable-injected values are frozen at container start — understanding this distinction prevents "I updated the ConfigMap but nothing changed" incidents.
- **Every multi-environment deployment pattern in this roadmap builds on ConfigMaps as the primary customization lever.** Namespaces as an isolation boundary and Kustomize overlays ([§47](./Section-47-Part6-Multi-Environment-Configuration-Patterns.md)) both frequently vary nothing but the ConfigMap contents between environments, leaving the rest of the manifest untouched.

🔑 **Key Takeaway:** A ConfigMap decouples configuration from the container image through three consumption patterns — environment variables, `envFrom`, and volume mounts — each with different update-propagation behavior, and none of which provide any confidentiality (that's what Secrets, [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md), are for).

## 3. Prerequisites and Dependencies

Builds on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (full Pod spec anatomy, where ConfigMap references first appear structurally inside `env`, `envFrom`, and `volumes`) and assumes familiarity with basic `kubectl apply` workflows from Part 4.

## 4. Architecture: How a ConfigMap Reaches a Running Container

```text
   ┌───────────────────────────┐
   │      ConfigMap            │
   │  (etcd-stored API object) │
   │  data:                    │
   │    LOG_LEVEL: "info"      │
   │    app.properties: |      │
   │      db.host=db-svc       │
   │      db.port=5432         │
   └───────────────┬───────────┘
                   │
   ┌───────────────┼───────────────────────┐
   ▼               ▼                       ▼
┌─────────┐ ┌──────────────┐    ┌────────────────────┐
│ env:    │ │ envFrom:     │    │ volumes:           │
│ single  │ │ ALL keys →   │    │ each key → one FILE│
│ key →   │ │ env vars     │    │ inside a mounted   │
│ one var │ │ (bulk import)│    │ directory          │
└────┬────┘ └──────┬───────┘    └──────────┬─────────┘
     │             │                       │
     ▼             ▼                       ▼
  Container process environment      /etc/config/LOG_LEVEL
  (frozen at container start)        /etc/config/app.properties
                                     (updates propagate ~minutes
                                     later via kubelet sync,
                                     env vars do NOT update)
```

- **`env` with `configMapKeyRef`** pulls exactly one named key into exactly one named environment variable — the most explicit, least "magic" option.
- **`envFrom` with `configMapRef`** bulk-imports every key in the ConfigMap as an environment variable of the same name — convenient, but any key with an invalid environment variable name (containing dots, for instance) is silently skipped, not an error.
- **Volume mounts** turn every key into a file inside the mount path, named after the key, containing the value as file content — the only pattern that supports live updates to a running container without a restart.

## 5. Hands-On: The Three Consumption Patterns

### 5.1 Creating ConfigMaps: Imperative and Declarative

**Purpose:** Show both the fast imperative path (useful for ad-hoc or exam-speed work) and the declarative YAML path (the production standard, since it's version-controlled).

**Syntax:**

```bash
# Imperative, from literal values
kubectl create configmap app-config \
  --from-literal=LOG_LEVEL=info \
  --from-literal=MAX_CONNECTIONS=100

# Imperative, from a file (key becomes the filename)
kubectl create configmap app-properties \
  --from-file=app.properties
```

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: production
data:
  LOG_LEVEL: "info"
  MAX_CONNECTIONS: "100"
  app.properties: |
    db.host=db-service
    db.port=5432
    cache.enabled=true
```

**Example usage and expected output:**

```bash
$ kubectl apply -f app-config.yaml
configmap/app-config created

$ kubectl get configmap app-config -o yaml | head -8
apiVersion: v1
data:
  LOG_LEVEL: "info"
  MAX_CONNECTIONS: "100"
  app.properties: |
    db.host=db-service
    db.port=5432
kind: ConfigMap
```

**Production usage example:** Production teams almost always author ConfigMaps declaratively and check them into the same Git repository as the Deployment manifest, so a config change and a code change that depends on it can be reviewed and rolled out together.

**Common errors:** Values in `data` are always strings — writing `MAX_CONNECTIONS: 100` (unquoted) as YAML technically parses as an integer type internally, which the API server coerces, but explicitly quoting numeric-looking values avoids ambiguity and is the safer convention.

### 5.2 Consuming as Environment Variables (`env` and `envFrom`)

**Purpose:** Inject specific keys individually, or an entire ConfigMap's keys in bulk, as environment variables visible to the container process.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: config-consumer
spec:
  containers:
    - name: app
      image: myregistry.example.com/app:2.1.0
      env:
        - name: LOG_LEVEL # explicit single-key injection
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: LOG_LEVEL
      envFrom:
        - configMapRef: # bulk import every key
            name: app-config
```

**Example usage and expected output:**

```bash
$ kubectl exec config-consumer -- env | grep -E 'LOG_LEVEL|MAX_CONNECTIONS'
LOG_LEVEL=info
MAX_CONNECTIONS=100
```

**Production usage example:** `envFrom` is common for services with dozens of tunable settings (feature flags, timeouts) where explicitly listing every key under `env` would be unwieldy; `env` with `configMapKeyRef` is preferred when only one or two specific values matter and explicitness in the manifest aids readability during review.

**Common errors:** Editing the source ConfigMap after the Pod is running has **no effect** on already-injected environment variables — they were resolved once at container start; the Pod must be recreated (typically via a Deployment rollout) to pick up new values, a very common point of confusion covered further in [§44](./Section-44-Part6-Environment-Variable-Injection-Precedence-Rules.md).

### 5.3 Consuming as a Mounted Volume

**Purpose:** Expose every key in a ConfigMap as a file inside a directory in the container's filesystem — the pattern that supports live updates.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: config-volume-consumer
spec:
  containers:
    - name: app
      image: myregistry.example.com/app:2.1.0
      volumeMounts:
        - name: config-vol
          mountPath: /etc/config
          readOnly: true
  volumes:
    - name: config-vol
      configMap:
        name: app-config
        items: # optional: project only specific keys
          - key: app.properties
            path: app.properties
```

**Example usage and expected output:**

```bash
$ kubectl exec config-volume-consumer -- cat /etc/config/app.properties
db.host=db-service
db.port=5432
cache.enabled=true

$ kubectl exec config-volume-consumer -- ls /etc/config
app.properties
```

**Production usage example:** Applications that support hot-reloading their configuration file (checking for file changes on an interval or via `inotify`) benefit directly from this pattern — updating the ConfigMap and re-applying it propagates to the mounted file within roughly a minute (kubelet's sync period) without any Pod restart, unlike environment variable injection.

**Common errors:** Mounting a ConfigMap volume at a path that already contains files from the container image **replaces the entire directory contents** with only the ConfigMap's keys unless `subPath` is used to mount a single file into an existing directory — a common mistake that silently deletes expected files from the image.

## 6. Production Usage Notes

- ConfigMaps have a **1 MiB size limit** (etcd's default object size ceiling) — large configuration files should be split across multiple ConfigMaps or reconsidered as an external configuration service rather than forced into a single object.
- Combining `immutable: true` on a ConfigMap (a field available since Kubernetes 1.19+) prevents accidental edits and improves api-server performance by letting it skip watching that object for changes — recommended for ConfigMaps that are meant to be replaced wholesale (new name, new rollout) rather than edited in place.
- Because Deployment rollouts don't automatically restart Pods on a referenced ConfigMap change ([§44](./Section-44-Part6-Environment-Variable-Injection-Precedence-Rules.md) covers this precedence and refresh behavior in depth), many teams embed a hash of the ConfigMap's contents into a Pod template annotation specifically to force a rollout whenever the config changes.

## 7. Security Considerations

- ConfigMaps are **not encrypted at rest by any special mechanism** beyond whatever applies to etcd generally ([§43](./Section-43-Part6-Encrypting-Secrets-At-Rest-EncryptionConfiguration.md)) and are readable by anyone with `get`/`list` RBAC permission on ConfigMaps in that namespace — never place sensitive values here, even "just for now."
- `kubectl describe pod` and `kubectl get pod -o yaml` both reveal environment variables sourced from ConfigMaps in plaintext to anyone with Pod read access, reinforcing that ConfigMaps are for non-sensitive settings only.
- Volume-mounted ConfigMap files inherit permissive default file permissions (`0644`) unless `defaultMode` is explicitly set on the volume — for hardened Pod Security Standard compliance ([§45](./Section-45-Part6-SecurityContext-Pod-Container-Level.md), [§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)) it's worth setting this explicitly even for non-secret data.

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                                    | Resolution Path                                                                                      |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Pod stuck `CreateContainerConfigError`                            | Referenced ConfigMap (or a specific key within it) doesn't exist                | `kubectl describe pod`, verify ConfigMap name/key spelling with `kubectl get configmap -o yaml`      |
| Updated ConfigMap but app still uses old values                   | Env-var-based consumption doesn't hot-reload; volume mounts lag by up to ~1 min | Restart the Pod (rollout) for env vars; wait for kubelet sync or check mount propagation for volumes |
| Volume mount hides files that should exist in the container image | Mounting a ConfigMap volume directly over an existing directory                 | Use `subPath` to mount individual files instead of the whole directory                               |

## 9. Best Practices

- Prefer volume mounts for configuration that might change without a full redeploy, and environment variables for values that are genuinely static per-release.
- Use `immutable: true` on ConfigMaps that shouldn't be edited in place, and adopt a naming convention (suffixing with a content hash or version) to force clean rollouts on change.
- Keep ConfigMap manifests in the same Git repository and review process as the workloads that consume them, so config and code changes are reviewed together.

## 10. Common Anti-Patterns / Mistakes

- **Storing secrets inside a ConfigMap** "temporarily" — there is no confidentiality boundary here at all; use a Secret ([§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)) even for values that feel low-risk.
- **Assuming an `envFrom` update automatically refreshes a running Pod's environment** — it does not; only a new Pod (via rollout) picks up the new values.
- **Mounting a ConfigMap over an existing directory without `subPath`**, unintentionally deleting expected files baked into the container image.

## 11. Interview Questions

**🎯 Beginner:** _"What is a ConfigMap, and what are the three ways a container can consume one?"_
**Model answer:** A ConfigMap is a Kubernetes object that stores non-sensitive configuration as key-value pairs, kept separate from the container image so the same image can be configured differently across environments. A container can consume it as individual environment variables via `env.valueFrom.configMapKeyRef`, as a bulk set of environment variables via `envFrom.configMapRef`, or as mounted files in a volume where each key becomes a filename and its value becomes the file's content.
_What the interviewer is probing for:_ Baseline familiarity with the object and all three consumption mechanisms, not just one.

**🎯 Intermediate:** _"A team updated a ConfigMap and expected their running Pods to pick up the change immediately, but nothing happened. What's going on?"_
**Model answer:** It depends on how the ConfigMap is consumed. If it's injected as environment variables (either `env` or `envFrom`), those values are resolved once when the container starts and are never re-read afterward — updating the source ConfigMap has zero effect on already-running containers; only a new Pod (typically via a Deployment rollout) picks up the change. If instead the ConfigMap is mounted as a volume, the kubelet does periodically sync updated ConfigMap content to the mounted files in the running Pod, typically within about a minute, without requiring a restart — but the application itself still needs to notice the file changed (e.g., via polling or `inotify`) to actually act on it.
_What the interviewer is probing for:_ Understanding that consumption method fundamentally changes update-propagation behavior, a frequent real-world confusion point.

**🎯 Senior:** _"How would you force a Deployment's Pods to roll out automatically whenever a referenced ConfigMap changes, given that Kubernetes doesn't do this by itself?"_
**Model answer:** Kubernetes deliberately doesn't restart Pods on ConfigMap changes because it has no way to know whether a given config change is safe to apply live. The standard pattern is to compute a hash of the ConfigMap's contents (many teams use a templating tool or a Helm chart helper for this) and inject that hash as a Pod template annotation on the Deployment — since the Pod template's checksum then changes whenever the ConfigMap's content changes, the Deployment controller detects a template diff and performs a normal rolling update, even though the ConfigMap reference itself didn't change. Alternatively, tools like Reloader or Kustomize's ConfigMap generator (which appends a content hash directly to the ConfigMap's name) achieve the same effect by treating each distinct config version as an entirely new object.
_What the interviewer is probing for:_ Practical experience with a real gap in Kubernetes' native behavior and the common workarounds used in production.

**🎯 Architect:** _"You're designing the configuration strategy for a platform serving dozens of teams' microservices across dev/staging/production. How would you structure ConfigMap usage to avoid drift and sprawl?"_
**Model answer:** I'd standardize on Kustomize overlays ([§47](./Section-47-Part6-Multi-Environment-Configuration-Patterns.md)) with a common base ConfigMap per service and per-environment patches only for values that genuinely differ, rather than letting each team hand-author near-duplicate ConfigMaps per environment. I'd enforce `immutable: true` combined with a content-hash suffix in the ConfigMap name for anything beyond the most trivial toggle, so every config version is a distinct, auditable object rather than an object silently mutated in place, and pair that with automatic Pod template hash injection so rollouts happen deterministically on config change. I'd also draw a hard line in tooling/policy (via an admission policy or CI lint) that nothing resembling a credential, token, or connection string with embedded auth ever lands in a ConfigMap — that boundary needs to be enforced structurally, not left to individual team discipline, given how easy it is to blur the line under deadline pressure.
_What the interviewer is probing for:_ Ability to think about ConfigMap usage as a platform-governance problem — consistency, auditability, and enforcement — not just single-Pod mechanics.

## 12. Common Misconceptions

1. **"ConfigMaps and Secrets are basically the same thing, just named differently."** ConfigMaps provide zero confidentiality; Secrets ([§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)) are a distinct object type specifically because sensitive data needs different handling, even though the API mechanics look superficially similar.
2. **"Updating a ConfigMap immediately updates every Pod using it."** Only volume-mounted consumption updates live (with a propagation delay); environment-variable-based consumption is frozen at container start.
3. **"Mounting a ConfigMap as a volume merges its files into whatever's already in that directory."** Without `subPath`, mounting a ConfigMap volume replaces the entire target directory's contents with only the ConfigMap's keys.

## 13. 🔑 Key Takeaways

- A ConfigMap stores non-sensitive key-value configuration data, decoupled from the container image, consumed via `env`, `envFrom`, or a volume mount.
- Environment-variable consumption is resolved once at container start and never updates live; volume-mounted consumption updates within roughly a minute of a ConfigMap change.
- ConfigMaps carry no confidentiality guarantee whatsoever — Secrets ([§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)) exist precisely because ConfigMaps are unsuitable for sensitive values.
- Forcing a rollout on ConfigMap change (via content-hash annotations or tooling like Reloader) is a standard production pattern, not a native Kubernetes behavior.
- A 1 MiB size ceiling and `subPath` mount semantics are two practical constraints worth knowing before designing a configuration strategy around ConfigMaps.

## 14. Related Concepts & What's Next

This section built on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)'s Pod spec anatomy, where `env`, `envFrom`, and `configMap` volumes first appeared structurally. [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md), immediately next, covers Secrets — the parallel object type for sensitive values, sharing much of the same consumption mechanics shown here but with critical differences around encoding and confidentiality. [§44](./Section-44-Part6-Environment-Variable-Injection-Precedence-Rules.md) returns to environment variable precedence when multiple sources define the same variable name, and [§47](./Section-47-Part6-Multi-Environment-Configuration-Patterns.md) covers Kustomize overlays as the standard way to vary ConfigMap contents across environments.

**Next Section:** [§42](./Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md) — `Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md`
