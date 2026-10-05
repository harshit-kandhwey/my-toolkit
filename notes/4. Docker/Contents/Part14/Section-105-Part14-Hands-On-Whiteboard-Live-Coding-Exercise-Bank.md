# Section 105 (Part 14): Hands-On Whiteboard / Live-Coding Exercise Bank

## 1. Definition

**Plain language:** A bank of small, timed exercises you can be handed in an interview, a pairing session or a DCA-style practical: draw this on the whiteboard, write this Dockerfile, fix this broken file, make this container behave. Each exercise has a prompt, a time box, a reference solution and the checks that prove the solution works.

**Precise definition:** The exercises fall into three formats. **Whiteboard** exercises ask you to draw and narrate a mechanism (what happens on `docker run`, how a published port reaches a container) with no keyboard. **Live-coding** exercises ask you to author or repair a Dockerfile, Compose file or entrypoint script while someone watches your reasoning. **Debug-live** exercises hand you something broken and ask you to find the cause with `docker inspect`, `logs`, `exec` and friends. Every exercise here is self-contained and uses only throwaway images, containers, networks and volumes named with the prefix `kb-` so cleanup is one filter away.

> 💡 **Tip:** Narrate while you work. Interviewers score the reasoning (what you check first, what you rule out) at least as highly as the final file.

## 2. Why This Matters

- Written answers ([§101](Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md)) prove you know facts; live exercises prove you can apply them under mild pressure.
- Dockerfile review ([§103](Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md)) and troubleshooting ([§102](Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md)) questions are often delivered as a shared screen, not as prose.
- Muscle memory matters: the same dozen commands (`inspect`, `logs`, `exec`, `history`, `stats`, `top`) solve most live problems.
- Practising on throwaway resources builds the habit of never experimenting against real data, which is also the safe operating habit in production.

## 3. Prerequisites and Dependencies

You should have worked through Dockerfile authoring ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md), [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), runtime flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), Compose ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md), [§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), networking ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), volumes ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)) and multi-stage builds ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)). Design-level practice is in [§104](Section-104-Part14-System-Design-Questions-Involving-Containers.md). You need a working Docker Engine 27/28 with BuildKit (the default) and Compose v2, plus a scratch directory (`mkdir kb-exercises && cd kb-exercises`).

## 4. Architecture / Conceptual Diagram

```text
  Exercise loop (use it for every item in the bank)

  ┌──────────┐   ┌───────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐
  │ 1 Clarify│──►│ 2 State   │──►│ 3 Build / │──►│ 4 Verify │──►│ 5 Clean │
  │  the ask │   │ the plan  │   │ draw it   │   │ with     │   │ up kb-* │
  │          │   │ (30 sec)  │   │           │   │ commands │   │         │
  └──────────┘   └───────────┘   └───────────┘   └────┬─────┘   └─────────┘
                                                      │ fails?
                                                      ▼
                                          inspect ► logs ► exec ► top ► events

  Whiteboard reference: what `docker run -p 8080:80 nginx` touches

  docker CLI ──REST──► dockerd ──gRPC──► containerd ──► runc ──► container
      │                   │                                         │
      │                   ├─ image pull/unpack (overlay2 snapshot)  ├─ namespaces
      │                   ├─ network: veth + bridge + iptables DNAT └─ cgroups v2
      │                   └─ container config.v2.json
      ▼
  host:8080 ──DNAT──► 172.17.0.x:80   (docker-proxy only for loopback/IPv6 cases)
```

- **Time boxes:** whiteboard 5-10 min, live-coding 15-20 min, debug-live 10-15 min.
- **Difficulty tags** below: (E) easy, (M) medium, (H) hard.

## 5. Hands-On

All commands assume a POSIX shell. Each exercise states a **Task**, a **Reference solution** and **Verify**. Resources use the `kb-` prefix; the cleanup at the end of this section removes only those.

### 5.1 Whiteboard W1 (E): Trace `docker run`

**Task:** Draw every component involved from `docker run -d -p 8080:80 nginx:1.27` to a served request.

**Reference solution:** CLI sends a REST call over `/var/run/docker.sock`; dockerd resolves the image (pulls missing layers, [§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), asks containerd to create a task; containerd's shim invokes runc, which sets up namespaces and cgroups ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)) and execs the entrypoint ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). dockerd attaches a veth to the bridge and writes a DNAT rule for 8080 to the container's port 80 ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).

**Verify (optional):**

```bash
docker run -d --name kb-w1 -p 127.0.0.1:18080:80 nginx:1.27-alpine
docker inspect kb-w1 --format '{{.NetworkSettings.IPAddress}} {{json .NetworkSettings.Ports}}'
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18080
```

```text
172.17.0.2 {"80/tcp":[{"HostIp":"127.0.0.1","HostPort":"18080"}]}
200
```

### 5.2 Whiteboard W2 (M): Layers and Copy-on-Write

**Task:** Explain on the board why deleting a file in a later `RUN` does not shrink the image, and where a running container's writes go.

**Reference solution:** Draw a stack of read-only lower layers, one upper writable layer, and the merged view. A `rm` in a later layer adds a whiteout entry; the earlier layer still holds the bytes. Container writes land in the upper dir (copy-up on first modification, [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)).

**Verify:**

```bash
mkdir -p kb-w2 && cd kb-w2
printf 'FROM alpine:3.20\nRUN dd if=/dev/zero of=/big bs=1M count=20\nRUN rm /big\n' > Dockerfile
docker build -q -t kb-w2 . && docker history kb-w2 --format '{{.Size}}\t{{.CreatedBy}}' | head -4
```

```text
0B      RUN /bin/sh -c rm /big # buildkit
21MB    RUN /bin/sh -c dd if=/dev/zero ... # buildkit
```

### 5.3 Whiteboard W3 (M): Two Containers Talk by Name

**Task:** Draw why `ping db` works on a user-defined network but not on the default bridge.

**Reference solution:** User-defined networks get Docker's embedded DNS at `127.0.0.11` inside each container; the default `bridge` does not provide name resolution ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)).

**Verify:**

```bash
docker network create kb-net
docker run -d --name kb-db --network kb-net alpine:3.20 sleep 600
docker run --rm --network kb-net alpine:3.20 ping -c1 kb-db
docker run --rm alpine:3.20 ping -c1 kb-db
```

```text
64 bytes from 172.20.0.2: seq=0 ttl=64 time=0.1 ms
ping: bad address 'kb-db'
```

### 5.4 Live-Coding L1 (E): Containerize a Small Python App

**Task:** Write a Dockerfile for a Flask-style app that runs as non-root, caches dependencies and stops cleanly.

**Reference solution:**

```dockerfile
# kb-l1/Dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
RUN useradd --system --uid 10001 app
USER 10001
EXPOSE 8000
CMD ["python", "app.py"]
```

```python
# kb-l1/app.py  (stdlib only so the exercise needs no dependencies)
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok\n")
HTTPServer(("0.0.0.0", 8000), H).serve_forever()
```

**Verify:**

```bash
mkdir -p kb-l1 && cd kb-l1   # create the files above, plus an empty requirements.txt
docker build -t kb-l1 .
docker run -d --name kb-l1 -p 127.0.0.1:18000:8000 kb-l1
docker exec kb-l1 id -u
time docker stop kb-l1
```

```text
10001
real    0m0.2s    # exec form, python is PID 1 and exits on SIGTERM
```

Talking points: dependency file copied before source ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), numeric UID so Kubernetes `runAsNonRoot` can verify it ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)).

### 5.5 Live-Coding L2 (M): Multi-Stage Build for a Static Binary

**Task:** Shrink a Go "hello" service to a small final image without a shell.

**Reference solution:**

```dockerfile
# kb-l2/Dockerfile
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY main.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/hello .

FROM scratch
COPY --from=build /out/hello /hello
USER 10001:10001
ENTRYPOINT ["/hello"]
```

```go
// kb-l2/main.go
package main
import "fmt"
func main() { fmt.Println("hello from scratch") }
```

```bash
mkdir -p kb-l2 && cd kb-l2 && printf 'module kbhello\n\ngo 1.23\n' > go.mod   # add main.go
docker build -t kb-l2 .
docker run --rm kb-l2
docker image ls kb-l2 --format '{{.Size}}'
```

```text
hello from scratch
1.6MB
```

Talking points: `scratch` has no CA bundle or timezone data (copy them from the build stage if the app needs TLS), no shell for `exec` debugging ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md), [§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)).

### 5.6 Live-Coding L3 (M): Entrypoint Script with `exec`

**Task:** Write an entrypoint that fails fast when `APP_MODE` is missing, renders a line of config, then hands PID 1 to the real command.

**Reference solution:**

```sh
#!/bin/sh
# kb-l3/entrypoint.sh
set -eu
: "${APP_MODE:?APP_MODE must be set}"
echo "mode=${APP_MODE}" > /tmp/app.conf
exec "$@"
```

```dockerfile
# kb-l3/Dockerfile
FROM alpine:3.20
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]
CMD ["sleep", "300"]
```

**Verify:**

```bash
docker build -t kb-l3 kb-l3
docker run --rm kb-l3 true; echo "exit=$?"
docker run -d --name kb-l3 -e APP_MODE=dev kb-l3
docker exec kb-l3 ps -o pid,args
```

```text
/usr/local/bin/entrypoint.sh: line 4: APP_MODE: APP_MODE must be set
exit=2
PID   COMMAND
    1 sleep 300
```

Talking points: [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md) semantics, `${VAR:?}` for validation, CRLF line endings as the classic Windows failure.

### 5.7 Live-Coding L4 (M): Compose with a Health-Gated Dependency

**Task:** Two services: a "database" and a client that must not start until the database is healthy. Use only Alpine so no registry credentials or large pulls are needed.

**Reference solution:**

```yaml
# kb-l4/compose.yaml
name: kb-l4
services:
  db:
    image: alpine:3.20
    command: sh -c "sleep 5 && touch /tmp/ready && sleep 600"
    healthcheck:
      test: ["CMD", "test", "-f", "/tmp/ready"]
      interval: 2s
      timeout: 2s
      retries: 10
  client:
    image: alpine:3.20
    command: sh -c "echo db was healthy before I started && sleep 5"
    depends_on:
      db:
        condition: service_healthy
```

```bash
docker compose -f kb-l4/compose.yaml up --abort-on-container-exit
docker compose -f kb-l4/compose.yaml down -v
```

```text
db-1      | (waits about 5s)
client-1  | db was healthy before I started
```

Talking points: plain `depends_on` only orders start, not readiness ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)); `down -v` removes the project's volumes and network.

### 5.8 Live-Coding L5 (H): Back Up and Restore a Named Volume

**Task:** Write data into a volume, back it up to a tarball using a helper container, destroy the volume, restore into a new one and prove integrity.

**Reference solution:**

```bash
docker volume create kb-data
docker run --rm -v kb-data:/data alpine:3.20 sh -c 'echo precious > /data/file.txt'

mkdir -p kb-backup
docker run --rm -v kb-data:/data:ro -v "$PWD/kb-backup:/backup" alpine:3.20 \
  tar -czf /backup/data.tgz -C /data .

docker volume rm kb-data
docker volume create kb-data-restored
docker run --rm -v kb-data-restored:/data -v "$PWD/kb-backup:/backup:ro" alpine:3.20 \
  tar -xzf /backup/data.tgz -C /data
docker run --rm -v kb-data-restored:/data:ro alpine:3.20 cat /data/file.txt
```

```text
precious
```

Talking points: mount the source read-only for backup; restore into a **new** empty volume rather than overwriting ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)); for databases prefer the engine's own dump tool for consistency.

### 5.9 Debug-Live D1 (M): The Container That Exits Immediately

**Task:** `docker run -d kb-d1` shows `Exited (0)` after a second. Find out why and fix it without changing the application.

**Setup and diagnosis:**

```bash
mkdir -p kb-d1 && printf 'FROM alpine:3.20\nCMD ["echo","done"]\n' > kb-d1/Dockerfile
docker build -t kb-d1 kb-d1
docker run -d --name kb-d1 kb-d1
docker ps -a --filter name=kb-d1 --format '{{.Status}}'
docker logs kb-d1
docker inspect kb-d1 --format '{{json .Config.Cmd}} exit={{.State.ExitCode}}'
```

```text
Exited (0) 2 seconds ago
done
["echo","done"] exit=0
```

**Fix:** a container lives as long as PID 1. A foreground process (a server, or `sleep infinity` for a debug container) must be PID 1. Do not "fix" this with `tail -f /dev/null` in production images ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)).

### 5.10 Debug-Live D2 (H): The Memory-Limited Process That Disappears

**Task:** A container with a 64 MiB limit dies with exit code 137 and no application log. Prove the cause.

```bash
docker run -d --name kb-d2 --memory 64m --memory-swap 64m alpine:3.20 \
  sh -c 'a=x; while true; do a="$a$a"; done'
sleep 3
docker inspect kb-d2 --format 'oom={{.State.OOMKilled}} exit={{.State.ExitCode}}'
```

```text
oom=true exit=137
```

**Fix:** raise the limit or fix the leak; watch `docker stats`; exit 137 is 128 + SIGKILL(9) ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md), [§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)).

### 5.11 Cleanup (removes only `kb-` resources)

```bash
docker rm -f $(docker ps -aq --filter "name=kb-") 2>/dev/null
docker compose -f kb-l4/compose.yaml down -v 2>/dev/null
docker network rm kb-net 2>/dev/null
docker volume rm kb-data kb-data-restored 2>/dev/null
docker image rm kb-w2 kb-l1 kb-l2 kb-l3 kb-d1 2>/dev/null
cd .. && rm -r kb-exercises   # the scratch folder you created in section 3 only
```

## 6. Production Usage Notes

- Each exercise compresses a production task: L1/L2 the build pipeline, L3 the entrypoint contract ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), L4 local-dev parity ([§41](../Part5/Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md)), L5 the backup runbook.
- Keep a toolbox of one-liners (`docker inspect --format`, `docker events`, `docker system df`).
- A competent engineer should finish L1 in under 10 minutes.

## 7. Security Considerations

- Never run destructive experiments against real volumes or home folders; mount only a dedicated scratch directory, `:ro` when possible ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)).
- Do not mount `/var/run/docker.sock`; it is root-equivalent ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- Publish exercise ports on `127.0.0.1` only.
- In interviews, state why you use non-root users, pinned tags and read-only mounts.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| Build cannot find `requirements.txt` | Wrong context or `.dockerignore` | Check [§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md) |
| `exec format error` on entrypoint | CRLF or missing shebang | Convert to LF, add `#!/bin/sh` |
| `permission denied` on script | No execute bit | `COPY --chmod=755` |
| Restore shows empty volume | Tar path mismatch | List with `tar -tzf` first |
| `ping: bad address` | Default bridge, no DNS | Use a user-defined network |

## 9. Best Practices

- Clarify requirements, start minimal, run it, then improve.
- State the expected output before pressing Enter.
- Default to pinned tags, exec form, `WORKDIR` and non-root `USER` ([§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)).
- Clean up with filters (`--filter name=kb-`), never global prunes.

## 10. Common Anti-Patterns / Mistakes

- `docker system prune -a` on a shared machine ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).
- `COPY . .` before dependency install ([§95](../Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)).
- `tail -f /dev/null` as a production fix; silent debugging without `logs` and `inspect`.

## 11. Interview Questions

**🎯 Beginner:** _"Live: write a Dockerfile for a small Python script that prints a greeting, and show me two ways to run it with a different message."_
**Model answer:** `FROM python:3.12-slim`, `WORKDIR /app`, `COPY greet.py .`, `ENTRYPOINT ["python","greet.py"]`, `CMD ["hello"]`. Run with `docker run --rm img` for the default, and either pass arguments (`docker run --rm img "good morning"`, which replaces CMD) or an environment variable the script reads (`-e GREETING=...`). I would build it, run it, and show the exec-form behavior with `docker inspect` to confirm what was stored.
_What the interviewer is probing for:_ Basic Dockerfile fluency and the CMD/ENTRYPOINT/env override paths.

**🎯 Intermediate:** _"Here is a Dockerfile that copies the whole repo, then runs `pip install`. Builds take four minutes on every code change. Fix it live."_
**Model answer:** Invalidation happens because `COPY . .` precedes the install, so any source change busts the dependency layer. Copy only `requirements.txt`, run the install, then copy the rest. Add a `.dockerignore` for `.git`, virtualenvs and caches, and use a BuildKit cache mount (`RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt`) so even a changed requirements file reuses downloaded wheels. Verify with a second build where only `app.py` changed: the install layer should show `CACHED`.
_What the interviewer is probing for:_ Layer-cache ordering and BuildKit cache mounts.

**🎯 Senior:** _"A service container restarts every few minutes in production with exit code 137. You have five minutes on a shared screen. Walk me through it."_
**Model answer:** 137 is SIGKILL. First `docker inspect --format '{{.State.OOMKilled}} {{.HostConfig.Memory}}'` to separate the kernel OOM killer (true) from a manual `kill` or a `docker stop` timeout (false, shell-form PID 1 as in [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)). If OOM, compare `docker stats` against the limit and check whether the runtime (JVM, Node) honors the cgroup limit; look at the cgroup `memory.events`. Short-term raise the limit or set the heap relative to it; long-term fix the leak or the sizing, and add a memory alert before the limit rather than after the kill.
_What the interviewer is probing for:_ Structured diagnosis, distinguishing OOM from signal-timeout kills, cgroup awareness.

**🎯 Architect:** _"Design the practical assessment you would give candidates for a platform-engineering role so it measures judgment, not memorization."_
**Model answer:** A time-boxed exercise on a throwaway environment containing a deliberately flawed service: a Dockerfile with cache, size and root-user issues, a Compose file with a race on database startup, and one runtime fault (OOM or bad healthcheck). Score on a rubric: diagnosis method, fix correctness, security defaults, whether they verify, and how they communicate trade-offs. Provide the allowed documentation, make cleanup part of the task, and run the same exercise through a pilot of existing engineers to calibrate time and difficulty. Avoid trivia such as flag memorization.
_What the interviewer is probing for:_ Assessment design thinking and the ability to tie evaluation criteria to real platform work.

## 12. Common Misconceptions

- "Live exercises test speed." They test method; a slow, correct, verified answer beats a fast guess.
- "If the container is `Exited (0)` something is broken." It may have completed its task; PID 1 simply ended.
- "A later `RUN rm` shrinks the image." Earlier layers keep the data.
- "`depends_on` waits for readiness." Only with `condition: service_healthy`.
- "Backing up a volume means copying `/var/lib/docker/volumes`." Use a helper container or the application's dump tool.

## 13. 🔑 Key Takeaways

- Follow the loop: clarify, plan, build, verify, clean up.
- The same diagnostic ladder (`ps -a`, `logs`, `inspect`, `exec`, `stats`) solves most debug-live tasks.
- Cache-friendly ordering, non-root USER, exec form and pinned tags are expected defaults.
- Name and filter your throwaway resources so cleanup is surgical.
- Narrate reasoning; verification is part of the answer.

## 14. Related Concepts & What's Next

Related: interview Q&A ([§101](Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md)), troubleshooting scenarios ([§102](Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md)), Dockerfile review ([§103](Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md)), system design ([§104](Section-104-Part14-System-Design-Questions-Involving-Containers.md)), DCA domains ([§100](Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)). The wrap-up part turns these one-off drills into a progressive lab path.

**Next Section:** [§106](../Part15/Section-106-Part15-Progressive-Hands-On-Labs-Beginner-Production-Style.md) — `Section-106-Part15-Progressive-Hands-On-Labs-Beginner-Production-Style.md`
