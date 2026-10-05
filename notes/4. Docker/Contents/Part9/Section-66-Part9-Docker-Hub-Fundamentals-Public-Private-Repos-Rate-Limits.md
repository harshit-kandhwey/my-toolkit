# Section 66 (Part 9): Docker Hub Fundamentals: Public/Private Repos, Rate Limits

## 1. Definition

**Plain language:** Docker Hub is the default public library where container images live. When you type `docker pull nginx` and never name a server, Docker Hub is where the image comes from. You can also store your own images there, publicly for anyone or privately for your team.

**Precise definition:** Docker Hub is a hosted OCI-compliant registry (`registry-1.docker.io`, with authentication at `auth.docker.io` and the web UI at `hub.docker.com`) plus a service layer: user and organization namespaces, repositories, access tokens, teams, webhooks, automated vulnerability scanning via Docker Scout, and the curated content programs described below. An image reference without a registry host, such as `nginx:1.27`, is normalized by the CLI to `docker.io/library/nginx:1.27`. Repositories are addressed as `namespace/repository`, where `library/` is the namespace reserved for **Docker Official Images**.

Content categories on Hub:

- **Docker Official Images:** curated, reviewed Dockerfiles for base OSes and popular software (`alpine`, `postgres`, `python`).
- **Verified Publisher:** images from commercial vendors that have a partnership with Docker.
- **Docker-Sponsored Open Source (DSOS):** open-source projects sponsored by Docker, which get free pulls without rate limits for consumers.
- **Community / user repositories:** anything else; no review at all.

> 💡 **Tip:** "Public" means anyone can pull without authentication. It does not mean "trusted". Trust comes from the publisher category and from signing and scanning ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

## 2. Why This Matters

- Almost every `FROM` line in the world resolves to Docker Hub. CI pipelines that pull anonymously from shared runner IPs hit rate limits and fail with `toomanyrequests`, usually at the worst moment.
- Choosing public versus private repositories is a data-exposure decision. A public push is effectively irreversible, because mirrors and caches copy it quickly.
- Plan limits (private repository counts, pull quotas) drive real cost and architecture choices: mirror, pull-through cache, or move to a cloud registry ([§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)).
- Hub is a frequent DCA and interview topic because it is the registry most developers know and the one with the most operational surprises.

## 3. Prerequisites and Dependencies

You should understand image layers and manifests ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) and tag conventions ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)). The registry protocol is defined by the OCI distribution spec ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). Daemon-side mirror settings live in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Authentication mechanics are expanded in [§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md), and push workflows in [§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md).

## 4. Architecture / Conceptual Diagram

```text
  docker pull nginx:1.27
        │  normalized to docker.io/library/nginx:1.27
        ▼
  ┌───────────────┐  1. GET /v2/ ─► 401 + WWW-Authenticate (realm=auth.docker.io)
  │  dockerd /    │  2. GET token (anonymous, or Basic with user + PAT)
  │  containerd   │  3. GET /v2/library/nginx/manifests/1.27   ◄── counted as 1 pull
  └──────┬────────┘  4. GET blobs (config + layers) from CDN (no extra count)
         │
         ▼
  ┌─────────────────────────── Docker Hub ───────────────────────────┐
  │ auth.docker.io  ──► token (scope: repository:library/nginx:pull) │
  │ registry-1.docker.io ──► manifests; blobs redirect to CDN        │
  │ Rate limiter: keyed by IP (anonymous) or account (authenticated) │
  └──────────────────────────────────────────────────────────────────┘

  Who gets which quota (documented model; confirm current numbers on Docker's pricing page)
  ┌─────────────────────┬────────────────────────────────────────────┐
  │ Anonymous           │ Limited per source IP (IPv6: per /64)      │
  │ Authenticated Free  │ Higher limit, counted per account          │
  │ Pro / Team / Business│ Unlimited under fair-use                  │
  │ DSOS / Official     │ Pulling them is still counted for YOU      │
  └─────────────────────┴────────────────────────────────────────────┘
```

- **A "pull" is a manifest GET.** A `HEAD` request for a manifest does not count, which is why `docker pull` of an up-to-date image can be cheaper than it looks, and why tools like `regctl` and `skopeo inspect` can check digests safely.
- **Multi-arch pulls** fetch an index plus one platform manifest. The documented behavior is that the platform-specific fetch is what counts.
- **Anonymous quota is shared** among everyone behind one NAT address, such as a corporate office or a cloud NAT gateway.

## 5. Hands-On

### 5.1 Pull from Hub, Explicitly and Implicitly

```bash
docker pull nginx:1.27
docker pull docker.io/library/nginx:1.27
docker image inspect nginx:1.27 --format '{{.RepoTags}} {{.RepoDigests}}'
```

```text
["nginx:1.27"] ["nginx@sha256:5f2b...c9"]
```

Both pull commands resolve to the same image. Pin by digest (`nginx@sha256:...`) when you need immutability.

### 5.2 Create a Personal Access Token and Log In

Create a token under Account settings, Personal access tokens, with the least scope needed (Read-only for pulls, Read and Write for pushes).

```bash
echo "$DOCKERHUB_PAT" | docker login --username myuser --password-stdin
```

```text
Login Succeeded
```

Use a PAT, never your account password. Organizations should use Organization Access Tokens (OATs) for CI so that pipelines do not depend on a person's account.

### 5.3 Check Your Remaining Rate Limit

Docker documents a dedicated preview repository that returns limit headers without consuming a pull.

```bash
# Anonymous
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" \
  https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep -i ratelimit

# Authenticated
TOKEN=$(curl -s -u "myuser:$DOCKERHUB_PAT" "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl -sI -H "Authorization: Bearer $TOKEN" \
  https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest | grep -i ratelimit
```

```text
ratelimit-limit: 100;w=21600
ratelimit-remaining: 96;w=21600
docker-ratelimit-source: 203.0.113.7
```

`w=21600` is the window in seconds (six hours). The `docker-ratelimit-source` header shows whether you were counted by IP or by account. The numbers above are illustrative; the values returned are authoritative.

### 5.4 Create a Repository and Push

```bash
docker tag myapp:1.0 myuser/myapp:1.0
docker push myuser/myapp:1.0
```

```text
The push refers to repository [docker.io/myuser/myapp]
5f70bf18a086: Pushed
1.0: digest: sha256:9a3c...e1 size: 1570
```

A push to a repository that does not yet exist creates it, and the default visibility follows your account setting (public unless changed). Verify visibility in the Hub UI right after the first push.

### 5.5 Observe the Rate-Limit Failure Mode

```bash
docker pull alpine:3.20
```

```text
Error response from daemon: toomanyrequests: You have reached your unauthenticated pull rate limit.
https://www.docker.com/increase-rate-limit
```

The fix is to authenticate, add a pull-through cache, or mirror the base images you depend on.

### 5.6 Configure a Registry Mirror (Pull-Through Cache)

```json
{
  "registry-mirrors": ["https://mirror.example.internal"]
}
```

```bash
sudo systemctl restart docker
docker info --format '{{json .RegistryConfig.Mirrors}}'
```

```text
["https://mirror.example.internal/"]
```

The `registry-mirrors` setting applies only to Docker Hub pulls. Running your own cache is covered in [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md) (the `proxy` mode of the open-source registry, and Harbor proxy-cache projects).

### 5.7 Inspect Tags Without Pulling

```bash
docker buildx imagetools inspect nginx:1.27
```

```text
Name:      docker.io/library/nginx:1.27
MediaType: application/vnd.oci.image.index.v1+json
Digest:    sha256:5f2b...c9
Manifests:
  Name:      docker.io/library/nginx:1.27@sha256:aa11...
  Platform:  linux/amd64
  ...
```

This reads only manifests, so you can see the platforms and digests an image offers before committing to a pull.

## 6. Production Usage Notes

- **Always authenticate CI pulls.** Anonymous runners share NAT addresses and exhaust the quota quickly. Store an OAT or PAT as a CI secret and run `docker login` as the first step.
- **Mirror your base images.** For anything that must build during an outage, copy `FROM` images into a registry you control and reference those. This removes both rate limits and a supply-chain dependency.
- **Use a pull-through cache** for fleets of build agents or Kubernetes nodes. One cache means one upstream pull per image rather than one per node.
- **Private repository count is plan-dependent.** The Free plan includes a small number of private repositories; paid plans raise or remove the limit. Check the pricing page before designing around it.
- **Prefer Official Images, Verified Publisher and DSOS content** for base layers, and pin to a digest in production after your scanner approves it.
- **Webhooks** on a repository can trigger deployments or mirror jobs when a tag is pushed.
- **Docker Hub remains one SaaS dependency.** Production clusters usually pull from a cloud or private registry ([§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)) and only CI touches Hub.

## 7. Security Considerations

- **Use scoped tokens.** A PAT or OAT with Read-only scope cannot push a malicious tag. Rotate tokens, name them by purpose, and revoke the ones that are unused.
- **Enable 2FA** on every account; tokens bypass 2FA by design, which is why their scope matters.
- **Public pushes leak.** Secrets baked into any layer of a public image are public forever. Scan with `docker history` and a scanner before the first public push, and rotate anything that escaped ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Typosquatting and impersonation** are real on community namespaces. Check the publisher badge, pull counts, and last update, and never trust a name alone.
- **Tags are mutable.** `latest` or `1.27` can change under you. Pin digests and verify signatures ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Mirror and cache hygiene:** a pull-through cache that serves unauthenticated clients still stores upstream content; restrict who can reach it.
- **Credential storage:** `docker login` writes to `~/.docker/config.json`, base64 only unless a credential helper is configured ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `toomanyrequests: You have reached your pull rate limit` | Anonymous or free quota exhausted; shared NAT IP | `docker login`, add a mirror or cache, upgrade the plan |
| `pull access denied for X, repository does not exist or may require 'docker login'` | Typo, private repo without login, or wrong namespace | Check spelling; log in; verify the repo exists and you have access |
| `denied: requested access to the resource is denied` on push | Not logged in, image not tagged with your namespace, or token lacks Write | Tag as `user/repo:tag`, re-login with a Read and Write token |
| Pull works locally, fails in CI | CI runs anonymously from a shared IP | Add authenticated login step with a CI secret |
| Mirror configured but still hitting Hub | Image is not from Docker Hub, or the daemon was not restarted | Mirrors cover Hub only; restart dockerd; check `docker info` |
| `unauthorized: incorrect username or password` | Used the account password with 2FA, or a revoked token | Create a new PAT; use `--password-stdin` |
| Pull succeeds but count still drops | Each tag or platform pull is counted | Pull by digest less often; cache at a mirror |
| Cannot create more private repos | Plan limit reached | Delete unused repos or upgrade |

## 9. Best Practices

- Authenticate everywhere, with token scope matching the job (Read-only for pulls).
- Use Organization Access Tokens for CI and automation, not personal tokens.
- Mirror or cache critical base images so builds survive Hub outages and limits.
- Pin to digests in production and record the digest you scanned.
- Prefer Official, Verified Publisher or DSOS images for bases.
- Set the default repository visibility to private for new organization repositories, and review visibility after the first push.
- Monitor remaining quota with the preview repository check in CI logs.
- Document the registry strategy: which registry for development, which for production.

## 10. Common Anti-Patterns / Mistakes

- Running CI anonymously and being surprised by intermittent failures.
- Using a personal password or a full-scope personal token in a shared pipeline.
- Pushing an image to a public repo "just for a quick test" with credentials inside.
- Relying on `latest` from a community repository in production.
- Pointing every Kubernetes node directly at Hub with no cache, so one rollout triggers hundreds of pulls.
- Assuming `registry-mirrors` caches images from other registries (it does not).
- Treating "has many pulls" as proof an image is safe.

## 11. Interview Questions

**🎯 Beginner:** _"What does `docker pull ubuntu` actually pull from and where does that name get resolved?"_
**Model answer:** With no registry host in the name, the CLI uses Docker Hub. The reference is normalized to `docker.io/library/ubuntu:latest`, where `library` is the namespace of Docker Official Images. The daemon contacts `registry-1.docker.io`, obtains a pull token from `auth.docker.io` (anonymous if you are not logged in), downloads the manifest for the tag, then the config and layer blobs. Because the tag defaults to `latest`, the content can change, so production should pin a version tag or digest.
_What the interviewer is probing for:_ That unqualified names mean Docker Hub, the `library/` namespace, and the default tag.

**🎯 Intermediate:** _"Your CI builds start failing at noon with `toomanyrequests`. Nothing in the pipeline changed. Diagnose and fix."_
**Model answer:** Anonymous pulls are limited per source IP over a rolling six-hour window, and hosted CI runners share a small pool of addresses, so a busy period exhausts the budget. I would confirm by calling the `ratelimitpreview/test` manifest endpoint from a runner and reading `ratelimit-remaining` and `docker-ratelimit-source`. The fix is to add a `docker login` step using an Organization Access Token stored as a CI secret, which moves counting to the account. For lasting resilience I would add a pull-through cache or mirror critical base images into our own registry.
_What the interviewer is probing for:_ Understanding of how the limit is keyed and the layered remediation (authenticate, cache, mirror).

**🎯 Senior:** _"How would you design image sourcing so that a Docker Hub outage or policy change cannot stop production deploys?"_
**Model answer:** Separate dependency intake from consumption. A scheduled job copies approved upstream images (by digest) from Hub into an internal registry such as Harbor or a cloud registry, after scanning and signing. Dockerfiles and manifests reference only the internal registry, ideally through an admission policy that rejects images from other hosts. Build agents and clusters pull from the internal registry or a proxy-cache project. Hub is touched only by the intake job, authenticated with a scoped OAT. I would also record the digest-to-source mapping for audit and alert when an upstream tag moves.
_What the interviewer is probing for:_ Supply-chain thinking, mirroring versus caching, and policy enforcement.

**🎯 Architect:** _"Evaluate Docker Hub paid plans against a self-hosted or cloud registry for an organization with 300 engineers, 40 services, and a regulated environment."_
**Model answer:** Hub is strongest for public distribution and as the upstream for Official Images, and paid tiers remove pull limits and give team management, SSO and Scout. For a regulated environment the main questions are data residency, private network access, audit logs, vulnerability gating, and availability. Cloud registries (ECR, ACR, Artifact Registry) give private networking, IAM-based auth without long-lived tokens, and lifecycle policies close to the runtime. Harbor gives portability, replication, signing and RBAC if we must run on premises. My recommendation is a primary private registry near the workloads, with Hub used only as a controlled upstream through a proxy cache, and a paid Hub plan only where we publish public images. I would decide using cost per pull volume, egress, and operational burden of self-hosting.
_What the interviewer is probing for:_ Trade-off analysis across availability, compliance, cost and operational ownership.

## 12. Common Misconceptions

- "Public repository means safe to use." It only means unauthenticated read access.
- "Rate limits count bytes." They count manifest pulls, not data volume.
- "Logging in removes all limits." Free accounts have a higher but finite limit.
- "A mirror caches every registry." `registry-mirrors` applies to Docker Hub only.
- "Deleting a public tag removes the image from the world." Copies and caches may remain.
- "`latest` is the newest build." It is just a tag that whoever pushes can point anywhere.

## 13. 🔑 Key Takeaways

- Unqualified image names resolve to `docker.io/library/...` on Docker Hub.
- Rate limits apply per IP for anonymous pulls and per account when authenticated; check headers on `ratelimitpreview/test`.
- Authenticate CI with scoped tokens (OATs for organizations).
- Mirror or cache critical base images; do not let production depend on live Hub pulls.
- Public means readable by anyone, not trustworthy; pin digests and verify.
- Treat first public push as irreversible for any secret inside the image.

## 14. Related Concepts & What's Next

Related: image anatomy ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), tagging ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), scanning and signing ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), authentication ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)). Next, [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md) shows how to run your own registry and Harbor when Hub is not the right home for your images.

**Next Section:** [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md) — `Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md`
