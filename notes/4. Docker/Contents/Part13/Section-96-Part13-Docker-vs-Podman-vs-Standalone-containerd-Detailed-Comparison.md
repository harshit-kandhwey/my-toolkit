# Section 96 (Part 13): Docker vs. Podman vs. Standalone containerd: Detailed Comparison

## 1. Definition

**Plain language:** Docker, Podman and containerd all run OCI containers on Linux, but they sit at different layers. Docker is a full developer platform (CLI, daemon, build, Compose, Desktop). Podman is a daemonless, rootless-first engine with a Docker-compatible CLI. containerd is a low-level runtime manager with no developer UX, meant to be embedded by something else such as Kubernetes.

**Precise definition:** All three ultimately start containers through an OCI runtime (`runc` by default, or `crun`, `youki`, `gVisor`, `kata`) per the OCI Runtime Spec ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). They differ in process model and scope:

- **Docker Engine:** a long-running `dockerd` that owns images, networks, volumes, build (BuildKit) and the REST API, and delegates container execution to `containerd` and `runc` ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)).
- **Podman:** a fork-exec tool with no central daemon. Each `podman run` spawns a per-container monitor (`conmon`) that supervises the OCI runtime. State lives in on-disk databases (containers/storage, BoltDB or SQLite), and a socket-activated REST service exists only if you ask for it.
- **containerd (standalone):** a daemon exposing a gRPC API for image pull, snapshots, content store, tasks and CRI. Its bundled CLI `ctr` is a debugging tool, and `nerdctl` is the Docker-compatible CLI that adds Compose, build and networking on top.

> 💡 **Tip:** Compare them by asking "what owns the container's parent process and who can talk to it?" That one question explains most of the security and operational differences.

## 2. Why This Matters

- Since Kubernetes removed dockershim (v1.24), clusters run containerd or CRI-O directly; knowing the layers explains why `docker ps` shows nothing on a node.
- Licensing and rootless requirements push regulated and enterprise teams toward Podman or Docker Engine without Docker Desktop ([§6](../Part1/Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)).
- "Replace Docker with Podman" is a common migration request; the real gaps (Compose behavior, BuildKit features, socket consumers) decide whether it is a one-day or a three-month project.
- Interviewers use this comparison to test whether you understand the stack or only the CLI.

## 3. Prerequisites and Dependencies

Requires the positioning overview in [§3](../Part1/Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md), the engine architecture in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), containerd and CRI in [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md), and user namespaces in [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md). Rootless background is in [§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) and [§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md). Build behavior is in [§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md) and [§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md).

## 4. Architecture / Conceptual Diagram

```text
 DOCKER                         PODMAN                       CONTAINERD (+ nerdctl)
 ┌──────────────┐               ┌──────────────┐             ┌──────────────┐
 │ docker CLI   │               │ podman CLI   │             │ nerdctl / ctr│
 └──────┬───────┘               └──────┬───────┘             │ kubelet(CRI) │
        │ REST /var/run/docker.sock    │ fork/exec           └──────┬───────┘
        ▼                              │ (optional REST socket)     │ gRPC
 ┌──────────────┐                      │                            ▼
 │ dockerd      │ images, nets,        │                     ┌──────────────┐
 │ (root daemon)│ volumes, BuildKit    │                     │ containerd   │
 └──────┬───────┘                      │                     │ (root daemon)│
        │ gRPC                         ▼                     └──────┬───────┘
        ▼                       ┌──────────────┐                    │ shim v2
 ┌──────────────┐               │ conmon       │ one per            ▼
 │ containerd   │               │ (per ctr)    │ container   ┌──────────────┐
 └──────┬───────┘               └──────┬───────┘             │ containerd-  │
        │ shim v2                      │                     │ shim-runc-v2 │
        ▼                              ▼                     └──────┬───────┘
 ┌──────────────┐               ┌──────────────┐                    ▼
 │ runc / crun  │               │ runc / crun  │             ┌──────────────┐
 └──────────────┘               └──────────────┘             │ runc / crun  │
                                                             └──────────────┘
 Single point of failure:        No central daemon:           Daemon but no build,
 dockerd (live-restore helps)    each ctr is independent      no compose without nerdctl

 Feature positioning
 ┌─────────────────────┬────────────┬────────────┬───────────────────────┐
 │ Capability          │ Docker     │ Podman     │ containerd+nerdctl    │
 ├─────────────────────┼────────────┼────────────┼───────────────────────┤
 │ Daemonless          │ no         │ yes        │ no (but no dockerd)   │
 │ Rootless            │ supported  │ default    │ supported             │
 │ Pods (K8s-style)    │ no         │ yes        │ no                    │
 │ Build engine        │ BuildKit   │ Buildah    │ BuildKit (buildkitd)  │
 │ Compose             │ v2 plugin  │ podman-compose / compose provider │ nerdctl compose │
 │ Swarm               │ yes        │ no         │ no                    │
 │ systemd integration │ via unit   │ Quadlet    │ via unit              │
 │ K8s CRI             │ cri-dockerd│ no (CRI-O) │ native                │
 └─────────────────────┴────────────┴────────────┴───────────────────────┘
```

- **Docker** adds the most between the user and runc, which is exactly where its UX comes from.
- **Podman** reuses libraries shared with CRI-O and Buildah (`containers/image`, `containers/storage`, `netavark`), so its images and local storage are not shared with Docker's.
- **containerd** is what Docker itself uses; installing Docker already installs it, so both can coexist on one host in separate namespaces (`moby` vs `k8s.io`).

## 5. Hands-On

### 5.1 See Which Runtime a Host Actually Uses

```bash
docker info --format '{{.DefaultRuntime}} {{.ContainerdCommit.ID}} {{.Driver}} {{.CgroupVersion}}'
podman info --format '{{.Host.OCIRuntime.Name}} {{.Host.CgroupsVersion}} {{.Store.GraphDriverName}} rootless={{.Host.Security.Rootless}}'
sudo ctr version
```

```text
runc 1c4457e... overlay2 2
crun 2 overlay rootless=true
Client: Version: v1.7.x  Server: Version: v1.7.x
```

### 5.2 Podman Uses the Docker CLI Vocabulary

```bash
podman run --rm -d --name web -p 8080:80 docker.io/library/nginx:1.27-alpine
podman ps
podman logs web | head -3
podman stop web
alias docker=podman         # works for most day-to-day commands
```

```text
CONTAINER ID  IMAGE                           COMMAND               STATUS        PORTS                 NAMES
3a1f9c2b7d4e  docker.io/library/nginx:1.27-alpine  nginx -g daemon o...  Up 2 seconds  0.0.0.0:8080->80/tcp  web
```

Podman requires fully qualified image names or a configured `unqualified-search-registries` in `/etc/containers/registries.conf`; Docker silently assumes `docker.io`.

### 5.3 Rootless Podman and UID Mapping

```bash
podman unshare cat /proc/self/uid_map
grep "^$USER:" /etc/subuid
podman run --rm alpine id
ps -o user,pid,cmd -C conmon
```

```text
         0       1000          1
         1     100000      65536
harsh:100000:65536
uid=0(root) gid=0(root) groups=0(root)
harsh    48211 /usr/bin/conmon --api-version 1 -c 6f...
```

Root inside the container is the invoking user outside, with the rest mapped from the `subuid` range.

### 5.4 Pods and Kubernetes YAML Round-Trip (Podman)

```bash
podman pod create --name demo -p 8080:80
podman run -d --pod demo --name app docker.io/library/nginx:1.27-alpine
podman generate kube demo > demo.yaml     # Kubernetes Pod manifest
podman kube play demo.yaml                # replay it elsewhere
```

This pod model (shared network namespace, `infra` container) has no Docker equivalent, and it is the main reason developers prototype Kubernetes workloads with Podman.

### 5.5 Systemd Integration with Quadlet

```ini
# ~/.config/containers/systemd/web.container
[Unit]
Description=Web

[Container]
Image=docker.io/library/nginx:1.27-alpine
PublishPort=8080:80
ReadOnly=true

[Service]
Restart=always

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user start web.service
systemctl --user status web.service --no-pager | head -5
```

Quadlet replaced the older `podman generate systemd` approach. Systemd becomes the supervisor, which removes the need for Docker restart policies and a daemon.

### 5.6 Standalone containerd with nerdctl

```bash
sudo nerdctl run --rm -d --name web -p 8080:80 nginx:1.27-alpine
sudo nerdctl ps
sudo nerdctl compose -f compose.yaml up -d
sudo ctr -n default containers ls
sudo ctr -n k8s.io containers ls | head      # containers Kubernetes created on a node
sudo crictl ps                                # CRI view, the right tool on a K8s node
```

`ctr` has no port publishing or networking; it is a debugging aid. `nerdctl` adds the CNI-based networking, Compose and lazy-pulling (eStargz) features that make containerd usable standalone.

### 5.7 Compatibility Check Before Migrating

```bash
# Who talks to the Docker socket on this host?
sudo ss -xp | grep docker.sock
grep -rn "docker.sock" /etc /opt ~/ci 2>/dev/null | head

# Point Docker-API tools at Podman
systemctl --user enable --now podman.socket
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
docker version        # the real docker CLI now talks to Podman
```

Socket consumers (Traefik, Portainer, CI agents, Testcontainers) are the usual migration blockers. The Podman socket covers most of the Docker API but not Swarm endpoints.

## 6. Production Usage Notes

- **Kubernetes nodes:** use containerd (or CRI-O). Docker on a node adds a daemon you do not need; use `crictl` and `ctr -n k8s.io` for node debugging.
- **Single-host services:** Docker Engine with Compose is the lowest-friction choice; Podman with Quadlet is the better fit when systemd is already the fleet's process manager.
- **RHEL, Fedora, CentOS Stream:** Podman is the vendor-supported engine, Docker Engine is not shipped in the base repositories, and SELinux integration is first class.
- **CI:** rootless Podman or Buildah avoid privileged builders and the Docker-socket exposure discussed in [§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md).
- **Daemon crashes:** `dockerd` restarts can stop containers unless `live-restore` is set in `daemon.json`; Podman containers are independent processes and survive the CLI.
- **Image storage is per tool.** Images pulled with Docker are invisible to Podman and containerd; use a registry, `podman save`/`docker save` or `skopeo copy` to move them.
- **Docker Desktop alternatives:** Podman Desktop, Rancher Desktop (containerd or moby backend) and Colima/Lima cover developer laptops where Desktop licensing matters.

## 7. Security Considerations

- **Docker socket = root.** Anyone able to reach `/var/run/docker.sock` can start a privileged container with the host root mounted. Rootless Docker and Podman limit the blast radius to the invoking user.
- **Podman rootless by default** maps container root to an unprivileged UID, so a container escape yields a normal user, not host root. Docker rootless gives the same property but is opt-in and has limitations (no `--net=host` privilege, slirp4netns/pasta networking, restricted ports below 1024 unless sysctl is set).
- **No daemon** means no always-on root-owned API listening; the attack surface becomes the setuid helpers (`newuidmap`, `newgidmap`) and the optional socket service.
- **Default seccomp and capability sets** are broadly similar across the three but not identical; verify with `capsh --decode` rather than assuming ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§60](../Part8/Section-60-Part8-Seccomp-Profiles.md)).
- **SELinux/AppArmor:** Podman on RHEL-family hosts applies `container_t` labels and `:Z`/`:z` volume relabeling by default workflows; Docker on Ubuntu relies on the `docker-default` AppArmor profile ([§61](../Part8/Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)).
- **Registry trust:** Podman supports `policy.json` signature verification (sigstore, GPG) natively; Docker Content Trust is a separate Notary mechanism ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **containerd's gRPC socket** (`/run/containerd/containerd.sock`) is equally root-equivalent; treat it like the Docker socket.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `short-name "nginx" did not resolve` (Podman) | No unqualified-search registry configured | Use `docker.io/library/nginx` or set `unqualified-search-registries` |
| Rootless Podman cannot bind port 80 | Unprivileged port floor is 1024 | `sysctl net.ipv4.ip_unprivileged_port_start=80` or publish a high port behind a proxy |
| `ERRO[0000] cannot find UID/GID for user` | No `/etc/subuid` and `/etc/subgid` entry | `usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $USER`, then `podman system migrate` |
| Volume permission errors in rootless mode | UID mapping shifts ownership | Use `:U`, `--userns=keep-id`, or `podman unshare chown` |
| `docker compose` fails against Podman | Compose uses BuildKit/Engine APIs Podman lacks | Use `podman compose` with a provider, or point at the Podman socket and test |
| Image missing after switching tools | Separate storage per engine | Push to a registry or `skopeo copy` |
| `ctr run` container has no network | `ctr` does not configure CNI | Use `nerdctl`, or CNI plugins explicitly |
| `crictl` says "unable to determine runtime API version" | Missing `/etc/crictl.yaml` | Set `runtime-endpoint: unix:///run/containerd/containerd.sock` |
| Testcontainers fails under Podman | Needs Ryuk privileges or socket path | Set `DOCKER_HOST`, `TESTCONTAINERS_RYUK_DISABLED=true` or use the rootful socket |

## 9. Best Practices

- Pick by role: Docker for developer workflow and single-host Compose, containerd for Kubernetes nodes, Podman for rootless, daemonless and systemd-native hosts.
- Always use fully qualified image references so tools behave identically.
- Standardize on OCI images and registries as the interchange format; never depend on one engine's local storage.
- Prefer rootless mode anywhere the workload allows it.
- Pin runtimes and versions (`containerd`, `runc`/`crun`) and track runc CVEs.
- Keep the Docker-socket consumer inventory (CI agents, dashboards, proxies) before any engine migration.
- Test migrations in a throwaway VM or container, not on a production host.
- Verify cgroup v2 on every engine ([§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)); resource-limit behavior under rootless depends on systemd delegation.

## 10. Common Anti-Patterns / Mistakes

- `alias docker=podman` as a migration plan with no testing of Compose files, build features or socket consumers.
- Running Docker on Kubernetes nodes since 1.24 "for debugging convenience".
- Using `ctr` as if it were Docker and concluding containerd "has no networking".
- Mounting the Docker or containerd socket into application containers to "manage" siblings.
- Assuming images and volumes are shared between Docker and Podman on the same machine.
- Choosing an engine by popularity or by a single benchmark rather than by operational requirements.
- Running rootless Podman without `loginctl enable-linger`, so containers die when the user logs out.
- Treating Podman pods as a substitute for Kubernetes scheduling, health management or scaling.

## 11. Interview Questions

**🎯 Beginner:** _"What is the practical difference between Docker and Podman?"_
**Model answer:** Docker uses a central root daemon (`dockerd`) that the CLI talks to over a socket, and that daemon delegates to containerd and runc. Podman has no daemon: the CLI forks a `conmon` monitor and the OCI runtime directly, and it runs rootless by default. The CLI vocabulary is nearly identical, so most `docker run`, `ps` and `build` habits transfer. Podman also adds pods and Quadlet systemd integration, while Docker adds Swarm, Docker Desktop and the BuildKit-native Compose workflow. Both produce standard OCI images that any registry accepts.
_What the interviewer is probing for:_ The daemon versus daemonless model, and that the images are interoperable.

**🎯 Intermediate:** _"Kubernetes dropped Docker support. Does that mean our Docker-built images stop working?"_
**Model answer:** No. Kubernetes removed dockershim, the in-tree adapter between the kubelet and Docker Engine. The kubelet now talks CRI directly to containerd or CRI-O. Docker-built images are OCI-compliant, so they run unchanged. What changes is on the nodes: `docker ps` shows nothing, so use `crictl` or `ctr -n k8s.io`. Anything relying on the Docker socket on a node (log shippers, build-in-cluster jobs, docker-in-docker tools) breaks and must move to a different mechanism such as Kaniko, BuildKit or Buildah. Docker could still be used via `cri-dockerd` if truly necessary, but it is an extra layer with no benefit.
_What the interviewer is probing for:_ Distinguishing image format from runtime, and knowing the operational fallout.

**🎯 Senior:** _"A security team wants Docker removed from build servers and replaced with rootless Podman. What would you check before agreeing, and what would you keep?"_
**Model answer:** First inventory consumers of the Docker socket and API: CI agents, `docker compose` files, Testcontainers, Dockerfiles that use BuildKit-only syntax (`RUN --mount=type=cache`, `--mount=type=secret`, heredocs), and scripts that parse `docker` output. Podman builds with Buildah, which supports most of the Dockerfile frontend but differs on cache mounts, `--ssh` and exporter options, so run representative builds and compare image digests and timings. Check rootless constraints: subuid ranges, unprivileged ports, storage on a filesystem that supports overlay with fuse-overlayfs or native overlay, and `loginctl enable-linger` for background jobs. I would keep a standalone BuildKit (`buildkitd` rootless) as an option when cache and multi-platform features matter. Roll out per pipeline with the old path as a fallback, and compare scan results and SBOMs to prove outputs match.
_What the interviewer is probing for:_ Migration risk analysis beyond "the CLI is the same", including build-feature gaps.

**🎯 Architect:** _"Design the container runtime strategy for a company with developer laptops, CI, a few RHEL VM fleets and three Kubernetes clusters."_
**Model answer:** Standardize on the OCI image and registry as the contract, so the runtime is a per-environment decision. Laptops: Docker Desktop where licensed, otherwise Podman Desktop or Rancher Desktop, all validated against one reference Compose and devcontainer setup. CI: rootless, ephemeral builders using BuildKit or Buildah with registry-backed caches and no Docker socket mounts. RHEL fleets: Podman with Quadlet units managed by configuration management, SELinux enforcing, and auto-update timers for image refresh. Kubernetes: containerd on all nodes (or CRI-O on OpenShift), a pinned runc/crun version policy, and optionally a sandboxed runtime class (gVisor or Kata) for untrusted workloads. Add admission and registry policy (signature verification, SBOM, vulnerability gates) that is runtime-agnostic. Track the exit cost of each choice: licensing for Desktop, vendor support for RHEL, and the skills to operate containerd directly.
_What the interviewer is probing for:_ Treating the runtime as a replaceable layer behind open standards, with per-environment justification.

## 12. Common Misconceptions

- "Podman is a different container technology." It runs the same OCI images through the same runc or crun.
- "Docker is dead because Kubernetes dropped it." Only the dockershim integration was removed; Docker remains the main developer tool and builds the images clusters run.
- "Daemonless means more secure automatically." The setuid helpers and misconfigured rootful Podman still matter; rootless is the real benefit, and Docker offers it too.
- "containerd is a replacement for Docker on my laptop." Without `nerdctl` it has no build, no Compose and no friendly networking.
- "`alias docker=podman` is a full drop-in." Compose, BuildKit features, Swarm and socket consumers all differ.
- "Docker and Podman share images on one host." Each keeps its own storage.

## 13. 🔑 Key Takeaways

- Docker = platform (dockerd + containerd + runc + BuildKit + Compose); Podman = daemonless, rootless-first, pods and Quadlet; containerd = embeddable runtime for Kubernetes and tools like nerdctl.
- All three run OCI images; the registry is the portable interface.
- Kubernetes nodes use containerd or CRI-O; use `crictl` there, not `docker`.
- Rootless is the main security differentiator, and it is available (with trade-offs) in both Docker and Podman.
- Migration risk lives in socket consumers, BuildKit-only Dockerfile features and Compose behavior.
- Image and volume storage is per engine, so move data through registries, not local copies.

## 14. Related Concepts & What's Next

Related: positioning overview ([§3](../Part1/Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md)), engine architecture ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), containerd and CRI ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)), rootless installation ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)), multi-arch builds with buildx ([§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)), and the orchestration path ([§99](Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)). Next, [§97](Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md) looks at the cases where none of these engines is the right answer.

**Next Section:** [§97](Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md) — `Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md`
