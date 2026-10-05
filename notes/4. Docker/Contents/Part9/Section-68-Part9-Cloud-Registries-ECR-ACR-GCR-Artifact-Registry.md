# Section 68 (Part 9): Cloud Registries: ECR, ACR, GCR/Artifact Registry

## 1. Definition

**Plain language:** A cloud registry is a managed image registry run by your cloud provider. You get a registry endpoint that speaks the standard registry protocol, tied into the provider's identity system (IAM, Entra ID, Google IAM), private networking, scanning and billing, so you do not operate storage, TLS or garbage collection yourself.

**Precise definition:** The three major offerings are **Amazon Elastic Container Registry (ECR)**, **Azure Container Registry (ACR)** and **Google Artifact Registry** (the successor to Google Container Registry, GCR). All implement the OCI Distribution API ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), so `docker push` and `docker pull` work unchanged; what differs is the hostname format, the authentication exchange ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)), the repository model and the governance features (lifecycle rules, replication, scanning, private endpoints).

| | ECR | ACR | Artifact Registry |
|---|---|---|---|
| Hostname | `<acct>.dkr.ecr.<region>.amazonaws.com` | `<name>.azurecr.io` | `<region>-docker.pkg.dev` |
| Image path | `<host>/<repo>:<tag>` | `<host>/<repo>:<tag>` | `<host>/<project>/<repo>/<image>:<tag>` |
| Repo must pre-exist | Yes, one ECR repo per image name | No, repos created on first push | Yes, the Artifact Registry repository must exist; image names inside it are free-form |
| Native auth | IAM, 12 hour token | Entra ID, tokens, 3 hour login token | Google IAM, OAuth access token or key |

> 💡 **Tip:** Google Container Registry (`gcr.io`) is retired. Google shut it down in 2025 and transitioned `gcr.io` hostnames to be served from Artifact Registry. Use `*-docker.pkg.dev` for new work and migrate any remaining `gcr.io` references.

## 2. Why This Matters

- Production clusters (EKS, AKS, GKE, ECS, Cloud Run) pull from the registry in the same cloud with no static passwords, using node or workload identity.
- Docker Hub rate limits and outage risk ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)) disappear when base images are mirrored or cached into your own cloud registry.
- Pulls inside a region or over a private endpoint are fast and avoid NAT egress charges.
- Interviewers expect you to compare the three on auth, repository model, replication and cost, and to pick one for a given cloud footprint.

## 3. Prerequisites and Dependencies

Requires the push/pull model of images ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), tagging ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), the registry concepts from Docker Hub and self-hosted registries ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)), and the credential mechanics in [§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md). You need the matching cloud CLI (`aws`, `az`, `gcloud`) and an account with permission to create registries. Push workflows are in [§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md), retention in [§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md) and multi-arch in [§72](Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md).

## 4. Architecture / Conceptual Diagram

```text
                    Developer / CI                       Cluster node / service
                          │ docker push                          │ docker pull / kubelet
                          ▼                                      ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  Cloud IAM (token exchange)                                              │
   │  AWS: get-login-password  Azure: az acr login  GCP: gcloud access token  │
   └──────────────────────────────┬───────────────────────────────────────────┘
                                  │ short-lived bearer token
                                  ▼
   ┌────────────────────────── Managed registry ──────────────────────────────┐
   │  OCI Distribution API  (/v2/...)                                         │
   │  ┌────────────┐  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐   │
   │  │ repos/tags │  │ scanning    │  │ lifecycle /  │  │ replication /  │   │
   │  │ manifests  │  │ on push     │  │ cleanup rules│  │ pull-through   │   │
   │  └─────┬──────┘  └─────────────┘  └──────────────┘  └────────────────┘   │
   │        ▼                                                                 │
   │   Blob storage (S3-backed / Azure Storage / GCS-backed), encrypted       │
   └──────────────────────────────────────────────────────────────────────────┘
        ▲ private endpoint (VPC endpoint / Private Link / Private Service Connect)
```

- **Control plane vs data plane:** IAM decides who gets a token; the registry only validates the bearer token and serves blobs.
- **Private connectivity** keeps pulls off the public internet: ECR uses VPC interface endpoints plus an S3 gateway endpoint (layers live in S3), ACR uses Private Link (Premium), Artifact Registry uses Private Google Access or Private Service Connect.
- **Replication** copies images across regions so clusters pull locally.

## 5. Hands-On

### 5.1 ECR: Create a Repository, Log In, Push

```bash
export AWS_REGION=eu-west-1
export ACCT=$(aws sts get-caller-identity --query Account --output text)
export REG=$ACCT.dkr.ecr.$AWS_REGION.amazonaws.com

aws ecr create-repository --repository-name myapp \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true

aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $REG

docker tag myapp:1.4.2 $REG/myapp:1.4.2
docker push $REG/myapp:1.4.2
```

```text
Login Succeeded
The push refers to repository [123456789012.dkr.ecr.eu-west-1.amazonaws.com/myapp]
1.4.2: digest: sha256:9f2c... size: 1363
```

The password is a token valid for 12 hours. Pushing to a repository that does not exist fails with `name unknown: The repository with name 'myapp' does not exist`.

### 5.2 ECR: Lifecycle Policy and Pull-Through Cache

```bash
cat > lifecycle.json <<'EOF'
{ "rules": [
  { "rulePriority": 1, "description": "expire untagged after 7 days",
    "selection": { "tagStatus": "untagged", "countType": "sinceImagePushed",
                   "countUnit": "days", "countNumber": 7 },
    "action": { "type": "expire" } },
  { "rulePriority": 2, "description": "keep last 30 release images",
    "selection": { "tagStatus": "tagPrefixList", "tagPrefixList": ["v"],
                   "countType": "imageCountMoreThan", "countNumber": 30 },
    "action": { "type": "expire" } } ] }
EOF
aws ecr put-lifecycle-policy --repository-name myapp --lifecycle-policy-text file://lifecycle.json

# Cache Docker Hub through ECR (Docker Hub credentials stored in Secrets Manager)
aws ecr create-pull-through-cache-rule --ecr-repository-prefix dockerhub \
  --upstream-registry-url registry-1.docker.io \
  --credential-arn arn:aws:secretsmanager:eu-west-1:123456789012:secret:ecr-pullthroughcache/dockerhub
docker pull $REG/dockerhub/library/alpine:3.20
```

### 5.3 ACR: Create, Log In, Push

```bash
az group create --name rg-registry --location westeurope
az acr create --resource-group rg-registry --name contosoreg --sku Standard \
  --admin-enabled false

az acr login --name contosoreg           # exchanges your Entra ID login for a Docker token
docker tag myapp:1.4.2 contosoreg.azurecr.io/myapp:1.4.2
docker push contosoreg.azurecr.io/myapp:1.4.2
az acr repository list --name contosoreg --output table
```

```text
Login Succeeded
Result
--------
myapp
```

When no Docker daemon is available (CI), use `az acr login --name contosoreg --expose-token` and pass the returned token to `docker login --username 00000000-0000-0000-0000-000000000000 --password-stdin`. Building in the cloud avoids local push entirely: `az acr build --registry contosoreg --image myapp:1.4.2 .`.

### 5.4 ACR: Grant Pull to a Cluster, Create a Scoped Token

```bash
# AKS pulls with its kubelet identity, no password stored
az aks update --name aks1 --resource-group rg-app --attach-acr contosoreg

# Repository-scoped credential for an external system
az acr scope-map create --registry contosoreg --name pull-myapp \
  --repository myapp content/read
az acr token create --registry contosoreg --name ext-puller --scope-map pull-myapp
```

Prefer role assignments (`AcrPull`, `AcrPush`) for Azure identities and scope-map tokens for non-Azure consumers. Keep the registry **admin user disabled**; it is one shared all-powerful credential.

### 5.5 Artifact Registry: Create, Configure Docker, Push

```bash
gcloud services enable artifactregistry.googleapis.com
gcloud artifacts repositories create apps --repository-format=docker \
  --location=europe-west1 --description="App images"

gcloud auth configure-docker europe-west1-docker.pkg.dev   # writes a credHelpers entry

docker tag myapp:1.4.2 europe-west1-docker.pkg.dev/my-project/apps/myapp:1.4.2
docker push europe-west1-docker.pkg.dev/my-project/apps/myapp:1.4.2
gcloud artifacts docker images list europe-west1-docker.pkg.dev/my-project/apps
```

`configure-docker` does not log in; it registers `docker-credential-gcloud` as the helper for that hostname, so every push fetches a fresh token ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)).

### 5.6 Artifact Registry: Cleanup Policy and Roles

```bash
cat > cleanup.json <<'EOF'
[ { "name": "delete-old-untagged", "action": {"type": "Delete"},
    "condition": {"tagState": "untagged", "olderThan": "604800s"} },
  { "name": "keep-recent-releases", "action": {"type": "Keep"},
    "mostRecentVersions": {"keepCount": 20} } ]
EOF
gcloud artifacts repositories set-cleanup-policies apps \
  --location=europe-west1 --policy=cleanup.json

gcloud artifacts repositories add-iam-policy-binding apps --location=europe-west1 \
  --member="serviceAccount:ci@my-project.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

Roles are `artifactregistry.reader`, `writer`, `repoAdmin` and `admin`. Grant at repository level, not project level, wherever possible.

### 5.7 Quick Comparison Checks

```bash
# Confirm which registry an image really came from and its digest
docker image inspect myapp:1.4.2 --format '{{json .RepoDigests}}'
# Pin by digest for reproducible deploys
docker pull $REG/myapp@sha256:9f2c...
```

## 6. Production Usage Notes

- **Choose by where compute runs.** Run in AWS: ECR. Azure: ACR. GCP: Artifact Registry. Cross-cloud pulls work but cost egress and need extra credentials.
- **ECR specifics:** one repository per image name; immutable tags are a per-repository setting; basic scanning (Clair-derived) or enhanced scanning through Amazon Inspector; cross-region and cross-account replication are registry-level settings; ECR Public (`public.ecr.aws`) is a separate public gallery whose auth API is only in `us-east-1`.
- **ACR specifics:** SKUs Basic, Standard and Premium differ in storage, throughput and features. Geo-replication, Private Link, customer-managed keys and content trust-style signing need Premium. ACR Tasks builds and patches images in the cloud and can rebuild automatically when a base image changes.
- **Artifact Registry specifics:** supports Docker, Maven, npm, Python and more in one service; **remote repositories** proxy Docker Hub and others, **virtual repositories** merge several repositories behind one endpoint. Regional and multi-regional locations exist; choose the same region as compute.
- **Mirror base images** into the cloud registry (ECR pull-through cache, ACR cache rules, Artifact Registry remote repo) so builds stop depending on Docker Hub.
- **Cost drivers:** storage per GB-month, cross-region and internet egress, and for ECR/AR scanning charges. Retention rules ([§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)) are the main cost control.
- **Tagging:** use immutable semantic tags plus digests in deploy manifests ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)).

## 7. Security Considerations

- **No long-lived credentials.** Use node/workload identity (IRSA or EKS Pod Identity, AKS kubelet identity or workload identity, GKE Workload Identity) for pulls and OIDC federation for CI pushes ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)).
- **Least privilege.** Separate push and pull permissions; pull-only for runtime, push only for the pipeline, scoped to specific repositories.
- **Disable ACR admin user** and avoid broad service-account keys on GCP.
- **Private networking.** Disable public access or restrict by network once clusters use private endpoints.
- **Immutable tags** stop an attacker or an accident from replacing `v1.4.2` after it was approved.
- **Scanning on push** finds known CVEs ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)); pair it with signing and SBOM verification at admission ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Encryption** at rest is default; customer-managed keys (KMS, Key Vault, Cloud KMS) satisfy stricter policy.
- **Audit logs:** CloudTrail, Azure Activity/Monitor and Cloud Audit Logs record who pushed or deleted what.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `no basic auth credentials` on push | Not logged in, or token expired (ECR 12 h, ACR 3 h) | Re-run the login step; use a credential helper |
| `denied: User ... is not authorized to perform: ecr:InitiateLayerUpload` | IAM role lacks push actions | Add `ecr:BatchCheckLayerAvailability`, `PutImage`, `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload` plus `ecr:GetAuthorizationToken` |
| `name unknown: repository ... does not exist` | ECR/AR repo not created | Create the repository first |
| `tag invalid: The image tag ... already exists ... cannot be overwritten` | Immutable tags enabled | Push a new tag, never reuse |
| AKS `ErrImagePull` / 401 | Cluster identity lacks `AcrPull` | `az aks update --attach-acr` or assign the role |
| `Permission 'artifactregistry.repositories.uploadArtifacts' denied` | Missing writer role or wrong repo path | Grant `roles/artifactregistry.writer`; check project and repo in the path |
| Pulls hang from private subnet | Missing VPC endpoints (ECR needs `ecr.api`, `ecr.dkr` and S3) | Add all three endpoints and DNS |
| `gcr.io` pull fails after migration | Old reference or missing permissions | Switch to the `pkg.dev` path and grant Artifact Registry reader |

## 9. Best Practices

- Pick one registry per cloud and one repository naming scheme (`team/service`).
- Authenticate with identity, not stored passwords; make token refresh automatic through helpers.
- Enable immutable tags, scan on push and lifecycle rules at repository creation, ideally via IaC.
- Deploy by digest or immutable semantic tag; promote the same artifact across environments ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)).
- Replicate or cache into each region where you run clusters.
- Mirror and pin third-party base images instead of pulling from Docker Hub at build time.
- Monitor storage growth and failed-auth events.

## 10. Common Anti-Patterns / Mistakes

- Using the ACR admin account or a shared GCP service-account JSON key in CI.
- Publishing `:latest` into a mutable repository and deploying from it.
- Granting `ecr:*` or project-wide `artifactregistry.admin` to pipelines.
- Never setting lifecycle rules, then paying for years of untagged CI images.
- Running a cluster in one region and pulling from a registry in another.
- Treating `gcr.io` as current and ignoring the migration.
- Baking cloud credentials into images to "make pulls work".

## 11. Interview Questions

**🎯 Beginner:** _"How do you push an image to Amazon ECR?"_
**Model answer:** Create a repository (one per image name), authenticate Docker, tag the image with the full registry path and push. Authentication uses `aws ecr get-login-password --region R | docker login --username AWS --password-stdin ACCT.dkr.ecr.R.amazonaws.com`, which exchanges IAM credentials for a token valid 12 hours. Then `docker tag app:1 ACCT.dkr.ecr.R.amazonaws.com/app:1` and `docker push` it. The IAM principal needs `ecr:GetAuthorizationToken` plus the layer upload and `PutImage` actions.
_What the interviewer is probing for:_ Knowing the repo-must-exist rule and the token-based login flow.

**🎯 Intermediate:** _"Your AKS pods fail with ImagePullBackOff from ACR. Walk through the diagnosis."_
**Model answer:** Read the pod events for the exact error. A 401/403 points to authorization: confirm the kubelet managed identity has `AcrPull` on the registry (`az aks check-acr --name aks1 --resource-group rg --acr contosoreg.azurecr.io` tests it) or attach it with `az aks update --attach-acr`. If the error is name resolution or timeout, check Private Link DNS and network rules on the registry firewall. If it is "manifest unknown", the tag or repository path is wrong or the image was never pushed or was removed by a retention rule. Verify the digest with `az acr repository show-tags`.
_What the interviewer is probing for:_ Separating auth, network and content failures, and knowing identity-based pull.

**🎯 Senior:** _"Design how CI pushes to ECR and production clusters pull from it, with no static secrets."_
**Model answer:** CI authenticates with OIDC federation: the CI provider's token is exchanged for a short-lived IAM role scoped to push on specific repositories. The workflow runs `aws ecr get-login-password | docker login` or the ECR login action, builds, pushes an immutable tag and records the digest. Clusters pull through IRSA or EKS Pod Identity or the node role with `ecr:BatchGetImage`, `GetDownloadUrlForLayer` and `GetAuthorizationToken`, so no Kubernetes pull secret is needed (the kubelet uses its credential provider). Add immutable tags, scan on push, lifecycle rules, and replication to the cluster regions. Deploy by digest.
_What the interviewer is probing for:_ Identity federation, least-privilege split between push and pull, and no stored credentials.

**🎯 Architect:** _"A company runs workloads on AWS, Azure and GCP and wants one image supply chain. How do you structure registries?"_
**Model answer:** Avoid one global registry that every cloud pulls from over the internet: it adds latency, egress cost and a single point of failure. Build and sign once in CI, push to a primary registry, then replicate or promote the same digest into the native registry of each cloud (ECR, ACR, Artifact Registry) using registry-native replication or a tool such as `crane copy`/`oras copy`. Each cluster pulls locally with workload identity. Signatures and SBOM attestations travel with the digest and are verified by admission policy in every cluster. Centralize policy (tag immutability, scan thresholds, retention) in IaC modules that apply identically across clouds, and keep an optional central catalog such as Harbor ([§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)) only if the organization needs vendor-neutral governance.
_What the interviewer is probing for:_ Trade-offs of centralized versus per-cloud registries, digest-based promotion and uniform policy.

## 12. Common Misconceptions

- "GCR and Artifact Registry are the same product." Container Registry is retired; Artifact Registry is the supported service with a different repository model.
- "`docker login` to ECR is permanent." The token expires after 12 hours.
- "ACR creates repositories automatically, so ECR does too." ECR requires the repository to exist first.
- "A cloud registry makes images secure." It stores and controls access; scanning, signing and policy are separate configuration.
- "`gcloud auth configure-docker` logs you in." It only installs a credential-helper entry.

## 13. 🔑 Key Takeaways

- ECR, ACR and Artifact Registry are managed OCI registries tied to cloud IAM; pick the one next to your compute.
- Auth is a token exchange: ECR 12 h, ACR 3 h, GCP via a gcloud-backed helper.
- ECR needs a repo per image; ACR creates on push; Artifact Registry needs the repository, with images free-form inside.
- Enable immutable tags, scan on push and lifecycle/cleanup rules from day one.
- Use workload identity and OIDC instead of static passwords; keep ACR admin disabled.
- `gcr.io` is legacy: use `*-docker.pkg.dev`.

## 14. Related Concepts & What's Next

Related: Docker Hub ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)), self-hosted registries and Harbor ([§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)), image scanning ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)), secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), supply chain security ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Next, [§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md) explains exactly how `docker login`, `config.json` and credential helpers make those token exchanges work.

**Next Section:** [§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md) — `Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md`
