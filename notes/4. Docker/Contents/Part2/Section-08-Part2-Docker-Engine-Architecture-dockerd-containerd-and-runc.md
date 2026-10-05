# Section 8 (Part 2): Docker Engine Architecture: dockerd, containerd, and runc

## 1. Definition

**Plain language:** When you type `docker run`, several separate programs cooperate to start your container. The `docker` command only sends a request. A long-running daemon called `dockerd` handles images, networks, and volumes. It hands the actual container lifecycle to `containerd`, which in turn uses `containerd-shim` processes and the low-level tool `runc` to ask the Linux kernel to create the isolated process.

**Precise definition:** The **Docker Engine** is a layered system: `dockerd` (the high-level daemon exposing the REST API described in [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)) delegates container and image lifecycle management to **containerd**, a separate daemon with its own gRPC API. containerd starts each container through a per-container **shim** (`containerd-shim-runc-v2`), which invokes an OCI runtime, by default **runc** (specification in [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), to set up namespaces ([§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), cgroups ([§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)), and the root filesystem ([§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)) and then `exec` the container's entrypoint. Once the container process is running, runc exits and the shim remains as its parent, so the container survives restarts of dockerd and containerd.

> 💡 **Tip:** Remember the chain as "CLI ► dockerd ► containerd ► shim ► runc ► your process". Every troubleshooting question about "who owns this process" is answered by walking that chain.

## 2. Why This Matters

- **It explains what actually restarts.** Because the shim, not dockerd, is the parent of the container, restarting dockerd with live-restore enabled does not kill running containers.
- **It clarifies where bugs live.** Image pull and build problems live in dockerd/BuildKit, container start failures often come from runc, and unresponsive containers often relate to the shim or the kernel.
- **It makes Kubernetes comprehensible.** Kubernetes talks to containerd (or CRI-O) directly and does not need dockerd at all ([§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).
- **It defines the attack surface.** Each component runs with elevated privilege, and the socket exposing dockerd is a root-equivalent entry point.
- **It informs logging and monitoring.** Daemon logs, containerd logs, and container logs are three different streams, collected in different places.

## 3. Prerequisites and Dependencies

Requires [§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md) (the container model), [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) (namespaces, cgroups, networking basics), and [§3](../Part1/Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) (how containerd and Podman relate to Docker). This section is the foundation for [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) (the API in front of dockerd), [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) (the OCI specs that runc implements), [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md)-[§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) (the kernel features runc drives), and [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) (containerd as a standalone runtime).

## 4. Architecture / Conceptual Diagram

```text
   docker CLI  ──REST over /var/run/docker.sock──►  dockerd
   (client)                                          │  images, networks,
                                                     │  volumes, build, API
                                                     ▼  gRPC (containerd.sock)
                                                 containerd
                                                     │  image store, snapshots,
                                                     │  container lifecycle
                                     ┌───────────────┼───────────────┐
                                     ▼               ▼               ▼
                            containerd-shim   containerd-shim   containerd-shim
                                 (per container, stays alive)
                                     │               │               │
                                     ▼ runc create/start (then exits)
                                   ┌────────┐   ┌────────┐     ┌────────┐
                                   │ nginx  │   │ redis  │     │  app   │
                                   │  PID 1 │   │  PID 1 │     │  PID 1 │
                                   └────────┘   └────────┘     └────────┘
                                        Linux kernel: namespaces, cgroups,
                                        overlayfs, seccomp, capabilities
```

- **dockerd is the "Docker-specific" layer.** Networking (bridge, overlay), volumes, Swarm, and the classic build front-end live here.
- **containerd is the reusable runtime layer.** It is what Kubernetes uses and can be run without Docker at all.
- **The shim decouples containers from daemons.** It keeps stdio open, reports the exit code, and reaps the process, allowing daemon upgrades without container downtime.
- **runc is short-lived.** It sets up isolation, execs your process, and exits.

## 5. Hands-On

### 5.1 Inspect the Running Components

**Purpose:** See the chain of processes on a host with one container running.

**Syntax:**

```bash
docker run -d --name web nginx:1.27
ps -eo pid,ppid,cmd | grep -E 'dockerd|containerd|nginx' | grep -v grep
```

**Example usage and expected output:**

```bash
$ ps -eo pid,ppid,cmd | grep -E 'dockerd|containerd|nginx' | grep -v grep
    812       1 /usr/bin/containerd
    955       1 /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
   2140       1 /usr/bin/containerd-shim-runc-v2 -namespace moby -id 9c1f... -address /run/containerd/containerd.sock
   2162    2140 nginx: master process nginx -g daemon off;
   2201    2162 nginx: worker process
```

**Production usage example:** When a container "hangs" and `docker stop` fails, this listing shows whether the shim and the container process still exist, helping you decide between `docker kill`, killing the shim, or investigating a stuck kernel operation.

**Common errors:** Empty output usually means Docker Desktop, where these processes run inside a VM rather than on your host.

### 5.2 Ask the Engine About Its Runtime

**Purpose:** Discover the runtime and containerd version in use.

**Syntax:**

```bash
docker info --format 'runtimes={{json .Runtimes}} default={{.DefaultRuntime}}'
docker version --format '{{range .Server.Components}}{{.Name}} {{.Version}}{{"\n"}}{{end}}'
```

**Example usage and expected output:**

```bash
$ docker info --format 'runtimes={{json .Runtimes}} default={{.DefaultRuntime}}'
runtimes={"io.containerd.runc.v2":{"path":"runc"},"runc":{"path":"runc"}} default=runc

$ docker version --format '{{range .Server.Components}}{{.Name}} {{.Version}}{{"\n"}}{{end}}'
Engine 27.3.1
containerd 1.7.22
runc 1.1.14
docker-init 0.19.0
```

**Production usage example:** Security advisories frequently target runc or containerd versions; this output is what you compare to the advisory to decide whether a host is affected.

**Common errors:** If `containerd` is missing from the list, the engine is using an external containerd or an unusual packaging; check `docker info` for details.

### 5.3 Talk to containerd Directly with `ctr`

**Purpose:** Prove that containerd works independently of dockerd and see Docker's containers in the `moby` namespace.

**Syntax:**

```bash
sudo ctr namespaces ls
sudo ctr -n moby containers ls
sudo ctr -n moby tasks ls
```

**Example usage and expected output:**

```bash
$ sudo ctr namespaces ls
NAME LABELS
moby

$ sudo ctr -n moby tasks ls
TASK                                                                PID     STATUS
9c1f5a4e0b7d2c...                                                   2162    RUNNING
```

**Production usage example:** When dockerd is down or wedged, `ctr` (or `nerdctl`) still lets you list and inspect containers to confirm they survived.

**Common errors:** `ctr: failed to dial "/run/containerd/containerd.sock"` means containerd is not running or you lack root. Note that containers created by Kubernetes appear in the `k8s.io` namespace instead.

### 5.4 Observe Live Restore

**Purpose:** Demonstrate that containers outlive a dockerd restart when live restore is enabled.

**Syntax:**

```bash
# /etc/docker/daemon.json contains: { "live-restore": true }
sudo systemctl restart docker
docker ps
```

**Example usage and expected output:**

```bash
$ sudo systemctl restart docker
$ docker ps
CONTAINER ID   IMAGE        COMMAND                  CREATED         STATUS         PORTS    NAMES
9c1f5a4e0b7d   nginx:1.27   "/docker-entrypoint.…"   5 minutes ago   Up 5 minutes   80/tcp   web
```

**Production usage example:** Enabling `live-restore` lets you patch dockerd without restarting every workload on a single-host deployment. Details on daemon settings are in [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md).

**Common errors:** Live restore is not supported together with Swarm mode, and changes to certain daemon options still require container restarts.

## 6. Production Usage Notes

- **Pin and track versions of all three components.** dockerd, containerd, and runc are packaged together on most distributions, but they have independent release cadences and advisories.
- **Use `live-restore` on single hosts** where brief daemon restarts must not disrupt workloads.
- **Collect logs from journald for `docker.service` and `containerd.service`** in addition to container logs.
- **Kubernetes nodes can drop dockerd entirely.** Running containerd alone shrinks the attack surface and resource footprint ([§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).
- **Docker Desktop hides this layout inside a VM,** so use `docker run --privileged --pid=host` debug containers or the Desktop tooling to inspect processes.

## 7. Security Considerations

- **Access to the dockerd socket is equivalent to root on the host.** Anyone who can create a container can mount `/` into it.
- **runc has had container-escape vulnerabilities.** A well-known example is CVE-2019-5736, which allowed a malicious container to overwrite the host runc binary. Keep runc patched.
- **Shims and containerd run as root by default.** Rootless mode ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)) moves the whole stack into a user namespace.
- **Restrict who can talk to containerd.sock** in the same way as docker.sock.
- **Use default seccomp and capability profiles;** they are applied by the runtime when it sets up the container.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Diagnostic |
|---|---|---|
| `Cannot connect to the Docker daemon` | dockerd not running or wrong socket | `systemctl status docker`, `ls -l /var/run/docker.sock` |
| `OCI runtime create failed` | runc could not set up the container (bad mount, missing binary) | Read the full error, `journalctl -u docker` |
| `docker stop` hangs | PID 1 ignores SIGTERM | `docker kill`, fix the entrypoint signal handling |
| Containers vanish after upgrade | live-restore disabled | Enable it, plan maintenance windows |
| Zombie shim process | Container process stuck in uninterruptible I/O | Check `dmesg`, storage backend health |

## 9. Best Practices

- Keep dockerd, containerd, and runc updated through your package manager.
- Enable `live-restore` where Swarm is not in use.
- Monitor the health of the daemon and containerd as first-class services.
- Use `docker info` and `docker version` in automated fleet audits.
- Keep a debug runbook that includes `ps`, `ctr`, and `journalctl` steps for the whole chain.

## 10. Common Anti-Patterns / Mistakes

- **Assuming Docker is one binary.** Debugging stalls when you look in the wrong component.
- **Mounting `/var/run/docker.sock` into application containers** for convenience, which gives them host-level control.
- **Killing the shim to "clean up".** This orphans the container process and can corrupt state.
- **Running old runc for compatibility** and ignoring security advisories.
- **Confusing container namespaces with kernel namespaces** when reading `ctr namespaces ls`.

## 11. Interview Questions

**🎯 Beginner:** _"When you run `docker run nginx`, which components are involved and what does each do?"_
**Model answer:** The CLI sends a REST request to dockerd, which handles images, networks, and volumes and delegates the lifecycle to containerd. containerd creates a shim process and invokes runc, the OCI runtime, which sets up namespaces and cgroups, starts the process, then exits. You can see it with `ps -ef --forest | grep -E 'dockerd|containerd|shim|nginx'`. The shim, not dockerd, is the container's parent.
_What the interviewer is probing for:_ Ability to trace the chain and place each component's role.

**🎯 Intermediate:** _"After restarting dockerd for a config change, all your containers died. How do you avoid that, and why does the shim matter?"_
**Model answer:** Enable live-restore in `/etc/docker/daemon.json` (`"live-restore": true`) so containers keep running while dockerd is down. This works because the shim keeps the container's stdio and exit status independent of the daemons, and the process is parented to the shim, not dockerd. Live-restore does not cover every change and is incompatible with Swarm mode. Verify with `docker info | grep -i live`.
_What the interviewer is probing for:_ Connecting shim design to operational behavior like daemon upgrades.

**🎯 Senior:** _"After a dockerd crash, `docker ps` is empty but users say the service is still responding. What do you check and how do you recover?"_
**Model answer:** Check whether the container processes and shims survive: `ps -ef | grep containerd-shim`, `ctr -n moby containers ls`, and `ctr -n moby tasks ls`. If containerd and the shims are alive, restart dockerd and it should re-adopt them if state is intact; otherwise run `journalctl -u docker` for the failure and check `/var/lib/docker` health and disk space. Avoid removing the surviving containers until state is understood. Follow up by enabling live-restore and alerting on dockerd health.
_What the interviewer is probing for:_ Structured debugging across the layered architecture.

**🎯 Architect:** _"A runc container-escape CVE is announced (like CVE-2019-5736), and you run untrusted workloads on shared hosts. What is your response and long-term posture?"_
**Model answer:** Immediate: identify versions with `docker version` and `runc --version`, patch runc and containerd through packages, restart affected containers as required, and assess exploitation likelihood from logs. Long-term: treat runc and containerd as privileged components with rapid patch SLAs, use rootless mode and user namespaces to reduce impact, and run untrusted code under gVisor or Kata via an alternative OCI runtime. Also restrict image sources and capabilities to narrow the exploit path.
_What the interviewer is probing for:_ Combining incident response with a hardening strategy for the runtime layer.
## 12. Common Misconceptions

- **"Docker is a hypervisor."** It uses kernel features on the shared host kernel ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)).
- **"Restarting dockerd always kills containers."** Not with live-restore.
- **"containerd is a Docker product only."** It is a CNCF graduated project used by Kubernetes and others.
- **"runc keeps running as long as the container does."** It exits after starting the process.

## 13. 🔑 Key Takeaways

- The Engine is layered: CLI, dockerd, containerd, shim, runc, process.
- The shim, not dockerd, is the container's parent process.
- containerd can be used without Docker and is what Kubernetes typically uses.
- Patch runc and containerd promptly; they are privileged and have had escape CVEs.
- Use `ps`, `ctr`, and `docker info` to see the whole chain.

## 14. Related Concepts & What's Next

- [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) details the REST API that dockerd exposes to the CLI.
- [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) explains the OCI specs that runc and containerd implement.
- [§11](Section-11-Part2-Linux-Namespaces-Deep-Dive.md)-[§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) explain the kernel primitives runc configures.
- [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) covers containerd on its own and its relationship to Kubernetes.
- [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) shows how to configure dockerd through `daemon.json`.

**Next Section:** [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) — `Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md`
