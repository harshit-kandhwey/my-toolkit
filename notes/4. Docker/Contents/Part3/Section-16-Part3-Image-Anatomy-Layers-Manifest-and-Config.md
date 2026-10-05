# Section 16 (Part 3): Image Anatomy: Layers, Manifest, and Config

## 1. Definition

**Plain language:** A Docker image is not one big file. It is a small stack of compressed filesystem snapshots (layers) plus two tiny JSON documents: a **manifest** that lists the pieces, and a **config** that says how to run them. Everything you `docker pull` is just those parts, fetched by content hash.

**Precise definition:** An OCI/Docker image consists of (1) an ordered set of **layer** blobs, each a tar archive (usually gzip-compressed) holding the filesystem changes introduced by one build step; (2) an **image configuration** JSON blob containing runtime defaults (`Env`, `Cmd`, `Entrypoint`, `WorkingDir`, `User`, `ExposedPorts`, `Labels`), the `rootfs.diff_ids` (uncompressed layer digests) and build `history`; and (3) an **image manifest** JSON that references the config and each layer by `sha256` digest, size and media type. Multi-platform images add a top-level **image index** (manifest list) that maps platforms to per-platform manifests. These formats are standardized by the OCI image spec ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). Every object is **content-addressable**: its identifier is the SHA-256 of its bytes, so it cannot change without changing its name.

> 💡 **Tip:** The image ID shown by `docker images` is the digest of the *config* blob, not of the manifest. The digest shown as `RepoDigests` / `@sha256:...` in a registry is the digest of the *manifest* (or index). They are different values.

## 2. Why This Matters

- **Layer caching and reuse** follow directly from layer identity. Two images sharing a base share those layer blobs on disk and on the wire.
- **Image size is the sum of layers.** Deleting a file in a later layer does not shrink the image, because earlier layers are immutable.
- **Digest pinning** (`image@sha256:...`) gives reproducible, tamper-evident deploys; tags are mutable, digests are not.
- **Debugging pulls and pushes** ("layer already exists", "manifest unknown", wrong architecture) requires knowing which object is which.
- **Security scanning and SBOMs** operate layer by layer; secrets baked into any layer stay recoverable.
- **Interviews** routinely ask what an image really is and why layers are immutable.

## 3. Prerequisites and Dependencies

Requires the container-vs-image distinction from Part 1 ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)-[§7](../Part1/Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md)) and the OCI image and distribution specifications ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). Layers are stacked at run time by a union filesystem driver, covered in [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) (overlay2). The daemon and containerd components that store and unpack blobs are described in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) and [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md). The next section, [§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md), shows how Dockerfile instructions create these layers.

## 4. Architecture / Conceptual Diagram

```text
                 Image index (optional, multi-arch)
                 ┌───────────────────────────────────┐
                 │ linux/amd64 ──► sha256:aaa... (manifest)
                 │ linux/arm64 ──► sha256:bbb... (manifest)
                 └───────────────────────────────────┘
                                 │ (pick platform)
                                 ▼
                    Image manifest  sha256:aaa...
                 ┌──────────────────────────────────┐
                 │ config ─────► sha256:ccc... (JSON)│
                 │ layers[0] ──► sha256:111... (tar.gz)
                 │ layers[1] ──► sha256:222... (tar.gz)
                 │ layers[2] ──► sha256:333... (tar.gz)
                 └──────────────────────────────────┘
                                 │
        ┌────────────────────────┴───────────────┐
        ▼                                        ▼
  Config blob (image ID = its sha256)      Layer blobs (bottom ► top)
  ┌─────────────────────────────┐          ┌───────────────┐ 3 app code
  │ config.Env / Cmd / User ... │          ├───────────────┤ 2 deps
  │ rootfs.diff_ids [d1,d2,d3]  │          ├───────────────┤ 1 base OS
  │ history [step per layer]    │          └───────────────┘
  └─────────────────────────────┘
```

- **Compressed vs uncompressed digests differ.** The manifest lists digests of the *compressed* blobs; the config's `diff_ids` list digests of the *uncompressed* tars. Both identify the same layer.
- **A layer is a diff, not a full snapshot.** It records added/modified files and "whiteout" markers for deletions.
- **Metadata-only steps** (`ENV`, `CMD`, `LABEL`) add history entries with `empty_layer: true` and no blob.

## 5. Hands-On

### 5.1 List Layers with `docker history`

**Purpose:** See which build step produced each layer and how large it is.

```bash
docker pull alpine:3.20
docker history alpine:3.20
```

```text
IMAGE          CREATED       CREATED BY                                      SIZE      COMMENT
a606584aa9aa   5 weeks ago   CMD ["/bin/sh"]                                 0B        buildkit.dockerfile.v0
<missing>      5 weeks ago   ADD alpine-minirootfs-3.20.3-x86_64.tar.gz /    7.8MB     buildkit.dockerfile.v0
```

`0B` rows are metadata-only steps with no layer blob.

### 5.2 Read the Config and Layer Digests

**Purpose:** Inspect the config blob's view of the image.

```bash
docker image inspect alpine:3.20 --format '{{json .RootFS}}'
docker image inspect alpine:3.20 --format '{{.Id}}'
docker image inspect alpine:3.20 --format '{{json .Config.Cmd}}'
```

```text
{"Type":"layers","Layers":["sha256:63ca1fbb43ae5034640e5e6cb3e083e05c290072c5366fcaa9d62435a4cced85"]}
sha256:a606584aa9aa875552092ec9e1d62cb98d486f51f389609914039aabd9414687
["/bin/sh"]
```

`.RootFS.Layers` are the uncompressed `diff_ids`; `.Id` is the config digest.

### 5.3 Fetch the Raw Manifest

**Purpose:** View the registry-side manifest or index without pulling.

```bash
docker buildx imagetools inspect alpine:3.20
docker manifest inspect alpine:3.20 | head -30
```

```text
Name:      docker.io/library/alpine:3.20
MediaType: application/vnd.oci.image.index.v1+json
Digest:    sha256:1e42bbe2508154c9126d48c2b8a75420c3544343bf86fd041fb7527e017a4b4a

Manifests:
  Name:      docker.io/library/alpine:3.20@sha256:...
  Platform:  linux/amd64
  Name:      docker.io/library/alpine:3.20@sha256:...
  Platform:  linux/arm64/v8
```

(Digests vary by release.)

### 5.4 Unpack an Image to See the Real Files

**Purpose:** Prove an image is just tarballs and JSON.

```bash
docker save alpine:3.20 -o alpine.tar
mkdir alpine-oci && tar -xf alpine.tar -C alpine-oci
ls alpine-oci alpine-oci/blobs/sha256
cat alpine-oci/index.json
```

```text
blobs  index.json  manifest.json  oci-layout  repositories
1e42bbe25081...  63ca1fbb43ae...  a606584aa9aa...
{"schemaVersion":2,"mediaType":"application/vnd.oci.image.index.v1+json","manifests":[{...}]}
```

The layout of `docker save` output varies by Docker version (newer engines with the containerd image store emit OCI layout as shown; older ones emit `<id>/layer.tar` directories).

### 5.5 Watch Layer Sharing

```bash
docker pull node:20-alpine
docker pull node:20-alpine3.20
```

```text
20-alpine3.20: Pulling from library/node
Digest: sha256:...
Status: Image is up to date for node:20-alpine3.20
```

Identical digests mean the second pull downloads nothing.

## 6. Production Usage Notes

- **Deploy by digest** in production manifests (or resolve tag to digest in CI) to avoid tag drift.
- **Layer order affects cache efficiency and pull size.** Put rarely changing layers first.
- **Registries deduplicate** blobs across repositories on the same registry; cross-repo mounts avoid re-uploading.
- **Pull time** is dominated by the number and size of *new* layers; concurrent layer download defaults are configurable in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Multi-arch images** need an index; pulling on the wrong architecture yields `exec format error` at run time.
- Since Docker Engine 29 the containerd image store is the default on fresh installs; on older setups the classic graph driver store is used, and `docker image ls` semantics (index vs manifest) differ slightly.

## 7. Security Considerations

- **Layers are immutable, so secrets persist.** `RUN rm secret.txt` leaves the file in the earlier layer; anyone with the image can extract it.
- **Content addressing gives integrity**, but not authenticity. Use signatures (Docker Content Trust or Sigstore/cosign) to prove who built a digest.
- **Config blob leaks build info.** `history` shows full commands, including any `ARG`/`ENV` values passed inline.
- **Scanners read layers**; stale base layers carry inherited CVEs even if your layer is clean.
- **Untrusted images**: never `docker load` tarballs from unknown sources without inspecting them first.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `manifest unknown` on pull | Tag or digest does not exist in that repo | Verify with `docker buildx imagetools inspect`; check spelling and registry |
| `no matching manifest for linux/arm64/v8` | Index lacks that platform | Use `--platform linux/amd64` or rebuild multi-arch |
| `exec format error` at run | Image arch differs from host | Pull correct platform; check `docker image inspect --format '{{.Architecture}}'` |
| Image "didn't shrink" after `rm` | File removed in later layer only | Delete in the same `RUN` or use multi-stage builds |
| Digest differs between registry and `.Id` | Manifest digest vs config digest | Compare `RepoDigests` to registry; `.Id` is config |
| `missing layer` after `docker load` | Corrupt or partial tar | Re-export with `docker save`, verify checksums |

## 9. Best Practices

- Pin production images by digest and keep the tag as a human-readable comment.
- Keep layers purposeful: one logical concern per layer, cleanup in the same layer that created the mess.
- Order layers from least to most frequently changing.
- Inspect with `docker history --no-trunc` and `docker buildx imagetools inspect` before shipping.
- Build multi-arch indexes when targets include ARM.
- Store SBOM and provenance attestations alongside the image digest.

## 10. Common Anti-Patterns / Mistakes

- Assuming `docker rmi` of a tag deletes layers still referenced by other tags.
- Deploying `:latest` and expecting reproducibility.
- Copying credentials into a layer and "deleting" them afterwards.
- Confusing image ID with manifest digest in scripts and admission policies.
- Squashing everything into one layer without considering cache and pull benefits.

## 11. Interview Questions

**🎯 Beginner:** _"What is inside a Docker image?"_
**Model answer:** An image is a set of layer tarballs plus a manifest and a config JSON. The config holds metadata such as environment, entrypoint, cmd, exposed ports, and the ordered list of layer diff IDs, and the manifest lists digests of the config and layers. Everything is content addressed with sha256. You can view it with `docker image inspect`, `docker history`, or `docker save` and unpack the tar.
_What the interviewer is probing for:_ Awareness of manifest, config, and layers as separate objects.

**🎯 Intermediate:** _"What is the difference between a tag and a digest, and why should production deploys use digests?"_
**Model answer:** A tag such as `nginx:1.27` is a mutable pointer that the publisher can move to a different image at any time. A digest such as `nginx@sha256:...` is the hash of the manifest, so it always resolves to exactly the same content. Pinning digests gives reproducible deploys and protects against tag tampering or silent base-image changes, and `docker buildx imagetools inspect` shows the digest. The cost is manual updates, which tools such as Renovate or Dependabot can automate.
_What the interviewer is probing for:_ Immutability and supply-chain reasoning.

**🎯 Senior:** _"What is a multi-platform image, and how does a client decide which layers to pull?"_
**Model answer:** A multi-arch tag points to an OCI index or manifest list, which contains one manifest per platform (for example linux/amd64 and linux/arm64). The client matches its OS and architecture, or the `--platform` flag, fetches that platform's manifest, then the config and layers by digest. You can inspect with `docker manifest inspect` or `docker buildx imagetools inspect`. Building one with `docker buildx build --platform linux/amd64,linux/arm64 --push` needs QEMU emulation or native builders. Layers are not shared across platforms.
_What the interviewer is probing for:_ Understanding the index versus manifest structure.

**🎯 Architect:** _"An image was built with a secret copied in and then deleted in a later layer. Explain why that is still a leak and how you would fix and prevent it."_
**Model answer:** Layers are immutable tar diffs, so a later `RUN rm` only adds a whiteout, while the original layer with the secret is still in the image and recoverable with `docker save` or by reading layer blobs. Anyone who can pull the image can extract it, and the config's history may also expose build arguments. Fix by rotating the secret, rebuilding without it, and using BuildKit `RUN --mount=type=secret` or SSH mounts so the secret never enters a layer. Prevent recurrence with secret scanning in CI, image scanning, and multi-stage builds where the final stage copies only artifacts.
_What the interviewer is probing for:_ Deep understanding of layer immutability and secure build patterns.

## 12. Common Misconceptions

- "An image is a single file." It is a manifest, a config and N blobs.
- "The `docker images` ID is the digest shown on Docker Hub." Usually not; that is the manifest or index digest.
- "Removing a file in a later layer removes it from the image." It only hides it from the merged view.
- "Tags identify content." They are mutable labels.

## 13. 🔑 Key Takeaways

- Image = manifest + config + ordered layer tarballs, all addressed by SHA-256.
- Layers are immutable diffs; sizes add up and secrets persist.
- Image ID is the config digest; the registry digest is the manifest (or index) digest.
- Multi-arch relies on an index over per-platform manifests.
- Pin by digest for reproducibility and integrity.

## 14. Related Concepts & What's Next

Related: OCI image and distribution specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), overlay2 layer stacking ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), containerd content store ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)), daemon storage settings ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Next, [§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md) covers how `FROM`, `RUN`, `COPY` and `ADD` create these layers, and [§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md) returns to inspecting images in depth.

**Next Section:** [§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md) — `Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md`
