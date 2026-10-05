# Section 12 (Part 2): Control Groups (cgroups) Deep Dive: v1 vs v2

## 1. Definition

**Plain language:** Control groups (cgroups) are how Linux limits, accounts for, and prioritizes the resources a group of processes uses: CPU time, memory, disk I/O, and the number of processes. If namespaces decide what a container can *see*, cgroups decide how much it can *consume*.

**Precise definition:** A **cgroup** is a kernel-managed hierarchy of process groups, exposed through a pseudo-filesystem (`cgroupfs`), to which **controllers** (subsystems) attach. Two generations exist:

- **cgroup v1:** multiple independent hierarchies, one per controller (`cpu`, `memory`, `blkio`, `pids`, ...), mounted under `/sys/fs/cgroup/<controller>/`. A process can be in different places in each hierarchy.
- **cgroup v2 (unified hierarchy):** a single hierarchy at `/sys/fs/cgroup/`, where a process belongs to exactly one cgroup and controllers are enabled per subtree via `cgroup.subtree_control`. It adds better memory accounting, `memory.high` throttling, pressure stall information (PSI), and safe delegation to unprivileged users.

Docker maps flags such as `--memory`, `--cpus`, `--cpu-shares`, and `--pids-limit` onto controller files through runc ([§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). Docker supports cgroup v2 from Engine 20.10, and most current distributions (Ubuntu 22.04+, Debian 11+, Fedora, RHEL 9) default to v2.

> 💡 **Tip:** To see which version a host uses, run `stat -fc %T /sys/fs/cgroup/`: `cgroup2fs` means v2, `tmpfs` means v1 (or hybrid).

## 2. Why This Matters

- **Noisy neighbours:** without limits, one container can starve every other workload on the host.
- **OOM behaviour:** whether a container is killed, throttled, or swapped depends on memory cgroup settings; misunderstanding it produces mysterious `Exited (137)` states.
- **CPU throttling:** `--cpus` uses CFS bandwidth control, which can throttle latency-sensitive apps even when the host is idle.
- **v1 vs v2 differences** change file paths, tooling, monitoring, and rootless capabilities; many "works on my laptop" failures trace back to a version mismatch.
- **Kubernetes** requests and limits become cgroup settings on every node, and the kubelet requires the cgroup driver to match the runtime's (systemd vs cgroupfs).

## 3. Prerequisites and Dependencies

Depends on [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) (namespaces and cgroups recap), [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (runc writes cgroup settings), and [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md) (namespaces, the visibility counterpart). [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)'s `linux.resources` section is where limits appear in the runtime spec. [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) covers the `cgroup-parent` and `exec-opts native.cgroupdriver` daemon settings. You need a Linux host (or WSL2/Docker Desktop VM) for the hands-on.

## 4. Architecture / Conceptual Diagram

```text
      cgroup v1 (per-controller trees)         cgroup v2 (unified tree)

  /sys/fs/cgroup/                          /sys/fs/cgroup/
   ├─ cpu/                                  ├─ cgroup.controllers
   │   └─ docker/<id>/  cpu.cfs_quota_us    ├─ system.slice/
   ├─ memory/                               │   └─ docker-<id>.scope/
   │   └─ docker/<id>/  memory.limit_in_bytes│        ├─ cpu.max
   ├─ blkio/                                │        ├─ memory.max
   │   └─ docker/<id>/  ...                 │        ├─ memory.high
   └─ pids/                                 │        ├─ pids.max
       └─ docker/<id>/  pids.max            │        └─ cgroup.procs
                                            └─ ...
   Same container appears in each tree      One place per process; controllers
   at potentially different paths           enabled top-down via subtree_control

       docker run --memory 256m --cpus 0.5
                    │
                    ▼ (dockerd ► containerd ► runc writes the files)
        memory.max = 268435456     cpu.max = "50000 100000"
```

Under the systemd cgroup driver, each container is a transient `.scope` unit; under the `cgroupfs` driver, Docker manages the directories itself.

## 5. Hands-On

### 5.1 Identify the cgroup version and driver

```bash
$ stat -fc %T /sys/fs/cgroup/
cgroup2fs
$ docker info --format 'version={{.CgroupVersion}} driver={{.CgroupDriver}}'
version=2 driver=systemd
$ cat /sys/fs/cgroup/cgroup.controllers
cpuset cpu io memory hugetlb pids rdma misc
```

### 5.2 Set limits and read them back (v2)

```bash
$ docker run -d --name lim --memory 256m --memory-swap 256m --cpus 0.5 --pids-limit 100 nginx:1.27
$ ID=$(docker inspect -f '{{.Id}}' lim)
$ D=/sys/fs/cgroup/system.slice/docker-$ID.scope
$ cat $D/memory.max $D/cpu.max $D/pids.max
268435456
50000 100000
100
$ cat $D/memory.swap.max
0
```

`cpu.max` is `<quota> <period>` in microseconds: 50 ms of CPU per 100 ms window equals 0.5 CPU. Setting `--memory-swap` equal to `--memory` means no swap. On cgroupfs-driver hosts the path is `/sys/fs/cgroup/docker/$ID/`.

### 5.3 The v1 equivalent

```bash
$ cat /sys/fs/cgroup/memory/docker/$ID/memory.limit_in_bytes
268435456
$ cat /sys/fs/cgroup/cpu/docker/$ID/cpu.cfs_quota_us /sys/fs/cgroup/cpu/docker/$ID/cpu.cfs_period_us
50000
100000
$ cat /sys/fs/cgroup/pids/docker/$ID/pids.max
100
```

### 5.4 Live usage and accounting

```bash
$ docker stats --no-stream lim
CONTAINER ID  NAME  CPU %  MEM USAGE / LIMIT  MEM %  NET I/O    BLOCK I/O  PIDS
3f9c1a2b7d10  lim   0.00%  4.5MiB / 256MiB    1.76%  1.05kB/0B  0B/0B      3
$ cat $D/memory.current
4718592
$ grep -E 'usage_usec|nr_throttled|throttled_usec' $D/cpu.stat
usage_usec 41234
nr_throttled 0
throttled_usec 0
```

A rising `nr_throttled` indicates the CFS quota is being hit and the app is being paused.

### 5.5 Trigger an OOM kill

```bash
$ docker run --rm --name oom --memory 50m --memory-swap 50m \
    python:3.12-slim python -c "x = bytearray(200*1024*1024)"
$ echo $?
137
$ docker run -d --name oom2 --memory 50m --memory-swap 50m python:3.12-slim \
    python -c "x = bytearray(200*1024*1024)"
$ docker inspect -f '{{.State.OOMKilled}} {{.State.ExitCode}}' oom2
true 137
```

Exit code 137 is 128 + SIGKILL(9). `OOMKilled=true` confirms the kernel's memory cgroup killed it (a plain `kill -9` also gives 137 but with `OOMKilled=false`). Use `dmesg | grep -i 'killed process'` for the kernel log line.

### 5.6 Update limits on a running container

```bash
$ docker update --memory 512m --memory-swap 512m --cpus 1 lim
lim
$ cat $D/memory.max
536870912
```

### 5.7 CPU shares vs hard quota

```bash
$ docker run -d --name a --cpu-shares 1024 alpine sh -c 'while :; do :; done'
$ docker run -d --name b --cpu-shares 256  alpine sh -c 'while :; do :; done'
$ docker stats --no-stream a b
```

Under contention, `a` receives roughly four times the CPU of `b`; on an idle host both may burst to a full core, because shares are relative weights (`cpu.weight` in v2), not limits.

### 5.8 Hand-made cgroup (v2)

```bash
$ sudo mkdir /sys/fs/cgroup/demo
$ echo "+memory +cpu" | sudo tee /sys/fs/cgroup/cgroup.subtree_control
$ echo 100M | sudo tee /sys/fs/cgroup/demo/memory.max
$ echo $$ | sudo tee /sys/fs/cgroup/demo/cgroup.procs
$ cat /proc/$$/cgroup
0::/demo
```

That is essentially what runc does for every container. Remove with `rmdir` after moving processes out.

## 6. Production Usage Notes

- **Always set memory limits** on shared hosts, and set the request/limit relationship deliberately in Kubernetes.
- **Prefer `memory.high` style soft limits (v2)** through orchestrators that expose it, to throttle instead of kill; plain Docker exposes `--memory-reservation` as a soft limit.
- **CPU limits vs shares:** hard quotas can throttle bursty, latency-sensitive services; many teams use requests (shares/weight) and omit hard limits for those workloads.
- **Cgroup driver alignment:** use the `systemd` driver on systemd hosts, and keep Docker, containerd, and the kubelet on the same driver.
- **Java and other runtimes** should be container-aware (modern JVMs read cgroup limits) to size heaps correctly.
- **Monitoring:** scrape `memory.events` (v2) for `oom_kill` counters and `cpu.stat` for throttling; cAdvisor exposes both.

## 7. Security Considerations

- **`--pids-limit`** prevents fork bombs from exhausting the host PID table.
- **Missing limits are a denial-of-service vector:** one compromised container can consume all memory or CPU.
- **Device cgroup** (`devices` controller in v1, eBPF in v2) restricts which device nodes a container can access; `--privileged` disables that restriction.
- **Writable cgroup mounts:** mounting `/sys/fs/cgroup` read-write into a container has enabled historical escapes (for example `release_agent` in v1); Docker mounts it read-only by default.
- **Rootless Docker** relies on cgroup v2 delegation via systemd to enforce limits; on v1, limits are unavailable to rootless containers.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `Exited (137)` | OOM kill or `SIGKILL` | Check `OOMKilled` in `docker inspect`; raise limit or fix leak |
| `WARNING: Your kernel does not support swap limit capabilities` | Swap accounting disabled | Enable `swapaccount=1` in kernel cmdline (v1 hosts) |
| `--cpus` ignored/no effect | Host lacks CFS bandwidth support or cpu controller not delegated | Check `cat /sys/fs/cgroup/cgroup.controllers` |
| Latency spikes with low average CPU | CFS throttling | Check `nr_throttled`; raise quota or remove limit |
| Kubelet fails: `cgroup driver mismatch` | Docker/containerd uses `cgroupfs`, kubelet uses `systemd` | Align driver in `daemon.json`/containerd config |
| Files under `/sys/fs/cgroup/memory/` missing | Host is on v2 | Use v2 paths (`memory.max`) |
| Old image tooling breaks on v2 | Tools that read v1 paths (older monitoring agents) | Upgrade tooling or boot with v1 (`systemd.unified_cgroup_hierarchy=0`) |

## 9. Best Practices

- Set `--memory`, `--cpus` (or shares), and `--pids-limit` for every long-running container.
- Set `--memory-swap` equal to `--memory` to disable swap unless it is wanted.
- Use cgroup v2 with the systemd driver on new hosts.
- Alert on OOM events and CPU throttling, not just utilization.
- Test with the same cgroup version in CI and production.

## 10. Common Anti-Patterns / Mistakes

- Running production containers with no memory limit.
- Assuming `--cpu-shares` is a cap.
- Setting a limit below the application's real working set, then treating restarts as an app bug.
- Mixing cgroup drivers between runtime and kubelet.
- Hard-coding v1 paths in scripts and health checks.

## 11. Interview Questions

**🎯 Beginner:** _"What do cgroups do, and how do they differ from namespaces?"_
**Model answer:** Control groups account for and limit resource use of a group of processes: CPU, memory, I/O, and PIDs. Namespaces restrict what a process can see, while cgroups restrict how much it can consume. Docker maps flags such as `--memory=512m`, `--cpus=1.5`, and `--pids-limit=200` onto files in the cgroup filesystem. You can read the live values under `/sys/fs/cgroup/`.
_What the interviewer is probing for:_ The see-versus-use split between namespaces and cgroups.

**🎯 Intermediate:** _"A container is killed with exit code 137 and `OOMKilled: true`. Walk through what happened and how you would confirm and fix it."_
**Model answer:** The container's cgroup reached `memory.max` (v2) or `memory.limit_in_bytes` (v1) and reclaim failed, so the kernel OOM killer sent SIGKILL, giving 137. Confirm with `docker inspect -f '{{.State.OOMKilled}}'`, `memory.events` (the `oom_kill` counter), and `dmesg`. Compare `docker stats` with the limit, and note that page cache counts toward the cgroup. Fix by raising the limit, fixing the leak, or tuning runtime heap settings that assume host memory such as the JVM `-XX:MaxRAMPercentage`.
_What the interviewer is probing for:_ Understanding the OOM path and that runtimes must be cgroup-aware.

**🎯 Senior:** _"How does cgroup v2 differ from v1, and what practical effects does it have on Docker hosts?"_
**Model answer:** v1 has a separate hierarchy per controller, while v2 has a single unified hierarchy where a process belongs to one cgroup and controllers are enabled through `cgroup.subtree_control`. v2 adds `memory.high` for throttling before the hard limit, PSI pressure metrics, better I/O accounting, and safe delegation to unprivileged users, which rootless Docker relies on. Check the mode with `stat -fc %T /sys/fs/cgroup` (`cgroup2fs`). Older tools, monitoring agents, and Java or Node versions that read v1 paths can misreport limits, so the fleet needs a version audit before flipping the kernel default.
_What the interviewer is probing for:_ Concrete migration knowledge rather than a feature list.

**🎯 Architect:** _"Design a resource policy for a multi-tenant Docker host so that one noisy container cannot harm the others."_
**Model answer:** Set mandatory limits per workload: `--memory` with a sensible `--memory-reservation`, `--cpus` or `--cpu-shares` for relative weighting, `--pids-limit` against fork bombs, and I/O weights or `--device-write-bps` for disk. Put tenants under separate parent cgroups through `--cgroup-parent` so quotas aggregate, and use v2 with PSI-based alerting to catch contention before OOM. Set `--oom-score-adj` so critical services die last, and enforce limits by admission policy or Compose defaults rather than trusting authors. The trade-off is throttling and tail latency from tight CPU quotas, so limits should come from measured p99 usage.
_What the interviewer is probing for:_ Systematic capacity and fairness design, including the throttling trade-off.

## 12. Common Misconceptions

- **"`--memory` guarantees memory."** It is a ceiling; `--memory-reservation` is a soft hint.
- **"cgroups isolate the filesystem."** No; that is the mount namespace and rootfs ([§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)).
- **"Swap is off by default."** With only `--memory` set, Docker allows swap up to 2x the memory value when the host supports it.
- **"v2 is just v1 with new file names."** Its unified hierarchy and delegation model differ fundamentally.
- **"`docker stats` memory equals RSS."** It reports usage minus reclaimable page cache, which is not identical to process RSS.

## 13. 🔑 Key Takeaways

- cgroups limit and account for CPU, memory, I/O, and PIDs; namespaces isolate views.
- v2 is a single unified hierarchy and is the modern default.
- Docker flags translate to files such as `memory.max`, `cpu.max`, and `pids.max`.
- Exit 137 with `OOMKilled=true` means the memory cgroup killed the container.
- CPU quotas can throttle; shares are relative weights, not caps.
- Keep the cgroup driver consistent between Docker, containerd, and kubelet.

## 14. Related Concepts & What's Next

Related: [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) (recap), [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (runc applies cgroup settings), [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) (`linux.resources` in the runtime spec), [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md) (namespaces), [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) (containerd and the CRI, where kubelet cgroup drivers matter), [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) (daemon-level cgroup settings). Later Docker topics cover resource constraints in `docker run` and Compose, monitoring with cAdvisor, and rootless mode.

**Next Section:** [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) — `Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md`
