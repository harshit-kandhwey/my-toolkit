# Section 30 (Part 4): Copying Files: docker cp and Data Exchange Patterns

## 1. Definition

**Plain language:** `docker cp` copies files and directories between your host and a container's filesystem, like `cp` or `scp` with a container name in front of the path. It is the quick, one-off way to move a file in or out. For anything repeated or stateful, Docker offers better tools: volumes, bind mounts, and tar streams.

**Precise definition:** `docker cp [OPTIONS] CONTAINER:SRC_PATH DEST_PATH|-` and `docker cp [OPTIONS] SRC_PATH|- CONTAINER:DEST_PATH` call the Engine API archive endpoints (`GET` and `PUT /containers/{id}/archive`, see [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)). The daemon reads or writes a **tar stream** against the container's merged filesystem (the overlay2 mount from [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)); the CLI unpacks or packs it locally. It works on **running and stopped** containers, needs no shell inside the container, and uses `-` to read a tar from stdin or write a tar to stdout. Options: `-a` / `--archive` (preserve source UID/GID), `-L` / `--follow-link` (follow symlinks in the source path), `-q` / `--quiet` (suppress progress).

> 💡 **Tip:** `docker cp` is a tar transport. Anything you can do with `tar` (filter, compress, pipe over SSH) you can do with `docker cp -`.

## 2. Why This Matters

- **Debugging and forensics:** pull a core dump, log file or config out of a crashed container that no longer starts (works on stopped containers).
- **Extracting build artifacts:** `docker create` plus `docker cp` pulls a binary out of an image without running it.
- **Choosing the right mechanism:** copying into a container is a *snapshot into the writable layer*; it vanishes with the container. Teams that confuse this with persistent storage lose data.
- **Interviews and DCA:** "How do you get data in and out of a container, and which way survives `docker rm`?" is a standard question.

## 3. Prerequisites and Dependencies

Requires the container filesystem model: image layers plus a writable layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)). The CLI-to-daemon API path is in [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md). Build-time copying (`COPY`, `ADD`) is a different mechanism covered in [§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md) and the build context in [§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md). The `VOLUME` instruction is in [§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md). Log extraction as an alternative to copying log files is in [§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md). Volumes and bind mounts are explored fully in the storage part of this knowledge base; this section covers only what is needed to choose between them and `cp`.

## 4. Architecture / Conceptual Diagram

```text
   HOST                                         DOCKER ENGINE                CONTAINER
 ┌─────────────┐   tar stream over API   ┌───────────────────────┐
 │ docker cp   │ ──────────────────────► │ PUT  /containers/id/  │  unpack into
 │  ./a.conf   │                         │      archive?path=    │ ─────────────►  merged FS
 │  c1:/etc/   │ ◄────────────────────── │ GET  /containers/id/  │  (writable
 └─────────────┘   tar stream back       │      archive?path=    │ ◄─────────────   layer)
                                          └───────────────────────┘   pack from

   Data exchange options, by lifetime
  ┌──────────────────┬────────────────────────┬───────────────────────────────┐
  │ Mechanism        │ Data lives in          │ Survives docker rm?           │
  ├──────────────────┼────────────────────────┼───────────────────────────────┤
  │ docker cp        │ container writable layer│ No (copy OUT before removal)  │
  │ bind mount       │ host path              │ Yes (it is the host's file)   │
  │ named volume     │ /var/lib/docker/volumes│ Yes (until volume is removed) │
  │ tmpfs            │ host RAM               │ No (gone at stop)             │
  │ tar pipe (exec)  │ either side            │ depends on destination        │
  └──────────────────┴────────────────────────┴───────────────────────────────┘

   Path resolution for  docker cp SRC DEST  (directory SRC):
     SRC ends with  /.   ──► copy the CONTENTS of SRC into DEST
     SRC without    /.   ──► copy the directory itself as DEST/<basename>
```

- **Never a live link:** `cp` is a point-in-time copy; later changes on either side do not propagate.
- **Mount points are invisible to `cp`:** it operates on the container's own filesystem, not on volumes, bind mounts or tmpfs mounted over it.
- **No daemon-side shell:** the Engine does the tar work, so minimal and distroless images work.

## 5. Hands-On

### 5.1 Copy a File Into and Out of a Container

```bash
docker run -d --name web nginx:1.27-alpine
echo "<h1>patched</h1>" > index.html
docker cp index.html web:/usr/share/nginx/html/index.html
docker exec web cat /usr/share/nginx/html/index.html
docker cp web:/etc/nginx/nginx.conf ./nginx.conf.copy
ls -l nginx.conf.copy
```

```text
<h1>patched</h1>
-rw-r--r-- 1 user user 648 Sep 30 10:12 nginx.conf.copy
```

### 5.2 Trailing Slash and `/.` Semantics

```bash
mkdir -p site/css && echo a > site/index.html && echo b > site/css/app.css

docker cp site web:/tmp/          # creates /tmp/site/...
docker cp site/. web:/tmp/dest/   # contents of site into /tmp/dest (dest must exist or be created by Engine rules)
docker exec web ls -R /tmp/site
```

```text
/tmp/site:
css
index.html

/tmp/site/css:
app.css
```

The rules mirror `cp -a`: if `DEST` exists and is a directory, the source is placed *inside* it; if `SRC` ends with `/.`, only its contents are copied. Copying a directory onto an existing *file* is an error.

### 5.3 Copy From a Stopped Container (Post-Mortem)

```bash
docker run --name crashy alpine:3.20 sh -c 'echo "state=bad" > /tmp/state.txt; exit 1'
docker cp crashy:/tmp/state.txt .
cat state.txt
docker rm crashy
```

```text
state=bad
```

The writable layer persists until `docker rm`, so a crashed container is still inspectable. After `rm`, the data is gone.

### 5.4 Extract a Build Artifact From an Image Without Running It

```bash
docker create --name extract myorg/builder:1.0
docker cp extract:/out/app ./app
docker rm extract
```

`docker create` makes the container (and its writable layer) without starting a process. This is the classic pattern for pulling a compiled binary or a generated report out of a build image.

### 5.5 Ownership and Permissions: `-a`

```bash
docker run -d --name own alpine:3.20 sleep 600
touch mine.txt
docker cp mine.txt own:/tmp/mine.txt
docker exec own ls -ln /tmp/mine.txt
docker cp -a mine.txt own:/tmp/mine-a.txt
docker exec own ls -ln /tmp/mine-a.txt
```

```text
-rw-r--r--    1 0        0                0 Sep 30 10:20 /tmp/mine.txt
-rw-r--r--    1 1000     1000             0 Sep 30 10:20 /tmp/mine-a.txt
```

Without `-a`, files copied into a container are owned by root (UID:GID 0:0) and files copied out are owned by the invoking user. With `-a`, the source UID:GID is preserved, which matters when the container runs as a non-root user ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)). On Docker Desktop the outputs depend on the VM file sharing layer.

### 5.6 Streaming Tar With `-`

```bash
# Container to stdout as tar, list it without writing to disk
docker cp web:/etc/nginx - | tar -tv | head -5

# Host tar stream into a container directory (dest must exist)
tar -C site -cf - . | docker cp - web:/tmp/dest

# Compress while copying out
docker cp web:/var/log/nginx - | gzip > nginx-logs.tar.gz
```

```text
drwxr-xr-x 0/0               0 2024-08-12 nginx/
-rw-r--r-- 0/0            1077 2024-08-12 nginx/fastcgi.conf
...
```

Note the output of `docker cp CONTAINER:SRC -` is always a tar archive, never the bare file contents. To print a single file, extract it: `docker cp web:/etc/hostname - | tar -xO`.

### 5.7 Moving Data Between Two Containers

```bash
docker cp a:/data - | docker cp - b:/
```

The tar streams straight through the client; no temporary file is needed. For large data sets prefer a shared named volume.

### 5.8 What `cp` Cannot Reach: Mounts and Special Paths

```bash
docker run -d --name mnt -v appdata:/data alpine:3.20 sleep 600
echo hi | docker exec -i mnt sh -c 'cat > /data/f.txt'
docker cp mnt:/data/f.txt .          # behavior with mounted paths is limited; see note
docker cp mnt:/proc/cpuinfo . ; echo "exit=$?"
```

```text
exit=1
```

Per the Docker CLI documentation, resources under `/proc`, `/sys`, `/dev`, tmpfs mounts and user-created mounts cannot be reliably copied with `docker cp`. Use the tar-over-exec pattern instead:

```bash
docker exec mnt tar -C /data -cf - . | tar -xf - -C ./data-copy
docker exec -i mnt tar -C /data -xf - < backup.tar
```

This requires `tar` in the image, but it reads the container's real mount view.

### 5.9 Volume Backup With a Helper Container

```bash
docker run --rm -v appdata:/data:ro -v "$PWD":/backup alpine:3.20 \
  tar -czf /backup/appdata.tgz -C /data .
```

The `:ro` flag guarantees the helper cannot alter the volume. Mount only the folder you want the archive in, not your home directory.

### 5.10 Bind Mount as the Alternative to Repeated cp

```bash
docker run -d --name dev -v "$PWD/site":/usr/share/nginx/html:ro -p 8080:80 nginx:1.27-alpine
echo "<h1>v2</h1>" > site/index.html     # visible immediately, no cp needed
```

## 6. Production Usage Notes

- **Do not treat `cp` as deployment.** Configuration should arrive via image build, environment, mounted configs/secrets or orchestrator objects, never by hand-copying into running containers; the change is lost on recreation and drifts across replicas.
- **Kubernetes parallel:** `kubectl cp` has the same tar-streaming model and the same requirement that `tar` exists in the container; it does not work on distroless images.
- **Diagnostics:** `docker cp` from a stopped container is a standard way to rescue state. In incident runbooks, copy first, then `docker rm`.
- **Large transfers:** the API call is a single stream through the Docker socket or TCP connection. Multi-gigabyte copies are slow and hold daemon resources; use volumes or a registry for bulk movement.
- **Read-only root filesystems:** copying *into* a container started with `--read-only` is rejected; copy into a writable mount or use a volume.
- **Remote daemons:** `DOCKER_HOST=ssh://...` makes `cp` act on the remote host's container, with the local side being your machine.
- **Alternatives for file exchange at scale:** shared named volumes between services, a registry or object store for artifacts, `docker build` with `COPY --from` for build artifacts ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)).

## 7. Security Considerations

- **Path traversal and symlink attacks:** copying *out* of an untrusted container can write attacker-chosen paths on the host if the tar contains `../` entries or symlinks. The Engine sanitizes and resolves paths within the container root, and fixes for symlink races (for example CVE-2018-15664 class issues) have been made, but keep the Engine patched and avoid running `docker cp` as root against untrusted containers.
- **Extract into a throwaway directory:** when pulling files from an untrusted container, copy into an empty scratch directory and inspect before moving anything.
- **Ownership surprises:** files copied in are root-owned by default; a world-writable copy of a secret is still readable by any process in the container. Use explicit modes before copying (`chmod 600`) and `-a` deliberately.
- **Secrets in the writable layer:** copying a secret into a container writes it to disk in the container layer, where it persists until removal and is included by `docker commit`. Prefer secrets mounts or tmpfs.
- **Daemon access is root-equivalent:** anyone who can reach the Docker socket can `docker cp` any file out of any container, including mounted-in host files ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Bind mount scope:** never bind-mount the home directory, a drive root, or cloud-synced folders just to exchange one file; mount only the single project folder, read-only when writing is not needed.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Error: No such container:path: web:/x` | Source path does not exist in the container | `docker exec web ls` or inspect a stopped container with `docker diff` |
| `cannot overwrite non-directory ... with directory` | Copying a directory onto an existing file | Choose a different destination or remove the file first |
| Output of `cp c:/file -` looks like binary garbage | `-` emits a tar archive, not the bare file | Pipe through `tar -xO`; remember `-` means tar stdin/stdout |
| Copied file not visible via the app | Path is covered by a volume or bind mount | Copy to the mount's source, or use the tar-over-exec pattern |
| `container rootfs is marked read-only` | Container started with `--read-only` | Copy to a writable mount or recreate without `--read-only` |
| App gets permission denied on copied file | File landed as root-owned, app runs as non-root | `docker cp -a`, or `docker exec -u 0 c chown app:app file` |
| Windows path mistaken for container name | `C:\x` parsed as `C` container | Use a relative path like `.\x` or `/c/x` in Git Bash |
| Copy from `/proc` or `/sys` fails | Special filesystems unsupported | `docker exec c cat /proc/...` redirect to a file |
| Copied data is gone after recreate | `docker rm`/recreate drops the writable layer | Use a volume or bind mount for persistence |
| `cp` hangs or is slow on huge trees | Single-stream tar through the API | Use a volume, or compress with tar piping |

## 9. Best Practices

- Use `docker cp` for **ad hoc** movement: debugging, rescue, artifact extraction. Use volumes and bind mounts for anything recurring.
- Always use `docker create` rather than `docker run` to extract from an image, so no entrypoint executes.
- Quote the trailing `/.` form when you intend "contents only" and test with `ls` afterward.
- Preserve ownership explicitly with `-a` when running non-root containers, or fix with `chown` after.
- For files that live in volumes or tmpfs, use `docker exec ... tar -cf - | tar -xf -`.
- Keep stream copies inside pipelines (`tar`, `gzip`, `ssh`) to avoid temporary files containing sensitive data.
- Mount volumes with `:ro` for backups, and mount only the project folder for bind mounts.
- Treat anything copied from an untrusted container as untrusted input on the host.
- Capture evidence before cleanup: copy files and `docker logs` ([§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md)) first, then remove.

## 10. Common Anti-Patterns / Mistakes

- Hot-patching production containers with `docker cp` instead of rebuilding the image.
- Expecting copied-in data to survive `docker rm` or a rolling update.
- Copying database files out of a running database container and calling it a backup (inconsistent state; use the database's dump tool).
- Using `cp` to synchronize a source tree for development on every change instead of a bind mount.
- Bind-mounting the entire home directory or drive to "make copying easy".
- Forgetting that `docker cp CONTAINER:file -` yields a tar and piping it straight into an application.
- Copying secrets into a container layer and then `docker commit`-ing it into an image.
- Assuming `cp` follows symlinks by default (it does not; pass `-L`).

## 11. Interview Questions

**🎯 Beginner:** _"How do you get a file out of a container that has already exited, and what happens to that file if you run `docker rm` first?"_
**Model answer:** Use `docker cp CONTAINER:/path/in/container ./local`. It works on stopped containers because the writable layer remains on disk until the container is removed. If you run `docker rm` first, the writable layer is deleted and the file is lost unless it lived in a volume or bind mount. So in a post-mortem you copy first, then remove. You can list what changed with `docker diff` to know what to look for.
_What the interviewer is probing for:_ Understanding that `cp` works against the container's writable layer and that its lifetime is the container's lifetime.

**🎯 Intermediate:** _"Explain the difference between `docker cp src web:/tmp/` and `docker cp src/. web:/tmp/`, and why files you copy in are owned by root."_
**Model answer:** Without `/.`, a directory `src` is copied as `/tmp/src`. With `/.`, only the contents are copied into `/tmp`, following `cp -a` rules. Ownership: the daemon unpacks the tar as root, so copied files are UID:GID 0:0 by default, and files copied out belong to the invoking user. The `-a` flag keeps the source UID:GID instead. If the container runs as a non-root user, the app may not be able to write to the copied files, so use `-a`, `chown` via `docker exec -u 0`, or better, bake the files into the image with `COPY --chown`.
_What the interviewer is probing for:_ Command semantics and awareness of the ownership gotcha.

**🎯 Senior:** _"A teammate copied a config file into a container and the app still reads the old values. List the possible causes and how you would verify each."_
**Model answer:** First, the path may be covered by a volume or bind mount, so the copy landed on the underlying layer while the app sees the mount; verify with `docker inspect --format '{{json .Mounts}}'` and `docker exec cat`. Second, the app reads config only at startup, so it needs a restart or reload signal. Third, the file may be root-owned with restrictive modes and the app falls back to defaults. Fourth, the container may have been recreated (the copy was in the old writable layer), or there are multiple replicas and only one was patched. Fifth, an environment variable may override the file. I would verify with `docker exec` reading the file as the app user, check `docker diff`, and then fix the real problem by baking config into the image or mounting it, not by patching by hand.
_What the interviewer is probing for:_ Systematic debugging across mounts, permissions, lifecycle and drift.

**🎯 Architect:** _"Design the standard for moving data into and out of containers across a platform with compliance requirements: config, secrets, artifacts, backups and incident evidence."_
**Model answer:** Separate by lifetime and sensitivity. Immutable inputs (code, default config) go in the image via `COPY`. Environment config goes through env or mounted read-only config objects; secrets through a secrets manager or orchestrator secrets mounted as tmpfs, never copied or baked. Persistent state lives in named volumes or managed storage, backed up with a helper container mounting the volume read-only, or with the database's native dump. Build artifacts leave through a registry or artifact store, with `docker create` plus `cp` used only inside CI. `docker cp` is reserved for break-glass diagnostics, restricted by socket access controls, logged through audit tooling, and followed by evidence handling rules. Enforce read-only root filesystems so hand-patching is impossible, and alert on exec and cp API calls via daemon audit logs.
_What the interviewer is probing for:_ Choosing mechanisms by data lifetime, governance and immutability principles.

## 12. Common Misconceptions

- "`docker cp` only works on running containers." It also works on stopped ones.
- "Copied files persist with the image." They live in the container's writable layer only.
- "`docker cp` can copy from volumes like any directory." Mounts, tmpfs, `/proc`, `/sys` and `/dev` are not reliably supported.
- "`docker cp c:file -` prints the file." It emits a tar archive.
- "It needs a shell or `cp` binary in the container." The Engine does the work; distroless is fine (unlike `kubectl cp`, which needs `tar`).
- "A bind mount and `docker cp` are equivalent." One is a live shared path, the other a one-time snapshot.

## 13. 🔑 Key Takeaways

- `docker cp` is a tar transport over the Engine API that works on running and stopped containers.
- Copied data lives in the writable layer and disappears with `docker rm`.
- Trailing `/.` means "contents of"; `-a` preserves UID:GID; `-L` follows symlinks; `-` streams tar.
- Mounts, tmpfs and `/proc`, `/sys`, `/dev` need the `docker exec ... tar` pattern instead.
- Use volumes and bind mounts for repeated or persistent exchange; `docker create` plus `cp` for artifacts.
- Treat contents of untrusted containers as untrusted when copying out.

## 14. Related Concepts & What's Next

Related: overlay2 and the writable layer ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), `COPY` and `ADD` at build time ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), `VOLUME` and `USER` ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), build context ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), container logs ([§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md)). Next, [§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md) covers `--memory`, `--cpus` and `--pids-limit`, the cgroup-backed controls that stop one container from starving the rest of the host.

**Next Section:** [§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md) — `Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md`
