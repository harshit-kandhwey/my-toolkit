# Section 3 (Part 1): Docker vs. Podman, LXC, rkt, and containerd Standalone

## 1. Definition

**Plain language:** Docker is one of several ways to build and run containers. Podman runs the same images without a central daemon, LXC runs whole "system containers" that feel like lightweight VMs, rkt was an early competitor that has since been retired, and containerd is the engine underneath Docker that can be used on its own. Choosing among them is a question of what you are optimizing: developer experience, security posture, Kubernetes node simplicity, or system-level isolation.

**Precise definition:** These tools differ along four axes: **architecture** (client-server daemon vs. fork-exec daemonless), **container type** (application containers vs. system containers), **privilege model** (root daemon vs. rootless by default), and **scope** (full developer platform vs. runtime-only component). Most modern alternatives implement the **OCI image and runtime specifications** ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), so an image built by one can typically run in another. The Docker architecture being compared against is described in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) and [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md).

> 💡 **Tip:** Ask "what does this tool do that `runc` does not?" for every runtime. Nearly all of them ultimately call an OCI runtime to create the process; they differ in everything wrapped around it.

## 2. Why This Matters

- **Kubernetes nodes rarely need Docker.** Understanding containerd and CRI-O standalone is essential for cluster operations ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).
- **Security teams increasingly ask for daemonless or rootless tooling.** Podman's model directly answers the "root daemon on every host" objection ([§7](Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md)).
- **Licensing and policy pressure** ([§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)) pushed developers to evaluate Podman, Rancher Desktop, and Colima as Docker Desktop replacements.
- **Different workloads want different container types.** A full init system with multiple services fits LXC/LXD; a single stateless service fits Docker or Podman.
- **Interview and design questions** frequently ask for a defended choice between Docker, Podman, and containerd rather than a feature list.
- **Portability is a career skill.** An engineer who only knows `docker` commands but not the equivalents `podman`, `nerdctl`, or `crictl` struggles on any node without a Docker daemon.

## 3. Prerequisites and Dependencies

Requires [§1](Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md) (container model), [§2](Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md) (history, especially the OCI and component split), and a working sense of the engine chain from [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md). Rootless concepts referenced here are introduced in [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) and rest on user namespaces from [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md). [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) goes deeper on containerd's CRI plugin and Kubernetes integration, and [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) explains the OCI specs that make cross-tool image portability possible.

## 4. Architecture / Conceptual Diagram

```text
   Docker (daemon)              Podman (daemonless)         containerd standalone

   ┌──────────────┐             ┌──────────────┐            ┌──────────────┐
   │  docker CLI  │             │  podman CLI  │            │ nerdctl/ctr/ │
   └──────┬───────┘             └──────┬───────┘            │ crictl/kubelet│
          │ REST/unix sock             │ fork/exec           └──────┬───────┘
   ┌──────▼───────┐                    │                            │ gRPC
   │   dockerd    │  (root daemon)     │                     ┌──────▼───────┐
   └──────┬───────┘                    │                     │  containerd  │
          │ gRPC                       │                     └──────┬───────┘
   ┌──────▼───────┐             ┌──────▼───────┐             ┌──────▼───────┐
   │  containerd  │             │ conmon (per  │             │ shim ► runc  │
   └──────┬───────┘             │  container)  │             └──────────────┘
   ┌──────▼───────┐             └──────┬───────┘
   │ shim ► runc  │             ┌──────▼───────┐
   └──────────────┘             │ runc / crun  │
                                └──────────────┘

   LXC/LXD: liblxc ──► full init (systemd) inside container, "system container"
   rkt:     no daemon, pod-native, App Container spec ──► project ended (2020)
```

```text
   Comparison at a glance

   Tool         Daemon?    Rootless      Container type   Status
   ──────────── ────────── ───────────── ──────────────── ─────────────────
   Docker       yes (root) optional      application      active, dominant
   Podman       no         default-ish   application+pods active
   containerd   yes (thin) supported     application      active (CNCF grad.)
   CRI-O        yes (thin) supported     application      active (K8s-only)
   LXC / LXD    optional   supported     system           active
   rkt          no         limited       pod / app        archived
```

- **Docker sits on top of containerd; containerd is not "less than" Docker.** It is the part of Docker that actually manages container lifecycle, image pulls, and snapshots.
- **Podman's key trait is the missing daemon.** Each container is a child of `conmon`, not of a central root process, so there is no single point of failure or single privileged API surface.
- **rkt's ideas outlived it.** Pods, and the push toward a neutral spec, fed directly into Kubernetes and the OCI.

## 5. Hands-On

### 5.1 Same Image, Different Engines

**Purpose:** Demonstrate that OCI images are portable by running one image through Docker and Podman.

**Syntax:**

```bash
docker run --rm IMAGE COMMAND
podman run --rm IMAGE COMMAND
```

**Example usage and expected output:**

```bash
$ docker run --rm docker.io/library/alpine:3.20 echo "hello from docker"
hello from docker

$ podman run --rm docker.io/library/alpine:3.20 echo "hello from podman"
Trying to pull docker.io/library/alpine:3.20...
Getting image source signatures
Copying blob 43c4264eed91 done
Writing manifest to image destination
hello from podman
```

**Production usage example:** Teams migrating from Docker Desktop keep identical Dockerfiles and compose files; only the CLI binary changes. Note Podman requires the full registry name by default (or a configured search registry list).

**Common errors:** `Error: short-name "alpine" did not resolve to an alias and no unqualified-search registries are defined` means you must use `docker.io/library/alpine` or configure `registries.conf`.

### 5.2 Daemon vs. Daemonless Process Trees

**Purpose:** See the architectural difference in the host's process table.

**Syntax:**

```bash
docker run -d --name d1 alpine:3.20 sleep 300
podman run -d --name p1 alpine:3.20 sleep 300
ps -eo pid,ppid,comm | grep -E 'dockerd|containerd-shim|conmon|sleep'
```

**Example usage and expected output:**

```bash
$ ps -eo pid,ppid,user,comm | grep -E 'dockerd|containerd-shim|conmon|sleep'
 1187     1 root    dockerd
20460     1 root    containerd-shim
20481 20460 root    sleep
31042     1 alice   conmon
31045 31042 alice   sleep
```

The Docker container's ancestry runs through the root `dockerd`/containerd-shim chain; the Podman container is owned by an unprivileged user via `conmon`, with no shared daemon.

**Production usage example:** Restarting `dockerd` on a node is a deliberate operational event (with `live-restore` enabled containers survive it). A Podman host has no equivalent daemon to restart.

**Common errors:** Expecting `podman ps` to show Docker's containers. Each engine has its own storage and state; they do not share containers.

### 5.3 containerd Standalone with `ctr` and `nerdctl`

**Purpose:** Run a container using containerd directly, with no Docker daemon involved.

**Syntax:**

```bash
sudo ctr images pull IMAGE
sudo ctr run --rm -t IMAGE ID COMMAND
sudo nerdctl run --rm IMAGE COMMAND
```

**Example usage and expected output:**

```bash
$ sudo ctr images pull docker.io/library/alpine:3.20
docker.io/library/alpine:3.20:                       resolved
manifest-sha256:1e42bbe2...:                         done
elapsed: 2.1 s                                       total: 3.4 Mi (1.6 MiB/s)

$ sudo ctr run --rm -t docker.io/library/alpine:3.20 demo uname -a
Linux localhost 6.8.0-45-generic #45-Ubuntu SMP x86_64 Linux

$ sudo nerdctl run --rm alpine:3.20 echo "docker-compatible CLI on containerd"
docker-compatible CLI on containerd
```

**Production usage example:** On Kubernetes nodes use `crictl` (CRI-level) or `ctr -n k8s.io` (containerd-level) for debugging, since `docker ps` is unavailable.

**Common errors:** `ctr` has no `-p`, build, or compose functionality and no default namespace equal to Docker's; use `nerdctl` for a Docker-like experience and `-n k8s.io` for Kubernetes containers.

### 5.4 LXC System Container

**Purpose:** Contrast application containers with a full-OS system container.

**Syntax:**

```bash
lxc launch ubuntu:24.04 NAME
lxc exec NAME -- COMMAND
```

**Example usage and expected output:**

```bash
$ lxc launch ubuntu:24.04 sys1
Creating sys1
Starting sys1

$ lxc exec sys1 -- systemctl is-system-running
running

$ lxc exec sys1 -- ps -e | head -4
    PID TTY          TIME CMD
      1 ?        00:00:01 systemd
     52 ?        00:00:00 systemd-journal
     92 ?        00:00:00 systemd-logind
```

PID 1 is a real init system (`systemd`), unlike a Docker container whose PID 1 is usually the application itself.

**Production usage example:** LXD suits VPS-style hosting and multi-service test environments that need to behave like a full OS.

**Common errors:** Trying to deploy an app with `lxc` the way you would with an OCI image; system containers are stateful machines, not immutable artifacts.

### 5.5 Migration Aid: Docker-Compatible Podman Socket

**Purpose:** Let tools that expect the Docker API talk to Podman.

**Syntax:**

```bash
systemctl --user enable --now podman.socket
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
```

**Example usage and expected output:**

```bash
$ systemctl --user enable --now podman.socket
Created symlink /home/alice/.config/systemd/user/sockets.target.wants/podman.socket.

$ export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
$ docker ps
CONTAINER ID  IMAGE  COMMAND  CREATED  STATUS  PORTS  NAMES
```

**Production usage example:** CI runners and IDE plugins that call the Docker REST API ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)) work unmodified against this compatibility socket.

**Common errors:** Forgetting that Podman's socket is per-user and rootless; tools that assume `/var/run/docker.sock` need the `DOCKER_HOST` variable set.

## 6. Production Usage Notes

- **Servers running application workloads:** Docker Engine or containerd; both are well understood and widely supported. Choose containerd directly when an orchestrator manages the node and no human needs `docker build`.
- **Kubernetes nodes:** containerd (default on most managed offerings) or CRI-O (default on OpenShift). No Docker daemon is needed.
- **Developer laptops:** Docker Desktop for the smoothest experience, Podman Desktop, Rancher Desktop, or Colima where licensing ([§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)) or rootless policy matters.
- **Build systems:** Daemonless builders such as Buildah, Kaniko, and BuildKit rootless avoid mounting the Docker socket in CI.
- **System-container needs:** LXC/LXD (now also Incus, a community fork) for VM-like Linux hosts without a hypervisor.
- **Mixed estates are normal.** Docker for builds and local development, containerd for runtime; images flow between them via registries.

## 7. Security Considerations

- **Docker's root daemon is a large privileged target.** Socket access equals host root; membership in the `docker` group is effectively root ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md), [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Podman reduces that surface** with no daemon and default rootless operation using user namespaces, at the cost of some features (binding privileged ports, certain network modes) needing extra configuration.
- **Rootless is available on Docker too** ([§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)); it narrows the gap but is not the default install.
- **containerd standalone exposes a gRPC socket** (`/run/containerd/containerd.sock`), which is equally powerful and must be protected identically.
- **System containers (LXC) share the host kernel** just like Docker; unprivileged LXC uses user namespaces to contain root.
- **rkt is unmaintained.** Running archived software means no security patches; migrate off if any remains.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Diagnostic |
|---|---|---|
| `podman: short-name did not resolve` | No unqualified-search registries configured | Use fully qualified name; edit `/etc/containers/registries.conf` |
| Podman rootless cannot bind port 80 | Unprivileged ports start at 1024 | `sysctl net.ipv4.ip_unprivileged_port_start`; publish a high port or lower the sysctl |
| `ctr images ls` empty for Kubernetes images | Wrong containerd namespace | `sudo ctr -n k8s.io images ls` |
| `docker ps` fails on a Kubernetes node | No Docker daemon (containerd/CRI-O runtime) | `sudo crictl ps` |
| Compose file fails under Podman | Feature/plugin differences | `podman compose` or `podman-compose`; check the version and unsupported keys |
| Rootless container cannot pull or write layers | Missing `/etc/subuid` and `/etc/subgid` ranges | `grep $USER /etc/subuid /etc/subgid` |

## 9. Best Practices

- **Depend on OCI interfaces** (image spec, runtime spec, CRI) rather than a specific tool's features.
- Use **fully qualified image names** so behavior is identical across engines.
- Keep **build tooling and runtime separate**: build with Docker/BuildKit/Buildah, run on containerd or CRI-O.
- Prefer **rootless or daemonless tools in CI** to avoid exposing the Docker socket.
- Learn the **`crictl` and `ctr -n k8s.io`** equivalents before you need them during an incident.
- Test **Compose and Dockerfile portability** before committing to an engine migration.

## 10. Common Anti-Patterns / Mistakes

- **Choosing a runtime by brand rather than requirement.**
- **Mounting `/var/run/docker.sock` into CI containers** for convenience, granting host root.
- **Running LXC-style workloads (full OS, SSH, many services) in Docker** and fighting the model.
- **Assuming Podman is a drop-in for every Docker feature** (Swarm, some networking modes, Desktop extensions).
- **Alias-swapping (`alias docker=podman`) without testing Compose, volumes, and networking behavior.**
- **Leaving rkt-era tooling in production.**

## 11. Interview Questions

**🎯 Beginner:** _"What is the main architectural difference between Docker and Podman, and can Podman run the same images?"_
**Model answer:** Docker uses a central root daemon (dockerd) that clients talk to over a socket; Podman is daemonless and forks containers directly, and is rootless-friendly by default. Both use OCI-compatible images, so `podman run nginx` pulls from the same registries and `alias docker=podman` works for common commands. Podman also has pods, grouping containers that share namespaces like Kubernetes pods.
_What the interviewer is probing for:_ Knowing daemon vs. daemonless and OCI portability.

**🎯 Intermediate:** _"A Kubernetes node has no Docker installed. How do you list and debug containers on it?"_
**Model answer:** Nodes typically run containerd or CRI-O, so use `crictl ps`, `crictl logs <id>`, `crictl exec -it <id> sh`, and `crictl inspect`. For lower-level containerd access use `ctr -n k8s.io containers ls`, or `nerdctl --namespace k8s.io ps` for a Docker-like CLI. Point crictl at the runtime with `/etc/crictl.yaml` (`runtime-endpoint: unix:///run/containerd/containerd.sock`). Kubernetes containers live in the `k8s.io` namespace, not `moby`.
_What the interviewer is probing for:_ Practical fluency with CRI-level tooling.

**🎯 Senior:** _"Your CI build farm exposes the Docker socket to jobs. Compare Docker, rootless Podman, and standalone containerd as alternatives."_
**Model answer:** Socket exposure is root-equivalent, so builders should be rootless or daemonless. Rootless Podman/Buildah avoids a privileged daemon but has constraints: no privileged ports, slirp4netns/pasta network overhead, storage driver limits, and subuid/subgid setup. Docker with BuildKit gives the best cache and ecosystem, and can run rootless too. containerd alone runs images but lacks a build story, so it needs BuildKit or another builder. I would choose rootless BuildKit or Buildah on ephemeral runners with a remote cache.
_What the interviewer is probing for:_ Weighing security, ergonomics, and build features with concrete constraints.

**🎯 Architect:** _"Define a runtime strategy for developer laptops, CI, and production Kubernetes in a regulated multi-tenant company. How do you migrate off Docker Desktop for 2,000 developers?"_
**Model answer:** Standardize on OCI images everywhere; let developers choose Docker Desktop, Podman Desktop, Rancher Desktop, or Colima; use rootless builders in CI and containerd or CRI-O in production. For regulated tenants add sandboxed runtimes (gVisor/Kata), signed images, admission control, and no socket exposure. Migration: pilot a group, verify Compose and Testcontainers compatibility, provide a Docker-compatible socket, automate rollout via MDM with a rollback path, and track support tickets before widening.
_What the interviewer is probing for:_ Strategic use of standards, phased rollout, and compliance controls.
## 12. Common Misconceptions

- **"Podman is just Docker with a different name."** Its architecture (daemonless, fork-exec, pods) and default security model differ meaningfully.
- **"Kubernetes requires Docker."** It requires a CRI runtime; containerd and CRI-O are the norm.
- **"containerd can build images."** It runs and manages them; building needs BuildKit or another builder.
- **"LXC and Docker are competitors for the same job."** System containers and application containers serve different models.
- **"Rootless means fully safe."** It narrows privilege, but the shared kernel remains.
- **"rkt is a current alternative."** It was archived in 2020.

## 13. 🔑 Key Takeaways

- **Docker** is a full platform with a root daemon; **Podman** is daemonless and rootless-friendly; **containerd** is the runtime core; **CRI-O** is Kubernetes-only; **LXC** is for system containers; **rkt** is retired.
- OCI standards make images portable across all of them.
- Kubernetes nodes typically run containerd or CRI-O, not Docker.
- Rootless and daemonless designs reduce privileged attack surface.
- Choose by requirement, and depend on standards rather than brands.
- Know `crictl`, `ctr`, and `nerdctl` so a missing Docker daemon is never a blocker.

## 14. Related Concepts & What's Next

- [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) covers installing Docker Desktop, Docker Engine, and rootless mode.
- [§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md) covers the licensing changes that drive many Podman and Rancher Desktop evaluations.
- [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) details the dockerd, containerd, runc chain compared here; [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) covers containerd and the CRI's relationship to Kubernetes.
- [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) gives the OCI specs behind cross-tool portability; [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) covers daemon configuration and socket permissions.

**Next Section:** [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) — `Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md`
