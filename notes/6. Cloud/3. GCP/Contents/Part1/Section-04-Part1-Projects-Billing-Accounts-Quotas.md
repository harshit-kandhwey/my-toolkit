# Section 4 (Part 1): Projects, Billing Accounts & Quotas

## 4.1 Definition

**Plain language:** A GCP **Project** is the container that everything you build actually lives inside — think of it as the equivalent of a single "account" in other systems. Every resource belongs to exactly one Project, every Project is linked to exactly one Billing Account so Google knows who to charge, and every Project has its own set of **Quotas** — hard caps on how much of a given resource you can consume — that protect both Google's infrastructure and you from runaway costs.

**Precise:** A **Project** is the base unit of resource ownership, API enablement, and quota allocation in GCP, identified by a unique Project ID, a numeric Project Number, and a human-readable Project Name. A **Billing Account** is a separate object representing a payment method and billing responsibility, linked to one or more Projects to determine who is charged for that Project's resource consumption. **Quotas** are per-Project (and often per-region) limits on resource consumption, enforced independently of billing, that can be viewed and, within limits, increased via a request process.

## 4.2 Why It Exists / Problem It Solves

Without a well-defined base unit, there would be no natural boundary for cost attribution, no natural boundary for API enablement (which services are turned on), and no natural boundary for blast radius when something goes wrong (a leaked credential, a misconfigured script). The Project solves all three simultaneously:

- **Cost attribution:** Every dollar spent is traceable to a specific Project, which is linked to a specific Billing Account — critical for chargeback/showback in multi-team organizations.
- **API enablement boundary:** Enabling the BigQuery API in one Project doesn't expose BigQuery to a completely unrelated Project; each Project's enabled-API surface is independent.
- **Blast-radius containment:** If a Project's service account key is leaked, the damage is scoped to that Project's IAM grants and quotas, not the entire company — this is why enterprises are pushed toward many small, purpose-scoped Projects rather than one giant Project holding everything (explored further in Section 59).

**Quotas** exist as a distinct, separate safety mechanism from billing: even with an unlimited-spend billing account, Google enforces hard ceilings on things like the number of CPUs you can spin up in a region, to (a) protect the shared physical infrastructure from any single customer over-consuming capacity unexpectedly, and (b) give customers themselves a safety net against runaway automated scripts or programming errors that could otherwise generate a catastrophic bill before anyone notices.

## 4.3 Project Identity: ID, Number, and Name

| Identifier         | Description                                                                                                                                   | Mutable?                      |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **Project ID**     | Globally unique, human-chosen string (e.g., `payments-prod-01`), used in most `gcloud` commands and referenced in resource URLs/APIs.         | No — permanent once chosen    |
| **Project Number** | Globally unique numeric identifier auto-assigned by Google at creation (e.g., `123456789012`), used internally by some APIs and IAM bindings. | No — permanent, auto-assigned |
| **Project Name**   | A display label, not required to be unique, purely cosmetic for the console UI.                                                               | Yes — can be renamed anytime  |

> ⚠️ **Interview-relevant nuance:** A deleted Project's ID cannot be reused by anyone, ever, even by the same organization — this trips up teams that try to delete and immediately recreate a project with the identical ID expecting a clean slate.

## 4.4 Billing Accounts

A **Billing Account** holds a payment method (credit card, invoiced terms) and is a separate resource from any Project. A single Billing Account can be linked to many Projects (the common enterprise pattern — one central Billing Account for the whole company, linked to hundreds of Projects), and a Project can only ever be linked to one Billing Account at a time.

- **Billing Account roles** (IAM, Section 35) control who can _link/unlink_ a Project to a Billing Account and who can _view/manage_ billing data, separately from who has IAM permissions on the Projects themselves — a deliberate separation of duties so that, for example, a finance team can manage Billing Accounts without needing any access to the Projects' actual resources.
- **Sub-accounts and billing export:** Enterprises typically export detailed billing data to BigQuery (a "billing export," covered further in Section 57 — Cost Optimization & FinOps) for granular cost analysis beyond what the console's built-in reports provide.

### 4.4.1 Budgets and Budget Alerts

A **Budget** is a configured spending threshold attached to a Billing Account (optionally scoped to specific Projects or labels) that triggers **alerts** via email or Pub/Sub notifications when actual or forecasted spend crosses defined percentage thresholds (e.g., 50%, 90%, 100% of budget). Budgets are purely observational by default — crossing a budget threshold sends a notification but does **not** automatically stop spending or disable resources, unless the organization builds custom automation (e.g., a Cloud Function triggered by the Pub/Sub notification that disables billing on the Project) on top of the alert.

> ⚠️ **Common misconfiguration:** Teams sometimes assume a Budget alert will "cap" spending automatically. It will not, out of the box — it is a notification mechanism only. Actual spend-capping requires custom automation layered on top, or hard quota limits (Section 4.5) which are a genuinely separate mechanism.

## 4.5 Quotas

**Quotas** are consumption ceilings enforced independently of billing, at multiple possible scopes:

- **Per-project quotas:** e.g., a limit on the total number of Cloud Storage buckets a Project may create.
- **Per-region quotas:** e.g., a limit on the number of CPUs (`CPUS` quota) a Project may run simultaneously within `us-central1` — a different, independent ceiling applies per region, since capacity is a regional/zonal physical constraint.
- **Rate quotas vs. allocation quotas:** Some quotas limit a rate (e.g., API requests per minute), while others limit a standing allocation (e.g., total number of VM instances running at once) — these are conceptually different and both matter when capacity planning.

### 4.5.1 Requesting a Quota Increase

Default quotas are deliberately conservative for new Projects (again, partly as a fraud/runaway-cost safety net). Production workloads routinely need increases, requested via the console's IAM & Admin → Quotas page or programmatically, with Google's automated systems approving many routine increases near-instantly and larger requests requiring manual review.

## 4.6 Hands-On Examples

**Purpose:** Create a new Project (specifying a unique Project ID).

```bash
gcloud projects create payments-prod-02 \
  --name="Payments Prod 02" \
  --organization=123456789012
```

**Expected output:**

```
Create in progress for [https://cloudresourcemanager.googleapis.com/v1/projects/payments-prod-02].
Waiting for [operations/cp.987654321] to finish...done.
```

**Purpose:** List available Billing Accounts and link one to the new Project.

```bash
gcloud billing accounts list
gcloud billing projects link payments-prod-02 \
  --billing-account=012345-6789AB-CDEF01
```

**Expected output:**

```
ACCOUNT_ID            NAME                  OPEN
012345-6789AB-CDEF01  Corporate Billing     True

billingAccountName: billingAccounts/012345-6789AB-CDEF01
billingEnabled: true
name: projects/payments-prod-02/billingInfo
projectId: payments-prod-02
```

**Purpose:** Check the current CPU quota for a specific region — the exact command run before requesting a capacity increase for a large VM rollout.

```bash
gcloud compute regions describe us-central1 \
  --format="table(quotas.metric, quotas.limit, quotas.usage)" \
  --flatten="quotas[]" \
  --filter="quotas.metric=CPUS"
```

**Expected output:**

```
METRIC  LIMIT  USAGE
CPUS    24.0   6.0
```

> 💡 **Tip:** A brand-new Project's default CPU quota per region (commonly 24 or lower for new billing accounts) is frequently the very first blocker a team hits when trying to launch more than a handful of VMs — always check quota before diagnosing "why won't my Managed Instance Group scale up" as an application bug.

## 4.7 Production & Enterprise Usage

- **Project-per-workload/environment convention:** Enterprises typically avoid a single monolithic Project, instead creating separate Projects per application and per environment (e.g., `payments-prod-01`, `payments-staging-01`, `payments-dev-01`), each independently billed, quota-tracked, and IAM-scoped — this containment strategy is central to the landing zone patterns in Section 59.
- **Centralized Billing Account, decentralized Projects:** A single Billing Account is commonly linked to every Project company-wide, with cost allocation done via Project-level labels and BigQuery billing export analysis (Section 57), rather than creating one Billing Account per team.
- **Proactive quota management:** Mature organizations request quota increases ahead of planned scale-up events (e.g., a Black-Friday-style traffic spike) rather than reactively, since large quota increases can take longer to approve than a last-minute request allows for.

## 4.8 Common Misconceptions

- **Misconception:** "Project ID and Project Name are the same thing, and I can change either freely." The Project ID is permanent once set; only the Project Name is a freely editable display label.
- **Misconception:** "A Budget alert stops spending automatically." It does not — budgets are notification-only unless custom automation is built on top of the Pub/Sub notification.
- **Misconception:** "Quota increases are guaranteed if you're willing to pay more." Quotas are a capacity/safety mechanism, not purely a monetization lever — some increases (especially for scarce hardware like GPUs) can be denied or delayed regardless of willingness to pay, based on actual regional capacity availability.

## 4.9 Interview Questions

**🎯 Beginner:** _What's the difference between a Project ID and a Project Number?_
**Model answer:** The Project ID is a globally unique, human-chosen string (e.g., `payments-prod-01`) used in most `gcloud` commands and URLs, and it's permanent once chosen — it can never be reused, even after deletion. The Project Number is a globally unique numeric identifier automatically assigned by Google, also permanent, used internally by some APIs and IAM bindings. Neither should be confused with the Project Name, which is just a cosmetic, freely-editable display label.

**🎯 Intermediate:** _A team's Budget alert fired at 100% of their monthly threshold, but their bill kept growing afterward. Why, and what would you do differently?_
**Model answer:** Budget alerts are notification-only by default — crossing a threshold sends an email or Pub/Sub message but does not stop resource consumption or disable billing automatically. To actually cap spend, the team would need custom automation subscribed to the budget's Pub/Sub notification (e.g., a Cloud Function that disables billing on the Project or scales down resources when a critical threshold is hit), or rely on hard quota ceilings as an independent backstop, since quotas are enforced regardless of billing configuration.

**🎯 Senior/Architect:** _You're designing the Project structure for a company with 30 application teams, each needing dev/staging/prod environments, with a finance requirement for clean per-team cost attribution and a security requirement that no team's workload can accidentally exhaust another team's regional compute capacity. How do you structure Projects, Billing, and quotas?_
**Model answer:** I'd create one Project per application per environment (90 Projects total for 30 teams × 3 environments), all linked to a single centralized Billing Account for consolidated invoicing, with consistent labeling (team, environment, cost-center) on every Project so BigQuery billing export (Section 57) can produce clean per-team cost attribution without needing separate Billing Accounts. Because quotas are enforced per-Project and per-region independently, one team's Project exhausting its own CPU quota in a region has no effect on another team's Project's quota in that same region — this containment is automatic given separate Projects, so I wouldn't need any additional mechanism beyond the Project-per-workload structure itself. I'd also set team-appropriate default quotas proactively and set Budget alerts per Project (or per label group) at 50/90/100% thresholds, routed to both the team and a central FinOps function, with the 100% threshold on production Projects wired to an automated Pub/Sub-triggered alert to on-call rather than relying on passive email review.

## 4.10 Key Takeaways

- 🔑 A Project has three identifiers — ID (permanent, human-chosen), Number (permanent, auto-assigned), Name (mutable, cosmetic) — and every resource belongs to exactly one Project.
- 🔑 A Billing Account is a separate resource from a Project; one Billing Account commonly links to many Projects, but each Project links to only one Billing Account at a time.
- 🔑 Budgets and budget alerts are notification-only by default — they do not automatically stop spending without custom automation.
- 🔑 Quotas are a distinct safety/capacity mechanism from billing, enforced per-project and often per-region, and default quotas are deliberately conservative for new Projects.
- 🔑 Enterprise practice favors many small, purpose-scoped Projects (per app, per environment) over one monolithic Project, for cleaner cost attribution, quota isolation, and blast-radius containment.

## 4.11 Related Concepts

Resource hierarchy (Section 3), the compute services that consume project quotas (Sections 5–9), Organization Policies (Section 37), BigQuery billing export and FinOps practices (Section 57), and landing zone/project-vending automation (Sections 59 and 63) all build directly on the Project/Billing/Quota model introduced here.
