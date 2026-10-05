# Section 28 (Part 4): Executing Commands in Running Containers: exec and attach

## 1. Definition

**Plain language:** `docker exec` starts a *new* process inside a container that is already running, which is how you open a shell, run a one-off diagnostic or trigger a maintenance task. `docker attach` does something different: it connects your terminal to the container's *existing* main process (PID 1) so you can see its output and send it input.

**Precise definition:** `docker exec [OPTIONS] CONTAINER COMMAND [ARG...]` asks the daemon to create an *exec instance* in a running container. The daemon (through containerd and runc, [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)) forks a new process that joins the container's existing namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) and cgroup ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), then streams its stdio back to the client. The exec process is not PID 1, is not supervised, is not restarted, and does not keep the container alive. `docker attach CONTAINER` instead binds the client's stdin/stdout/stderr to the container's main process stream, so the container's lifetime and your session are coupled.

Key `exec` options: `-i` (keep stdin open), `-t` (allocate a pseudo-TTY), `-d` (detached, run in background), `-u` (user), `-w` (working directory), `-e` / `--env-file` (extra environment), `--privileged` (extended privileges for the process), `--detach-keys`. Key `attach` options: `--no-stdin`, `--sig-proxy` (default true), `--detach-keys` (default `ctrl-p,ctrl-q`).

> 💡 **Tip:** `exec` = "start another process in there". `attach` = "plug into the process that is already running". When in doubt, you want `exec`.

## 2. Why This Matters

- **Debugging a live system:** inspecting config files, DNS, connectivity and processes inside the real runtime environment is the fastest way to confirm a hypothesis.
- **Operational tasks:** database migrations, cache clears, `psql`/`redis-cli` sessions and framework consoles are routinely run through `exec`.
- **Attach surprises:** pressing Ctrl-C in an attached session can stop the production container; many outages begin this way.
- **Security boundary:** anyone allowed to `exec` into a container effectively has that container's privileges, and often a path to the host.
- **Interviews and DCA:** the `exec` versus `attach` distinction, exit-code behavior and detach keys are classic questions.

## 3. Prerequisites and Dependencies

Requires `docker run` basics ([§26](Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), in particular `-i`, `-t` and `-d`, and the container lifecycle ([§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)): `exec` works only on a *running* (not paused, not stopped) container. Understanding why exec'd processes see the container's world needs namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) and cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)). PID 1 semantics and the `ENTRYPOINT`/`CMD` pair that defines the process you attach to are in [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md). The CLI-to-daemon streaming path is explained in [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md), and the `USER` default that exec inherits in [§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md). Moving files in and out without a shell is [§30](Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md).

## 4. Architecture / Conceptual Diagram

```text
   docker CLI                 dockerd                 containerd / runc          Container "web"
  ┌───────────┐  REST/HTTP   ┌──────────┐            ┌──────────────────┐   ┌───────────────────────┐
  │ docker    │ ───────────► │ exec     │ ─────────► │ runc exec        │   │ PID 1: nginx (main)   │
  │ exec -it  │  POST        │ create   │            │ (setns into      │   │   ▲                   │
  │ web sh    │  /containers │ + start  │            │  container ns)   │   │   │ attach streams    │
  └───────────┘  /web/exec   └──────────┘            └────────┬─────────┘   │   │ PID 1's stdio     │
        ▲                          │                          │ new process │   │                       │
        │   hijacked stdio stream  │                          ▼             │ PID 27: sh  ◄── exec  │
        └──────────────────────────┘                  joins same namespaces  │ PID 35: ps  ◄── exec  │
                                                      + same cgroup          └───────────────────────┘
   docker attach web ──────────────► stdio of PID 1 (nginx) directly

  Lifetime rules
  ┌──────────────────────┬──────────────────────────────┬─────────────────────────────────┐
  │                      │ docker exec                  │ docker attach                   │
  ├──────────────────────┼──────────────────────────────┼─────────────────────────────────┤
  │ Process involved     │ NEW process (own PID)        │ EXISTING PID 1                  │
  │ Exit of your session │ only that process ends       │ may stop container (Ctrl-C/exit)│
  │ Multiple sessions    │ independent                  │ all share the same streams      │
  │ Needs container -i   │ no (uses its own -i)         │ yes, for stdin to be forwarded  │
  │ Container stopped    │ exec process is killed       │ session ends                    │
  └──────────────────────┴──────────────────────────────┴─────────────────────────────────┘
```

- An exec process inherits the container's image config (user, working directory, base environment) but **not** variables an entrypoint script exported at runtime; those exist only in PID 1's environment.
- Exec processes are children of the container's shim/runtime, appear under `docker top`, and count against the container's cgroup limits.
- `attach` multiplexes onto the stream that `docker logs` also reads, so attached output is also logged ([§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md)).

## 5. Hands-On

### 5.1 Open an Interactive Shell

```bash
docker run -d --name web nginx:1.27
docker exec -it web bash
```

```text
root@3f2a9c1d5b7e:/# whoami
root
root@3f2a9c1d5b7e:/# ps aux | head -3
USER   PID %CPU %MEM    VSZ   RSS TTY   STAT START TIME COMMAND
root     1  0.0  0.1  11116  7936 ?     Ss   10:02 0:00 nginx: master process nginx -g daemon off;
nginx   29  0.0  0.0  11568  3072 ?     S    10:02 0:00 nginx: worker process
root@3f2a9c1d5b7e:/# exit
```

```bash
docker ps --filter name=web --format '{{.Names}} {{.Status}}'
```

```text
web Up 2 minutes
```

Exiting the exec shell did not touch the container. `-i` keeps stdin open and `-t` gives a terminal; you need both for an interactive shell. Alpine and distroless-style images may have no `bash`; use `sh` or see 5.9.

### 5.2 One-Off Commands and Exit Codes

```bash
docker exec web cat /etc/nginx/nginx.conf | head -4
docker exec web nginx -t
echo "exit code: $?"
docker exec web sh -c 'exit 7'; echo "exit code: $?"
```

```text
user  nginx;
worker_processes  auto;
nginx: configuration file /etc/nginx/nginx.conf test is successful
exit code: 0
exit code: 7
```

`docker exec` returns the exit status of the command, so it composes into scripts and health probes. Omit `-t` when piping output (a TTY converts `\n` to `\r\n` and merges stderr into stdout).

### 5.3 User, Working Directory and Environment

```bash
docker exec -u nginx -w /usr/share/nginx/html -e GREETING=hi web sh -c 'id -un; pwd; echo $GREETING'
docker exec -u 0 web id
docker exec web printenv NGINX_VERSION
```

```text
nginx
/usr/share/nginx/html
hi
uid=0(root) gid=0(root) groups=0(root)
1.27.1
```

Without `-u`, the process uses the container's configured user (image `USER` or `--user` at run time, [§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)). `-u 0` is the standard way to get root for a diagnostic in an image that otherwise runs unprivileged. `-e` applies only to this exec process.

### 5.4 Detached Execs

```bash
docker exec -d web sh -c 'sleep 120; echo done > /tmp/job.done'
docker top web
docker inspect web --format '{{json .ExecIDs}}'
```

```text
UID    PID    PPID   C STIME TTY   TIME CMD
root   2411   2390   0 10:02 ?     00:00:00 nginx: master process nginx -g daemon off;
root   2518   2390   0 10:05 ?     00:00:00 sleep 120
["b7c1e0..."]
```

`-d` returns immediately and discards output. The job dies if the container stops or restarts; do not use detached exec as a job scheduler.

### 5.5 What Exec Sees: Namespaces and PID 1

```bash
docker exec web readlink /proc/1/ns/pid /proc/self/ns/pid
docker exec web sh -c 'echo "my pid: $$"; cat /proc/1/cmdline | tr "\0" " "'
```

```text
pid:[4026532611]
pid:[4026532611]
my pid: 48
nginx: master process nginx -g daemon off;
```

Same namespace ID proves the exec process lives inside the container's PID namespace, even though it is not PID 1.

### 5.6 Attach to the Main Process

```bash
docker run -dit --name pinger alpine:3.20 ping 127.0.0.1
docker attach pinger
```

```text
64 bytes from 127.0.0.1: seq=41 ttl=64 time=0.060 ms
64 bytes from 127.0.0.1: seq=42 ttl=64 time=0.058 ms
^P^Q                       # detach sequence: container keeps running
read escape sequence
```

```bash
docker ps --filter name=pinger --format '{{.Status}}'
```

```text
Up About a minute
```

The default detach sequence is Ctrl-P then Ctrl-Q. Attaching shows output from the moment you connect (use `docker logs` for history, [§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md)).

### 5.7 Attach Pitfalls: Ctrl-C and the Missing Stdin

```bash
docker run -d --name quiet alpine:3.20 sleep 600
docker attach quiet            # no -i at run time: stdin is not wired up, typing does nothing
```

```bash
docker run -dit --name risky alpine:3.20 sh
docker attach risky
/ # exit                        # exits PID 1: the container stops
docker ps -a --filter name=risky --format '{{.Status}}'
```

```text
Exited (0) 2 seconds ago
```

With `--sig-proxy=true` (default) and no TTY, Ctrl-C is forwarded to PID 1 as SIGINT and can stop the container. With a TTY (`-t`), Ctrl-C is delivered as a character to the terminal line discipline instead, and whether PID 1 reacts depends on the program. Safer options: `docker attach --sig-proxy=false NAME`, a custom `--detach-keys`, or simply use `exec`.

```bash
docker attach --detach-keys="ctrl-x" --sig-proxy=false pinger
```

### 5.8 Windows and Git Bash TTY Quirks

```bash
docker exec -it web bash
# Git Bash on Windows: "the input device is not a TTY"
winpty docker exec -it web bash
# or run from PowerShell / Windows Terminal, or:
MSYS_NO_PATHCONV=1 docker exec -it web ls /etc     # stop path rewriting of /etc
```

Git Bash (MinTTY) is not a real console, so TTY allocation fails without `winpty`. Git Bash also rewrites arguments that look like POSIX paths; `MSYS_NO_PATHCONV=1` or a double leading slash (`//etc`) avoids it.

### 5.9 Debugging Images with No Shell

```bash
docker exec distroless-app sh
# OCI runtime exec failed: exec: "sh": executable file not found in $PATH

# Attach a tooling container to the target's namespaces instead
docker run --rm -it --pid=container:distroless-app --network=container:distroless-app \
  nicolaka/netshoot bash
```

```text
bash-5.2# ps aux
PID   USER   COMMAND
  1   65532  /app/server
 14   root   bash
bash-5.2# ss -ltnp
LISTEN 0 4096 *:8080 *:* users:(("server",pid=1,fd=3))
```

A sidecar sharing the PID and network namespaces gives you full tooling without changing the image. File access to the target's filesystem is via `/proc/1/root/`. Docker Desktop also offers `docker debug` for this purpose, and Kubernetes has `kubectl debug` with ephemeral containers.

### 5.10 Verifying Exec Is Gone After Restart

```bash
docker exec -d web sh -c 'sleep 999'
docker restart web
docker exec web pgrep -x sleep || echo "no sleep process"
```

```text
no sleep process
```

Restart kills every exec'd process; only the original command (with the same `ENTRYPOINT`/`CMD`) comes back.

## 6. Production Usage Notes

- **Treat exec as a break-glass tool.** Prefer changing the image, config or deployment over manual fixes inside a running container; changes made via exec live in the writable layer and vanish when the container is replaced.
- **Orchestrators:** `kubectl exec` and `docker exec` share the same model. Keep the habit of using logs and metrics first, exec second.
- **Scripts and cron jobs:** use `docker exec` without `-t`, check the exit code, and wrap with `timeout` since the call blocks until the command ends.
- **Database and framework tasks:** `docker exec -u postgres db psql -c '...'`, `docker exec app python manage.py migrate`. For recurring work, prefer a separate short-lived `docker run --rm` using the same image.
- **Concurrency:** many exec sessions are fine, but each consumes memory from the container's cgroup limit; a forgotten `exec -d` job can trigger an OOM kill of the whole container.
- **Auditing:** daemon audit rules (for example auditd watching the socket) and Docker events (`docker events --filter event=exec_start`, `exec_die`) record who ran what; commands run via exec are visible in `docker events` with the full command line.
- **Minimal images:** plan your debugging story before shipping distroless or `scratch` images (ephemeral debug container, `docker debug`, or a `-debug` image variant).

## 7. Security Considerations

- **`exec` is container root-equivalent for the container's user.** Access to the Docker socket or `docker` group membership allows `docker exec -u 0` into any container and `docker run --privileged` on the host, so it is host root in practice. Restrict who can reach the daemon ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **`--privileged` on exec** grants all capabilities and device access to that process even if the container was started unprivileged. Avoid it; it bypasses much of the isolation chosen at `docker run`.
- **Secrets on the command line:** `-e SECRET=...` is stored in the exec metadata and visible in `docker events` and process listings. Use `--env-file` with restrictive permissions or read from a mounted file.
- **Seccomp, AppArmor and capability limits still apply** to exec processes, which is useful: an exec shell cannot exceed the container's confinement unless `--privileged` is given.
- **Interactive access is not a deployment mechanism.** Reproduce fixes through the image build so they are reviewed and traceable.
- **Attach exposes sensitive output.** Anything printed by PID 1 (tokens in debug logs) becomes visible to the attaching user, and multiple attached clients all see the same stream.
- **Shell-free images reduce exec abuse:** distroless and `scratch` images have no shell to drop into, raising the bar for attackers who gain exec rights, though not eliminating it.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Error response from daemon: container ... is not running` | Container exited or crashed | `docker ps -a`, check `docker logs`, fix the crash; exec cannot start a stopped container |
| `container ... is paused` | Frozen with `docker pause` | `docker unpause` first ([§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)) |
| `OCI runtime exec failed: exec: "bash": executable file not found in $PATH` | Image has no bash (Alpine, distroless) | Use `sh`, or an ephemeral debug container (5.9) |
| `the input device is not a TTY` | `-t` used from a script, CI job or Git Bash | Drop `-t`, use `winpty` on Git Bash, or run from a real terminal |
| Output has stray `\r` characters when piped | TTY allocated with `-t` | Remove `-t` for non-interactive use |
| Typing in `docker attach` does nothing | Container started without `-i` | Recreate with `-it`, or use `exec` |
| Container stops when you leave `attach` | You exited or interrupted PID 1 | Detach with Ctrl-P Ctrl-Q; set `--sig-proxy=false`; use `exec` |
| Ctrl-P Ctrl-Q does nothing, or the shell lags | Shell captures Ctrl-P (history) or conflicts with readline | Set `--detach-keys "ctrl-x"` or `detachKeys` in `~/.docker/config.json` |
| Variable set in entrypoint missing in exec shell | Exec gets image/run env, not PID 1's runtime exports | Pass `-e`, or read `/proc/1/environ` (`tr '\0' '\n' < /proc/1/environ`) |
| Exec'd process missing after a while | Container restarted (policy or crash) | Check `docker inspect --format '{{.RestartCount}}'`; run jobs as separate containers |
| `exec` hangs | Command waits for stdin or never ends | Add `-d`, redirect stdin (`< /dev/null`), or wrap in `timeout` |
| Git Bash converts `/etc` to `C:/Program Files/Git/etc` | MSYS path conversion | `MSYS_NO_PATHCONV=1` or `//etc` |

## 9. Best Practices

- Use `docker exec -it NAME sh` for ad hoc work and `docker exec NAME cmd` (no `-t`) in scripts.
- Prefer `exec` over `attach` for everything except watching a TTY-based foreground program.
- If you must attach, set a safe `--detach-keys` and `--sig-proxy=false`, and know how to detach before you start.
- Read state first (`docker logs`, `docker inspect`, `docker top`) and exec second.
- Use `-u` explicitly when the user matters (file ownership of generated files, least privilege).
- Do not make lasting changes in a running container; encode them in the Dockerfile or deployment and redeploy.
- Give every long-lived container a debugging path: a shell in dev images, an ephemeral tooling container for minimal images.
- Capture `exec_start` and `exec_die` events centrally on shared hosts.
- Pass non-secret data with `-e` and secrets via files or a secret manager.

## 10. Common Anti-Patterns / Mistakes

- Using `docker attach` to "get a shell" and then typing `exit`, which stops production.
- Treating a container like a VM: SSH-ing in (or running sshd) for maintenance instead of `exec` plus immutable redeploys.
- Fixing a production bug with `exec` and `vi` and never updating the image.
- Using `docker exec -d` as a job scheduler, with no retries or visibility.
- Running `docker exec -it` in cron or CI, causing "not a TTY" failures and hung jobs.
- Granting developers the `docker` group on shared production hosts so they can exec anywhere.
- Passing passwords with `-e PASSWORD=...` in shell history.
- Expecting `exec` to inherit variables exported only by the entrypoint script.
- Installing debugging tools into the production image "just in case".

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `docker exec` and `docker attach`, and which one would you use to get a shell in a running container?"_
**Model answer:** `docker exec` starts a new process inside the running container, for example `docker exec -it web sh`; when that process exits only it ends and the container continues. `docker attach` connects your terminal to the container's main process (PID 1), so you see its output and send it input, and exiting or interrupting it can stop the container. For a shell you use `exec` with `-i` for stdin and `-t` for a terminal. To leave an attach session without stopping the container, use the detach sequence Ctrl-P then Ctrl-Q.
_What the interviewer is probing for:_ A clear model of "new process" versus "existing PID 1" and awareness of the attach risk.

**🎯 Intermediate:** _"You ran `docker exec app env` and a variable that the entrypoint script exports is missing, and `docker exec -it app bash` fails on an Alpine image. Explain both, and how you would get a debug shell anyway."_
**Model answer:** An exec process is created fresh from the container's configuration (image `Env`, `-e` at run time, and any `-e` on the exec), so variables exported by the entrypoint script exist only in PID 1's environment. Read them from `/proc/1/environ` or re-run the same setup. Alpine ships BusyBox `sh` and no bash, so use `docker exec -it app sh` or install nothing and instead start a tooling container that shares namespaces. For a shell-less image, run `docker run --rm -it --pid=container:app --network=container:app nicolaka/netshoot`, which provides tools while the target stays unchanged.
_What the interviewer is probing for:_ How exec constructs its environment and practical handling of minimal images.

**🎯 Senior:** _"A team reports that a cron job running `docker exec -it worker python task.py` intermittently hangs and sometimes the output contains carriage returns. Diagnose and harden the approach."_
**Model answer:** Under cron there is no TTY, so `-t` either fails with "the input device is not a TTY" or, in wrappers that fake one, converts newlines to CRLF and merges stderr into stdout, and `-i` can block waiting for a stdin that never closes. Remove `-t` (and `-i` unless input is needed), redirect stdin from `/dev/null`, wrap with `timeout`, and check `$?` since exec propagates the command's exit code. Better, run the task as its own short-lived `docker run --rm` with the same image, or a scheduled job in the orchestrator, so it has its own resource limits, logs and restart semantics; an exec'd process shares the service container's cgroup and dies when the container restarts. Add `docker events --filter event=exec_die` or application-level logging for observability.
_What the interviewer is probing for:_ TTY semantics, exit code propagation, and recognizing that exec is the wrong scheduling primitive.

**🎯 Architect:** _"Define your organization's policy for interactive access to production containers across Docker hosts and Kubernetes, balancing incident response with security and auditability."_
**Model answer:** Default to no interactive access: observability (logs, metrics, traces) and immutable redeploys solve most problems. Provide break-glass access that is time-bound, approved and logged: no standing membership in the `docker` group, access via a bastion or an RBAC-controlled path (`kubectl exec` guarded by RBAC and audit logging, or a session-recording tool), with `exec_start` events and API audit logs shipped to a SIEM. Ship minimal, non-root, shell-less production images, and standardize an ephemeral debug container (netshoot or `kubectl debug`) that is only attachable under the break-glass role. Forbid `--privileged` exec, disallow persistent changes (read-only root filesystems make unauthorized edits impossible), and review every break-glass event post-incident, converting each manual fix into code or an image change.
_What the interviewer is probing for:_ Least privilege, auditability, immutability, and a practical operational model rather than blanket prohibition.

## 12. Common Misconceptions

- "`docker attach` opens a new shell." It connects to PID 1's existing streams; no new process starts.
- "Exiting `docker exec` stops the container." Only the exec process ends.
- "Ctrl-C always detaches." The detach sequence is Ctrl-P Ctrl-Q; Ctrl-C is forwarded as SIGINT by default.
- "`exec` works on stopped or paused containers." It requires a running container.
- "Exec sessions get the same environment as PID 1." They get the configured environment, not runtime exports.
- "Changes I make via exec are saved." They persist only in that container's writable layer and are lost on replacement.
- "Multiple `attach` sessions are independent." They share one stream.

## 13. 🔑 Key Takeaways

- `docker exec` spawns a new process in the container's namespaces and cgroup; `docker attach` binds to PID 1's stdio.
- Use `-it` for interactive shells, no `-t` for scripts, and read the exit code.
- Detach from attach with Ctrl-P Ctrl-Q; `--sig-proxy=false` prevents Ctrl-C from reaching PID 1.
- Exec needs a running container, dies on restart, and does not see entrypoint-exported variables.
- Minimal images need an ephemeral tooling container sharing `--pid` and `--network`.
- Exec access equals privileged access; restrict, audit and avoid `--privileged`.

## 14. Related Concepts & What's Next

Related: `docker run` flags ([§26](Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), lifecycle states ([§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), PID 1 and `CMD`/`ENTRYPOINT` ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), daemon socket security ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), image inspection ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)). Next, [§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md) covers container logs and log drivers: the non-interactive way to see what a container's main process is doing, which is usually where debugging should start before you reach for `exec`.

**Next Section:** [§29](Section-29-Part4-Container-Logs-and-Log-Drivers.md) — `Section-29-Part4-Container-Logs-and-Log-Drivers.md`
