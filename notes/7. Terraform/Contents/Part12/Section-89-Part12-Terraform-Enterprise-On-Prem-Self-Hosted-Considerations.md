# Section 89 (Part 12): Terraform Enterprise: On-Prem/Self-Hosted Considerations

## 1. Definition

**Plain language:** Terraform Enterprise (TFE) is the same organization/workspace/run product as Terraform Cloud, but installed and run inside an organization's own infrastructure (on-prem data center, private cloud, or air-gapped network) instead of on HashiCorp's SaaS — for organizations that can't or won't send their configuration, state, and run execution to a third-party-hosted service.

**Precise definition:** **Terraform Enterprise** is the self-hosted distribution of the Terraform Cloud product, distributed as a container-based application (deployable on Kubernetes, Docker, or supported VM images) that an organization installs and operates on its own infrastructure. It provides the same organization/workspace/run model, VCS integration, Sentinel policy engine, private registries, and API surface as TFC — the functional feature set is intentionally kept close to parity — but the organization is responsible for the operational concerns SaaS TFC handles invisibly: installation, upgrades, database and object-storage backing services, TLS certificate management, backup/restore, high availability, and network/firewall configuration, including support for fully **air-gapped** installations with no outbound internet access at all.

> 💡 **Tip:** The decision between TFC and TFE is almost never about missing features — it's about data residency, compliance, and network isolation requirements. A team asking "does TFE support Sentinel?" or "does TFE have the private registry?" is usually asking the wrong question; both products carry the same core capabilities. The real question is "can our configuration, state, and credentials leave our network boundary and be processed on infrastructure we don't operate?" — if the answer is no (common in regulated industries, government, or air-gapped environments), TFE is the answer regardless of feature parity.

## 2. Why This Matters

- **Regulatory and data-residency requirements sometimes mandate self-hosting outright.** Government, financial services, and healthcare organizations frequently have compliance regimes that prohibit sending infrastructure state (which can contain sensitive values) to a third-party SaaS product at all.
- **Air-gapped networks need a fully offline-capable option.** Some environments (classified/defense networks, certain industrial control systems) have no outbound internet connectivity whatsoever — TFE explicitly supports air-gapped installation with offline license and update mechanisms, which SaaS TFC cannot serve by definition.
- **Self-hosting shifts real operational burden onto the adopting organization.** Upgrades, backups, HA, and incident response for the TFE application itself become the platform team's responsibility — a cost that needs to be weighed honestly against the compliance benefit, not treated as free.
- **Network architecture decisions cascade from this choice.** TFE needs to reach the organization's VCS provider, cloud APIs, and any private registries it serves — often across firewall boundaries that need deliberate design in a way SaaS TFC's outbound-only model doesn't.
- **Licensing and cost models differ meaningfully from TFC's per-seat SaaS pricing.** TFE is typically licensed at the organization/deployment level, which changes the cost conversation from "per user" to "per platform investment."

## 3. Prerequisites and Dependencies

Assumes the full TFC organization/workspace/run model from [§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)–[§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md) — TFE is best understood as "the same product, self-operated," not a separate learning track. Some familiarity with container orchestration (Docker/Kubernetes) is assumed for the operational aspects covered here; see the Docker and Kubernetes knowledge bases if unfamiliar with those platforms specifically.

## 4. Architecture / Conceptual Diagram

```text
              TERRAFORM CLOUD (SaaS)              TERRAFORM ENTERPRISE (self-hosted)

   Org's network  ──HTTPS outbound──►  app.terraform.io      Org's network
        │                              (HashiCorp-operated)        │
        │  API tokens, VCS OAuth                                   ▼
        │                                                 ┌───────────────────────────────┐
        ▼                                                 │   TFE application             │
   Runs execute on HashiCorp                              │   (containers/K8s/VM)         │
   infrastructure; state stored                           │                               │
   on HashiCorp infrastructure                            │  - run execution (local       │
                                                          |  or agent-based)              │
                                                          │  - PostgreSQL (state/metadata)│
                                                          │  - object storage (blobs,     │
                                                          │    state versions)            │
                                                          │  - Vault (internal secrets)   │
                                                          └───────────────────────────────┘
                                                                        │
                                                          org-operated backups, HA,
                                                          upgrades, TLS certs, network
                                                          policy — all self-managed
```

- TFE requires the organization to stand up and operate its own PostgreSQL database and object storage backend (or use TFE's bundled equivalents for smaller deployments), unlike TFC where these are entirely invisible SaaS internals.
- TFE can be deployed in **air-gapped mode**, where updates and license validation happen via offline artifact bundles rather than reaching HashiCorp's servers.
- Run execution within TFE can still use agent-based execution ([§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)'s Agent execution mode) to reach further-isolated internal networks the TFE application itself can't directly access.

## 5. Hands-On

### 5.1 A Minimal TFE Deployment Configuration Shape (Conceptual)

**Purpose:** Illustrate the operational inputs a TFE install requires that a TFC signup never asks for.

**Syntax (Terraform Enterprise's own operational config, expressed as a Helm-values-style shape for the Kubernetes deployment path):**

```yaml
tfe:
  hostname: "tfe.internal.acme.corp"
  license: "${TFE_LICENSE}"
  encryption_password: "${TFE_ENCRYPTION_PASSWORD}"

database:
  host: "tfe-postgres.internal.acme.corp"
  name: "tfe"

object_storage:
  type: "s3"
  s3:
    bucket: "acme-tfe-object-storage"
    region: "us-east-1"

tls:
  cert_file: "/etc/tfe/tls/tls.crt"
  key_file: "/etc/tfe/tls/tls.key"
```

**Example usage and expected output:**

```bash
$ helm install tfe hashicorp/terraform-enterprise -f tfe-values.yaml -n tfe
NAME: tfe
STATUS: deployed

$ curl -sk https://tfe.internal.acme.corp/_health_check
{"status": "healthy"}
```

**Common errors:** Underestimating the PostgreSQL and object-storage sizing for the expected number of workspaces/state versions leads to performance degradation as run history grows — unlike TFC, where storage scaling is invisible, TFE's backing services need capacity planning like any other self-hosted stateful application.

### 5.2 Air-Gapped License and Update Handling

**Purpose:** Show the operational difference for environments with no outbound internet.

**Example usage and expected output:**

```bash
$ replicated app-manager install-bundle --license-file license.rli \
    --airgap-bundle terraform-enterprise-airgap-v202406-1.tar.gz
Verifying airgap bundle...
Installing Terraform Enterprise (air-gapped mode)...
Terraform Enterprise is installed and running.

# No outbound calls to HashiCorp's license/update servers occur at any point.
```

**Production usage example:** A defense contractor operating on a fully isolated network installs TFE via periodically delivered air-gap bundles (physically transferred or via a controlled one-way data diode), with license renewal handled the same offline way rather than any live check-in to HashiCorp.

**Common errors:** Assuming air-gapped TFE behaves identically to connected TFE for every feature — some integrations that assume outbound connectivity (e.g., certain VCS webhook flows, if the VCS provider itself is also external) need additional network design or aren't usable at all in a fully isolated deployment.

## 6. Production Usage Notes

- **High availability requires deliberate architecture**, not a checkbox — TFE HA typically means multiple application nodes behind a load balancer, a highly available PostgreSQL instance, and redundant object storage, all of which the operating organization designs and maintains.
- **Upgrade cadence becomes the organization's responsibility.** TFC is always on the latest version invisibly; TFE releases versioned updates the organization must plan, test, and apply on its own schedule — falling behind on TFE upgrades is a real, self-inflicted risk that doesn't exist for TFC customers.
- **Agent-based execution is often even more central in TFE deployments than in TFC**, since TFE is frequently deployed specifically to serve workloads in network segments the TFE application server itself can't directly reach, making agents the standard pattern for run execution against deeply internal infrastructure.

## 7. Security Considerations

- Self-hosting TFE means the organization now owns the full security posture of the application itself — patching, hardening the underlying hosts/containers, and securing the PostgreSQL/object-storage backends — responsibilities that are entirely HashiCorp's problem on SaaS TFC.
- TFE's internal secrets (encryption passwords, database credentials, the internal Vault instance TFE uses for its own credential storage) are now the organization's own key-custody problem, with the same rigor required as any other self-hosted secrets-bearing system.
- Air-gapped deployments trade internet-exposure risk for a harder operational reality: security patches and version updates arrive on a manual, often delayed cadence via offline bundles, which needs its own compensating controls (network segmentation, strict change control) since automatic patching isn't available.

## 8. Common Troubleshooting Scenarios

| Symptom                                              | Likely Cause                                                                                                              | Resolution Path                                                                                                                                   |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| TFE application fails health checks after deployment | Misconfigured database or object-storage connectivity, or missing/invalid license                                         | Check TFE application logs for the specific backing-service connection failure; verify license validity and encryption password                   |
| Runs queue but never execute                         | Run execution capacity (application nodes or configured agents) is insufficient, or an agent pool has no available agents | Scale application nodes or agent pool; check agent connectivity/heartbeat status                                                                  |
| Upgrade to a new TFE version fails or corrupts data  | Skipped required intermediate upgrade steps, or database backup wasn't taken before attempting the upgrade                | Always follow the documented upgrade path (some versions require sequential intermediate upgrades) and take a verified backup before any upgrade  |
| Air-gapped instance reports license/update errors    | Attempting an online-mode operation against an air-gapped install, or an expired offline license bundle                   | Confirm the instance is correctly configured for air-gapped mode; renew and reapply the offline license bundle through the proper offline process |

## 9. Best Practices

- Size and test the PostgreSQL and object-storage backing services for realistic run-history and state-version growth before going into production, not after performance degrades.
- Establish a tested, repeatable backup/restore process for TFE's database and object storage before relying on the platform for production workspaces — this is now the organization's own disaster-recovery responsibility.
- Treat TFE upgrades like any other critical infrastructure upgrade: staged in a non-production instance first, with a rollback plan, rather than applied directly to the production instance.

## 10. Common Anti-Patterns / Mistakes

- **Choosing TFE "just in case" without an actual compliance/data-residency requirement driving it.** This takes on real, ongoing operational burden (hosting, patching, HA, backups) for a benefit the organization doesn't actually need — TFC should be the default unless a concrete requirement says otherwise.
- **Under-resourcing the platform team responsible for operating TFE.** Self-hosting a stateful, production-critical application without dedicated ownership leads to deferred upgrades, unpracticed backups, and eventual incidents.
- **Assuming air-gapped mode is a simple checkbox with no workflow implications.** VCS integrations, notification webhooks, and any feature assuming outbound connectivity need explicit redesign in a fully isolated network, not just a configuration flag.

## 11. Interview Questions

**🎯 Beginner:** _"What is Terraform Enterprise, and how is it different from Terraform Cloud?"_
**Model answer:** Terraform Enterprise is the same core product as Terraform Cloud — organizations, workspaces, runs, policy-as-code, private registries — but self-hosted on the organization's own infrastructure instead of run as a SaaS product by HashiCorp. The feature set is intentionally close to identical; the difference is who operates it and where it runs.
_What the interviewer is probing for:_ Correct understanding that this is a deployment-model difference, not a feature-set difference.

**🎯 Intermediate:** _"What operational responsibilities does an organization take on by choosing Terraform Enterprise over Terraform Cloud?"_
**Model answer:** Installation and initial setup, ongoing version upgrades, backing service management (PostgreSQL, object storage), TLS certificate management, backup and disaster recovery, high-availability architecture if needed, and general application security hardening and patching — all of which are invisible, HashiCorp-managed concerns under SaaS Terraform Cloud but become the organization's own platform-team responsibility under Terraform Enterprise.
_What the interviewer is probing for:_ Whether the candidate understands TFE as a real operational commitment, not just a checkbox toggle.

**🎯 Senior:** _"A team wants to move from Terraform Cloud to Terraform Enterprise purely because 'it feels more secure to host it ourselves.' How would you push back or validate that reasoning?"_
**Model answer:** Push back by separating the actual driver from the vague intuition: "more secure" needs to be grounded in a specific requirement — data residency regulation, contractual prohibition on third-party processing of infrastructure state, or genuine air-gap need — because self-hosting doesn't automatically mean more secure; it means the organization now owns patching, hardening, and incident response for the TFE application itself, which for a team without a dedicated platform security practice can easily be _less_ secure than HashiCorp's dedicated, continuously hardened SaaS operation. If there's a genuine compliance driver, TFE is clearly justified and the operational cost is simply the price of meeting that requirement. If the reasoning really is just a vague feeling, TFC with well-configured access controls, least-privilege credentials ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), and policy-as-code ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) likely delivers equal or better real-world security with far less operational burden.
_What the interviewer is probing for:_ Ability to distinguish a legitimate compliance-driven decision from security theater, and to push back constructively on a stated but under-examined preference.

**🎯 Architect:** _"Design the network architecture for a Terraform Enterprise deployment that needs to manage infrastructure across three network segments, one of which is fully air-gapped with no route to the TFE application server."_
**Model answer:** Deploy TFE itself in the most centrally reachable segment (or its own dedicated management segment) with HA across multiple nodes, backed by an HA PostgreSQL cluster and redundant object storage. For the two segments TFE can reach directly, use standard remote execution or agent pools as needed based on firewall posture. For the fully air-gapped segment, deploy a Terraform Cloud/Enterprise **Agent** inside that segment — agents only need outbound connectivity back to the TFE application (a single, tightly controlled egress path) rather than the TFE application needing inbound access into the air-gapped segment, which inverts the connectivity requirement to match how tightly isolated networks are normally designed (deny-inbound, tightly-controlled outbound). If the air-gapped segment can't make even that single outbound call, this pattern hits a hard limit — at that point, a fully separate, physically isolated TFE instance dedicated to that segment (with its own offline license/update process) may be the only option, accepting the operational cost of a second, wholly independent instance rather than trying to force one instance to bridge an unbridgeable network boundary.
_What the interviewer is probing for:_ Real understanding of agent-based execution as the standard pattern for reaching isolated networks, plus recognizing when even that pattern hits a hard architectural limit.

## 12. Common Misconceptions

1. **"Terraform Enterprise has fewer or more limited features than Terraform Cloud."** Core capabilities (Sentinel, private registries, run triggers, policy-as-code) are intentionally kept at close feature parity — the difference is deployment and operational model, not capability.
2. **"Self-hosting is automatically more secure."** It shifts security responsibility to the operating organization; whether that results in better or worse security depends entirely on that organization's own operational maturity.
3. **"TFE upgrades work like TFC's invisible, always-current model."** TFE upgrades are versioned releases the organization must plan and apply on its own schedule — falling behind is a real, self-inflicted risk.
4. **"Air-gapped mode is just a configuration flag with no other implications."** It changes the operational model for licensing, updates, and any integration assuming outbound internet connectivity — a meaningfully different day-to-day operating reality.

## 13. 🔑 Key Takeaways

- Terraform Enterprise is the self-hosted distribution of Terraform Cloud, with close feature parity — the real distinction is deployment model and operational ownership, not capability.
- Choosing TFE should be driven by a concrete data-residency, compliance, or air-gap requirement, not a vague security intuition, given the real operational burden it introduces.
- Self-hosting means the organization owns installation, upgrades, backing-service management, HA, and backup/restore — all invisible under SaaS TFC.
- Agent-based execution is the standard way to reach network segments the TFE application server itself can't directly access, including air-gapped segments (via controlled outbound-only connectivity).
- Air-gapped TFE supports fully offline license and update handling, but this changes the operational cadence for patching and upgrades meaningfully compared to a connected deployment.

## 14. Related Concepts & What's Next

[§90](./Section-90-Part12-Cost-Estimation-Features.md) returns to a feature shared by both TFC and TFE: cost estimation within the run pipeline. [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) covers least-privilege execution roles relevant to both SaaS and self-hosted deployments. [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) revisits performance-at-scale considerations relevant to sizing a self-hosted TFE deployment's backing services.

**Next Section:** [§90](./Section-90-Part12-Cost-Estimation-Features.md) — `Section-90-Part12-Cost-Estimation-Features.md`
