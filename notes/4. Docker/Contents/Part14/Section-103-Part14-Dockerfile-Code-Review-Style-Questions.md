# Section 103 (Part 14): Dockerfile Code-Review Style Questions

## 1. Definition

**Plain language:** In a Dockerfile code-review question the interviewer hands you a flawed Dockerfile and says "review this as if it were a pull request." You are expected to find the problems, rank them by severity, explain why each hurts, and show the corrected file.

**Precise definition:** A Dockerfile review evaluates five axes: **correctness** (does it build and start reproducibly), **security** (user, secrets, base image, attack surface), **cache efficiency** (instruction ordering and layer boundaries), **image size** (build tooling leaking into runtime, package manager residue), and **operability** (signals, health, logging, metadata). Each finding should cite the instruction, state the consequence, and propose a specific change.

> 💡 **Tip:** Present findings in descending severity (blocker, major, minor, nit) and say which you would block the merge on. That ranking is what separates a reviewer from a linter.

## 2. Why This Matters

- Reviewing a Dockerfile is a daily task for platform and DevOps engineers; interviewers use it to test breadth in 15 minutes.
- Most of the sins are cheap to fix and expensive to ignore: leaked secrets, root runtime, cache-busting `COPY`, 1 GB images.
- It reveals whether a candidate understands mechanisms (layers, cache keys, PID 1) rather than slogans.
- The checklist in [§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md) and the anti-patterns in [§95](../Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md) become the rubric you apply live.

## 3. Prerequisites and Dependencies

Dockerfile instructions ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md), [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md), [§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md), [§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), base images ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)), caching ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), multi-stage builds ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)) and non-root users ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)). Companion practice: [§102](Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md).

## 4. Architecture / Conceptual Diagram

```text
              REVIEW PASS ORDER (what to read for, top to bottom)

  FROM ................ pinned? trusted? right size?       (supply chain, size)
  ARG / ENV ........... secrets? needed at build or run?   (leaks, cache)
  RUN apt/apk ......... update+install+cleanup one layer?  (size, staleness)
  COPY ................ deps manifest before source?       (cache)
  RUN build ........... tooling stays in builder stage?    (size, attack surface)
  USER ................ non-root before CMD?               (privilege)
  EXPOSE/HEALTHCHECK .. documented port, real probe?       (operability)
  ENTRYPOINT/CMD ...... exec form, signals reach app?      (shutdown)

  Cache key view: each instruction's key = parent layer + instruction text
                  (+ file checksums for COPY/ADD)

      FROM ──► RUN deps ──► COPY manifest ──► RUN install ──► COPY src ──► RUN build
        ▲                                         ▲              │
        │ stable                                  │ reused       ▼ changes every commit
        └─────── put slow, rarely-changing steps ─┘      only layers from here rebuild

  Severity ladder
  ┌─────────┬────────────────────────────────────────────────────────┐
  │ Blocker │ secret in image/layer, root + exposed service, curl|sh │
  │ Major   │ unpinned base, no multi-stage, cache-busting COPY      │
  │ Minor   │ missing HEALTHCHECK, apt cache left, many tiny layers  │
  │ Nit     │ instruction ordering of LABELs, casing                 │
  └─────────┴────────────────────────────────────────────────────────┘
```

- The cache key rule explains most "slow build" findings: a changed `COPY` invalidates everything below it.
- Secrets baked in any layer are a blocker even if a later `RUN rm` deletes them, because the earlier layer still contains them ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)).

## 5. Hands-On

### 5.1 Exercise 1: The Classic Node Service

```dockerfile
FROM node:latest
ENV NPM_TOKEN=<your-npm-token>
WORKDIR /app
COPY . .
RUN apt-get update
RUN apt-get install -y curl vim
RUN npm install
EXPOSE 3000
CMD npm start
```

**Review findings**

| Sev | Line | Problem | Why it hurts |
|---|---|---|---|
| Blocker | `ENV NPM_TOKEN=...` | Secret persisted in image config | Visible via `docker history`/`inspect` to anyone who can pull |
| Major | `FROM node:latest` | Floating, huge tag | Non-reproducible; breaking major bumps; full Debian |
| Major | `COPY . .` before install | Any source change reinstalls all dependencies | Slow builds; also copies `.git`, `.env`, `node_modules` if no `.dockerignore` |
| Major | `apt-get update` alone in a layer | Cached stale index; later `install` can fail | Classic cache bug |
| Minor | `vim`, `curl` in runtime | Tools unneeded in production | Larger attack surface and image |
| Major | no `USER` | Runs as root | Container escape or file write impact is larger |
| Major | `CMD npm start` | Shell form plus npm as PID 1 | SIGTERM not delivered; 10 s stop delay ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) |
| Minor | `npm install` | Not deterministic, dev dependencies | Use `npm ci --omit=dev` |
| Minor | no `HEALTHCHECK` | Orchestrator cannot detect hangs | |

**Corrected**

```dockerfile
# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev

FROM gcr.io/distroless/nodejs22-debian12:nonroot
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --chown=nonroot:nonroot . .
EXPOSE 3000
CMD ["server.js"]
```

The distroless Node image sets `node` as its entrypoint, so `CMD ["server.js"]` runs `node server.js` as PID 1 with a non-root user. The secret is mounted only during the install step and is never written to a layer ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)). A distroless image has no shell or curl, so a health probe must come from the orchestrator or a bundled binary.

### 5.2 Exercise 2: The Python Image That Ships a Compiler

```dockerfile
FROM python:3.12
WORKDIR /srv
RUN apt-get update && apt-get install -y build-essential libpq-dev
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN pip install -e .
USER root
ENTRYPOINT ["python", "-m", "app"]
CMD ["--port", "8000"]
```

Findings:

- **Good:** requirements are copied before source (cache-friendly), exec-form entrypoint plus CMD ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).
- **Major:** `build-essential` remains in the runtime image (about 300 MB and a compiler for an attacker). Use a builder stage and copy a virtualenv or wheels.
- **Major:** `USER root` explicit; add an unprivileged user.
- **Minor:** `apt-get` without `--no-install-recommends` and without `rm -rf /var/lib/apt/lists/*`.
- **Minor:** `pip install` without `--no-cache-dir`; no hash pinning (`--require-hashes`) for supply-chain strictness.
- **Minor:** `python:3.12` is the full Debian image; `3.12-slim` suffices with a builder stage.

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY . .
RUN pip install --no-deps .

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --no-create-home app
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
ENTRYPOINT ["python", "-m", "app"]
CMD ["--port", "8000"]
```

### 5.3 Exercise 3: Secrets and Remote Scripts

```dockerfile
FROM ubuntu:22.04
ARG GITHUB_TOKEN
RUN apt-get update && apt-get install -y git curl
RUN git clone https://${GITHUB_TOKEN}@github.com/acme/private.git /src
RUN curl -sSL https://example.com/install.sh | bash
RUN rm -rf /src/.git
```

- **Blocker:** `ARG GITHUB_TOKEN` is recorded in `docker history` and in image metadata (build args are visible); deleting `.git` later does not remove it from earlier layers. Use `RUN --mount=type=ssh` or `--mount=type=secret` ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Blocker:** `curl | bash` executes unverified remote code at build time. Download, verify a pinned checksum or signature, then run.
- **Major:** unpinned `ubuntu:22.04` tag; pin a digest for production, with an automated update bot.
- **Minor:** `rm -rf` in a later layer saves nothing; combine or use multi-stage.

### 5.4 Linting and Measuring the Review

```bash
docker build --check .                      # BuildKit's built-in lint (Docker 27+)
docker run --rm -i hadolint/hadolint < Dockerfile
docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' app:dev | head
docker run --rm -v "$PWD:/w:ro" aquasec/trivy config /w   # IaC misconfig scan
```

```text
WARNING: LatestTagWarning - ... Using latest is prone to errors if the image will ever update. (line 1)
WARNING: SecretsUsedInArgOrEnv - Do not use ARG or ENV instructions for sensitive data (ENV "NPM_TOKEN") (line 2)
```

State that tools catch the mechanical rules, but judgments (whether to use distroless, whether the healthcheck is meaningful) need a human.

## 6. Production Usage Notes

- **Automate the mechanical review:** run `docker build --check`, hadolint and a config scanner in CI so humans review design, not typos ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)).
- **Standardize on base images** owned by the platform team with a stable contract (user, tini, tz, CA certificates) and monthly rebuilds.
- **Pin by digest** in production Dockerfiles (`FROM node:22-bookworm-slim@sha256:...`) and let a dependency bot propose updates.
- **Enforce size and layer budgets** (for example fail CI above 300 MB for a service image) to keep regressions visible.
- **Review the `.dockerignore` in the same PR** as the Dockerfile; a missing one is a finding ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).
- **Add LABELs** for source repository and revision (OCI annotations) so images are traceable ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).

## 7. Security Considerations

- **Secrets:** never in `ENV`, `ARG`, `COPY`-ed files or URLs; use BuildKit secrets and runtime secret mounts ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Privilege:** a numeric non-root `USER` (so Kubernetes `runAsNonRoot` can verify it) and no setuid binaries needed ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)).
- **Supply chain:** trusted, pinned bases; verified downloads; no `curl | sh`; `ADD <url>` avoided in favor of verified `curl` or `ADD --checksum` ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Attack surface:** remove shells, package managers and compilers from the final stage; distroless or slim bases reduce CVE count ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- **Context leakage:** `COPY . .` without a `.dockerignore` can ship `.env`, `.git`, SSH keys and cloud credentials into a layer.
- **Writable paths:** design for `--read-only` by declaring where the app writes ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).

## 8. Common Troubleshooting Scenarios

Symptoms that a Dockerfile review should have caught.

| Symptom after build/run | Dockerfile root cause | Fix |
|---|---|---|
| Every build reinstalls dependencies | `COPY . .` before dependency install | Copy manifest and lockfile first |
| `apt-get install` fails with 404 later | `apt-get update` in separate, cached layer | One `RUN update && install` |
| 10 s `docker stop` | Shell-form CMD/ENTRYPOINT | Exec form, `exec "$@"` |
| Image 1.5 GB | Toolchain and caches in final stage | Multi-stage, `--no-install-recommends`, cache mounts |
| `Permission denied` writing at runtime | `USER app` set but directory owned by root | `COPY --chown`, `mkdir` plus `chown` before `USER` |
| `exec format error` | Wrong platform base or CRLF script | `--platform`, normalize line endings |
| `not found` for an existing binary on Alpine | glibc binary on musl base | Use matching base or static build |
| Secret visible in `docker history` | `ARG`/`ENV` used for credentials | BuildKit secret mounts |
| Different behavior between builds | Floating tags, unpinned packages | Pin base digest and package versions |
| Healthcheck always failing | `curl` absent in slim/distroless image | Use a binary present in the image |

## 9. Best Practices

- **Review in this order:** secrets and privilege first, reproducibility second, cache and size third, polish last.
- **Phrase feedback as consequence plus fix:** "root runtime means a compromised app owns the container filesystem; add `USER 10001`."
- **Praise what is good** briefly; it shows balance and often the Dockerfile has two or three correct choices.
- **Offer the corrected file**, not just criticism; keep the diff minimal for a PR.
- **Merge `RUN` steps that share a cleanup**, not all steps; split where cache boundaries differ.
- **Use `COPY --chown` and `--chmod`** instead of follow-up `RUN chown` layers.
- **Prefer `COPY` over `ADD`** except for local tar auto-extraction or checksum-verified remote files.
- **Order for cache:** least-changing first; OS packages, dependency manifest, install, source, build.
- **Set `STOPSIGNAL`, `HEALTHCHECK` and OCI labels** when the platform consumes them.

## 10. Common Anti-Patterns / Mistakes

- Judging only on size and missing a baked-in secret.
- Recommending Alpine reflexively without noting musl compatibility trade-offs.
- Suggesting one giant `RUN` with everything, which destroys cache granularity.
- Using `latest` in the "corrected" version, or forgetting to pin the builder stage as well.
- Proposing `scratch` for an app that needs CA certificates, timezone data or a non-root user entry in `/etc/passwd`.
- Adding `apt-get upgrade -y` to every image, making builds non-reproducible.
- Reviewing the Dockerfile in isolation from `.dockerignore`, Compose overrides and CI build arguments.
- Treating hadolint output as a complete review.
- Leaving `VOLUME` declarations that create anonymous volumes and make later `COPY` into that path silently lost ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)).

## 11. Interview Questions

**🎯 Beginner:** _"Why is `RUN apt-get update` on one line and `RUN apt-get install -y nginx` on the next considered a bug?"_
**Model answer:** Each `RUN` is a separate cached layer. The `update` layer's cache key never changes, so BuildKit reuses a stale package index while the `install` layer's text may change, and later builds can fail with 404 errors for packages that moved. The fix is to chain them in one instruction, `RUN apt-get update && apt-get install -y --no-install-recommends nginx && rm -rf /var/lib/apt/lists/*`, so the index and the install always share a cache decision and the lists never remain in the layer.
_What the interviewer is probing for:_ Understanding that layers are cached by instruction text and that cleanup must occur in the same layer.

**🎯 Intermediate:** _"Here is a Dockerfile with `COPY . .` followed by `RUN pip install -r requirements.txt`. Builds take six minutes every commit. Fix it and explain."_
**Model answer:** The `COPY . .` layer's cache key includes the checksum of every file, so any source edit invalidates it and every later layer, including the dependency install. I would first copy only `requirements.txt`, run the install, and then `COPY . .`. Dependency installs are then reused until the requirements file changes. I would add a BuildKit pip cache mount so even a changed requirements file reuses downloaded wheels, add a `.dockerignore` to keep `.git` and virtualenvs out of the context, and in CI export the cache to a registry or the GitHub cache so ephemeral runners also benefit.
_What the interviewer is probing for:_ Cache-key mechanics and practical ordering, plus awareness of CI cache persistence.

**🎯 Senior:** _"You find `ARG DB_PASSWORD` used in a `RUN` command and later deleted with `unset`. The author says the secret is gone. Respond, and explain the correct design."_
**Model answer:** It is not gone. Build arguments are recorded in the image history and metadata, and any file or output written in a layer remains in that layer even if a later layer hides it; `docker history --no-trunc` and a layer export both reveal it. Anyone who can pull the image has the credential, so it must be rotated now and treated as compromised. The correct design avoids needing a build-time secret; if one is unavoidable (private package index, SSH clone), use `RUN --mount=type=secret` or `--mount=type=ssh`, which exposes it on a tmpfs for that single instruction and writes nothing to a layer. Runtime credentials come from the orchestrator's secret store or a mounted file, not the image. Add a CI check (BuildKit `SecretsUsedInArgOrEnv` rule, Trivy secret scan) to block regressions.
_What the interviewer is probing for:_ Layer immutability, incident response (rotate), and the BuildKit secret-mount mechanism.

**🎯 Architect:** _"You are defining a Dockerfile review policy for 200 services in 5 languages. What is enforced automatically, what needs human review, and how do you keep it from becoming a bottleneck?"_
**Model answer:** I would split rules into three tiers. Tier one is automated and blocking: `docker build --check`, hadolint, a secret scanner, a config scan (Trivy), rejection of floating tags and root users, and size budgets, all in a shared CI template. Tier two is automated and advisory: image CVE counts, layer count, base image age versus the platform base. Tier three needs human judgment and is limited to design questions: a nonstandard base, new capabilities, or deviations from the golden multi-stage templates. To avoid a bottleneck, provide per-language golden Dockerfiles and base images maintained by the platform team, so most services inherit compliance, and use CODEOWNERS routing so only exceptions reach reviewers. Measure the policy through the share of images on golden bases, mean CVE age and the rate of review-found defects, and review the rules quarterly.
_What the interviewer is probing for:_ Scalable governance: automation, paved roads, exceptions and metrics.

## 12. Common Misconceptions

- "Fewer layers always means a better image." Layer count matters little; cache boundaries and what each layer contains matter more.
- "Deleting a file in a later `RUN` removes it from the image." The earlier layer still stores it.
- "`ARG` is safe for secrets because it is not in the final environment." It remains in history and metadata.
- "Alpine is always the best small base." musl, DNS and performance quirks can outweigh the size gain.
- "`USER` anywhere in the file is enough." Only instructions after it run as that user, and the last `USER` sets the runtime user.
- "`EXPOSE` publishes the port." It is documentation; publishing is a run-time decision.
- "A passing hadolint run means the Dockerfile is good." Linters do not judge architecture.

## 13. 🔑 Key Takeaways

- Review in severity order: secrets and privilege, reproducibility, cache and size, operability, polish.
- Cache keys depend on instruction text and file checksums; put volatile steps last.
- Layers are immutable; secrets in any layer are leaked, use `--mount=type=secret`.
- Multi-stage builds keep compilers out of runtime; pair with a numeric non-root `USER`.
- Exec-form entrypoints and a real healthcheck are part of the contract, not decoration.
- Give each finding as instruction, consequence and fix, then show the corrected file.
- Automate mechanical checks so human review focuses on design.

## 14. Related Concepts & What's Next

Related: best-practice checklist ([§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)), anti-patterns ([§95](../Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)), size minimization ([§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)), BuildKit syntax ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), and vulnerability scanning ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)). Next, [§104](Section-104-Part14-System-Design-Questions-Involving-Containers.md) zooms out from one file to whole-system design questions.

**Next Section:** [§104](Section-104-Part14-System-Design-Questions-Involving-Containers.md) — `Section-104-Part14-System-Design-Questions-Involving-Containers.md`
