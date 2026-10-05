# Section 102 (Part 14): Scenario-Based Troubleshooting Questions

## 1. Definition

**Plain language:** A scenario-based troubleshooting question gives you a broken situation ("the container keeps restarting", "the disk is full", "service A cannot reach service B") and watches how you investigate. The interviewer cares less about the final answer than about your method: what you check first, what you rule out, and what you refuse to guess.

**Precise definition:** A scenario question supplies a symptom, a partial environment and sometimes a command output, and expects a structured diagnosis: observe, form a hypothesis, test it with the least invasive command, fix, and prevent recurrence. For Docker the evidence sources are a small, finite set: container state and exit code (`docker inspect`), logs ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)), live process and resource view (`docker top`, `docker stats`), a shell in the same namespaces (`docker exec`, [§28](../Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)), daemon events and logs, and host-level kernel evidence (`dmesg`, `journalctl`).

> 💡 **Tip:** Answer every scenario with the same skeleton: **symptom, scope, evidence, hypothesis, fix, prevention**. A consistent structure signals experience even when you do not recognize the exact bug.

## 2. Why This Matters

- Troubleshooting questions are the most discriminating interview format: memorized definitions do not help, a systematic method does.
- The DCA exam and real on-call work both reward knowing which command reveals which layer ([§100](Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)).
- Roughly ten failure patterns (exit 137, exit 125/126/127, port conflicts, DNS between containers, full disk, permission denied on mounts, slow builds, unhealthy status, restart loops, "works on my machine") account for most real incidents.
- Strong candidates narrate their reasoning aloud; weak candidates jump to `docker system prune` or "restart it".

## 3. Prerequisites and Dependencies

You should be comfortable with container lifecycle and exit codes ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), resource limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), restart policies and health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)), networking diagnostics ([§47](../Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), and volumes ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)). The production-grade version of this material lives in [§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md); this section trains the interview delivery. General question styles are in [§101](Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md).

## 4. Architecture / Conceptual Diagram

```text
                 THE DIAGNOSTIC LADDER (work top to bottom, stop when found)

  1. Is it running?        docker ps -a            ► State, exit code, restarts
        │
  2. Why did it stop?      docker inspect -f '{{json .State}}' c
        │                  (ExitCode, OOMKilled, Error, FinishedAt)
        ▼
  3. What did it say?      docker logs --tail 100 -t c
        │
        ▼
  4. What is it doing?     docker top c ; docker stats --no-stream c
        │
        ▼
  5. What does it see?     docker exec -it c sh   (or nsenter / debug sidecar)
        │                  env, mount, ip addr, getent hosts, curl
        ▼
  6. What does the daemon  docker events --since 10m ; journalctl -u docker
     / host say?           dmesg -T | grep -i -E 'oom|killed'
        │
        ▼
  7. What changed?         image digest, compose diff, host patch, quota, DNS

  Exit code cheat sheet
  ┌──────┬──────────────────────────────────────────────────────────────┐
  │ 0    │ clean exit (CMD finished: not a daemon, or intentional)      │
  │ 1    │ application error                                            │
  │ 125  │ docker run itself failed (bad flag, daemon error)            │
  │ 126  │ command found but not executable (permissions, wrong arch)   │
  │ 127  │ command not found (PATH, missing binary, shell-form on slim) │
  │ 137  │ SIGKILL (128+9): OOM killer or docker kill / stop timeout    │
  │ 139  │ SIGSEGV (128+11): native crash                               │
  │ 143  │ SIGTERM (128+15): graceful stop requested                    │
  └──────┴──────────────────────────────────────────────────────────────┘
```

- Steps 1 to 3 solve most incidents in under two minutes.
- Exit code plus `OOMKilled` separates "the kernel killed it" from "something sent a signal".
- Always ask "what changed?" last but never skip it: most outages follow a deploy, a base-image refresh or a host change.

## 5. Hands-On

The scenarios below are written as an interviewer would pose them, followed by the investigation you would narrate. Reproduce them locally in a throwaway container only.

### 5.1 Scenario A: Container Exits Immediately

**Prompt:** "`docker run -d myapp` prints an ID, but `docker ps` shows nothing."

```bash
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Command}}'
docker inspect -f 'exit={{.State.ExitCode}} oom={{.State.OOMKilled}} err={{.State.Error}}' <name>
docker logs <name>
```

```text
NAMES     STATUS                     COMMAND
myapp     Exited (127) 3 seconds ago "./start.sh"
exit=127 oom=false err=
sh: ./start.sh: not found
```

Exit 127 plus "not found" for a script that exists usually means a bad shebang interpreter (`#!/bin/bash` on Alpine) or CRLF line endings turning the interpreter name into `bash\r`. Exit 0 would instead mean the main process finished: the container lives only as long as PID 1. Fix the shebang or convert to LF; do not "keep it alive" with `tail -f /dev/null`.

### 5.2 Scenario B: Exit 137 and Restart Loop

**Prompt:** "A Java service restarts every few hours. `docker ps` shows `Restarting (137)`."

```bash
docker inspect -f '{{.State.OOMKilled}} {{.HostConfig.Memory}} {{.RestartCount}}' svc
docker stats --no-stream svc
dmesg -T | grep -i -E 'killed process|memory cgroup'
```

```text
true 536870912 14
CONTAINER  MEM USAGE / LIMIT   MEM %
svc        511MiB / 512MiB     99.8%
Memory cgroup out of memory: Killed process 4121 (java) ...
```

`OOMKilled=true` confirms the kernel enforced the cgroup limit ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md), [§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)). The JVM heap plus metaspace, threads and native buffers exceeded 512 MiB. Remedies: set `-XX:MaxRAMPercentage=70`, raise the limit with evidence, fix a leak. If `OOMKilled=false` with 137, something else sent SIGKILL, typically the stop timeout after a SIGTERM was ignored by a shell-form PID 1 ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).

### 5.3 Scenario C: "Bind for 0.0.0.0:8080 failed: port is already allocated"

```bash
docker ps --filter publish=8080 --format '{{.Names}} {{.Ports}}'
ss -ltnp | grep ':8080'          # Linux host: who owns the port?
```

Either another container or a host process holds the port. Fix by choosing another host port (`-p 8081:8080`), stopping the holder, or removing publishing entirely and fronting with a reverse proxy on a shared network. In Compose, a stale project with the same ports is the usual culprit (`docker compose ls`).

### 5.4 Scenario D: Service A Cannot Reach Service B

```bash
docker network inspect appnet --format '{{range .Containers}}{{.Name}} {{end}}'
docker exec a getent hosts b          # name resolution
docker exec a nc -zv b 5432           # connectivity
docker exec b ss -ltn                 # is B listening on 0.0.0.0, not 127.0.0.1?
```

Work the three layers separately: same user-defined network? ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), the default bridge has no name DNS); does the name resolve ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md))? is the server bound to an address reachable from outside its own loopback? The most common root cause is an app bound to `127.0.0.1` inside B, or A using `localhost` to mean B.

### 5.5 Scenario E: Disk Full on the Docker Host

```bash
docker system df -v | head -40
du -sh /var/lib/docker/* 2>/dev/null | sort -h | tail
docker ps -a --size --format '{{.Names}} {{.Size}}'
```

Candidates: unbounded `json-file` logs (set `max-size`/`max-file`, [§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)), dangling images and build cache, orphaned volumes, or a container writing into its writable layer. Prune with intent (`docker builder prune`, `docker image prune`) and never `docker volume prune` blind ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).

### 5.6 Scenario F: Permission Denied on a Mounted Volume

```bash
docker exec app id
docker exec app ls -ld /data
ls -ldn ./data                         # numeric owner on the host
```

```text
uid=1000(app) gid=1000(app)
drwxr-xr-x 2 0 0 4096 /data
```

The container user (UID 1000) cannot write a directory owned by UID 0. Fix ownership on the host, use `--user`, `chown` in the entrypoint of a named volume's first run, or an init container. On SELinux hosts add `:z`/`:Z` to the bind mount ([§61](../Part8/Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)). Rootless mode and user namespaces remap UIDs ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)).

## 6. Production Usage Notes

- **Keep evidence before fixing.** Capture `docker inspect`, `docker logs` and `docker events` output into the ticket before restarting; recreating a container destroys its writable layer and `RestartCount`.
- **Change one variable at a time.** Reproduce with the same image digest, not `:latest`.
- **Use debug sidecars** for distroless images: `docker run --rm -it --pid=container:app --net=container:app nicolaka/netshoot` shares namespaces without modifying the image ([§47](../Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)).
- **Know your logging path.** With a remote log driver, `docker logs` may be unavailable; look in the aggregator ([§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)).
- **Roll back first, debug second** when users are affected ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)); an interviewer expects you to prioritize recovery over root cause in an incident.
- **Daemon-level failures** (daemon will not start, containers vanish after reboot) require `journalctl -u docker`, `daemon.json` validation and the live-restore setting ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

## 7. Security Considerations

- **Do not "fix" with privilege.** `--privileged`, `chmod 777`, running as root or disabling seccomp to silence an error is the wrong answer in an interview and in production ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§60](../Part8/Section-60-Part8-Seccomp-Profiles.md)). Diagnose the missing capability or path and grant exactly that.
- **Logs and inspect output leak secrets.** `docker inspect` shows environment variables; redact before pasting into tickets or chat ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Debug access is access.** Anyone who can `docker exec` or reach the Docker socket is effectively root on the host; time-box and audit break-glass access.
- **Debug images** (netshoot, busybox) should come from a trusted registry and be pinned by digest.
- **Compromise signs masquerading as bugs:** unexpected outbound connections, a crypto-miner pegging CPU in `docker stats`, new processes in `docker top`. Say that you would consider incident response, not just a restart.

## 8. Common Troubleshooting Scenarios

A rapid-fire lookup the interviewer may ask for as follow-ups.

| Symptom | Likely cause | First command | Fix |
|---|---|---|---|
| `Exited (0)` immediately | CMD finished; not a long-running process | `docker logs c` | Run the service in the foreground (`daemon off;`) |
| `Exited (126)` | Not executable or wrong CPU architecture | `docker inspect -f '{{.Config.Entrypoint}}' c` | `chmod +x`, match `--platform` ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)) |
| `exec format error` | amd64 image on arm64 host (or reverse) | `docker image inspect --format '{{.Architecture}}' img` | Build multi-arch |
| `Exited (137)`, OOMKilled true | Memory limit hit | `docker stats` | Raise limit, tune runtime heap |
| `no space left on device` | Logs, layers, build cache | `docker system df` | Rotate logs, prune selectively |
| `pull access denied` / `toomanyrequests` | Auth missing or Hub rate limit | `docker login`; check mirror | Credentials, private mirror ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)) |
| App slow only in container | CPU throttling by `--cpus` | `cat /sys/fs/cgroup/cpu.stat` | Raise quota, check `nr_throttled` |
| `Cannot connect to the Docker daemon` | Daemon down or socket permission | `systemctl status docker`; `ls -l /var/run/docker.sock` | Start daemon; add user to `docker` group deliberately |
| Published port unreachable remotely | Firewall or bound to 127.0.0.1 | `docker port c`; `ss -ltn` | Open firewall; publish on `0.0.0.0` intentionally ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)) |
| `depends_on` started but DB refuses | Started is not ready | `docker compose ps` | `condition: service_healthy` ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)) |

## 9. Best Practices

- **State the method first**, then the commands: "I would establish scope, then read exit code and logs, then enter the container."
- **Prefer read-only commands** (`inspect`, `logs`, `stats`, `events`) before anything that mutates state.
- **Ask clarifying questions:** one container or all? since when? after what change? does it reproduce on another host? An interviewer scores this highly.
- **Separate mitigation from root cause** and give both, plus the prevention (alert, limit, test, lint).
- **Quote evidence**, not intuition: "`OOMKilled` is true, therefore..." beats "probably memory".
- **Know the escape hatches:** `docker run --entrypoint sh`, `docker commit` for forensic copies only, `docker cp` to extract artifacts, `docker diff` to see unexpected writes.
- **Reproduce minimally** in a throwaway container and tear it down afterwards.

## 10. Common Anti-Patterns / Mistakes

- Running `docker system prune -a --volumes` on a production host to free space (deletes data volumes).
- Restarting before capturing evidence, so the cause is lost.
- Setting `restart: always` to hide a crash loop instead of reading the exit code.
- "Fixing" permission errors with `chmod -R 777` or `--privileged`.
- Editing a running container by hand (`docker exec` then `apt install`), producing a snowflake that vanishes on redeploy.
- Blaming Docker networking before checking that the app listens on `0.0.0.0` and the right port.
- Debugging with `latest` tags, so the failing image cannot be identified later.
- Treating exit 143 as an error, or exit 0 as success for a service that should never exit.
- Answering with a list of commands and no hypothesis.

## 11. Interview Questions

**🎯 Beginner:** _"A container you started with `docker run -d` is not in `docker ps`. How do you find out what happened?"_
**Model answer:** `docker ps` shows only running containers, so I would run `docker ps -a` to see it with its status and exit code, then `docker logs <name>` for output and `docker inspect -f '{{.State.ExitCode}} {{.State.OOMKilled}} {{.State.Error}}' <name>` for detail. Exit 0 means the main process simply finished; 1 is an application error; 125 means Docker itself could not start it; 126 and 127 mean the command was not executable or not found; 137 means SIGKILL, often out-of-memory. I would only start changing things once I know which of those it is.
_What the interviewer is probing for:_ Knowing `-a`, exit code meaning, and starting with evidence rather than re-running blindly.

**🎯 Intermediate:** _"A web container is healthy and listening, but a second container on the same host gets 'connection refused' calling it by name. Walk through your diagnosis."_
**Model answer:** I split the problem into name resolution, routing and listening. First confirm both containers are on the same user-defined network with `docker network inspect`, because the default bridge does not provide DNS by name. From the caller, `getent hosts web` proves resolution and `nc -zv web 8080` tests the port. "Connection refused" (as opposed to a timeout) means the packet arrived and nothing was listening on that address, so I check `ss -ltn` inside the web container: an app bound to `127.0.0.1` is unreachable from other containers and must bind `0.0.0.0`. I also confirm the caller uses the container port, not the host-published port. A timeout instead would point at a network policy, firewall or different network.
_What the interviewer is probing for:_ Layered network reasoning and the difference between refused, timeout and NXDOMAIN.

**🎯 Senior:** _"At 02:00 a payment service container enters a restart loop with exit 137 after a Friday deploy. Customers are failing. What do you do, in order?"_
**Model answer:** First restore service: roll back to the previous image digest, since the deploy is the strongest change signal, and confirm health. Then preserve evidence from the failed instance: `docker inspect` for `OOMKilled`, limits and `RestartCount`, the last logs, `docker stats` history from monitoring, and `dmesg` for the cgroup OOM line. If OOM is confirmed I compare memory profiles between versions, check whether the new build changed heap settings, base image or a dependency, and reproduce under the same limit in staging. The fix is a code or tuning change, with a load test that asserts memory headroom. Prevention: a memory-usage alert at around 80 percent of the limit, a deploy gate that watches restart counts, canary rollout, and a blameless postmortem. I would also check whether `restart: always` masked earlier occurrences.
_What the interviewer is probing for:_ Prioritizing mitigation, preserving evidence, and closing the loop with prevention.

**🎯 Architect:** _"Your organization runs 800 containers across 60 hosts and on-call keeps getting paged for the same container problems. How do you reduce incident volume and mean time to diagnose?"_
**Model answer:** I would classify the last quarter's incidents by cause; typically a handful (OOM, disk full from logs, missing health checks, bad rollouts, registry rate limits) dominate. Then convert each into a platform guardrail: mandatory memory and PID limits with defaults, log rotation or a central log driver set in `daemon.json`, a standard HEALTHCHECK and graceful-shutdown contract in the base images, digest-pinned deploys with automatic rollback on health regression, and a registry mirror to remove Hub limits. For diagnosis speed, ship metrics (cAdvisor and Prometheus), centralized logs, container events and deploy markers onto one dashboard so the "what changed?" question is answered in seconds, and publish runbooks keyed to exit codes. Finally, rehearse with game days and track MTTD, MTTR and repeat-incident rate as the success metrics.
_What the interviewer is probing for:_ Systemic thinking: turning recurring tickets into guardrails, observability and measurable outcomes.

## 12. Common Misconceptions

- "Exit 137 always means out-of-memory." It means SIGKILL; check `OOMKilled` to know whether the OOM killer or a stop timeout did it.
- "`docker logs` shows everything the app ever wrote." Only what the log driver retained; rotation and remote drivers change this.
- "If `docker ps` shows Up, the app is working." Without a health check, "Up" only means PID 1 exists.
- "Connection refused and timeout mean the same thing." Refused means reachable but not listening; timeout means dropped or unrouted.
- "Restarting the container is a fix." It resets symptoms and erases evidence.
- "Pruning is always safe." Volumes hold state, and unused is not the same as unimportant.

## 13. 🔑 Key Takeaways

- Use one repeatable ladder: state and exit code, logs, processes and resources, inside view, daemon and host, then what changed.
- Memorize the exit codes: 0, 1, 125, 126, 127, 137, 139, 143.
- Separate mitigation (rollback) from root cause, and finish every answer with prevention.
- Refused, timeout and NXDOMAIN point to different layers.
- Never solve a diagnosis problem by adding privilege or deleting data.
- Capture evidence before restarting, and reproduce against the same image digest.

## 14. Related Concepts & What's Next

Related: production troubleshooting ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)), network tooling ([§47](../Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), logging ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)), cleanup ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)), and rollback ([§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). Next, [§103](Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md) shifts from runtime failures to reviewing a flawed Dockerfile line by line.

**Next Section:** [§103](Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md) — `Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md`
