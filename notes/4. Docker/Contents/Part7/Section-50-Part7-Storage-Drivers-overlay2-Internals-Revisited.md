# Section 50 (Part 7): Storage Drivers: overlay2 Internals Revisited

## 1. Definition

**Plain language:** A storage driver is the part of Docker that stacks read-only image layers and one thin writable layer into the single filesystem a container sees. It governs how image data is laid out on disk and what happens when a container modifies a file that came from an image.

**Precise definition:** A storage driver (graph driver) or, with the containerd image store, a containerd **snapshotter**, implements copy-on-write layering for image layers and the per-container writable layer. `overlay2` is the default and recommended driver on modern Linux. It uses the kernel's OverlayFS with `lowerdir` (the read-only layers, up to 128), `upperdir` (the container's writable layer), `workdir` (scratch space required by the kernel) and `merged` (the unified view mounted as the container root). Data written to the writable layer is **ephemeral**: it is deleted with the container. Persistent data belongs in volumes or bind mounts ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)). Section [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) introduced the mechanism; this section revisits it from the storage operator's angle: other drivers, copy-up cost, whiteouts, quotas, and the containerd snapshotter.

> 💡 **Tip:** Run `docker info --format '{{.Driver}}'` first. Most "storage" debugging starts with knowing which driver and backing filesystem you are actually on.

## 2. Why This Matters

- Writing heavily into the container layer is slower than writing to a volume and is lost on removal.
- Copy-up of a large file (a multi-GB database file baked into an image) stalls the first write and doubles disk use.
- `/var/lib/docker` fills disks, and the cause is often layers, dead containers or logs rather than volumes.
- Driver and backing filesystem mismatches (overlay2 on an unsupported filesystem, missing `d_type`) fail at daemon start.
- Docker Engine 29 and newer ships the containerd image store as the default for fresh installs, changing on-disk layout and `docker info` output you may already rely on.

## 3. Prerequisites and Dependencies

Requires the union filesystem model ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), image layers and content-addressable digests ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), and the dockerd/containerd/runc split ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). Daemon-level settings such as `data-root` and `storage-driver` live in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Mount namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) are what make the merged view appear as `/` inside the container. Image inspection tools are in [§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md).

## 4. Architecture / Conceptual Diagram

```text
  Container view (mounted at /var/lib/docker/overlay2/<id>/merged)
  ┌───────────────────────────────────────────────────────────────┐
  │                       merged  (what / looks like)             │
  └──────────────▲────────────────────────────────▲───────────────┘
                 │ reads fall through             │ writes land here
  ┌──────────────┴──────────────┐      ┌──────────┴───────────────┐
  │ lowerdir (read-only, shared)│      │ upperdir  (diff/)        │
  │  L3  app code    ◄── top    │      │  new files, copied-up    │
  │  L2  libs                   │      │  files, whiteouts        │
  │  L1  base OS     ◄── bottom │      ├──────────────────────────┤
  └─────────────────────────────┘      │ workdir   (work/)        │
     shared by every container         │  kernel scratch space    │
     started from the same image       └──────────────────────────┘

  Lookup order for a read:  upperdir ► L3 ► L2 ► L1   (first hit wins)

  Operations on the merged view
  ┌──────────────────┬───────────────────────────────────────────────┐
  │ read file in L1  │ served from lowerdir, no copy                 │
  │ modify file in L1│ COPY-UP whole file to upperdir, then modify   │
  │ create new file  │ written straight to upperdir                  │
  │ delete file in L1│ whiteout: char device 0/0 in upperdir         │
  │ delete directory │ opaque dir: xattr trusted.overlay.opaque="y"  │
  └──────────────────┴───────────────────────────────────────────────┘

  On disk: /var/lib/docker/overlay2/
     <layer-id>/diff   <layer-id>/link   <layer-id>/lower   <layer-id>/work
     l/  shortened symlinks (keeps mount option under the page-size limit)
```

- **Copy-up is whole-file**, not block-level: changing one byte of a 4 GB file copies 4 GB once (subsequent writes go to the copy).
- **Whiteouts** hide lower files without altering them; this is why deleting a file in a later `RUN` does not shrink the image.
- **Shared lowers:** ten containers from one image share one copy of every image layer; only the upper layers differ.
- **Driver choice** is per daemon, not per container. Changing it makes existing images and containers invisible until you switch back.

## 5. Hands-On

### 5.1 Identify Driver, Backing Filesystem and Image Store

```bash
docker info --format 'driver={{.Driver}} rootdir={{.DockerRootDir}}'
docker info | grep -iE 'storage driver|backing filesystem|supports d_type|native overlay diff|driver-type'
```

```text
driver=overlay2 rootdir=/var/lib/docker
 Storage Driver: overlay2
  Backing Filesystem: extfs
  Supports d_type: true
  Using metacopy: false
  Native Overlay Diff: true
  userxattr: false
```

On a containerd-image-store setup the output instead shows `Storage Driver: overlayfs` with `driver-type: io.containerd.snapshotter.v1`.

### 5.2 Look at a Container's Layers

```bash
docker run -d --name ov alpine:3.20 sleep 600
docker inspect ov --format '{{json .GraphDriver.Data}}' | tr ',' '\n'
```

```text
{"LowerDir":"/var/lib/docker/overlay2/ab12...-init/diff:/var/lib/docker/overlay2/9f3c.../diff"
"MergedDir":"/var/lib/docker/overlay2/ab12.../merged"
"UpperDir":"/var/lib/docker/overlay2/ab12.../diff"
"WorkDir":"/var/lib/docker/overlay2/ab12.../work"}
```

The `-init` layer holds files Docker injects such as `/etc/hosts` and `/etc/resolv.conf` placeholders.

### 5.3 Observe Copy-Up and Whiteouts

Inspect the upper layer on the Docker host (or inside a Linux VM for Docker Desktop):

```bash
docker exec ov sh -c 'echo changed >> /etc/os-release; rm /etc/motd; touch /new.txt'
UPPER=$(docker inspect ov --format '{{.GraphDriver.Data.UpperDir}}')
sudo ls -la "$UPPER" "$UPPER/etc"
docker diff ov
```

```text
/var/lib/docker/overlay2/ab12.../diff:
-rw-r--r-- 1 root root 0 ... new.txt
drwxr-xr-x 1 root root .. etc
/var/lib/docker/overlay2/ab12.../diff/etc:
-rw-r--r-- 1 root root 360 ... os-release        # copied up, then modified
c--------- 1 root root 0, 0 ... motd              # whiteout (character device 0/0)
C /etc
C /etc/os-release
D /etc/motd
A /new.txt
```

`docker diff` reports `A` (added), `C` (changed) and `D` (deleted), computed from the upper layer.

### 5.4 Why a Later `rm` Does Not Shrink an Image

```dockerfile
FROM alpine:3.20
RUN dd if=/dev/zero of=/big bs=1M count=200
RUN rm /big
```

```bash
docker build -t whiteout-demo .
docker history whiteout-demo
```

```text
IMAGE          CREATED BY                         SIZE
...            RUN /bin/sh -c rm /big             0B
...            RUN /bin/sh -c dd if=/dev/zero...  210MB
```

The 200 MB layer persists underneath a whiteout. Create and delete in the same `RUN`, or use a multi-stage build (see [§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)).

### 5.5 Measure the Writable Layer

```bash
docker ps -s --format 'table {{.Names}}\t{{.Size}}'
docker system df -v | head -30
```

```text
NAMES   SIZE
ov      12.3kB (virtual 7.8MB)
```

`size` is the writable layer; `virtual` includes the shared read-only image layers.

### 5.6 Per-Container Disk Quotas (xfs and pquota)

The `overlay2.size` option caps the writable layer, but only when `/var/lib/docker` is on **xfs mounted with `pquota`**:

```bash
sudo mount -o pquota /dev/sdb1 /var/lib/docker       # or in /etc/fstab
docker run --rm --storage-opt size=2G alpine:3.20 df -h /
```

```json
{
  "storage-driver": "overlay2",
  "storage-opts": ["overlay2.size=20G"]
}
```

On ext4 the option errors out with `--storage-opt is supported only for overlay over xfs with 'pquota' mount option`.

### 5.7 Enabling the containerd Image Store

```json
{
  "features": { "containerd-snapshotter": true }
}
```

```bash
sudo systemctl restart docker
docker info -f '{{ .DriverStatus }}'
```

```text
[[driver-type io.containerd.snapshotter.v1]]
```

Images and containers from the classic store do not appear after switching. They remain on disk under the old driver directory; switching back restores them. Do not delete `/var/lib/docker/overlay2` to "clean up" before confirming which store you are on.

## 6. Production Usage Notes

- **Use overlay2** on a supported backing filesystem: ext4, or xfs with `ftype=1` (required for `d_type`). Docker rejects overlay2 on xfs created with `ftype=0`.
- **Put `data-root` on a dedicated disk or volume** with monitoring and alerts, so a layer storm does not fill the root filesystem.
- **Other drivers and when they appear:**

| Driver | Status | Notes |
|---|---|---|
| `overlay2` | Default, recommended | Kernel 4.0+ (5.x+ preferred), ext4 or xfs |
| `overlayfs` (containerd snapshotter) | Default for new installs on newer Engine releases, opt-in on 27/28 | Enables multi-platform images in the local store, lazy-pull plugins |
| `fuse-overlayfs` | Rootless fallback | Used on kernels without unprivileged overlay (pre-5.11); slower |
| `btrfs` / `zfs` | Supported | Use only when `data-root` already sits on that filesystem; snapshot-native |
| `vfs` | Works anywhere | No copy-on-write: full copy per layer, very slow and large; for testing |
| `devicemapper`, `aufs` | Removed | Migrate to overlay2 |

- **Rootless Docker** (see [§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)) on kernel 5.11+ uses native overlayfs with the `userxattr` option; older kernels fall back to fuse-overlayfs.
- **Docker Desktop** runs the daemon inside a Linux VM; the layers live in a virtual disk image, not in a path you can browse on the host.
- **Reclaiming space:** see the prune commands in [§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md). Container logs (json-file) sit outside the layers but also under `data-root` ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)).
- **Do not hand-edit** or run backup tools against `/var/lib/docker/overlay2` of a running daemon; the layout is an implementation detail.

## 7. Security Considerations

- **Writable layers are a persistence channel for attackers.** Combine a read-only root filesystem with tmpfs for scratch space ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Shared layers are shared by digest:** layers are immutable and content-addressed, so a poisoned layer cannot be silently altered, but a poisoned base image reaches every dependent image ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Secrets baked into any layer persist** even after a later `rm`, because the whiteout only hides the file. Use build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Host access to `/var/lib/docker` equals root access** to all container data; restrict it to root and exclude it from broad file shares and backup agents that may leak content.
- **A full disk is a denial of service.** A container with no writable-layer quota can fill the host. Use `--storage-opt size` on xfs/pquota, volumes with limits, or `--read-only`.
- **Historic overlayfs kernel CVEs** (privilege escalation through overlayfs in user namespaces, for example CVE-2021-3493 on some Ubuntu kernels) make kernel patching part of container security.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `/var/lib/docker` full, few containers | Dangling images, build cache, stopped containers, large json logs | `docker system df -v`, prune, set log rotation |
| `overlay2: the backing xfs filesystem is formatted without d_type support` | xfs created with `ftype=0` | Recreate filesystem with `mkfs.xfs -n ftype=1` |
| `--storage-opt is supported only for overlay over xfs with 'pquota'` | Backing fs is ext4 or lacks pquota | Move `data-root` to xfs mounted with `pquota` |
| Images vanish after daemon change | Switched driver or enabled containerd store | Revert the setting; old data is still on disk |
| First write to a large file is slow | Whole-file copy-up | Put the file on a volume or copy it in at start |
| `docker rmi` frees little space | Layers shared with other images | Expected; check `docker system df` SHARED SIZE |
| `too many levels of symbolic links` / mount failure with many layers | Over the 128 lower-layer limit or mount option length | Flatten layers (multi-stage build, squash) |
| Slow `docker build`/`pull` on NFS or network `data-root` | overlay2 on network filesystem | Move `data-root` to local block storage |

## 9. Best Practices

- Stay on overlay2 (or the containerd snapshotter) on ext4 or xfs with `ftype=1`; avoid exotic drivers without a clear reason.
- Place `data-root` on its own volume, monitor free space and inodes, and alert at 80 percent.
- Keep all runtime-mutated state out of the container layer: volumes for data, tmpfs for scratch ([§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)).
- Use `docker diff` and `docker ps -s` to audit unexpected writes, then fix the app or mount a path.
- Combine create-and-delete operations inside one `RUN`; prefer multi-stage builds for size.
- Rotate container logs (`max-size`, `max-file`) so they do not dominate `data-root`.
- Keep the kernel patched; overlayfs is kernel code.
- Treat the directory layout under `data-root` as private and never script against it.

## 10. Common Anti-Patterns / Mistakes

- Writing databases, uploads or caches into the container layer and treating the container as durable.
- Deleting `/var/lib/docker/overlay2/*` by hand to reclaim space, corrupting images and containers.
- Using `vfs` in production because overlay2 "did not work", instead of fixing the backing filesystem.
- Assuming `rm` in a later Dockerfile layer removes data from the image.
- Baking multi-gigabyte mutable files into an image, causing copy-up stalls.
- Storing `data-root` on network storage.
- Backing up `/var/lib/docker` with file-level tools while the daemon runs.
- Enabling the containerd store on a production host without a plan for existing images.

## 11. Interview Questions

**🎯 Beginner:** _"Where does data written inside a running container go, and what happens to it when the container is removed?"_
**Model answer:** Writes go to the container's thin writable layer, the OverlayFS `upperdir`, stacked on top of the read-only image layers. Reads fall through to lower layers when the file is not in the upper layer. When the container is removed, the writable layer is deleted and the data is gone, so anything that must survive belongs in a volume or bind mount. You can see what changed with `docker diff` and measure it with `docker ps -s`.
_What the interviewer is probing for:_ The ephemeral nature of the container layer and the layered read path.

**🎯 Intermediate:** _"You delete a 500 MB file in a late `RUN` step, yet the image is still 500 MB larger. Why, and what does copy-up have to do with runtime behavior?"_
**Model answer:** Layers are immutable. Deleting a file in a new layer writes a whiteout entry (a 0/0 character device) that hides the lower file; the original bytes remain in the earlier layer and are still pulled. The fix is to create and remove in the same `RUN`, or to use a multi-stage build and copy only the final artifacts. Copy-up is the runtime counterpart: when a container modifies a file that lives in a lower layer, overlay2 copies the entire file to the upper layer first, so a small edit to a huge file is slow once and duplicates the space. Hot, large, mutable files should be on a volume.
_What the interviewer is probing for:_ Immutability of layers, whiteouts, and the cost model of copy-on-write.

**🎯 Senior:** _"A host's root disk is 95 percent full and `/var/lib/docker` is the culprit. How do you find the cause and prevent it, without damaging running workloads?"_
**Model answer:** Start with `docker system df -v` to split images, containers (writable layers), volumes and build cache, then `docker ps -s` and `du` on the container log files, since json-file logs without rotation are a classic cause. Remove only unused objects with targeted prune commands, never by deleting overlay2 directories. Prevent recurrence with log rotation in `daemon.json`, moving `data-root` to a dedicated disk, per-container quotas via `--storage-opt size` on xfs with pquota (or `--read-only` plus tmpfs), alerting on space and inodes, and CI that flags images with oversized layers. Also check for volumes that grew legitimately, because those are not safe to prune.
_What the interviewer is probing for:_ Systematic diagnosis, safe cleanup, and preventive controls.

**🎯 Architect:** _"Your platform runs mixed hosts, including rootless developers' machines, xfs servers and Docker Desktop. How do you standardize storage behavior, and what is your position on the containerd image store?"_
**Model answer:** Standardize on overlay2 semantics: xfs `ftype=1` (with pquota where quotas matter) or ext4 on servers, local block storage for `data-root`, and a documented rule that application state never lives in the container layer. Accept that rootless uses native overlayfs on kernel 5.11+ or fuse-overlayfs on older kernels, with performance differences, and that Docker Desktop hides the layer store in a VM, so no tooling may depend on host paths. For the containerd image store, adopt it deliberately: it unlocks multi-platform images locally and snapshotter plugins, and is becoming the default on newer Engine releases, but it changes the on-disk store, so plan migration (images are re-pulled or re-loaded), test CI cache behavior, and pin the setting via configuration management. Add a conformance check that runs `docker info` on each host class and fails on drift.
_What the interviewer is probing for:_ Fleet-level driver standards, awareness of the snapshotter transition, and avoiding host-path coupling.

## 12. Common Misconceptions

- "Deleting a file in a later layer makes the image smaller." The earlier layer still carries it.
- "Containers each get a full copy of the image." Lower layers are shared; only the writable layer is per container.
- "Copy-up copies only the changed blocks." overlay2 copies the whole file.
- "Volumes and the container layer have the same performance." Volumes bypass the union filesystem.
- "devicemapper or aufs are still options." Both were removed from current Engine releases.
- "Changing the storage driver migrates my images." It does not; the old data is simply not visible.

## 13. 🔑 Key Takeaways

- overlay2 stacks read-only `lowerdir` layers with one writable `upperdir`; the merged view is the container root.
- Copy-up is whole-file; deletes are whiteouts; layers are immutable.
- The writable layer is ephemeral; persistent data goes to volumes.
- Quotas need xfs with `pquota`; overlay2 needs `d_type` (xfs `ftype=1`).
- The containerd snapshotter is the future default; switching stores hides existing images.
- Never manipulate `/var/lib/docker/overlay2` by hand.

## 14. Related Concepts & What's Next

Related: union filesystem fundamentals ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), image anatomy ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), disk cleanup ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)), storage performance ([§56](Section-56-Part7-Storage-Performance-Considerations.md)), read-only roots ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)). Next, [§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md) shows where data should live instead of the writable layer: volumes, bind mounts and tmpfs.

**Next Section:** [§51](Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md) — `Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md`
