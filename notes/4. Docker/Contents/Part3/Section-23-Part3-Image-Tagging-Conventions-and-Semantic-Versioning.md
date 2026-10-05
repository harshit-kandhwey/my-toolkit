# Section 23 (Part 3): Image Tagging Conventions and Semantic Versioning

## 1. Definition

**Plain language:** A tag is a human-friendly label attached to an image so you can refer to it without memorizing a hash. `nginx:1.27` and `nginx:latest` point at images; the tag is just the part after the colon.

**Precise definition:** An image reference has the form `[registry[:port]/][namespace/]repository[:tag][@digest]`. A **tag** is a mutable pointer, stored by the registry, from a string (max 128 characters, `[A-Za-z0-9_.-]`, not starting with `.` or `-`) to a manifest **digest** ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)). A **digest** (`sha256:...`) is the content hash of the manifest and is immutable. If no tag is given, Docker assumes `latest`, which has no special meaning to the registry: it is only a default name. **Semantic versioning** (`MAJOR.MINOR.PATCH`) is the most common scheme for tag names, allowing consumers to pin at the precision they want.

> 💡 **Tip:** Tags are pointers, digests are identities. Any decision about reproducibility or security should be made against the digest.

## 2. Why This Matters

- **Reproducibility:** `FROM python:3.12` today and six months from now can resolve to different bits; only a digest guarantees identical content.
- **Rollbacks:** If `myapp:latest` is overwritten on every release, you cannot say what was running last Tuesday. Immutable version tags make rollback a redeploy of a known tag.
- **Supply chain safety:** Mutable tags can be re-pointed by anyone with push rights (or an attacker who compromises them). Digest pinning limits that blast radius.
- **Cache behavior:** Kubernetes and Docker decide whether to pull based on the tag (`latest` implies `Always` pull in Kubernetes) and on local presence.
- **Interviews:** "Why is `latest` bad?" is one of the most common Docker questions.

## 3. Prerequisites and Dependencies

Requires understanding of manifests and digests ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) and of the OCI image and distribution specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). The build command that applies tags is covered in [§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md), and inspecting which tags/digests an image carries is covered in [§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md). Base image choice, which interacts strongly with tag strategy, is in [§22](Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md).

## 4. Architecture / Conceptual Diagram

```text
   Registry repository: myorg/api

   Tags (mutable pointers)                 Manifests (immutable)

   1.4.2  ─────────────┐
   1.4    ─────────────┼───────────────►  sha256:9f2c...a1   (build of 1.4.2)
   1      ─────────────┤
   latest ─────────────┘

   1.4.1  ───────────────────────────────► sha256:41be...07   (older patch)

   1.5.0-rc.1 ───────────────────────────► sha256:c8d0...5e   (pre-release)

   sha-3fa9c21 ──────────────────────────► sha256:9f2c...a1   (same build, git SHA tag)

   Releasing 1.4.3 moves tags 1.4, 1 and latest to a new digest;
   1.4.2 and sha-3fa9c21 keep pointing at sha256:9f2c...a1.
```

- **Multiple tags, one digest:** Tags are cheap aliases; one manifest can carry many.
- **Rolling tags** (`1`, `1.4`, `latest`) move on each release. **Fixed tags** (`1.4.2`, `sha-<commit>`) should never move by policy, although the registry will allow it unless immutability is enabled.

## 5. Hands-On

### 5.1 Tagging and pushing multiple tags

```bash
$ docker build -t myorg/api:1.4.2 .
$ docker tag myorg/api:1.4.2 myorg/api:1.4
$ docker tag myorg/api:1.4.2 myorg/api:1
$ docker tag myorg/api:1.4.2 myorg/api:latest
$ docker images myorg/api
REPOSITORY    TAG      IMAGE ID       CREATED         SIZE
myorg/api     1.4.2    5d1e0c7a9b3f   2 minutes ago   142MB
myorg/api     1.4      5d1e0c7a9b3f   2 minutes ago   142MB
myorg/api     1        5d1e0c7a9b3f   2 minutes ago   142MB
myorg/api     latest   5d1e0c7a9b3f   2 minutes ago   142MB
$ docker push --all-tags myorg/api
```

All four tags share the same IMAGE ID, so no extra disk is used.

### 5.2 Tagging with the git commit SHA

```bash
$ SHA=$(git rev-parse --short=7 HEAD)
$ docker build -t myorg/api:sha-$SHA -t myorg/api:1.4.2 .
```

Passing `-t` more than once tags at build time. The SHA tag gives exact traceability from a running container back to source.

### 5.3 Finding the digest and pulling by digest

```bash
$ docker push myorg/api:1.4.2
1.4.2: digest: sha256:9f2c7be1d3a04c6e5b8f1a2d7c90e4b36f5a8d1c2e7b9043a6d5f10c8e2b7a1c size: 1573
$ docker inspect --format '{{index .RepoDigests 0}}' myorg/api:1.4.2
myorg/api@sha256:9f2c7be1d3a04c6e5b8f1a2d7c90e4b36f5a8d1c2e7b9043a6d5f10c8e2b7a1c
$ docker pull myorg/api@sha256:9f2c7be1d3a04c6e5b8f1a2d7c90e4b36f5a8d1c2e7b9043a6d5f10c8e2b7a1c
```

### 5.4 Pinning both tag and digest in a Dockerfile

```dockerfile
FROM python:3.12.5-slim@sha256:<digest-of-that-tag>
```

When both are present, Docker resolves by digest and ignores the tag; the tag remains as a human-readable hint. Tools such as Renovate or Dependabot can then bump both together.

### 5.5 Watching a tag move

```bash
$ docker pull alpine:3.20
$ docker inspect --format '{{index .RepoDigests 0}}' alpine:3.20
alpine@sha256:<digest-A>
# weeks later, after a patch rebuild upstream
$ docker pull alpine:3.20
$ docker inspect --format '{{index .RepoDigests 0}}' alpine:3.20
alpine@sha256:<digest-B>
```

The tag stayed the same; the digest changed. That is the mutability that pinning by digest protects against.

### 5.6 Removing a tag versus deleting an image

```bash
$ docker rmi myorg/api:latest
Untagged: myorg/api:latest
```

`rmi` on one of several tags only untags; layers are deleted only when the last tag (and no container) references the image.

## 6. Production Usage Notes

- A common scheme: publish `MAJOR.MINOR.PATCH` (immutable), rolling `MAJOR.MINOR` and `MAJOR`, plus `sha-<commit>` from CI. Deploy manifests reference the fixed tag or the digest, never `latest`.
- **Variant suffixes** follow the upstream convention: `1.4.2-alpine`, `1.4.2-slim`, `-bookworm`. Keep the version first and the variant last.
- **Multi-arch:** A tag like `1.4.2` typically points to a manifest list (image index) that fans out to per-platform manifests; the digest of the index differs from each platform image's digest.
- **Registry immutability settings** (for example Amazon ECR tag immutability, Harbor immutable tag rules) enforce that fixed tags cannot be overwritten. Enable them for release repositories.
- GitOps tooling (Argo CD, Flux) and Kubernetes manifests should record the tag or digest that was actually promoted, so environment state is auditable.
- Metadata: pair tags with OCI labels such as `org.opencontainers.image.revision` and `org.opencontainers.image.version` (see WORKDIR/ENV/ARG/LABEL in [§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).
- Pre-releases follow SemVer: `2.0.0-rc.1`. Note that `+` (build metadata) is not a legal tag character, so use `_` or `-` instead, e.g. `1.4.2_build5`.

## 7. Security Considerations

- **Mutable tags are a trust gap:** whoever can push to the repository can silently change what `1.4.2` means. Restrict push rights, enable immutability, and sign images (Docker Content Trust or Sigstore cosign) so consumers verify identity.
- **Pin by digest** for base images in security-sensitive builds, and automate digest bumps so pinning does not freeze in unpatched CVEs.
- **Typosquatting:** A wrong namespace (`myorg` vs `my0rg`) pulls a different publisher's image. Prefer fully qualified references with your private registry hostname.
- **`latest` hides vulnerable versions:** scanners report on digests; a fleet running "latest" cannot be mapped to a version quickly during an incident.
- Do not embed secrets or internal hostnames in tag names; they are visible to anyone who can list tags.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `manifest for myorg/api:1.4.3 not found` | Tag never pushed, wrong registry, or typo | `docker push` the tag; check `docker images`; verify the registry host |
| Deployment runs old code after "re-pushing latest" | Node already has `latest` cached and `imagePullPolicy: IfNotPresent` | Use unique tags per build; or set pull policy `Always` |
| `invalid reference format` | Uppercase repository name, trailing `:`, illegal chars | Repository names must be lowercase; tags limited to allowed characters |
| `tag does not exist` on `docker tag` | Source reference is not present locally | Build or pull it first |
| Tag pushed but `docker images` shows `<none>` for TAG | A dangling image: a later build took the tag | Retag by IMAGE ID: `docker tag <id> repo:tag` |
| Push rejected: tag is immutable | Registry immutability policy | Publish a new version; never reuse a released tag |

## 9. Best Practices

- Use immutable, unique tags per build (SemVer and/or commit SHA); treat rolling tags as convenience only.
- Never deploy `latest` to production; do not rely on the implicit default in scripts.
- Record the digest at build time and promote that exact digest across dev, staging, and prod (promote, do not rebuild).
- Pin third-party base images by tag plus digest and update them through automation.
- Enable registry tag immutability for release repositories.
- Sign images and verify signatures at admission time.
- Keep tag naming consistent across repositories so tooling and humans can predict it.
- Clean up old tags with retention/lifecycle policies to control storage cost.

## 10. Common Anti-Patterns / Mistakes

- **Only ever tagging `latest`:** no rollback path, no traceability.
- **Overwriting a released version tag** (`1.4.2` re-pushed with a fix): different hosts now run different bits under one name.
- **Rebuilding per environment** (`myapp:staging`, `myapp:prod` built separately): what you tested is not what you shipped.
- **Assuming `latest` means newest:** it is only whatever was last pushed without an explicit tag, and can even be an older build.
- **Encoding environment in the tag** (`1.4.2-prod`) instead of promoting the same artifact.
- **Pinning by digest and never updating**, leaving known CVEs in place.
- **Date-only tags** (`20240915`) with no link to source version or commit.

## 11. Interview Questions

**🎯 Beginner:** _"You run `docker build -t api .` and `docker push api`. What tag was used, and how do you add a second tag?"_
**Model answer:** With no tag, Docker uses `latest`, which is just a default name with no special meaning and is not necessarily the newest image. Add a second name with `docker tag api:latest registry.example.com/team/api:1.4.2`, which creates another pointer to the same image ID. Push each tag separately or use `docker push --all-tags`.
_What the interviewer is probing for:_ That latest is only a default and tags are pointers.

**🎯 Intermediate:** _"Explain tag versus digest, and why does `latest` with Kubernetes cause stale or surprising deployments?"_
**Model answer:** A tag is a mutable pointer that can be moved to a new image, while a digest (`@sha256:...`) is the immutable hash of the manifest. Kubernetes defaults `imagePullPolicy` to Always for `latest` but IfNotPresent for other tags, so a repointed non-latest tag can leave nodes running different content. Use unique immutable tags or digests. A good SemVer scheme keeps the full `1.4.2` fixed, moves rolling `1.4` and `1` tags, and adds the git SHA (`1.4.2-abc1234`) for traceability.
_What the interviewer is probing for:_ Mutability semantics and a workable tagging scheme.

**🎯 Senior:** _"A rolling tag `1.4` was silently repointed and caused an outage. How do you prove staging matches prod, and prevent recurrence?"_
**Model answer:** Build once, record the digest from `docker buildx imagetools inspect` or push output, and promote by digest (or re-tag the same digest) so prod runs exactly what staging tested. Prevent repointing by enabling registry tag immutability, restricting push credentials to CI, pinning deployments by digest, signing with cosign, and enforcing signature and digest checks via admission policy (Kyverno or Gatekeeper). Alert on tag-move events from registry audit logs.
_What the interviewer is probing for:_ Controls that give integrity across environments.

**🎯 Architect:** _"Design an image naming and retention policy for 200 services across multiple regions, and weigh digest pinning against tag pinning."_
**Model answer:** Use a registry hierarchy (`registry/team/service`), mandatory SemVer plus SHA tags, immutable release tags, and replication by digest to regional registries. Attach SBOMs and provenance attestations, and apply lifecycle rules that keep released tags and expire untagged or snapshot images after N days. Digest pinning gives integrity and reproducibility but is unreadable and needs automation to stay patched; tags are readable but mutable. A pragmatic answer is human-readable tag plus digest in manifests, updated by a bot, with base-image rebuild pipelines.
_What the interviewer is probing for:_ Governance design and honest treatment of trade-offs.

## 12. Common Misconceptions

- "`latest` is the newest version." It is only the default tag name.
- "Tags are immutable." Not unless the registry enforces it.
- "Deleting a tag deletes the image." It removes a pointer; the manifest and layers may persist and other tags may still reference them.
- "The digest shown locally is the image ID." The image ID is the hash of the image config; the repo digest is the hash of the manifest. They differ.
- "SemVer build metadata (`+`) works in tags." `+` is not permitted.

## 13. 🔑 Key Takeaways

- A tag is a mutable pointer; a digest is the immutable identity.
- Tag every build uniquely (SemVer and/or commit SHA) and deploy those, never `latest`.
- Build once and promote the same digest through environments.
- Rolling tags (`1.4`, `1`) are conveniences for consumers, not deployment references.
- Enable registry immutability and image signing for release repositories.
- Pin base images by digest, and automate updates.

## 14. Related Concepts & What's Next

Related: image manifests and digests ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), OCI specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), base image selection ([§22](Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)), labels ([§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)). Next, [§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md) covers building images with `docker build` and BuildKit, where `-t` applies the tags discussed here, and [§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md) covers inspecting images to read their tags, digests, and history.

**Next Section:** [§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md) — `Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md`
