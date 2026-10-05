# Section 11 (Part 2): Linux Namespaces Deep Dive

## 1. Definition

**Plain language:** A namespace gives a process its own private view of some system resource. Two processes in different PID namespaces can both be "process 1"; two processes in different network namespaces each have their own network interfaces and routing tables. Containers are ordinary Linux processes placed into a set of namespaces, which is why they *look* like separate machines.

**Precise definition:** A Linux **namespace** wraps a global kernel resource in an abstraction so that processes inside the namespace see an isolated instance. The kernel provides eight types, created with `clone(2)`, `unshare(2)`, or joined with `setns(2)`:

| Namespace | Flag | Isolates |
|---|---|---|
| Mount | `CLONE_NEWNS` | Mount points and filesystem view |
| PID | `CLONE_NEWPID` | Process ID numbering |
| Network | `CLONE_NEWNET` | Interfaces, IPs, routes, iptables, sockets |
| UTS | `CLONE_NEWUTS` | Hostname and NIS domain name |
| IPC | `CLONE_NEWIPC` | SysV IPC and POSIX message queues |
| User | `CLONE_NEWUSER` | UID/GID mappings |
| Cgroup | `CLONE_NEWCGROUP` | View of the cgroup hierarchy |
| Time | `CLONE_NEWTIME` | Boot and monotonic clock offsets |

Docker uses mount, PID, network, UTS, IPC, and cgroup namespaces by default, and the user namespace only if `userns-remap` or rootless mode is enabled ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md), [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). The time namespace is available in the kernel but not used by default.

> ⚠️ **Warning:** Namespaces provide *visibility* isolation, not resource limiting and not a complete security boundary. Limits come from cgroups ([§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)); attack-surface reduction comes from capabilities, seccomp, and LSMs.

## 2. Why This Matters

- **It explains what a container actually is:** a process with a namespace set, a cgroup, and a rootfs, not a lightweight VM ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)).
- **Debugging:** `nsenter` and `/proc/<pid>/ns` let you enter a container's network or mount namespace from the host when the image has no shell or tools.
- **Networking behaviour:** container IPs, port mapping, and `--network host` semantics all come from the network namespace.
- **Security decisions:** `--pid=host`, `--net=host`, `--ipc=host`, and `--privileged` each remove a namespace boundary; knowing the consequence is essential.
- **Kubernetes parity:** a Pod is a group of containers sharing network, IPC, and (optionally) PID namespaces.

## 3. Prerequisites and Dependencies

Requires [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) (namespaces, cgroups, and networking recap) and [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (runc is the component that calls `clone`/`unshare`). [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) shows where namespaces appear in the runtime spec's `config.json`. Comfort with a Linux shell and root access (or `sudo`) on a Linux host or WSL2 VM is assumed. [§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) covers the companion mechanism, cgroups, and [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) covers the mount namespace's rootfs.

## 4. Architecture / Conceptual Diagram

```text
                      Linux host (init namespaces)
  ┌────────────────────────────────────────────────────────────────┐
  │ PID 1 systemd    dockerd    containerd    eth0 10.0.0.5        │
  │                                                                │
  │  ┌────────── Container A ──────────┐  ┌──── Container B ────┐  │
  │  │ pid ns:  nginx = PID 1          │  │ pid ns: app = PID 1 │  │
  │  │ net ns:  eth0 172.17.0.2        │  │ net ns: eth0        │  │
  │  │ mnt ns:  own rootfs (overlay2)  │  │         172.17.0.3  │  │
  │  │ uts ns:  hostname "web"         │  │ uts ns: "api"       │  │
  │  │ ipc ns:  private shm            │  │ ...                 │  │
  │  └───────────────┬─────────────────┘  └─────────┬───────────┘  │
  │                veth ◄──────────► docker0 ◄──────► veth         │
  └────────────────────────────────────────────────────────────────┘
      Same kernel underneath; only the *view* differs per namespace.
```

Each namespace is identified by an inode number visible under `/proc/<pid>/ns/`. Two processes sharing an inode share that namespace.

## 5. Hands-On

### 5.1 List a process's namespaces

```bash
$ ls -l /proc/$$/ns
lrwxrwxrwx 1 user user 0 ... cgroup -> 'cgroup:[4026531835]'
lrwxrwxrwx 1 user user 0 ... ipc -> 'ipc:[4026531839]'
lrwxrwxrwx 1 user user 0 ... mnt -> 'mnt:[4026531841]'
lrwxrwxrwx 1 user user 0 ... net -> 'net:[4026531840]'
lrwxrwxrwx 1 user user 0 ... pid -> 'pid:[4026531836]'
lrwxrwxrwx 1 user user 0 ... time -> 'time:[4026531834]'
lrwxrwxrwx 1 user user 0 ... user -> 'user:[4026531837]'
lrwxrwxrwx 1 user user 0 ... uts -> 'uts:[4026531838]'
```

Inode numbers will differ per host.

### 5.2 Compare host and container namespaces

```bash
$ docker run -d --name web nginx:1.27
$ PID=$(docker inspect -f '{{.State.Pid}}' web)
$ sudo readlink /proc/$PID/ns/net /proc/1/ns/net
net:[4026532501]
net:[4026531840]
$ sudo readlink /proc/$PID/ns/user /proc/1/ns/user
user:[4026531837]
user:[4026531837]
```

The network namespaces differ; the user namespace is the same, confirming Docker does not use user namespaces by default.

### 5.3 Create namespaces by hand with `unshare`

```bash
$ sudo unshare --pid --fork --mount-proc --uts bash
# hostname demo-ns
# hostname
demo-ns
# ps aux
USER  PID %CPU %MEM ... COMMAND
root    1  0.0  0.1 ... bash
root    8  0.0  0.0 ... ps aux
# exit
$ hostname
myhost
```

Inside the new PID namespace `bash` is PID 1, and the hostname change never touched the host UTS namespace.

### 5.4 Enter a container's namespaces with `nsenter`

```bash
$ sudo nsenter -t $PID -n ip addr show eth0
5: eth0@if6: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff link-netns default
    inet 172.17.0.2/16 brd 172.17.255.255 scope global eth0
$ sudo nsenter -t $PID -n ss -tlnp
State  Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
LISTEN 0      511          0.0.0.0:80         0.0.0.0:*     users:(("nginx",pid=...))
```

`-n` enters only the network namespace, so host tools (`ip`, `ss`, `tcpdump`) run against the container's network even though the image contains none of them.

### 5.5 PID namespace sharing

```bash
$ docker run -d --name app alpine sleep 3600
$ docker run --rm --pid=container:app alpine ps
PID   USER     TIME  COMMAND
    1 root      0:00 sleep 3600
    7 root      0:00 ps
$ docker run --rm --pid=host alpine ps | head -3
PID   USER     TIME  COMMAND
    1 root      0:03 /sbin/init
```

`--pid=container:<name>` joins another container's PID namespace (the basis of debug sidecars and `docker debug`-style tooling); `--pid=host` exposes every host process, so use it deliberately.

### 5.6 Network and UTS options

```bash
$ docker run --rm --net=host alpine ip -br addr | head -2
lo               UNKNOWN        127.0.0.1/8
eth0             UP             10.0.0.5/24
$ docker run --rm --hostname web01 alpine hostname
web01
$ docker run --rm --uts=host alpine hostname
myhost
```

### 5.7 User namespace demonstration

```bash
$ unshare --user --map-root-user bash -c 'id; cat /proc/self/uid_map'
uid=0(root) gid=0(root) groups=0(root),65534(nogroup)
         0       1000          1
```

An unprivileged user appears as root inside, while the kernel still sees UID 1000. This mapping is what rootless Docker and `userns-remap` build on. Some distributions restrict unprivileged user namespaces through sysctls (for example `kernel.unprivileged_userns_clone` or AppArmor policy on recent Ubuntu), in which case this command fails with `Operation not permitted`.

### 5.8 Inspect mount namespace

```bash
$ sudo nsenter -t $PID -m cat /proc/self/mountinfo | head -2
$ docker exec web cat /proc/1/mountinfo | grep -c .
```

The container sees only its own overlay rootfs and masked `/proc` paths.

## 6. Production Usage Notes

- **Kubernetes Pods** share one network namespace (via the pause container) and IPC by default; `shareProcessNamespace: true` adds PID sharing.
- **Debugging distroless images:** `nsenter` from the node, `kubectl debug` with an ephemeral container, or `docker run --pid=container:X --net=container:X` with a toolbox image.
- **Namespace count limits:** `/proc/sys/user/max_*_namespaces` caps namespaces per user; extremely dense hosts can hit them.
- **PID 1 semantics:** the first process in a PID namespace ignores signals without handlers and must reap zombies; use `docker run --init` (tini) for applications that do not.
- **Host networking** avoids NAT overhead but bypasses port isolation; reserve it for performance-critical agents.

## 7. Security Considerations

- **`--privileged`, `--pid=host`, `--net=host`, `--ipc=host`, `--uts=host`** each weaken isolation. `--privileged` additionally grants all capabilities and device access.
- **Without user namespaces, container root is host root** (UID 0 is the same UID) constrained only by capabilities, seccomp, and LSMs. Enable `userns-remap` or rootless mode where the workload allows ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md), [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Namespaces are not a sandbox boundary** against kernel vulnerabilities: all containers share one kernel. Use gVisor, Kata, or VMs for untrusted multi-tenant code.
- **Mounting `/var/run/docker.sock`** into a container grants control of the daemon and thus the host, regardless of namespaces.
- **`/proc/<pid>/ns` handles** kept open or bind-mounted keep namespaces alive; audit for leaks on long-running hosts.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `nsenter: reassociate to namespace 'ns/net' failed: Operation not permitted` | Not root, or PID wrong | Use `sudo`; re-fetch `State.Pid` |
| `docker inspect` shows `Pid: 0` | Container is not running | Start it; PIDs exist only while running |
| Signals ignored, `docker stop` takes 10 s | App is PID 1 without signal handlers | Add `--init` or handle SIGTERM |
| Zombie processes accumulate | PID 1 does not reap children | Use tini or `--init` |
| `unshare: Operation not permitted` (user ns) | Unprivileged userns disabled by sysctl/AppArmor | Adjust host policy or use `sudo` |
| Container cannot see host processes with `ps` | Expected; PID namespace | Use `--pid=host` only for diagnostics |
| Host `ip netns list` empty though containers run | Docker does not register netns under `/var/run/netns` | Symlink from `/proc/<pid>/ns/net` or use `nsenter -t` |

## 9. Best Practices

- Keep default namespace isolation; opt out one namespace at a time with a documented reason.
- Enable user-namespace remapping or rootless mode for hosts running less-trusted workloads.
- Use `--init` for images whose entrypoint is not a proper init.
- Prefer ephemeral debug containers sharing namespaces over installing tools into production images.
- Combine namespaces with cgroups, seccomp, dropped capabilities, and read-only rootfs; never rely on namespaces alone.

## 10. Common Anti-Patterns / Mistakes

- Using `--net=host` just to "make ports work" instead of publishing with `-p`.
- Running `--privileged` to avoid diagnosing a single missing capability.
- Believing that root in a container is harmless because it is "namespaced".
- Assuming containers have separate kernels or separate `/proc/sys` for all sysctls (only namespaced sysctls are per-container).
- Forgetting that `docker exec` joins the container's namespaces, so exec'd processes see the container view, not the host.

## 11. Interview Questions

**🎯 Beginner:** _"What is a Linux namespace, and which ones does Docker use?"_
**Model answer:** A namespace gives a process its own view of one kind of system resource. Docker creates a new set for each container: pid (own process tree, the entrypoint is PID 1), net (own interfaces and routing table), mnt (own root filesystem and mounts), uts (own hostname), ipc (own SysV IPC and shared memory), user (optional uid remapping), and cgroup. You can list a process's namespaces with `ls -l /proc/<pid>/ns`. Namespaces limit what a process can see, not how much it can use.
_What the interviewer is probing for:_ That containers are isolated views on one shared kernel, not VMs.

**🎯 Intermediate:** _"How would you debug a container that has no shell or tools, from the host?"_
**Model answer:** Find its PID with `docker inspect -f '{{.State.Pid}}' <c>`, then enter selected namespaces with `nsenter -t <pid> -n ip addr` for the network view or `-m -u -i -p` for the rest, running host binaries inside the container's namespaces. `docker run --rm --net container:<c> nicolaka/netshoot` or `docker debug` achieves the same without needing nsenter. Under the hood `nsenter` calls `setns(2)` on the `/proc/<pid>/ns/*` files. This works because a container is just a process with namespace memberships.
_What the interviewer is probing for:_ Practical use of namespace primitives rather than treating containers as opaque.

**🎯 Senior:** _"Explain what `--pid=host`, `--net=host`, and a shared `--pid=container:X` change, and when each is justified."_
**Model answer:** Each flag makes the container join an existing namespace instead of creating a new one, using `setns` or skipping `unshare`. `--net=host` removes network isolation so the container binds host ports directly, which suits high-throughput or port-range workloads but bypasses published-port controls. `--pid=host` exposes every host process to signals and `/proc` inspection, which is needed for some monitoring agents. `--pid=container:X` or `--net=container:X` is the sidecar pattern that Kubernetes pods use via a shared pause container. Each flag weakens isolation, so it should be reviewed like a privilege grant.
_What the interviewer is probing for:_ Ability to reason about the security cost of sharing namespaces.

**🎯 Architect:** _"Design the isolation model for running untrusted tenant code on shared hosts. Where do namespaces stop being enough?"_
**Model answer:** Namespaces plus cgroups, seccomp, dropped capabilities, and a user namespace (uid 0 in the container mapped to an unprivileged host range via `userns-remap` or rootless mode) form the baseline. They still share one kernel, so a kernel bug or a namespace-unaware resource such as `/proc/sys` entries, kernel keyrings, or the clock can cross the boundary. For hostile multi-tenancy I would add a stronger boundary: gVisor's user-space kernel or Kata/Firecracker microVMs as the OCI runtime, per-tenant nodes, and network policy. The trade-off is startup time, syscall overhead, and reduced compatibility versus a much smaller kernel attack surface.
_What the interviewer is probing for:_ Knowing the real security boundary of namespaces and when to escalate to sandboxed runtimes.

## 12. Common Misconceptions

- **"Namespaces limit CPU and memory."** They do not; cgroups do ([§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)).
- **"Each container has its own kernel."** All containers share the host kernel.
- **"Docker uses user namespaces by default."** It does not; rootful Docker maps container root to host root unless configured.
- **"Network namespaces appear in `ip netns list`."** Docker keeps them anonymous unless you link them.
- **"Namespaces make containers secure."** They are one layer among several.

## 13. 🔑 Key Takeaways

- A container is a process with namespaces plus cgroups plus a rootfs.
- Eight namespace types exist; Docker uses six by default and user namespaces only when configured.
- `/proc/<pid>/ns`, `unshare`, and `nsenter` are the inspection and experimentation tools.
- Sharing flags (`--pid`, `--net`, `--ipc`, `--uts`) trade isolation for convenience.
- Namespaces isolate views; they neither limit resources nor secure against kernel bugs.

## 14. Related Concepts & What's Next

Related: [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) (recap), [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (runc creates namespaces), [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) (namespaces in `config.json`), [§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) (cgroups), [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) (mount namespace and overlay rootfs), [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) (`userns-remap` in `daemon.json`). Later Docker topics cover container networking drivers built on network namespaces and security hardening with capabilities and seccomp.

**Next Section:** [§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) — `Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md`
