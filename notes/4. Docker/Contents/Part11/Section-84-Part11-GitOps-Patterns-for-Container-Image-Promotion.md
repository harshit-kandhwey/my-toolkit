# Section 84 (Part 11): GitOps Patterns for Container Image Promotion

## 1. Definition

**Plain language:** GitOps means the desired state of what runs in each environment lives in a Git repository, and an automated agent makes reality match it. *Image promotion* is the act of moving the same, already-built image from dev to staging to production without rebuilding it. In GitOps, "promote" means "change a line in Git that names the image," and the change is reviewed, auditable and revertible like any other commit.

**Precise definition:** A GitOps promotion pipeline has four parts:

1. **Build once** in CI, producing an immutable image identified by a content digest (`sha256:...`) and one or more human-friendly tags ([§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)).
2. **Desired-state repository** (the "config repo" or an environments folder) holding manifests: Compose files, Kubernetes manifests, Helm values or Kustomize overlays. These reference images by tag or, preferably, digest.
3. **Promotion mechanism**: a pull request, an automated commit or a tag operation that edits the desired-state repository for the next environment.
4. **Reconciler**: a pull-based agent (Argo CD, Flux, or for plain Docker hosts a small poller or Watchtower-like tool) that continuously compares the running state with Git and converges it.

The defining property is that CI never holds production credentials and never runs `docker run` or `kubectl apply` against production. The cluster pulls; CI only pushes images and commits.

> 💡 **Tip:** Promote the artifact, not the source. If staging and production run images built from the same commit but in two separate builds, you have tested one thing and shipped another.

## 2. Why This Matters

- **Build once, deploy many:** a rebuild can differ (base image updated, package index changed, timestamps), so the staging approval no longer applies to the production artifact.
- **Auditability:** "who changed production and why" is `git log` plus a PR review, not a CI log that expires.
- **Rollback is a revert:** reverting a commit in the config repo restores the previous image reference, and the reconciler does the rest.
- **Reduced blast radius:** pipeline credentials only need registry write access, not cluster admin ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- **Drift detection:** manual `docker run` or `kubectl edit` changes on a host are detected and reverted, which keeps environments reproducible.
- Common system-design and platform-engineering interview topic.

## 3. Prerequisites and Dependencies

You need a CI pipeline that builds and pushes images ([§80](Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), a registry that supports immutable digests and retention rules ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](../Part9/Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)), and a tagging strategy ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)). Integration tests with ephemeral containers ([§83](Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)) provide the gate evidence. Compose basics ([§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), [§38](../Part5/Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)) matter for the single-host variant, and signing and SBOMs ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)) matter for the verified-promotion variant.

## 4. Architecture / Conceptual Diagram

```text
  App repo                      Registry                     Config repo (desired state)
 ┌──────────┐  1. build once  ┌──────────────┐            ┌─────────────────────────┐
 │ source   │ ───────────────►│ app@sha256:A │            │ envs/dev/values.yaml    │
 │ + tests  │  push + sign    │ tags: git-1f3│            │ envs/staging/values.yaml│
 └────┬─────┘  + SBOM         └──────┬───────┘            │ envs/prod/values.yaml   │
      │                              │                    └───────────┬─────────────┘
      │ 2. CI commits image ref      │                                │
      └──────────────────────────────┼───────────────────────────────►│ dev: app@sha256:A
                                     │                                │
        3. gate passes (tests, scan, approval) ─ PR edits staging ───►│ staging: app@sha256:A
        4. release approval         ─ PR edits prod    ──────────────►│ prod:    app@sha256:A
                                     │                                │
                                     ▼                                ▼
                              ┌─────────────┐   pulls Git    ┌────────────────┐
                              │ Docker host │◄───────────────│ Reconciler     │
                              │ / cluster   │  pulls image   │ (Argo CD/Flux) │
                              └─────────────┘◄───────────────└────────────────┘

  Same digest A is promoted: dev ► staging ► prod. Only the Git pointer moves.
```

- **Pull model:** the reconciler lives inside the environment and reaches out; no inbound CI access is needed.
- **Environment = directory or branch:** directories (folder per environment on `main`) are generally preferred over long-lived branches, which drift and need merges.
- **Promotion = commit:** the diff of the promotion PR is a one-line image reference change.

## 5. Hands-On

### 5.1 Build Once, Capture the Digest

```bash
docker buildx build --push -t registry.example.com/shop/api:git-1f3a9c2 --metadata-file meta.json .
DIGEST=$(jq -r '."containerimage.digest"' meta.json)
echo "$DIGEST"
```

```text
sha256:9b1c0e4f7d2a5e8b3c6d1f0a9e8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b
```

The digest, not the tag, is the identity that gets promoted. Equivalent without a metadata file: `docker buildx imagetools inspect registry.example.com/shop/api:git-1f3a9c2 --format '{{json .Manifest.Digest}}'`.

### 5.2 Desired-State Repository Layout

```text
config-repo/
├── base/compose.yaml            # shared service definition
└── envs/
    ├── dev/compose.override.yaml
    ├── staging/compose.override.yaml
    └── prod/compose.override.yaml
```

```yaml
# envs/staging/compose.override.yaml
services:
  api:
    image: registry.example.com/shop/api@sha256:9b1c0e4f7d2a5e8b3c6d1f0a9e8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b
```

A reference by digest is immutable: even if someone re-pushes the tag, the host runs the exact bytes that were tested.

### 5.3 Automated Promotion Step in CI (Dev Auto-Deploy)

```yaml
# .github/workflows/promote-dev.yml (runs after a successful build on main)
jobs:
  update-dev:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          repository: shop/config-repo
          token: ${{ secrets.CONFIG_REPO_TOKEN }}   # scoped: contents write on config repo only
      - name: Set image digest for dev
        run: |
          yq -i '.services.api.image = "registry.example.com/shop/api@${{ needs.build.outputs.digest }}"' \
            envs/dev/compose.override.yaml
      - run: |
          git config user.name "ci-bot" && git config user.email "ci-bot@example.com"
          git commit -am "dev: api -> ${{ needs.build.outputs.digest }}"
          git push
```

The token can write to the config repo only; it cannot touch any host.

### 5.4 Promotion by Pull Request (Staging and Production)

```bash
# promote.sh: copy the digest currently in dev into the target environment as a PR
set -euo pipefail
TARGET=$1                                     # staging | prod
DIGEST=$(yq '.services.api.image' envs/dev/compose.override.yaml | sed 's/.*@//')
git switch -c "promote/${TARGET}-${DIGEST:7:12}"
yq -i ".services.api.image = \"registry.example.com/shop/api@${DIGEST}\"" "envs/${TARGET}/compose.override.yaml"
git commit -am "${TARGET}: promote api ${DIGEST:0:19}"
gh pr create --fill --label "promotion:${TARGET}"
```

Branch protection requires a review (and, for prod, a CODEOWNERS approval) before merge. The merge *is* the deployment decision.

### 5.5 A Minimal Pull-Based Reconciler for a Single Docker Host

```bash
# /usr/local/bin/gitops-sync.sh, run every minute by a systemd timer
set -euo pipefail
cd /srv/config-repo
git fetch --quiet origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  git reset --hard origin/main                # host copy of the repo is disposable
  docker compose -f base/compose.yaml -f envs/prod/compose.override.yaml pull
  docker compose -f base/compose.yaml -f envs/prod/compose.override.yaml up -d --remove-orphans
fi
```

```text
[+] Pulling 1/1
 ✔ api Pulled
[+] Running 2/2
 ✔ Container shop-db-1   Running
 ✔ Container shop-api-1  Started
```

On Kubernetes the same role is played by Argo CD or Flux; the principle (pull, compare, converge) is identical. Note that `git reset --hard` here targets the dedicated checkout directory only; never point such a script at a directory containing other data.

### 5.6 Argo CD Application Pointing at an Environment Folder

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata: { name: shop-prod, namespace: argocd }
spec:
  project: default
  source:
    repoURL: https://github.com/shop/config-repo
    targetRevision: main
    path: envs/prod
  destination: { server: https://kubernetes.default.svc, namespace: shop }
  syncPolicy:
    automated: { prune: true, selfHeal: true }   # selfHeal reverts manual drift
```

### 5.7 Automating Tag-Follow Updates (Optional)

Tools such as Argo CD Image Updater, Flux image automation and Renovate watch a registry and open commits or PRs when a new image matching a policy (for example `~1.4`) appears. They are convenient for non-production environments; for production, prefer an explicit human-approved promotion of a digest.

### 5.8 Verifying Before Promotion

```bash
cosign verify registry.example.com/shop/api@${DIGEST} \
  --certificate-identity-regexp 'https://github.com/shop/api/.github/workflows/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
trivy image --exit-code 1 --severity CRITICAL registry.example.com/shop/api@${DIGEST}
```

Run in the promotion PR's checks so a non-signed or critically vulnerable digest cannot reach staging or production ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

## 6. Production Usage Notes

- **Two repositories** (app repo and config repo) separate code review from release decisions and keep CI commit noise out of the app history. Small teams may use one repo with an `envs/` folder.
- **Tag plus digest:** write `image: repo/app:1.4.2@sha256:...` so humans read the version and Docker enforces the digest. When a digest is present, Docker pulls by digest and the tag is informational.
- **Immutable tags in the registry** (ECR/Harbor/ACR support it) stop silent overwrites of a promoted tag.
- **Promotion gates** typically are: unit tests, integration tests ([§83](Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)), vulnerability scan, smoke test in staging, then a manual approval for prod.
- **Retention:** garbage collection must never remove digests still referenced by any environment's config or by recent history needed for rollback ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- **Rollback:** `git revert` the promotion commit; do not rebuild the old version. Keep the last N digests per environment pinned in retention rules ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)).
- **Multi-architecture:** promote the manifest-list digest, not a single-platform digest, so every node pulls the right variant ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)).
- **Secrets stay out of Git in plaintext:** use sealed-secrets, SOPS or an external secret store ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Deployment strategy** (rolling, blue/green) is decided by the manifests and is covered in [§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md).

## 7. Security Considerations

- **Credentials flow inward, not outward:** the reconciler holds cluster or host access; CI holds only registry push and config-repo write. Compromising CI should not equal compromising production.
- **Protect the config repo as production:** branch protection, required reviews, signed commits and CODEOWNERS. Whoever can merge there can deploy anything.
- **Pin by digest** so a tag overwrite or registry compromise of a mutable tag cannot change what runs.
- **Verify signatures and attestations at admission or in the promotion check** (cosign with keyless identity, or Kubernetes admission policies) so only images built by your pipeline are deployable.
- **Restrict who can push to the registry** to the CI identity; developers get pull-only access.
- **Separate tokens per environment** and use short-lived OIDC credentials instead of long-lived PATs where the platform supports it.
- **Avoid auto-promoting to production** from a mutable-tag watcher; an attacker who can push a tag then controls production.
- Scan on promotion, not only at build time, because new CVEs appear after the build ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Reconciler shows `OutOfSync` forever | Manifest field mutated by a controller or defaulting | Add ignore-differences rule or set the defaulted value explicitly in Git |
| New image deployed but old pods keep running | Tag reused (`latest`), manifest unchanged so no rollout | Reference a digest or unique tag so the manifest changes |
| `manifest unknown` on pull | Retention policy deleted the digest or wrong repository | Check registry lifecycle rules; restore from backup or re-promote a retained digest |
| `no matching manifest for linux/arm64` | Promoted a single-platform digest to mixed nodes | Promote the manifest-list digest ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)) |
| `ImagePullBackOff` / `unauthorized` after promotion | Environment lacks pull credentials | Provision per-environment pull secret or credential helper ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)) |
| Promotion PR conflicts constantly | Many writers editing the same file | One file per environment/service, use bots with rebase, or Kustomize image transformer |
| Drift keeps reappearing on a host | Someone runs manual `docker run` or `compose up` | Enable self-heal, remove shell access, alert on drift |
| Prod runs different bytes than staging | Tag-based reference rebuilt or retagged | Switch to digests and immutable tags |

## 9. Best Practices

- Build once, promote the digest through every environment.
- Keep desired state in Git, one folder per environment, reconciled by a pull-based agent.
- Auto-promote to dev, gate staging on tests, gate production on explicit approval.
- Write `tag@digest` references and enable immutable tags.
- Sign images and verify the signature in the promotion check.
- Make rollback a `git revert` and rehearse it regularly.
- Alert on sync failures and on drift, not just on failed pipelines.
- Keep secrets encrypted or external; never commit plaintext.
- Make retention rules aware of what environments reference.

## 10. Common Anti-Patterns / Mistakes

- Rebuilding the image for each environment ("build per environment") and calling it promotion.
- Deploying `:latest` from Git, so the manifest never changes and nothing rolls out or rolls back predictably.
- Giving CI a production kubeconfig or SSH key and running `docker compose up` from the pipeline (push-based, wide blast radius).
- Long-lived environment branches (`staging`, `prod`) that diverge and require cherry-picks.
- Putting environment-specific configuration inside the image rather than in the desired-state repo.
- Auto-updating production from a tag watcher with no gate.
- Config repo with no branch protection, so any contributor can change production.
- Treating Git as an audit log but still allowing manual changes on hosts.

## 11. Interview Questions

**🎯 Beginner:** _"What does 'promote an image' mean in a GitOps workflow, and why is it not 'rebuild for production'?"_
**Model answer:** Promotion means taking the exact image that was built and tested, identified by its digest, and updating the desired-state repository so the next environment runs it. Rebuilding creates a new artifact that may differ because base images, dependencies or timestamps changed, so the tests that passed in staging do not describe it. The Git change is usually a one-line edit of the image reference, reviewed through a pull request, and an agent such as Argo CD or Flux applies it.
_What the interviewer is probing for:_ Build-once-deploy-many and the idea that Git holds desired state.

**🎯 Intermediate:** _"Your team deploys by tag `1.4.2`. Someone re-pushes `1.4.2` with a hotfix. What breaks, and how do you prevent it?"_
**Model answer:** Tags are mutable pointers. Hosts that already pulled `1.4.2` keep the old bytes, new hosts get the new ones, and the manifest in Git did not change so the reconciler reports everything healthy. Environments silently diverge and the audit trail is wrong. Prevent it with immutable tags in the registry, by referencing `tag@sha256:digest` in Git so the pull is pinned to content, and by promoting only via a Git commit. Re-pushing a fixed build should create a new tag and new digest, which flows through the same promotion path.
_What the interviewer is probing for:_ Tag mutability, digest pinning and registry immutability controls.

**🎯 Senior:** _"Design the promotion flow from commit to production for a service with a database migration, with rollback. Where do approvals and automated checks sit?"_
**Model answer:** CI builds once, pushes, signs and attaches an SBOM, then commits the digest to the dev folder of the config repo. The reconciler deploys dev; integration tests against ephemeral containers run as a gate. A bot opens a promotion PR to staging with checks for signature verification and a vulnerability scan; merging deploys staging where smoke tests and the migration rehearsal run. The production PR requires CODEOWNERS approval and a passing staging soak. For the migration, use expand/contract so the old and new image versions both work with the intermediate schema; the migration runs as a pre-sync job or init step and is backwards compatible, which makes `git revert` of the image safe. Rollback is reverting the promotion commit; the retention policy keeps previous digests, and data rollback is not attempted automatically.
_What the interviewer is probing for:_ Gate placement, schema compatibility and why rollback of code must be decoupled from data.

**🎯 Architect:** _"You run 300 services across 12 clusters. Compare push-based CI deploys with pull-based GitOps, and describe how you scale the config repository and avoid it becoming a bottleneck."_
**Model answer:** Push-based means CI needs credentials to every cluster, offers no continuous drift correction and couples pipeline availability to deployment. Pull-based keeps credentials local to each cluster, continuously reconciles, and scales by adding reconcilers. For scale, split the config into a platform repo (shared base, policies) and per-team or per-domain repos, use an ApplicationSet-style generator or Kustomize/Helm layering so environments are generated rather than copied, and have bots handle promotion commits with rebase-retry to avoid conflicts. Use progressive delivery (canary or blue/green via a controller) for production rollouts, admission policies to enforce signed images and approved registries, and metrics on sync latency and drift. The trade-offs are eventual consistency, a harder debugging story (an extra layer between commit and running pod) and the need to treat the config repo as a tier-0 system with its own backup and access model.
_What the interviewer is probing for:_ Security model comparison, repo topology at scale and operational trade-offs.

## 12. Common Misconceptions

- "GitOps requires Kubernetes." The pattern works with Compose on a host and a poller; tooling is richer on Kubernetes.
- "GitOps means CI/CD is replaced." CI still builds, tests and signs; GitOps replaces the deploy step.
- "Pinning a digest makes updates impossible." Updates are still a commit; they are just explicit.
- "One branch per environment is the GitOps way." Folders on one branch are easier to review and promote.
- "Auto-sync everywhere is always better." Production usually deserves an approval gate.

## 13. 🔑 Key Takeaways

- Build once; promote the same digest through dev, staging and production.
- Git holds desired state; a pull-based reconciler converges reality and reverts drift.
- Promotion is a reviewed commit or PR; rollback is a `git revert`.
- Reference `tag@digest`, enable immutable tags, and sign and verify images.
- CI holds registry and config-repo credentials only, never production access.
- Retention and garbage collection must respect digests referenced by environments.

## 14. Related Concepts & What's Next

Related: pipelines ([§80](Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), test gates ([§83](Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)), tagging and registries ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md), [§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)), signing ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), rollout and rollback ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md), [§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). Next, [§85](Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md) tackles the other half of a fast pipeline: making the build step itself quick through cache reuse across ephemeral CI runners.

**Next Section:** [§85](Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md) — `Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md`
