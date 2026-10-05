# Section 95 (Part 13): Common Anti-Patterns and Why They Hurt

## 1. Definition

**Plain language:** An anti-pattern is a habit that looks reasonable, works in a demo, and causes pain later. This section lists the most common Docker anti-patterns, shows the mechanism by which each hurts, and gives the replacement.

**Precise definition:** Each entry below follows one shape: **pattern** (what people do), **mechanism** (the specific Docker or Linux behaviour that makes it harmful), **symptom** (what you observe) and **fix**. The mechanism is the important part: knowing why lets you recognize variants that no list contains. Anti-patterns cluster into five groups: image construction, runtime process model, state and data, security, and operations.

> 💡 **Tip:** If a Docker practice feels like treating a container as a small VM (SSH in, patch, keep it for years), it is probably an anti-pattern. Containers are disposable processes with a packaged filesystem.

## 2. Why This Matters

- Anti-patterns are the leading cause of slow builds, bloated images, data loss, leaked secrets and unexplained restarts.
- They are cheap to avoid and expensive to unwind once hundreds of services copy them.
- Code-review and interview questions are largely "spot the anti-pattern" ([§103](../Part14/Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md), [§101](../Part14/Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md)).
- Naming the mechanism turns "because the checklist says so" into engineering judgment, which is what senior roles assess.

## 3. Prerequisites and Dependencies

This section is a synthesis of earlier material and assumes the checklist in [§94](Section-94-Part13-Dockerfile-Best-Practices-Checklist.md). Mechanisms refer to layers ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), PID 1 and signals ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), volumes ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), privileges ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md), [§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)), cleanup ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)) and logging ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)).

## 4. Architecture / Conceptual Diagram

```text
  Anti-pattern map: where each one bites

  BUILD TIME                 RUN TIME                 OPERATIONS
  ┌───────────────┐          ┌───────────────┐        ┌────────────────┐
  │ latest tags   │──────────► surprise upgrade│        │ no limits      │
  │ COPY . . first│─► cache  │ shell-form CMD│─► 10s  │ no health check│
  │ secrets in    │   misses │ root user     │  stop  │ logs unrotated │
  │   ENV / ARG   │─► leak   │ privileged    │─► host │ prune --all in │
  │ fat final img │─► size,  │ SSH in        │  owned │   prod         │
  │   (no multi-  │   CVEs   │ docker.sock   │        │ no rollback    │
  │   stage)      │          │   mounted     │        │   tag          │
  └───────────────┘          └───────┬───────┘        └────────────────┘
                                     │
                             STATE   ▼
                    ┌─────────────────────────────┐
                    │ data in writable layer      │──► lost on `rm`
                    │ bind-mounting host paths    │──► permission / portability
                    │ DB in container, no volume  │──► data loss, no backup
                    └─────────────────────────────┘
```

- **Build-time** mistakes become permanent properties of the image.
- **Run-time** mistakes become incidents.
- **State** mistakes become data loss, the most expensive class.

## 5. Hands-On

### 5.1 Image Construction Anti-Patterns

| Pattern | Mechanism | Symptom | Fix |
|---|---|---|---|
| `FROM ubuntu:latest` / `node:latest` | Tag is mutable; a rebuild silently picks a new base | "Worked yesterday" breakage, differing environments | Pin version and digest ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)) |
| `COPY . .` before dependency install | Any source change invalidates the install layer | Minutes per build | Copy lockfile first ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)) |
| Missing `.dockerignore` | Whole directory (including `.git`, `node_modules`, `.env`) becomes context and layers | Slow context upload, leaked files | Strict ignore file ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)) |
| Single-stage image with compilers | Final layers carry toolchains and source | 1 GB images, thousands of CVEs | Multi-stage ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)) |
| `RUN apt-get update` on its own line | Cached layer keeps an old package index | `404` on install after weeks | `update && install` in one `RUN` |
| `RUN rm -rf` of files created in an earlier layer | Lower layers are immutable; deletion adds a whiteout, size stays | Image not smaller | Clean in the same `RUN`, or use a multi-stage copy |
| `ADD` for local files | `ADD` also extracts tars and fetches URLs | Surprise extraction, unverified downloads | Use `COPY` |
| Secrets via `ENV` / `ARG` / `COPY .env` | Values persist in image config and layers | `docker history` reveals them | `RUN --mount=type=secret` ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)) |
| `RUN curl ... \| sh` | Unverified remote code executed at build, nondeterministic | Supply-chain risk, flaky builds | Download, verify checksum, then run |
| `docker commit` as a build system | No record of how the image was made; cannot rebuild | Unreproducible "golden image" | Dockerfile in version control |

```bash
# Prove the "delete does not shrink" mechanism
cat > Dockerfile <<'EOF'
FROM alpine:3.20
RUN dd if=/dev/zero of=/big bs=1M count=100
RUN rm /big
EOF
docker build -t whiteout .
docker history whiteout --format '{{.Size}}\t{{.CreatedBy}}' | head -3
```

```text
0B      RUN /bin/sh -c rm /big
105MB   RUN /bin/sh -c dd if=/dev/zero of=/big ...
7.8MB   ADD alpine-minirootfs ...
```

The `rm` layer is 0 B and the 105 MB layer remains, so the image is still large.

### 5.2 Runtime Process-Model Anti-Patterns

| Pattern | Mechanism | Symptom | Fix |
|---|---|---|---|
| Shell-form `CMD python app.py` | `/bin/sh` is PID 1 and does not forward SIGTERM | `docker stop` takes 10 s, then SIGKILL | Exec form ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) |
| `ENTRYPOINT ["npm","start"]` | npm becomes PID 1 and spawns node; signals are lost | Slow shutdown, dropped requests | `["node","server.js"]` |
| Several daemons in one container (supervisord, sshd + app) | One lifecycle for unrelated processes; cannot scale, limit or restart independently | Opaque failures, shared limits | One process per container, compose them |
| SSH server in the container | Extra daemon, keys, patching, bypasses audit | Larger attack surface | `docker exec`, or debug sidecars ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)) |
| Backgrounding the app (`app &` then `tail -f`) | Container lives as long as `tail`, not the app | Dead app, "healthy" container | Run the app in the foreground |
| Writing logs to files inside the container | Writable layer grows, logs unreachable by `docker logs`, lost on removal | Disk fills, no log shipping | Log to stdout/stderr ([§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)) |
| Ignoring SIGTERM in the app | No handler; container killed mid-request | Errors on every deploy | Graceful shutdown handler, `STOPSIGNAL` |
| Long `sleep` / `tail -f /dev/null` to "keep it alive" | Masks that there is no real service | Containers that do nothing | Real foreground process, or use `docker run -d` with a proper command |

```bash
docker run -d --name bad  alpine sh -c 'sleep 300'     # shell as PID 1 (busybox sh may exec; behaviour varies)
docker run -d --name good alpine sleep 300
docker exec bad ps -o pid,args
time docker stop bad ; time docker stop good
```

```text
PID   ARGS
    1 sh -c sleep 300
    6 sleep 300
real 0m10.2s    # SIGTERM not forwarded, killed after grace period
real 0m0.3s
```

### 5.3 State and Data Anti-Patterns

| Pattern | Mechanism | Symptom | Fix |
|---|---|---|---|
| Database data in the writable layer | Layer is deleted with the container | Data vanishes on `docker rm` / recreate | Named volume ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)) |
| Anonymous volumes from image `VOLUME` | Each run creates a new unnamed volume | Hundreds of orphan volumes, "my data is gone" | Name volumes explicitly; prune carefully |
| Bind-mounting source trees in production | Couples container to host paths and permissions, bypasses immutability | "Works on host A only" | Bake artifacts into the image; bind mounts for dev only ([§41](../Part5/Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md)) |
| No backup of volumes | Volumes are just directories on one host | Single-disk failure loses everything | Scheduled backup and restore tests ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)) |
| Treating containers as pets (patch in place) | Hand changes live only in one container | Drift, impossible to reproduce | Rebuild and redeploy; treat as immutable |
| Storing config baked per environment | One image per env, rebuilt for each change | Image sprawl, untested artifacts | One image, config injected at run time ([§36](../Part5/Section-36-Part5-Environment-Variables-and-env-Files.md)) |

### 5.4 Security Anti-Patterns

| Pattern | Mechanism | Symptom | Fix |
|---|---|---|---|
| Running as root | Container root is UID 0 on the host kernel; escapes and bind-mount writes are root-owned | Host files owned by root, larger blast radius | `USER` numeric non-root ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)) |
| `--privileged` | Grants all capabilities, all devices, no seccomp/AppArmor | Container compromise equals host compromise | Specific `--cap-add`, `--device` ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)) |
| Mounting `/var/run/docker.sock` | Socket is root-equivalent access to the host | Any compromise owns the node | Rootless builders, socket proxy, Kaniko/BuildKit ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)) |
| Exposing the daemon on TCP 2375 | Unauthenticated remote root | Cryptominers within hours | TLS or SSH contexts ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) |
| `-p 5432:5432` for internal services | Publishes on all host interfaces, bypassing host firewall rules | Database reachable from the internet | Internal networks; bind `127.0.0.1:5432:5432` ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)) |
| Unscanned, never-rebuilt images | CVEs accumulate in a frozen base | Audit findings, exploited libraries | Scan and rebuild on schedule ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)) |
| Pulling unknown Hub images | Unverified publisher content | Malware, backdoors | Official/verified images, signatures ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)) |
| Passwords in environment variables | Visible in `inspect`, `/proc/<pid>/environ`, crash dumps | Credential exposure | Secrets files or a secret manager ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)) |

### 5.5 Operational Anti-Patterns

| Pattern | Mechanism | Symptom | Fix |
|---|---|---|---|
| No memory or CPU limits | One container can exhaust the host; kernel OOM picks any victim | Neighbour outages | Set limits and monitor ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md), [§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)) |
| No `HEALTHCHECK` / readiness | Orchestrator assumes "running" means "ready" | Traffic to broken instances | Real health probes ([§88](../Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)) |
| Default `json-file` without rotation | Log file grows without bound | Disk full, daemon trouble | `max-size` / `max-file` or remote driver |
| `docker system prune -a --volumes` on a host in use | Removes unused images and volumes, including data volumes of stopped services | Data loss, slow redeploys | Targeted prune, label filters ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)) |
| Deploying `latest` | Cannot tell what runs; rollback impossible | Mystery regressions | Immutable tags/digests ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)) |
| `restart: always` hiding crash loops | Infinite fast restarts with no alert | Burnt CPU, unnoticed outage | Alert on restart count; back-off; fix cause |
| `depends_on` as readiness | Only orders start, not readiness | App fails first connect | Health-based conditions ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)) |
| Using Compose scale-out as a full production platform without understanding limits | Single host, no rescheduling | Host failure is total outage | Use an orchestrator when HA matters ([§99](Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)) |

### 5.6 Detecting Anti-Patterns Automatically

```bash
docker inspect app --format 'user={{.Config.User}} priv={{.HostConfig.Privileged}} mem={{.HostConfig.Memory}} health={{if .Config.Healthcheck}}yes{{else}}no{{end}} restart={{.HostConfig.RestartPolicy.Name}}'
docker ps --format '{{.Names}} {{.Ports}}' | grep '0.0.0.0'
docker ps -q | xargs docker inspect --format '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' | grep docker.sock
docker volume ls -qf dangling=true | wc -l
```

```text
user= priv=false mem=0 health=no restart=always
/db 0.0.0.0:5432->5432/tcp
/ci-runner /var/run/docker.sock
37
```

An empty `user`, `mem=0`, `health=no`, a database on `0.0.0.0` and a socket mount are four anti-patterns found in four commands.

## 6. Production Usage Notes

- **Turn each anti-pattern into a check.** Examples: admission or CI policy for non-root and no `latest`; Prometheus alert on restart count; a nightly script listing containers without limits or health checks.
- **Audit existing fleets** with the commands in 5.6 before writing standards; fix the highest-blast-radius items first (docker.sock, privileged, exposed databases, no volumes).
- **Migrate gradually:** introduce the replacement in templates, then bots open pull requests for existing services.
- **Not every pattern is wrong everywhere:** a socket mount in a throwaway local dev tool or `--privileged` for a specific low-level test can be justified. The anti-pattern is doing it unknowingly or in production without compensating controls.
- **Document accepted exceptions** with an owner and expiry.

## 7. Security Considerations

- The highest-risk anti-patterns are the ones that convert container compromise into host compromise: `--privileged`, docker socket, host namespaces (`--pid=host`, `--net=host`), sensitive host bind mounts (`/`, `/etc`, `/var/lib/docker`) and added capabilities such as `SYS_ADMIN`.
- Information-leak anti-patterns (secrets in layers or env, `.git` in context) are permanent once the image is pushed: rotate the secret, do not just rebuild.
- Exposed ports bypassing host firewall rules is a Docker-specific trap: published ports are DNAT'ed before typical `INPUT` rules apply ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)); bind to loopback or use `DOCKER-USER` rules.
- "Pets" containers that are patched by hand cannot be verified against a source of truth, which breaks provenance and incident response.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely anti-pattern behind it | Check |
|---|---|---|
| Builds slow after tiny change | `COPY . .` too early; huge context | `docker build` output for `CACHED`; context size line |
| Image will not shrink | Delete in later layer; fat base | `docker history`, `dive` ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)) |
| Every deploy produces 502s | Shell-form CMD / no SIGTERM handling / no readiness | `docker stop` timing; probes |
| Data gone after redeploy | State in writable layer or anonymous volume | `docker inspect` mounts; `docker volume ls` |
| Host disk full | Unrotated logs; unused images; large layers | `docker system df`; log sizes |
| Strange outbound traffic from a node | Exposed 2375 or compromised privileged container | `ss -ltnp`, `docker ps`, daemon config |
| Permission errors on bind mounts | Root-owned files from root container | `ls -ln`; run with matching UID |
| Containers affecting one another | No limits | `docker stats`, `memory.events` |

## 9. Best Practices

- Learn the mechanism behind each rule so you can judge edge cases.
- Prefer secure, immutable, disposable containers: build once, configure at run time, replace rather than patch.
- Use policy-as-code (hadolint, OPA/Conftest, admission control) to catch patterns before merge.
- Keep a short "never in production" list: `--privileged`, docker.sock, 2375, `latest`, root, secrets in env.
- Review third-party Compose files and `docker run` snippets from blogs critically; many demonstrate anti-patterns for brevity.
- Pair every stateful container with a volume, a backup and a restore test.
- Fix root causes of restarts rather than relying on restart policies.
- Run periodic fleet audits with inspect-based scripts and track the counts over time.

## 10. Common Anti-Patterns / Mistakes

Meta-level mistakes about handling anti-patterns themselves:

- Memorizing a list without understanding mechanisms, then misapplying it (for example banning all bind mounts including legitimate config mounts).
- Declaring a pattern "never allowed" without a paved alternative, which pushes teams to hide it.
- Fixing symptoms (bigger log disk, higher memory limit, longer stop timeout) instead of the cause.
- Cleaning up with blanket `prune` commands to fix disk pressure and deleting needed data.
- Auditing once and never again, so anti-patterns return with the next service.
- Over-engineering the other direction: dozens of micro-optimizations that slow delivery without measurable gain.

## 11. Interview Questions

**🎯 Beginner:** _"Why shouldn't you store a database's data inside the container filesystem?"_
**Model answer:** The container's writable layer lives and dies with the container: `docker rm` or recreating it for an upgrade deletes the data. It is also slower than a volume because writes go through the union filesystem with copy-on-write. Use a named volume (or a managed database) mounted at the data directory, back it up regularly and test restores. An image's `VOLUME` instruction creates an anonymous volume per container if you do not name one, which makes data hard to find later.
_What the interviewer is probing for:_ Understanding of layer lifecycle versus volume lifecycle.

**🎯 Intermediate:** _"Why is mounting `/var/run/docker.sock` into a container considered dangerous, and what would you use instead for a CI job that builds images?"_
**Model answer:** The socket is the daemon's API, which runs as root; any process that can talk to it can start a privileged container with the host root bind-mounted, so the container effectively has root on the host. It also lets jobs see and affect all other containers. For CI builds, use daemonless or rootless builders (BuildKit rootless, Kaniko, Buildah), a remote BuildKit builder, or an ephemeral dind sandbox per job on isolated runners, and if the socket is unavoidable put a filtering socket proxy in front and limit the runner's network and credentials.
_What the interviewer is probing for:_ Recognizing socket access as host-root equivalent and knowing practical alternatives.

**🎯 Senior:** _"A team says their image is small because they delete build tools in a later `RUN`. Is the claim true? How do you show it, and what do you recommend?"_
**Model answer:** Not true: layers are immutable and union-mounted, so deleting a file in a later layer adds a whiteout entry but the bytes stay in the earlier layer; the image size, pull time and anything extractable from that layer remain. I show it with `docker history` (the install layer is large, the `rm` layer is 0 B) or `dive`, and by saving the image and extracting the layer tar. The fix is to install and remove in the same `RUN`, or better, use multi-stage builds so only the needed artifacts are copied into a clean final stage. That also keeps compilers and credentials out of the shipped image.
_What the interviewer is probing for:_ Deep understanding of layer semantics and the multi-stage rationale.

**🎯 Architect:** _"Leadership asks you to reduce container-related incidents by half in six months. Which anti-patterns do you target first, and how do you measure progress?"_
**Model answer:** Start from incident data, then rank patterns by frequency times blast radius. Typically: state without volumes/backups (data loss), no limits/health checks/log rotation (outages), shell-form commands and missing graceful shutdown (deploy errors), `latest` and no rollback (slow recovery), then privileged/socket/exposed-port patterns (security). Create paved-road templates and policy gates in CI and admission, run a fleet audit script to produce a baseline scoreboard, assign owners, and have bots open fix pull requests. Track leading indicators (percent of services with limits, probes, non-root, pinned digests; restart-loop and OOM counts) and lagging ones (incident count, MTTR, change failure rate), and review exceptions monthly.
_What the interviewer is probing for:_ Data-driven prioritization, automation of enforcement, and metrics that connect practice to outcomes.

## 12. Common Misconceptions

- "Putting everything in one container is simpler." It is simpler to start and harder to operate, scale, limit and debug.
- "Restart policies make crashing apps acceptable." They hide the failure.
- "`-p` with a firewall on the host is safe." Docker's NAT rules can bypass common firewall configurations.
- "Bind mounts are always wrong." They are right for dev workflows and read-only config; wrong as a production deployment mechanism for code.
- "`docker system prune` is harmless." With `-a --volumes` it can delete data and warm caches.
- "Alpine fixes everything." It reduces size but introduces musl compatibility issues.

## 13. 🔑 Key Takeaways

- Learn the mechanism: layers are immutable, PID 1 gets the signals, the writable layer is ephemeral, the socket is root.
- Most severe anti-patterns: state without volumes, privileged/socket/exposed daemon, secrets in layers or env, root users.
- Most common operational ones: no limits, no health checks, unrotated logs, `latest` tags, blanket prune.
- Build-time mistakes persist in the image; fix them in templates, not per service.
- Detect with `docker inspect`, `docker history`, linting and policy gates; fix causes, not symptoms.

## 14. Related Concepts & What's Next

Related: the positive checklist ([§94](Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)), troubleshooting ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)), size and caching ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md), [§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)), security model ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)). Next, [§96](Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md) compares Docker with Podman and standalone containerd, including how their different designs avoid some of these problems (daemonless, rootless by default).

**Next Section:** [§96](Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md) — `Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md`
