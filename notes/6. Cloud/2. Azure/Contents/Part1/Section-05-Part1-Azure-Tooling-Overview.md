# Section 5 — Azure Portal, CLI, PowerShell, SDKs: Tooling Overview

## 1. Definition

**Plain language:** Azure gives you several different ways to talk to Azure Resource Manager (ARM, Section 4) — a visual web interface, command-line tools, scripting languages, and programming-language libraries — and they all ultimately send the same underlying API requests, just packaged differently for different workflows.

**Precise definition:** All Azure management tools (Portal, CLI, PowerShell, SDKs, REST API directly) are clients of the same ARM REST API. They differ in interface (graphical vs. text vs. programmatic), authentication flow, scripting/automation suitability, and target audience, but produce identical underlying resource operations and are subject to identical RBAC and Policy enforcement.

## 2. Why It Exists / Problem It Solves

Different tasks and different people need different interfaces to the same underlying system. A person exploring Azure for the first time, or debugging a resource visually, benefits from a graphical Portal. A DevOps engineer writing a repeatable deployment script needs a scriptable command-line tool. A Windows-centric enterprise team already invested in PowerShell for on-premises Active Directory management wants a PowerShell-native interface. A developer building an application that needs to programmatically create or query Azure resources needs a language SDK, not a human-facing tool at all. Having one underlying API (ARM) with multiple front-ends solves all of these needs without duplicating the platform itself.

## 3. Azure Portal

**Definition:** The Azure Portal (portal.azure.com) is a web-based graphical user interface for creating, viewing, and managing Azure resources.

**When to use it:** Learning and exploration (seeing available options visually rather than memorizing CLI flags), one-off manual tasks, visually inspecting resource relationships and metrics dashboards, and quickly checking on resource status without writing a script.

**Limitations:** Not scriptable/repeatable — actions taken in the Portal are not automatically reproducible, making it a poor fit for production deployment processes where repeatability and audit trails matter. The Portal is best understood as a _discovery and inspection_ tool, not a _production deployment_ tool — production deployments should use Infrastructure as Code (Part 9) instead.

> 💡 **Tip:** The Portal includes a "Cloud Shell" — a free, browser-based terminal with the Azure CLI and PowerShell pre-installed — useful for quick scripted tasks without installing anything locally.

## 4. Azure CLI

**Definition:** The Azure CLI (`az` command) is a cross-platform command-line tool for managing Azure resources, installable on Windows, macOS, and Linux, and usable interactively or in scripts.

**Syntax pattern:** Azure CLI commands generally follow the structure:

```bash
az <resource-group-name-or-service> <sub-command> [--parameters]
```

**Example — creating a Virtual Machine:**

```bash
az vm create \
  --resource-group rg-myapp-prod \
  --name vm-web-01 \
  --image Ubuntu2204 \
  --admin-username azureuser \
  --generate-ssh-keys
```

- **Purpose:** Creates a new Linux VM in one command, including generating an SSH key pair for authentication if one doesn't already exist locally.
- **Important arguments explained individually:**
  - `--resource-group` — the target resource group (Section 4.3.2) the VM will belong to; must already exist.
  - `--name` — the resource name for the VM, used in its Resource ID.
  - `--image` — the base OS image; Azure CLI accepts shorthand aliases like `Ubuntu2204` as well as full image URNs for more specific version pinning.
    > ⚠️ Available shorthand aliases change over time — verify current aliases against `az vm image list` before relying on one in a script.
  - `--admin-username` — the initial administrative user created on the VM.
  - `--generate-ssh-keys` — tells the CLI to create a new SSH key pair automatically if none is found at the default local path, rather than requiring the user to pre-generate one.
- **Expected output (abbreviated):**

```json
{
  "fqdns": "",
  "id": "/subscriptions/<sub-id>/resourceGroups/rg-myapp-prod/providers/Microsoft.Compute/virtualMachines/vm-web-01",
  "powerState": "VM running",
  "publicIpAddress": "20.185.xx.xx",
  "resourceGroup": "rg-myapp-prod"
}
```

- **Common errors:** `ResourceGroupNotFound` if the resource group doesn't exist yet; `SkuNotAvailable` if the chosen VM size isn't available in the target region (requiring either a different size or a different region).
- **Production usage:** CLI commands are the backbone of most CI/CD pipeline deployment scripts, wrapped in pipeline YAML (Azure DevOps or GitHub Actions, Part 9) rather than run manually.

**When to use CLI over PowerShell:** Teams with a Linux/macOS-centric or cross-platform background, teams already using Bash-based automation, or teams that find the CLI's syntax (closer to typical Unix tools) more natural.

## 5. Azure PowerShell

**Definition:** Azure PowerShell is a set of PowerShell modules (`Az` module) providing cmdlets for managing Azure resources, following PowerShell's verb-noun naming convention (e.g., `New-AzVM`, `Get-AzResourceGroup`).

**Example — creating a resource group (PowerShell equivalent of the CLI example in Section 3.5):**

```powershell
New-AzResourceGroup -Name "rg-myapp-prod" -Location "eastus"
```

- **Purpose:** Identical underlying operation to the CLI's `az group create`, expressed in PowerShell's verb-noun cmdlet style.
- **Expected output:** A PowerShell object representing the resource group, with properties like `ResourceGroupName`, `Location`, and `ProvisioningState` accessible as native PowerShell object properties (not just text) — this is PowerShell's key structural advantage: output is a real object you can pipe into further cmdlets, not just text you'd need to parse.

**When to use PowerShell over CLI:** Teams already deeply invested in PowerShell for other automation (especially Windows Server, on-premises Active Directory, or Microsoft 365 administration), where consistent tooling and PowerShell's object-pipeline model (versus CLI's text/JSON output) provides real workflow advantages, particularly for complex scripts that need to inspect and branch on returned data.

## 6. SDKs (Software Development Kits)

**Definition:** Azure SDKs are language-specific libraries (available for Python, .NET/C#, Java, JavaScript/Node.js, Go, and others) that let application code programmatically create, query, and manage Azure resources, using the same underlying ARM API as the Portal, CLI, and PowerShell.

**When to use it:** When Azure resource management needs to be embedded _inside application logic_ itself — for example, an application that dynamically provisions a new storage container per customer, or an internal tool that automates resource cleanup based on custom business logic that doesn't fit a simple CLI script.

**Example conceptual usage (Python, illustrative):**

```python
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient

credential = DefaultAzureCredential()
client = ResourceManagementClient(credential, subscription_id="<sub-id>")
client.resource_groups.create_or_update(
    "rg-myapp-prod",
    {"location": "eastus"}
)
```

- **Purpose:** Demonstrates the same resource-group-creation operation as the previous two examples, now embedded in application code rather than run as a standalone command.

> ⚠️ Exact SDK method names, package names, and authentication class names evolve across SDK versions — always verify current syntax against the official SDK documentation for your specific language and version before relying on this pattern in production code; this example is illustrative of the general pattern (credential object + management client + resource operation), not a guaranteed-current API surface.

## 7. REST API (The Common Foundation)

All of the tools above are ultimately clients of the same underlying **ARM REST API** — for example, creating a resource group is fundamentally a `PUT` request to a URL like `https://management.azure.com/subscriptions/<sub-id>/resourceGroups/<rg-name>?api-version=<version>` with a JSON body specifying the location. Understanding this matters because: (1) it explains why CLI, PowerShell, Portal, and SDKs all enforce identical RBAC/Policy rules — there's no "back door" tool that bypasses governance, and (2) if a specific capability isn't yet exposed in a given tool's latest release, it can often still be reached by calling the REST API directly.

## 8. Comparison Matrix

| Tool                     | Best For                                                           | Scriptable    | Learning Curve | Platform                            |
| ------------------------ | ------------------------------------------------------------------ | ------------- | -------------- | ----------------------------------- |
| Portal                   | Exploration, visual inspection, one-off tasks                      | No            | Lowest         | Web browser, any OS                 |
| CLI (`az`)               | Scripts, CI/CD pipelines, cross-platform teams                     | Yes           | Low–Medium     | Windows/macOS/Linux                 |
| PowerShell (`Az` module) | Scripts, teams already using PowerShell, object-pipeline workflows | Yes           | Low–Medium     | Windows/macOS/Linux (PowerShell 7+) |
| SDKs                     | Embedding resource management inside applications                  | Yes (as code) | Medium–High    | Language-specific                   |
| REST API                 | Direct/custom integration, tools without native SDK support        | Yes           | High           | Any (HTTP)                          |

## 9. Production & Enterprise Usage

In production environments, **manual Portal changes are strongly discouraged** for anything beyond initial exploration or emergency troubleshooting, because they aren't repeatable, aren't naturally version-controlled, and tend to cause "configuration drift" between what's documented/expected and what's actually deployed. Enterprises standardize on either CLI or PowerShell (sometimes both, depending on team background) wrapped in Infrastructure as Code templates (ARM/Bicep/Terraform, Part 9) and executed through CI/CD pipelines, with the Portal reserved for read-only dashboards, cost review, and incident investigation. SDKs are used specifically where resource management logic needs to be part of a larger application rather than a standalone operational task.

## 10. Security Considerations

Regardless of which tool is used, authentication ultimately flows through Microsoft Entra ID (Part 2) — the CLI and PowerShell both support interactive login (`az login` / `Connect-AzAccount`) for human users and non-interactive authentication via Service Principals or Managed Identities (Section 9) for automation scenarios like CI/CD pipelines, which should **never** use a human user's personal credentials for automated processes, since that creates an audit and security liability tied to an individual rather than a dedicated, scoped automation identity.

## 11. Interview Questions — Section 5

### 🎯 Beginner

**Q: Why would you use the CLI instead of the Portal for deploying resources?**

_Model answer:_ The CLI is scriptable and repeatable — you can save the exact commands used to create an environment, re-run them to recreate it identically, version-control them, and integrate them into automated pipelines, none of which is possible with manual Portal clicks. The Portal is better suited to exploration and one-off inspection tasks rather than repeatable production deployments.

_What the interviewer is probing:_ whether the candidate understands the operational difference between manual and automated processes, a core DevOps mindset check.

### 🎯 Intermediate

**Q: A CI/CD pipeline needs to deploy Azure resources automatically. What authentication approach should it use, and why not just use a personal Azure login?**

_Model answer:_ The pipeline should authenticate using a Service Principal or, where the pipeline runs on Azure-hosted infrastructure, a Managed Identity (both covered in Section 9) — dedicated, non-human identities scoped with only the permissions the pipeline actually needs. Using a personal login ties automation to an individual's identity, meaning the pipeline breaks if that person leaves or their password rotates, obscures audit trails (was this action a human or the pipeline?), and typically grants the pipeline broader permissions than it actually needs since personal accounts often carry broad access for day-to-day work.

_What the interviewer is probing:_ understanding of the identity-lifecycle and least-privilege problems that arise from conflating human and automation credentials — a common real-world security anti-pattern interviewers specifically screen for.

## 12. Common Misconceptions

- **"The Portal is less powerful than the CLI."** Not entirely true — nearly everything is available in both; the real difference is repeatability and automation suitability, not raw capability.
- **"You must pick one tool and use it exclusively."** False — most engineers fluidly move between Portal (for inspection), CLI/PowerShell (for scripting), and SDKs (for application-embedded logic) depending on the task at hand.

## 13. Key Takeaways

- 🔑 All Azure tools (Portal, CLI, PowerShell, SDKs) are clients of the same underlying ARM REST API, so they enforce identical RBAC and Policy rules — no tool is a "back door."
- 🔑 The Portal is best for exploration and inspection; CLI/PowerShell/IaC are the standard for repeatable production deployment; SDKs are for embedding resource logic inside applications.
- 🔑 Automation (CI/CD pipelines) should authenticate via Service Principals or Managed Identities, never personal human credentials.
- 🔑 Choice between CLI and PowerShell is largely a team-background and object-vs-text-output preference, not a capability difference.

## 14. Related Concepts / Part 1 Wrap-Up

This completes **Part 1 — Foundations & Cloud Computing Model**. You now have the conceptual grounding (what Azure is, the service/deployment models, the physical global infrastructure, the ARM management hierarchy, and the tooling used to interact with it) needed for everything that follows. **Part 2 — Identity & Access Management** begins next with Section 6, covering Microsoft Entra ID — the identity system that determines _who_ can use the tools just described, and _what_ they're allowed to do once authenticated, directly building on the RBAC concept introduced in Section 4.4 and referenced throughout this section.
