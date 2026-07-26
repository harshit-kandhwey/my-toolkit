# Section 25 (Part 3): Shared VPC, VPC Peering & Private Service Connect

## 1. Definition

**Plain language:** Large organizations rarely want one giant flat network, but they also don't want every team building isolated networks that can't talk to each other or to shared services. GCP offers three distinct answers depending on exactly what you're trying to share: Shared VPC lets many projects use subnets from one central network. VPC Peering directly connects two separate VPC networks so their resources can talk to each other privately. Private Service Connect lets you privately consume (or publish) a specific service without connecting whole networks together at all.

**Precise:** **Shared VPC** lets a designated **host project** share its VPC network's subnets with one or more **service projects**, so resources in different projects share IP address space and can communicate as if on one network, while billing/IAM/resource management stay separated by project. **VPC Network Peering** establishes direct, private RFC 1918 connectivity between two entire VPC networks (in the same or different organizations) without traversing the public internet, but is explicitly **non-transitive**. **Private Service Connect (PSC)** provides private, one-directional connectivity to a specific published service (Google-managed or a third party's/your own) via an internal IP endpoint, without connecting or exposing the full network on either side.

## 2. Why It Exists / Problem It Solves

As organizations scale past a handful of teams, three distinct connectivity problems emerge that a single mechanism can't solve well. First: centralized network administration — security/network teams want to own IP address planning, firewall policy, and routing centrally, while still letting individual product teams operate freely within their own project (billing, IAM, resource lifecycle) — Shared VPC solves this by decoupling network ownership from project ownership. Second: connecting genuinely separate networks (different organizations, acquired companies, or intentionally separate VPCs) without merging them into one shared network — VPC Peering solves this with direct, private, non-transitive connectivity between exactly two networks. Third: consuming or exposing a specific service (a managed database, a SaaS partner's API, an internal team's service) without either whole-network peering (too broad, exposes everything) or public internet exposure (too insecure) — Private Service Connect solves this narrowly, exposing just the one service via a private IP.

## 3. Core Concepts

### 3.1 Shared VPC: Host and Service Projects

A **host project** owns the Shared VPC network and its subnets. One or more **service projects** are attached to the host project and granted permission (via Shared VPC-specific IAM roles) to create resources (VMs, GKE clusters, etc.) that use the host's subnets. IP address space, routes, and firewall rules are centrally managed in the host project, while service project teams retain full control over their own compute/application resources and billing. This is GCP's standard enterprise pattern for "one VPC per environment" (e.g., one host VPC for `prod`, attached to dozens of service projects) rather than "one VPC per team."

### 3.2 VPC Network Peering

Two VPC networks establish a peering connection, after which resources in either network can communicate using internal (private) IP addresses as if on the same network — but each network retains independent ownership, IAM, and firewall rules. The defining limitation is **non-transitivity**: if VPC-A peers with VPC-B, and VPC-B peers with VPC-C, VPC-A **cannot** reach VPC-C through VPC-B — peering does not chain. This means peering scales poorly for many interconnected networks (a full mesh of N networks needs a quadratic number of peering connections), which is precisely the problem Network Connectivity Center (Section 26) exists to solve at scale.

### 3.3 Private Service Connect (PSC)

PSC has two primary directions. **Consuming a service:** you create a PSC endpoint (an internal IP address in your VPC) that privately connects to a published service — a Google API (e.g., Cloud Storage, BigQuery) via **Private Google Access**-style endpoints, or a service published by another VPC/organization. **Publishing a service:** you can act as a service producer, publishing your own service (fronted by an internal load balancer) via a **Service Attachment**, letting consumer VPCs (including those outside your organization) privately connect to it through their own PSC endpoint — without peering networks, without the consumer needing any visibility into your VPC's topology, and traffic never traverses the public internet.

### 3.4 Choosing Between the Three

Shared VPC is the right choice when projects should behave as if on one administratively centralized network (same organization, closely related teams). VPC Peering is right for connecting two genuinely separate, already-existing networks that need broad bidirectional connectivity, when the non-transitive limitation is acceptable (few, stable networks). PSC is right when only narrow, specific service-level access is needed — most commonly for SaaS/managed-service exposure, or when the consumer and producer should have zero visibility into each other's broader network.

## 4. Comparison Table

| Mechanism               | Scope of Access                | Transitive?                                    | Typical Use Case                                                |
| ----------------------- | ------------------------------ | ---------------------------------------------- | --------------------------------------------------------------- |
| Shared VPC              | Whole subnets, shared IP space | N/A (one network, many projects)               | Centralized network admin across many projects in one org       |
| VPC Peering             | Whole networks, bidirectional  | No — non-transitive                            | Connecting two specific existing VPCs (same or different orgs)  |
| Private Service Connect | One specific published service | N/A (point-to-service, not network-to-network) | Privately consuming/publishing a narrow service, cross-org SaaS |

## 5. Architecture Diagram

```
                     SHARED VPC (host project: net-host)
      ┌────────────────────────────────────────────────────────┐
      │        Subnet: us-central1 (10.0.1.0/24)               │
      │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
      │  │ svc-project-A│  │ svc-project-B│  │ svc-project-C│  │
      │  │ (VMs use host│  │ (VMs use host│  │ (VMs use host│  │
      │  │  subnet)     │  │  subnet)     │  │  subnet)     │  │
      │  └──────────────┘  └──────────────┘  └──────────────┘  │
      └────────────────────────────────────────────────────────┘
                        │  VPC Peering (non-transitive)
                        ▼
      ┌─────────────────────────┐        ┌──────────────────────────┐
      │  VPC-Partner (separate  │        │ VPC-D (peered to Partner,│
      │  org, peered directly)  │───X───►│ NOT reachable from       │
      └─────────────────────────┘  no    │ net-host — non-transitive│
                                chain    └──────────────────────────┘

      ┌──────────────────────┐    PSC endpoint   ┌──────────────────────────┐
      │  Consumer VPC        │◄──(internal IP)──►│  Producer service        │
      │  (only sees the      │    one service    │  (Service Attachment,    │
      │  endpoint, not the   │     only          │  own VPC, own topology,  │
      │  producer's network) │                   │  invisible to consumer)  │
      └──────────────────────┘                   └──────────────────────────┘
```

## 6. Comparison: GCP vs AWS vs Azure

| GCP                                                                | AWS Equivalent                                                                          | Azure Equivalent                                                                             | Notes                                                                                                                      |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Shared VPC                                                         | (No direct AWS equivalent — closest is sharing subnets via AWS Resource Access Manager) | (No direct single-product equivalent — Azure Virtual WAN/hub-spoke approximates the outcome) | GCP's Shared VPC as a first-class, purpose-built construct is fairly distinctive                                           |
| VPC Peering                                                        | VPC Peering                                                                             | VNet Peering                                                                                 | Same non-transitive limitation exists in all three clouds                                                                  |
| Private Service Connect                                            | AWS PrivateLink                                                                         | Azure Private Link                                                                           | Closest direct like-for-like: narrow, service-level private connectivity without full network peering, in all three clouds |
| (Peering doesn't scale) → Network Connectivity Center (Section 26) | Transit Gateway                                                                         | Azure Virtual WAN                                                                            | All three clouds solve non-transitive peering's scaling problem with a hub-based transitive-routing product                |

> ⚠️ **Interview-relevant nuance:** AWS PrivateLink and Azure Private Link are the most direct cross-cloud analogs to PSC — all three exist specifically because full network peering/VPC-to-VPC connectivity is too broad a grant for consuming a single managed service, and all three avoid public internet exposure for that service traffic.

## 7. Hands-On Examples

**Beginner — enable Shared VPC on a host project and attach a service project:**

```bash
gcloud compute shared-vpc enable net-host-project

gcloud compute shared-vpc associated-projects add svc-project-a \
  --host-project=net-host-project
```

_Purpose:_ Designates `net-host-project` as a Shared VPC host, then attaches `svc-project-a` as a service project so its resources can use the host's subnets (subject to IAM permissions granted per-subnet).

**Expected output:**

```
Updated [net-host-project].
Updated [svc-project-a].
```

**Intermediate — create a VPC Peering connection:**

```bash
gcloud compute networks peerings create peer-a-to-b \
  --network=vpc-a \
  --peer-network=vpc-b \
  --auto-create-routes
```

_Purpose:_ Establishes one direction of a VPC Peering connection from `vpc-a` to `vpc-b` (the reciprocal peering must also be created from `vpc-b`'s side for the connection to become ACTIVE), enabling private IP connectivity between the two networks.

**Expected output:**

```
Created [https://www.googleapis.com/compute/v1/projects/my-project/global/networks/vpc-a/peerings/peer-a-to-b].
STATE: INACTIVE (waiting for peer-b-to-a to be created on vpc-b)
```

## 8. Production & Enterprise Usage

- **Shared VPC as the default enterprise pattern:** one host VPC per environment (`prod`, `staging`, `dev`), with dozens of service projects attached, centralizing IP planning and firewall policy while giving product teams project-level autonomy.
- **VPC Peering for a small, stable number of cross-organization connections** (e.g., peering with a recently acquired company's VPC, or a specific partner integration) where the non-transitive limitation is acceptable because the topology is small and won't grow into a mesh.
- **Private Service Connect for consuming managed/SaaS services privately** (e.g., a data vendor's API, a partner's internal service) and for **publishing internal platform services** (e.g., a central logging or auth service) to many consumer teams/organizations without granting them network-level visibility.
- **PSC for Google APIs specifically:** many enterprises use PSC endpoints for Google-managed services (Cloud Storage, BigQuery, etc.) to keep that traffic entirely on private IPs, satisfying compliance requirements that prohibit any traffic path touching the public internet, even to reach a Google API.

## 9. Common Misconceptions

- **Misconception:** "If A peers with B, and B peers with C, A can reach C." VPC Peering is explicitly non-transitive — this is one of the most tested facts about GCP networking, and the direct reason Network Connectivity Center (Section 26) exists for larger topologies.
- **Misconception:** "Shared VPC and VPC Peering solve the same problem, just at different scales." They don't — Shared VPC is about **many projects sharing one network's IP space under central administration**, while Peering is about **connecting two genuinely separate, independently administered networks**. Choosing between them is a question of administrative boundary, not just topology size.
- **Misconception:** "Private Service Connect exposes the consumer's or producer's whole network to the other side." It exposes exactly one service via one internal IP endpoint in each direction — neither side gains visibility into the other's broader VPC topology, routes, or other resources.

## 10. Interview Questions

**🎯 Beginner:** _What's the key limitation of VPC Peering that architects need to plan around?_
**Model answer:** VPC Peering is non-transitive — if network A peers with B, and B peers with C, A cannot reach C through B. Each pair of networks that needs connectivity requires its own direct peering connection, which means a fully connected mesh of N networks needs a quadratic number of peering connections, an operational burden that doesn't scale to many networks.

**🎯 Intermediate:** _When would you choose Private Service Connect over VPC Peering to connect to a partner organization's service?_
**Model answer:** PSC when you only need access to one specific service the partner is publishing, and neither side should gain visibility into the other's broader network topology, IP ranges, or other resources — this is also the safer default for cross-organization connectivity from a security/blast-radius standpoint. VPC Peering when the relationship genuinely requires broad, bidirectional network-level connectivity between the two organizations' resources, not just access to a single service.

**🎯 Senior/Architect:** _Design the network-sharing model for an enterprise with one central platform team, 30 product teams needing standard connectivity to shared internal services, and a requirement to let three external partner companies consume a specific internal API without any broader network access._
**Model answer:** For the 30 internal product teams, I'd use Shared VPC with the platform team owning the host project (centralizing IP address planning, routing, firewall policy), and each product team as a service project attached to the host VPC — giving them full autonomy over their own resources/billing while inheriting consistent, centrally-managed networking. For the three external partner companies needing access to one specific internal API, I would explicitly avoid VPC Peering (too broad a grant, exposes network topology, and doesn't scale cleanly to more partners later) in favor of Private Service Connect: publish the API as a service via a Service Attachment, and have each partner create their own PSC endpoint to consume it privately — this keeps each partner's access scoped to exactly that one API, with no visibility into the platform's internal Shared VPC topology, and adding a fourth partner later requires zero changes to the existing three.

## 11. Key Takeaways

- 🔑 Shared VPC decouples network administration (host project) from project/resource ownership (service projects) — GCP's standard "one VPC per environment" enterprise pattern.
- 🔑 VPC Peering is direct, private, bidirectional network-to-network connectivity, but explicitly non-transitive — it does not chain across multiple hops.
- 🔑 Private Service Connect provides narrow, one-service-at-a-time private connectivity via an internal IP endpoint, without exposing either side's broader network — the closest analog to AWS PrivateLink/Azure Private Link.
- 🔑 Choosing between the three is a question of _what_ needs to be shared: whole subnets (Shared VPC), whole networks (Peering), or one specific service (PSC) — not merely a question of scale.

## 12. Related Concepts

VPC fundamentals establishing the global-network/regional-subnet model these constructs build on (Section 19), Cloud DNS zone authorization and peering that must be separately configured alongside network-level Peering (Section 23), Network Connectivity Center for transitive hub-and-spoke connectivity at scale beyond what Peering supports (Section 26), and VPC Service Controls for perimeter security around these connectivity patterns (Section 41).
