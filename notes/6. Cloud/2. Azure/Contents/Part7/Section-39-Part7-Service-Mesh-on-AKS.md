# Section 39 — Service Mesh on AKS (Istio, Linkerd & Open Service Mesh)

## 1. Definition

**Plain language:** A service mesh is an extra layer that sits between every microservice in your AKS cluster, handling how those services talk to each other — routing, retries, encryption, and detailed traffic metrics — without each service's own code having to implement any of that itself. Think of it as upgrading every service's network connection to come with built-in traffic management and security, applied consistently across the whole cluster rather than reimplemented per service.

**Precise definition:** A service mesh is an infrastructure layer, typically implemented via a **sidecar proxy** (or, in newer "sidecar-less"/ambient designs, a node-level proxy) injected alongside every workload pod, that intercepts and manages all pod-to-pod network traffic within a Kubernetes cluster — providing mutual TLS (mTLS) encryption between services, fine-grained traffic splitting and routing rules, automatic retries and circuit breaking, and detailed per-service observability, independent of the application code running in each pod. On AKS, the common options are self-managed **Istio** or **Linkerd**, and the AKS-integrated **Istio-based add-on** (Azure's managed Istio offering), with **Open Service Mesh (OSM)** having been a prior Microsoft-backed option now in maintenance/deprecated status. ⚠️ Verify the current status and recommended option among these against official AKS documentation, as Microsoft's supported service mesh offering has changed over time.

## 2. Why It Exists / Problem It Solves

[Section 37](./Section-37-Part7-AKS-Networking-Scaling-Security.md) covered Ingress controllers and AGIC (Application Gateway Ingress Controller) — these solve _north-south_ traffic (external clients reaching services inside the cluster) well, but say nothing about _east-west_ traffic (services inside the cluster calling each other), which is where the majority of traffic in a genuinely microservices-based application actually flows. Without a service mesh, solving east-west concerns — encrypting service-to-service traffic, splitting traffic between two versions of a service for a canary rollout, retrying a failed call automatically, or getting a consistent latency/error-rate metric per service pair — means either building that logic into every single service's application code (duplicated effort, inconsistent implementations, and a burden on every application team) or accepting that the cluster has no answer for these concerns at all. A service mesh solves this by moving all of that logic out of application code and into a uniform, cluster-wide infrastructure layer, so any service gets mTLS, retries, and fine-grained traffic control for free simply by being part of the mesh — the same "sidecar" pattern briefly previewed for custom-container scenarios elsewhere in this Part's AKS coverage, now applied specifically to networking rather than compute.

## 3. Core Service Mesh Capabilities

### 3.1 Mutual TLS (mTLS)

**Definition:** The mesh automatically encrypts and authenticates traffic between every pod it manages, using certificates the mesh's control plane issues and rotates itself — meaning every service-to-service call inside the mesh is both encrypted and cryptographically verified as coming from a legitimate mesh-managed workload, without any application code needing to implement TLS itself.

### 3.2 Traffic Splitting & Canary Routing

**Definition:** The mesh can route a defined percentage of traffic destined for a service to a different version of that service (e.g., 95% to `v1`, 5% to `v2`) based purely on mesh configuration — enabling canary rollouts and A/B testing patterns at the traffic-routing layer, distinct from and more granular than the rolling-update mechanics of a Kubernetes Deployment itself.

### 3.3 Retries, Timeouts & Circuit Breaking

The mesh can be configured to automatically retry a failed call to a service a defined number of times, enforce request timeouts, and "circuit break" (stop sending traffic to) a service instance that's consistently failing or slow — resilience behaviors that would otherwise need to be implemented, and kept consistent, inside every calling service's own code.

### 3.4 Observability — Golden Signals Per Service Pair

Because all traffic flows through the mesh's proxies, the mesh can emit detailed, consistent metrics (request rate, error rate, latency — the "golden signals") for every service-to-service call pair in the cluster, without any application-level instrumentation — typically visualized via a service graph/topology view showing exactly how services depend on and call each other.

### 3.5 Sidecar vs. Ambient/Sidecar-less Architectures

**Sidecar model:** The traditional approach injects a proxy container into every application pod, intercepting that pod's traffic — simple to reason about per-pod, but adds per-pod resource overhead (an extra container running alongside every workload) and operational complexity (sidecar injection, upgrade coordination).

**Ambient/sidecar-less model:** Newer mesh architectures (an evolving area across the Istio/Linkerd ecosystem) move traffic interception to a shared, node-level proxy rather than one-per-pod, reducing per-pod resource overhead — ⚠️ this is an actively evolving area of the service mesh ecosystem; verify current maturity and AKS support status against official documentation before choosing an ambient-mode deployment for production.

## 4. Istio on AKS — Managed Add-on vs. Self-Managed

| Aspect                  | AKS-Managed Istio Add-on                                                               | Self-Managed Istio (or Linkerd)                                                                                   |
| ----------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Installation & upgrades | Managed by Azure as part of the AKS control plane, enabled via an AKS add-on flag      | Customer installs and upgrades the mesh's control plane themselves (via Helm or the mesh's own CLI)               |
| Version control         | Tied to Azure's supported/tested Istio versions and release cadence                    | Customer chooses and controls the exact mesh version and upgrade timing                                           |
| Support model           | Covered under Azure support as part of the AKS service                                 | Community/self-supported (or third-party commercial support if purchased separately)                              |
| Best fit                | Teams wanting mesh capabilities without taking on mesh lifecycle management themselves | Teams needing a specific mesh feature/version not yet available in the managed add-on, or preferring full control |

🎯 **Interview Tip:** A frequently tested point: enabling a service mesh is **not free** from a resource-overhead perspective — sidecar proxies (or the ambient-mode node-level proxy) consume additional CPU/memory across the cluster, and this overhead should be explicitly accounted for in node-pool sizing and the cluster autoscaler/HPA-related capacity planning covered in [Section 38](./Section-38-Part7-AKS-Production-Operations.md).6, not treated as a purely software-layer decision with no infrastructure cost.

## 5. Architecture Diagram

```
AKS Cluster
 │
 ├── Namespace "checkout" (mesh-enabled)
 │    ├── Pod: checkout-service   [App container] + [Sidecar proxy]
 │    └── Pod: checkout-service   [App container] + [Sidecar proxy]  (v2, canary — 5% traffic)
 │
 ├── Namespace "inventory" (mesh-enabled)
 │    └── Pod: inventory-service  [App container] + [Sidecar proxy]
 │
 │   (all inter-pod traffic flows sidecar → sidecar, mTLS-encrypted,
 │    with retries/circuit-breaking and metrics applied automatically)
 │
 └── Mesh Control Plane (istiod or equivalent)
       ├── Issues/rotates mTLS certificates for every sidecar
       ├── Distributes traffic-routing rules (e.g., 95/5 canary split) to sidecars
       └── Aggregates telemetry for the service-to-service observability graph

External clients ──(Ingress / AGIC, Section 37)──► Ingress Gateway ──► mesh-enabled services above
```

## 6. Configuration & Hands-On Example

**Enabling the AKS-managed Istio-based add-on and labeling a namespace for mesh injection:**

```bash
az aks mesh enable \
  --resource-group rg-aks \
  --name aks-prod

kubectl label namespace checkout istio.io/rev=asm-1-20
```

- **Purpose:** Enables Azure's managed Istio-based service mesh add-on on an existing AKS cluster, then labels the `checkout` namespace so that any pod created in it automatically gets a sidecar proxy injected — no per-pod configuration required beyond the namespace label.
- **Important arguments explained individually:**
  - `az aks mesh enable` — this specific command enables the managed add-on rather than requiring the customer to Helm-install Istio's control plane themselves; ⚠️ exact command names and supported revision labels change as the managed offering evolves — verify against current documentation.
  - `istio.io/rev=asm-1-20` — the revision label both opts the namespace into mesh injection and pins it to a specific mesh control-plane revision, allowing a controlled, namespace-by-namespace upgrade path rather than an all-or-nothing cluster-wide mesh version change.
- **Common error:** Enabling the mesh add-on without labeling any namespace results in no sidecars actually being injected anywhere — enabling the mesh control plane and opting individual namespaces into injection are two distinct, separately-required steps.

**Example traffic-splitting rule (Istio `VirtualService`, illustrative):**

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: checkout-service
spec:
  hosts:
    - checkout-service
  http:
    - route:
        - destination:
            host: checkout-service
            subset: v1
          weight: 95
        - destination:
            host: checkout-service
            subset: v2
          weight: 5
```

- **Purpose:** Defines the 95/5 canary traffic split shown in [Section 39](./Section-39-Part7-Service-Mesh-on-AKS.md).5's diagram, routed entirely at the mesh layer — no changes to application code or to the Kubernetes Service/Deployment objects themselves are required to shift this split.

## 7. Production & Enterprise Usage

Organizations running genuinely large numbers of interdependent microservices on AKS — where east-west traffic volume and complexity substantially exceed north-south traffic — adopt a service mesh specifically to get consistent mTLS, retries, and observability across every service without relying on every application team to implement these correctly and consistently themselves. Smaller AKS deployments, or those with only a handful of services and modest inter-service call complexity, often find the added operational and resource overhead of a mesh isn't yet justified, and rely on Kubernetes-native NetworkPolicies ([Section 37](./Section-37-Part7-AKS-Networking-Scaling-Security.md).4) and application-level resilience libraries instead — mirroring the same "don't reach for the heaviest tool before the scale genuinely demands it" judgment call seen elsewhere in this roadmap (e.g., Virtual WAN vs. manual hub-and-spoke, [Section 27](../Part5/Section-27-Part5-Azure-Virtual-WAN.md).7).

## 8. Security Considerations

- mTLS between services is one of the most commonly cited reasons for adopting a mesh specifically for compliance-sensitive workloads (e.g., payment processing, healthcare data) where encryption-in-transit between every internal service, not just at the cluster's external edge, is a genuine requirement rather than a nice-to-have.
- The mesh's control plane (issuing and rotating every service's mTLS certificates) becomes a high-value, high-consequence component — its own security posture (access control, certificate rotation cadence, control-plane availability) deserves the same scrutiny as any other cluster-wide security-critical system, since its compromise would undermine the mTLS guarantees for the entire mesh.

## 9. Performance Considerations

Every hop through a sidecar proxy adds a small amount of latency compared to a direct pod-to-pod call — for most workloads this overhead is negligible relative to the resilience/observability benefits gained, but latency-critical, high-throughput services should specifically benchmark mesh-enabled vs. non-mesh-enabled call latency before assuming the overhead is acceptable for their particular workload, rather than assuming it's always negligible by default. Sidecar proxy resource consumption ([Section 39](./Section-39-Part7-Service-Mesh-on-AKS.md).4's "not free" point) should be included in node-pool and HPA capacity planning ([Section 38](./Section-38-Part7-AKS-Production-Operations.md).6) rather than treated as an afterthought once the mesh is already in production.

## 10. Monitoring

Mesh-generated telemetry (the golden-signal metrics per service pair from [Section 39](./Section-39-Part7-Service-Mesh-on-AKS.md).3.4) typically flows into the same observability stack covered in Part 10 — Azure Monitor container insights and, where used, Prometheus/Grafana-based dashboards — giving operators a consistent, service-graph-level view of inter-service health layered on top of the pod/node-level metrics AKS already provides.

## 11. Troubleshooting

| Symptom                                                          | Likely Cause                                                                                                       | Fix                                                                                                                                                             |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A pod in a mesh-enabled namespace has no sidecar container       | Pod was created before the namespace was labeled for injection, or the label is missing/incorrect                  | Verify the namespace injection label, then restart/recreate the affected pods so injection applies                                                              |
| Traffic-splitting rule has no effect                             | Routing rule (e.g., `VirtualService`) references a subset/version label that doesn't match the actual pod labels   | Verify the `DestinationRule`/subset labels exactly match the labels on the deployed pods                                                                        |
| Noticeable latency increase after enabling the mesh cluster-wide | Sidecar proxy overhead not accounted for, or overly aggressive retry/timeout configuration causing cascading delay | Benchmark mesh-enabled latency specifically ([Section 39](./Section-39-Part7-Service-Mesh-on-AKS.md).9); review retry/timeout policy for excessive retry counts |

## 12. Interview Questions — [Section 39](./Section-39-Part7-Service-Mesh-on-AKS.md)

### 🎯 Intermediate

**Q: What's the difference between what an Ingress controller/AGIC ([Section 37](./Section-37-Part7-AKS-Networking-Scaling-Security.md)) handles and what a service mesh handles?**

_Model answer:_ Ingress controllers and AGIC manage north-south traffic — external clients reaching services inside the cluster from outside. A service mesh manages east-west traffic — how services inside the cluster call each other — providing mTLS encryption, traffic splitting, retries/circuit breaking, and per-service-pair observability for that internal traffic. The two are complementary, not competing: a typical production architecture uses an Ingress controller/AGIC at the edge and a service mesh for internal service-to-service communication, as shown in [Section 39](./Section-39-Part7-Service-Mesh-on-AKS.md).5's diagram.

_What the interviewer is probing:_ whether the candidate correctly distinguishes north-south from east-west traffic concerns, rather than conflating "traffic management on Kubernetes" into a single undifferentiated concept.

### 🎯 Senior/Architect

**Q: A team wants to adopt a service mesh primarily to get mTLS between all their microservices for a compliance requirement. They're concerned about the operational overhead of running Istio themselves. How would you advise them?**

_Model answer:_ Given the primary driver is a compliance requirement for encryption-in-transit rather than a need for advanced traffic-splitting or resilience features, I'd first confirm whether AKS's managed Istio-based add-on meets their needs — since it shifts mesh control-plane installation, upgrades, and support to Azure, directly addressing their operational-overhead concern, and mTLS is a core, well-supported capability of the managed offering rather than an advanced edge-case feature. I'd size the node pools to account for the sidecar proxy resource overhead ([Section 39](./Section-39-Part7-Service-Mesh-on-AKS.md).4/39.9) before rollout, and start injection on a single non-critical namespace first to validate latency impact and correct behavior before labeling every namespace cluster-wide. I'd also make sure the team understands that adopting the mesh doesn't remove the need for Kubernetes-native NetworkPolicies ([Section 37](./Section-37-Part7-AKS-Networking-Scaling-Security.md).4) — mTLS provides encryption and identity verification for traffic that's already permitted to flow; network policy still controls which traffic is permitted to flow in the first place, and the two should be used together rather than treating the mesh as a full substitute for network-layer segmentation.

_What the interviewer is probing:_ whether the candidate can map a specific business driver (compliance-mandated mTLS) to the right-sized solution (the managed add-on, rather than defaulting to self-managed Istio or over-engineering with unneeded advanced features), account for the genuine operational/resource costs involved, and correctly distinguish mTLS from network-policy-based segmentation rather than treating a mesh as a complete security solution on its own.

## 13. Common Misconceptions

- **"A service mesh is required for any production AKS cluster."** False — many production clusters run successfully without one; a mesh is justified when east-west traffic complexity, compliance-mandated mTLS, or fine-grained traffic-shaping needs are genuine requirements, not as a default best practice applied regardless of scale.
- **"mTLS from a service mesh makes Kubernetes NetworkPolicies ([Section 37](./Section-37-Part7-AKS-Networking-Scaling-Security.md).4) unnecessary."** False — mTLS encrypts and authenticates traffic that's already permitted to flow between pods; NetworkPolicies control which traffic is permitted to flow in the first place. The two operate at different layers and are typically used together, not as substitutes for one another.

## 14. Key Takeaways

- 🔑 A service mesh manages east-west (service-to-service) traffic inside a cluster — mTLS, traffic splitting, retries/circuit breaking, and per-service observability — complementing rather than replacing Ingress/AGIC's north-south traffic handling ([Section 37](./Section-37-Part7-AKS-Networking-Scaling-Security.md)).
- 🔑 Sidecar proxies (or newer ambient/sidecar-less architectures) intercept pod traffic to provide these capabilities uniformly, without requiring every application to implement them in its own code.
- 🔑 AKS offers a managed Istio-based add-on that shifts mesh control-plane installation and upgrades to Azure, versus self-managing Istio/Linkerd directly for full version control.
- 🔑 Mesh adoption has genuine resource overhead (sidecar CPU/memory across every pod) and should be factored into node-pool and autoscaler capacity planning ([Section 38](./Section-38-Part7-AKS-Production-Operations.md).6), not treated as free.
- 🔑 mTLS from a mesh and Kubernetes NetworkPolicies address different concerns (encryption/identity vs. permitted traffic) and are typically deployed together rather than as alternatives.

## 15. Related Concepts / Part 7 Wrap-Up

This completes **Part 7 — Containers & Orchestration**, covering Docker fundamentals, Azure Container Registry, AKS architecture, AKS networking/scaling/security (including Ingress/AGIC), AKS production operations, and now service mesh for advanced east-west traffic management — the full container orchestration foundation for running microservices on Azure. **Part 8 — Serverless & Integration** begins next with [Section 40](../Part8/Section-40-Part8-Azure-Functions-Deep-Dive.md), covering Azure Functions in depth, shifting from container-based compute to event-driven serverless compute as an alternative (or complementary) execution model for the same kinds of workloads.
