# Section 91 (Part 12): Zero-Downtime Deployment Patterns with Docker

## 1. Definition

**Plain language:** A zero-downtime deployment replaces the running version of an application with a new one while users keep getting successful responses. No request lands on a container that is not ready, and no in-flight request is cut off.

**Precise definition:** Zero downtime is achieved by combining four mechanisms: (1) **overlap**, meaning the new version runs alongside the old one before traffic moves; (2) **readiness gating**, where traffic is sent to the new version only after a health check proves it can serve; (3) **traffic switching** through a layer that can change its upstream atomically (a reverse proxy, a load balancer, DNS with short TTL, or a Swarm/orchestrator service VIP); and (4) **graceful drain**, where the old version stops receiving new requests, finishes what it has in flight, then exits on SIGTERM within its stop grace period. The common strategies built from those mechanisms are **rolling**, **blue/green**, **canary** and **recreate** (the last is not zero-downtime). A plain `docker compose up -d` on a changed image is a recreate: it stops the old container, then starts the new one.

> 💡 **Tip:** Two things must be true for any pattern to work: the application must shut down gracefully, and the database schema must be compatible with both versions during the overlap.

## 2. Why This Matters

- Every `docker stop` followed by `docker run` creates a window of failed requests; for a busy service that is thousands of errors per release.
- Frequent releases (CI/CD, [§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)) are only safe if each release is invisible to users.
- It forces good habits: health checks, signal handling, backward-compatible migrations, and instant rollback.
- A classic interview scenario: "How do you deploy without downtime on a single Docker host?" tests whether you understand the proxy layer, not just Kubernetes.

## 3. Prerequisites and Dependencies

Requires container lifecycle and stop signals ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), `CMD`/`ENTRYPOINT` signal handling ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), Compose dependency ordering and scaling ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md), [§39](../Part5/Section-39-Part5-Scaling-Services-with-Compose.md)), DNS and service discovery ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)), image tagging and promotion ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)), and Swarm update config ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)).

## 4. Architecture / Conceptual Diagram

```text
 A) RECREATE (downtime)           B) ROLLING / START-FIRST
    v1 ████████╳                     v1 ████████████╳╳╳
    v2          ╳██████████          v2      ██████████████████   (one at a time)
         gap ──►│◄── errors

 C) BLUE / GREEN (single host, proxy switch)

   clients ──► proxy (nginx / Traefik / Caddy / HAProxy)
                    │  upstream = blue
                    ├──────────────► blue  (v1)  ◄── serving
                    └ ─ ─ ─ ─ ─ ─ ► green (v2)  ◄── started, health-checked, smoke-tested
        step: validate green ─► reload proxy to green ─► drain blue ─► stop blue
        rollback: reload proxy back to blue (still running for N minutes)

 D) CANARY (weighted)

   clients ──► proxy ──── 95% ──► stable (v1 × many)
                    └──── 5%  ──► canary (v2 × 1) ──► watch error rate / latency ──► promote or abort

 Lifecycle of the OLD container during any switch:
   proxy stops routing ─► SIGTERM ─► app finishes in-flight requests ─► exit(0)
                                     (stop_grace_period; SIGKILL if exceeded)
```

- **Rolling** replaces instances gradually; needs N ≥ 2 and a layer that sends traffic only to ready instances.
- **Blue/green** keeps two full environments and flips traffic once; the previous one stays warm for instant rollback. Cost: double capacity during the switch.
- **Canary** shifts a small, measured share of traffic first; needs weighted routing and metrics.
- **Expand/contract migrations** make the database safe for overlap: add (expand) in release N, deploy code that uses it, remove (contract) in release N+2.

## 5. Hands-On

The examples below run on a single Docker host with Compose v2. Use a scratch project directory; nothing here deletes existing data.

### 5.1 The Baseline Problem

`docker compose up -d` after an image change stops v1 and creates v2, so requests fail until v2 is ready. Compose does not run two versions side by side unless you scale.

### 5.2 Make the App Deployable: Health Check and Graceful Shutdown

```yaml
# compose.yaml
services:
  api:
    image: registry.example.com/api:1.4.0
    init: true
    stop_grace_period: 30s
    stop_signal: SIGTERM
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/ready"]
      interval: 5s
      timeout: 2s
      retries: 3
      start_period: 15s
    deploy:
      resources:
        limits: { memory: 256M }
```

The `/ready` endpoint must return success only when the app can really serve (DB connection pool warm, caches loaded). A separate `/live` endpoint avoids restarting a container that is merely waiting for a dependency.

### 5.3 Rolling Update on a Single Host with Compose Scale and a Proxy

```yaml
# compose.yaml (proxy in front, api scaled)
services:
  proxy:
    image: traefik:v3.1
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
    ports: ["80:80"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
  api:
    image: registry.example.com/api:${TAG:-1.4.0}
    labels:
      - traefik.enable=true
      - traefik.http.routers.api.rule=PathPrefix(`/`)
      - traefik.http.services.api.loadbalancer.server.port=8000
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/ready"]
      interval: 5s
      retries: 3
      start_period: 15s
    stop_grace_period: 30s
```

```bash
docker compose up -d --scale api=2          # two v1 instances behind Traefik
TAG=1.5.0 docker compose up -d --no-recreate --scale api=4   # add two instances; existing ones untouched
```

The new `TAG` only applies to *newly created* containers when `--no-recreate` is used, so you can add v2 instances next to v1. When the new instances report healthy (`docker compose ps`), stop the old ones individually:

```bash
docker compose ps --format '{{.Name}} {{.Image}} {{.Status}}'
docker stop --time 30 <old-container-name>      # SIGTERM, then SIGKILL after 30s
docker rm <old-container-name>
```

Traefik's Docker provider removes a container from the backend pool as soon as it is unhealthy or stopping, and only includes containers whose Docker health status is `healthy` when a healthcheck is defined. Because the Docker socket is mounted, treat this proxy as highly privileged ([§7](#7-security-considerations)).

Note on tooling: the community script `docker-rollout` automates exactly this scale-up, wait-for-healthy, remove-old sequence for Compose services.

### 5.4 Blue/Green with an nginx Upstream Switch

```nginx
# /etc/nginx/conf.d/upstream.conf (included by the proxy container)
upstream app {
    server api_green:8000;      # was api_blue:8000
}
```

```yaml
services:
  proxy:
    image: nginx:1.27
    ports: ["80:80"]
    volumes: ["./nginx:/etc/nginx/conf.d:ro"]
  api_blue:
    image: registry.example.com/api:1.4.0
  api_green:
    image: registry.example.com/api:1.5.0
    profiles: ["green"]
```

```bash
docker compose --profile green up -d api_green                 # start green alongside blue
docker compose exec proxy wget -qO- http://api_green:8000/ready # smoke test through the network
sed -i 's/api_blue/api_green/' nginx/upstream.conf              # flip (in your scratch project)
docker compose exec proxy nginx -t && docker compose exec proxy nginx -s reload
```

`nginx -s reload` starts new workers with the new config and lets old workers finish active requests, which is a built-in graceful drain. Roll back by flipping the file back and reloading while blue is still up. After a soak period, stop blue.

### 5.5 Canary with Weighted Upstreams

```nginx
upstream app {
    server api_stable:8000 weight=19;
    server api_canary:8000 weight=1;      # about 5 percent of requests
}
```

Increase the weight stepwise (1, 5, 25, 100) while watching error rate and latency ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)). Abort by setting the canary weight to 0 or removing it.

### 5.6 Swarm Rolling Update (Orchestrated)

```bash
docker service update \
  --image registry.example.com/api:1.5.0 \
  --update-order start-first --update-parallelism 1 --update-delay 10s \
  --update-monitor 30s --update-failure-action rollback \
  --stop-grace-period 30s api
docker service rollback api
```

Swarm starts the replacement, waits for the health check, then stops the old task, and reverts automatically if the monitored window fails. Details in [§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md).

### 5.7 Verify: Probe While You Deploy

```bash
# terminal 1: continuous probe, prints any non-200
while true; do curl -s -o /dev/null -w '%{http_code} %{time_total}\n' http://localhost/ready; sleep 0.2; done | grep -v '^200'
# terminal 2: run the deployment
```

An empty output through the whole deploy is your evidence. Run the same probe in staging as a release gate.

## 6. Production Usage Notes

- **Choose by constraints:** single host plus Compose = proxy-based rolling or blue/green; Swarm = `start-first` rolling; Kubernetes = Deployments with `maxSurge`/`maxUnavailable` readiness gates; managed PaaS usually gives you this for free.
- **Sizing:** rolling with surge and blue/green both need spare CPU and memory for the overlap; set limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) and reserve headroom, or the new containers get OOM-killed mid-deploy.
- **Connection draining:** keep `stop_grace_period` larger than your longest request and the proxy's keep-alive timeout. Long-lived connections (WebSockets, gRPC streams) need the app to send a close frame on SIGTERM.
- **Sticky sessions and in-memory state** break overlap; externalise sessions to Redis or use signed cookies.
- **Immutable, digest-pinned images** make rollback a re-point, not a rebuild ([§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md), [§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)). Do not garbage-collect the previous release for at least a few versions.
- **Pre-pull** images (`docker compose pull`) so download time is not part of the deploy.
- **Queue consumers:** version message schemas; two versions share one queue during overlap.
- **Automate the rollback trigger** on error-rate and latency thresholds.

## 7. Security Considerations

- **Docker socket in the proxy:** Traefik's Docker provider (and `nginx-proxy`) needs the socket, which is root-equivalent on the host. Mount it `:ro` (limits writes to the socket file but not API calls), or use a socket proxy that allows only `GET /containers` and `/events`, or use file-based config instead ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **Do not expose the green or canary environment publicly** before it is validated; route the smoke test over the internal network or a header-restricted route.
- **Deploy credentials:** the CI job that runs `docker compose up` or `docker service update` can run anything on the host; use a restricted SSH key or a deploy user, short-lived registry tokens ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)) and signed, scanned images ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Old versions linger:** a kept-warm blue environment is an unpatched attack surface; set a time limit before it is removed and keep it off public routes.
- **Secrets rotation** should itself follow the overlap rule: accept old and new credentials during the transition ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Config drift:** a hand-edited proxy config is an unreviewed change; keep it in Git and apply it through the pipeline.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| 502/503 for a few seconds on every deploy | Traffic sent before the app is ready, or old instance killed before proxy stops routing | Add readiness health check; proxy only routes to healthy; drain before stop |
| In-flight requests fail with connection reset | App ignores SIGTERM or `stop_grace_period` too short | Exec-form CMD/`init: true`, handle SIGTERM, raise grace period ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) |
| New container marked `unhealthy` forever | Probe runs before the app is up, or probe tool missing in image | Set `start_period`; use a binary present in the image |
| Proxy still routes to the old container IP | DNS cached by nginx at startup | Use a resolver with `set $upstream` variables, or reload nginx after the flip |
| `docker compose up --scale` recreates the old containers | Image/config changed so Compose sees drift | Use `--no-recreate`, or `docker-rollout`-style tooling |
| Deploy works, but errors spike afterwards | Incompatible schema or message format between versions | Expand/contract migrations, feature flags |
| OOM kill during deploy | Overlap doubles memory demand | Raise host capacity, lower parallelism ([§89](Section-89-Part12-Resource-Management-at-Scale.md)) |
| Rollback fails: image not found | Retention policy deleted old tag | Keep N prior releases, pin by digest |
| Websocket clients drop at every deploy | No graceful close; clients do not reconnect | Server close frames, client backoff reconnect |

## 9. Best Practices

- Define separate liveness and readiness endpoints and use readiness for traffic gating.
- Handle SIGTERM explicitly: stop accepting, finish in flight, close pools, exit 0.
- Set `stop_grace_period` above the longest normal request.
- Always run two or more instances of anything that must not drop traffic.
- Keep the previous version running through a soak window, and make rollback a single, rehearsed command.
- Make migrations backward compatible (expand/contract) and decouple deploy from release with feature flags.
- Deploy by immutable tag or digest; never `latest`.
- Gate promotion on automated metrics, and probe continuously during deploys.
- Keep the deploy procedure in the pipeline, not in someone's shell history.

## 10. Common Anti-Patterns / Mistakes

- Treating `docker compose up -d` as zero-downtime.
- Single replica plus "rolling update" (nothing to overlap).
- Health check that only tests that the process exists, not that dependencies work.
- Switching traffic first and checking health afterwards.
- Destructive migrations (drop/rename column) in the same release as the code change.
- Deleting the previous image or environment immediately after the flip.
- Storing session state in container memory.
- Mounting the Docker socket read-write into an internet-facing proxy.
- Skipping the post-deploy probe because "CI was green".

## 11. Interview Questions

**🎯 Beginner:** _"Why does `docker compose up -d` cause downtime when you change an image, and what is the simplest way to avoid it?"_
**Model answer:** For a changed service Compose stops and removes the old container, then creates and starts the new one, so there is a gap in which nothing serves requests, plus extra time until the app is ready. The simplest fix is to run at least two instances behind a reverse proxy and replace them one at a time: start new instances first, wait for their health check to pass, then stop old ones with a SIGTERM and a grace period. A health check on the container and graceful shutdown in the app are what make the switch invisible.
_What the interviewer is probing for:_ Understanding of overlap, readiness and the recreate behaviour of Compose.

**🎯 Intermediate:** _"Compare rolling, blue/green and canary deployments, including the cost and rollback story of each."_
**Model answer:** Rolling replaces instances gradually in one pool; it needs little extra capacity, but old and new run together for the whole rollout and rollback means rolling forward or back again, which takes time. Blue/green runs a complete second environment and flips traffic once; rollback is an instant flip back while blue is retained, but it needs double capacity during the cutover and a shared database that supports both versions. Canary sends a small percentage to the new version and promotes on evidence, which limits blast radius at the price of weighted routing, good metrics and a longer release. In practice I combine them: canary first, then rolling to full, with the previous version kept for fast rollback.
_What the interviewer is probing for:_ Trade-offs, not definitions, and awareness of database compatibility.

**🎯 Senior:** _"Your zero-downtime deploy still drops about 1% of requests each release. How do you find and fix it?"_
**Model answer:** Reproduce with a continuous probe or load test during a staging deploy and log status codes and timestamps. Then check the usual suspects in order. First, the order of events: does the proxy stop routing before the old container receives SIGTERM, or after? Second, signal handling: is the app PID 1 (exec form, `init: true`) and does it finish in-flight requests, and is `stop_grace_period` long enough? Third, readiness: does the health check represent real readiness, with `start_period` set? Fourth, keep-alive and connection reuse: the proxy may hold connections to a closed backend, so lower upstream keep-alive timeouts or enable retries on idempotent requests. Fifth, DNS caching in the proxy. Fix the specific cause, then keep the probe as a regression test in the pipeline.
_What the interviewer is probing for:_ Systematic diagnosis of the request path and lifecycle ordering.

**🎯 Architect:** _"Design the release process for a stateful, database-backed service with 200 deploys a week and a 99.95% availability target."_
**Model answer:** Separate three concerns: build once and promote an immutable, signed image by digest through environments (GitOps, [§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)); deploy with canary then rolling, gated on SLO-based automated analysis with automatic rollback; and release features through flags so deploy is not release. Enforce expand/contract migrations with a CI check that every migration is backward compatible with the previous app version, and run them as a separate pre-deploy step, not at app start. Require health/readiness, SIGTERM handling and drain behaviour as a platform contract tested by a deployment probe in CI. Keep the last several releases pullable and rehearse rollback, including a data-level plan ([§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). At 200 deploys a week, 99.95% allows about 22 minutes of downtime a month, so automated rollback and small batch sizes matter more than any single technique.
_What the interviewer is probing for:_ System thinking across build, deploy, data and release, tied to a measurable availability budget.

## 12. Common Misconceptions

- "Rolling update means zero downtime." Only with readiness gating, enough replicas and graceful shutdown.
- "Blue/green removes the need for backward-compatible migrations." The database is usually shared, so it does not.
- "`depends_on` makes the new container wait for readiness of the proxy." It only orders startup within a Compose project.
- "Health checks automatically remove unhealthy containers from the proxy." That depends on the proxy integrating with Docker health status; a plain Docker health check only labels the container.
- "Kubernetes is required for zero downtime." A reverse proxy and discipline are enough for many systems.

## 13. 🔑 Key Takeaways

- Zero downtime = overlap + readiness gating + atomic traffic switch + graceful drain.
- `docker compose up -d` recreates; it is not a rolling update.
- Make rollback a pre-tested single step: keep the previous version running and pullable.
- Backward-compatible (expand/contract) migrations are mandatory for any overlap strategy.
- Prove it with a continuous probe during the deploy.
- Protect the privileged pieces: proxy with Docker socket access, deploy credentials.

## 14. Related Concepts & What's Next

Related: lifecycle and signals ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), health checks and self-healing ([§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), Swarm update config ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)), CI/CD and GitOps ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)), Compose scaling ([§39](../Part5/Section-39-Part5-Scaling-Services-with-Compose.md)). Next, [§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md) covers what to do when a release (or the host) goes wrong anyway: rollback, backups and disaster recovery.

**Next Section:** [§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md) — `Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md`
