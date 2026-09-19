# 🛠️ my-toolkit

Personal reference repository for DevOps & Cloud engineering — reusable configs, scripts, commands, and notes I reach for regularly.

> Not meant to be a polished project. Just a fast, reliable place to pull things from.

---

## 📁 Structure

```
my-toolkit/
├── aws/
│   ├── policies/                # Reusable IAM & resource-based policy JSON
│   ├── cloudformation/          # Reusable CloudFormation templates
│   ├── scripts/                 # AWS CLI automation scripts (audits, cleanup, reports)
│   └── lambda-functions/        # Deployable Lambda functions (inventory, cleanup, protect)
├── terraform/                   # Reusable Terraform modules and snippets
├── linux/                       # Linux commands and shell cheatsheets
└── notes/                       # Study notes and learning references
```

---

## 🔧 What's Inside

### `aws/`
AWS-specific configs, templates, and scripts — see [aws/README.md](aws/README.md) for the full index.

- **`policies/`** — Reusable IAM and resource-based policies for common patterns (S3 cross-account/scoped-folder/read-only access, MFA enforcement, cross-account role assumption, developer permissions boundary).
- **`cloudformation/`** — CloudFormation templates for common AWS infrastructure patterns (VPC, secure S3 bucket, EC2 instance, IAM cross-account role, Lambda function).
- **`scripts/`** — AWS CLI + `jq` scripts for recurring audit/cleanup/reporting tasks.

### `terraform/`
Reusable modules and config snippets across environments — VPC, EC2, ECS, RDS, IAM, S3, and more. Structured for multi-env setups (dev/prod) with remote state patterns.

### `linux/`
Linux command references, Bash snippets, and shell scripting patterns — mostly for Ubuntu, RHEL, and Amazon Linux environments.

### `notes/`
Study notes on AWS, DevOps concepts, certifications, and anything worth writing down.

---

## ⚙️ Tech Stack

![AWS](https://img.shields.io/badge/AWS-%23FF9900.svg?style=flat&logo=amazon-aws&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-%235835CC.svg?style=flat&logo=terraform&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-FCC624?style=flat&logo=linux&logoColor=black)
![Bash](https://img.shields.io/badge/Bash-%23121011.svg?style=flat&logo=gnu-bash&logoColor=white)

---

## 🔒 Private Repo

This is a private reference repo for personal use. Content here is work-in-progress and updated as needed.

---

*Harshit Kandhwey — [LinkedIn](https://linkedin.com/in/harshit-kandhwey) · [GitHub](https://github.com/harshit-kandhwey)*
