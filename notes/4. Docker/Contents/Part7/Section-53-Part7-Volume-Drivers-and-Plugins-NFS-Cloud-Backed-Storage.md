# Section 53 (Part 7): Volume Drivers and Plugins: NFS and Cloud-Backed Storage

## 1. Definition

**Plain language:** A volume driver decides where a volume's bytes actually live. The built-in `local` driver uses a directory on the host, but it can also mount an NFS share, and third-party plugins can back volumes with cloud disks, SAN arrays or distributed filesystems.

**Precise definition:** Docker volumes are created and mounted through a driver API. The `local` driver is built into `dockerd` and accepts mount-style options (`type`, `o`, `device`) that it passes to the Linux `mount` call, which is how NFS, CIFS, tmpfs and bind-backed volumes work without any plugin. Out-of-process **volume plugins** implement the Docker volume plugin protocol (`VolumeDriver.Create`, `Mount`, `Unmount`, `Remove`, `Get`, `List`, `Path`, `Capabilities`). Managed plugins (the "v2" plugin system) are distributed as images, installed with `docker plugin install`, and run by the daemon in their own root filesystem; legacy plugins run as a separate process or container listening on a Unix socket under `/run/docker/plugins/`. The driver is chosen per volume, and volume options are fixed at creation time.

> 💡 **Tip:** Before looking for a plugin, check whether `--driver local` with `type=nfs` already does the job. For plain NFS or EFS it does.

## 2. Why This Matters

- Local volumes are tied to one host. When a container must move between hosts, or several containers on different hosts need the same files, you need storage that is reachable over the network.
- Choosing the wrong backend causes the hardest class of storage bugs: stale file handles, locking failures, silent data corruption from two writers, and 10x latency on database workloads.
- Plugin-based storage runs with root privileges inside the Docker host trust boundary, so selection is a security and supply-chain decision, not just a performance one.
- Most cloud setups map to a handful of patterns (NFS/EFS for shared files, block volumes for single-writer databases), and interviewers expect you to know which fits which.

## 3. Prerequisites and Dependencies

Requires named volume lifecycle ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), the mount-type comparison ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)) and the daemon's role in launching containers ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). NFS needs basic networking ([§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md)): TCP 2049 reachable from the Docker host, and the `nfs-common` / `nfs-utils` client package installed on the host (the mount happens in the host's mount namespace, not in the container). Compose usage builds on [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md). Performance trade-offs continue in [§56](Section-56-Part7-Storage-Performance-Considerations.md) and persistence design in [§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md).

## 4. Architecture / Conceptual Diagram

```text
   docker run -v appdata:/data ...
                │
                ▼
         ┌─────────────┐   volume record: name, driver, options
         │   dockerd   │──────────────────────────────┐
         └──────┬──────┘                              │ driver = ?
                │                                     ▼
     ┌──────────┴───────────────┐        ┌────────────────────────────┐
     │ built-in "local" driver  │        │ plugin (managed or legacy) │
     │  mount(2) with type/o/   │        │  JSON over unix socket:    │
     │  device from volume opts │        │  Create / Mount / Unmount  │
     └──────────┬───────────────┘        └──────────────┬─────────────┘
                │                                       │
      ┌─────────┼─────────┬──────────┐                  ▼
      ▼         ▼         ▼          ▼           cloud API / SAN / FUSE
  host dir    NFS       CIFS      tmpfs          (EBS, Azure Files, sshfs,
  (default)  server     share                     Ceph, Portworx ...)
                │
                ▼
     host mount point  ──►  bind into container mount namespace at /data

   Where NFS is mounted:  HOST namespace first, then bind-mounted into the
   container. The container needs no NFS client; the host does.

   Placement guide
   ┌──────────────────────┬───────────────────────────┬──────────────────┐
   │ Need                 │ Typical backend           │ Writers          │
   ├──────────────────────┼───────────────────────────┼──────────────────┤
   │ Shared files, CMS    │ NFS / AWS EFS / Azure Files│ many             │
   │ Single database      │ Block (EBS, PD, local SSD)│ one              │
   │ Scratch / cache      │ tmpfs or local            │ one              │
   │ Pod mobility at scale│ Kubernetes CSI, not Docker│ per PV mode      │
   └──────────────────────┴───────────────────────────┴──────────────────┘
```

- **Create does not mount.** For `local` with NFS options, `docker volume create` only records options. The mount occurs when a container using it starts, so a bad server name surfaces at `docker run`, not at create time.
- **Options are immutable.** To change the server or mount options, remove the volume and create it again.
- **Lazy host mount:** the mount is removed when the last container using the volume stops.

## 5. Hands-On

### 5.1 NFS Volume with the Local Driver

```bash
docker volume create --driver local \
  --opt type=nfs \
  --opt o=addr=10.0.1.20,rw,nfsvers=4.1,hard,timeo=600,retrans=2 \
  --opt device=:/exports/appdata \
  appdata
docker volume inspect appdata --format '{{json .Options}}'
docker run --rm -v appdata:/data alpine:3.20 sh -c 'echo ok > /data/probe && ls -l /data'
```

```text
{"device":":/exports/appdata","o":"addr=10.0.1.20,rw,nfsvers=4.1,hard,timeo=600,retrans=2","type":"nfs"}
total 4
-rw-r--r--    1 root     root             3 Oct  6 09:30 probe
```

Note the leading colon in `device=:/exports/appdata`; the server address goes in `o=addr=`. If the NFS client packages are missing on the host you will see `mount: ... bad option; for several filesystems (e.g. nfs, cifs) you might need a /sbin/mount.<type> helper program`.

### 5.2 The Same Thing with `--mount` (No Pre-Created Volume)

```bash
docker run --rm \
  --mount 'type=volume,src=appdata2,dst=/data,volume-driver=local,volume-opt=type=nfs,volume-opt=device=:/exports/appdata,"volume-opt=o=addr=10.0.1.20,rw,nfsvers=4.1"' \
  alpine:3.20 ls /data
```

Quote any `volume-opt` value that contains a comma so the CSV parser keeps it whole.

### 5.3 Compose with NFS and with AWS EFS

```yaml
services:
  web:
    image: nginx:1.27
    volumes:
      - uploads:/usr/share/nginx/html/uploads
volumes:
  uploads:
    driver: local
    driver_opts:
      type: nfs
      o: "addr=fs-0abc1234.efs.eu-west-1.amazonaws.com,nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport"
      device: ":/"
```

EFS speaks NFSv4.1 on port 2049 and needs a security group that allows it from the instance. For encryption in transit, mount through the `amazon-efs-utils` helper on the host (`type=efs`, `o=tls`) or use a tunnel; plain NFS is unencrypted.

### 5.4 CIFS/SMB and tmpfs via Local Driver

```bash
docker volume create --driver local \
  --opt type=cifs --opt device=//fileserver/share \
  --opt o=username=svc_app,password=REDACTED,uid=1000,gid=1000,vers=3.0 smbdata

docker volume create --driver local \
  --opt type=tmpfs --opt device=tmpfs --opt o=size=128m,mode=1777 ramscratch
```

Putting a password in `o=` stores it in the volume record (visible to `docker volume inspect`). Prefer a credentials file readable only by root and `o=credentials=/etc/smb.cred`.

### 5.5 Installing and Managing a Managed Plugin

```bash
docker plugin install --grant-all-permissions vieux/sshfs
docker plugin ls
docker plugin inspect vieux/sshfs --format '{{.Config.Interface.Types}}'
docker volume create -d vieux/sshfs -o sshcmd=user@10.0.1.30:/srv/data -o password=REDACTED sshvol
docker run --rm -v sshvol:/data alpine:3.20 ls /data
```

```text
ID             NAME                  DESCRIPTION               ENABLED
a1b2c3d4e5f6   vieux/sshfs:latest    sshFS plugin for Docker   true
[{docker.volumedriver/1.0}]
```

Without `--grant-all-permissions` the CLI prints the plugin's requested privileges (network, `SYS_ADMIN` capability, host devices) and asks you to approve them. Read that list; it is the plugin's security profile.

### 5.6 Lifecycle of a Plugin

```bash
docker plugin disable vieux/sshfs     # fails if volumes are in use; -f to force
docker plugin set vieux/sshfs DEBUG=1
docker plugin enable vieux/sshfs
docker plugin upgrade vieux/sshfs vieux/sshfs:latest
docker plugin rm vieux/sshfs
```

Volumes created with a plugin stay registered in the daemon. If the plugin is removed, those volumes become unusable until it is back (and may block `docker volume rm`).

### 5.7 Which Driver Owns a Volume

```bash
docker volume ls --format '{{.Driver}}\t{{.Name}}'
docker volume ls --filter driver=vieux/sshfs
docker plugin ls --format '{{.Name}} {{.Enabled}}'
```

### 5.8 Observing the Host Mount

```bash
docker run -d --name w -v appdata:/data alpine:3.20 sleep 600
findmnt -t nfs4                 # run on the Docker host
docker rm -f w
findmnt -t nfs4                 # the mount is gone
```

```text
TARGET                                              SOURCE                    FSTYPE OPTIONS
/var/lib/docker/volumes/appdata/_data               10.0.1.20:/exports/appdata nfs4  rw,relatime,vers=4.1,hard,...
```

### 5.9 Common Cloud Patterns Without a Plugin

- **AWS:** EFS through the NFS recipe above for shared files. EBS volumes are single-attach block devices: attach, format and mount on the host (or use a `local` volume with `type=none,o=bind,device=/mnt/ebs/data`), and handle failover with your own automation or move to ECS/EKS with their native volume integrations.
- **Azure:** Azure Files over SMB 3 with the CIFS recipe, or via the cloud's Docker integration.
- **GCP:** Filestore over NFS; Persistent Disk as a mounted host path.
- **Bare metal:** NFS from a NAS, or Ceph/GlusterFS mounted on the host and exposed with `type=none,o=bind`.

## 6. Production Usage Notes

- **Single writer for databases.** Run databases on block storage with a single writer. NFS is acceptable for some engines under strict conditions (hard mounts, NFSv4, supported by the vendor) but is a classic cause of corruption and poor fsync latency ([§56](Section-56-Part7-Storage-Performance-Considerations.md)).
- **Use `hard` mounts for writable data.** `soft` can return I/O errors mid-write and corrupt files; `hard` blocks until the server is back, so also set `timeo`/`retrans` sensibly and monitor for hung processes (`D` state).
- **Prefer NFSv4.1+** (one port, better locking and recovery). Pin the version with `nfsvers=`.
- **Boot ordering:** the container may start before the network or NFS server is ready. Combine `restart: unless-stopped`, health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)) and dependencies ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)).
- **UID/GID mapping:** NFS authorizes by numeric IDs (AUTH_SYS). The container's UID must match the export's permissions; `root_squash` turns container root into `nobody`, so root-owned paths become unwritable. Align IDs, or use `all_squash` with `anonuid`/`anongid`, or Kerberos for real identity.
- **Plugin selection checklist:** actively maintained, signed or from a known publisher, supports your Engine and cgroup/OS version, documented failure behavior. Many once-popular plugins are archived (for example REX-Ray, Docker's Cloudstor); verify status before adopting.
- **Plugins are host-global.** Install and upgrade them on every Docker host in the fleet, and keep versions aligned.
- **At scale prefer an orchestrator.** Kubernetes CSI drivers provide provisioning, attach/detach, snapshots and topology awareness that the Docker volume API does not.
- **Back up what the remote storage does not:** an NFS export is still one logical copy; use server-side snapshots ([§55](Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).

## 7. Security Considerations

- **Managed plugins run privileged-ish.** They commonly request `CAP_SYS_ADMIN`, host network and `/dev` access. A malicious or compromised plugin controls every volume mount on the host, which is effectively root on that host.
- **Pin and verify plugin sources.** Use a specific tag or digest (`docker plugin install name@sha256:...`), prefer vendor-maintained images, and review the privilege prompt rather than blanket `--grant-all-permissions` outside a lab. See [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md).
- **Credentials in `docker volume inspect`.** Options such as `password=` are stored in plain text in the volume record and visible to anyone with Docker API access. Use credential files, instance roles or Kerberos keytabs on the host instead.
- **NFS is unauthenticated by default and unencrypted.** Restrict exports to specific host IPs, put them on a private network, use a security group or firewall, and use TLS (EFS mount helper, NFS over TLS in newer kernels/servers) or an overlay such as WireGuard.
- **`root_squash` and `nosuid,nodev,noexec`:** mount shared data with `nosuid,nodev` (and `noexec` when nothing should execute from it) to limit what a compromised container can do through the share.
- **Blast radius:** a shared writable volume lets one compromised container tamper with data used by others. Segment exports per application.
- **Docker socket access equals access to every volume driver,** so protect it ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `bad option; ... need a /sbin/mount.nfs helper` | NFS client not installed on the host | Install `nfs-common` / `nfs-utils` on the Docker host |
| `mount ... permission denied` at `docker run` | Export does not allow this client IP, or wrong path | Check `/etc/exports`, `showmount -e server`, security groups |
| `connection timed out` | Port 2049 blocked, wrong `addr` | Test with `nc -zv server 2049`; fix routing/firewall |
| Volume creation succeeded but run fails | Create only records options; mount happens later | Validate by running a test container right after create |
| Wrong server/option, cannot edit | Volume options are immutable | `docker volume rm` then recreate with correct options |
| Files owned by `nobody:nogroup` | `root_squash` or ID mismatch | Align UID/GID, adjust export squash settings |
| `Stale file handle` | Export path replaced or server restarted without state | Remount (stop containers using it), prefer NFSv4, avoid recreating exports |
| Processes hang in `D` state | `hard` mount with server outage | Restore server/network; plan HA for the NAS |
| `error looking up volume plugin` | Plugin not installed or disabled on this host | `docker plugin ls`; install/enable on every host |
| `plugin disable` fails | Volumes from it still in use | Stop containers; use `-f` only after understanding impact |
| SQLite/DB locks misbehave on NFS | Weak lock semantics on network FS | Move that data to local/block storage |
| Slow fsync on database | NFS write latency | Use block storage; tune `rsize/wsize` only for throughput workloads |

## 9. Best Practices

- Start with the `local` driver and NFS options; add a plugin only for a feature the host mount cannot give you.
- Declare network volumes in Compose with `driver_opts` so configuration is versioned.
- Pin NFS version, use `hard`, set explicit `timeo`/`retrans`, add `nosuid,nodev`.
- Keep credentials out of volume options; use files or host-level identity.
- One writer per volume unless the application is built for shared access.
- Pre-test with a throwaway container immediately after creating any network volume.
- Version-pin plugins by digest, review requested privileges, and manage them as fleet configuration.
- Use server-side snapshots and separate backups for network-backed data.
- Monitor mount health and latency, not only container status.

## 10. Common Anti-Patterns / Mistakes

- Running a production database on an NFS share without vendor support and tested failover.
- Using `soft` mounts for writable application data.
- Embedding SMB or SSHFS passwords in `docker volume create` commands and shell history.
- Installing plugins with `--grant-all-permissions` from unvetted publishers.
- Assuming a network volume makes a container "portable" while the app still needs a single writer or specific hosts.
- Installing the plugin on one node and forgetting the others, then wondering why rescheduled containers fail.
- Mounting a whole NFS export root read-write into many unrelated containers.
- Depending on abandoned plugins for critical data paths.

## 11. Interview Questions

**🎯 Beginner:** _"How can you make a Docker volume use an NFS share, and do you need a plugin?"_
**Model answer:** No plugin is needed. The built-in `local` driver passes mount options to the kernel, so you create the volume with `--driver local --opt type=nfs --opt o=addr=<server>,rw,nfsvers=4.1 --opt device=:/export/path`, or the equivalent `driver_opts` in Compose. The Docker host must have the NFS client package installed because the mount is performed on the host and then bind-mounted into the container. The volume is only actually mounted when a container using it starts.
_What the interviewer is probing for:_ Knowing that `local` supports NFS and where the mount really happens.

**🎯 Intermediate:** _"You create an NFS-backed volume successfully, but `docker run` fails with a mount error. How do you debug it?"_
**Model answer:** Creation only stores options, so the failure is in the mount at container start. I would check on the host that the NFS client is installed, that the server is reachable on TCP 2049 (`nc -zv`), that `showmount -e` or the server's exports permit this client IP, and that the `addr`, `device` path (with the leading colon) and `nfsvers` are right. I would try the same mount manually with `mount -t nfs4 ...` to get the real kernel error, then fix the cause. Because volume options are immutable, I would remove and recreate the volume with corrected options. I would also check security groups or firewalls and whether `root_squash` explains permission errors after the mount succeeds.
_What the interviewer is probing for:_ Understanding create-versus-mount timing and a systematic, host-level debugging approach.

**🎯 Senior:** _"A team wants to put PostgreSQL's data directory on an EFS-backed Docker volume so the container can move between hosts. What is your response?"_
**Model answer:** I would push back. A database needs low-latency fsync, correct POSIX locking and exactly one writer; NFS adds latency, weaker semantics under failure, and noisy-neighbour variability, and a rescheduled container could briefly overlap with the old one and cause corruption. Mobility alone is not worth that risk. Better options are block storage (EBS) attached to the host running the database with controlled failover, a managed database service, or replication (streaming replicas with promotion) so each node has local data. EFS is a good fit for shared uploads, static content and build artifacts. If they insist, require single-writer fencing, `hard` NFSv4.1 mounts, vendor-support confirmation, and measured fsync benchmarks.
_What the interviewer is probing for:_ Matching storage semantics to workload, and spotting split-brain/double-writer risks.

**🎯 Architect:** _"Define the storage strategy for a fleet of Docker hosts running mixed stateless and stateful services, including when you introduce volume plugins."_
**Model answer:** Classify data by access pattern: ephemeral (tmpfs/local), single-writer durable (block storage with backups and snapshots), and shared files (NFS/EFS with per-app exports). Use the `local` driver with declared options for all three wherever possible, since it needs no extra software. Introduce a plugin only when a required capability is missing, such as dynamic provisioning or snapshots from a specific array, and then vet it for maintenance status, privileges, supported Engine versions and rollback, pin it by digest, and deploy it through configuration management to every host. Document failure modes (NAS outage with hard mounts, plugin crash), health-check mounts, and test restores. For anything needing automated rescheduling, topology awareness or snapshots at scale, move to Kubernetes with a CSI driver rather than extending the Docker volume API. Encrypt in transit and at rest, and keep credentials out of volume records.
_What the interviewer is probing for:_ Pragmatic layering, supply-chain and operational risk management, and knowing the limits of Docker's volume abstraction.

## 12. Common Misconceptions

- "You need a plugin for NFS." The `local` driver handles it.
- "The container mounts the NFS share." The host mounts it and Docker bind-mounts it in; the container needs no client.
- "`docker volume create` validates the connection." It only records options.
- "Network volumes make stateful apps safely mobile." Locking, latency and single-writer constraints still apply.
- "Volume options can be edited later." They are fixed; recreate the volume.
- "Volume plugins are sandboxed." They are privileged components of the host's trust boundary.

## 13. 🔑 Key Takeaways

- `local` driver plus `type=nfs|cifs|tmpfs` covers most network and special-purpose volumes.
- The NFS client must be on the Docker host; mounting happens lazily at container start.
- Options are immutable; credentials in options are visible via inspect.
- Plugins are installed per host, run with powerful privileges, and many are unmaintained, so vet and pin them.
- Match backend to workload: shared files on NFS/EFS, databases on block storage with one writer.
- For fleet-scale stateful scheduling, use Kubernetes CSI rather than Docker volume plugins.

## 14. Related Concepts & What's Next

Related: named volume management ([§52](Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), mount types ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), daemon trust and socket ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), plugin supply chain ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), cloud registries and platforms ([§68](../Part9/Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)). Next, [§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md) applies these building blocks to concrete persistence patterns for databases, queues and other stateful containers.

**Next Section:** [§54](Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md) — `Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md`
