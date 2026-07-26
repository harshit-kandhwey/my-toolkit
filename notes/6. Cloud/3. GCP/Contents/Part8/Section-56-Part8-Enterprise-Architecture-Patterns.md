# Section 56 (Part 8): Enterprise Architecture Patterns on GCP

## 1. Definition

**Plain language:** Enterprise architecture patterns are proven, repeatable blueprints for combining GCP's individual services — compute, load balancing, databases, messaging — into complete systems that survive real-world failure, scale, and change without needing to be redesigned from scratch every time. Instead of inventing an architecture from zero for every project, architects reuse patterns that have already been battle-tested across many organizations.

**Precise:** An enterprise architecture pattern on GCP is a documented arrangement of managed services — typically spanning compute, networking, data, and messaging layers — designed to satisfy specific non-functional requirements (availability, latency, consistency, cost) that recur across many workloads. Patterns are evaluated against a structured set of quality pillars, formalized by Google as the **Google Cloud Architecture Framework**.

## 2. Why It Exists / Problem It Solves

Individually, GCP services (Compute Engine, Cloud SQL, Pub/Sub, Cloud Run) are just building blocks — none of them alone guarantees a working, resilient system. Without shared patterns:

- Every team reinvents multi-region failover logic, often getting subtle details wrong (e.g., forgetting that a load balancer needs health checks in every backend region, not just the primary).
- Reviewers and auditors have no common vocabulary to evaluate whether a design is sound — every architecture review starts from first principles.
- Organizations end up with inconsistent reliability and cost profiles across teams, because each team makes ad hoc trade-offs.

Enterprise architecture patterns and a shared framework solve this by giving architects a common, well-understood vocabulary ("active-active," "n-tier," "event-driven") and a shared checklist of quality attributes to evaluate any design against, regardless of which team built it.

## 3. Multi-Region Availability Patterns

### 3.1 Active-Passive (Warm/Cold Standby)

One region (the **primary**) serves all live traffic. A second region (the **standby**) is kept ready — either **cold** (infrastructure defined as code, deployed only on failover), **warm** (running at reduced capacity, scaled up on failover), or **hot but idle** (running at full capacity, but receiving no traffic until failover). Data replicates one-way from primary to standby (e.g., Cloud SQL cross-region read replica, GCS multi-region bucket).

- **Pros:** Simpler to reason about — no risk of write conflicts, since only one region accepts writes at a time.
- **Cons:** The standby region's compute capacity is either wasted (if hot) or introduces failover delay (if cold/warm), and failover requires a explicit cutover step (DNS change, load balancer reconfiguration, promoting a replica to primary).

### 3.2 Active-Active (Multi-Region Read/Write)

Two or more regions simultaneously accept live production traffic, typically routed by a **Global External Application Load Balancer** based on user proximity. Requires a data layer that supports multi-region writes with defined consistency guarantees — on GCP this usually means **Cloud Spanner** (external consistency across regions) rather than Cloud SQL (single-writer, regional).

- **Pros:** No idle standby capacity; a full regional failure only removes a fraction of total capacity, and failover is often automatic (the load balancer simply stops routing to the unhealthy region).
- **Cons:** Significantly more architectural complexity — the application must tolerate eventual or externally-consistent multi-region data semantics, and conflict resolution logic (or a database engineered to avoid conflicts, like Spanner) is mandatory.

| Dimension                | Active-Passive                                           | Active-Active                                                       |
| ------------------------ | -------------------------------------------------------- | ------------------------------------------------------------------- |
| **Write topology**       | Single writer region                                     | Multiple writer regions                                             |
| **Typical data service** | Cloud SQL cross-region read replica                      | Cloud Spanner multi-region configuration                            |
| **Failover**             | Manual/scripted cutover (promote replica, update DNS/LB) | Automatic (load balancer routes around unhealthy region)            |
| **Idle cost**            | Standby capacity often underutilized                     | All regional capacity actively serves traffic                       |
| **Complexity**           | Lower                                                    | Higher — requires conflict-free or externally consistent data layer |
| **RTO**                  | Minutes (cutover time)                                   | Near-zero (traffic simply reroutes)                                 |

> 💡 **Tip:** Don't default to active-active because it sounds more resilient. Most enterprise workloads (internal line-of-business apps, most transactional systems) are well served by active-passive with a clearly rehearsed failover runbook — active-active is justified when the cost of even a few minutes of downtime is very high (e.g., global consumer payments) and the team can operate the added complexity.

## 4. N-Tier Architecture on GCP

The classic **n-tier** pattern separates a system into layers, each independently scalable:

```
        Users
          │
          ▼
┌───────────────────────────┐
│  Global External ALB      │  ◄ Layer 1: Load Balancing / Edge (Section 22)
│ (+ Cloud CDN, Cloud Armor)│
└───────────────────────────┘
          │
          ▼
┌───────────────────────────┐
│  Managed Instance Group   │  ◄ Layer 2: Application/Compute
│   or GKE Deployment       │     (Compute Engine MIG — Section 5, or GKE — Section 30)
└───────────────────────────┘
          │
          ▼
┌───────────────────────────┐
│  Cloud SQL (regional)     │  ◄ Layer 3: Data
│   or Cloud Spanner        │     (Section 13, Section 14)
│   (multi-region)          │
└───────────────────────────┘
```

- **Presentation/edge tier:** Global External Application Load Balancer, optionally fronted by Cloud CDN for static assets and Cloud Armor for WAF/DDoS protection (Section 22 covers load balancing in depth).
- **Application tier:** Stateless compute — either a regional Managed Instance Group of Compute Engine VMs (autoscaled, spread across zones) or a GKE Deployment (autoscaled pods across node pools). Statelessness here is what makes horizontal autoscaling and zone/region failover possible without session-affinity complications.
- **Data tier:** Cloud SQL for single-region relational workloads with standard availability needs, or Cloud Spanner where horizontal scale and multi-region strong consistency are required. Each tier scales and fails over independently — a spike in application traffic doesn't require touching the database tier, and a database failover doesn't require redeploying application code.

## 5. Event-Driven Architecture Pattern

Rather than services calling each other directly (tight coupling), an **event-driven architecture** has services publish events describing "what happened," and other services react asynchronously:

- **Pub/Sub** (Section 45) is the durable, at-least-once messaging backbone — producers publish events to a topic without knowing who (if anyone) is listening.
- **Eventarc** (Section 53) standardizes how events from over 130 GCP sources (Cloud Storage object changes, Firestore writes, Cloud Audit Logs, custom application events) get routed as CloudEvents-formatted messages to subscribers, removing the need for each service to hand-roll its own event plumbing.
- **Cloud Run** (Section 7) is the most common event _consumer_ — Eventarc triggers invoke a Cloud Run service per matching event, and Cloud Run scales the number of running instances (including to zero when idle) to match event volume automatically.

```
 Cloud Storage        Firestore           Custom App
 (object finalized)   (document write)    (business event)
        │                   │                    │
        └─────────┬─────────┴──────────┬─────────┘
                   ▼                    ▼
              Eventarc (routes as CloudEvents)   ── or direct Pub/Sub topic
                   │
                   ▼
            Cloud Run service
        (scales 0►N on event volume,
         processes and acknowledges)
```

This pattern decouples producers from consumers entirely: a new consumer can be added later without changing the producer, and a producer can be replaced without consumers noticing, as long as the event contract (schema) is preserved.

## 6. The Google Cloud Architecture Framework

Unlike AWS, which markets a single trademarked "AWS Well-Architected Framework" with six named pillars, Google publishes a functionally equivalent but distinctly branded **Google Cloud Architecture Framework**, organized around similar quality pillars:

| Pillar                                | Focus                                                                                                                            |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Operational excellence**            | Automating deployment and operations (Section 50–51), observability (Section 54), incident response (Section 55).                |
| **Security, privacy, and compliance** | IAM least privilege (Section 35), org policies (Section 37), VPC Service Controls (Section 41), compliance mapping (Section 40). |
| **Reliability**                       | Multi-zone/multi-region resilience (this section, Section 58), SLOs and error budgets (Section 55).                              |
| **Cost optimization**                 | Rightsizing, discounts, budgets — covered in full in Section 57.                                                                 |
| **Performance optimization**          | Choosing the right compute/storage/network tier for the workload's latency and throughput needs (Section 10, Section 18).        |

> ⚠️ **Accuracy note:** GCP does not have a single trademarked framework name identical to "AWS Well-Architected Framework" — the equivalent Google documentation set is titled the **Google Cloud Architecture Framework**, and its pillar list and internal structure have evolved over time (for example, some versions fold "sustainability" in as a cross-cutting theme rather than a standalone pillar). Verify the current pillar list against Google's live documentation before quoting exact pillar names in a formal setting, since this is a documentation set Google actively revises.

## 7. Comparison: GCP vs AWS vs Azure Architecture Frameworks

| Aspect                              | AWS Well-Architected Framework                                                                                                                                         | Azure Well-Architected Framework                         | Google Cloud Architecture Framework                                                                                                         |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Branding**                        | Single trademarked name, six pillars                                                                                                                                   | Single named framework, five pillars                     | Named framework, pillars conceptually similar but Google revises grouping over time                                                         |
| **Tooling**                         | AWS Well-Architected Tool (in-console self-review workflow)                                                                                                            | Azure Well-Architected Review (assessment questionnaire) | Recommender + Security Command Center posture findings feed into framework reviews, but no single unified "review tool" branded identically |
| **Lens/workload-specific guidance** | "Lenses" for specific workload types (e.g., SaaS, ML)                                                                                                                  | "Workload" specific guides (e.g., mission-critical)      | Workload-specific guidance documents (e.g., AI/ML, data analytics) published separately                                                     |
| **Core intent**                     | Same across all three: give architects a shared, auditable vocabulary for evaluating designs against reliability, security, cost, performance, and operational quality | Same intent                                              | Same intent                                                                                                                                 |

## 8. Production & Enterprise Usage

- Large organizations formalize architecture review boards that evaluate every new system design against the Architecture Framework pillars before granting production approval, using it as a shared checklist rather than a one-time reading exercise.
- Regulated industries (finance, healthcare) often mandate active-active or active-passive multi-region deployment for tier-1 systems as part of business continuity policy, independent of whether the workload technically "needs" that resilience level day-to-day.
- Event-driven patterns are increasingly the default for new greenfield systems at scale, because they let teams ship independently without coordinating deploy schedules — a team consuming Pub/Sub events doesn't need to be online or aware of the producing team's release cycle.

## 9. Common Misconceptions

- **Misconception:** "Active-active is strictly better than active-passive." In reality, active-active trades operational simplicity for resilience, and for most workloads the added complexity of multi-region write consistency is not worth it unless the business genuinely cannot tolerate a multi-minute failover cutover.
- **Misconception:** "Event-driven architecture removes the need to think about ordering or duplicates." Pub/Sub delivers **at-least-once**, and does not guarantee strict ordering by default (ordering keys are opt-in and constrain throughput) — consumers must be designed to be idempotent and tolerant of out-of-order delivery unless ordering keys are explicitly configured.

## 10. Interview Questions

**🎯 Beginner:** _What is the difference between active-active and active-passive multi-region architecture?_
**Model answer:** In active-passive, one region serves all live traffic while a second region stands by (cold, warm, or hot but idle) and only takes over traffic after an explicit failover cutover. In active-active, two or more regions simultaneously serve live traffic, typically routed by proximity via a global load balancer, and failover is largely automatic since traffic simply stops being routed to an unhealthy region. Active-active requires a data layer capable of multi-region writes (like Cloud Spanner), while active-passive can use simpler single-writer replication (like a Cloud SQL cross-region read replica).

**🎯 Intermediate:** _How do Pub/Sub, Eventarc, and Cloud Run combine to implement an event-driven architecture?_
**Model answer:** Pub/Sub is the durable messaging backbone that decouples producers from consumers — producers publish to a topic without knowing who's subscribed. Eventarc standardizes event routing from many GCP sources (Cloud Storage, Firestore, audit logs, custom events) into a common CloudEvents format and can deliver those events as Pub/Sub messages or direct HTTP triggers. Cloud Run is the most common consumer: it receives triggered events and scales the number of running instances up or down (including to zero) based on event volume, so the system pays only for actual event processing rather than idle capacity.

**🎯 Senior/Architect:** _A retail client wants a multi-region e-commerce platform with an n-tier architecture, and asks whether to use active-active or active-passive. How do you decide, and what does the resulting architecture look like?_
**Model answer:** I'd start from the business requirement, not the pattern: what's the actual cost of downtime during a regional outage, and how quickly must service resume? For most e-commerce platforms, a few minutes of failover time during a rare regional outage is acceptable, so I'd default to active-passive to avoid the complexity of multi-region write consistency — global External ALB routing to a primary-region Managed Instance Group or GKE cluster, backed by Cloud SQL with a cross-region read replica kept warm in the secondary region, promoted on failover. I would reserve active-active (Spanner-backed, dual-region live traffic) only for a component where the client has explicitly quantified that even seconds of unavailability translate to significant revenue loss — for example, the checkout/payment path specifically, rather than the entire platform. This lets me apply the more complex, more expensive pattern surgically rather than architecting the whole n-tier stack around the hardest requirement in the system.

## 11. Key Takeaways

- 🔑 Active-passive trades resilience for simplicity (single-writer, manual/scripted cutover); active-active trades simplicity for near-zero failover time but requires a multi-region-write-capable data layer like Cloud Spanner.
- 🔑 The n-tier pattern (Global Load Balancer → stateless compute tier → managed data tier) lets each layer scale and fail over independently.
- 🔑 Event-driven architecture (Pub/Sub + Eventarc + Cloud Run) decouples producers from consumers, but requires idempotent, order-tolerant consumers since Pub/Sub is at-least-once by default.
- 🔑 The Google Cloud Architecture Framework is Google's equivalent of AWS's and Azure's well-architected frameworks — same intent (operational excellence, security, reliability, cost, performance), different branding and evolving pillar structure.

## 12. Related Concepts

Cloud Load Balancing (Section 22), Pub/Sub and Dataflow (Section 45), Eventarc and Workflows (Section 53), cost optimization pillar in depth (Section 57), disaster recovery and multi-region architecture (Section 58), and the consolidated GCP vs AWS vs Azure comparison (Section 82) all extend the patterns introduced here.
