# Section 79 (Part 11): Networking as Code (VPC/VNet Peering, Subnets, Security Groups/NSGs)

## 1. Definition

**Plain language:** Networking as code means declaring not just individual networks in isolation, but the connections _between_ them — peering two VPCs together, subdividing address space into subnets, and controlling what traffic is allowed to flow — entirely in Terraform, so the whole network topology is reviewable, versioned, and reproducible rather than assembled by hand across multiple consoles.

**Precise definition:** **Networking as code** extends the single-network provisioning covered in [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)–[§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) to inter-network connectivity and traffic control: **peering** (`aws_vpc_peering_connection`, `azurerm_virtual_network_peering`, `google_compute_network_peering`) establishes private routing between two otherwise isolated networks without traversing the public internet; **subnetting** divides a network's CIDR block into smaller, purpose-scoped address ranges (public-facing vs. private, per-AZ/zone/region); and **traffic control** (AWS security groups, Azure NSGs, GCP firewall rules) defines allow/deny rules that gate what can reach what. All three providers implement these concepts with materially different resource shapes and default postures, making this one of the areas where cross-provider translation mistakes are most consequential.

> 💡 **Tip:** Peering is never transitive on any of the three providers. If VPC A peers with VPC B, and VPC B peers with VPC C, traffic still cannot flow from A to C through B — each pair needs its own explicit peering connection (or a hub/transit construct like AWS Transit Gateway). This trips up engineers who reason about peering like routing, where transitivity would normally be expected.

## 2. Why This Matters

- **Peering topology is a common source of "why can't these two things talk to each other" production incidents**, and getting the non-transitivity property wrong at design time compounds as an organization's network grows.
- **Subnet CIDR planning done ad hoc breaks scaling** — under-provisioned address ranges force disruptive re-IP migrations later; Terraform makes CIDR planning an explicit, computable, reviewable step via functions like `cidrsubnet()` ([§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) instead of manual spreadsheet tracking.
- **Traffic-control resources are the most security-sensitive layer covered in this Part** — a misconfigured security group, NSG, or firewall rule is one of the most common root causes of real cloud security incidents, and Terraform's `plan` diff is the best available review checkpoint before such a mistake reaches production.

## 3. Prerequisites and Dependencies

Builds directly on the VPC/VNet/network fundamentals from [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) (`aws_vpc`, `aws_subnet`, `aws_security_group`), [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md) (`azurerm_virtual_network`, `azurerm_subnet`, `azurerm_network_security_group`), and [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) (`google_compute_network`, `google_compute_subnetwork`, `google_compute_firewall`). Also assumes the `cidrsubnet()` function from [§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) for computed subnet allocation.

## 4. Architecture / Conceptual Diagram

```text
              VPC-A (10.0.0.0/16)              VPC-B (10.1.0.0/16)
              us-east-1                         us-west-2
                    │                                  │
         aws_vpc_peering_connection.a_to_b (requester)
         aws_vpc_peering_connection_accepter.b (accepter, other region)
                    │◄───────────peering──────────────►│
                    │       (NOT transitive —          │
                    │        does not reach VPC-C)     │
                    │                                  │
         aws_route.a_to_b_route              aws_route.b_to_a_route
         (10.1.0.0/16 → pcx-xxxx)            (10.0.0.0/16 → pcx-xxxx)

    Within VPC-A:
         subnet-public (10.0.1.0/24)  ──security_group──►  0.0.0.0/0:443 allowed
         subnet-private (10.0.2.0/24) ──security_group──►  only from subnet-public

    Peering requires explicit ROUTES on both sides in addition
    to the peering connection itself — the connection alone does
    not make traffic flow; routes must point at it explicitly.
```

- A peering _connection_ resource and the _routes_ that make use of it are separate resources on all three providers — a common mistake is creating the peering connection and stopping there, leaving no route pointing traffic at it.
- Security groups (AWS) are stateful and instance-attached; NSGs (Azure) and firewall rules (GCP) are stateful too but attach at the subnet/network level by default — the placement difference matters when auditing "what actually protects this workload."

## 5. Hands-On

### 5.1 VPC Peering (AWS)

**Purpose:** Connect two VPCs in different regions so resources in each can reach each other privately.

**Syntax:**

```hcl
resource "aws_vpc_peering_connection" "a_to_b" {
  vpc_id      = aws_vpc.a.id
  peer_vpc_id = aws_vpc.b.id
  peer_region = "us-west-2"
  auto_accept = false
}

resource "aws_vpc_peering_connection_accepter" "b" {
  provider                 = aws.us_west_2
  vpc_peering_connection_id = aws_vpc_peering_connection.a_to_b.id
  auto_accept                = true
}

resource "aws_route" "a_to_b" {
  route_table_id            = aws_route_table.a_private.id
  destination_cidr_block    = aws_vpc.b.cidr_block
  vpc_peering_connection_id = aws_vpc_peering_connection.a_to_b.id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_vpc_peering_connection.a_to_b will be created
  # aws_vpc_peering_connection_accepter.b will be created
  # aws_route.a_to_b will be created

Plan: 3 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
```

**Production usage example:** Cross-region peering requires a second `aws` provider alias ([§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)) configured for the peer region — `provider = aws.us_west_2` above — since a single provider block is pinned to one region and the accepter resource must run against the peer VPC's own region.

**Common errors:** Creating the peering connection and accepter but forgetting the `aws_route` resources on _both_ sides is the most common mistake — the connection shows as `active` in the AWS console, giving false confidence, but no traffic actually flows until routes on both route tables point at it.

### 5.2 VNet Peering (Azure)

**Purpose:** Connect two VNets, illustrating Azure's requirement for a peering resource on _each_ side, symmetric and independently configured.

**Syntax:**

```hcl
resource "azurerm_virtual_network_peering" "a_to_b" {
  name                      = "peer-a-to-b"
  resource_group_name       = azurerm_resource_group.a.name
  virtual_network_name      = azurerm_virtual_network.a.name
  remote_virtual_network_id = azurerm_virtual_network.b.id
}

resource "azurerm_virtual_network_peering" "b_to_a" {
  name                      = "peer-b-to-a"
  resource_group_name       = azurerm_resource_group.b.name
  virtual_network_name      = azurerm_virtual_network.b.name
  remote_virtual_network_id = azurerm_virtual_network.a.id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # azurerm_virtual_network_peering.a_to_b will be created
  # azurerm_virtual_network_peering.b_to_a will be created

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Unlike AWS's requester/accepter split, Azure's peering is two fully symmetric resources — production modules typically wrap both directions in one child module invoked once per VNet pair, so callers can't accidentally create a one-directional (broken) peering.

**Common errors:** Creating only `a_to_b` and forgetting `b_to_a` leaves the peering in a `Disconnected` state on Azure's side — traffic doesn't flow in either direction until both peering resources exist, unlike some mental models that assume one direction "mostly works."

### 5.3 Firewall Rules (GCP) and Subnet CIDR Planning

**Purpose:** Show GCP's network-attached firewall model and computed subnet CIDR allocation via `cidrsubnet()`.

**Syntax:**

```hcl
resource "google_compute_firewall" "allow_internal" {
  name    = "allow-internal"
  network = google_compute_network.vpc.id

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  source_ranges = ["10.0.0.0/16"]
}

resource "google_compute_subnetwork" "zone" {
  for_each      = toset(["us-central1", "us-east1", "europe-west1"])
  name          = "subnet-${each.key}"
  region        = each.key
  network       = google_compute_network.vpc.id
  ip_cidr_range = cidrsubnet("10.0.0.0/16", 8, index(["us-central1", "us-east1", "europe-west1"], each.key))
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # google_compute_firewall.allow_internal will be created
  # google_compute_subnetwork.zone["us-central1"] will be created
  # google_compute_subnetwork.zone["us-east1"] will be created
  # google_compute_subnetwork.zone["europe-west1"] will be created

Plan: 4 to add, 0 to change, 0 to destroy.
```

**Production usage example:** `cidrsubnet()` computing per-region CIDR blocks from a single parent range (rather than hardcoding each region's `/24`) means adding a fourth region is a one-line change to the `for_each` set — the CIDR math is derived, not manually re-planned each time.

**Common errors:** Using `index()` against a list inside `for_each` (as shown) works but is fragile if the list's order ever changes — reordering the region list silently reassigns which region gets which CIDR block on the next `apply`, forcing subnet recreation; a static `map(string) -> number` of region-to-CIDR-index is safer for anything long-lived.

## 6. Production Usage Notes

- Peering topology should be diagrammed and version-controlled as explicitly as the Terraform code itself — because peering is non-transitive, an org with more than a handful of networks quickly needs either a documented mesh or a hub/transit design (AWS Transit Gateway, Azure Virtual WAN, GCP's Network Connectivity Center), not ad hoc pairwise peering.
- Security group/NSG/firewall-rule sprawl (dozens of overlapping, undocumented rules) is one of the most common sources of "nobody knows why this port is open" findings in security audits — Terraform's ability to name, tag, and comment every rule in version control is a direct mitigation if the discipline is maintained.
- CIDR planning should reserve headroom explicitly — allocating exactly the address space currently needed, with no room for a new subnet later, is a common oversight that eventually forces a disruptive re-IP.

## 7. Security Considerations

- Default-deny is the correct starting posture on all three providers for custom (non-default) networks — explicitly allow only the traffic a workload needs, rather than starting broad and trying to narrow later.
- Peering connections do not respect the peer network's own security groups/NSGs/firewall rules automatically in all cases — always verify that traffic allowed by the peering _and_ route configuration is also explicitly permitted by the destination's own traffic-control rules; peering alone does not grant access, it only makes the path reachable.
- Cross-region and cross-account/subscription/project peering ([§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md)) introduces a governance question — who can approve a peering request into a shared or sensitive network — that should be enforced via policy-as-code (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), not just code review discipline.

## 8. Common Troubleshooting Scenarios

| Symptom                                                         | Likely Cause                                                                   | Resolution Path                                                                         |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| Peering shows "active"/"connected" but no traffic flows         | Routes weren't created on one or both sides pointing at the peering connection | Add explicit route resources referencing the peering connection ID on both route tables |
| Resources in VPC-A can't reach resources in VPC-C via VPC-B     | Peering is not transitive on any provider                                      | Establish a direct A↔C peering, or introduce a hub/transit gateway construct            |
| Azure VNet peering stuck in "Disconnected"                      | Only one of the two symmetric peering resources was created                    | Create the matching peering resource on the other VNet                                  |
| Unexpected subnet recreation after reordering a `for_each` list | `cidrsubnet()` combined with `index()` against a list whose order changed      | Use a stable map keyed by region name instead of positional list indexing               |

## 9. Best Practices

- Always pair a peering connection with the explicit route resources needed on both sides in the same module, so the two can never be applied out of sync.
- Use computed CIDR allocation (`cidrsubnet()`) keyed by stable identifiers (a map, not a list index) rather than hardcoded or positionally-derived subnet ranges.
- Default every custom network's traffic-control rules to deny, and add narrowly scoped allow rules per workload rather than broad allow rules narrowed later.

## 10. Common Anti-Patterns / Mistakes

- **Assuming peering is transitive.** It never is on any of the three providers; each pair needs its own explicit connection or a hub/transit construct.
- **Creating a peering connection without corresponding routes**, leaving a connection that looks "active" but carries no traffic — a frequent source of confusing "it's connected but doesn't work" tickets.
- **Reserving no CIDR headroom** when initially planning subnets, forcing a disruptive re-IP migration the first time a new subnet is needed and no address space remains.

## 11. Interview Questions

**🎯 Beginner:** _"If VPC A is peered with VPC B, and VPC B is peered with VPC C, can traffic flow from A to C?"_
**Model answer:** No. VPC peering is not transitive on any major provider — A and C would need their own direct peering connection, or the organization would need a hub/transit construct (like AWS Transit Gateway) that all three connect to.
_What the interviewer is probing for:_ Whether the candidate has this specific, frequently-tested property memorized correctly, since it's a common source of real misconfiguration.

**🎯 Intermediate:** _"You've created an `aws_vpc_peering_connection` and confirmed it shows as `active`, but instances in the two VPCs still can't reach each other. What's the most likely missing piece?"_
**Model answer:** Routes. The peering connection resource only establishes the logical connection; it does not automatically add routes to either VPC's route tables. Both sides need an explicit `aws_route` (or equivalent route table entry) with the peer VPC's CIDR as the destination and the peering connection as the target. Additionally, security groups on the destination resources must explicitly allow traffic from the peer VPC's CIDR range — the peering being active doesn't override traffic-control rules.
_What the interviewer is probing for:_ Practical debugging knowledge — knowing that "active" peering status is necessary but not sufficient for traffic to actually flow.

**🎯 Senior:** _"How would you design subnet CIDR allocation in Terraform so that adding a new region or availability zone later doesn't require manually renumbering existing subnets?"_
**Model answer:** Use `cidrsubnet()` to derive each subnet's range from a single parent CIDR block, keyed by a stable, order-independent identifier — a map from region/AZ name to a fixed subnet index, not a list position computed via `index()`, since reordering a list changes positional indices and forces recreation of unrelated subnets. Reserve deliberate headroom in the parent CIDR (e.g., size the subnet mask assuming twice the currently needed number of regions) so a new region's subnet is purely additive — a new map entry — rather than requiring the parent block itself to be resized, which would force renumbering everything downstream.
_What the interviewer is probing for:_ Understanding that stability under `for_each`/map keys, not just correct CIDR math, is what prevents unnecessary resource churn as the topology grows.

**🎯 Architect:** _"An organization has grown to 15 VPCs across three AWS accounts, all pairwise-peered as needed over two years of ad hoc requests. What's wrong with this topology, and how would you redesign it?"_
**Model answer:** Pairwise peering at 15 VPCs means up to 105 potential peering connections if fully meshed, each with its own routes and security group considerations to audit — this is a maintenance and security-review burden that scales quadratically and is exactly the failure mode hub/transit architectures exist to avoid. The redesign is a hub-and-spoke model using AWS Transit Gateway (or the Azure Virtual WAN / GCP Network Connectivity Center equivalents in a multi-cloud context, covered further in [§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md)): every VPC peers (attaches) once to a central transit resource instead of pairwise to every other VPC it needs to reach, reducing the connection count to one per VPC and centralizing route and access-control review to the transit gateway's route tables and attachment policies. The migration itself needs to be staged carefully — existing pairwise peerings can't simply be deleted before transit gateway routes are proven to replace them, so this is a multi-phase cutover with rollback checkpoints, ideally validated with `terraform plan` review at each stage and monitored traffic-flow logs confirming no path is silently broken.
_What the interviewer is probing for:_ Recognition of the quadratic-scaling problem with pairwise peering meshes, familiarity with the hub/transit alternative, and a realistic, staged migration approach rather than a "just replace it" answer.

## 12. Common Misconceptions

1. **"Peering is transitive, like routing through a shared gateway."** It is never transitive on any of the three providers; each pair requires its own explicit connection.
2. **"An 'active' peering connection means traffic is flowing."** It means the logical connection exists; routes on both sides and traffic-control rules on the destination still gate actual traffic.
3. **"Azure VNet peering, like AWS, has a requester/accepter distinction."** Azure's peering is two fully symmetric resources, one per VNet, both required.
4. **"CIDR allocation via `for_each` and `cidrsubnet()` is inherently stable."** It's only stable if keyed by an order-independent identifier (a map); positional list indexing reassigns ranges on reordering.

## 13. 🔑 Key Takeaways

- Peering is never transitive on AWS, Azure, or GCP — reaching a third network always requires either a direct additional peering connection or a hub/transit construct.
- A peering connection and the routes that use it are separate resources everywhere; "active" status does not imply routes exist.
- AWS peering has an asymmetric requester/accepter model (often cross-region, requiring a provider alias); Azure peering is fully symmetric and requires a resource on both VNets.
- Stable, map-keyed CIDR allocation via `cidrsubnet()` avoids unintended subnet recreation when the set of regions/zones changes.
- Traffic-control rules (security groups, NSGs, firewall rules) still gate access across an active peering connection — peering alone does not grant access.

## 14. Related Concepts & What's Next

[§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md), [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md), and [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) established the single-network resource vocabulary (VPC/VNet, subnet, security group/NSG/firewall) this section extended into inter-network connectivity. [§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md) (provider aliases) is required for the cross-region AWS peering pattern in 5.1. [§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md) picks up the hub/transit and multi-region/multi-account topology question raised in the architect answer above as its own dedicated topic. [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) now turns from network-layer access control to identity-layer access control — IAM as code across all three providers.

**Next Section:** [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) — `Section-80-Part11-IAM-as-Code-Across-Providers.md`
