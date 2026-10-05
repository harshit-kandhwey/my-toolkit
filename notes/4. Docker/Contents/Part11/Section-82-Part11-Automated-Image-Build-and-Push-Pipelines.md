# Section 82 (Part 11): Automated Image Build-and-Push Pipelines

## 1. Definition

**Plain language:** An automated image pipeline is the CI/CD job that turns a Git commit into a tagged, scanned, signed image in a registry, with no human running `docker build` or `docker push` by hand.

**Precise definition:** A pipeline that, on a defined trigger (push, tag, pull request, schedule), (1) checks out source, (2) authenticates to a registry using short-lived credentials ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)), (3) computes tags and OCI labels from Git metadata ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), (4) builds with BuildKit ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), usually for several platforms ([§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)), (5) tests and scans the result, (6) pushes it, (7) emits provenance, an SBOM and a signature ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), and (8) records the immutable **digest** so later stages deploy exactly what was built.

> 💡 **Tip:** The unit of promotion is the **digest** (`sha256:...`), not the tag. Tags are labels that can move; digests cannot.

## 2. Why This Matters

- Manual pushes produce "works on my laptop" images, with unknown base images, dirty working trees and stale caches.
- Automation is the only way to enforce policy consistently: scanning, signing, tag rules, and provenance.
- Pipelines are the highest-value supply-chain target: they hold registry write credentials and decide what production runs.
- Reproducible tags and digests make rollback ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)) and GitOps promotion ([§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)) deterministic.
- Registries bill and throttle: careless pipelines trigger Docker Hub rate limits ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)) or storage bloat ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).

## 3. Prerequisites and Dependencies

Requires solid Dockerfile and build knowledge ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md), [§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md), [§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), registry fundamentals ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](../Part9/Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)), push workflows ([§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)), and CI runner choices ([§80](Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)). Build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)), reproducibility ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)) and scanning ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)) feed directly into the stages below.

## 4. Architecture / Conceptual Diagram

```text
  Git event                CI runner (ephemeral)                          Registry
 ┌─────────┐   trigger   ┌─────────────────────────────────────────┐   ┌────────────┐
 │ push to │────────────►│ 1 checkout                              │   │            │
 │ main /  │             │ 2 login (OIDC, short-lived token) ──────┼──►│ auth       │
 │ tag v1.2│             │ 3 metadata: tags + OCI labels           │   │            │
 │ / PR    │             │ 4 buildx build (cache-from/to)          │   │            │
 └─────────┘             │      ├── linux/amd64                    │   │            │
                         │      └── linux/arm64                    │   │            │
                         │ 5 test + scan (fail on HIGH/CRITICAL)   │   │            │
                         │ 6 push by digest ───────────────────────┼──►│ repo:      │
                         │ 7 attest: SBOM + provenance + cosign sig│   │  sha256:.. │
                         │ 8 output digest ► deploy / GitOps PR    │   │  tags:     │
                         └─────────────────────────────────────────┘   │  1.2.3,    │
                                                                       │  1.2, sha-X│
 PR builds: stages 1-5 only (no push, or push to a scratch repo)       └────────────┘

 Tag policy
 ┌───────────────┬──────────────────────────────────────────────┐
 │ Trigger       │ Tags produced                                │
 ├───────────────┼──────────────────────────────────────────────┤
 │ PR            │ none pushed (or pr-123, short retention)     │
 │ main          │ sha-<7>, edge                                │
 │ tag v1.2.3    │ 1.2.3, 1.2, 1, latest (if stable), sha-<7>   │
 │ nightly cron  │ nightly-YYYYMMDD (rebuild for base patches)  │
 └───────────────┴──────────────────────────────────────────────┘
```

- **Build once, promote many:** the image tested in staging is the same digest that reaches production.
- **PRs never get push credentials** for the production repository.
- **Scan before push** where possible (or push to a quarantine repo, scan, then promote).

## 5. Hands-On

### 5.1 The Minimum Viable Script (Any CI)

```bash
set -euo pipefail
IMAGE=registry.example.com/team/app
SHA=$(git rev-parse --short=7 HEAD)
VERSION=$(git describe --tags --always)

docker build \
  --label org.opencontainers.image.revision="$(git rev-parse HEAD)" \
  --label org.opencontainers.image.source="https://github.com/example/app" \
  --label org.opencontainers.image.version="$VERSION" \
  -t "$IMAGE:sha-$SHA" .

docker push "$IMAGE:sha-$SHA"
docker inspect --format '{{index .RepoDigests 0}}' "$IMAGE:sha-$SHA"
```

```text
registry.example.com/team/app@sha256:9b2f6c0e1d7a...
```

Pushing registers the digest; `RepoDigests` is empty until the first push. This script is a baseline, not the target: it lacks login, scanning, cache and signing.

### 5.2 GitHub Actions: Build, Tag, Push (Multi-Platform) to GHCR

```yaml
name: image
on:
  push:
    branches: [main]
    tags: ["v*.*.*"]
  pull_request:

permissions:
  contents: read
  packages: write        # push to GHCR
  id-token: write        # keyless signing / OIDC to clouds
  attestations: write

jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        if: github.event_name != 'pull_request'
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha,format=short
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=edge,branch=main

      - id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: mode=max
          sbom: true

      - run: echo "digest=${{ steps.build.outputs.digest }}"
```

`docker/metadata-action` derives tags and OCI labels from the Git ref; `build-push-action` outputs the digest. Pin actions by commit SHA in high-trust environments, not just by major tag.

### 5.3 Scan Gate and Keyless Signing

```yaml
      - uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: ghcr.io/${{ github.repository }}@${{ steps.build.outputs.digest }}
          severity: HIGH,CRITICAL
          exit-code: "1"
          ignore-unfixed: true

      - uses: sigstore/cosign-installer@v3
      - name: Sign by digest
        if: github.event_name != 'pull_request'
        run: cosign sign --yes ghcr.io/${{ github.repository }}@${{ steps.build.outputs.digest }}
```

Because the job was granted `id-token: write`, cosign uses a GitHub OIDC token to obtain a short-lived Fulcio certificate: no long-lived signing key exists. Verification:

```bash
cosign verify ghcr.io/example/app@sha256:9b2f6c0e1d7a... \
  --certificate-identity-regexp 'https://github.com/example/app/.github/workflows/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

```text
Verification for ghcr.io/example/app@sha256:9b2f... --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - The code-signing certificate was verified using trusted certificate authority certificates
```

Note: with scan-after-push in this example, a failing scan leaves an unsigned image in the registry. Either scan before the push (`load: true`, single-platform) or push to a staging repository and promote only on success.

## 6. Production Usage Notes

- **Tag immutability:** enable it on the registry (ECR, ACR, Harbor, GHCR retention rules) for release tags so `1.2.3` can never be repointed. Keep mutable tags (`edge`, `latest`) clearly separate.
- **Deploy by digest:** the final stage writes `image: repo@sha256:...` into the deployment manifest or opens a GitOps pull request ([§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)); a human-readable tag may sit alongside for display.
- **Caching:** use `type=gha` on GitHub, `type=registry` on GitLab/Jenkins, or an S3/Azure Blob backend, with `mode=max` to cache intermediate stages ([§85](Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)). Remember that cache layers consume registry storage.
- **Base image freshness:** schedule a nightly or weekly rebuild so base-image CVE fixes flow in without a code change; Renovate/Dependabot can bump pinned base digests.
- **Registry limits:** authenticate pulls of base images in CI to avoid Hub anonymous rate limits; mirror critical bases into your own registry ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)).

## 7. Security Considerations

- **Credential scope:** prefer OIDC federation with short-lived tokens over stored passwords. If a static token is unavoidable, scope it to one repository with push-only rights and rotate it.
- **Untrusted triggers:** forked pull requests must never receive secrets or `packages: write`. Avoid `pull_request_target` with checkout of PR code, a known injection route.
- **Pin and verify dependencies:** pin third-party actions/orbs/plugins by commit SHA, pin base images by digest ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)), and review updates.
- **Build secrets:** use `--secret` mounts rather than `ARG`/`ENV` ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)); secrets in layers are recoverable from the pushed image forever.
- **Provenance and signatures:** generate SBOM and SLSA provenance, sign by digest, and enforce verification at admission time (Kubernetes policy controllers, Docker Scout policies) so unsigned images do not run.
- **Cache poisoning:** a shared registry cache writable by PR builds can inject layers into release builds. Scope caches per branch or restrict cache writes to trusted refs.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `denied: requested access to the resource is denied` | Missing login, wrong repository path, or token lacks write scope | Check `docker/login-action` ran (not skipped on this event), repo name, and `packages: write` |
| `unauthorized: authentication required` on base pull | Anonymous Hub rate limit or private base | Log in to Hub in CI, or mirror bases |
| `toomanyrequests: You have reached your pull rate limit` | Shared runner IPs on anonymous pulls | Authenticated pulls, pull-through cache |
| Cache never hits | Cache key/ref differs per run, `mode=min`, or non-deterministic `COPY .` | Stable cache ref, `mode=max`, tighten `.dockerignore` ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)) |
| `exec format error` on a deployed node | Image pushed for amd64 only | Add `platforms:` and verify the manifest list |
| Digest in deploy differs from built digest | Re-tagged or rebuilt downstream | Pass the digest as a job output; deploy by digest |
| Cosign verify fails | Identity regex or issuer mismatch, or signing tag instead of digest | Sign and verify by digest with the exact workflow identity |

## 9. Best Practices

- Build **once**, produce an immutable **digest**, and promote the same artifact through environments.
- Derive tags and labels from Git metadata automatically; include `org.opencontainers.image.source` and `revision`.
- Authenticate with **OIDC** and least-privilege, push-only roles.
- Gate on **tests and vulnerability scan** results; fail on severity thresholds agreed with security.
- Generate **SBOM and provenance**, sign by digest, verify at deploy.
- Keep PR builds **unprivileged**: build and test, do not push to production repositories.
- Use remote cache with a **trusted-writer** policy.
- Rebuild on a **schedule** for base-image patches, and apply retention rules.
- Make the pipeline **idempotent**: rerunning the same commit yields the same tags (or fails clearly if immutable).

## 10. Common Anti-Patterns / Mistakes

- Pushing from developer laptops to production repositories.
- Only ever pushing `latest`, so rollback and audit are impossible.
- Deploying by mutable tag (`:1.2`) instead of digest.
- Long-lived registry passwords in CI variables shared across all projects.
- Letting fork PRs push images or access secrets.
- Baking secrets in via `ARG`/`ENV`/`COPY .env` then pushing publicly.
- Building a different artifact per environment (rebuilding for staging and production), so what was tested is not what ships.
- No cache, so every run re-downloads dependencies; or cache shared writable by untrusted refs.

## 11. Interview Questions

**🎯 Beginner:** _"Walk me through what a CI job should do to build and publish a Docker image."_
**Model answer:** Check out the code, log in to the registry with a CI credential, build the image with a Dockerfile, tag it with something traceable such as the short Git SHA and, for releases, the semantic version, then push it. A good pipeline also runs tests and a vulnerability scan before publishing and records the image digest. Pull requests should build and test but not push to the production repository, and the registry credential should have only the access it needs.
_What the interviewer is probing for:_ The basic stages and awareness of tagging, gating and credential separation.

**🎯 Intermediate:** _"Why deploy by digest instead of by tag, and how do you carry the digest through the pipeline?"_
**Model answer:** A tag is a mutable pointer; someone can push a different image to `1.2.3` or `latest`, and a rebuild can change what a tag means. A digest is the content hash of the manifest, so it identifies exactly one image. In the pipeline, the build step (for example `build-push-action`'s `digest` output, or `docker buildx build --metadata-file`) exposes the digest; later jobs scan, sign and deploy `repo@sha256:...`. Deployment manifests can keep a tag for readability, but the digest is authoritative, and enabling tag immutability on the registry adds defense in depth. This also ensures that what staging validated is byte-for-byte what production runs.
_What the interviewer is probing for:_ Mutability of tags, content addressing, and build-once-promote-many discipline.

**🎯 Senior:** _"A security review finds that your image pipeline has a static registry password, runs on pull requests from forks, and uses an unpinned third-party action. What do you change and in what order?"_
**Model answer:** First, stop the bleeding: remove secrets from fork-triggered workflows (use `pull_request`, not `pull_request_target`; restrict `GITHUB_TOKEN` permissions to read) and rotate the static password immediately because it should be assumed exposed. Second, replace it with OIDC federation to the registry or cloud IAM role bound to repository and branch claims, with push-only permission on a specific repository. Third, pin the action by full commit SHA, review its source, and let Dependabot/Renovate propose updates. Fourth, add the guardrails: default read-only permissions, required reviews for workflow changes (CODEOWNERS on `.github/workflows`), environment protection for release pushes, and a scan-and-sign stage with admission-time verification. Finally, audit the registry logs for unexpected pushes.
_What the interviewer is probing for:_ Prioritization (contain, then redesign), knowledge of CI supply-chain attack vectors, and least privilege through short-lived credentials.

**🎯 Architect:** _"Design the image build-and-promotion platform for 200 services across three clouds, with auditability, fast builds, and the ability to prove what is running in production."_
**Model answer:** Standardize on a reusable pipeline template (reusable workflows or shared CI library) that every service consumes, so policy changes are made once. Each build runs on ephemeral runners, authenticates via OIDC, builds with BuildKit using a registry cache, produces multi-platform images, and pushes to a single authoritative registry with tag immutability. Per-image SBOM, SLSA provenance and a keyless signature are attached by digest. A policy engine (admission controller on every cluster) only admits images signed by the platform's CI identity with passing scan attestations. Promotion is a GitOps change that updates the digest in an environment repo ([§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)); no rebuilds per environment. Replicate the registry to each cloud (pull-through caches or replication) for latency and resilience, define retention by tag class, and ship pipeline and registry audit logs to a central store. Provenance links runtime digest to commit, workflow run and builder, which answers "what is running and where did it come from" for incident response. Trade-offs: central template adoption friction and registry as a single dependency, mitigated by replication and escape hatches with review.
_What the interviewer is probing for:_ End-to-end thinking: standardization, supply-chain controls, promotion model, multi-cloud operations and traceability.

## 12. Common Misconceptions

- "Pushing `latest` is enough." It prevents rollback, audit and reproducibility.
- "A signed tag is a signed image." Signatures bind to digests; tags can move.
- "PR builds should push so reviewers can test." Use ephemeral or scratch registries with short retention, never the release repository.
- "Storing a registry password as a secret is safe." It is long-lived and widely scoped; OIDC avoids storing it at all.

## 13. 🔑 Key Takeaways

- Pipeline stages: login, metadata, build, test, scan, push, attest and sign, record digest.
- Build once, deploy by digest; tags are convenience labels.
- Use OIDC short-lived credentials; keep fork PRs unprivileged.
- Derive tags and OCI labels from Git automatically; enable registry tag immutability for releases.
- Cache with `mode=max` through a registry or CI backend, restricted to trusted writers.
- Sign and attest by digest; enforce verification at admission.
- Rebuild on a schedule for base patches; apply retention rules.

## 14. Related Concepts & What's Next

Related: registry authentication ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)), tagging strategies ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)), multi-platform builds ([§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)), scanning and supply-chain security ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), and CI caching ([§85](Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)). Next, [§83](Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md) covers the test stage in depth: using throwaway containers for databases and dependencies so tests run against real services before an image is published.

**Next Section:** [§83](Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md) — `Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md`
