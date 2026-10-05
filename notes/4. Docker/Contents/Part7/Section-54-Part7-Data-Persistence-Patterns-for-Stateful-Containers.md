# Section 54 (Part 7): Data Persistence Patterns for Stateful Containers

## 1. Definition

**Plain language:** A container's writable layer disappears with the container. A *persistence pattern* is a deliberate way of placing a stateful program's data (database files, uploads, queues, caches) somewhere that outlives any single container, and wiring the container so it finds that data again after a restart, upgrade or reschedule.

**Precise definition:** The container's writable layer is the top layer of the overlay2 stack ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§50](Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md)) and is deleted by `docker rm`. State survives only when it lives on a mount that is independent of that layer: a named volume ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), a bind mount, a volume-driver-backed volume ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)), or an external service. A persistence pattern combines three decisions: **where** the data lives (mount type), **who** owns its lifecycle (Compose project, operator, external system), and **how** the application initializes, upgrades and recovers it.

> 💡 **Tip:** Treat the container as disposable and the data as the asset. If `docker rm -f` on the container would lose something you care about, the pattern is incomplete.

## 2. Why This Matters

- Databases, message brokers and CI caches are the workloads where "just rebuild the container" destroys business data.
- The most common production data-loss incident is an image whose `VOLUME` declaration created an anonymous volume that nobody named, then pruned ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).
- Initialization is subtle: official images such as postgres and mysql run first-boot scripts only when the data directory is empty, so mounting the wrong thing changes behavior.
- Choosing the pattern early decides whether backup ([§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)), performance ([§56](Section-56-Part7-Storage-Performance-Considerations.md)) and upgrades are easy or painful.
- It is a standard DCA and senior-interview topic: "how would you run a database in Docker, and should you?"

## 3. Prerequisites and Dependencies

Requires the volume vs bind mount vs tmpfs distinctions ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), named volume lifecycle ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)) and the `VOLUME` instruction ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)). Compose volume syntax comes from [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md); readiness gating uses health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)). Memory limits matter for databases ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), and stop behavior depends on signal handling ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md), [§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)).

## 4. Architecture / Conceptual Diagram

```text
  Pattern A: named volume (default for single-host state)
  ┌─────────────┐   mount    ┌───────────────────────────────┐
  │ container   │ ─────────► │ /var/lib/docker/volumes/pgdata│  (Docker-managed)
  │ postgres    │            └───────────────────────────────┘
  └─────────────┘     docker rm container: data stays

  Pattern B: bind mount (host path you own and back up)
  ┌─────────────┐   mount    ┌───────────────┐
  │ container   │ ─────────► │ /srv/pg/data  │  (host path, host ownership rules)
  └─────────────┘            └───────────────┘

  Pattern C: external managed service (state leaves Docker entirely)
  ┌─────────────┐   TCP      ┌────────────────────────┐
  │ app         │ ─────────► │ RDS / Cloud SQL / S3   │
  └─────────────┘            └────────────────────────┘

  Pattern D: init / sidecar pair sharing one volume
  ┌────────────┐  writes   ┌──────────┐  reads   ┌────────────┐
  │ init job   │ ────────► │  volume  │ ◄─────── │ main app   │
  └────────────┘           └──────────┘          └────────────┘

  Pattern E: ephemeral state (tmpfs / no volume) - cache can be lost by design
  ┌─────────────┐  tmpfs   ┌───────────┐
  │ app cache   │ ───────► │ RAM only  │  gone on stop
  └─────────────┘          └───────────┘
```

- **A** is the default; Docker creates the directory, applies image-seeded content on first use, and keeps lifecycle separate from the container.
- **B** gives direct host visibility (easy file-level backup, easy mistakes with ownership and Docker Desktop file sharing).
- **C** is often the right answer for production databases: the container holds no state.
- **D** and **E** handle configuration seeding and deliberately non-durable data.

## 5. Hands-On

### 5.1 Prove That the Writable Layer Is Disposable

```bash
docker run -d --name tmpdb -e POSTGRES_PASSWORD=pw postgres:16
docker exec tmpdb psql -U postgres -c "create table t(i int); insert into t values (1);"
docker rm -f tmpdb
docker run -d --name tmpdb2 -e POSTGRES_PASSWORD=pw postgres:16
docker exec tmpdb2 psql -U postgres -c "select * from t;"
```

```text
ERROR:  relation "t" does not exist
```

The postgres image declares `VOLUME /var/lib/postgresql/data`, so the first container silently used an anonymous volume. It was not reused by the second container, so the data looks lost.

```bash
docker volume ls -f dangling=true
```

```text
DRIVER    VOLUME NAME
local     3f1c0e...   # orphaned anonymous volume still holding the first table
```

### 5.2 The Named-Volume Pattern for a Database

```bash
docker volume create pgdata
docker run -d --name pg -e POSTGRES_PASSWORD=pw \
  -v pgdata:/var/lib/postgresql/data postgres:16
docker exec pg psql -U postgres -c "create table t(i int); insert into t values (1);"
docker rm -f pg
docker run -d --name pg -e POSTGRES_PASSWORD=pw \
  -v pgdata:/var/lib/postgresql/data postgres:16
docker exec pg psql -U postgres -c "select * from t;"
```

```text
 i 
---
 1
(1 row)
```

Note: for postgres 18 and later images the documented data path moved to `/var/lib/postgresql` (a versioned subdirectory underneath). Always check the image's README for the exact mount target for the tag you pin.

### 5.3 Compose Pattern with Health Gate and Named Volume

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/pg_pw
    secrets: [pg_pw]
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10
    stop_grace_period: 60s
    restart: unless-stopped
  app:
    image: myapp:1.4.2
    depends_on:
      db: { condition: service_healthy }

volumes:
  pgdata:
    name: myapp_pgdata   # fixed name, not prefixed by project

secrets:
  pg_pw:
    file: ./secrets/pg_pw.txt
```

Key points: a fixed `name:` makes the volume survive a project rename; `stop_grace_period` gives the database time to checkpoint; `docker compose down` keeps the volume, while `docker compose down -v` deletes it.

### 5.4 Seeding Data with the Initialization Directory

```bash
mkdir -p init
printf "create table seed(i int);\ninsert into seed values (42);\n" > init/01-seed.sql
docker run -d --name seeded -e POSTGRES_PASSWORD=pw \
  -v seeddata:/var/lib/postgresql/data \
  -v "$PWD/init:/docker-entrypoint-initdb.d:ro" postgres:16
docker exec seeded psql -U postgres -c "select * from seed;"
```

```text
 i  
----
 42
```

These scripts run only when the data directory is empty. Mounting a pre-populated volume skips them, which is the correct behavior but surprises people who edit the script and restart.

### 5.5 Initializing a Volume from Image Content (Populate-on-First-Use)

```bash
docker run --rm -v appdata:/data alpine:3.20 sh -c 'ls /data | wc -l'
docker run --rm -v appdata:/usr/share/nginx/html nginx:1.27 ls /usr/share/nginx/html
```

```text
0
50x.html
index.html
```

An *empty* named volume is populated from the image directory it covers the first time it is mounted; a non-empty volume is never overwritten. This copy-up does not happen for bind mounts, which simply hide the image content.

### 5.6 Sharing State Between Containers: Init Pattern

```bash
docker volume create shared
docker run --rm -v shared:/out alpine:3.20 sh -c 'echo ready > /out/flag'
docker run --rm -v shared:/in:ro alpine:3.20 cat /in/flag
```

```text
ready
```

The `:ro` suffix on the consumer prevents accidental writes. Only one writer should own a given path; two database processes sharing one data directory corrupts it.

### 5.7 Bind Mount Pattern with Correct Ownership

```bash
sudo mkdir -p /srv/redis && sudo chown 999:999 /srv/redis
docker run -d --name redis -v /srv/redis:/data redis:7 redis-server --appendonly yes
ls -ln /srv/redis
```

```text
-rw-r--r-- 1 999 999  ... appendonlydir
```

The container's UID (999 for redis and postgres images) must be able to write to the host directory. Mismatched ownership is the leading cause of "permission denied" on first start.

## 6. Production Usage Notes

- **Prefer managed databases for production tier-1 data** and keep containers for stateless services; run databases in containers for development, CI, edge, or when you can operate storage, backup and failover yourself.
- **Name every volume.** Use `name:` in Compose and review `docker volume ls` for anonymous 64-hex names.
- **Give databases time to stop:** `stop_grace_period` (Compose) or `--stop-timeout` so SIGTERM can flush; a SIGKILL forces crash recovery.
- **One writer per data directory.** Never run two replicas of a single-node database on the same volume; use the database's own replication.
- **Single-host reality:** a local volume ties the data to one machine. Rescheduling to another host needs network storage ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)), replication, or acceptance of downtime.
- **Filesystem choice:** databases on NFS or other network filesystems risk locking and fsync problems; prefer block storage with ext4 or xfs ([§56](Section-56-Part7-Storage-Performance-Considerations.md)).
- **Separate data classes:** database files on a durable volume, caches and temp on tmpfs or a disposable volume, config as read-only bind mount or Compose `configs`.
- **Upgrades:** major database version upgrades need a dump/restore or `pg_upgrade`-style process. Changing the image tag on an old data directory fails or corrupts. Take a backup first ([§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).
- **Docker Desktop:** bind mounts cross a VM file-sharing boundary and are slower; named volumes live inside the VM and are faster, but you cannot browse them directly from the host.
- **Orchestrators:** Kubernetes models this as PersistentVolumeClaims and StatefulSets; the same principles (separate data lifecycle, one writer, ordered shutdown) apply ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 7. Security Considerations

- **Volume contents are plain files on the host**, readable by root and anyone in the docker group. Encrypt the underlying disk, or use database-level encryption for sensitive data.
- **Pass credentials with secrets or `_FILE` variables**, not `-e PASSWORD=...`, which is visible in `docker inspect` ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Mount config and init scripts read-only** (`:ro`) so a compromised app cannot rewrite them.
- **Least-privilege mounts:** never mount the Docker socket, `/`, or a home directory to "make persistence easy" ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **Read-only root filesystem** plus an explicit writable data volume and tmpfs for `/tmp` is the hardened shape for stateful services ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Ownership and non-root:** run as the image's non-root user and set volume ownership to match, rather than chmod 777 ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)). With user-namespace remapping, volume files appear owned by a remapped high UID.
- **Backups inherit the sensitivity** of the data; treat archives as secrets.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Data gone after `docker rm` and re-run | Anonymous volume from `VOLUME` was not re-attached | Mount a named volume explicitly; recover from `docker volume ls -f dangling=true` |
| Data gone after `compose down -v` | `-v` removes named volumes declared in the file | Omit `-v`; mark critical volumes `external: true` |
| New Compose project, empty database | Volume name is prefixed by the project name | Set `name:` on the volume or use `external: true` |
| Init scripts not re-run | Data directory already populated | Remove the volume (only on disposable data) or run SQL manually |
| `initdb: directory exists but is not empty` | Mount contains `lost+found` or other files | Mount a subdirectory (`PGDATA=/var/lib/postgresql/data/pgdata`) |
| `permission denied` on bind mount | Host UID does not match container UID | `chown` host dir to the container UID or use a named volume |
| Database "was not shut down cleanly" after redeploy | Stop timeout too short, SIGKILL | Increase `stop_grace_period`; ensure exec form so signals arrive |
| Database fails after image upgrade | Data directory from an older major version | Dump from old version, restore into new; or in-place upgrade tool |
| Slow database on Docker Desktop | Bind mount across the VM boundary | Use a named volume |
| Edits to a bind-mounted file not seen | Editor replaced the inode (rename on save) while container held the old one | Mount the directory, not the single file |

## 9. Best Practices

- Declare and name every persistent path; list them in the README next to the image.
- Use named volumes for databases, bind mounts for source code and operator-owned config.
- Keep the data lifecycle separate: `external: true` volumes for anything that must survive `compose down -v`.
- Add a health check and gate dependents on `service_healthy`.
- Set a generous stop timeout for stateful services and test `docker stop` timing.
- Pin image tags including the major version of the database.
- Back up before every upgrade and test the restore ([§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).
- Prefer application-level replication or managed services for availability; volumes give durability, not high availability.
- Label volumes (`--label env=prod --label backup=daily`) so cleanup and backup tooling can select them.
- Document the data path per image version; paths can change between major tags.

## 10. Common Anti-Patterns / Mistakes

- Relying on the container's writable layer for anything that matters.
- Letting `VOLUME` in a third-party image create anonymous volumes in production.
- Running `docker system prune --volumes` on a host that holds unmounted but valuable volumes.
- Sharing one database data directory between two running containers.
- Storing database files on a network share without verifying locking and fsync semantics.
- `chmod -R 777` on a bind mount to silence permission errors.
- Putting secrets, `.env` files, or the volume's own backups inside the same volume.
- Using `latest` for the database image so an automatic pull silently moves to a new major version.
- Treating a single-host volume as high availability.
- Baking data into the image (`COPY dump.sql`) instead of seeding through init scripts or restores.

## 11. Interview Questions

**🎯 Beginner:** _"You run a MySQL container, create some tables, remove the container and start a new one. The tables are gone. Why, and what do you change?"_
**Model answer:** Files written inside a container go to its writable layer, which is deleted with the container. The MySQL image declares `VOLUME /var/lib/mysql`, so Docker created an anonymous volume, but the new container got a fresh anonymous volume instead of reusing it. The fix is to mount a named volume explicitly, for example `-v mysqldata:/var/lib/mysql`, so every new container attaches the same data. The old anonymous volume may still exist and can be found with `docker volume ls -f dangling=true`.
_What the interviewer is probing for:_ Understanding of writable-layer lifecycle versus volumes, and the anonymous-volume trap.

**🎯 Intermediate:** _"Your Compose-based app lost its database after a teammate ran `docker compose down -v` and, separately, after renaming the project directory. Explain both and make the setup resilient."_
**Model answer:** `down -v` removes named volumes declared in the Compose file, so the data was deleted by design. Renaming the directory changes the default project name, and Compose prefixes volume names with it (`oldproj_pgdata` versus `newproj_pgdata`), so the new project created an empty volume while the old one sat unused. To make it resilient, set an explicit `name:` on the volume, or declare it `external: true` and create it out-of-band so Compose never deletes it. Add backups, and use `COMPOSE_PROJECT_NAME` or the top-level `name:` field to keep project identity stable.
_What the interviewer is probing for:_ Knowing Compose volume naming and the lifecycle commands that destroy data.

**🎯 Senior:** _"Design persistence for a single-node PostgreSQL container used by a small internal service. Cover storage, shutdown, upgrades and what you would tell the team about its limits."_
**Model answer:** Use a named volume on a block-backed ext4/xfs filesystem, mounted at the image's documented data path, with a fixed name and `external: true` in production. Pass credentials via secrets, pin the image to a major version, add a `pg_isready` health check, and set a long `stop_grace_period` so SIGTERM triggers a clean checkpoint. Run scheduled `pg_dump` (logical) and periodic volume snapshots, with restore tested into a fresh volume. Major upgrades go through dump and restore or `pg_upgrade` into a new volume, never by retagging over the old data. I would state the limits plainly: one host means a host failure is an outage, the volume gives durability but not availability, and anything needing failover should use replication or a managed database.
_What the interviewer is probing for:_ End-to-end operational thinking rather than just "use a volume".

**🎯 Architect:** _"A platform team wants to run all company databases as containers on a Docker fleet. What is your position, and what would you require for the workloads you allow?"_
**Model answer:** I would separate by criticality. Tier-1 transactional data goes to managed services or an operator-driven platform with replication, PITR and tested failover, because Docker volumes alone provide neither HA nor scheduling-aware storage. Containerized databases are acceptable for dev, test, CI, ephemeral review environments and edge deployments. For those allowed in production, require: network or replicated block storage with a volume driver that supports reattachment, anti-affinity and one-writer enforcement, resource limits sized above the database cache, documented backup and restore SLOs with automated restore tests, encrypted volumes, a standard image and entrypoint contract, and a upgrade runbook. I would also keep an exit path: data formats must be portable to a managed service.
_What the interviewer is probing for:_ Risk-based judgment about stateful workloads and knowing what Docker does not provide.

## 12. Common Misconceptions

- "Volumes make a container highly available." They make data durable on one host.
- "`docker rm` deletes my volume." It does not, unless you pass `-v` (which removes only anonymous volumes of that container).
- "Bind mounts are always faster than volumes." On Docker Desktop they are usually slower; on Linux they are about equal.
- "Init scripts run on every start." They run only against an empty data directory.
- "Putting the database in the image makes it portable." It bakes in state, bloats layers, and loses writes on recreate.
- "Containers can't run databases." They can, with the discipline described here; the limits are operational, not technical.

## 13. 🔑 Key Takeaways

- State must live outside the writable layer: named volume, bind mount, driver-backed volume, or an external service.
- Name every volume; anonymous volumes get orphaned and pruned.
- `compose down -v` and project renames are the classic data-loss causes; use `name:` and `external: true`.
- Init scripts and image-content seeding apply only to empty volumes.
- One writer per data directory; give databases a long stop grace period.
- Volumes give durability, not availability; major upgrades need dump/restore and a backup first.

## 14. Related Concepts & What's Next

Related: volume types ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), named volume lifecycle ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), volume drivers ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)), health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)), secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), disaster recovery ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). Next, [§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md) covers how to back up and restore the data these patterns persist.

**Next Section:** [§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md) — `Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md`
