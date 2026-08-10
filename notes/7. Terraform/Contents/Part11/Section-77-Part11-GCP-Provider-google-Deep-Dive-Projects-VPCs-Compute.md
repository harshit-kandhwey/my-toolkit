# Section 77 (Part 11): GCP Provider (google) Deep Dive: Projects, VPCs, Compute Instances

## 1. Definition

**Plain language:** The `google` provider lets Terraform create GCP resources. GCP's organizing unit is the **project** — every resource lives inside exactly one project, which functions as GCP's billing, IAM, and API-enablement boundary all at once, playing a role that sits somewhere between AWS's account and Azure's resource group.

**Precise definition:** The **`google` provider** (`hashicorp/google`, with a parallel `google-beta` provider for pre-GA features) maps HCL resource blocks to Google Cloud APIs. Every resource requires a `project` (often supplied at the provider level rather than per-resource) and most require the relevant Google Cloud API to be explicitly enabled via `google_project_service` before the resource type can be created — a provisioning step with no direct AWS or Azure equivalent, since those platforms don't require explicit per-API activation. GCP's networking model is also structurally distinct: `google_compute_network` (GCP's VPC equivalent) is **global by default**, with subnets (`google_compute_subnetwork`) being the region-scoped construct — the reverse of AWS/Azure, where the VPC/VNet itself is regional.

> 💡 **Tip:** A `google_compute_instance` created without an explicit `google_project_service` enabling `compute.googleapis.com` first will fail with an API-not-enabled error, not a resource-not-found error — this trips up engineers coming from AWS/Azure, where API "enablement" isn't a provisioning step at all, it's just always on.

## 2. Why This Matters

- **GCP is the third major hyperscaler** in most multi-cloud Terraform codebases, and its project/API-enablement model is different enough from AWS and Azure that naive translation between them breaks.
- **The global-VPC/regional-subnet model** is the opposite of AWS's and Azure's regional-VPC model — getting this backwards is a common source of confused `plan` output when engineers assume symmetry across providers.
- **Explicit API enablement as a provisioning step** is unique to GCP among the three major providers and is a frequent first-apply failure for teams new to the `google` provider.

## 3. Prerequisites and Dependencies

Builds on the AWS ([§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)) and Azure ([§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md)) provider deep dives this section directly contrasts against, and on provider authentication patterns from [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) (GCP typically uses a service account JSON key or Workload Identity Federation). General GCP service familiarity is assumed — see `../../../6. Cloud/3. GCP/` for that background; this section covers only the Terraform provisioning layer.

## 4. Architecture / Conceptual Diagram

```text
                    google_project.app
                    (project_id = "my-app-prod-123")
                                 │
                    google_project_service.compute
                    (enables compute.googleapis.com)
                                 │
                    google_compute_network.vpc
                    (GLOBAL resource — auto_create_subnetworks = false)
                                 │
                ┌────────────────┴─────────────────┐
                │                                  │
      google_compute_subnetwork.us     google_compute_subnetwork.eu
      (region = "us-central1",          (region = "europe-west1",
       10.0.1.0/24)                      10.0.2.0/24)
                │                                  │
      google_compute_instance.web       google_compute_instance.eu_app
                │
      google_compute_firewall.allow-https
      (attaches to the VPC by network reference,
       not to the instance directly — like Azure NSGs,
       unlike AWS security groups)

      google_service_account.vm_sa  ← attached via service_account
      block on google_compute_instance (GCP's IAM-role-equivalent
      binding to compute)
```

- The network (`google_compute_network`) is a single global resource; subnets under it are pinned to specific regions — a single VPC can span every GCP region without any peering, unlike AWS/Azure where cross-region reach requires explicit peering or a transit construct.
- Firewall rules (`google_compute_firewall`) attach to the network as a whole (filtered further by target tags or service accounts), conceptually closer to Azure's NSG-as-separate-resource model than AWS's security-group-per-instance model.

## 5. Hands-On

### 5.1 Project Configuration and API Enablement

**Purpose:** Confirm the project boundary and explicitly enable the Compute Engine API before any compute resource can be created — the GCP-specific provisioning step with no AWS/Azure equivalent.

**Syntax:**

```hcl
provider "google" {
  project = "my-app-prod-123"
  region  = "us-central1"
}

resource "google_project_service" "compute" {
  project = "my-app-prod-123"
  service = "compute.googleapis.com"

  disable_on_destroy = false
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # google_project_service.compute will be created

Plan: 1 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

$ terraform apply    # google_compute_instance applied before this exists
Error: Error creating instance: googleapi: Error 403: Compute Engine API
has not been used in project my-app-prod-123 before or it is disabled
```

**Production usage example:** Production GCP root modules enable every API a module's resources depend on as one of the first resources applied, often via `for_each` over a list of required service names, and set `disable_on_destroy = false` so a `terraform destroy` doesn't disable APIs still needed by resources outside this module's scope.

**Common errors:** Applying a `google_compute_instance` in the same `apply` run as the `google_project_service` that enables its API can still fail intermittently — API enablement is asynchronous on GCP's side and may not have fully propagated even after Terraform reports the `google_project_service` resource as created; an explicit `depends_on` plus, in stubborn cases, a brief `time_sleep` ([§38](../Part5/Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md)) resource is a documented workaround.

### 5.2 VPC and Subnet Provisioning

**Purpose:** Provision the global network and its region-scoped subnets, contrasting with AWS/Azure's regional-VPC model.

**Syntax:**

```hcl
resource "google_compute_network" "vpc" {
  name                    = "app-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.compute]
}

resource "google_compute_subnetwork" "us_central" {
  name          = "app-subnet-us-central1"
  ip_cidr_range = "10.0.1.0/24"
  region        = "us-central1"
  network       = google_compute_network.vpc.id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # google_compute_network.vpc will be created
  # google_compute_subnetwork.us_central will be created

Plan: 2 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

**Production usage example:** `auto_create_subnetworks = false` is the standard production setting — the default `true` creates one automatic subnet per region across the _entire_ GCP footprint, which is rarely the intended topology and makes CIDR planning effectively impossible to control.

**Common errors:** Leaving `auto_create_subnetworks` at its default `true` and then trying to also declare explicit `google_compute_subnetwork` resources produces overlapping CIDR ranges and confusing `plan` diffs — this is the single most common GCP networking misconfiguration for engineers new to the provider.

### 5.3 Compute Instance Provisioning

**Purpose:** Launch a VM inside the subnet, attached to a service account for GCP's IAM-equivalent binding.

**Syntax:**

```hcl
resource "google_service_account" "vm_sa" {
  account_id   = "web-vm-sa"
  display_name = "Web VM Service Account"
}

resource "google_compute_instance" "web" {
  name         = "web-instance"
  machine_type = "e2-small"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.us_central.id
    access_config {}    # ephemeral public IP
  }

  service_account {
    email  = google_service_account.vm_sa.email
    scopes = ["cloud-platform"]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # google_service_account.vm_sa will be created
  # google_compute_instance.web will be created

Plan: 2 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.

$ terraform apply    # after changing machine_type to e2-medium
  ~ machine_type = "e2-small" -> "e2-medium"
Plan: 0 to add, 1 to change, 0 to destroy.
```

**Production usage example:** `scopes = ["cloud-platform"]` combined with fine-grained IAM bindings on the service account itself (rather than broad legacy scopes like `compute-rw`) is the modern recommended pattern — access control is enforced by IAM policy bindings on the service account, not by the instance-level scope list, mirroring how [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) recommends handling least privilege across all three providers.

**Common errors:** Omitting the `access_config {}` block entirely (even empty) means the instance gets no public IP — unlike AWS's `map_public_ip_on_launch` toggle on the subnet, GCP's public-IP assignment is controlled per network interface on the instance itself, and its absence is easy to miss since the block takes no required arguments.

## 6. Production Usage Notes

- Explicit API enablement (5.1) should be treated as a foundational, always-first resource group in any GCP root module — bootstrapping scripts or a dedicated `apis` module applied before anything else avoids the propagation-delay failures described above.
- Because `google_compute_network` is global, a single production VPC can legitimately span every region an organization operates in without peering — the design question in GCP is usually about _firewall segmentation within_ one VPC rather than _how many VPCs to peer_, a different default posture from AWS/Azure.
- `google-beta` (a separate provider block) is required for pre-GA resource arguments; mixing `google` and `google-beta` resources in the same module is normal and expected, not a smell.

## 7. Security Considerations

- Prefer per-service-account IAM bindings (`google_project_iam_member` scoped to a specific service account) over broad legacy OAuth scopes on the instance — scopes are a coarse, largely legacy access-control layer that IAM policy bindings have superseded.
- `google_compute_firewall` rules default-deny all ingress except what's explicitly allowed, but the _default network_ (when `auto_create_subnetworks = true`) ships with permissive default firewall rules allowing internal traffic broadly — a custom VPC (`auto_create_subnetworks = false`, as in 5.2) starts with no implicit rules and requires everything to be declared explicitly, which is the safer starting point.
- Avoid attaching a service account with the broad `roles/editor` or `roles/owner` project-level role to a VM "for convenience" — this is the GCP equivalent of the AWS `AdministratorAccess`-on-EC2 anti-pattern flagged in [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                   | Resolution Path                                                                                               |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `Error 403: <API> has not been used in project ... or it is disabled` | The relevant `google_project_service` wasn't applied, or hasn't propagated yet | Apply the `google_project_service` resource first with an explicit `depends_on`, retry after a short delay    |
| Overlapping subnet CIDR errors                                        | `auto_create_subnetworks = true` combined with manually declared subnets       | Set `auto_create_subnetworks = false` and declare all subnets explicitly                                      |
| VM has no public IP despite expecting one                             | Missing `access_config {}` block inside `network_interface`                    | Add an empty `access_config {}` block to request an ephemeral public IP                                       |
| Instance can't reach other GCP APIs despite a service account         | Service account lacks IAM role bindings, or `scopes` excludes `cloud-platform` | Grant specific IAM roles to the service account and confirm the instance scope list includes `cloud-platform` |

## 9. Best Practices

- Always set `auto_create_subnetworks = false` on custom VPCs and declare subnets explicitly for predictable CIDR control.
- Enable required APIs as an explicit, first-applied resource group rather than discovering missing-API errors reactively.
- Bind least-privilege IAM roles to per-workload service accounts rather than relying on broad OAuth scopes or project-level roles.

## 10. Common Anti-Patterns / Mistakes

- **Leaving `auto_create_subnetworks` at its default `true`** and fighting the automatically created subnets instead of explicitly opting into manual subnet mode from the start.
- **Assuming GCP's provisioning model mirrors AWS's regional-VPC assumption** — treating `google_compute_network` as region-scoped leads to unnecessary duplicate VPCs where a single global VPC with multiple regional subnets would have worked.
- **Skipping explicit API enablement** and only discovering the dependency when `apply` fails partway through a larger configuration, rather than treating it as a first-class, first-applied step.

## 11. Interview Questions

**🎯 Beginner:** _"In GCP's Terraform provider, what has to happen before you can create a compute instance that has no equivalent step in AWS or Azure?"_
**Model answer:** The relevant Google Cloud API (`compute.googleapis.com`) must be explicitly enabled on the project via a `google_project_service` resource. AWS and Azure don't require an equivalent "turn on this API" provisioning step — their APIs are always available to an authenticated caller with sufficient permissions.
_What the interviewer is probing for:_ Awareness of GCP's distinctive API-enablement model as a real provisioning dependency, not an obscure edge case.

**🎯 Intermediate:** _"Is a GCP VPC regional or global, and how does that change subnet design compared to AWS?"_
**Model answer:** A `google_compute_network` is global — a single VPC can have subnets in every GCP region without peering. Subnets (`google_compute_subnetwork`) are the region-scoped construct. This is the reverse of AWS, where the VPC itself is regional and reaching another region requires a separate VPC plus peering or a transit gateway. In GCP, the design question shifts from "how many VPCs do I need across regions" to "how do I segment firewall rules and IAM within one VPC that already spans every region I need."
_What the interviewer is probing for:_ Concrete understanding of the global-vs-regional distinction and its downstream effect on network design decisions, not just rote memorization of the fact.

**🎯 Senior:** _"An `apply` that creates a `google_project_service` and a `google_compute_instance` depending on it in the same run occasionally fails with the API-not-enabled error, even though the service resource shows as successfully created. Why, and how do you fix it reliably?"_
**Model answer:** `google_project_service` completing in Terraform's state means the API-enablement API call succeeded, not that the enablement has fully propagated through Google's internal systems — this is an eventual-consistency gap similar in kind (though a different mechanism) to AWS IAM propagation delay covered in [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md). An explicit `depends_on` ensures correct ordering but doesn't wait for propagation, only for the API call to return. The reliable fix is either a `time_sleep` resource ([§38](../Part5/Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md)) chained via `depends_on` between the service and the instance, or — better for CI reliability — splitting API enablement into a separate `apply` run (a bootstrap stage) that completes and is confirmed stable before the resource-provisioning stage runs.
_What the interviewer is probing for:_ Recognition that `depends_on` guarantees ordering, not propagation completion, and a concrete, production-viable mitigation rather than "just add depends_on."

**🎯 Architect:** _"You're designing a multi-region GCP footprint for a new product. Given that GCP VPCs are global, how does your network design differ from what you'd build in AWS, and what tradeoffs does that introduce?"_
**Model answer:** In AWS, multi-region typically means one VPC per region plus explicit peering or a transit gateway to connect them, since regional isolation is the default. In GCP, a single global VPC with regional subnets is usually the better starting point — routing between regions works automatically without peering, and centralized firewall policy applies uniformly across the whole footprint from day one. The tradeoff is blast radius: a single global VPC concentrates network-level configuration mistakes (an overly permissive firewall rule, a misconfigured route) across every region simultaneously, where AWS's per-region VPC isolation would have contained the same mistake to one region. The mitigating pattern is to lean harder on firewall rule scoping (target tags/service accounts) and Shared VPC with per-team service projects for organizational boundaries, since the network boundary itself is not doing that isolation work by default the way separate regional VPCs would in AWS.
_What the interviewer is probing for:_ Ability to reason about how a structural platform difference (global vs. regional VPC) changes both the design and the risk profile, not just reciting the mechanical difference.

## 12. Common Misconceptions

1. **"A GCP VPC is regional, like an AWS VPC or Azure VNet."** It's global by default; subnets are the region-scoped construct, the reverse of AWS/Azure.
2. **"If a resource type exists in the provider schema, it's ready to provision."** Many GCP resources also require their backing API to be enabled first via `google_project_service`, a step with no AWS/Azure equivalent.
3. **"`depends_on` on a `google_project_service` guarantees the API is usable immediately after."** It guarantees ordering of the Terraform operation, not that GCP's backend has finished propagating the enablement.
4. **"GCP instance scopes are the primary access-control mechanism, like an AWS instance profile."** IAM role bindings on the service account are the primary mechanism; scopes are a coarser, largely legacy layer.

## 13. 🔑 Key Takeaways

- GCP's project is the combined billing/IAM/API-enablement boundary, and most resources require their backing API explicitly enabled via `google_project_service` before creation.
- `google_compute_network` is global; `google_compute_subnetwork` is the region-scoped construct — the reverse of AWS/Azure's regional-VPC model.
- `auto_create_subnetworks = false` on custom VPCs is the standard production setting for predictable CIDR control.
- Service accounts plus IAM role bindings are GCP's primary compute-identity access-control mechanism, analogous to AWS instance profiles and Azure managed identities.
- API-enablement propagation delay is a real, documented eventual-consistency gap that `depends_on` alone does not fully solve.

## 14. Related Concepts & What's Next

[§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) and [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md) covered the AWS and Azure equivalents this section contrasted against throughout — together the three form the multi-cloud provisioning foundation this Part builds on. [§78](./Section-78-Part11-Cross-Provider-Patterns-Shared-Modules-Across-Clouds.md) now synthesizes all three into genuinely provider-agnostic module patterns, the natural next step after seeing each provider's idiosyncrasies in isolation. [§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) extends the networking patterns from 5.2 into peering and cross-network scenarios across all three providers. [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) covers IAM-as-code across providers, expanding on the service-account pattern from 5.3.

**Next Section:** [§78](./Section-78-Part11-Cross-Provider-Patterns-Shared-Modules-Across-Clouds.md) — `Section-78-Part11-Cross-Provider-Patterns-Shared-Modules-Across-Clouds.md`
