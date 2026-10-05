# Section 21 (Part 3): .dockerignore and Build Context Mechanics

## 1. Definition

**Plain language:** When you run `docker build .`, the `.` is the *build context*: the set of files Docker makes available to the build. Only files in the context can be `COPY`'d into the image. A `.dockerignore` file lists paths to leave out of that context, keeping builds fast, small, and free of secrets.

**Precise definition:**

- **Build context** is a directory (or URL, Git repo, or tarball) whose contents are sent to the builder. With the classic builder the entire context is tarred and shipped to the daemon; with BuildKit only the files actually needed are transferred incrementally.
- **`.dockerignore`** is a file at the root of the context, with one pattern per line, using Go `filepath.Match` rules extended with `**` for any number of directories. Patterns are relative to the context root. A line starting with `!` re-includes a path; a line starting with `#` is a comment. The last matching rule wins.
- With `-f`/`--file`, a Dockerfile-specific ignore file `<Dockerfile-name>.dockerignore` (for example `Dockerfile.prod.dockerignore`) can override the default when using BuildKit.

> 💡 **Tip:** The context is a contract: "these are the only files the build may touch." Keep it as small as the build permits.

## 2. Why This Matters

- **Speed.** Shipping a 2 GB context (with `node_modules`, `.git`, datasets) to the daemon on every build wastes minutes. `Sending build context to Docker daemon 1.9GB` is a classic symptom.
- **Cache efficiency.** `COPY . .` invalidates its layer whenever any file in the context changes. Ignoring logs, build output, and editor files stops needless rebuilds.
- **Secrets hygiene.** `.env` files, SSH keys, cloud credentials, and `.git` history copied via `COPY . .` end up permanently in a layer.
- **Reproducibility.** Ignoring host-built artifacts (`node_modules`, `target/`, `__pycache__`) prevents host-OS binaries from overwriting what the image installs.
- **Smaller images.** Fewer stray files means fewer bytes in layers.

## 3. Prerequisites and Dependencies

- The Dockerfile instructions `COPY` and `ADD` and how layer caching works ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md), [§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)).
- Client/daemon split: the CLI packages the context and sends it to the daemon over the API ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)).
- Basic glob syntax.
- Awareness of BuildKit as the modern builder (covered in [§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)).
- Git basics; `.dockerignore` resembles but does not equal `.gitignore`.

## 4. Architecture / Conceptual Diagram

```
   docker build -t app .
        │
        ▼
   ┌─────────────┐   read .dockerignore   ┌─────────────────────────┐
   │ Docker CLI  │──────────────────────►│ filter file list         │
   └─────────────┘                        └───────────┬─────────────┘
                                                      │ remaining files
                       classic builder: tar whole ────┤
                       BuildKit: send only needed ────┤
                                                      ▼
                                          ┌──────────────────────┐
                                          │ dockerd / BuildKit    │
                                          │  COPY src/ /app       │◄── only context files
                                          │  cache key = checksum │
                                          └──────────────────────┘

   Context root/                Ignored?
   ├── src/                     no
   ├── package.json             no
   ├── node_modules/            YES (node_modules)
   ├── .git/                    YES (.git)
   ├── .env                     YES (.env*)
   └── Dockerfile               (sent, but usually ignored for COPY)
```

## 5. Hands-On

### 5.1 Seeing the context size

```
$ ls -a
.  ..  .git  Dockerfile  node_modules  package.json  src
$ du -sh .git node_modules
412M    .git
1.1G    node_modules
$ DOCKER_BUILDKIT=0 docker build -t ctxdemo .
Sending build context to Docker daemon  1.52GB
Step 1/4 : FROM node:20-alpine
...
```

With the legacy builder the whole tree, including `.git` and `node_modules`, is uploaded before step 1.

### 5.2 Adding a .dockerignore

```
# .dockerignore
.git
.gitignore
node_modules
npm-debug.log
dist
coverage
.env
.env.*
*.md
!README.md
**/*.swp
**/.DS_Store
Dockerfile*
docker-compose*.yml
```

```
$ DOCKER_BUILDKIT=0 docker build -t ctxdemo .
Sending build context to Docker daemon  84.5kB
```

The upload dropped from 1.52 GB to 84.5 kB.

### 5.3 BuildKit transfers only what is needed

```
$ docker build --progress=plain -t ctxdemo . 2>&1 | grep -i context
#2 [internal] load build context
#2 transferring context: 82.31kB 0.0s done
```

BuildKit reports a small transfer even without an ignore file when the Dockerfile only copies a few paths, but `COPY . .` still pulls everything, so ignore files remain important.

### 5.4 Pattern semantics and negation

```
# ignore all markdown except the README
*.md
!README.md

# ignore every .tmp file at any depth
**/*.tmp

# ignore only a top-level dir
/build
```

Root-relative behavior: a pattern `temp*` matches `tempfile` in the context root and in immediate subdirectories one level down (`*/temp*`), but not deeper; use `**/temp*` for any depth. Order matters: put `!` exceptions after the rule they override.

### 5.5 Verifying what actually gets copied

```dockerfile
FROM alpine:3.20
COPY . /ctx
RUN find /ctx -maxdepth 2 | sort
```

```
$ docker build --progress=plain --no-cache -t ctxcheck . 2>&1 | grep '^#' | grep /ctx
#6 0.310 /ctx
#6 0.310 /ctx/package.json
#6 0.310 /ctx/src
#6 0.310 /ctx/src/index.js
```

A throwaway Dockerfile like this is the most reliable way to test your ignore rules.

### 5.6 Choosing a different context and Dockerfile

```
$ docker build -f docker/Dockerfile.prod -t app:prod .        # context is repo root
$ docker build -t app:svc ./services/api                       # context is the subdirectory
$ docker build -t app:git https://github.com/example/app.git#main:docker
$ tar -cz . | docker build -t app:stdin -                       # tar context from stdin
$ docker build -t app:nofiles - < Dockerfile                   # no context at all
```

Files outside the context cannot be referenced: `COPY ../secrets /x` fails with `forbidden path outside the build context`.

### 5.7 Per-Dockerfile ignore files with BuildKit

```
$ ls
Dockerfile  Dockerfile.dockerignore  Dockerfile.test  Dockerfile.test.dockerignore
$ docker build -f Dockerfile.test -t app:test .   # uses Dockerfile.test.dockerignore
```

### 5.8 Two-step cache-friendly copy

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
```

Copying dependency manifests first means source edits do not invalidate the `npm ci` layer, and `.dockerignore` keeps `COPY . .` from dragging in `node_modules`.

## 6. Production Usage Notes

- Commit `.dockerignore` to every repo that has a Dockerfile; treat it as required.
- Prefer an **allowlist** strategy for sensitive or messy repos: ignore everything (`*`), then re-include what is needed (`!src`, `!package*.json`).
- In monorepos, use a small context per service or `--build-context` named contexts (BuildKit) to avoid sending the whole tree.
- Remote builders (CI runners, `docker buildx` with remote drivers) pay network cost for the context, so trimming it saves real time.
- Keep `.dockerignore` and `.gitignore` aligned but separate; Docker needs to exclude `.git`, which Git itself never lists.
- Use `docker build --progress=plain` in CI to log context transfer size and catch regressions.
- Note that `Dockerfile` and `.dockerignore` are always sent to the daemon so it can read them, even if listed in the ignore file; they just cannot be `COPY`'d when ignored.

## 7. Security Considerations

- **Ignore credentials by default**: `.env*`, `*.pem`, `*.key`, `id_rsa*`, `.aws`, `.npmrc`, `.git-credentials`, `*.tfstate`, kubeconfig files.
- **Ignore `.git`.** History can contain deleted-but-recoverable secrets, and `COPY . .` would bake all of it into the image forever.
- A file that is copied in one layer and deleted in the next is still recoverable from the earlier layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)). Prevention through context filtering is the only reliable control.
- Ignore rules are **not a security boundary against a malicious Dockerfile**; they only govern what is sent and copyable.
- Use BuildKit `--mount=type=secret` for build-time secrets so they never enter the context or layers.
- Remote Git contexts and tarball URLs are fetched by the builder; treat them as untrusted inputs and pin refs to commits.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `Sending build context ... 2GB`, very slow | No `.dockerignore`; large dirs included | Add ignore rules; check with `du -sh * .[!.]*` |
| `COPY failed: file not found in build context` | Path is ignored or outside context | Remove the pattern or `!` re-include it |
| `forbidden path outside the build context` | `COPY ../x` | Move the build context up or use `--build-context` |
| Cache always misses at `COPY . .` | Volatile files (logs, `dist`, timestamps) in context | Ignore them; split manifest copy |
| Negation `!file` ignored | The parent directory was already excluded | Re-include the parent path pattern too |
| `.dockerignore` seemingly not applied | Wrong location (not context root) or wrong `-f` naming | Place at context root or use `<Dockerfile>.dockerignore` |
| Host `node_modules` overwrote container ones | Not ignored | Add `node_modules` |
| Build works locally, fails in CI | File exists locally but ignored/untracked in CI checkout | Make dependencies explicit in context |

## 9. Best Practices

- Always ship a `.dockerignore`, starting with `.git`, dependency directories, build output, logs, and env files.
- Consider deny-all-then-allow for strict control.
- Split `COPY` into manifests then source for cache reuse.
- Verify the effective context with a throwaway `find` step (5.5).
- Keep contexts per service in monorepos.
- Review `.dockerignore` in code review like any security file.
- Use `docker build --progress=plain` to watch transfer size over time.

## 10. Common Anti-Patterns / Mistakes

- Running `docker build` from `/` or `~` (the entire home directory becomes the context).
- `COPY . .` with no `.dockerignore`.
- Ignoring `package-lock.json` or other files the build needs, then wondering about failures.
- Copying `.env` into the image and "deleting it later".
- Assuming `.gitignore` is honored by Docker. It is not.
- Depending on ignored files being present at build time.
- Writing `!` exceptions before the rule they should override.

## 11. Interview Questions

**🎯 Beginner:** _"What is the build context in `docker build -t app .`, and can `COPY ../secret.txt /` work?"_
**Model answer:** The build context is the directory (or URL or tarball) given as the last argument, here `.`, and its files are what the builder can see. `COPY` can only reference paths inside the context, so `../secret.txt` fails with a not-found or outside-context error. `.dockerignore` at the context root excludes matching paths. To use files from elsewhere, pass a wider context or a named context with `--build-context`.
_What the interviewer is probing for:_ The context boundary and role of .dockerignore.

**🎯 Intermediate:** _"Builds are slow and cache always misses on `COPY . .` even when only a README changed. How does `.dockerignore` help, and what are its syntax quirks versus `.gitignore`?"_
**Model answer:** `COPY . .` checksums every file in the context, so a volatile file (logs, `.git`, README edits, build output) invalidates that layer and all following. List them in `.dockerignore` so they never enter the checksum, and split copies: `COPY package.json package-lock.json ./`, then `RUN npm ci`, then `COPY . .`. Docker does not read `.gitignore`; patterns are relative to the context root, support `**`, and `!path` re-includes but later rules override earlier, so order matters. Re-including a file inside an ignored directory needs care because a parent excluded by a rule cannot always be traversed.
_What the interviewer is probing for:_ Cache invalidation mechanics and correct ignore pattern semantics.

**🎯 Senior:** _"How does BuildKit treat the context differently from the legacy builder, and how do you keep secrets out of images provably?"_
**Model answer:** The legacy builder tars and uploads the whole context to the daemon before starting; BuildKit transfers only files a step actually needs, incrementally and cached. To keep secrets out, ignore secret files (`.env`, `*.pem`) in `.dockerignore`, inject credentials with `RUN --mount=type=secret` rather than COPY or ARG, and never rely on a later `rm`, since the earlier layer still contains the file. Verify by scanning the built image (trivy, gitleaks) and inspecting with `docker history --no-trunc` and `dive`.
_What the interviewer is probing for:_ Builder differences and defense that survives layer immutability.

**🎯 Architect:** _"Design the context strategy for a monorepo with 40 services, and the org-wide controls you would require."_
**Model answer:** Give each service its own Dockerfile with a narrow context (`docker build -f services/x/Dockerfile services/x`) or use named contexts for shared libraries, avoiding a root-wide context. Use allowlist-style `.dockerignore` (`*` then `!src`, `!package.json`), shared base images, and remote cache (registry or gha cache) so unchanged services do not rebuild. Mandate BuildKit, a template `.dockerignore`, a CI lint that fails on missing ignore files, context-size budgets measured from build logs, and secret scanning of contexts and images. Path-filtered CI triggers ensure only affected services build.
_What the interviewer is probing for:_ Scaling context hygiene, caching, and governance in a monorepo.

## 12. Common Misconceptions

- "`.dockerignore` speeds up builds only slightly." It can turn gigabytes into kilobytes.
- "Deleting a file in a later layer removes it." It stays in the earlier layer.
- "`.dockerignore` is like `.gitignore`." Similar syntax, different semantics and anchoring.
- "The Dockerfile must be inside the context." `-f` may point elsewhere (though it is sent alongside).
- "BuildKit makes the ignore file unnecessary." `COPY . .` still copies everything not excluded.

## 13. 🔑 Key Takeaways

- The context is everything the build can see; minimize it.
- `.dockerignore` lives at the context root and is separate from `.gitignore`.
- Ignore `.git`, secrets, dependency directories, and build output.
- Filtering, not deleting, is the only way to keep secrets out of layers.
- Test ignore rules with a throwaway `find` build.

## 14. Related Concepts & What's Next

Related: `COPY`/`ADD` and caching ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), image layers and why deletions do not shrink images ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `WORKDIR`/`ARG` ([§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), client/daemon transfer ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)), and the union filesystem ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). BuildKit features such as named contexts and secret mounts continue in [§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md). Next we choose what goes at the bottom of the image: the base.

**Next Section:** [§22](Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md) — `Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md`
