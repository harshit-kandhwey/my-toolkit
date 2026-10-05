# Section 97 (Part 13): When Docker Is the Wrong Tool

## 1. Definition

**Plain language:** Containers are excellent for packaging and running stateless Linux services, but they are not a universal answer. Docker is the wrong tool when the workload needs stronger isolation than a shared kernel gives, a different operating system, direct hardware access, extreme I/O or latency determinism, or when the operational overhead exceeds the benefit.

**Precise definition:** A container is a set of Linux processes constrained by namespaces, cgroups, capabilities and seccomp, sharing the host kernel ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md), [§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)). Every limitation of that model, namely the shared kernel, the Linux-only ABI, the layered copy-on-write filesystem, the single-host default scope and the daemon-centric tooling, defines a boundary past which an alternative (VMs, microVMs, serverless, native packages, Kubernetes, unikernels) fits better.

> 💡 **Tip:** Before containerizing, name the problem you expect Docker to solve (reproducible packaging, density, deployment speed). If you cannot, you probably do not need it.

## 2. Why This Matters

- Choosing containers for the wrong workload produces slow, fragile or insecure systems that are then blamed on the tool.
- Architects are expected to justify technology choices, including "no container" and "not Docker".
- Many incidents (data loss, noisy neighbors, escapes) trace back to forcing a workload into a model it was not designed for.
- Interview answers that include trade-offs and counterexamples signal seniority far more than feature recitation.

## 3. Prerequisites and Dependencies

Requires the container-versus-VM model ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)), namespaces and cgroups ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), the security model ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), storage options ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md), [§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md), [§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md)), and the runtime comparison in [§96](Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md).

## 4. Architecture / Conceptual Diagram

```text
   Isolation strength (weakest ──────────────────────────► strongest)

   plain process   container          sandboxed container    microVM          full VM
   ┌─────────┐    ┌───────────┐      ┌────────────────┐    ┌───────────┐    ┌──────────┐
   │ app     │    │ app       │      │ app            │    │ app       │    │ app      │
   ├─────────┤    ├───────────┤      ├────────────────┤    ├───────────┤    ├──────────┤
   │ host    │    │ host      │      │ gVisor (user-  │    │ guest     │    │ guest OS │
   │ kernel  │    │ kernel    │      │ space kernel)  │    │ kernel    │    │ kernel   │
   └─────────┘    └───────────┘      │ host kernel    │    │ Firecracker│   │ hypervisor│
                  runc               └────────────────┘    │ / Kata    │    └──────────┘
                                     runsc                 └───────────┘
   Syscall surface exposed to host kernel:   ~350 ─► ~350 filtered ─► ~70 (sentry) ─► ~0 (VMM boundary)

   Decision flow
   ┌────────────────────────────────┐
   │ Need Linux userland on Linux   │── no ──► Windows/macOS-native app, VM, or Windows containers
   │ kernel features you can share? │
   └───────────────┬────────────────┘
                   │ yes
                   ▼
   ┌────────────────────────────────┐
   │ Runs untrusted/multi-tenant    │── yes ─► gVisor / Kata / Firecracker / dedicated VM
   │ code?                          │
   └───────────────┬────────────────┘
                   │ no
                   ▼
   ┌────────────────────────────────┐
   │ Stateful, I/O- or latency-     │── yes ─► managed service, VM or bare metal; containers
   │ critical, needs raw devices?   │          only with care (volumes, host networking)
   └───────────────┬────────────────┘
                   │ no
                   ▼
   ┌────────────────────────────────┐
   │ Many services, many hosts,     │── yes ─► Kubernetes or managed container service
   │ HA and autoscaling needed?     │          (Docker alone is not an orchestrator)
   └───────────────┬────────────────┘
                   │ no
                   ▼
              Docker (Compose on one host) is a good fit
```

- **The kernel is shared.** A kernel vulnerability, a mis-set privilege or a missing limit affects every container on the host.
- **The ABI is Linux.** On macOS and Windows, Docker Desktop silently runs a Linux VM; the container is never "native".
- **Scope is one host.** Docker Engine does not schedule, self-heal across nodes or autoscale; those are orchestration problems ([§99](Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 5. Hands-On

### 5.1 Prove the Kernel Is Shared

```bash
uname -r
docker run --rm alpine uname -r
docker run --rm --pid=host alpine ps -e | head -3     # host processes visible (lab only)
```

```text
6.8.0-45-generic
6.8.0-45-generic
    1 root     /sbin/init
```

Same kernel string means no separate kernel. A guest that needs a different kernel version or custom modules cannot be a container.

### 5.2 Windows and macOS: The Hidden VM

```bash
docker info --format '{{.OperatingSystem}} | {{.OSType}} | {{.KernelVersion}}'
docker run --rm alpine uname -a
```

```text
Docker Desktop | linux | 6.10.14-linuxkit
Linux 6.10.14-linuxkit ... aarch64 Linux
```

On a Mac the kernel is `linuxkit`, not Darwin. macOS apps, iOS builds and Xcode toolchains cannot run in Linux containers. Windows containers exist for Windows Server workloads, but are a separate ecosystem with large images and version-matching rules.

### 5.3 Observe the Overhead of Bind Mounts on Desktop

```bash
mkdir -p /tmp/iotest && cd /tmp/iotest
time docker run --rm -v "$PWD:/data" alpine sh -c 'for i in $(seq 1 5000); do echo x > /data/f$i; done'
time docker run --rm alpine sh -c 'for i in $(seq 1 5000); do echo x > /tmp/f$i; done'
```

```text
real  0m11.9s      # bind mount through file sharing layer
real  0m0.6s       # container-local overlay
```

Numbers vary widely, but the gap is real on Docker Desktop (virtiofs/gRPC FUSE) and is a reason heavy file-watching builds sometimes belong in a native toolchain or a volume ([§41](../Part5/Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md), [§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md)).

### 5.4 Demonstrate Missing Hardware Access

```bash
docker run --rm alpine ls /dev | head
docker run --rm --device /dev/nvidia0 alpine true          # fails without the driver on the host
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

```text
core  fd  full  mqueue  null  ptmx  pts  random  shm  stderr
docker: Error response from daemon: error gathering device information ... no such file or directory
```

GPUs, USB, serial, real-time clocks and PCI passthrough require host drivers plus the NVIDIA Container Toolkit or `--device` and extra privileges. The more raw hardware you pass through, the more a VM or bare metal install is the honest design.

### 5.5 Test a Sandboxed Runtime for Untrusted Code

```bash
# lab VM with gVisor installed and registered in /etc/docker/daemon.json as runtime "runsc"
docker run --rm --runtime=runsc alpine dmesg | head -3
docker run --rm alpine dmesg | head -3
```

```text
[    0.000000] Starting gVisor...
dmesg: klogctl: Operation not permitted
```

If code from users or third parties must run on your hosts, swap the runtime (gVisor, Kata) or move to microVMs instead of hardening `runc` containers alone ([§60](../Part8/Section-60-Part8-Seccomp-Profiles.md)).

### 5.6 A Stateful Database in a Container: What It Really Costs

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=pw -v pgdata:/var/lib/postgresql/data postgres:16
docker stop -t 2 pg           # short grace period risks unclean shutdown on a busy database
docker volume inspect pgdata --format '{{.Mountpoint}}'
```

A container can host a database, and many teams do so successfully, but you now own volume backup and restore ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)), stop timeouts, upgrade procedures, HA and failover. A managed database (RDS, Cloud SQL) removes all of that for a price. Treat "containerize the database in production" as a decision, not a default.

### 5.7 Single Static Binary: Container Optional

```bash
CGO_ENABLED=0 go build -o app ./cmd/app
scp app server:/usr/local/bin/ && ssh server 'systemctl restart app'
```

A static Go or Rust binary under systemd needs no image, registry, daemon or runtime. Containers still help for uniform deployment, but a team of two with one binary and one server may not need them.

## 6. Production Usage Notes

- **Strong multi-tenancy:** SaaS platforms running customer code, CI for public pull requests and notebook services should use gVisor, Kata or Firecracker; AWS Lambda and Fargate run each tenant in a Firecracker microVM for this reason.
- **Different OS or kernel needs:** kernel modules, custom `sysctl`, eBPF-heavy network appliances, DPDK and real-time workloads belong on VMs or bare metal, or containers with `--privileged`/host networking, which erase most benefits.
- **GUI and desktop apps:** possible with X11/Wayland socket mounts, but fragile; Flatpak, Snap or native packaging fit better.
- **Latency-critical trading and HPC:** CPU pinning, NUMA, huge pages and kernel-bypass networking are achievable, but overlay networking, NAT and cgroup throttling add jitter; bare metal or tuned VMs are typical.
- **Stateful and licensed software:** vendors that do not support containers (some Oracle, SAP, commercial databases) make unsupported deployments an audit and incident risk.
- **Mobile, embedded and edge:** consider whether the device has a kernel with required features (cgroups v2, overlayfs) and enough RAM and storage; small devices may prefer OSTree/Yocto images or Wasm runtimes.
- **Serverless and PaaS:** when a team does not want to operate hosts at all, Cloud Run, Fargate, App Service or Lambda container images remove the need to run a Docker daemon in production.
- **Scale threshold:** beyond a handful of hosts, hand-run Docker plus scripts turns into an accidental orchestrator; move to Kubernetes or a managed service ([§99](Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 7. Security Considerations

- **Containers are not a security boundary against hostile code.** Container escapes (runc CVE-2019-5736 and the 2024 "Leaky Vessels" set) show that a shared kernel is a real attack surface.
- **Privileged or socket-mounted containers** (`--privileged`, `-v /var/run/docker.sock`, `--pid=host`) are effectively root on the host and nullify the isolation that justified using containers ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **Compliance regimes** (PCI, HIPAA, FedRAMP) may mandate hypervisor-level separation between tenants or data classes; document that containers alone do not satisfy it.
- **Secrets and state in images or volumes** are harder to rotate and audit than in a managed secrets service or database ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Kernel patching still matters.** Container image patching does not fix a vulnerable host kernel; managed platforms that patch the kernel for you reduce that burden.
- **Wasm and unikernels** offer smaller attack surfaces for narrow workloads, at the cost of ecosystem maturity.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely mismatch | Alternative |
|---|---|---|
| Builds and tests 5-10x slower on Mac or Windows | Bind mounts through the Desktop VM | Use volumes, sync tools, devcontainers in the VM, or native toolchain |
| `modprobe` or `sysctl` fails in container | Kernel settings are host-owned | Configure on host/VM; use privileged only deliberately |
| Database corruption after node reboot | Short stop timeout, local volume, no backup | Managed DB, or tune `--stop-timeout`, WAL archiving, tested restores |
| Cannot reach GPU or USB device | Missing host drivers/toolkit | NVIDIA Container Toolkit, `--device`, or VM passthrough |
| Noisy-neighbor latency spikes | Shared kernel, CPU throttling | Pin CPUs, dedicated nodes, or VMs ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) |
| Customer code reads other tenants' data | Shared kernel and weak isolation | Sandboxed runtime or per-tenant microVM |
| Docker Compose in production keeps growing scripts | Orchestration gap | Kubernetes or managed container service |
| Windows .NET Framework app will not run | Needs Windows containers or a VM | Windows Server containers or lift-and-shift to VM |

## 9. Best Practices

- Write down the reasons for using containers and revisit them when requirements change.
- Match isolation to trust: first-party code in containers; untrusted code in sandboxed runtimes or VMs.
- Keep stateful systems on managed services unless you have the skills to back up, restore and upgrade them.
- Use VMs or bare metal for kernel-dependent, hardware-bound or ultra-low-latency workloads.
- Prefer managed container platforms when you do not want to operate hosts.
- Benchmark on the target platform (production Linux, not just laptops).
- Keep the packaging portable (OCI images) so you can change the runtime or platform later ([§96](Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md)).
- Avoid `--privileged`; if you need it, ask whether a VM is the honest answer.

## 10. Common Anti-Patterns / Mistakes

- "Containerize everything" regardless of workload, support status or team skills.
- Running multi-tenant untrusted code in plain `runc` containers on shared hosts.
- Using `--privileged`, `--net=host` and device passthrough together, then calling it "a container".
- Production Compose files stretched across many hosts with SSH scripts, instead of a scheduler.
- Putting the production database in a container with a bind mount, no backup and a default stop timeout.
- Benchmarking on Docker Desktop and extrapolating to production.
- Using containers as lightweight VMs: SSH daemons, init systems and long-lived mutable state.
- Treating Docker as a build tool only and adopting its whole runtime stack for no reason.

## 11. Interview Questions

**🎯 Beginner:** _"Name two situations where you would not use a Docker container, and what you would use instead."_
**Model answer:** One is running untrusted or multi-tenant code, because containers share the host kernel and a kernel exploit or misconfiguration compromises everything; I would use a VM, a microVM such as Firecracker, or a sandboxed runtime like gVisor or Kata. Another is software that needs a different operating system or kernel, such as macOS or Windows-native applications or code that loads kernel modules; I would use a VM or bare metal. Other good answers are latency-critical hardware-bound workloads, and a simple static binary on one server where systemd is enough.
_What the interviewer is probing for:_ Understanding that the kernel is shared and what that implies.

**🎯 Intermediate:** _"Your team wants to run the production PostgreSQL in a Docker container on a single VM. What are your concerns, and when is it acceptable?"_
**Model answer:** It works technically, but you take on durable storage, backup and restore, upgrades, HA, failover and monitoring that a managed service gives you. Risks include data loss from an unclean stop (short `docker stop` timeout), a volume that lives on a single disk, and a Compose redeploy that recreates the container with a different config. It is acceptable for dev, test, small internal systems or when compliance or cost rules out managed services, provided there is a named volume or block device with tested backups (base backups plus WAL archiving), a long `--stop-timeout`, pinned versions, resource limits, and a rehearsed restore. For anything with strict RPO/RTO I would recommend managed Postgres or an operator-based HA setup on Kubernetes.
_What the interviewer is probing for:_ Balanced judgment on stateful workloads, with concrete mitigations rather than a blanket yes or no.

**🎯 Senior:** _"A platform lets customers upload code to run in your cluster. A security review says containers are not enough. How do you respond, and what would you propose?"_
**Model answer:** The reviewer is right that runc containers rely on one shared kernel with a very large syscall surface, and several container-escape CVEs have shown it. I would layer defenses and raise the isolation tier. Run customer code in a sandboxed RuntimeClass (gVisor or Kata Containers) on dedicated node pools, or use per-tenant microVMs (Firecracker) if the density and start-time budget allow. Add the baseline hardening anyway: rootless or user namespaces, dropped capabilities, a tight seccomp profile, read-only root, no service-account tokens, egress network policies, CPU/memory/PID limits, and short-lived nodes. Separate the control plane from tenant nodes and never mount sockets. Accept the costs: sandbox overhead on syscall- and I/O-heavy workloads and compatibility gaps, which I would measure with representative customer workloads before rollout.
_What the interviewer is probing for:_ Ability to name concrete isolation tiers, quantify trade-offs and still apply defense in depth.

**🎯 Architect:** _"Build a decision framework for the CTO on when the company should use Docker/containers, VMs, serverless or bare metal."_
**Model answer:** Start from workload properties, not technology. Stateless services with standard Linux dependencies and variable load go to containers on a managed orchestrator, or a serverless container platform if the team does not want to operate nodes. Untrusted or regulated multi-tenant workloads go to VMs or microVMs, with sandboxed container runtimes where density matters. Stateful systems default to managed services; self-hosted only where there is a clear reason and operational maturity. Kernel-coupled, GPU/hardware-bound, HPC and ultra-low-latency workloads go to tuned VMs or bare metal, with containers only as a packaging format. Event-driven bursty glue goes to functions. Add cross-cutting criteria: team skills, vendor support, licensing, cost at scale, exit cost, and compliance. Keep OCI images as the shared artifact so a workload can move between tiers when requirements change, and review the decision when load, risk or team size changes.
_What the interviewer is probing for:_ Systematic reasoning across workload characteristics, risk and organizational capability instead of tool preference.

## 12. Common Misconceptions

- "Containers are lightweight VMs." They are processes sharing a kernel; the isolation is weaker and the model differs.
- "If it runs in a container it's secure." Defaults reduce risk but do not stop determined kernel-level attacks.
- "Docker runs macOS or Windows apps natively." Linux containers need a Linux kernel; Desktop uses a VM.
- "Containers are always faster than VMs." CPU performance is near native in both; I/O, networking and startup differ by configuration.
- "Docker handles high availability." The single-host engine restarts containers, but it does not reschedule across nodes.
- "Stateful workloads cannot be containerized." They can, with real investment in storage, backup and operators.

## 13. 🔑 Key Takeaways

- A shared kernel is the defining limitation: untrusted code, different kernels and hardware coupling push you toward VMs, microVMs or sandboxed runtimes.
- Containers on macOS and Windows run inside a hidden Linux VM, with real I/O costs.
- Stateful production data usually deserves managed services or operator-backed designs.
- Docker alone does not orchestrate; multi-host scale needs a scheduler.
- Keep OCI images as the portable artifact so the runtime and platform remain replaceable.
- Justify every use of containers with a named benefit, and every use of `--privileged` with a reason a VM could not serve.

## 14. Related Concepts & What's Next

Related: container versus VM model ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)), isolation limits ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), stateful patterns ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)), resource management at scale ([§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)), runtime choices ([§96](Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md)). Next, [§98](Section-98-Part13-Performance-Tuning-Recap.md) consolidates the performance levers for the cases where Docker is the right tool.

**Next Section:** [§98](Section-98-Part13-Performance-Tuning-Recap.md) — `Section-98-Part13-Performance-Tuning-Recap.md`
