# Section 89 (Part 12): Resource Management at Scale

## 1. Definition

**Plain language:** Resource management at scale is deciding how much CPU, memory, process slots, disk and I/O each container may use, enforcing it, and sizing hosts so that hundreds of containers share machines without starving one another or crashing the node.

**Precise definition:** Docker translates run-time flags and Compose settings into cgroup controls ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)). The vocabulary splits into **limits** (hard ceilings: `--memory`, `--cpus`, `--pids-limit`), **reservations** (soft guarantees or hints: `--memory-reservation`, `--cpu-shares`), and **placement** (which host or CPUs run what: `--cpuset-cpus`, Swarm constraints, orchestrator schedulers). "At scale" adds fleet concerns: defaults enforced by policy, noisy-neighbor isolation, overcommit ratios, headroom for the daemon and OS, disk and log growth, and capacity planning driven by measured usage ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)). Individual flags are introduced in [§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md); this section is about applying them systematically.

> 💡 **Tip:** Limits protect *the host and neighbors* from one container; reservations and placement protect *one container* from neighbors. You need both ideas, and Docker alone gives you far more of the first than the second.

## 2. Why This Matters

- A container without a memory limit can consume the whole host; the kernel OOM killer then picks victims, often `dockerd` or a database rather than the offender.
- A fork bomb or thread leak without `--pids-limit` can exhaust the host's PID table.
- CPU is compressible (processes slow down) but memory is not (processes die). Treating them identically leads to wrong limits.
- Over-provisioned limits waste money; under-provisioned limits cause OOM kills and throttling latency. Right-sizing is a continuous activity.
- Disk is the quiet resource killer: unrotated logs, writable layers and dangling images fill `/var/lib/docker` and stop every container on the host ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).
- These concepts carry directly into Kubernetes requests/limits and QoS classes, a frequent senior interview topic.

## 3. Prerequisites and Dependencies

Requires cgroups v1 vs v2 ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), the basic constraint flags ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), `docker run` ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), Compose ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md), [§39](../Part5/Section-39-Part5-Scaling-Services-with-Compose.md)), storage behaviour ([§50](../Part7/Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md), [§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md)), and metrics ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)).

## 4. Architecture / Conceptual Diagram

```text
 Host: 16 CPU / 64 GiB RAM / 500 GB disk
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ Reserved for OS + dockerd + containerd + monitoring  (~10-15%)            │
 ├───────────────────────────────────────────────────────────────────────────┤
 │  root cgroup (/sys/fs/cgroup)                                             │
 │   ├── system.slice/docker.service        (daemon, optional MemoryMax)     │
 │   ├── system.slice/docker-<id>.scope     (container A)                    │
 │   │       memory.max   = --memory                                         │
 │   │       memory.low   = --memory-reservation   (cgroup v2: soft protect) │
 │   │       memory.swap.max (via --memory-swap)                             │
 │   │       cpu.max      = --cpus  (quota/period)                           │
 │   │       cpu.weight   = --cpu-shares (relative, only under contention)   │
 │   │       cpuset.cpus  = --cpuset-cpus                                    │
 │   │       pids.max     = --pids-limit                                     │
 │   │       io.max/io.weight = --device-read-bps / --blkio-weight           │
 │   └── tenant-a.slice/ (via --cgroup-parent)  ◄── group quota for tenants  │
 └───────────────────────────────────────────────────────────────────────────┘

  Behaviour under pressure
  ┌────────────┬───────────────────────────────────────────────────────────┐
  │ CPU        │ over quota ──► throttled (slower, not killed)             │
  │ Memory     │ over memory.max ──► reclaim, then OOM-kill in that cgroup │
  │ PIDs       │ at pids.max ──► fork() fails with EAGAIN                  │
  │ Disk       │ no per-container cap by default ──► host fills, all fail  │
  └────────────┴───────────────────────────────────────────────────────────┘

  Overcommit:  sum(limits) may exceed host capacity;  sum(reservations) should not.
```

- **Hard limits are enforced per container cgroup,** so one container's OOM kills only its own processes.
- **CPU shares only matter under contention;** an idle host lets any container burst.
- **Sum of limits** greater than physical memory is overcommit: safe only if usage is rarely simultaneous and the limit-to-request gap is understood.

## 5. Hands-On

### 5.1 The Core Flags and What They Do

```bash
docker run -d --name api \
  --memory 512m --memory-reservation 384m --memory-swap 512m \
  --cpus 1.5 --cpu-shares 512 \
  --pids-limit 200 \
  --ulimit nofile=4096:8192 \
  --oom-score-adj 300 \
  myorg/api:1.4.2

docker inspect api --format 'mem={{.HostConfig.Memory}} res={{.HostConfig.MemoryReservation}} swap={{.HostConfig.MemorySwap}} nano={{.HostConfig.NanoCpus}} pids={{.HostConfig.PidsLimit}}'
```

```text
mem=536870912 res=402653184 swap=536870912 nano=1500000000 pids=200
```

- `--memory-swap` equal to `--memory` disables swap for the container (swap total = memory + swap).
- `--oom-score-adj` raises the container's attractiveness to the host OOM killer (range -1000 to 1000). Giving less important workloads a higher value protects critical ones.
- `--cpu-shares` is a relative weight (default 1024), not a cap.

### 5.2 Verify the Limits Inside the Kernel View

```bash
CID=$(docker inspect -f '{{.Id}}' api)
cat /sys/fs/cgroup/system.slice/docker-$CID.scope/memory.max
cat /sys/fs/cgroup/system.slice/docker-$CID.scope/cpu.max
cat /sys/fs/cgroup/system.slice/docker-$CID.scope/pids.max
docker exec api cat /sys/fs/cgroup/memory.max
```

```text
536870912
150000 100000
200
536870912
```

`cpu.max` of `150000 100000` means 150 ms of CPU per 100 ms period, i.e. 1.5 cores. The path above applies to the systemd cgroup driver on cgroup v2; with `cgroupfs` the scope path differs.

### 5.3 Observe a Memory Limit Being Enforced

```bash
docker run --rm --name hog --memory 64m --memory-swap 64m python:3.12-slim \
  python -c "x=[]; [x.append(b'x'*1024*1024) for _ in range(200)]"
echo "exit=$?"
docker inspect hog --format '{{.State.OOMKilled}}' 2>/dev/null || true
```

```text
Killed
exit=137
```

Exit code 137 is 128 + SIGKILL(9). With `--rm` the state is gone, so use a named container without `--rm` and inspect `.State.OOMKilled` to confirm the cause.

### 5.4 Compose: Limits and Reservations

```yaml
services:
  api:
    image: myorg/api:1.4.2
    deploy:
      resources:
        limits:
          cpus: "1.5"
          memory: 512M
          pids: 200
        reservations:
          cpus: "0.5"
          memory: 384M
    ulimits:
      nofile: { soft: 4096, hard: 8192 }
    restart: unless-stopped
```

Compose v2 honors `deploy.resources.limits` outside Swarm (`docker compose up`); `reservations` become `--memory-reservation` for memory, and are scheduling constraints only under Swarm. Confirm with `docker compose config` and `docker inspect`.

### 5.5 Fleet Defaults in `daemon.json`

```json
{
  "default-ulimits": { "nofile": { "Name": "nofile", "Hard": 65536, "Soft": 65536 } },
  "log-driver": "local",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "default-shm-size": "64M",
  "live-restore": true,
  "storage-driver": "overlay2"
}
```

```bash
sudo systemctl reload docker      # live-restore lets containers survive a daemon restart
docker info --format 'logdriver={{.LoggingDriver}} cgroup={{.CgroupVersion}}/{{.CgroupDriver}}'
```

```text
logdriver=local cgroup=2/systemd
```

Daemon-level defaults give every container sane ulimits and bounded logs ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)) even if a team forgets to set them. Memory and CPU have no daemon-wide default: enforce those through templates and admission checks.

### 5.6 Disk: Writable Layer and Volume Budgeting

```bash
docker system df -v | head -20
docker ps -s --format 'table {{.Names}}\t{{.Size}}'
# per-container writable-layer cap (overlay2 on XFS with pquota only)
docker run -d --storage-opt size=5G --name capped myorg/api:1.4.2
```

`--storage-opt size` works only when `/var/lib/docker` is on XFS mounted with `pquota`; on ext4 it errors. A more portable control is to put `/var/lib/docker` on its own volume, alert at 70-80% usage, run scheduled prunes of dangling data, and mount `tmpfs` with `size=` for scratch space ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)).

```bash
docker run -d --read-only --tmpfs /tmp:rw,size=64m,noexec myorg/api:1.4.2
```

### 5.7 Group Quotas and Noisy-Neighbor Isolation

```bash
# systemd slice that caps a tenant's total CPU and memory
sudo systemd-run --unit=tenant-a --slice=tenant-a.slice -p CPUQuota=400% -p MemoryMax=16G --property=Delegate=yes sleep infinity
# containers join the slice's cgroup
docker run -d --cgroup-parent=tenant-a.slice --memory 1g myorg/tenant-a-app:3.1
```

Per-container limits cannot stop 100 small containers from together consuming the host. A parent cgroup (slice) provides an aggregate ceiling for a tenant, team or environment. Pin latency-critical workloads to dedicated cores with `--cpuset-cpus 2-5` and keep batch jobs on the rest.

### 5.8 Right-Sizing with Measurements

```text
# p95 working set over 14 days, per service (Prometheus)
quantile_over_time(0.95, container_memory_working_set_bytes{name=~"api.*"}[14d])

# peak CPU cores used vs. configured limit
max_over_time(rate(container_cpu_usage_seconds_total{name=~"api.*"}[5m])[14d:5m])
```

A common rule: memory limit = observed p99 peak plus 20-30 percent headroom (memory cannot be borrowed back by throttling); CPU limit around 1.5-2x the p95 for latency-sensitive services, or no CPU limit with reservations for fairness when throttling hurts more than neighbor risk.

## 6. Production Usage Notes

- **Always set memory limits in production.** CPU limits are a policy decision; memory limits are a requirement.
- **Protect the platform:** give `dockerd`/`containerd` a negative `OOMScoreAdjust` in their systemd units and reserve memory so containers cannot starve them. Keep monitoring agents in their own cgroup with guaranteed shares.
- **Avoid swap for latency-sensitive containers** (`--memory-swap` equal to `--memory`); allow limited swap for batch jobs to smooth spikes.
- **Match JVM/Go/Node runtimes to limits:** modern JVMs read cgroup limits (`-XX:MaxRAMPercentage=75`), Go needs `GOMEMLIMIT` and, for CPU, `GOMAXPROCS` aligned with `--cpus` (or the automaxprocs library), Node needs `--max-old-space-size`. Ignoring this causes OOM kills and throttling.
- **Standardize via templates:** shared Compose fragments (`extends`/`include`) or platform defaults ([§38](../Part5/Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)) so every service declares resources; reject those that do not in CI ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)).
- **Swarm placement:** resource reservations drive the scheduler; add `--constraint node.labels.tier==batch` and `--placement-pref spread` to avoid hot nodes ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)).
- **Kubernetes mapping:** limit becomes `limits`, reservation becomes `requests`; requests == limits gives Guaranteed QoS, which is evicted last ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).

## 7. Security Considerations

- **Resource exhaustion is a denial-of-service vector.** Limits (memory, PIDs, file descriptors, disk) are a security control, not just an operations one ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- **`--pids-limit`** blunts fork bombs; set it for any container processing untrusted input. Combine with `--ulimit nproc` carefully since `nproc` is per-UID across the host, not per-container.
- **Do not disable the OOM killer** (`--oom-kill-disable`): a container hitting its limit with the killer off can freeze and hold host memory. It is also unsupported on cgroup v2.
- **Writable-layer and tmpfs quotas** stop a compromised container from filling the host disk; pair with `--read-only` ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Privileged containers bypass isolation** (they can change cgroup settings, mount devices). Never run tenant workloads privileged ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).
- **Multi-tenant hosts:** per-tenant slices, separate user namespaces ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)), and separate network segments ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)). Shared kernels mean noisy-neighbor and side-channel risks remain; use VM-level isolation for hostile tenants.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Container exits 137, `OOMKilled=true` | Exceeded `memory.max` | Raise limit after finding the leak/peak; set runtime heap flags |
| Exit 137 but `OOMKilled=false` | Killed by `docker kill`/stop timeout, or host-level OOM | Check `dmesg -T | grep -i oom`, `journalctl -k`, stop timeout |
| Random host-wide OOM kills of `dockerd` or databases | No limits on some containers; no host reserve | Limits everywhere; `OOMScoreAdjust` for daemon; reserve memory |
| Latency spikes but CPU graph low | CFS throttling from `--cpus` | Check throttle ratio ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)); raise/remove CPU limit; reduce threads |
| `fork: retry: Resource temporarily unavailable` | `pids.max` reached | Raise `--pids-limit` or fix thread/process leak |
| `too many open files` | Low `nofile` ulimit | Set `--ulimit nofile` or daemon `default-ulimits` |
| `--storage-opt size` fails: "backing fs not supported" | Not XFS with `pquota` | Use XFS `pquota`, or volume quotas elsewhere |
| Host disk full, all containers fail | Unbounded logs, writable layers, images | Log rotation, prune, separate disk, alerts at 80% |

## 9. Best Practices

- Set `--memory`, `--pids-limit` and `ulimit nofile` on every production container; add CPU limits or reservations deliberately.
- Derive numbers from measured p95/p99 data plus headroom, then review quarterly.
- Keep a host reserve for OS, daemon and monitoring; never schedule to 100%.
- Prefer requests/reservations equal to typical use and limits near peak, and track the gap (overcommit ratio) as a metric.
- Align runtime settings (JVM heap, GOMEMLIMIT/GOMAXPROCS, worker counts) with container limits.
- Bound logs and scratch space; put `/var/lib/docker` on a dedicated, monitored volume.
- Isolate critical and batch workloads with cpusets, slices, or separate hosts.
- Enforce resource declarations through templates, CI linting and admission policy rather than documentation.
- Alert on OOM events, throttling ratio, PID usage, inode and disk usage, and on limit-vs-usage drift.

## 10. Common Anti-Patterns / Mistakes

- No limits "because it works in dev," then production hosts OOM.
- Setting memory limits equal to average usage (guaranteed OOM at peaks).
- Copying one CPU limit across all services regardless of concurrency profile.
- Ignoring runtime awareness (JVM sizing from host memory, `GOMAXPROCS` = host cores) so the app overshoots its cgroup.
- Allowing swap for latency-critical containers so p99 collapses silently.
- Using `--oom-kill-disable` or privileged mode to "fix" kills.
- Unrotated `json-file` logs and `docker system prune -a --volumes` run blindly on schedule.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `--memory` and `--memory-reservation`, and what happens when a container exceeds each?"_
**Model answer:** `--memory` is a hard limit (`memory.max`); when the container's cgroup cannot reclaim enough, the kernel OOM-kills a process inside it, usually exit code 137 with `OOMKilled=true`. `--memory-reservation` is a soft limit; it only has effect when the host is under memory pressure, where the kernel reclaims from containers exceeding their reservation first. It must be lower than `--memory` and does not by itself prevent usage. `--memory-swap` controls swap on top, and setting it equal to `--memory` disables swap.
_What the interviewer is probing for:_ Hard vs soft limits and the observable failure mode.

**🎯 Intermediate:** _"Explain `--cpus`, `--cpu-shares` and `--cpuset-cpus`. When would each be the right tool?"_
**Model answer:** `--cpus` sets a CFS quota (quota/period), a hard cap on CPU time that throttles the container even if the host is idle; good for protecting neighbors or enforcing billing tiers, but it can add latency through throttling. `--cpu-shares` is a relative weight (default 1024) that only matters when CPUs are contended, so it prioritizes without capping; good for mixed workloads where bursting is fine. `--cpuset-cpus` pins to specific cores, giving isolation and cache locality for latency-critical or NUMA-aware workloads at the cost of flexibility. In practice: shares for fairness, cpuset for isolation, `--cpus` for hard ceilings where throttling is acceptable.
_What the interviewer is probing for:_ Understanding of the underlying scheduler semantics rather than memorized flags.

**🎯 Senior:** _"A host with 30 containers started killing random processes, including the database container, though each service has a memory limit. Diagnose."_
**Model answer:** If the sum of limits exceeds physical RAM, simultaneous peaks cause a host-level (global) OOM even though no cgroup hit its own limit. I would check `dmesg`/`journalctl -k` for `Out of memory: Killed process` versus `Memory cgroup out of memory`, compare sum(limits) and sum(working sets) to RAM, look for containers without limits and for page-cache and tmpfs usage that counts toward cgroups, and confirm swap settings. The kernel chose victims by `oom_score`, so I would set `--oom-score-adj` low for the database and high for batch services, give the daemon a protected score, reserve host headroom, cap overcommit by scheduling on reservations, and add alerts for host memory pressure (PSI) before kills occur. Longer term, move the database to a dedicated node or Guaranteed-style allocation where requests equal limits.
_What the interviewer is probing for:_ Distinguishing cgroup OOM from global OOM, and overcommit reasoning.

**🎯 Architect:** _"Design resource governance for a shared Docker platform serving 30 teams across 100 hosts."_
**Model answer:** Create a resource contract: every workload declares memory and PIDs limits, CPU reservations, and ulimits, enforced in CI and by an admission layer; platform defaults for logs and ulimits live in `daemon.json`. Partition capacity into tiers (guaranteed, burstable, batch) using node pools and parent cgroups/slices per team for aggregate quotas, with `oom-score-adj` aligned to tier. Scheduling uses reservations with a defined overcommit ratio per tier (for example 1.0 guaranteed, up to 2.0 batch) and host reserves for system daemons. Observability closes the loop: dashboards for usage vs request vs limit, automated right-sizing recommendations from 14-day percentiles, chargeback/showback, and alerts on OOMs, throttling and disk. Disk and log budgets are per host and per team. If requirements outgrow Docker/Swarm (bin-packing, quotas, priority and preemption, namespaces), the same contract maps to Kubernetes ResourceQuota, LimitRange and QoS classes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).
_What the interviewer is probing for:_ Governance, tiering, feedback loops and an honest view of Docker's scheduling limits.

## 12. Common Misconceptions

- "`--cpus 2` guarantees two cores." It is a ceiling; guarantees come from reservations, shares or cpusets.
- "A container's OOM kills the host." With limits, it kills inside its cgroup; without them, the global OOM killer decides.
- "Memory limit applies to heap only." It counts anonymous memory, page cache, kernel memory, tmpfs and more.
- "Docker has per-container disk quotas by default." Only with XFS `pquota`; otherwise you manage disk at the host.

## 13. 🔑 Key Takeaways

- Docker maps flags to cgroups: `memory.max`, `memory.low`, `cpu.max`, `cpu.weight`, `cpuset.cpus`, `pids.max`, `io.*`.
- CPU is throttled; memory is killed. Size memory from p99 plus headroom, and watch CFS throttling.
- Set memory, PIDs, ulimit and log limits everywhere; use `daemon.json` for fleet defaults.
- Protect the platform with host reserves and `OOMScoreAdjust`; use slices/cpusets for tenant isolation.
- Disk and logs fail hosts silently: dedicated volume, rotation, alerts, XFS quotas where needed.
- Make runtimes limit-aware, measure continuously, and plan capacity with explicit headroom and N+1.

## 14. Related Concepts & What's Next

Related: cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), constraint flags ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), metrics ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)), health and self-healing ([§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), performance tuning ([§98](../Part13/Section-98-Part13-Performance-Tuning-Recap.md)). Next, [§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md) shows how Docker's built-in orchestrator schedules services using reservations, constraints and replicas.

**Next Section:** [§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md) — `Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md`
