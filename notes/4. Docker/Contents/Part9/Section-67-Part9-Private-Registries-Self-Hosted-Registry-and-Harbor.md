# Section 67 (Part 9): Private Registries: Self-Hosted Registry and Harbor

## 1. Definition

**Plain language:** A private registry is an image store that you run yourself, inside your own network. You decide who can push and pull, where the bytes are stored, and how long images are kept.

**Precise definition:** A self-hosted registry is any server implementing the OCI Distribution API (`/v2/...`). Two options dominate:

- **Distribution (`registry` image):** the CNCF reference implementation (formerly Docker Registry v2). It is a single stateless Go binary storing content-addressed blobs and manifests in a pluggable backend (local filesystem, S3, Azure Blob, GCS). It offers basic auth, token auth, a catalog API, and pull-through caching, but no UI, no RBAC beyond what auth gives it, no scanning and no replication.
- **Harbor:** a CNCF graduated, full registry platform that wraps Distribution with a core service, PostgreSQL, Redis, a job service, a web UI and plug-in scanners (Trivy). It adds projects, RBAC, robot accounts, replication, proxy-cache projects, tag immutability, retention policies, quotas, audit logs, OIDC/LDAP login, and signature policy enforcement (cosign and Notation).

Current images are published as `registry:3` (Distribution v3) and the older `registry:2`. Prefer v3 for new installs, and note that the in-container config path differs between the two (`/etc/distribution/config.yml` versus `/etc/docker/registry/config.yml`).

> 💡 **Tip:** If you only need a cache or a local test registry, run Distribution. If more than one team will use it, you almost certainly want Harbor.

## 2. Why This Matters

- Regulated, air-gapped or on-premises environments often cannot pull from the public internet or from SaaS registries.
- Owning the registry removes third-party rate limits ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)), outage dependency, and egress costs for large clusters.
- Harbor gives a central place to enforce policy: scan on push, block vulnerable pulls, require signatures, and keep an audit trail.
- It is also the usual answer to "how do we cache Hub for 500 nodes".
- Running a registry badly (no TLS, no garbage collection, local disk only) is a classic way to lose images or fill a disk.

## 3. Prerequisites and Dependencies

You need the registry protocol and manifests ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md), [§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), daemon trust and insecure-registry settings ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), Compose for Harbor's stack ([§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), volumes for persistence ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), and TLS basics. Authentication details continue in [§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md); cleanup in [§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md).

## 4. Architecture / Conceptual Diagram

```text
  Plain Distribution registry                       Harbor
 ┌──────────────┐  HTTPS   ┌───────────────┐   ┌──────────────────────────────────────────┐
 │ docker push/ │ ───────► │ registry:3    │   │ nginx proxy (TLS, :443)                  │
 │ pull         │          │ htpasswd auth │   │   ├─► core (API, UI, auth, RBAC, policy) │
 └──────────────┘          └──────┬────────┘   │   │      ├─► PostgreSQL (metadata)       │
                                  │            │   │      ├─► Redis (cache, queues)       │
                                  ▼            │   │      └─► jobservice (GC, replication,│
                        ┌───────────────────┐  │   │            retention, scans)         │
                        │ storage backend   │  │   ├─► registry (Distribution) ──► storage│
                        │ fs / S3 / Azure / │  │   └─► trivy adapter (vulnerability scan) │
                        │ GCS               │  └──────────────────────────────────────────┘
                        └───────────────────┘     ▲ OIDC/LDAP login   ▲ robot accounts (CI)

  Harbor object model
   Project (public/private) ──► Repository ──► Artifact (tag/digest) ──► Scan, Signature
   Project policies: retention ● tag immutability ● CVE gate ● quota ● webhooks
   Project types: regular | proxy-cache (of Docker Hub, GHCR, ECR, ...)
   Cross-registry: Replication rules (push or pull, by filter or schedule)
```

- **Distribution is content-addressed:** a delete removes only a manifest reference; blobs stay until garbage collection runs.
- **Harbor proxy-cache projects** fetch from an upstream on first pull and serve from cache afterwards, a more capable replacement for Distribution's simple `proxy` mode.
- **Auth in Harbor is token-based:** the Docker client is redirected to Harbor core for a bearer token scoped to the requested repository action.

## 5. Hands-On

### 5.1 Run a Minimal Local Registry

```bash
docker run -d --name registry -p 127.0.0.1:5000:5000 \
  -v registry-data:/var/lib/registry \
  registry:3

docker pull alpine:3.20
docker tag alpine:3.20 localhost:5000/alpine:3.20
docker push localhost:5000/alpine:3.20
curl -s http://localhost:5000/v2/_catalog
curl -s http://localhost:5000/v2/alpine/tags/list
```

```text
{"repositories":["alpine"]}
{"name":"alpine","tags":["3.20"]}
```

`localhost` and `127.0.0.0/8` are treated as insecure-allowed by default, so plain HTTP works here and only here. This instance has no authentication; it is for local testing.

### 5.2 Add TLS and Basic Authentication

Generate a bcrypt htpasswd file (Distribution accepts bcrypt only) using a throwaway container:

```bash
mkdir -p auth certs
docker run --rm --entrypoint htpasswd httpd:2 -Bbn ci "$REGISTRY_PASSWORD" > auth/htpasswd
# certs/domain.crt and certs/domain.key come from your CA, with a SAN matching registry.example.internal
```

```bash
docker run -d --name registry --restart unless-stopped -p 443:5000 \
  -v registry-data:/var/lib/registry \
  -v "$PWD/auth:/auth:ro" -v "$PWD/certs:/certs:ro" \
  -e REGISTRY_AUTH=htpasswd \
  -e REGISTRY_AUTH_HTPASSWD_REALM="Registry Realm" \
  -e REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd \
  -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/domain.crt \
  -e REGISTRY_HTTP_TLS_KEY=/certs/domain.key \
  -e REGISTRY_STORAGE_DELETE_ENABLED=true \
  registry:3

docker login registry.example.internal -u ci
docker push registry.example.internal/team/app:1.0
```

```text
Login Succeeded
```

### 5.3 Trust a Private CA on the Docker Host

```bash
sudo mkdir -p /etc/docker/certs.d/registry.example.internal
sudo cp ca.crt /etc/docker/certs.d/registry.example.internal/ca.crt
```

No daemon restart is needed. Avoid `insecure-registries` in `daemon.json` for anything but isolated labs; it disables certificate verification for that host.

### 5.4 Compose File with S3 Storage

```yaml
services:
  registry:
    image: registry:3
    restart: unless-stopped
    ports: ["5000:5000"]
    environment:
      REGISTRY_STORAGE: s3
      REGISTRY_STORAGE_S3_BUCKET: my-registry-bucket
      REGISTRY_STORAGE_S3_REGION: eu-west-1
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
      REGISTRY_HTTP_SECRET: ${REGISTRY_HTTP_SECRET}
    # credentials come from an instance role, not environment variables
```

`REGISTRY_HTTP_SECRET` must be identical across replicas so that upload sessions work behind a load balancer.

### 5.5 Pull-Through Cache for Docker Hub (Distribution)

```yaml
# config.yml
version: 0.1
storage:
  filesystem:
    rootdirectory: /var/lib/registry
http:
  addr: :5000
proxy:
  remoteurl: https://registry-1.docker.io
  username: myuser          # use a read-only token for the password
  password: ${HUB_TOKEN}
```

Point clients at it with `"registry-mirrors": ["https://cache.example.internal"]` in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). A registry configured in proxy mode is pull-only; you cannot also push to it.

### 5.6 Install Harbor

Download the offline installer for a released version from the Harbor GitHub releases page, extract it, then edit `harbor.yml`:

```yaml
hostname: harbor.example.internal
https:
  port: 443
  certificate: /etc/harbor/certs/server.crt
  private_key: /etc/harbor/certs/server.key
harbor_admin_password: "<set a strong value, rotate after first login>"
data_volume: /data
```

```bash
sudo ./install.sh --with-trivy
docker compose -f docker-compose.yml ps    # run from the generated installer directory
```

```text
harbor-core        running (healthy)
harbor-db          running (healthy)
harbor-jobservice  running (healthy)
nginx              running (healthy)
redis              running (healthy)
registry           running (healthy)
trivy-adapter      running (healthy)
```

Then log in to the UI, create a **project** (private), and push:

```bash
docker login harbor.example.internal -u robot'$ci-bot' --password-stdin <<< "$ROBOT_SECRET"
docker tag myapp:1.0 harbor.example.internal/team-a/myapp:1.0
docker push harbor.example.internal/team-a/myapp:1.0
```

Robot accounts are named `robot$<project>+<name>` (the exact form depends on the Harbor version and the configured prefix); quote the `$` in a shell.

### 5.7 Harbor Policy Features Worth Turning On

- **Scan on push** and **prevent vulnerable images from running** (blocks pulls above a chosen severity).
- **Tag immutability** rules (for example `v*` and `release-*`) so released tags cannot be overwritten.
- **Retention policy** per project: "keep the 10 most recently pushed tags matching `**`, and anything pulled within 30 days" ([§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- **Proxy-cache project** for `docker.io`: create a registry endpoint for Docker Hub, then a project of type proxy cache. Pull as `harbor.example.internal/hub-cache/library/nginx:1.27`.
- **Replication** to a DR site or cloud registry on push or on a schedule.

## 6. Production Usage Notes

- **Do not use local disk for Distribution in production.** Use an object-store backend (S3, Azure Blob, GCS) so replicas are interchangeable and capacity is not tied to a node.
- **Run behind TLS always,** terminated at the registry or at a trusted proxy. Raise proxy body-size and timeout limits; large layers fail otherwise.
- **High availability:** Distribution scales horizontally on shared storage with a load balancer. Harbor HA needs external PostgreSQL and Redis, shared object storage, and (on Kubernetes) the official Helm chart rather than the single-host installer.
- **Use robot accounts per pipeline** with the minimum permissions (pull only for deployers, push for the build that owns the project).
- **Garbage collection must be scheduled.** Deleting tags does not free space (see [§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)). Harbor offers online scheduled GC; Distribution needs `registry garbage-collect`, preferably in read-only or maintenance mode.
- **Back up the metadata, not only the blobs.** For Harbor that means PostgreSQL plus the storage backend; losing the database orphans every artifact's project and permission mapping.
- **Monitor** disk or bucket growth, Harbor's `/metrics` endpoint if enabled, and certificate expiry.
- **Upgrade deliberately.** Harbor upgrades run a migration step; read the release notes and take a database backup first.

## 7. Security Considerations

- **Never expose an unauthenticated registry beyond localhost.** Anyone can push, and anyone can read every image, including secrets baked into layers.
- **Use TLS with a verifiable chain.** Prefer an internal CA distributed to hosts over `insecure-registries`.
- **Authenticate with tokens or robot accounts, not human credentials.** Prefer OIDC for humans in Harbor.
- **Change Harbor's default admin password** immediately and keep `harbor.yml` (which contains secrets) out of version control and with tight file permissions.
- **Enable the delete API only when you need it.** On Distribution, deletion is off unless `REGISTRY_STORAGE_DELETE_ENABLED=true`, and the API does not distinguish a user who may delete from one who may push.
- **Isolate the network:** place the registry in a private subnet, allow only build agents and cluster nodes, and restrict outbound access to configured upstreams.
- **Sign and verify.** Enforce cosign or Notation signatures in Harbor project policy and in an admission controller ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Scan continuously.** A scan at push time goes stale; Harbor rescans on a schedule against fresh vulnerability data ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- **Audit logs:** Harbor records pushes, pulls, deletes and policy changes; ship them to your log system.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `http: server gave HTTP response to HTTPS client` | Registry is plain HTTP, client expects TLS | Enable TLS; for a lab only, list it in `insecure-registries` |
| `x509: certificate signed by unknown authority` | Host does not trust your CA | Put the CA in `/etc/docker/certs.d/<host[:port]>/ca.crt` |
| `x509: certificate is valid for X, not Y` | Certificate lacks a SAN for the hostname used | Reissue with correct SAN (CN is ignored) |
| `unauthorized: authentication required` | Not logged in, bad htpasswd (not bcrypt), or token expired | Re-login; regenerate htpasswd with `-B` |
| `413 Request Entity Too Large` on push | Reverse proxy body limit | Raise `client_max_body_size` (nginx) or equivalent |
| Disk keeps growing after deleting tags | Blobs remain until GC | Enable delete, run garbage collection |
| `Error: manifest unknown` after GC | GC run while a push was in progress | Run GC in read-only/maintenance mode; re-push |
| Harbor push fails `project not found` | Project must exist first | Create the project, then push to `host/project/repo` |
| Robot login fails | `$` expanded by shell, or secret expired | Single-quote the username; check expiry |
| Pulls from proxy-cache project hit Hub limit | Upstream endpoint has no credentials | Add a Hub token to the registry endpoint |

## 9. Best Practices

- Choose Harbor for shared enterprise use and Distribution for caches and small, single-team needs.
- Store blobs in an object store, metadata in managed PostgreSQL (Harbor), and back up both.
- Use TLS everywhere with an internal CA and automated renewal.
- Give every pipeline its own robot account with project-scoped permissions.
- Turn on scan-on-push, tag immutability for release tags, and retention policies from day one.
- Schedule garbage collection and alert on storage growth.
- Mirror upstream bases through proxy-cache projects, and restrict developers to your registry through policy.
- Version and review the Harbor and registry configuration as code (without secrets).
- Rehearse restore: recreate a Harbor from backup in a test environment.

## 10. Common Anti-Patterns / Mistakes

- Exposing `registry:2` with no auth on a routable address.
- Using `insecure-registries` as a permanent fix for a missing CA.
- Keeping the data on a single node's local disk with no backup.
- Never running garbage collection and discovering the disk full during an incident.
- Sharing one admin credential across all CI jobs.
- Forgetting that Distribution has no UI or RBAC, then bolting on fragile proxies.
- Running Harbor on one VM without database backups and calling it highly available.
- Mutable release tags (`1.0` overwritten) with no immutability rule.

## 11. Interview Questions

**🎯 Beginner:** _"How do you start a private registry on one machine and push an image to it?"_
**Model answer:** Run the `registry` image publishing port 5000 with a volume at `/var/lib/registry`, then tag an image with the registry host as a prefix, for example `localhost:5000/alpine:3.20`, and `docker push` it. The registry host is part of the image name, which is how Docker knows where to send it. `localhost` is allowed over HTTP, but any other host needs TLS or an `insecure-registries` entry. For real use you add TLS and authentication, since the base container has neither.
_What the interviewer is probing for:_ That the registry host is embedded in the image name and the TLS requirement.

**🎯 Intermediate:** _"You deleted old tags from your registry but the disk did not shrink. Why, and what is the safe fix?"_
**Model answer:** Deleting a tag or manifest removes only the reference. Layer blobs are content-addressed and may be shared, so they remain until garbage collection finds blobs with no remaining references and deletes them. Deletion must also be enabled (`REGISTRY_STORAGE_DELETE_ENABLED=true`). Run `registry garbage-collect` with the config file, ideally with the registry in read-only mode or stopped, because a concurrent push could reference a blob that GC is about to remove. Start with `--dry-run`. In Harbor, use scheduled GC in the admin UI, which handles this coordination, and pair it with retention policies.
_What the interviewer is probing for:_ Understanding of content-addressed storage and the GC race.

**🎯 Senior:** _"Design a highly available Harbor for three regions, including how images get to each region and how you recover from a failure."_
**Model answer:** Deploy Harbor on Kubernetes via the Helm chart in the primary region with external HA PostgreSQL, Redis, and S3-compatible object storage using versioning and cross-region replication. Run a smaller Harbor (or a pull-only proxy) in each other region and configure Harbor replication rules with event-based push of tagged release artifacts from the primary. Pipelines push only to the primary; clusters pull from their local instance, with a fallback order in the image reference policy. Recovery relies on database point-in-time backups, object storage durability, and infrastructure as code for the Harbor config, tested by regularly restoring into a scratch environment. I would also define RPO and RTO per environment and monitor replication lag.
_What the interviewer is probing for:_ Stateful-component separation, replication topology, and tested recovery.

**🎯 Architect:** _"Leadership wants to stop pulling anything from the public internet in production. What registry architecture and controls do you put in place?"_
**Model answer:** Establish a single trusted intake path: a Harbor (or cloud registry) that is the only registry reachable from production networks. Upstream content enters through proxy-cache projects or a replication job that pulls approved images by digest, scans them, signs them, and promotes them to a production project. Production egress rules block public registries, and a cluster admission policy enforces both the registry host allow-list and signature verification. CI authenticates with project-scoped robot accounts or workload identity; humans use OIDC. Tag immutability and retention protect releases and cost. The trade-offs are the operating cost of the platform, a slower path for new base images unless intake is automated, and the need for an SLA on the registry because it now sits on every deploy path.
_What the interviewer is probing for:_ Defense in depth around registry, policy enforcement, and awareness of the operational cost and availability burden.

## 12. Common Misconceptions

- "A private registry is private by default." The Distribution image has no auth until you configure it.
- "Deleting an image frees space." Only garbage collection frees blobs.
- "Harbor is just a UI for the registry." It adds RBAC, replication, scanning, quotas, proxy cache and policy.
- "`insecure-registries` is fine in production." It removes certificate verification for that host.
- "A registry pull-through cache can also accept pushes." Proxy mode is read-only for client pushes.
- "One registry container is highly available." It is a single point of failure unless backed by shared storage and a load balancer.

## 13. 🔑 Key Takeaways

- Distribution is a minimal, headless registry; Harbor is a governed platform built on top of it.
- Always add TLS and authentication; `localhost` is the only default exception.
- Use object storage for production, and back up Harbor's database as well as its blobs.
- Deleting tags does not reclaim space; plan garbage collection and retention.
- Use robot accounts, tag immutability, scanning and signatures as policy rather than convention.
- Proxy-cache projects solve Docker Hub rate limits and give a controlled intake path.

## 14. Related Concepts & What's Next

Related: Docker Hub and rate limits ([§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), volumes ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), signing ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), retention ([§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)). Next, [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md) covers managed cloud registries, which remove most of the operational burden described here.

**Next Section:** [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md) — `Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md`
