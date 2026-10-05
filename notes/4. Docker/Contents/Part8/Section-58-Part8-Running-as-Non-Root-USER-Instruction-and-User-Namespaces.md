# Section 58 (Part 8): Running as Non-Root: USER Instruction and User Namespaces

## 1. Definition

**Plain language:** By default a container's main process runs as `root` (UID 0) inside the container. Running as non-root means the process uses an unprivileged UID/GID instead, so that a bug in the application or a container escape starts from a much weaker position. There are three separate mechanisms, and they solve different problems:

- **`USER` / `--user`:** choose which UID the container process runs as *inside* the container.
- **User namespace remapping (`userns-remap`):** make container UID 0 map to an unprivileged UID range *on the host*, so "root in the container" is not root on the host.
- **Rootless mode:** run the Docker daemon itself as an unprivileged user ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)).

**Precise definition:** `USER <user>[:<group>]` sets the default user in the image config ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) for all subsequent `RUN`, `CMD` and `ENTRYPOINT` instructions and for the container at run time. The value may be a name (resolved through the image's `/etc/passwd`) or a numeric UID/GID (used as-is, which works even when no passwd entry exists). `docker run --user` overrides it. With `dockerd --userns-remap`, the daemon maps container IDs onto the host ranges listed in `/etc/subuid` and `/etc/subgid`, using the kernel user namespace ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)).

> 💡 **Tip:** Prefer a numeric UID in `USER` (for example `USER 10001:10001`). Orchestrators that enforce `runAsNonRoot` can verify a number but cannot verify a name.

## 2. Why This Matters

- Containers share the host kernel ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)). Most container-escape bugs and misconfigurations are far less useful to an attacker who is not UID 0.
- A root process in a container can use any capability still granted to it ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)), write to any bind-mounted host path it can reach, and modify the image's own filesystem.
- Compliance baselines (CIS Docker Benchmark, Pod Security Standards "restricted", PCI controls) all require non-root workloads.
- Many hardened platforms (OpenShift, GKE Autopilot, restricted Kubernetes namespaces) refuse root images outright, so a root-only image is not portable.

## 3. Prerequisites and Dependencies

Requires the Dockerfile basics ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), `USER` as covered with `EXPOSE` and `VOLUME` ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), and the user namespace and capability concepts from [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md). Volume ownership interacts with the storage material in [§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md) and [§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md). The daemon settings live in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

## 4. Architecture / Conceptual Diagram

```text
  Without userns-remap                    With userns-remap (dockremap)
  ─────────────────────                   ─────────────────────────────
  Container view   Host view              Container view   Host view
  UID 0 (root) ───► UID 0 (root)          UID 0 (root) ───► UID 100000 (nobody-ish)
  UID 1000     ───► UID 1000              UID 1000     ───► UID 101000
  UID 65534    ───► UID 65534             UID 65534    ───► UID 165534

  /etc/subuid:  dockremap:100000:65536    (container UID n  ──► host UID 100000 + n)

  Three layers, each independent
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ 1. USER in image/--user : who the process is INSIDE the container        │
  │ 2. userns-remap         : what that identity is ON THE HOST (daemon-wide)│
  │ 3. rootless dockerd     : who the DAEMON and runc run as on the host     │
  └──────────────────────────────────────────────────────────────────────────┘

  Build-time vs run-time:   USER app ► subsequent RUN steps also run as app
                            (switch back with USER root for privileged steps)
```

- **`USER` is a default, not a lock.** `docker run --user 0` or `-u root` replaces it; enforcement belongs in policy (admission control, daemon settings), not in the Dockerfile alone.
- **userns-remap is daemon-wide.** All containers share one mapping unless you opt a container out with `--userns=host`. Images and layers are stored in a separate directory per remapped range (`/var/lib/docker/<uid>.<gid>/`).
- **Rootless is stronger than remap** for the daemon, but has networking and storage limits ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)).

## 5. Hands-On

### 5.1 Observe the Default: Root

```bash
docker run --rm alpine:3.20 id
docker run --rm --user 10001:10001 alpine:3.20 id
```

```text
uid=0(root) gid=0(root) groups=0(root),1(bin),2(daemon),3(sys),4(adm),6(disk),10(wheel),11(floppy),20(dialout),26(tape),27(video)
uid=10001 gid=10001 groups=10001
```

A numeric UID needs no passwd entry; the name column is simply absent.

### 5.2 A Non-Root Dockerfile (Debian/Ubuntu Style)

```dockerfile
FROM python:3.12-slim

# Fixed numeric IDs make volume ownership predictable across hosts
RUN groupadd --system --gid 10001 app \
 && useradd  --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /srv/app
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . .

USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "app"]
```

The order matters: do privileged work (package installs, `chmod`) first, then switch with `USER` as late as practical. Use `COPY --chown`, not a later `RUN chown -R`, which duplicates every file into a new layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)).

### 5.3 Alpine and Distroless Variants

```dockerfile
# Alpine (BusyBox adduser/addgroup)
FROM alpine:3.20
RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app -H -s /sbin/nologin app
USER app
```

```dockerfile
# Distroless: ships a ready-made nonroot user (UID/GID 65532)
FROM gcr.io/distroless/static-debian12:nonroot
COPY --chown=65532:65532 ./server /server
USER 65532:65532
ENTRYPOINT ["/server"]
```

Distroless has no shell or `useradd`, so the user must already exist in the base image or be referenced by number ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)).

### 5.4 Verify the Result

```bash
docker build -t nonroot-demo .
docker run -d --name nr nonroot-demo
docker exec nr id
docker top nr -eo user,pid,args
docker image inspect nonroot-demo --format '{{.Config.User}}'
```

```text
uid=10001(app) gid=10001(app) groups=10001(app)
USER   PID    COMMAND
10001  4182   python -m app
10001:10001
```

`docker top` shows the **host** view of the user; with `userns-remap` it would show the remapped host UID, not 10001.

### 5.5 Privileged Ports Without Root

```bash
docker run --rm --user 10001 alpine:3.20 nc -l -p 80
docker run --rm --user 10001 --sysctl net.ipv4.ip_unprivileged_port_start=0 alpine:3.20 nc -l -p 80
```

Since Docker Engine 20.10 the daemon sets `net.ipv4.ip_unprivileged_port_start=0` in container network namespaces, so a non-root process can usually bind port 80 or 443 without `NET_BIND_SERVICE`. If a custom runtime, rootless setup or Kubernetes node resets the sysctl, the bind fails with `Permission denied`. The portable fix is to listen on a port above 1024 (for example 8080) and map it with `-p 80:8080`.

### 5.6 Volume Ownership: The Classic Non-Root Failure

```bash
docker volume create appdata
docker run --rm -v appdata:/data --user 10001 alpine:3.20 touch /data/x
```

```text
touch: /data/x: Permission denied
```

A new named volume is created root-owned unless the image already has that path owned by another user, in which case Docker copies the ownership from the image on first use. Fix it in the image:

```dockerfile
RUN mkdir -p /data && chown 10001:10001 /data
VOLUME /data
USER 10001:10001
```

For bind mounts the host directory's ownership wins; use `chown` on the host, `--user "$(id -u):$(id -g)"` for development, or `--group-add` for shared groups. Do not `chmod 777` to make it go away.

### 5.7 Enabling User Namespace Remapping

```json
{
  "userns-remap": "default"
}
```

```bash
sudo systemctl restart docker
grep dockremap /etc/subuid /etc/subgid
sudo ls /var/lib/docker
docker run --rm alpine:3.20 id
docker run -d --name remapped alpine:3.20 sleep 300
ps -o user:12,pid,cmd -C sleep
docker run --rm --userns=host alpine:3.20 id
```

```text
/etc/subuid:dockremap:100000:65536
/etc/subgid:dockremap:100000:65536
100000.100000   containers   image   network   ...
uid=0(root) gid=0(root) groups=0(root)
USER           PID CMD
100000        5120 sleep 300
```

Inside the container the process is still "root", but the host shows UID 100000. After enabling remap the daemon uses a fresh data directory, so existing images and containers appear to be missing until you pull or rebuild (they are not deleted; switching back restores them).

### 5.8 Hardening Flags That Complement Non-Root

```bash
docker run --rm \
  --user 10001:10001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --read-only --tmpfs /tmp \
  nonroot-demo
```

`no-new-privileges` stops setuid binaries (and file capabilities) from raising privileges after start. See [§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md) and [§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md).

## 6. Production Usage Notes

- **Set the user in the image**, then enforce in the platform: Kubernetes `securityContext.runAsNonRoot: true`, `runAsUser`, `runAsGroup`, `fsGroup`; Compose `user: "10001:10001"`.
- **Fixed numeric UIDs** across all images in a fleet make shared volumes and NFS exports ([§53](../Part7/Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)) manageable.
- **Entrypoint scripts that need root briefly** (chown a mounted volume, render config) can start as root and drop privileges with `exec gosu app "$@"` or `su-exec`; this pattern is used by the official postgres and redis images ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)). Prefer fixing ownership at build time so the container never needs root.
- **Arbitrary UIDs (OpenShift):** the platform assigns a random UID in the root group (GID 0). Make writable paths group-writable (`chgrp -R 0 /app && chmod -R g=u /app`) instead of relying on a specific UID.
- **Choosing between remap and rootless:** remap protects against container-to-host UID collisions on a normal daemon; rootless also removes root from the daemon and runc. Both change networking, volume and port behavior, so test them before a fleet rollout.
- **Compatibility limits of userns-remap:** it cannot be combined with `--privileged` for host-namespace features, `--net=host`, `--pid=host` without `--userns=host`, and some storage and volume drivers. Mounting `/var/run/docker.sock` still gives host-root equivalent control to whoever can use it ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).

## 7. Security Considerations

- **Non-root is not a sandbox.** A non-root process shares the kernel; kernel exploits, writable host mounts and the Docker socket still apply ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- **UID 0 in the container with a bind mount is UID 0 on the host files** (unless remapped). A root container can write `/etc/cron.d` into a mounted host directory. Mount narrowly and read-only where possible.
- **Setuid and setgid binaries** inside the image are privilege-escalation steps for a non-root process; remove them (`find / -perm /6000 -type f`) or rely on `no-new-privileges`.
- **Group membership matters.** Adding a user to the `docker` group or mounting the socket grants root-equivalent power regardless of `USER`.
- **Shell and package manager in the image** let a compromised non-root process attempt local escalation; minimal images ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)) reduce that.
- **Do not create users with login shells and passwords.** Use `--system`, `nologin` and no password.
- **Scan and audit:** include a check for `Config.User` being empty or `0` in CI ([§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Permission denied` writing to a volume or bind mount | Directory owned by root or another UID | `chown` in the image before `VOLUME`; `chown` host dir; `--user` matching the host owner |
| `bind: permission denied` on port 80 | Sysctl `ip_unprivileged_port_start` not 0 (rootless, custom runtime) | Listen on 8080 and publish `-p 80:8080`, or set the sysctl |
| `unable to find user app: no matching entries in passwd file` | `USER app` but user never created (common with `scratch`/distroless) | Create the user in an earlier stage or use a numeric UID |
| `container has runAsNonRoot and image has non-numeric user` (Kubernetes) | `USER app` by name | Use `USER 10001` or set `runAsUser` |
| Images and containers "disappeared" after enabling `userns-remap` | Daemon switched to the remapped data directory | Expected; revert setting to see old data, or re-pull |
| `Error response from daemon: ... cannot be used with user namespaces` | `--privileged`, `--net=host` or similar with remap on | Add `--userns=host` for that container, or reconsider the design |
| App cannot write to `/tmp` or its cache dir | Directory owned by root in the image | `mkdir` and `chown` in the build, or mount a `tmpfs` with `uid=` |
| `npm`/`pip` fails at run time with `EACCES` | Package manager home directory not writable | Set `HOME` to a writable path or install at build time |
| `useradd: command not found` | Alpine or distroless base | Use `adduser -S`, or copy `/etc/passwd` from a builder stage |

## 9. Best Practices

- Create a dedicated system user with a fixed numeric UID/GID and switch to it with `USER <number>:<number>`.
- Do privileged setup first, `USER` last, and never switch back to root at the end.
- Use `COPY --chown` and `--chmod`; avoid recursive `chown` layers.
- Pre-create and own every writable path (data, cache, tmp) and declare `VOLUME` after setting ownership.
- Combine with `--cap-drop ALL`, `no-new-privileges` and a read-only root filesystem.
- Listen on unprivileged ports and map them at publish time.
- Enforce non-root by policy (Kubernetes admission, CI check of `Config.User`), not by convention.
- Evaluate rootless Docker or `userns-remap` for hosts that run untrusted or multi-tenant workloads.

## 10. Common Anti-Patterns / Mistakes

- Leaving the default root user because "it works".
- `USER root` as the last instruction after a debugging session.
- Using `chmod 777` or `chmod -R a+w` to fix permission errors.
- Running `sudo` inside containers, or installing it to make a non-root user "flexible".
- Referring to `USER app` by name when the platform requires a numeric UID.
- Adding the application user to the `docker` group or mounting the Docker socket.
- Assuming `--user` makes bind-mounted host files safe; the process still sees whatever its UID can access.
- Enabling `userns-remap` on a shared host without testing volumes, networking and CI tooling first.

## 11. Interview Questions

**🎯 Beginner:** _"Why should containers not run as root, and how do you change the user in a Dockerfile?"_
**Model answer:** A container shares the host kernel, so a root process has the widest possible starting point for abusing capabilities, writable mounts and kernel bugs, and files it writes to bind mounts are root-owned on the host. In a Dockerfile you create a user (for example `useradd --system --uid 10001 app`) and then add `USER 10001:10001` after the privileged setup steps. `docker run --user` overrides it at run time. Prefer a numeric ID, and make sure the directories the app writes to are owned by that UID.
_What the interviewer is probing for:_ The `USER` instruction, ordering of privileged steps, and the basic risk model.

**🎯 Intermediate:** _"Your non-root container fails with `Permission denied` on a named volume that worked as root. Why, and what are the options?"_
**Model answer:** A fresh named volume is root-owned unless the image already contains the mount path with different ownership, in which case Docker copies that ownership on first use. The fix is to create the directory in the image, `chown` it to the app UID, and only then declare `VOLUME` (the order matters because changes after `VOLUME` to that path are discarded). For bind mounts the host directory's owner decides, so use host `chown`, `--user $(id -u):$(id -g)` in development, or a shared supplementary group with `--group-add`. A root entrypoint that chowns and then drops privileges with `gosu` is a last resort. `chmod 777` is a smell.
_What the interviewer is probing for:_ Understanding of volume initialization, ownership semantics and practical remediation.

**🎯 Senior:** _"Explain the difference between `USER app`, `userns-remap` and rootless Docker. When would you use each?"_
**Model answer:** `USER` changes the identity of the process inside the container only; if it is root, it is real UID 0 on the host unless something else remaps it, and it can be overridden by whoever starts the container. `userns-remap` is a daemon-wide setting that maps container IDs to a subordinate host range from `/etc/subuid`, so even container root is an unprivileged UID on the host, which neutralizes many escape and bind-mount issues; costs are a separate image store, incompatibility with host namespaces and some volume drivers. Rootless runs `dockerd`, containerd and runc themselves as an ordinary user inside a user namespace, so a daemon compromise is not host root; costs are slirp4netns/pasta networking limits, no privileged ports by default, storage driver and cgroup delegation requirements. I use `USER` always, and remap or rootless for multi-tenant or CI hosts where I cannot trust the images.
_What the interviewer is probing for:_ Clear separation of the three layers and an honest view of trade-offs.

**🎯 Architect:** _"You must roll out a non-root-only policy to 300 services, some of which legitimately need a privileged startup step. Design the rollout."_
**Model answer:** Establish a standard base image with a fixed UID/GID and ready-owned writable directories, and a shared entrypoint library that never needs root. Add CI gates: scan `Config.User`, reject empty or `0`, and fail images with setuid binaries outside an allowlist. Enforce at runtime with Kubernetes Pod Security "restricted" (or an admission policy) and `runAsNonRoot`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, plus `fsGroup` for volume access. Run in audit/warn mode first, publish a violation dashboard, migrate team by team, and handle the few real exceptions through an init container or a one-off migration job that fixes ownership, not by keeping the main container root. On Docker hosts that remain, enable rootless or remap on build and CI machines. Track exceptions with an owner and expiry date.
_What the interviewer is probing for:_ Policy-as-code thinking, migration strategy and handling of legitimate exceptions without weakening the standard.

## 12. Common Misconceptions

- "Root in a container is harmless." It is real UID 0 on the host unless user namespaces remap it.
- "`USER` in the Dockerfile makes the image safe." It can be overridden, and the process still shares the kernel.
- "Non-root cannot bind port 80." Docker sets the unprivileged port sysctl to 0 inside container namespaces; where that fails, use a high port and publish.
- "`userns-remap` deletes my images." It uses a different storage directory; the originals return when you disable it.
- "Rootless Docker and `userns-remap` are the same feature." Remap is a daemon option on a root daemon; rootless runs the daemon itself unprivileged.
- "`chown -R` at the end of the Dockerfile is fine." It duplicates every changed file into a new layer.

## 13. 🔑 Key Takeaways

- `USER <uid>:<gid>` (numeric) after privileged setup; never end an image as root.
- `--user` overrides the image, so enforce non-root by policy.
- `userns-remap` maps container root to an unprivileged host UID; rootless removes root from the daemon.
- Most non-root failures are ownership problems on volumes, bind mounts and writable directories; fix ownership in the image.
- Combine with `--cap-drop ALL`, `no-new-privileges` and a read-only filesystem.
- Non-root reduces blast radius; it does not replace sandboxing.

## 14. Related Concepts & What's Next

Related: security model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), user namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), rootless install ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)), `USER` instruction ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), volumes ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), read-only roots ([§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)). Next, [§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md) covers Linux capabilities, which decide what even a root process may still do.

**Next Section:** [§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md) — `Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md`
