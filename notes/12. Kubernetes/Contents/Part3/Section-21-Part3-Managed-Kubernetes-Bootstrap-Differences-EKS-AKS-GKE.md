# Section 21 (Part 3): Managed Kubernetes Bootstrap Differences: EKS, AKS, GKE

## 1. Definition

**Plain language:** Amazon EKS, Azure AKS, and Google GKE all give you a working Kubernetes API endpoint at the end of the process, but how you actually get there — what commands you run, what identity model you end up with, and what's configured for you versus what you must configure yourself — differs meaningfully between the three, and those differences show up on day one of using each cluster.

**Precise definition:** "Bootstrapping" a managed Kubernetes cluster means provisioning the **control plane** (fully hosted and operated by the cloud provider) and **worker node capacity**, then obtaining authenticated `kubectl` access. Each provider automates this differently: **EKS** requires an explicit, separate step to map AWS IAM identities to Kubernetes RBAC (historically the `aws-auth` ConfigMap, now increasingly **EKS access entries**); **AKS** offers first-class **Azure Active Directory (Entra ID) integration**, mapping Azure AD groups/users directly to Kubernetes RBAC with less manual wiring; and **GKE** has the tightest native IAM integration of the three, plus a distinct fork in the bootstrap model itself between **Standard mode** (customer manages node pools directly) and **Autopilot mode** (Google manages nodes entirely, billing per-Pod resource usage instead of per-node). Understanding these differences is what separates "I ran the quickstart" from actually knowing what identity and access model a given managed cluster left you with.

## 2. Why This Matters

- **The identity-to-RBAC mapping step is the single most common "why can't I access my new cluster" surprise across all three providers**, but the actual mechanism (and how automatic vs. manual it is) differs substantially — EKS in particular has caught many teams off guard because IAM identities have zero Kubernetes RBAC access by default until explicitly mapped.
- **This section is the practical continuation of §5's distribution spectrum** (Part 1), narrowing specifically into the "managed cloud" tier of that spectrum and showing that even within "managed," EKS/AKS/GKE are not interchangeable in their bootstrap and identity models.
- **Enterprise platform teams standardizing on one or multiple clouds need this comparison to make real architectural decisions** — §122–§129 (Part 16) builds directly on this section for enterprise-scale, cloud-specific considerations (cost governance, multi-cluster patterns, landing zones).

🔑 **Key Takeaway:** All three major managed offerings host the control plane for you, but EKS demands an explicit IAM-to-RBAC mapping step (`aws-auth` ConfigMap or access entries), AKS leans on native Azure AD group-to-RBAC integration, and GKE offers the tightest built-in IAM integration plus a genuine architectural fork between Standard and Autopilot modes — none of these details are optional trivia once you're actually operating one of these clusters.

## 3. Prerequisites and Dependencies

Builds directly on §5 (Part 1, the distribution spectrum, specifically the "managed cloud offerings" tier) and §20 (kubeconfig files and contexts, since each provider's bootstrap ends by populating exactly that kind of file). Assumes basic familiarity with each cloud's respective IAM model.

## 4. Bootstrap Model Comparison Diagram

```text
                    EKS                         AKS                          GKE
        ┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
        │ eksctl create cluster │   │ az aks create         │   │ gcloud container      │
        │  or Terraform/console │   │  (Azure AD integration│   │   clusters create     │
        │                       │   │  available at create  │   │   (or --enable-       │
        │                       │   │  time)                │   │   autopilot)          │
        └───────────┬───────────┘   └───────────┬───────────┘   └───────────┬───────────┘
                    │                           │                           │
                    ▼                           ▼                           ▼
        ┌───────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
        │ AWS IAM identity has  │   │ Azure AD user/group    │   │ GCP IAM principal has  │
        │ NO Kubernetes RBAC    │   │ can authenticate via   │   │ access if granted a    │
        │ access by default     │   │ `az aks get-credentials│   │ GKE-specific IAM role  │
        │                       │   │ ` + AD login; RBAC     │   │ (e.g., roles/container.│
        │ ─ MUST explicitly map:│   │ still needs a          │   │ developer) — IAM and   │
        │  aws-auth ConfigMap OR│   │ RoleBinding/           │   │ K8s RBAC integration   │
        │  EKS access entries   │   │ ClusterRoleBinding to  │   │ is native and tighter  │
        │  (IAM principal →     │   │ the AD identity        │   │ by default than EKS/   │
        │  Kubernetes username/ │   │                        │   │ AKS                    │
        │  group)               │   │                        │   │                        │
        └───────────┬───────────┘   └────────────┬───────────┘   └────────────┬───────────┘
                    │                            │                            │
                    ▼                            ▼                            ▼
        ┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
        │ aws eks update-        │   │ az aks get-credentials │   │ gcloud container       │
        │  kubeconfig            │   │                        │   │  clusters get-         │
        │  → populates kubeconfig│   │  → populates kubeconfig│   │  credentials           │
        │  with an exec-plugin   │   │  with Azure AD-based   │   │  → populates kubeconfig│
        │  credential (aws CLI/  │   │  exec-plugin credential│   │  with gcloud-based     │
        │  IAM authenticator)    │   │                        │   │  exec-plugin credential│
        └────────────────────────┘   └────────────────────────┘   └───────────┬────────────┘
                                                                              │
                                                        ┌─────────────────────┴─────────────────────┐
                                                        ▼                                           ▼
                                              ┌─────────────────────┐                       ┌───────────────────┐
                                              │  STANDARD MODE      │                       │  AUTOPILOT MODE   │
                                              │  customer manages   │                       │  Google manages   │
                                              │  node pools directly│                       │  nodes entirely;  │
                                              │  (sizes, scaling,   │                       │  billed per-Pod   │
                                              │  OS patching)       │                       │  resource usage   │
                                              └─────────────────────┘                       └───────────────────┘
```

- **EKS's identity gap is the sharpest of the three**: creating an EKS cluster with, say, Terraform, and then trying to `kubectl get nodes` with a _different_ IAM identity than the one that created the cluster fails outright until that second identity is explicitly added — this single fact accounts for a large share of "I can't access my own cluster" support tickets.
- **AKS's Azure AD integration is closer to "on by default" for organizations already using Azure AD**, since group-based RBAC bindings can be pre-provisioned as part of infrastructure-as-code, but a RoleBinding/ClusterRoleBinding is still a required, separate Kubernetes-side object even after AD authentication succeeds.
- **GKE's Standard-vs-Autopilot fork is not just a configuration flag but a genuinely different operational model** — Autopilot removes node-level access (no `kubectl exec` into a node, no DaemonSets requiring host access in the usual way) in exchange for Google fully managing node provisioning, scaling, and patching.

## 5. Hands-On: Bootstrapping and Authenticating Against Each Provider

### 5.1 EKS: Cluster Creation and the IAM-to-RBAC Mapping Step

**Purpose:** Show the explicit two-step nature of EKS access — cluster creation, then separately granting a given IAM identity Kubernetes-side access.

**Syntax:**

```bash
eksctl create cluster --name my-cluster --region us-east-1 --nodes 3
aws eks update-kubeconfig --name my-cluster --region us-east-1
```

**Example usage and expected output (checking/adding an access entry, the modern approach superseding manual `aws-auth` edits):**

```bash
$ aws eks list-access-entries --cluster-name my-cluster
{
    "accessEntries": [
        "arn:aws:iam::123456789012:role/EKSClusterCreatorRole"
    ]
}

$ aws eks create-access-entry \
    --cluster-name my-cluster \
    --principal-arn arn:aws:iam::123456789012:user/jane \
    --type STANDARD

$ aws eks associate-access-policy \
    --cluster-name my-cluster \
    --principal-arn arn:aws:iam::123456789012:user/jane \
    --access-scope type=cluster \
    --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSAdminPolicy
```

**Production usage example:** Terraform-managed EKS clusters commonly manage `aws_eks_access_entry` resources declaratively alongside the cluster itself, so every engineer or CI identity needing access is version-controlled rather than manually added via one-off CLI calls after the fact.

**Common errors:** Assuming the IAM identity that ran `eksctl create cluster`/`terraform apply` is automatically usable by teammates — by default, only that original identity (or whichever principal is explicitly granted) has any Kubernetes RBAC access at all; every other identity gets an `error: You must be logged in to the server (Unauthorized)` until explicitly mapped.

### 5.2 AKS: Cluster Creation With Azure AD Integration

**Purpose:** Show how Azure AD group-to-RBAC mapping is configured largely at cluster-creation time, and how `az aks get-credentials` differs from the EKS/GKE equivalents in triggering an interactive AD login.

```bash
$ az aks create \
    --resource-group my-rg \
    --name my-cluster \
    --enable-aad \
    --aad-admin-group-object-ids <azure-ad-group-object-id> \
    --generate-ssh-keys

$ az aks get-credentials --resource-group my-rg --name my-cluster

$ kubectl get nodes
To sign in, use a web browser to open the page https://microsoft.com/devicelogin
and enter the code ABCD1234 to authenticate.
```

**Production usage example:** Enterprises already standardized on Azure AD for corporate identity commonly find AKS's access model the least additional integration work of the three, since existing AD groups (already used for other corporate access control) can be bound directly to Kubernetes ClusterRoles without introducing a second parallel identity system.

**Common errors:** Enabling `--enable-aad` on an _existing_ non-AAD cluster is a disruptive, one-way migration in older AKS versions — Azure AD integration is far simpler to enable at cluster-creation time than to retrofit later.

### 5.3 GKE: Standard vs. Autopilot Bootstrap

**Purpose:** Contrast the two fundamentally different node-management models available at GKE cluster-creation time.

```bash
# Standard mode — customer manages node pools
$ gcloud container clusters create my-cluster \
    --zone us-central1-a --num-nodes 3 --machine-type e2-standard-4

# Autopilot mode — Google manages nodes entirely
$ gcloud container clusters create-auto my-cluster --region us-central1

$ gcloud container clusters get-credentials my-cluster --region us-central1
Fetching cluster endpoint and auth data.
kubeconfig entry generated for my-cluster.
```

**Production usage example:** Teams running unpredictable, spiky workloads (e.g., CI/CD runners, batch data processing) frequently prefer Autopilot specifically to avoid capacity-planning node pools manually, accepting a per-Pod pricing model in exchange for removing node-level operational burden entirely — while teams needing DaemonSets, custom node-level agents, or specific node OS/kernel tuning generally require Standard mode.

**Common errors:** Attempting to run a privileged DaemonSet or a workload requiring host-level access (common in some security/monitoring tooling) on Autopilot fails or is restricted, since Autopilot deliberately limits node-level access as part of its fully-managed model — this is a common surprise for teams migrating an existing Standard-mode workload to Autopilot without reviewing its node-level assumptions first.

## 6. Production Usage Notes

- **EKS's access-entries API (GA since 2023) is materially better than the legacy `aws-auth` ConfigMap approach** it's superseding — access entries are managed via the EKS API directly (auditable via CloudTrail, manageable via Terraform/IaC as first-class resources) rather than requiring careful, error-prone hand-edits of a ConfigMap where a YAML mistake could lock out all cluster access.
- **AKS's Azure AD integration pairs naturally with Azure RBAC for Kubernetes Authorization**, an alternative to native Kubernetes RBAC where Azure's own RBAC system (not `Role`/`ClusterRoleBinding` objects) governs Kubernetes access — a meaningfully different authorization model teams should deliberately choose, not default into.
- **GKE Autopilot's per-Pod billing model changes cost optimization strategy entirely** compared to Standard mode's per-node billing — rightsizing Pod resource requests/limits becomes the primary lever for cost control on Autopilot, whereas Standard mode cost optimization is more about node pool sizing and bin-packing efficiency.
- **All three providers' `kubectl` credential flows depend on their respective CLI being authenticated first** (`aws configure`/SSO session, `az login`, `gcloud auth login`) — a kubeconfig populated by any of these three commands is only as good as the underlying cloud CLI session remaining valid, which is a common gap in CI pipelines that copy a developer's kubeconfig without an equivalent non-interactive credential.

## 7. Security Considerations

- **EKS's explicit IAM-to-RBAC mapping, while initially more friction, gives fine-grained, auditable control over exactly which AWS principals get exactly which Kubernetes access** — treating this as a nuisance to bypass (e.g., overly broad access-entry policies) undermines the actual security value of the model.
- **AKS's Azure AD integration inherits whatever conditional access, MFA, and group-membership policies the organization already enforces in Azure AD**, which can be a meaningful security win — but it also means Kubernetes access security is only as strong as the underlying Azure AD hygiene (stale group memberships are a common, easily-overlooked risk).
- **GKE's tight IAM integration means a GCP IAM misconfiguration (an overly broad `roles/container.admin` grant) can translate directly into broad Kubernetes cluster access** — reviewing GCP IAM bindings with Kubernetes access implications specifically in mind is a distinct security review step from reviewing general GCP IAM hygiene.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                                       | Likely Cause                                                                                              | Resolution Path                                                                                                                                                    |
| ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `error: You must be logged in to the server (Unauthorized)` on a freshly created EKS cluster (as a teammate, not the creator) | IAM identity has no EKS access entry / `aws-auth` mapping                                                 | Add an access entry (`aws eks create-access-entry` + `associate-access-policy`) or edit `aws-auth` ConfigMap for that principal                                    |
| `az aks get-credentials` succeeds but `kubectl` hangs on a device-login prompt repeatedly                                     | Azure AD-integrated cluster requiring interactive login in a non-interactive context (script, CI)         | Use a service principal or managed identity credential flow instead of interactive AD login for automation                                                         |
| DaemonSet or privileged workload fails to schedule on GKE                                                                     | Cluster is running in Autopilot mode, which restricts node-level/privileged access                        | Confirm cluster mode (`gcloud container clusters describe`); migrate the workload to Standard mode if node-level access is genuinely required                      |
| Managed cluster's kubeconfig entry works locally but fails in CI                                                              | Underlying cloud CLI session (AWS SSO, `az login`, `gcloud auth`) not authenticated in the CI environment | Configure CI-appropriate non-interactive credentials (IAM role for service accounts, service principal, workload identity) rather than reusing a developer session |

## 9. Best Practices

- Manage IAM/Azure AD/GCP IAM-to-Kubernetes-RBAC mappings declaratively as infrastructure-as-code (Terraform `aws_eks_access_entry`, AKS AD group bindings, GCP IAM role grants) rather than ad-hoc CLI commands, so access is auditable and reproducible.
- Choose GKE Autopilot vs. Standard (and equivalently, whether a workload truly needs node-level access on any provider) deliberately at design time, not as an afterthought discovered when a DaemonSet fails to schedule.
- Treat each provider's underlying CLI authentication (AWS SSO session, `az login`, `gcloud auth login`) as a distinct prerequisite from the kubeconfig itself, and provision CI/automation-appropriate credentials separately from human developer sessions.

## 10. Common Anti-Patterns / Mistakes

- **Assuming "I created the cluster" is equivalent to "my team has access to the cluster"** on EKS specifically — the creating identity's access does not automatically extend to anyone else without an explicit access entry or `aws-auth` mapping.
- **Granting overly broad access-entry policies or IAM roles "to make the error go away"** rather than scoping Kubernetes RBAC access to what's actually needed — defeating the purpose of each provider's fine-grained identity integration.
- **Migrating an existing Standard-mode GKE workload to Autopilot without reviewing its node-level assumptions** (privileged DaemonSets, custom node configuration, specific host access patterns) first, then being surprised when it fails to schedule.

## 11. Interview Questions

**🎯 Beginner:** _"You just created a new EKS cluster and a teammate tries to run `kubectl get pods` against it — but gets an authorization error. Why?"_
**Model answer:** By default, only the IAM identity that created the EKS cluster has Kubernetes RBAC access — no other AWS IAM user or role is automatically granted access. The teammate's IAM identity needs to be explicitly mapped to a Kubernetes identity, either via an EKS access entry (the modern approach) or the legacy `aws-auth` ConfigMap, before their `kubectl` commands will be authorized.
_What the interviewer is probing for:_ Awareness of EKS's distinctive, explicit IAM-to-RBAC gap, which is one of the most common early-EKS surprises.

**🎯 Intermediate:** _"Compare how EKS, AKS, and GKE each handle mapping cloud identity to Kubernetes RBAC access."_
**Model answer:** EKS requires the most explicit, separate step — IAM principals have zero Kubernetes access by default and must be added via EKS access entries (or the older `aws-auth` ConfigMap), mapping an IAM ARN to a Kubernetes username/group. AKS offers native Azure AD integration, where AD users or groups authenticate via `az aks get-credentials` and interactive AD login, though a Kubernetes-side RoleBinding/ClusterRoleBinding is still required to actually grant permissions once authenticated. GKE has the tightest built-in integration of the three — granting a GCP IAM role like `roles/container.developer` can itself confer meaningful Kubernetes access with comparatively less separate Kubernetes-side configuration, though fine-grained access still benefits from Kubernetes RBAC layered on top.
_What the interviewer is probing for:_ Genuine comparative knowledge across all three providers, not just familiarity with whichever one the candidate has used most.

**🎯 Senior:** _"A team wants to migrate a workload from a self-managed kubeadm cluster to GKE Autopilot to reduce operational overhead. What would you check before approving that migration?"_
**Model answer:** I'd first audit the workload for any node-level assumptions that Autopilot restricts — privileged containers, DaemonSets requiring host access, custom kernel parameters or node-level agents (security scanners, custom CNI configuration), and any `hostNetwork`/`hostPath` usage, since Autopilot's fully-managed node model deliberately limits these to maintain its operational guarantees. I'd also review the workload's resource request/limit hygiene closely, since Autopilot bills per-Pod resource usage rather than per-node — a workload with poorly-set requests/limits that was previously "hidden" inside underutilized node capacity would suddenly have its actual resource cost made very visible and directly billed. Finally, I'd confirm whether any existing IAM-to-RBAC or cluster-level customization the team relies on (custom admission webhooks, specific network policies) is compatible with Autopilot's more restricted, opinionated cluster configuration surface, since Autopilot intentionally locks down certain cluster-level customization options in exchange for its managed guarantees.
_What the interviewer is probing for:_ Ability to translate the conceptual "Autopilot manages nodes for you" tagline into concrete migration-blocking checks, not just accepting the marketing framing at face value.

**🎯 Architect:** _"Your organization runs workloads across EKS, AKS, and GKE for different business units, and you're asked to design a consistent identity and access governance model across all three. What would you propose, and what's the core tension you're managing?"_
**Model answer:** I'd propose federating all three providers' Kubernetes RBAC access through the organization's existing central identity provider (most commonly via OIDC federation) rather than relying on each cloud's native identity integration in isolation, so a single source of truth (group memberships, joiner/mover/leaver processes) governs access consistently across all three clusters' underlying clouds. Concretely, that likely means: EKS access entries mapped to IAM roles that are themselves federated from the central IdP via SSO; AKS's native Azure AD integration, which — if the org's central IdP is Azure AD itself — requires the least additional federation work; and GKE IAM roles granted to federated identities via Workload Identity Federation rather than long-lived GCP service account keys. The core tension I'm managing is that each provider's "native" identity integration is the path of least resistance and best supported by that provider's tooling, but leaning fully into three different native models risks three inconsistent, independently-drifting access policies over time — versus centralizing through a common IdP, which adds federation complexity but gives the organization one place to enforce and audit access policy regardless of which cloud a given cluster runs on. I'd bias toward the centralized approach specifically because the organization's stated goal is _consistent_ governance across clouds, not just "working" access per cloud.
_What the interviewer is probing for:_ Ability to reason about cross-cloud governance trade-offs at a genuinely architectural level, recognizing the tension between per-provider convenience and organization-wide consistency, rather than picking one cloud's native model and declaring it the answer for all three.

## 12. Common Misconceptions

1. **"Creating a managed cluster automatically grants my whole team access."** True on none of the three by default — EKS requires the most explicit separate mapping step, but even AKS and GKE require deliberate RBAC/IAM configuration beyond just cluster creation.
2. **"Managed Kubernetes means there's nothing left to configure."** The control plane is managed, but IAM/RBAC mapping, node pool sizing (outside Autopilot), networking, and workload configuration remain entirely the customer's responsibility on all three.
3. **"GKE Autopilot and Standard mode are just a pricing toggle."** They're genuinely different operational models — Autopilot removes node-level access and imposes workload restrictions in exchange for Google's full node management, not simply a different billing formula on an otherwise identical cluster.
4. **"AKS's Azure AD integration means Kubernetes RBAC is unnecessary."** Azure AD handles authentication (proving who you are); Kubernetes RBAC (or Azure RBAC for Kubernetes Authorization, an alternative) still governs authorization (what that identity is allowed to do) — the two layers remain distinct even with AD integration enabled.

## 13. 🔑 Key Takeaways

- All three managed offerings host the control plane, but their identity-to-RBAC bootstrap models differ substantially: EKS requires explicit access entries/`aws-auth` mapping, AKS leans on native Azure AD group integration, GKE has the tightest built-in IAM integration of the three.
- EKS's "creator-only default access" is the single most common managed-Kubernetes onboarding surprise and must be explicitly addressed for every team member or automation identity needing access.
- GKE's Standard vs. Autopilot split is a genuine architectural fork (node-level access and billing model), not a superficial configuration flag — choose deliberately based on whether the workload needs node-level access.
- Every provider's kubeconfig-populating CLI command depends on that cloud's own CLI being authenticated first, a frequently-missed prerequisite in CI/automation contexts.
- Enterprise-scale governance across multiple managed providers benefits from centralizing identity through a common IdP rather than relying on each provider's native integration in isolation (§122–§129 build on this at enterprise depth).

## 14. Related Concepts & What's Next

This section narrowed §5's (Part 1) broader distribution spectrum specifically into the "managed cloud" tier, and built on §20's kubeconfig mechanics, since every provider's bootstrap flow ends by populating exactly that kind of file. §122–§129 (Part 16) return to EKS/AKS/GKE at enterprise scale — multi-cluster governance, cost optimization, and landing-zone patterns that assume this section's bootstrap-level differences as a starting point. §22 (next) shifts from managed cloud offerings to the opposite end of the distribution spectrum: lightweight distributions and local dev clusters (k3s, MicroK8s, kind, minikube).

**Next Section:** §22 — `Section-22-Part3-Lightweight-Distributions-Local-Dev-Clusters.md`
