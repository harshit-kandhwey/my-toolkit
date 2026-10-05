# Section 13 (Part 2): Union Filesystems and Layered Storage (overlay2 Internals)

## 1. Definition

**Plain language:** A Docker image is not one big disk image. It is a stack of read-only layers, and a running container adds one thin writable layer on top. A union filesystem presents that whole stack to the container as a single ordinary directory tree. Layers are shared between images and containers, so ten containers from the same image do not need ten copies of the image on disk.

**Precise definition:** A **union filesystem** merges multiple directories (branches) into one logical view. **overlay2** is Docker's default storage driver on modern Linux. It is built on the kernel's **OverlayFS** (mainline since Linux 3.18; overlay2 needs kernel 4.0+, and Docker documents 4.0+ as the minimum). OverlayFS mounts with four parameters:

- `lowerdir`: one or more read-only directories (the image layers), colon-separated, topmost first.
- `upperdir`: the single writable directory (the container layer).
- `workdir`: a scratch directory on the same filesystem as `upperdir`, used for atomic operations.
- `merged`: the mountpoint where the unified view appears, and which becomes the container's root filesystem.

The mechanism that makes it efficient is **copy-on-write (CoW)**: a file from a lower layer is copied to the upper layer only when the container first modifies it. Deletions are recorded as **whiteout** files (character device 0/0), and deleted-directory markers use the `trusted.overlay.opaque` xattr.

> 💡 **Tip:** Think of overlay2 as transparent sheets stacked on a projector. You see the topmost sheet's content wherever it has ink, and lower sheets show through elsewhere. Writing means drawing on the top sheet only.

## 2. Why This Matters

- **Disk usage.** Shared read-only layers are why `docker pull` of a second image built on the same base downloads only the differing layers.
- **Startup speed.** Creating a container does not copy the image; it just adds an empty upper layer and mounts it. That is why containers start in milliseconds.
- **Write performance.** The first write to a large file in a lower layer copies the entire file up (file-level CoW, not block-level). A container that appends to a 2 GB log file baked into the image pays a 2 GB copy.
- **Dockerfile design.** Layer order and content determine cache reuse, image size, and whether deleted secrets are still recoverable ([§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) explains why `RUN rm` in a later layer does not shrink or scrub an earlier one).
- **Troubleshooting.** "No space left on device" on a Docker host is usually `/var/lib/docker/overlay2` growing, and knowing the directory layout lets you find the culprit.
- **Data that must survive.** The writable layer dies with the container. Understanding that boundary is the reason volumes exist.

## 3. Prerequisites and Dependencies

- [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) covers the engine components (`dockerd`, containerd, runc); the storage driver lives inside `dockerd`, and the snapshotter concept reappears with containerd in [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md).
- [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) defines OCI image layers as tar archives with a diff-ID; overlay2 stores each unpacked layer as a directory.
- [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md) covers mount namespaces, which give each container its own view of the merged mount as `/`.
- [§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) is relevant for the I/O controller limits that apply to writes to the upper layer.
- Basic Linux filesystem knowledge: inodes, hard links, mount, `df`, `du`.

## 4. Architecture / Conceptual Diagram

```text
              Container view of "/"  (the merged mount)
        ┌──────────────────────────────────────────────┐
        │  /app/config.yml   /etc/hosts   /var/log/x   │
        └──────────────────────┬───────────────────────┘
                               │ overlayfs union
      ┌────────────────────────┴───────────────────────┐
      │                                                │
      ▼                                                ▼
 ┌─────────────────────────┐              ┌─────────────────────┐
 │ upperdir  (read-write)  │              │ workdir (scratch)   │
 │ container writable layer│              │ same fs as upper    │
 │  diff/                  │              └─────────────────────┘
 └───────────┬─────────────┘
             │ shadows
             ▼
 ┌─────────────────────────────────────────────────────────┐
 │ lowerdir (read-only, top ► bottom)                      │
 │  ┌───────────────────────────────┐                      │
 │  │ Layer 3: COPY app/  (diff/)   │  top of image        │
 │  ├───────────────────────────────┤                      │
 │  │ Layer 2: RUN apt-get install  │                      │
 │  ├───────────────────────────────┤                      │
 │  │ Layer 1: base OS (FROM)       │  bottom of image     │
 │  └───────────────────────────────┘                      │
 └─────────────────────────────────────────────────────────┘

 Copy-on-write:  read  ► found in highest layer that has it
                 write ► copy_up file to upperdir, then modify
                 rm    ► whiteout entry created in upperdir
```

- **Lookup order.** A path is resolved from `upperdir` first, then each `lowerdir` in order. The first hit wins.
- **Directory layout.** On disk, each layer is `/var/lib/docker/overlay2/<id>/` with `diff/` (contents), `link` (a short alias name), `lower` (the chain of parent aliases), and `work/` plus `merged/` for container layers. Short aliases live in `overlay2/l/` as symlinks to keep mount option strings under the kernel page-size limit.
- **Layer limit.** OverlayFS historically allows about 128 lower layers, which is why very long Dockerfiles can fail.

## 5. Hands-On

### 5.1 Confirm the storage driver and backing filesystem

```bash
$ docker info --format '{{.Driver}}'
overlay2

$ docker info | grep -A6 "Storage Driver"
 Storage Driver: overlay2
  Backing Filesystem: extfs
  Supports d_type: true
  Using metacopy: false
  Native Overlay Diff: true
  userxattr: false
```

`Supports d_type: true` is required. On XFS the filesystem must be formatted with `ftype=1` (`xfs_info /var/lib/docker | grep ftype`).

### 5.2 Inspect an image's layers

```bash
$ docker pull nginx:1.27
$ docker inspect nginx:1.27 --format '{{json .GraphDriver.Data}}' | python3 -m json.tool
{
    "LowerDir": "/var/lib/docker/overlay2/3f1c.../diff:/var/lib/docker/overlay2/a9d2.../diff:...",
    "MergedDir": "/var/lib/docker/overlay2/7be4.../merged",
    "UpperDir": "/var/lib/docker/overlay2/7be4.../diff",
    "WorkDir": "/var/lib/docker/overlay2/7be4.../work"
}

$ docker inspect nginx:1.27 --format '{{json .RootFS.Layers}}'
["sha256:1287fbecdfcc...","sha256:e3c2c1a5e2f4...","sha256:8d6a0b3a4c2e..."]
```

Image `GraphDriver.Data` shows the image's top layer as `UpperDir`; a container's shows its own writable directory on top.

### 5.3 Watch copy-on-write happen

```bash
$ docker run -d --name cow alpine sleep 3600
$ docker exec cow sh -c 'echo "new" > /newfile; echo "changed" >> /etc/os-release; rm /etc/motd'

$ UPPER=$(docker inspect cow --format '{{.GraphDriver.Data.UpperDir}}')
$ sudo ls -la "$UPPER" "$UPPER/etc"
/var/lib/docker/overlay2/5c1e.../diff:
-rw-r--r-- 1 root root    4 Sep 22 10:01 newfile
drwxr-xr-x 1 root root   62 Sep 22 10:01 etc

/var/lib/docker/overlay2/5c1e.../diff/etc:
c--------- 1 root root 0, 0 Sep 22 10:01 motd
-rw-r--r-- 1 root root  400 Sep 22 10:01 os-release
```

`newfile` is a fresh file, `os-release` was copied up and modified, and `motd` appears as a `c 0,0` whiteout that hides the lower layer's file.

### 5.4 See the actual overlay mount

```bash
$ mount | grep overlay | head -1
overlay on /var/lib/docker/overlay2/5c1e.../merged type overlay (rw,relatime,
lowerdir=/var/lib/docker/overlay2/l/K3YABC:/var/lib/docker/overlay2/l/ZQ9DEF,
upperdir=/var/lib/docker/overlay2/5c1e.../diff,
workdir=/var/lib/docker/overlay2/5c1e.../work)
```

### 5.5 Diff a container against its image

```bash
$ docker diff cow
C /etc
C /etc/os-release
D /etc/motd
A /newfile
```

`A` is added, `C` is changed, `D` is deleted. This reads the upper layer.

### 5.6 Build your own overlay mount

```bash
$ mkdir -p /tmp/ov/{lower,upper,work,merged}
$ echo base > /tmp/ov/lower/a.txt; echo base > /tmp/ov/lower/b.txt
$ sudo mount -t overlay overlay \
    -o lowerdir=/tmp/ov/lower,upperdir=/tmp/ov/upper,workdir=/tmp/ov/work /tmp/ov/merged
$ echo edited > /tmp/ov/merged/a.txt; rm /tmp/ov/merged/b.txt
$ ls -l /tmp/ov/upper
total 4
-rw-r--r-- 1 root root 7 Sep 22 10:05 a.txt
c--------- 1 root root 0, 0 Sep 22 10:05 b.txt
$ cat /tmp/ov/lower/a.txt
base
$ sudo umount /tmp/ov/merged
```

### 5.7 Measure disk use

```bash
$ docker system df
TYPE            TOTAL   ACTIVE   SIZE      RECLAIMABLE
Images          14      3        4.21GB    3.02GB (71%)
Containers      5       2        12.4MB    8.1MB (65%)
Local Volumes   6       2        1.2GB     900MB (75%)
Build Cache     38      0        2.6GB     2.6GB

$ docker ps -s --format 'table {{.Names}}\t{{.Size}}'
NAMES   SIZE
cow     4.1kB (virtual 7.8MB)
```

`size` is the writable layer; `virtual` includes the image layers.

## 6. Production Usage Notes

- Put `/var/lib/docker` on a dedicated volume so image bloat cannot fill the root filesystem, and monitor it (alert at 80 percent).
- Use ext4 or XFS with `ftype=1`. Avoid running overlay2 on top of another overlay (nested containers) or on network filesystems, which are unsupported.
- Keep the writable layer nearly empty: write logs to stdout, data to volumes. Heavy writes through overlay2 are slower than volumes because of copy-up and the extra filesystem layer.
- Reclaim space routinely with `docker image prune`, `docker builder prune`, and `docker system prune` in a controlled, scheduled way, never blindly on shared hosts.
- Changing the storage driver hides existing images and containers (they remain in the old driver's directory), so treat it as a migration.
- Recent Docker Engine releases can use the containerd image store (containerd snapshotters) as an alternative to the classic graph drivers; overlayfs remains the default snapshotter. The on-disk layout differs ([§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).

## 7. Security Considerations

- **Layers keep history.** A secret added in one layer and deleted in a later one is still present in the lower layer's tar and recoverable via `docker save`. Never `COPY` secrets in; use build secrets.
- **Whiteouts are not erasure.** They only hide a file from the merged view.
- **Host visibility.** Anyone with root on the host can read every container's `diff/` and `merged/` directory directly under `/var/lib/docker`. Restrict host access and the directory's permissions (default `710` root).
- **Shared layers, shared trust.** A poisoned base layer is shared by every image built on it; verify digests ([§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)).
- **Kernel attack surface.** OverlayFS has had privilege-escalation CVEs (for example CVE-2021-3493 in Ubuntu's overlayfs and CVE-2023-0386). Keep kernels patched.
- **Rootless mode** uses overlay2 with user namespaces on kernel 5.11+, or falls back to `fuse-overlayfs` on older kernels.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `no space left on device` while `df` shows free blocks | Inode exhaustion in `/var/lib/docker` | `df -i`; prune; move to a filesystem with more inodes |
| `/var/lib/docker/overlay2` is huge | Dangling images, stopped containers, build cache, large container writable layers | `docker system df -v`; targeted prunes |
| `overlay2: backing filesystem is xfs without d_type` | XFS created with `ftype=0` | Reformat with `mkfs.xfs -n ftype=1` |
| Daemon fails: `driver not supported` | Kernel lacks overlay module or unsupported backing fs | `modprobe overlay`; check `/proc/filesystems` |
| First write to a big file is slow | Whole-file copy-up | Move the file to a volume |
| `max depth exceeded` on build | More than about 125 layers | Combine `RUN` steps; multi-stage builds |
| Deleted file still shows in image size | Removed in a later layer | Delete in the same `RUN` that created it |

```bash
$ df -i /var/lib/docker
Filesystem      Inodes   IUsed  IFree IUse% Mounted on
/dev/nvme1n1   6553600 6553600      0  100% /var/lib/docker
$ docker system df -v | head -20
```

## 9. Best Practices

- Write persistent or high-churn data to volumes or bind mounts, never the container layer.
- Chain cleanup with creation in one `RUN` instruction (`apt-get install ... && rm -rf /var/lib/apt/lists/*`).
- Use multi-stage builds so build tools never reach the final layers.
- Order Dockerfile instructions from least to most frequently changing to maximize layer reuse.
- Run containers with `--read-only` plus `--tmpfs` where the app allows it.
- Isolate `/var/lib/docker` on its own filesystem and monitor both blocks and inodes.
- Pin base images by digest to make shared layers predictable.

## 10. Common Anti-Patterns / Mistakes

- **Treating the container filesystem as durable.** `docker rm` deletes the upper layer and all data in it.
- **Deleting in a later layer to save space.** The image stays the same size.
- **Databases on overlay2.** High random-write load and fsync behavior hurt; use volumes.
- **Manually editing or deleting directories under `/var/lib/docker/overlay2`.** This corrupts the daemon's metadata.
- **Giant single layers** from `COPY . .` of build artifacts, defeating cache and slowing pulls.
- **Assuming `docker ps -s` size is the total.** It excludes shared image layers.

## 11. Interview Questions

**🎯 Beginner:** _"What is a container image layer, and why are layers shared between images?"_
**Model answer:** Each Dockerfile instruction that changes the filesystem produces a read-only layer identified by a content hash. Images that start from the same base reference the same layer blobs, so they are stored once on disk and pulled once. When a container starts, a thin writable layer is added on top. `docker history` and `docker image inspect` show the layer stack.
_What the interviewer is probing for:_ Layering, content addressing, and copy-on-write basics.

**🎯 Intermediate:** _"Explain how overlay2 presents layers as one filesystem, and what happens when a container modifies or deletes a file from a lower layer."_
**Model answer:** overlay2 mounts with `lowerdir` (read-only image layers), `upperdir` (the container's writable layer), and `workdir`, and produces a merged view, all visible in `mount | grep overlay` and under `/var/lib/docker/overlay2/`. Modifying a lower file triggers copy-up: the whole file is copied into `upperdir` first, which is slow for large files. Deleting creates a whiteout (a 0/0 character device) in the upper layer, or an opaque directory marker, hiding the lower entry without removing it. Data in lower layers is never changed, which is why deleted secrets still exist in earlier layers.
_What the interviewer is probing for:_ Mechanism-level understanding of copy-up and whiteouts.

**🎯 Senior:** _"A container's writes are slow and the host disk is filling under /var/lib/docker. How do you diagnose and address it?"_
**Model answer:** Run `docker system df -v` to see image, container writable-layer, and volume usage, and `du -sh /var/lib/docker/overlay2/*` to map directories to containers. Heavy writes to the merged filesystem pay copy-up and overlay overhead, so move databases and hot paths to volumes or tmpfs, which bypass overlay. Prune unused images and build cache with `docker system prune` and `docker builder prune`, set log rotation, and check that the backing filesystem is xfs with `d_type` support and `pquota` if quotas are needed. Also check inode exhaustion with `df -i`, which small-file images can hit.
_What the interviewer is probing for:_ Operational triage across layers, volumes, and the backing filesystem.

**🎯 Architect:** _"When would you choose a storage driver other than overlay2, and how do you plan a migration?"_
**Model answer:** overlay2 is the default and best-supported choice on modern kernels. Alternatives include `btrfs` or `zfs` for native snapshots, quotas, and dedup on hosts already using them, and `fuse-overlayfs` or `vfs` for rootless or unusual kernels, at a cost in performance or disk use. Changing `storage-driver` in `daemon.json` makes existing images and containers invisible because each driver keeps its own store, so migration means save or push images, wipe, switch, then reload, ideally by replacing nodes rather than in place. I would validate with the target workload's I/O profile and keep the change behind a canary.
_What the interviewer is probing for:_ Judgment about default versus specialized drivers and safe migration.

## 12. Common Misconceptions

- **"Each container gets a full copy of the image."** No, only a thin upper layer.
- **"Layers are just tarballs on disk."** They arrive as tarballs but are unpacked into directories under `overlay2/<id>/diff`.
- **"Copy-on-write is block-level."** In overlay2 it is file-level (metadata-only copy-up exists with `metacopy` but is not the default).
- **"`rm` in a Dockerfile removes data from the image."** It only masks it.
- **"overlay and overlay2 are the same."** `overlay` was the older driver with hard-link-heavy layering; overlay2 supersedes it.

## 13. 🔑 Key Takeaways

- Images are stacks of read-only layers; containers add one writable upper layer.
- overlay2 merges `lowerdir` layers and `upperdir` into a `merged` mount via OverlayFS.
- Copy-on-write copies a whole file up on first write; deletions use whiteouts.
- `docker diff`, `docker inspect ... GraphDriver`, and `docker system df` are the core inspection tools.
- Anything deleted in a later layer remains recoverable from earlier ones.
- State belongs in volumes, not the container layer.
- Monitor blocks and inodes on `/var/lib/docker`.

## 14. Related Concepts & What's Next

- [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) (OCI image spec) defines layers and diff-IDs that overlay2 unpacks.
- [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md) (namespaces) gives each container its own mount view of the merged directory.
- [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) (containerd) explains snapshotters, containerd's generalization of storage drivers.
- Part 3 (Images and Dockerfile Authoring) builds on layer mechanics for cache and size optimization; Part 7 (Storage and Volumes) covers volumes, bind mounts, and tmpfs in depth.

**Next Section:** [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) — `Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md`
