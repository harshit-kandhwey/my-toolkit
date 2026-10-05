# Section 92 (Part 12): Disaster Recovery and Rollback Strategies

## 1. Definition

**Plain language:** Rollback is how you undo a bad release quickly. Disaster recovery (DR) is how you get the whole system back after something much worse: a lost host, a deleted volume, a corrupted database, a compromised registry or a vanished region. Containers make rollback easy, because images are immutable. They make DR deceptively easy to ignore, because the *data* and the *configuration* are not in the image.

**Precise definition:** A container platform has four recoverable layers. (1) **Artifacts**: images in registries, pinned by digest. (2) **Declarative state**: Dockerfiles, Compose/stack files, proxy and daemon config, environment templates, all in Git. (3) **Secrets and identities**: registry credentials, TLS keys, Swarm unlock keys, secret stores. (4) **Data**: named volumes, bind-mounted directories, databases, and Swarm Raft state in `/var/lib/docker/swarm`. Everything except layer 4 can be rebuilt from sources; layer 4 can only be restored from backups. Recovery is measured by **RTO** (recovery time objective: how long you may be down) and **RPO** (recovery point objective: how much data you may lose). A strategy is real only if its restore procedure has been rehearsed against those targets.

> 💡 **Tip:** Containers are cattle, volumes are pets. Plan for the pets.

## 2. Why This Matters

- Most real container outages are self-inflicted (a bad deploy, `docker system prune --volumes`, a deleted stack) and are fixed by rollback or restore, not by heroics.
- A container's writable layer and anonymous volumes vanish with `docker rm`; teams discover this during the incident.
- Backups that were never restored are not backups. Interviewers probe exactly this.
- The cost of preparing is small (pinned digests, scripted backups, a runbook), and the cost of improvising is measured in lost customer data.
- It ties together much of this course: tagging ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), cleanup ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)), volumes ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md), [§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)), registries ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)) and deployments ([§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).

## 3. Prerequisites and Dependencies

Requires volumes and persistence patterns ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md), [§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)), backup mechanics ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)), registry retention and tagging ([§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md), [§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), secrets handling ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), deployment patterns ([§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)) and Swarm state ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)). A good grasp of monitoring ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)) helps you detect when to roll back.

## 4. Architecture / Conceptual Diagram

```text
                     WHAT TO RECOVER                         HOW IT COMES BACK
 ┌───────────────────────────────────────────────┐   ┌───────────────────────────────────┐
 │ 1 Images        registry (digest-pinned)      │──►│ docker pull repo@sha256:...       │
 │ 2 Declarative   Git: compose.yaml, daemon.json│──►│ git clone + docker compose up -d  │
 │ 3 Secrets       vault / sealed store          │──►│ re-inject, rotate if exposed      │
 │ 4 Data          volumes, DB dumps, Raft state │──►│ RESTORE from verified backup      │
 └───────────────────────────────────────────────┘   └───────────────────────────────────┘
        rebuildable (1-3)                                  only restorable (4)

 ROLLBACK (minutes)                          DISASTER RECOVERY (hours)
 ─────────────────                           ─────────────────────────
 bad release detected                        host / region / volume lost
      │                                            │
      ▼                                            ▼
 re-point to previous digest ──► verify      provision new host (IaC) ──► restore data
 (data unchanged, or migration reversible)   ──► pull pinned images ──► start stack ──► verify

 Backup targets and time:
   RPO ◄────────── data lost ──────────► last good backup ......... failure
                                                       failure ......... service restored ► RTO
 Tiers:  local snapshot ► off-host copy ► off-site/immutable copy (3-2-1 rule)
```

- **Rollback is cheap only while data stays compatible.** After a destructive migration, rollback needs a restore.
- **3-2-1 rule:** three copies, two media types, one off-site (preferably immutable or write-once).
- **Restore-test loop:** back up, restore into a scratch environment, run a verification query, record elapsed time (this is your measured RTO).

## 5. Hands-On

Run restore drills against scratch volumes and scratch containers only. Every restore command below targets a *new, empty* volume; never restore over a volume that already holds data (compare first, then decide).

### 5.1 Make Rollback Possible: Digest Pinning and Release Records

```bash
docker buildx imagetools inspect registry.example.com/api:1.5.0 --format '{{.Manifest.Digest}}'
docker inspect api --format '{{.Image}} {{.Config.Image}}'
docker compose config --images
```

Record the digest of every release in Git (a `releases/` file, a GitOps manifest, or a deployment log). Tags can be repointed ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)); `repo@sha256:...` cannot.

```yaml
services:
  api:
    image: registry.example.com/api@sha256:3f1c...e9a2   # exact release, rollback = previous line in Git
```

### 5.2 Rollback with Compose

```bash
git revert <deploy-commit>        # or: git checkout <previous-tag> -- compose.yaml
docker compose pull
docker compose up -d              # recreates only services whose image reference changed
docker compose ps
```

Keeping the deploy definition in Git makes rollback a normal, reviewable change, and `docker compose up -d` is idempotent.

### 5.3 Rollback with Swarm

```bash
docker service rollback api                  # revert to PreviousSpec
docker service inspect api --format '{{json .PreviousSpec.TaskTemplate.ContainerSpec.Image}}'
```

Swarm remembers only one previous spec, so a second rollback toggles forward again. For deeper history, rely on Git, not the cluster.

### 5.4 Backing Up a Named Volume (Disposable Helper Container)

```bash
docker run --rm \
  -v app_data:/data:ro \
  -v "$PWD/backups":/backup \
  alpine:3.20 \
  tar czf /backup/app_data-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
sha256sum backups/app_data-*.tar.gz > backups/SHA256SUMS
```

The source volume is mounted read-only. This is crash-consistent only: for databases, prefer a logical dump (below) or stop the writer briefly.

### 5.5 Restoring into a New Volume and Verifying

```bash
docker volume create app_data_restore
docker run --rm \
  -v app_data_restore:/data \
  -v "$PWD/backups":/backup:ro \
  alpine:3.20 \
  sh -c 'tar xzf /backup/app_data-20261006-020000.tar.gz -C /data && ls -la /data | head'
docker run --rm -v app_data_restore:/data:ro alpine:3.20 du -sh /data
```

Restore to a *new* volume, point a scratch copy of the stack at it, verify, and only then decide how to cut over. If a volume with the same name already exists and differs, compare the contents (file lists, sizes, hashes) with the backup and decide per file; do not extract over it.

### 5.6 Database-Aware Backups (Prefer Logical Dumps)

```bash
# PostgreSQL: consistent dump while running
docker compose exec -T db pg_dump -U app -Fc appdb > backups/appdb-$(date +%F).dump
# restore into a scratch database
docker compose exec -T db createdb -U app appdb_restore_test
docker compose exec -T db pg_restore -U app -d appdb_restore_test --no-owner < backups/appdb-2026-10-06.dump
docker compose exec -T db psql -U app -d appdb_restore_test -c 'SELECT count(*) FROM orders;'
```

For MySQL use `mysqldump --single-transaction`. For point-in-time recovery (RPO of seconds), archive the WAL/binlog to off-host storage. Copying a live database's data directory with `tar` produces a possibly unusable backup.

### 5.7 Host and Daemon Configuration

Generate hosts with infrastructure as code and keep `daemon.json` in Git, so there is nothing to capture. As a cheap inventory, `docker volume ls`, `docker network ls` and `docker ps -a --format '{{.Names}} {{.Image}}'` redirected to files document what existed.

### 5.8 Swarm State Backup and Recovery

```bash
# on a manager, with the engine stopped (or on a drained manager), per Docker's documented procedure
systemctl stop docker
tar czf swarm-backup.tgz -C /var/lib/docker swarm
systemctl start docker
```

To restore: stop Docker on a fresh node, extract into `/var/lib/docker/swarm`, start Docker, then `docker swarm init --force-new-cluster --advertise-addr <ip>`. If autolock was enabled, you need the unlock key. Treat the archive as secret: it contains the Raft data, including secrets and CA keys ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)).

### 5.9 Registry as a Single Point of Failure

```bash
docker pull registry.example.com/api@sha256:3f1c...e9a2
docker tag registry.example.com/api@sha256:3f1c...e9a2 backup-registry.example.net/api:1.5.0
docker push backup-registry.example.net/api:1.5.0
docker save registry.example.com/api@sha256:3f1c...e9a2 | gzip > images/api-1.5.0.tar.gz
```

Mirror critical images to a second registry or keep `docker save` archives of the last known-good release, and scope retention policies so rollback targets are never garbage collected ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).

### 5.10 A Game-Day Drill

1. On a scratch host, deploy the stack from Git only.
2. Delete the scratch host (a throwaway VM, not a real server).
3. Provision a replacement from IaC, restore the latest backup into new volumes, pull pinned images, start the stack.
4. Run the verification queries, record elapsed time against the RTO, list what was missing from the runbook, fix it.

## 6. Production Usage Notes

- **Define RTO/RPO per service**, not per platform. A cache can have RPO = everything; a payments database cannot.
- **Backup schedule and retention:** daily full plus WAL/binlog archiving for databases; keep daily for 7-14 days, weekly for 4-8 weeks, monthly for a year (adjust for compliance). Encrypt and ship off-host automatically.
- **Immutable and separate:** store at least one copy where the production credentials cannot delete it (object-lock bucket, separate account), which also defends against ransomware.
- **Monitor backups:** alert on missing or undersized backups and on restore-test failures, not just on job exit codes.
- **Database-specific tooling wins:** pgBackRest, WAL-G, Percona XtraBackup, `mongodump`/snapshots. Use volume tar only for simple file data.
- **Cloud snapshots** (EBS, managed disks) are quick but crash-consistent; combine with application quiesce or logical dumps.
- **Rollback and migrations:** pair each release with a tested rollback plan including a down migration or a restore point taken just before the migration ([§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).
- **Runbooks beat memory:** keep the restore procedure next to the code, written for someone paged at 3 a.m. Include contact points and decision criteria for "roll back or fix forward".
- **Prune safely:** `docker system prune --volumes` and `docker volume prune` delete unreferenced volumes, including a stack's data when the stack is down. Never schedule them blindly ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).

## 7. Security Considerations

- **Backups contain everything**: database contents, credentials in config, Swarm secrets and CA keys. Encrypt at rest and in transit, restrict access, and audit restore operations.
- **Backup credentials should be write-only** for the producing host so a compromised application cannot delete history.
- **Restore into isolation first** when compromise is suspected: a backup taken after the intrusion may contain the attacker's persistence.
- **Rotate secrets after DR** if the cause was a breach or the secret store was exposed; recovered credentials equal exposed credentials.
- **Verify what you restore:** checksums for archives, signature and digest checks for images ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), so a poisoned registry tag or archive is not reintroduced.
- **Do not store the only copy of the unlock key or recovery key on the system it protects** (Swarm autolock key, encryption keys, vault unseal keys).
- **Access to DR tooling** (cloud consoles, registry admin) is highly privileged; use break-glass accounts with logging.
- **Image provenance in rollback:** only roll back to images that were signed and scanned; an old digest may carry a now-known vulnerability, so decide consciously ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Rollback pulls the wrong image | Mutable tag was repointed | Roll back by digest; stop reusing tags |
| `manifest unknown` on rollback | Retention policy or cleanup removed the old image | Keep N releases; mirror or `docker save` last-good |
| Data missing after `docker compose down -v` or prune | `-v` / `--volumes` deleted named volumes | Restore from backup; remove `-v` from routines, protect with `external: true` volumes |
| Restored DB container will not start | Copied live data directory (inconsistent), version mismatch | Restore from logical dump or proper base backup; match major version |
| Restore extracts files with wrong ownership | UID/GID differ, tar run without preserving ownership | Run restore container as root with `tar -p`; ensure same numeric IDs ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)) |
| Backup job "succeeds" but archive is empty | Wrong volume name (Compose prefixes project name) | `docker volume ls`; verify size and checksum in the job |
| Rollback works but app errors | Schema already migrated forward | Restore from pre-migration backup or run down migration; use expand/contract |
| Swarm restore comes up without secrets/services | Restored wrong directory or autolock key missing | Restore `/var/lib/docker/swarm` fully; supply unlock key |
| Containers start but data empty | Volume name or mount path changed, so a new empty volume was created | Compare `docker inspect` mounts with the backup layout |

## 9. Best Practices

- Pin releases by digest and record every deployed digest in Git.
- Keep all runtime configuration (Compose, proxy, daemon config) in version control; rebuild hosts from IaC.
- Treat volumes as the only irreplaceable layer: name them, back them up, and keep them `external` where deletion would hurt.
- Prefer application-aware backups (logical dumps, WAL archiving) for databases.
- Follow 3-2-1 with an immutable off-site copy and encryption.
- Rehearse restores on a schedule and record measured RTO and RPO.
- Take a restore point before every risky migration.
- Retain at least the last several releases in the registry and mirror critical images.
- Write short, tested runbooks with explicit rollback criteria.
- Alert on backup freshness and size, not only on job failure.

## 10. Common Anti-Patterns / Mistakes

- Never testing a restore.
- Backing up the container or image but not the volumes.
- Copying a running database's data directory.
- Backups on the same host or credentials as production.
- Mutable tags, so "previous version" is undefined.
- `docker system prune -a --volumes` or `compose down -v` in production automation.
- Anonymous volumes for important data.
- Assuming rollback is safe after a schema change.
- A single registry with no second copy.

## 11. Interview Questions

**🎯 Beginner:** _"What survives when you delete a container, and what does not? What does that mean for backups?"_
**Model answer:** The image survives (it is shared and immutable), and so do named volumes and bind-mounted host directories. The container's writable layer and any anonymous volumes are removed with it, so anything the app wrote there is lost. For backups this means you back up volumes and databases, plus the Compose and config files in Git, but you do not back up containers. Images should be recoverable from a registry; you can always rebuild or re-pull them. The one irreplaceable thing is the data, so I name volumes explicitly and test restoring them.
_What the interviewer is probing for:_ The container/image/volume persistence model and where state lives.

**🎯 Intermediate:** _"How would you back up and restore a PostgreSQL database running in a container with a named volume?"_
**Model answer:** Prefer a logical backup that is consistent while the database runs: `docker exec` or `compose exec` with `pg_dump -Fc`, written to a file outside the container, checksummed, and copied off-host. For stricter RPO I archive WAL with a tool such as pgBackRest or WAL-G for point-in-time recovery. A tar of the volume is acceptable only with the database stopped or via a filesystem snapshot, because a live copy can be inconsistent. To restore, create a new volume or scratch container, load the dump with `pg_restore`, run verification queries, then cut over. I would match the major PostgreSQL version and rehearse the whole process regularly to know the real RTO.
_What the interviewer is probing for:_ Consistency awareness and a tested restore procedure.

**🎯 Senior:** _"A deployment included a destructive migration and errors are climbing. Rolling the image back doesn't fix it. What now, and how do you prevent it?"_
**Model answer:** First, stop the damage: shift traffic away or put the service in maintenance mode, and decide whether to fix forward or restore, based on data written since the migration. If a down migration exists and is safe, run it, then roll back the image by digest. Otherwise restore from the backup or snapshot taken just before the migration into a scratch instance, validate it, and replay or reconcile writes made afterwards (from WAL/PITR or application logs) as far as the RPO allows. Communicate impact, then do a blameless review. Prevention: expand/contract migrations so the old version always works with the new schema, never dropping or renaming in the same release as the code change, a mandatory restore point before migrations, migration CI checks against the previous app version, and canary releases ([§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).
_What the interviewer is probing for:_ Incident judgment and understanding that code rollback does not roll back data.

**🎯 Architect:** _"Design DR for a Docker-based platform on three hosts with a Swarm cluster, a Postgres primary, a private registry and secrets. RTO 1 hour, RPO 5 minutes."_
**Model answer:** Separate the layers. Infrastructure: hosts defined in IaC, reproducible in a second zone or region. Declarative state: stacks, daemon config and proxy config in Git, deployed by pipeline from digests. Images: the registry itself is replicated or mirrored to a second registry, with retention that protects release digests; CI can rebuild from source as a last resort. Secrets: stored in an external secrets manager with its own replication, not only in the Swarm Raft store; Swarm state is backed up regularly and the autolock key stored in a vault. Data: Postgres with streaming replication to a standby in another zone and continuous WAL archiving to an immutable object store, giving an RPO under five minutes, plus daily base backups and logical dumps. Recovery path: promote the standby, bring up a new Swarm from IaC, restore or re-init, deploy pinned digests, switch DNS or the load balancer. Validate with quarterly game days that measure RTO against the one-hour target, monitoring of replication lag and backup freshness, and a documented decision tree for rollback versus failover.
_What the interviewer is probing for:_ Layered thinking, concrete RTO/RPO mapping to mechanisms, and operational proof through drills.

## 12. Common Misconceptions

- "Containers are stateless so there's nothing to back up." Volumes, databases and cluster state are very stateful.
- "Rollback = deploy the previous tag." Only if the tag is immutable still available, and data is compatible.
- "Replication is a backup." It replicates deletes and corruption as well; you need point-in-time backups.
- "Snapshots of the volume are always consistent." They are crash-consistent at best.
- "`docker compose down` deletes my data." It does not, unless `-v` is used; `down -v` and `volume prune` do.
- "A successful backup job means a usable backup." Only a restore test proves it.

## 13. 🔑 Key Takeaways

- Images, config, and secrets are rebuildable; data is only restorable.
- Roll back by immutable digest, with the deploy definition in Git.
- Rollback fails after destructive migrations: use expand/contract and take restore points.
- Use application-aware backups for databases; keep an off-site, immutable, encrypted copy.
- Rehearse restores; measured RTO and RPO matter more than designed ones.
- Guard against self-inflicted loss: `down -v`, `volume prune`, and registry cleanup.

## 14. Related Concepts & What's Next

Related: volume backup mechanics ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)), persistence patterns ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)), registry retention ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)), secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), Swarm state ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)) and zero-downtime releases ([§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)). Next, [§93](Section-93-Part12-Troubleshooting-Production-Container-Issues.md) turns to diagnosing live production container problems, the skill you need when rollback or recovery is on the table.

**Next Section:** [§93](Section-93-Part12-Troubleshooting-Production-Container-Issues.md) — `Section-93-Part12-Troubleshooting-Production-Container-Issues.md`
