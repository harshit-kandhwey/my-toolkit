# Section 32 (Part 4): Restart Policies and Health Checks (HEALTHCHECK Instruction)

## 1. Definition

**Plain language:** A *restart policy* tells the Docker daemon what to do when a container's main process exits (start it again, or leave it dead). A *health check* is a small command Docker runs inside the container on a schedule to ask "is the application actually working?". The two are separate features: the restart policy reacts to the process **exiting**, the health check reports on whether a **running** process is useful.

**Precise definition:** The restart policy is a property of the container's host config, set with `docker run --restart` (or `docker update --restart`). Four values exist: `no` (default), `on-failure[:max-retries]`, `always`, and `unless-stopped`. The daemon applies the policy when the container's init process exits, with an exponentially increasing delay between attempts. The health check is defined in the image by the `HEALTHCHECK` instruction ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md) covers the other Dockerfile instructions) or at run time with `--health-*` flags. Docker runs the command inside the container every `--interval`, and tracks a status of `starting`, `healthy` or `unhealthy` from its exit code (0 = success, 1 = failure, 2 is reserved and should not be used). **Docker Engine does not restart a container merely because it is `unhealthy`**; the status is information for you, Compose, Swarm, or an external supervisor.

> 💡 **Tip:** Remember the split: `--restart` answers "the process died, now what?" and `HEALTHCHECK` answers "the process is alive, is it OK?". Nothing connects them automatically in a plain Engine.

## 2. Why This Matters

- A crashed service with `--restart no` stays down until a human notices; the right policy turns a 3 a.m. page into a 100 ms blip.
- A process that is running but deadlocked, out of connections or still warming up looks fine to `docker ps`; only a health check exposes it.
- Wrong policies cause **crash loops** that burn CPU, flood logs and hide the real error, or the opposite: a container you deliberately stopped comes back after a host reboot.
- Health status is the contract that Compose `depends_on: condition: service_healthy` (Part 5), Swarm and many load balancers consume.
- Interview and DCA staple: "Does Docker restart an unhealthy container?" is answered wrongly by a large share of candidates.

## 3. Prerequisites and Dependencies

Requires the container lifecycle states and `docker run` basics from earlier in Part 4, the daemon and containerd/runc split ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)) because the *daemon* owns restart decisions, and daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) for `live-restore`. Dockerfile instruction syntax and exec versus shell form are in [§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md) and [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md); PID 1 and signal behavior ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) explains why a process exits the way it does. The immediately preceding section, [§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md), matters because the most common reason for a restart loop is the OOM killer enforcing a `--memory` limit. Inspecting results uses `docker inspect` ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)).

## 4. Architecture / Conceptual Diagram

```text
  Restart policy (owned by dockerd)

   container process exits (exit code N)
              │
              ▼
   ┌─────────────────────────────────────────────────────────┐
   │ policy = no              ──► stay Exited                │
   │ policy = on-failure[:M]  ──► restart only if N != 0     │
   │                              and attempts < M           │
   │ policy = always          ──► restart (even exit 0)      │
   │ policy = unless-stopped  ──► like always, but not if    │
   │                              you ran docker stop        │
   └──────────────────────────┬──────────────────────────────┘
                              ▼
        wait: 100ms ► 200ms ► 400ms ► 800ms ... (doubles; capped)
        delay resets once the container stays up >= 10 s
                              ▼
                        container Restarting ──► Running

  Health check (owned by dockerd, executed inside the container)

        start ──► [ starting ] ── first probe passes ──► [ healthy ]
                      │ (failures during --start-period
                      │  do not count toward retries)
                      ▼
          probe exits 1 / times out, --retries times in a row
                      ▼
                 [ unhealthy ] ── next probe passes ──► [ healthy ]

   probe = docker exec-like run of CMD every --interval, killed after --timeout
   Engine action on unhealthy: NONE (event + status only)
   Consumers: docker ps, docker inspect, docker events, Compose, Swarm, scripts
```

- Policies are evaluated by the daemon, so a stopped daemon restarts nothing; `live-restore` keeps containers alive across daemon downtime but is a different mechanism.
- A manual `docker stop` or `docker kill` marks the container as deliberately stopped; `always` revives it on the next daemon start, `unless-stopped` does not.
- The backoff starts at 100 ms and doubles per consecutive failed start, which is why a flapping container shows `Restarting (1) 12 seconds ago`.
- Health state transitions emit `health_status` events on the daemon event stream.

## 5. Hands-On

### 5.1 The Four Policies Side by Side

```bash
docker run -d --name p-no       --restart no             alpine:3.20 sh -c 'sleep 2; exit 1'
docker run -d --name p-onfail   --restart on-failure:3   alpine:3.20 sh -c 'sleep 2; exit 1'
docker run -d --name p-always   --restart always         alpine:3.20 sh -c 'sleep 2; exit 0'
docker run -d --name p-unless   --restart unless-stopped alpine:3.20 sleep 3600
sleep 20
docker ps -a --format 'table {{.Names}}\t{{.Status}}'
docker inspect -f '{{.Name}} restarts={{.RestartCount}} policy={{.HostConfig.RestartPolicy.Name}}' p-no p-onfail p-always p-unless
```

```text
NAMES       STATUS
p-unless    Up 20 seconds
p-always    Restarting (0) 3 seconds ago
p-onfail    Exited (1) 9 seconds ago
p-no        Exited (1) 17 seconds ago
/p-no restarts=0 policy=no
/p-onfail restarts=3 policy=on-failure
/p-always restarts=6 policy=always
/p-unless restarts=0 policy=unless-stopped
```

`on-failure:3` gave up after three retries; `always` restarts even a clean exit 0 forever.

### 5.2 Observing Backoff and the OOM Case

```bash
docker run -d --name crashy --restart on-failure alpine:3.20 sh -c 'exit 2'
sleep 10
docker inspect -f 'restarts={{.RestartCount}} state={{.State.Status}} exit={{.State.ExitCode}}' crashy
docker events --since 30s --filter container=crashy --filter event=die | head
```

```text
restarts=5 state=restarting exit=2
2026-10-06T10:01:12.100 container die ... exitCode=2 name=crashy
2026-10-06T10:01:12.300 container die ... exitCode=2 name=crashy
2026-10-06T10:01:12.700 container die ... exitCode=2 name=crashy
```

Intervals double (100 ms, 200 ms, 400 ms...). For a memory-limited container ([§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) check `docker inspect -f '{{.State.OOMKilled}}' <name>`: `true` means the kernel killed it and the policy is just replaying the failure.

### 5.3 Changing a Policy on a Live Container

```bash
docker update --restart unless-stopped crashy
docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' crashy
```

```text
unless-stopped
```

`docker update` changes the policy without recreating the container. Note that `--restart` cannot be combined with `--rm`; the daemon rejects the pair.

### 5.4 HEALTHCHECK in a Dockerfile

```dockerfile
FROM nginx:1.27-alpine
RUN apk add --no-cache curl
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --start-interval=2s --retries=3 \
  CMD curl -fsS http://127.0.0.1/ || exit 1
```

```bash
docker build -t web-hc .
docker run -d --name web web-hc
docker ps --format 'table {{.Names}}\t{{.Status}}'
sleep 25
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

```text
NAMES   STATUS
web     Up 3 seconds (health: starting)
NAMES   STATUS
web     Up 28 seconds (health: healthy)
```

Option defaults: `--interval=30s`, `--timeout=30s`, `--start-period=0s`, `--start-interval=5s` (Engine 25 and later), `--retries=3`. Only the **last** `HEALTHCHECK` in a Dockerfile counts; `HEALTHCHECK NONE` disables one inherited from the base image.

### 5.5 Making a Container Unhealthy and Reading the Log

```bash
docker run -d --name web2 --health-cmd 'test -f /tmp/ok' --health-interval 5s --health-retries 2 alpine:3.20 sleep 3600
sleep 15
docker inspect -f '{{.State.Health.Status}} failing={{.State.Health.FailingStreak}}' web2
docker inspect -f '{{json (index .State.Health.Log 0)}}' web2
docker exec web2 touch /tmp/ok
sleep 8
docker inspect -f '{{.State.Health.Status}}' web2
```

```text
unhealthy failing=3
{"Start":"2026-10-06T10:05:01Z","End":"2026-10-06T10:05:01Z","ExitCode":1,"Output":""}
healthy
```

`State.Health.Log` keeps the last five probe results with their stdout/stderr (truncated to 4096 bytes), which is the first place to look. The container stayed `Up` throughout: **Docker took no corrective action.**

### 5.6 Filtering and Watching Health

```bash
docker ps --filter health=unhealthy
docker events --filter event=health_status
```

```text
CONTAINER ID   IMAGE       STATUS                     NAMES
3f2a9c1d7e44   alpine:3.20 Up 2 minutes (unhealthy)   web2
2026-10-06T10:06:00 container health_status: healthy name=web2
```

### 5.7 Closing the Loop: Restart on Unhealthy (External Supervisor)

```bash
# Illustrative loop; production setups use Swarm, Kubernetes liveness probes, or systemd
for c in $(docker ps -q --filter health=unhealthy); do docker restart "$c"; done
```

This is what sidecars such as `autoheal` automate. They need the Docker socket, which is root-equivalent (see section 7).

### 5.8 Cleanup

```bash
docker rm -f p-no p-onfail p-always p-unless crashy web web2 2>/dev/null
```

## 6. Production Usage Notes

- **Default choice for long-running services:** `unless-stopped` (or `always` when you want a deliberately stopped container to come back after a daemon restart). Use `on-failure:5` for batch-like jobs where exit 0 means done.
- **Pair policy with logging and alerting:** a restart count that climbs is a symptom; alert on `RestartCount` growth rather than relying on the policy to hide it.
- **Health check content:** probe the local dependency path the application needs (a cheap `/healthz` that checks the database pool), not just that the port is open. Keep probes fast, side-effect free and cheap, since they run forever.
- **Tune timing to the app:** set `--start-period` to the slowest realistic warm-up so slow starters are not marked unhealthy; use `--start-interval` for quick probing during that window.
- **Probe tooling must exist in the image:** a distroless or scratch image has no `curl` or shell. Ship a tiny static probe binary, use the app's own `--healthcheck` flag, or define the check in Compose/orchestrator instead.
- **Compose:** `restart:` maps to the Engine policy, `healthcheck:` mirrors the Dockerfile options, and `depends_on: condition: service_healthy` gates startup order on health. Compose (Part 5) is the usual place to wire this together.
- **Swarm:** ignores `--restart`; use `deploy.restart_policy`. Swarm *does* replace tasks that fail health checks. **Kubernetes ignores the Dockerfile `HEALTHCHECK`**; define liveness, readiness and startup probes in the pod spec.
- **Daemon restarts:** `live-restore: true` in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) keeps containers running while `dockerd` is down for upgrades; policies still apply after it returns.
- **Docker Desktop and rootless mode:** policies work, but the daemon itself must be started at login/boot for `always` and `unless-stopped` to matter.

## 7. Security Considerations

- **Docker socket sidecars:** auto-heal containers mount `/var/run/docker.sock`, giving root-equivalent control of the host. Prefer orchestrator-native healing, or a socket proxy that allows only `restart` on specific containers.
- **Probe commands run inside the container** with the container's user and filesystem. Do not embed credentials in the probe command; they appear in `docker inspect` and the image config.
- **Health output leaks:** probe stdout/stderr is stored in `State.Health.Log`; never print tokens or connection strings.
- **Crash loops as denial of service:** a restart storm consumes CPU and disk (log growth). Combine with log rotation ([§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md) covers limits; log drivers are earlier in Part 4) and resource limits.
- **Unbounded `always` hides compromise:** a container killed by a defender or crashing from exploitation silently returns. Alert on restart counts and unexpected exit codes.
- **Extra tooling for probes** (curl, wget, a shell) widens the attack surface; prefer a purpose-built static binary in minimal images.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Container shows `Restarting (1) N seconds ago` forever | Process exits immediately; policy keeps retrying | `docker logs`, fix the startup error; use `on-failure:N` while debugging |
| Stopped container came back after reboot | Policy `always` | Use `unless-stopped`, or `docker update --restart no` |
| Container did not come back after `docker stop` and host reboot | `unless-stopped` honours the manual stop | Expected; `docker start` it, or use `always` |
| Marked `unhealthy` but keeps running | Engine never kills on unhealthy | Add a supervisor, use Swarm, or restart manually |
| Stays `starting` for a long time | Probe slower than `--interval`/`--timeout`, or start-period too long | Tune options; check `State.Health.Log` |
| Immediately `unhealthy` on slow apps | No `--start-period` | Set it to the warm-up time |
| Probe fails with `exec: "curl": not found` | Tool missing in image | Install a probe tool or use a static binary |
| `docker run --rm --restart always` fails | The flags conflict | Drop `--rm` or the policy |
| Restart loop, `OOMKilled=true` | Memory limit too low ([§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) | Raise the limit or fix the leak |
| Policy ignored in a Swarm service | Swarm uses its own settings | Set `deploy.restart_policy` |
| `on-failure` never retries | Exit code was 0 | Use `always`/`unless-stopped` or exit non-zero |

## 9. Best Practices

- Use `unless-stopped` for services and `on-failure:N` for jobs; avoid bare `always` unless you want reboot resurrection of stopped containers.
- Define `HEALTHCHECK` in the image so every consumer gets it, and override per environment in Compose when needed.
- Write health endpoints that test real readiness but stay under a second.
- Always set `--start-period` for apps with warm-up, and `--timeout` below `--interval`.
- Use exec form for the probe where possible and exit with 0 or 1 only.
- Monitor `RestartCount`, `OOMKilled` and health transitions, not just container up/down.
- Test failure paths deliberately: kill the process, break the dependency, and confirm status and alerts.
- Enable `live-restore` on hosts where daemon upgrades must not interrupt workloads.

## 10. Common Anti-Patterns / Mistakes

- Believing `unhealthy` triggers a restart, and building no remediation.
- `--restart always` on a container that exits non-zero at once, producing a tight crash loop that hides the cause.
- Health checks that only test "port is open" or return success unconditionally (`CMD exit 0`).
- Probes that are expensive (full DB queries every 5 seconds) or have side effects (writing data, sending email).
- Health checks calling external dependencies, so one upstream outage marks every replica unhealthy at once.
- Putting retry logic in a shell loop inside `CMD` instead of using the policy and health check.
- Probing with a tool absent from a minimal image, so the container is permanently unhealthy.
- Mixing up Dockerfile `HEALTHCHECK` with Kubernetes probes and expecting one to configure the other.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `--restart always` and `--restart unless-stopped`?"_
**Model answer:** Both restart a container when its process exits and when the Docker daemon starts, with the same exponential backoff. The difference shows up after a manual stop. With `always`, a container you stopped with `docker stop` is started again when the daemon restarts (for example after a host reboot). With `unless-stopped`, the daemon remembers you stopped it deliberately and leaves it stopped. `on-failure[:N]` restarts only on non-zero exit codes, optionally at most N times, and `no` is the default. A restart policy takes effect only after the container has been up for about ten seconds, and it cannot be combined with `--rm`.
_What the interviewer is probing for:_ Precise knowledge of the four values and the manual-stop distinction.

**🎯 Intermediate:** _"A container is marked `unhealthy` but nothing happens. Why, and how do you act on it?"_
**Model answer:** In plain Docker Engine the health check only sets a status (`starting`, `healthy`, `unhealthy`) and emits `health_status` events; it never restarts or kills the container. The restart policy reacts to process exit, not health. To act, you can run a supervisor that watches `docker events` or `docker ps --filter health=unhealthy` and restarts the container (accepting the socket-access risk), use Swarm which replaces unhealthy tasks, or use an orchestrator such as Kubernetes with liveness probes. Compose can use health status to gate `depends_on: condition: service_healthy`, but that governs startup order, not remediation. Diagnose first with `docker inspect` on `.State.Health.Log`.
_What the interviewer is probing for:_ Knowing health is advisory in Engine and knowing the real remediation options.

**🎯 Senior:** _"Design the health check and restart settings for a Java service with a 60 second warm-up and a database dependency."_
**Model answer:** Use `HEALTHCHECK --start-period=90s --start-interval=3s --interval=15s --timeout=3s --retries=3` calling a local `/healthz` that verifies the service can serve and its connection pool is alive, but does not hard-fail on transient database blips that would cause every replica to flap together. Failures during the start period do not count toward retries, so the slow JVM is not penalized, while `--start-interval` gets it to `healthy` quickly once ready. Set the restart policy to `unless-stopped` so crashes recover, and set a memory limit with headroom so the policy is not replaying OOM kills. Alert on `RestartCount` and health transitions, ship a small probe tool in the image, and in Compose gate dependents on `service_healthy`. Separate liveness (am I stuck?) from readiness (can I take traffic?) when moving to Kubernetes.
_What the interviewer is probing for:_ Correct use of start-period/start-interval, thoughtful probe semantics, and avoiding cascading failures.

**🎯 Architect:** _"Standardize self-healing across 300 containerized services on a mixed fleet of plain Docker hosts, Swarm and Kubernetes."_
**Model answer:** Treat the image-level `HEALTHCHECK` as a portable baseline contract and enforce it with a CI lint on image config, but recognize each platform consumes health differently: Engine only reports, Swarm replaces tasks, Kubernetes ignores it and needs explicit probes (generate them from the same endpoint convention). For plain hosts, prefer `unless-stopped` plus a hardened remediator that acts through a restricted socket proxy, or migrate those to an orchestrator. Mandate `live-restore` for upgrade safety, resource limits to avoid OOM loops, centralized log shipping with rotation, and fleet metrics on restart counts, OOM kills and unhealthy duration with paging thresholds and crash-loop circuit breakers (`on-failure:N` plus alert) so failures surface instead of looping silently. Document the policy per workload class: services, jobs, one-shot migrations.
_What the interviewer is probing for:_ Platform-aware design, operational guardrails, and governance at fleet scale.

## 12. Common Misconceptions

- "Docker restarts unhealthy containers." It does not; Swarm does, Engine does not.
- "`always` and `unless-stopped` are the same." They differ after a manual stop plus daemon restart.
- "`on-failure` retries forever." Without `:N` it does, but with `:N` it stops after N attempts, and it never retries exit code 0.
- "A passing health check means the app is correct." It only means the probe command exited 0.
- "Restart policies work with `--rm`." They conflict.
- "The Dockerfile HEALTHCHECK also configures Kubernetes." Kubernetes ignores it.
- "Restarting is instant." Backoff doubles from 100 ms, so flapping containers wait progressively longer.

## 13. 🔑 Key Takeaways

- Policies: `no`, `on-failure[:max]`, `always`, `unless-stopped`; the daemon applies them with doubling backoff, after the container has stayed up long enough to count as started.
- `always` revives manually stopped containers on daemon start; `unless-stopped` does not.
- Health states are `starting`, `healthy`, `unhealthy`; probes exit 0 or 1; defaults are interval 30s, timeout 30s, start-period 0s, start-interval 5s, retries 3.
- Docker Engine never restarts a container just for being unhealthy.
- Inspect with `State.Health.Log`, `RestartCount`, `OOMKilled`; filter with `docker ps --filter health=unhealthy`.
- Healing sidecars that mount the Docker socket are a root-level risk.

## 14. Related Concepts & What's Next

Related: Dockerfile instructions ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), exec versus shell form and PID 1 ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), daemon configuration and `live-restore` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), engine architecture ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), resource limits and OOM ([§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), inspection ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)). Compose `restart:` and `healthcheck:` keys arrive in Part 5, starting with §34. Next, [§33](Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md) covers cleaning up the stopped containers, dangling images and unused volumes that restart-heavy and build-heavy hosts accumulate.

**Next Section:** [§33](Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md) — `Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md`
