# Section 87 (Part 12): Monitoring: cAdvisor, Prometheus, and Container Metrics

## 1. Definition

**Plain language:** Container monitoring means continuously collecting numbers (CPU, memory, network, disk, restarts, health) about every container, storing them over time, and alerting when they drift from normal. Logs tell you *what happened*; metrics tell you *how much, how fast, and whether it is getting worse*.

**Precise definition:** On a Docker host the raw numbers come from the kernel's cgroup accounting files ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)) and from the Docker Engine API. A **collector** reads them and exposes them in a scrapeable format. The standard open-source stack is:

- **cAdvisor** (Container Advisor, Google): a daemon that reads cgroup and `/proc` data for every container on the host and exposes per-container metrics at `/metrics` in Prometheus text format.
- **Docker Engine metrics endpoint:** `dockerd` itself can expose daemon-level metrics (container counts by state, image pulls, builder activity) when `metrics-addr` is set in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **node_exporter:** host-level metrics (CPU, memory, disks, filesystems, network) that cAdvisor does not cover.
- **Prometheus:** a time-series database that *pulls* (scrapes) targets on an interval, evaluates alert rules, and answers PromQL queries.
- **Alertmanager** routes alerts; **Grafana** visualizes.

> 💡 **Tip:** `docker stats` is a live viewer, not monitoring. It keeps no history, raises no alerts, and shows nothing after a container dies. Use it for a quick look, and use the stack above for everything else.

## 2. Why This Matters

- Without history you cannot answer "was it slow before the deploy?" or "does memory grow by 5 MB per hour?"
- A container killed by the OOM killer ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) leaves only an exit code 137; metrics show the climb that preceded it.
- CPU throttling from `--cpus` limits is invisible in `docker stats` yet is a top cause of latency spikes. Only cgroup throttle counters expose it.
- Capacity planning, right-sizing limits ([§89](Section-89-Part12-Resource-Management-at-Scale.md)) and SLO alerting all need per-container series.
- Monitoring is the third observability pillar next to logs ([§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)) and traces, and it feeds self-healing decisions ([§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)).

## 3. Prerequisites and Dependencies

Requires understanding of cgroups and what they count ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), resource limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), Compose ([§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), user-defined networks and DNS ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)), and health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)). Basic PromQL helps: `rate()`, `sum by()`, and label matching.

## 4. Architecture / Conceptual Diagram

```text
 Docker host
 ┌───────────────────────────────────────────────────────────────────────┐
 │  /sys/fs/cgroup/system.slice/docker-<id>.scope/  (cpu.stat, memory.*) │
 │            │ read                                                     │
 │            ▼                                                          │
 │  ┌───────────────┐   ┌────────────────┐   ┌────────────────────────┐  │
 │  │   cAdvisor    │   │ node_exporter  │   │ dockerd :9323/metrics  │  │
 │  │ :8080/metrics │   │ :9100/metrics  │   │ (metrics-addr)         │  │
 │  └──────┬────────┘   └───────┬────────┘   └───────────┬────────────┘  │
 │         │   container_*      │ node_*                 │ engine_*      │
 └─────────┼────────────────────┼────────────────────────┼───────────────┘
           │                    │       HTTP GET (pull)  │
           └────────────┬───────┴────────────────────────┘
                        ▼
               ┌──────────────────┐  rules   ┌───────────────┐   ┌───────┐
               │   Prometheus     ├─────────►│ Alertmanager  ├──►│ Slack │
               │ TSDB + PromQL    │          └───────────────┘   │ Pager │
               └────────┬─────────┘                              └───────┘
                        │ PromQL
                        ▼
                  ┌──────────┐
                  │ Grafana  │
                  └──────────┘
```

- **Pull model:** Prometheus initiates scrapes, so a dead target is itself a signal (`up == 0`).
- **Labels, not names:** cAdvisor labels series with `name`, `image`, and, with Compose, `container_label_com_docker_compose_service`.
- **Cardinality:** one series per metric per container; ephemeral containers create new series on every restart, so churn drives Prometheus memory.

## 5. Hands-On

### 5.1 Quick Look: `docker stats` and the Engine API

```bash
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.PIDs}}'
docker system df
```

```text
NAME     CPU %   MEM USAGE / LIMIT    MEM %   NET I/O          PIDS
web      0.12%   34.5MiB / 256MiB     13.5%   1.2kB / 0B       5
db       1.80%   210MiB / 1GiB        20.5%   8.4kB / 3.1kB    12
```

`MEM USAGE` here already subtracts page cache (inactive file), which is closer to what the OOM killer considers than raw usage.

### 5.2 Enable the Engine Metrics Endpoint

```json
{
  "metrics-addr": "127.0.0.1:9323"
}
```

```bash
sudo systemctl restart docker
curl -s http://127.0.0.1:9323/metrics | grep -E '^engine_daemon_container_states_containers'
```

```text
engine_daemon_container_states_containers{state="paused"} 0
engine_daemon_container_states_containers{state="running"} 2
engine_daemon_container_states_containers{state="stopped"} 1
```

Bind to loopback or a private interface only; the endpoint is unauthenticated. A restart of `dockerd` restarts containers unless `live-restore` is enabled.

### 5.3 A Complete Compose Monitoring Stack

```yaml
# compose.monitoring.yaml
services:
  cadvisor:
    image: ghcr.io/google/cadvisor:v0.49.1   # pin; check the current release
    container_name: cadvisor
    restart: unless-stopped
    command:
      - --docker_only=true
      - --housekeeping_interval=15s
      - --store_container_labels=false
      - --whitelisted_container_labels=com.docker.compose.service
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    devices:
      - /dev/kmsg
    networks: [monitoring]

  prometheus:
    image: prom/prometheus:v2.55.1
    restart: unless-stopped
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=15d
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./alerts.yml:/etc/prometheus/alerts.yml:ro
      - prom-data:/prometheus
    ports:
      - "127.0.0.1:9090:9090"
    networks: [monitoring]

  grafana:
    image: grafana/grafana:11.3.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    networks: [monitoring]

networks:
  monitoring:
volumes:
  prom-data:
  grafana-data:
```

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
rule_files:
  - /etc/prometheus/alerts.yml
scrape_configs:
  - job_name: cadvisor
    static_configs: [{ targets: ["cadvisor:8080"] }]
  - job_name: docker-engine
    static_configs: [{ targets: ["host.docker.internal:9323"] }]
```

For the `docker-engine` job, the Prometheus service needs `extra_hosts: ["host.docker.internal:host-gateway"]` and the daemon must listen on an address reachable from the bridge (for example the bridge gateway IP) rather than only `127.0.0.1`. Docker Desktop resolves `host.docker.internal` automatically.

```bash
docker compose -f compose.monitoring.yaml up -d
curl -s localhost:9090/api/v1/targets | grep -o '"health":"[a-z]*"'
```

```text
"health":"up"
"health":"up"
"health":"up"
```

### 5.4 The Metrics That Matter (PromQL)

```text
# CPU cores used per container (5m rate of cumulative CPU seconds)
sum by (name) (rate(container_cpu_usage_seconds_total{name!=""}[5m]))

# Working-set memory: what the kernel will not easily reclaim; compare to the limit
container_memory_working_set_bytes{name!=""}

# Memory as a fraction of its limit (only containers that have a limit)
container_memory_working_set_bytes{name!=""}
  / (container_spec_memory_limit_bytes{name!=""} > 0)

# CPU throttling ratio: share of scheduling periods in which the container was throttled
rate(container_cpu_cfs_throttled_periods_total{name!=""}[5m])
  / rate(container_cpu_cfs_periods_total{name!=""}[5m])

# Network throughput
sum by (name) (rate(container_network_receive_bytes_total{name!=""}[5m]))

# OOM kills seen by cAdvisor
increase(container_oom_events_total{name!=""}[1h])

# Restart/flap detection: container start time changing
changes(container_start_time_seconds{name!=""}[1h])
```

### 5.5 Alert Rules

```yaml
# alerts.yml
groups:
  - name: containers
    rules:
      - alert: ContainerMemoryNearLimit
        expr: |
          container_memory_working_set_bytes{name!=""}
            / (container_spec_memory_limit_bytes{name!=""} > 0) > 0.90
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.name }} is above 90% of its memory limit"

      - alert: ContainerCpuThrottled
        expr: |
          rate(container_cpu_cfs_throttled_periods_total{name!=""}[5m])
            / rate(container_cpu_cfs_periods_total{name!=""}[5m]) > 0.25
        for: 15m
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.name }} is CPU-throttled in over 25% of periods"

      - alert: ContainerRestartLoop
        expr: changes(container_start_time_seconds{name!=""}[15m]) > 3
        labels: { severity: critical }
        annotations:
          summary: "{{ $labels.name }} restarted more than 3 times in 15 minutes"

      - alert: TargetDown
        expr: up == 0
        for: 2m
        labels: { severity: critical }
```

## 6. Production Usage Notes

- **One cAdvisor per host**, not per container. On Swarm, run it as a `mode: global` service ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)). On Kubernetes the kubelet already embeds cAdvisor ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).
- **Retention and sizing:** Prometheus needs roughly 1-2 bytes per sample after compression; 500 series at a 15 s interval for 15 days is modest, but unbounded label cardinality is not. Drop unneeded cAdvisor metrics with `metric_relabel_configs` or `--disable_metrics`.
- **Housekeeping interval:** cAdvisor's default (1 s internal, per-container) is CPU hungry on hosts with hundreds of containers; set `--housekeeping_interval=15s` and match the scrape interval.
- **Alert on symptoms first** (error rate, latency, saturation) and use container metrics to explain them. A container at 95% CPU is only a problem if users notice.
- **Health and restart counts:** pair metrics with the Docker health state ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)); cAdvisor does not export `healthy/unhealthy`, so export it with a small exporter or probe the application endpoint via the Blackbox exporter.

## 7. Security Considerations

- **cAdvisor needs broad read access** (`/`, `/sys`, `/var/lib/docker`, often `/dev/kmsg`). Mount everything `:ro`, avoid `privileged: true` unless a specific metric needs it, and pin the image by digest.
- **Never mount the Docker socket** into a monitoring container as a convenience. The socket is root on the host ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)); cAdvisor does not need it for cgroup-based metrics.
- **Endpoints are unauthenticated.** cAdvisor's web UI and `/metrics`, the engine `metrics-addr`, node_exporter and Prometheus itself all expose internal topology and image names. Publish only on loopback or a private network, put a reverse proxy with TLS and authentication in front of anything remote, and keep scrape targets off public interfaces.
- **Publishing `-p 8080:8080` binds 0.0.0.0** and bypasses host firewall rules managed by ufw ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)). Prefer `127.0.0.1:` prefixes or internal networks ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| cAdvisor shows only `/` and system slices, no container names | Missing `/var/lib/docker` or `/var/run` mount, or Docker data root is custom | Mount the actual `data-root`; check `docker info -f '{{.DockerRootDir}}'` |
| `name` label empty on all container series | Metrics come from non-Docker cgroups (`name=""`) | Filter with `name!=""` and use `--docker_only=true` |
| cAdvisor logs `failed to get container "/system.slice/..."` | cgroup v2 path or Docker Desktop VM layout differs | Update cAdvisor to a recent release; on Desktop, run it inside the VM context as documented |
| Memory metric far above `docker stats` | `container_memory_usage_bytes` includes page cache | Use `container_memory_working_set_bytes` |
| `container_spec_memory_limit_bytes` is 0 or huge | No limit set | Filter `> 0`, and set limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) |
| Prometheus target `connection refused` | Wrong network, service name, or scrape from a different Compose network | Put both on the same user-defined network; test with `docker exec prometheus wget -qO- cadvisor:8080/metrics` |
| Engine target unreachable from container | `metrics-addr` on 127.0.0.1 only | Bind to the bridge gateway or use `host.docker.internal` plus `host-gateway` |

## 9. Best Practices

- Run cAdvisor, node_exporter and Prometheus themselves with `restart: unless-stopped`, resource limits, pinned versions and named volumes.
- Alert on saturation and errors (memory fraction of limit, throttling ratio, restart rate, `up == 0`), not on raw CPU percentages.
- Use `working_set` for memory, `rate()` over counters, and ratios against limits.
- Set resource limits on application containers; without them, utilization ratios are meaningless.
- Aggregate by Compose service or orchestrator label, not by container ID.
- Put every monitoring port on loopback or a private network with TLS and auth in front.

## 10. Common Anti-Patterns / Mistakes

- Relying on `docker stats` or `docker top` as "monitoring."
- Alerting on CPU > 80% with no `for:` duration, producing flapping pages.
- Using `container_memory_usage_bytes` and panicking about cache.
- Publishing cAdvisor or Prometheus on 0.0.0.0 with no authentication.
- Mounting `/var/run/docker.sock` into a monitoring container "to make it work."
- Dashboards keyed by container name, which break when containers are recreated.
- No alert on the monitoring stack itself (silent failure).

## 11. Interview Questions

**🎯 Beginner:** _"How do you see how much CPU and memory a running container is using, and what are the limits of that tool?"_
**Model answer:** `docker stats` streams live CPU percent, memory usage versus limit, network and block I/O, and PID count per container; `--no-stream` prints one snapshot and `--format` customizes columns. It reads cgroup counters through the Engine API. It has no history, no alerting, no aggregation across hosts, and it loses data when a container exits. For anything beyond a quick look you export the same counters via cAdvisor to Prometheus and graph them in Grafana.
_What the interviewer is probing for:_ Knowing the difference between an ad hoc viewer and a monitoring system.

**🎯 Intermediate:** _"Latency spikes on a service whose `docker stats` CPU shows 30%. What might be happening and how do you prove it?"_
**Model answer:** A container with `--cpus 0.5` uses CFS bandwidth control: it gets a quota per 100 ms period and is paused for the remainder once spent. Bursts can exhaust quota within a period, causing stalls even though the average looks low. cAdvisor exposes `container_cpu_cfs_throttled_periods_total` and `container_cpu_cfs_periods_total`; the ratio of their rates is the fraction of periods throttled, and `container_cpu_cfs_throttled_seconds_total` gives time lost. If it is high I raise or remove the CPU limit (keep `--cpu-shares` or requests for fairness), or make the app use fewer threads. On cgroup v2 the same data is in `cpu.stat` (`nr_throttled`, `throttled_usec`).
_What the interviewer is probing for:_ Understanding cgroup CPU quotas and which metric reveals throttling.

**🎯 Senior:** _"Design the metrics pipeline for 40 Docker hosts running Compose stacks. What do you run, what do you alert on, and what are the failure modes?"_
**Model answer:** Per host: cAdvisor (global, `--docker_only`, 15 s housekeeping), node_exporter, and the engine `metrics-addr` bound privately. Prometheus (or an agent such as Grafana Alloy/Prometheus agent mode) scrapes them with service discovery (file, DNS, or cloud tags), ships by remote write to Thanos, Mimir or a managed backend for retention and HA, with Alertmanager clustered. Rules: `up == 0`, memory working set over 90% of limit for 10 minutes, throttling ratio, restart-loop via `changes(container_start_time_seconds)`, disk and inode usage on `data-root`, and engine container-state anomalies. Failure modes: cardinality blow-up from churn (relabel and drop), single Prometheus as a SPOF (HA pair or remote write), scraping over untrusted networks (mTLS/VPN), and alert fatigue (symptom-based alerts, `for:` durations, inhibition rules). I also run a dead-man's-switch alert so a silent Alertmanager gets noticed.
_What the interviewer is probing for:_ Scalable, secure design plus awareness of cardinality, HA and alert quality.

**🎯 Architect:** _"Leadership wants one view of container health across Docker hosts today and Kubernetes next year without redoing instrumentation. How do you approach it?"_
**Model answer:** Standardize on open formats and conventions rather than a vendor agent: applications expose Prometheus or OpenMetrics `/metrics` and emit OpenTelemetry traces and structured logs; the platform layer collects infrastructure metrics (cAdvisor now, kubelet cAdvisor and kube-state-metrics later) into the same label schema (`service`, `env`, `team`). Use a vendor-neutral collector (OpenTelemetry Collector or Alloy) as the integration point so backends can change, and define SLOs with recording rules that do not depend on where a workload runs. Define a cardinality budget and ownership per team, a retention tier policy (raw 15 days, downsampled for a year), and golden-signal dashboards generated from templates. Migration is then relabeling, not re-instrumenting.
_What the interviewer is probing for:_ Vendor neutrality, label schema design, and planning for the Docker-to-Kubernetes transition ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 12. Common Misconceptions

- "High cache means a memory leak." Page cache is reclaimable; watch the working set.
- "CPU under the limit means no throttling." Throttling is per 100 ms period, not per average.
- "cAdvisor needs the Docker socket." It reads cgroups and `/var/lib/docker`; the socket is optional.
- "Prometheus pushes." It pulls; push requires the Pushgateway, meant for short batch jobs only.
- "Monitoring and health checks are the same." Health checks decide *restart/route*; monitoring records *trends* and pages humans.

## 13. 🔑 Key Takeaways

- Source of truth is cgroup accounting; cAdvisor turns it into Prometheus metrics, `dockerd` adds engine metrics via `metrics-addr`, node_exporter covers the host.
- Use `container_memory_working_set_bytes` and the CFS throttle ratio, not raw usage and average CPU.
- Alert on saturation, restart loops and `up == 0`, with `for:` durations.
- Bind every monitoring endpoint privately, mount read-only, never expose the Docker socket.
- Control cardinality: limit labels, tune housekeeping, expect container churn.
- Set resource limits so utilization ratios mean something.

## 14. Related Concepts & What's Next

Related: cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), resource constraints ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), logging architectures ([§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)), image scanning as the security counterpart to runtime visibility ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)). Next, [§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md) turns these signals into automatic recovery through health checks and restart policies.

**Next Section:** [§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md) — `Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md`
