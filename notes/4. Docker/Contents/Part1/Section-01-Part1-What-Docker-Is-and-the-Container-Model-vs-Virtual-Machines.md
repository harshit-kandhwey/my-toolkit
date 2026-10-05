# Section 1 (Part 1): What Docker Is and the Container Model vs. Virtual Machines

## 1. Definition

**Plain language:** Docker is a tool for packaging an application together with everything it needs to run (its libraries, runtime, and configuration) into a single portable unit called an **image**, and then running that image as an isolated process called a **container**. The container behaves like a tiny, private Linux machine, but it is really just a normal process on the host that the kernel has fenced off from everything else.

**Precise definition:** **Docker** is a platform, made of a client CLI, a long-running daemon (`dockerd`), an image format, and a registry protocol, that builds, distributes, and runs **OS-level virtualized** workloads. A **container** is a process (or process tree) started from an image and isolated using Linux kernel features: **namespaces** (what the process can *see*: PIDs, network, mounts, hostname, IPC, users) and **control groups / cgroups** (how much the process can *use*: CPU, memory, I/O, PIDs), with a layered, copy-on-write root filesystem assembled from the image. Containers share the host kernel; they do not boot their own. The kernel mechanisms are covered in depth in [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md) (namespaces) and [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) (cgroups), and the layered filesystem in [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md).

> 💡 **Tip:** "A container is not a thing the kernel knows about." The Linux kernel has no `container` object. A container is a convention: a process placed in a set of namespaces and a cgroup, with a different root filesystem. Docker is the tooling that applies that convention consistently.

## 2. Why This Matters

- **It removes "works on my machine".** The image carries the userland (glibc, Python, OpenSSL, app code), so dev, CI, and production run byte-identical filesystems on top of whatever host kernel is present.
- **Startup is measured in milliseconds, not minutes.** No firmware, bootloader, or guest kernel boot is involved; starting a container is `clone()` with namespace flags plus a filesystem mount.
- **Density and cost.** With no guest OS per workload, a host that runs 10 VMs can often run hundreds of containers. Idle overhead is a few MB per container versus hundreds of MB to GB per VM.
- **It is the unit of modern delivery.** Kubernetes, ECS, Cloud Run, and most CI systems schedule containers, not VMs or tarballs. Understanding Docker is the entry point to all of them.
- **It changes the security model.** Shared-kernel isolation is weaker than hypervisor isolation. Knowing precisely where that boundary sits is what separates safe container use from dangerous container use.
- **Interviews and the DCA exam** ([§7](Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md)) begin with the container-vs-VM distinction; weak answers here signal weak fundamentals everywhere else.

## 3. Prerequisites and Dependencies

This is the entry point of the Docker knowledge base and assumes working Linux command-line literacy and a general idea of what a process, a filesystem, and a virtual machine are. [§2](Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md) explains how the industry arrived at this model, and [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) positions Docker against alternative runtimes. [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) walks through installation so the hands-on commands in this section can be run. [§5](Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) recaps the Linux primitives (namespaces, cgroups, networking) that this section only sketches, and [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) opens up the engine internals (dockerd, containerd, runc) that turn `docker run` into a running process.

## 4. Architecture / Conceptual Diagram

```text
        Virtual Machines                          Containers

  ┌────────┐ ┌────────┐ ┌────────┐        ┌────────┐ ┌────────┐ ┌────────┐
  │ App A  │ │ App B  │ │ App C  │        │ App A  │ │ App B  │ │ App C  │
  ├────────┤ ├────────┤ ├────────┤        ├────────┤ ├────────┤ ├────────┤
  │ Libs   │ │ Libs   │ │ Libs   │        │ Libs   │ │ Libs   │ │ Libs   │
  ├────────┤ ├────────┤ ├────────┤        └───┬────┘ └───┬────┘ └───┬────┘
  │Guest OS│ │Guest OS│ │Guest OS│            │          │          │
  │(kernel)│ │(kernel)│ │(kernel)│        ┌───▼──────────▼──────────▼────┐
  └───┬────┘ └───┬────┘ └───┬────┘        │  Container runtime (Docker)  │
      │          │          │             ├──────────────────────────────┤
  ┌───▼──────────▼──────────▼────┐        │   Host OS kernel (shared)    │
  │        Hypervisor            │        │ namespaces + cgroups + LSMs  │
  ├──────────────────────────────┤        ├──────────────────────────────┤
  │  Host OS / bare metal        │        │       Hardware / VM          │
  ├──────────────────────────────┤        └──────────────────────────────┘
  │         Hardware             │
  └──────────────────────────────┘

  Isolation boundary:  VM  = hypervisor + separate kernels (hardware-enforced)
                       CTR = one shared kernel, fenced by namespaces/cgroups
```

```text
              What `docker run nginx` produces on the host

  docker CLI ──► dockerd ──► containerd ──► runc ──► [nginx process]
                                                          │
                     ┌────────────────────────────────────┤
                     ▼                  ▼                 ▼
               namespaces          cgroup slice      overlay2 rootfs
             (pid,net,mnt,        (cpu, memory,      (image layers +
              uts,ipc,user)         pids, io)        writable layer)
```

- **The left stack has two kernels per workload boundary; the right has one.** That single difference explains nearly every trade-off: containers are lighter and faster, VMs are more strongly isolated and can run a different OS entirely.
- **A container cannot run a different kernel than its host.** A Linux container needs a Linux kernel. Docker Desktop on macOS and Windows quietly runs a small Linux VM to provide one ([§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)).
- **The lower diagram is the mental model for the rest of Part 2.** [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) dissects the chain of processes, [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md) to [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) dissect the three kernel mechanisms at the bottom.

## 5. Hands-On

### 5.1 Confirm the Toolchain and Run a First Container

**Purpose:** Verify the client and daemon are both reachable, then run a container end to end.

**Syntax:**

```bash
docker version
docker run [OPTIONS] IMAGE [COMMAND] [ARG...]
```

**Example usage and expected output:**

```bash
$ docker version --format '{{.Client.Version}} / {{.Server.Version}}'
27.3.1 / 27.3.1

$ docker run --rm hello-world
Unable to find image 'hello-world:latest' locally
latest: Pulling from library/hello-world
c1ec31eb5944: Pull complete
Digest: sha256:d211f485f2dd1dee407a80973c8f129f00d54604d2c90732e8e320e5038a0348
Status: Downloaded newer image for hello-world:latest

Hello from Docker!
This message shows that your installation appears to be working correctly.
```

**Production usage example:** `docker version` is the first line of many CI diagnostics; a version mismatch between client and daemon (or an unreachable daemon) explains a large class of pipeline failures.

**Common errors:** `Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?` means the daemon is stopped or your user cannot read the socket (see [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

### 5.2 A Container Is Just a Process on the Host

**Purpose:** Prove that a container is an ordinary host process, not a VM.

**Syntax:**

```bash
docker run -d --name web nginx:1.27
docker top web
ps -ef | grep 'nginx: master'
```

**Example usage and expected output:**

```bash
$ docker run -d --name web nginx:1.27
8f3c1d2a9b7e5c4d6a1f0e2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d

$ docker top web
UID    PID     PPID    C   STIME  TTY  TIME      CMD
root   20481   20460   0   10:12  ?    00:00:00  nginx: master process nginx -g daemon off;
101    20527   20481   0   10:12  ?    00:00:00  nginx: worker process

$ ps -ef | grep 'nginx: master'
root     20481   20460  0 10:12 ?  00:00:00 nginx: master process nginx -g daemon off;

$ docker exec web cat /proc/1/cmdline | tr '\0' ' '
nginx: master process nginx -g daemon off;
```

**Production usage example:** Host-level tools (`ps`, `top`, `perf`, `strace`) can observe container processes directly by their host PID, which is how node-level monitoring agents work.

**Common errors:** On Docker Desktop, `ps` on your laptop will *not* show the process because it lives inside the Docker Desktop Linux VM.

### 5.3 Shared Kernel vs. Guest Kernel

**Purpose:** Show that containers report the host kernel, regardless of the image's distribution.

**Syntax:**

```bash
uname -r
docker run --rm IMAGE uname -r
```

**Example usage and expected output:**

```bash
$ uname -r
6.8.0-45-generic

$ docker run --rm alpine:3.20 uname -r
6.8.0-45-generic

$ docker run --rm alpine:3.20 cat /etc/os-release | head -2
NAME="Alpine Linux"
ID=alpine
```

**Production usage example:** Kernel-feature dependencies (eBPF, specific cgroup version, io_uring) are properties of the *host*, not the image. Node upgrades can change container behavior with no image change.

**Common errors:** Assuming an image "brings its own kernel" and being surprised when a kernel-dependent tool fails on an older host.

### 5.4 Resource Isolation and Limits

**Purpose:** See namespaces and cgroups at work from inside a container.

**Syntax:**

```bash
docker run --rm --memory=128m --cpus=0.5 alpine:3.20 sh -c '...'
```

**Example usage and expected output:**

```bash
$ docker run --rm --memory=128m --cpus=0.5 alpine:3.20 sh -c 'ps aux; hostname; cat /sys/fs/cgroup/memory.max'
PID   USER     TIME  COMMAND
    1 root      0:00 sh -c ps aux; hostname; cat /sys/fs/cgroup/memory.max
    7 root      0:00 ps aux
a4be6d1c9f02
134217728
```

The container sees only its own two processes (PID namespace), its own hostname (UTS namespace), and its memory ceiling of 128 MiB (cgroup v2).

**Production usage example:** Every Kubernetes `resources.limits` block ultimately becomes exactly these cgroup files.

**Common errors:** On cgroup v1 hosts the file is `/sys/fs/cgroup/memory/memory.limit_in_bytes`; the path in the example above is cgroup v2 only ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)).

### 5.5 Startup Time Comparison

**Purpose:** Quantify the practical difference from a VM boot.

**Example usage and expected output:**

```bash
$ time docker run --rm alpine:3.20 true

real    0m0.412s
user    0m0.018s
sys     0m0.021s
```

A comparable VM boot (firmware, kernel, init, services) typically takes tens of seconds even when optimized.

## 6. Production Usage Notes

- **Containers are meant to be ephemeral and immutable.** Treat a running container as disposable; state belongs in volumes or external services, and changes belong in a rebuilt image.
- **One main process per container** is the norm. Multiple concerns (app, log shipper, proxy) go in separate containers composed together.
- **Containers and VMs are complementary.** Most production estates run containers *inside* VMs (EC2 nodes running ECS/EKS) to get hypervisor isolation between tenants and container density within a tenant.
- **Pick VMs when you need** a different kernel or OS (Windows guest on Linux host), strong multi-tenant isolation for untrusted code, or kernel modules. Pick containers for stateless services, CI jobs, and microservices.
- **Sandboxed runtimes bridge the gap.** gVisor and Kata Containers add a user-space kernel or a micro-VM per container when stronger isolation is required for untrusted workloads.
- **Always pin image tags** (`nginx:1.27`, ideally a digest) so "the same container" really is the same.

## 7. Security Considerations

- **The shared kernel is the shared attack surface.** A kernel vulnerability reachable from inside a container (a container escape) compromises the host and every other container on it. VMs have a much smaller, hypervisor-based boundary.
- **Root in a container is not harmless.** By default UID 0 in the container is UID 0 on the host unless user namespaces or rootless mode are used ([§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md), [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)). Prefer non-root users in images.
- **Access to the Docker socket equals root on the host.** Anyone able to talk to `/var/run/docker.sock` can start a privileged container mounting `/`. See [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) and [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md).
- **`--privileged` removes most of the fencing.** It grants all capabilities and device access; treat it as "no container" from a security standpoint.
- **Defaults help but are not a guarantee.** Docker applies a default seccomp profile, drops many capabilities, and can use AppArmor/SELinux; hardening beyond these defaults is covered in the security parts of this knowledge base.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Diagnostic |
|---|---|---|
| `Cannot connect to the Docker daemon` | Daemon stopped or no socket permission | `systemctl status docker`, `ls -l /var/run/docker.sock`, `id` |
| Container exits immediately with code 0 | Main process finished (containers live only as long as PID 1) | `docker logs <c>`, `docker inspect -f '{{.Config.Cmd}}' <c>` |
| Container exits with 137 | Killed by SIGKILL, often OOM by the cgroup memory limit | `docker inspect -f '{{.State.OOMKilled}}' <c>`, `dmesg -T \| grep -i oom` |
| `exec format error` | Image architecture (arm64/amd64) differs from host | `docker image inspect -f '{{.Architecture}}' <img>`, `uname -m` |
| Works on host, fails in container | Missing libraries, different UID, different network namespace (`localhost` is the container's own) | `docker exec -it <c> sh`, `docker exec <c> id` |
| Cannot see container processes with `ps` on macOS/Windows | Processes live in the Docker Desktop VM | `docker top <c>` instead |

## 9. Best Practices

- Explain and design around the **one shared kernel** fact: choose isolation level deliberately per workload.
- Keep containers **stateless and disposable**; externalize state to volumes or managed services.
- Use **small, purpose-built base images** to reduce size and attack surface.
- Run as a **non-root user** and drop capabilities the workload does not need.
- Set **memory and CPU limits** so one container cannot starve its neighbors.
- **Pin versions** of base images and tools; rebuild regularly to pick up patches.
- Use `--rm` for throwaway containers to avoid accumulating stopped containers.

## 10. Common Anti-Patterns / Mistakes

- **Treating a container like a VM:** SSH-ing into it, patching it in place, running an init system with five services. Changes are lost on recreation and drift is invisible.
- **Storing data in the container's writable layer.** It vanishes with `docker rm`.
- **Using `latest` in production.** The tag moves; deployments become non-reproducible.
- **Running everything `--privileged` "to make it work".** This defeats the isolation model.
- **Assuming containers are a security boundary equivalent to VMs** for hostile multi-tenant code.
- **Ignoring resource limits**, leading to noisy-neighbor outages and host OOM kills.

## 11. Interview Questions

**🎯 Beginner:** _"A teammate says a container is just a lightweight VM. How would you correct them, and how can you prove it on a machine?"_
**Model answer:** A container is an ordinary host process isolated by namespaces and limited by cgroups; it has no guest OS or hypervisor. Run `docker run -d --name w nginx`, then `docker inspect -f '{{.State.Pid}}' w` and `ps -ef | grep <pid>` on the host to see the process directly. Compare `uname -r` on the host and `docker exec w uname -r` inside: they match because the kernel is shared. A VM would report its own guest kernel.
_What the interviewer is probing for:_ That the candidate understands the shared-kernel model rather than the VM analogy.

**🎯 Intermediate:** _"A container keeps exiting with code 137 a few minutes after start. How do you diagnose it?"_
**Model answer:** Code 137 is 128 plus SIGKILL (9), commonly the kernel OOM killer enforcing a cgroup memory limit. Check `docker inspect -f '{{.State.OOMKilled}} {{.HostConfig.Memory}}' <c>` and `dmesg | grep -i oom` on the host. Then compare `docker stats` against the limit set with `--memory`, and either raise the limit or fix the leak. If OOMKilled is false, look for a `docker kill` or a stop timeout that escalated to SIGKILL.
_What the interviewer is probing for:_ Linking exit codes to cgroup limits and knowing where evidence lives.

**🎯 Senior:** _"A vendor wants to run its agent as a container that mounts /var/run/docker.sock. Security objects. Who is right, and what do you offer instead?"_
**Model answer:** Security is right: access to the socket lets the container call the API to create a privileged container with `-v /:/host`, which is root on the host. If the agent only needs read-only visibility, put a socket proxy in front that allows only GET on specific endpoints, or use the agent's host-installed mode. Otherwise isolate it on a dedicated node, run rootless, and audit API calls. Document the residual risk if it must stay.
_What the interviewer is probing for:_ Recognizing socket access as root-equivalent and offering least-privilege alternatives.

**🎯 Architect:** _"You run a platform that executes customer-submitted code on shared nodes. Would you use plain containers, and how do containers and VMs fit into your design?"_
**Model answer:** Plain containers share the host kernel, so a kernel CVE or misconfiguration is a cross-tenant escape; for hostile tenants I would add a stronger boundary. Use sandboxed runtimes such as gVisor or Kata (a micro-VM per tenant or pod), keep the VM as the tenant boundary, and run containers inside for packaging and density. Layer on rootless operation, seccomp, dropped capabilities, strict cgroup limits, and network policy. Budget for kernel patching across the fleet, since every node upgrade affects all tenants sharing it.
_What the interviewer is probing for:_ Matching isolation strength to the threat model and understanding the cost of the shared kernel.
## 12. Common Misconceptions

- **"Containers are lightweight VMs."** They are isolated processes; there is no guest OS or hypervisor.
- **"A container has its own kernel."** It shares the host kernel, which `uname -r` confirms.
- **"Containers are always more secure than running directly on the host."** They add isolation layers but also a large shared kernel surface and a powerful daemon.
- **"Docker is the same as containers."** Docker is one toolchain; containers are a kernel-level concept implemented by several tools ([§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md), [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)).
- **"Containers are faster than bare metal."** They run at near-native speed, not faster; the gain is in startup and density.
- **"Data in a container persists."** Only data in volumes or bind mounts survives container removal.

## 13. 🔑 Key Takeaways

- A container is a **regular host process** isolated by **namespaces** and limited by **cgroups**, with a layered root filesystem from an image.
- Containers **share the host kernel**; VMs each run their own kernel on a hypervisor.
- That shared kernel gives containers speed, density, and portability, and costs them isolation strength.
- Docker is the tooling: CLI, daemon, image format, and registry workflow.
- Containers are **ephemeral**; state lives outside them.
- Choose containers and VMs per workload, and often combine them.

## 14. Related Concepts & What's Next

- [§2](Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md) covers how dotCloud's internal tooling became Docker and how the OCI later standardized the formats.
- [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) compares Docker with Podman, LXC, rkt, and standalone containerd.
- [§5](Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) recaps namespaces, cgroups, and networking basics; [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md), and [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) go deep on each.
- [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) explains how `docker run` traverses dockerd, containerd, and runc.

**Next Section:** [§2](Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md) — `Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md`
