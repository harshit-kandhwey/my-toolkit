# Part 1 · Section 5 — Ways to Interact with AWS

> AWS Zero-to-Enterprise Knowledge Base · Part 1: Foundations & Global Infrastructure

---

## 1. Definition

**Plain-language:** AWS gives several doors into the same house — click around a website (Console), type commands (CLI), write code that talks to AWS directly (SDK), use a browser-based terminal with nothing to install (CloudShell), or call the raw API underneath all of them. Infrastructure as Code describes infrastructure as text files that build it for you.

**Precise:** Every interaction method is a client calling the same underlying **AWS API** — RESTful HTTPS endpoints, one set per service per Region. Console, CLI, SDKs, CloudShell are different interfaces over an **identical API surface**.

> 🔑 There is exactly **one API underneath everything**. Interface choice is about convenience, auditability, automation — not capability. "Console things" and "CLI things" are not separate categories.

---

## 2. Why Multiple Interfaces Exist

- Different tasks need different interfaces: exploring benefits from a visual Console; repeating deployments benefits from scriptable CLI/SDK.
- **Humans vs machines:** Console = human judgment; CLI/SDK/API = repeatable, automatable, machine-driven work (dominant at enterprise scale).
- **Zero-install barrier:** CloudShell removes the "can't install anything" problem entirely.

---

## 3. AWS Management Console

- **What:** web GUI at `console.aws.amazon.com`; click through dashboards/forms/wizards.
- **Best for:** learning, one-off exploration, visual monitoring, seeing resource relationships.
- **Not ideal for:** repeatable/scriptable/high-volume tasks — hard to version-control or code-review.
- **Login:** root (email+password, rare/root-only tasks) or IAM/federated identity (direct sign-in URL or IAM Identity Center SSO).
- **Structure:** top nav (Region selector, search, account menu), services menu, per-service dashboards (resource list, Create button, detail tabs).
- **Enterprise use:** exploration and incident investigation; discouraged for repeatable provisioning (causes configuration drift — Part 9 IaC exists to prevent this).
- **Security:** always use MFA; Console and CLI/API use **different underlying credentials**.

> ⚠️ Manual, undocumented production Console changes "just this once" are a leading cause of configuration drift.

---

## 4. AWS CLI

- **What:** unified command-line tool: `aws <service> <action> [options]`.
- **Why:** enables repeatable operations, shell scripting, CI/CD integration (Part 9).
- **Install:** CLI **v2** is current/recommended (v1 legacy). Verify install steps against official docs (they change).
- **Verify:** `aws --version` → `aws-cli/2.x.x Python/3.x.x ...`

### Configuration

- `aws configure` prompts for: **Access Key ID**, **Secret Access Key** (never root), **default Region**, **default output format** (json/text/table/yaml).
- Stored in `~/.aws/credentials` (secrets) and `~/.aws/config` (Region, format, **named profiles**).
- Named profiles: `aws configure --profile dev-account`; `aws s3 ls --profile dev-account`.
- **Modern best practice:** avoid long-lived keys — use `aws sso login` (IAM Identity Center) or assumed roles with short-lived, auto-rotated credentials.

### Command: `aws s3 ls`

- **Purpose:** confirm credentials work; list S3 buckets — a common first sanity check.
- **Syntax:** `aws s3 ls`
- **Common options:** `--profile <name>`, `--region <region>`, `--output json|table|text`, `--query '<JMESPath>'`.
- **Example:**
  ```
  aws s3 ls
  2024-11-02 14:21:03 my-app-logs-bucket
  2025-01-15 09:03:41 my-website-assets
  ```
- **Production use:** `aws s3 sync ./build s3://my-website-assets --delete` in a CI/CD pipeline (full S3 detail Part 5).
- **Exit codes:** `0` success; non-zero failure (commonly `1` generic error, `2` CLI usage/parse error) — scripts should check.
- **Common errors:** `Unable to locate credentials` (never configured / wrong profile); `AccessDenied` (IAM policy, Part 2); `Could not connect to the endpoint URL` (wrong Region / network).
- **Security impact:** runs with configured credentials' permissions — broad CLI permissions = broad risk.
- **Performance:** large accounts may paginate results; CLI auto-paginates by default.
- **Troubleshooting:** `--debug` shows the full HTTP request/response.

### Enterprise Usage

- Backbone of shell automation and CI/CD steps; wrapped in standardized scripts/Makefiles for consistency.

---

## 5. AWS SDKs

- **What:** language-specific libraries letting app code call AWS natively (objects/functions) instead of shelling out to CLI.
- **Why:** apps need to talk to AWS from within running code (e.g., upload to S3, read from SQS) without spawning fragile CLI subprocesses.
- **Available:** Python (Boto3), JavaScript/TypeScript, Java, .NET/C#, Go, Ruby, PHP, others — each idiomatic, same underlying API.

### Example (Boto3)

```python
import boto3
s3 = boto3.client('s3', region_name='us-east-1')
response = s3.list_buckets()
for bucket in response['Buckets']:
    print(bucket['Name'])
```

- `list_buckets()` = same underlying API action as `aws s3 ls`.
- **Credential resolution order:** env vars → `~/.aws/credentials` → attached IAM role (EC2/Lambda) → explicit in-code credentials (discouraged — never hardcode secrets).
- **Common error:** `NoCredentialsError` — same root cause as CLI's missing-credentials error.

### Enterprise Usage

- Dominant method for application-level AWS integration (web backend ↔ DynamoDB, Lambda ↔ SQS, pipeline ↔ S3).
- **Best practice:** compute resources (EC2/Lambda/ECS) use attached **IAM roles**; never embed long-lived keys in app code/config.

---

## 6. AWS CloudShell

- **What:** browser-based terminal inside the Console, pre-authenticated, pre-installed with AWS CLI and common tools — no local install.
- **Why:** removes install barriers and credential-configuration friction; inherits Console session permissions.
- **Characteristics:** ~1 GB persistent storage per identity/Region; CLI pre-configured plus editor, Python, etc.
- **Best for:** quick one-off CLI tasks, troubleshooting from unfamiliar machines.
- **Not ideal for:** heavy/long-running automation — it's a convenience shell, not general compute.

---

## 7. The AWS API — The Foundation

- **What:** RESTful HTTPS endpoints every service exposes; every Console click/CLI command/SDK call becomes signed HTTPS requests to these.
- **SigV4 signing:** every request is cryptographically signed with **AWS Signature Version 4**, proving authenticity without transmitting the secret key. CLI/SDKs handle this automatically.
- **Why it matters:** explains why Console vs CLI/API use different credential types (session cookie vs signed keys); explains why third-party tools (Terraform) can fully manage AWS — they're just another API client. Confirms: one API, many doors.

---

## 8. Infrastructure as Code (IaC) — Preview

- **What:** describing desired AWS resources in text files/code that a tool reads to create/update/delete real resources.
- **Why:** Console/ad-hoc CLI don't scale to enterprise complexity and cause configuration drift. IaC files are version-controlled, code-reviewed, tested, and repeatable across dev/staging/prod.
- **Main tools (full depth Part 9):**
  - **CloudFormation** — AWS-native; YAML/JSON templates → managed "stack."
  - **CDK** — write infra in a real language (TypeScript, Python, Java); compiles to CloudFormation.
  - **Terraform** — HashiCorp, multi-cloud; talks to AWS via the same API using HCL config.

> 🔑 IaC tools are not a "fifth interface" bypassing AWS rules — they're automated API clients, just like the CLI, computing which API calls to make from a declarative desired-state description.

---

## 9. Comparison Matrix

| Interface               | Best for                                         | Not ideal for                                    | Credential type                  | Repeatable?      |
| ----------------------- | ------------------------------------------------ | ------------------------------------------------ | -------------------------------- | ---------------- |
| Console                 | Learning, exploration, monitoring, investigation | High-volume/repeated tasks, auditable automation | Password + MFA (session)         | No — manual      |
| CLI                     | Scripting, quick ops, CI/CD steps                | Complex application logic                        | Access keys / SSO / assumed role | Yes, via scripts |
| SDK                     | Application code integration                     | One-off human tasks                              | Same as CLI, in-code             | Yes, part of app |
| CloudShell              | Zero-install quick tasks, unfamiliar machines    | Heavy/long-running automation                    | Inherited Console session        | Somewhat         |
| Direct API/HTTPS        | Building own tooling                             | Everyday human use                               | Manually signed (SigV4)          | Yes              |
| IaC (CFN/CDK/Terraform) | Enterprise version-controlled infra              | Quick one-off exploration                        | Same as CLI/SDK, tool-used       | Yes — the point  |

---

## 10. Production & Enterprise Usage Summary

- **Small/learning:** Console for exploration, CLI for quick tasks.
- **Growing teams:** CLI/SDK dominate; Console for monitoring/investigation; early IaC adoption.
- **Mature enterprises:** IaC is primary; Console often **read-only** in production; CLI/SDK access scoped via IAM roles, not long-lived keys.

---

## 11. Security Considerations Summary

- Never hardcode access keys in scripts/code/version control.
- Prefer temporary credentials: IAM roles (compute), IAM Identity Center/SSO (humans), assumed roles (cross-account).
- MFA on Console access, always.
- **CloudTrail logs every API call** regardless of interface — unified audit trail.

---

## 12. Troubleshooting

| Symptom                               | Cause                                     | Fix                                                          |
| ------------------------------------- | ----------------------------------------- | ------------------------------------------------------------ |
| `Unable to locate credentials` (CLI)  | `aws configure` never run / wrong profile | Run `aws configure` or specify `--profile`                   |
| `NoCredentialsError` (SDK)            | No credentials in resolution chain        | Set env vars, configure credentials file, or attach IAM role |
| `AccessDenied` any interface          | IAM policy doesn't permit action          | Review/adjust IAM policy (Part 2)                            |
| Console shows different data than CLI | Mismatched Region                         | Confirm Region matches in both                               |
| CLI works locally, fails in CI/CD     | CI lacks same credentials/profile         | Configure CI-specific (ideally assumed role) credentials     |

---

## 13. Best Practices & Anti-Patterns

**Best practices:** Console for learning/investigation only; move to CLI/SDK once a task repeats; adopt IaC early for real infrastructure; use temporary/federated credentials; use CloudShell for quick no-install tasks.

**Anti-patterns:** manual production Console changes "just this once"; hardcoding/committing access keys; assuming CLI/Console differ in capability; heavy automation inside CloudShell.

---

## 14. Common Misconceptions

- "CLI can do more than the Console (or vice versa)." → False — same API; gaps are UI lag, not fundamental limits.
- "CloudShell has no real AWS access." → False — fully authenticated with your actual permissions.
- "IaC tools are a special-access path." → False — ordinary API clients, same IAM/CloudTrail.
- "SDK calls don't need credentials." → False — signed API requests like any other.

---

## 15. Interview Questions (with model answers)

**🟢 Main ways to interact with AWS?** Console (visual GUI), CLI (terminal scripting), SDKs (app code integration), CloudShell (zero-install browser terminal), the underlying REST API, and IaC tools (CloudFormation/Terraform) as API clients managing resources declaratively.

**🟡 Why restrict Console access in production if it calls the same API?** Not capability — manual changes aren't version-controlled/reviewable/repeatable and cause configuration drift vs. IaC's source of truth. Read-only Console forces real changes through IaC + CI/CD — a process control.

**🟡 How should an EC2 app authenticate to S3 via SDK?** Use an attached IAM role, not hardcoded keys. SDK credential chain auto-picks up temporary, auto-rotated role credentials from instance metadata — avoids embedded secrets; compromise exposure is short-lived.

**🔴 What happens under the hood running a CLI command?** CLI parses command → builds HTTPS request to the service's regional endpoint → signs with SigV4 using resolved credentials (profile/env/SSO/assumed role) → AWS validates signature + IAM permissions → executes → returns response CLI formats as json/table/text. Same path as SDK calls or Terraform — CLI is a thin general-purpose client over the one API.

**🔴 Structure interface access/credentials for a large org?** Humans via IAM Identity Center federated to corporate IdP, no standalone long-lived IAM user keys; CLI/Console use short-lived SSO creds. App workloads use attached IAM roles. All infra changes via IaC executed by CI/CD with scoped temporary-role credentials. Production Console mostly read-only; break-glass access logged/time-limited. CloudTrail captures every call across every interface for one complete audit trail.

---

## 🔑 Key Takeaways

1. Exactly one AWS API underneath every interface — Console, CLI, SDK, CloudShell, IaC are all SigV4-signed REST clients; capability doesn't differ, convenience/fit does.
2. Console = learning/exploration/investigation; CLI/SDK = repeatable/scriptable/app-integrated; CloudShell = zero-install convenience; IaC = enterprise standard for real changes.
3. Credentials differ by path: Console = password+MFA session; CLI/SDK/API = access keys or (preferably) temporary role/SSO — never hardcode long-lived keys.
4. Manual production Console changes cause configuration drift — mature orgs restrict to read-only and route changes through IaC + CI/CD.
5. CloudTrail logs every API call regardless of origin interface — a single unified audit trail.

## 🌐 Related Concepts (forward links)

- IAM roles, policies, IAM Identity Center → Part 2
- CloudFormation, CDK, Terraform in depth → Part 9
- CloudTrail → Part 8
