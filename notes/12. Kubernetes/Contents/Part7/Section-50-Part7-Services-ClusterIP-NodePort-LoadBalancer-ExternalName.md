# Section 50 (Part 7): Services: ClusterIP, NodePort, LoadBalancer, ExternalName

## 1. Definition

**Plain language:** Pods are mortal — they get rescheduled, replaced, and get new IPs every time. If every client had to track individual Pod IPs directly, nothing would work reliably for more than a few minutes. A Service gives a group of Pods a single, stable address that doesn't change even as the Pods behind it come and go.

**Precise definition:** A **Service** is a Kubernetes API object that defines a stable network identity (a virtual IP and/or DNS name) for a set of Pods selected by a **label selector**, and continuously updates its backing **Endpoints** (or **EndpointSlices**) as matching Pods are created, replaced, or removed. Four **Service types** exist: **ClusterIP** (the default — a stable virtual IP reachable only from inside the cluster, proxied by kube-proxy per §48's flat network), **NodePort** (additionally opens a static port on every node's IP, forwarding to the ClusterIP), **LoadBalancer** (additionally provisions an external cloud load balancer that targets the NodePort/ClusterIP, requiring cloud-controller-manager integration), and **ExternalName** (a special type that performs **no proxying or selection at all** — it is purely a DNS **CNAME** record pointing a Kubernetes-internal name to an external DNS name, with no virtual IP, no Endpoints, and no kube-proxy involvement whatsoever).

## 2. Why This Matters

- **Services are the abstraction that makes Pod mortality invisible to clients.** Because a Deployment's Pods (§29) are constantly replaced during rollouts (§30) and rescheduling, without a Service's stable virtual IP every client would need its own logic to track which Pod IPs are currently valid — Services push that complexity into one place, enforced by kube-proxy (§9, mechanics in §51).
- **ExternalName is qualitatively different from the other three types, not just "another option on the list."** ClusterIP, NodePort, and LoadBalancer all proxy real traffic to real Pod Endpoints; ExternalName does neither — it's pure DNS redirection with no health checking, no load balancing, and no Endpoints object at all, a distinction that trips up engineers who assume all four types behave similarly.
- **Services alone don't solve HTTP-layer routing needs** (host/path-based routing, TLS termination, request rewriting) — that's the explicit reason Ingress (§53) exists as a layer above Services, a gap worth understanding clearly rather than trying to force a Service to do a routing job it isn't designed for.

🔑 **Key Takeaway:** A Service gives a set of Pods a stable identity that survives individual Pod churn, with ClusterIP/NodePort/LoadBalancer forming a nested progression of exposure scope (internal → per-node → external load balancer) all backed by real proxying, while ExternalName stands apart as a DNS-only alias with no proxying behavior whatsoever.

## 3. Prerequisites and Dependencies

Builds on §48 (the flat Pod network Services are proxied across) and §29 (Deployments, whose Pods a Service typically selects via labels from §27).

## 4. Architecture Diagram

```text
   ClusterIP (default)                    NodePort (superset of ClusterIP)
   ┌────────────────────────┐               ┌──────────────────────────────┐
   │ Client (in-cluster)    │               │ External client              │
   │        │               │               │        │                     │
   │        ▼               │               │        ▼                     │
   │  ClusterIP: 10.96.5.5  │               │  NodeIP:30080 (every node)   │
   │  (virtual, stable)     │               │        │                     │
   │        │ kube-proxy    │               │        ▼                     │
   │        ▼ rules         │               │  ClusterIP: 10.96.5.5 (same) │
   │  ┌─────┐ ┌─────┐       │               │        │ kube-proxy rules    │
   │  │ Pod │ │ Pod │       │               │        ▼                     │
   │  └─────┘ └─────┘       │               │  ┌─────┐ ┌─────┐             │
   └────────────────────────┘               │  │ Pod │ │ Pod │             │
                                            │  └─────┘ └─────┘             │
                                            └──────────────────────────────┘

   LoadBalancer (superset of NodePort)      ExternalName (no proxying at all)
   ┌────────────────────────────────┐        ┌──────────────────────────────┐
   │ External client                │        │ Client (in-cluster)          │
   │        │                       │        │        │                     │
   │        ▼                       │        │        ▼  DNS query only     │
   │  Cloud Load Balancer           │        │  my-svc.namespace.svc        │
   │  (provisioned via cloud-       │        │        │  CNAME              │
   │   controller-manager)          │        │        ▼                     │
   │        │                       │        │  external-db.example.com     │
   │        ▼                       │        │  (resolved directly by DNS,  │
   │  NodePort: 30080 (every node)  │        │   client connects there —    │
   │        │                       │        │   no kube-proxy involvement) │
   │        ▼                       │        └──────────────────────────────┘
   │  ClusterIP → Pods (as above)   │
   └────────────────────────────────┘
```

- **Each type is a strict superset of the one before it** (except ExternalName): NodePort includes a ClusterIP; LoadBalancer includes a NodePort. This is why `kubectl get svc` on a LoadBalancer-type Service still shows a `CLUSTER-IP` and a node port allocated, in addition to the external IP.
- **ExternalName never allocates a ClusterIP, never creates Endpoints, and never involves kube-proxy** — CoreDNS (§52) resolves the Service name directly to a CNAME pointing at the external hostname, and the client's own DNS resolver/HTTP client handles the rest.

## 5. Hands-On: Creating and Verifying Each Service Type

### 5.1 ClusterIP — Internal-Only Stable Access

**Purpose:** Give a set of Pods a stable, in-cluster-only address, the default and most common Service type.

**Syntax:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend-svc
spec:
  type: ClusterIP # default; can be omitted
  selector:
    app: backend
  ports:
    - port: 80
      targetPort: 8080
```

**Example usage and expected output:**

```bash
$ kubectl apply -f backend-svc.yaml
service/backend-svc created

$ kubectl get svc backend-svc
NAME          TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)   AGE
backend-svc   ClusterIP   10.96.44.12   <none>        80/TCP    5s

$ kubectl get endpoints backend-svc
NAME          ENDPOINTS
backend-svc   10.244.1.5:8080,10.244.2.7:8080
```

**Production usage example:** An internal microservice (e.g., a `backend` API only ever called by other in-cluster services, never directly by external clients) is almost always exposed as ClusterIP — there's no reason to widen its exposure beyond the cluster, and doing so unnecessarily would expand attack surface for no benefit.

**Common errors:** An empty `ENDPOINTS` list despite `Running` Pods almost always means the Service's `selector` labels don't actually match the Pods' labels — the single most common Service misconfiguration; verify with `kubectl get pods --show-labels` against the Service's `spec.selector`.

### 5.2 NodePort — Exposing via Every Node's IP

**Purpose:** Additionally expose the Service on a static port on every node's IP, typically used when an external load balancer isn't available (on-prem, local dev) or as the underlying mechanism a LoadBalancer type builds on.

**Syntax:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web-svc
spec:
  type: NodePort
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 8080
      nodePort: 30080 # optional; auto-assigned from 30000-32767 if omitted
```

**Example usage and expected output:**

```bash
$ kubectl apply -f web-svc.yaml
service/web-svc created

$ kubectl get svc web-svc
NAME      TYPE       CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
web-svc   NodePort   10.96.88.20    <none>        80:30080/TCP   3s

$ curl http://<any-node-ip>:30080/
```

**Production usage example:** On-premises clusters without an integrated cloud load balancer commonly use NodePort behind a hand-configured external load balancer or reverse proxy that targets every node's IP on the assigned port — a manual version of what LoadBalancer-type automates on supported cloud platforms.

**Common errors:** Reaching `<node-ip>:<nodePort>` works even when hitting a node that has _no_ matching Pods running locally — traffic is still correctly forwarded to a Pod on another node via kube-proxy's rules (§51), which surprises engineers expecting node-local-only routing.

### 5.3 LoadBalancer — Cloud-Provisioned External Access

**Purpose:** Automatically provision a cloud load balancer that fronts the Service, the standard way to expose a Service to the public internet on managed cloud Kubernetes.

**Syntax:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: public-web-svc
spec:
  type: LoadBalancer
  selector:
    app: web
  ports:
    - port: 443
      targetPort: 8443
```

**Example usage and expected output:**

```bash
$ kubectl apply -f public-web-svc.yaml
service/public-web-svc created

$ kubectl get svc public-web-svc
NAME             TYPE           CLUSTER-IP    EXTERNAL-IP       PORT(S)        AGE
public-web-svc   LoadBalancer   10.96.99.30   <pending>         443:31443/TCP  10s

$ kubectl get svc public-web-svc   # after cloud provisioning completes
NAME             TYPE           CLUSTER-IP    EXTERNAL-IP        PORT(S)        AGE
public-web-svc   LoadBalancer   10.96.99.30   34.120.55.10       443:31443/TCP  90s
```

**Production usage example:** A public-facing API Gateway Service on EKS/AKS/GKE requests `type: LoadBalancer`, and cloud-controller-manager (§8) provisions a real cloud load balancer (an AWS NLB/ALB, Azure Load Balancer, or GCP Load Balancer respectively) — the `EXTERNAL-IP` transitions from `<pending>` to a real address once cloud provisioning completes, which can take anywhere from seconds to a couple of minutes.

**Common errors:** `EXTERNAL-IP` stuck permanently on `<pending>` on a self-managed (kubeadm) cluster is expected, not a bug — there's no cloud-controller-manager to provision anything; this Service type only functions fully on managed cloud Kubernetes or with a self-hosted cloud-integration controller (e.g., MetalLB) installed.

### 5.4 ExternalName — DNS-Only Alias to an External Service

**Purpose:** Give in-cluster Pods a Kubernetes-internal DNS name that resolves, via CNAME, to an external service — with no proxying, no health checks, and no Endpoints at all.

**Syntax:**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: external-db
spec:
  type: ExternalName
  externalName: prod-db.us-east-1.rds.amazonaws.com
```

**Example usage and expected output:**

```bash
$ kubectl apply -f external-db-svc.yaml
service/external-db created

$ kubectl get svc external-db
NAME          TYPE           CLUSTER-IP   EXTERNAL-IP                          PORT(S)   AGE
external-db   ExternalName   <none>       prod-db.us-east-1.rds.amazonaws.com   <none>    5s

$ kubectl exec -it some-pod -- nslookup external-db.default.svc.cluster.local
Server:    10.96.0.10
Name:      external-db.default.svc.cluster.local
Aliases:   prod-db.us-east-1.rds.amazonaws.com
```

**Production usage example:** An application migrating from a hardcoded external database hostname to Kubernetes uses an ExternalName Service as an abstraction seam — application code refers only to `external-db.default.svc.cluster.local`, and platform teams can later swap `externalName` to point at a different backend (or eventually replace it with a real in-cluster Service) without any application code change.

**Common errors:** Assuming ExternalName Services support port remapping, health checks, or load balancing across multiple backends the way the other three types do — none of that applies; it is exactly and only a CNAME record, resolved once by DNS, with the client's own networking stack handling everything past that point (including whatever TLS/port behavior the external endpoint itself expects).

## 6. Production Usage Notes

- **`kubectl get endpoints` (or `kubectl get endpointslices` on newer clusters) is the fastest way to confirm a Service is actually backed by healthy Pods** — a Service object existing correctly doesn't guarantee its selector is matching anything; this is the single most useful first diagnostic for "Service isn't working" reports.
- **NodePort's default range (30000-32767) is a real constraint on very large clusters** running many NodePort/LoadBalancer Services — exhausting the range is a real, if uncommon, operational limit worth knowing about.
- **LoadBalancer-type Services provision real, billed cloud infrastructure per Service** by default on most cloud providers — teams commonly consolidate multiple HTTP-based backends behind a single Ingress (§53) fronted by one LoadBalancer Service, rather than provisioning one expensive cloud load balancer per backend.
- **ExternalName's total absence of health checking means a failing external endpoint produces no Kubernetes-visible signal at all** — from the cluster's perspective the ExternalName Service always looks fine, since it never proxies traffic or tracks Endpoint health; monitoring the actual external dependency requires separate, external-facing checks.

## 7. Security Considerations

- **NodePort exposes a port on every node's IP by default**, which — absent host firewalling or security groups restricting that port range — can inadvertently expose a Service more broadly than intended, since it bypasses any Ingress-layer access controls entirely.
- **ExternalName Services are a notable, sometimes-overlooked DNS exfiltration/redirection vector**: because they resolve purely by DNS with no validation of the target, a compromised or careless ExternalName Service definition can silently redirect traffic intended for a legitimate external service to an unintended destination — RBAC controlling who can create/modify Service objects (Part 10) matters as much for this type as for any other.
- **LoadBalancer-type Services often default to accepting traffic from `0.0.0.0/0`** unless `spec.loadBalancerSourceRanges` (or the cloud provider's equivalent annotation) is explicitly set — a common misconfiguration that exposes a Service more broadly than the application actually requires.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                    | Resolution Path                                                                                               |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Service exists but `kubectl get endpoints` shows nothing         | Service `selector` doesn't match any Pod's labels                               | Compare `spec.selector` against `kubectl get pods --show-labels`; fix label mismatch                          |
| NodePort/LoadBalancer reachable but connections time out         | Node firewall / cloud security group blocking the node port or LB's target port | Verify security group/firewall rules allow the specific NodePort range or LB target port                      |
| LoadBalancer `EXTERNAL-IP` stuck on `<pending>` indefinitely     | Self-managed cluster with no cloud-controller-manager (or MetalLB) installed    | Confirm cloud integration is actually present; on bare self-managed clusters, use NodePort or install MetalLB |
| ExternalName Service's traffic goes to an unexpected destination | `externalName` field misconfigured or pointing at a stale/incorrect hostname    | Review the Service's `spec.externalName` value directly; treat it with the same change control as DNS records |

## 9. Best Practices

- Default to ClusterIP for anything not genuinely needing external exposure, and prefer routing external HTTP/HTTPS traffic through a single Ingress (§53) rather than provisioning a LoadBalancer Service per backend.
- Always verify `kubectl get endpoints` after creating or modifying a Service's selector or a Pod's labels — a mismatched selector is silent (no error) but produces a completely non-functional Service.
- Set `loadBalancerSourceRanges` (or equivalent) explicitly on any LoadBalancer-type Service that shouldn't be open to the entire internet, rather than relying on the cloud provider's permissive default.

## 10. Common Anti-Patterns / Mistakes

- **Assuming ExternalName Services proxy or load-balance traffic like the other three types** — it is DNS-only, with none of the health-checking or routing behavior engineers reasonably expect from "a Service."
- **Provisioning one LoadBalancer-type Service per backend microservice** instead of consolidating HTTP-based services behind a single Ingress, needlessly multiplying cloud load balancer cost and count.
- **Treating a successfully created Service object as proof the Service is working**, without checking `kubectl get endpoints` to confirm it's actually backed by matching, healthy Pods.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between ClusterIP, NodePort, and LoadBalancer Service types?"_
**Model answer:** ClusterIP gives a Service a stable virtual IP reachable only from inside the cluster — it's the default. NodePort does everything ClusterIP does, plus opens the same port on every node's real IP, making it reachable from outside the cluster via any node's address. LoadBalancer does everything NodePort does, plus asks the cloud provider to provision an actual external load balancer that targets that NodePort — each type is a superset of the previous one.
_What the interviewer is probing for:_ Correct understanding of the nested, nothing-removed progression between the three, not just memorized separate definitions.

**🎯 Intermediate:** _"How is an ExternalName Service fundamentally different from the other three Service types?"_
**Model answer:** ClusterIP, NodePort, and LoadBalancer all involve real proxying — they allocate a virtual IP or port, maintain an Endpoints object tracking healthy backing Pods, and kube-proxy actively routes traffic to those Pods. ExternalName does none of that: it never gets a ClusterIP, never has Endpoints, and never involves kube-proxy at all — it's purely a CNAME DNS record that CoreDNS resolves, pointing an in-cluster name at an external hostname. There's no health checking or load balancing; the client's own DNS resolution and networking stack handle everything after the CNAME resolves.
_What the interviewer is probing for:_ Whether the candidate understands ExternalName is categorically different, not just "another exposure level," since this misunderstanding leads to wrongly expecting health-check or load-balancing behavior from it.

**🎯 Senior:** _"A Service's Pods are healthy and `Running`, but `kubectl get endpoints` shows an empty list. Walk through your diagnosis."_
**Model answer:** An empty Endpoints list with healthy Pods almost always means the Service's label selector isn't matching those Pods — I'd immediately compare `kubectl get svc <name> -o yaml`'s `spec.selector` against the actual labels on the target Pods via `kubectl get pods --show-labels`, looking specifically for a typo, a stale selector left over from a refactor, or a readiness-probe failure (Pods that are `Running` but not `Ready` are excluded from Endpoints even with a correct selector). If the selector and labels genuinely match and Pods are both Running and Ready, I'd next check for a Pod-count-zero race right after a rolling update, or a namespace mismatch if the Service and Pods were assumed to be co-located but aren't. This is deliberately the first thing I check before touching networking infrastructure at all, since a Service/label mismatch is far more common than an actual networking fault.
_What the interviewer is probing for:_ Structured elimination that correctly prioritizes the most statistically common cause (selector/label mismatch, readiness state) before assuming a deeper infrastructure problem.

**🎯 Architect:** _"You're designing external exposure strategy for a platform with 60 HTTP-based microservices needing public access, plus 3 services needing raw TCP (non-HTTP) exposure. How do you use Service types and Ingress together, and what are you optimizing for?"_
**Model answer:** For the 60 HTTP-based services, I'd expose none of them directly as LoadBalancer-type — instead, each gets a ClusterIP Service, and a single Ingress resource (§53) fronted by one shared LoadBalancer-type Service (the Ingress controller's own Service) handles host/path-based routing to all 60, since LoadBalancer Services provision real, billed cloud infrastructure per Service and 60 separate cloud load balancers would be both expensive and operationally unwieldy to manage TLS/DNS for individually. For the 3 raw-TCP services, since Ingress is fundamentally an HTTP/HTTPS-layer abstraction (§53) and doesn't apply to arbitrary TCP protocols, I'd expose those specifically as LoadBalancer-type Services directly (or via a TCP-aware Ingress controller extension where supported), accepting the additional cloud load balancer cost for those few cases since there's no equivalent consolidation option at the Service layer for non-HTTP traffic. The overall optimization is minimizing both cloud cost and DNS/TLS-certificate management surface by consolidating everything that genuinely can share a single entry point (HTTP/HTTPS traffic) while accepting dedicated exposure only where the protocol genuinely requires it.
_What the interviewer is probing for:_ Whether the candidate can architect a cost- and operationally-aware exposure strategy that correctly distinguishes what Ingress can and can't handle, rather than defaulting to "LoadBalancer everything" or "Ingress everything" without justification.

## 12. Common Misconceptions

1. **"ExternalName Services proxy traffic like ClusterIP does."** ExternalName performs no proxying whatsoever — it's a DNS CNAME only; the other three types all involve real kube-proxy-managed traffic routing to Endpoints.
2. **"NodePort only routes to Pods running on the node you connect to."** kube-proxy forwards NodePort traffic to any healthy backing Pod cluster-wide, not just Pods local to the node you happened to connect through.
3. **"LoadBalancer-type Services work identically on any cluster."** They require cloud-controller-manager (or a self-hosted equivalent like MetalLB) to actually provision anything; on a bare self-managed cluster without that integration, `EXTERNAL-IP` stays `<pending>` indefinitely.
4. **"A Service existing and looking correctly configured means it's working."** A Service can be perfectly well-formed and still be completely non-functional if its selector doesn't match any Pod's labels — always verify via `kubectl get endpoints`.

## 13. 🔑 Key Takeaways

- Services give a set of Pods a stable identity that survives individual Pod replacement, resolving the mismatch between mortal Pods and clients that need a consistent address.
- ClusterIP, NodePort, and LoadBalancer form a strict nested progression (internal-only → per-node → cloud-provisioned external), each a superset of the one before.
- ExternalName is categorically different — a pure DNS CNAME with no virtual IP, no Endpoints, no health checking, and no kube-proxy involvement at all.
- `kubectl get endpoints` is the essential verification step for any Service — a well-formed Service object with a mismatched selector produces no error but zero actual functionality.
- Services alone don't provide HTTP-layer routing (host/path rules, TLS termination) — that gap is exactly why Ingress (§53) exists as a layer above them.

## 14. Related Concepts & What's Next

§48 established the flat Pod network Services are proxied across, and §9 introduced kube-proxy at a high level; §51 goes deep on exactly how kube-proxy implements the ClusterIP/NodePort/LoadBalancer routing described here through its iptables and IPVS modes. §53 (Ingress) picks up where Services alone stop being sufficient, adding HTTP-layer host/path routing and TLS termination on top of the Service abstraction covered in full here.

**Next Section:** §51 — `Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md`
