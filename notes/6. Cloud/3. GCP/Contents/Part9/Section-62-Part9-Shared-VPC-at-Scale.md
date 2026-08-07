# Section 62 (Part 9): Shared VPC at Scale & Multi-Project Networking

## 1. Definition

**Plain language:** [Section 25](../Part3/Section-25-Part3-Shared-VPC-Peering-PSC.md) introduced Shared VPC as the mechanism letting one project own the network while other projects attach to it and use its subnets. That works cleanly for a handful of projects. This section is about what changes when it's not a handful — it's dozens of teams, several environments, and a networking team that cannot realistically hand-approve every attachment request without becoming the organization's biggest bottleneck.

**Precise:** **Shared VPC at scale** is the design pattern for operating one or more Shared VPC **host projects** as permanent landing-zone infrastructure ([Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md)) serving many **service projects** across an enterprise, using delegated IAM roles so that networking administration stays centralized while day-to-day subnet attachment and Private Service Connect consumption are self-service for individual teams within boundaries the networking team defines in advance.

## 2. Why It Exists / Problem It Solves

- [Section 25](../Part3/Section-25-Part3-Shared-VPC-Peering-PSC.md) covered the mechanics of a single host project and a single service project attaching to it. In an enterprise landing zone, the real question is architectural: how many host projects should exist (one? one per environment? one per business unit?), who is allowed to attach a new service project, and who is allowed to request a new subnet — answered once, centrally, rather than negotiated ad hoc every time a new team onboards.
- Without a deliberate pattern, two failure modes are common: (1) every team creates its own VPC, leading to a sprawl of disconnected networks that need complex peering or VPN mesh to communicate, defeating the purpose of Shared VPC entirely; or (2) one host project is used but the networking team becomes a manual approval bottleneck for every subnet-level IAM change, slowing every team's onboarding.
- The landing zone ([Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md)) provisions Shared VPC host projects during its networking stage specifically to avoid both failure modes — a small, deliberately chosen number of host projects exist from day one, and delegated IAM ([Section 62](./Section-62-Part9-Shared-VPC-at-Scale.md).4) lets teams self-serve attachment without needing the networking team to hand-run every request.

## 3. Host Project Topology Choices at Enterprise Scale

| Topology                            | Description                                                                                                  | When Chosen                                                                                                                                                                                                                       |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Single host project (org-wide)**  | One host project, one VPC, subnets segmented by environment and region, every service project attaches to it | Smaller-to-mid-size orgs, or orgs where production/nonproduction separation is enforced entirely through IAM and Organization Policy rather than network isolation                                                                |
| **Per-environment host projects**   | Separate host projects for production, nonproduction, and sandbox, each with its own VPC                     | Most common enterprise pattern (matches the folder structure in [Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md).5) — provides a hard network boundary between environments in addition to IAM boundaries |
| **Per-business-unit host projects** | Separate host project per business unit (each potentially further split by environment)                      | Large, decentralized enterprises where business units need independent network administration and cannot share a single networking team's change queue                                                                            |

> 💡 **Tip:** The per-environment topology is the default recommendation because it adds a genuine network-layer boundary (separate VPCs cannot route to each other without deliberate peering or a Network Connectivity Center hub) on top of the IAM/Organization-Policy boundary between production and nonproduction — a defense-in-depth property that a single shared VPC across environments cannot offer, since a single misconfigured firewall rule in a single-VPC design risks crossing the environment boundary.

## 4. IAM for Shared VPC: Delegated Administration

- **`roles/compute.xpnAdmin`** — granted at the organization or folder level to the networking team; lets holders designate any project as a host project and enable/disable Shared VPC.
- **`roles/compute.networkAdmin`** on the host project — full control over the host project's VPC, subnets, routes, and firewall rules; held by the central networking team, not by service project owners.
- **`roles/compute.networkUser`** — the key delegation role for self-service at scale. Granted **per subnet** (via IAM conditions or subnet-level IAM bindings, not just at the host project level) to a specific service project's service accounts/group, it allows that service project to create resources (VMs, GKE clusters) using that specific subnet, without granting any ability to modify the subnet itself, see other subnets, or touch firewall rules.
- **`roles/compute.networkViewer`** — read-only visibility into the host project's network configuration, commonly granted broadly to service project teams so they can see what subnets and IP ranges exist when planning their own resource placement, without any modification rights.

### 4.1 The Self-Service Onboarding Flow

1. The networking team pre-creates subnets for each expected team/environment combination during landing zone provisioning or as part of a standard "new team" runbook, sized generously enough to avoid frequent resizing ([Section 20](../Part3/Section-20-Part3-Subnets-IP-Addressing-and-Routes.md)-adjacent CIDR planning).
2. A new service project is vended ([Section 63](./Section-63-Part9-Folder-Project-Vending-Automation.md)) already carrying the correct `compute.networkUser` binding for its designated subnet(s) as part of the standard baseline — the team never files a manual ticket to "get network access," because the project factory already granted it based on which environment/business-unit folder the project was created under.
3. Ongoing subnet-level changes (a new subnet, a changed CIDR range, a new firewall rule) still route through the central networking team, since those actions require `compute.networkAdmin`, deliberately kept out of individual teams' hands.

> ⚠️ **Interview-relevant nuance:** `compute.networkUser` granted at the **subnet** level (not the project level) is the detail that makes Shared VPC genuinely scale to many teams safely — project-level `networkUser` would let a service project use _every_ subnet in the host project, including ones belonging to other teams' workloads, defeating the segmentation the subnet design was meant to provide.

## 5. Private Service Connect at Scale

- [Section 25](../Part3/Section-25-Part3-Shared-VPC-Peering-PSC.md) introduced **Private Service Connect (PSC)** as a mechanism for privately consuming a managed service (or another team's internal service) without traversing the public internet or requiring full VPC peering. At enterprise scale, PSC becomes the standard way service projects consume both Google-managed APIs and other teams' internally published services, without adding VPC peering relationships that become difficult to reason about as the number of projects grows.
- A **PSC endpoint** created inside a service project's attached subnet gives that service project a private IP address routing to the target service, while the target service's operator controls exactly which consumers are allowed to connect via a **service attachment** with an explicit accept list — this scales far better than peering, where every new consumer requires a new bidirectional peering relationship and NxN routing complexity grows with the number of projects involved.
- Enterprises publishing internal platform services (a shared logging ingestion API, a shared authentication service) as PSC service attachments let any authorized service project consume them with a single endpoint creation, rather than needing a dedicated peering connection or a Shared VPC attachment to the platform team's own project.

## 6. Architecture Diagram

```
                    fldr: production                       fldr: nonproduction
                          │                                        │
              host-prod (compute.networkAdmin: netadmin-team)  host-nonprod
              VPC: vpc-prod                                    VPC: vpc-nonprod
                  │                                               │
      ┌───────────┼───────────┐                        ┌──────────┼──────────┐
      ▼           ▼           ▼                        ▼          ▼          ▼
  subnet-a     subnet-b    subnet-c                 subnet-a   subnet-b   subnet-c
  (team-pay)  (team-ord)  (team-plat)               (team-pay)(team-ord) (team-plat)
      │           │           │
  networkUser  networkUser  networkUser
  granted to   granted to   granted to
  svc-payments svc-orders   svc-platform
  (prod)       (prod)       (prod)
      │           │           │
      ▼           ▼           ▼
 svc-payments  svc-orders  svc-platform
 (service       (service     (service
  project)       project)     project)
      │
      └──► PSC endpoint ──► service attachment (published by another team's
                              internal service, or a Google-managed API)
```

## 7. Hands-On Example: Granting Subnet-Scoped Network User Access

**Purpose:** Delegate the ability to use a specific production subnet to a service project's compute service account, without granting broader host-project access.

```bash
gcloud compute networks subnets add-iam-policy-binding subnet-a \
  --project=host-prod \
  --region=us-central1 \
  --member="serviceAccount:svc-payments-compute@svc-payments-prod.iam.gserviceaccount.com" \
  --role="roles/compute.networkUser"
```

**Expected output:**

```
Updated IAM policy for subnet [subnet-a].
bindings:
- members:
  - serviceAccount:svc-payments-compute@svc-payments-prod.iam.gserviceaccount.com
  role: roles/compute.networkUser
etag: BwYqQZ...
```

**Purpose:** Confirm which service projects are currently attached to a host project, useful when auditing Shared VPC attachment sprawl.

```bash
gcloud compute shared-vpc associated-projects list host-prod
```

**Expected output:**

```
RESOURCE_ID
svc-payments-prod
svc-orders-prod
svc-platform-prod
```

> 💡 **Tip:** Binding IAM at the subnet resource (`gcloud compute networks subnets add-iam-policy-binding`) rather than the host project is the step teams most commonly skip, then wonder why a service project with project-level `compute.networkUser` still cannot use subnets it wasn't explicitly granted — project-level `networkUser` alone does not exist as a meaningful broad grant in a well-segmented design; the subnet-level binding is the actual control point.

## 8. Production & Enterprise Usage

- Enterprises track subnet-to-team ownership as part of their Shared VPC design documentation (commonly encoded directly in the Terraform that provisions subnets and their `networkUser` bindings together, so ownership is never ambiguous or undocumented) — this is provisioned during the `3-networking` stage of the Enterprise Foundations Blueprint ([Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md).4).
- CIDR ranges for every subnet across every host project are planned centrally and tracked in an IP address management (IPAM) sheet or tool before any subnet is created, since Shared VPC's core promise — no overlapping ranges, clean routing — collapses if two teams are independently allocating ranges without central coordination.
- Regular audits of `compute.networkUser` bindings (who has access to which subnet) are standard practice, since stale bindings — a service project retaining access to a subnet after its workload has migrated elsewhere — are a common source of unexpected lateral network reachability during a security review.

## 9. Common Misconceptions

- **Misconception:** "Shared VPC means every project in the org shares one giant flat network." False — subnets segment the network by team/environment, and `compute.networkUser` at the subnet level restricts each service project to only the subnet(s) it was explicitly granted, not the whole host project's address space.
- **Misconception:** "Granting `compute.networkUser` at the project level is simpler and just as safe as subnet-level grants." False at any meaningful scale — project-level grants let a service project use every current and future subnet in the host project, silently expanding a team's reachability every time the networking team adds a new subnet for someone else.
- **Misconception:** "Private Service Connect and VPC Peering are interchangeable at scale." They solve different shapes of problem — PSC scales cleanly to many consumers of one published service via an accept list on the publisher's side, while peering creates a bidirectional relationship whose complexity grows roughly with the square of the number of participating networks; PSC is generally preferred for the many-consumers-of-one-service pattern common at enterprise scale.

## 10. Interview Questions

**🎯 Beginner:** _What problem does granting `compute.networkUser` at the subnet level, rather than the project level, solve?_
**Model answer:** A host project typically has many subnets, each intended for a different team or environment. Granting `compute.networkUser` at the project level would let a service project use every subnet in the host project, including ones belonging to other teams, breaking the segmentation the subnet design exists to provide. Granting it at the specific subnet level restricts a service project to only the subnet(s) it was explicitly authorized to use, so adding a new subnet for one team never silently expands another team's network reachability.

**🎯 Intermediate:** _An enterprise is deciding between a single org-wide Shared VPC host project and separate host projects per environment (production, nonproduction, sandbox). What's the key trade-off?_
**Model answer:** A single host project is simpler to administer — one VPC, one set of routes and firewall rules to reason about — but means production and nonproduction share the same network fabric, relying entirely on IAM and firewall rules (not network topology) to keep them separated, and a misconfiguration risks crossing that boundary. Separate host projects per environment add a genuine network-layer boundary — separate VPCs that cannot route to each other without deliberate peering or a connectivity hub — providing defense-in-depth on top of IAM, at the cost of more infrastructure to manage and, if cross-environment communication is ever legitimately needed, additional peering or hub-and-spoke design. Most enterprises choose per-environment host projects specifically for the added isolation.

**🎯 Senior/Architect:** _A platform team wants to publish an internal authentication service that dozens of other service projects across multiple host projects need to consume privately, without VPC peering sprawl. How would you design this with Private Service Connect?_
**Model answer:** I would have the platform team front their authentication service with an internal load balancer and publish it as a PSC **service attachment**, configuring an explicit accept list (or an automatic-accept policy scoped to specific projects/organizations) rather than accepting all connections. Each consuming service project — regardless of which host project's Shared VPC it's attached to — would then create a PSC **endpoint** in its own attached subnet, giving it a private IP that routes to the authentication service without any VPC peering relationship between the consumer's host project and the platform team's project. This scales linearly: adding the fortieth consumer means creating one more PSC endpoint and one more accept-list entry, not a new bidirectional peering relationship with NxN complexity, and it also means the platform team retains full control over exactly which projects are authorized to connect, independent of the broader Shared VPC IAM ([Section 62](./Section-62-Part9-Shared-VPC-at-Scale.md).4) governing subnet usage.

## 11. Key Takeaways

- 🔑 At enterprise scale, Shared VPC topology is a deliberate choice — single org-wide host project, per-environment host projects (most common), or per-business-unit host projects — made once as part of the landing zone, not improvised project by project.
- 🔑 `compute.networkUser` granted at the **subnet** level, not the project level, is what makes Shared VPC scale safely to many teams without silently expanding reachability as new subnets are added.
- 🔑 Self-service onboarding works by pre-granting the correct subnet-level IAM as part of automated project vending ([Section 63](./Section-63-Part9-Folder-Project-Vending-Automation.md)), removing the networking team from the day-to-day approval path while keeping subnet/firewall administration centralized.
- 🔑 Private Service Connect scales the many-consumers-of-one-service pattern far better than VPC peering, via an accept-list on the publishing side rather than a bidirectional relationship per consumer.

## 12. Related Concepts

Shared VPC and Private Service Connect fundamentals ([Section 25](../Part3/Section-25-Part3-Shared-VPC-Peering-PSC.md)), subnet/CIDR design ([Section 20](../Part3/Section-20-Part3-Subnets-IP-Addressing-and-Routes.md)), landing zone networking stage ([Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md).4), Organization Policy restriction of allowed subnets ([Section 60](./Section-60-Part9-Organization-Policy-Hierarchy-Deep-Dive.md).4's `compute.restrictSharedVpcSubnetworks`), and automated project vending granting the IAM bindings described here ([Section 63](./Section-63-Part9-Folder-Project-Vending-Automation.md)) all connect directly to this section.
