# Section 98 (Part 13): Performance Tuning Recap

## 1. Definition

**Plain language:** Docker performance work falls into five areas: how fast images build, how small and quick to pull they are, how fast containers start, how efficiently they use CPU and memory, and how fast their storage and network paths are. This section is the checklist that ties together tuning advice from earlier parts.

**Precise definition:** Container runtime overhead is small (namespaces and cgroups add negligible CPU cost), so measurable differences come from the layers around the process: build cache behavior, image size and layout, the storage driver and mount type, the network path (bridge NAT, userland proxy, overlay), cgroup limits (CPU throttling, memory pressure, PID and I/O limits), and the application itself. Tuning means measuring first (`docker stats`, `docker system df`, `time`, build timings, `perf`, cAdvisor), changing one variable, and measuring again.

> 💡 **Tip:** Never tune without a baseline. A change that "feels faster" on a laptop often disappears on a production host with different storage and cgroup settings.

## 2. Why This Matters

- Slow builds multiply across every developer and every CI run; a 10-minute build executed 200 times a week is 33 hours of waiting.
- Large images slow deployments, autoscaling reaction time and incident recovery (pull time dominates cold starts).
- Misconfigured CPU limits throttle latency-sensitive services even at low average load.
- Storage and networking choices (bind mounts on Desktop, NAT with userland proxy) are common hidden causes of "Docker is slow".
- Interviewers often ask "the container is slow, what do you check?" to test a structured method.

## 3. Prerequisites and Dependencies

Builds and cache: [§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md), [§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md), [§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md), [§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md), [§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md). Resources and cgroups: [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md), [§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md), [§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md). Storage and network: [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md), [§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md), [§47](../Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md). Monitoring: [§87](../Part12/Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md).

## 4. Architecture / Conceptual Diagram

```text
   Where time goes, from code to a serving container

   BUILD                 DISTRIBUTE               START                 RUN
 ┌────────────┐        ┌─────────────┐        ┌─────────────┐     ┌────────────────────┐
 │ context    │        │ push/pull   │        │ unpack layers│    │ CPU  ◄─ cgroup cpu │
 │ transfer   │──────► │ layer count │──────► │ snapshotter  │──► │ MEM  ◄─ memory.max │
 │ cache hits │        │ image size  │        │ create ns/   │    │ IO   ◄─ storage    │
 │ parallel   │        │ registry    │        │ cgroups, net │    │ NET  ◄─ NAT/proxy  │
 │ stages     │        │ proximity   │        │ app init/JIT │    │ PIDs ◄─ pids.max   │
 └────────────┘        └─────────────┘        └─────────────┘     └────────────────────┘
   .dockerignore         multi-stage, slim,      lazy pull, warm      right-size limits,
   ordering, mounts      zstd, regional mirror   nodes, small init    volumes, host nets

   Measure ► change one thing ► re-measure
   ┌────────────────┬──────────────────────────────────────────────┐
   │ Symptom        │ First tool                                   │
   ├────────────────┼──────────────────────────────────────────────┤
   │ slow build     │ docker build --progress=plain, buildx --timings│
   │ slow pull      │ docker pull timing, docker history, dive     │
   │ slow start     │ docker events + app logs, strace -f -tt      │
   │ high latency   │ docker stats, cpu.stat (nr_throttled)        │
   │ OOM kills      │ docker inspect .State.OOMKilled, memory.events│
   │ slow disk      │ fio on volume vs overlay, iostat             │
   │ slow network   │ iperf3, ss -s, conntrack -S                  │
   └────────────────┴──────────────────────────────────────────────┘
```

- **Build time** is dominated by cache misses and context size, not CPU.
- **Pull time** scales with compressed size and layer parallelism.
- **Run-time overhead** is almost always limits, storage path or network path rather than the container abstraction itself.

## 5. Hands-On

### 5.1 Build: Order Layers by Change Frequency and Use Cache Mounts

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "app"]
```

```bash
time docker build -t perf-demo .                       # cold
echo "# change" >> app/main.py
time docker build -t perf-demo .                       # dependencies layer is cached
docker build --progress=plain --no-cache-filter=base -t perf-demo . 2>&1 | grep -E "DONE|CACHED"
```

```text
real  0m41.2s
real  0m1.9s
#6 CACHED
#7 DONE 0.4s
```

Dependency manifests are copied first so source edits do not invalidate the install layer. The cache mount keeps downloaded wheels across builds even when the layer is rebuilt ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md), [§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)).

### 5.2 Build: Shrink the Context

```bash
cat > .dockerignore <<'EOF'
.git
node_modules
**/__pycache__
*.log
dist
EOF
docker build --progress=plain -t perf-demo . 2>&1 | grep "transferring context"
```

```text
#2 transferring context: 4.12kB 0.0s
```

A multi-hundred-megabyte context sent to the builder on every build is a frequent hidden cost, especially with remote builders ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).

### 5.3 Image Size: Multi-Stage and Slim Bases

```bash
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | grep -E 'perf|python'
docker history perf-demo --no-trunc=false --format '{{.Size}}\t{{.CreatedBy}}' | head -5
```

```text
python        3.12        1.02GB
python        3.12-slim   131MB
perf-demo     latest      168MB
```

Smaller images pull and start faster, and expose fewer packages to scan. Use multi-stage builds so compilers stay out of the runtime image ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md), [§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)). Compare with `dive` ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)).

### 5.4 Start-Up: Measure Where the Time Goes

```bash
time docker run --rm perf-demo true                   # runtime overhead (create + start + stop)
docker run -d --name slow perf-demo
docker events --since 1m --filter container=slow --format '{{.Time}} {{.Action}}'
docker logs -t slow | head -5                          # time to first app log line
```

```text
real  0m0.38s
1760000001 create
1760000001 start
2026-10-06T10:00:03Z app: loading models...
```

Container creation costs a few hundred milliseconds. If start-up takes seconds, the cost is almost always inside the application (JIT warmup, schema migration, large initialization), so fix it in the app or with readiness probes rather than the runtime.

### 5.5 CPU: Detect Throttling, Not Just Usage

```bash
docker run -d --name api --cpus 0.5 perf-demo
CID=$(docker inspect -f '{{.Id}}' api)
cat /sys/fs/cgroup/system.slice/docker-$CID.scope/cpu.stat
docker stats --no-stream api
```

```text
usage_usec 8123456
nr_periods 4200
nr_throttled 3100
throttled_usec 91000000
CONTAINER ID  NAME  CPU %  MEM USAGE / LIMIT
```

A high `nr_throttled` relative to `nr_periods` means the quota is clipping bursts, which shows up as latency spikes. Options: raise `--cpus`, use `--cpu-shares` for relative weighting instead of a hard cap, or pin with `--cpuset-cpus` for predictable workloads ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)).

### 5.6 Memory: Limits, Swap and OOM

```bash
docker run -d --name worker --memory 512m --memory-swap 512m perf-demo
docker inspect worker --format 'OOMKilled={{.State.OOMKilled}} exit={{.State.ExitCode}}'
cat /sys/fs/cgroup/system.slice/docker-$(docker inspect -f '{{.Id}}' worker).scope/memory.events
```

```text
OOMKilled=true exit=137
low 0
high 0
max 12
oom 1
oom_kill 1
```

Set limits above the application's real working set (including page cache pressure and runtime overhead). Runtimes such as the JVM and Node need explicit heap flags; modern JVMs are container-aware (`-XX:MaxRAMPercentage`), but older settings and some native allocators are not. Setting `--memory-swap` equal to `--memory` disables swap and avoids silent thrashing.

### 5.7 Storage: Pick the Right Mount for Write-Heavy Paths

```bash
docker volume create fastvol
docker run --rm -v fastvol:/vol alpine sh -c 'time dd if=/dev/zero of=/vol/f bs=1M count=512 oflag=dsync'
docker run --rm alpine sh -c 'time dd if=/dev/zero of=/f bs=1M count=512 oflag=dsync'
docker run --rm --tmpfs /scratch:rw,size=1g alpine sh -c 'time dd if=/dev/zero of=/scratch/f bs=1M count=512'
```

```text
512 MB copied, 1.9 s      # named volume (host filesystem speed)
512 MB copied, 3.4 s      # overlay2 copy-up and layering overhead
512 MB copied, 0.3 s      # tmpfs (RAM)
```

Databases, caches and build artifacts should live on volumes or tmpfs, not the container's writable layer, which adds copy-on-write overhead and disappears on removal ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md), [§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md)).

### 5.8 Network: Compare Paths

```bash
docker run -d --name srv --network bridge -p 5201:5201 networkstatic/iperf3 -s
docker run --rm --network host networkstatic/iperf3 -c 127.0.0.1 -t 5          # via published port
docker rm -f srv
docker run -d --name srv2 --network host networkstatic/iperf3 -s
docker run --rm --network host networkstatic/iperf3 -c 127.0.0.1 -t 5          # host networking
docker rm -f srv2
```

```text
[SUM] 0.00-5.00 sec  9.82 Gbits/sec   # bridge + NAT
[SUM] 0.00-5.00 sec  38.4 Gbits/sec   # host network
```

Bridge networking with NAT and the userland proxy costs throughput and adds connection-tracking pressure at high connection rates. Host networking removes that at the price of isolation and port clashes; use it selectively for latency-critical proxies. Check `conntrack -S` and tune `nf_conntrack_max` before reaching for exotic options ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).

### 5.9 Daemon and Disk Housekeeping

```bash
docker system df
docker builder prune --filter until=168h -f      # test on a throwaway host first
```

```json
{
  "log-driver": "local",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "max-concurrent-downloads": 6,
  "max-concurrent-uploads": 6,
  "live-restore": true
}
```

Unbounded `json-file` logs, dangling images and build cache fill disks and degrade I/O. The `local` log driver is more efficient than `json-file`, and rotation is mandatory ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md), [§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md), [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

## 6. Production Usage Notes

- **CI:** use registry or `type=gha`/`type=s3` buildx cache backends, `--cache-from`/`--cache-to mode=max`, and persistent BuildKit builders ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md), [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)).
- **Registry proximity:** pull through a regional mirror or pull-through cache; avoid Docker Hub rate limits and cross-region latency ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)).
- **Node warmup:** pre-pull base images onto autoscaled nodes (baked AMIs, DaemonSet prepullers) to cut cold-start times.
- **Layer design for pulls:** put rarely-changing layers first so nodes reuse them; fewer, well-ordered layers beat many tiny ones, but do not squash away cache reuse.
- **Limits policy:** set memory limits for every service; prefer CPU requests/shares over hard CPU limits for latency-sensitive services where throttling is a risk (a debated trade-off in Kubernetes as well).
- **Init and signals:** a proper PID 1 (tini, `--init`) improves shutdown time, which matters for rolling updates ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md), [§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).
- **Docker Desktop:** raise VM CPU/memory allotment, use virtiofs, store hot data in volumes rather than bind mounts, and keep source inside the Linux VM when possible ([§41](../Part5/Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md)).
- **Observe continuously:** cAdvisor plus Prometheus with throttling, OOM and I/O wait panels catches regressions before users do ([§87](../Part12/Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)).

## 7. Security Considerations

- Performance changes should not weaken isolation: `--net=host`, `--privileged`, `--pid=host`, disabling seccomp or mounting the Docker socket "for speed" trade security for marginal gains ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§60](../Part8/Section-60-Part8-Seccomp-Profiles.md)).
- Resource limits are also a security control: memory, CPU and `--pids-limit` stop fork bombs and noisy-neighbor denial of service.
- Shared build caches can leak secrets or be poisoned; scope cache keys per repository and branch, and never put secrets in cached layers ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- Pull-through caches and mirrors must verify digests and be access controlled, or they become supply-chain pivots ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- Reducing image size through stripping and minimal bases also reduces attack surface; scan after optimization ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- `tmpfs` mounts keep sensitive scratch data off disk, but it counts against container memory.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Every build reinstalls dependencies | `COPY . .` before dependency install, or volatile `ARG`/timestamp earlier in file | Copy manifests first, reorder, pin volatile values late |
| Build context transfer takes minutes | Missing `.dockerignore`, huge `node_modules` or `.git` | Add `.dockerignore`, use build contexts from Git URL or smaller subdirectory |
| Latency spikes at low CPU usage | CFS quota throttling | Check `nr_throttled`, raise or remove `--cpus`, use shares |
| Container killed with exit 137 | OOM kill (`OOMKilled=true`) | Raise memory, fix leak, tune runtime heap flags |
| Slow file I/O on Mac/Windows | Bind mounts via file sharing | Use named volumes or in-VM source, enable virtiofs |
| Slow start of many containers | Image pull, low `max-concurrent-downloads`, registry throttling | Pre-pull, mirror, raise concurrency, smaller images |
| Disk full, daemon sluggish | Logs, dangling images, build cache | `docker system df`, rotate logs, schedule prune |
| High connection failures under load | conntrack table full or ephemeral port exhaustion | Tune `nf_conntrack_max`, `ip_local_port_range`, reuse connections, host networking for proxies |
| Slow DNS in containers | Search domains, `ndots`, resolver latency | Use FQDNs, tune `dns` options, local cache |

## 9. Best Practices

- Establish baselines for build time, image size, start time, p99 latency and throttling before tuning.
- Change one variable at a time and keep the result in the pull request.
- Order Dockerfile instructions from least to most frequently changed; use BuildKit cache and bind mounts.
- Use multi-stage builds and slim or distroless bases; remove build tools and caches from the final stage.
- Keep a strict `.dockerignore`.
- Put hot data on volumes or tmpfs; avoid the writable layer for anything write-heavy.
- Right-size memory limits with headroom and monitor OOM events; use CPU shares or generous limits for latency-sensitive services.
- Rotate logs and schedule cleanup; monitor `docker system df`.
- Use registry-backed build caches and regional mirrors in CI and production.
- Re-run benchmarks after upgrading Docker, kernel, storage driver or base image.

## 10. Common Anti-Patterns / Mistakes

- Optimizing image size at the expense of debuggability and cache reuse without measuring pull time gains.
- Setting low CPU limits "to be safe" on latency-sensitive services, then chasing phantom latency.
- No memory limit, so one leaking container takes down the host.
- `RUN apt-get update` and install in separate layers, or one giant layer that invalidates all the time.
- Benchmarking on Docker Desktop bind mounts and blaming Docker for the result.
- Disabling security features for speed without profiling first.
- Using `docker system prune -a` in production hosts as a performance fix, forcing slow re-pulls.
- Never rotating logs, leading to multi-gigabyte `json-file` logs.
- Running everything with `--net=host` to avoid learning NAT behavior.

## 11. Interview Questions

**🎯 Beginner:** _"Your Docker image builds take 10 minutes even for a one-line code change. What do you look at first?"_
**Model answer:** Layer ordering and the build context. If `COPY . .` comes before the dependency install, any source change invalidates the install layer, so I would copy only `package.json` or `requirements.txt` first, install dependencies, then copy the source. I would check that `.dockerignore` excludes `.git`, `node_modules` and build outputs so the context is small, and use `docker build --progress=plain` to see which steps are not `CACHED`. BuildKit cache mounts (`RUN --mount=type=cache`) for package managers speed up the steps that do re-run.
_What the interviewer is probing for:_ Understanding cache invalidation and a methodical, evidence-based approach.

**🎯 Intermediate:** _"A service shows 20% average CPU but occasional latency spikes. It runs with `--cpus 1`. What is happening and how do you confirm?"_
**Model answer:** CFS bandwidth throttling. A limit of 1 CPU grants 100ms of CPU time per 100ms period across all threads; a multi-threaded service can burn that quota in a burst and be paused for the rest of the period, even though the average is low. I confirm by reading `cpu.stat` in the container's cgroup (`nr_throttled`, `throttled_usec`) or through cAdvisor's `container_cpu_cfs_throttled_periods_total`. Fixes include raising or removing the hard limit and relying on `--cpu-shares` for fairness, reducing thread-pool size to the quota, or pinning cores with `--cpuset-cpus`. I would validate with load tests and watch p99 latency afterward.
_What the interviewer is probing for:_ Knowing cgroup CPU quota mechanics and how to measure throttling instead of looking at average utilization.

**🎯 Senior:** _"Pipeline builds are slow and flaky: 25-minute builds, Docker Hub rate-limit errors, and nodes that take minutes to start new pods. Propose a plan."_
**Model answer:** Treat as three separate problems. Build speed: enable BuildKit everywhere, restructure Dockerfiles for caching, parallelize independent stages, and push/pull a shared registry cache (`--cache-to type=registry,mode=max`) because CI runners are ephemeral. Rate limits: authenticate pulls and introduce a pull-through cache or internal mirror, and pin base images by digest to avoid surprise rebuilds. Start-up latency: shrink images with multi-stage and slim bases, pre-pull images on nodes via AMI baking or a prepuller, use regional registries, and consider lazy-pull snapshotters (stargz/SOCI) if images are large. Measure each stage (build time, pull time, time-to-ready) before and after, and set budgets in CI so regressions fail the build.
_What the interviewer is probing for:_ Decomposition into build, distribution and start-up, and use of cache backends and mirrors.

**🎯 Architect:** _"You're asked to cut infrastructure cost 30% for a fleet of containerized services without degrading latency. What do you analyze and change?"_
**Model answer:** Start with data: per-service CPU and memory usage versus requests/limits, throttling and OOM rates, p99 latency, image sizes and pull frequency, and node utilization. Typical wins are right-sizing over-provisioned memory and CPU requests (using percentiles, not peaks), removing hard CPU limits where throttling hurts, bin-packing on fewer or cheaper nodes (including ARM instances, with multi-arch images), and autoscaling on the right signal. Reduce waste in the delivery path: smaller images, regional caches to cut egress and registry bills, retention policies, and shorter-lived CI caches. For performance-critical services keep headroom and test with load before rollout; for batch workloads consider spot capacity. Put guardrails in place (SLO dashboards, canary rollouts, rollback plans) so savings are reversible, and re-evaluate quarterly.
_What the interviewer is probing for:_ Connecting container tuning to cost, with data-driven right-sizing and risk controls.

## 12. Common Misconceptions

- "Containers add significant CPU overhead." Isolation itself is near-free; the cost sits in storage, network and limits.
- "More layers always means slower." Layer count matters less than size, ordering and cache reuse; extreme counts do add some overhead.
- "`--cpus` guarantees CPU." It caps CPU; `--cpu-shares` gives relative priority, and neither reserves cores.
- "`docker system prune -a` speeds things up." It frees disk but forces re-pulls and rebuilds.
- "Alpine is always faster." musl can slow some workloads (DNS, allocators, glibc-specific binaries), and slim Debian is often a better trade.
- "Host networking is a free speedup." It trades isolation and port management for throughput.

## 13. 🔑 Key Takeaways

- Measure first: baseline, change one thing, re-measure.
- Build speed comes from layer order, small context, BuildKit cache mounts and shared CI caches.
- Distribution speed comes from small images, mirrors and pre-pulled bases.
- Run speed depends on right-sized limits (watch CPU throttling and OOM), volumes or tmpfs for hot paths, and the network path.
- Rotate logs and prune on a schedule to keep the host healthy.
- Never trade away isolation for speed without evidence and a reviewed exception.

## 14. Related Concepts & What's Next

Related: Dockerfile checklist ([§94](Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)), anti-patterns ([§95](Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)), caching ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), size minimization ([§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)), resource management at scale ([§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)), and production troubleshooting ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)). Next, [§99](Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md) covers the path from single-host Docker to orchestration.

**Next Section:** [§99](Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md) — `Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md`
