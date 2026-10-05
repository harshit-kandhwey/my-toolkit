# Section 29 (Part 4): Container Logs and Log Drivers

## 1. Definition

**Plain language:** Docker captures whatever a container's main process writes to standard output and standard error, stores it (by default in a file on the host), and lets you read it with `docker logs`. A *log driver* decides where those captured lines go: a local file, the system journal, a syslog server, Fluentd, Graylog, AWS CloudWatch Logs and so on.

**Precise definition:** For each container the daemon attaches to the stdout and stderr streams of PID 1 ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) and forwards every line to the container's configured *logging driver*, set daemon-wide in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) with `log-driver` and `log-opts`, or per container with `--log-driver` and `--log-opt`. The default driver is `json-file`. Other built-in drivers include `local`, `journald`, `syslog`, `fluentd`, `gelf`, `awslogs`, `splunk`, `gcplogs`, `etwlogs` (Windows) and `none`. Only some drivers can be read back with `docker logs` (`local`, `json-file`, `journald` natively); for the others, Docker Engine 20.10 and later keeps a local *dual logging* cache so `docker logs` still works. Delivery runs in one of two modes: **blocking** (default; the application's write waits for the driver) or **non-blocking** (writes go to an in-memory ring buffer and are dropped if it fills).

> 💡 **Tip:** Containers should log to stdout/stderr and nothing else. Anything written to a file inside the container is invisible to `docker logs` and is lost with the container.

## 2. Why This Matters

- **First-line debugging:** `docker logs` is the fastest way to see why a container exited, crashed or misbehaves, before reaching for `exec` ([§28](Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)).
- **Disk exhaustion:** the default `json-file` driver has **no size limit or rotation**. A chatty container can fill the host disk and take down every workload on it.
- **Reliability trade-offs:** a blocking log driver pointing at an unreachable server can freeze your application on its next `write()`.
- **Compliance and observability:** logs must reach a central system, with retention, search and access control.
- **Interviews and DCA:** log drivers, rotation options and the blocking/non-blocking choice are common production-readiness questions.

## 3. Prerequisites and Dependencies

Requires the container lifecycle ([§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)) and `docker run` flags ([§26](Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), since logging options are `run`-time flags. Knowing that the daemon owns the container streams comes from the engine architecture ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)) and the client/API split ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)). Daemon-wide defaults live in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Why an application must write to stdout (PID 1 behavior, exec versus shell form) is in [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md). Log files consume the writable layer or host disk, relevant to storage ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). Moving existing log files out of a container is [§30](Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md).

## 4. Architecture / Conceptual Diagram

```text
   Container                          dockerd (host)                          Destinations
  ┌──────────────────┐   stdout/    ┌─────────────────────────────┐
  │ PID 1: app       │   stderr     │  per-container log copier   │
  │  write(1, ...)   │ ───────────► │   (reads pipe, parses lines)│
  │  write(2, ...)   │   pipe       │            │                │
  └──────────────────┘              │            ▼                │
                                    │   ┌── mode: blocking ──┐    │      json-file ─► /var/lib/docker/
   app file logs                    │   │   (default)        │    │                    containers/<id>/<id>-json.log
   /var/log/app.log  ✗ not captured │   ├── mode: non-blocking    │      local     ─► .../local-logs/container.log
   (unless symlinked to /dev/stdout)│   │   ring buffer       │    │      journald  ─► systemd journal
                                    │   │   max-buffer-size   │    │      syslog    ─► syslog server (udp/tcp/tls)
                                    │   └─────────┬──────────┘    │      fluentd   ─► Fluentd / Fluent Bit
                                    │             ▼               │      gelf      ─► Graylog / Logstash
                                    │      LOG DRIVER  ───────────┼────► awslogs   ─► CloudWatch Logs
                                    │             │               │      splunk    ─► Splunk HEC
                                    │   dual-logging cache (local)│      none      ─► (discarded)
                                    │             │               │
                                    └─────────────┼───────────────┘
                                                  ▼
                                      docker logs  (reads driver, or local cache
                                                    for remote-only drivers)

  Rotation (json-file / local):  file ──full at max-size──► file.1 ──► file.2 ... (max-file copies, oldest deleted)
```

- Logs are stored per container and removed when the container is removed (`docker rm`).
- A driver is chosen at container **creation**; changing the daemon default affects only containers created afterward.
- `docker logs` shows both stdout and stderr, tagged by stream internally; with `-t` (TTY allocated) the two streams are merged.
- Lines longer than 16 KiB are split into partial messages by the daemon and reassembled by readers that support it.

## 5. Hands-On

### 5.1 Reading Logs

```bash
docker run -d --name ticker alpine:3.20 sh -c 'i=0; while true; do i=$((i+1)); echo "tick $i"; echo "warn $i" >&2; sleep 1; done'
docker logs ticker | tail -4
docker logs --tail 3 -t ticker
docker logs --since 10s ticker | wc -l
docker logs -f --tail 0 ticker
```

```text
tick 27
warn 27
tick 28
warn 28
2026-10-06T10:14:09.402Z tick 31
2026-10-06T10:14:09.402Z warn 31
2026-10-06T10:14:10.403Z tick 32
20
tick 34
warn 34
^C
```

Options worth knowing: `-f` follow, `--tail N` last N lines, `--since`/`--until` (relative like `10m` or absolute timestamps), `-t` add timestamps, `--details` show extra attributes from `--log-opt labels/env`. Ctrl-C ends `docker logs -f` without affecting the container (unlike `attach`, [§28](Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)). Separate streams in a script with `docker logs ticker 2>err.txt >out.txt`.

### 5.2 Checking the Current Driver and Where Files Live

```bash
docker info --format '{{.LoggingDriver}}'
docker inspect ticker --format '{{.HostConfig.LogConfig.Type}} {{json .HostConfig.LogConfig.Config}}'
docker inspect ticker --format '{{.LogPath}}'
```

```text
json-file
json-file {}
/var/lib/docker/containers/9d3b7c1a.../9d3b7c1a...-json.log
```

```bash
# On a Linux host (or inside the Docker Desktop VM), the raw file:
sudo tail -2 /var/lib/docker/containers/9d3b7c1a.../9d3b7c1a...-json.log
```

```text
{"log":"tick 41\n","stream":"stdout","time":"2026-10-06T10:14:19.404118Z"}
{"log":"warn 41\n","stream":"stderr","time":"2026-10-06T10:14:19.404191Z"}
```

An empty config (`{}`) means no `max-size`: the file grows without bound. On Docker Desktop for Windows or macOS these paths are inside the VM, not on your host file system.

### 5.3 Rotation with json-file

```bash
docker run -d --name capped \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 --log-opt compress=true \
  alpine:3.20 sh -c 'while true; do echo "$(date) filler line filler line filler line"; done'

docker inspect capped --format '{{json .HostConfig.LogConfig}}'
sudo ls -lh $(dirname $(docker inspect capped --format '{{.LogPath}}'))
```

```text
{"Type":"json-file","Config":{"compress":"true","max-file":"3","max-size":"10m"}}
-rw-r----- 1 root root 8.2M ...-json.log
-rw-r----- 1 root root 10M  ...-json.log.1
-rw-r----- 1 root root 1.1M ...-json.log.2.gz
```

When the active file reaches `max-size` it is renamed to `.1`; older files shift up; the oldest beyond `max-file` is deleted. Total on-disk budget is roughly `max-size x max-file`. Rotation drops history, so ship logs elsewhere if you need retention.

### 5.4 The local Driver (Recommended Default)

```json
{
  "log-driver": "local",
  "log-opts": { "max-size": "20m", "max-file": "5" }
}
```

```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{ "log-driver": "local", "log-opts": { "max-size": "20m", "max-file": "5" } }
EOF
sudo systemctl restart docker           # existing containers keep their old driver
docker run -d --name loc alpine:3.20 echo hello
docker inspect loc --format '{{.HostConfig.LogConfig.Type}} {{.LogPath}}'
```

```text
local /var/lib/docker/containers/c41e.../local-logs/container.log
```

`local` uses a compact binary format with compression and rotation on by default (`max-size` 20m, `max-file` 5 even if you set nothing). It is read only by Docker; for external tools use `json-file` or ship to a remote driver. A daemon restart is needed for `daemon.json` changes, and `live-restore` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) can keep containers running meanwhile. Note: `docker info` may still show the old default until restart completes.

### 5.5 Sending Logs to syslog or journald

```bash
docker run -d --name sl --log-driver syslog \
  --log-opt syslog-address=udp://192.0.2.10:514 --log-opt tag="{{.Name}}/{{.ImageName}}" \
  nginx:1.27

docker run -d --name jd --log-driver journald --log-opt tag=web nginx:1.27
journalctl CONTAINER_NAME=jd -n 3 --no-pager
docker logs jd | tail -2
```

```text
Oct 06 10:20:01 host web[2310]: 172.17.0.1 - - [06/Oct/2026:10:20:01 +0000] "GET / HTTP/1.1" 200 615
```

`journald` stores container metadata as journal fields (`CONTAINER_NAME`, `CONTAINER_ID`, `IMAGE_NAME`), so `journalctl` can filter on them. `docker logs` works with `journald`. The `tag` option accepts Go templates such as `{{.Name}}`, `{{.ID}}`, `{{.ImageName}}`.

### 5.6 Fluentd, GELF and awslogs

```bash
docker run -d --log-driver fluentd \
  --log-opt fluentd-address=fluentd.internal:24224 \
  --log-opt tag="docker.{{.Name}}" --log-opt fluentd-async=true \
  --name api myorg/api:1.4.2

docker run -d --log-driver gelf \
  --log-opt gelf-address=udp://graylog.internal:12201 --name gl myorg/api:1.4.2

docker run -d --log-driver awslogs \
  --log-opt awslogs-region=eu-west-1 --log-opt awslogs-group=/docker/api \
  --log-opt awslogs-stream=api-1 --log-opt awslogs-create-group=true \
  --name aw myorg/api:1.4.2
```

`fluentd` requires the Fluentd/Fluent Bit endpoint to be reachable at container start unless `fluentd-async=true` is set; without it, the container fails to start if the endpoint is down. `awslogs` needs AWS credentials available to the **daemon** (instance role or the daemon's environment) and IAM permissions `logs:CreateLogStream` and `logs:PutLogEvents` (plus `logs:CreateLogGroup` when `awslogs-create-group=true`).

### 5.7 Dual Logging: docker logs with a Remote Driver

```bash
docker run -d --name remote-ok --log-driver gelf \
  --log-opt gelf-address=udp://graylog.internal:12201 alpine:3.20 sh -c 'echo hi; sleep 600'
docker logs remote-ok
```

```text
hi
```

On Engine 20.10 and later, `docker logs` works even though `gelf` cannot be read back, because the daemon also writes a local `local`-format cache. Tune with `--log-opt cache-disabled=false|true`, `cache-max-size` (default 20m), `cache-max-file` (default 5), `cache-compress`. Disable the cache (`cache-disabled=true`) to avoid the extra disk use when `docker logs` is not needed.

### 5.8 Blocking vs Non-Blocking Mode

```bash
docker run -d --name nb \
  --log-driver syslog --log-opt syslog-address=tcp://192.0.2.99:514 \
  --log-opt mode=non-blocking --log-opt max-buffer-size=4m \
  myorg/api:1.4.2
```

```text
# blocking (default): app write() waits for the driver; unreachable TCP log server stalls the app
# non-blocking: write() returns at once; if the 4m ring buffer fills, oldest messages are DROPPED
```

Blocking guarantees delivery order and completeness but couples application availability to the logging backend. Non-blocking keeps the app responsive and accepts possible loss. The default `max-buffer-size` is 1m. Daemon warnings such as `Dropped N messages` show up in the daemon log when the buffer overflows.

### 5.9 Per-Container Override and Compose

```yaml
# compose.yaml
services:
  api:
    image: myorg/api:1.4.2
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
        labels: "env,team"
    labels:
      env: prod
      team: payments
```

```bash
docker compose up -d
docker inspect api-1 --format '{{json .HostConfig.LogConfig}}' 2>/dev/null || docker compose logs -f --tail 20 api
```

Compose applies the same options per service. `labels` and `env` log-opts add selected container labels or environment variables to each record (visible with `docker logs --details` or in the json-file `attrs` field).

### 5.10 Making Application Log Files Visible

```dockerfile
FROM nginx:1.27
# official image already does this:
RUN ln -sf /dev/stdout /var/log/nginx/access.log \
 && ln -sf /dev/stderr /var/log/nginx/error.log
```

For software that insists on a file, symlink it to `/dev/stdout` or `/dev/stderr`, or configure it to log to the console. If a file really is required, mount a volume and ship it with a sidecar.

### 5.11 Truncating and Recovering Disk Space

```bash
# Find the biggest json logs (Linux host)
sudo du -ah /var/lib/docker/containers/ | grep -- '-json.log$' | sort -rh | head -3

# Emergency: truncate in place (does not require stopping the container)
sudo truncate -s 0 "$(docker inspect --format '{{.LogPath}}' ticker)"
```

Truncating is a stopgap; the durable fix is `max-size`/`max-file` or switching to `local`. Do not delete the file out from under a running container: the daemon keeps its file descriptor open and the space is not freed.

## 6. Production Usage Notes

- **Set daemon-wide defaults on every host** (`local` or `json-file` with `max-size`/`max-file`) so a forgotten flag cannot fill the disk.
- **Centralize:** forward logs from the host with a node agent (Fluent Bit, Vector, Promtail, CloudWatch agent) reading the json-file/journal output, or use a remote driver. Agents reading files keep the application decoupled from backend outages; drivers are simpler but couple lifecycle to the destination.
- **Structured logging:** emit one JSON object per line from the application; json-file wraps each line, but collectors can parse the inner JSON. Include timestamp, level, request/trace IDs.
- **Mode choice:** use non-blocking with an adequately sized buffer for latency-sensitive services where a lost line is acceptable; keep blocking where audit completeness matters and the backend is highly available.
- **`docker logs` works with `local`, `json-file`, `journald`** and (via dual logging) the rest, but `docker service logs` and Kubernetes (`kubectl logs` reads the node's container log files through the CRI, [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)) have their own behavior and rotation settings.
- **Daemon and container logs are different:** the Docker daemon's own log is in `journalctl -u docker` (Linux) or the Docker Desktop diagnostics; engine problems with log drivers appear there.
- **Capacity planning:** budget `max-size x max-file x containers` per host, plus the dual-logging cache (default up to 100 MB per container for remote drivers).
- **Cost control:** verbose debug logging at scale is expensive in CloudWatch/Splunk; filter at the agent and set log levels via environment.

## 7. Security Considerations

- **Logs often contain secrets and personal data** (tokens in URLs, passwords in debug output, PII). Redact at the source, restrict who can run `docker logs`, and apply retention limits.
- **File permissions:** json-file logs under `/var/lib/docker/containers` are root-only (`0640`); granting broad read access defeats the control. Anyone in the `docker` group can read all logs through `docker logs`.
- **Log injection:** an attacker who controls logged input can forge lines (newline injection). Log structured JSON and encode untrusted values.
- **Transport:** syslog over UDP and plain GELF are unauthenticated and unencrypted. Use TLS (`tcp+tls://` for syslog, the Fluent forward protocol with TLS) or an agent in a trusted network.
- **Daemon credentials:** `awslogs` and `splunk` use daemon-level credentials (instance role, token in log-opts). Tokens in `--log-opt` appear in `docker inspect`, so prefer instance roles and minimal IAM policies.
- **Denial of service:** unbounded logs fill disks; a blocking driver with an unreachable endpoint can hang applications. Rotate and choose the mode deliberately.
- **Integrity and retention:** local files are mutable by root; ship to append-only or write-once storage when auditability is required.
- **`none` driver** disables logging (and `docker logs` fails), which may violate audit requirements and hides incident evidence.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Host disk full, large `*-json.log` | json-file default has no `max-size` | Set `log-opts` in `daemon.json`, recreate containers; truncate as a stopgap |
| Changed `daemon.json` but old containers still unbounded | Driver and options fixed at container creation | Recreate the containers after the daemon restart |
| `docker logs` shows nothing | App logs to a file, not stdout/stderr | Symlink to `/dev/stdout`, or configure console logging |
| `configured logging driver does not support reading` | Pre-20.10 engine, or `cache-disabled=true` with a remote driver | Upgrade, enable dual logging, or read at the destination |
| Container fails to start: `failed to initialize logging driver` | Fluentd/GELF/syslog TCP endpoint unreachable at start | Fix connectivity, use `fluentd-async=true`, or switch to a local driver plus agent |
| App latency spikes or hangs | Blocking mode with a slow or down backend | Use `mode=non-blocking` with a buffer, or an agent-based design |
| Missing log lines at the destination | Non-blocking buffer overflow, UDP loss | Increase `max-buffer-size`, use TCP/TLS, or switch to blocking |
| Garbled or interleaved stdout and stderr | TTY (`-t`) merges streams | Run without `-t`, or accept merged output |
| `awslogs` errors: `AccessDeniedException` / `NoCredentialProviders` | Daemon lacks AWS credentials or IAM permissions | Attach an instance role to the host/daemon, grant `PutLogEvents` and `CreateLogStream` |
| `docker logs -f` exits when the container restarts | Stream ends with the container process | Re-run with `-f --since`, or use a collector that follows by container ID |
| Timestamps in the wrong timezone | Application time versus Docker UTC | Docker `-t` is UTC (RFC3339Nano); set app TZ or rely on Docker timestamps |
| Very long lines appear split | 16 KiB partial-message splitting | Use readers that rejoin partials, or keep lines small |

## 9. Best Practices

- Log to stdout/stderr, one event per line, preferably JSON.
- Always bound local logs: `local` driver defaults, or json-file with `max-size` and `max-file`.
- Set host-wide defaults in `daemon.json` and verify them with `docker info` and `docker inspect`.
- Prefer node-level collection agents for central shipping; use remote drivers only when you accept the coupling.
- Choose blocking versus non-blocking consciously and test behavior with the backend down.
- Include correlation IDs and levels; keep secrets and PII out of logs.
- Use `--tail` and `--since` rather than dumping an entire history; add `-t` when correlating across containers.
- Add `labels`/`env` log-opts or `tag` templates so records are attributable to a service and version.
- Rehearse log-driver failure: bring the destination down and confirm containers still start and run.
- Monitor disk usage under `/var/lib/docker` and alert before it fills.

## 10. Common Anti-Patterns / Mistakes

- Leaving the default `json-file` with no rotation on long-lived hosts.
- Writing logs to files inside the container's writable layer and expecting `docker logs` to show them.
- Running a syslog daemon or `cron` + logrotate inside each container.
- Using `docker logs` as the retention strategy; logs vanish with `docker rm`.
- Setting a blocking TCP driver against a single, non-redundant log server.
- Deleting (`rm`) a huge log file instead of truncating it, leaving the space reserved by the open descriptor.
- Using the `none` driver to "save disk" and losing all diagnostic evidence.
- Putting API keys in `--log-opt` values where `docker inspect` reveals them.
- Logging at debug level in production without volume budgeting.
- Assuming a daemon-level change retroactively updates existing containers.

## 11. Interview Questions

**🎯 Beginner:** _"A container exited immediately. How do you find out why, and how can you watch a running container's output live?"_
**Model answer:** Run `docker logs NAME` (works on stopped containers too, as long as the container has not been removed) to see its stdout and stderr, and check `docker ps -a` for the exit code. For live output use `docker logs -f NAME`, optionally with `--tail 50` and `-t` for timestamps; `--since 10m` limits the window. This works because Docker captures the main process's stdout and stderr and stores them via the logging driver, by default json-file. If nothing appears, the application is probably writing to a file instead of the console.
_What the interviewer is probing for:_ Basic `docker logs` usage and the stdout/stderr capture model.

**🎯 Intermediate:** _"Your Docker hosts keep running out of disk and the culprit is `/var/lib/docker/containers/*/*-json.log`. Explain the cause and the permanent fix, including why changing the config doesn't help existing containers."_
**Model answer:** The default `json-file` driver does not rotate: without `max-size` and `max-file` each container's log file grows forever. The permanent fix is to set `log-driver` and `log-opts` in `/etc/docker/daemon.json` (for example the `local` driver, or json-file with `max-size=10m` and `max-file=3`), restart the daemon, and then recreate existing containers, because logging configuration is fixed when the container is created. As an emergency measure you can `truncate -s 0` the file without stopping the container; deleting it does not free space while the daemon holds the file descriptor open. Add an agent or remote driver so history is retained elsewhere, and alert on disk usage.
_What the interviewer is probing for:_ Knowing the default-unbounded trap, where configuration is applied, and safe emergency handling.

**🎯 Senior:** _"After enabling the fluentd log driver, your latency-sensitive API occasionally stalls for seconds when the log aggregator is restarted. Explain what is happening and design alternatives, including trade-offs."_
**Model answer:** The default delivery mode is blocking, so when the driver's connection to Fluentd stalls, the container's `write()` to stdout waits and the application thread blocks. Options: set `mode=non-blocking` with a larger `max-buffer-size` (default 1 MB) so writes return immediately, at the cost of dropped messages if the buffer overflows; use `fluentd-async=true` so startup and reconnection do not block; or remove the driver coupling by keeping the local driver (bounded rotation) and running a node-level agent (Fluent Bit) that tails the files and buffers to disk with retries, which survives aggregator outages with no application impact. Trade-offs are completeness versus availability and operational complexity of running agents. I'd test by taking the aggregator down in staging and watching request latency, dropped-message warnings in the daemon log, and agent backlog.
_What the interviewer is probing for:_ Blocking versus non-blocking semantics, backpressure, and the driver-versus-agent architecture trade-off.

**🎯 Architect:** _"Design the logging architecture for 400 hosts running Docker (some Kubernetes) with compliance requirements: tamper-evident retention for 1 year, searchable within seconds, and a hard guarantee that logging never takes down workloads."_
**Model answer:** Standardize stdout/stderr JSON logging with a mandatory schema (timestamp, level, service, version, trace ID, no PII or secrets). On every host set a bounded `local` driver in `daemon.json` so workloads are decoupled from the pipeline and disks are protected; deploy a hardened node agent (Fluent Bit or Vector) as a DaemonSet or systemd service that reads container logs, enriches with metadata, redacts known sensitive patterns, buffers on disk, and forwards over TLS with retries and backpressure to a regional aggregation tier (Kafka or Kinesis). From there fan out to a search store (OpenSearch/Loki/CloudWatch) for hot queries and to object storage with Object Lock/WORM for the one-year tamper-evident archive, with hashing or signed manifests. Use RBAC so access to logs is least-privilege and audited, ship `docker events` and daemon audit logs too, set per-service sampling and rate limits for cost, alert on agent lag and dropped logs, and run regular failure-injection tests proving workloads keep running when any pipeline stage is down. Avoid blocking remote drivers in the data path for the "never takes down workloads" requirement.
_What the interviewer is probing for:_ Decoupling, buffering, compliance storage, security, and cost and failure-mode thinking at fleet scale.

## 12. Common Misconceptions

- "`docker logs` shows everything the app wrote." It shows only stdout and stderr, not files in the container.
- "Logs persist after `docker rm`." Container logs are deleted with the container (for local file drivers).
- "json-file rotates by default." It does not; `local` does.
- "Changing `daemon.json` updates running containers." It applies to newly created containers only.
- "Remote log drivers break `docker logs`." Since Engine 20.10, dual logging keeps a local cache (unless disabled).
- "Non-blocking mode never loses logs." It drops messages when the buffer fills.
- "`docker logs -f` stops the container on Ctrl-C." It only stops following.
- "`none` driver saves nothing important." It removes your diagnostic trail.

## 13. 🔑 Key Takeaways

- Docker captures stdout/stderr; `docker logs` reads them (`-f`, `--tail`, `--since`, `-t`).
- Default `json-file` is unbounded: set `max-size` and `max-file`, or use the rotating `local` driver.
- Drivers: `local`, `json-file`, `journald`, `syslog`, `fluentd`, `gelf`, `awslogs`, `splunk`, `none`; choose per host or per container.
- Dual logging lets `docker logs` work with remote-only drivers (Engine 20.10+).
- Blocking mode risks stalls; non-blocking risks drops; agent-based shipping avoids the trade-off.
- Driver settings are fixed at container creation; recreate containers after changing defaults.
- Treat logs as sensitive data: redact, restrict access, encrypt transport, set retention.

## 14. Related Concepts & What's Next

Related: `docker run` flags ([§26](Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), lifecycle ([§27](Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), exec and attach ([§28](Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), PID 1 and entrypoints ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), engine architecture ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). Next, [§30](Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md) covers copying files with `docker cp` and other data-exchange patterns, including how to retrieve log files and other artifacts that the stdout-only logging model does not capture.

**Next Section:** [§30](Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md) — `Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md`
