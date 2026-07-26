# Section 11 — Azure Virtual Machines: Architecture, Sizing, Images

## 1. Definition

**Plain language:** An Azure Virtual Machine (VM) is a software-based emulation of a physical computer, running on Microsoft's shared hardware, that you can create in minutes, choose the size and OS of, and fully control from the OS level upward — the core IaaS compute building block introduced conceptually in Section 2.4.

**Precise definition:** An Azure VM is a virtualized compute instance running atop the Azure Hypervisor on physical host hardware within an Azure data center, provisioned from a disk image, allocated a defined quantity of virtual CPU, memory, and network/storage bandwidth according to its selected VM size (SKU), and billed based on that size, running duration, and any attached resources (disks, public IPs).

## 2. Why It Exists / Problem It Solves

Some workloads require full operating-system-level control: custom kernel parameters, specific unsupported legacy software, direct hardware-adjacent configuration, or simply an exact lift-and-shift replica of an existing on-premises server with minimal re-engineering. Azure VMs solve this by providing IaaS-level compute (Section 2.4) — Microsoft manages only the physical host and hypervisor, while the customer retains full control of everything from the guest OS upward, at the cost of taking on OS patching, security hardening, and availability configuration as their own responsibility.

## 3. Internal Working — Virtualization Architecture

**How virtualization works (foundational concept):** A **hypervisor** is a thin layer of software running directly on physical server hardware that creates and manages multiple isolated **virtual machines**, each believing it has exclusive access to its own CPU, memory, and devices, while the hypervisor actually multiplexes the real physical hardware among all VMs running on that host. Azure's compute fleet runs on the **Azure Hypervisor**, a Microsoft-built, Hyper-V-based hypervisor purpose-built for Azure's hyperscale, multi-tenant environment.

**Multi-tenancy and isolation:** Multiple customers' VMs typically run on the same physical host hardware simultaneously (multi-tenancy) — this is fundamental to cloud economics, since it allows Microsoft to sell fractional slices of physical hardware capacity rather than requiring dedicated hardware per customer. The hypervisor is responsible for strict isolation between tenants' VMs at the memory, CPU, and I/O level, so that one customer's VM can never read another customer's VM's memory or data, even though they share the same underlying physical hardware — this isolation guarantee is a foundational element of public cloud security, distinct from network-level isolation (covered in Part 5).

⚠️ For workloads with strict regulatory or compliance requirements against any hardware multi-tenancy, Azure offers **Dedicated Hosts** — physical servers reserved exclusively for one customer's VMs, eliminating co-tenancy at the hardware level entirely, at a corresponding cost premium; verify current Dedicated Host availability and pricing against official documentation when this requirement arises.

### 3.1 Architecture Diagram

```
Physical Host Server (in an Azure data center)
 └── Azure Hypervisor (host OS / virtualization layer)
      ├── Customer A's VM  (isolated: own vCPU, memory, virtual disk)
      ├── Customer B's VM  (isolated: own vCPU, memory, virtual disk)
      └── Customer A's VM #2 (a second VM, still isolated from Customer B)

Each VM:
 ├── Guest OS (Windows or Linux — fully customer-managed)
 ├── Virtual CPU (vCPU) — allocated per VM size
 ├── Virtual Memory (RAM) — allocated per VM size
 ├── OS Disk (managed disk, Section 18) — boot volume
 ├── (optional) Data Disk(s) — additional attached storage
 └── Virtual Network Interface — connects to a Virtual Network (Section 21)
```

## 4. VM Sizing (SKUs)

**Definition:** A **VM size** (or SKU) is a predefined bundle of virtual CPU count, memory, temporary storage, and maximum network/disk throughput that a VM is provisioned with. Azure organizes VM sizes into **series**, each optimized for a different workload profile.

**Common VM series categories:**

| Series Example                       | Optimized For                | Typical Use Case                                       |
| ------------------------------------ | ---------------------------- | ------------------------------------------------------ |
| General purpose (e.g., "D-series")   | Balanced CPU-to-memory ratio | Most standard application workloads, web servers       |
| Compute optimized (e.g., "F-series") | High CPU-to-memory ratio     | Batch processing, application servers, gaming servers  |
| Memory optimized (e.g., "E-series")  | High memory-to-CPU ratio     | In-memory databases, large caches, analytics workloads |
| Storage optimized (e.g., "L-series") | High disk throughput/IOPS    | Big data, SQL/NoSQL databases with heavy I/O needs     |
| GPU-enabled (e.g., "N-series")       | Attached GPU hardware        | Machine learning training, rendering, visualization    |

⚠️ Specific series names, exact vCPU/memory ratios, and available sizes within each series change over time as Azure introduces new hardware generations and retires older ones — always verify current series names and specifications against official documentation (or `az vm list-sizes`) before designing around a specific SKU, since this is one of the most frequently updated areas of Azure's catalog.

**How to choose a size — decision factors:**

- **CPU/memory ratio needed** by the actual application workload (profile the application, don't guess).
- **Network and disk throughput requirements** — larger VM sizes within a series generally unlock higher maximum network and disk bandwidth, not just more CPU/memory, an often-overlooked sizing dimension.
- **Cost** — larger sizes cost proportionally more; right-sizing (matching the smallest size that meets actual sustained load, augmented with autoscaling for peaks rather than statically over-provisioning) is a core cost-optimization practice covered further in Part 12.
- **Availability in the target region** — not every size is available in every region; verify with `az vm list-skus --location <region>` before committing to a design.

💡 **Tip:** A very common real-world mistake is over-provisioning "just in case" rather than right-sizing based on actual measured utilization and using autoscaling (Section 12, VM Scale Sets) to handle genuine peak demand — right-sizing plus autoscaling is almost always more cost-effective than a permanently oversized static VM.

## 5. VM Images

**Definition:** An **image** is the template used to create a VM's OS disk — containing a pre-configured operating system (and optionally, pre-installed software) that Azure copies to create the new VM's initial disk state.

**Image sources:**

- **Azure Marketplace images** — Microsoft- and partner-published images for common operating systems (Ubuntu, Windows Server, Red Hat, etc.) and pre-configured software stacks (e.g., a pre-built WordPress or SQL Server image), the most common starting point.
- **Custom images** — captured from a VM you've already configured (installed software, applied settings) and generalized, allowing you to create multiple new VMs from that exact known-good starting state rather than repeating manual configuration each time.
- **Azure Compute Gallery** (formerly Shared Image Gallery) — a managed service for versioning, replicating (across regions), and sharing custom images across an organization at scale, the enterprise-standard mechanism for managing golden/standardized images rather than ad hoc custom image files.

⚠️ **Generalized vs. specialized images** is an important distinction: a **generalized** image has had machine-specific information (like the computer name and security identifiers) removed via a tool like `sysprep` (Windows) or `waagent -deprovision` (Linux), making it safe to use as a template for multiple new VMs; a **specialized** image retains that machine-specific information and is intended to preserve a single, specific VM's exact state (e.g., for disaster recovery), not to be used as a multi-VM template — using a specialized image incorrectly as a multi-instance template can cause identity conflicts between the resulting VMs.

## 6. Configuration & Hands-On Example

**Creating a VM with a specific size and querying available sizes first:**

```bash
# Step 1: Check available VM sizes in the target region
az vm list-sizes --location eastus --output table

# Step 2: Create the VM with an explicitly chosen size
az vm create \
  --resource-group rg-myapp-prod \
  --name vm-web-01 \
  --image Ubuntu2204 \
  --size Standard_D2s_v5 \
  --admin-username azureuser \
  --generate-ssh-keys
```

- **Purpose:** Explicitly selects a general-purpose VM size (`Standard_D2s_v5`, illustrative — verify current series naming) rather than accepting a default, following the right-sizing principle from Section 11.4.
- **Important arguments explained individually:**
  - `--size` — the VM SKU; omitting this parameter lets Azure choose a default size, which is rarely the ideal choice for a real workload and should generally be explicitly specified after actual sizing analysis.
- **Common error:** `SkuNotAvailable` — the requested size isn't available in the target region or for the target subscription's quota; resolved by choosing a different size, a different region, or requesting a quota increase.
- **Production usage:** In production, this exact creation logic is virtually always expressed as Infrastructure as Code (ARM/Bicep/Terraform, Part 9) rather than a one-off CLI command, so the chosen size and image are version-controlled and consistently reproducible.

**Capturing a custom image from a configured VM (conceptual sequence):**

```bash
# Step 1: Deallocate and generalize the VM (Linux example)
az vm deallocate --resource-group rg-myapp-prod --name vm-template-01
az vm generalize --resource-group rg-myapp-prod --name vm-template-01

# Step 2: Capture the image
az image create --resource-group rg-myapp-prod --name img-webapp-golden --source vm-template-01
```

- **Purpose:** Converts a manually-configured, known-good VM into a reusable generalized image, following the golden-image pattern used to standardize new VM deployments.
- ⚠️ The exact generalization command differs meaningfully by OS (Linux typically uses `waagent -deprovision+user` run inside the VM before the Azure-level `az vm generalize` step; Windows uses `sysprep` inside the VM first) — always verify the current, correct OS-specific generalization procedure in official documentation before capturing a production golden image, since doing this incorrectly can produce a broken or insecure template.

## 7. Production & Enterprise Usage

Enterprises rarely create VMs manually and repeatedly from marketplace images for ongoing operations — instead, they build and maintain a small set of standardized, hardened **golden images** (via Azure Compute Gallery) that bake in required security agents, monitoring agents, and baseline configuration, then deploy new VMs (often via VM Scale Sets, Section 12, rather than individual VMs) from those standardized images through Infrastructure as Code pipelines. VM sizing decisions at enterprise scale are typically informed by actual usage telemetry (via Azure Monitor, Part 10) rather than guesswork, with periodic right-sizing reviews as part of cost governance (Part 12).

## 8. Security Considerations

- The guest OS is entirely the customer's responsibility to patch and harden under the IaaS model (Section 2.4) — unpatched VM operating systems are a common real-world breach vector, making automated patch management (or automated VM replacement from updated golden images) an operational necessity, not optional.
- Golden images should have security baselines (disabled unnecessary services, applied hardening benchmarks, pre-installed required security/monitoring agents) baked in before being used as a deployment template, rather than relying on post-deployment configuration to achieve consistent hardening.
- Direct public internet exposure of a VM's management ports (like SSH port 22 or RDP port 3389) is a common and serious misconfiguration; this is addressed via Network Security Groups and just-in-time VM access, covered in Part 5 and Part 11 respectively.

## 9. Performance Considerations

VM performance is bounded not just by vCPU count but by the size's associated network and disk throughput limits — a workload that's disk-I/O-bound will not improve by simply choosing a size with more vCPUs if that size doesn't also increase disk throughput limits; matching the size's full resource profile (CPU, memory, disk throughput, network bandwidth) to the actual workload bottleneck is essential and is a frequent source of "why isn't scaling up helping" troubleshooting scenarios.

## 10. Monitoring

Basic VM health and performance metrics (CPU utilization, disk I/O, network throughput) are available by default through Azure Monitor (Part 10) at the platform level; deeper, in-guest metrics and log collection require installing the Azure Monitor Agent inside the VM — this distinction between platform-level and in-guest monitoring is elaborated fully in Part 10.

## 11. Troubleshooting

| Symptom                                                                      | Likely Cause                                                               | Fix                                                                                                                  |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `SkuNotAvailable` error at creation                                          | Chosen size not available in target region, or subscription quota exceeded | Check `az vm list-sizes --location <region>`; request a quota increase if needed                                     |
| VM created from a "specialized" image conflicts with an identical sibling VM | Machine-specific identifiers weren't removed before capture                | Recapture the image after properly generalizing (sysprep/waagent deprovision) the source VM                          |
| VM performance doesn't improve after resizing to more vCPUs                  | The actual bottleneck is disk or network throughput, not CPU               | Re-profile the workload's actual resource bottleneck; choose a size that increases the specific constrained resource |

## 12. Interview Questions — Section 11

### 🎯 Beginner

**Q: What is the difference between a VM size (SKU) and a VM image?**

_Model answer:_ A VM size defines the hardware resources allocated to the VM — vCPU count, memory, and associated network/disk throughput limits. A VM image is the template used for the VM's OS disk — the operating system and any pre-installed software the VM starts with. They're independent choices: the same image can be deployed at many different sizes, and the same size can run many different images.

_What the interviewer is probing:_ basic conceptual separation between "how powerful is the machine" and "what's installed on it" — foundational VM vocabulary.

### 🎯 Senior

**Q: How would you design a golden image strategy for an enterprise deploying hundreds of VMs across multiple teams?**

_Model answer:_ I'd establish a small set of standardized base images (e.g., one hardened Linux baseline, one hardened Windows Server baseline) built and maintained centrally, with required security agents, monitoring agents, and compliance hardening baked in, versioned and distributed through Azure Compute Gallery so teams across regions and subscriptions can consume consistent, current versions rather than building their own ad hoc images. I'd establish a regular rebuild cadence (rather than patching golden images in place indefinitely) to keep base OS patch levels current, and would have teams extend these base images minimally for their specific application needs rather than starting from scratch, keeping the baseline hardening consistent across the fleet. Deployment would happen exclusively through Infrastructure as Code referencing specific image versions, never through manual VM creation from arbitrary marketplace images, ensuring every production VM traces back to an approved, hardened, version-tracked source.

_What the interviewer is probing:_ whether the candidate thinks about image management as an ongoing governance and lifecycle practice at organizational scale, not just a one-time technical capture operation — a strong signal of real platform-engineering experience.

## 13. Common Misconceptions

- **"A bigger VM size is always better performance."** False — performance is bounded by whichever resource dimension (CPU, memory, disk throughput, network bandwidth) is the actual bottleneck for the workload; scaling the wrong dimension yields no improvement.
- **"You can use a specialized image the same way as a generalized image to create multiple VMs."** False and risky — specialized images preserve machine-specific identity information and are intended for single-instance recovery scenarios, not multi-VM templating.

## 14. Key Takeaways

- 🔑 Azure VMs run on the Azure Hypervisor, which provides strict isolation between co-tenant VMs sharing the same physical host — a foundational public cloud security guarantee.
- 🔑 VM sizing should be driven by actual workload resource-bottleneck analysis (CPU, memory, disk throughput, network bandwidth), not guesswork or arbitrary over-provisioning.
- 🔑 Generalized images (via sysprep/waagent deprovisioning) are the correct template mechanism for creating multiple VMs; specialized images preserve single-instance identity and are unsuitable as multi-VM templates.
- 🔑 Enterprise environments manage golden images centrally through Azure Compute Gallery with a regular rebuild cadence, rather than relying on ad hoc marketplace image usage per team.

## 15. VM Workload Availability & Disaster Recovery

### 15.1 Availability Sets vs. Availability Zones vs. VM Scale Sets

Azure provides three distinct, sometimes-confused mechanisms for VM-level resilience, each addressing a different scope of failure and suited to a different scenario:

| Mechanism                                         | What It Protects Against                                                | How It Works                                                                                                                                                                                            | Typical Use                                                                                                                   |
| ------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Availability Set**                              | Rack-level failure (power, network switch) within a single data center  | Groups VMs across multiple **Fault Domains** (distinct racks/power/network) and **Update Domains** (groups patched/rebooted at different times during platform maintenance), all within one data center | Regions/scenarios where Availability Zones (Section 3.3.2) aren't available, or for legacy deployments predating zone support |
| **Availability Zone** (applied to standalone VMs) | Data-center/zone-level failure                                          | Manually pinning individual VMs to specific, different zones (e.g., VM1 in Zone 1, VM2 in Zone 2, VM3 in Zone 3)                                                                                        | Manually-managed small fleets of standalone VMs needing zone-level resilience without full VM Scale Set automation            |
| **VM Scale Set** (Section 12)                     | Rack- or zone-level failure, PLUS automatic elastic capacity management | Automatically distributes and scales instances across zones/fault domains, with autoscaling and rolling upgrades built in                                                                               | The standard modern choice for any horizontally-scalable, stateless workload — combines resilience with elasticity            |

⚠️ **A critical, frequently tested distinction:** Availability Sets and Availability Zones are **not combinable** for the same VM — a VM is deployed into either an Availability Set (data-center-local fault/update domains) or a specific Availability Zone, not both simultaneously, since they represent different, mutually exclusive resiliency scopes. VM Scale Sets, by contrast, can be configured to span multiple zones directly (Section 12.3.3), making them the more capable and generally preferred mechanism when the workload is suited to horizontal, elastic scaling. Availability Sets remain relevant primarily for singleton or small, non-elastic VM groups in regions without zone support, or where legacy architecture constraints require them.

💡 **Tip:** For genuinely stateful, non-horizontally-scalable singleton workloads (e.g., a single legacy database VM that can't run as multiple identical replicas), neither Availability Sets nor Availability Zones alone provide _failover_ — they only reduce the _likelihood_ of simultaneous failure. True failover for a stateful singleton workload requires a database/application-level HA mechanism (such as SQL Server Always On Availability Groups on IaaS, or a managed PaaS alternative like Azure SQL Database's built-in HA, Section 29.3.4) layered on top of the chosen placement strategy.

### 15.2 VM Backup

**Definition:** **Azure Backup** provides application-consistent, scheduled backups of VMs (and their attached Managed Disks), stored in a Recovery Services Vault, independent of the VM's own lifecycle — protecting against data loss, corruption, accidental deletion, or ransomware, none of which Availability Sets/Zones/Scale Sets address, since those mechanisms protect against _infrastructure_ failure, not data-level _corruption or deletion_.

**Why this is a distinct concern from HA:** High availability (Availability Sets/Zones/VMSS) keeps a workload _running_ despite infrastructure failure; backup protects the _data itself_ from logical failures — an accidentally deleted file, a ransomware encryption event, or a bad application deployment corrupting data are all scenarios where the VM infrastructure remains perfectly healthy, but the data itself needs to be recovered from a point in time before the corruption occurred. HA and backup are complementary, not substitutes for each other — a well-architected VM workload needs both.

**Key backup configuration concepts:**

- **Backup Policy** — defines backup frequency (e.g., daily) and retention duration (how long each recovery point is kept, e.g., 30 days daily, 12 months monthly, 7 years yearly).
- **Application-consistent snapshots** — Azure Backup coordinates with the VM's guest OS (via the VM agent) to quiesce the file system and, where supported, application-level state (like a database's transaction log) before taking the snapshot, ensuring the recovery point is usable without corruption, rather than a purely crash-consistent snapshot that might capture data mid-write.
- **Recovery Services Vault** — the storage container holding backup data, itself benefiting from its own redundancy configuration (LRS/GRS, conceptually similar to Section 20's Storage Account redundancy options).

### 15.3 Disaster Recovery Options for VMs

**Azure Site Recovery (ASR)** (introduced by name here, covered in full in Section 62, Part 12) provides VM-level disaster recovery by continuously replicating a VM's disk changes to a secondary region, allowing the VM to be failed over and brought online in that secondary region if the primary region becomes unavailable — a fundamentally different capability from backup (which restores data to a point in time, generally with some recovery _time_, i.e. it isn't designed for rapid regional failover) and from Availability Zones (which protect within a region, not across regions).

**Summary of the three-layer VM resilience model:**

1. **Availability Sets/Zones/VMSS** — keep the workload running despite a rack, update-domain, or zone-level infrastructure failure _within_ a region.
2. **Backup (Azure Backup)** — recover data to a prior point in time after logical/data-level loss or corruption, regardless of infrastructure health.
3. **Disaster Recovery (Azure Site Recovery)** — recover the entire workload in a _different region_ if the primary region itself becomes unavailable.

These three layers address genuinely different failure modes and are not interchangeable — a production VM workload's resilience design should deliberately consider all three, rather than assuming one (e.g., "we use Availability Zones, so we're covered") addresses the concerns the others are specifically designed for.

🎯 **Interview Tip:** "We have Availability Zones configured — are we protected against data corruption or a full regional outage?" is a common trap question. The correct answer is no on both counts: Availability Zones protect against a zone-level infrastructure failure only; data corruption requires Backup, and a full regional outage requires Site Recovery (or an equivalent DR strategy). Being able to clearly separate these three concerns is one of the most reliable signals of genuine, practical Azure resilience design experience.

### 15.4 Interview Questions — Section 11.15

**🎯 Intermediate**
**Q: Can a single VM be placed in both an Availability Set and a specific Availability Zone simultaneously?**

_Model answer:_ No — Availability Sets and Availability Zones are mutually exclusive placement mechanisms for a given VM. An Availability Set groups VMs across fault/update domains within a single data center, while an Availability Zone pins a VM to one of several physically separate data centers within a region. A VM is deployed using one mechanism or the other, not both, since they represent different, non-combinable resiliency scopes.

_What the interviewer is probing:_ a specific, commonly tested factual distinction that separates genuine hands-on familiarity from surface-level knowledge of "Azure has availability features."

**🎯 Senior**
**Q: A stakeholder says "our production VM workload uses Availability Zones, so we're fully protected." How would you respond?**

_Model answer:_ I'd clarify that Availability Zones protect specifically against a data-center/zone-level infrastructure failure within the current region — they don't protect against data corruption, accidental deletion, or ransomware (which requires Azure Backup with an appropriate retention policy), and they don't protect against the loss of the entire region itself (which requires a disaster recovery solution like Azure Site Recovery replicating to a secondary region). I'd recommend treating these as three distinct, complementary layers of a complete resilience strategy — zone-level HA, backup for data-level recovery, and cross-region DR for regional-level recovery — rather than assuming zone redundancy alone constitutes complete protection, and would work with the stakeholder to assess which of the other two layers are currently missing and whether the business's actual risk tolerance and recovery objectives justify adding them.

_What the interviewer is probing:_ whether the candidate can correctly identify and communicate the gap between infrastructure-level HA and the separate concerns of data protection and regional DR — a genuinely common real-world miscommunication this question is designed to surface.

### 15.5 Key Takeaways — Section 11.15

- 🔑 Availability Sets (data-center-local fault/update domains) and Availability Zones (data-center-level separation) are mutually exclusive per VM; VM Scale Sets can span zones directly and are the generally preferred modern mechanism for horizontally-scalable workloads.
- 🔑 Azure Backup protects against data-level loss/corruption (a concern HA mechanisms do not address); Azure Site Recovery protects against full regional loss (a concern neither HA nor Backup alone addresses).
- 🔑 A complete VM resilience strategy deliberately layers all three: intra-region HA (Sets/Zones/VMSS), data backup, and cross-region DR — treating any one as sufficient on its own is a common and consequential design gap.

## 16. Related Concepts (Next Up)

Section 12 covers **VM Scale Sets** — the mechanism for running and automatically scaling a fleet of identical VMs (built from the same images and sizing principles just covered) to handle variable load and provide high availability across Availability Zones (Section 3.3.2), directly extending the single-VM concepts covered in this section to a managed, elastic group.
