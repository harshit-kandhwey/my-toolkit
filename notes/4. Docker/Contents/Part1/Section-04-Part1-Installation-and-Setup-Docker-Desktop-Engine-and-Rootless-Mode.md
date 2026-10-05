# Section 4 (Part 1): Installation and Setup: Docker Desktop, Engine, and Rootless Mode

## 1. Definition

**Plain language:** "Installing Docker" can mean three different things. On a laptop you usually install **Docker Desktop**, a packaged app that bundles everything and hides a small Linux VM. On a Linux server you install **Docker Engine** directly from a package repository. If you do not want the daemon running as root, you can run Docker in **rootless mode**, where the daemon and containers live entirely inside an unprivileged user's account.

**Precise definition:** **Docker Engine** is the open-source daemon (`dockerd`), CLI (`docker`), and supporting components (containerd, runc, Buildx, Compose plugin) that run natively on Linux. **Docker Desktop** is a commercial desktop distribution for macOS, Windows, and Linux that ships Docker Engine inside a managed lightweight VM (WSL 2 or Hyper-V on Windows, Apple Virtualization/QEMU on macOS, KVM/QEMU on Linux) along with a GUI, Kubernetes toggle, and integrations. **Rootless mode** runs `dockerd` and the container processes as a non-root user by leaning on user namespaces (see [§5](Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) and [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), so a container escape lands as an unprivileged user rather than host root.

> 💡 **Tip:** Containers need a Linux kernel. Docker Desktop on macOS and Windows is really "a Linux VM plus a client that talks to it"; the `docker` command on your Mac is not running containers on macOS.

## 2. Why This Matters

- **The install path decides your security posture.** A default Engine install gives a root daemon; a member of the `docker` group is effectively root on that host. Rootless mode is the main mitigation.
- **Desktop and Engine behave differently.** File sharing, networking to `localhost`, resource limits, and the daemon socket location all differ, and "works on my laptop" bugs often come from this gap.
- **Licensing follows the install choice.** Docker Desktop has commercial terms for larger organizations ([§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)); Docker Engine on Linux does not.
- **Correct setup avoids a class of first-day failures**: permission denied on the socket, cgroup driver mismatches, missing WSL integration, or an old distro package shadowing the official one.
- **Reproducible installs matter for CI and fleets.** Repository-based installs, pinned versions, and a documented `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) are the difference between a fleet you can patch and a fleet of snowflakes.

## 3. Prerequisites and Dependencies

Assumes the container-versus-VM model from [§1](Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md) and the lineage in [§2](Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md) and [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) (why `dockerd`, containerd, and runc exist as separate pieces). Kernel features used by all installs (namespaces, cgroups) are recapped in [§5](Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) and treated in depth in [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md) and [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md). Editions and licensing context is in [§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md). The daemon configuration file used after install is covered in [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md), and the engine component split in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md).

## 4. Architecture / Conceptual Diagram

```text
   Docker Engine on Linux            Docker Desktop (macOS / Windows)
  ┌──────────────────────┐          ┌─────────────────────────────────┐
  │ docker CLI           │          │ docker CLI (host OS)            │
  │    │ /var/run/       │          │    │ forwarded socket / pipe    │
  │    ▼ docker.sock     │          │    ▼                            │
  │ dockerd (root)       │          │ ┌──────── Linux VM ───────────┐ │
  │    │                 │          │ │ dockerd ► containerd ► runc │ │
  │    ▼                 │          │ │ containers                  │ │
  │ containerd ► runc    │          │ └─────────────────────────────┘ │
  │ containers           │          │ WSL2 / Hyper-V / Virtualization │
  └──────────────────────┘          └─────────────────────────────────┘

   Rootless mode (Linux)
  ┌────────────────────────────────────────────────────────────┐
  │ user "alice" (uid 1000)                                    │
  │  docker CLI ► $XDG_RUNTIME_DIR/docker.sock                 │
  │       ▼                                                    │
  │  dockerd (uid 1000, inside user namespace)                 │
  │       ▼                                                    │
  │  containerd ► runc ► container "root" == host uid 1000     │
  │  networking: slirp4netns or pasta (userspace)              │
  └────────────────────────────────────────────────────────────┘
```

- **Engine on Linux is direct**: the CLI talks to a root-owned Unix socket, so socket access equals root access.
- **Desktop inserts a VM boundary**, which is why host paths must be shared into the VM and why published ports are forwarded by Desktop rather than bound natively by the kernel you are sitting on.
- **Rootless remaps identities**: uid 0 inside the container maps to your own uid outside, using subordinate id ranges from `/etc/subuid` and `/etc/subgid`.

## 5. Hands-On

### 5.1 Installing Docker Engine on Ubuntu from the Official Repository

**Purpose:** Install a supported, upgradeable Engine, replacing any distro-packaged variants.

**Syntax and steps:**

```bash
# Remove conflicting unofficial packages (safe if none are installed)
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
  sudo apt-get remove -y $pkg
done

# Add Docker's official GPG key and apt repository
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

**Example usage and expected output:**

```bash
$ sudo systemctl status docker --no-pager | head -4
● docker.service - Docker Application Container Engine
     Loaded: loaded (/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Mon 2026-09-21 09:12:41 UTC; 1min 3s ago
TriggeredBy: ● docker.socket

$ sudo docker run --rm hello-world | head -3
Unable to find image 'hello-world:latest' locally
latest: Pulling from library/hello-world
Hello from Docker!
```

**Production usage example:** Configuration management (Ansible, cloud-init) runs exactly these steps, often pinning a version with `apt-get install docker-ce=<version>` and holding the package to control upgrade timing.

**Common errors:** `E: Unable to locate package docker-ce` means the repository line or key is wrong (often an unsupported codename); a leftover `docker.io` package can conflict with `containerd.io`.

### 5.2 Post-Install: Running Without `sudo` and Enabling on Boot

**Purpose:** Let a user run `docker` without `sudo`, understanding what that grants.

```bash
sudo groupadd docker 2>/dev/null || true
sudo usermod -aG docker "$USER"
newgrp docker            # or log out and back in
sudo systemctl enable --now docker.service containerd.service
```

```bash
$ docker version --format '{{.Client.Version}} / {{.Server.Version}}'
28.0.1 / 28.0.1
$ id | tr ',' '\n' | grep docker
999(docker)
```

**Production usage example:** Restrict the `docker` group on shared hosts; on build servers, membership is usually limited to the CI service account.

**Common errors:** `permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock` means the current shell has not picked up the new group membership yet.

### 5.3 Setting Up Rootless Mode

**Purpose:** Run the daemon as an unprivileged user.

```bash
sudo apt-get install -y uidmap dbus-user-session docker-ce-rootless-extras
grep "^$USER:" /etc/subuid /etc/subgid
sudo systemctl disable --now docker.service docker.socket   # optional: stop the rootful daemon
dockerd-rootless-setuptool.sh install
systemctl --user enable --now docker
sudo loginctl enable-linger "$USER"     # keep daemon alive after logout
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock
```

```bash
$ dockerd-rootless-setuptool.sh install
[INFO] Creating /home/alice/.config/systemd/user/docker.service
[INFO] starting systemd service docker.service
[INFO] Installed docker.service successfully.
[INFO] Creating CLI context "rootless"
Successfully created context "rootless"

$ docker info --format '{{.SecurityOptions}}'
[name=seccomp,profile=builtin name=rootless name=cgroupns]
$ docker run --rm alpine id
uid=0(root) gid=0(root) groups=0(root)
$ ps -o user,cmd -C dockerd
USER     CMD
alice    dockerd
```

**Production usage example:** Multi-tenant build hosts and developer workstations where a container escape must not equal host root.

**Common errors:** Missing `newuidmap` (install `uidmap`), no `/etc/subuid` entry for the user, and binding to ports below 1024 (needs `net.ipv4.ip_unprivileged_port_start=0` or a higher port). Some features, such as certain storage drivers and `--network host` semantics, are limited.

### 5.4 Docker Desktop and Verification

**Purpose:** Install Desktop on Windows or macOS and verify the client-server pairing.

```bash
# Windows: winget install -e --id Docker.DockerDesktop   (WSL 2 backend recommended)
# macOS:   brew install --cask docker
docker context ls
docker version
docker info | grep -E "Operating System|OSType|Server Version"
```

```bash
$ docker context ls
NAME              DESCRIPTION                               DOCKER ENDPOINT
default           Current DOCKER_HOST based configuration   unix:///var/run/docker.sock
desktop-linux *   Docker Desktop                            unix:///Users/alice/.docker/run/docker.sock
$ docker info | grep -E "Operating System|OSType"
 Operating System: Docker Desktop
 OSType: linux
```

**Common errors:** `error during connect ... the system cannot find the file specified` on Windows means Desktop is not running or the WSL 2 backend failed to start; virtualization disabled in BIOS produces the same class of symptom.

## 6. Production Usage Notes

- **Servers run Engine, not Desktop.** Desktop is a developer tool; production hosts use the repository-installed Engine (or a managed platform).
- **Pin and stage upgrades.** Upgrading Engine restarts `dockerd`; without `live-restore` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) containers stop. Roll upgrades through canary hosts.
- **Install from the official repository**, not the convenience script (`get.docker.com`), for anything long-lived; the script is meant for test and dev.
- **Keep `containerd` and `runc` in the supported set** shipped by the same repository; mixing versions from different sources is a known source of odd failures.
- **Desktop resources are VM-bound.** CPU, memory, and disk for containers on Desktop are capped by the VM settings, not by the host's totals.

## 7. Security Considerations

- **The `docker` group is root-equivalent.** Anyone who can start a container can mount `/` and read or write any host file: `docker run -v /:/host alpine chroot /host`.
- **Never expose the daemon on unauthenticated TCP** (`tcp://0.0.0.0:2375`). If remote access is required, use SSH (`DOCKER_HOST=ssh://user@host`) or mutual TLS on 2376.
- **Prefer rootless mode** where its limits are acceptable; it converts many container-escape bugs from host-root to user-level compromise.
- **Verify what you install.** Use the signed apt/yum repositories and their GPG keys rather than piping scripts to a shell on production hosts.
- **Mounting the socket into a container** (`-v /var/run/docker.sock:/var/run/docker.sock`) hands that container full control of the host daemon.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| `permission denied ... docker.sock` | User not in `docker` group, or shell not refreshed | `usermod -aG docker $USER`, then `newgrp docker` or re-login |
| `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | Daemon not running, or `DOCKER_HOST`/context points elsewhere | `systemctl status docker`; check `docker context ls` and `echo $DOCKER_HOST` |
| Rootless install fails with `newuidmap` errors | `uidmap` missing or no subuid/subgid range | Install `uidmap`; add ranges to `/etc/subuid` and `/etc/subgid` |
| Desktop stuck on "starting" on Windows | WSL 2 or virtualization not enabled | `wsl --update`, enable virtualization in BIOS, enable the WSL 2 feature |
| `E: Unable to locate package docker-ce` | Wrong repo codename or missing key | Recheck `/etc/apt/sources.list.d/docker.list` and key path |
| Rootless container cannot bind port 80 | Unprivileged users cannot bind below 1024 | Publish a high port, or lower `net.ipv4.ip_unprivileged_port_start` |

## 9. Best Practices

- Use the official repository on servers and pin versions; use Desktop only on workstations.
- Verify every install with `docker version` and `docker run --rm hello-world`, and confirm the server side responds, not just the client.
- Choose rootless mode for developer machines and shared build hosts when its feature limits are acceptable.
- Keep one documented `daemon.json` per host role ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) under configuration management.
- Use `docker context` to switch between local, remote, and rootless daemons explicitly rather than editing `DOCKER_HOST` ad hoc.

## 10. Common Anti-Patterns / Mistakes

- **Running `curl | sh` installers on production hosts** with no version pinning or review.
- **Adding every developer to the `docker` group on shared servers** without recognizing it is root access.
- **Exposing port 2375 for "convenience"**, a frequent cause of cryptomining compromises.
- **Installing distro `docker.io` alongside the official packages**, producing conflicting versions.
- **Treating Desktop like a server**, for example running long-lived production workloads on a laptop VM.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between Docker Desktop and Docker Engine?"_
**Model answer:** Engine is the open-source daemon and CLI that runs natively on Linux. Desktop is a packaged application for Windows, macOS, and Linux that runs Engine inside a managed Linux VM and adds a GUI, integrations, and update management. Servers use Engine; developer machines commonly use Desktop.
_What the interviewer is probing for:_ Understanding that containers need a Linux kernel and that Desktop provides one via a VM.

**🎯 Intermediate:** _"Why does `docker run` fail with 'permission denied' on the socket, and what is the risk in the usual fix?"_
**Model answer:** The socket `/var/run/docker.sock` is owned by root and group `docker`. Adding the user to that group fixes it, but the group is root-equivalent because container creation lets a user bind-mount the host filesystem or run privileged containers.
_What the interviewer is probing for:_ Awareness that convenience and security trade off here.

**🎯 Senior:** _"How does rootless mode work, and what are its limitations?"_
**Model answer:** The daemon runs as an unprivileged user inside a user namespace, with uid 0 in containers mapped to a subordinate range using `newuidmap`/`newgidmap`. Networking uses a userspace stack (slirp4netns or pasta), so throughput and source-IP visibility differ; low ports, some storage drivers, and certain cgroup controls need extra configuration. It greatly reduces the impact of an escape but is not a complete substitute for seccomp, AppArmor, and least privilege.
_What the interviewer is probing for:_ Mechanism-level knowledge and honest limits.

**🎯 Architect:** _"You are standardizing container runtimes across developer laptops, CI runners, and production hosts. What install strategy do you choose?"_
**Model answer:** Developers get Desktop (or an approved alternative, considering licensing in [§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)); CI runners get repository-installed Engine, ideally rootless or ephemeral VMs; production either runs a managed container platform or repository-installed Engine with pinned versions, `live-restore`, and TLS/SSH-only remote access, all managed by configuration management. I would set one supported version band across all three so image behavior stays consistent.
_What the interviewer is probing for:_ Balancing licensing, security, and operational consistency.

## 12. Common Misconceptions

1. **"Docker runs natively on macOS and Windows."** It runs in a Linux VM; only the client is native.
2. **"The `docker` group is just for convenience."** It is equivalent to passwordless root.
3. **"Rootless means completely safe."** It narrows blast radius but does not remove kernel attack surface.
4. **"`get.docker.com` is the production install method."** It is a convenience script intended for development and testing.

## 13. 🔑 Key Takeaways

- Three install shapes: Engine on Linux, Desktop with a hidden VM, and rootless Engine.
- Use the official repository with pinned versions on servers.
- Socket access is root access; protect it and never expose it unauthenticated.
- Rootless mode maps container root to an unprivileged host user via user namespaces, at the cost of some features.
- Always verify both client and server with `docker version` and a test container.

## 14. Related Concepts & What's Next

[§5](Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) recaps the kernel features (namespaces, cgroups) that rootless mode and all installs depend on. [§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md) covers the editions and licensing rules that decide when Desktop is permitted in a company. [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) opens up what actually got installed (`dockerd`, containerd, runc), and [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) covers `daemon.json` and socket permissions in depth. Later Parts cover hardening, rootless operations, and registry authentication in detail.

**Next Section:** [§5](Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) — `Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md`
