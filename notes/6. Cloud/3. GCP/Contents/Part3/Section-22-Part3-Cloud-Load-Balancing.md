# Section 22 (Part 3): Cloud Load Balancing (All Types)

## 1. Definition

**Plain language:** Cloud Load Balancing is Google's family of load balancers that spread incoming traffic across many backend servers, so no single server is overwhelmed and traffic keeps flowing even if some backends fail. Unlike most clouds, GCP offers a single unified software-defined load balancing layer built on Google's own global network and the same technology (Envoy-based proxying) that powers Google's own production services like Search and YouTube.

- **Precise:** **Cloud Load Balancing** is a fully-distributed, software-defined load balancing service offered in multiple product variants distinguished along two axes — **scope** (global vs. regional) and **traffic type** (external vs. internal, and Layer 4/TCP-UDP vs. Layer 7/HTTP(S)) — all provisioned via a common forwarding-rule/backend-service/health-check model rather than as separate standalone appliances.

## 2. Why It Exists / Problem It Solves

A single server (or even a single-zone fleet of servers) cannot reliably absorb internet-scale traffic or survive a zone/region failure. Load balancing solves availability (routing away from unhealthy backends), scalability (spreading load across many backends, auto-scaling with them), and, for global variants, latency (routing users to the nearest healthy region). GCP's specific architectural choice — building load balancing as a software-defined layer on Google's global network edge, rather than as a fleet of dedicated proxy VMs you provision — means even the "global" load balancer variants can front traffic entering at over 100 points of presence worldwide and route it over Google's private backbone to the nearest healthy backend, without you managing any proxy infrastructure.

## 3. Core Concepts

### 3.1 The Unified Load Balancing Model

Every Cloud Load Balancing product shares the same conceptual pieces: a **forwarding rule** (the IP + port that receives traffic), one or more **backend services** or **backend buckets** (the pool of backends and their health checks), and, for HTTP(S) types, **URL maps** (routing traffic to different backend services based on host/path). What differs between variants is scope (global vs. regional) and protocol layer (Layer 4 vs Layer 7) — not the fundamental configuration model.

### 3.2 Global External HTTP(S) Load Balancer

Terminates HTTP(S) traffic at Google's global edge (anycast IP — one IP address advertised from every edge PoP simultaneously), then routes each request over Google's private backbone to the closest healthy backend across any region. Supports advanced Layer 7 features: URL-path-based routing, host-based routing, SSL offload, Cloud CDN integration, and Cloud Armor (WAF/DDoS, Section 74) integration. Used for internet-facing web applications and APIs that need global reach with a single anycast IP.

### 3.3 Global External TCP/SSL Proxy Load Balancer

Also uses a single global anycast IP entering at the edge, but operates at Layer 4 (TCP) or performs SSL termination without HTTP-aware routing — for non-HTTP TCP/SSL traffic (e.g., custom TCP protocols, some database front-ends) that still benefits from a global anycast entry point and Google's backbone routing.

### 3.4 Regional External Load Balancers

Includes the **regional external Application Load Balancer** (HTTP(S), regional scope) and the **external passthrough Network Load Balancer** (Layer 4, regional, preserves client source IP all the way to the backend — "passthrough" because it does not proxy/terminate the connection). Used when traffic and backends are confined to a single region by design (e.g., regulatory data-residency requirements, or simply an application that doesn't need global reach) or when the raw client-IP-preservation of a passthrough Network LB is required.

### 3.5 Internal Load Balancers

Includes the **Internal HTTP(S) Load Balancer** (Layer 7, regional, for east-west microservice traffic within a VPC, or reachable via Shared VPC/PSC) and the **internal passthrough Network Load Balancer** (Layer 4, regional, no public IP at all). These never expose a public IP; they load-balance traffic entirely within private VPC space, commonly used for internal microservice-to-microservice or internal-app-tier traffic that must never be reachable from the internet.

## 4. Comparison Table by Layer and Scope

| Load Balancer Type               | Layer       | Scope            | Public/Internal | Typical Use Case                                             |
| -------------------------------- | ----------- | ---------------- | --------------- | ------------------------------------------------------------ |
| Global external HTTP(S) LB       | 7           | Global (anycast) | Public          | Internet-facing web apps/APIs needing global reach, CDN, WAF |
| Global external TCP/SSL Proxy LB | 4 (TCP/SSL) | Global (anycast) | Public          | Non-HTTP TCP/SSL traffic needing global anycast entry        |
| Regional external Application LB | 7           | Regional         | Public          | Region-confined HTTP(S) apps (compliance/data-residency)     |
| External passthrough Network LB  | 4           | Regional         | Public          | Raw TCP/UDP, client-source-IP preservation required          |
| Internal HTTP(S) LB              | 7           | Regional         | Internal only   | East-west microservice HTTP(S) traffic within a VPC          |
| Internal passthrough Network LB  | 4           | Regional         | Internal only   | East-west raw TCP/UDP traffic, no public exposure ever       |

## 5. Architecture Diagram

```
                       INTERNET USERS (worldwide)
                                │
                                ▼
              ┌───────────────────────────────────┐
              │  Global anycast IP (one IP,       │
              │  advertised from 100+ edge PoPs)  │
              │  Global External HTTP(S) LB       │
              └───────────────────────────────────┘
                   │                        │
     ┌─────────────┘                        └─────────────┐
     ▼                                                    ▼
REGION: us-central1                               REGION: europe-west1
┌───────────────────────┐                         ┌───────────────────────┐
│ Backend Service       │                         │ Backend Service       │
│ (MIG, health-checked) │                         │ (MIG, health-checked) │
└───────────────────────┘                         └───────────────────────┘
     │
     ▼ (internal, east-west, no public IP)
┌───────────────────────┐
│ Internal HTTP(S) LB   │──► App-tier backend service (regional, private)
└───────────────────────┘
```

## 6. Comparison: GCP Cloud Load Balancing vs AWS ELB Family vs Azure Load Balancing

| GCP                              | AWS Equivalent                               | Azure Equivalent                             | Notes                                                                                                                                      |
| -------------------------------- | -------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Global external HTTP(S) LB       | CloudFront + ALB (combined)                  | Azure Front Door                             | GCP achieves global anycast HTTP(S) as one native product; AWS composes two services, Azure Front Door is the closer single-product analog |
| Global external TCP/SSL Proxy LB | Network Load Balancer + CloudFront (partial) | Azure Front Door (limited) / Traffic Manager | GCP's global TCP anycast has no single direct AWS equivalent                                                                               |
| Regional external Application LB | Application Load Balancer (ALB)              | Application Gateway                          | Closest like-for-like regional Layer 7 comparison                                                                                          |
| External passthrough Network LB  | Network Load Balancer (NLB)                  | Azure Load Balancer (public)                 | Both preserve client source IP, Layer 4                                                                                                    |
| Internal HTTP(S) LB              | Internal ALB                                 | Internal Application Gateway                 | Regional, private Layer 7                                                                                                                  |
| Internal passthrough Network LB  | Internal NLB                                 | Azure Load Balancer (internal)               | Regional, private Layer 4                                                                                                                  |

> ⚠️ **Interview-relevant nuance:** GCP's global load balancers are a genuinely distinctive architectural advantage — a single anycast IP address serving global traffic natively, with no separate CDN-layer product required to get global anycast entry, unlike AWS's typical CloudFront+ALB composition.

## 7. Hands-On Examples

**Beginner — reserve a global static IP for a global HTTP(S) LB:**

```bash
gcloud compute addresses create web-global-ip --global
```

_Purpose:_ Reserves a stable global anycast IP address to attach to a global forwarding rule, so the public-facing address doesn't change across backend/config updates.

**Expected output:**

```
Created [https://www.googleapis.com/compute/v1/projects/my-project/global/addresses/web-global-ip].
```

**Intermediate — create a backend service and check backend health:**

```bash
gcloud compute backend-services create web-backend-service \
  --global \
  --protocol=HTTP \
  --health-checks=web-health-check \
  --port-name=http

gcloud compute backend-services get-health web-backend-service --global
```

_Purpose:_ Creates a global backend service tied to a health check, then confirms which backend instances are currently reporting healthy — the standard first troubleshooting step when a load balancer returns 502 errors.

**Expected output:**

```
---
backend: .../instanceGroups/web-mig-us-central1
status:
  healthStatus:
  - healthState: HEALTHY
    instance: .../instances/web-mig-us-central1-abcd
```

## 8. Production & Enterprise Usage

- **Global HTTP(S) LB as the default front door** for internet-facing enterprise applications spanning multiple regions, paired with Cloud CDN for static content and Cloud Armor for WAF/DDoS protection (Section 74).
- **Internal HTTP(S) LB for service-mesh-adjacent microservice traffic**, often as a stepping stone before or alongside a full service mesh via Traffic Director (Section 27).
- **Regional external LBs for regulated workloads** where data-residency or compliance requirements dictate all traffic (including load balancer entry) must terminate within one specific region/country, rather than at a global edge PoP that could be anywhere.
- **Passthrough Network LBs for legacy or non-HTTP protocols** and any scenario where the backend application itself must see the true client source IP (e.g., IP-based access control logic inside the application).

## 9. Common Misconceptions

- **Misconception:** "GCP's 'global' load balancer just means it's reachable globally, like any public IP." It specifically means the **same IP address is simultaneously advertised from every Google edge PoP worldwide** (anycast), and Google's network — not the public internet — carries the request from the edge to the nearest healthy regional backend.
- **Misconception:** "You need CDN for global reach." Cloud CDN is a distinct caching layer that can be enabled on top of a Global External HTTP(S) LB; the LB's global anycast reach exists independently of whether CDN caching is turned on.

## 10. Interview Questions

**🎯 Beginner:** _What's the fundamental difference between a global and a regional load balancer in GCP?_
**Model answer:** A global load balancer uses a single anycast IP address advertised from all of Google's edge points of presence worldwide, with traffic routed over Google's private backbone to the nearest healthy backend in any region — enabling one IP to serve a worldwide audience with automatic nearest-region routing. A regional load balancer's IP and traffic entry point are confined to a single region, appropriate when backends, traffic, or compliance requirements are intentionally scoped to one region.

**🎯 Intermediate:** _When would you choose a passthrough Network Load Balancer over an Application Load Balancer?_
**Model answer:** When the protocol isn't HTTP(S) (e.g., a custom TCP protocol or non-HTTP database traffic), when the backend application needs to see the true client source IP address for its own logic (passthrough LBs don't terminate/proxy the connection), or when ultra-low latency Layer 4 forwarding is preferred over Layer 7 features like URL-based routing, which aren't needed for the workload.

**🎯 Senior/Architect:** _Design the load balancing layer for a global e-commerce platform: public web/API traffic worldwide, an internal microservices layer, and a subset of traffic requiring EU-only data residency._
**Model answer:** For the public web/API tier, I'd use a Global External HTTP(S) LB with a single anycast IP, Cloud CDN for cacheable static assets, and Cloud Armor in front for WAF/DDoS protection, using URL maps to route by path to different backend services across regions. For internal microservice-to-microservice traffic, I'd use Internal HTTP(S) Load Balancers per region (no public IP), potentially evolving toward Traffic Director-managed service mesh (Section 27) as the microservice count grows. For the EU-data-residency-constrained subset of traffic, I'd deploy a separate Regional External Application Load Balancer confined to an EU region, ensuring both the load balancer's entry point and its backends stay within the required jurisdiction, rather than relying on the global LB's anycast entry (which could technically accept the connection at a non-EU edge PoP before routing it, which may itself be a residency concern requiring VPC Service Controls (Section 41) evaluation).

## 11. Key Takeaways

- 🔑 All Cloud Load Balancing products share one configuration model (forwarding rule, backend service, health check); they differ by scope (global vs regional) and layer (HTTP(S) Layer 7 vs TCP/SSL Layer 4).
- 🔑 Global load balancers use true anycast — one IP advertised from every edge PoP — routing over Google's private backbone to the nearest healthy region, natively, with no separate CDN product required for global reach.
- 🔑 Passthrough Network Load Balancers preserve the original client source IP and don't proxy/terminate the connection, unlike proxy-based HTTP(S) and TCP/SSL Proxy load balancers.
- 🔑 Internal load balancers (HTTP(S) and Network) never expose a public IP and are the standard choice for east-west, intra-VPC microservice traffic.

## 12. Related Concepts

Cloud DNS for directing users to load balancer IPs (Section 23), Cloud Armor for WAF/DDoS protection at the load balancer edge (Section 74), Traffic Director for service-mesh-managed internal traffic (Section 27), and GKE Ingress/Gateway resources that provision these load balancers automatically for containerized workloads (Section 31).
