# Section 26 (Part 4): docker run Deep Dive: Flags and Common Patterns

## 1. Definition

**Plain language:** `docker run` takes an image and turns it into a running container in one step. Every flag you put before the image name changes how that container is isolated, configured, networked and cleaned up; everything after the image name is the command or arguments.

**Precise definition:** `docker run [OPTIONS] IMAGE [COMMAND] [ARG...]` is a convenience wrapper over three API calls: `POST /containers/create` (build the container's writable layer and config from the image config plus your flags), `POST /containers/{id}/start` (ask containerd and runc to create namespaces and cgroups and exec the process, see [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) and [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)), and, unless `-d` is set, an attach to the container's stdio plus a wait for exit. If the image is not present locally it is pulled first (`--pull=missing` is the default). Flags override image defaults from the config ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)): `ENTRYPOINT`/`CMD` ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), `ENV`/`WORKDIR` ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), `USER` and `EXPOSE` ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)). The exit status of `docker run` is the container's exit status, except for the reserved codes 125, 126 and 127.

> 💡 **Tip:** Flags go before the image name. Anything after the image name is passed to the container, so `docker run alpine -d` hands `-d` to the container's command rather than detaching.

## 2. Why This Matters

- `docker run` is the most-typed Docker command; most "works on my machine" differences are a missing or mistaken flag (port binding, env, user, mounts).
- Flags are the first line of security and resource policy: `--read-only`, `--cap-drop`, `--user`, `--memory` are all set here, and Compose or Kubernetes simply re-expose the same kernel features.
- Exit codes and attach behavior decide whether scripts and CI jobs notice a failing container.
- It is the largest single topic on the DCA exam's orchestration and installation domains and a staple of practical interviews.

## 3. Prerequisites and Dependencies

Requires the image model ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), CMD/ENTRYPOINT precedence ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), and the kernel features the flags configure: namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) and cgroups v2 ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)). The client/daemon split ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)) explains why `--env-file` and relative bind-mount paths are resolved on the client while mount sources are resolved on the daemon host. The stages after creation are covered in [§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md); networking, volumes, resource limits and restart policies get their own parts and sections (§31, §32).

## 4. Architecture / Conceptual Diagram

```text
 docker run [FLAGS] IMAGE [CMD...]
      │
      ▼  (CLI: parse flags, read --env-file, resolve --pull)
 ┌─────────────────────────────────────────────────────────────┐
 │ dockerd                                                     │
 │  1. pull image if absent        (--pull=missing)            │
 │  2. CREATE  merge image config + flags ► container config   │
 │             add RW layer, allocate name/ID, set up mounts   │
 │  3. START   network namespace + veth ► bridge, publish -p   │
 │             hand OCI spec to containerd ► runc              │
 └───────────────────────┬─────────────────────────────────────┘
                         ▼
 runc: clone(namespaces) ► cgroup limits ► pivot_root ► drop caps
       ► seccomp ► exec ENTRYPOINT+CMD  (PID 1 in the container)
                         │
      foreground ◄───────┴───────► -d: print ID, return at once
      attach stdio, proxy signals,
      exit with container's exit code

 Flag families
 ┌──────────────┬────────────────────────────────────────────────┐
 │ Identity     │ --name --hostname --label --platform           │
 │ Process      │ --entrypoint -w -u -e --env-file --init -t -i  │
 │ Networking   │ -p -P --network --dns --add-host               │
 │ Storage      │ -v --mount --tmpfs --read-only                 │
 │ Resources    │ -m --cpus --pids-limit --ulimit                │
 │ Security     │ --cap-add/-drop --security-opt --privileged    │
 │ Lifecycle    │ -d --rm --restart --stop-signal --stop-timeout │
 └──────────────┴────────────────────────────────────────────────┘
```

- **Merge order:** image config provides defaults; flags override them; `-e` overrides image `ENV` of the same name.
- **Foreground vs detached:** foreground ties your terminal to PID 1; detached returns the full container ID and leaves the container to the daemon.
- **Reserved exit codes:** 125 means the daemon failed to run the container, 126 means the command was found but not executable, 127 means the command was not found, and 128+N means the process died from signal N (137 = SIGKILL, 143 = SIGTERM).

## 5. Hands-On

### 5.1 Foreground, Interactive and Detached

```bash
docker run --rm alpine:3.20 echo hello
docker run --rm -it alpine:3.20 sh
docker run -d --name web nginx:1.27
docker ps --filter name=web
```

```text
hello
/ #                       # interactive shell; exit to leave
3f1c9a0e5c7b...           # -d prints the container ID
CONTAINER ID   IMAGE        COMMAND                  STATUS         NAMES
3f1c9a0e5c7b   nginx:1.27   "/docker-entrypoint.…"   Up 2 seconds   web
```

`-i` keeps stdin open and `-t` allocates a pseudo-terminal. You need both for a usable shell; `-t` alone gives a prompt that cannot receive input, and `-i` alone gives input with no line editing. To detach from a running `-it` container without stopping it, press `Ctrl-p Ctrl-q` (customizable with `--detach-keys`).

### 5.2 Naming, Cleanup and Exit Codes

```bash
docker run --rm --name once alpine:3.20 sh -c 'exit 7'; echo "exit=$?"
docker run --rm alpine:3.20 nosuchcmd;                   echo "exit=$?"
docker run --rm alpine:3.20 /etc/passwd;                 echo "exit=$?"
docker run --rm --nope alpine:3.20;                      echo "exit=$?"
```

```text
exit=7
docker: Error response from daemon: ... exec: "nosuchcmd": executable file not found in $PATH
exit=127
docker: Error response from daemon: ... exec: "/etc/passwd": permission denied
exit=126
unknown flag: --nope
exit=125
```

`--rm` deletes the container (and its anonymous volumes) after it exits. It cannot be combined with `--restart` other than `no`, because a restart policy needs the container to persist.

### 5.3 Environment Variables

```bash
export DB_PASS=s3cret
docker run --rm -e MODE=dev -e DB_PASS alpine:3.20 env | grep -E 'MODE|DB_PASS'
printf 'A=1\nB=two words\n# comment\n' > app.env
docker run --rm --env-file app.env alpine:3.20 env | grep -E '^(A|B)='
```

```text
MODE=dev
DB_PASS=s3cret
A=1
B=two words
```

`-e NAME` with no value copies the variable from the client's environment. In `--env-file`, each line is `KEY=value`, lines starting with `#` are ignored, and quotes are not stripped (a `"` would become part of the value). Values passed this way are visible in `docker inspect`; see section 7.

### 5.4 Publishing Ports

```bash
docker run -d --name w1 -p 8080:80 nginx:1.27
docker run -d --name w2 -p 127.0.0.1:8081:80 nginx:1.27
docker run -d --name w3 -P nginx:1.27
docker port w1; docker port w3
```

```text
80/tcp -> 0.0.0.0:8080
80/tcp -> [::]:8080
80/tcp -> 0.0.0.0:32768
```

`-p HOST:CONTAINER` publishes explicitly; prefix an IP to restrict the interface. `-P` publishes every port the image `EXPOSE`s to random high host ports. `EXPOSE` alone publishes nothing ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)).

### 5.5 Mounts: -v vs --mount, tmpfs and Read-Only Roots

```bash
mkdir -p "$PWD/site" && echo hi > "$PWD/site/index.html"
docker run -d --name m1 -v "$PWD/site:/usr/share/nginx/html:ro" nginx:1.27
docker run --rm --mount type=bind,src="$PWD/nope",dst=/x alpine:3.20 true
docker run --rm --read-only --tmpfs /tmp:rw,size=16m alpine:3.20 \
  sh -c 'touch /tmp/ok && echo tmp-ok; touch /etc/x'
```

```text
docker: Error response from daemon: invalid mount config for type "bind": bind source path does not exist: .../nope
tmp-ok
touch: /etc/x: Read-only file system
```

`-v` silently creates a missing host source directory (as root), whereas `--mount` fails loudly, which is why `--mount` is preferred in scripts. `--read-only` makes the image layers' root filesystem read-only; writable scratch space is added back with `--tmpfs` or volumes.

### 5.6 Identity, Working Directory and User

```bash
docker run --rm -u 1000:1000 -w /work -v "$PWD:/work" alpine:3.20 sh -c 'id; pwd; touch made-by-1000'
docker run --rm --hostname build01 --add-host db.internal:10.0.0.5 alpine:3.20 \
  sh -c 'hostname; grep db.internal /etc/hosts'
```

```text
uid=1000 gid=1000
/work
build01
10.0.0.5	db.internal
```

Files created through a bind mount are owned by the UID the container runs as, so `-u "$(id -u):$(id -g)"` is the usual way to avoid root-owned files in a working tree.

### 5.7 Overrides: Entrypoint, Platform, Pull Policy and Init

```bash
docker run --rm --entrypoint /bin/sh alpine:3.20 -c 'echo from-override'
docker run --rm --platform linux/arm64 alpine:3.20 uname -m
docker run --rm --pull=always alpine:3.20 true
docker run -d --init --name i1 alpine:3.20 sleep 300 && docker exec i1 ps -o pid,args
```

```text
from-override
aarch64
PID   COMMAND
    1 /sbin/docker-init -- sleep 300
    7 sleep 300
```

Running a non-native `--platform` requires QEMU/binfmt emulation. `--init` inserts Docker's bundled tini as PID 1 to forward signals and reap zombies ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).

### 5.8 A Hardened Service Run

```bash
docker run -d --name api \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges \
  --memory 256m --cpus 0.5 --pids-limit 100 \
  --restart unless-stopped \
  -u 10001:10001 \
  -p 127.0.0.1:8443:8443 \
  --label app=api --label env=prod \
  myorg/api:1.4.2
docker inspect api --format '{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.Memory}} {{.HostConfig.RestartPolicy.Name}}'
```

```text
true 268435456 unless-stopped
```

This is the pattern to template: least privilege, bounded resources, loopback-only publishing behind a reverse proxy, a pinned tag, and labels for later filtering (`docker ps --filter label=env=prod`).

## 6. Production Usage Notes

- **Pin image tags or digests** ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)); `docker run app:latest` is non-reproducible.
- **Prefer `--mount`** over `-v` in automation for explicit, fail-fast semantics.
- **Always name long-lived containers** and label them; random names do not survive into runbooks.
- **Use `--restart`** (`unless-stopped` or `on-failure:5`) for single-host services, and add health checks (§32).
- **Set resource limits** on every non-trivial container. Under cgroup v2, `--memory` maps to `memory.max` and `--cpus` to `cpu.max`; the OOM killer acts inside that cgroup only ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)).
- **Treat `docker run` as a development and single-host tool.** For anything declarative, translate flags into a Compose file or Kubernetes manifest so they live in version control.
- **CI usage:** `docker run --rm` plus the exit code is a clean pass/fail primitive; mount the workspace and pass `-u "$(id -u):$(id -g)"`.
- **Detached containers log to the daemon**; check `docker logs` rather than expecting terminal output (§29).

## 7. Security Considerations

- **`--privileged`** grants all capabilities, disables seccomp and AppArmor confinement, and exposes host devices. It is effectively root on the host; use targeted `--cap-add` or `--device` instead.
- **`-v /var/run/docker.sock:/var/run/docker.sock`** hands the container full control of the daemon, which equals host root.
- **Never mount** `/`, `/etc`, the home directory or cloud-credential folders into a container; mount the narrowest path, read-only where possible.
- **Default user is root** unless the image sets `USER`. Run with `-u` a non-root UID, `--cap-drop ALL`, and `--security-opt no-new-privileges`.
- **Published ports bypass host firewalls** such as ufw and firewalld rules on the INPUT chain, because Docker programs its own iptables/nftables rules. Bind to `127.0.0.1` unless the service must be public.
- **Secrets in `-e` or `--env-file`** appear in `docker inspect`, `/proc/<pid>/environ` and sometimes crash dumps. Prefer mounted secret files (tmpfs or orchestrator secrets) and keep `.env` files out of Git.
- **`--pid=host`, `--net=host`, `--ipc=host`, `--userns=host`** drop namespace isolation ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)); allow them only with explicit justification.
- **Access to the Docker socket is access to every flag above**; restrict who may run containers (docker group membership is root-equivalent).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Bind for 0.0.0.0:8080 failed: port is already allocated` | Host port in use by another container or process | Pick another host port, or find the owner with `docker ps` / `ss -ltnp` |
| `docker: Error response from daemon: Conflict. The container name "/web" is already in use` | A stopped container still holds the name | `docker rm web` or use `--rm` / a new name |
| Exit code 127 or "executable file not found" | Typo, missing binary, or exec form given a shell builtin | Check `docker run --entrypoint sh img -c 'command -v x'`; use full path |
| Exit code 126 / `permission denied` | Script not executable or `noexec` mount | `chmod +x`, or `COPY --chmod=755` |
| Exit code 137 | SIGKILL: OOM kill or `docker kill` / stop timeout | `docker inspect -f '{{.State.OOMKilled}}'`; raise `--memory` or fix the leak |
| Shell prompt appears but typing does nothing | Used `-t` without `-i` | Use `-it` |
| Files in bind mount owned by root | Container ran as root | Run with `-u "$(id -u):$(id -g)"` |
| Service unreachable from host | App binds `127.0.0.1` inside the container | Bind `0.0.0.0` in the app; keep `-p` restrictive on the host side |
| `exec format error` | Image architecture differs from host | Use a matching image or `--platform` with emulation |
| `--env-file` value includes quotes | Docker does not parse shell quoting | Remove quotes from the file |
| `-v ./rel:/x` treated as a named volume | Relative path without `./` or `$PWD` | Use an absolute path or `"$PWD/rel"` |

## 9. Best Practices

- Put flags in a consistent order: lifecycle, identity, process, networking, storage, resources, security, image, command.
- Use `--rm` for one-off and CI containers, `--name` and `--restart` for services.
- Bind published ports to a specific interface; default to `127.0.0.1`.
- Run as non-root with dropped capabilities and a read-only root filesystem, adding back only what the workload proves it needs.
- Use `--mount` and `--env-file` in scripts; avoid `-e SECRET=value` on a shared shell where history or process lists are visible.
- Add `--init` when the application is not a proper PID 1.
- Capture working invocations as Compose files once they exceed about five flags.
- Verify what actually applied with `docker inspect` rather than assuming flag effects.

## 10. Common Anti-Patterns / Mistakes

- Putting flags after the image name, so they become arguments to the container command.
- Using `--privileged` to "make it work" instead of finding the one missing capability or device.
- Mounting the Docker socket into application containers.
- Relying on `latest` and `docker run` with no `--pull` policy in production.
- Running `docker run -it` inside non-interactive CI and getting "the input device is not a TTY".
- Publishing a database port to `0.0.0.0` on a cloud VM.
- Using `-v` with a typo'd host path and silently getting an empty root-owned directory.
- Forgetting `--rm` in loops and leaving thousands of exited containers.
- Treating `-d` plus `sleep infinity` as a service design.

## 11. Interview Questions

**🎯 Beginner:** _"What actually happens when you run `docker run -d -p 8080:80 nginx`? Include what each part does."_
**Model answer:** The client asks the daemon to create a container: if `nginx:latest` is not local it is pulled, then a container is created from the image config (a writable layer on top of the read-only layers) and started. `-d` means the client does not attach and prints the container ID. `-p 8080:80` adds a NAT rule so connections to host port 8080 are forwarded to port 80 in the container's network namespace. The default command comes from the image's ENTRYPOINT/CMD. Without `-d`, the terminal would stay attached to nginx's output; without `-p`, the service would be reachable only from other containers on the same network. Using `latest` is convenient but not reproducible.
_What the interviewer is probing for:_ That `run` is create plus start plus attach, and that `-p` is distinct from `EXPOSE`.

**🎯 Intermediate:** _"A CI job runs `docker run myimage make test` and always shows green even though tests fail. How do you investigate?"_
**Model answer:** `docker run` propagates the container's exit code, so first check whether the command really returns non-zero (`docker run ...; echo $?`). Common causes are the pipeline swallowing the status (`| tee` without `pipefail`), a `-d` run where the client returns immediately, or an entrypoint script that ends without `exec` and masks the child's code. Also check for the reserved codes: 125 (daemon error), 126, 127. If it is detached, use `docker wait` to retrieve the status. Fix by running in the foreground with `--rm`, setting `set -o pipefail`, and ensuring the entrypoint uses `exec "$@"`.
_What the interviewer is probing for:_ Exit-code semantics and attach versus detach behavior.

**🎯 Senior:** _"Design the `docker run` invocation for an internet-facing stateless API on a single host, and justify each flag."_
**Model answer:** Pinned image digest or version tag; `-d --name --restart unless-stopped` for operability; `-u` non-root, `--cap-drop ALL` with only the capabilities needed, `--security-opt no-new-privileges`, `--read-only` with `--tmpfs /tmp` to contain compromise; `--memory`, `--cpus` and `--pids-limit` to bound blast radius via cgroup v2; `-p 127.0.0.1:PORT:PORT` behind a TLS-terminating reverse proxy because published ports bypass host firewall rules; env from a mounted secret file rather than `-e`; `--init` if the app does not reap children; a `--health-cmd`; log options to cap file size. Then I would say this belongs in Compose so it is reviewable, and I would verify with `docker inspect` and a negative test (writing to `/`, binding a low port, fork bomb).
_What the interviewer is probing for:_ Applying isolation, resource and network flags with reasons, and awareness of the firewall bypass.

**🎯 Architect:** _"Teams across the company run `docker run` with ad-hoc flags on shared build hosts. How do you reduce risk and inconsistency without banning Docker?"_
**Model answer:** Remove direct daemon access where possible: rootless Docker or per-job ephemeral runners so `--privileged` and socket mounts cannot escape to a shared host. Where the daemon is shared, front it with an authorization plugin or policy proxy that rejects dangerous flags (`--privileged`, host namespaces, sensitive bind mounts), and set daemon-level defaults in `daemon.json` (userns-remap, default ulimits, log rotation, `no-new-privileges`). Provide blessed Compose templates and wrapper scripts with hardened defaults, scan images in CI, and enforce the same policy in the orchestrator via admission control so the rules do not differ between laptop and cluster. Audit with daemon events and `docker inspect` exports.
_What the interviewer is probing for:_ Policy enforcement at the daemon and platform level rather than reliance on developer discipline.

## 12. Common Misconceptions

- "`EXPOSE` publishes the port." It only documents it; `-p` or `-P` publishes.
- "`docker run` always creates a new image." It creates a container; images are unchanged.
- "`-d` makes the container restart if it crashes." That needs `--restart`.
- "`--rm` removes named volumes." It removes only anonymous volumes of that container.
- "Everything after `docker run` is a Docker option." Only what precedes the image name.
- "Published ports are protected by my host firewall." Docker's own rules typically take precedence.
- "`-v` and `--mount` are identical." `-v` creates missing host paths; `--mount` errors.

## 13. 🔑 Key Takeaways

- `docker run` = pull if missing, create, start, then attach unless `-d`.
- Flags precede the image; the rest is the container command.
- Exit codes: 125 daemon error, 126 not executable, 127 not found, 128+N signal.
- `-p` publishes, `EXPOSE` documents; bind to `127.0.0.1` unless public.
- Harden by default: non-root, `--cap-drop ALL`, `--read-only`, resource limits.
- Prefer `--mount`, pinned tags, `--rm` for one-offs and Compose for repeatable setups.

## 14. Related Concepts & What's Next

Related: CMD/ENTRYPOINT overrides ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), `ENV` and `WORKDIR` ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), `EXPOSE`, `VOLUME` and `USER` ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), image inspection ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)), namespaces and cgroups ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)). Next, [§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md) breaks `docker run` into its separate lifecycle commands and explains the states and signals behind stop, pause and kill.

**Next Section:** [§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md) — `Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md`
