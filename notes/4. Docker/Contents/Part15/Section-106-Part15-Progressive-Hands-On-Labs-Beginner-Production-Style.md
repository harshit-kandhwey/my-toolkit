# Section 106 (Part 15): Progressive Hands-On Labs (Beginner to Production-Style)

## 1. Definition

**Plain language:** A ladder of ten labs. Each one builds on the previous, starting with running a single container and ending with a hardened, health-checked, multi-service stack with backup and rollback. Every lab lists its goal, the commands, the expected output and an explicit cleanup.

**Precise definition:** The labs are grouped in four levels: **Level 1 Foundations** (labs 1-3: run, build, inspect), **Level 2 Composition** (labs 4-6: networks, volumes, Compose), **Level 3 Hardening** (labs 7-8: least privilege, limits, health), and **Level 4 Production-style** (labs 9-10: multi-stage pipeline artifacts, deploy/rollback/backup). All resources carry the prefix `lab` plus the lab number (for example `lab4-net`) and the label `kb.lab=true`, so a single filtered cleanup removes everything and nothing else.

> ⚠️ **Warning:** Run these labs only against a disposable Docker Engine or Docker Desktop VM. Never mount your home folder, a drive root, Desktop, Documents, OneDrive or AppData into any lab container. Every bind mount below uses a scratch directory you create yourself.

## 2. Why This Matters

- Reading about namespaces, layers and networks produces recognition; running them produces recall.
- The path mirrors how knowledge compounds: you cannot reason about Compose healthchecks without understanding single-container lifecycle, nor about rollback without tagging discipline.
- Labs generate the evidence you cite in interviews ("I measured the image drop from 1.1 GB to 14 MB") instead of claims.
- A consistent labelling and cleanup habit transfers directly to CI runners and shared hosts, where stray containers cost money and ports.

## 3. Prerequisites and Dependencies

A working Docker Engine 27/28 (BuildKit default, cgroup v2, Compose v2) reachable without sudo, internet access to pull small images (`alpine:3.20`, `nginx:1.27-alpine`, `python:3.12-slim`, `golang:1.23-alpine`), and a scratch directory: `mkdir ~/kb-labs && cd ~/kb-labs`. Background: [§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md), [§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md), [§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md), [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md), [§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md), [§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md).

## 4. Architecture / Conceptual Diagram

```text
  Level 1 Foundations      Level 2 Composition       Level 3 Hardening        Level 4 Production-style
  ┌────────────────────┐   ┌────────────────────┐   ┌───────────────────┐   ┌────────────────────────┐
  │ L1 run & lifecycle │   │ L4 networks + DNS  │   │ L7 non-root, caps │   │ L9  multi-stage, tags  │
  │ L2 build a Docker- │──►│ L5 volumes + backup│──►│    read-only fs   │──►│ L10 deploy ► rollback  │
  │    file            │   │ L6 Compose stack   │   │ L8 limits, health │   │     ► backup ► verify  │
  │ L3 inspect & debug │   │                    │   │    restart policy │   │                        │
  └────────────────────┘   └────────────────────┘   └───────────────────┘   └────────────────────────┘
        containers               plumbing                 safety                    operations

  Safety rails common to every lab
  ┌───────────────────────────────────────────────────────────────┐
  │ names:   labN-*            label: kb.lab=true                  │
  │ ports:   127.0.0.1 only    mounts: ~/kb-labs/<lab> only        │
  │ cleanup: docker ... --filter label=kb.lab=true  (final step)   │
  └───────────────────────────────────────────────────────────────┘
```

- Do the labs in order; each states what it assumes from earlier ones.
- If a lab fails, use the troubleshooting table in section 8 before moving on.
- **Time estimate:** about 5-15 minutes per lab, 2 hours for the full ladder.

## 5. Hands-On

### 5.1 Lab 1: Run, Observe, Stop (Foundations)

**Goal:** Understand that a container is a process whose lifetime is PID 1.

```bash
docker run -d --name lab1-web --label kb.lab=true -p 127.0.0.1:18081:80 nginx:1.27-alpine
docker ps --filter label=kb.lab=true --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18081
docker logs --tail 3 lab1-web
docker top lab1-web
docker stop lab1-web && docker ps -a --filter name=lab1-web --format '{{.Status}}'
```

```text
NAMES       STATUS         PORTS
lab1-web    Up 3 seconds   127.0.0.1:18081->80/tcp
200
... "GET / HTTP/1.1" 200 615 "-" "curl/8.x"
UID  PID  PPID  C STIME TTY TIME CMD
root 1234 1210  0 10:00 ?   00:00:00 nginx: master process nginx -g daemon off;
Exited (0) 1 second ago
```

**Checkpoint:** you can explain why `docker top` shows a host PID different from the container's PID 1 ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)).

### 5.2 Lab 2: Write and Build a Dockerfile (Foundations)

**Goal:** Build a small Python HTTP service image with sensible defaults.

```bash
mkdir -p lab2 && cd lab2
cat > app.py <<'EOF'
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(f"hello from {os.uname().nodename} v{os.getenv('APP_VERSION','0')}\n".encode())
HTTPServer(("0.0.0.0", 8000), H).serve_forever()
EOF
cat > Dockerfile <<'EOF'
FROM python:3.12-slim
ARG APP_VERSION=1
ENV APP_VERSION=${APP_VERSION} PYTHONUNBUFFERED=1
LABEL kb.lab=true
WORKDIR /app
COPY app.py .
EXPOSE 8000
CMD ["python", "app.py"]
EOF
printf '__pycache__\n.git\n' > .dockerignore
docker build -t lab2-app:1 --build-arg APP_VERSION=1 .
docker run -d --name lab2-app --label kb.lab=true -p 127.0.0.1:18082:8000 lab2-app:1
curl -s http://127.0.0.1:18082
cd ..
```

```text
hello from 3f9c1a2b7d10 v1
```

**Checkpoint:** change `app.py`, rebuild, and confirm the `FROM` and `ARG` steps show `CACHED` while `COPY` re-runs ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).

### 5.3 Lab 3: Inspect and Debug (Foundations)

**Goal:** Learn the diagnostic ladder on the Lab 2 container.

```bash
docker image history lab2-app:1 --format '{{.Size}}\t{{.CreatedBy}}' | head -6
docker image inspect lab2-app:1 --format 'user={{.Config.User}} cmd={{json .Config.Cmd}} env={{json .Config.Env}}'
docker inspect lab2-app --format 'pid={{.State.Pid}} ip={{.NetworkSettings.IPAddress}} restarts={{.RestartCount}}'
docker exec lab2-app sh -c 'id; ps; cat /proc/1/cgroup'
docker diff lab2-app
```

```text
user= cmd=["python","app.py"] env=[...,"APP_VERSION=1","PYTHONUNBUFFERED=1"]
uid=0(root) gid=0(root)
0::/
```

**Checkpoint:** note `user=` is empty, meaning root. Lab 7 fixes this. `0::/` is the cgroup v2 unified hierarchy ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)).

### 5.4 Lab 4: Networks and DNS (Composition)

**Goal:** Prove name resolution and isolation on user-defined networks.

```bash
docker network create --label kb.lab=true lab4-front
docker network create --label kb.lab=true --internal lab4-back
docker run -d --name lab4-api  --label kb.lab=true --network lab4-front lab2-app:1
docker network connect lab4-back lab4-api
docker run -d --name lab4-db   --label kb.lab=true --network lab4-back alpine:3.20 sleep 600
docker run --rm --network lab4-front alpine:3.20 wget -qO- http://lab4-api:8000
docker run --rm --network lab4-front alpine:3.20 ping -c1 -W2 lab4-db
docker exec lab4-api python -c "import socket;print(socket.gethostbyname('lab4-db'))"
docker run --rm --network lab4-back alpine:3.20 wget -qO- -T3 http://example.com
```

```text
hello from 8a1b2c3d4e5f v1
ping: bad address 'lab4-db'
172.21.0.2
wget: download timed out
```

**Checkpoint:** `lab4-db` is reachable only through `lab4-api`, and the `--internal` network has no route out ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md), [§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).

### 5.5 Lab 5: Volumes, Persistence and Backup (Composition)

**Goal:** Show that data outlives the container, and practice a safe backup and restore.

```bash
docker volume create --label kb.lab=true lab5-data
docker run --rm -v lab5-data:/data alpine:3.20 sh -c 'date > /data/stamp; ls -l /data'
docker run --rm -v lab5-data:/data alpine:3.20 cat /data/stamp    # new container, same data

mkdir -p lab5-backup
docker run --rm -v lab5-data:/data:ro -v "$PWD/lab5-backup:/backup" alpine:3.20 \
  tar -czf /backup/lab5.tgz -C /data .
docker volume create --label kb.lab=true lab5-restore
docker run --rm -v lab5-restore:/data -v "$PWD/lab5-backup:/backup:ro" alpine:3.20 \
  tar -xzf /backup/lab5.tgz -C /data
docker run --rm -v lab5-data:/a:ro -v lab5-restore:/b:ro alpine:3.20 \
  sh -c 'cmp /a/stamp /b/stamp && echo identical'
```

```text
Thu Oct  1 10:00:00 UTC 2026
Thu Oct  1 10:00:00 UTC 2026
identical
```

**Checkpoint:** restored into a *new* volume, never over the original ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md), [§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).

### 5.6 Lab 6: A Compose Stack with Health Gating (Composition)

**Goal:** Model two services, a network and a volume declaratively, with readiness ordering.

```bash
mkdir -p lab6 && cat > lab6/compose.yaml <<'EOF'
name: lab6
x-labels: &labels
  kb.lab: "true"
services:
  cache:
    image: alpine:3.20
    command: sh -c "touch /tmp/ready; while true; do sleep 5; done"
    labels: *labels
    volumes: ["state:/state"]
    healthcheck:
      test: ["CMD", "test", "-f", "/tmp/ready"]
      interval: 2s
      retries: 5
  web:
    image: nginx:1.27-alpine
    labels: *labels
    ports: ["127.0.0.1:18086:80"]
    depends_on:
      cache:
        condition: service_healthy
volumes:
  state: {labels: *labels}
EOF
docker compose -f lab6/compose.yaml up -d --wait
docker compose -f lab6/compose.yaml ps
docker compose -f lab6/compose.yaml config --services
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18086
```

```text
NAME          SERVICE  STATUS                  PORTS
lab6-cache-1  cache    Up 6 seconds (healthy)
lab6-web-1    web      Up 3 seconds            127.0.0.1:18086->80/tcp
200
```

**Checkpoint:** `up --wait` blocks until healthy; `web` started only after `cache` passed its check ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md), [§40](../Part5/Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md)).

### 5.7 Lab 7: Least Privilege and Read-Only Runtime (Hardening)

**Goal:** Fix Lab 3's root finding and apply a hardened run profile.

```bash
cd lab2
sed -i 's/^WORKDIR \/app/RUN useradd --system --uid 10001 app\nWORKDIR \/app/' Dockerfile
sed -i 's/^CMD /USER 10001\nCMD /' Dockerfile
docker build -t lab2-app:2 --build-arg APP_VERSION=2 . && cd ..
docker run -d --name lab7-app --label kb.lab=true \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 100 -p 127.0.0.1:18087:8000 lab2-app:2
docker exec lab7-app id
docker exec lab7-app sh -c 'touch /app/x' ; echo "write exit=$?"
docker exec lab7-app sh -c 'grep -E "Cap(Eff|Prm)" /proc/1/status'
docker inspect lab7-app --format 'ro={{.HostConfig.ReadonlyRootfs}} caps_drop={{json .HostConfig.CapDrop}}'
```

```text
uid=10001(app) gid=10001 groups=10001
touch: /app/x: Read-only file system
write exit=1
CapPrm: 0000000000000000
CapEff: 0000000000000000
ro=true caps_drop=["ALL"]
```

**Checkpoint:** the app still serves on 8000 (a high port needs no capability). Explain what would break if it needed `/var/cache` or port 80 ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).

### 5.8 Lab 8: Limits, Health and Self-Healing (Hardening)

**Goal:** Observe cgroup enforcement and automatic restart.

```bash
docker run -d --name lab8-oom --label kb.lab=true --memory 32m --memory-swap 32m \
  --restart on-failure:3 alpine:3.20 sh -c 'a=x; while true; do a="$a$a"; done'
sleep 8
docker inspect lab8-oom --format 'oom={{.State.OOMKilled}} restarts={{.RestartCount}} status={{.State.Status}}'

docker run -d --name lab8-hc --label kb.lab=true   --health-cmd 'test -f /tmp/ok' --health-interval 2s --health-retries 2 alpine:3.20 sleep 600
sleep 7; docker inspect lab8-hc --format '{{.State.Health.Status}}'
docker exec lab8-hc touch /tmp/ok; sleep 4
docker inspect lab8-hc --format '{{.State.Health.Status}}'
```

```text
oom=true restarts=3 status=exited
unhealthy
healthy
```

**Checkpoint:** a restart policy hides crash loops unless you read `RestartCount`; health status does not restart plain Docker containers by itself ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md), [§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§88](../Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)).

### 5.9 Lab 9: Multi-Stage Build and Tagging (Production-style)

**Goal:** Produce a minimal, labelled, immutably tagged artifact and compare sizes.

```bash
mkdir -p lab9 && cd lab9
printf 'module lab9\n\ngo 1.23\n' > go.mod
cat > main.go <<'EOF'
package main
import ("fmt";"net/http";"os")
func main() {
  http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request){ fmt.Fprintln(w,"ok") })
  http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request){ fmt.Fprintf(w,"version %s\n", os.Getenv("APP_VERSION")) })
  http.ListenAndServe(":8080", nil)
}
EOF
cat > Dockerfile <<'EOF'
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
RUN --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/app .

FROM gcr.io/distroless/static-debian12:nonroot
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
LABEL kb.lab=true org.opencontainers.image.version=${APP_VERSION}
COPY --from=build /out/app /app
EXPOSE 8080
ENTRYPOINT ["/app"]
EOF
docker build -t lab9-app:1.0.0 --build-arg APP_VERSION=1.0.0 .
docker tag lab9-app:1.0.0 lab9-app:1.0 && docker tag lab9-app:1.0.0 lab9-app:1
docker image ls lab9-app --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.ID}}'
docker image inspect lab9-app:1.0.0 --format 'user={{.Config.User}} ep={{json .Config.Entrypoint}}'
cd ..
```

```text
lab9-app:1.0.0 9.3MB  b1c2d3e4f5a6
lab9-app:1.0   9.3MB  b1c2d3e4f5a6
lab9-app:1     9.3MB  b1c2d3e4f5a6
user=65532 ep=["/app"]
```

**Checkpoint:** three tags, one image ID: tags are pointers. Contrast with `golang:1.23-alpine` (hundreds of MB) using `docker image ls`; note the final image has no shell, so debug with an ephemeral sidecar ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md), [§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)).

### 5.10 Lab 10: Deploy, Roll Back and Verify (Production-style)

**Goal:** Practice a blue/green style swap with a health gate and a rollback path, using the Lab 9 image.

```bash
docker build -q -t lab9-app:1.1.0 --build-arg APP_VERSION=1.1.0 lab9 >/dev/null
docker network create --label kb.lab=true lab10-net

deploy() {   # usage: deploy <tag> <name>
  docker run -d --name "$2" --label kb.lab=true --network lab10-net \
    --read-only --cap-drop ALL --security-opt no-new-privileges --memory 64m \
    "lab9-app:$1"
  for i in $(seq 1 10); do
    docker run --rm --network lab10-net alpine:3.20 wget -qO- "http://$2:8080/healthz" 2>/dev/null | grep -q ok && return 0
    sleep 1
  done
  return 1
}

deploy 1.0.0 lab10-blue   && echo "blue healthy"
deploy 1.1.0 lab10-green  && echo "green healthy"
docker run --rm --network lab10-net alpine:3.20 wget -qO- http://lab10-green:8080/

# simulate a bad release: green fails verification, so keep blue and discard green
docker rm -f lab10-green
docker run --rm --network lab10-net alpine:3.20 wget -qO- http://lab10-blue:8080/
```

```text
blue healthy
green healthy
version 1.1.0
version 1.0.0
```

**Checkpoint:** the rollback was instant because the previous version was still running and the old tag still existed. Write down what a real router (proxy, load balancer) would add: weighted traffic, connection draining ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md), [§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)). Add a Lab 5 style volume backup before any stateful change.

### 5.11 Final Cleanup (removes only labelled lab resources)

```bash
docker compose -f lab6/compose.yaml down -v 2>/dev/null
docker rm -f $(docker ps -aq --filter label=kb.lab=true) 2>/dev/null
docker rm -f lab1-web lab8-oom lab8-hc 2>/dev/null   # these three were created labelled; belt and braces
docker network rm lab4-front lab4-back lab10-net 2>/dev/null
docker volume rm lab5-data lab5-restore 2>/dev/null
docker image rm lab2-app:1 lab2-app:2 lab9-app:1.0.0 lab9-app:1.0 lab9-app:1 lab9-app:1.1.0 2>/dev/null
docker network ls --filter label=kb.lab=true -q; docker volume ls --filter label=kb.lab=true -q
```

The last two commands should print nothing. Then remove the `~/kb-labs` scratch folder yourself once you have checked it contains only lab files. Do not use `docker system prune` on a machine where you have other work.

## 6. Production Usage Notes

- Labs 9 and 10 map to real pipelines: immutable version tags, a promoted digest ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)), health-gated rollout, retained previous versions.
- Lab 8 shows why production needs both a memory limit and an alert on `RestartCount`; silent restarts mask leaks.
- Lab 7 settings translate to Kubernetes `securityContext`; Lab 6 is local-dev and CI shape ([§83](../Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)); at scale use an orchestrator ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 7. Security Considerations

- Every port binds to `127.0.0.1`; an unqualified `-p 8080:80` listens on all interfaces and Docker's iptables rules bypass many host firewalls ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).
- Bind mounts are restricted to scratch folders; no lab touches the host home or the Docker socket.
- Do not put real secrets in `ARG`, `ENV` or labels ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)); build args show in `docker history`.
- Scan `lab2-app:1` and `lab9-app:1.0.0` with Trivy to see the vulnerability difference ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` | Host port in use | Change the host side of `-p` |
| Empty reply right after start | App not ready | Loop on the health endpoint |
| `useradd: command not found` (Alpine) | Different tooling | `adduser -S -u 10001 app` |
| `sed -i` edits nothing (macOS) | BSD sed | Edit the Dockerfile by hand |
| Compose `--wait` times out | Healthcheck never passes | `docker compose logs`; run the test via `exec` |
| Cleanup leaves a network | Container still attached | Remove containers first |

## 9. Best Practices

- Name and label everything; filter on the label for listing and cleanup.
- Predict the output before running each command.
- Re-run labs 7-10 with a deliberate fault (wrong user, missing healthcheck) and fix it.
- Read state with `inspect` rather than assuming flags took effect.

## 10. Common Anti-Patterns / Mistakes

- Running labs where production contexts exist; check `docker context ls` first.
- `--privileged` or docker.sock mounts "to make it work".
- `docker system prune -a --volumes` as cleanup ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).
- Copy-pasting without reading the output, and leaving labs running.

## 11. Interview Questions

**🎯 Beginner:** _"You ran `docker run -d nginx` and the page works. How do you show what is running, its port and logs, then remove it?"_
**Model answer:** `docker ps` shows status and ports; `docker logs -f <name>` shows output; `docker inspect <name>` gives detail. Remove with `docker rm -f <name>`. Data written inside the container is lost on removal unless it is on a volume.
_What the interviewer is probing for:_ CLI fluency and the container versus volume data lifecycle.

**🎯 Intermediate:** _"Let an API container reach a database by name, with the database unreachable from the host and the internet."_
**Model answer:** Create user-defined networks (embedded DNS gives name resolution), publish no database port, put the database on an `--internal` network, and attach the API to both that and an external-facing network so only the API bridges them. Verify with throwaway probe containers and `docker inspect` on network membership.
_What the interviewer is probing for:_ Network scoping, DNS, publishing and segmentation.

**🎯 Senior:** _"Your Compose stack works locally but flakes in CI with 'connection refused' to the database. Fix and prove it."_
**Model answer:** `depends_on` without a health condition orders start, not readiness. Add a real healthcheck (`pg_isready`), `condition: service_healthy`, client retry with backoff, and `docker compose up --wait` in CI. Prove it by looping the stack 20 times and comparing failure rates; also ensure CI does not reuse stale volumes.
_What the interviewer is probing for:_ Readiness versus start order and evidence-based fixing.

**🎯 Architect:** _"You must train 50 engineers on containers in a month. How do you structure the practical component?"_
**Model answer:** A progressive lab ladder like this one with checkpoints and a graded capstone, run in disposable sandboxes with a labelling and cleanup convention. Pair each lab with the production control it mirrors (limits, non-root, healthchecks, tagging, rollback) and finish by taking a flawed service to a hardened, rollback-capable deployment on your real platform. Measure outcomes such as time to first successful deploy, not attendance.
_What the interviewer is probing for:_ Curriculum design tied to standards and measurable results.

## 12. Common Misconceptions

- "Completing the labs equals production readiness." They teach mechanics; operations also needs monitoring, patching and incident practice.
- "`--restart always` makes a service reliable." It can hide a crash loop.
- "`EXPOSE` publishes a port." It documents; `-p` publishes.
- "Multiple tags mean multiple images." They are references to one image ID.
- "`HEALTHCHECK` restarts unhealthy containers." Plain Docker only reports status; orchestrators act on it.

## 13. 🔑 Key Takeaways

- Progress from running, to building, to composing, to hardening, to operating.
- Label and prefix every lab resource, bind only to loopback, mount only scratch folders.
- Verify with `inspect`, `logs`, `stats` and throwaway probe containers rather than assumptions.
- Hardened defaults: non-root, read-only filesystem, dropped capabilities, limits, health checks.
- Production-style delivery means immutable tags, a health gate, and a tested rollback and restore path.

## 14. Related Concepts & What's Next

Related: lifecycle and run flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md), [§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), Compose ([§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), storage ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)), CI pipelines ([§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), exercise bank ([§105](../Part14/Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank.md)). Next, the consolidated checklist condenses everything these labs exercise into a review list.

**Next Section:** [§107](Section-107-Part15-Consolidated-Key-Takeaways-Checklist.md) — `Section-107-Part15-Consolidated-Key-Takeaways-Checklist.md`
