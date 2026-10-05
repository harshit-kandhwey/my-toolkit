# Section 76 (Part 10): Build Secrets and SSH Forwarding During Build

## 1. Definition

**Plain language:** Sometimes a build needs a credential: a private npm token, a pip index password, or an SSH key to `git clone` a private repository. Build secrets and SSH forwarding let a single `RUN` step *see* that credential while it executes, without the credential ever being written into an image layer, the build cache, or the image history.

**Precise definition:** BuildKit ([§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)) provides two special mount types for `RUN` instructions:

- `RUN --mount=type=secret,id=NAME` mounts a secret as a read-only, in-memory file (default path `/run/secrets/NAME`) or, with `env=VAR`, exposes it as an environment variable for that one command. The value is supplied by the client at build time with `docker build --secret id=NAME,src=FILE` or `--secret id=NAME,env=VAR`.
- `RUN --mount=type=ssh` forwards a Unix socket for an SSH agent into the build step. The client supplies it with `docker build --ssh default` (or `--ssh default=$SSH_AUTH_SOCK`). The private key never leaves the host; only agent *signing requests* cross the socket.

Neither mount contributes to the layer's filesystem diff, so neither is stored in the image. This is the opposite of `ARG`, `ENV` and `COPY`, which permanently record values ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).

> ⚠️ **Warning:** A secret passed with `--build-arg` is visible in `docker history` and in image provenance. Treat every `ARG` as public.

## 2. Why This Matters

- Build-time credentials leak into images constantly; once an image is pushed ([§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)), the secret lives in every pulled copy and every registry backup.
- Deleting a secret in a later layer (`RUN rm .npmrc`) does not help: the earlier layer still contains it and can be extracted with `docker save` ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)).
- Private dependencies (internal npm/PyPI/Maven repositories, private Git modules) are normal in real companies, so every serious Dockerfile eventually needs this.
- Runtime secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)) and build secrets are different problems; interviews test whether you can tell them apart.
- Security scanners and compliance audits flag credentials baked into layers as critical findings.

## 3. Prerequisites and Dependencies

You need a working BuildKit builder, which is the default in Docker Engine 23+ and Docker Desktop ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md), [§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)). Understand how layers and the cache key work ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md), [§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), and multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), which complement secrets by discarding build-only stages. An SSH agent (`ssh-agent`, 1Password agent, or Windows OpenSSH agent) is required for SSH forwarding. Registry credentials for pushing are a separate topic ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)).

## 4. Architecture / Conceptual Diagram

```text
   HOST (client side)                      BUILDKIT (builder)
  ┌──────────────────────┐   gRPC session  ┌────────────────────────────────┐
  │ docker build         │◄───────────────►│ solver executes Dockerfile     │
  │  --secret id=npm,    │  secrets and    │                                │
  │      src=~/.npmrc    │  agent socket   │ RUN --mount=type=secret,id=npm │
  │  --ssh default       │  streamed on    │   │                            │
  │                      │  demand         │   ▼                            │
  │ ~/.npmrc (file)      │                 │  tmpfs: /run/secrets/npm       │
  │ ssh-agent ◄──────────┼─────────────────┼─ /run/buildkit/ssh_agent.0     │
  │  (keys stay here)    │  sign requests  │   (socket, SSH_AUTH_SOCK)      │
  └──────────────────────┘                 │   │                            │
                                           │   ▼  command runs; mount       │
                                           │      is unmounted afterwards   │
                                           │                                │
                                           │ layer diff = files the command │
                                           │ wrote (secret mount excluded)  │
                                           └───────────────┬────────────────┘
                                                           ▼
                                      image layer + cache key do NOT contain
                                      the secret value (only the secret ID)
```

- **Session channel:** the client streams secrets and the agent socket to the builder over the same gRPC session it uses for the build context; nothing is stored in the build context.
- **Cache key:** the secret *ID* and mount options participate in the key, the *value* does not. Rotating a secret therefore does **not** invalidate the cache; force a rebuild with `--no-cache` or a cache-busting `ARG` when it matters.
- **tmpfs:** file-type secrets live in memory for the duration of the single `RUN`.

## 5. Hands-On

### 5.1 The Wrong Way: ARG and COPY Leak

```dockerfile
# BAD: do not do this
FROM node:22-alpine
ARG NPM_TOKEN
RUN echo "//registry.npmjs.org/:_authToken=${NPM_TOKEN}" > ~/.npmrc \
 && npm ci \
 && rm ~/.npmrc
```

```bash
docker build --build-arg NPM_TOKEN=npm_abc123 -t leaky .
docker history --no-trunc leaky | grep -i npm_
```

```text
<missing>   2 minutes ago   RUN |1 NPM_TOKEN=npm_abc123 /bin/sh -c echo "//registry... # buildkit
```

The token is in the history, in the layer that wrote `~/.npmrc` (the `rm` only hides it in a later layer), and in provenance metadata.

### 5.2 Secret File Mount

```dockerfile
# syntax=docker/dockerfile:1
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    npm ci --omit=dev
COPY . .
CMD ["node", "server.js"]
```

```bash
docker build --secret id=npmrc,src=$HOME/.npmrc -t app:1 .
docker history --no-trunc app:1 | grep -ci token
```

```text
0
```

`target` sets where the file appears; without it the file is at `/run/secrets/npmrc`. Mount options include `required=true` (fail if not supplied), `mode=0400`, `uid=` and `gid=`.

### 5.3 Secret as an Environment Variable

Supported in recent Dockerfile frontends (`dockerfile:1`) and clients:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.13-slim
COPY requirements.txt .
RUN --mount=type=secret,id=PIP_INDEX_URL,env=PIP_INDEX_URL \
    pip install --no-cache-dir -r requirements.txt
```

```bash
export PIP_INDEX_URL='https://user:pass@pypi.internal.example/simple'
docker build --secret id=PIP_INDEX_URL,env=PIP_INDEX_URL -t py-app .
```

The variable exists only inside that one command's process environment. It is not in `ENV`, not in `docker inspect`, and not in a later `RUN`.

### 5.4 Verifying That the Secret Is Absent

```bash
docker run --rm app:1 ls -la /root/.npmrc /run/secrets 2>&1
docker save app:1 | tar -xO | grep -a -c "npm_abc123"
```

```text
ls: cannot access '/root/.npmrc': No such file or directory
ls: cannot access '/run/secrets': No such file or directory
0
```

Run the `docker save | grep` check in CI against a known canary value to prove no regression. Use a harmless dummy secret for this test.

### 5.5 SSH Forwarding for Private Git Dependencies

```dockerfile
# syntax=docker/dockerfile:1
FROM golang:1.23 AS build
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client \
 && rm -rf /var/lib/apt/lists/*
# Trust GitHub's host key (pin the fingerprint in real pipelines)
RUN mkdir -p -m 0700 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts
WORKDIR /src
COPY go.mod go.sum ./
ENV GOPRIVATE=github.com/acme/*
RUN --mount=type=ssh \
    git config --global url."git@github.com:".insteadOf "https://github.com/" \
 && go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app ./cmd/app

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/app /app
ENTRYPOINT ["/app"]
```

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
docker build --ssh default -t private-go-app .
```

```text
=> [build 5/7] RUN --mount=type=ssh git config ... && go mod download     6.1s
```

`--ssh default` forwards whatever `SSH_AUTH_SOCK` points to. You can also name a specific socket (`--ssh github=$SSH_AUTH_SOCK`) or key file (`--ssh mykey=$HOME/.ssh/id_ed25519`, passphrase-less keys only), then reference it with `--mount=type=ssh,id=github`.

> 💡 **Tip:** `git config --global ...` inside the `RUN` that has the mount writes to the filesystem and would persist into the layer. That is harmless here because the config contains no secret, and the multi-stage final image discards the whole build stage anyway.

### 5.6 Compose and CI Wiring

```yaml
# compose.yaml
services:
  api:
    build:
      context: .
      secrets:
        - npmrc
      ssh:
        - default
secrets:
  npmrc:
    file: ${HOME}/.npmrc
```

```yaml
# GitHub Actions fragment
- uses: docker/build-push-action@v6
  with:
    context: .
    push: true
    tags: ghcr.io/acme/app:${{ github.sha }}
    secrets: |
      npmrc=${{ secrets.NPMRC_CONTENT }}
    ssh: |
      default=${{ env.SSH_AUTH_SOCK }}
```

In the Actions example, the `secrets:` input takes `id=value` pairs and the action writes them to temporary files for BuildKit. Pipelines are covered in [§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md) and [§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md).

### 5.7 Static Checks for Mistakes

```bash
docker build --check .
```

```text
 1 warning found (use docker --debug to expand):
 - SecretsUsedInArgOrEnv: Do not use ARG or ENV instructions for sensitive data (ARG "NPM_TOKEN") (line 2)
```

Build checks (BuildKit with Dockerfile frontend 1.8+) flag secret-looking names in `ARG` and `ENV`. Add `--check` to CI as a gate.

## 6. Production Usage Notes

- **Prefer short-lived credentials:** CI-issued tokens (GitHub Actions OIDC, GitLab job tokens, cloud-provider STS) that expire minutes after the build limit blast radius if one does leak.
- **Prefer ssh-agent over key files:** the private key never enters the builder, which matters when the builder is remote or shared (`docker buildx` remote drivers, BuildKit in Kubernetes).
- **Scope tokens read-only** to exactly the registries or repositories needed.
- **Secret ID naming:** use stable, descriptive IDs (`npmrc`, `pip_conf`, `github_token`); IDs appear in cache keys and logs, values never do.
- **Cache sharing:** exported caches ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)) contain layer outputs, not secrets, unless a command writes secret-derived data (such as a generated config containing the token) into its output.
- **Rotate after exposure:** if a secret ever hit a layer, assume compromise and rotate it; rebuilding does not remove copies already pushed.

## 7. Security Considerations

- **Output exfiltration:** a secret mounted into a `RUN` is readable by every process in that command, including scripts from `npm install` or `pip install` (supply-chain attack surface, [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Mount secrets only on the specific step that needs them and use read-only tokens.
- **Echoing:** `RUN echo $TOKEN` or `cat /run/secrets/x` prints the value into build logs, which CI systems retain. Mask secrets in CI and never `set -x` around secret use.
- **Command-line leakage:** avoid passing the secret as a command argument (`curl -u user:$(cat /run/secrets/pw)`); it is visible in `ps` inside the build container. Prefer tool-native config files.
- **Provenance and SBOM:** BuildKit attestations (`--provenance=mode=max`) record build args and the Dockerfile; secrets are not recorded, but build args are. Never put sensitive data in args.
- **Agent hijack:** a forwarded agent lets build steps request signatures for *any* key loaded in it. Use a dedicated agent with a single deploy key, not your personal agent with all keys.
- **Host key verification:** `ssh-keyscan` trusts whatever answers first. For production, pin the expected host fingerprint or copy a vetted `known_hosts` through a `COPY` or bind mount.
- **Untrusted Dockerfiles:** building a third-party Dockerfile with `--ssh` or `--secret` hands those credentials to its author. Only forward what a build you have read actually requests.
- **Runtime is different:** these mechanisms do not give the running container any secret. Runtime secret delivery is in [§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `failed to solve: secret NAME not found` | `--secret id=NAME` missing at build, and mount has `required=true` | Pass `--secret id=NAME,src=...` with the exact same ID |
| Secret file empty or missing in step | ID mismatch, or default target `/run/secrets/<id>` not the one the tool reads | Set `target=` to the path the tool expects |
| `unknown flag: --mount` / mount ignored | Legacy builder (`DOCKER_BUILDKIT=0`) or old frontend | Use BuildKit; add `# syntax=docker/dockerfile:1` |
| `Permission denied (publickey)` | Agent has no key, `--ssh` omitted, or no `SSH_AUTH_SOCK` | `ssh-add -l` on host; build with `--ssh default` |
| `Host key verification failed` | `known_hosts` missing for the git host | Add `ssh-keyscan` or pinned `known_hosts` in the build stage |
| `could not open a connection to your authentication agent` in CI | Agent not started in that job | Start `ssh-agent`, `ssh-add` the deploy key, then build |
| Rebuild did not pick up a rotated token | Secret value is not part of the cache key | `--no-cache` for that step, or bump a cache-busting `ARG` |
| `docker build` in Compose ignores secrets | `secrets:` listed under service rather than `build.secrets` | Put it under `build:` and define top-level `secrets:` |

## 9. Best Practices

- Use `--mount=type=secret` for every credential needed during build; never `ARG`, `ENV` or `COPY` for secrets.
- Put `# syntax=docker/dockerfile:1` first so you get current mount features.
- Mount secrets only on the single `RUN` that needs them, and keep that `RUN` minimal.
- Use `--mount=type=ssh` with a dedicated, restricted agent or deploy key rather than copying keys.
- Pair with multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)) so any build-time tooling and config is discarded from the final image.
- Add `docker build --check` and a canary-value `docker save | grep` test to CI.
- Prefer short-lived, read-only, narrowly scoped tokens.
- Keep secrets out of `.dockerignore`-unprotected build contexts: add `.npmrc`, `.env`, `*.pem` to `.dockerignore` ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)) so `COPY . .` cannot sweep them in.
- Rotate any credential that has ever appeared in an image, log or history.

## 10. Common Anti-Patterns / Mistakes

- `ARG TOKEN` or `ENV TOKEN` for credentials (recorded in history and provenance).
- `COPY id_rsa /root/.ssh/` followed by `RUN rm /root/.ssh/id_rsa` (the key is still in the earlier layer).
- `COPY . .` before secrets are excluded, which copies a local `.env` or `.npmrc` into the image.
- Embedding credentials in URLs: `RUN git clone https://user:token@github.com/...` (stored in layer metadata and history).
- Multi-stage "protection" by copying a whole stage's filesystem into the final stage (`COPY --from=build / /`), which brings the leaked file along.
- Using `--ssh` with a personal agent holding every key you own.
- Echoing secrets into logs to "debug".

## 11. Interview Questions

**🎯 Beginner:** _"Why is `ARG NPM_TOKEN` followed by `RUN ... rm ~/.npmrc` not a safe way to install private packages?"_
**Model answer:** Every Dockerfile instruction produces a layer or metadata that stays in the image. The `ARG` value is recorded in the image history and the command that wrote `~/.npmrc` created a layer containing the token. A later `rm` only adds a whiteout in a new layer; the earlier layer still holds the file and can be extracted with `docker save` or inspected with `docker history --no-trunc`. The safe way is `RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci` with `docker build --secret id=npmrc,src=$HOME/.npmrc`, since the mount is in-memory and not part of the layer diff.
_What the interviewer is probing for:_ Understanding that layers are immutable and additive, and knowing the BuildKit secret mount as the correct primitive.

**🎯 Intermediate:** _"You need to `go mod download` private GitHub modules during build. Walk me through the Dockerfile and build command, and say what protects the key."_
**Model answer:** Add `# syntax=docker/dockerfile:1`, install `git` and `openssh-client` in the build stage, add GitHub's host key to `known_hosts`, set `GOPRIVATE`, and run the download with `RUN --mount=type=ssh` after a `git config url.<ssh>.insteadOf` rewrite. Build with `docker build --ssh default .` after `ssh-add` of a deploy key. The private key never enters the builder: BuildKit forwards the agent socket and only signature requests cross it. The socket is mounted only during that `RUN`, so the layer and cache contain nothing sensitive. A multi-stage build keeps git, ssh and module caches out of the final image.
_What the interviewer is probing for:_ Practical fluency with the `ssh` mount, host key handling, and the agent trust model.

**🎯 Senior:** _"A security scan finds a live API key in a production image built last year. What do you do, and what changes to the build pipeline prevent recurrence?"_
**Model answer:** First treat the key as compromised: revoke and rotate it immediately, review access logs, then identify every image tag, registry replica and cache containing the layer (including exported CI caches) and delete or expire them, since removal does not un-leak copies already pulled. Find the root cause with `docker history --no-trunc` and layer inspection (usually `ARG`/`ENV`/`COPY`). Prevent recurrence by moving to `--mount=type=secret`, adding `docker build --check` and a secret scanner such as Trivy ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)) as blocking CI gates, tightening `.dockerignore`, using short-lived OIDC-issued tokens, and adding a canary test that fails if a known dummy secret appears in `docker save` output.
_What the interviewer is probing for:_ Incident response order (rotate first), understanding that deletion does not recall leaked data, and layered preventive controls.

**🎯 Architect:** _"Design the build-time credential strategy for 200 repositories that all pull from a private package registry and private Git, built on shared remote BuildKit builders."_
**Model answer:** Avoid long-lived personal credentials. Issue per-job, short-lived, read-only tokens through workload identity (OIDC federation to the registry and Git provider) and pass them with `--secret id=...,env=...` so they exist only in the build process and are never written to disk on a shared builder. Use SSH agent forwarding or tokens instead of key files because remote builders must never store keys. Isolate builders per trust boundary (no shared builder between untrusted and trusted repos), because a secret mounted into a step is readable by that step's code. Publish a reusable Dockerfile template and CI action that already contain the correct mounts, enforce `docker build --check` and image secret scanning as policy, and attach provenance/SBOM attestations ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Reduce secrets needed at all by mirroring dependencies through an internal proxy reachable without credentials inside the build network where policy allows.
_What the interviewer is probing for:_ Threat modeling shared builders, credential lifetime and scope, and platform-level enforcement rather than per-repo discipline.

## 12. Common Misconceptions

- "Deleting the file in a later `RUN` removes it from the image." The earlier layer retains it.
- "Multi-stage builds make `ARG` secrets safe." Build args are still recorded in the stage's history and in provenance; only the final stage's history ships, but cache and attestations may still expose them.
- "Secrets in `--build-arg` are hidden because the build is private." They appear in `docker history` and provenance.
- "`--mount=type=secret` gives the running container the secret." It exists only for the single `RUN`.
- "Rotating the secret rebuilds the layer." The value is excluded from the cache key.
- "SSH forwarding copies my key into the builder." Only the agent socket is forwarded.
- "Using `ENV` and unsetting it later is fine." The `ENV` layer metadata persists.

## 13. 🔑 Key Takeaways

- Use `RUN --mount=type=secret` for files or `env=` variables, supplied via `docker build --secret`.
- Use `RUN --mount=type=ssh` with `docker build --ssh default` for private Git; the key stays on the host.
- Never use `ARG`, `ENV`, `COPY` or credentials in URLs for secrets; later deletion does not help.
- Secret values are not in the cache key: rotation does not invalidate cache.
- Verify with `docker history --no-trunc`, `docker save | grep`, and `docker build --check`.
- Short-lived, scoped credentials and isolated builders limit damage when something still goes wrong.

## 14. Related Concepts & What's Next

Related: BuildKit features ([§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), cache invalidation ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), runtime secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), supply chain security ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), and build-arg discipline ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)). Next, [§77](Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md) turns to making the images you build smaller, which also shrinks the attack surface.

**Next Section:** [§77](Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md) — `Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md`
