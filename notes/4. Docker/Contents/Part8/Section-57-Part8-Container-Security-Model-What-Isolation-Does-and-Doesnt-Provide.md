# Section 57 (Part 8): Container Security Model: What Isolation Does and Doesn't Provide

## 1. Definition

**Plain language:** A container is an ordinary Linux process wrapped in several kernel restrictions. It is isolated from other containers, but it shares the host's kernel. That makes containers lighter than virtual machines and also weaker as a security boundary: a kernel bug or a misconfiguration can let a process escape to the host.

**Precise definition:** The Docker security model is defense in depth built from kernel primitives: namespaces (what a process can see, [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), cgroups (how much it can use, [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)), seccomp syscall filtering ([§60](Section-60-Part8-Seccomp-Profiles.md)), LSM profiles (AppArmor or SELinux, [§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)), read-only root filesystems ([§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)), and optionally user namespaces and rootless mode ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)). Security also includes the daemon's attack surface (the root-owned socket), the image supply chain ([§63](Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), secrets handling ([§64](Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), and networking ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).

> ⚠️ **Warning:** A container is not a sandbox for hostile code by default. Treat it as a packaging and resource-control boundary with useful hardening, and add stronger isolation (microVMs, gVisor) when running untrusted workloads.

## 2. Why This Matters

- Container escapes and privilege escalations (for example runc CVE-2019-5736, CVE-2024-21626 "Leaky Vessels") show the shared-kernel boundary is real attack surface.
- Most real incidents come from configuration: `--privileged`, a mounted Docker socket, root users, exposed daemon ports, stale images, leaked secrets.
- Teams that assume "it's in a container, so it's safe" skip the hardening that costs little and prevents most breaches.
- The security model drives later design choices: non-root users, dropped capabilities, read-only filesystems, scanning, signing.
- It is a core DCA and interview topic; answers must distinguish what is isolated from what is shared.

## 3. Prerequisites and Dependencies

Requires the container-vs-VM model ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)), namespaces and cgroups ([§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md), [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), the engine architecture ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), and the daemon socket and its permissions ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md), [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Runtime flags are in [§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md).

## 4. Architecture / Conceptual Diagram

```text
 ┌─────────────────────────── Host ────────────────────────────────────────┐
 │  ┌──────────────┐   ┌──────────────┐        Layers of containment       │
 │  │ Container A  │   │ Container B  │   1. Namespaces: pid net mnt uts   │
 │  │  app (uid 0?)│   │  app (uid 1k)│                 ipc user cgroup    │
 │  └──────┬───────┘   └──────┬───────┘   2. cgroups: cpu mem pids io      │
 │         │ syscalls         │            3. Capabilities (default set)   │
 │         ▼                  ▼            4. seccomp (default profile)    │
 │  ┌───────────────────────────────┐      5. AppArmor / SELinux           │
 │  │      SHARED HOST KERNEL       │      6. Read-only rootfs, no-new-priv│
 │  │  (one bug here = all escape)  │      7. User namespace / rootless    │
 │  └──────────────┬────────────────┘                                      │
 │                 │                                                       │
 │  ┌──────────────▼────────────┐   ┌─────────────────────────────────┐    │
 │  │ dockerd (root) + socket   │◄──┤ Anyone who can talk to the      │    │
 │  │ /var/run/docker.sock      │   │ socket is effectively root      │    │
 │  └───────────────────────────┘   └─────────────────────────────────┘    │
 └─────────────────────────────────────────────────────────────────────────┘

 Isolated by default            Shared / NOT isolated by default
 ─────────────────────          ───────────────────────────────────────────
 process tree, hostname          kernel (version, bugs, modules, sysctls
 mounts, network stack            not namespaced)
 IPC objects, users (if userns)  kernel keyrings, /proc and /sys parts,
 resource usage (if limited)     system time, kernel log, some devices
                                 uid 0 inside == uid 0 outside (no userns)
```

- **Shared kernel:** every container makes syscalls into the same kernel; isolation is policy enforced by that kernel.
- **Root in the container is root on the host,** just with fewer capabilities and filters, unless user namespaces or rootless mode remap it.
- **The daemon is the highest-value target:** access to the Docker socket is equivalent to root on the host.

## 5. Hands-On

### 5.1 Prove the Kernel Is Shared

```bash
uname -r
docker run --rm alpine:3.20 uname -r
```

```text
6.8.0-45-generic
6.8.0-45-generic
```

Both report the same kernel. On Docker Desktop the "host" is the lightweight Linux VM, so the version is the VM's kernel, not Windows or macOS.

### 5.2 See the Default Hardening Applied

```bash
docker run --rm alpine:3.20 sh -c 'grep -E "Cap(Prm|Eff|Bnd)|Seccomp|NoNewPrivs" /proc/self/status'
docker inspect --format 'caps={{.HostConfig.CapAdd}}/{{.HostConfig.CapDrop}} sec={{.HostConfig.SecurityOpt}} priv={{.HostConfig.Privileged}}' $(docker run -d alpine:3.20 sleep 30)
```

```text
CapPrm: 00000000a80425fb
CapEff: 00000000a80425fb
CapBnd: 00000000a80425fb
NoNewPrivs:     0
Seccomp:        2
caps=[]/[] sec=[] priv=false
```

`Seccomp: 2` means a seccomp filter is active (Docker's default profile). The capability mask is the reduced default set of 14 capabilities rather than the kernel's full set.

### 5.3 Compare with --privileged (What Not to Do)

```bash
docker run --rm --privileged alpine:3.20 sh -c 'grep -E "CapEff|Seccomp" /proc/self/status; ls /dev | wc -l'
docker run --rm alpine:3.20 sh -c 'ls /dev | wc -l'
```

```text
CapEff: 000001ffffffffff
Seccomp:        0
152
15
```

`--privileged` grants all capabilities, disables seccomp, relaxes AppArmor, and exposes all host devices. From such a container, mounting the host disk and escaping is trivial. Reserve it for tightly controlled tooling (for example, Docker-in-Docker CI runners on isolated hosts, [§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).

### 5.4 Docker Socket Equals Root

```bash
# Anyone able to run this on a host owns the host:
docker run --rm -v /:/host alpine:3.20 chroot /host id
```

```text
uid=0(root) gid=0(root) groups=0(root),...
```

Membership of the `docker` group (or access to `docker.sock`) is therefore root-equivalent. A container with `/var/run/docker.sock` mounted can do the same by launching a new privileged container.

### 5.5 Shared Resources Without Limits

```bash
docker run --rm alpine:3.20 sh -c ':(){ :|:& };:' &   # fork bomb: do NOT run on a real host without limits
```

Run that only in a disposable VM. The safe lesson is the mitigation:

```bash
docker run --rm --pids-limit 100 --memory 128m --cpus 0.5 alpine:3.20 sh -c 'echo contained'
```

```text
contained
```

Namespaces hide resources; only cgroup limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) cap consumption.

### 5.6 A Hardened Baseline Run

```bash
docker run -d --name hardened \
  --user 10001:10001 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --pids-limit 200 --memory 256m --cpus 0.5 \
  --network app-net \
  myapp:1.4.2
docker inspect hardened --format 'user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} drop={{.HostConfig.CapDrop}}'
```

```text
user=10001:10001 ro=true drop=[ALL]
```

Each flag is explored in its own section: [§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md).

### 5.7 Audit a Host with Docker Bench

```bash
docker run --rm --net host --pid host --userns host --cap-add audit_control \
  -v /etc:/etc:ro -v /var/lib:/var/lib:ro -v /var/run/docker.sock:/var/run/docker.sock:ro \
  docker/docker-bench-security
```

```text
[WARN] 2.1  - Ensure network traffic is restricted between containers on the default bridge
[PASS] 2.2  - Ensure the logging level is set to 'info'
[WARN] 4.1  - Ensure that a user for the container has been created
```

Docker Bench for Security checks the host and daemon against the CIS Docker Benchmark. Run it in a test environment first; it mounts sensitive host paths read-only and needs host namespaces.

## 6. Production Usage Notes

- **Threat model first:** decide whether workloads are trusted (your own code) or untrusted (customer code, CI from forks). Untrusted code needs a stronger boundary: gVisor (`runsc`), Kata Containers, or Firecracker microVMs as an alternate OCI runtime.
- **Standard baseline for every service:** non-root user, `--cap-drop ALL` plus only needed additions, default seccomp kept on, `no-new-privileges`, read-only root filesystem, resource limits, pinned and scanned images.
- **Protect the daemon:** do not expose TCP 2375; if remote access is needed use TLS (2376) or SSH contexts ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Consider rootless mode or `userns-remap`.
- **Keep the kernel and runtime patched;** container hardening cannot compensate for an unpatched kernel or runc.
- **Segment networks** and avoid the default bridge for sensitive services ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- **Enforce by policy:** admission control, CI checks on Compose files and Dockerfiles, and image allow-lists rather than relying on developers to remember flags.
- **Log and audit** daemon events and API access; centralize logs ([§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)).

## 7. Security Considerations

This whole section is the security model, so the highest-impact points are listed here by attack surface.

- **Kernel (shared):** syscall and driver bugs enable escapes. Mitigate with seccomp, user namespaces, patching, and stronger runtimes for untrusted workloads.
- **Runtime (runc/containerd):** vulnerabilities such as Leaky Vessels (CVE-2024-21626, via leaked file descriptors) affected the runtime itself. Track Docker Engine, containerd and runc releases.
- **Daemon and socket:** root-equivalent access; never mount `docker.sock` into application containers, never publish the API without TLS, restrict `docker` group membership.
- **Configuration:** `--privileged`, `--pid=host`, `--net=host`, `--cap-add=SYS_ADMIN`, `--security-opt seccomp=unconfined`, writable mounts of `/`, `/proc`, `/sys` or `/etc` each remove a layer.
- **Images and supply chain:** vulnerable packages, malicious base images, tag mutation. Scan, pin by digest, sign, and generate SBOMs.
- **Secrets:** environment variables and image layers leak through `docker inspect`, `/proc`, logs and history ([§64](Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Network:** all containers on the default bridge can reach each other; unpublished ports are not a security control against neighbors.
- **Resources:** unlimited containers can exhaust memory, PIDs or disk (denial of service).
- **Docker Desktop:** the VM adds a second boundary between the host OS and containers, so a container escape lands in the VM first, but shared folders and published ports still bridge to the host.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `operation not permitted` for a legitimate action (for example `ping`, `mount`, `iptables`) | Capability dropped or blocked by seccomp/AppArmor | Identify the needed capability and add only it with `--cap-add`; avoid `--privileged` |
| `Permission denied` writing files after switching to a non-root user | Files owned by root; volume ownership mismatch | `chown` at build or `COPY --chown`; fix volume permissions |
| App fails to bind port 80 as non-root | Privileged port | Use port above 1024, or `--sysctl net.ipv4.ip_unprivileged_port_start=80`, or `NET_BIND_SERVICE` |
| `read-only file system` errors | `--read-only` without writable paths | Add `--tmpfs` or volumes for `/tmp`, `/run`, cache dirs |
| Tool needs the Docker API and someone mounts the socket | Convenient but root-equivalent | Use a socket proxy limiting API calls, or rootless/remote contexts |
| Security scanner flags many CVEs | Large base image, outdated packages | Smaller base, rebuild regularly, patch ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)) |
| Docker Bench warnings on default bridge, no user, no limits | Defaults are permissive | Apply the baseline from 5.6 and daemon settings |
| Unknown outbound connections from a container | Compromise or an unexpected dependency | Inspect with `docker diff`, network logs, drop egress with network policy, rebuild from clean image |

## 9. Best Practices

- Assume breach: layer controls so no single failure grants host access.
- Run as non-root, drop all capabilities and add back minimally, keep default seccomp, set `no-new-privileges`.
- Use read-only root filesystems with explicit tmpfs/volumes for writable paths.
- Set memory, CPU and PID limits on every container.
- Never use `--privileged`, host namespaces or the Docker socket mount in application containers without a documented exception.
- Scan images in CI and at rest, pin by digest, sign, and keep SBOMs.
- Keep secrets out of images and environment variables.
- Patch the host kernel, Docker Engine, containerd and runc promptly.
- Use rootless Docker or user namespaces where compatible.
- Choose stronger runtimes (gVisor, Kata) for untrusted multi-tenant workloads.
- Benchmark against the CIS Docker Benchmark and automate the checks.

## 10. Common Anti-Patterns / Mistakes

- "It's just a container" thinking: treating isolation like VM isolation.
- Adding `--privileged` to silence a permission error instead of finding the missing capability.
- Mounting `/var/run/docker.sock` into CI jobs or dashboards.
- Exposing the Docker daemon on TCP without TLS.
- Running everything as root because it is the image default.
- Baking credentials into `ENV`, build args or image layers.
- Using `latest` tags and never rebuilding, so known CVEs accumulate.
- Adding all developers to the `docker` group on shared hosts.
- Relying on "unpublished" ports to protect services on the shared default bridge.
- Disabling AppArmor or seccomp globally to fix one application.

## 11. Interview Questions

**🎯 Beginner:** _"How is a container different from a VM in terms of security isolation?"_
**Model answer:** A VM runs its own kernel on virtualized hardware under a hypervisor, so the attack surface between guest and host is the hypervisor. A container is a process that shares the host kernel and is isolated by namespaces, cgroups, capabilities, seccomp and LSMs. That is lighter and faster, but a kernel vulnerability or a misconfiguration (for example `--privileged`) can let a process reach the host. Containers are therefore a weaker boundary by default and need hardening, or an extra layer such as a microVM for untrusted code.
_What the interviewer is probing for:_ The shared-kernel concept and an honest comparison rather than "containers are secure" or "containers are insecure".

**🎯 Intermediate:** _"Why is mounting `/var/run/docker.sock` into a container dangerous, and what are the alternatives?"_
**Model answer:** The socket is the Docker API on a root-owned daemon. A process with access can create a container that bind-mounts the host root filesystem, runs privileged, or joins host namespaces, which is a full host takeover. Alternatives: build in rootless BuildKit or Kaniko-style daemonless builders, use Docker-in-Docker on isolated runners with trade-offs ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)), use a filtering socket proxy that exposes only needed endpoints read-only, or use remote contexts over SSH with restricted keys. Where the socket is unavoidable, isolate those hosts and treat the container as trusted as root.
_What the interviewer is probing for:_ Knowing socket access is root-equivalent, with practical mitigations.

**🎯 Senior:** _"A pentest report says one of your containers is compromised. Walk through what limits the blast radius, and what you would verify on the host."_
**Model answer:** The blast radius depends on layers: non-root user and dropped capabilities limit what the attacker can do inside; default seccomp and AppArmor/SELinux limit reachable syscalls and files; read-only root blocks persistence and tool drops; network segmentation limits lateral movement; cgroup limits prevent resource abuse; user namespaces or rootless mode make container root unprivileged on the host. I would verify the container's run configuration (`docker inspect` for privileged, mounts, socket, host namespaces, capabilities), check `docker diff` and logs, review host kernel and runtime versions against known escape CVEs, look for new containers or images created through the API, and rotate any secrets that were reachable. Then rebuild from a clean image rather than cleaning in place.
_What the interviewer is probing for:_ Defense-in-depth reasoning plus incident-response habits.

**🎯 Architect:** _"You are building a platform that runs customer-supplied container images. How do you design the isolation model?"_
**Model answer:** Treat every tenant as hostile, so a plain shared-kernel runc container is insufficient on its own. Run workloads under a sandboxed runtime (gVisor for syscall interception or Kata/Firecracker for hardware-virtualized isolation), on dedicated or pooled nodes per trust level, with rootless or userns-mapped execution. Enforce non-root, no capabilities, restrictive seccomp, read-only roots, strict cgroup limits, and egress-deny-by-default network policy with per-tenant segmentation. Control the supply chain with registry allow-lists, scanning, signature verification and admission policy. Keep the control plane separate from tenant nodes, never expose the Docker socket, and add runtime detection (Falco/eBPF) with audit logging. Accept the trade-offs: sandboxes cost performance and compatibility, so tier the offering and test syscall coverage for common workloads.
_What the interviewer is probing for:_ Matching isolation strength to the threat model and knowing the alternatives to runc.

## 12. Common Misconceptions

- "Containers are VMs." They share the host kernel.
- "Root inside the container is harmless." Without user namespaces it is uid 0 on the host, restricted but not unprivileged.
- "A container escape needs an exotic zero-day." Most are caused by privileged flags, socket mounts or writable host mounts.
- "If a port isn't published, it's protected." Other containers on the same network can still reach it.
- "Scanning the image once is enough." New CVEs appear continuously; rescan and rebuild.
- "Docker Desktop makes the host immune." It adds a VM layer but shared folders and ports still connect to the host.
- "Seccomp and AppArmor are optional extras." Docker enables both by default; disabling them is a regression.

## 13. 🔑 Key Takeaways

- Containers isolate with namespaces, cgroups, capabilities, seccomp and LSMs, but share one host kernel.
- Docker socket or `docker` group access equals root on the host.
- `--privileged`, host namespaces and sensitive mounts remove most protections.
- Baseline every workload: non-root, `--cap-drop ALL`, `no-new-privileges`, read-only rootfs, resource limits.
- Untrusted code needs stronger isolation than runc: gVisor, Kata or microVMs.
- Patch kernel and runtime, scan and sign images, and keep secrets out of images and ENV.

## 14. Related Concepts & What's Next

Related: namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), cgroups ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), network isolation ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)), anti-patterns ([§95](../Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)). Next, [§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md) covers running as non-root with the `USER` instruction and user namespaces, the first and highest-value hardening step.

**Next Section:** [§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md) — `Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md`
