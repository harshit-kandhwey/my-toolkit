# Section 56 (Part 7): Storage Performance Considerations

## 1. Definition

**Plain language:** Where a container writes its data decides how fast it runs. Writing into the container's own layer goes through a union filesystem and is slow for heavy I/O. Writing to a volume goes almost straight to the host filesystem and is fast. Bind mounts on Docker Desktop cross a virtualization boundary and can be very slow.

**Precise definition:** Storage performance in Docker is the throughput, IOPS and latency a containerized workload sees on each of its storage paths: the writable layer (overlay2 copy-on-write, [§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md)), named volumes and bind mounts ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), `tmpfs` mounts (RAM-backed), and remote volume drivers such as NFS ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)). It is shaped by the storage driver, the backing filesystem and disk (`/var/lib/docker`), page-cache behavior, cgroup I/O controllers ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), and on Docker Desktop the file-sharing layer between host and VM.

> 💡 **Tip:** The rule of thumb is simple: anything written often belongs on a volume or tmpfs, never in the writable layer.

## 2. Why This Matters

- Databases, queues and build caches placed in the writable layer can run several times slower and suffer latency spikes on first write to a lower-layer file (copy-up).
- Bind-mounted source trees on macOS and Windows are a top cause of "Docker is slow" complaints in local development.
- One noisy container can saturate a shared disk and starve its neighbors unless I/O is limited.
- Image pulls, builds and `docker system prune` are I/O-bound; slow disks lengthen CI times and deployments.
- Choosing the wrong data path is cheap to fix early and expensive to fix after data has accumulated.

## 3. Prerequisites and Dependencies

Requires overlay2 internals ([§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md), [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), the volume/bind/tmpfs distinction ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), and named-volume management ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)). I/O throttling uses cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)); the broader resource-constraint flags are in [§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md). Persistence patterns for databases are in [§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md).

## 4. Architecture / Conceptual Diagram

```text
 Container process: write(2)
        │
        ├─► Path A: file in image / writable layer (not a mount)
        │      overlayfs ──► copy-up on first modify of a lower-layer file
        │         │             (whole file copied to upperdir, then written)
        │         ▼
        │      /var/lib/docker/overlay2/<id>/diff   (host filesystem: ext4/xfs)
        │
        ├─► Path B: named volume
        │      bind of /var/lib/docker/volumes/<name>/_data   (no overlay, no copy-up)
        │         ▼
        │      host filesystem ── near-native speed
        │
        ├─► Path C: bind mount of host dir
        │      Linux host: near-native
        │      Docker Desktop: host FS ◄──► file-sharing layer ◄──► VM ◄──► container
        │                       (VirtioFS / gRPC FUSE / 9p: per-op round trips)
        │
        ├─► Path D: tmpfs
        │      page cache / RAM only, lost on stop, bounded by --tmpfs size
        │
        └─► Path E: volume driver (NFS, cloud block)
               network round trips: latency = network RTT + remote disk

  Relative speed for write-heavy, small-file workloads (typical):
   tmpfs  >  named volume ≈ Linux bind  >  writable layer  >  Desktop bind  ≈  NFS (varies)
```

- **Copy-up** is the main hidden cost of the writable layer: modifying a 1 GB lower-layer file copies all 1 GB first.
- **Page cache** is shared with the host kernel, so reads of recently used data are fast on every local path.
- **Journaling and sync behavior** of the backing filesystem (ext4 vs xfs, `fsync` cost) apply to paths A, B and C alike.

## 5. Hands-On

### 5.1 Compare Writable Layer vs Volume vs tmpfs

```bash
docker volume create perfvol

# Writable layer
docker run --rm alpine:3.20 sh -c 'time dd if=/dev/zero of=/layer.bin bs=1M count=512 conv=fsync'

# Named volume
docker run --rm -v perfvol:/data alpine:3.20 sh -c 'time dd if=/dev/zero of=/data/vol.bin bs=1M count=512 conv=fsync'

# tmpfs (needs enough RAM)
docker run --rm --tmpfs /mnt/ram:rw,size=1g alpine:3.20 sh -c 'time dd if=/dev/zero of=/mnt/ram/t.bin bs=1M count=512 conv=fsync'
```

```text
536870912 bytes (512.0MB) copied, 1.9 seconds, 270 MB/s     # writable layer
536870912 bytes (512.0MB) copied, 1.7 seconds, 300 MB/s     # volume
536870912 bytes (512.0MB) copied, 0.2 seconds, 2.5 GB/s     # tmpfs
```

Sequential throughput on a fresh overlay2 layer is often close to a volume. The gap appears with many small files, `fsync`-heavy databases and copy-up, which `dd` does not show. Numbers above are illustrative; measure on your own hardware.

### 5.2 Measure Small-File and Random I/O with fio

```bash
docker run --rm -v perfvol:/data alpine:3.20 sh -c '
  apk add --no-cache fio >/dev/null &&
  fio --name=randwrite --directory=/data --rw=randwrite --bs=4k --size=256m \
      --ioengine=libaio --iodepth=16 --direct=1 --runtime=20 --time_based --group_reporting'
```

```text
randwrite: (groupid=0, jobs=1): err= 0: pid=18
  write: IOPS=41.2k, BW=161MiB/s (169MB/s)
  clat (usec): min=60, avg=380, 99.00th=[ 1100 ]
```

Repeat with `--directory=/` (writable layer) and compare IOPS and p99 latency. `--direct=1` bypasses the page cache and tests the disk rather than RAM; some filesystems (and tmpfs) reject it.

### 5.3 Observe Copy-Up Cost

```bash
docker run --rm alpine:3.20 sh -c '
  time cat /bin/busybox >/dev/null          # read: no copy
  time sh -c "echo x >> /bin/busybox"       # append: copies the whole lower-layer file first'
```

For a small file the delay is invisible. For a multi-gigabyte file baked into an image layer, the first write stalls while the file is copied into the upper layer. Fix by mounting a volume over the data path or by not modifying large files from the image.

### 5.4 Throttle Container I/O

```bash
# Cap a container to 10 MB/s write and 500 write IOPS against a specific device
docker run --rm \
  --device-write-bps /dev/nvme0n1:10mb \
  --device-write-iops /dev/nvme0n1:500 \
  -v perfvol:/data alpine:3.20 \
  sh -c 'dd if=/dev/zero of=/data/limited.bin bs=1M count=200 oflag=direct'
```

```text
209715200 bytes (200.0MB) copied, 20.0 seconds, 10.0MB/s
```

These flags (`--device-read-bps`, `--device-write-bps`, `--device-read-iops`, `--device-write-iops`) use the cgroup v2 `io.max` controller and apply to a block device, so they cannot throttle tmpfs, NFS or most network filesystems. On cgroup v2, buffered writes are throttled correctly; on cgroup v1 only direct I/O was.

### 5.5 Bind-Mount Speed on Docker Desktop

```bash
# Slow on Desktop: thousands of small files over the file-sharing layer
docker run --rm -v "$PWD":/src -w /src node:22 sh -c 'time npm ci'

# Faster: keep node_modules in a named volume (stays inside the VM), mount only source
docker run --rm -v "$PWD":/src -v nm:/src/node_modules -w /src node:22 sh -c 'time npm ci'
```

```text
real  2m41s     # node_modules over bind mount
real  0m38s     # node_modules in a named volume
```

Ratios vary by backend (VirtioFS on current Docker Desktop is much faster than older gRPC FUSE), but the pattern holds: keep dependency trees, caches and build output off the shared mount. Consistency options such as `:cached` and `:delegated` are largely no-ops on current Docker Desktop.

### 5.6 Inspect Storage Driver and Disk Usage

```bash
docker info --format 'driver={{.Driver}} root={{.DockerRootDir}}'
docker system df
docker system df -v | head -20
df -hT /var/lib/docker
```

```text
driver=overlay2 root=/var/lib/docker
TYPE            TOTAL   ACTIVE   SIZE      RECLAIMABLE
Images          14      5        4.1GB     2.6GB (63%)
Containers      6       3        312MB     120MB (38%)
Local Volumes   9       4        7.8GB     3.1GB (39%)
Build Cache     88      0        2.2GB     2.2GB
Filesystem  Type  Size  Used  Avail  Use%  Mounted on
/dev/nvme0n1p3 xfs  500G  210G  290G   42%   /var
```

overlay2 requires a backing filesystem with `d_type` support: ext4, or xfs created with `ftype=1`. Docker warns at startup otherwise.

## 6. Production Usage Notes

- **Put `/var/lib/docker` on its own fast disk** (NVMe or provisioned-IOPS cloud volume) so image pulls and container writes do not compete with the OS.
- **Use xfs or ext4** for the data root; xfs with `pquota` enables per-container disk quotas via `--storage-opt size=` on overlay2.
- **Databases:** mount a volume at the data directory, use the filesystem and options the database vendor recommends, and avoid NFS for databases that need strict `fsync` semantics ([§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)).
- **Scratch and temp data:** use `--tmpfs` with a size limit for session files, caches and sockets; it also supports read-only root filesystems ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Logging:** the default `json-file` driver writes to the host disk; set `max-size` and `max-file` rotation ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)) so logs do not fill the disk and degrade everything.
- **Layer count and size:** fewer, smaller layers speed pulls and extraction; see [§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md).
- **Monitor** disk latency and saturation (`iostat -x`, `node_exporter` disk metrics, cAdvisor `container_fs_*` metrics, [§87](../Part12/Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)) rather than only free space.
- **Cloud volumes:** EBS gp3 and similar let you provision IOPS and throughput independently of size; size to the workload, not just the capacity.

## 7. Security Considerations

- **Disk exhaustion is a denial of service.** A container writing endlessly to its writable layer or to a volume can fill the host disk. Use `--storage-opt size=` (xfs + pquota), volume size limits via driver options, log rotation, and monitoring.
- **Unbounded tmpfs consumes RAM.** Always set `size=`; without it the default is half of host RAM, and it counts toward the container's memory cgroup ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)).
- **I/O limits are a noisy-neighbor control**, but they are per block device and do not replace quotas.
- **Performance shortcuts weaken guarantees.** `--mount type=bind` with relaxed sync or disabling `fsync` in a database to "go faster" trades durability for speed.
- **Bind mounts expose host paths;** speeding up local dev by mounting broad host directories widens the blast radius ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)).
- **Benchmark containers** run `fio` or `dd` as root against real devices if given `--device`; run them in throwaway environments only.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Database slow, high latency in a container | Data directory in the writable layer, or on NFS | Mount a local named volume at the data dir |
| First write to a file in an image stalls | overlay2 copy-up of a large lower-layer file | Avoid modifying big image files; mount a volume |
| `npm install` or tests very slow on Mac/Windows | Bind mount crosses the VM file-sharing layer | Named volume for `node_modules`/caches; enable VirtioFS; use WSL2 filesystem on Windows |
| Host disk full, containers failing | Unrotated `json-file` logs, dangling images, build cache | Log rotation, `docker system df`, prune ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)) |
| `--device-write-bps` has no effect | Target is tmpfs/NFS/overlay path, wrong device, or cgroup v1 buffered writes | Apply to the real block device; use cgroup v2 |
| Daemon warns about `d_type` or overlay2 unsupported | xfs created with `ftype=0` | Recreate filesystem with `ftype=1` |
| Container OOM-killed while writing to tmpfs | tmpfs counts against memory limit | Raise limit or shrink tmpfs `size=` |
| Image pulls slow despite fast network | Slow disk during layer extraction; many concurrent pulls | Faster disk; reduce `max-concurrent-downloads`; smaller images |
| Intermittent stalls under load | Disk saturation by a neighbor container | Per-container I/O limits; separate volumes/disks |

## 9. Best Practices

- Never write high-churn data into the writable layer; use volumes or tmpfs.
- Benchmark with the real workload pattern (`fio` with matching block size, queue depth and sync mode), not only `dd`.
- On Docker Desktop, keep dependency directories and build caches in named volumes and mount only source code; prefer VirtioFS.
- Give `/var/lib/docker` dedicated, monitored, fast storage with `d_type` support.
- Rotate logs and prune on a schedule.
- Set explicit `size=` on tmpfs mounts and consider per-container disk quotas.
- Throttle I/O for batch jobs sharing hosts with latency-sensitive services.
- Prefer local disk for databases; reserve NFS for shared, read-mostly or tolerant data.
- Record baseline numbers so regressions after upgrades or migrations are measurable.

## 10. Common Anti-Patterns / Mistakes

- Running a production database with no volume, so data lives in the writable layer.
- Bind-mounting an entire monorepo, including `node_modules`, into a Desktop container and blaming Docker for slowness.
- Using `dd` once and concluding that overlay2 and volumes are equivalent.
- Putting the Docker data root on the OS disk of a small cloud instance.
- Leaving default `json-file` logging unbounded.
- Using NFS volumes for SQLite or write-ahead-log databases.
- Setting a huge tmpfs without a memory limit.
- Switching storage drivers (`devicemapper`, `vfs`) for imagined speed; `overlay2` is the supported default and `vfs` is far slower.
- Tuning with `--storage-opt` options on a backing filesystem that does not support them.

## 11. Interview Questions

**🎯 Beginner:** _"Why is it recommended to put database files on a volume instead of in the container filesystem?"_
**Model answer:** The container filesystem is a union of read-only image layers and a thin writable layer. Writes there go through overlay2 copy-on-write, which adds overhead (and copy-up when modifying lower-layer files), and the data disappears when the container is removed. A volume is a plain host directory bind-mounted into the container: it bypasses the union filesystem for near-native speed and has a lifecycle independent of the container, so data survives replacement and upgrades.
_What the interviewer is probing for:_ Understanding both the performance and the persistence argument for volumes.

**🎯 Intermediate:** _"Developers on macOS report that `docker compose up` with a bind-mounted source tree is slow. What is happening and what do you change?"_
**Model answer:** On Docker Desktop the containers run in a Linux VM, so a bind mount from the host passes through a file-sharing layer (VirtioFS, or older gRPC FUSE) with a round trip per file operation. Workloads touching thousands of small files, such as `npm install`, test runners and compilers, suffer. Keep the host mount for source only and place `node_modules`, package caches and build output in named volumes inside the VM; switch to VirtioFS; exclude heavy directories with `.dockerignore` and watcher ignore lists; use Compose `develop.watch` sync instead of mounting where it fits. On Windows, keep the project inside the WSL2 filesystem rather than `/mnt/c`.
_What the interviewer is probing for:_ Knowing the cause is the virtualization boundary, with concrete, cheap mitigations.

**🎯 Senior:** _"A latency-sensitive service shares a host with a batch job. The batch job periodically causes p99 spikes. How do you diagnose and contain it?"_
**Model answer:** Check device saturation with `iostat -x` (await, %util) and per-container I/O via cAdvisor or `docker stats` block I/O, and confirm with cgroup `io.stat`. If the batch job is the source, constrain it with `--device-read-bps`/`--device-write-bps` and IOPS limits against the real block device (cgroup v2 `io.max`, which also covers buffered writes), or schedule it elsewhere. Better still, separate data paths: dedicated volumes or disks, and `io.weight` (`--blkio-weight` on v1) for proportional sharing. Confirm the throttle applies to the right device and that neither workload is writing into the overlay layer or logging to the same disk. Then add alerts on disk latency, not just free space.
_What the interviewer is probing for:_ Systematic diagnosis with real metrics and knowledge of how the I/O controller works and its limits.

**🎯 Architect:** _"Design the storage layout for a fleet of Docker hosts running mixed stateless services and a few stateful databases, with predictable performance and bounded failure impact."_
**Model answer:** Separate concerns by device: a small OS disk; a dedicated data-root disk for `/var/lib/docker` (xfs `ftype=1`, pquota for per-container quotas); and dedicated provisioned-IOPS volumes mounted for each database's data via named volumes or bind mounts to those paths. Stateless services run with read-only root filesystems plus small sized tmpfs mounts, so their writable-layer I/O is near zero. Enforce log rotation fleet-wide in `daemon.json`, schedule prune jobs, cap I/O on batch classes, and alert on disk latency, inode use and saturation. For databases on orchestrated clusters, prefer local or block storage with replication at the application layer over network filesystems, and document restore tests ([§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)). Validate with fio profiles that mimic production and keep them in CI for host image changes.
_What the interviewer is probing for:_ Layered, quota-aware design that ties performance, failure isolation and operations together.

## 12. Common Misconceptions

- "Volumes are always faster than the writable layer." For large sequential writes the difference can be small; it shows up with small files, fsync-heavy loads and copy-up.
- "tmpfs is free." It uses RAM that counts toward the container's memory limit.
- "`:cached` and `:delegated` speed up bind mounts." They are mostly ignored on current Docker Desktop.
- "I/O limits work on any mount." They apply to block devices, not tmpfs or network filesystems.
- "Docker adds a big overhead to everything." CPU and network are near native; storage overhead comes from the layer or mount path you pick.
- "A fast network drive is as good as local disk for a database." Latency and fsync semantics usually say otherwise.

## 13. 🔑 Key Takeaways

- Choose the data path deliberately: tmpfs for scratch, volumes for persistent hot data, never the writable layer for heavy writes.
- overlay2 copy-up makes the first modification of large image files expensive.
- On Docker Desktop, bind mounts cost a file-sharing round trip per operation; keep dependencies in named volumes.
- `--device-*-bps/iops` throttle real block devices through cgroup v2 `io.max`.
- Back `/var/lib/docker` with fast, monitored storage that supports `d_type`; rotate logs and prune.
- Benchmark with realistic `fio` profiles and monitor latency, not only capacity.

## 14. Related Concepts & What's Next

Related: overlay2 internals ([§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md), [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), mount types ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), volume drivers ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)), resource limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), performance recap ([§98](../Part13/Section-98-Part13-Performance-Tuning-Recap.md)). This closes Part 7. Next, Part 8 starts with [§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md), which examines what container isolation does and does not protect.

**Next Section:** [§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md) — `Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md`
