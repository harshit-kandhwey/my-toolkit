# Section 55 (Part 7): Backup and Restore Strategies for Volumes

## 1. Definition

**Plain language:** A volume backup is a copy of the data in a volume, stored somewhere else, that you can bring back after loss or corruption. A restore is the tested, repeatable procedure that turns that copy back into a working volume.

**Precise definition:** Docker has no built-in `docker volume backup` command. Backups are built from primitives: (1) **file-level** archives of the volume's directory made by a throwaway container that mounts the volume (`tar`), (2) **application-level** exports made through the application's own tooling (`pg_dump`, `mysqldump`, `redis-cli --rdb`, SQLite `.backup`), (3) **storage-level** snapshots of the underlying block device or filesystem (LVM, ZFS, Btrfs, EBS), and (4) **replication** to another node. A backup is only valid once a restore from it has been tested. File-level copies of a *running* database are **crash-consistent at best** and may be unusable.

> 💡 **Tip:** "Backup succeeded" is not a result. "Restored into a fresh volume, application started, row counts matched" is a result.

## 2. Why This Matters

- Volumes are durable against container removal, not against `docker volume rm`, `compose down -v`, `prune`, disk failure, host loss or operator error ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md), [§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)).
- Copying a live database directory produces torn pages and inconsistent WAL; the failure appears only at restore time.
- Restore is the step teams never rehearse; the RTO and RPO you promise depend on it.
- Restoring carelessly over existing data is itself a common cause of data loss, so restores should target new, empty volumes.
- Backup strategy is a core part of disaster recovery ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)) and a frequent senior interview topic.

## 3. Prerequisites and Dependencies

Requires named volume mechanics ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), mount types ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)) and the persistence patterns that decide what must be backed up ([§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)). Volume drivers change where data physically lives ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)). Helper containers use `docker run --rm` ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), `docker cp` ([§30](../Part4/Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md)) and `exec` ([§28](../Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)). Container stop semantics ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)) matter for consistent cold backups.

## 4. Architecture / Conceptual Diagram

```text
  Four backup layers (pick by consistency need and data size)

  1. Application-level (logical)        2. File-level (tar of the volume)
  ┌────────┐  pg_dump   ┌──────────┐    ┌────────┐ mount ┌────────┐ tar ┌──────────┐
  │ db     │ ─────────► │ dump.sql │    │ helper │ ◄──── │ volume │ ──► │ .tar.gz  │
  └────────┘  (online,  └──────────┘    └────────┘       └────────┘     └──────────┘
              consistent)                 (consistent only if app is stopped/quiesced)

  3. Storage-level snapshot             4. Replication
  ┌────────┐     ┌────────────┐         ┌─────────┐ stream ┌─────────┐
  │ volume │ ──► │ LVM/ZFS/EBS│         │ primary │ ─────► │ replica │ (HA + backup source)
  └────────┘     │ snapshot   │         └─────────┘        └─────────┘
                 └────────────┘
                       │ ship off-host
                       ▼
                 ┌───────────────┐   restore path (always into a NEW volume)
                 │ object store /│ ──────────────► docker volume create restored
                 │ backup server │                 untar / psql < dump ──► verify ──► cut over
                 └───────────────┘
```

- **Logical dumps** are portable across versions and consistent without stopping the database; slower for large data.
- **Tar of a stopped volume** is simple, fully consistent, and requires downtime.
- **Snapshots** are fast and near-consistent (crash-consistent), and need host or cloud storage features.
- **Always ship copies off the host**; a backup on the same disk as the data protects against nothing important.

## 5. Hands-On

### 5.1 Back Up a Volume to a Tarball (Helper Container)

```bash
docker volume create demo-data
docker run --rm -v demo-data:/data alpine:3.20 sh -c 'echo "important" > /data/file.txt'

mkdir -p "$PWD/backups"
docker run --rm \
  -v demo-data:/source:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.20 \
  tar czf "/backup/demo-data-$(date +%Y%m%d-%H%M%S).tar.gz" -C /source .
ls -l backups
```

```text
-rw-r--r-- 1 root root  165 ... demo-data-20261006-101500.tar.gz
```

The source is mounted `:ro` so the backup cannot damage the data. The `-C /source .` form stores relative paths, which makes restoring into any directory straightforward. The `$(date ...)` is expanded by the host shell, which gives each archive a unique name and avoids overwriting earlier backups.

### 5.2 Verify the Archive Before Trusting It

```bash
docker run --rm -v "$PWD/backups:/backup:ro" alpine:3.20 \
  sh -c 'tar tzf /backup/demo-data-*.tar.gz && sha256sum /backup/*.tar.gz'
```

```text
./
./file.txt
9a1f...  /backup/demo-data-20261006-101500.tar.gz
```

Store the checksum with the archive; compare it after every transfer.

### 5.3 Restore into a New, Empty Volume (Never Over Existing Data)

```bash
docker volume create demo-data-restored
docker run --rm \
  -v demo-data-restored:/target \
  -v "$PWD/backups:/backup:ro" \
  alpine:3.20 \
  sh -c 'test -z "$(ls -A /target)" && tar xzf /backup/demo-data-20261006-101500.tar.gz -C /target'
docker run --rm -v demo-data-restored:/data alpine:3.20 cat /data/file.txt
```

```text
important
```

The `test -z "$(ls -A /target)"` guard aborts if the target volume is not empty, so a restore cannot silently overwrite live data. If the target is not empty, restore into a different new volume, compare, then decide.

### 5.4 Preserve Ownership, Permissions and Extended Attributes

```bash
docker run --rm -v pgdata:/source:ro -v "$PWD/backups:/backup" alpine:3.20 \
  tar czf /backup/pgdata-files.tar.gz --numeric-owner --xattrs -C /source .
```

`--numeric-owner` stores UIDs rather than names, which matters because the helper image's `/etc/passwd` differs from the database image's. Restore with `--numeric-owner` as well, running as root in the helper, so files come back owned by UID 999 (postgres) and the database can start.

### 5.5 Online Logical Backup of PostgreSQL

```bash
docker exec pg pg_dump -U postgres -Fc appdb > backups/appdb-$(date +%Y%m%d).dump
# restore into a new database in a new container/volume
docker volume create pgdata-new
docker run -d --name pg-new -e POSTGRES_PASSWORD=pw -v pgdata-new:/var/lib/postgresql/data postgres:16
docker exec pg-new createdb -U postgres appdb
docker exec -i pg-new pg_restore -U postgres -d appdb < backups/appdb-20261006.dump
docker exec pg-new psql -U postgres -d appdb -c "select count(*) from t;"
```

```text
 count 
-------
     1
```

`-Fc` (custom format) allows parallel and selective restore. For whole clusters use `pg_dumpall` or physical backups with `pg_basebackup` plus WAL archiving for point-in-time recovery.

### 5.6 MySQL and Redis Examples

```bash
# MySQL / MariaDB: consistent InnoDB dump without locking tables
docker exec mysql sh -c 'mysqldump --single-transaction --routines --all-databases -uroot -p"$MYSQL_ROOT_PASSWORD"' \
  > backups/mysql-all-$(date +%Y%m%d).sql

# Redis: trigger and copy an RDB snapshot
docker exec redis redis-cli SAVE
docker cp redis:/data/dump.rdb backups/redis-$(date +%Y%m%d).rdb
```

For production Redis prefer `BGSAVE` (non-blocking) and wait for `rdb_bgsave_in_progress:0` in `INFO persistence` before copying. `SAVE` blocks the server and suits only small or idle instances.

### 5.7 Cold Backup: Stop, Archive, Start

```bash
docker stop -t 60 pg
docker run --rm -v pgdata:/source:ro -v "$PWD/backups:/backup" alpine:3.20 \
  tar czf /backup/pgdata-cold-$(date +%Y%m%d).tar.gz --numeric-owner -C /source .
docker start pg
```

A clean stop makes the files consistent. Downtime equals the archive time, so this suits small data or maintenance windows.

### 5.8 Backing Up Via `--volumes-from`

```bash
docker run --rm --volumes-from pg -v "$PWD/backups:/backup" alpine:3.20 \
  tar czf /backup/pg-volumes.tar.gz /var/lib/postgresql/data
```

This reuses whatever mounts the container has, which is convenient but includes every volume and bind mount of that container and uses the container's absolute paths. Mounting the named volume directly (5.1) is more explicit.

### 5.9 Filesystem Snapshot (LVM Example, Linux Host)

```bash
# find where the volume lives
docker volume inspect pgdata --format '{{.Mountpoint}}'
# if /var/lib/docker is on LVM volume vg0/docker:
sudo lvcreate --snapshot --size 5G --name docker-snap /dev/vg0/docker
sudo mount -o ro /dev/vg0/docker-snap /mnt/snap
# copy /mnt/snap/volumes/pgdata/_data off-host, then:
sudo umount /mnt/snap && sudo lvremove -y /dev/vg0/docker-snap
```

A snapshot of a running database is crash-consistent: PostgreSQL recovers from WAL on restart, but you should still test it. For application-consistent snapshots, run `CHECKPOINT`, use `pg_backup_start`/`pg_backup_stop`, or briefly freeze writes. Cloud equivalents are EBS, Azure managed-disk or Persistent Disk snapshots.

### 5.10 Automating with Compose and Cron

```yaml
services:
  backup:
    image: alpine:3.20
    profiles: ["backup"]
    volumes:
      - pgdata:/source:ro
      - ./backups:/backup
    entrypoint: ["sh", "-c"]
    command: ["tar czf /backup/pgdata-$(date +%Y%m%d-%H%M%S).tar.gz -C /source ."]
volumes:
  pgdata:
    external: true
```

```bash
docker compose --profile backup run --rm backup
```

Inside the YAML `command`, the `$(date ...)` is evaluated in the container because the string is passed to `sh -c`; Compose only interpolates `${VAR}` forms, so use `$$` if you ever need a literal dollar before braces. Schedule with host cron or a systemd timer, and add retention (for example `find /backup -name '*.tar.gz' -mtime +14 -print` first to review, then delete deliberately).

### 5.11 Moving a Volume to Another Host

```bash
docker run --rm -v pgdata:/source:ro alpine:3.20 tar cf - -C /source . \
  | ssh user@newhost 'docker volume create pgdata && docker run --rm -i -v pgdata:/target alpine:3.20 tar xf - -C /target --numeric-owner'
```

Run the destination `docker volume create` and untar only against a volume that is new on the target host; verify with checksums on both ends.

## 6. Production Usage Notes

- **Define RPO and RTO first.** Nightly dumps give an RPO of up to 24 hours; WAL archiving or binlog shipping gives minutes; replication gives seconds.
- **3-2-1 rule:** three copies, two media, one off-site (object storage with versioning and object lock).
- **Choose per data type:** logical dump for databases, tar for static uploads and config, snapshots for large datasets, replication for availability.
- **Large volumes:** use incremental tools (`restic`, `borg`, `kopia`, `rclone`) from a helper container with the volume mounted read-only.
- **Pause or quiesce** non-database writers (`docker pause` is consistent for memory but does not flush application buffers; prefer application-level flush or stop).
- **Monitor backups:** alert on missing, small, or stale archives, and on failed jobs; a silent cron failure is a classic outage precursor.
- **Test restores on a schedule** into a scratch volume and run application smoke tests; record the measured restore time.
- **Back up what Compose does not hold:** the Compose file, `.env` structure (not secrets), image tags/digests, and secret references belong in version control.
- **Plain volumes do not carry across drivers:** NFS or cloud-backed volumes ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)) may already be snapshotted by the storage layer; confirm rather than assume.
- **Docker Desktop:** volumes live inside the VM disk image; use the helper-container tar method rather than copying the VM file.
- **Swarm and Kubernetes:** use CSI volume snapshots or tools such as Velero; the same principles (consistency, off-site, tested restore) apply ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)).

## 7. Security Considerations

- **Backups contain everything the volume contains**, including credentials, PII and keys. Encrypt archives at rest (`age`, `gpg`, or storage-side KMS) and in transit; restrict access to the backup location.
- **Mount sources read-only** and the backup destination as the only writable path.
- **Do not mount the host home directory or drive roots** into helper containers; mount only a dedicated backups directory.
- **Use pinned, minimal helper images** (digest-pinned alpine or a purpose-built backup image) and avoid pulling `latest` in backup jobs ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- **Secrets for dump tools:** pass database passwords through secrets, `.pgpass` or `_FILE` variables rather than command-line arguments visible in `ps` and `docker inspect` ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Immutable, off-account copies** (object lock, separate credentials) protect against ransomware and a compromised host deleting its own backups.
- **Restore into a quarantined volume first** when the archive's origin is not fully trusted; tar archives can carry unexpected paths and setuid files.
- **Retention equals exposure:** delete expired backups according to policy, and review whether regulated data may leave a region.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Restored database will not start, "invalid checkpoint record" | Archive of a live data directory | Use logical dump or cold/snapshot backup; try WAL replay only as a last resort |
| Restored files owned by wrong user, `permission denied` | Names mapped via helper image; no `--numeric-owner` | Re-extract with `--numeric-owner` as root, or `chown -R 999:999` in a helper |
| Archive contains an extra leading directory | Used absolute path instead of `-C dir .` | Re-create archive using `-C /source .` |
| Backup job exits 0 but file is tiny | Wrong volume name created an empty volume on the fly | Verify `docker volume ls`; use `external: true`; check size and file list in the job |
| `tar: file changed as we read it` | Writes during archive | Quiesce or stop the app; use dump or snapshot |
| Restore "worked" but data is old | Restored the wrong dated archive | Include timestamps and checksums; log what was restored |
| `pg_restore: error: role does not exist` | Dump references roles missing on target | Restore globals with `pg_dumpall --globals-only` first |
| Restore into non-empty volume refused by guard | Target already has data | Restore to a new volume, diff against the old, and choose deliberately |
| Backups fill the host disk | No retention; archives on same disk | Add retention and ship off-host |
| `docker cp` of Redis dump is stale | RDB not refreshed before copy | Run `BGSAVE` and wait for completion |
| Slow tar of many small files | Per-file overhead on overlay/bind mounts | Use snapshots or an incremental tool; exclude caches |

## 9. Best Practices

- Use application-level backups for databases, and file-level only when the app is stopped or the data is static.
- Restore only into new, empty volumes; compare, verify, then cut over.
- Mount sources read-only and name archives with timestamps and checksums.
- Preserve numeric ownership and permissions (`--numeric-owner`).
- Keep at least one copy off-host and one immutable copy.
- Automate, monitor, and test restores on a schedule; track measured RTO and RPO.
- Back up before upgrades, migrations and any `down -v` or prune operation.
- Keep volume names, mount paths and database versions documented next to the backup job.
- Encrypt archives and rotate backup credentials.
- Prefer one clear mechanism per data class over ad hoc scripts.

## 10. Common Anti-Patterns / Mistakes

- Never testing a restore.
- Copying `/var/lib/docker/volumes/...` directly from the host while the database runs.
- Storing backups on the same disk or same volume as the data.
- Extracting a restore archive directly over a live volume.
- Backing up only the volume and forgetting the Compose file, image tags and secrets references.
- Backing up with `docker commit` and expecting volume data to be included (volumes are excluded from images).
- Passing database passwords on command lines in cron jobs.
- Unbounded retention or no retention at all.
- Relying on `docker export` for state; it exports a container filesystem without volume contents.
- Assuming replication is a backup (it replicates deletions and corruption too).

## 11. Interview Questions

**🎯 Beginner:** _"How do you back up a Docker named volume, given there is no built-in command?"_
**Model answer:** Run a short-lived helper container that mounts the volume (read-only) plus a host backup directory, and have it create a tar archive: `docker run --rm -v vol:/source:ro -v "$PWD/backups:/backup" alpine tar czf /backup/vol.tar.gz -C /source .`. To restore, create a new empty volume and extract the archive into it with the same pattern. Check the archive listing and a checksum, and store a copy off the host.
_What the interviewer is probing for:_ Knowing the helper-container tar pattern and that volumes are reached through mounts, not through image commits.

**🎯 Intermediate:** _"Why is tarring a running PostgreSQL volume risky, and what are your alternatives?"_
**Model answer:** Postgres writes data files, WAL and control data continuously, so a file copy taken while it runs can capture a mix of states, leaving torn pages or a mismatched checkpoint; the failure shows up only when you try to restore. Safer options are `pg_dump` or `pg_dumpall` for a logical online backup, `pg_basebackup` with WAL archiving for physical backups and point-in-time recovery, stopping the container cleanly for a cold tar, or a storage snapshot (crash-consistent, relying on WAL replay). I would pick based on size and RPO: dumps for small or medium databases, base backup plus WAL for larger ones.
_What the interviewer is probing for:_ Consistency versus convenience, and knowing database-native tools.

**🎯 Senior:** _"Your restore procedure overwrites the target directory. Argue for or against it, and describe a safer restore workflow."_
**Model answer:** I would argue against restoring over existing data. If the restore is wrong (wrong date, wrong archive, partial corruption), overwriting destroys the only other copy and removes the ability to compare. The safer workflow: create a new empty volume, extract or load the backup there, refuse to proceed if the target is not empty, start a temporary container against it, run integrity checks and application smoke tests, then switch the service to the new volume (change the mount or rename via a controlled cutover). Keep the old volume until the new one has run successfully, then retire it deliberately. The same approach gives a repeatable restore drill and a measured RTO.
_What the interviewer is probing for:_ Operational caution, non-destructive recovery design, and restore rehearsal.

**🎯 Architect:** _"Design backup and recovery for 40 stateful containers across 10 hosts with RPO 15 minutes and RTO 1 hour for tier 1."_
**Model answer:** Classify workloads. For tier-1 databases use native continuous protection: WAL archiving or binlog shipping to versioned, encrypted, object-locked storage in another account, plus a streaming replica for fast failover; schedule base backups nightly. For files and config use a deduplicating tool (restic or kopia) from a read-only helper container, or storage snapshots on block volumes, with 15-minute cadence where RPO demands it. Drive everything from declarative labels on volumes so new volumes are discovered automatically, with a central scheduler, success metrics and alerts on staleness. Run automated weekly restore drills into scratch volumes with smoke tests, recording RTO; run a full-region exercise quarterly. Document runbooks, store keys separately from data, and define retention per compliance class. Where hosts are interchangeable, move to a platform with CSI snapshots (Kubernetes with Velero) rather than hand-managed scripts.
_What the interviewer is probing for:_ Mapping RPO/RTO to mechanisms, automation, verification, and security of backups at fleet scale.

## 12. Common Misconceptions

- "Replication or RAID is a backup." They copy mistakes and corruption instantly.
- "`docker commit` or `docker export` captures my volume data." Volumes are not part of images or container exports.
- "A file-level copy of a running database is fine." It is at best crash-consistent and often unusable.
- "Backups are done when the job succeeds." Only a verified restore proves it.
- "Restoring means extracting over the old data." Restore into a new volume and cut over.
- "Docker will warn me before deleting volumes." `down -v` and prune do not ask for second confirmation of content value.

## 13. 🔑 Key Takeaways

- There is no built-in volume backup; use a helper container with a read-only mount and `tar`, or application and storage tooling.
- Databases need logical dumps, cold backups or snapshots with WAL replay; avoid live file copies.
- Preserve numeric ownership; verify with listings and checksums.
- Restore into a new, empty volume, verify, then cut over; never extract over live data.
- Ship copies off-host, encrypt them, monitor jobs, and rehearse restores to measure RTO and RPO.

## 14. Related Concepts & What's Next

Related: persistence patterns ([§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)), named volumes ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), volume drivers ([§53](Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)), cleanup risks ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)), registry retention ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)), disaster recovery and rollback ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). Next, [§56](Section-56-Part7-Storage-Performance-Considerations.md) examines how storage choices affect throughput, latency and the cost of the backup methods above.

**Next Section:** [§56](Section-56-Part7-Storage-Performance-Considerations.md) — `Section-56-Part7-Storage-Performance-Considerations.md`
