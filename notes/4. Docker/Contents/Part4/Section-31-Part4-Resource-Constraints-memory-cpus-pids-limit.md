# Section 31 (Part 4): Resource Constraints: --memory, --cpus, --pids-limit

## 1. Definition

**Plain language:** By default a container may use as much CPU, memory and as many processes as the host will give it. Resource flags put a ceiling (or a priority) on that use, so one runaway container cannot starve its neighbors or take down the host.

**Precise definition:** Docker translates `docker run` resource flags into **cgroup** settings ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)) applied by runc to the container's cgroup. The main flags are:

| Flag | Meaning | cgroup v2 file |
|---|---|---|
| `-m`, `--memory` | Hard memory limit (RAM, plus swap if not capped by `--memory-swap`) | `memory.max` |
| `--memory-swap` | Total of memory **plus** swap; `-1` = unlimited swap | `memory.swap.max` (swap part) |
| `--memory-reservation` | Soft limit, enforced only under host memory pressure | `memory.low` |
| `--cpus` | Number of CPUs of time (fractional allowed), a hard cap | `cpu.max` (quota/period) |
| `--cpu-shares` | Relative weight (default 1024) used only under contention | `cpu.weight` |
| `--cpuset-cpus` | Pin to specific CPU cores | `cpuset.cpus` |
| `--pids-limit` | Maximum tasks (processes and threads); `-1` = unlimited | `pids.max` |

When a container exceeds its memory limit and the kernel cannot reclaim enough, the **OOM killer** terminates a process in that cgroup. CPU limits **throttle** rather than kill. Limits can be changed on a live container with `docker update`.

> 💡 **Tip:** Memory is incompressible (exceed it and something dies); CPU is compressible (exceed it and you slow down). Size them accordingly.

## 2. Why This Matters

- **Noisy neighbors:** one leaking service can trigger host-wide swapping and OOM kills of unrelated containers or `dockerd` itself.
- **Fork bombs and thread leaks:** without a PID limit a container can exhaust the host's process table.
- **Predictable performance:** CPU quotas and shares make capacity planning and latency behavior explainable.
- **Kubernetes parity:** `requests` and `limits` in pod specs are the same cgroup mechanisms; exit code 137 and `OOMKilled` mean the same thing in both.
- **Interviews and DCA:** "What happens at the memory limit?", "What is the difference between `--cpus` and `--cpu-shares`?" and "What is `--memory-swap`?" are staple questions.

## 3. Prerequisites and Dependencies

Requires cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md), and the overview in [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md)), the runtime chain that applies them ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), and daemon-level defaults ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Familiarity with `docker run` flags and PID 1 behavior ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) helps. Logs that show a killed process are in [§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md). Restart behavior after an OOM kill is in [§32](Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md). On Docker Desktop, limits apply *inside* the Linux VM, which itself has a CPU and memory allocation configured in Desktop settings.

## 4. Architecture / Conceptual Diagram

```text
   docker run --memory=512m --cpus=1.5 --pids-limit=200 app
        │
        ▼
   dockerd ──► containerd ──► runc ──► writes cgroup files
                                         │
   /sys/fs/cgroup/system.slice/docker-<id>.scope/       (cgroup v2, systemd driver)
      ├─ memory.max       = 536870912        ◄── --memory
      ├─ memory.swap.max  = 0 .. N           ◄── --memory-swap minus --memory
      ├─ memory.low       = soft target      ◄── --memory-reservation
      ├─ cpu.max          = "150000 100000"  ◄── --cpus=1.5  (quota period)
      ├─ cpu.weight       = 1..10000         ◄── --cpu-shares (1024 ≈ weight 39)
      └─ pids.max         = 200              ◄── --pids-limit

   Memory limit hit                             CPU limit hit
  ┌──────────────────────────┐              ┌──────────────────────────┐
  │ 1. kernel reclaims cache │              │ quota used inside the    │
  │ 2. swap (if allowed)     │              │ 100 ms period            │
  │ 3. OOM killer picks a    │              │   ──► threads throttled  │
  │    process in the cgroup │              │ until next period        │
  │ 4. exit 137, OOMKilled   │              │ (nr_throttled counters)  │
  └──────────────────────────┘              └──────────────────────────┘

   Swap arithmetic (--memory=512m)
  ┌──────────────────────────┬──────────────────────────────────────────┐
  │ --memory-swap not set    │ swap allowed = 512m (total 1g) if host   │
  │                          │ has swap enabled                         │
  │ --memory-swap=512m       │ equal to memory: NO swap                 │
  │ --memory-swap=1g         │ 512m RAM + 512m swap                     │
  │ --memory-swap=-1         │ unlimited swap                           │
  └──────────────────────────┴──────────────────────────────────────────┘
```

- **Hard vs soft:** `--memory` and `--cpus` are ceilings; `--memory-reservation` and `--cpu-shares` are only consulted under pressure or contention.
- **Total, not additive:** `--memory-swap` is RAM plus swap combined, a common source of mistakes.
- **cgroup v1 vs v2:** file names differ (v1 uses `memory.limit_in_bytes`, `cpu.cfs_quota_us`, `cpu.shares`), but the Docker flags are the same.

## 5. Hands-On

### 5.1 Set Limits and Confirm Them

```bash
docker run -d --name limited --memory=256m --cpus=0.5 --pids-limit=100 alpine:3.20 sleep 3600
docker inspect limited --format 'Mem={{.HostConfig.Memory}} NanoCpus={{.HostConfig.NanoCpus}} Pids={{.HostConfig.PidsLimit}} Swap={{.HostConfig.MemorySwap}}'
```

```text
Mem=268435456 NanoCpus=500000000 Pids=100 Swap=536870912
```

`NanoCpus` is `--cpus` times 10^9. Swap shows 512 MiB because, unset, it defaults to twice `--memory` when the host has swap enabled.

### 5.2 Read the Limits From Inside the Container (cgroup v2)

```bash
docker exec limited sh -c 'cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max /sys/fs/cgroup/pids.max'
```

```text
268435456
50000 100000
100
```

`50000 100000` means 50 ms of CPU time per 100 ms period, which is 0.5 CPU. On a cgroup v1 host the same data is under `/sys/fs/cgroup/memory/memory.limit_in_bytes` and `/sys/fs/cgroup/cpu/cpu.cfs_quota_us`. Check which one you have with `docker info --format '{{.CgroupVersion}}'`.

### 5.3 Trigger and Diagnose an OOM Kill

Run this in a throwaway container only; it allocates memory beyond the limit.

```bash
docker run --name oomtest --memory=64m --memory-swap=64m alpine:3.20 \
  sh -c 'head -c 200m /dev/zero | tail -c 1 >/dev/null'
echo "exit=$?"
docker inspect oomtest --format 'OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}}'
docker rm oomtest
```

```text
exit=137
OOMKilled=true ExitCode=137
```

Exit code 137 is 128 plus signal 9 (SIGKILL). `OOMKilled=true` confirms the cause was the memory cgroup, not a manual `docker kill` (which also yields 137 but with `OOMKilled=false`). Host-side evidence appears in `dmesg` as `Memory cgroup out of memory: Killed process ...`, and `docker events --filter event=oom` records the event live.

### 5.4 Watch Usage Against Limits

```bash
docker stats --no-stream limited
```

```text
CONTAINER ID   NAME      CPU %   MEM USAGE / LIMIT   MEM %   NET I/O     BLOCK I/O   PIDS
3f1c9a7b02de   limited   0.00%   612KiB / 256MiB     0.23%   796B / 0B   0B / 0B     1
```

Without a limit, the LIMIT column shows total host (or Docker Desktop VM) memory, which is a quick way to spot unconstrained containers.

### 5.5 CPU: `--cpus` (Hard Cap) vs `--cpu-shares` (Relative Weight)

```bash
# Hard cap: never more than 0.5 CPU even if the host is idle
docker run -d --name capped --cpus=0.5 alpine:3.20 sh -c 'while :; do :; done'

# Weights: only matter when CPUs are contended
docker run -d --name heavy --cpu-shares=2048 --cpuset-cpus=0 alpine:3.20 sh -c 'while :; do :; done'
docker run -d --name light --cpu-shares=512  --cpuset-cpus=0 alpine:3.20 sh -c 'while :; do :; done'
docker stats --no-stream capped heavy light
docker rm -f capped heavy light
```

```text
NAME     CPU %
capped   50.12%
heavy    79.8%
light    20.1%
```

`heavy` and `light` are pinned to the same core with `--cpuset-cpus=0` to create contention; the 2048:512 weight ratio yields roughly an 80/20 split. Remove the pinning on an idle multi-core host and both would take a full core: shares never cap, they only arbitrate.

### 5.6 Throttling Evidence

```bash
docker exec capped cat /sys/fs/cgroup/cpu.stat 2>/dev/null | grep -E 'nr_periods|nr_throttled|throttled_usec'
```

```text
nr_periods 842
nr_throttled 840
throttled_usec 41872033
```

A high `nr_throttled / nr_periods` ratio means the app wants more CPU than its quota. This is the usual explanation for "latency spikes while CPU graphs look low".

### 5.7 PID Limit Versus a Fork Bomb

Safe only because the container has a hard cap and runs on a throwaway name; do not run this without `--pids-limit`.

```bash
docker run --rm --pids-limit=50 alpine:3.20 sh -c 'for i in $(seq 1 200); do sleep 30 & done; echo spawned'
```

```text
sh: can't fork: Resource temporarily unavailable
sh: can't fork: Resource temporarily unavailable
spawned
```

The pids cgroup refuses new tasks beyond 50. Both processes and threads count, so a thread-heavy JVM or Go service may need a few hundred.

### 5.8 Soft Reservation

```bash
docker run -d --name soft --memory=1g --memory-reservation=256m nginx:1.27-alpine
docker inspect soft --format '{{.HostConfig.MemoryReservation}}'
```

```text
268435456
```

The container can burst to 1 GiB, but when the host is under memory pressure the kernel reclaims it back toward 256 MiB first. The reservation must be lower than `--memory`.

### 5.9 Change Limits on a Running Container with `docker update`

```bash
docker update --memory=512m --memory-swap=512m --cpus=1 --pids-limit=300 limited
docker inspect limited --format 'Mem={{.HostConfig.Memory}} NanoCpus={{.HostConfig.NanoCpus}}'
```

```text
Mem=536870912 NanoCpus=1000000000
```

No restart is needed. When lowering `--memory`, set `--memory-swap` in the same command, otherwise the new memory value can conflict with the old swap value and be rejected. `docker update --restart` is covered in [§32](Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md). `docker update` changes the live cgroup and the stored container config but not the image or Compose file, so it will be reverted on recreation.

### 5.10 Compose and Daemon Defaults

```yaml
services:
  api:
    image: myorg/api:1.4.2
    mem_limit: 512m
    cpus: 1.0
    pids_limit: 200
    # Compose v2 also accepts the Swarm-style form:
    # deploy:
    #   resources:
    #     limits: { cpus: "1.0", memory: 512M, pids: 200 }
    #     reservations: { memory: 256M }
```

Per-container defaults can be set daemon-wide only for a few things (for example `default-ulimits` and `default-shm-size` in `daemon.json`, [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)); there is no daemon-wide default memory limit, so enforce limits in the run command, Compose file or orchestrator policy.

## 6. Production Usage Notes

- **Always set a memory limit on production containers**, sized from measured working set plus headroom (typically peak RSS plus 20-30%).
- **Pair `--memory` with `--memory-swap` equal to it** to disable swap for latency-sensitive services; swapping inside a container hides leaks and wrecks tail latency.
- **Language runtimes must be limit-aware.** Modern JVMs (container support since JDK 10, backported to 8u191) read the cgroup limit; set `-XX:MaxRAMPercentage=75`. Node.js needs `--max-old-space-size` set below the limit; Go may need `GOMEMLIMIT` and `GOMAXPROCS` aligned to `--cpus`.
- **CPU limits vs shares:** many teams set a memory limit and a CPU *request-like* share, avoiding hard CPU caps to prevent throttling latency; others cap strictly for multi-tenant fairness. Make it a conscious policy.
- **Visible CPU count:** a container with `--cpus=1` still sees all host cores in `nproc` and `/proc/cpuinfo`; libraries sizing thread pools by core count will over-subscribe. Use `--cpuset-cpus` or cgroup-aware settings.
- **Restart policy interplay:** an OOM-killed container with `--restart=always` or `on-failure` loops; combine with alerting on restart counts and `OOMKilled` ([§32](Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)).
- **Monitoring:** scrape cgroup metrics via cAdvisor or the Docker stats API; alert on memory working set near limit, `nr_throttled` growth and PID count near `pids.max`.
- **Kubernetes mapping:** `resources.limits.memory` becomes `memory.max`, `limits.cpu` becomes `cpu.max`, `requests.cpu` becomes `cpu.weight`, `requests.memory` feeds scheduling and `memory.low`/QoS.
- **Page cache counts toward the limit** but is reclaimable; `docker stats` subtracts inactive file cache in recent versions, so a high raw number is not automatically a leak.

## 7. Security Considerations

- **Denial of service containment:** unlimited containers let one compromised or buggy tenant exhaust host memory, CPU and PIDs. Limits are a core part of container hardening alongside capabilities and seccomp.
- **Fork bomb defense:** `--pids-limit` is the mitigation; `--ulimit nproc` is per-UID across the host and is a poor substitute.
- **OOM killer targets:** under host-wide memory exhaustion the kernel may kill `dockerd` or other containers. Limits keep pressure inside each cgroup. Use `--oom-score-adj` to make critical containers less likely victims, and avoid `--oom-kill-disable`: with a hard limit it can hang the container and, without a limit, can freeze the host.
- **Privileged containers escape limits:** `--privileged` containers can write to cgroup files and lift their own caps; combine limits with dropping privileges ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md) covers the namespace side).
- **Docker socket access = ability to `docker update`:** anyone who can reach the daemon can raise or remove limits ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Side channels:** shared CPU cores still allow timing channels between tenants; limits do not replace isolation for hostile multi-tenancy.
- **Observability of limits:** log and alert when containers are started without limits (policy engines or CI checks on Compose files).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Container exits with code 137 | SIGKILL: OOM kill or `docker kill`/stop timeout | `docker inspect` `.State.OOMKilled`; check `dmesg`; raise limit or fix leak |
| `OOMKilled=false` but exit 137 | Killed by `docker stop` timeout or an external `kill -9` | Fix SIGTERM handling ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) |
| `WARNING: Your kernel does not support swap limit capabilities` | Swap accounting disabled on host | Enable `swapaccount=1` kernel parameter, or ignore if swap is off |
| `Minimum memory limit allowed is 6MB` | Limit set too low | Use at least 6 MiB; realistically far more |
| `Memory limit should be smaller than already set memoryswap limit` on update | Lowering `--memory` below old swap total | Update `--memory` and `--memory-swap` together |
| App slow, CPU graph low | CFS throttling at `--cpus` cap | Check `cpu.stat`; raise quota or use shares |
| JVM or Node killed despite "free" memory | Heap sized from host RAM, not cgroup | Set `MaxRAMPercentage`, `--max-old-space-size`, `GOMEMLIMIT` |
| `can't fork` / `Resource temporarily unavailable` | `pids.max` reached (threads count too) | Raise `--pids-limit`; find the thread or process leak |
| `docker stats` limit equals host RAM | No limit set | Add `--memory` |
| Limits ignored on Docker Desktop | VM allocation is the real ceiling | Raise it in Desktop settings and still set per-container limits |
| `--cpus` > host cores rejected | Exceeds available CPUs | Use at most the number of cores (`nproc`) |

## 9. Best Practices

- Set `--memory`, `--memory-swap` (equal to memory for no swap) and `--pids-limit` on every long-running container; add `--cpus` or shares per policy.
- Derive limits from load-test measurements; revisit after each major release.
- Make the application cgroup-aware and keep its internal heap below the container limit.
- Use `--memory-reservation` and `--cpu-shares` to express priority, and hard limits to express safety.
- Use `docker update` for emergency adjustments, then encode the change in the Compose or deployment file.
- Alert on `OOMKilled`, restart count, CPU throttling ratio and PID usage.
- Test limits in disposable containers before applying them to real workloads, and keep experiments away from important data.
- Enforce "no limit, no deploy" with admission or CI policy.
- Prefer `--cpuset-cpus` only for latency-critical pinned workloads; it reduces scheduler flexibility.

## 10. Common Anti-Patterns / Mistakes

- Running production containers with no limits "because it's simpler".
- Setting only `--memory` and unknowingly allowing equal swap, masking leaks.
- Reading `--memory-swap` as additional swap rather than the RAM-plus-swap total.
- Treating `--cpu-shares` as a cap and expecting 512 shares to mean "half a CPU".
- Using `--oom-kill-disable` without `--memory`, which can hang the host.
- Setting a JVM `-Xmx` equal to the container limit, leaving no room for metaspace, threads and native memory.
- Setting `--cpus=1` and a thread pool sized by `nproc` (all host cores).
- Using `docker update` as the permanent configuration and losing it on redeploy.
- Setting `--pids-limit` so low that normal thread pools fail, or never setting it at all.
- Confusing `--kernel-memory` (deprecated and removed in modern Engine versions) with `--memory`.

## 11. Interview Questions

**🎯 Beginner:** _"A container started with `--memory=256m` keeps restarting with exit code 137. What does that mean and how do you confirm the cause?"_
**Model answer:** Exit 137 means the process received SIGKILL (128 + 9). With a memory limit, the most likely source is the kernel OOM killer acting inside the container's memory cgroup after the process exceeded 256 MiB and the kernel could not reclaim enough. Confirm with `docker inspect --format '{{.State.OOMKilled}}' name`, which is true for OOM kills, plus `dmesg` lines mentioning "Memory cgroup out of memory" and `docker events --filter event=oom`. If `OOMKilled` is false, the SIGKILL came from elsewhere, for instance a `docker stop` that timed out. Fix by raising the limit if the working set is legitimately larger, or fixing the leak.
_What the interviewer is probing for:_ Exit-code literacy and the ability to separate OOM kills from other SIGKILLs.

**🎯 Intermediate:** _"What is the difference between `--cpus=0.5` and `--cpu-shares=512`, and when would each be the right choice?"_
**Model answer:** `--cpus` sets a hard quota: through CFS bandwidth control (`cpu.max`) the container gets at most 0.5 CPU-seconds per second, even if the host is idle; beyond that its threads are throttled. `--cpu-shares` is a relative weight (default 1024, mapped to `cpu.weight` on cgroup v2) that matters only when CPUs are contended; on an idle host a 512-share container can still use every core. Use `--cpus` for multi-tenant fairness or cost-bounded workloads where predictability matters more than throughput; use shares to prioritize critical services while letting everything burst when there is spare capacity. Hard caps can cause latency spikes through throttling, which is visible in `cpu.stat`.
_What the interviewer is probing for:_ Quota versus weight, and awareness of throttling trade-offs.

**🎯 Senior:** _"Explain `--memory`, `--memory-swap` and `--memory-reservation` together. What exactly happens if you set `--memory=512m --memory-swap=1g`, and what would you change for a latency-sensitive API?"_
**Model answer:** `--memory` is the hard RAM ceiling and `--memory-swap` is the combined RAM plus swap budget, so 512m and 1g gives 512 MiB RAM plus up to 512 MiB swap (if the host has swap and accounting enabled). Pages beyond the RAM limit can be swapped before an OOM kill occurs, which postpones failure but adds disk-latency stalls. `--memory-reservation` is a soft target honored only under host pressure (`memory.low` on v2). For a latency-sensitive API I would set `--memory-swap` equal to `--memory` to disable swap, so a leak surfaces as a fast, observable OOM kill and restart rather than slow degradation; pick `--memory` from measured peak working set plus headroom, set the runtime heap below it, and add `--memory-reservation` only if I need priority under pressure. I would alert on OOM events and restart counts.
_What the interviewer is probing for:_ Correct swap arithmetic and operational judgement on failure modes.

**🎯 Architect:** _"You run 300 containers on shared hosts across teams. Design the resource governance model: defaults, enforcement, observability, and handling of noisy neighbors and fork bombs."_
**Model answer:** Define tiers (for example small, medium, large) with fixed memory, CPU weight/limit and PID caps, and make "no limit, no deploy" a CI and admission rule (Compose lint or Kubernetes LimitRange and ResourceQuota). Memory: hard limit, swap disabled, runtime heap tuned to a percentage of the cgroup. CPU: requests as shares for scheduling and fairness, hard limits only for batch or untrusted tenants, because throttling hurts latency-critical services. PIDs: a default `pids.max` (for example a few hundred) with an exception process. Host protections: reserve memory for the OS and `dockerd` (system.slice), set `--oom-score-adj` for platform agents, and run kubelet/Docker with cgroup v2 and the systemd driver for accurate accounting. Observability: cAdvisor/Prometheus with alerts on working-set-to-limit ratio, throttle ratio, PID saturation, OOM events and restart loops, plus quarterly right-sizing from the data. For hostile tenants add sandboxed runtimes (gVisor or Kata) because cgroups limit consumption, not isolation.
_What the interviewer is probing for:_ Policy-based governance, knowledge of the cgroup controllers, and limits of cgroups as a security boundary.

## 12. Common Misconceptions

- "`--cpus=2` gives the container two dedicated cores." It is a quota of two CPUs' worth of time spread across any cores.
- "`--memory-swap` is extra swap." It is RAM plus swap in total.
- "`--cpu-shares` limits CPU." It is a relative weight that only applies under contention.
- "Exceeding the CPU limit kills the container." It throttles; only memory overuse triggers the OOM killer.
- "Without a limit, the container is safe because the host will protect itself." The host OOM killer may pick the wrong victim, including `dockerd`.
- "`nproc` inside the container reflects `--cpus`." It still shows host cores.
- "`docker update` is permanent." It lasts for the life of that container only.
- "Exit 137 always means OOM." It means SIGKILL; check `OOMKilled`.

## 13. 🔑 Key Takeaways

- Resource flags configure cgroup files: `memory.max`, `cpu.max`, `cpu.weight`, `pids.max` on v2.
- Memory overuse leads to an OOM kill (exit 137, `OOMKilled=true`); CPU overuse leads to throttling.
- `--memory-swap` is the RAM-plus-swap total; set it equal to `--memory` to forbid swap.
- `--cpus` is a hard quota; `--cpu-shares` is a relative weight; `--cpuset-cpus` pins cores.
- `--pids-limit` is the defense against fork bombs and counts threads too.
- `docker update` adjusts limits live, `docker stats` and `docker inspect` verify them.
- Make applications cgroup-aware and enforce limits through policy, not goodwill.

## 14. Related Concepts & What's Next

Related: cgroups v1 vs v2 ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), runtime chain ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), logs that record OOM-killed processes ([§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md)), moving files out of a dead container ([§30](Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md)). Next, [§32](Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md) covers restart policies and health checks, which decide what happens after an OOM kill and how Docker knows a limited container is still healthy.

**Next Section:** [§32](Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md) — `Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md`
