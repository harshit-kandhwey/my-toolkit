# Section 18 (Part 3): CMD vs ENTRYPOINT: Semantics and Interactions

## 1. Definition

**Plain language:** `ENTRYPOINT` says *what program* the container is for; `CMD` supplies *default arguments* (or a default command when there is no entrypoint). Anything you type after the image name in `docker run` replaces `CMD` but not `ENTRYPOINT`.

**Precise definition:** Both instructions store process definitions in the image config ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) and take **exec form** (`["executable","arg"]`, JSON array, no shell) or **shell form** (`command arg`, wrapped as `/bin/sh -c`). At run time the effective command is `ENTRYPOINT` followed by `CMD` (or by the arguments given to `docker run`, which override `CMD`). `--entrypoint` on `docker run` overrides the image's `ENTRYPOINT` and, as a side effect, clears any image `CMD`. Only the last `CMD` and last `ENTRYPOINT` in a Dockerfile take effect.

> 💡 **Tip:** Use exec form for both. Shell form makes `/bin/sh` PID 1, which usually does not forward signals to your application.

## 2. Why This Matters

- The wrong form causes containers that ignore `docker stop` and get SIGKILLed after 10 seconds.
- The pair defines your image's public "CLI contract": tool-style images (`ENTRYPOINT`) versus service images (`CMD`).
- Kubernetes maps `command` to ENTRYPOINT and `args` to CMD; misunderstanding this breaks manifests.
- A frequent interview and DCA topic because the interaction table is easy to get wrong.

## 3. Prerequisites and Dependencies

Requires Dockerfile basics ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)) and image config ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)). Signal handling and PID 1 behavior relate to namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), while the process itself is started by runc under containerd ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)). The runtime override flags belong to the `docker run` deep dive in Part 4; `ENV` and `WORKDIR` are covered in [§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md).

## 4. Architecture / Conceptual Diagram

```text
   Image config                       docker run <image> [ARGS...]
  ┌──────────────────┐                      │
  │ Entrypoint: [E]  │                      │
  │ Cmd:        [C]  │                      │
  └────────┬─────────┘                      │
           │                                ▼
           │            ARGS given? ── yes ──► use ARGS in place of C
           │                  │
           │                  no ──► use C
           ▼
     final argv = E + (ARGS or C)         (if E is empty: argv = ARGS or C)

  Interaction matrix (exec forms)
  ┌───────────────────┬──────────────────┬──────────────────────────────┐
  │                   │ no ENTRYPOINT    │ ENTRYPOINT ["e","x"]         │
  ├───────────────────┼──────────────────┼──────────────────────────────┤
  │ no CMD            │ error: no command│ e x                          │
  │ CMD ["c","y"]     │ c y              │ e x c y                      │
  │ CMD c y (shell)   │ /bin/sh -c c y  │ e x /bin/sh -c c y           │
  └───────────────────┴──────────────────┴──────────────────────────────┘
  Shell-form ENTRYPOINT ignores both CMD and run-time ARGS.
```

- **Override precedence:** `docker run image ARGS` replaces CMD; `--entrypoint` replaces ENTRYPOINT.
- **Shell form** adds a `/bin/sh -c` wrapper: variable expansion works, but PID 1 is the shell.
- **Mixing exec ENTRYPOINT with shell CMD** yields nonsense like `e x /bin/sh -c c y`.

## 5. Hands-On

### 5.1 CMD Only: Default Command, Fully Overridable

```dockerfile
FROM alpine:3.20
CMD ["echo", "hello from CMD"]
```

```bash
docker build -t cmd-demo .
docker run --rm cmd-demo
docker run --rm cmd-demo echo overridden
docker run --rm cmd-demo ls /
```

```text
hello from CMD
overridden
bin
dev
etc
...
```

### 5.2 ENTRYPOINT Only: Arguments Get Appended

```dockerfile
FROM alpine:3.20
ENTRYPOINT ["echo", "prefix:"]
```

```bash
docker build -t ep-demo .
docker run --rm ep-demo
docker run --rm ep-demo one two
```

```text
prefix:
prefix: one two
```

### 5.3 ENTRYPOINT plus CMD: Fixed Program, Default Arguments

```dockerfile
FROM alpine:3.20
ENTRYPOINT ["ping", "-c", "2"]
CMD ["127.0.0.1"]
```

```bash
docker build -t ping-demo .
docker run --rm ping-demo
docker run --rm ping-demo 1.1.1.1
```

```text
PING 127.0.0.1 (127.0.0.1): 56 data bytes
64 bytes from 127.0.0.1: seq=0 ttl=64 time=0.052 ms
...
PING 1.1.1.1 (1.1.1.1): 56 data bytes
```

This "tool image" pattern is how `curl`, `kubectl` and `terraform` images behave.

### 5.4 Overriding ENTRYPOINT for Debugging

```bash
docker run --rm -it --entrypoint /bin/sh ping-demo
docker run --rm --entrypoint "" alpine:3.20 echo "no entrypoint"
```

```text
/ # 
no entrypoint
```

When you override the entrypoint, the image's `CMD` is discarded unless you pass arguments explicitly.

### 5.5 Shell Form vs Exec Form: Signal Handling

```dockerfile
# Dockerfile.shell
FROM alpine:3.20
CMD sleep 300
```

```dockerfile
# Dockerfile.exec
FROM alpine:3.20
CMD ["sleep", "300"]
```

```bash
docker build -f Dockerfile.shell -t sleep-shell .
docker build -f Dockerfile.exec  -t sleep-exec .
docker run -d --name s1 sleep-shell
docker run -d --name s2 sleep-exec
docker exec s1 ps
time docker stop s1
time docker stop s2
```

```text
PID   USER   COMMAND
    1 root   /bin/sh -c sleep 300
    7 root   sleep 300

s1   real  0m10.2s     # shell is PID 1, SIGTERM ignored, SIGKILL after timeout
s2   real  0m0.3s      # sleep is PID 1 and dies on SIGTERM
```

BusyBox `sleep` as PID 1 exits promptly here because the kernel applies default signal actions poorly to PID 1 only when no handler is set; results can vary by tool, but the shell wrapper reliably delays shutdown.

### 5.6 The `exec` Trick in Entrypoint Scripts

```dockerfile
FROM alpine:3.20
COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
```

```sh
#!/bin/sh
set -e
# prepare config, wait for dependencies, etc.
echo "starting with: $*"
exec "$@"        # replace the shell so the app becomes PID 1
```

`exec "$@"` hands control to whatever `CMD` (or run-time args) supplied, so signals reach the real process.

### 5.7 Inspecting What Was Set

```bash
docker image inspect ping-demo --format 'ENTRYPOINT={{json .Config.Entrypoint}} CMD={{json .Config.Cmd}}'
docker inspect s1 --format '{{json .Config.Cmd}} {{.Path}} {{json .Args}}'
```

```text
ENTRYPOINT=["ping","-c","2"] CMD=["127.0.0.1"]
["/bin/sh","-c","sleep 300"] /bin/sh ["-c","sleep 300"]
```

## 6. Production Usage Notes

- **Service images:** `CMD ["app", "--config", "/etc/app.yaml"]`, easily overridden for debugging.
- **Tool/CLI images:** `ENTRYPOINT ["tool"]` with `CMD ["--help"]`.
- **Wrapper scripts** (`docker-entrypoint.sh`) are common in official images (postgres, nginx, redis); always end with `exec "$@"`.
- **Kubernetes mapping:** `command:` replaces ENTRYPOINT, `args:` replaces CMD.
- **Compose:** `entrypoint:` and `command:` follow the same override rules.
- **Init process:** if the app does not reap zombies or handle signals, use `docker run --init` or a tini-style init in ENTRYPOINT.
- Set `STOPSIGNAL` when the app expects something other than SIGTERM.

## 7. Security Considerations

- **Shell form expands variables at run time**, which can create injection paths if environment values are untrusted.
- **Entrypoint scripts** run as the container user (often root during startup); validate inputs and drop privileges (`exec gosu app "$@"`) as early as possible.
- **Overridable entrypoints:** anyone allowed to run containers can replace ENTRYPOINT; do not rely on it as an access control.
- **Avoid secrets in CMD/ENTRYPOINT arguments**; they are visible in `docker inspect` and `ps` output.
- Keep scripts minimal; a full shell in the image widens attack surface, so distroless images lean on exec-form binaries.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Container takes 10s to stop | Shell-form CMD/ENTRYPOINT; shell is PID 1 | Use exec form or `exec` in scripts |
| `exec: "cmd": executable file not found in $PATH` | Exec form given a shell builtin or missing binary | Use full path or shell form deliberately |
| `$HOME` printed literally | Exec form performs no expansion | Use `["sh","-c","echo $HOME"]` |
| Run-time args ignored | Shell-form ENTRYPOINT | Switch to exec-form ENTRYPOINT |
| Image CMD vanished after `--entrypoint` | `--entrypoint` clears CMD | Pass the arguments explicitly |
| `exec format error` in script | Missing shebang or CRLF line endings | Add `#!/bin/sh`, convert to LF |
| `permission denied` on entrypoint | Script not executable | `COPY --chmod=755` or `RUN chmod +x` |

## 9. Best Practices

- Use exec form for both instructions.
- Use ENTRYPOINT for the fixed executable and CMD for default, overridable arguments.
- Make entrypoint scripts POSIX-sh, `set -e`, and finish with `exec "$@"`.
- Handle SIGTERM in the application or run under an init.
- Document how to override each in the image's README.
- Test with `docker run image --help` and with `docker stop` timing.

## 10. Common Anti-Patterns / Mistakes

- Multiple `CMD` lines expecting all to run (only the last applies).
- Shell-form `ENTRYPOINT` combined with a `CMD` that is expected to append arguments.
- Using `CMD` to run a build-time setup step (that belongs in `RUN`).
- Entrypoint scripts that end without `exec`, leaving a shell as PID 1.
- Running multiple daemons via a backgrounding shell script instead of separate containers.
- Using `ENTRYPOINT ["/bin/bash","-c"]` and then passing quoted strings incorrectly.

## 11. Interview Questions

**🎯 Beginner:** _"A teammate's image has `ENTRYPOINT ["python","app.py"]` and `CMD ["--port","8000"]`. What does `docker run img --port 9000` execute, and what does `docker run img bash` execute?"_
**Model answer:** With exec-form ENTRYPOINT plus CMD, the final argv is ENTRYPOINT followed by CMD. Arguments after the image name replace CMD entirely, so the first command runs `python app.py --port 9000`. The second runs `python app.py bash`, because `bash` is only treated as an argument, not a replacement command. To get a shell you must override the entrypoint with `docker run --entrypoint bash -it img`. Only the last CMD in a Dockerfile counts.
_What the interviewer is probing for:_ That ENTRYPOINT is the fixed program and CMD is replaceable default arguments.

**🎯 Intermediate:** _"A container's `docker stop` always takes 10 seconds, and the Dockerfile uses `CMD python app.py` (shell form). Why, and how do you fix it?"_
**Model answer:** Shell form wraps the command in `/bin/sh -c`, so the shell becomes PID 1 and the app is a child. `docker stop` sends SIGTERM to PID 1; `sh` does not forward it and the app never sees it, so after the 10-second grace period the daemon sends SIGKILL. Switch to exec form `CMD ["python","app.py"]` so the app is PID 1 and receives signals directly. If a wrapper script is needed, end it with `exec "$@"`. You can confirm with `docker exec c ps -o pid,args` and tune with `--stop-timeout` or `STOPSIGNAL`.
_What the interviewer is probing for:_ Exec vs shell form and signal delivery to PID 1.

**🎯 Senior:** _"Your entrypoint wrapper script does env-to-config templating, then starts the app, but the app ignores SIGTERM and leaves zombie processes. Diagnose and correct the design."_
**Model answer:** The script likely runs the app as a child (`myapp &` or plain `myapp` without `exec`), so the shell stays PID 1, does not forward signals, and does not reap orphans. End the script with `exec "$@"` so the app replaces the shell and inherits PID 1 with the CMD as its arguments. If the app spawns children, add a minimal init with `docker run --init` or `tini` as ENTRYPOINT so zombies are reaped and signals forwarded. Use `set -e` in the script so templating failures abort startup, and verify with `docker stop` timing and `docker top`.
_What the interviewer is probing for:_ Practical PID 1 handling: exec, init, and signal forwarding.

**🎯 Architect:** _"You must define an entrypoint contract for 150 images across teams, and Kubernetes workloads override it. What do you standardize, and how do Kubernetes fields map?"_
**Model answer:** Standardize exec-form ENTRYPOINT pointing to one shared wrapper that validates required env vars, renders config, then `exec "$@"`, with CMD holding only default arguments, plus `STOPSIGNAL`, a HEALTHCHECK, and a documented override point. Include an init (tini) for reaping. In Kubernetes, `command` replaces ENTRYPOINT and `args` replaces CMD; setting only `command` drops the image CMD, and setting only `args` keeps ENTRYPOINT, which is a common source of surprises. Enforce the contract with a CI lint on `docker inspect` output (`Config.Entrypoint`, `Config.Cmd`) and publish an override guide so platform teams never rewrite the wrapper.
_What the interviewer is probing for:_ Fleet-level standardization and understanding of orchestrator override semantics.

## 12. Common Misconceptions

- "CMD and ENTRYPOINT are interchangeable." They differ in overridability and combination.
- "`docker run image foo` appends to CMD." It replaces CMD.
- "Shell form is just a shorter syntax." It changes PID 1 and signal delivery.
- "ENTRYPOINT cannot be changed at run time." `--entrypoint` overrides it.

## 13. 🔑 Key Takeaways

- Effective command = ENTRYPOINT + (run args or CMD).
- Prefer exec form; shell form makes `/bin/sh` PID 1.
- `--entrypoint` overrides ENTRYPOINT and clears image CMD.
- Entrypoint scripts must `exec "$@"`.
- Kubernetes: `command` maps to ENTRYPOINT, `args` to CMD.

## 14. Related Concepts & What's Next

Related: Dockerfile instructions ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), image config ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), PID namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), runtime process startup ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)). Next, [§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md) covers `WORKDIR`, `ENV`, `ARG` and `LABEL`, which shape the environment your entrypoint runs in.

**Next Section:** [§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md) — `Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md`
