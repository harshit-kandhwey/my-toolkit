# Section 93 (Part 12): Troubleshooting Production Container Issues

## 1. Definition

**Plain language:** Production troubleshooting is a repeatable way to answer "why is this container down, slow or misbehaving?" without guessing. You collect evidence in a fixed order (state, exit reason, logs, resources, network, host) and only then change something.

**Precise definition:** A container is a normal Linux process tree isolated by namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) and limited by cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)). Every failure therefore leaves evidence in one of five places: the **container state** (`docker inspect`: `State.ExitCode`, `State.OOMKilled`, `State.Error`, `RestartCount`), the **process output** (`docker logs`), the **daemon event stream** (`docker events`), the **cgroup counters** (`docker stats`, `memory.events`), and the **host** (kernel log, `journalctl -u docker`, disk, conntrack). The skill is mapping a symptom to the right place quickly.

> 💡 **Tip:** Start with `docker inspect`, not `docker logs`. The exit code and `OOMKilled` flag classify the failure in seconds; logs only explain it.

## 2. Why This Matters

- Most production incidents are one of a short list (OOM kill, crash loop, failed health check, full disk, DNS or port problems), and a fixed triage order resolves them faster than intuition.
- Destructive "fixes" such as `docker rm` or a restart erase the evidence (writable layer, in-memory state, `RestartCount`); you need to capture first.
- Minimal images (distroless, scratch; [§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)) have no shell, so you need techniques that do not depend on `docker exec ... sh`.
- Containers hide the host: the root cause is often the node (disk, inode, conntrack, kernel OOM), not the app.
- It is the core of the DCA troubleshooting domain and of every on-call interview.

## 3. Prerequisites and Dependencies

Requires the lifecycle and `exec` commands ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md), [§28](../Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)), logging ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md), [§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)), limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md), [§89](Section-89-Part12-Resource-Management-at-Scale.md)), health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), network tools ([§47](../Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), metrics ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)) and rollback ([§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). Host access (SSH or a node shell) is needed for daemon and kernel evidence.

## 4. Architecture / Conceptual Diagram

```text
  SYMPTOM
     │
     ▼
 1. Is it running?  docker ps -a ; docker inspect → State
     │
     ├─ exited ─► ExitCode / OOMKilled / Error ─────────────┐
     │             0 clean   1 app error   125 daemon error │
     │             126 not executable   127 not found       │
     │             137 SIGKILL (OOM or stop timeout)        │
     │             139 SIGSEGV   143 SIGTERM                │
     │                                                      ▼
     ├─ restarting ─► RestartCount rising ─► logs --since / events ─► root cause
     │
     ├─ running but unhealthy ─► Health.Log (probe output) ─► app vs probe bug
     │
     └─ running but slow/wrong
           ├─ CPU/mem/pids   ─► docker stats ; cgroup counters (throttling)
           ├─ network/DNS    ─► netshoot sidecar sharing the netns
           ├─ disk/IO        ─► docker system df ; df -h ; df -i on the host
           └─ host           ─► dmesg ; journalctl -u docker ; conntrack

  Evidence sources:   inspect   logs   events   stats   host (dmesg, journald)
```

- **Order matters:** state, then exit reason, then logs, then resources, then network, then host.
- **Capture before change:** `docker inspect`, `docker logs`, `docker top` and `docker diff` outputs go to a ticket before any restart.
- **Debug without a shell** by borrowing namespaces from a second container instead of modifying the broken one.

## 5. Hands-On

### 5.1 Triage Snapshot

```bash
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
docker inspect api --format \
 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} err={{.State.Error}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}'
```

```text
NAMES   STATUS                         IMAGE
api     Restarting (137) 12 seconds ago  shop/api:2.4.1
db      Up 3 days (healthy)            postgres:16

status=restarting exit=137 oom=true restarts=14 err= started=2026-10-06T08:11:02Z finished=2026-10-06T08:11:41Z
```

`exit=137` with `oom=true` is a memory-limit kill, not an application bug.

### 5.2 Reading Exit Codes

| Code | Meaning | First check |
|---|---|---|
| 0 | Process exited cleanly | Was it supposed to be long-running? CMD may be a one-shot command |
| 1 | Generic application error | `docker logs` |
| 125 | `docker run` itself failed | Bad flag, name conflict, daemon error text |
| 126 | Command found but not executable | File mode, wrong architecture, CRLF in a script |
| 127 | Command not found | Wrong path, missing binary in a minimal image |
| 137 | SIGKILL (128+9) | `OOMKilled`? else stop timeout or `docker kill` |
| 139 | SIGSEGV (128+11) | Native crash; core dump, library mismatch (musl vs glibc) |
| 143 | SIGTERM (128+15) | Normal `docker stop` where the app exited on the signal |

### 5.3 Logs With Boundaries

```bash
docker logs --since 15m --timestamps api | tail -n 100
docker logs --until "2026-10-06T08:11:41Z" --tail 50 api      # lines just before the crash
docker events --since 30m --filter container=api --filter type=container
```

```text
2026-10-06T08:11:02.1Z container start  api
2026-10-06T08:11:39.8Z container oom    api
2026-10-06T08:11:41.0Z container die    api (exitCode=137)
```

`docker events` shows the `oom` event that application logs never contain, because the kernel killed the process mid-write.

### 5.4 Resources and Throttling

```bash
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.PIDs}}'
docker exec api cat /sys/fs/cgroup/cpu.stat        # cgroup v2
docker exec api cat /sys/fs/cgroup/memory.events
```

```text
usage_usec 98211000
nr_periods 41210
nr_throttled 18902
throttled_usec 612000000

low 0
high 0
max 214
oom 3
oom_kill 3
```

High `nr_throttled / nr_periods` means the `--cpus` limit, not the app, is the bottleneck (latency without high host CPU). `oom_kill > 0` confirms memory pressure inside the container's cgroup.

### 5.5 Debugging a Shell-less Container With a Sidecar

```bash
# Share network namespace: tcpdump, curl, dig as if inside the container
docker run --rm -it --network container:api nicolaka/netshoot \
  sh -c 'ss -tnp; dig +short db; curl -sv http://localhost:8080/health'

# Share PID namespace too: see the app process and its files via /proc
docker run --rm -it --pid container:api --network container:api \
  --cap-add SYS_PTRACE nicolaka/netshoot sh -c 'ps aux; ls /proc/1/root/etc'
```

```text
State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
ESTAB  0      0      172.18.0.4:51322   172.18.0.2:5432
;; connection timed out; no servers could be reached     # DNS problem found
```

Alternatives: `docker debug <container>` (Docker Desktop and subscription feature, attaches a toolbox without changing the image) and, on the host, `nsenter -t $(docker inspect -f '{{.State.Pid}}' api) -n ss -tnp`.

### 5.6 Preserving Evidence Before Acting

```bash
docker diff api                                  # files changed in the writable layer
docker top api -eo pid,ppid,stat,etime,args      # processes, zombies (Z)
docker export api | gzip > api-fs-$(date +%F).tgz   # filesystem snapshot (not volumes)
docker commit api debug/api:incident-4711        # keep the broken state as an image
docker inspect api > api-inspect.json
```

`docker commit` keeps the failed filesystem so you can start it later with `--entrypoint sh` and inspect it offline.

### 5.7 Host-Level Checks

```bash
journalctl -u docker.service --since "1 hour ago" | tail -n 50
journalctl -k --since "1 hour ago" | grep -iE 'oom|killed process|segfault'
docker system df
df -h /var/lib/docker ; df -i /var/lib/docker
docker info --format '{{.Driver}} {{.LoggingDriver}} {{.CgroupVersion}} {{.LiveRestoreEnabled}}'
```

```text
Out of memory: Killed process 2931 (java) total-vm:6.1GB, anon-rss:1.9GB ... oom_memcg=/docker/3f1a...
Images          42   12   18.4GB  14.1GB (76%)
/dev/nvme0n1p2   100G  100G  0  100% /var/lib/docker
```

A 100% `/var/lib/docker` filesystem causes failed pulls, failed starts and containers that cannot write logs.

## 6. Production Usage Notes

- **Runbook per symptom:** keep one page each for crash loop, OOM, unhealthy, slow, unreachable, disk full, daemon down. Link them from alerts.
- **Crash loops** hide evidence because each restart recreates the process; `restart: unless-stopped` with a back-off helps, and `docker events` plus `RestartCount` give the timeline. Temporarily stop the loop (`docker update --restart=no api`) to keep the last state.
- **OOM:** distinguish container OOM (`OOMKilled=true`, `memory.events`) from host OOM (kernel log shows the victim chosen across cgroups). Raise the limit only after confirming whether it is a leak, a heap setting (JVM and Node heap flags ignoring the cgroup) or genuine growth.
- **Logs missing:** with `json-file` and no rotation, the disk fills; with `--log-driver` remote drivers, an unreachable endpoint can block the app (`mode: non-blocking` trades loss for liveness; see [§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)).
- **Unhealthy but serving:** read `docker inspect --format '{{json .State.Health}}'`; the probe output is stored there. A probe that needs `curl` fails in images that lack it.
- **Network:** check the order DNS, route, port, firewall. Embedded DNS (127.0.0.11) only works on user-defined networks ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)). Published ports use NAT; check `iptables -t nat -S DOCKER` or the nftables equivalent ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).
- **Daemon restarts:** without `live-restore` all containers stop when `dockerd` restarts ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Write a blameless post-incident note** with timeline, evidence, root cause and the alert or test that would have caught it.

## 7. Security Considerations

- **Debug access is privileged access.** `docker exec`, `--pid container:` with `SYS_PTRACE`, and `nsenter` bypass application auth and can read secrets from memory and `/proc/<pid>/environ`. Restrict, log and time-box them.
- **Do not make the debug fix permanent:** never add `--privileged`, `--cap-add SYS_PTRACE` or a shell to the production image "to make debugging easier"; use a separate debug image or sidecar.
- **Evidence contains secrets:** `docker inspect` shows environment values and `docker commit`/`export` capture files; redact before pasting into tickets and treat archives as sensitive ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Do not expose the Docker socket or remote API** for convenience during an incident; use SSH-based contexts (`docker context create --docker host=ssh://...`).
- **Treat unexpected processes as compromise signals:** an unfamiliar binary in `docker diff` or `docker top`, outbound connections to unknown hosts, or a container running as root with new files under `/tmp` should trigger the security path, not just a restart ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Check and fix |
|---|---|---|
| Exit 137, `OOMKilled=true` | Memory limit too low or leak | `memory.events`, heap flags, raise `--memory` or fix leak |
| Exit 137, `OOMKilled=false` | Stop timeout SIGKILL or external `kill` | Shell-form CMD ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)); raise `--stop-timeout`; check who called kill via `docker events` |
| Exit 127 / 126 | Missing binary, wrong arch, CRLF script | `docker run --entrypoint sh`, `file`, check platform ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)) |
| Restart loop, no logs | Crash before logging, bad entrypoint | `docker logs` empty: run with `--entrypoint sh`, inspect `State.Error` |
| `no space left on device` | `/var/lib/docker` full or inodes exhausted | `docker system df`, `df -i`, prune ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)), log rotation |
| `unhealthy` but app works | Probe wrong port, missing curl, tight timeout | `Health.Log`, tune `start_period`, `timeout` |
| High latency, low host CPU | CFS throttling | `cpu.stat nr_throttled`; raise `--cpus` or remove tiny limits |
| `Temporary failure in name resolution` | Default bridge (no DNS), broken host resolv.conf | Use user-defined network; check `/etc/resolv.conf` in container |
| Port published but refused | App binds `127.0.0.1` inside container | Bind `0.0.0.0`; `ss -ltn` from netshoot |
| Intermittent connection resets | Conntrack table full, MTU mismatch (overlay/VPN) | `dmesg` conntrack, `ip link` MTU, set daemon `mtu` |
| `permission denied` on volume | UID mismatch, SELinux label | Compare `id` with file owner; `:z`/`:Z` ([§61](../Part8/Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)) |
| Many `Z` processes in `docker top` | PID 1 does not reap children | Add `--init`/tini |
| `Cannot connect to the Docker daemon` | Daemon down or socket permissions | `systemctl status docker`, `journalctl -u docker`, group membership |
| Pull fails `toomanyrequests` | Registry rate limit | Authenticate, mirror ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)) |

## 9. Best Practices

- Follow a fixed order: state, exit code, logs, events, resources, network, host.
- Capture evidence (`inspect`, `logs`, `diff`, `top`) before restarting or removing anything.
- Alert on symptoms you can act on: restart count, OOM events, throttling ratio, disk and inode usage, health status ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)).
- Give every container a health check, log rotation, memory limit and a tag that maps to a Git commit so "what is running" is answerable ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- Keep a pinned debug image (netshoot or similar) in your private registry for sidecar use.
- Reproduce on a copy: run the same image digest with the same env and limits in staging before changing production.
- Prefer rollback to a known-good digest over live patching when the cause is a bad release ([§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)).
- Record each incident in a runbook so the next occurrence is a lookup, not an investigation.

## 10. Common Anti-Patterns / Mistakes

- Restarting first and investigating later, which destroys `OOMKilled` context, the writable layer and in-memory state.
- Reading only application logs and missing that the kernel or the daemon killed the container.
- Raising memory limits blindly instead of checking for leaks or ignored cgroup limits.
- Installing debug tools into the running container (`apt install` in prod), changing it and leaving drift.
- Adding `--privileged` or the Docker socket to "see more".
- Debugging on the wrong host or wrong tag because deployments use `latest`.
- Ignoring disk and inode exhaustion on the daemon host.
- Treating "works on my machine" as proof; compare image digest, env, limits, platform and kernel.

## 11. Interview Questions

**🎯 Beginner:** _"A container keeps restarting. What are your first three commands?"_
**Model answer:** `docker ps -a` to confirm the state and restart count; `docker inspect <c> --format '{{.State.ExitCode}} {{.State.OOMKilled}} {{.State.Error}}'` to classify the failure; and `docker logs --tail 100 <c>` for the last output before the crash. Exit 137 with OOMKilled true means a memory limit kill, 127 means a missing command, 1 usually an application error. I would also check `docker events` for the timeline before changing anything.
_What the interviewer is probing for:_ A structured start with state and exit code before logs, and knowing common exit codes.

**🎯 Intermediate:** _"A distroless container is misbehaving and has no shell. How do you debug it?"_
**Model answer:** Use a second container that joins the broken one's namespaces: `docker run --rm -it --network container:app nicolaka/netshoot` for network tools, adding `--pid container:app --cap-add SYS_PTRACE` for process inspection and file access through `/proc/<pid>/root`. On the host, `nsenter -t <pid> -n` gives the same view, and `docker debug` is an option on Docker Desktop and subscriptions. Copy files out with `docker cp`. I would not rebuild the image with a shell for production; I would use a separate debug variant for staging.
_What the interviewer is probing for:_ Namespace sharing as a debugging tool and keeping production images minimal.

**🎯 Senior:** _"Users report latency spikes, but host CPU is 30% and the app shows no errors. Walk through your diagnosis."_
**Model answer:** Suspect CFS throttling: with `--cpus` set, a bursty process is paused for the rest of each 100 ms period even though the host is idle. I read `cpu.stat` (`nr_throttled`, `throttled_usec`) from the container's cgroup or the cAdvisor `container_cpu_cfs_throttled_periods_total` metric. If the ratio is high, raise or remove the limit, or reduce thread count to match it. I also check GC pauses, noisy neighbours (host `iowait`, `docker stats` of siblings), conntrack or DNS latency, and CPU requests versus limits if under Kubernetes. I would confirm the fix by watching the throttle ratio and p99 latency together.
_What the interviewer is probing for:_ Knowing that container limits produce performance symptoms invisible at host level, and using cgroup counters to prove it.

**🎯 Architect:** _"Design the troubleshooting capability for a fleet of 500 containers across 40 hosts so that on-call engineers resolve most incidents without SSH."_
**Model answer:** Centralize the evidence: structured logs shipped off-host with rotation locally ([§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)); metrics from cAdvisor/Prometheus including restarts, OOM, throttling, disk and inode usage; daemon events and `docker inspect` state exported as metrics or events; and exit-code-labelled alerts linked to runbooks. Standardize images with health checks, labels (git SHA, owner), digest-pinned tags and an init. Provide audited, time-boxed debug access (SSH contexts or a break-glass role) plus a signed debug sidecar image. Automate safe first responses (restart with back-off, rollback on failed health gate) and require a post-incident review that feeds new alerts and runbooks. Measure MTTR and the share of incidents solved from telemetry alone.
_What the interviewer is probing for:_ Observability by design, controlled privileged access, and process maturity rather than ad hoc heroics.

## 12. Common Misconceptions

- "Exit code 137 always means out of memory." It means SIGKILL; check `OOMKilled`, since stop timeouts also produce it.
- "If the logs are empty, nothing happened." The process may have been killed before flushing, or the log driver may have failed.
- "`docker restart` is a safe first step." It erases state you may need.
- "Containers can't be debugged without a shell." Namespace-sharing sidecars and `nsenter` work on any container.
- "High host CPU is required for CPU problems." Throttling hurts at low host utilization.
- "A healthy status means the app is correct." It only means the probe passed.

## 13. 🔑 Key Takeaways

- Triage order: state, exit code, logs, events, resources, network, host.
- Exit 137 plus `OOMKilled=true` is a memory kill; 137 alone is a SIGKILL from stop timeout or an external signal.
- Preserve evidence (`inspect`, `logs`, `diff`, `top`, `commit`) before restarting.
- Debug minimal images by joining their namespaces from a sidecar, not by modifying them.
- Check cgroup counters (`memory.events`, `cpu.stat`) and host disk, inodes and kernel log, not only application logs.
- Debug access is privileged; keep it audited and temporary.

## 14. Related Concepts & What's Next

Related: logging ([§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)), metrics ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)), health checks ([§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), rollback ([§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)), network troubleshooting ([§47](../Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)). Scenario drills appear in [§102](../Part14/Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md). Part 13 begins by turning the lessons from many incidents into a checklist, starting with [§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md).

**Next Section:** [§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md) — `Section-94-Part13-Dockerfile-Best-Practices-Checklist.md`
