# Section 51 (Part 7): Volumes vs. Bind Mounts vs. tmpfs: When Each Applies

## 1. Definition

**Plain language:** Docker offers three ways to give a container storage that is not the throwaway writable layer. A **volume** is storage Docker creates and manages for you. A **bind mount** is a specific file or directory from the host mapped into the container. A **tmpfs mount** is memory-backed scratch space that disappears when the container stops.

**Precise definition:** All three are mounts into the container's mount namespace that sit above the overlay2 root ([§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md)), bypassing copy-on-write. Volumes live under `/var/lib/docker/volumes/<name>/_data` (for the default `local` driver) and are addressed by name through the Docker API. Bind mounts reference an absolute host path that must exist (with `--mount`) and are subject to host permissions and, on Linux, optional propagation settings. tmpfs mounts are Linux-only, backed by host RAM (and swap), and never written to the host filesystem. The preferred syntax is `--mount type=volume|bind|tmpfs,...`; `-v` / `--volume` is the older, terser form with different failure semantics.

> 💡 **Tip:** Rule of thumb: volume for data the container owns, bind mount for files the host owns, tmpfs for data nobody should keep.

## 2. Why This Matters

- Choosing the wrong type causes data loss (container layer), permission errors (bind mounts), slow I/O (bind mounts on Docker Desktop) or leaked secrets (files on disk).
- It is the first design decision for any stateful container: databases, queues, uploads, caches.
- `-v` silently creates a missing host directory as root, while `--mount` errors; this difference causes production surprises.
- Core DCA and interview material, and the foundation for the lifecycle, driver and backup topics that follow.

## 3. Prerequisites and Dependencies

Requires the writable-layer model ([§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md), [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), mount namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), the `VOLUME` instruction ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)) and `docker run` flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)). Memory limits matter for tmpfs because its pages count against the container's cgroup ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)). The Compose equivalents are in [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md).

## 4. Architecture / Conceptual Diagram

```text
                    Container filesystem (mount namespace)
   ┌───────────────────────────────────────────────────────────────────┐
   │  /                 overlay2 merged root  (ephemeral upper layer)  │
   │  /var/lib/db   ◄── volume mount                                   │
   │  /app/src      ◄── bind mount                                     │
   │  /run/scratch  ◄── tmpfs mount                                    │
   └───────┬─────────────────────┬──────────────────────┬──────────────┘
           │                     │                      │
           ▼                     ▼                      ▼
   ┌───────────────┐    ┌─────────────────┐    ┌─────────────────┐
   │ Docker area   │    │ Any host path   │    │ Host RAM / swap │
   │ /var/lib/     │    │ /home/me/proj   │    │ (kernel page    │
   │ docker/       │    │ (you manage     │    │  cache, no disk │
   │ volumes/NAME/ │    │  perms, backup) │    │  files)         │
   │ _data         │    └─────────────────┘    └─────────────────┘
   └───────────────┘

   ┌────────────────┬─────────────────┬──────────────────┬───────────────┐
   │                │ Volume          │ Bind mount       │ tmpfs         │
   ├────────────────┼─────────────────┼──────────────────┼───────────────┤
   │ Managed by     │ Docker          │ You              │ Kernel        │
   │ Survives rm    │ Yes (unless -v) │ Yes (host files) │ No            │
   │ Survives stop  │ Yes             │ Yes              │ No            │
   │ Host path need │ No              │ Yes, absolute    │ No            │
   │ Pre-populated  │ From image path │ No (host wins)   │ No            │
   │ Drivers (NFS…) │ Yes             │ No               │ No            │
   │ Works on Win   │ Yes             │ Yes (slower)     │ Linux only    │
   └────────────────┴─────────────────┴──────────────────┴───────────────┘
```

- **Pre-population:** an empty named volume mounted over an image directory is initialized with that directory's content from the image; a bind mount or non-empty volume hides it.
- **Obscuring:** any mount on a non-empty container path hides the original files, which are still in the lower layers.
- **Lifecycle:** volumes are independent of containers; bind mounts are just paths; tmpfs ends with the container.

## 5. Hands-On

### 5.1 Named Volume (Docker-Managed)

```bash
docker volume create appdata
docker run -d --name db1 --mount type=volume,src=appdata,dst=/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=example postgres:16
docker rm -f db1
docker run --rm --mount type=volume,src=appdata,dst=/data alpine:3.20 ls /data | head -3
```

```text
base
global
pg_commit_ts
```

The data outlived the container. Removing the container without `-v` never deletes named volumes.

### 5.2 Bind Mount (Host Path)

```bash
mkdir -p ~/demo/site && echo '<h1>hi</h1>' > ~/demo/site/index.html
docker run -d --name web -p 8080:80 \
  --mount type=bind,src="$HOME/demo/site",dst=/usr/share/nginx/html,readonly nginx:1.27
curl -s localhost:8080
echo '<h1>edited</h1>' > ~/demo/site/index.html && curl -s localhost:8080
```

```text
<h1>hi</h1>
<h1>edited</h1>
```

Edits on the host appear immediately, which is why bind mounts power development workflows ([§41](../Part5/Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md)). The `readonly` flag blocks writes from the container side only.

### 5.3 tmpfs Mount

```bash
docker run --rm --mount type=tmpfs,dst=/scratch,tmpfs-size=64m,tmpfs-mode=1777 \
  alpine:3.20 sh -c 'df -h /scratch; dd if=/dev/zero of=/scratch/f bs=1M count=100'
```

```text
Filesystem   Size   Used  Available Use% Mounted on
tmpfs       64.0M      0     64.0M   0% /scratch
dd: error writing '/scratch/f': No space left on device
```

The shorthand is `--tmpfs /scratch:rw,size=64m,noexec`. Without a size, tmpfs defaults to half of host RAM, so set a limit.

### 5.4 `-v` vs `--mount` on a Missing Host Path

```bash
docker run --rm -v /srv/does-not-exist:/data alpine:3.20 ls /data
docker run --rm --mount type=bind,src=/srv/does-not-exist,dst=/data alpine:3.20 ls /data
```

```text
(first command succeeds; Docker created /srv/does-not-exist as root on the host)
docker: Error response from daemon: invalid mount config for type "bind": bind source path does not exist: /srv/does-not-exist.
```

`--mount` fails loudly, which is what you want in production. Note that `-v` has a legacy behavior that varies by Docker Desktop version, so do not rely on it.

### 5.5 Anonymous Volumes and the `VOLUME` Instruction

```dockerfile
FROM alpine:3.20
VOLUME /data
```

```bash
docker build -t vol-demo .
docker run -d --name v1 vol-demo sleep 300
docker volume ls -q | head -2
docker inspect v1 --format '{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{"\n"}}{{end}}'
```

```text
5c1f0e...(64 hex chars)
volume 5c1f0e...(64 hex chars) -> /data
```

Every `docker run` of this image creates a new anonymous volume that is easy to leak. Prefer naming the volume explicitly at run time. See [§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md).

### 5.6 Permissions: UID Mismatch on Bind Mounts

```bash
mkdir ~/owned && sudo chown 1000:1000 ~/owned
docker run --rm --user 2000:2000 --mount type=bind,src="$HOME/owned",dst=/w alpine:3.20 touch /w/x
```

```text
touch: /w/x: Permission denied
```

Bind mounts use host numeric UIDs and GIDs. Match them with `--user "$(id -u):$(id -g)"`, adjust ownership, or use a volume where Docker initializes ownership from the image path.

### 5.7 SELinux Labels and Propagation (Linux)

```bash
docker run --rm -v "$PWD":/work:Z alpine:3.20 ls /work         # private relabel (SELinux)
docker run --rm --mount type=bind,src="$PWD",dst=/work,bind-propagation=rslave alpine:3.20 ls /work
```

`:z` shares the label among containers, `:Z` gives a private one. Never use `:Z` on a shared system directory such as `/home` or `/etc`: it relabels real host files. See [§61](../Part8/Section-61-Part8-AppArmor-and-SELinux-with-Docker.md).

### 5.8 Compose Equivalent

```yaml
services:
  db:
    image: postgres:16
    volumes:
      - dbdata:/var/lib/postgresql/data      # named volume
      - ./init:/docker-entrypoint-initdb.d:ro # bind mount, read-only
    tmpfs:
      - /run/postgresql                       # tmpfs
volumes:
  dbdata:
```

## 6. Production Usage Notes

- **Default to named volumes** for databases and application state; they are portable across hosts that share the same driver and easy to back up and migrate ([§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).
- **Bind mounts belong to development and to host-owned config:** source code, certificates, a read-only config file, the Docker socket (a high-risk exception, see [§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **tmpfs fits:** scratch files, session sockets, secrets that must never reach disk, and the writable bits a `--read-only` container needs (`/tmp`, `/run`) ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Set tmpfs size limits.** Its memory is charged to the container's cgroup; an unbounded tmpfs can trigger an OOM kill.
- **Docker Desktop:** bind mounts cross a VM boundary through file sharing (virtiofs, gRPC FUSE) and are much slower than volumes for I/O-heavy workloads such as `node_modules`. Keep dependency directories in volumes ([§56](Section-56-Part7-Storage-Performance-Considerations.md)).
- **Orchestrators:** Swarm and Kubernetes prefer volumes or claim abstractions; bind mounts tie a workload to one node's filesystem.
- **Read-only mounts** (`readonly` or `:ro`) are cheap least-privilege hardening; apply them to all config and source mounts.
- **Choosing quickly:**

| Need | Pick |
|---|---|
| Database or queue data | Named volume |
| Live-edit source in dev | Bind mount (or Compose `develop.watch`) |
| Ship config from the host | Bind mount, read-only |
| Share files between containers | Named volume (same name, multiple containers) |
| Temporary cache, fast, disposable | tmpfs |
| Secret that must not touch disk | tmpfs (or Docker/Compose secrets, [§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)) |
| Remote or cloud-backed storage | Volume with a driver ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)) |

## 7. Security Considerations

- **Bind mounts expose host files with host permissions.** A writable bind mount of a sensitive directory (`/`, `/etc`, `/var/run/docker.sock`, a home folder) lets a compromised container modify or take over the host.
- **Docker socket mounts equal root on the host**; treat them as privileged ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **Use `readonly` wherever the container should not write**, and `noexec,nosuid,nodev` on tmpfs mounts for `/tmp`.
- **Symlink and path races:** a container-controlled path inside a bind mount can point back to host locations on the host side; avoid mounting directories that untrusted containers can populate and the host then trusts.
- **Volumes are not encrypted.** Data in `/var/lib/docker/volumes` is plain on disk; use encrypted block devices or encrypted volume drivers for sensitive data, and back up securely.
- **tmpfs can be swapped to disk.** For strict no-disk guarantees, disable swap on the host or use encrypted swap.
- **Rootless and userns-remap** change effective ownership of mounted files; verify UID mapping ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)).
- **Clean up volumes holding sensitive data** explicitly; they persist after container removal.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Data gone after `docker run` again | No mount; data was in the container layer | Mount a named volume at the data path |
| Fresh empty directory where files should be | Mount hides image content (bind mount or non-empty volume) | Use an empty named volume to pre-populate, or copy files at startup |
| `Permission denied` writing to bind mount | UID/GID mismatch, SELinux label, or `readonly` | Match `--user`, add `:z`/`:Z`, drop `readonly` |
| `invalid mount config ... source path does not exist` | `--mount` bind with missing path | Create the path first |
| Host dir owned by root unexpectedly | `-v` auto-created the path | Use `--mount` and pre-create with correct owner |
| Very slow builds/tests on Mac or Windows | Bind-mounted dependency dir across the VM | Use a volume for `node_modules`/caches, or file-sharing tuning |
| Container OOM-killed with plenty of disk | Large tmpfs counted as container memory | Size the tmpfs and raise `--memory` |
| Many unnamed volumes in `docker volume ls` | `VOLUME` in Dockerfile with anonymous mounts | Name volumes at run time; prune dangling ones |
| `docker rm -v` removed data unexpectedly | `-v` deletes anonymous volumes of the container | Use named volumes for data you keep |

## 9. Best Practices

- Use `--mount` (or Compose long syntax) in scripts and production; keep `-v` for quick interactive use.
- Name every volume that holds data; do not rely on anonymous volumes.
- Mount config and code read-only; mount data read-write only into the one container that owns it.
- Keep one writer per volume unless the application supports concurrent access.
- Set explicit tmpfs `size`, and add `noexec,nosuid` where possible.
- On Docker Desktop, keep high-churn directories off bind mounts.
- Document each mount's purpose, owner UID and backup plan in the Compose file.
- Pair `--read-only` with targeted tmpfs mounts for `/tmp` and `/run`.

## 10. Common Anti-Patterns / Mistakes

- Running a database with no volume and trusting the container layer.
- Bind-mounting `/var/run/docker.sock` or `/` "just for convenience".
- Using `-v ./relative/path:/data`, which Docker parses as a volume name, not a path (use `$PWD/relative/path`, or a Compose relative path).
- Mounting a host directory over `/app` in production, so the image's own code is hidden.
- Sharing one read-write volume among several writers with no coordination.
- Omitting tmpfs size limits, letting scratch data consume host memory.
- Using `:Z` on shared host directories and breaking other services' SELinux labels.
- Putting secrets in a bind-mounted `.env` file that is committed or world-readable.

## 11. Interview Questions

**🎯 Beginner:** _"What are the three kinds of mounts in Docker, and which would you use for a database's data directory?"_
**Model answer:** Volumes, bind mounts and tmpfs mounts. A volume is created and managed by Docker under its own storage area and survives container removal. A bind mount maps an existing host path into the container. tmpfs is memory-backed and vanishes when the container stops. For a database's data directory I use a named volume, because Docker manages its location and lifecycle, it is easy to back up, it works across Linux, Mac and Windows, and it avoids host-path and permission coupling.
_What the interviewer is probing for:_ Correct vocabulary and the default choice for persistent data.

**🎯 Intermediate:** _"Explain the difference between `-v` and `--mount`, with a failure case that bites in production."_
**Model answer:** Both create mounts, but `--mount` is explicit key-value syntax that supports every type and is stricter. With `-v /srv/data:/data`, if `/srv/data` does not exist Docker silently creates it as a root-owned directory, which hides typos and breaks permissions. `--mount type=bind,src=/srv/data,dst=/data` errors out instead. Another trap is `-v data:/x`, where `data` is treated as a volume name, so a relative path without a slash becomes an unintended named volume. In scripts and Compose I prefer the explicit form.
_What the interviewer is probing for:_ Practical syntax semantics and defensive habits.

**🎯 Senior:** _"A team's Node app runs five times slower on Docker Desktop for Mac than in CI. They bind-mount the whole project. What do you change?"_
**Model answer:** On Docker Desktop, bind mounts cross a VM boundary through a file-sharing layer, so many small file operations such as reading `node_modules` are expensive. Keep source in a bind mount (or use Compose `develop.watch` to sync) but move `node_modules` and build caches to a named volume so they live on the VM's native filesystem. Ensure the volume is initialized by the image build rather than by host files, consider virtiofs file sharing, and use `.dockerignore` to shrink the context. Verify with timing before and after, and confirm CI uses the same dependency layout so results are comparable.
_What the interviewer is probing for:_ Understanding why bind mounts are slow on VM-based Docker and how to split mounts by access pattern.

**🎯 Architect:** _"Design a mount policy for a platform where hundreds of services run on shared hosts, including a requirement that some secrets never touch disk."_
**Model answer:** Define an allowlist by workload class. Stateful services get named volumes with a approved driver (encrypted block or network storage), one writer each, with quotas and a backup contract. Stateless services run `--read-only` with sized `noexec` tmpfs for `/tmp` and `/run`. Bind mounts are denied by admission policy except for an audited list of read-only config paths, and the Docker socket and host root are banned outright. Secrets use the orchestrator's secret mechanism, which Docker mounts as an in-memory tmpfs file, with swap disabled or encrypted on hosts so tmpfs pages cannot spill. Enforce with policy-as-code on Compose or manifests, monitor mount inventories via `docker inspect`, and test restore procedures regularly.
_What the interviewer is probing for:_ Policy-level thinking: least privilege, enforcement points, secrets handling, and operational readiness.

## 12. Common Misconceptions

- "Volumes are deleted when the container is removed." Only anonymous volumes with `docker rm -v`; named volumes persist.
- "A bind mount is just a faster volume." It is host-path coupled and often slower on Docker Desktop.
- "tmpfs data is safe from the disk." It can be swapped out.
- "`readonly` on a bind mount protects the host file from everything." It blocks writes from that container only.
- "Mounting over an image directory merges the contents." The mount hides what was there.
- "`VOLUME` in a Dockerfile makes data persistent and named." It creates anonymous volumes at run time.

## 13. 🔑 Key Takeaways

- Volume = Docker-managed and durable; bind mount = host path; tmpfs = RAM, gone at stop.
- Prefer `--mount`; it fails on missing paths where `-v` creates them silently.
- Named volumes for state, read-only bind mounts for host config, sized tmpfs for scratch.
- Bind mounts expose the host: never mount the Docker socket or system directories lightly.
- Bind mounts are slow on Docker Desktop; keep hot directories in volumes.
- Mounts hide the image content beneath them; empty named volumes get pre-populated.

## 14. Related Concepts & What's Next

Related: writable layer and overlay2 ([§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md)), `VOLUME` instruction ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), Compose volumes ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), read-only filesystems ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)), secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), persistence patterns ([§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)). Next, [§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md) goes deep on named volumes: creation, inspection, sharing, labels and cleanup.

**Next Section:** [§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md) — `Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md`
