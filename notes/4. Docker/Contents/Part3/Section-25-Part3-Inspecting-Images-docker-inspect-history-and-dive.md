# Section 25 (Part 3): Inspecting Images: docker inspect, history, and dive

## 1. Definition

**Plain language:** Inspecting an image means looking inside it without running it: what it will run by default, which environment variables and ports it declares, which layers it contains, how big each layer is, and how it was built.

**Precise definition:** Image inspection uses the metadata in the image config and manifest ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) exposed by tooling. `docker inspect` (or `docker image inspect`) prints the full JSON config for an image. `docker history` lists each layer with the instruction that created it and its size. `dive` is a third-party TUI that unpacks each layer's filesystem diff and estimates wasted space. Related commands include `docker images` (with filters and formats), `docker manifest inspect` and `docker buildx imagetools inspect` (registry-side manifests), and `docker save` (export the layer tarballs).

> 💡 **Tip:** Everything `docker inspect` shows for an image comes from the config JSON built by your Dockerfile; if a default is wrong at runtime, look there first.

## 2. Why This Matters

- **Debugging:** Confirm `ENTRYPOINT`, `CMD`, `USER`, `WORKDIR`, `ENV`, and `EXPOSE` ([§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)-[§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)) actually landed as intended.
- **Size optimization:** `history` and `dive` reveal which instruction added 400 MB.
- **Security review:** Find leaked secrets in history, root users, and unexpected files before shipping.
- **Provenance:** Digests, labels, and creation time tie a running container to a build ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- **Interviews:** "How would you find out why an image is huge?" is a classic.

## 3. Prerequisites and Dependencies

Requires understanding of image layers, manifest and config ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), overlay2 layer storage ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), and the Dockerfile instructions that write config fields ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)-[§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)). Tags and digests are in [§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md) and how images are built is in [§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md). The CLI and API behind these commands are covered in [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md), and the OCI image format in [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md).

## 4. Architecture / Conceptual Diagram

```text
   Image (as stored)

   manifest ──► config JSON ───────────────► docker inspect
      │          ├─ Cmd, Entrypoint, Env, User, ExposedPorts, Labels
      │          ├─ rootfs.diff_ids  (ordered layer hashes)
      │          └─ history[]  (instruction per layer) ───► docker history
      │
      ├──► layer 1 tar (base)   ┐
      ├──► layer 2 tar (RUN)    ├─► unpacked and diffed ───► dive
      └──► layer 3 tar (COPY)   ┘    (per-layer file changes, wasted space)

   docker manifest inspect / buildx imagetools inspect
        └─► reads the manifest (or index) from the REGISTRY, no pull needed
   docker save
        └─► writes manifest + config + layer tars to a local tar archive
```

- `inspect` and `history` read only metadata; they are instant and need no extra tools.
- `dive` and `docker save` read actual layer contents.
- Registry-side commands inspect an image you have not pulled.

## 5. Hands-On

### 5.1 docker inspect with format templates

```bash
$ docker inspect myorg/api:1.4.2 --format '{{json .Config.Entrypoint}} {{json .Config.Cmd}}'
["/app/entrypoint.sh"] ["python","app.py"]
$ docker inspect myorg/api:1.4.2 --format '{{.Config.User}} {{.Config.WorkingDir}}'
appuser /app
$ docker inspect myorg/api:1.4.2 --format '{{json .Config.ExposedPorts}}'
{"8000/tcp":{}}
$ docker inspect myorg/api:1.4.2 --format '{{range .Config.Env}}{{println .}}{{end}}'
PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
PYTHON_VERSION=3.12.5
APP_ENV=production
```

Use `docker inspect` on an image reference (add `--type image` if a container has the same name).

### 5.2 Key fields in the JSON

```bash
$ docker inspect myorg/api:1.4.2 | head -40
[
    {
        "Id": "sha256:5d1e0c7a9b3f...",
        "RepoTags": ["myorg/api:1.4.2", "myorg/api:latest"],
        "RepoDigests": ["myorg/api@sha256:9f2c7be1d3a0..."],
        "Created": "2026-09-20T10:42:11.318Z",
        "Architecture": "amd64",
        "Os": "linux",
        "Size": 148213004,
        "Config": { "User": "appuser", "Labels": {"org.opencontainers.image.version": "1.4.2"}, ... },
        "RootFS": { "Type": "layers", "Layers": ["sha256:...", "sha256:...", "sha256:..."] }
    }
]
```

`Id` is the config hash; `RepoDigests` holds the manifest digest. `RootFS.Layers` lists the diff IDs in order. Values shown are illustrative.

### 5.3 docker history

```bash
$ docker history myorg/api:1.4.2
IMAGE          CREATED        CREATED BY                                      SIZE      COMMENT
5d1e0c7a9b3f   2 hours ago    CMD ["python" "app.py"]                         0B        buildkit.dockerfile.v0
<missing>      2 hours ago    COPY . . # buildkit                             1.2MB     buildkit.dockerfile.v0
<missing>      2 hours ago    RUN /bin/sh -c pip install --no-cache-dir ...   38.4MB    buildkit.dockerfile.v0
<missing>      2 hours ago    COPY requirements.txt . # buildkit              48B       buildkit.dockerfile.v0
<missing>      2 hours ago    WORKDIR /app                                    0B        buildkit.dockerfile.v0
<missing>      3 weeks ago    CMD ["python3"]                                 0B        buildkit.dockerfile.v0
<missing>      3 weeks ago    RUN /bin/sh -c set -eux; apt-get update ...     ...
```

`<missing>` is normal: with BuildKit, intermediate steps have no local image IDs. Add `--no-trunc` for full commands, and `--format "{{.Size}}\t{{.CreatedBy}}"` for compact output.

### 5.4 Spotting a leaked secret

```bash
$ docker history --no-trunc myorg/legacy:1.0 | grep -i -E 'token|password|secret'
<missing>   4 months ago   ENV API_TOKEN=abc123...   0B
```

Anything passed through `ENV`, `ARG` (recorded in history), or `RUN` command text is visible to anyone with the image. Rotate the credential and rebuild with secret mounts ([§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)).

### 5.5 dive: layer-by-layer exploration

```bash
$ dive myorg/api:1.4.2
# or without installing:
$ docker run --rm -it -v /var/run/docker.sock:/var/run/docker.sock wagoodman/dive:latest myorg/api:1.4.2
```

The TUI shows layers on the left and the file tree changes on the right. Keys include Tab (switch pane), Ctrl+U/Ctrl+A (toggle added/modified/removed views), and Ctrl+C to quit. The summary reports an image efficiency score and wasted bytes. In CI:

```bash
$ CI=true dive myorg/api:1.4.2 --ci-config .dive-ci
  efficiency: 98.7 %
  wastedBytes: 1843200 bytes (1.8 MB)
  userWastedPercent: 1.2 %
Result: PASS
```

Note that mounting the Docker socket gives the container root-equivalent host control; prefer a locally installed `dive` where possible.

### 5.6 Registry-side inspection and multi-arch manifests

```bash
$ docker buildx imagetools inspect myorg/api:1.4.2
Name:      docker.io/myorg/api:1.4.2
MediaType: application/vnd.oci.image.index.v1+json
Digest:    sha256:9f2c7be1d3a0...

Manifests:
  Name:      docker.io/myorg/api:1.4.2@sha256:41be...
  Platform:  linux/amd64
  Name:      docker.io/myorg/api:1.4.2@sha256:c8d0...
  Platform:  linux/arm64
```

`docker manifest inspect myorg/api:1.4.2` prints the raw JSON similarly. Neither requires pulling layers.

### 5.7 Exporting and reading layers directly

```bash
$ docker save myorg/api:1.4.2 -o api.tar
$ mkdir api && tar -xf api.tar -C api && ls api
blobs  index.json  manifest.json  oci-layout
$ cat api/manifest.json
[{"Config":"blobs/sha256/5d1e...","RepoTags":["myorg/api:1.4.2"],"Layers":["blobs/sha256/...","blobs/sha256/..."]}]
```

The exact layout depends on the Docker version and image store; newer versions emit an OCI layout, older ones per-layer directories.

### 5.8 Listing and filtering images

```bash
$ docker images --filter dangling=true
$ docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'
$ docker images --digests
```

## 6. Production Usage Notes

- Add inspection gates to CI: assert `Config.User` is non-root, no `latest` bases, `Labels` contain version and revision, and dive efficiency above a threshold.
- Use `docker history` and `dive` when triaging size regressions between two releases.
- `docker inspect` on a running container shows the container's effective config (with runtime overrides); on an image, only the defaults from the build. Do not confuse them.
- Scanners (Trivy, Grype, Docker Scout) read the same layers; use `docker scout quickview` or `trivy image` alongside manual review.
- For registries you cannot pull from quickly, use `imagetools inspect` or `crane manifest`/`skopeo inspect` (third-party) for metadata.

## 7. Security Considerations

- **History is a permanent record:** any secret ever written into any layer or instruction persists, even if a later `RUN rm` hides the file from the final filesystem.
- Check `Config.User`: empty or `root` means the container runs as root by default ([§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)).
- Review `ExposedPorts`, `Volumes`, and `Env` for unexpected defaults.
- Inspect third-party images before use: look for unexpected entrypoints, embedded credentials, or suspicious layers.
- Do not run `dive` via a mounted Docker socket on shared or untrusted hosts.
- Verify digests and signatures rather than trusting tag names ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker inspect` returns a container instead of an image | Name matches both | `docker image inspect NAME` or `--type image` |
| `Error: No such image` | Not pulled locally, or wrong tag | `docker pull`; use `imagetools inspect` for registry-only |
| History shows `<missing>` IDs | Normal for BuildKit or pulled images | No fix required; use `--no-trunc` for detail |
| `history` shows a big layer but `dive` says little is wasted | Layer is legitimately large content (for example the base OS) | Change base or use multi-stage |
| Image is large after `rm -rf` in a later `RUN` | Files persist in the earlier layer | Delete in the same `RUN` that created them, or use multi-stage |
| Template error in `--format` | Wrong field path or missing `json` function | Run plain `docker inspect` to see the actual keys |
| `dive` cannot find the image | It reads via the Docker socket or a source flag | Use `dive --source docker|podman|docker-archive` |

## 9. Best Practices

- Inspect every image you produce before promoting it: entrypoint, user, ports, labels.
- Use `--format` templates to script checks instead of parsing JSON by eye.
- Run `docker history --no-trunc` on any third-party base before adopting it.
- Add size and efficiency regression checks to CI.
- Standardize OCI labels so `inspect` answers "what commit is this?".
- Prefer inspecting by digest when verifying a deployed artifact.
- Use registry-side inspection to check multi-arch coverage before rollout.

## 10. Common Anti-Patterns / Mistakes

- Assuming the final filesystem view equals what is in the image (deleted files remain in layers).
- Trusting `docker images` SIZE as the download size: it is the uncompressed local size; registry transfer is compressed and shared layers are not re-pulled.
- Treating `history` output as an audit trail of the Dockerfile: comments and multi-stage earlier stages are not fully represented.
- Never looking at images from the internet until a scanner flags them.
- Shipping without verifying the `USER` and `ENTRYPOINT` that actually landed.
- Confusing image config (`docker image inspect`) with container config (`docker container inspect`).

## 11. Interview Questions

**🎯 Beginner:** _"How do you see an image's default command and the steps that created it?"_
**Model answer:** Run `docker inspect --format '{{.Config.Cmd}}' img` for the default command (also `.Config.Entrypoint`, `.Config.User`, `.Config.Env`). `docker history img` shows each layer with the instruction that created it and its size; add `--no-trunc` for full command text. `dive img` gives an interactive view of per-layer file changes and an efficiency score.
_What the interviewer is probing for:_ Basic inspection tooling.

**🎯 Intermediate:** _"Why does `docker history` show `<missing>` layers, what is the difference between image ID and repo digest, and how do you inspect a multi-arch image without pulling?"_
**Model answer:** `<missing>` means there is no local image ID for that intermediate layer, which is normal with BuildKit or for pulled images and does not mean corruption. The image ID is the hash of the image config blob, while the repo digest is the hash of the manifest as stored in a registry; they differ and only the digest is registry-verifiable. Inspect a remote multi-arch image with `docker buildx imagetools inspect repo/img:tag` or `docker manifest inspect`, which list the per-platform manifests.
_What the interviewer is probing for:_ Correct identity concepts and remote inspection.

**🎯 Senior:** _"An image is 1.2 GB. How do you find the cause, and how could a secret be recovered even though the running container has no such file?"_
**Model answer:** Use `docker history --no-trunc` and `dive` to locate the fat layer (for example a package cache or build toolchain), then fix with multi-stage, a slimmer base, cleanup in the same RUN, and `.dockerignore`. A secret can be recovered because layers are immutable: an earlier layer still holds a file removed later, and `ENV`, `ARG`, or command text appear in history. Extract with `docker save img | tar -x` and inspect layer tarballs. The fix is `--mount=type=secret` and rotating the exposed credential.
_What the interviewer is probing for:_ Layer-level diagnosis and why deletion does not remove data.

**🎯 Architect:** _"Design automated image policy checks in CI/CD, and explain how you would audit thousands of registry images for root users and stale bases."_
**Model answer:** In CI, inspect config for non-root `User`, required OCI labels, and pinned base digests, gate on a `dive` efficiency threshold, run a scanner and SBOM generation, verify signatures, and enforce again at admission control. For a registry audit, read config blobs via the registry API using `skopeo inspect --config` or `crane config` at scale, extract `User`, labels, and base-image annotations, and join with scanner metadata. Produce a report keyed by owner label, then enforce with deadlines and block deploys of noncompliant images.
_What the interviewer is probing for:_ Automation, scalable auditing, and enforcement thinking.

## 12. Common Misconceptions

- "`docker inspect` runs the image." It only reads metadata.
- "SIZE in `docker images` equals what gets pulled." Pulls are compressed and layer-deduplicated.
- "Removing a secret file in a later layer removes it from the image." It remains in the earlier layer.
- "`<missing>` means the image is corrupted." It does not.
- "dive changes or rebuilds the image." It is read-only analysis.

## 13. 🔑 Key Takeaways

- `docker inspect` reveals the image's config: entrypoint, cmd, user, env, ports, labels, digests.
- `docker history` maps layers to instructions and sizes, and can expose leaked secrets.
- `dive` explores each layer's file changes and quantifies wasted space.
- Registry-side tools inspect manifests and multi-arch indexes without pulling.
- Deleted files and secrets persist in earlier layers; fix at build time, not by deleting later.
- Image inspection belongs in CI as an automated gate.

## 14. Related Concepts & What's Next

Related: image anatomy ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), layers and overlay2 ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), build instructions ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)-[§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), tagging and digests ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), building ([§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), OCI specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). This closes Part 3 on images and Dockerfiles. Part 4 turns to running them: the `docker run` command, its flags, and container lifecycle management.

**Next Section:** [§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md) — `Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md`
