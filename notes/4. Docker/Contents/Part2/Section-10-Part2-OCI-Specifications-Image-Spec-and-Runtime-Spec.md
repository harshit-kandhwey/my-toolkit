# Section 10 (Part 2): OCI Specifications: Image Spec and Runtime Spec

## 1. Definition

**Plain language:** The Open Container Initiative (OCI) specifications are the written contracts that make containers portable between tools. One contract says what an *image* looks like on disk and in a registry; another says how a *runtime* must start a container from an unpacked image; a third says how images are pushed and pulled over HTTP. Because of these contracts, an image built by Docker can be run by containerd, CRI-O, or Podman, and stored in any compliant registry.

**Precise definition:** The OCI, hosted by the Linux Foundation, maintains three specifications:

- **Image Spec** (`image-spec`): defines the **image manifest**, **image index** (multi-platform), **image configuration**, and **filesystem layers** (tar archives, usually gzip or zstd compressed), all addressed by content digest (`sha256:...`).
- **Runtime Spec** (`runtime-spec`): defines the **filesystem bundle** (a directory holding `config.json` plus a `rootfs/`) and the **container lifecycle** (`create`, `start`, `kill`, `delete`, `state`). `runc` is the reference implementation ([§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)).
- **Distribution Spec** (`distribution-spec`): defines the HTTP API a registry exposes for pushing and pulling blobs and manifests.

> 💡 **Tip:** Think of the three specs as "what is stored" (image), "how it is run" (runtime), and "how it is moved" (distribution). Docker's own pre-OCI formats (image v1.x, schema2) were the seed; the OCI versions are the neutral descendants.

## 2. Why This Matters

- **Vendor neutrality:** Images are not locked to Docker Engine. Kubernetes nodes running containerd or CRI-O pull the same images you built locally ([§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).
- **Reproducibility by digest:** Content addressing means `image@sha256:...` refers to exactly one set of bytes, which underpins supply-chain tooling such as signing and SBOM attachment.
- **Debuggability:** Knowing that an image is just a manifest, a config JSON, and tarballs lets you inspect and repair images with `tar`, `jq`, and `skopeo` when the daemon is unavailable.
- **Runtime substitution:** Because `config.json` is standardized, sandboxed runtimes (gVisor `runsc`, Kata) can replace `runc` without changing how images are built.
- **Interview and DCA relevance:** "What is in an image?" and "What does runc consume?" are standard questions.

## 3. Prerequisites and Dependencies

Read [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (engine architecture: dockerd, containerd, runc) first, since the runtime spec is what containerd hands to runc. [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) covers the API through which images are pulled. [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md) and [§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) explain the namespaces and cgroups that the runtime spec's `linux` section configures, and [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) explains how layers are stacked into a rootfs. Basic familiarity with JSON, tar, and SHA-256 hashing is assumed.

## 4. Architecture / Conceptual Diagram

```text
                 OCI Image (stored in a registry or on disk)

   image index (optional, multi-platform)
   ┌──────────────────────────────────────────────┐
   │ manifests: [ linux/amd64 ──► sha256:aaa...   │
   │              linux/arm64 ──► sha256:bbb... ] │
   └─────────────────────┬────────────────────────┘
                         ▼
   image manifest (sha256:aaa...)
   ┌──────────────────────────────────────────────┐
   │ config ──────────────► image config JSON     │
   │ layers: [ L1, L2, L3 ] ──► tar+gzip blobs    │
   └──────────────────────────────────────────────┘

        unpack layers (§13)          generate from image config
              │                                │
              ▼                                ▼
   ┌───────────────────────── OCI Runtime Bundle ───────────────┐
   │  rootfs/        (merged filesystem)                        │
   │  config.json    (process, mounts, namespaces, cgroups ...) │
   └───────────────────────────┬────────────────────────────────┘
                               ▼
                    runc create / start ──► container process
```

The image is *data at rest*; the bundle is the *input to a runtime*. containerd converts one into the other.

## 5. Hands-On

### 5.1 Inspect an image manifest with the CLI

```bash
$ docker pull alpine:3.20
$ docker image inspect alpine:3.20 --format '{{.Id}} {{.Os}}/{{.Architecture}}'
sha256:91ef0af61f39ece4d6710e465df5ed6ca12112358344fd51ae6a3b886634148b linux/amd64
$ docker buildx imagetools inspect alpine:3.20
Name:      docker.io/library/alpine:3.20
MediaType: application/vnd.oci.image.index.v1+json
Digest:    sha256:beefdbd8a1da6d2915566fde36db9db0b524eb737fc57cd1367effd16dc0d06d

Manifests:
  Name:      docker.io/library/alpine:3.20@sha256:...
  MediaType: application/vnd.oci.image.manifest.v1+json
  Platform:  linux/amd64
  ...
```

The top-level object is an OCI **image index**; each platform entry points at its own manifest. (Digests shown are illustrative; yours will differ as tags move.)

### 5.2 Export an image and read its structure

```bash
$ docker save alpine:3.20 -o alpine.tar
$ mkdir alpine-oci && tar -xf alpine.tar -C alpine-oci
$ ls alpine-oci
blobs  index.json  manifest.json  oci-layout  repositories
$ cat alpine-oci/oci-layout
{"imageLayoutVersion":"1.0.0"}
$ jq . alpine-oci/index.json
```

`oci-layout` and `index.json` are the marker files of the OCI image layout; `manifest.json` is Docker's legacy compatibility file. (Recent Docker versions using the containerd image store write this layout; older engines emit only the legacy format, in which case `manifest.json` and `<id>.json` are present instead.)

### 5.3 Follow digests to the config and layers

```bash
$ M=$(jq -r '.manifests[0].digest' alpine-oci/index.json | cut -d: -f2)
$ jq . alpine-oci/blobs/sha256/$M
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.manifest.v1+json",
  "config": {
    "mediaType": "application/vnd.oci.image.config.v1+json",
    "digest": "sha256:...",
    "size": 1471
  },
  "layers": [
    {
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
      "digest": "sha256:...",
      "size": 3623807
    }
  ]
}
```

If the first manifest entry is itself an index, repeat once more to reach the platform manifest. Then read the config blob:

```bash
$ jq '{architecture, os, cmd: .config.Cmd, diff_ids: .rootfs.diff_ids}' \
    alpine-oci/blobs/sha256/<config-digest>
{
  "architecture": "amd64",
  "os": "linux",
  "cmd": ["/bin/sh"],
  "diff_ids": ["sha256:..."]
}
```

Note the two digests per layer: the manifest digest is of the *compressed* blob; `diff_ids` in the config are of the *uncompressed* tar.

### 5.4 Pull image manifests without Docker (skopeo)

```bash
$ skopeo inspect docker://docker.io/library/alpine:3.20 | jq '.Digest, .Layers'
$ skopeo copy docker://alpine:3.20 oci:alpine-layout:3.20
```

`skopeo copy ... oci:` writes a pure OCI layout directory, no daemon needed.

### 5.5 Build an OCI runtime bundle and run it with runc

```bash
$ mkdir -p bundle/rootfs && cd bundle
$ docker export $(docker create alpine:3.20) | tar -C rootfs -xf -
$ runc spec            # generates a default config.json
$ jq '.process.args, .process.terminal, .root.path' config.json
[
  "sh"
]
true
"rootfs"
$ sudo runc run demo
/ # hostname
runc
/ # exit
```

`runc spec` writes the runtime-spec `config.json`; `runc run` creates and starts the container from the bundle. No image, registry, or daemon was involved.

### 5.6 Inspect the runtime-spec sections

```bash
$ jq '.linux.namespaces, .linux.resources // "none"' config.json
[
  {"type": "pid"},
  {"type": "network"},
  {"type": "ipc"},
  {"type": "uts"},
  {"type": "mount"}
]
"none"
```

Each entry maps directly to a namespace that runc will `unshare` ([§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md)); `linux.resources` is where cgroup limits go ([§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)).

## 6. Production Usage Notes

- **Pin by digest** (`image@sha256:...`) in Kubernetes manifests and Compose files for deployments that must be bit-for-bit reproducible; tags are mutable.
- **Multi-platform images:** publish an image index so `arm64` (Graviton, Apple silicon) and `amd64` nodes both resolve correctly. `docker buildx build --platform linux/amd64,linux/arm64 --push` produces one.
- **Registry compatibility:** any Distribution-spec registry (Docker Hub, ECR, GHCR, Harbor, Artifactory) accepts the same images; `oras` and `cosign` use OCI artifacts (non-image manifests) to attach signatures and SBOMs.
- **Alternate runtimes** are selected per container (`docker run --runtime=runsc`) or per Kubernetes RuntimeClass; this works because they all consume the same bundle format.
- **Compression:** zstd layers are supported by the OCI image spec and by recent engines, but older clients cannot pull them; check consumers before switching.

## 7. Security Considerations

- **Digest verification** is the integrity mechanism: clients hash downloaded blobs and compare with the manifest. A tag alone provides no integrity guarantee.
- **Signatures are not part of the core image spec.** Sigstore/cosign and Notary v2 store signatures as separate OCI artifacts referencing the image digest; verification must be enforced by admission policy.
- **`config.json` is the security boundary description:** capabilities, seccomp profile, masked paths, and `noNewPrivileges` all live there. A permissive `config.json` (e.g. `--privileged`) removes those protections.
- **Untrusted layers:** tar extraction must guard against path traversal and symlink tricks; use maintained runtimes rather than hand-rolled unpackers.
- **Secrets baked into layers** remain readable from any layer blob even if a later layer deletes them ([§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `no matching manifest for linux/arm64/v8 in the manifest list entries` | Image index lacks your platform | Rebuild multi-platform or use `--platform linux/amd64` (emulated) |
| `manifest unknown` | Tag or digest does not exist in registry | Verify with `docker buildx imagetools inspect` or `skopeo inspect` |
| `unsupported media type application/vnd.oci.image.index.v1+json` | Very old client or registry | Upgrade client, or push Docker schema2 format |
| `runc run` fails: `rootfs (/...) does not exist` | Bundle missing `rootfs/` or wrong `root.path` | Ensure `config.json` `root.path` matches directory |
| `layer does not match digest` / `unexpected EOF` | Corrupted or truncated blob | Re-pull; check proxy or mirror |
| Image digest differs between registries | Manifest was re-encoded or recompressed | Compare `diff_ids`; digest of manifest is not preserved by all copy tools |

## 9. Best Practices

- Reference production images by digest, and keep a human-readable tag alongside for readability (`image:1.4.2@sha256:...`).
- Build multi-platform images with an image index.
- Use `skopeo`, `crane`, or `oras` for registry-side operations that do not need a daemon.
- Attach SBOMs and signatures as OCI referrers rather than embedding them in the image.
- Keep `config.json` generation in the engine; only hand-edit bundles for experiments.

## 10. Common Anti-Patterns / Mistakes

- Deploying `:latest` and assuming it is stable.
- Confusing the manifest digest (compressed layers) with the image ID (digest of the config blob).
- Assuming `docker save` output is always OCI layout; older engines write a Docker-specific archive.
- Editing an image's tarballs and forgetting to update the digests in the manifest and config.
- Treating "OCI-compliant" as "secure": compliance describes format, not content.

## 11. Interview Questions

**🎯 Beginner:** _"What is the OCI, and what makes up an OCI image?"_
**Model answer:** The Open Container Initiative is a Linux Foundation project standardizing image, runtime, and distribution formats so containers are portable across tools. An image is a manifest, a config JSON, and one or more layer tarballs, optionally referenced from an image index for multiple platforms. Everything is content-addressed by digest. runc is the reference runtime implementing the runtime spec.
_What the interviewer is probing for:_ Knowing the three specs and the image structure.

**🎯 Intermediate:** _"You pull an image and see two different digests: the RepoDigest and the image ID. Why, and why do layers also have two digests?"_
**Model answer:** The RepoDigest is the digest of the manifest as stored in the registry; the image ID is the digest of the config blob, so they differ. Layers have a compressed digest listed in the manifest (transport integrity) and an uncompressed diff_id in the config, used to compute chain IDs. Inspect with `docker inspect` and `skopeo inspect --raw docker://nginx | jq`.
_What the interviewer is probing for:_ Understanding content-addressing details.

**🎯 Senior:** _"A registry tag was re-pushed and production behavior changed. How do you explain and prevent this, and how would you inspect the image without a daemon?"_
**Model answer:** Tags are mutable pointers in the registry; a digest is a hash of the content, so new content means a new digest. Prevent it by deploying by digest (`image@sha256:...`) and signing digests. Without a daemon, use `skopeo copy docker://img oci:layout:tag` then `jq` through `index.json`, the manifest, and config blobs, or `skopeo inspect`. Compare digests across environments to find the drift.
_What the interviewer is probing for:_ Explaining mutability and using daemonless tooling.

**🎯 Architect:** _"Design a supply-chain policy built on OCI artifacts, and describe the migration risks of moving to OCI media types and zstd layers."_
**Model answer:** Sign image digests with cosign, attach SBOMs and provenance as referrers, enforce verification in admission control, and deploy by digest only. Risks in migrating from Docker schema2 to OCI manifests and zstd layers: older clients, registries, and scanners may not parse the new media types, so stage rollouts and test each consumer first. OCI reduces format lock-in, but lock-in remains in build tooling, registry features, and orchestration APIs.
_What the interviewer is probing for:_ Applying the spec to supply-chain security and realistic migration planning.
## 12. Common Misconceptions

- **"OCI is a runtime."** It is a set of specifications; runc, crun, and youki are implementations.
- **"An image is one big file."** It is a graph of small JSON documents and layer blobs joined by digests.
- **"Docker images are not OCI images."** Modern Docker builds and pushes OCI-compatible manifests, and Docker can pull both formats.
- **"The image ID is the manifest digest."** The image ID is the digest of the config blob; the manifest digest (shown as `RepoDigests`) is different.
- **"A signed tag is safe."** Signatures should bind to the digest, since tags move.

## 13. 🔑 Key Takeaways

- Three OCI specs: Image, Runtime, Distribution.
- Images are content-addressed: index ► manifest ► config + layers.
- A runtime bundle is `rootfs/` plus `config.json`; runc consumes it.
- Pin by digest for reproducibility and integrity.
- `skopeo`, `jq`, and `runc spec` let you work with images and bundles without a daemon.
- Compliance is about format; security policy is still your job.

## 14. Related Concepts & What's Next

Related: [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (where containerd and runc sit), [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) (API used to pull images), [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) (how layers become a merged rootfs), [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) (containerd and CRI). Later Docker topics cover image anatomy in depth, registries, buildx multi-platform builds, and image signing with Docker Content Trust and cosign.

**Next Section:** [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md) — `Section-11-Part2-Linux-Namespaces-Deep-Dive.md`
