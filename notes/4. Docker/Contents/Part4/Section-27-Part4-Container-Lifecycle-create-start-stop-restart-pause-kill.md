# Section 27 (Part 4): Container Lifecycle: create, start, stop, restart, pause, kill

## 1. Definition

**Plain language:** A container is not just "running" or "gone". It moves through states: it is created, started, possibly paused, stopped or killed, and finally removed. Each lifecycle command moves it between those states, and each has different consequences for the process inside, for its data, and for how long it takes.

**Precise definition:** The Docker Engine tracks each container in one of seven states: `created` (config and writable layer exist, no process), `running`, `paused` (processes frozen in place), `restarting` (a restart policy is waiting or relaunching), `removing`, `exited` (the process ended; the container and its writable layer remain), and `dead` (a removal failed part-way; it cannot be restarted). The commands are `docker create`, `docker start`, `docker stop`, `docker restart`, `docker pause`/`unpause`, `docker kill`, `docker wait` and `docker rm`. Stopping works by signalling the container's PID 1: `docker stop` sends `SIGTERM` (or the image's `STOPSIGNAL`) and, after a grace period (default 10 seconds), `SIGKILL`; `docker kill` sends `SIGKILL` by default or any signal chosen with `-s`; `docker pause` does not signal at all but freezes the container's cgroup. The state, exit code and timestamps live in `docker inspect` under `.State`.

> 💡 **Tip:** `docker stop` is a request followed by a deadline; `docker kill` is an immediate order. Production shutdown should always go through `stop` so the application gets a chance to finish its work.

## 2. Why This Matters

- Clean shutdown (draining requests, flushing buffers, closing database connections) depends entirely on whether SIGTERM reaches the application and whether the grace period is long enough.
- Exit codes 137 and 143 are the first clue in most "container died" incidents; knowing what produces them shortens triage.
- Understanding which state keeps data (the writable layer survives `stop` and `start`, but not `rm`) prevents both data loss and disk leaks.
- `pause` and `restart` are frequently confused; the difference matters for debugging, snapshots and tests.
- Orchestrators (Kubernetes `terminationGracePeriodSeconds`, Compose `stop_grace_period`) reuse exactly these semantics.

## 3. Prerequisites and Dependencies

Requires `docker run` ([§26](Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)) since `run` is create plus start, and PID 1/signal behavior from CMD and ENTRYPOINT ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)). The mechanisms underneath are PID namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), the cgroup v2 freezer used by `pause` ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), and the daemon, containerd and runc chain that tracks processes via shims ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)). Writable-layer behavior comes from overlay2 ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). Automatic restarts via policies are covered later in Part 4 (§32), and bulk cleanup in §33.

## 4. Architecture / Conceptual Diagram

```text
                       docker create
        (none) ───────────────────────────► CREATED
          │                                    │ docker start
          │ docker run (create+start)          ▼
          └──────────────────────────────► RUNNING ◄──────────────┐
                                           │  │  │                │
                         docker pause      │  │  │ restart policy │ docker unpause
                      ┌───────────────────►│  │  └──► RESTARTING  │
                      ▼                    │  │         (backoff)  │
                   PAUSED ─────────────────┼──┼────────────────────┘
                (cgroup frozen)            │  │
                                           │  │ docker stop  : SIGTERM ─(10s)─► SIGKILL
          process exits by itself ────────►│  │ docker kill  : SIGKILL (or -s SIG)
                                           ▼  ▼
                                         EXITED (code 0..255) ──docker start──► RUNNING
                                           │
                                           │ docker rm
                                           ▼
                                        REMOVING ──► (gone)      failed rm ► DEAD

  What each command does to the container
  ┌──────────────┬────────────────────┬──────────────┬─────────────────────┐
  │ Command      │ Delivered to PID 1 │ Same PID 1?  │ Writable layer      │
  ├──────────────┼────────────────────┼──────────────┼─────────────────────┤
  │ stop         │ SIGTERM, then KILL │ ends         │ kept                │
  │ kill         │ SIGKILL / -s SIG   │ ends (KILL)  │ kept                │
  │ restart      │ stop, then start   │ new process  │ kept                │
  │ pause        │ none (freezer)     │ same, frozen │ kept, RAM kept      │
  │ rm           │ none (must be off) │ n/a          │ deleted             │
  │ rm -f        │ SIGKILL, then rm   │ ends         │ deleted             │
  └──────────────┴────────────────────┴──────────────┴─────────────────────┘
```

- **Identity persists:** container ID, name, config, network settings and writable layer survive stop/start/restart; the process, its PID, its memory and (usually) its IP address do not.
- **Signals go only to PID 1.** Children receive them only if PID 1 forwards them or exits and takes the PID namespace down with it, at which point the kernel SIGKILLs the rest.
- **PID 1 is special:** signals sent from inside the namespace to an init process are ignored unless it installed a handler. Signals sent from the host (the daemon) are delivered with default actions only for SIGKILL and SIGSTOP; for SIGTERM the process must have a handler. This is why signal handling in the app or an `--init` process matters.

## 5. Hands-On

### 5.1 Create, Inspect, Then Start

```bash
docker create --name life alpine:3.20 sh -c 'echo started; sleep 30'
docker ps -a --filter name=life --format '{{.Names}} {{.Status}}'
docker inspect life --format '{{.State.Status}} pid={{.State.Pid}}'
docker start -a life
```

```text
life Created
created pid=0
started
```

`create` allocates everything (writable layer, config, network settings are resolved at start) but runs nothing. `start -a` attaches to output and blocks until exit; without `-a`, `start` returns immediately and prints the name. After the `sleep 30` completes, the state becomes `exited`.

### 5.2 Reading State, Exit Code and Timestamps

```bash
docker run -d --name quick alpine:3.20 sh -c 'sleep 2; exit 3'
docker wait quick
docker inspect quick --format \
  'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}'
```

```text
3
status=exited exit=3 oom=false started=2026-10-06T09:12:01.1Z finished=2026-10-06T09:12:03.1Z
```

`docker wait` blocks until the container stops and prints its exit code, a handy primitive for scripts. `.State.Error` holds the daemon's message if the start failed.

### 5.3 Graceful Stop vs Ignored SIGTERM

```bash
cat > trap.sh <<'EOF'
#!/bin/sh
trap 'echo got TERM, cleaning up; sleep 1; exit 0' TERM
echo ready
while true; do sleep 1; done
EOF
chmod +x trap.sh

docker run -d --name graceful -v "$PWD/trap.sh:/trap.sh:ro" alpine:3.20 /trap.sh
docker run -d --name stubborn alpine:3.20 sh -c 'while true; do sleep 1; done'
time docker stop graceful
time docker stop stubborn
docker inspect -f '{{.State.ExitCode}}' graceful stubborn
docker logs graceful
```

```text
graceful   real 0m1.2s
stubborn   real 0m10.2s
0
137
ready
got TERM, cleaning up
```

The trapping script handles SIGTERM and exits cleanly with 0. The second container runs `sh` as PID 1 with no SIGTERM handler, so the signal is ignored (PID 1 rule), the daemon waits out the 10-second timeout, sends SIGKILL, and the exit code is 137 (128 + 9).

### 5.4 Tuning the Grace Period and Stop Signal

```bash
docker stop -t 30 graceful              # per-call timeout (--time)
docker run -d --name slow --stop-timeout 60 --stop-signal SIGINT myorg/worker:2.1
docker inspect slow --format '{{.Config.StopSignal}} {{.Config.StopTimeout}}'
docker stop -t 0 slow                   # immediate SIGKILL after SIGINT
```

```text
SIGINT 60
```

Precedence for the timeout is the `-t` flag on the command, then `--stop-timeout` set at creation, then the daemon default of 10 seconds. `STOPSIGNAL` in a Dockerfile ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)) or `--stop-signal` changes SIGTERM to another signal (nginx uses SIGQUIT for graceful stop).

### 5.5 Restart Keeps State, Replaces the Process

```bash
docker run -d --name keep alpine:3.20 sh -c 'echo run >> /data.txt; cat /data.txt; sleep 300'
docker restart keep
docker logs keep
docker inspect keep --format 'id={{.Id}} restarts={{.RestartCount}} pid={{.State.Pid}}'
```

```text
run
run
run
```

Each start appends to a file in the writable layer, so after the restart the file holds two lines: the process is new but the layer is the same. `RestartCount` stays 0 because it counts policy-driven restarts only, not manual `docker restart`. `docker restart -t N` sets the stop timeout for the stop half.

### 5.6 Pause and Unpause Use the cgroup Freezer

```bash
docker run -d --name ticker alpine:3.20 sh -c 'while true; do date +%T; sleep 1; done'
sleep 3; docker pause ticker
docker inspect ticker --format '{{.State.Status}} paused={{.State.Paused}}'
docker stats --no-stream ticker
sleep 5; docker unpause ticker; sleep 2
docker logs ticker | tail -n 8
cat /sys/fs/cgroup/system.slice/docker-$(docker inspect -f '{{.Id}}' ticker).scope/cgroup.freeze
```

```text
paused paused=true
CONTAINER   CPU %   MEM USAGE / LIMIT ...
ticker      0.00%   1.1MiB / 7.6GiB
09:20:01
09:20:02
09:20:03
09:20:12    # gap of about 5 seconds while frozen, no catch-up
09:20:13
0           # after unpause (1 while frozen)
```

On cgroup v2 hosts `pause` writes `1` to the container cgroup's `cgroup.freeze`; on v1 it uses the `freezer` controller's `FROZEN` state. The process is not signalled and cannot notice, memory stays allocated, and wall-clock time keeps moving, so timers and network peers may time out. Only the cgroup path layout differs by cgroup driver (systemd shown above, `/sys/fs/cgroup/docker/<id>/` for cgroupfs).

### 5.7 Kill, Custom Signals and Force Removal

```bash
docker run -d --name k1 nginx:1.27
docker kill -s HUP k1                   # nginx reloads config, stays running
docker kill k1                          # SIGKILL
docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' k1
docker rm k1
docker run -d --name k2 nginx:1.27 && docker rm -f k2
docker rm life quick graceful stubborn keep ticker slow 2>/dev/null
```

```text
exited 137
```

`kill -s HUP` demonstrates that `kill` is really "send this signal", often used for config reload. `rm` refuses a running container ("cannot remove a running container"); `rm -f` kills it first. `rm -v` also removes its anonymous volumes. Never script `rm -f` as your normal shutdown path.

### 5.8 Following the Lifecycle via Events

```bash
docker events --filter type=container --since 1m --until 0s \
  --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' &
docker run --rm --name evt alpine:3.20 true
```

```text
1759742000 create evt
1759742000 attach evt
1759742000 start evt
1759742001 die evt
1759742001 destroy evt
```

The event stream shows `create`, `start`, `die` (with `exitCode` in the attributes), `stop`, `kill` (with the signal), `pause`, `unpause`, `restart`, `oom` and `destroy`. It is the right source for alerting on unexpected deaths.

## 6. Production Usage Notes

- **Make shutdown graceful:** handle SIGTERM in the app, finish in-flight work within the grace period, and size `--stop-timeout` (Compose: `stop_grace_period`) to the real drain time.
- **Use exec-form commands and `exec` in wrapper scripts** so PID 1 is the application ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)); add `--init` if it spawns children.
- **Prefer `docker stop` over `kill`** in runbooks. Use `kill -s` for reload signals and for deliberate crash testing.
- **Monitor exit codes and `OOMKilled`;** a 137 with `OOMKilled=true` means memory limit, while 137 with `false` means someone or something sent SIGKILL (including a timed-out `stop`).
- **`restart` is not a zero-downtime tool.** It stops then starts a single container; rolling updates need an orchestrator or a proxy with two replicas.
- **Daemon restarts:** by default stopping `dockerd` stops containers; `"live-restore": true` in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) keeps them running through daemon restarts and upgrades.
- **Exited containers still use disk** for their writable layer and logs. Remove short-lived ones with `--rm`, and clean up the rest regularly (§33).
- **Pause is for debugging and quiescing,** such as freezing a container before inspecting or snapshotting its filesystem; do not use it for load shedding.

## 7. Security Considerations

- **Authority over lifecycle is authority over availability.** Anyone with Docker API access can stop, kill or pause every container; guard the socket and avoid exposing it over unauthenticated TCP.
- **Graceful stop protects data integrity:** databases killed with SIGKILL may need crash recovery; a long enough grace period prevents corruption.
- **`docker kill -s` can deliver any signal,** including ones that make some applications dump core files containing secrets (SIGQUIT, SIGABRT); restrict core dumps on hosts.
- **Stopped containers retain secrets** in environment variables, writable layers and logs until removed. Remove sensitive one-off containers promptly (`--rm`).
- **`docker start` of a stale container re-applies its old configuration,** including outdated base-image vulnerabilities and old mounts. Recreate from a freshly pulled image rather than restarting indefinitely.
- **Paused containers keep holding memory,** including any secrets in it, and keep their network sockets; they are not an isolation or forensics-safe state by themselves.
- **Forensics:** for suspected compromise, prefer `docker pause` or `docker export`/`docker commit` of the writable layer before `rm`, so evidence is preserved.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `docker stop` always takes 10 seconds | PID 1 ignores SIGTERM (shell form, no handler) | Exec form, `exec "$@"`, handle SIGTERM, or `--init` |
| Exit code 137 | SIGKILL: OOM kill, `docker kill`, or stop timeout expired | Check `State.OOMKilled`; raise `--memory` or `--stop-timeout` |
| Exit code 143 | Process exited because of SIGTERM with no handler | Add a handler and exit 0 for a clean shutdown |
| Exit code 139 | SIGSEGV in the application | Debug the app or libc mismatch (musl vs glibc) |
| `Error response from daemon: cannot remove a running container` | Container still running | `docker stop` first, or `rm -f` if acceptable |
| `You cannot remove a container that is restarting` | Restart policy loop | `docker update --restart=no c`, then stop and remove |
| Container immediately `Exited (0)` after `start` | Main process finished (for example `CMD ["bash"]` without a TTY) | Use `-it`, or give it a long-running foreground process |
| `docker start` fails with "port is already allocated" | Host port taken since the container was created | Free the port or recreate with a different `-p` |
| Container IP changed after restart | Addresses are reassigned on start | Use names and user-defined networks, not IPs |
| `Status: Dead` and removal errors | Storage busy or mount leaked | Retry `docker rm -f`; check `lsof`, restart daemon if needed |
| Paused container's clients time out | Frozen process cannot answer; clocks keep running | Unpause; set client-side timeouts and retries |
| `docker restart` lost my changes | Changes were in tmpfs or `--rm` container, or recreated container | Persist data in volumes ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)) |

## 9. Best Practices

- Treat every container as disposable but its shutdown as important: handle SIGTERM and exit 0.
- Set `STOPSIGNAL` in the Dockerfile to match what the application expects.
- Match `--stop-timeout` to measured drain time, not a guess; never use `stop -t 0` as routine.
- Read `docker inspect` `.State` (status, exit code, OOMKilled, error) before guessing at causes.
- Use `docker wait` or `docker run` exit codes in scripts and CI rather than parsing logs.
- Keep state in volumes, not in the writable layer, so `rm` and recreate are safe.
- Use `docker kill -s HUP` (or the app's documented reload signal) instead of restarting for config reloads.
- Log lifecycle events centrally (`docker events`) so unexpected `die` and `oom` are alertable.
- Recreate rather than restart when the image or config must change.

## 10. Common Anti-Patterns / Mistakes

- Using `docker kill` or `rm -f` as the standard stop procedure.
- Shell-form `CMD`/`ENTRYPOINT`, then raising the stop timeout to hide slow shutdown.
- Expecting `docker restart` to pick up a newly pulled image or changed flags; it reuses the old container.
- Treating `pause` as `stop` (memory stays allocated; connections stay half-open).
- Storing application data in the writable layer and then running `docker rm`.
- Ignoring exit codes: starting containers with `-d` in CI and never calling `docker wait` or inspecting the state.
- Hard-coding container IP addresses that change on each start.
- Keeping hundreds of `Exited` containers "just in case" and leaking disk.
- Running `docker stop $(docker ps -q)` on shared hosts without scoping filters.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `docker stop` and `docker kill`, and what is the difference between `docker stop` and `docker pause`?"_
**Model answer:** `docker stop` sends SIGTERM (or the configured stop signal) to the container's main process, waits up to 10 seconds by default, then sends SIGKILL. That gives the application a chance to shut down cleanly. `docker kill` sends SIGKILL immediately by default (or any signal with `-s`), so the process cannot clean up. `docker pause` is different from both: it does not signal the process or end it; it freezes all its processes with the cgroup freezer until `docker unpause`. A stopped container is `exited` and can be started again with a new process, while a paused container is still the same process with its memory intact.
_What the interviewer is probing for:_ Correct signal semantics and the distinction between ending a process and freezing it.

**🎯 Intermediate:** _"A service container takes exactly 10 seconds to stop and exits with code 137. Walk me through diagnosis and the fix."_
**Model answer:** The 10 seconds is the default grace period and 137 is 128 + SIGKILL, so SIGTERM was not acted on and the daemon escalated. Check `docker top` or `docker exec c ps` to see what PID 1 is; typically it is `/bin/sh -c ...` from a shell-form CMD, or a wrapper script that did not `exec`, or an app with no SIGTERM handler (PID 1 does not get default signal dispositions). Fix by using exec-form CMD, ending the wrapper with `exec "$@"`, installing a handler (or running under `--init`), and, if the application legitimately needs more time to drain, raising `--stop-timeout`. Verify by timing `docker stop` and checking the exit code is 0 and `OOMKilled` is false.
_What the interviewer is probing for:_ PID 1 signal behavior, exit code arithmetic, and fixing the cause rather than extending the timeout.

**🎯 Senior:** _"Explain exactly what `docker restart` preserves and what it discards, and why a `docker restart` is not a deployment strategy."_
**Model answer:** It is `stop` (SIGTERM, grace period, SIGKILL) followed by `start` on the same container object. The container ID, name, create-time configuration, writable layer, and volumes persist. The process, PID, in-memory state and normally the IP address are new. The image the container references is the one it was created from, so a newly pulled tag is not used, and flags such as ports or env cannot change except for a few `docker update` fields. It also creates a window with no running instance. A deployment strategy therefore needs creating a new container from the new image, health-checking it, switching traffic, and then stopping the old one, which a Compose recreate, a reverse proxy with two replicas, or an orchestrator's rolling update provides.
_What the interviewer is probing for:_ Understanding of container identity versus process identity and why immutability drives deployment design.

**🎯 Architect:** _"Define the shutdown contract for a fleet of stateful and stateless containers, covering signals, timeouts, daemon upgrades and failure handling."_
**Model answer:** Standardize on SIGTERM-based shutdown with a documented per-service drain time: images use exec-form entrypoints with a common init, set `STOPSIGNAL` where required, and expose readiness so traffic is removed before termination. Grace periods come from measured p99 drain times, with orchestrator values (`stop_grace_period`, `terminationGracePeriodSeconds`) set above that and below the platform's maximum. Stateful services use longer timeouts and crash-safe storage because SIGKILL is the fallback, and they write data to volumes only. For host maintenance use `live-restore` so daemon upgrades do not kill workloads, while for node drains use the orchestrator. Alert on `die` events with exit codes 137 and `oom` events, and on stop durations that hit the timeout, which is the signature of ignored SIGTERM. Test the contract in CI by stopping a container and asserting exit code 0 within a budget.
_What the interviewer is probing for:_ Treating lifecycle as a platform contract with measurable SLOs, not an operator habit.

## 12. Common Misconceptions

- "`docker stop` kills the container immediately." It sends a catchable signal first.
- "`docker restart` pulls a fresh image." It reuses the existing container and image.
- "`docker pause` sends SIGSTOP." It uses the cgroup freezer; the process cannot observe it.
- "Exited containers are deleted automatically." Only with `--rm`.
- "Stopping a container loses its files." The writable layer survives until `docker rm`.
- "Exit code 137 always means out of memory." It means SIGKILL; check `OOMKilled`.
- "`docker kill` only sends SIGKILL." With `-s` it sends any signal.
- "A container's IP is stable across restarts." It is not guaranteed.

## 13. 🔑 Key Takeaways

- States: created, running, paused, restarting, exited, removing, dead; `docker run` = create + start.
- `stop` = SIGTERM (or STOPSIGNAL), 10 s default grace, then SIGKILL; `kill` = immediate, signal selectable.
- Exit 137 = SIGKILL (128+9), 143 = SIGTERM, check `State.OOMKilled` to distinguish.
- `restart` keeps the container and writable layer but starts a new process; `rm` deletes the layer.
- `pause` freezes via the cgroup freezer (`cgroup.freeze` on v2); no signal, no state loss, clocks keep running.
- Make PID 1 your app (exec form, `exec`, or `--init`) or shutdown will hit the timeout.
- Use `docker inspect`, `wait` and `events` to observe and automate lifecycle.

## 14. Related Concepts & What's Next

Related: `docker run` flags ([§26](Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), CMD/ENTRYPOINT and PID 1 ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), PID namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), daemon configuration including `live-restore` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Restart policies and health checks (§32) automate the transitions shown here. Next, [§28](Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md) covers running additional commands inside a running container with `exec` and connecting to its main process with `attach`.

**Next Section:** [§28](Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md) — `Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md`
