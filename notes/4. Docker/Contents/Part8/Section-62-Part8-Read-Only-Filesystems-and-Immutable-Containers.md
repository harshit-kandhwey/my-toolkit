# Section 62 (Part 8): Read-Only Filesystems and Immutable Containers

## 1. Definition

**Plain language:** A read-only container cannot write to its own filesystem. The app runs, but an attacker (or a buggy script) cannot drop a web shell, replace a binary, or edit a config file inside the container. Anything the app genuinely needs to write goes to a small number of explicitly provided, writable places.

**Precise definition:** `docker run --read-only` (Compose: `read_only: true`) mounts the container's root filesystem with the `ro` flag, so the writable overlay2 upper layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)) becomes unwritable. Writes then fail with `EROFS` (read-only file system). It does **not** affect mounts you add on top: volumes, bind mounts and `tmpfs` mounts ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)) keep their own mode, and Docker still manages `/etc/hosts`, `/etc/resolv.conf`, `/etc/hostname` and `/dev/shm`-style special mounts. An **immutable container** is the broader operational idea: the running container is never modified or patched; to change anything you rebuild the image and replace the container.

> 💡 **Tip:** `--read-only` protects the *container* filesystem. It does nothing for data in writable volumes, and a process with `CAP_SYS_ADMIN` could remount the root writable, which is why it pairs with dropped capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).

## 2. Why This Matters

- It removes the most common post-exploit step: persisting a payload or tool on disk.
- It blocks configuration drift, where someone `docker exec`s in and "fixes" production by hand.
- It surfaces hidden writes (caches, pid files, temp files) so they are made explicit and bounded.
- It is a standard hardening baseline: CIS Docker Benchmark, Kubernetes `readOnlyRootFilesystem`, Pod Security "restricted" guidance and most scanner policies check for it.
- It makes images behave identically across hosts, which simplifies rollback and incident forensics.

## 3. Prerequisites and Dependencies

Requires the layered filesystem model ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)) and the storage options for writable paths: volumes, bind mounts and tmpfs ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)). Background on the threat model is in [§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md). It is normally combined with a non-root user ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)), dropped capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)) and a seccomp profile ([§60](Section-60-Part8-Seccomp-Profiles.md)). Compose syntax is in [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md).

## 4. Architecture / Conceptual Diagram

```text
  Normal container                         --read-only container
 ┌──────────────────────────┐            ┌──────────────────────────────────┐
 │ writable upper layer (rw)│            │ rootfs: image layers + upper (ro)│
 │  ◄── any write succeeds  │            │  ◄── write = EROFS               │
 ├──────────────────────────┤            ├──────────────────────────────────┤
 │ image layers (ro)        │            │  explicit writable mounts only:  │
 └──────────────────────────┘            │   /tmp        tmpfs (RAM, rw)    │
                                         │   /run        tmpfs (RAM, rw)    │
                                         │   /var/cache  tmpfs or volume    │
                                         │   /data       named volume (rw)  │
                                         └──────────────────────────────────┘

  Immutable lifecycle:
  code change ──► build image ──► scan/sign ──► replace container ──► (never patch in place)
        ▲                                                                 │
        └────────────────────── rollback = previous tag ◄─────────────────┘
```

- **Layers stay shared:** the image layers were always read-only; `--read-only` simply removes the per-container writable layer.
- **tmpfs is RAM-backed:** contents vanish at stop and count against memory limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)).
- **Special files stay managed:** Docker bind-mounts `/etc/hosts`, `/etc/hostname` and `/etc/resolv.conf` writable by the daemon so networking still works.

## 5. Hands-On

### 5.1 See the Difference

```bash
docker run --rm alpine:3.20 sh -c 'echo hi > /file && cat /file'
docker run --rm --read-only alpine:3.20 sh -c 'echo hi > /file && cat /file'
```

```text
hi
sh: can't create /file: Read-only file system
```

### 5.2 Provide Writable Scratch Space with tmpfs

```bash
docker run --rm --read-only --tmpfs /tmp alpine:3.20 sh -c 'echo ok > /tmp/x && cat /tmp/x'
docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m alpine:3.20 \
  sh -c 'mount | grep " /tmp "'
```

```text
ok
tmpfs on /tmp type tmpfs (rw,nosuid,noexec,relatime,size=16384k)
```

`noexec` stops anything written to `/tmp` from being executed, which defeats the classic "download and run" step. The long form is `--mount type=tmpfs,destination=/tmp,tmpfs-size=16m,tmpfs-mode=1777`.

### 5.3 A Real Service: nginx

Stock nginx writes to `/var/cache/nginx`, `/var/run` (pid) and `/tmp`. Start it read-only and read the errors:

```bash
docker run -d --name web --read-only -p 8080:80 nginx:1.27-alpine
docker logs web 2>&1 | head -5
```

```text
... [emerg] 1#1: mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
```

Fix it by giving those paths tmpfs mounts:

```bash
docker rm -f web
docker run -d --name web --read-only \
  --tmpfs /var/cache/nginx --tmpfs /var/run --tmpfs /tmp \
  -p 8080:80 nginx:1.27-alpine
curl -sI http://localhost:8080 | head -1
```

```text
HTTP/1.1 200 OK
```

(If you run nginx as a non-root user, the tmpfs mounts also need matching `uid=`/`gid=` options, for example `--tmpfs /var/cache/nginx:uid=101,gid=101`.)

### 5.4 Find What Your App Actually Writes

Run the app normally, exercise it, then list changes to the writable layer:

```bash
docker run -d --name probe -p 8080:80 nginx:1.27-alpine
curl -s localhost:8080 >/dev/null
docker diff probe
```

```text
C /run
A /run/nginx.pid
C /var
C /var/cache
C /var/cache/nginx
A /var/cache/nginx/client_temp
A /var/cache/nginx/proxy_temp
...
```

`A` is added, `C` is changed, `D` is deleted. Every path listed is a candidate tmpfs or volume. `docker diff` on a short-lived container misses code paths not exercised, so also test error paths and startup.

### 5.5 Compose

```yaml
services:
  api:
    image: registry.example.com/api:1.8.2
    read_only: true
    tmpfs:
      - /tmp:size=16m,noexec,nosuid
      - /run
    volumes:
      - api-data:/var/lib/api        # the only persistent write location
    user: "10001:10001"
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
volumes:
  api-data:
```

### 5.6 Read-Only Volumes and Bind Mounts

Mounting config or secrets read-only gives the same guarantee for those paths even on a writable root:

```bash
docker run --rm -v "$PWD/conf":/etc/app:ro alpine:3.20 sh -c 'echo x > /etc/app/a'
docker run --rm --mount type=bind,src="$PWD/conf",dst=/etc/app,readonly alpine:3.20 true
```

```text
sh: can't create /etc/app/a: Read-only file system
```

### 5.7 Verifying the Setting and Detecting Drift

```bash
docker inspect web --format 'ReadonlyRootfs={{.HostConfig.ReadonlyRootfs}} Tmpfs={{json .HostConfig.Tmpfs}}'
docker diff web          # for an immutable container this should list nothing under app paths
docker ps --format '{{.Names}}' | xargs -I{} sh -c 'echo {}: $(docker diff {} | wc -l) changes'
```

```text
ReadonlyRootfs=true Tmpfs={"/tmp":"","/var/cache/nginx":"","/var/run":""}
```

`docker diff` does not list tmpfs or volume paths, so on a correctly configured read-only container its output stays empty; any entry means something wrote to the root filesystem.

## 6. Production Usage Notes

- **Roll it out per service:** start with `docker diff`, build the tmpfs/volume list, test under load, then enforce. Do not enable on all services in one change.
- **Common writable paths:** `/tmp`, `/run`, `/var/run`, `/var/tmp`, framework caches (`~/.cache`, `/var/cache/<app>`), language runtimes (Python `__pycache__` and `PYTHONDONTWRITEBYTECODE=1`, JVM `-Djava.io.tmpdir`, Node `~/.npm`), and log files.
- **Logs:** write to stdout/stderr ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)) instead of files; this removes the largest source of unexpected writes.
- **Databases and stateful apps:** keep the root read-only and mount only the data directory as a volume ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)). Official images such as postgres and mysql run an init step that writes to the root (for example, `/var/run/postgresql`); add a tmpfs for those paths.
- **tmpfs sizing:** set `size=` explicitly. An unbounded tmpfs can consume host RAM up to the container memory limit.
- **Kubernetes:** the equivalent is `securityContext.readOnlyRootFilesystem: true` plus `emptyDir` volumes (optionally `medium: Memory`) for writable paths.
- **Docker Desktop and rootless:** `--read-only` behaves the same; tmpfs ownership options matter more when the container user is not root.
- **Immutable deploys:** deploy by image digest ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), roll back by redeploying the previous digest, and prohibit `docker exec` write operations in production runbooks.

## 7. Security Considerations

- **What it stops:** writing webshells, modifying application code or `/etc/passwd`, replacing system binaries, planting persistence in the container.
- **What it does not stop:** in-memory attacks, writes to mounted volumes, network exfiltration, or abusing a binary already in the image. It is one layer, not a sandbox.
- **Add `noexec` on tmpfs** so scratch space cannot hold executables. Note that some runtimes (JIT engines, certain Python/Java libraries that extract native libs to `/tmp`) require exec on their temp directory; scope the exception to a dedicated path rather than all of `/tmp`.
- **Capability interplay:** with `CAP_SYS_ADMIN` a process can remount filesystems read-write. Drop all capabilities and add back only what is needed ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)). Never run `--privileged` and expect `--read-only` to hold.
- **Never mount the Docker socket** into a read-only container; it gives the process the ability to start a new, writable, privileged container ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- **Writable volumes are the new attack surface:** keep them narrow, owned by the app user, mounted `nosuid,nodev`, and never executable from a trusted path.
- **Secrets:** deliver them as read-only mounts or files ([§64](Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), not by writing them into the container at start.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Read-only file system` in app logs at startup | App writes to a path under `/` | Find it with `docker diff` or `strace`; add `--tmpfs` or a volume |
| nginx `mkdir() ... client_temp failed (30)` | Cache dirs not writable | `--tmpfs /var/cache/nginx --tmpfs /var/run` |
| tmpfs mounted but `Permission denied` | tmpfs is root-owned, app runs as non-root | Add `uid=`/`gid=` and `mode=` to the tmpfs options |
| `exec format error` / `Permission denied` running from `/tmp` | `noexec` on the tmpfs | Move the executable elsewhere or give a dedicated exec-enabled path |
| Container OOM-killed after a while | Unbounded tmpfs filling RAM | Set `size=` and check app cleanup of temp files |
| Python/Node prints cache write warnings | Runtime tries `__pycache__` or `~/.cache` | `PYTHONDONTWRITEBYTECODE=1`, set `HOME`/`XDG_CACHE_HOME` to a tmpfs |
| Postgres fails: `could not create lock file` | `/var/run/postgresql` not writable | tmpfs for `/var/run/postgresql` plus a data volume |
| `docker cp` into the container fails | Root filesystem is read-only | Copy into a mounted volume or tmpfs path instead ([§30](../Part4/Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md)) |
| `docker exec` shell cannot create `.bash_history` | Read-only root, home is on rootfs | Expected; set `HISTFILE=/dev/null` or mount tmpfs on the home directory |

## 9. Best Practices

- Make read-only the default in every Compose file and run template, and require a written justification to disable it.
- Enumerate writable paths deliberately, keep each small and sized, and prefer tmpfs over volumes for anything disposable.
- Log to stdout/stderr; do not write log files in the container.
- Combine with non-root `USER`, `cap_drop: [ALL]`, `no-new-privileges` and the default seccomp profile.
- Build images so nothing is written at start-up: do package installs, config generation and permission changes at build time ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), not in the entrypoint.
- Mount configuration and credentials with `:ro`.
- Deploy by digest and treat any `docker diff` output on a read-only container as an alert-worthy anomaly.
- Test the read-only configuration in CI by starting the container and running its health check ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)).

## 10. Common Anti-Patterns / Mistakes

- Mounting the entire app directory or `/var` as a writable volume to "make it work", which defeats the purpose.
- Using `--read-only` together with `--privileged` or the Docker socket.
- Using an unbounded `--tmpfs /tmp` and no memory limit.
- Dropping `noexec` everywhere because one tool needs it in one directory.
- Patching a running container (`apt-get install`, edit config, restart) and calling it "fixed".
- Treating a read-only root as a replacement for a non-root user or for patching vulnerable packages.
- Writing logs and uploads under the application directory instead of a dedicated volume.
- Assuming a read-only root makes persistent data safe; volumes remain writable and survive restarts.

## 11. Interview Questions

**🎯 Beginner:** _"What does `docker run --read-only` do, and why would your app then fail to start?"_
**Model answer:** It mounts the container's root filesystem read-only, so the writable layer on top of the image cannot be modified and any write returns "Read-only file system". Apps often need to write temp files, pid files, caches or logs under `/tmp`, `/run` or `/var`. Those writes fail at startup. You fix it by giving those specific paths a writable mount, usually `--tmpfs /tmp` for disposable data or a volume for data that must persist, and by finding the paths with `docker diff` on a normal run.
_What the interviewer is probing for:_ Basic understanding of the writable layer and the tmpfs/volume escape hatches.

**🎯 Intermediate:** _"You have enabled `--read-only` and `--tmpfs /tmp`. A non-root service still gets `Permission denied` writing to `/tmp`, and a helper binary extracted to `/tmp` will not run. Explain both."_
**Model answer:** A tmpfs is created root-owned with mode 1777 by default in Docker, but custom options or application-specific subdirectories can differ, and ownership matters for directories like `/var/cache/app` that are not world-writable; set `uid=`, `gid=` and `mode=` on the tmpfs mount to match the container user. The second failure is `noexec`: if you mounted `/tmp:rw,noexec,nosuid` the kernel refuses to execute anything there, which is the intended protection. Move the helper to the image at build time, or provide a separate narrowly scoped exec-enabled path, instead of removing `noexec` from all scratch space.
_What the interviewer is probing for:_ Mount options, ownership, and awareness that hardening flags have functional trade-offs.

**🎯 Senior:** _"Roll out read-only root filesystems across 80 services with no outages. What is your approach?"_
**Model answer:** Treat it as discovery then enforcement. First, collect write paths: run each service in staging under realistic load with a normal root, capture `docker diff` and, where needed, `strace -f -e trace=file` or an audit rule, and include startup, health check, migration and error paths. Second, generate a per-service tmpfs and volume list, change logs to stdout, move build-time work out of entrypoints, and set runtime env vars such as `PYTHONDONTWRITEBYTECODE`. Third, enable `read_only: true` in staging with CI checks that start the container and run its health check. Fourth, canary in production, watch for `EROFS` in logs and restart loops, and keep a documented, time-boxed exception process. Finally, make read-only the default in the shared Compose/Helm template so new services start hardened.
_What the interviewer is probing for:_ A measured rollout plan, path discovery technique, and platform-level defaults rather than per-team heroics.

**🎯 Architect:** _"Define an immutable-infrastructure standard for containers and say where a read-only root fits and where it does not."_
**Model answer:** The standard: images are built once in CI, scanned, signed and referenced by digest; containers are never modified after start; configuration arrives through environment, mounted config and secret stores; state lives only in declared volumes or external services; changes ship by replacing containers; and production forbids interactive write access (`exec` is audited or disabled). A read-only root is the runtime enforcement of that policy and gives cheap tamper evidence (`docker diff` should be empty). It does not cover writable volumes, in-memory attacks, or vulnerable code in the image, so it sits beside non-root users, capability drops, seccomp/LSM profiles, vulnerability scanning and network policy. Exceptions are legitimate for tools that must manage a filesystem (build agents, some databases during init); isolate those on separate hosts or namespaces and document the compensating controls.
_What the interviewer is probing for:_ Systems thinking: policy, enforcement, limits and layering, not just a flag.

## 12. Common Misconceptions

- "`--read-only` makes the whole container immutable and its data safe." Volumes and tmpfs remain writable.
- "A read-only root means no writes at all, so `/tmp` also fails." It does fail unless you mount something, but Docker still manages `/etc/hosts` and similar files.
- "tmpfs is persistent scratch space." It is RAM-backed and erased when the container stops.
- "Read-only containers cannot be debugged." You can still `docker exec` and read; add a debug tmpfs or use an ephemeral debug container.
- "It replaces running as non-root." The two are complementary; root can often remount or write to mounted paths.
- "It is free." It needs per-app discovery work and sized tmpfs mounts.

## 13. 🔑 Key Takeaways

- `--read-only` / `read_only: true` makes the container rootfs unwritable; volumes and tmpfs are unaffected.
- Provide writable paths explicitly: `--tmpfs /tmp:rw,noexec,nosuid,size=...` for disposable data, volumes for persistent data.
- Discover required writes with `docker diff`, then enforce; log to stdout.
- Pair with non-root, `cap_drop: ALL`, `no-new-privileges` and seccomp; do not combine with `--privileged` or the Docker socket.
- Immutable containers: rebuild, scan, replace by digest; never patch in place.
- An empty `docker diff` on a read-only container is the healthy state; anything else is drift worth investigating.

## 14. Related Concepts & What's Next

Related: overlay2 and the writable layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), tmpfs versus volumes ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), non-root users ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)), capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)), seccomp ([§60](Section-60-Part8-Seccomp-Profiles.md)) and AppArmor/SELinux ([§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)). Next, [§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md) covers scanning images for known vulnerabilities, the step that decides which image gets deployed as the immutable artifact.

**Next Section:** [§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md) — `Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md`
