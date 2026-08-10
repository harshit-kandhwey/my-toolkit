# Section 76 (Part 11): Azure Provider (azurerm) Deep Dive: Resource Groups, VNets, VMs

## 1. Definition

**Plain language:** The `azurerm` provider is the plugin that lets Terraform create and manage Azure resources. Its defining trait compared to AWS is that almost everything in Azure must belong to a **resource group** — a logical container that groups resources for lifecycle, billing, and access-control purposes — so provisioning in Azure always starts one level above where AWS provisioning starts.

**Precise definition:** The **`azurerm` provider** (published by Microsoft/HashiCorp jointly, sourced as `hashicorp/azurerm`) maps HCL resource blocks to Azure Resource Manager (ARM) API calls. Nearly every `azurerm_*` resource requires a `resource_group_name` and `location` argument, reflecting Azure's mandatory resource-group containment model — a structural difference from AWS, where resources exist directly within an account/region with no equivalent mandatory grouping construct. The foundational resources — `azurerm_resource_group`, `azurerm_virtual_network`, `azurerm_subnet`, `azurerm_linux_virtual_machine`/`azurerm_windows_virtual_machine` — form the Azure equivalent of the AWS VPC/EC2 pairing covered in [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md).

> 💡 **Tip:** In `azurerm`, deleting a resource group deletes _everything inside it_ — Azure enforces this at the platform level, independent of Terraform. This makes the resource group both a convenience (one `terraform destroy` on a group-scoped root module tears down everything cleanly) and a hazard (a mistaken `resource_group_name` reference in an unrelated module can point at, and destroy, the wrong group's contents).

## 2. Why This Matters

- **Azure is one of the two other major hyperscalers** Terraform practitioners are expected to know, and its resource-group model is different enough from AWS's flat account model that naive AWS-to-Azure translation of Terraform code produces broken or insecure configurations.
- **Resource groups are a first-class Terraform citizen**, not an optional organizational nicety — nearly every other `azurerm_*` resource has a hard dependency on one, making it the mandatory root of the dependency graph for any Azure module.
- **Naming and location propagation matters more in Azure than AWS** — Azure resources inherit `location` from their resource group by convention (though it must still be passed explicitly in most resource blocks), and getting this wrong produces resources scattered across regions unintentionally.

## 3. Prerequisites and Dependencies

Builds directly on the AWS provider patterns from [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) and the provider authentication concepts from [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) (Azure specifically uses Service Principal or Managed Identity authentication, distinct from AWS's IAM-role-based patterns). General Azure service familiarity (resource groups, VNets, VMs conceptually) is assumed — see `../../../6. Cloud/2. Azure/` for that background; this section covers only the Terraform provisioning layer.

## 4. Architecture / Conceptual Diagram

```text
                    azurerm_resource_group.main
                    (name="app-rg", location="eastus")
                                 │
                ┌────────────────┴─────────────────┐
                │                                  │
      azurerm_virtual_network.vnet         azurerm_storage_account.diag
      (10.0.0.0/16)                        (VM boot diagnostics)
                │
      ┌─────────┴──────────┐
      │                    │
azurerm_subnet.web   azurerm_subnet.data
(10.0.1.0/24)         (10.0.2.0/24)
      │                    │
azurerm_network_       azurerm_network_
interface.web_nic      interface.data_nic
      │                    │
azurerm_linux_         azurerm_linux_
virtual_machine.web    virtual_machine.data
      │
azurerm_network_security_group.web_nsg
(attached via azurerm_subnet_network_security_group_association
 or azurerm_network_interface_security_group_association)

      All resources above reference resource_group_name and
      location either directly from azurerm_resource_group.main
      or inherited by convention — everything is scoped to
      the group's lifecycle.
```

- The resource group sits at the top of every dependency chain — even resources with no logical relationship to each other (a VM and an unrelated storage account) both reference the same `resource_group_name`, meaning Terraform's graph fans out from a single node.
- Network security groups (NSGs) in Azure attach at the subnet or NIC level via separate association resources, not inline on the VM resource — a structural difference from AWS security groups, which attach directly to the instance.

## 5. Hands-On

### 5.1 Resource Group and Virtual Network Provisioning

**Purpose:** Establish the mandatory container and network boundary that all subsequent resources reference.

**Syntax:**

```hcl
resource "azurerm_resource_group" "main" {
  name     = "app-rg"
  location = "eastus"
}

resource "azurerm_virtual_network" "vnet" {
  name                = "app-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_subnet" "web" {
  name                 = "web-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # azurerm_resource_group.main will be created
  # azurerm_virtual_network.vnet will be created
  # azurerm_subnet.web will be created

Plan: 3 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
```

**Production usage example:** Referencing `azurerm_resource_group.main.location` (instead of hardcoding `"eastus"` again on every resource) is the standard pattern — it guarantees every resource in the module lands in the same region as its group and means a single variable change relocates the whole module.

**Common errors:** Deleting a resource group outside Terraform (via the Azure Portal, "just to clean up") silently invalidates every resource Terraform's state thinks still exists inside it — the next `plan` reports all of them as needing to be created again, which looks like state corruption but is actually accurate: they really are gone.

### 5.2 Virtual Machine Provisioning

**Purpose:** Launch a Linux VM attached to the subnet via a network interface, following Azure's decoupled NIC-then-VM provisioning model.

**Syntax:**

```hcl
resource "azurerm_network_interface" "web_nic" {
  name                = "web-nic"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.web.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "web" {
  name                = "web-vm"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = "Standard_B1s"
  admin_username      = "azureuser"

  network_interface_ids = [azurerm_network_interface.web_nic.id]

  admin_ssh_key {
    username   = "azureuser"
    public_key = file("~/.ssh/id_rsa.pub")
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts"
    version   = "latest"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # azurerm_network_interface.web_nic will be created
  # azurerm_linux_virtual_machine.web will be created

Plan: 2 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.

$ terraform apply    # after changing size to Standard_B2s
  ~ size = "Standard_B1s" -> "Standard_B2s"
Plan: 0 to add, 1 to change, 0 to destroy.
```

**Production usage example:** Unlike `aws_instance` (which embeds the network interface configuration inline), Azure requires provisioning `azurerm_network_interface` as a standalone resource first — production modules typically wrap this NIC-then-VM pairing inside a single child module so callers provision "a VM" as one logical unit rather than remembering the two-resource sequence every time.

**Common errors:** Forgetting `admin_ssh_key` (or `admin_password` for Windows VMs with `disable_password_authentication = false`) causes an `apply`-time validation error, not a silent failure — Azure requires an explicit authentication method, unlike AWS's `aws_instance` which can launch keyless (though inaccessible) without complaint.

### 5.3 Network Security Group Provisioning

**Purpose:** Restrict inbound/outbound traffic at the subnet or NIC level, Azure's equivalent of an AWS security group but attached via a separate association resource.

**Syntax:**

```hcl
resource "azurerm_network_security_group" "web_nsg" {
  name                = "web-nsg"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "AllowHTTPS"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "web" {
  subnet_id                 = azurerm_subnet.web.id
  network_security_group_id = azurerm_network_security_group.web_nsg.id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # azurerm_network_security_group.web_nsg will be created
  # azurerm_subnet_network_security_group_association.web will be created

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Associating the NSG at the subnet level (rather than per-NIC) is the standard production pattern when every VM in that subnet should share the same rule set — per-NIC association is reserved for cases where individual VMs within the same subnet need genuinely different rules.

**Common errors:** Defining `security_rule` blocks inline on the NSG _and_ separately via standalone `azurerm_network_security_rule` resources referencing the same NSG causes a documented conflict — the provider explicitly warns against mixing the two styles because they fight over ownership of the rule set.

## 6. Production Usage Notes

- Azure's mandatory resource-group scoping makes it natural (and standard practice) to structure Terraform root modules per resource group per environment — `rg-app-prod`, `rg-app-staging` — rather than per-service, since so much else is scoped to the group.
- `azurerm` provider authentication in CI/CD typically uses a Service Principal with a client ID/secret or, increasingly, Azure Workload Identity Federation (OIDC) for GitHub Actions/Azure DevOps — the least-privilege patterns from [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) apply directly here.
- Azure enforces `Standard_LRS`/`Premium_LRS` disk-tier and VM-size validity at apply time per region — a size valid in `eastus` may not exist in `westeurope`, producing a plan-time-invisible, apply-time-only failure that AWS's simpler, more uniform instance-type availability rarely produces.

## 7. Security Considerations

- Disabling password authentication (`disable_password_authentication = true`, the default for `azurerm_linux_virtual_machine`) and requiring `admin_ssh_key` is materially safer than password-based VM access and should not be overridden without a specific reason.
- NSGs default-deny inbound traffic from the internet except what's explicitly allowed — but the default _outbound_ rules are more permissive than most teams expect; audit `security_rule` outbound blocks explicitly rather than assuming they mirror inbound restrictiveness.
- Storage accounts (`azurerm_storage_account`) default to allowing public network access in older provider versions — explicitly setting `public_network_access_enabled = false` and using private endpoints is standard for anything holding sensitive data.

## 8. Common Troubleshooting Scenarios

| Symptom                                                 | Likely Cause                                                                                  | Resolution Path                                                                           |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `plan` wants to recreate everything in a resource group | The resource group was deleted or renamed outside Terraform                                   | Reconcile with `terraform state rm`/`import`, or restore the group before reapplying      |
| `apply` fails with VM size not available in region      | Chosen `size` (e.g. `Standard_B2s`) isn't offered in the target `location`                    | Check regional SKU availability via `az vm list-skus` before hardcoding a size            |
| VM created but SSH connection refused                   | Missing or mismatched `admin_ssh_key`, or NSG not allowing port 22                            | Verify the public key matches the private key in use, and confirm an NSG rule permits SSH |
| Conflicting NSG rule errors on `apply`                  | Inline `security_rule` blocks mixed with standalone `azurerm_network_security_rule` resources | Standardize on one style per NSG, not both                                                |

## 9. Best Practices

- Reference `azurerm_resource_group.main.location` and `.name` from every dependent resource instead of repeating literals, so the whole module relocates with a single variable change.
- Wrap the NIC-then-VM two-step pattern inside a reusable child module so callers provision "a VM" as one unit.
- Apply NSGs at the subnet level by default; reserve per-NIC association for genuine per-instance exceptions.

## 10. Common Anti-Patterns / Mistakes

- **Assuming Azure's provisioning model mirrors AWS's 1:1.** Copying an AWS module structure and swapping resource names without accounting for the mandatory resource-group layer and the decoupled NIC/VM resources produces broken references.
- **Hardcoding `location` independently on every resource** instead of deriving it from the resource group, causing silent regional drift when the group's location changes but dependent resources don't follow.
- **Mixing inline and standalone NSG rule definitions**, which the provider explicitly documents as unsupported and a source of confusing plan diffs.

## 11. Interview Questions

**🎯 Beginner:** _"What Azure concept does every `azurerm_\*` resource almost always depend on, and what does deleting it do?"_
**Model answer:** The resource group (`azurerm*resource_group`) — nearly every other Azure resource requires a `resource_group_name`. Deleting a resource group deletes everything inside it, enforced by Azure itself, not just by Terraform's dependency graph.
\_What the interviewer is probing for:* Basic grasp of Azure's mandatory containment model as the core structural difference from AWS.

**🎯 Intermediate:** _"How does provisioning a VM's network attachment differ between AWS and Azure in Terraform?"_
**Model answer:** In AWS, `aws_instance` takes a `subnet_id` and `vpc_security_group_ids` directly — the network interface is implicit and managed by the instance resource itself. In Azure, the network interface is a standalone resource (`azurerm_network_interface`) that must be created first, with its own `ip_configuration` block referencing the subnet; the VM resource (`azurerm_linux_virtual_machine`) then references the NIC's ID via `network_interface_ids`. This is a two-step dependency chain in Azure versus effectively one step in AWS.
_What the interviewer is probing for:_ Concrete, resource-level understanding of the provider difference, not just "they're different."

**🎯 Senior:** _"A colleague deleted an Azure resource group manually in the Portal to 'clean things up' after a demo. What happens the next time someone runs `terraform plan` against that root module, and what's the safe recovery path?"_
**Model answer:** `plan` will show every resource that was in state as needing to be created — not "updated" or "recreated," but freshly created, since Terraform's refresh step confirms none of them exist anymore. If the intent truly was to delete the environment, the safe path is `terraform state rm` (or simply re-running `apply` to legitimately rebuild it) rather than treating this as corruption. If the deletion was accidental and some resources held state that can't be trivially recreated (a database with data, for instance), the real fix is prevention — `prevent_destroy` lifecycle rules ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) don't help here since the deletion happened outside Terraform entirely; the actual mitigation is Azure RBAC restricting who can delete resource groups directly in the Portal, forcing all destructive changes through the Terraform pipeline.
_What the interviewer is probing for:_ Understanding that Terraform-side safeguards (`prevent_destroy`) cannot protect against out-of-band changes, and that the real fix is access control at the cloud platform layer, not the Terraform layer.

**🎯 Architect:** _"You're designing the root-module boundary strategy for an Azure-based Terraform codebase serving multiple teams. Given Azure's resource-group containment model, how would you draw state boundaries, and what does this cost you compared to AWS?"_
**Model answer:** Because so much of Azure's access control, cost allocation, and blast radius naturally aligns with resource groups, the most defensible boundary is one root module (and state file) per resource group per environment, rather than per logical application layer as might be more natural in AWS's flatter model. This keeps the Terraform state boundary congruent with the platform's own security and billing boundary, so a compromised or misconfigured pipeline for one team's resource group cannot touch another's. The cost compared to AWS is more root modules and more cross-module data-source lookups (or remote state reads, [§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)) for shared infrastructure like a hub VNet that multiple resource groups need to peer against — AWS's flatter model makes sharing a VPC ID across modules simpler since there's no equivalent mandatory grouping construct forcing state fragmentation in the first place.
_What the interviewer is probing for:_ Ability to reason about how a cloud platform's own structural model (resource groups) should influence Terraform's state-boundary design, not just applying a generic pattern uncritically.

## 12. Common Misconceptions

1. **"Azure resource groups are just tags, like AWS resource tags."** They're a hard containment boundary enforced by the platform — deleting a group deletes its contents, which tags never do.
2. **"A VM resource in `azurerm` works the same as `aws_instance`."** Azure decouples the network interface into its own resource that must exist before the VM references it; AWS embeds this inline.
3. **"NSGs attach directly to a VM like an AWS security group attaches to an instance."** They attach to a subnet or a NIC via a separate association resource, not to the VM resource itself.
4. **"A VM size available in one Azure region is available everywhere."** SKU availability is region-specific and can fail at apply time even when the plan looked fine.

## 13. 🔑 Key Takeaways

- Azure's resource-group model is a mandatory containment layer that nearly every `azurerm_*` resource depends on — the core structural difference from AWS's flatter account/region model.
- VM provisioning in Azure is a two-step chain (NIC, then VM) rather than AWS's single-resource `aws_instance`.
- NSGs attach via separate association resources at the subnet or NIC level, not inline on the VM.
- Deleting a resource group outside Terraform invalidates everything Terraform's state thinks exists inside it — state boundaries should be designed with this platform behavior in mind.
- Region/SKU availability mismatches surface at apply time, not plan time, more often in Azure than AWS.

## 14. Related Concepts & What's Next

[§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) covered the equivalent AWS patterns this section contrasted against throughout. [§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) extends the networking patterns here (VNets, subnets, NSGs) into cross-network peering scenarios. [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) covers IAM-as-code across providers, including Azure's role-based access control (RBAC) and Service Principal model as the Azure analog to AWS IAM. [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) now turns to the GCP provider's project-and-VPC model, the third leg of the multi-cloud provisioning foundation this Part builds.

**Next Section:** [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) — `Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md`
