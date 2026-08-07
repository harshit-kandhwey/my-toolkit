# Section 54 (Part 7): Gateway API: the Modern Successor to Ingress

## 1. Definition

**Plain language:** Ingress worked, but every meaningful feature beyond "route this path to that Service" ended up bolted on through vendor-specific annotations that don't transfer between controllers — Gateway API is a newer, more expressive routing API designed from the start to model those richer use cases directly, with roles split cleanly between infrastructure operators and application developers.

**Precise definition:** The **Gateway API** is a Kubernetes SIG-Network project defining a set of role-oriented resources — **GatewayClass** (a template for a type of load balancer/proxy, managed by infrastructure providers), **Gateway** (a concrete instance of that class, managed by platform/cluster operators, binding to listeners/ports/TLS), and **Routes** (`HTTPRoute`, `TCPRoute`, `GRPCRoute`, and others, managed by application teams, defining actual routing rules) — that together replace the single, flatter `Ingress` object with a layered model expressing native, portable support for traffic splitting, header-based routing, and cross-namespace routing that Ingress could only achieve through non-portable, controller-specific annotations.

## 2. Why This Matters

- **Gateway API exists specifically because Ingress's annotation-based extension model became unwieldy at scale.** Anything beyond basic host/path routing under Ingress ([§53](./Section-53-Part7-Ingress-Ingress-Controllers.md)) — traffic splitting for canary releases, request header matching, cross-namespace route binding — required controller-specific annotations that locked configuration to one controller's dialect; Gateway API models these as first-class, portable API fields instead.
- **The role separation (infrastructure provider / cluster operator / application developer) matches how large organizations actually operate Kubernetes**, letting a platform team own `GatewayClass`/`Gateway` objects (load balancer provisioning, TLS, listener configuration) while application teams independently own `HTTPRoute` objects for their own routing rules, without either needing access to the other's resources.
- **Gateway API is a genuinely newer, less universally adopted standard than Ingress**, not (yet) a wholesale replacement in most production estates — understanding both is necessary for real-world clusters, since Ingress remains the dominant, most battle-tested option in the large majority of currently-running clusters today.

🔑 **Key Takeaway:** Gateway API is a role-oriented, more expressive successor to Ingress, splitting infrastructure (`GatewayClass`/`Gateway`) from application-level routing (`HTTPRoute` and friends) to solve Ingress's annotation-sprawl problem with portable, native fields — but it is a newer standard still earning the breadth of production adoption Ingress ([§53](./Section-53-Part7-Ingress-Ingress-Controllers.md)) already has.

## 3. Prerequisites and Dependencies

Builds directly on [§53](./Section-53-Part7-Ingress-Ingress-Controllers.md) (Ingress), whose annotation-based limitations directly motivate Gateway API's design, and indirectly on [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) (Services, since Routes still ultimately forward to Services).

## 4. Architecture Diagram

```text
   Infrastructure provider role         Cluster operator role         App team role
   ┌──────────────────────────┐    ┌────────────────────────────┐   ┌────────────────────────┐
   │      GatewayClass        │    │          Gateway           │   │     HTTPRoute          │
   │  (e.g. "nginx", "istio", │───►│  listeners: 80, 443        │◄──│  parentRef: Gateway    │
   │   "cilium" — a template  │    │  TLS cert reference        │   │  rules:                │
   │   for a controller type) │    │  one instance per Gateway  │   │   - match: /api        │
   └──────────────────────────┘    │   provisioned by the class │   │     backendRef: api-svc│
                                   └────────────────────────────┘   │   - match: /           │
                                                                    │     backendRef: web-svc│
                                                                    └────────────────────────┘
                                              │
                                              ▼
                          External client → Gateway's LB IP → matched HTTPRoute rule
                                              │
                                ┌─────────────┴──────────────┐
                                ▼                            ▼
                        Service: api-svc                Service: web-svc
                                │                            │
                                ▼                            ▼
                          api-* Pods                       web-* Pods
```

- **`GatewayClass` is analogous to `IngressClass`**, but is explicitly the infrastructure provider's artifact (e.g., a cloud provider or a controller vendor ships a `GatewayClass`), separating "what kind of load balancer implementation exists" from "an actual running instance of one."
- **A single `Gateway` can have multiple `Route` objects attached from different namespaces**, using explicit `parentRef`/namespace-selector permission — a native, portable way to let application teams self-service their own routing rules against a shared, centrally-managed Gateway, without the platform team needing to touch each team's routes.
- **`HTTPRoute` natively supports traffic-weight splitting across multiple backends** (e.g., 90%/10% for a canary) as a plain API field, something Ingress could only express through a specific controller's non-portable annotation.

## 5. Hands-On: Defining a Gateway and HTTPRoute

### 5.1 Creating a Gateway (Cluster-Operator-Owned)

**Purpose:** Provision a concrete listener/load-balancer instance from a `GatewayClass` — the infrastructure-facing half of the model.

**Syntax:**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shared-gateway
  namespace: gateway-infra
spec:
  gatewayClassName: nginx
  listeners:
    - name: https
      protocol: HTTPS
      port: 443
      tls:
        certificateRefs:
          - name: app-tls-secret
      allowedRoutes:
        namespaces:
          from: All
```

**Example usage and expected output:**

```bash
$ kubectl apply -f gateway.yaml
gateway.gateway.networking.k8s.io/shared-gateway created

$ kubectl get gateway -n gateway-infra
NAME             CLASS   ADDRESS         PROGRAMMED   AGE
shared-gateway   nginx   203.0.113.20    True         40s
```

**Production usage example:** Platform teams provision one or a small number of shared `Gateway` objects per cluster (often per environment or traffic tier — public vs. internal), with `allowedRoutes.namespaces.from: All` (or a label selector) explicitly granting application namespaces permission to attach their own `HTTPRoute` objects, without the platform team needing to create or approve each individual route.

**Common errors:** Leaving `allowedRoutes` unset or scoped too narrowly (e.g., `Same` namespace only) silently prevents application teams' `HTTPRoute` objects in other namespaces from attaching at all — the Route object is created successfully but never actually accepted by the Gateway, visible only via the Route's `status.parents` conditions.

### 5.2 Creating an HTTPRoute (Application-Team-Owned)

**Purpose:** Define application-specific routing rules, including native traffic splitting, attached to the shared Gateway from 5.1.

**Syntax:**

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: web-app-route
  namespace: web-app
spec:
  parentRefs:
    - name: shared-gateway
      namespace: gateway-infra
  hostnames:
    - "app.example.com"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /api
      backendRefs:
        - name: api-svc
          port: 8080
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: web-svc-v1
          port: 80
          weight: 90
        - name: web-svc-v2
          port: 80
          weight: 10
```

**Example usage and expected output:**

```bash
$ kubectl apply -f httproute.yaml
httproute.gateway.networking.k8s.io/web-app-route created

$ kubectl get httproute -n web-app
NAME            HOSTNAMES               AGE
web-app-route   ["app.example.com"]     15s

$ kubectl describe httproute web-app-route -n web-app | grep -A3 "Parents"
Status:
  Parents:
    Conditions:
      Reason:  Accepted
```

**Production usage example:** The `weight` field on `backendRefs` implements a native canary/traffic-split pattern — 90% of traffic to `web-svc-v1`, 10% to `web-svc-v2` — expressed as a portable API field rather than a controller-specific annotation, meaning this exact manifest behaves identically regardless of which Gateway API implementation (NGINX, Istio, Cilium) is actually running underneath.

**Common errors:** Confirming a route was "Accepted" requires checking `status.parents[].conditions` on the `HTTPRoute` itself, not just that `kubectl apply` succeeded — a Route can be created successfully in the API while still being rejected by its intended Gateway (e.g., due to `allowedRoutes` restrictions from 5.1), and this rejection is visible only in that status field.

## 6. Production Usage Notes

- **Gateway API adoption is real but still trails Ingress significantly in production breadth** — most existing production clusters and most third-party tooling/documentation still center on Ingress; teams adopting Gateway API today are generally doing so deliberately for its traffic-splitting/multi-tenancy benefits, not because Ingress has stopped being viable.
- **Several major service meshes and Ingress controllers now support Gateway API as an alternative or parallel configuration surface** (e.g., Istio, Cilium, and ingress-nginx's Gateway API support), meaning many clusters can adopt it incrementally alongside existing Ingress objects rather than requiring a hard cutover.
- **The role-oriented split (GatewayClass/Gateway vs. Route) is most valuable in multi-team, multi-tenant clusters** — a single-team cluster with one application may not see much practical benefit over a simpler Ingress setup, and adopting Gateway API purely for its own sake without an actual multi-tenancy or traffic-splitting need adds complexity without matching payoff.

## 7. Security Considerations

- The explicit `allowedRoutes` cross-namespace binding model is itself a security control — it lets a platform team precisely scope which namespaces may attach routes to a shared, security-sensitive Gateway (e.g., one handling TLS termination for a public-facing domain), a more granular boundary than Ingress's flatter, single-namespace-object model typically offers.
- TLS certificate references on a `Gateway` object follow the same Secret-based, namespace-scoped access considerations as Ingress TLS ([§53](./Section-53-Part7-Ingress-Ingress-Controllers.md)) — the Gateway's namespace must have access to the referenced Secret.
- Because multiple application teams' `HTTPRoute` objects can attach to one shared `Gateway`, a misconfigured or overly permissive route in one namespace has a wider blast radius (the shared, often public-facing Gateway) than a mistake in a per-team Ingress object would — route review discipline matters more, not less, with a shared Gateway model.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Likely Cause                                                                       | Resolution Path                                                                                                 |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `HTTPRoute` created but traffic never reaches it                    | Route not accepted by the Gateway (`allowedRoutes` restriction, wrong `parentRef`) | `kubectl describe httproute`; check `status.parents[].conditions` for `Accepted: False`                         |
| `Gateway` shows `PROGRAMMED: False`                                 | No controller implementing the referenced `GatewayClass`, or listener misconfig    | Confirm a Gateway API-supporting controller is installed and its `GatewayClass` name matches exactly            |
| Traffic-split weights don't match expected distribution             | Weight values misread, or backend Service unhealthy on one weighted target         | Verify `backendRefs[].weight` values and check target Services' Endpoint health independently                   |
| Team unsure whether to use Ingress or Gateway API for a new service | No documented platform standard on Gateway API adoption maturity for this cluster  | Confirm current cluster's supported/installed controller capability before defaulting to either API arbitrarily |

## 9. Best Practices

- Adopt Gateway API deliberately where its specific benefits (native traffic splitting, multi-tenant route delegation) are an actual current requirement, rather than migrating off a working Ingress setup purely because Gateway API is newer.
- Use `allowedRoutes` scoping intentionally on shared Gateways, treating cross-namespace route-attachment permission as a real access-control decision, not a default left wide open.
- Check `HTTPRoute` (and `Gateway`) status conditions explicitly after every apply — successful object creation in the API does not guarantee the route was accepted by its intended parent Gateway.

## 10. Common Anti-Patterns / Mistakes

- **Assuming Gateway API has fully replaced Ingress in the ecosystem** and is required for all new clusters, when in practice Ingress remains dominant in production breadth and remains a fully valid choice, especially for simpler single-team use cases.
- **Migrating to Gateway API without verifying the cluster's installed controller actually supports it**, resulting in `Gateway` objects that never reach `PROGRAMMED: True`.
- **Not checking `status.parents[].conditions` on `HTTPRoute` objects**, assuming a successful `kubectl apply` means the route is actually live and accepted by its target Gateway.

## 11. Interview Questions

**🎯 Beginner:** _"What is the Gateway API, and how does it relate to Ingress?"_
**Model answer:** The Gateway API is a newer Kubernetes routing API, designed as a more expressive successor to Ingress. Instead of one flat `Ingress` object, it splits responsibilities across `GatewayClass` (a template for a load balancer type), `Gateway` (a concrete provisioned instance), and Route objects like `HTTPRoute` (actual routing rules) — giving infrastructure teams and application teams separate, independently-manageable resources, and natively supporting features like traffic splitting that Ingress could only achieve through controller-specific annotations.
_What the interviewer is probing for:_ Basic understanding of the role split and the motivation (moving beyond annotations), not just "it's the new Ingress."

**🎯 Intermediate:** _"Why was the Gateway API created if Ingress already existed and worked?"_
**Model answer:** Ingress's core API only really covers basic host- and path-based routing; anything more advanced — traffic splitting for canary deployments, header-based routing, cross-namespace route delegation — had to be implemented through controller-specific annotations, which aren't portable between different Ingress Controllers and made configurations effectively locked to whichever controller a team happened to choose. Gateway API was designed to model these richer use cases as native, portable API fields (like `backendRefs[].weight` for traffic splitting) instead of annotations, and to explicitly separate infrastructure-level concerns (Gateway, GatewayClass) from application-level routing (HTTPRoute), matching how larger organizations actually split responsibility between platform and application teams.
_What the interviewer is probing for:_ Specific, accurate knowledge of Ingress's actual limitation (annotation sprawl and non-portability) rather than a vague "it's more modern."

**🎯 Senior:** _"A platform team wants to migrate a large multi-tenant cluster from Ingress to Gateway API. What would you evaluate before recommending that migration, and how would you sequence it?"_
**Model answer:** I'd first confirm the cluster's existing Ingress Controller(s) — or any alternative — actually have mature Gateway API support, since not every controller supports both equally well, and check what specific Gateway API features (traffic splitting, cross-namespace route delegation) are the actual driver for migrating, rather than migrating for its own sake. Given it's multi-tenant, I'd design the `Gateway`/`GatewayClass` layer first as a platform-owned resource with carefully scoped `allowedRoutes`, since this is exactly the layer that gives Gateway API its multi-tenant advantage over Ingress. I'd sequence the migration incrementally — since most controllers support Gateway API and Ingress objects coexisting — moving a small number of lower-risk application teams' routes to `HTTPRoute` first, validating status conditions and actual traffic behavior, before mandating a broader migration, rather than a single cutover across every tenant simultaneously.
_What the interviewer is probing for:_ Awareness that migration should be driven by a concrete need and validated incrementally, not treated as a mandatory or all-at-once technology refresh.

**🎯 Architect:** _"How do you decide, as a platform architecture standard, whether new clusters in your organization should default to Ingress or Gateway API?"_
**Model answer:** I'd base the decision on the organization's actual multi-tenancy and routing-complexity needs rather than newness alone: for clusters with multiple independent application teams needing self-service routing against a shared, centrally-managed entry point, or requiring native traffic splitting for progressive delivery, Gateway API's role separation and portable fields deliver genuine, measurable operational benefit that justifies its comparative immaturity. For simpler, single-team, or lower-complexity clusters, Ingress remains the more battle-tested, broadly-documented, and lower-risk default, and mandating Gateway API there would add complexity without matching payoff. I would also track, rather than assume, each intended Ingress Controller or service mesh's actual Gateway API support maturity before standardizing on it organization-wide, since the ecosystem's support is real but still uneven across implementations — the decision should be need-driven and re-evaluated periodically as adoption matures, not a one-time "always use the newer API" mandate.
_What the interviewer is probing for:_ Ability to make a calibrated, need-driven platform standard rather than defaulting to either "always use the new thing" or "never change what works," while accurately weighing current ecosystem maturity.

## 12. Common Misconceptions

1. **"Gateway API has replaced Ingress."** It is a newer, increasingly capable alternative, but Ingress remains dominant in current production breadth and is not deprecated or being removed.
2. **"Gateway API requires abandoning existing Ingress objects immediately."** Most controllers supporting Gateway API allow it to run alongside existing Ingress objects, enabling incremental, low-risk migration.
3. **"GatewayClass, Gateway, and Route are interchangeable or redundant layers."** Each has a distinct, intentional ownership role — infrastructure provider, cluster operator, and application team, respectively — mirroring real organizational boundaries.
4. **"A successfully applied HTTPRoute is automatically live."** It must additionally be accepted by its target Gateway (subject to `allowedRoutes` and other conditions), verifiable only via the Route's status conditions.

## 13. 🔑 Key Takeaways

- Gateway API splits Ingress's single flat object into `GatewayClass` (infrastructure template), `Gateway` (a provisioned instance), and Route objects (`HTTPRoute` and others, application-owned) — a role-oriented model matching real organizational boundaries.
- It exists specifically to replace Ingress's non-portable, controller-specific annotation sprawl with native, portable fields for traffic splitting, header matching, and cross-namespace route delegation.
- `allowedRoutes` on a Gateway is an explicit, granular cross-namespace access control, letting a shared Gateway safely serve multiple application teams' routes.
- Gateway API is a genuinely newer standard with growing but not yet universal adoption — Ingress remains the dominant, more battle-tested choice in most current production clusters.
- Route acceptance must be verified via status conditions, not assumed from successful object creation alone.

## 14. Related Concepts & What's Next

[§53](./Section-53-Part7-Ingress-Ingress-Controllers.md) covers Ingress in full, whose annotation-based limitations directly motivate this section's design, and [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) remains the underlying Service abstraction every Route ultimately forwards to. [§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) shifts from HTTP-layer routing to network-layer security policy with NetworkPolicies, and [§122](../Part16/Section-122-Part16-Service-Mesh-Concepts-Sidecar-Proxy-Pattern.md) revisits service mesh traffic management, which Gateway API's design increasingly overlaps and integrates with.

**Next Section:** [§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) — `Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md`
