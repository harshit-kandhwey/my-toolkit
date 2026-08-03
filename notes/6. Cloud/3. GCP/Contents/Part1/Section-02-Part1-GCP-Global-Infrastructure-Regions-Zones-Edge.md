# Section 2 (Part 1): GCP Global Infrastructure (Regions, Zones, Edge)

## 1. Definition

**Plain language:** Google's cloud runs on real physical data centers scattered around the world. GCP organizes these data centers into a structured hierarchy — **regions**, **zones**, and **edge locations** — so you can choose exactly where your workloads physically run, balancing latency, availability, and legal/compliance requirements.

**Precise:** GCP's global infrastructure consists of a private global fiber network connecting **regions** (independent geographic areas), each subdivided into **zones** (isolated failure domains within a region), supplemented by **edge points of presence (PoPs)** that bring content and networking closer to end users outside of full regions.

## 2. Why It Exists / Problem It Solves

A single data center is a single point of failure — a power outage, fire, network cut, or natural disaster can take down every resource located there. It's also physically far from most users, adding network latency. GCP's region/zone model exists to solve two separate problems simultaneously:

1. **Fault isolation:** By spreading resources across independent zones and regions, a failure in one zone (e.g., a cooling failure in one building) does not take down resources in another zone, and a regional disaster does not take down resources in a different region.
2. **Latency reduction:** By offering many regions around the world, users can deploy their application physically close to their end users, reducing the round-trip network time for requests.

## 3. Core Concepts

### 3.1 Region

A **region** is an independent geographic area — for example, `us-central1` (Iowa, USA), `europe-west1` (Belgium), or `asia-south1` (Mumbai, India). Regions are named using a `<continent><direction><number>` convention.

- Each region is a separate area chosen to be geographically distant enough from other regions to survive large-scale regional disasters (earthquakes, storms, regional power grid failures) without affecting other regions.
- Not all GCP services are available in all regions — newer or specialized services (e.g., some AI/ML services with specific hardware requirements) roll out to a subset of regions first.
- Data residency: some organizations are legally required to keep data within a specific country's borders (e.g., financial or healthcare data in the EU). Choosing the right region lets you satisfy this requirement, and GCP publishes explicit data residency commitments per-region for many services.

### 3.2 Zone

A **zone** is a deployment area within a region, roughly corresponding to one or a small number of physical data center buildings with independent power, cooling, and networking. Zones within the same region are named `<region>-<letter>`, e.g., `us-central1-a`, `us-central1-b`, `us-central1-c`.

- Zones within a region are connected to each other via low-latency, high-bandwidth network links, so cross-zone communication within a region is fast (typically sub-millisecond to a few milliseconds).
- Zones are designed to be **independent failure domains**: a power or cooling failure affecting one zone should not affect another zone in the same region. This is why high-availability architectures spread identical resources (e.g., VM replicas) across multiple zones — covered in depth in Phase 4 (Production & Enterprise Usage).
- Not every zone offers every machine type or GPU type — capacity and hardware availability can vary zone to zone, which matters when provisioning specialized hardware (GPUs, TPUs) at scale.

### 3.3 Multi-Region

Some GCP services (notably Cloud Storage and BigQuery) offer a **multi-region** option, which stores data redundantly across multiple regions within a larger geographic area (e.g., "US" multi-region spans several US regions). This maximizes availability and durability at the cost of higher latency for writes and typically higher storage cost, because data must be replicated over long distances.

### 3.4 Edge Points of Presence (PoPs)

Beyond full regions, Google operates many more **edge locations** — smaller facilities that don't run general-purpose compute/storage but instead cache content and provide network entry points closer to users. These power:

- **Cloud CDN** — caching static content close to end users to reduce latency.
- **Google Cloud's global network backbone** — Google operates its own private fiber network connecting regions and edge points, meaning traffic between a user and the nearest Google edge location — and between Google data centers globally — largely travels over Google-owned infrastructure rather than the public internet, improving speed and reducing exposure to public internet congestion or interception.

## 4. Architecture Diagram

```
                         ┌─────────────────────────────────────────┐
                         │              GCP GLOBAL NETWORK         │
                         │         (Google-owned private fiber)    │
                         └─────────────────────────────────────────┘
                                    │                    │
              ┌─────────────────────┘                    └──────────────────────┐
              ▼                                                                 ▼
      ┌──────────────────────┐                                       ┌───────────────────────┐
      │ REGION: us-central1  |                                       │  REGION: europe-west1 |
      │  (Iowa, USA)         │                                       │  (Belgium)            │
      │                      │                                       │                       │
      │  ┌────────────────┐  │                                       │  ┌────────────────┐   │
      │  │ Zone: -a       │  │                                       │  │ Zone: -b       │   │
      │  │ (independent   │  │◄──low-latency intra-region network──► │  │ (independent   │   │
      │  │  power/cooling)│  │                                       │  │  power/cooling)│   │
      │  └────────────────┘  │                                       │  └────────────────┘   │
      │  ┌────────────────┐  │                                       └───────────────────────┘
      │  │ Zone: -b       │  │
      │  └────────────────┘  │
      │  ┌────────────────┐  │
      │  │ Zone: -c       │  │
      │  └────────────────┘  │
      └──────────────────────┘

      Edge PoPs (many more locations than regions) — cache content via Cloud CDN,
      serve as network entry points onto Google's private backbone.
```

## 5. How Regions and Zones Interact With Resources

- **Zonal resources:** Some resources must be created in a specific zone and only exist there — e.g., a Compute Engine VM instance, or a zonal Persistent Disk. If the zone fails, the resource is unavailable until you provision it elsewhere.
- **Regional resources:** Some resources are regional — e.g., a regional Managed Instance Group, or a Regional Persistent Disk, which synchronously replicates data across two zones within the same region for higher availability.
- **Multi-regional / global resources:** Some resources span multiple regions or are global by nature — e.g., a Cloud Storage multi-region bucket, a global HTTP(S) Load Balancer, or a VPC network itself (VPC networks in GCP are global resources, a distinctive design choice versus other clouds — covered in depth in §19).

> ⚠️ **Interview-relevant nuance:** In GCP, a VPC network is a **global** resource, and its **subnets** are **regional** resources (not zonal). This is a well-known distinction from AWS (where VPCs are regional and subnets are zonal), and interviewers frequently probe this specific difference. It is covered in full in Sections 19–20.

## 6. Choosing a Region: Decision Factors

| Factor                          | Consideration                                                                                                                                 |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Latency to users**            | Choose the region geographically closest to your primary user base to minimize round-trip time.                                               |
| **Service availability**        | Not all services/machine types/GPUs are available in every region — verify before committing.                                                 |
| **Pricing**                     | Compute and storage pricing varies by region; some regions are more expensive due to local costs (power, real estate, taxes).                 |
| **Compliance / data residency** | Legal requirements (e.g., GDPR considerations, industry regulations) may mandate that data stay within a specific country or economic region. |
| **Disaster recovery strategy**  | For multi-region DR, pick a secondary region geographically distant enough to be unaffected by the same disaster as your primary region.      |
| **Carbon footprint**            | Google publishes carbon-free energy percentage data per region; sustainability-conscious organizations may factor this into region selection. |

## 7. Hands-On Example: Listing Regions and Zones

**Beginner example — list all available regions:**

```bash
gcloud compute regions list
```

**Expected output (abbreviated):**

```
NAME                     CPUS  DISKS_GB  ADDRESSES  RESERVED_ADDRESSES  STATUS  TURNDOWN_DATE
asia-east1               ...   ...       ...        ...                 UP
us-central1               ...   ...       ...        ...                 UP
europe-west1               ...   ...       ...        ...                 UP
...
```

**List zones within a specific region:**

```bash
gcloud compute zones list --filter="region:us-central1"
```

**Expected output:**

```
NAME             REGION        STATUS
us-central1-a    us-central1   UP
us-central1-b    us-central1   UP
us-central1-c    us-central1   UP
```

> 💡 **Tip:** `gcloud compute zones list` without a filter returns every zone across every region globally — useful for scripting automated multi-region deployments, but very long; always pipe through `--filter` or `grep` in real usage.

## 8. Production & Enterprise Usage

- **High availability within a region:** Enterprises typically deploy redundant instances of a service across at least 3 zones within a region (e.g., a Managed Instance Group spanning `us-central1-a`, `-b`, `-c`) so that a single zone failure doesn't cause an outage.
- **Multi-region for disaster recovery:** Mission-critical systems (e.g., banking, healthcare) often deploy fully redundant infrastructure in a second, geographically distant region, with data replication and failover mechanisms — covered in depth in Section 58 (Disaster Recovery & Multi-Region Architecture).
- **Global load balancing:** Enterprises serving a worldwide user base use GCP's Global HTTP(S) Load Balancer (Section 22) to route users to the nearest healthy region automatically, rather than manually managing region selection.

## 9. Common Misconceptions

- **Misconception:** "A zone is the same as a single physical data center building." In reality, a zone may correspond to one or more buildings/facilities; Google does not publicly guarantee a strict 1:1 mapping, and zones should be treated as an abstraction representing an independent failure domain rather than a literal building count.
- **Misconception:** "More zones always means better availability." Spreading resources across zones only improves availability if your application architecture is actually designed to tolerate a zone failure (e.g., stateless services behind a load balancer with health checks) — simply having resources "in 3 zones" without proper failover logic doesn't automatically grant high availability.

## 10. Interview Questions

**🎯 Beginner:** _What is the difference between a region and a zone in GCP?_
**Model answer:** A region is an independent geographic area (e.g., `us-central1`), and a zone is an isolated deployment area within that region (e.g., `us-central1-a`), roughly corresponding to a data center with independent power and cooling. Regions provide geographic separation for disaster recovery and latency purposes, while zones within a region provide fault isolation with low-latency connectivity between them, letting you build highly available architectures without the higher latency of cross-region communication.

**🎯 Intermediate:** _Why would you choose a regional Managed Instance Group over a zonal one?_
**Model answer:** A zonal Managed Instance Group places all instances within a single zone, so a zone-level failure takes down the entire group. A regional Managed Instance Group spreads instances across multiple zones within the region automatically, so the application remains available even if one zone fails. The trade-off is slightly more complexity in some data consistency scenarios (e.g., needing to handle cross-zone latency for stateful workloads), but for stateless workloads, regional MIGs are almost always preferred in production.

**🎯 Senior/Architect:** _A client needs 99.99% availability with data residency restricted to the European Union, and a disaster recovery target region for business continuity. How would you approach region selection?_
**Model answer:** I'd select a primary EU region (e.g., `europe-west1` in Belgium) for data residency compliance, deploying the primary workload across at least 3 zones within that region for intra-region high availability against zone-level failures. For disaster recovery, I'd choose a second EU region that is geographically distant enough to avoid correlated disasters (e.g., `europe-west3` in Frankfurt, or `europe-north1` in Finland) while still satisfying the EU data residency requirement — I would not select a US region as DR target, since that would violate the residency constraint even for backup/replica data. I'd then design either an active-passive or active-active replication strategy between the two regions depending on RPO/RTO requirements (detailed in Section 49), and use a Global Load Balancer with health checks to handle regional failover automatically.

## 11. Key Takeaways

- 🔑 GCP's infrastructure hierarchy is: Global network → Region → Zone, with edge PoPs supplementing regions for CDN and network entry.
- 🔑 Zones are independent failure domains within a region, connected by low-latency links, enabling multi-zone high availability without high cross-zone latency.
- 🔑 GCP VPC networks are global resources and subnets are regional — a key architectural difference from AWS, revisited in Part 3.
- 🔑 Region choice should weigh latency, service availability, pricing, compliance, and disaster recovery strategy together, not any single factor alone.

## 12. Related Concepts

Resource hierarchy (Section 3), VPC networks and subnets (Sections 19–20), regional vs zonal vs global load balancers (Section 22), and disaster recovery/multi-region architecture (Section 58) all build directly on the region/zone model introduced here.
