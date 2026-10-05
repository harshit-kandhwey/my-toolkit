# Section 22 (Part 3): Base Image Selection (distroless, alpine, slim, scratch)

## 1. Definition

**Plain language:** Every image starts from a base named in `FROM`. That base decides how big your image is, what tools exist inside it, which C library your program links against, how many known vulnerabilities you inherit, and how easy debugging will be. Choosing it is one of the highest-leverage decisions in a Dockerfile.

**Precise definition:** A **base image** is the parent image in a `FROM` instruction whose layers become the bottom of the new image. Common families:

- **Full distro images** (`debian:bookworm`, `ubuntu:24.04`): complete userland, glibc, package manager, shell. Hundreds of MB for language variants.
- **`-slim` variants** (`python:3.12-slim`, `node:20-bookworm-slim`): Debian with most non-essential packages removed; still glibc and `apt`.
- **Alpine** (`alpine:3.20`, `python:3.12-alpine`): built on **musl libc** and **BusyBox**, with the `apk` package manager; base is roughly 7-8 MB.
- **Distroless** (`gcr.io/distroless/*`): images from Google containing only the app runtime (and glibc, certificates, tzdata, `/etc/passwd`) with **no shell and no package manager**.
- **`scratch`**: the reserved, empty image. No files at all; you supply a statically linked binary and anything it needs.

> 💡 **Tip:** The base is a trade among four axes: size, compatibility, security surface, and debuggability. No option wins all four.

## 2. Why This Matters

- **Size** drives pull time, cold-start latency, registry storage, and cost.
- **Attack surface.** Every package in the base is a potential CVE. Shell-less images also deny attackers easy post-exploitation tools.
- **Compatibility.** Alpine's musl differs from glibc; some prebuilt wheels, JVM native libs, and DNS behaviors misbehave.
- **Operational ergonomics.** Without a shell, `docker exec -it ... sh` fails, changing how you debug.
- **Supply chain and compliance.** The base is the biggest chunk of third-party code you ship; auditors and scanners start there.

## 3. Prerequisites and Dependencies

- Image layers and how a `FROM` base contributes layers ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)).
- `RUN`, `COPY`, and multi-stage builds ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)); static vs dynamic linking; what libc is.
- Non-root `USER` ([§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), since minimal images often lack user tooling and need numeric IDs.
- Tag and digest conventions ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), which apply to base pinning.
- OCI image spec and the meaning of `scratch` ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)).

## 4. Architecture / Conceptual Diagram

```
  Approx. compressed size and contents (illustrative; varies by version)

  ubuntu/debian full   ~30-50 MB  ┃ glibc ┃ apt ┃ bash ┃ coreutils ┃ many pkgs ┃
  debian -slim         ~25-30 MB  ┃ glibc ┃ apt ┃ bash ┃ fewer pkgs             ┃
  alpine               ~3-4 MB    ┃ musl  ┃ apk ┃ busybox sh                    ┃
  distroless/static    ~2 MB      ┃ CA certs ┃ tzdata ┃ /etc/passwd  (no shell)  ┃
  distroless/base      ~20 MB     ┃ glibc ┃ libssl ┃ CA certs     (no shell)     ┃
  scratch              0 bytes    ┃ (nothing)                                    ┃

  Language-runtime variants add the runtime on top (python, node, jre...).

  Decision flow
  ─────────────
  Static binary (Go, Rust musl)? ──yes──► scratch or distroless/static
        │no
  Needs glibc / prebuilt wheels?  ──yes──► *-slim or distroless (python3, java, nodejs)
        │no
  Need tiny + shell + apk, code tested on musl? ──► alpine
        │
  Need broad tooling / debugging? ──► debian/ubuntu (dev stage only)
```

## 5. Hands-On

### 5.1 Comparing sizes

```
$ docker pull -q ubuntu:24.04 debian:bookworm-slim alpine:3.20 gcr.io/distroless/static-debian12 >/dev/null
$ docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | grep -E 'ubuntu|debian|alpine|distroless'
ubuntu                          24.04              78.1MB
debian                          bookworm-slim      74.8MB
alpine                          3.20               7.8MB
gcr.io/distroless/static-debian12   latest         2.05MB
```

`docker images` shows uncompressed on-disk sizes, so numbers are larger than registry (compressed) sizes. Exact values change with releases.

### 5.2 Python app on three bases

```dockerfile
# Dockerfile.full
FROM python:3.12
# Dockerfile.slim
FROM python:3.12-slim
# Dockerfile.alpine
FROM python:3.12-alpine
```

```
$ for v in full slim alpine; do docker build -q -f Dockerfile.$v -t py:$v .; done
$ docker images py --format '{{.Tag}}\t{{.Size}}'
alpine  60.3MB
slim    131MB
full    1.02GB
```

### 5.3 The musl compatibility trap

```
$ docker run --rm python:3.12-alpine pip install numpy 2>&1 | tail -3
Building wheel for numpy (pyproject.toml) ... done
...
$ docker run --rm python:3.12-slim pip install numpy 2>&1 | tail -2
Successfully installed numpy-2.1.0
```

On slim, pip downloads a prebuilt manylinux (glibc) wheel in seconds. On Alpine older toolchains may need to compile from source, needing `gcc`, headers, and minutes of build time, although newer projects publish musllinux wheels. Test your dependency set before committing to Alpine.

### 5.4 Static Go binary on scratch

```dockerfile
FROM golang:1.23 AS build
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/app .

FROM scratch
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /out/app /app
USER 10001:10001
ENTRYPOINT ["/app"]
```

```
$ docker build -t goscratch .
$ docker images goscratch --format '{{.Size}}'
6.4MB
$ docker run --rm goscratch
hello from scratch
$ docker run --rm -it goscratch sh
docker: Error response from daemon: ... exec: "sh": executable file not found in $PATH
```

`scratch` has no shell, no certificates, no timezone data, and no `/etc/passwd` unless you copy them. Note `USER 10001:10001` works numerically without a passwd entry.

### 5.5 Distroless with a language runtime

```dockerfile
FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt
COPY app.py .

FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY --from=build /deps /deps
COPY --from=build /app/app.py .
ENV PYTHONPATH=/deps
CMD ["app.py"]
```

Distroless language images use the interpreter as the entrypoint, so `CMD` supplies the script ([§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)). The `:nonroot` tag runs as UID 65532.

### 5.6 Debugging a shell-less container

```
$ docker exec -it web sh
OCI runtime exec failed: exec failed: unable to start container process: exec: "sh": executable file not found in $PATH
$ docker run --rm -it --pid=container:web --network=container:web busybox sh
/ # ps
```

Attach a throwaway debug container that shares the target's PID and network namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)). Alternatively use `docker debug` (Docker Desktop / subscription feature) or the `:debug` distroless tags, which include BusyBox.

### 5.7 Comparing vulnerability counts

```
$ docker scout quickview python:3.12 | tail -3
$ docker scout quickview python:3.12-slim | tail -3
```

Tools like Docker Scout, Trivy, or Grype typically report far fewer findings for slim and distroless bases than full images because fewer packages are present. Exact counts change daily; always scan your own final image.

## 6. Production Usage Notes

- **Multi-stage builds are the standard pattern**: a fat builder stage (compilers, headers) and a minimal runtime stage, copying only artifacts.
- **Pin bases** by version tag and, for reproducibility, by digest (`FROM alpine:3.20@sha256:...`); refresh them on a schedule so security patches flow in.
- **Prefer official or verified publisher images**; know who maintains your base and how quickly they patch.
- **Match dev and prod libc.** Building on glibc and running on musl (or the reverse) causes runtime surprises. Static builds are the exception.
- **Alpine caveats:** musl's DNS resolver historically differed (search domain and `ndots` handling, TCP fallback), slower malloc for some workloads, and Python/JVM native-extension friction.
- **Slim is the safe default** for Python, Node, and Ruby when you need compatibility and moderate size.
- **Use distroless or scratch** for Go, Rust, Java (distroless/java), and other compiled apps where debugging is done through logs, metrics, and ephemeral debug containers.
- **Mirror base images** into your own registry to avoid rate limits and upstream removals.

## 7. Security Considerations

- **Fewer packages, fewer CVEs.** Minimal bases reduce scanner noise and exploitability, but scanning is still needed for your own dependencies.
- **No shell, no package manager** limits an attacker's ability to download tools or run scripts after a compromise, though it does not stop attacks that use the app's own runtime.
- **Digest pinning** protects against a tag being repointed maliciously or accidentally; pair with automated update PRs (Dependabot, Renovate).
- **`latest` is a supply-chain risk** and breaks reproducibility.
- **Provenance:** prefer bases with signatures/SBOM/attestations (for example Docker Official Images with provenance, distroless signed with cosign).
- **Add-ons still matter:** CA certificates and tzdata must be present for TLS verification; do not disable verification to work around a missing bundle on `scratch`.
- Use non-root variants (`:nonroot`) and verify UID at run time ([§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `exec /app: no such file or directory` on scratch/alpine although file exists | Dynamically linked glibc binary; loader missing | Build static (`CGO_ENABLED=0`) or use a glibc base |
| `x509: certificate signed by unknown authority` | No CA bundle on `scratch` | Copy `ca-certificates.crt` from build stage |
| `sh: not found` / cannot exec into container | Distroless or scratch | Use a debug container or `:debug` tag |
| pip/npm builds very slow on Alpine | Compiling native modules from source | Switch to slim or install build deps in builder stage |
| Odd DNS failures in Alpine | musl resolver behavior | Test with glibc base; check `ndots`/search domains |
| Timezone shows UTC / `unknown time zone` | No tzdata | Copy `/usr/share/zoneinfo` or set `ZONEINFO`, use distroless base |
| Image larger than expected | Build tools left in final stage | Use multi-stage and copy only artifacts |
| `standard_init_linux.go: exec user process caused: exec format error` | Architecture mismatch (arm64 vs amd64) | Build with `--platform` |

## 9. Best Practices

- Start with the official slim variant; move to distroless or scratch when the app allows; use Alpine deliberately, not reflexively.
- Use multi-stage builds so build tooling never ships.
- Pin versions and digests; automate updates.
- Rebuild regularly so base patches are picked up, even without code changes.
- Standardize a small set of approved bases across the organization.
- Scan every image in CI and gate on severity.
- Test on the same libc you deploy on.
- Document the debugging procedure for shell-less images before an incident.

## 10. Common Anti-Patterns / Mistakes

- `FROM ubuntu` then `apt-get install` a whole toolchain in the runtime image.
- Choosing Alpine solely for size, then fighting glibc-dependent wheels.
- `FROM node:latest` or any floating tag in production.
- Building glibc binaries and copying them to `scratch`.
- Skipping CA certificates on `scratch` and setting `InsecureSkipVerify`.
- Leaving debug tools (curl, vim, netcat) in production images "just in case".
- Never rebuilding, so months-old base layers accumulate CVEs.

## 11. Interview Questions

**🎯 Beginner:** _"A Go binary is statically compiled. Could it run on `scratch`, and why is Alpine small?"_
**Model answer:** Yes. `scratch` is an empty reserved base with no filesystem contents, so a static binary (`CGO_ENABLED=0`) can be copied in with `COPY app /app` and run with `ENTRYPOINT ["/app"]`. Alpine is small because it uses musl libc and BusyBox instead of glibc and GNU coreutils, at about 5 MB. A slim image is a Debian variant with non-essential packages removed.
_What the interviewer is probing for:_ Difference between minimal base types and what each contains.

**🎯 Intermediate:** _"A Python app works on `python:3.12-slim` but crashes on `python:3.12-alpine`, and the scratch-based Go service fails on HTTPS calls. Explain both."_
**Model answer:** Alpine uses musl, not glibc, so prebuilt manylinux wheels may not install, native extensions can be missing symbols, and DNS and locale behavior differ; slim (glibc) avoids this. The scratch image has no CA certificates, so TLS verification fails; copy `/etc/ssl/certs/ca-certificates.crt` from the builder stage. Distroless static images already include certs and tzdata, plus a nonroot user. When debugging a shell-less image, use `docker debug`, a `:debug` tag with BusyBox, or an ephemeral debug container sharing namespaces.
_What the interviewer is probing for:_ Diagnosing libc and missing-runtime-asset failures.

**🎯 Senior:** _"How does multi-stage build interact with base selection, and what are the trade-offs of digest pinning the bases?"_
**Model answer:** Use a full-featured builder stage (compilers, package managers) and copy only artifacts into a minimal runtime stage such as distroless or slim with `COPY --from=build`. Pinning `FROM image@sha256:...` gives immutable, reproducible builds and protects against tag repointing, but you stop receiving patches unless automation (Renovate or Dependabot) bumps digests and CI rebuilds. Keep the human-readable tag alongside for clarity (`image:1.2@sha256:...`). Scan both stages, though only the runtime stage ships.
_What the interviewer is probing for:_ Combining multi-stage design with reproducibility versus patch cadence.

**🎯 Architect:** _"Define an organization-wide base-image strategy and how you choose among Alpine, distroless, slim, and scratch."_
**Model answer:** Publish curated golden bases built from trusted upstreams, rebuilt nightly, signed, with SBOMs, mirrored to an internal registry, scanned with policy gates, and consumed by digest with automated bump PRs. Provide per-language guidance: slim for compatibility and team familiarity; distroless for minimal attack surface and fewer CVEs; Alpine for small, tested workloads that need a shell; scratch for static binaries. Document a debug workflow (ephemeral containers, `:debug` variants) so minimal images are supportable. Track adoption and CVE age as metrics.
_What the interviewer is probing for:_ Balancing attack surface, compatibility, supportability, and patch pipeline at org level.

## 12. Common Misconceptions

- "Alpine is always the best choice." It trades compatibility and sometimes performance for size.
- "Smaller means more secure." Fewer packages helps, but your own dependencies dominate risk.
- "Distroless means no OS." It still includes a minimal userland and libc (except static variants).
- "`scratch` is a real image you can pull." It is a reserved no-op base.
- "Pinning a tag guarantees immutability." Tags can be repointed; digests cannot.

## 13. 🔑 Key Takeaways

- Base choice balances size, compatibility, attack surface, and debuggability.
- Slim is the safe default; distroless and scratch are for compiled or tightly controlled apps; Alpine needs musl testing.
- Multi-stage builds keep toolchains out of runtime images.
- Pin and regularly rebuild bases; scan final images.
- Plan debugging for shell-less containers in advance.

## 14. Related Concepts & What's Next

Related: image layers and config ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `FROM`/`RUN`/`COPY` and multi-stage builds ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), `CMD` vs `ENTRYPOINT` for interpreter-based distroless ([§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), non-root users ([§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), the context that feeds these builds ([§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), the OCI specs behind `scratch` ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), and overlay2 ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). Next we look at how to name, tag, and version the images you produce from these bases.

**Next Section:** [§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md) — `Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md`
