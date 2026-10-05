# Section 69 (Part 9): Authentication: docker login and Credential Helpers

## 1. Definition

**Plain language:** `docker login` proves who you are to a registry and saves that proof so later `push` and `pull` commands succeed. A **credential helper** is a small external program that stores and fetches those secrets in a safe place (OS keychain, cloud SDK) instead of leaving them in a plain file.

**Precise definition:** The Docker CLI reads client configuration from `~/.docker/config.json` (or the directory in `DOCKER_CONFIG`). Its `auths` map holds per-registry entries; its `credsStore` key names a helper used for all registries, and `credHelpers` maps specific registries to specific helpers. A helper is an executable named `docker-credential-<name>` that implements a stdin/stdout protocol with four commands: `get`, `store`, `erase` and `list`. Registries authenticate clients with the Distribution token flow: an unauthenticated request returns `401` with a `WWW-Authenticate: Bearer realm=...,service=...,scope=...` header; the client then calls that realm with its credentials (Basic auth) and receives a short-lived bearer token to retry the request. Note that the credentials are applied by the **client** (CLI, BuildKit, buildx), not by the daemon, with the exception of Swarm/`--with-registry-auth` flows.

> ⚠️ **Warning:** Without a helper, the `auth` value in `config.json` is merely base64 of `user:password`. It is encoding, not encryption, and anyone who can read the file can use it.

## 2. Why This Matters

- Leaked registry credentials let an attacker pull private images (source and secrets inside) or push poisoned ones ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- Cloud registries use tokens that expire in hours ([§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)); helpers remove manual re-login.
- CI jobs, shared build servers and developer laptops each need a different, least-privilege authentication method.
- `unauthorized: incorrect username or password`, `no basic auth credentials` and Docker Hub rate-limit surprises are among the most common Docker errors.

## 3. Prerequisites and Dependencies

Requires the client/server split ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)), registry basics ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)) and secrets hygiene ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)). Installing Docker Desktop or Engine is in [§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md). Build-time use of credentials is in [§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md), and pipeline use in [§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md) and [§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md).

## 4. Architecture / Conceptual Diagram

```text
  docker push registry.example.com/app:1
        │
        ▼
  Docker CLI / BuildKit client
        │ 1. look up credentials for "registry.example.com"
        ▼
  ~/.docker/config.json
  ┌──────────────────────────────────────────────────────────────┐
  │ "credHelpers": { "123.dkr.ecr.eu-west-1.amazonaws.com":"ecr-login" } ◄─ most specific
  │ "credsStore":  "desktop" | "osxkeychain" | "wincred" | "secretservice" | "pass"
  │ "auths":       { "registry.example.com": { "auth": "base64(user:pw)" } } ◄─ plaintext fallback
  └───────────┬──────────────────────────────────────────────────┘
              │ exec  docker-credential-<helper> get   (server URL on stdin)
              ▼
     helper returns {"ServerURL","Username","Secret"}  (JSON on stdout)
              │
              ▼
  2. GET /v2/ ─────────────────────────────────────────────► Registry
  3. ◄────── 401  WWW-Authenticate: Bearer realm="https://auth..",service="..",scope=".."
  4. POST/GET realm with Basic(user:secret) ───────────────► Token service
  5. ◄────── bearer token (minutes to hours)
  6. push/pull blobs and manifests with  Authorization: Bearer <token> ──► Registry
```

- **Lookup order:** `credHelpers[registry]`, then `credsStore`, then `auths`.
- **Secrets never reach the daemon** for ordinary `push` and `pull`; the CLI talks to the registry directly for push, and sends credentials (`X-Registry-Auth`) with API pulls.
- **Token vs password:** the registry-held secret is exchanged for a bearer token with a scope such as `repository:app:pull,push`.

## 5. Hands-On

### 5.1 Interactive and Non-Interactive Login

```bash
docker login                               # Docker Hub, prompts for user and password/PAT
docker login registry.example.com          # a specific registry

# Non-interactive, secret never appears in argv or shell history
echo "$REGISTRY_TOKEN" | docker login registry.example.com -u ci-bot --password-stdin
```

```text
Login Succeeded
```

Never use `-p`/`--password`: it exposes the secret in `ps` output and shell history, and Docker prints a warning for it. For Docker Hub use a **personal access token** or an **organization access token** with the minimum scope (read-only for pulls), not the account password.

### 5.2 What Gets Written

```bash
cat ~/.docker/config.json
```

```json
{
  "auths": {
    "registry.example.com": { "auth": "<base64-of-user:password>" }
  }
}
```

```bash
echo '<base64-of-user:password>' | base64 -d      # user:password   <- trivially reversible
```

This is what a Linux server without a helper looks like. On a desktop with a helper the entry is `"registry.example.com": {}` and the secret sits in the keychain.

### 5.3 Install and Configure a Credential Helper

```json
{
  "credsStore": "desktop"
}
```

Typical helper names by platform:

| Platform | Helper binary | Backend |
|---|---|---|
| Docker Desktop (all OS) | `docker-credential-desktop` | Desktop's secure store |
| macOS | `docker-credential-osxkeychain` | Keychain |
| Windows | `docker-credential-wincred` | Credential Manager |
| Linux desktop | `docker-credential-secretservice` | GNOME Keyring / libsecret |
| Linux server | `docker-credential-pass` | `pass` + GPG |

Test a helper directly, using the same protocol Docker uses:

```bash
echo "registry.example.com" | docker-credential-pass get
docker-credential-pass list
```

```text
{"ServerURL":"registry.example.com","Username":"ci-bot","Secret":"s3cret"}
```

> ⚠️ **Warning:** `list` and `get` print secrets in clear text. Run them only in a private terminal.

### 5.4 Per-Registry Helpers for Cloud Registries

```json
{
  "credHelpers": {
    "123456789012.dkr.ecr.eu-west-1.amazonaws.com": "ecr-login",
    "public.ecr.aws": "ecr-login",
    "europe-west1-docker.pkg.dev": "gcloud",
    "contosoreg.azurecr.io": "acr-env"
  }
}
```

- **`ecr-login`** is `docker-credential-ecr-login` from the open-source amazon-ecr-credential-helper. It uses the standard AWS credential chain (env vars, profile, SSO, instance role) and requests a fresh token on every operation, so there is no 12-hour expiry problem and nothing is written to disk.
- **`gcloud`** is `docker-credential-gcloud`, installed with the Google Cloud CLI; `gcloud auth configure-docker europe-west1-docker.pkg.dev` writes the entry for you.
- **Azure:** `az acr login --name contosoreg` writes a short-lived token (about 3 hours) into the config; Microsoft also publishes a Docker credential helper for ACR (`docker-credential-acr-env`, which reads service-principal credentials from environment variables) for unattended use.

### 5.5 Authenticating Without Touching Disk

```bash
# Use a throwaway config directory for one job, delete it afterwards
export DOCKER_CONFIG=$(mktemp -d)
echo "$TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin
docker push ghcr.io/acme/app:1.4.2
rm -rf "$DOCKER_CONFIG"          # only ever a directory this job created
docker logout ghcr.io            # if you used the default config location
```

`DOCKER_CONFIG` also lets two accounts on the same machine stay separate. `docker logout <registry>` removes the stored entry, and for helpers calls `erase`.

### 5.6 Cloud Login Patterns

```bash
# ECR (token valid 12 hours)
aws ecr get-login-password --region eu-west-1 \
  | docker login --username AWS --password-stdin 123456789012.dkr.ecr.eu-west-1.amazonaws.com

# ACR without a local docker daemon login helper (CI)
TOKEN=$(az acr login --name contosoreg --expose-token --output tsv --query accessToken)
echo "$TOKEN" | docker login contosoreg.azurecr.io \
  --username 00000000-0000-0000-0000-000000000000 --password-stdin

# Artifact Registry with a short-lived OAuth token
gcloud auth print-access-token \
  | docker login -u oauth2accesstoken --password-stdin https://europe-west1-docker.pkg.dev
```

### 5.7 CI: Registry Login with OIDC (GitHub Actions)

```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::123456789012:role/ci-ecr-push
      aws-region: eu-west-1
  - uses: aws-actions/amazon-ecr-login@v2
  - run: docker push 123456789012.dkr.ecr.eu-west-1.amazonaws.com/app:${{ github.sha }}
```

No long-lived key exists; the job gets a role session that expires.

### 5.8 Pull Secrets for Other Consumers

```bash
# Kubernetes: build an imagePullSecret from a token
kubectl create secret docker-registry regcred \
  --docker-server=registry.example.com --docker-username=ci-bot \
  --docker-password="$REGISTRY_TOKEN"

# Swarm: forward the CLI's credentials to the nodes
docker service create --with-registry-auth --name web registry.example.com/web:1
```

A Kubernetes `kubernetes.io/dockerconfigjson` secret is the same `config.json` format, so it carries the same base64 weakness; prefer node identity ([§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)).

## 6. Production Usage Notes

- **Developer laptops:** Docker Desktop or an OS-keychain helper; log in with a PAT, not the account password, and enable 2FA on the account.
- **CI runners:** prefer OIDC to cloud registries; otherwise inject a short-scoped token as a masked secret and use `--password-stdin`. Use a per-job `DOCKER_CONFIG` on shared runners so one job cannot reuse another's login.
- **Build servers and VMs:** use the cloud helper (`ecr-login`, `gcloud`) bound to the instance or workload identity, so no secrets live on disk.
- **Docker Hub:** authenticated pulls get higher rate limits ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)); log in on build hosts, or mirror through a pull-through cache.
- **BuildKit and buildx** read the same client config, so a `docker login` covers `docker buildx build --push` too ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md), [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)).
- **Rootless Docker** and `sudo`: credentials belong to the user whose `HOME` runs the CLI. `sudo docker login` writes `/root/.docker/config.json`, not yours.
- **Rotation:** short-lived tokens and PATs with expiry dates; revoke immediately on offboarding or suspected leak.

## 7. Security Considerations

- **Base64 is not protection.** Treat `config.json` like a private key: mode `0600`, never in an image, a repository or a shared volume.
- **Never mount `~/.docker` into containers** unless the workload truly needs registry access, and then mount a dedicated, minimal-scope config read-only.
- **Do not bake credentials into images.** `COPY config.json` or `ARG TOKEN` leaves secrets in layers and history ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md), [§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Least privilege:** read-only tokens for pull, repository-scoped push tokens for CI, separate identities per pipeline.
- **TLS only.** Logging in over plain HTTP to an "insecure registry" sends credentials unencrypted ([§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)).
- **Helpers are executables found on `PATH`:** a malicious binary named `docker-credential-x` would receive your secrets, so install helpers only from trusted sources and keep `PATH` clean.
- **Exposure of the Docker socket** gives full daemon control, which includes using credentials sent through the API ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Logging:** `--password-stdin` keeps secrets out of process lists; CI log masking should cover token variables.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Error saving credentials: error storing credentials ... exit status 1` | Helper configured but its backend is unavailable (no keyring, no D-Bus, `pass` not initialized) | Remove `credsStore` or set up the backend (`pass init`, unlock keyring) |
| `error getting credentials - err: exec: "docker-credential-desktop": executable file not found in $PATH` | `credsStore` points at a helper that is not installed (often after removing Docker Desktop) | Install the helper or delete `credsStore` from `config.json` |
| `unauthorized: incorrect username or password` | Wrong secret, expired PAT, or using the account password where SSO/2FA requires a token | Create a new PAT and log in again |
| `no basic auth credentials` | No login for that exact registry hostname | Log in to the same hostname used in the image name, including port |
| Works with `docker`, fails with `sudo docker` (or vice versa) | Different `HOME`, different `config.json` | Log in as the user that runs the command |
| ECR/ACR works then fails hours later | Token expired | Use a credential helper or re-run login in the job |
| `Login Succeeded` but pull of a private image still denied | Account lacks repository permission | Check repository access, not the login |
| Windows/WSL mismatch: login in one side not seen in the other | Separate config files | Share one helper, or set `DOCKER_CONFIG` consistently |
| `denied: requested access to the resource is denied` on push | Wrong namespace or no write permission | Tag with the correct `org/repo`; check role |

Diagnose with `docker logout <registry>` followed by a fresh login, `cat ~/.docker/config.json` (look for keys, never share the file) and `DOCKER_CONFIG` or `echo $DOCKER_CONFIG`.

## 9. Best Practices

- Always `--password-stdin`; never `-p`.
- Use a credential helper on every machine that holds human or long-lived credentials.
- Prefer federated identity (OIDC, workload identity, instance roles) over stored secrets.
- Use access tokens with the least scope and an expiry, never account passwords.
- Use a job-scoped `DOCKER_CONFIG` on shared CI runners and clean it up afterwards.
- Log out at the end of ephemeral jobs when the config location is shared.
- Keep `config.json` out of backups, images and repositories, and add it to scanning rules ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).

## 10. Common Anti-Patterns / Mistakes

- `docker login -u user -p password` in scripts, committing the secret to CI logs.
- Believing the base64 `auth` string is encrypted and sharing `config.json` in tickets or chat.
- Using one all-powerful shared account for every pipeline and developer.
- Committing `.docker/config.json` or copying it into an image to "make the build log in".
- Mounting the host's `~/.docker` into build or app containers.
- Leaving `credsStore: desktop` in a config copied to a server that has no such helper.
- Hard-coding cloud registry passwords instead of using the provider's helper or OIDC.

## 11. Interview Questions

**🎯 Beginner:** _"Where does `docker login` store your credentials, and is it secure?"_
**Model answer:** It stores them in `~/.docker/config.json`. If a credential helper is configured via `credsStore` or `credHelpers`, the secret goes into the OS keychain or the helper's backend and the file only has an empty placeholder. If not, the file contains `auths` entries with `user:password` base64-encoded, which is encoding rather than encryption, so anyone who can read the file can reuse it. Use a helper or a short-lived token, and restrict the file permissions.
_What the interviewer is probing for:_ Knowing the base64 weakness and that helpers move secrets to a secure store.

**🎯 Intermediate:** _"How would you log in to a registry from a CI script without leaking the password?"_
**Model answer:** Supply the secret through a masked CI variable and pipe it with `echo "$TOKEN" | docker login host -u user --password-stdin`, never `-p`, because arguments show up in `ps` and logs. Use a token with minimal scope. On shared runners set a job-specific `DOCKER_CONFIG` directory and remove it at the end, or run `docker logout`. Where the registry supports it, avoid stored secrets altogether with OIDC federation (for example GitHub Actions to an AWS role for ECR).
_What the interviewer is probing for:_ Practical secret handling in automation, and awareness of federation.

**🎯 Senior:** _"Explain how a credential helper is invoked and how you would debug 'executable file not found' or 'error storing credentials'."_
**Model answer:** The CLI resolves the helper for a registry in order `credHelpers`, `credsStore`, then `auths`, and runs `docker-credential-<name>` from `PATH`, sending the server URL on stdin for `get` or JSON for `store`, and reading JSON back. "Executable not found" means `config.json` names a helper that is not installed, common after removing Docker Desktop or copying a laptop config to a server; remove the key or install the helper. "Error storing credentials" means the helper ran but its backend failed, such as no unlocked keyring, missing D-Bus session, or an uninitialized `pass` store. I would call the helper manually (`echo host | docker-credential-pass get`), check `PATH`, check the environment of the process (cron and systemd lack the desktop session), and as a fallback use an explicit `DOCKER_CONFIG` with no `credsStore`.
_What the interviewer is probing for:_ Understanding the helper protocol and lookup order well enough to debug it.

**🎯 Architect:** _"Design registry authentication for 300 developers, 40 pipelines and 5 Kubernetes clusters across two clouds."_
**Model answer:** Humans authenticate with SSO to the cloud CLIs and use credential helpers (`ecr-login`, `gcloud`, `az acr login`) so tokens are short-lived and nothing sits in plaintext; any Docker Hub use goes through a PAT in the OS keychain or a pull-through cache. Pipelines use OIDC federation to per-pipeline roles that can push only to their own repositories, with no stored secrets. Clusters pull through workload or node identity bound to read-only roles, avoiding imagePullSecrets; where a secret is unavoidable it is synced from a secret manager and rotated. Policy sits in IaC: repository-scoped permissions, token expiry, audit logs for all pushes and failed auths, and alerting on credential use from unexpected networks. Break-glass accounts are separate, monitored and vaulted. Add image signing so even a stolen push credential cannot produce an artifact admission control will accept.
_What the interviewer is probing for:_ Identity-based design at scale, separation of duties and layered defenses beyond the login itself.

## 12. Common Misconceptions

- "The `auth` string in `config.json` is encrypted." It is plain base64.
- "`docker login` authenticates the daemon." The client (CLI/BuildKit) holds and uses the credentials.
- "Logging in once covers all registries." Credentials are per registry hostname.
- "A Docker Hub password and a PAT are equivalent." A PAT is revocable, scoped and works when 2FA is enabled.
- "`gcloud auth configure-docker` or `docker-credential-ecr-login` performs a login." They install lookups that fetch credentials on demand.
- "Credential helpers are only for desktops." They are equally useful on servers (`pass`, `ecr-login`, `gcloud`).

## 13. 🔑 Key Takeaways

- Config lives in `~/.docker/config.json` (or `DOCKER_CONFIG`); lookup order is `credHelpers`, `credsStore`, `auths`.
- Without a helper, secrets are base64 only; use a helper or short-lived tokens.
- Always `--password-stdin`; never `-p`.
- Helpers are `docker-credential-<name>` executables speaking `get`/`store`/`erase`/`list`.
- Prefer OIDC and workload identity over stored credentials; use PATs with minimal scope.
- Keep credentials out of images, repositories, logs and shared mounts.

## 14. Related Concepts & What's Next

Related: Docker Hub tokens and rate limits ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)), private registry auth ([§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)), cloud registries ([§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)), secrets management ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)). Next, [§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md) puts authenticated access to work in end-to-end push and pull workflows and tagging strategies.

**Next Section:** [§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md) — `Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md`
