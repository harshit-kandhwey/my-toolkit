# Section 86 (Part 12): Logging Architectures for Containerized Applications

## 1. Definition

**Plain language:** A container is disposable, so its logs must not live inside it. A logging architecture decides how the text your application prints travels from the container to a durable, searchable place, and what happens to it on the way (buffering, parsing, enrichment, retention, access control).

**Precise definition:** Docker captures whatever the container's main process writes to stdout and stderr. The `containerd-shim`/daemon reads those streams and hands each line to a **logging driver** configured per daemon or per container ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)). Production architectures fall into a few patterns:

1. **Driver-to-backend:** the Docker logging driver ships directly (`fluentd`, `gelf`, `syslog`, `awslogs`, `gcplogs`, `splunk`, `journald`).
2. **Local file plus node agent:** the default `json-file` or `local` driver writes on the host and an agent (Fluent Bit, Vector, Promtail/Alloy, Filebeat) tails the files and forwards.
3. **Sidecar:** a second container shares a volume with the app and ships files the app writes (for legacy apps that log to files).
4. **Application-direct:** the app uses a logging library to send straight to a backend (discouraged except for special cases).

The aggregation tier (Loki, Elasticsearch/OpenSearch, Splunk, CloudWatch, Cloud Logging) stores and indexes the data; visualization and alerting sit on top.

> 💡 **Tip:** The twelve-factor rule still holds: treat logs as an event stream written unbuffered to stdout. Routing is the platform's job, not the application's.

## 2. Why This Matters

- `docker logs` only works while the container exists. Remove the container or lose the host and the logs are gone.
- Unbounded `json-file` logs are one of the most common causes of "disk full" incidents on Docker hosts.
- Incidents are diagnosed across many containers and hosts; without central aggregation and correlation IDs you cannot follow a request.
- Logging drivers can block the application when the backend is slow (blocking delivery mode), converting a logging outage into an application outage.
- Compliance (PCI, HIPAA, SOC 2) needs retention, integrity and access controls on logs.
- Frequent senior-level interview theme: "how do you handle logs for 500 containers?"

## 3. Prerequisites and Dependencies

Read the logging driver mechanics in [§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md) and the daemon configuration in [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md). Understanding of the engine's process model ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), volumes ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)) and Compose ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)) helps. Disk-pressure handling relates to [§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md), and monitoring (metrics rather than logs) continues in [§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md).

## 4. Architecture / Conceptual Diagram

```text
 Docker host
┌─────────────────────────────────────────────────────────────────────────┐
│  ┌────────┐ stdout/stderr                                               │
│  │  app   │─────────┐                                                   │
│  └────────┘         ▼                                                   │
│  ┌────────┐   ┌───────────┐   json-file/local   /var/lib/docker/       │
│  │  web   │──►│ dockerd   │──────────────────►  containers/<id>/*.log  │
│  └────────┘   │ log driver│                            │               │
│               └─────┬─────┘                            │ tail           │
│  ┌────────┐         │ fluentd/gelf/syslog              ▼               │
│  │legacy  │ file    │ (driver ships directly)    ┌────────────┐        │
│  │app     │──┐      │                            │ node agent │        │
│  └────────┘  │      │                            │ Fluent Bit │        │
│       volume ▼      │                            └─────┬──────┘        │
│  ┌────────────┐     │                                  │               │
│  │ sidecar    │─────┼──────────────────────────────────┤               │
│  │ log shipper│     │                                  │               │
│  └────────────┘     │                                  │               │
└─────────────────────┼──────────────────────────────────┼───────────────┘
                      │ TCP/TLS                          │ TCP/TLS, buffered
                      ▼                                  ▼
              ┌───────────────────── Aggregation tier ─────────────────┐
              │ collector / queue ► parse ► enrich ► index/store       │
              │ Loki | OpenSearch | Splunk | CloudWatch | Cloud Logging│
              └──────────────────────────┬─────────────────────────────┘
                                         ▼
                              dashboards, search, alerts, archive (S3)
```

- **Path A (driver direct):** least moving parts, but backend slowness can stall the app (`mode=blocking`, the default) and `docker logs` is limited for some drivers.
- **Path B (agent tailing files):** decouples the app from the backend; the agent buffers and retries. Most common in production.
- **Path C (sidecar):** needed only when the app writes files instead of stdout.
- **Rotation** must exist on the host for path B, otherwise the files grow forever.

## 5. Hands-On

### 5.1 Inspect Where Logs Go and Their Limits

```bash
docker info --format '{{.LoggingDriver}}'
docker inspect web --format '{{.HostConfig.LogConfig.Type}} {{json .HostConfig.LogConfig.Config}}'
docker inspect web --format '{{.LogPath}}'
```

```text
json-file
json-file {"max-file":"3","max-size":"10m"}
/var/lib/docker/containers/9f3c.../9f3c...-json.log
```

If `Config` is `{}`, no rotation is set and the file is unbounded.

### 5.2 Set Safe Daemon-Wide Defaults

```json
{
  "log-driver": "local",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
```

Save as `/etc/docker/daemon.json` and restart `dockerd`; the defaults apply to *new* containers only. The `local` driver uses a compact binary format with rotation on by default (100 MB total by default per container) and works with `docker logs`. `json-file` is fine but needs explicit `max-size`/`max-file`.

### 5.3 Per-Service Logging in Compose (Rotated JSON Files for an Agent)

```yaml
services:
  api:
    image: registry.example.com/shop/api:1.4.2
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
        tag: "{{.Name}}"
        labels: "service,env"
    labels:
      service: api
      env: prod
```

### 5.4 Node Agent: Fluent Bit Tailing Container Logs and Shipping to Loki

```yaml
services:
  fluent-bit:
    image: fluent/fluent-bit:3.1
    volumes:
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - ./fluent-bit.conf:/fluent-bit/etc/fluent-bit.conf:ro
      - fb-state:/state
    restart: unless-stopped
volumes:
  fb-state:
```

```ini
# fluent-bit.conf
[SERVICE]
    Flush        2
    Parsers_File parsers.conf
[INPUT]
    Name         tail
    Path         /var/lib/docker/containers/*/*-json.log
    Parser       docker
    DB           /state/flb.db
    Mem_Buf_Limit 20MB
    Refresh_Interval 10
[FILTER]
    Name         parser
    Match        *
    Key_Name     log
    Parser       json
    Reserve_Data On
[OUTPUT]
    Name         loki
    Match        *
    Host         loki.example.com
    Port         443
    tls          on
    labels       job=docker
```

The read-only mount lets the agent read host log files without write access. `DB` persists file offsets so a restart does not resend or lose lines.

### 5.5 Driver-Direct Shipping (GELF/Fluentd) with Non-Blocking Delivery

```bash
docker run -d --name api \
  --log-driver fluentd \
  --log-opt fluentd-address=fluentd.example.com:24224 \
  --log-opt fluentd-async=true \
  --log-opt tag=docker.{{.Name}} \
  registry.example.com/shop/api:1.4.2
```

```bash
# generic protection against a slow or dead backend for any driver
docker run -d --log-opt mode=non-blocking --log-opt max-buffer-size=4m ...
```

`non-blocking` trades possible log loss under backpressure for application availability. Choose deliberately: audit logs usually prefer blocking, high-volume debug logs prefer non-blocking. Note that with remote drivers, `docker logs` may be unavailable (the `dual logging` cache keeps a local copy for most drivers in Engine 20.10+, with its own `cache-max-size`).

### 5.6 Structured Logging and Correlation IDs

```python
import json, logging, sys, uuid
class J(logging.Formatter):
    def format(self, r):
        return json.dumps({"ts": self.formatTime(r, "%Y-%m-%dT%H:%M:%S%z"),
                           "level": r.levelname, "msg": r.getMessage(),
                           "service": "api", "request_id": getattr(r, "request_id", None)})
h = logging.StreamHandler(sys.stdout); h.setFormatter(J())
logging.basicConfig(level="INFO", handlers=[h])
logging.getLogger().info("order created", extra={"request_id": str(uuid.uuid4())})
```

```text
{"ts": "2026-10-06T10:14:03+0000", "level": "INFO", "msg": "order created", "service": "api", "request_id": "5c1b..."}
```

One JSON object per line is parsed reliably by agents and queried by field. Multi-line stack traces should be single-line JSON fields, or use the agent's multiline parser.

### 5.7 Sidecar for an App That Writes Files

```yaml
services:
  legacy:
    image: legacy-app:2.0            # writes /var/log/app/app.log
    volumes: [applogs:/var/log/app]
  shipper:
    image: busybox:1.36
    command: ["tail", "-F", "/logs/app.log"]   # re-emits to stdout, picked up by the Docker driver
    volumes: [applogs:/logs:ro]
volumes:
  applogs:
```

Simplest sidecar: re-emit the file to stdout so the normal pipeline handles it. Alternative: symlink the file to `/dev/stdout` in the Dockerfile (how the official nginx image works).

### 5.8 Quick Operational Checks

```bash
docker logs --since 10m --tail 200 -t api
docker logs -f api 2>&1 | grep -i error
du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail -5
```

```text
2.1G    /var/lib/docker/containers/7ad1.../7ad1...-json.log
```

A multi-gigabyte log file is the signature of missing rotation.

## 6. Production Usage Notes

- **Default to stdout/stderr** and one agent per host (daemonset equivalent), with rotation configured daemon-wide so it is never forgotten.
- **Pick `local` or `json-file` plus agent** for resilience: the local file is a buffer if the network or backend is down.
- **Label and tag logs** (service, environment, version, image digest, host) at the agent so queries and dashboards are consistent.
- **Cost control:** cardinality is the enemy. Loki labels should be low-cardinality (service, env), with request IDs left in the log body. Sample or drop DEBUG in production, set retention per tier (hot 7-14 days, archive to object storage for compliance).
- **Back-pressure:** configure agent buffers (disk-backed where available), retry with exponential backoff and a drop policy that you chose consciously.
- **Time:** make sure hosts use NTP and logs carry UTC timestamps so cross-host ordering is trustworthy.
- **Correlation:** propagate a request ID (and trace ID, linking with tracing/metrics, see [§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)) through all services.
- **Health of the pipeline itself:** monitor agent restarts, dropped records, queue length and ingest lag; a silent logging outage is discovered at the worst time ([§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)).
- **Swarm and clusters:** `docker service logs` aggregates tasks on Swarm ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)); Kubernetes writes under `/var/log/pods` and uses the same node-agent pattern.
- **Multiple environments:** CI containers' logs ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)) are usually retained in the CI system, not the production stack.

## 7. Security Considerations

- **Never log secrets or personal data:** tokens, passwords, full card numbers, session cookies, PII. Mask at the source and add scrubbing filters at the agent as a second layer ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Log injection:** untrusted input containing newlines or JSON can forge entries; use structured logging that escapes fields.
- **Transport:** use TLS and authentication to the collector; plaintext syslog/GELF over UDP leaks and loses data.
- **Access control:** log stores contain sensitive operational detail. Apply RBAC, per-tenant isolation and audit access.
- **Host exposure:** `/var/lib/docker/containers` is root-owned; an agent mounting it read-only is acceptable, but a log agent with the Docker socket mounted gains root-equivalent control ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)). Prefer file tailing to socket-based collection.
- **Integrity and retention:** ship logs off-host quickly so an attacker who compromises the container or host cannot erase evidence; use write-once storage for audit logs.
- **Disk-fill DoS:** a noisy or malicious container can fill the host disk; rotation limits and `--storage-opt`/quota or dedicated partitions for `/var/lib/docker` contain it ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Host disk 100% full, huge `*-json.log` | No `max-size`/`max-file` set | Set daemon defaults, recreate containers (options apply at creation); truncate with care only after confirming the file |
| `docker logs` prints nothing | App writes to a file, or buffers stdout (Python) | Log to stdout, use `PYTHONUNBUFFERED=1` / flush; sidecar or symlink to `/dev/stdout` |
| `docker logs` errors with a remote driver | Driver does not support reading | Use dual logging cache (default for most drivers), or query the backend |
| App hangs when log backend is down | Driver in blocking mode | `--log-opt mode=non-blocking` plus buffer, or use agent pattern |
| Changed `daemon.json` but old containers keep old settings | Log config is fixed at container creation | Recreate containers |
| Duplicate lines in the backend | Agent offset DB not persisted, or two collectors | Persist the `DB` path on a volume; one collector per file |
| Multi-line stack traces split into many entries | Plain line-based parsing | Use JSON logs or multiline parser rules |
| Missing logs from short-lived containers | Container removed with `--rm` before the agent read the tail | Use driver-direct for batch jobs, or tune agent refresh; ship before exit |
| Timestamps out of order across hosts | Clock skew | NTP/chrony; use event time from the app |
| Loki/Elasticsearch costs explode | High-cardinality labels or verbose DEBUG | Reduce labels, sample, set retention |

## 9. Best Practices

- Write structured (JSON), single-line, UTC-timestamped logs to stdout/stderr.
- Always set rotation (`max-size`, `max-file`) daemon-wide; prefer the `local` driver or `json-file` plus a node agent.
- Ship logs off-host quickly through a buffered agent; do not couple the app to the backend.
- Choose blocking versus non-blocking delivery deliberately, per log criticality.
- Standardize fields: service, env, version, host, request_id, trace_id.
- Keep label cardinality low and set retention tiers.
- Redact secrets and PII at source and again at the agent.
- Monitor the logging pipeline itself.
- Test log loss behavior: stop the backend and confirm the app and agent behave as intended.

## 10. Common Anti-Patterns / Mistakes

- Writing logs into the container's writable layer or a file inside the container and expecting to find them later.
- Leaving the default `json-file` driver with no limits on a production host.
- Running `ssh` into hosts and `grep`-ing `docker logs` across machines as the "aggregation" strategy.
- Mounting `/var/run/docker.sock` into every log collector without considering the privilege it grants.
- Logging full request bodies, headers or tokens.
- Using `syslog` over UDP for important events.
- Putting request IDs or user IDs into Loki labels.
- Running multiple daemons plus a log shipper inside one container with a process manager.
- Forgetting that changing daemon logging defaults does not affect existing containers.

## 11. Interview Questions

**🎯 Beginner:** _"Where do container logs come from, and why should an application write to stdout instead of a log file?"_
**Model answer:** Docker captures the main process's stdout and stderr and passes them to the configured logging driver, by default `json-file` on the host, which `docker logs` reads. Writing to stdout keeps the container stateless, lets the platform route and rotate logs without touching the app, and avoids the writable layer growing. If the app writes to a file, `docker logs` shows nothing and the file disappears with the container unless it is on a volume. Some images symlink the log file to `/dev/stdout` to get the best of both.
_What the interviewer is probing for:_ The stdout model, `docker logs`, and the twelve-factor principle.

**🎯 Intermediate:** _"A production host runs out of disk. `/var/lib/docker/containers` is mostly `*-json.log`. What happened, how do you recover safely, and how do you prevent a recurrence?"_
**Model answer:** The default `json-file` driver has no rotation unless `max-size`/`max-file` are set, so a chatty container grows its log forever. Recover by identifying the offender with `du`, fixing the noisy behavior, and freeing space without breaking the running container, for example truncating the specific file after confirming it is safe, since deleting an open file does not free space until the process closes it. Prevent by setting rotation defaults in `daemon.json` (or using the `local` driver), recreating containers because options apply at creation, shipping logs to a backend so local retention can be short, and alerting on disk usage.
_What the interviewer is probing for:_ Operational experience, creation-time log config, and prevention.

**🎯 Senior:** _"Compare driver-direct shipping (fluentd/gelf) with a node agent tailing files. Which would you choose for a payments platform and why?"_
**Model answer:** Driver-direct has fewer components but couples app availability to the backend in blocking mode, loses logs when the daemon restarts without buffering, and complicates `docker logs`. A node agent tailing local files treats the file as a durable buffer, retries with backoff, handles parsing and enrichment centrally, and survives backend outages. For payments I would use `local` or `json-file` with rotation plus a Fluent Bit or Vector agent with disk-backed buffering and TLS to a collector tier. Audit-grade events would additionally be written to a separate, append-only store, with blocking semantics where loss is unacceptable. Sensitive fields are redacted at source and again in the agent.
_What the interviewer is probing for:_ Trade-offs between coupling, durability and operational simplicity, and compliance awareness.

**🎯 Architect:** _"Design logging for 2,000 containers across 150 hosts and several regions with cost control, multi-tenancy and a 1-year retention requirement."_
**Model answer:** Standardize on stdout JSON logs and a schema of mandatory fields. Each host runs one agent with disk-backed buffers, shipping over TLS to regional collectors (Kafka or a managed queue as a shock absorber) that handle parsing, redaction and routing. Hot storage (Loki or OpenSearch) holds 7-14 days with low-cardinality labels and per-tenant limits and RBAC; everything also streams to object storage in compressed, partitioned form with lifecycle policies for the one-year retention and legal hold. Sampling or dropping DEBUG and rate limits per service control spend, with budgets and dashboards per team. Monitor the pipeline (ingest lag, drops, agent health), keep clocks synchronized, and test failure modes regularly. Correlate with metrics and traces via shared IDs so logs are one pillar of observability, not the only one.
_What the interviewer is probing for:_ End-to-end design: buffering, tiering, tenancy, cost and failure testing.

## 12. Common Misconceptions

- "Docker keeps container logs forever." Logs are removed with the container, and rotation may discard older data sooner.
- "Changing the default log driver updates all containers." Only newly created ones.
- "Centralized logging is just `docker logs` on many hosts." It requires shipping, parsing, indexing and retention.
- "Non-blocking mode is always safer." It can silently drop logs.
- "Logging agents need the Docker socket." Tailing files needs only read access to the log directory.
- "More labels make queries easier." High cardinality makes systems slow and expensive.

## 13. 🔑 Key Takeaways

- Apps write structured logs to stdout/stderr; the platform routes them.
- Configure rotation daemon-wide; options are fixed at container creation.
- Prefer a node agent tailing local files for resilience; use driver-direct deliberately and choose blocking versus non-blocking consciously.
- Keep labels low-cardinality, tag consistently, and carry correlation IDs.
- Protect logs: redact secrets, encrypt transport, restrict access, ship off-host fast.
- Monitor the logging pipeline itself.

## 14. Related Concepts & What's Next

Related: log drivers and `docker logs` ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)), daemon config ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), cleanup and disk usage ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)), secrets handling ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), troubleshooting ([§93](Section-93-Part12-Troubleshooting-Production-Container-Issues.md)). Part 11 ended with CI caching ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)); now that logs flow reliably, [§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md) adds the second observability pillar, metrics, with cAdvisor and Prometheus.

**Next Section:** [§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md) — `Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md`
