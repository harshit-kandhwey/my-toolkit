# Section 135 (Part 17): CKAD-Style Scenario Question Bank

## 1. Definition

**Plain language:** Where §134 drilled cluster-operator problems — broken nodes, stuck PVCs, etcd — this section drills the application-developer's half of the exam world: building, configuring, deploying, and exposing an application correctly, fast, from the developer's seat rather than the administrator's.

**Precise definition:** This section is a **scenario question bank** modeled on the CKAD's actual performance-based task format, weighted toward its five official domains — Application Design and Build, Application Deployment, Observability and Maintenance, Application Environment/Configuration/Security, and Services and Networking. Each scenario states the exam-style prompt, a worked `kubectl`/YAML solution, and the specific developer-facing skill it validates.

## 2. Why This Matters

- **CKAD candidates are graded on developer-facing correctness, not cluster administration** — a perfectly reasonable admin instinct (e.g., "just add a toleration") is usually the wrong tool when the actual gap is a missing ConfigMap key or a misconfigured probe; this bank trains the developer-first diagnostic reflex.
- **ConfigMaps, Secrets, and probes appear in some form in nearly every CKAD task**, because "Application Environment, Configuration and Security" is a 25%-weighted domain on its own — the single highest weight of any CKAD domain — making fluency here worth more exam points than any other single skill.
- **Multi-container Pod patterns (sidecar, init container, ambassador) are tested as design decisions, not just syntax** — a scenario often asks you to solve a problem ("this app needs to wait for a dependency before starting") without naming the pattern, requiring you to recognize init containers are the answer rather than being told to use one.

🔑 **Key Takeaway:** CKAD scenarios reward recognizing which developer-facing primitive (ConfigMap vs. Secret, liveness vs. readiness probe, init container vs. sidecar) solves a described problem, more than they reward raw kubectl typing speed — read for the underlying need, not just the literal ask.

## 3. Prerequisites and Dependencies

Builds on §134 (this bank assumes the same context-switch and time-box discipline already drilled there) and draws its scenario content from Pods and multi-container patterns (§24–§25), Deployments (§27–§28), ConfigMaps and Secrets (§41–§42), SecurityContext (§45), probes (§89), and Services/Ingress (Part 7). Where §134 tested cluster-operator instincts, this section tests the developer-facing use of the same underlying Kubernetes API objects.

## 4. Architecture Diagram: Scenario Category Breakdown

```text
   CKAD Exam Domain Weight → This Question Bank's Scenario Mix

   App Environment/Config/Security (25%) ████████████████████████████  Scenario 2, 3
   Application Design and Build (20%)     ██████████████████████        Scenario 1, 5
   Application Deployment (20%)           ██████████████████████        Scenario 4
   Services and Networking (20%)          ██████████████████████        Scenario 6
   Observability and Maintenance (15%)    █████████████████               Scenario 3 (probe half), 7

   Developer-scenario decision flow:
   ┌──────────────────────────────────────────────────────────────┐
   │ What does the prompt actually need, not what it literally    │
   │ says?                                                        │
   │  "app needs credentials"        → Secret, not ConfigMap      │
   │  "app must wait for dependency" → init container             │
   │  "app must self-heal on hang"   → liveness probe             │
   │  "app must not receive traffic  │                            │
   │   until warmed up"              → readiness probe            │
   │  "expose HTTP app externally    │                            │
   │   with path-based routing"      → Ingress, not NodePort      │
   └──────────────────────────────────────────────────────────────┘
```

- **The exam frequently under-specifies which object type to use**, describing a need in plain language rather than naming ConfigMap/Secret/probe explicitly — recognizing the right primitive from the described symptom is itself a tested skill.
- **Services and Networking is weighted identically to Deployment and Design/Build (20% each)**, so CKAD candidates who only practice workload-creation scenarios are under-preparing for a fifth of the exam.

## 5. Hands-On: The Scenario Question Bank

### Scenario 1 — Multi-Container Pod With an Init Container Dependency Gate (6 minutes)

**Prompt as seen on exam:**

> Namespace `orders`. Create a Pod named `order-api` running image `myregistry/order-api:2.1` that must not start its main container until a `Service` named `inventory-db` is resolvable via DNS. Use an init container to enforce this.

**Solution:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-api
  namespace: orders
spec:
  initContainers:
    - name: wait-for-inventory-db
      image: busybox:1.36
      command:
        - sh
        - -c
        - "until nslookup inventory-db.orders.svc.cluster.local; do echo waiting; sleep 2; done"
  containers:
    - name: order-api
      image: myregistry/order-api:2.1
      ports:
        - containerPort: 8080
```

```bash
kubectl apply -f order-api.yaml
kubectl -n orders get pod order-api -w
```

**What it's testing:** Recognizing an init-container use case from a plain-language dependency description (§24–§25), and correct DNS-name construction (`<service>.<namespace>.svc.cluster.local`) rather than assuming same-namespace short names always resolve across contexts.

### Scenario 2 — Injecting a Secret as an Environment Variable Without Exposing It in Plaintext YAML (5 minutes)

**Prompt as seen on exam:**

> Namespace `payments`. A Deployment `billing` needs a database password available as environment variable `DB_PASSWORD`, sourced from a Secret key `password` in Secret `billing-db-creds` (already exists). Update the Deployment accordingly without hardcoding the password anywhere in your manifest.

**Solution:**

```bash
kubectl -n payments get secret billing-db-creds -o yaml
```

```yaml
# add under the container spec of the billing Deployment
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: billing-db-creds
        key: password
```

```bash
kubectl -n payments edit deployment billing
kubectl -n payments rollout status deployment billing
kubectl -n payments exec deploy/billing -- printenv DB_PASSWORD
```

**What it's testing:** `secretKeyRef` env injection syntax exactly (§42), and the discipline of never typing a decoded Secret value directly into a manifest even during troubleshooting — a habit the exam and real production security practice both reward identically.

### Scenario 3 — Fixing a Misconfigured Liveness Probe Causing Restart Loops (6 minutes)

**Prompt as seen on exam:**

> Namespace `web`. Pod `app-frontend` is repeatedly restarting. `kubectl describe` shows liveness probe failures on `/healthz` port `8080`, but the application actually serves its health endpoint on port `9090` at path `/health`. Fix the Pod's probe configuration so it stabilizes.

**Solution:**

```bash
kubectl -n web describe pod app-frontend | grep -A5 Liveness
kubectl -n web get pod app-frontend -o yaml > app-frontend.yaml
```

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 9090
  initialDelaySeconds: 10
  periodSeconds: 10
```

```bash
# Pods are immutable for most fields incl. probes on a bare Pod;
# if owned by a Deployment, edit the Deployment instead:
kubectl -n web get pod app-frontend -o jsonpath='{.metadata.ownerReferences[0].kind}'
kubectl -n web edit deployment app-frontend
kubectl -n web rollout status deployment app-frontend
```

**What it's testing:** Distinguishing a probe misconfiguration from an actual application failure (§89), and the important exam trap that a bare Pod's probe spec is immutable in place — if the Pod is controller-owned, the fix belongs on the Deployment, not a direct Pod edit that will fail or silently not apply as expected.

### Scenario 4 — Blue/Green Style Deployment Cutover Using Labels (7 minutes)

**Prompt as seen on exam:**

> Namespace `checkout`. A `Service` named `checkout-svc` currently routes to Pods labeled `version: blue`. A new Deployment `checkout-green` is already running healthy Pods labeled `version: green`. Cut traffic over to green with zero downtime, without deleting the blue Deployment.

**Solution:**

```bash
kubectl -n checkout get pods --show-labels
kubectl -n checkout get svc checkout-svc -o yaml | grep -A3 selector
kubectl -n checkout patch svc checkout-svc -p '{"spec":{"selector":{"version":"green"}}}'
kubectl -n checkout get endpoints checkout-svc
kubectl -n checkout run debug --image=busybox:1.36 --rm -it --restart=Never -- wget -qO- checkout-svc:80
```

**What it's testing:** Blue/green deployment strategy as a label-selector operation rather than a scaling operation (§28), and verifying the cutover via Endpoints rather than assuming a patched selector immediately took effect without checking.

### Scenario 5 — ConfigMap-Driven Configuration With a Volume Mount (5 minutes)

**Prompt as seen on exam:**

> Namespace `reporting`. Create a ConfigMap named `report-config` from a literal key `MAX_ROWS=5000`, then mount it as a volume (not env vars) at `/etc/config` inside Pod `report-gen`'s existing container. The Pod does not yet exist — create it running image `myregistry/report-gen:3.0`.

**Solution:**

```bash
kubectl -n reporting create configmap report-config --from-literal=MAX_ROWS=5000
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: report-gen
  namespace: reporting
spec:
  containers:
    - name: report-gen
      image: myregistry/report-gen:3.0
      volumeMounts:
        - name: config-vol
          mountPath: /etc/config
  volumes:
    - name: config-vol
      configMap:
        name: report-config
```

```bash
kubectl apply -f report-gen.yaml
kubectl -n reporting exec report-gen -- ls /etc/config
kubectl -n reporting exec report-gen -- cat /etc/config/MAX_ROWS
```

**What it's testing:** Correctly choosing volume-mount consumption over env-var consumption when the prompt explicitly asks for a file-based config (§41), since defaulting to env vars out of habit is a common exam point-loser when the prompt is specific about delivery mechanism.

### Scenario 6 — Exposing an Application via Ingress With Path-Based Routing (7 minutes)

**Prompt as seen on exam:**

> Namespace `shop`. Two Services already exist: `catalog-svc` (port 80) and `cart-svc` (port 80). An Ingress controller is already installed. Create an Ingress named `shop-ingress` routing `/catalog` to `catalog-svc` and `/cart` to `cart-svc` on host `shop.example.com`.

**Solution:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-ingress
  namespace: shop
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    - host: shop.example.com
      http:
        paths:
          - path: /catalog
            pathType: Prefix
            backend:
              service:
                name: catalog-svc
                port:
                  number: 80
          - path: /cart
            pathType: Prefix
            backend:
              service:
                name: cart-svc
                port:
                  number: 80
```

```bash
kubectl apply -f shop-ingress.yaml
kubectl -n shop get ingress shop-ingress
kubectl -n shop describe ingress shop-ingress
```

**What it's testing:** Ingress path-based routing syntax exactly (`pathType`, `ingressClassName`, multiple `paths` entries) — one of the most syntax-heavy CKAD tasks, where a single indentation or field-name slip silently produces an Ingress that never routes correctly, so verification via `describe` (which shows resolved backends) matters more here than almost anywhere else in the exam.

### Scenario 7 — Debugging a Pod With an Ephemeral Container (6 minutes)

**Prompt as seen on exam:**

> Namespace `legacy`. Pod `old-app` is running a distroless image with no shell, making `kubectl exec` unusable for debugging. Attach an ephemeral debug container to investigate why the app is returning HTTP 500s, without restarting the Pod.

**Solution:**

```bash
kubectl -n legacy debug -it old-app --image=busybox:1.36 --target=old-app -- sh
# inside the ephemeral container's shared process namespace:
ps aux
wget -qO- localhost:8080/health
exit
kubectl -n legacy get pod old-app
```

**What it's testing:** `kubectl debug` with `--target` for process-namespace sharing against a distroless container (§90), a CKAD-relevant observability skill specifically because distroless/minimal images are increasingly common in real application delivery and `kubectl exec` genuinely cannot debug them without this mechanism.

## 6. Production Usage Notes: Practicing Under Real Exam Time Pressure

- **Practice writing Pod/Deployment YAML from a generator base (`kubectl run ... --dry-run=client -o yaml`) rather than from a blank file** — CKAD scenarios reward speed of getting to a correct starting skeleton, and hand-typing a full Pod spec from memory wastes minutes better spent on the actual fix.
- **Rehearse the ConfigMap/Secret creation one-liners until they're automatic** — `--from-literal`, `--from-file`, `--from-env-file` cover the large majority of exam config-injection tasks, and hesitating over which flag to use costs real time.
- **Time-box the Ingress/Service scenarios generously in early practice** — YAML-heavy networking tasks are where syntax slips are most costly, and the fastest path to a correct answer is often a known-good template adapted, not typed fresh under pressure.
- **Practice the `kubectl debug` ephemeral-container workflow specifically** — it's a newer, less-drilled feature than `exec`/`logs`, and candidates who haven't rehearsed it lose disproportionate time discovering the flag syntax live during the exam.

## 7. Security Considerations

- Scenario 2's Secret-injection pattern is the CKAD's most direct security-adjacent task: never let a decoded Secret value appear literally in a manifest, command history, or terminal output you'd leave visible — `secretKeyRef` exists precisely so the value never needs to be typed or seen during normal operation.
- Distroless images (Scenario 7) are themselves a security best practice — smaller attack surface, no shell for an attacker to pivot through — and the `kubectl debug --target` ephemeral-container pattern exists specifically so teams don't have to compromise that hardening just to gain debuggability.
- Any Pod or Deployment scenario that doesn't specify a SecurityContext should still default to non-root, read-only-root-filesystem thinking during practice (§45) — the exam sometimes rewards (and sometimes explicitly requires) hardened defaults even when the prompt doesn't mention security by name.

## 8. Common Troubleshooting Scenarios

| Symptom During Practice                                                          | Cause                                                                                      | Fix                                                                                               |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Probe fix edited directly on a Pod appears to have no effect                     | The Pod is controller-owned; direct Pod field edits for probes are blocked or get reverted | Edit the owning Deployment/StatefulSet instead of the bare Pod                                    |
| ConfigMap mounted as a volume shows a directory, not the expected file structure | Forgot that each key becomes a file under the mount path                                   | `ls` the mount path first to confirm the actual file layout before assuming a single file exists  |
| Ingress created but requests still return 404                                    | `ingressClassName` missing or doesn't match the installed controller                       | `kubectl get ingressclass` to confirm the exact class name, then set it explicitly on the Ingress |
| `kubectl exec` fails with "OCI runtime exec failed: no such file or directory"   | Target image is distroless/minimal with no shell                                           | Use `kubectl debug --target` with a debug image instead of `exec`                                 |
| Secret env var appears empty inside the container                                | Wrong `key` in `secretKeyRef`, or Secret created in a different namespace                  | Confirm both the Secret's namespace and its actual key names with `kubectl get secret -o yaml`    |

## 9. Best Practices

- Read each scenario for the underlying need described, not just the literal noun used — "must wait for a dependency" means init container even if the word "init" never appears in the prompt.
- Default to volume-mounted ConfigMaps/Secrets when config needs to be reloadable without a Pod restart, and env-var injection when the app only reads config at startup — know both mechanisms cold since the exam specifies one or the other deliberately.
- Verify networking-heavy tasks (Services, Ingress) with an actual request (`curl`/`wget` from inside the cluster), not just `kubectl get` — a resource existing is not the same as it correctly routing traffic.

## 10. Common Anti-Patterns / Mistakes

- **Defaulting to env vars for every config need** out of habit, even when the prompt explicitly asks for a file-based volume mount — this is a frequent, avoidable point-loser.
- **Editing a bare Pod's probe or resource fields directly when it's actually controller-owned**, wasting time on an edit that gets reverted or rejected instead of editing the Deployment.
- **Skipping verification on networking tasks** because `kubectl get ingress` shows the object exists — existence is not correctness; always check that the routing actually resolves.

## 11. Interview Questions

**🎯 Beginner:** _"When would you use an init container instead of just putting the wait logic inside your main container's entrypoint script?"_
**Model answer:** An init container cleanly separates a one-time setup/dependency-wait concern from the application's actual runtime logic — it runs to completion before the main container starts, keeps the main image free of setup-specific tooling, and its failure is reported distinctly in Pod status, making it easier to diagnose a stuck dependency versus an actual application crash. Baking the same logic into the entrypoint script conflates the two concerns and makes the failure mode harder to distinguish from an application bug.
_What the interviewer is probing for:_ Understanding init containers as a design choice for separation of concerns, not just a syntax feature.

**🎯 Intermediate:** _"What's the difference between mounting a ConfigMap as a volume versus injecting it as environment variables, and when does the choice actually matter functionally, not just stylistically?"_
**Model answer:** Volume-mounted ConfigMaps update live inside the container when the ConfigMap changes (subject to kubelet sync delay), without needing a Pod restart, which matters for applications that watch their config files for changes. Env-var injection is captured once at container start and never updates without a restart, which is simpler but means a ConfigMap change alone won't propagate. The functional choice matters specifically for apps that support hot-reload of config — those should use volume mounts — while apps that only read config at startup can use either with no practical difference.
_What the interviewer is probing for:_ Real understanding of the live-update behavior difference, not just syntax recall.

**🎯 Senior:** _"A Deployment's rollout appears successful (`rollout status` reports success) but the application is actually serving errors to users. How do you reconcile this, and what does it tell you about readiness probe design?"_
**Model answer:** `rollout status` reports success based on the Deployment controller's view — new Pods reached `Ready` per their readiness probe and the old ReplicaSet was scaled down — which only reflects what the readiness probe actually checks. If the probe checks a shallow endpoint (e.g., a `/healthz` that always returns 200 regardless of downstream dependency health) while the app's real functionality depends on something the probe doesn't verify (a database connection, a cache warm-up), the rollout can report success while genuinely broken Pods serve traffic. The fix is designing the readiness probe to actually reflect serving-readiness — checking the dependencies the app needs, not just process liveness — and treating "rollout succeeded" and "application is healthy" as two claims that only align when the probe is designed correctly.
_What the interviewer is probing for:_ Recognizing that Kubernetes's declarative success signals are only as trustworthy as the probes backing them, a subtlety many candidates miss by treating `rollout status` as ground truth.

**🎯 Architect:** _"Design the configuration and secrets strategy for an application that needs to hot-reload most of its config but must never expose one specific highly sensitive credential to a file on disk, even temporarily."_
**Model answer:** I'd split the concern in two: general configuration goes into a ConfigMap mounted as a volume so the application can watch the mount path and hot-reload without a restart, giving operational flexibility for the majority of settings that aren't sensitive. The one highly sensitive credential is deliberately kept out of that same mechanism — instead injected as an environment variable via `secretKeyRef` sourced from a Secret (ideally backed by an external secret store per Part 10's Vault/External Secrets Operator integration, so it's not even resting in etcd in plaintext without EncryptionConfiguration), specifically because a volume-mounted Secret still touches the container's filesystem as a file, however transient, while an env var sourced this way exists only in process memory and the container's environment block, never on disk. I'd also ensure the container's SecurityContext (§45) sets a read-only root filesystem so nothing — including that credential — could be persisted to disk by the application itself even accidentally, closing the gap the delivery mechanism alone doesn't fully cover. The architectural principle is treating "how sensitive is this value" as a first-class input to the delivery-mechanism choice, not defaulting to one mechanism for all configuration uniformly.
_What the interviewer is probing for:_ Ability to reason about configuration delivery as a security-tiered decision rather than a one-size-fits-all mechanism, and awareness that env-var vs. volume-mount has a genuine "touches disk or doesn't" security distinction beyond mere convenience.

## 12. Common Misconceptions

1. **"ConfigMaps and Secrets are functionally identical except for a naming convention."** Secrets are intended for sensitive data and integrate with encryption-at-rest and RBAC patterns differently in practice; treating them as interchangeable naming is a security-maturity gap, not just a style preference.
2. **"A successful `rollout status` means the application is actually healthy."** It only means the readiness probe passed — if the probe is shallow, a broken application can still show a successful rollout.
3. **"You can always `kubectl exec` into any container to debug it."** Distroless and minimal images have no shell; `kubectl debug` with an ephemeral container and `--target` is required instead.
4. **"Volume-mounted ConfigMaps and env-var ConfigMaps behave identically once consumed."** Only the volume-mounted form updates live without a Pod restart; env vars are captured once at container start.

## 13. 🔑 Key Takeaways

- CKAD scenarios describe a need in plain language more often than they name the Kubernetes object directly — recognizing ConfigMap vs. Secret, probe type, or multi-container pattern from the described symptom is itself the tested skill.
- Application Environment/Configuration/Security is the single highest-weighted CKAD domain (25%) — ConfigMap, Secret, SecurityContext, and probe fluency is worth more raw exam points than any other individual skill area.
- Probe and resource-field edits on a controller-owned Pod belong on the controller, not the Pod directly — a common and entirely avoidable exam trap.
- Networking tasks (Services, Ingress) should always be verified with an actual request, not just object existence, since a resource existing is not the same as it routing correctly.
- Sensitive values should never be typed literally into a manifest or terminal output; `secretKeyRef` exists specifically to avoid that exposure, on the exam and in real production practice alike.

## 14. Related Concepts & What's Next

This section drew its scenario material from multi-container Pod patterns (§24–§25), Deployments (§27–§28), ConfigMaps/Secrets (§41–§42), SecurityContext (§45), probes (§89), and Services/Ingress (Part 7), and built on §134's exam-discipline foundation (context switching, time-boxing, verify-then-move-on). §136 shifts focus again — from developer-facing correctness to security-first thinking, covering CKS-style scenarios that draw on the Part 15 security deep dive: cluster hardening, supply chain security, and runtime threat detection.

**Next Section:** §136 — `Section-136-Part17-CKS-Style-Scenario-Question-Bank.md`
