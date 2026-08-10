# Section 75 (Part 11): AWS Provider Deep Dive: VPC, EC2, S3, IAM Provisioning Patterns

## 1. Definition

**Plain language:** The AWS provider (`hashicorp/aws`) is the plugin that translates HCL resource blocks like `aws_vpc` or `aws_instance` into calls against the AWS API. Provisioning AWS infrastructure with Terraform means learning the shape of a small set of frequently used resource types — networking, compute, storage, identity — well enough to compose them correctly and predict what a `plan` will show before running it.

**Precise definition:** The **AWS provider** exposes AWS's service APIs as Terraform resource and data source schemas. Each resource type (`aws_vpc`, `aws_subnet`, `aws_instance`, `aws_s3_bucket`, `aws_iam_role`, and hundreds more) maps to one or more underlying AWS API calls, with the provider handling create/read/update/delete (CRUD) translation, eventual-consistency retries, and attribute diffing. Provisioning a working environment means composing resources across four foundational domains — networking (VPC), compute (EC2), storage (S3), and identity (IAM) — using implicit references (`aws_subnet.public.id`) so Terraform's dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) orders API calls correctly without the author specifying order manually.

> 💡 **Tip:** AWS resource arguments split into two categories that behave very differently on change: some are **in-place updatable** (a security group's `ingress` rules, an S3 bucket's tags) and some **force replacement** (an EC2 instance's `availability_zone`, an RDS instance's `engine`). `terraform plan` always tells you which is which — a `~` means update in place, a `-/+` means destroy-and-recreate — but knowing this in advance from the provider docs prevents surprise outages from an innocuous-looking config change.

## 2. Why This Matters

- **AWS is the most common Terraform target in production**, and the `aws` provider is consistently the most-downloaded provider on the Terraform Registry — fluency here transfers directly to real job requirements and to the Terraform Associate exam's AWS-heavy example set.
- **VPC, EC2, S3, and IAM are the load-bearing four.** Almost every non-trivial AWS Terraform codebase touches all four in its first hundred lines — a networking boundary, compute inside it, a storage bucket for state or artifacts, and an identity to run as.
- **Getting the resource graph right here prevents entire classes of `apply` failures** — e.g., an EC2 instance referencing a subnet that doesn't exist yet, or an IAM role with a policy attached before the role itself finishes creating.
- **AWS's eventual consistency and asynchronous resource creation** (IAM role propagation delay is the classic example) surface real bugs that a purely conceptual understanding of Terraform doesn't prepare you for.

## 3. Prerequisites and Dependencies

This section assumes the provider mechanics from Part 2 (provider configuration in [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md), authentication patterns in [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)) and the HCL fundamentals from Part 3 (resource blocks and addressing in [§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md), `for_each` in [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)). It does not re-explain what a VPC or IAM role _is_ conceptually — see `../../../6. Cloud/1. AWS/` for that — this section is scoped strictly to how Terraform's `aws` provider models and provisions these services.

## 4. Architecture / Conceptual Diagram

```text
                        aws_vpc.main (10.0.0.0/16)
                                 │
                ┌────────────────┴─────────────────┐
                │                                  │
      aws_subnet.public                  aws_subnet.private
      (10.0.1.0/24, AZ-a)                 (10.0.2.0/24, AZ-a)
                │                                  │
      aws_internet_gateway.igw           aws_nat_gateway.nat
      aws_route_table.public             aws_route_table.private
                │                                  │
      aws_instance.web ──────┐           aws_instance.app
      (public subnet)        │           (private subnet)
                │            │                     │
      aws_security_group.web │           aws_security_group.app
                             │
                    aws_iam_instance_profile
                             │
                    aws_iam_role.ec2_role
                    (trust policy: ec2.amazonaws.com)
                             │
                    aws_iam_role_policy_attachment
                             │
                    aws_iam_policy (least privilege)

      aws_s3_bucket.artifacts  ← referenced by aws_iam_policy
      (accessed via the instance role, not embedded credentials)
```

- Networking (`aws_vpc` → `aws_subnet` → `aws_route_table`) forms the base layer everything else attaches to.
- Compute (`aws_instance`) references a subnet ID and a security group ID — both implicit dependencies Terraform resolves automatically.
- Identity (`aws_iam_role` + `aws_iam_instance_profile`) is attached to the instance so it can call other AWS APIs (like reading from the S3 bucket) without embedded credentials — this is the standard production pattern, covered further in [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md).

## 5. Hands-On

### 5.1 VPC and Subnet Provisioning

**Purpose:** Establish the network boundary and addressable subnets that compute and other resources will live inside.

**Syntax:**

```hcl
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "main-vpc"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block               = "10.0.1.0/24"
  availability_zone        = "us-east-1a"
  map_public_ip_on_launch  = true

  tags = {
    Name = "public-subnet-a"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
Terraform will perform the following actions:
  # aws_vpc.main will be created
  # aws_subnet.public will be created

Plan: 2 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

**Production usage example:** Production VPC modules almost never hardcode CIDR ranges and AZs like this example — they compute subnet CIDRs with `cidrsubnet()` ([§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) across `for_each` over an availability-zone list, so the same module produces 2, 3, or 6 subnets depending on the input variable without duplicating resource blocks.

**Common errors:** Forgetting `map_public_ip_on_launch = true` on a subnet meant to be public is a frequent, silent mistake — the subnet still routes to an internet gateway correctly, but instances launched into it get no public IP and become unreachable, which looks like a security group problem until traced back to the subnet setting.

### 5.2 EC2 Instance Provisioning

**Purpose:** Launch compute inside the subnet, attached to a security group and an IAM instance profile.

**Syntax:**

```hcl
resource "aws_security_group" "web" {
  name   = "web-sg"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web" {
  ami                    = "ami-0abcdef1234567890"
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  tags = {
    Name = "web-instance"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_security_group.web will be created
  # aws_instance.web will be created

Plan: 2 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.

$ terraform apply    # after changing instance_type to t3.small
  # aws_instance.web will be updated in-place
  ~ instance_type = "t3.micro" -> "t3.small"
Plan: 0 to add, 1 to change, 0 to destroy.
```

**Production usage example:** Production configurations pin `ami` via a `data "aws_ami"` lookup with `most_recent = true` and owner/name filters rather than a hardcoded AMI ID, so the configuration doesn't silently rot as AMI IDs are region- and time-specific.

**Common errors:** Changing certain arguments — `availability_zone`, `subnet_id` in some cases, `user_data` when combined with certain lifecycle settings — forces `-/+` replacement rather than an in-place update; seeing an unexpected destroy-and-recreate in `plan` for a "small" change is the most common EC2-provisioning surprise for newcomers.

### 5.3 S3 Bucket Provisioning

**Purpose:** Provision durable object storage with the modern, split-resource S3 configuration style (post-provider v4).

**Syntax:**

```hcl
resource "aws_s3_bucket" "artifacts" {
  bucket = "my-org-build-artifacts"
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_s3_bucket.artifacts will be created
  # aws_s3_bucket_versioning.artifacts will be created
  # aws_s3_bucket_server_side_encryption_configuration.artifacts will be created
  # aws_s3_bucket_public_access_block.artifacts will be created

Plan: 4 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This split-resource pattern (bucket, versioning, encryption, and public-access-block as separate resources sharing the bucket ID) is the required style since provider v4 deprecated the old inline `versioning {}`/`server_side_encryption_configuration {}` blocks on `aws_s3_bucket` itself — modules written against provider v3 syntax fail to plan against v5+ and need this migration.

**Common errors:** `BucketAlreadyExists` on `apply` — S3 bucket names are globally unique across _all_ AWS accounts, not just your own, so a plausible-looking name like `artifacts` is almost always already taken; production naming conventions suffix the bucket name with the account ID or a random string (`random_id`, [§38](../Part5/Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md)) to guarantee uniqueness.

### 5.4 IAM Role and Policy Provisioning

**Purpose:** Grant the EC2 instance permission to read from the S3 bucket without embedding static credentials.

**Syntax:**

```hcl
resource "aws_iam_role" "ec2_role" {
  name = "ec2-s3-read-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "s3_read" {
  name = "s3-artifacts-read"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:GetObject", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.s3_read.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "ec2-s3-read-profile"
  role = aws_iam_role.ec2_role.name
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_iam_role.ec2_role will be created
  # aws_iam_policy.s3_read will be created
  # aws_iam_role_policy_attachment.attach will be created
  # aws_iam_instance_profile.ec2_profile will be created

Plan: 4 to add, 0 to change, 0 to destroy.
```

**Production usage example:** `jsonencode()` over policy documents (rather than raw heredoc JSON strings) is the standard production style since it lets Terraform interpolate resource ARNs directly (`aws_s3_bucket.artifacts.arn`) with correct escaping instead of manual string concatenation — a frequent source of malformed-JSON `apply` failures in older codebases.

**Common errors:** Launching the EC2 instance and immediately calling the S3 API from inside it can fail with `AccessDenied` for the first few seconds — IAM role/policy propagation across AWS's control plane is eventually consistent, not instant; production `user_data` scripts that depend on the instance role typically add a short retry loop rather than assuming immediate availability.

## 6. Production Usage Notes

- Real AWS Terraform codebases wrap these four resource groups into a small number of internal modules (a `vpc` module, a `compute` module, an `iam` module) rather than repeating raw resource blocks per environment — module composition patterns are covered fully in [§61](../Part8/Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md).
- Provider version pinning ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) matters more for `aws` than almost any other provider given how frequently AWS ships new resource arguments and deprecates old ones (the S3 split-resource change in 5.3 above is a direct example).
- Data sources (`data "aws_ami"`, `data "aws_availability_zones"`, `data "aws_caller_identity"`) are used pervasively to avoid hardcoding account- or region-specific values ([§33](../Part5/Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md)).

## 7. Security Considerations

- Never attach an IAM policy directly to an EC2 instance's static credentials — always use an instance profile/role as shown in 5.4, so credentials are short-lived and automatically rotated by AWS's metadata service rather than stored anywhere.
- Default-deny security group egress is rarely used in practice but should be considered for high-sensitivity workloads instead of the permissive `0.0.0.0/0` egress shown in the example above, which was simplified for illustration.
- `aws_s3_bucket_public_access_block` should be applied to every bucket by default, not opt-in per bucket — a missing block is one of the most common causes of accidental public data exposure in real incident postmortems.

## 8. Common Troubleshooting Scenarios

| Symptom                                                         | Likely Cause                                                               | Resolution Path                                                                               |
| --------------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `Error: creating S3 Bucket: BucketAlreadyExists`                | S3 bucket names are globally unique across all AWS accounts                | Add an account ID or `random_id` suffix to the bucket name                                    |
| `AccessDenied` calling AWS APIs immediately after instance boot | IAM role/policy propagation is eventually consistent, not instant          | Add a short retry loop in `user_data`, or delay dependent calls                               |
| `plan` shows unexpected `-/+` destroy-and-recreate on EC2       | Changed argument (e.g. `availability_zone`) forces replacement, not update | Check the resource's provider docs for `ForceNew`-equivalent arguments before changing them   |
| Instance in a "public" subnet has no internet access            | `map_public_ip_on_launch` unset, or missing route to an internet gateway   | Verify both the subnet's public-IP setting and the route table's `0.0.0.0/0` route to the IGW |

## 9. Best Practices

- Compose IAM permissions from the specific actions a workload needs (as in 5.4) rather than attaching AWS managed policies like `AdministratorAccess` for convenience.
- Use `data "aws_ami"` lookups instead of hardcoded AMI IDs so configurations don't silently reference stale or region-mismatched images.
- Tag every resource consistently (`Name`, `Environment`, `Owner`) via a shared `default_tags` block in the provider configuration ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) rather than repeating `tags = {}` per resource.

## 10. Common Anti-Patterns / Mistakes

- **Embedding AWS access keys directly in `.tf` files or `.tfvars`** instead of using instance profiles, `AWS_PROFILE`, or OIDC-based CI/CD authentication ([§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)) — this is both a security risk and a state-secrets risk ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)).
- **Treating S3 bucket names like local variables.** Because they're globally unique, hardcoding a plausible short name in a shared module guarantees a collision the first time two people apply it.
- **Skipping the public-access-block resource** on buckets "because the bucket isn't meant to be public anyway" — defense in depth means blocking public access explicitly, not relying on the absence of a public policy.

## 11. Interview Questions

**🎯 Beginner:** _"What four AWS Terraform resource types would you expect to see in almost any AWS configuration, and why?"_
**Model answer:** `aws_vpc`/`aws_subnet` for networking, `aws_instance` for compute, `aws_s3_bucket` for storage, and `aws_iam_role`/`aws_iam_policy` for identity — because nearly every workload needs a network boundary to live in, something to run, somewhere to persist data, and a permission model to access other AWS services securely.
_What the interviewer is probing for:_ Basic familiarity with the AWS provider's most common resource types and how they relate.

**🎯 Intermediate:** _"Why does Terraform sometimes show `-/+` (destroy and recreate) instead of `~` (update in place) for an EC2 instance change?"_
**Model answer:** Some EC2 arguments — like `availability_zone` — can't be changed on a running instance via the AWS API at all; there's no "modify AZ" API call. When a changed argument has no corresponding update API, the provider schema marks it as forcing replacement, and Terraform must destroy the old instance and create a new one to reach the declared state. This is a property of the underlying AWS API's capabilities, not a Terraform limitation.
_What the interviewer is probing for:_ Understanding that force-replacement is dictated by the cloud API's actual capabilities, and awareness that `plan` output must be read carefully before applying instance changes in production.

**🎯 Senior:** _"You need an EC2 instance to read objects from an S3 bucket. Walk through the IAM resources involved and why each is needed."_
**Model answer:** Four resources: `aws_iam_role` with a trust policy (`assume_role_policy`) allowing the EC2 service principal to assume it; `aws_iam_policy` defining the actual permissions (`s3:GetObject`, `s3:ListBucket`, scoped to the specific bucket ARN); `aws_iam_role_policy_attachment` linking the policy to the role; and `aws_iam_instance_profile`, which is the actual object EC2 attaches to an instance (a role by itself cannot be attached directly to an instance — the instance profile is the required intermediary). Skipping the instance profile is a common mistake since the role and policy alone look sufficient but the instance has no way to assume the role without it.
_What the interviewer is probing for:_ Precise understanding of the AWS IAM object model (role vs. policy vs. instance profile), not just "attach a policy."

**🎯 Architect:** _"A team's S3 buckets keep getting created with the exact same name across three different Terraform root modules, causing recurring `BucketAlreadyExists` failures during environment builds. How would you fix this systematically, not per-incident?"_
**Model answer:** The root cause is naming as a manual, uncoordinated string literal repeated across independently-owned configurations. The systematic fix is a shared naming-convention module (or a `locals` pattern enforced via a shared module) that computes bucket names deterministically from inputs guaranteed to be unique per environment — account ID via `data "aws_caller_identity"`, environment name, and workload name, e.g. `"${var.workload}-${data.aws_caller_identity.current.account_id}-${var.environment}"`. This removes the possibility of collision without relying on developers remembering a convention, and additionally documents intent (the bucket name itself communicates ownership). A secondary fix is a pre-commit or CI policy check (tflint custom rule, or Sentinel/OPA in Terraform Cloud contexts, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) that rejects hardcoded bucket name literals in new PRs.
_What the interviewer is probing for:_ Whether the candidate reaches for a structural, self-enforcing fix (a shared naming module + policy gate) instead of a one-off rename, showing systems thinking about recurring organizational failure modes.

## 12. Common Misconceptions

1. **"An `aws_iam_role` can be attached directly to an EC2 instance."** It can't — `aws_iam_instance_profile` is the actual attachment point; the instance profile references the role.
2. **"S3 bucket names are scoped to my AWS account like most other resource names."** They're globally unique across all AWS accounts and regions, which is why naming collisions with unrelated organizations happen.
3. **"If `terraform plan` shows a change, it's always an in-place update."** Many AWS resource arguments force full replacement; the diff symbol (`~` vs `-/+`) is what tells you which, and it must be checked before applying to production.
4. **"IAM changes take effect instantly."** IAM is eventually consistent; a role's permissions may not be usable by a freshly launched instance for a few seconds after creation.

## 13. 🔑 Key Takeaways

- The AWS provider's four foundational resource domains — VPC, EC2, S3, IAM — appear in nearly every non-trivial AWS Terraform codebase and compose via implicit references that drive Terraform's dependency graph.
- S3 bucket naming must account for global uniqueness across all AWS accounts, not just the current one.
- IAM's role → policy → attachment → instance-profile chain is the standard, credential-free way to grant compute access to other AWS services.
- Reading whether a `plan` diff is `~` (update) or `-/+` (destroy-and-recreate) is essential before applying changes to running production resources.
- The modern S3 configuration style splits versioning, encryption, and public-access-block into separate resources sharing the bucket ID, replacing deprecated inline blocks from provider v3.

## 14. Related Concepts & What's Next

[§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) goes deeper on IAM-as-code patterns across all three providers, expanding on the role/policy pattern introduced here. [§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) covers networking-as-code patterns (peering, security groups) that build on the VPC/subnet foundation from 5.1. [§33](../Part5/Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md) (data sources) and [§61](../Part8/Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md) (module composition) are the mechanical building blocks this section assumed familiarity with. [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md) now turns to the equivalent deep dive for Azure's `azurerm` provider, contrasting its resource-group-centric model against AWS's flatter, account-scoped model.

**Next Section:** [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md) — `Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md`
