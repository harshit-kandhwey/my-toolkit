# Section 64 (Part 8): Secrets Management: Docker Secrets and Avoiding ENV-Based Secrets

## 1. Definition

**Plain language:** A secret is any value that grants access (password, API key, TLS private key, token). Secrets management is the discipline of getting those values into a running container without baking them into the image, the Dockerfile, the Compose file, the shell history or the process environment where anything with read access can see them.

**Precise definition:** Docker offers three distinct mechanisms, and they are easy to confuse:

- **Swarm secrets** (`docker secret create`, `docker service create --secret`): stored encrypted in the Swarm Raft log, delivered only to nodes running a task that needs them, and mounted as an in-memory (tmpfs) file at `/run/secrets/<name>` inside the container.
- **Compose secrets** (top-level `secrets:` plus per-service `secrets:`): the same file-at-`/run/secrets/<name>` interface, but on a single host the source is a local file or an environment variable and the mount is a bind mount, not an encrypted store.
- **Build secrets** (`RUN --mount=type=secret`): available only during one `RUN` step and never written to a layer; covered in [§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md).

The anti-pattern they replace is the **environment variable secret** (`ENV DB_PASSWORD=...`, `-e DB_PASSWORD=...`, `ARG TOKEN`). Environment values are stored in image history or container config, visible in `docker inspect`, readable from `/proc/<pid>/environ`, inherited by every child process, and routinely dumped by crash reporters and debug endpoints.

> 💡 **Tip:** Prefer a file over an environment variable, and a short-lived credential fetched at runtime over either. Many official images support the `_FILE` convention (`POSTGRES_PASSWORD_FILE=/run/secrets/db_password`) precisely for this reason.

## 2. Why This Matters

- Secrets leaked via `ENV`/`ARG` live forever in image layers and registries; deleting the file in a later layer does not remove it ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md), [§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)).
- A single `docker inspect` by anyone in the `docker` group reveals every `-e` value; the Docker socket is effectively root ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- Credential scanners find leaked keys in public images within minutes; a leaked cloud key is an incident, not a bug.
- Secret handling is a standard audit finding (CIS Docker Benchmark, SOC 2, PCI) and a frequent interview topic.

## 3. Prerequisites and Dependencies

Requires image layers and history ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `ENV` and `ARG` semantics ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), and Compose environment handling ([§36](../Part5/Section-36-Part5-Environment-Variables-and-env-Files.md)). The tmpfs mount type is explained in [§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md). Swarm secrets assume a Swarm cluster ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)). Non-root file ownership matters for reading secrets ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)).

## 4. Architecture / Conceptual Diagram

```text
  WHERE A SECRET CAN LEAK (ENV path)                 SAFER PATH (file path)

  Dockerfile  ENV/ARG ──► image layer + history      secret store (Vault / SM / Swarm)
  docker run -e ───────► docker inspect (Config.Env)        │
  compose environment: ► config + `compose config`          ▼
  process env ─────────► /proc/<pid>/environ          /run/secrets/db_password
                         child processes, core dumps   (tmpfs in Swarm, bind in Compose)
                         error pages, debug logs              │
                                                              ▼
                                                     app reads file at startup,
                                                     keeps value in memory only

  Swarm secret delivery

  manager (Raft, encrypted at rest)
       │  mutual TLS, only to nodes with a task needing it
       ▼
  worker node ──► tmpfs ──► /run/secrets/<name> (mode 0444 by default, configurable)
                            gone when the task stops
```

- **Swarm:** secrets are encrypted in Raft and in transit, and exist on disk of a worker only in tmpfs.
- **Compose (single host):** `secrets:` with `file:` bind-mounts a host file read-only; it is only as safe as the host file permissions.
- **Build:** the secret mount exists only for the duration of that `RUN` and leaves no layer.

## 5. Hands-On

### 5.1 Demonstrating the ENV Leak

```bash
docker run -d --name leaky -e DB_PASSWORD=hunter2 alpine:3.20 sleep 300
docker inspect leaky --format '{{json .Config.Env}}'
docker exec leaky sh -c 'tr "\0" "\n" < /proc/1/environ | grep DB_'
docker rm -f leaky
```

```text
["DB_PASSWORD=hunter2","PATH=/usr/local/sbin:..."]
DB_PASSWORD=hunter2
```

### 5.2 The Dockerfile Leak (Never Do This)

```dockerfile
FROM alpine:3.20
ARG NPM_TOKEN
ENV API_KEY=<your-api-key>
RUN echo "//registry/:_authToken=${NPM_TOKEN}" > ~/.npmrc && npm ci && rm ~/.npmrc
```

```bash
docker build --build-arg NPM_TOKEN=tok123 -t leak-demo .
docker history --no-trunc leak-demo | grep -E 'API_KEY|NPM_TOKEN'
```

Both values appear in `docker history`: `ENV` is stored in the config, and `ARG` values used by a `RUN` are recorded in the history entry. The `rm` created a new layer; the earlier layer still holds the file.

### 5.3 Swarm Secrets

```bash
docker swarm init
printf 'S3cr3tPass' | docker secret create db_password -
docker secret ls

docker service create --name db \
  --secret db_password \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/db_password \
  postgres:16

docker exec $(docker ps -q -f name=db) ls -l /run/secrets/
docker exec $(docker ps -q -f name=db) mount | grep secrets
```

```text
ID                          NAME          CREATED         UPDATED
x7k2...                     db_password   5 seconds ago   5 seconds ago
-r--r--r-- 1 root root 10 ... db_password
tmpfs on /run/secrets type tmpfs (ro,...)
```

A secret cannot be read back from the CLI (`docker secret inspect` shows metadata only). Secrets are immutable: to rotate, create `db_password_v2`, update the service with `--secret-rm` and `--secret-add source=db_password_v2,target=db_password`.

### 5.4 Compose Secrets (File and Environment Sources)

```yaml
services:
  api:
    image: myorg/api:1.4.2
    secrets:
      - source: db_password
        target: db_password
        uid: "10001"
        mode: 0440
    environment:
      DB_PASSWORD_FILE: /run/secrets/db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt     # keep out of git, chmod 600
  api_token:
    environment: API_TOKEN              # taken from the shell that runs compose
```

```bash
chmod 600 secrets/db_password.txt
echo "secrets/" >> .gitignore
docker compose up -d
docker compose exec api ls -l /run/secrets/
```

Compose reads the `environment:` source from the invoking shell, so the value never appears in the YAML. Note that outside Swarm the mounted file is a bind mount of the host file; `uid`/`gid`/`mode` are honored only by recent Compose releases, so verify on your version and otherwise set permissions on the host file.

### 5.5 Application Side: Read the File, Do Not Re-Export It

```python
from pathlib import Path
import os

def read_secret(name: str) -> str:
    path = os.environ.get(f"{name}_FILE")
    if path:
        return Path(path).read_text().strip()
    raise RuntimeError(f"{name}_FILE not set")

DB_PASSWORD = read_secret("DB_PASSWORD")
```

In an entrypoint script, the official-image pattern is: if `VAR_FILE` is set, read the file into `VAR` for the one process that needs it. Do this inside the final `exec`'d process only, not for the whole container, and see the entrypoint rules in [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md).

### 5.6 Build-Time Secret (Pointer)

```dockerfile
# syntax=docker/dockerfile:1
FROM node:22-alpine
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci
```

```bash
docker build --secret id=npmrc,src=$HOME/.npmrc -t app .
```

The secret is mounted only for that step and never reaches a layer. Full detail, including SSH agent forwarding, is in [§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md).

### 5.7 Auditing an Image for Leaked Secrets

```bash
docker history --no-trunc myorg/api:1.4.2
docker image inspect myorg/api:1.4.2 --format '{{json .Config.Env}}'
trivy image --scanners secret myorg/api:1.4.2
```

Scanning for embedded secrets complements vulnerability scanning ([§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).

## 6. Production Usage Notes

- **External secret managers** (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager) are the source of truth; Docker secrets or a sidecar/agent are only the delivery mechanism.
- **Prefer workload identity** (IAM roles, instance profiles, OIDC) over long-lived static keys; then there is no secret to deliver.
- **Short-lived, dynamic credentials** (Vault database engine, STS tokens) limit blast radius and make rotation automatic.
- **Rotation:** applications must re-read files or restart; design for this. Swarm requires a new secret name per rotation.
- **Kubernetes** Secrets are base64, not encrypted, unless encryption at rest or an external store (External Secrets, CSI driver) is configured; the same file-over-env guidance applies.
- **CI/CD:** inject secrets from the pipeline's secret store at build via `--secret`, and never echo them in logs ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)).
- **`.env` files** are convenient for local dev but are plain text; keep them out of git and out of images ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md) `.dockerignore`).

## 7. Security Considerations

- **Assume anyone with Docker socket access can read all secrets** of every container on the host.
- **Default Swarm secret mode is 0444** and owned by root; set `uid`, `gid`, `mode` so only the app user can read it.
- **Compose file secrets are host files**: protect the directory (0700) and exclude it from backups that leave the trust boundary.
- **Core dumps, debug endpoints and `printenv`-style diagnostics** expose env secrets; files are not exposed this way unless the app logs their content.
- **Shell history** captures `docker run -e KEY=value` and `echo secret | ...`; use `read -s`, files, or `docker secret create name -` from a pipe sourced by a manager.
- **Image secrets are permanent**: if a secret ever entered an image, treat it as compromised and rotate it; rebuilding does not recall pulled copies.
- **Read-only root filesystem and tmpfs** limit where a compromised process can persist stolen values ([§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `permission denied` reading `/run/secrets/x` | App runs as non-root; file owned by root with restrictive mode | Set `uid`/`gid`/`mode` on the secret, or run as matching user |
| `/run/secrets` missing | Service not Swarm and no Compose `secrets:` entry, or secret not listed under the service | Declare it top-level and under the service |
| Compose error: secret file not found | Relative `file:` path wrong or file absent | Path is relative to the Compose file; create it first |
| Password has trailing newline | `echo` added newline when creating the file | Use `printf`, or `.strip()` in the app |
| `docker secret rm` fails: in use | A service still references it | Update services with `--secret-rm` first |
| Secret change not seen by app | Swarm secrets are immutable; app caches value | Create new secret name, redeploy |
| Official image ignores `_FILE` | Not every image supports it | Check the image docs; use a wrapper entrypoint |

## 9. Best Practices

- Deliver secrets as files under `/run/secrets`, and pass only the file path through the environment.
- Use `--mount=type=secret` for build-time credentials; never `ARG`/`ENV`.
- Keep secrets out of git, `.dockerignore`d, and out of Compose YAML values.
- Prefer workload identity and short-lived credentials; automate rotation.
- Grant least privilege per secret and per service; never share one credential across applications.
- Scan images and repositories for secrets in CI; fail the build on findings.
- Redact secrets in logs and avoid printing configuration at startup.

## 10. Common Anti-Patterns / Mistakes

- `ENV PASSWORD=...` or `ARG TOKEN` in a Dockerfile, then deleting the file in a later `RUN`.
- `COPY .env /app/.env` or a missing `.dockerignore` that ships credentials.
- Committing `.env` or `secrets/` to git, then "removing" it in the next commit.
- Passing secrets on the command line (`--password=...`), visible in `ps` and `docker inspect`.
- Treating base64 as encryption.
- One shared "admin" credential injected into every service.
- Logging the full config or environment at startup for debugging.

## 11. Interview Questions

**🎯 Beginner:** _"Why is passing a database password with `docker run -e DB_PASSWORD=...` considered poor practice?"_
**Model answer:** The value becomes part of the container config, so `docker inspect` shows it to anyone with Docker access. It also sits in the process environment (`/proc/<pid>/environ`), is inherited by child processes, and often leaks via crash dumps, debug pages or logs. It lands in shell history too. Better options are a mounted file such as `/run/secrets/db_password`, read by the application, or a runtime fetch from a secrets manager.
_What the interviewer is probing for:_ Knowing the concrete exposure paths of environment variables, not just "it is insecure".

**🎯 Intermediate:** _"A developer used `ARG NPM_TOKEN` and deleted `.npmrc` in a later `RUN`. Is the token safe? How should it be done?"_
**Model answer:** No. Each instruction creates a layer, so the file still exists in the earlier layer, and ARG values used in `RUN` appear in `docker history`. Anyone who pulls the image can extract it. Revoke the token, then use BuildKit: `RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm ci` with `docker build --secret id=npmrc,src=...`. The secret exists only during that step and is not stored in any layer. Multi-stage builds help but do not replace secret mounts, because intermediate stages can still be cached or exported.
_What the interviewer is probing for:_ Understanding layers as immutable and the BuildKit secret mount as the fix.

**🎯 Senior:** _"Compare Swarm secrets, Compose file secrets and Kubernetes Secrets in terms of protection, and describe how you would rotate a database password with zero downtime."_
**Model answer:** Swarm secrets are encrypted in Raft and in transit, delivered only to nodes running the task, and mounted on tmpfs. Compose file secrets are simply bind-mounted host files, so protection equals host file permissions. Kubernetes Secrets are base64 in etcd, encrypted only if encryption at rest or a KMS provider is enabled, and are mounted as tmpfs volumes or exposed as env vars. For rotation, support two valid credentials: create the new password in the database, publish it as a new secret version (a new name in Swarm), roll the service so tasks use it, verify, then revoke the old one. Dynamic credentials from Vault remove most of this by issuing short-lived users per instance.
_What the interviewer is probing for:_ Accurate security properties per platform and a safe, overlapping rotation procedure.

**🎯 Architect:** _"Design secrets handling for 200 containerized services across dev, CI and production, with audit, rotation and no static cloud keys in images."_
**Model answer:** Use workload identity (OIDC federation, IAM roles) so services authenticate without stored keys, and a central manager (Vault or the cloud's secret service) for everything else, with per-service policies and audit logs. Deliver at runtime via the platform's native mechanism (CSI/External Secrets in Kubernetes, Swarm secrets or an agent sidecar elsewhere) as files, never env vars, with short TTLs and automatic renewal. In CI, use OIDC to obtain ephemeral credentials and BuildKit secret mounts for build-time needs. Enforce with policy-as-code: image scanning for embedded secrets, admission rules rejecting `ENV` patterns, and break-glass procedures with alerting. Treat any secret that touched an image or log as burned and automate revocation.
_What the interviewer is probing for:_ Systemic design: identity over secrets, central audit, rotation, and preventive controls.

## 12. Common Misconceptions

- "Docker secrets work with plain `docker run`." The Swarm `docker secret` feature requires Swarm mode; plain `docker run` has no secret store.
- "Compose secrets are encrypted." On a single host they are bind-mounted files.
- "Deleting the file in a later layer removes it." The earlier layer retains it.
- "Environment variables are fine because the container is isolated." Isolation does not protect from Docker API access or the app's own leaks.
- "A private registry makes secrets in images safe." Every puller and every backup becomes a copy.

## 13. 🔑 Key Takeaways

- Never put secrets in `ENV`, `ARG`, image layers, Compose YAML values or command lines.
- Deliver secrets as files in `/run/secrets` and read them in the application (`_FILE` convention).
- Swarm secrets are encrypted and tmpfs-mounted; Compose secrets are bind-mounted host files.
- Use `RUN --mount=type=secret` for build-time credentials.
- Prefer workload identity and short-lived credentials; plan rotation from the start.
- A secret that entered an image must be rotated, not just rebuilt away.

## 14. Related Concepts & What's Next

Related: image anatomy and history ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `ENV`/`ARG` ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), Compose env files ([§36](../Part5/Section-36-Part5-Environment-Variables-and-env-Files.md)), security model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), image scanning ([§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)), build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)). Next, [§65](Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md) covers proving where an image came from and what is inside it.

**Next Section:** [§65](Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md) — `Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md`
