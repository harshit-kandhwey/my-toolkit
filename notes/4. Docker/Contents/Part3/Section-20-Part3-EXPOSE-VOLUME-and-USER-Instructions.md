# Section 20 (Part 3): EXPOSE, VOLUME, and USER Instructions

## 1. Definition

**Plain language:** `EXPOSE` documents which network port the app listens on. `VOLUME` marks a directory as holding data that should live outside the container's writable layer. `USER` chooses which account the container's processes run as, so they need not be root.

**Precise definition:**

- **`EXPOSE port[/protocol]`** records the port in image metadata (`Config.ExposedPorts`). It does **not** publish the port; it is documentation and a hint used by `docker run -P`, which maps all exposed ports to random high host ports. Default protocol is TCP.
- **`VOLUME ["/path"]`** declares a mount point. When a container starts, Docker creates an anonymous volume there (if none is mounted) and initializes it from the image's contents at that path. It is recorded in `Config.Volumes`.
- **`USER name|uid[:group|gid]`** sets the user (and optionally group) for subsequent `RUN`, `CMD`, and `ENTRYPOINT` and as the default for the container's main process (`Config.User`).

> ⚠️ **Warning:** `EXPOSE` opens nothing. Reachability is decided by `-p` / `--publish`, not by the Dockerfile.

## 2. Why This Matters

- **Least privilege.** By default container processes run as root (UID 0) inside the container. Combined with a container escape or a mounted host path, that is a serious risk; `USER` is the cheapest hardening step available.
- **Data lifecycle.** The writable layer disappears with the container (union filesystem, [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). `VOLUME` flags paths where data must survive, such as database directories.
- **Self-documenting images.** `EXPOSE` tells operators and tooling which ports the service uses without reading source code.
- **Orchestrators and policies** (for example rules that reject root images) read `Config.User` and the port list.

## 3. Prerequisites and Dependencies

- Layers and the writable container layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)).
- Namespaces, especially the user and network namespaces, and why UID 0 in a container is still UID 0 on the host unless user namespaces remap it ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)).
- Dockerfile basics ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), `WORKDIR` and `ENV` ([§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).
- Basic Linux permissions: UID/GID, `chown`, file modes.
- Familiarity with port publishing and volumes at the CLI level; those topics are covered in detail in the networking and storage parts later.

## 4. Architecture / Conceptual Diagram

```
   Dockerfile                       Image config              Effect at `docker run`
   ----------                       ------------              ----------------------
   EXPOSE 8080/tcp     ───────►  ExposedPorts {8080/tcp}  ──► nothing, unless -P or -p
   VOLUME /var/lib/db  ───────►  Volumes {/var/lib/db}    ──► anonymous volume auto-created
   USER 10001:10001    ───────►  User "10001:10001"       ──► main process runs as UID 10001

   Host                                    Container
   ┌────────────────────┐                  ┌───────────────────────────┐
   │ :49153  ◄───(-P)───┼──────────────────┼─► :8080 (app listens)     │
   │ :8080   ◄──(-p 8080:8080)─────────────┼─► :8080                   │
   │                    │                  │  /var/lib/db ◄── volume   │
   │ /var/lib/docker/   │                  │  (survives container rm)  │
   │   volumes/<id>/_data ◄────────────────┤                           │
   └────────────────────┘                  └───────────────────────────┘
```

## 5. Hands-On

### 5.1 EXPOSE is documentation, not publication

```dockerfile
FROM nginx:1.27-alpine
EXPOSE 80
```

```
$ docker build -t webdemo .
$ docker run -d --name w1 webdemo
$ docker port w1
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:80 || echo "unreachable from host"
unreachable from host
$ docker run -d --name w2 -P webdemo
$ docker port w2
80/tcp -> 0.0.0.0:32768
80/tcp -> [::]:32768
$ docker run -d --name w3 -p 8080:80 webdemo
$ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080
200
```

The first container is running and listening, but no host port maps to it. `-P` uses the `EXPOSE` list; `-p` works regardless of `EXPOSE`.

### 5.2 Multiple ports and UDP

```dockerfile
EXPOSE 8080 8443/tcp 5353/udp
```

```
$ docker inspect webdemo --format '{{json .Config.ExposedPorts}}'
{"5353/udp":{},"8080/tcp":{},"8443/tcp":{}}
```

### 5.3 VOLUME creates anonymous volumes

```dockerfile
FROM alpine:3.20
RUN mkdir -p /data && echo "seed" > /data/seed.txt
VOLUME /data
CMD ["sleep", "3600"]
```

```
$ docker build -t voldemo .
$ docker run -d --name v1 voldemo
$ docker inspect v1 --format '{{range .Mounts}}{{.Type}} {{.Name}} -> {{.Destination}}{{end}}'
volume 8c1f...e2a9 -> /data
$ docker exec v1 cat /data/seed.txt
seed
$ docker rm -f v1
$ docker volume ls
DRIVER    VOLUME NAME
local     8c1f...e2a9
```

The container is gone but the anonymous volume remains as a dangling volume until pruned (`docker volume prune`, or `docker rm -v` / `--rm` at run time).

### 5.4 The VOLUME-then-modify trap

```dockerfile
FROM alpine:3.20
VOLUME /data
RUN echo "hello" > /data/file.txt   # discarded!
```

```
$ docker build -t voltrap .
$ docker run --rm voltrap ls /data
$
```

Changes made to a declared volume path *after* the `VOLUME` instruction are discarded in the image. Put `VOLUME` last, after the directory is populated.

### 5.5 Running as a non-root user

```dockerfile
FROM alpine:3.20
RUN addgroup -g 10001 -S app && adduser -u 10001 -S -G app -h /home/app app
WORKDIR /srv/app
COPY --chown=app:app hello.sh .
USER app
CMD ["sh", "hello.sh"]
```

```
$ docker build -t userdemo .
$ docker run --rm userdemo id
uid=10001(app) gid=10001(app) groups=10001(app)
$ docker run --rm --user 0 userdemo id
uid=0(root) gid=0(root) groups=0(root),...
$ docker inspect userdemo --format '{{.Config.User}}'
app
```

`--user` at run time overrides the image's `USER`.

### 5.6 Numeric UID for Kubernetes-style checks

```dockerfile
USER 10001:10001
```

Policies such as "must run as non-root" can only verify a numeric UID; a name like `app` cannot be proven non-zero without reading `/etc/passwd`. Use numeric IDs when policy engines enforce non-root.

### 5.7 Ports below 1024

```
$ docker run --rm --user 10001 alpine nc -l -p 80
nc: bind: Permission denied
```

Non-root processes cannot bind privileged ports by default inside the container image context unless the sysctl `net.ipv4.ip_unprivileged_port_start` is lowered (Docker sets it to 0 in newer engines for container network namespaces, so behavior can differ by version). Portable practice: listen on 8080 or higher and map in `-p`.

## 6. Production Usage Notes

- Always end images with a non-root `USER`; create the account explicitly with a fixed UID/GID so file ownership on volumes and bind mounts is predictable.
- Make the app listen on an unprivileged port and let the platform map 80/443 externally.
- Keep `EXPOSE` accurate; monitoring, service catalogs, and `docker run -P` in test harnesses rely on it.
- Databases official images use `VOLUME` for data directories; for production, mount **named volumes** or platform storage explicitly rather than relying on anonymous ones so data is easy to back up and identify.
- Do the root-required work (package install, `chown`) first, then drop privileges with `USER` as late as possible, but before `CMD`.
- Use `COPY --chown` instead of a later `RUN chown -R`, which duplicates the files into another layer.
- Read-only root filesystems (`--read-only`) combine well with `USER` and `VOLUME`/`tmpfs` for the few writable paths.

## 7. Security Considerations

- **Root in the container is not harmless.** Without user-namespace remapping ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), UID 0 in the container is UID 0 on the host as far as file ownership on bind mounts is concerned, and it holds more capabilities to abuse.
- **`USER` is not a sandbox on its own**; pair it with dropped capabilities, `no-new-privileges`, seccomp, and read-only filesystems.
- **`VOLUME` and secrets.** Data written to an anonymous volume persists on the host in `/var/lib/docker/volumes` after the container is removed, including anything sensitive the app wrote. Clean up with `--rm` or `docker volume prune`.
- **A `VOLUME` on a path holding secrets or config** makes them harder to rotate and harder to audit.
- **`EXPOSE` can mislead audits**: an exposed port is not necessarily published, and a published port need not be exposed. Audit the runtime `HostConfig.PortBindings`, not the Dockerfile.
- **`USER root` in a final stage** should be treated as a review finding. Do not add `sudo` to images.
- Set `USER` to a numeric ID, and avoid `USER 0`-equivalents such as `root:root` in the final image.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| Cannot reach service from host | Relied on `EXPOSE` only | Add `-p host:container` |
| `Permission denied` writing to mounted dir | Non-root UID does not own bind mount or volume | Match UID (`--user`, `chown` on host) or init the directory in the image before `VOLUME` |
| Files added after `VOLUME` missing | Changes to declared volume path are discarded | Move `VOLUME` after population |
| Disk fills with orphan volumes | Anonymous volumes from `VOLUME` never removed | `docker rm -v`, `docker run --rm`, `docker volume prune` |
| `bind: permission denied` on port 80 | Non-root and privileged port | Use port >= 1024 or adjust capabilities/sysctl |
| App cannot write its own files after `USER` | `WORKDIR`/dirs owned by root | `COPY --chown` and `mkdir` + `chown` before `USER` |
| `unable to find user app` | `USER` appears before the account is created | Create user first with `RUN adduser ...` |

Useful commands: `docker port <c>`, `docker inspect <c> --format '{{json .Mounts}}'`, `docker exec <c> id`, `docker volume ls -f dangling=true`.

## 9. Best Practices

- Create a dedicated user with a fixed numeric UID/GID and set `USER` with that number.
- Prefer named volumes or explicit mounts at run time; treat `VOLUME` as a declaration of intent.
- `EXPOSE` every port the service listens on, with protocol where UDP is used.
- Populate and permission the directory before the `VOLUME` line.
- Use `COPY --chown` for application files.
- Run with `--read-only`, `--cap-drop=ALL`, and `--security-opt no-new-privileges` when possible.
- Verify with `docker run --rm <img> id` in CI, and fail builds that resolve to UID 0.

## 10. Common Anti-Patterns / Mistakes

- Assuming `EXPOSE 5432` makes the database reachable from the host.
- Running production containers as root because "it is only a container".
- Adding `VOLUME` to images for convenience, leaving anonymous volumes everywhere.
- Modifying files under a `VOLUME` path in later `RUN` steps.
- `RUN chown -R app:app /` in a late layer, bloating the image.
- Using `USER app` before creating `app`.
- Using `sudo` or `su` inside containers to switch users at run time.

## 11. Interview Questions

**🎯 Beginner:** _"A Dockerfile has `EXPOSE 8080`, yet `curl localhost:8080` from the host fails after `docker run img`. Why, and what user does the process run as?"_
**Model answer:** `EXPOSE` is only metadata documenting the port; it does not publish it. You need `docker run -p 8080:8080 img` to map a host port, or `-P` to map every exposed port to a random host port (see with `docker port`). Unless the image sets `USER` or you pass `--user`, the process runs as root (UID 0). Setting `USER 10001` is the standard fix for that.
_What the interviewer is probing for:_ That EXPOSE does not publish and that default is root.

**🎯 Intermediate:** _"You add `RUN chown -R app /data` and files after `VOLUME /data`, but the changes are missing at run time. Why, and what happens with a non-root USER and a bind mount?"_
**Model answer:** Build-time modifications made after a `VOLUME` declaration to that path are discarded, because at run time the path is backed by a volume. Do the file setup and `chown` before the `VOLUME` line, or seed data at startup. A non-root container writing to a bind mount fails with permission denied when host ownership does not match its UID, so align UID/GID (`--user $(id -u):$(id -g)`) or set matching ownership on the host directory. Use named volumes to avoid the ownership mismatch, since Docker copies image content and ownership into a fresh named volume.
_What the interviewer is probing for:_ Understanding VOLUME semantics and UID/GID mapping in mounts.

**🎯 Senior:** _"Why would a security team insist on a numeric `USER 10001` rather than `USER app`, and why do anonymous volumes from `VOLUME` cause operational trouble?"_
**Model answer:** A numeric UID lets admission policy (for example Kubernetes `runAsNonRoot`) verify non-zero without inspecting `/etc/passwd`, and names can resolve to different UIDs across base images. With user namespace remapping ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), container UID 0 maps to an unprivileged host UID, but non-root inside is still defense in depth. Anonymous volumes get random names, accumulate under `/var/lib/docker/volumes`, are not backed up, and are hard to attribute to a service; find them with `docker volume ls -f dangling=true`. Prefer explicit named volumes at run time.
_What the interviewer is probing for:_ Policy verifiability and lifecycle hygiene of volumes.

**🎯 Architect:** _"Define a container security baseline covering EXPOSE, VOLUME, and USER, and say when root is justified."_
**Model answer:** Baseline: numeric non-root `USER`, unprivileged ports above 1024, `--read-only` root filesystem with tmpfs for scratch, `--cap-drop=ALL` adding back only what is needed, `no-new-privileges`, and explicit named volumes for state. An admission policy rejects images whose `Config.User` is empty or root and images with unexpected volumes. Root is justified rarely, for example build stages or an entrypoint that must perform privileged setup; then drop privileges with `gosu`/`su-exec` before `exec`, or use rootless runtimes. Exceptions should be documented and time-boxed.
_What the interviewer is probing for:_ Layered defense-in-depth baseline with enforceable policy and disciplined exceptions.

## 12. Common Misconceptions

- "`EXPOSE` is a firewall rule." It is metadata only.
- "`-p` requires `EXPOSE`." It does not.
- "Removing the container removes its `VOLUME` data." Anonymous volumes persist unless removed.
- "`USER` makes the container secure." It is one layer of defense.
- "Root in a container is not real root." It is real UID 0 unless remapped.

## 13. 🔑 Key Takeaways

- `EXPOSE` documents; `-p` publishes.
- `VOLUME` creates anonymous volumes and discards later edits to that path.
- Run as a non-root numeric `USER`; do privileged work before dropping.
- Use `COPY --chown` and pre-create writable directories.
- Audit runtime configuration, not Dockerfile intent.

## 14. Related Concepts & What's Next

Related: layers and image config ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `COPY`/`RUN` ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), `CMD`/`ENTRYPOINT` ([§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), `WORKDIR`/`ENV` ([§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), user and network namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), cgroups and capability limits ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), union filesystems and the writable layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). Port publishing, volumes, and container hardening are treated in depth in later parts. Next up is controlling what enters the build in the first place.

**Next Section:** [§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md) — `Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md`
