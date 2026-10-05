# Section 70 (Part 9): Image Push/Pull Workflows and Tagging Strategies

## 1. Definition

**Plain language:** Pushing uploads an image's layers and metadata to a registry under a name; pulling downloads them. A *tag* is a human-friendly, movable label on an image; a *digest* is the immutable fingerprint of exactly one image.

**Precise definition:** An image reference has the form `[registry-host[:port]/]repository[:tag][@digest]`. If the host is omitted Docker assumes `docker.io`; if the tag is omitted it assumes `latest`. A tag is a mutable pointer stored by the registry that maps a name to a manifest digest (`sha256:...`); the digest is the SHA-256 of the manifest bytes and is content-addressed, so it can never point to different content ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)). A push performs, per layer blob, an existence check (`HEAD`), an upload if missing (`POST` then `PUT`), and finally uploads the manifest (`PUT /v2/<name>/manifests/<tag>`). A pull fetches the manifest (resolving a manifest list to the platform-specific manifest, see [§72](Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)), then downloads missing layer blobs in parallel and verifies each against its digest.

> 💡 **Tip:** `docker tag` does not copy anything. It adds another name that points at the same image ID, so retagging is free and instant.

## 2. Why This Matters

- Tags are the contract between CI and deployment. A bad tagging scheme causes "which build is running in prod?" incidents that are slow to diagnose.
- `latest` is not "the newest image"; it is just the default tag name. Deploying it means deployments are non-reproducible and rollbacks are impossible.
- Mutable tags can be overwritten, silently changing what a running orchestrator pulls on the next node restart.
- Layer-level deduplication makes pushes fast only if your build keeps lower layers stable; a good workflow exploits this to save time and registry bandwidth.
- Registry rate limits and egress charges ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)) punish wasteful pull patterns.

## 3. Prerequisites and Dependencies

You need a built image ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), a repository on a registry ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)) and credentials ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)). Signing and provenance, which attach to digests, are in [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md). Retention rules that delete old tags are in [§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md).

## 4. Architecture / Conceptual Diagram

```text
  Push                                              Registry (OCI Distribution API)
  ┌───────────┐  1. HEAD blob sha256:aaa  ─────────►  exists? yes ── skip
  │ docker    │  2. HEAD blob sha256:bbb  ─────────►  exists? no
  │ client /  │  3. POST + PUT blob bbb   ─────────►  store blob
  │ BuildKit  │  4. PUT manifest (tag v1.4.2) ─────►  tag v1.4.2 ──► sha256:m1
  └───────────┘                                       tag latest ──► sha256:m1
                                                      (tags are pointers)
  Pull
  docker pull app:v1.4.2
     │  GET manifest by tag ─► digest sha256:m1
     │  (index? pick linux/amd64 child manifest)
     ▼  GET blobs not already in local content store, verify digests

  Reference forms (increasing immutability)
  ┌──────────────────────────────┬──────────────────────────────────────┐
  │ app                          │ docker.io/library/app:latest (mutable)│
  │ app:1.4                      │ floating minor tag (mutable)          │
  │ app:1.4.2                    │ release tag (convention: immutable)   │
  │ app:1.4.2-3f9c1ab            │ version + git SHA (unique per build)  │
  │ app@sha256:9b2e...           │ digest (truly immutable)              │
  │ app:1.4.2@sha256:9b2e...     │ tag for humans, digest enforced       │
  └──────────────────────────────┴──────────────────────────────────────┘
```

- **Tags are many-to-one:** several tags can point at one digest; one tag points at exactly one digest at a time.
- **Untagged ("dangling") manifests** appear when a tag is moved; the old digest stays in the registry until garbage collection ([§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- **When both tag and digest are given, the tag is ignored for resolution**; the digest wins.

## 5. Hands-On

### 5.1 Tag and Push

```bash
docker build -t myapp:build .
docker tag myapp:build registry.example.com/team/myapp:1.4.2
docker tag myapp:build registry.example.com/team/myapp:1.4
docker tag myapp:build registry.example.com/team/myapp:latest
docker push registry.example.com/team/myapp:1.4.2
```

```text
The push refers to repository [registry.example.com/team/myapp]
5f70bf18a086: Layer already exists
c1d2e3f4a5b6: Pushed
1.4.2: digest: sha256:9b2e4c...d41 size: 1572
```

"Layer already exists" is the dedup check at work. To push every tag of a repository: `docker push --all-tags registry.example.com/team/myapp`.

### 5.2 Find and Pin the Digest

```bash
docker buildx imagetools inspect registry.example.com/team/myapp:1.4.2
docker inspect --format '{{index .RepoDigests 0}}' registry.example.com/team/myapp:1.4.2
```

```text
Name:      registry.example.com/team/myapp:1.4.2
MediaType: application/vnd.oci.image.index.v1+json
Digest:    sha256:9b2e4c...d41
```

`RepoDigests` is only populated after a push or pull, because the digest is assigned by the registry-side manifest. Capture this digest in CI output, since it is what you deploy.

### 5.3 Pull by Digest

```bash
docker pull registry.example.com/team/myapp@sha256:9b2e4c...d41
docker run --rm registry.example.com/team/myapp:1.4.2@sha256:9b2e4c...d41
```

Pulling by digest bypasses tag mutability entirely: if someone overwrote `1.4.2`, you still get the original content.

### 5.4 Inspect Without Pulling

```bash
docker manifest inspect registry.example.com/team/myapp:1.4.2
docker buildx imagetools inspect --raw registry.example.com/team/myapp:1.4.2
```

Both read the manifest from the registry without downloading layers, which is how CI jobs check whether a tag already exists before rebuilding.

### 5.5 A CI-Style Tag Set

```bash
VERSION=1.4.2
SHA=$(git rev-parse --short=7 HEAD)
IMG=registry.example.com/team/myapp

docker build -t "$IMG:$VERSION-$SHA" .
docker push "$IMG:$VERSION-$SHA"          # immutable build artifact
# promote after tests pass: retag the same bytes, no rebuild
docker buildx imagetools create -t "$IMG:$VERSION" -t "$IMG:1.4" "$IMG:$VERSION-$SHA"
```

`imagetools create` copies the manifest registry-side (no layer transfer), and it preserves multi-arch indexes, unlike `docker pull` then `docker tag` then `docker push`, which flattens an index to the local platform only.

### 5.6 Build and Push in One Step

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t registry.example.com/team/myapp:1.4.2-3f9c1ab --push .
```

`--push` sends layers straight from BuildKit to the registry; the images never enter the local image store (the classic store cannot hold multi-platform results anyway). With the containerd image store enabled this limitation is lifted.

### 5.7 Pull Behavior Flags

```bash
docker pull --platform linux/arm64 alpine:3.20
docker run --pull=always myapp:1.4      # re-check the registry on every start
docker run --pull=never myapp:1.4       # fail instead of contacting the registry
docker pull --quiet registry.example.com/team/myapp:1.4.2
```

The default `--pull=missing` only pulls when the tag is absent locally, so a moved floating tag is not noticed until the local copy is removed.

## 6. Production Usage Notes

- **Recommended tag set per build:** an immutable unique tag (`<version>-<gitsha>` or CI build number), plus floating convenience tags (`1.4`, `1`, `latest`) applied only on promotion.
- **Deploy by digest.** Resolve the tag to a digest once in CI, write the digest into the manifest (Kubernetes `image:`, Compose, Helm values) and keep the tag only as a comment or annotation. This gives reproducible rollouts and exact rollbacks.
- **Enable tag immutability** where the registry supports it (ECR immutable tags, Harbor immutability rules, Docker Hub and ACR equivalents) for release tags; keep only `latest`-style tags mutable.
- **Semantic versioning tags:** `1.4.2`, `1.4`, `1`, as in most official images. Consumers choose their risk: `1` takes minor updates, `1.4.2` takes none.
- **Base-image tags rot.** Pin base images by digest in Dockerfiles and let a bot (Dependabot, Renovate) open update PRs, so rebuilds are intentional.
- **Kubernetes pull policy:** `latest` tag defaults to `imagePullPolicy: Always`, any other tag to `IfNotPresent`. A digest reference makes the policy irrelevant to correctness.
- **Pull-through caches and mirrors** reduce Hub rate-limit exposure and egress cost ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)); set `registry-mirrors` in `daemon.json`.
- **Tag naming rules:** up to 128 characters, `[A-Za-z0-9_.-]`, cannot start with a period or dash. Avoid `+` (use `-` for build metadata) because it is not allowed.
- **Promotion across environments:** prefer copying the same digest between registries (`imagetools create`, `crane copy`, `skopeo copy --all`) over rebuilding.

## 7. Security Considerations

- **Mutable tags are a supply-chain risk.** An attacker or careless engineer who can push to a repository can repoint `1.4.2` at different content. Digest pinning and immutability rules defeat this.
- **Sign and verify digests**, not tags ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)); admission controllers should verify the signature on the digest being run.
- **Least privilege:** CI gets push-only credentials scoped to specific repositories; runtime nodes get pull-only ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)).
- **Never bake secrets into layers.** Every pushed layer is downloadable by anyone with pull access, and deleting a tag does not remove the blob from other manifests or caches.
- **Typosquatting and unqualified names:** always use fully qualified names for private images so a missing local tag cannot fall back to a public `docker.io` image of the same name (dependency confusion).
- **Scan before promotion:** gate the retag step on scan results ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `denied: requested access to the resource is denied` | Not logged in, wrong namespace, or no push permission | `docker login`, check repo path (`user/` or `org/` prefix), check role ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)) |
| `tag does not exist` / `manifest unknown` | Typo, tag never pushed, or removed by retention | `docker manifest inspect`, check [§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md) policies |
| `An image does not exist locally with the tag` | Pushing a name that was never tagged locally | `docker tag` first, or build with the full name |
| `toomanyrequests: You have reached your pull rate limit` | Anonymous or free Hub limits | Authenticate, use a mirror, or move base images to your registry |
| Node runs old code after "redeploy" | Floating tag plus `IfNotPresent` pull policy | Deploy by digest or unique tag |
| `tag invalid: The image tag 'x' already exists... cannot be overwritten` | Registry tag immutability | Create a new tag; never reuse release tags |
| `unauthorized` on pull in cluster only | Missing/expired image pull secret | Refresh credentials ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)) |
| `no matching manifest for linux/arm64` | Image published for amd64 only | Build multi-arch ([§72](Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)) or pass `--platform` |
| Multi-arch image became single-arch after retag | Used `docker pull`/`tag`/`push` | Use `buildx imagetools create` or `crane copy` |
| `http: server gave HTTP response to HTTPS client` | Plain-HTTP registry | Use TLS, or list it under `insecure-registries` for local tests only |

## 9. Best Practices

- Produce one immutable, unique tag per build and push it first; promote by retagging the same digest rather than rebuilding.
- Deploy by digest and record `tag + digest` in release notes and deployment metadata.
- Never deploy `latest`; reserve it for local development convenience if used at all.
- Turn on tag immutability for release tags.
- Add OCI labels (`org.opencontainers.image.revision`, `.source`, `.version`) so any digest can be traced back to a commit.
- Pin base images by digest with an automated update bot.
- Use `--push` from buildx for multi-platform builds, and cache layers in the registry (`--cache-to type=registry`) to speed up CI.
- Check existence with `docker manifest inspect` before rebuilding unchanged commits.
- Use a mirror or pull-through cache close to your compute.

## 10. Common Anti-Patterns / Mistakes

- Deploying `:latest` to production and expecting rollbacks to work.
- Reusing a release tag (`1.4.2`) for a rebuilt image.
- Rebuilding the image per environment (dev, staging, prod) instead of promoting one artifact.
- Encoding environment in the tag (`myapp:prod`) so the tag moves with each release and history is lost.
- Tagging only with the git branch name (`main`), which is just `latest` under a different label.
- Relying on `docker pull` + `docker push` to copy multi-arch images between registries.
- Pushing credentials or `.env` files into layers, then deleting the tag and assuming they are gone.
- Using date-only tags (`2026-10-06`) that collide when two builds run the same day.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between an image tag and an image digest, and why is `latest` not safe to deploy?"_
**Model answer:** A tag is a mutable label stored in the registry that points to a manifest; a digest is the SHA-256 of the manifest and always identifies the same bytes. `latest` is merely the default tag name used when none is given. It is not guaranteed to be the newest build, it changes whenever anyone pushes without a tag, and two nodes pulling it at different times can run different code. For production you deploy a unique version tag or, better, the digest.
_What the interviewer is probing for:_ Understanding of mutability versus content addressing and awareness that `latest` has no special meaning.

**🎯 Intermediate:** _"Describe what happens on the wire when you run `docker push` for an image whose base layers already exist in the registry."_
**Model answer:** The client walks the manifest's layers and, for each blob digest, asks the registry if it exists (HEAD). Existing blobs print "Layer already exists" and are skipped, and the registry may also mount a blob from another repository on the same registry (cross-repo mount) without uploading. Missing blobs are uploaded with POST then PUT, compressed with gzip or zstd. Finally the config blob and the manifest are uploaded and the tag is updated to point at the new manifest digest. The old manifest remains until garbage collected. This is why stable lower layers make pushes fast.
_What the interviewer is probing for:_ Knowledge of content-addressed layers, deduplication and the manifest-last ordering.

**🎯 Senior:** _"Design a tagging and promotion scheme for a service deployed to dev, staging and prod via Kubernetes, with fast rollback and an audit trail."_
**Model answer:** CI builds once per commit and pushes `app:<semver>-<sha>`, then records the resulting digest. Tests and scans run against that digest. Promotion copies the same digest to environment-specific references or just updates the GitOps manifest with `app@sha256:...`; no rebuild occurs, so what was tested is what ships. Floating tags (`1.4`) exist for consumers who want them but are never used by our deployments. Release tags are immutable at the registry; images are signed and admission policy verifies the signature on the digest. Rollback is a revert of the GitOps commit to the previous digest, which is guaranteed to still exist because retention policies protect any digest referenced by a deployed environment. OCI labels map digest to commit for audit.
_What the interviewer is probing for:_ Build-once-promote-many, digest deployment, immutability and the link with retention.

**🎯 Architect:** _"You run 400 services across three registries and two clouds. How do you standardize image references, ensure availability during a registry outage, and control cost?"_
**Model answer:** Standardize on one naming convention (`<registry>/<team>/<service>`) and a mandatory tag/label schema enforced by CI lint and admission policy that rejects mutable tags. Make the source of truth a primary registry and replicate digests (not tags) to regional or secondary registries using replication rules or `crane copy`, so a digest resolves identically everywhere. Clusters pull through a regional pull-through cache so a primary outage affects only new digests, and critical base images are mirrored internally to remove dependence on Docker Hub limits. Cost is controlled by retention policies plus lifecycle rules, same-region pulls to avoid egress, and layer reuse through shared base images. Policy-as-code enforces signature and provenance verification regardless of which registry served the image.
_What the interviewer is probing for:_ Fleet-scale thinking: replication by digest, availability design, supply-chain policy and cost.

## 12. Common Misconceptions

- "`latest` means the most recent image." It is a plain tag with no special semantics beyond being the default.
- "A tag identifies one image forever." Tags can be moved or overwritten; only digests are immutable.
- "`docker tag` copies the image." It creates an additional reference only.
- "Deleting a tag deletes the image data." Blobs and the manifest remain until garbage collection, and other tags may reference them.
- "Pushing uploads the whole image each time." Only layers missing from the repository (or registry, via mount) are sent.
- "If I give both tag and digest, the tag is verified." Docker resolves by digest and ignores the tag.

## 13. 🔑 Key Takeaways

- Reference = `host/repo:tag@digest`; only the digest is immutable.
- Build once, push a unique tag, promote by retagging the same digest.
- Deploy by digest; keep floating tags for humans.
- Use `buildx imagetools create` or `crane copy` to preserve multi-arch indexes.
- Enable tag immutability for release tags and pin base images by digest.
- Retention and deployment must agree: never delete a digest that production runs.

## 14. Related Concepts & What's Next

Related: image anatomy and manifests ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), Docker Hub limits ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)), private and cloud registries ([§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)), authentication ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)), signing ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Next, [§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md) covers how old tags and untagged manifests are expired and how registry storage is actually reclaimed.

**Next Section:** [§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md) — `Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md`
