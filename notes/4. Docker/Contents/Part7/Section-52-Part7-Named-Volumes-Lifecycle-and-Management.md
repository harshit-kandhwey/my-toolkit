# Section 52 (Part 7): Named Volumes: Lifecycle and Management

## 1. Definition

**Plain language:** A named volume is a piece of storage that Docker creates, names and manages for you. It lives outside any container's writable layer, so it survives `docker rm` and can be attached to a different container later.

**Precise definition:** A volume is a first-class Docker object with a name, a driver, driver options, labels and a scope. With the default `local` driver, its data sits on the host at `/var/lib/docker/volumes/<name>/_data` (the Docker data root, see [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). A volume is created explicitly (`docker volume create`) or implicitly the first time a container references a name that does not exist. A volume with no name given is an **anonymous volume** and receives a random 64-hex-character name. Volumes are only removed when you remove them (`docker volume rm`, `docker volume prune`, `docker run --rm` for anonymous ones, or `docker compose down -v`). Removing a container never removes a named volume.

> 💡 **Tip:** Think of a named volume as a disk you can unplug from one container and plug into another. The container is disposable, the volume is not.

## 2. Why This Matters

- Databases, uploads, caches and certificates must outlive container replacement during upgrades ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md) explains when a volume is the right mount type).
- Most data-loss incidents in Docker come from lifecycle confusion: an anonymous volume nobody can find, `down -v` run on the wrong stack, or a `prune` that removed something precious.
- Volume ownership, initialization and naming rules cause the bulk of "permission denied" and "my data vanished" tickets.
- Disk usage on a Docker host is dominated by volumes and images; knowing what is attached to what is how you reclaim space safely ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).

## 3. Prerequisites and Dependencies

Requires the image and container layer model ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md)) and the `docker run` mount flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)). The `VOLUME` Dockerfile instruction, which is the main source of anonymous volumes, is covered in [§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md). Compose volume declarations are in [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md). Non-local backends follow in [§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md); backup procedures in [§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md).

## 4. Architecture / Conceptual Diagram

```text
   Volume lifecycle (local driver)

   docker volume create pgdata            docker run -v pgdata:/var/lib/postgresql/data
            │                                          │
            ▼                                          ▼
   ┌──────────────────┐   first mount    ┌─────────────────────────┐
   │ CREATED / EMPTY  │ ───────────────► │ IN USE (>=1 container)  │
   │ /var/lib/docker/ │   (copy-up of    │  data written to _data  │
   │ volumes/pgdata/  │    image files   └───────────┬─────────────┘
   │ _data            │    if empty)                 │ docker rm -f <container>
   └──────────────────┘                              ▼
            ▲                            ┌─────────────────────────┐
            │  reattach to new           │ UNUSED ("dangling")     │
            └─────────────────────────── │ data intact, no owner   │
                                         └───────────┬─────────────┘
                                                     │ docker volume rm / prune
                                                     ▼
                                              data permanently gone

   Copy-up rule (named volumes only, volume empty on first mount):

   image: /var/lib/app/  {conf.d/, seed.db}     volume pgdata (empty)
            │                                          ▲
            └──────── contents copied once ────────────┘
   Non-empty volume: image content at that path is hidden, not merged.
```

- **Scope:** local volumes exist on one engine only; the same name on two hosts is two unrelated volumes.
- **Identity:** the volume name is the only handle. The host path is an implementation detail and can differ on Docker Desktop, where it is inside the VM.
- **Reference tracking:** the daemon records which containers (running or stopped) use each volume; `rm` and `prune` consult it.

## 5. Hands-On

### 5.1 Create, Inspect, Use

```bash
docker volume create --label app=shop --label env=dev pgdata
docker volume ls
docker volume inspect pgdata
```

```text
DRIVER    VOLUME NAME
local     pgdata
[
    {
        "CreatedAt": "2026-10-06T09:12:44Z",
        "Driver": "local",
        "Labels": { "app": "shop", "env": "dev" },
        "Mountpoint": "/var/lib/docker/volumes/pgdata/_data",
        "Name": "pgdata",
        "Options": null,
        "Scope": "local"
    }
]
```

### 5.2 Data Outlives the Container

```bash
docker run -d --name db -e POSTGRES_PASSWORD=pw -v pgdata:/var/lib/postgresql/data postgres:17
docker exec db psql -U postgres -c "create table t(id int); insert into t values (1);"
docker rm -f db
docker run -d --name db2 -e POSTGRES_PASSWORD=pw -v pgdata:/var/lib/postgresql/data postgres:17
docker exec db2 psql -U postgres -c "select * from t;"
```

```text
 id
----
  1
(1 row)
```

### 5.3 `--mount` Syntax and Read-Only Attachment

`--mount` is explicit and fails on typos instead of silently creating something.

```bash
docker run --rm --mount type=volume,src=pgdata,dst=/data,readonly alpine:3.20 ls /data
docker run --rm --mount type=volume,src=pgdata,dst=/data,volume-nocopy alpine:3.20 ls /data
```

`-v pgdata:/data:ro` is the short form. `volume-nocopy` (or `:nocopy` in `-v` form) disables the first-mount copy-up of image content.

### 5.4 Copy-Up Initialization

```bash
docker run --rm -v webroot:/usr/share/nginx/html nginx:1.27 ls /usr/share/nginx/html
docker run --rm -v webroot:/data alpine:3.20 ls /data
```

```text
50x.html
index.html
50x.html
index.html
```

The second container sees nginx's default files because the empty volume was seeded on first mount. If you later mount the volume somewhere that has different image content, the volume content wins and the image content is hidden.

### 5.5 Anonymous Volumes and Where They Come From

```bash
docker run -d --name r redis:7
docker inspect r --format '{{json .Mounts}}'
docker volume ls -f dangling=true
docker rm -f r
docker volume ls -f dangling=true
```

```text
[{"Type":"volume","Name":"3f1c...e9","Source":"/var/lib/docker/volumes/3f1c...e9/_data","Destination":"/data","Driver":"local","Mode":"","RW":true,"Propagation":""}]
DRIVER    VOLUME NAME
local     3f1c...e9
```

The Redis image declares `VOLUME /data`, so each `docker run` without `-v` makes a new anonymous volume. After `docker rm -f r` the volume is orphaned but still on disk. `docker rm -v r` (or `docker run --rm`) removes the container's anonymous volumes with it.

### 5.6 Finding Who Uses a Volume

```bash
docker ps -a --filter volume=pgdata --format '{{.Names}}\t{{.Status}}'
docker volume rm pgdata
```

```text
db2    Up 2 minutes
Error response from daemon: remove pgdata: volume is in use - [c0a1b2...]
```

A stopped container still counts as a user; remove the container first.

### 5.7 Safe Pruning

```bash
docker system df -v | sed -n '/Local Volumes/,$p'
docker volume prune                         # anonymous, unused only (Engine 23.0+ default)
docker volume prune --filter label=env=dev  # scope by label
docker volume prune --all                   # also unused NAMED volumes (dangerous)
```

Since Engine 23.0 `docker volume prune` removes only unused **anonymous** volumes unless `-a/--all` is given. Older engines removed every unused volume, so check the version before trusting old muscle memory. Always run `docker volume ls -f dangling=true` first and read the list.

### 5.8 Compose: Naming, Persistence and `down -v`

```yaml
# compose.yaml in directory "shop"
services:
  db:
    image: postgres:17
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata: {}             # created as shop_pgdata
  legacy:
    external: true       # must already exist, never created or removed by compose
  shared:
    name: company-shared # fixed name, no project prefix
```

```bash
docker compose up -d
docker volume ls --filter label=com.docker.compose.project=shop
docker compose down        # keeps volumes
docker compose down -v     # removes volumes declared in this file (not external ones)
```

### 5.9 Volumes with Driver Options (local driver)

```bash
docker volume create --driver local \
  --opt type=tmpfs --opt device=tmpfs --opt o=size=256m,uid=1000 scratch
```

The `local` driver can mount tmpfs, bind or NFS sources; [§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md) covers the NFS and plugin forms.

## 6. Production Usage Notes

- **Always name production volumes.** Anonymous volumes are invisible to humans and accumulate. For images that declare `VOLUME`, override with an explicit named mount.
- **Name and label by convention:** `<app>-<role>` plus labels such as `app`, `env`, `backup=true`, so prune filters and backup jobs can select them.
- **Volumes are not backups.** A volume on one host is as durable as that host's disk; see [§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md).
- **Stateful upgrades:** replace the container, keep the volume. Do not mount one volume read-write into two database containers; most databases corrupt on concurrent access ([§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)).
- **Disk capacity:** the `local` driver has no quota; a runaway container fills the host disk. Put the data root on its own filesystem, or use XFS project quotas (`--opt size=` works only with the `pquota`-mounted xfs and `overlay2`/volume backing) for hard limits.
- **Moving the data root** (`"data-root"` in `daemon.json`) moves every volume with it; plan a copy with ownership and xattrs preserved.
- **Docker Desktop:** volumes live inside the Linux VM; you cannot browse `/var/lib/docker/volumes` from the Windows or macOS host. Use a helper container or `docker cp`.
- **Swarm and cluster volumes:** Engine 24+ adds CSI-backed cluster volumes (`docker volume create --type mount --group ...`) managed by Swarm. This is a niche feature; Kubernetes `PersistentVolume` objects are the usual answer at scale.
- **Compose projects:** the project name prefixes volume names. Renaming the directory or using `-p` makes Compose create a fresh, empty volume and the old data looks lost. Use `name:` for stable identity.

## 7. Security Considerations

- **Anyone who can run containers can read every volume** by mounting it into a throwaway container as root. Volume names are not access control; restrict access to the Docker socket ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Host path exposure:** `/var/lib/docker/volumes` is root-only on the host. Never `chmod` it open to simplify tooling.
- **Volume contents are plaintext on disk.** Use disk-level encryption (LUKS, EBS encryption) for sensitive data; Docker offers no per-volume encryption.
- **Ownership:** copy-up preserves the image's UID/GID. A non-root app ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)) fails if the volume was first created root-owned; fix with a `chown` in the entrypoint, an init container, or pre-creating the path in the image with the right owner before the first mount.
- **Read-only mounts** (`readonly`/`:ro`) for consumers that only read, such as a web server reading uploaded static files.
- **Secrets do not belong in volumes.** Use Docker secrets or an external manager ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Stale data:** pruning removes the directory but does not securely wipe blocks. Treat decommissioned hosts accordingly.
- **SELinux hosts:** mounting host paths needs `:z`/`:Z`; named volumes are labeled automatically ([§61](../Part8/Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Data vanished after `compose up` from another directory | Different project name, so a new empty `<project>_<vol>` | Set `name:` on the volume or pass the original `-p` |
| `volume is in use` on remove | A running or stopped container references it | `docker ps -a --filter volume=NAME`, remove those containers |
| Database starts empty after image upgrade | Mounted path differs from the image's data dir, so an anonymous volume got the data | `docker inspect` Mounts; mount the right `Destination` |
| `permission denied` writing to volume | Volume root-owned, app runs as UID 1000 | `chown` once via a helper container or entrypoint |
| Volume shows image files you did not expect | Copy-up seeded an empty volume | Use `volume-nocopy`, or start from an empty directory in the image |
| `prune` removed less than expected | Engine 23+ skips named volumes | Use `--all` deliberately, after listing |
| `prune -a` removed important data | Named volume was not attached to a container at that moment | Restore from backup; add `backup=true` labels and filter with `label!=` |
| Disk full, no obvious cause | Many orphaned anonymous volumes | `docker system df -v`, `docker volume ls -f dangling=true` |
| Cannot find volume files on Windows/macOS | Data is inside the Desktop VM | Use `docker run --rm -v vol:/d alpine ls /d` |
| `Error: No such volume` with `external: true` | Volume not created beforehand | `docker volume create NAME` first |

## 9. Best Practices

- Name every volume; treat anonymous volumes as a bug in production definitions.
- Prefer `--mount` in scripts and docs; it is explicit and errors out on mistakes.
- Declare volumes in Compose, use `name:` where identity must not depend on the project name, and mark shared pre-existing ones `external: true`.
- Label volumes (`app`, `env`, `backup`) and prune only with filters.
- Inspect before deleting: list dangling volumes, check sizes with `docker system df -v`.
- Keep the data root on a dedicated, monitored, backed-up filesystem.
- Pre-create ownership for non-root apps, and test an upgrade that recreates the container.
- Document which volumes are authoritative state and which are disposable caches.

## 10. Common Anti-Patterns / Mistakes

- Running `docker volume prune --all` or `docker system prune --volumes` on a host that carries production state.
- Relying on `docker compose down -v` in scripts that also run against shared or non-dev stacks.
- Using the same volume read-write from two database instances.
- Hand-editing files inside `/var/lib/docker/volumes/...` on the host while containers run.
- Assuming a volume is a backup, or that it follows the container to another host.
- Leaving the `VOLUME` instruction's anonymous volume in place for stateful images, then losing track of data.
- Using bind mounts for what should be a volume just to see the files, then fighting host permissions ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)).

## 11. Interview Questions

**🎯 Beginner:** _"You delete a container that used a named volume and recreate it with the same `-v` flag. What happens to the data, and what would happen with an anonymous volume?"_
**Model answer:** The named volume persists independently of the container, so the new container mounts the same name and sees the existing data. With an anonymous volume, each `docker run` creates a fresh random-named volume, so the new container starts empty while the old data sits orphaned until pruned. `docker rm -v` or `--rm` deletes the container's anonymous volumes together with it. Named volumes are only deleted by `docker volume rm`, `prune --all`, or Compose `down -v`.
_What the interviewer is probing for:_ Understanding that volume lifecycle is separate from container lifecycle, and the anonymous versus named distinction.

**🎯 Intermediate:** _"A Compose stack was moved to a new folder and the database came up empty. Explain and fix."_
**Model answer:** Compose prefixes volume names with the project name, which defaults to the directory name. The new directory produced a new project name and therefore a new empty volume such as `newdir_pgdata`, while the data remains in `olddir_pgdata`. Fix by either running with `-p olddir` / `COMPOSE_PROJECT_NAME`, or by giving the volume a fixed `name:` (or `external: true` after creating it) so it no longer depends on the project name. If a rename is required, copy data with a helper container (`docker run --rm -v old:/from -v new:/to alpine cp -a /from/. /to/`) after confirming neither side is in use.
_What the interviewer is probing for:_ Knowledge of Compose naming, `external` and `name`, and a safe data migration method.

**🎯 Senior:** _"The disk on a Docker host is 95% full. Walk through finding and reclaiming space without losing production data."_
**Model answer:** Start with `docker system df -v` to split image, container and volume usage, then `docker volume ls -f dangling=true` to see unattached volumes, and inspect their sizes and labels. Identify which dangling volumes are anonymous leftovers versus named state that is temporarily detached (for example a stopped stack). Take or verify backups first, then remove only confirmed junk with `docker volume rm`, or `docker volume prune --filter` for labeled disposable ones. Remember Engine 23+ `prune` skips named volumes by default, and avoid `--all`. Address root cause: add log rotation, name volumes, set `--rm` on one-shot containers, and alert on data-root filesystem usage.
_What the interviewer is probing for:_ Operational caution, prune semantics, and preventing recurrence.

**🎯 Architect:** _"Design the volume strategy for 40 stateful containers across 10 Docker hosts. What do you standardize and what do you refuse to use named volumes for?"_
**Model answer:** Standardize naming and labels, a dedicated filesystem per host for the data root with monitoring and quotas where the filesystem supports them, encrypted block storage, and a backup job driven by the `backup=true` label that snapshots volumes through a helper container or storage-level snapshots. Make clear that local volumes are host-bound: a container rescheduled to another host sees nothing, so stateful workloads either pin to hosts, use a network-backed driver ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)) with a single-writer rule, or are moved to an orchestrator with CSI. Refuse volumes for secrets, for shared multi-writer database files, and for ephemeral caches that should be tmpfs. Define restore drills and a retention policy, and ban `prune --all` outside break-glass runbooks.
_What the interviewer is probing for:_ Recognizing locality limits, backup ownership, and policy-level guardrails rather than command trivia.

## 12. Common Misconceptions

- "Deleting the container deletes its volume." Only anonymous volumes with `-v`/`--rm`; named volumes remain.
- "`docker volume prune` removes all unused volumes." On Engine 23+ it removes only anonymous ones unless `--all`.
- "Volume contents are merged with image contents." Copy-up happens once into an empty volume; afterward the volume hides the image path.
- "Volumes are shared across hosts automatically." The `local` driver is single-host.
- "A volume is a backup." It is just storage on the same disk.
- "`-v name:/path` and `-v /host/path:/path` are the same thing." The first is a managed volume (with copy-up), the second a bind mount.

## 13. 🔑 Key Takeaways

- Named volumes have their own lifecycle: create, attach, orphan, remove.
- Only explicit removal (`volume rm`, `prune --all`, `down -v`) deletes a named volume.
- Anonymous volumes come from `VOLUME` and bare `-v /path`; name them or clean them up.
- Copy-up seeds an empty named volume once; `nocopy` disables it.
- Compose prefixes names with the project; use `name:` or `external:` for stable identity.
- Engine 23+ `volume prune` is anonymous-only by default; `--all` is the dangerous switch.
- Local volumes are per-host and not backups.

## 14. Related Concepts & What's Next

Related: mount types ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), `VOLUME` instruction ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), prune and disk usage ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)), Compose volumes ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), backup strategy ([§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)). Next, [§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md) shows how volumes can be backed by NFS and cloud storage through the `local` driver options and volume plugins.

**Next Section:** [§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md) — `Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md`
