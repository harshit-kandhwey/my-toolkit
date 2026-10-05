# Section 14 (Part 2): containerd and the CRI's Relationship to Kubernetes

## 1. Definition

**Plain language:** containerd is the daemon that actually manages containers on a host: it pulls images, stores them, sets up snapshots, and starts and supervises containers through a low-level runtime. Docker uses it internally. Kubernetes can use it directly, without Docker, through a standard interface called the CRI.

**Precise definition:**

- **containerd** is a CNCF-graduated, industry-standard container runtime daemon (originally extracted from Docker and donated to the CNCF in 2017; graduated in 2019). It exposes a gRPC API on a Unix socket (default `/run/containerd/containerd.sock`) and manages image transfer, content storage, snapshots, container metadata, tasks (running processes), and namespaces. It delegates actual container creation to an OCI runtime through **shims**, by default `containerd-shim-runc-v2` invoking runc.
- **CRI (Container Runtime Interface)** is a gRPC API defined by Kubernetes (`RuntimeService` and `ImageService`) that the **kubelet** uses to talk to a runtime. containerd implements it through a built-in CRI plugin (`io.containerd.grpc.v1.cri`). CRI-O is the other widely used CRI implementation.
- **dockershim** was the in-tree Kubernetes adapter that let the kubelet talk to Docker Engine. It was deprecated in Kubernetes 1.20 and removed in **Kubernetes 1.24** (2022). Docker Engine can still be used with Kubernetes through the external `cri-dockerd` adapter.

> 💡 **Tip:** Docker images are OCI images, so removing dockershim did not make existing Docker-built images stop working. Only the runtime that runs them changed.

## 2. Why This Matters

- **Kubernetes node debugging.** On modern clusters the node runtime is containerd, so `docker ps` shows nothing; you need `crictl` or `ctr`.
- **Clear mental model.** Docker is a developer-experience layer (CLI, build, Compose, networking, volumes) on top of containerd; Kubernetes needs only the runtime layer.
- **Smaller attack surface and footprint.** A Kubernetes node without `dockerd` runs fewer components.
- **Interview and certification relevance.** "Kubernetes deprecated Docker" is a frequent misunderstanding to be able to correct.
- **Extensibility.** containerd's plugin model (snapshotters, runtimes such as gVisor or Kata) explains how alternative sandboxes plug in.

## 3. Prerequisites and Dependencies

- [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) introduced the `dockerd` ► containerd ► runc chain; this section opens the middle box.
- [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) covers the Docker client and API, which sit above containerd and are not part of it.
- [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) defines the OCI runtime spec that shims and runc implement.
- [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) covers overlay2; containerd's equivalent is the **overlayfs snapshotter**.
- Basic Kubernetes vocabulary: node, pod, kubelet.

## 4. Architecture / Conceptual Diagram

```text
   Docker path                                Kubernetes path
 ┌──────────────┐                          ┌───────────────────┐
 │ docker CLI   │                          │      kubelet      │
 └──────┬───────┘                          └─────────┬─────────┘
        │ REST (docker.sock)                         │ CRI gRPC
        ▼                                            │
 ┌──────────────┐                                    │
 │   dockerd    │  build, compose, networks,         │
 │              │  volumes, API                      │
 └──────┬───────┘                                    │
        │ gRPC (containerd.sock)                     │
        ▼                                            ▼
 ┌────────────────────────────────────────────────────────────┐
 │                        containerd                          │
 │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌───────────────┐    │
 │  │ content │ │snapshot-│ │ metadata │ │  CRI plugin   │    │
 │  │  store  │ │  ters   │ │  (bolt)  │ │(for kubelet)  │    │
 │  └─────────┘ └─────────┘ └──────────┘ └───────────────┘    │
 └───────────────────────────┬────────────────────────────────┘
                             │ ttrpc
                  ┌──────────┴──────────┐
                  ▼                     ▼
        ┌──────────────────┐  ┌──────────────────┐
        │containerd-shim   │  │containerd-shim   │  one shim per
        │-runc-v2          │  │-runc-v2          │  pod or container
        └────────┬─────────┘  └────────┬─────────┘
                 ▼                     ▼
              ┌──────┐              ┌──────┐
              │ runc │              │ runc │  exits after start
              └──┬───┘              └──┬───┘
                 ▼                     ▼
          container process     container process
```

- **Shims decouple lifetimes.** The shim stays alive as the container's parent, holding stdio and exit status, so containerd (or dockerd) can restart without killing containers.
- **Namespaces in containerd.** containerd has its own API namespaces (not Linux namespaces): Docker uses `moby`, Kubernetes uses `k8s.io`. Containers created by one are invisible to the other unless you select the namespace.
- **Runtime classes.** Kubernetes `RuntimeClass` maps to containerd runtime handlers, letting some pods use Kata or gVisor.

## 5. Hands-On

### 5.1 Find containerd on a Docker host

```bash
$ systemctl status containerd --no-pager | head -4
● containerd.service - containerd container runtime
     Loaded: loaded (/lib/systemd/system/containerd.service; enabled)
     Active: active (running) since Mon 2026-09-21 08:02:11 UTC; 1d ago

$ docker info --format '{{.ContainerdCommit.ID}}'
7f4a0f3d5e1b...
$ ctr version
Client:
  Version:  v1.7.22
Server:
  Version:  v1.7.22
```

### 5.2 See Docker's containers through ctr

```bash
$ docker run -d --name web nginx:1.27
$ sudo ctr namespaces list
NAME LABELS
moby
$ sudo ctr -n moby containers list | head -3
CONTAINER      IMAGE    RUNTIME
9c1f0b...      -        io.containerd.runc.v2
$ sudo ctr -n moby tasks list
TASK        PID      STATUS
9c1f0b...   21873    RUNNING
```

The image column is `-` because dockerd, not containerd, tracks image references in the classic image store.

### 5.3 Use ctr as a standalone client

```bash
$ sudo ctr images pull docker.io/library/alpine:3.20
docker.io/library/alpine:3.20: resolved
done: 1.2s
$ sudo ctr run --rm -t docker.io/library/alpine:3.20 demo sh -c 'echo hi from containerd'
hi from containerd
$ sudo ctr images list -q
docker.io/library/alpine:3.20
```

`ctr` is a low-level debug tool with no networking setup by default; it is not a Docker replacement. `nerdctl` provides a Docker-compatible CLI on top of containerd.

### 5.4 Use crictl against the CRI (Kubernetes node)

```bash
$ cat /etc/crictl.yaml
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock

$ sudo crictl ps
CONTAINER      IMAGE          CREATED        STATE    NAME       POD ID
b3d2e1a4c5f6   4b9c...        2 hours ago    Running  coredns    7a1c9e0d2f33
$ sudo crictl pods
POD ID         CREATED        STATE   NAME                       NAMESPACE
7a1c9e0d2f33   2 hours ago    Ready   coredns-76f75df574-x2kqp   kube-system
$ sudo crictl images | head -3
IMAGE                        TAG      IMAGE ID       SIZE
registry.k8s.io/pause        3.9      e6f181688397   322kB
$ sudo ctr -n k8s.io containers list | wc -l
14
```

### 5.5 Inspect containerd's config

```bash
$ containerd config default | grep -n -E 'SystemdCgroup|snapshotter|sandbox_image' 
  sandbox_image = "registry.k8s.io/pause:3.9"
  snapshotter = "overlayfs"
            SystemdCgroup = false
```

On Kubernetes nodes using the systemd cgroup driver, set `SystemdCgroup = true` under `[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]` in `/etc/containerd/config.toml` and restart containerd. It must match the kubelet's `cgroupDriver` ([§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)).

### 5.6 Which runtime is my node using?

```bash
$ kubectl get nodes -o wide
NAME     STATUS   ROLES           VERSION   CONTAINER-RUNTIME
node-1   Ready    control-plane   v1.30.2   containerd://1.7.22
```

## 6. Production Usage Notes

- Managed Kubernetes (EKS, GKE, AKS) uses containerd on nodes today; do not assume `docker` exists there, and never depend on the Docker socket in pods.
- Tools that mounted `/var/run/docker.sock` (log shippers, CI builders, monitoring agents) break after the move to containerd; use CRI-aware alternatives or rootless builders such as BuildKit or Kaniko.
- Match the cgroup driver between kubelet and containerd; a mismatch causes unstable nodes.
- Keep the pause (sandbox) image and registry mirrors configured in `config.toml` for air-gapped clusters.
- On a Docker Engine host, upgrading containerd and dockerd independently is possible, but stay within supported version pairings.
- Monitor `/var/lib/containerd` disk usage the way you would `/var/lib/docker`.

## 7. Security Considerations

- **The containerd socket is root.** Anyone who can talk to `containerd.sock` can run privileged containers on the host; protect it like `docker.sock` ([§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Do not mount it into pods** unless there is a strong, reviewed reason.
- **Shim and runc CVEs** (for example the runc `/proc/self/exe` escape, CVE-2019-5736, and later runc container-escape fixes in 2024) require prompt patching of runc and containerd.
- **Sandboxed runtimes.** For multi-tenant clusters, use RuntimeClass with gVisor or Kata to add a kernel boundary.
- **Image trust.** Configure registry auth and pull policies in the CRI plugin; images pulled via CRI are not verified by Docker Content Trust.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker ps` empty on a K8s node | Runtime is containerd, not Docker | Use `crictl ps` or `ctr -n k8s.io` |
| `crictl` warns about default endpoints | No `/etc/crictl.yaml` | Create it with the socket path |
| Node flapping `NotReady` after upgrade | Cgroup driver mismatch | Align `SystemdCgroup` and kubelet `cgroupDriver` |
| `ImagePullBackOff` on private registry | Auth missing in CRI config | Use imagePullSecrets or `config.toml` registry config |
| `ctr` shows no containers for Docker | Wrong namespace | Use `-n moby` |
| Pod stuck `ContainerCreating`, `failed to create sandbox` | CNI missing or pause image unpullable | Check CNI config, `sandbox_image` access |
| Old pipeline fails with `Cannot connect to the Docker daemon` on node | Dockershim removed | Migrate to CRI-aware tooling or `cri-dockerd` |

```bash
$ sudo journalctl -u containerd --since "10 min ago" | tail
$ sudo crictl info | head
```

## 9. Best Practices

- Learn `crictl` for Kubernetes nodes and `ctr` or `nerdctl` for containerd debugging.
- Set `SystemdCgroup = true` on systemd hosts.
- Keep containerd, runc, and CNI plugins patched and version-tracked.
- Use `RuntimeClass` for workloads needing stronger isolation.
- Build images with BuildKit or Kaniko in CI instead of Docker-in-Docker on cluster nodes.
- Externalize config in `/etc/containerd/config.toml` using version 2 format and manage it through configuration management.

## 10. Common Anti-Patterns / Mistakes

- **Mounting `docker.sock` into pods** on containerd clusters (it does not exist, and where it does it is a root-equivalent hole).
- **Manually starting or deleting containers in `k8s.io` with `ctr`.** The kubelet will fight you.
- **Treating `ctr` as a daily driver.** It lacks Docker's UX and network defaults.
- **Assuming "Kubernetes dropped Docker support" means Docker images break.**
- **Editing `config.toml` without restarting** containerd and re-checking with `containerd config dump`.

## 11. Interview Questions

**🎯 Beginner:** _"What is containerd and how does it relate to Docker?"_
**Model answer:** containerd is a high-level container runtime daemon that manages images, snapshots, and container lifecycle, and calls a low-level runtime (runc) to create the process. `dockerd` sits on top of it and adds the API, build, networking, volumes, and Compose. You can see it with `ps` (`containerd`, `containerd-shim-runc-v2`) and talk to it directly with `ctr` or `nerdctl`. Kubernetes can use containerd without Docker at all.
_What the interviewer is probing for:_ The daemon layering: docker CLI, dockerd, containerd, shim, runc.

**🎯 Intermediate:** _"Why did Kubernetes remove dockershim, and what changes for someone who relied on `docker` commands on nodes?"_
**Model answer:** The kubelet spoke CRI, and dockershim was an in-tree adapter translating CRI to the Docker API, which was extra maintenance and an extra hop since Docker itself calls containerd. Removed in 1.24, kubelet now talks to containerd or CRI-O directly over the CRI socket. Images built with Docker still run because they are OCI images, but debugging on nodes uses `crictl ps`, `crictl logs`, and `crictl images` instead of `docker`. Anything mounting `/var/run/docker.sock` for builds or monitoring needs replacing.
_What the interviewer is probing for:_ Understanding CRI and the practical consequences of the migration.

**🎯 Senior:** _"Explain the role of the shim, and what happens to running containers if containerd or dockerd restarts."_
**Model answer:** Each container has a `containerd-shim-runc-v2` process that is the parent of the container process, holds its stdio and exit status, and reports back to containerd. Because the shim, not the daemon, owns the process, containers can survive a daemon restart, and containerd reconnects to the shims on startup. For `dockerd` itself, Docker exposes this as `live-restore` in `daemon.json`. Limitations are that live-restore cannot span major upgrades reliably and networking or port publishing changes are not applied while the daemon is down.
_What the interviewer is probing for:_ Knowledge of process ownership and upgrade behavior.

**🎯 Architect:** _"Design the runtime layer for a Kubernetes fleet that needs both standard and strongly isolated workloads."_
**Model answer:** Standardize on containerd with CRI, and define multiple runtime handlers in its config, for example `runc` as default and `runsc` (gVisor) or `kata` for untrusted workloads. In Kubernetes, expose them through `RuntimeClass` objects and let pods opt in with `runtimeClassName`, with admission policy forcing it for specific namespaces. Keep versions of containerd, runc, and kernel pinned and patched together, and use `crictl` plus node-level metrics for debugging. The trade-off is higher startup and syscall overhead and scheduling complexity, so isolate only the workloads that need it.
_What the interviewer is probing for:_ Architecture around CRI, RuntimeClass, and runtime choice.

## 12. Common Misconceptions

- **"Kubernetes deprecated Docker images."** It removed the Docker Engine integration, not image support.
- **"containerd is a replacement for Docker."** It is a component of Docker; it has no build or Compose features.
- **"containerd and runc are the same."** containerd supervises; runc creates the container process.
- **"The CRI is a CLI."** It is a gRPC API; `crictl` is a client for it.
- **"Docker and Kubernetes see the same containers on one host."** Separate containerd namespaces isolate them.

## 13. 🔑 Key Takeaways

- containerd manages image storage, snapshots, and container lifecycle, and delegates execution to runc via shims.
- dockerd sits above containerd; Kubernetes' kubelet talks to containerd through the CRI plugin.
- dockershim was removed in Kubernetes 1.24; `cri-dockerd` is the external adapter if needed.
- Use `crictl` (CRI view) and `ctr -n <ns>` (containerd view) for debugging.
- Docker uses namespace `moby`; Kubernetes uses `k8s.io`.
- Align cgroup drivers and protect the socket.

## 14. Related Concepts & What's Next

- [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (engine architecture) shows the overall chain; [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) (OCI specs) defines what shims and runc implement.
- [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) (overlay2) has the snapshotter counterpart; [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) covers the daemon configuration and socket permissions that also govern access to runtime sockets.
- Later material on Docker vs. Podman vs. standalone containerd and on the path from Docker to orchestration builds on this section.

**Next Section:** [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) — `Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md`
