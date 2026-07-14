# Part 1 · Section 2 — AWS Global Infrastructure

> AWS Zero-to-Enterprise Knowledge Base · Part 1: Foundations & Global Infrastructure

---

## 1. Definition

**Plain-language:** The worldwide set of physical data centers AWS owns and operates, organized into a hierarchy so you can place applications near users and survive hardware failures.

**Precise:** A hierarchy of geographically distributed, fault-isolated infrastructure — *Regions* (geographic areas) containing multiple *Availability Zones* (isolated data-center clusters), plus *edge locations*, *Local Zones*, *Wavelength Zones*, and *Outposts*, interconnected by AWS's private global fiber backbone.

> 💡 **Mental model:** Regions = countries; Availability Zones = independent power grids within a country; edge locations = local delivery depots caching content near users.

---

## 2. Why It Exists

Three problems → three components:
1. **Latency** (finite speed of data) → **Regions** near users.
2. **Fault isolation / availability** (a data center can fail) → **multiple AZs** per Region.
3. **Content-delivery speed** → hundreds of **edge locations**.

> 🔑 Regions solve geography, AZs solve availability, edge solves delivery speed.

---

## 3. Core Hierarchy

```
              AWS Global Infrastructure
                        │
     ┌──────────────────┼──────────────────┐
   Region            Region             Region
 (us-east-1)       (eu-west-1)        (ap-south-1)
     │
 ┌───┼───┬────┐
 AZ  AZ  AZ   AZ        (min 3 AZs per Region)
 │
 DC DC ...              (each AZ = one or more data centers)
```

### 3.1 Region
- Physical geographic area with a cluster of data centers, **min 3 isolated AZs**.
- **Fully isolated** from other Regions (no automatic data sharing; fault containment; data-residency compliance).
- Naming: `{geo}-{direction}-{number}` → `us-east-1` (N. Virginia), `us-west-2` (Oregon), `eu-west-1` (Ireland), `ap-south-1` (Mumbai), `ap-northeast-1` (Tokyo), `sa-east-1` (São Paulo).
- Each Region has its own service API endpoints.

> ⚠️ Counts change constantly — as of mid-2026 roughly ~39 Regions and 100+ AZs, growing. Always cite the live AWS Global Infrastructure page for exact numbers.

### 3.2 Availability Zone (AZ)
- One or more discrete data centers with redundant power, networking, connectivity, in separate facilities within a Region.
- Separated by a meaningful distance (~100 km / 60 mi) — far enough to avoid a shared disaster, close enough for low-latency redundant fiber (enables synchronous cross-AZ replication).
- **Name vs ID:**
  - **Name** (`us-east-1a`) is **randomized per account** to balance load — not a stable physical identifier across accounts.
  - **AZ ID** (`use1-az1`) is **consistent across all accounts** — use it for cross-account physical co-location.

> 🎯 Interview gotcha: AZ names are randomized per account; use AZ IDs (`use1-az1`) when physical placement across accounts matters.

### 3.3 Data Center
- Lowest unit; **not exposed** to you. You operate at AZ level and above.

---

## 4. Broader Infrastructure Components

| Component | What it is | Purpose |
|-----------|-----------|---------|
| Region | Geographic area, ≥3 AZs | Placement: geography, compliance, service availability |
| Availability Zone | Isolated data-center cluster | High availability within a Region |
| Edge Location (PoP) | Small PoP, hundreds worldwide | Cache/serve content near users (CloudFront, Route 53, Global Accelerator, WAF) |
| Regional Edge Cache | Larger cache between origin and edge | Holds less-popular content, improves cache hit ratio |
| Local Zone | Region extension in a major metro | Single-digit-ms latency (gaming, media, rendering) |
| Wavelength Zone | AWS infra inside telecom 5G networks | Ultra-low latency mobile/edge (AR/VR, vehicles) |
| Outposts | AWS-managed racks in your data center | Hybrid — same AWS APIs on-prem |

> 💡 Region → Local Zone → Wavelength → Outposts is a latency/location continuum: closer to users/facilities, fewer services available.

---

## 5. Special Region Types & Partitions

- **Standard commercial** — default public cloud, partition `aws`.
- **GovCloud (US)** — isolated US government Regions (ITAR, FedRAMP High); partition `aws-us-gov`; separate accounts.
- **China (Beijing, Ningxia)** — operated by local partners; partition `aws-cn`; separate accounts; no auto connectivity to global.
- **European Sovereign Cloud** — independent partition for EU sovereignty (first Region early 2026).

> 🔑 A **partition** is a top-level isolation boundary encoded in ARNs: `arn:aws:...`, `arn:aws-us-gov:...`, `arn:aws-cn:...`. Accounts/IAM/networking don't cross partitions.

---

## 6. Opt-In vs Default Regions

- **Default:** Regions before ~March 2019 are active automatically.
- **Opt-in:** Newer Regions must be explicitly enabled — a cost/security guardrail.

> ⚠️ Forgotten enabled Regions cause surprise bills and security gaps. Use Organizations SCPs to restrict allowed Regions.

---

## 7. Service Scope — Global vs Regional vs Zonal

| Scope | Meaning | Examples | Failure implication |
|-------|---------|----------|--------------------|
| Global | Spans all Regions | IAM, Route 53, CloudFront, WAF, Organizations | Wide blast radius; often `us-east-1` control-plane centered |
| Regional | Lives in chosen Region, AWS spreads across AZs | S3 (data), DynamoDB, Lambda, SQS | Survives AZ failure automatically |
| Zonal | Tied to one AZ | EC2 instance, EBS volume, subnet | Dies with the AZ — you must add cross-AZ redundancy |

> 🎯 AWS makes regional services multi-AZ for you; zonal resources (EC2, EBS) are your responsibility — deploy across AZs behind a load balancer.

> 💡 S3 bucket **names are globally unique**, but **data is regional** (stored in the bucket's Region).

---

## 8. Configuration / Interaction

- **Console:** Region selector dropdown (top-right).
- **CLI/SDK:** `AWS_REGION` / `AWS_DEFAULT_REGION`, `--region` flag, `~/.aws/config`.
- **AZ choice:** pick AZ/subnet for zonal resources; spread across AZs for HA.

---

## 9. Commands

### `aws ec2 describe-regions`
- **Purpose:** List Regions available/enabled for the account.
- **Syntax:** `aws ec2 describe-regions [--all-regions] [--region <r>] [--output <fmt>]`
- **Key options:** `--all-regions` (include disabled opt-in Regions); `--query` (JMESPath filter); `--output table|json|text`.
- **Example:**
  ```bash
  aws ec2 describe-regions --query 'Regions[].RegionName' --output text
  ```
- **Production:** CI/CD iterates Regions; compliance asserts only approved Regions enabled.
- **Errors:** `UnauthorizedOperation` (missing `ec2:DescribeRegions`), `AuthFailure` (no creds).

### `aws ec2 describe-availability-zones`
- **Purpose:** List AZs with names AND AZ IDs in a Region.
- **Example:**
  ```bash
  aws ec2 describe-availability-zones --region us-east-1 \
    --query 'AvailabilityZones[].[ZoneName,ZoneId]' --output table
  ```
  Output shows e.g. `us-east-1a → use1-az2` (illustrates name↔ID randomization).
- **Production:** IaC uses AZ IDs to co-locate cross-account resources.
- **Mistake:** hardcoding `us-east-1a` and assuming universal physical mapping.

---

## 10. Choosing a Region — Decision Criteria

1. **Latency / proximity** to primary users.
2. **Compliance / data residency / sovereignty** — can be mandatory and override latency.
3. **Service & feature availability** — not every service is in every Region; new services launch in `us-east-1` first.
4. **Pricing** — varies by Region; `us-east-1` often cheapest.

> 💡 Decision tree: legally required location? → compliance wins. Else → nearest Region with needed services, weighing latency vs price.

---

## 11. Production & Enterprise Usage

- **Multi-AZ by default** for production (LB across AZs, Multi-AZ RDS, Auto Scaling across AZs).
- **Multi-Region** for DR and global reach — more complex/costly; deliberate (Part 10).
- **Data residency** — pin to compliant Regions/partitions; enforce with SCPs.
- **Hybrid** — Outposts / Local Zones extend AWS to your facilities/metros.

---

## 12. Security / Performance / Monitoring

- **Security:** Region isolation = blast-radius containment; restrict Regions via SCPs; encrypt cross-Region transfers.
- **Performance:** placement is the biggest lever — Region near users + spread across AZs + edge caching.
- **Monitoring:** AWS Health Dashboard for Region/AZ events; CloudWatch metrics are regional.

---

## 13. Troubleshooting

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| "Service X not available here" | Not launched in Region | Use a supporting Region |
| App down on single-AZ issue | Zonal single-AZ deploy | Spread across ≥2 AZs + LB |
| Cross-account latency | Assumed AZ names match physically | Use AZ IDs |
| Can't create in Region Y | Opt-in not enabled / SCP blocks | Enable Region / adjust SCP |
| Works in commercial, fails in GovCloud/China | Hardcoded `aws` partition | Parameterize partition |

---

## 14. Best Practices & Anti-Patterns

**Best practices:** span ≥2 AZs in production; use AZ IDs for cross-account placement; restrict enabled Regions; choose Region by compliance → latency → availability → price.

**Anti-patterns:** single-AZ production; assuming `us-east-1a` is universal; ignoring service-availability differences; treating multi-Region as free HA.

---

## 15. Interview Questions (with model answers)

**🟢 Region vs AZ?** Region = geographic area with multiple AZs (solves geography/compliance); AZ = physically separate data center(s) within a Region (isolated but network-close, the unit of HA).

**🟡 Design HA in one Region?** Deploy across ≥2–3 AZs: stateless compute behind an ELB, Auto Scaling across AZs, Multi-AZ RDS with synchronous standby. Any single AZ failure is absorbed.

**🟡 Choose a Region?** Compliance/residency (often overriding), latency/proximity, service availability, price. Resolve compliance first, then optimize the rest.

**🔴 Why can `us-east-1a` differ between accounts?** AZ names are randomized per account for load balancing; the stable identifier is the AZ ID (`use1-az1`). Coordinate on IDs for cross-account co-location.

**🔴 Survive a full Region outage vs multi-AZ?** Multi-AZ handles data-center failure, not Region-wide events. Multi-Region: cross-Region data replication (S3 CRR, DynamoDB Global Tables, DB read replicas), IaC in a second Region, Route 53 health-check failover, and a DR pattern (backup/restore, pilot light, warm standby, active/active) chosen by RTO/RPO. Adds cross-Region consistency/failover complexity.

---

## 🔑 Key Takeaways

1. Hierarchy: Region (geography) → AZ (fault isolation) → data center; ≥3 AZs/Region; plus edge/Local Zones/Wavelength/Outposts.
2. AZs are the unit of HA — spread production across ≥2 AZs.
3. AZ names randomized per account; AZ IDs consistent — use IDs for cross-account co-location.
4. Every resource is global, regional, or zonal — AWS handles multi-AZ for regional services; you handle it for zonal (EC2, EBS).
5. Choose Region by compliance → latency → service availability → price; partitions (`aws`, `aws-us-gov`, `aws-cn`, sovereign) are hard isolation boundaries in ARNs.

## 🌐 Related Concepts (forward links)

- Shared Responsibility Model → Section 3
- VPC, subnets, load balancers → Part 4
- Multi-AZ RDS, S3 replication, DR patterns → Parts 5, 6, 10
