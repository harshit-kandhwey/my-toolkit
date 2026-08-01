# Section 53 (Part 7): Ingress and Ingress Controllers (NGINX Ingress and Alternatives)

## 1. Definition

**Plain language:** Exposing dozens of HTTP services to the outside world by giving each one its own cloud load balancer would be expensive and unwieldy — Ingress lets you define HTTP/HTTPS routing rules (which hostname or path goes to which Service) in one place, fronted by a single entry point.

**Precise definition:** An **Ingress** is a Kubernetes API object that declares HTTP/HTTPS routing rules — host-based and path-based rules mapping external requests to internal Services — but the Ingress object **has no built-in implementation**. It requires a separately installed **Ingress Controller** (a specific piece of software, e.g., **ingress-nginx**, Traefik, HAProxy Ingress, or a cloud provider's own controller) actually running in the cluster, watching Ingress objects, and configuring itself (typically a reverse proxy) to implement the routing rules described. Without an Ingress Controller installed, creating Ingress objects has zero observable effect — a very common point of confusion for anyone new to the API.

## 2. Why This Matters

- **Ingress does not replace Services — it routes to them.** An Ingress object's rules always point at a backend Service (§50), typically a ClusterIP Service; the Ingress Controller terminates external HTTP/HTTPS traffic and then forwards internally using ordinary Service-based routing, meaning everything already understood about Services and DNS (§52) still applies underneath.
- **"Ingress" the API object and "an Ingress Controller" the software are two different things, and conflating them is the single most common mistake with this feature.** Kubernetes ships the Ingress API by default, but ships **no default controller** — a cluster with Ingress objects applied but no controller installed will show the objects existing via `kubectl get ingress`, with no actual routing happening at all.
- **Ingress is the direct, widely-adopted predecessor to the Gateway API (§54)**, and remains the dominant HTTP routing mechanism in production Kubernetes today — understanding it thoroughly, including its real limitations (heavy reliance on controller-specific annotations for anything beyond basic host/path routing), is what motivates the newer API's design.

🔑 **Key Takeaway:** Ingress is purely a declarative API for HTTP/HTTPS routing rules; it requires a separately installed Ingress Controller to do anything at all, and that controller's job is to configure a reverse proxy that ultimately still forwards traffic to ordinary Kubernetes Services underneath.

## 3. Prerequisites and Dependencies

Builds directly on §50 (Services, since every Ingress rule ultimately routes to a Service, never directly to Pods) and §49 (CNI, which handles the actual Pod-to-Pod delivery once traffic reaches inside the cluster).

## 4. Architecture Diagram

```text
                         External client (browser)
                                    │
                                    ▼
                    DNS: app.example.com → LoadBalancer IP
                                    │
                                    ▼
              ┌────────────────────────────────────────────┐
              │  Ingress Controller (e.g. ingress-nginx)   │
              │  - runs as a Deployment + a Service        │
              │    (usually type LoadBalancer)             │
              │  - watches Ingress objects via API server  │
              │  - reconfigures its reverse proxy (NGINX)  │
              │    on every Ingress add/change             │
              └───────────────────┬────────────────────────┘
                                    │  reads
                                    ▼
              ┌───────────────────────────────────────────┐
              │  Ingress object (rules)                   │
              │   host: app.example.com                   │
              │     /api    → svc: api-svc:8080           │
              │     /       → svc: web-svc:80             │
              └───────────────────┬───────────────────────┘
                                    │ routes matched requests to
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
            Service: api-svc (ClusterIP)   Service: web-svc (ClusterIP)
                     │                             │
                     ▼                             ▼
                api-* Pods                      web-* Pods
```

- **The Ingress Controller's own entry point is typically a single `LoadBalancer` or `NodePort` Service** — meaning one cloud load balancer can front many Ingress objects and many Services, which is the core cost/complexity saving Ingress provides over a `LoadBalancer` Service per application.
- **The controller reconfigures its proxy dynamically as Ingress objects change** — creating, editing, or deleting an Ingress object triggers the controller to update its reverse-proxy configuration (e.g., regenerating an NGINX config and reloading), with no manual proxy-configuration step required.
- **TLS termination commonly happens at the Ingress Controller**, referencing a `Secret` containing a TLS certificate/key named in the Ingress object's `tls` field — traffic between the controller and backend Services is typically plain HTTP inside the cluster unless a service mesh (§122, Part 16) adds mTLS on top.

## 5. Hands-On: Installing and Using an Ingress Controller

### 5.1 Installing ingress-nginx

**Purpose:** Ingress objects have no effect until a controller is installed — this is always the first, required step.

**Syntax:**

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/cloud/deploy.yaml
```

**Example usage and expected output:**

```bash
$ kubectl apply -f deploy.yaml
namespace/ingress-nginx created
serviceaccount/ingress-nginx created
deployment.apps/ingress-nginx-controller created
service/ingress-nginx-controller created
...

$ kubectl get pods -n ingress-nginx
NAME                                        READY   STATUS    RESTARTS   AGE
ingress-nginx-controller-7d8f9c6b5d-x2m4p   1/1     Running   0          45s

$ kubectl get svc -n ingress-nginx
NAME                       TYPE           CLUSTER-IP     EXTERNAL-IP     PORT(S)
ingress-nginx-controller   LoadBalancer   10.96.50.10    203.0.113.10    80:31234/TCP,443:31567/TCP
```

**Production usage example:** Confirming the controller's Pods are `Running` and its Service has an assigned `EXTERNAL-IP` is the mandatory first check before debugging any "Ingress isn't working" report — a huge share of Ingress issues are actually "no controller installed" or "controller Service has no external IP yet," not a problem with the Ingress rules themselves.

**Common errors:** Applying Ingress objects and expecting routing to work with no controller installed at all — `kubectl get ingress` shows the object, but nothing is actually listening for or routing the described traffic.

### 5.2 Defining Host- and Path-Based Routing Rules

**Purpose:** Route different hostnames and URL paths to different backend Services through a single Ingress object.

**Syntax:**

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-svc
                port:
                  number: 8080
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web-svc
                port:
                  number: 80
```

**Example usage and expected output:**

```bash
$ kubectl apply -f app-ingress.yaml
ingress.networking.k8s.io/app-ingress created

$ kubectl get ingress
NAME          CLASS   HOSTS              ADDRESS         PORTS   AGE
app-ingress   nginx   app.example.com    203.0.113.10    80      30s

$ curl -H "Host: app.example.com" http://203.0.113.10/api/health
{"status":"ok"}
```

**Production usage example:** This exact pattern — one Ingress, one hostname, path-based routing to multiple backend Services — is the standard way production teams expose a frontend and its backing API under one domain without provisioning separate cloud load balancers for each.

**Common errors:** Omitting `ingressClassName` (or the older `kubernetes.io/ingress.class` annotation) in a cluster running multiple Ingress Controllers causes ambiguity about which controller should implement the rule — some controllers ignore Ingress objects without a matching class entirely, silently doing nothing rather than erroring.

### 5.3 TLS Termination at the Ingress

**Purpose:** Terminate HTTPS at the Ingress Controller using a certificate stored as a Kubernetes Secret.

**Syntax:**

```yaml
spec:
  tls:
    - hosts:
        - app.example.com
      secretName: app-tls-secret
  rules:
    - host: app.example.com
      # ...same rules as above
```

**Example usage and expected output:**

```bash
$ kubectl create secret tls app-tls-secret --cert=tls.crt --key=tls.key
secret/app-tls-secret created

$ kubectl apply -f app-ingress-tls.yaml
ingress.networking.k8s.io/app-ingress configured

$ curl -v https://app.example.com/
* Server certificate: app.example.com (matches)
< HTTP/2 200
```

**Production usage example:** Production clusters commonly automate this certificate lifecycle with **cert-manager**, which watches Ingress objects (via annotations) and automatically provisions/renews certificates from Let's Encrypt or an internal CA, rather than manually creating and rotating TLS Secrets.

**Common errors:** A `secretName` in the `tls` block that doesn't exist, or exists in the wrong namespace (TLS Secrets referenced by an Ingress must be in the same namespace as the Ingress object itself), results in the controller falling back to a default, self-signed certificate — connections succeed but present a certificate warning rather than failing outright.

## 6. Production Usage Notes

- **Most non-trivial routing behavior beyond basic host/path matching is implemented via controller-specific annotations** (`nginx.ingress.kubernetes.io/*` for ingress-nginx, different prefixes for Traefik/HAProxy Ingress) — this annotation sprawl, and the fact that annotations are not portable between controllers, is the exact pain point that motivated the Gateway API's design (§54).
- **Running multiple Ingress Controllers in one cluster is common** (e.g., an internal-facing controller and an external-facing one, each with its own `IngressClass`), letting teams route internal-only traffic differently from public traffic without separate clusters.
- **The Ingress Controller's own Pods are a single, shared point of scale and failure for all HTTP ingress traffic** — sizing its replica count, resource requests, and its fronting `LoadBalancer` Service's health appropriately is a real production capacity-planning concern, not a set-and-forget install.

## 7. Security Considerations

- The Ingress Controller is, by definition, one of the most externally-exposed components in the cluster — its own security posture (running as non-root, minimal RBAC, kept patched) matters disproportionately since it terminates all inbound HTTP/HTTPS traffic (§113, Part 15).
- TLS Secrets referenced by Ingress objects are ordinary Kubernetes Secrets and inherit all the same at-rest encryption and RBAC-access considerations as any other Secret (§42, Part 6) — anyone with read access to that Secret can extract the private key.
- Because Ingress relies heavily on annotations for advanced behavior (rate limiting, auth, IP allowlisting), a misconfigured or missing security-relevant annotation (e.g., forgetting an IP allowlist annotation meant to restrict an admin path) is an easy, annotation-based way to accidentally under-restrict access.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                     | Resolution Path                                                                                              |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `kubectl get ingress` shows the object, but requests get no response | No Ingress Controller installed, or none matching the Ingress's class            | `kubectl get pods -n <controller-namespace>`; confirm a controller matching `ingressClassName` is running    |
| Requests reach the wrong backend Service                             | Path/host rule ordering or `pathType` mismatch (`Exact` vs. `Prefix`)            | Review rule order and `pathType`; more specific paths should generally be listed and matched correctly first |
| HTTPS connects but shows a certificate warning                       | `tls.secretName` missing, wrong namespace, or controller falling back to default | Verify the TLS Secret exists in the Ingress's namespace and contains a valid cert/key pair                   |
| Ingress works for one controller but is ignored by another           | Missing or mismatched `ingressClassName` in a multi-controller cluster           | Set `ingressClassName` explicitly to the intended controller's `IngressClass` name                           |

## 9. Best Practices

- Always confirm an Ingress Controller is installed and healthy as the first step of any Ingress-related work — never assume the API object alone provides routing.
- Set `ingressClassName` explicitly on every Ingress object, even in single-controller clusters, to avoid ambiguity if a second controller or class is ever introduced later.
- Automate TLS certificate issuance and renewal (e.g., cert-manager) rather than manually managing TLS Secrets, since manual certificate rotation is a common source of unplanned expiry-related outages.

## 10. Common Anti-Patterns / Mistakes

- **Creating Ingress objects and assuming Kubernetes provides routing "out of the box"**, not realizing a controller must be separately installed — the single most common Ingress misconception.
- **Relying heavily on one controller's annotation dialect** (e.g., deeply ingress-nginx-specific annotations) without recognizing this creates lock-in, making a future migration to a different controller or to Gateway API (§54) far more disruptive than it needs to be.
- **Manually managing TLS certificates and their rotation** instead of automating issuance, leading to preventable certificate-expiry outages.

## 11. Interview Questions

**🎯 Beginner:** _"What is Ingress, and why doesn't creating an Ingress object alone make a service reachable from outside the cluster?"_
**Model answer:** Ingress is a Kubernetes API object that declares HTTP/HTTPS routing rules — which hostnames and paths should route to which Services — but Kubernetes doesn't ship a built-in implementation for it. A separate Ingress Controller (like ingress-nginx) has to be installed to actually watch Ingress objects and configure a real reverse proxy that implements the described routing; without a controller running, the Ingress object exists in the API but has no effect on actual traffic.
_What the interviewer is probing for:_ Correctly distinguishing the Ingress API object from the Ingress Controller software — the most common point of confusion with this feature.

**🎯 Intermediate:** _"Explain how an Ingress relates to Services — does Ingress replace the need for Services?"_
**Model answer:** No — Ingress routes to Services, it doesn't replace them. Every rule in an Ingress object's spec points at a backend Service (almost always a ClusterIP Service), and the Ingress Controller's job is to terminate external HTTP/HTTPS traffic and forward it internally to that Service, which then load-balances to its backing Pods exactly as it would for any other client. Ingress adds an HTTP-aware routing layer (host/path-based rules, TLS termination) in front of Services; it depends on Services being correctly set up underneath, it doesn't supersede them.
_What the interviewer is probing for:_ Clear understanding of the layering — Ingress as an additional HTTP routing layer on top of, not instead of, Services.

**🎯 Senior:** _"A team has an Ingress object correctly configured with the right host and path rules, and the Ingress Controller is confirmed running, but requests to the app still fail. How would you troubleshoot?"_
**Model answer:** I'd first confirm the controller's fronting Service (typically a LoadBalancer) actually has an external IP assigned and that DNS for the hostname points at it — a surprisingly common gap is DNS not yet propagated or pointed at the wrong IP. Next I'd check the Ingress object's `pathType` and rule ordering, since `Prefix` versus `Exact` mismatches or overlapping rules can route requests to an unintended backend even when the Ingress "looks" correct. I'd then verify the backend Service itself resolves and has healthy Endpoints (§50) — since Ingress failures are frequently actually a downstream Service/Pod health problem being surfaced as "Ingress isn't working." Only after ruling out DNS, rule matching, and backend Service health would I look at the controller's own logs for reverse-proxy-level errors (upstream timeouts, bad gateway responses).
_What the interviewer is probing for:_ A layered troubleshooting approach that doesn't assume the problem is Ingress-specific just because Ingress is the last thing configured, correctly checking DNS, rule matching, and backend health in a sensible order.

**🎯 Architect:** _"You're standardizing Ingress usage across dozens of application teams in one large cluster, some of which want very different, controller-specific routing behaviors. How do you approach this without creating unmanageable annotation sprawl?"_
**Model answer:** I'd standardize on a single Ingress Controller for the vast majority of use cases, with a documented, curated set of approved, commonly-needed annotations (rate limiting, basic auth, TLS/cert-manager integration) rather than letting every team discover and use arbitrary controller-specific annotations ad hoc — treating the annotation surface as something the platform team curates and documents, not an unrestricted extension point. For teams with genuinely divergent requirements (e.g., needing a second, differently-configured controller for internal-only traffic), I'd use separate `IngressClass` objects rather than annotation-level hacks on a shared controller. I'd also actively track Gateway API (§54) maturity as a longer-term direction, since its role-oriented, portable design is a direct answer to exactly this annotation-sprawl problem — but I wouldn't force an early migration before the ecosystem and team tooling around it are genuinely ready, given Ingress's currently much broader production adoption and battle-testing.
_What the interviewer is probing for:_ Platform-level thinking about governance of an extension mechanism (annotations) that easily sprawls, plus calibrated, non-hype awareness of Gateway API's trajectory relative to Ingress's current maturity.

## 12. Common Misconceptions

1. **"Ingress provides routing out of the box."** It is purely a declarative API; a separately installed Ingress Controller is required to implement any actual routing behavior.
2. **"Ingress replaces Services."** Ingress routes external HTTP/HTTPS traffic to Services; it depends on Services and their Endpoints being correctly configured, it does not substitute for them.
3. **"All Ingress Controllers behave identically given the same Ingress object."** Basic host/path routing is portable, but most advanced behavior is implemented via controller-specific annotations that don't transfer between controllers.
4. **"An Ingress with no matching `ingressClassName` will error out clearly."** In multi-controller clusters, a missing or mismatched class commonly results in the rule being silently ignored by all controllers, not a visible error.

## 13. 🔑 Key Takeaways

- Ingress is a declarative HTTP/HTTPS routing API with no built-in implementation; an Ingress Controller (ingress-nginx, Traefik, and others) must be separately installed to do anything at all.
- Every Ingress rule routes to a backend Service, never directly to Pods — Ingress adds an HTTP-aware layer on top of, not instead of, the Service abstraction (§50).
- TLS termination typically happens at the Ingress Controller, referencing a namespace-local Secret; cert-manager automation is standard production practice over manual certificate handling.
- Advanced routing behavior relies heavily on controller-specific annotations, which are not portable between controllers — a real source of lock-in and the direct motivation behind Gateway API (§54).
- Confirming the controller is installed and healthy, and that DNS/`ingressClassName` are correctly set, should always precede deeper Ingress-specific debugging.

## 14. Related Concepts & What's Next

§50 covers the Service abstraction every Ingress rule ultimately routes to, and §49 covers the CNI layer handling actual packet delivery once traffic is inside the cluster. §54 introduces the Gateway API, designed specifically to address the annotation-based extension model's limitations described in this section, and §113 (Part 15) revisits Ingress Controller hardening as part of CKS-level network security depth.

**Next Section:** §54 — `Section-54-Part7-Gateway-API-Modern-Successor-To-Ingress.md`
