# Section 60 — Azure Bastion

## 60.1 Definition

**Plain language:** Azure Bastion is a managed service that lets you RDP or SSH into a VM using nothing but a browser (or the Azure CLI), without that VM ever needing a public IP address and without opening any inbound RDP/SSH ports on your network. It's Azure's answer to "how do administrators reach VMs securely" that doesn't involve exposing management ports to the internet or maintaining your own jump-box VM.

**Precise definition:** Azure Bastion is a fully-managed PaaS service, deployed into a customer's VNet via a dedicated subnet, that provides secure RDP and SSH connectivity to VMs within that VNet (and peered VNets) directly through the Azure Portal, CLI, or native client tooling over TLS on port 443 — eliminating the need to assign public IP addresses to individual VMs or open inbound NSG rules for RDP (3389) or SSH (22) purely for administrative access.

## 60.2 Why It Exists / Problem It Solves

Section 22 established NSGs and the general principle of minimizing exposed inbound ports; Section 59's network security deep-dive covered perimeter firewalls, WAF, and DDoS protection for application traffic — but administrative access (an operator needing to RDP or SSH into a specific VM to troubleshoot or configure it) has traditionally been a persistent exception to "don't expose management ports," commonly solved by either giving VMs public IPs with NSG rules restricting RDP/SSH to specific source IPs (fragile — source IPs change, and any public IP with an open management port is a standing attack surface regardless of source restrictions), or by standing up a self-managed "jump box" VM with a public IP that administrators RDP/SSH into first, then hop from there to internal VMs (better, but the jump box itself is now a VM the customer must patch, secure, and keep available, and still typically needs its own exposed public IP and open port). Azure Bastion exists to remove this trade-off entirely: administrators get browser-based or CLI-based RDP/SSH access to any VM in the VNet, target VMs never need a public IP for this purpose, no inbound NSG rule for RDP/SSH ever needs to be opened, and Azure — not the customer — manages, patches, and scales the Bastion host itself, unlike a self-managed jump box.

## 60.3 How It Works

### 60.3.1 The AzureBastionSubnet

**Definition:** Azure Bastion must be deployed into a specifically-named, dedicated subnet called **`AzureBastionSubnet`** within the target VNet — similar in spirit to the `GatewaySubnet` requirement for VPN/ExpressRoute Gateways (Section 26.7), this exact naming is a hard platform requirement, not merely a convention, and the subnet cannot be shared with other resources.

### 60.3.2 Connection Flow

**How it works conceptually:** An administrator connects to the Bastion service's public endpoint (over HTTPS/443) via the Azure Portal, the Azure CLI, or native RDP/SSH client integration; Bastion then establishes the actual RDP/SSH session to the target VM using the VM's **private IP address**, entirely within the VNet — from the target VM's perspective, the connection arrives from Bastion's presence within the VNet, not from the administrator's original public-internet location, and the target VM itself never needs to expose any port to the internet at all.

### 60.3.3 Native Client Support

Beyond the browser-based Portal experience, Azure Bastion supports connecting via native RDP/SSH clients (e.g., using `az network bastion rdp` or `az network bastion ssh` from the Azure CLI, which tunnels the native client's connection through Bastion) — giving administrators the familiar tooling experience of a direct RDP/SSH client while still routing the connection through Bastion's managed, no-public-IP-required path.

### 60.3.4 SKU Tiers

Azure Bastion is offered in multiple SKU tiers (commonly a Basic/Standard-style distinction), with higher tiers unlocking capabilities like native client support, VM scale set connectivity, and higher concurrent session limits. ⚠️ Exact SKU names, their specific feature sets, and current concurrent-session limits change over time — verify current SKU capabilities against official documentation when sizing a production Bastion deployment.

## 60.4 Azure Bastion vs. Self-Managed Jump Box vs. Just-In-Time VM Access — Comparison

| Aspect                              | Public IP + NSG restriction      | Self-Managed Jump Box VM                                 | Azure Bastion                                                   | JIT VM Access (Section 55, Defender for Cloud)                                              |
| ----------------------------------- | -------------------------------- | -------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Target VM needs a public IP         | Yes                              | No (target VM stays private; jump box has the public IP) | No                                                              | No (still uses NSG rules, but time-limited)                                                 |
| Who manages/patches the access host | N/A (no separate host)           | Customer (it's just another VM)                          | Azure (fully managed PaaS)                                      | N/A (no separate host; NSG-based, not host-based)                                           |
| Inbound RDP/SSH port ever opened    | Yes, restricted by source IP     | Yes, on the jump box only                                | No — Bastion connects over 443; no RDP/SSH port opened anywhere | Yes, but only for a short, explicitly-requested time window                                 |
| Best fit                            | Rarely recommended in production | Legacy pattern, largely superseded by Bastion            | Standard recommended approach for ongoing administrative access | Complementary — reduces standing exposure for solutions still using direct NSG-based access |

🎯 **Interview Tip:** A frequently tested distinction: Azure Bastion and Just-In-Time (JIT) VM Access (Section 55.5.1) solve a similar underlying problem (reduce standing exposure of RDP/SSH) but via different mechanisms — JIT still opens an NSG rule for RDP/SSH, just for a short, explicitly-requested time window and typically restricted to the requester's IP; Bastion removes the need to ever open that NSG rule at all, since the connection never arrives as inbound RDP/SSH traffic to the VM's NSG in the first place. The two are complementary and can be used together, not mutually exclusive alternatives.

## 60.5 Architecture Diagram

```
Administrator's browser / Azure CLI
      │
      │  HTTPS (443) to Bastion's public endpoint
      ▼
Azure VNet "vnet-hub"
 ├── Subnet: AzureBastionSubnet
 │     └── Azure Bastion (managed PaaS host)
 │
 └──(private IP connection, RDP/SSH)──► Subnet: vnet-app-a (peered spoke, Section 23)
                                              └── VM "vm-web-01" — NO public IP, NO inbound RDP/SSH NSG rule
```

## 60.6 Configuration & Hands-On Example

**Creating the required subnet and deploying Azure Bastion:**

```bash
az network vnet subnet create \
  --resource-group rg-hub \
  --vnet-name vnet-hub \
  --name AzureBastionSubnet \
  --address-prefix 10.0.100.0/26

az network public-ip create \
  --resource-group rg-hub \
  --name pip-bastion \
  --sku Standard

az network bastion create \
  --resource-group rg-hub \
  --name bastion-hub \
  --vnet-name vnet-hub \
  --public-ip-address pip-bastion \
  --sku Standard
```

- **Purpose:** Creates the mandatory, exactly-named `AzureBastionSubnet`, a Standard SKU public IP (required for Bastion's own public-facing endpoint — this is Bastion's IP, not the target VMs'), and the Bastion resource itself.
- **Important arguments explained individually:**
  - `AzureBastionSubnet` — must match this exact name; unlike most Azure subnets, this name isn't customer-chosen.
  - `--address-prefix 10.0.100.0/26` — Bastion requires a minimum subnet size (commonly a /26 or larger, depending on current guidance); ⚠️ verify current minimum subnet size requirements against official documentation, as these have been revised over time.
  - `--sku Standard` — required for native client support and several other capabilities beyond the Basic tier (Section 60.3.4).
- **Common error:** Attempting to deploy Bastion into a subnet with any other name, or attempting to share `AzureBastionSubnet` with other resources, fails — this subnet must be dedicated exclusively to Bastion, exactly as `GatewaySubnet` (Section 26.7) must be dedicated exclusively to VPN/ExpressRoute Gateways.

**Connecting to a VM via the CLI using a native client:**

```bash
az network bastion rdp \
  --resource-group rg-hub \
  --name bastion-hub \
  --target-resource-id /subscriptions/.../virtualMachines/vm-web-01
```

- **Purpose:** Tunnels a native RDP client connection to `vm-web-01` through Bastion, giving the administrator their familiar RDP client experience while the underlying connection still routes through Bastion's managed, no-public-IP-required path (Section 60.3.3).

## 60.7 Production & Enterprise Usage

Enterprises typically deploy a single Azure Bastion instance in the hub VNet of a hub-and-spoke topology (Section 21.6, Section 66), giving administrators secure access to VMs across every peered spoke VNet from that one centrally-managed Bastion instance, rather than deploying Bastion separately per spoke VNet — mirroring the same centralization pattern already established for shared gateway infrastructure (Section 26.8) and Private DNS Zones (Section 28.7). This centralization also simplifies auditing: all administrative RDP/SSH access across the estate flows through one Bastion instance, giving a single point for access logging and review rather than access patterns scattered across multiple self-managed jump boxes or per-VM public IP exceptions.

## 60.8 Security Considerations

- Because Bastion eliminates the need for target VMs to have public IPs or open inbound RDP/SSH NSG rules, adopting it organization-wide meaningfully shrinks the VM-level attack surface compared to any pattern relying on direct public IP exposure for administrative access — this is Bastion's primary security value proposition, not merely a convenience feature.
- Access to Bastion itself should still be governed by RBAC (Section 8) and, where appropriate, Conditional Access/MFA (Section 10) — Bastion removes the network-level exposure problem, but administrative access to VMs through it still needs identity-level governance like any other privileged access path.
- Bastion can be combined with JIT VM Access (Section 55.5.1) for defense-in-depth on any remaining scenarios still using direct NSG-based access, though for VMs fully migrated to Bastion-only access, JIT's NSG-rule-based mechanism becomes largely unnecessary for that specific VM.

## 60.9 Performance Considerations

Bastion sessions route through the managed Bastion host rather than directly to the target VM's own network path, and higher-tier SKUs support more concurrent sessions — organizations with a large number of simultaneous administrators or heavy file-copy usage over Bastion sessions should size the SKU tier accordingly and verify current concurrent-session limits rather than assuming Basic tier capacity is sufficient at enterprise scale.

## 60.10 Monitoring

Bastion integrates with Azure Monitor and diagnostic logs (Part 10), providing session-level logs (who connected, to which VM, and when) — a valuable audit trail for privileged access review, particularly useful given that this centralizes what would otherwise be scattered, harder-to-audit access patterns across many self-managed jump boxes or per-VM public IP exceptions.

## 60.11 Troubleshooting

| Symptom                                                            | Likely Cause                                                                                                                     | Fix                                                                                                                       |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Cannot connect to a VM in a peered spoke VNet via Bastion          | VNet peering (Section 23) between the hub and spoke not configured, or NSG on the spoke blocking traffic from the Bastion subnet | Verify peering is active and that the spoke's NSGs permit RDP/SSH traffic originating from the `AzureBastionSubnet` range |
| Bastion deployment fails during subnet creation                    | Subnet not named exactly `AzureBastionSubnet`, or too small for current minimum size requirements                                | Recreate the subnet with the exact required name and a sufficiently large address range                                   |
| Native client connection via CLI fails, browser-based access works | Basic SKU in use, which doesn't support native client connectivity                                                               | Upgrade to Standard (or current equivalent higher) SKU tier                                                               |

## 60.12 Interview Questions — Section 60

### 🎯 Intermediate

**Q: How does Azure Bastion let administrators reach a VM without that VM having a public IP address?**

_Model answer:_ Azure Bastion is deployed as a managed PaaS service into a dedicated `AzureBastionSubnet` within the VNet. Administrators connect to Bastion's own public endpoint over HTTPS (443) via the Portal, CLI, or native client tooling; Bastion then establishes the actual RDP/SSH connection to the target VM using the VM's private IP address, entirely within the VNet (or a peered VNet). The target VM never needs a public IP or an open inbound RDP/SSH NSG rule, because the connection to it originates from Bastion inside the VNet, not from the administrator's original public-internet location.

_What the interviewer is probing:_ whether the candidate understands the actual connection flow (public endpoint on Bastion itself, private connection from Bastion to the target VM) rather than a vague "it's more secure" answer without explaining the underlying mechanism.

### 🎯 Senior

**Q: Your organization currently has several VMs with public IPs and NSG rules restricting RDP access to the office's IP range, plus one self-managed jump box VM for remote administrators. Security has flagged this as a risk. How would you redesign this using Azure Bastion, and what would you tell the team about JIT VM Access (Section 55.5.1)?**

_Model answer:_ I'd deploy a single Azure Bastion instance in the hub VNet (assuming a hub-and-spoke topology is in place, or establish one if not), remove the public IPs from the VMs currently using restricted NSG rules for RDP, and migrate administrative access to those VMs through Bastion instead — eliminating both the standing public IP exposure and the fragility of IP-range-based restrictions (which break the moment an administrator isn't connecting from the office network). I'd similarly retire the self-managed jump box, since Bastion provides the same "single, controlled entry point for administrative access" function without the customer needing to patch, secure, and maintain that jump box VM themselves. For any remaining scenario that, for a specific reason, still needs direct NSG-based RDP/SSH access rather than routing through Bastion, I'd recommend layering in JIT VM Access so that even that direct access path is only open for a short, explicitly-requested window rather than standing open continuously — but I'd be clear with the team that for any VM now behind Bastion, JIT's NSG-based mechanism is largely redundant, since Bastion has already removed the need for an open inbound port on that VM at all. I'd also make sure Bastion access itself is governed by RBAC and Conditional Access/MFA, since centralizing access through Bastion is only a security improvement if access to Bastion itself is properly controlled.

_What the interviewer is probing:_ whether the candidate can design a genuine migration away from risky legacy patterns (public IP + NSG restriction, self-managed jump box) to Bastion, correctly scope where JIT VM Access still adds value versus where it becomes redundant once Bastion is adopted, and remembers that centralizing access still requires identity-level governance on top of the network-level improvement.

## 60.13 Common Misconceptions

- **"Azure Bastion is just a VPN."** False — Bastion provides RDP/SSH session brokering to specific VMs through the Portal/CLI/native client tooling over HTTPS; it doesn't establish a general-purpose network tunnel into the VNet the way a VPN Gateway (Section 26.3) does, and isn't a substitute for VPN Gateway/ExpressRoute for broader hybrid connectivity needs.
- **"Once Bastion is deployed, JIT VM Access becomes entirely obsolete everywhere."** Not quite — for VMs fully migrated to Bastion-only access, JIT's NSG-based mechanism is indeed largely redundant for that VM specifically, but JIT still has a role for any remaining direct-access scenarios not yet migrated to Bastion.

## 60.14 Key Takeaways

- 🔑 Azure Bastion provides browser/CLI-based RDP/SSH access to VMs without those VMs needing a public IP or an open inbound RDP/SSH NSG rule.
- 🔑 It must be deployed into a dedicated, exactly-named `AzureBastionSubnet`, similar in requirement-strictness to the `GatewaySubnet` for VPN/ExpressRoute Gateways (Section 26.7).
- 🔑 Bastion is typically centralized in a hub VNet, giving secure administrative access to VMs across every peered spoke from one managed instance.
- 🔑 Bastion and JIT VM Access (Section 55.5.1) solve a similar problem via different mechanisms and can be used together, but Bastion removes the need to ever open an inbound RDP/SSH NSG rule at all, while JIT merely narrows the window such a rule is open.
- 🔑 Access to Bastion itself still requires RBAC/Conditional Access governance — it solves the network-exposure problem, not the identity-governance problem, and both matter for genuinely secure administrative access.

## 60.15 Related Concepts / Part 11 Wrap-Up

This completes **Part 11 — Security & Governance**, covering Microsoft Defender for Cloud/CSPM, Key Vault, Azure Policy/Blueprints, compliance/encryption, network security deep-dive, and now Azure Bastion for secure administrative access — the full security and governance foundation layered on top of every compute, storage, and networking resource covered so far. **Part 12 — HA, DR, Scaling & Cost** begins next with Section 61, shifting focus from securing the environment to making it resilient and cost-efficient, starting with HA/DR Patterns and the distinction between Availability Sets and Availability Zones.
