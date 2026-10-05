# Section 5 (Part 1): Prerequisites Recap: Linux Namespaces, cgroups, and Basic Networking

## 1. Definition

**Plain language:** A container is not a special kernel object. It is an ordinary Linux process that has been given a private view of the system (namespaces), a resource budget (cgroups), and a restricted filesystem and privilege set. This section is a fast refresher on the pieces Docker leans on, including the basic networking vocabulary you need before touching container networks.

**Precise definition:** **Namespaces** partition kernel resources so a process sees only its own instance of them (PIDs, mounts, network stack, hostname, IPC, users, cgroup root). **Control groups (cgroups)** account for and limit resource usage (CPU, memory, I/O, PIDs) for a group of processes. **Basic networking** here means IP addressing, subnets, ports, NAT, and bridge and veth devices, the primitives Docker composes into container networks. The deep dives are [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md) (namespaces) and [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) (cgroups); this section only establishes shared vocabulary.

> 💡 **Tip:** If you can explain `unshare`, `/sys/fs/cgroup`, and `ip link` on a plain Linux box, you already understand 80% of what Docker does under the hood.

## 2. Why This Matters

- **It demystifies containers.** "Isolation" is just kernel features you can inspect with `lsns`, `ls /proc/<pid>/ns`, and `cat /sys/fs/cgroup/...`.
- **Debugging leans on it.** OOM kills, CPU throttling, "port already in use", and "cannot reach container" all reduce to cgroup limits, network namespaces, or NAT rules.
- **It explains the limits of isolation.** Containers share the host kernel, so kernel-level bugs and misconfigured privileges matter in a way they do not for VMs ([§1](Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)).
- **Interviews and the DCA probe it.** Questions about what actually makes a container are standard.
- **It prepares you for later topics** such as bridge networks, port publishing, resource limits, and rootless mode ([§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)).

## 3. Prerequisites and Dependencies

Assumes basic Linux command-line fluency (processes, files, permissions) and the container-versus-VM framing from [§1](Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md). Installing something you can run these commands against is covered in [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md). Kernel isolation is expanded in [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md) and [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md), and the union filesystem that gives containers their root filesystem appears in [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md). The engine components that actually invoke these kernel features are described in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md).

## 4. Architecture / Conceptual Diagram

```text
                        Linux host (one shared kernel)
  ┌─────────────────────────────────────────────────────────────────┐
  │  Namespaces (what you can SEE)      cgroups (what you can USE)   │
  │  ┌───────────────────────────┐      ┌────────────────────────┐   │
  │  │ pid   mnt   net   uts     │      │ cpu    memory   io     │   │
  │  │ ipc   user  cgroup  time  │      │ pids   cpuset          │   │
  │  └───────────────────────────┘      └────────────────────────┘   │
  │            │  applied to one process tree  │                     │
  │            ▼                               ▼                     │
  │   ┌──────────────────────────────────────────────────────┐       │
  │   │            "container" = process + both               │       │
  │   └──────────────────────────────────────────────────────┘       │
  │                                                                  │
  │  Basic networking plumbing                                       │
  │   container eth0 ◄──veth pair──► vethXXXX ──► bridge docker0     │
  │   docker0 (172.17.0.1/16) ──► iptables NAT ──► host eth0 ──► net │
  └─────────────────────────────────────────────────────────────────┘
```

- **Namespaces limit visibility; cgroups limit consumption.** They are independent mechanisms that Docker (via runc) applies together.
- **A veth pair is a virtual cable.** One end sits in the container's network namespace as `eth0`, the other end attaches to a bridge on the host.
- **NAT connects the private bridge subnet to the outside world**, and port publishing (`-p`) adds DNAT rules in the other direction.

## 5. Hands-On

### 5.1 Seeing Namespaces of a Process

**Purpose:** Show that namespaces are visible kernel objects and compare a container to the host.

```bash
ls -l /proc/self/ns
lsns -t net
```

```bash
$ ls -l /proc/self/ns | awk '{print $9,$10,$11}'
cgroup -> cgroup:[4026531835]
ipc -> ipc:[4026531839]
mnt -> mnt:[4026531841]
net -> net:[4026531840]
pid -> pid:[4026531836]
time -> time:[4026531834]
user -> user:[4026531837]
uts -> uts:[4026531838]

$ docker run -d --name web nginx:alpine
$ sudo readlink /proc/$(docker inspect -f '{{.State.Pid}}' web)/ns/net
net:[4026532601]
```

**Production usage example:** Comparing the `net:[...]` inode of a container process with the host's proves whether a pod or container is using `--network host`.

**Common errors:** `Permission denied` reading another user's `/proc/<pid>/ns` needs `sudo`.

### 5.2 Creating Namespaces by Hand with `unshare`

**Purpose:** Build a "container" without Docker to internalize what it does.

```bash
sudo unshare --pid --fork --mount-proc --uts --net /bin/bash
hostname sandbox
ps aux
ip link
exit
```

```bash
root@host:/# hostname sandbox && hostname
sandbox
root@host:/# ps aux
USER  PID %CPU %MEM COMMAND
root    1  0.0  0.0 /bin/bash
root    8  0.0  0.0 ps aux
root@host:/# ip link
1: lo: <LOOPBACK> mtu 65536 qdisc noop state DOWN
```

**Production usage example:** Used in training and debugging; `nsenter -t <pid> -n ip addr` does the reverse, entering a container's network namespace from the host to run host tools inside it.

**Common errors:** Forgetting `--fork` with `--pid` gives `Cannot allocate memory` style errors because the calling process cannot become PID 1.

### 5.3 Inspecting and Limiting with cgroups

**Purpose:** See the resource budget Docker attaches.

```bash
stat -fc %T /sys/fs/cgroup        # cgroup2fs means cgroup v2
docker run -d --name limited --memory 128m --cpus 0.5 --pids-limit 100 nginx:alpine
CID=$(docker inspect -f '{{.Id}}' limited)
cat /sys/fs/cgroup/system.slice/docker-$CID.scope/memory.max
cat /sys/fs/cgroup/system.slice/docker-$CID.scope/cpu.max
```

```bash
$ stat -fc %T /sys/fs/cgroup
cgroup2fs
$ cat /sys/fs/cgroup/system.slice/docker-$CID.scope/memory.max
134217728
$ cat /sys/fs/cgroup/system.slice/docker-$CID.scope/cpu.max
50000 100000
```

**Production usage example:** Setting `--memory` turns a runaway container into an OOM kill of that container instead of a host-wide memory crisis; `docker stats` shows usage against those limits.

**Common errors:** The path differs by cgroup version and cgroup driver (`cgroupfs` versus `systemd`); on cgroup v1 look under `/sys/fs/cgroup/memory/docker/<id>/`.

### 5.4 Basic Networking Primitives Docker Uses

**Purpose:** Map container networking onto plain Linux objects.

```bash
ip -br addr show docker0
ip -br link | grep veth
docker inspect -f '{{.NetworkSettings.IPAddress}}' web
sudo iptables -t nat -S | grep -i docker | head -4
```

```bash
$ ip -br addr show docker0
docker0          UP             172.17.0.1/16
$ ip -br link | grep veth
veth3a1f9c2@if2  UP
$ docker inspect -f '{{.NetworkSettings.IPAddress}}' web
172.17.0.2
$ sudo iptables -t nat -S | grep -i docker | head -3
-N DOCKER
-A PREROUTING -m addrtype --dst-type LOCAL -j DOCKER
-A POSTROUTING -s 172.17.0.0/16 ! -o docker0 -j MASQUERADE
```

**Production usage example:** When published ports stop working, checking that the `DOCKER` chain and the `MASQUERADE` rule exist (and were not flushed by a firewall reload) is a standard first step.

**Common errors:** Firewall tools that flush iptables (for example a `firewalld` or `ufw` reload) can wipe Docker's rules; restarting the daemon recreates them.

## 6. Production Usage Notes

- **Always set memory limits** on production containers; unbounded containers can drive the host into global OOM and kill unrelated processes.
- **cgroup v2 is the default** on current distributions; confirm your tooling (monitoring agents, older Java versions) is cgroup v2 aware.
- **Subnet planning matters.** The default `172.17.0.0/16` bridge can collide with corporate or VPN ranges; configure `default-address-pools` in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Host kernel version is part of your platform.** Features and bug fixes come from the kernel, not the image.

## 7. Security Considerations

- **Namespaces are not a security boundary equal to a hypervisor.** A kernel vulnerability affects every container on the host.
- **Root in a container without a user namespace is uid 0 on the host**, restricted only by capabilities, seccomp, and LSMs. See rootless mode in [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md).
- **Sharing namespaces weakens isolation**: `--pid host`, `--network host`, and `--privileged` remove protections.
- **Missing cgroup limits are a denial-of-service vector**, including fork bombs without a `--pids-limit`.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| Container exits with code 137 | Killed by OOM killer (memory cgroup limit) | `docker inspect -f '{{.State.OOMKilled}}'`; raise limit or fix leak |
| Container cannot reach the internet | Missing MASQUERADE rule or `ip_forward=0` | `sysctl net.ipv4.ip_forward`; restart Docker to rebuild rules |
| Published port not reachable from other hosts | Firewall dropping, or container bound to loopback | Check `docker port`, host firewall, and `-p` bind address |
| Subnet conflicts with VPN | Default bridge range overlaps corporate range | Set `default-address-pools` and recreate networks |
| CPU-bound app slow despite idle host | CFS throttling from `--cpus` limit | Inspect `cpu.stat` `nr_throttled`; raise the quota |

## 9. Best Practices

- Learn to look at a container from the host: `lsns`, `nsenter`, `/proc/<pid>`, and `/sys/fs/cgroup`.
- Set explicit `--memory`, `--cpus`, and `--pids-limit` for production workloads.
- Plan address ranges up front and keep container subnets distinct from VPC, VPN, and on-prem ranges.
- Confirm cgroup version and driver before tuning; make Docker and the kubelet agree on the driver.
- Avoid host namespace sharing unless there is a specific, reviewed need.

## 10. Common Anti-Patterns / Mistakes

- **Believing containers are lightweight VMs.** They are processes; there is no guest kernel.
- **Running with no resource limits** and blaming Docker when the host falls over.
- **Flushing iptables on a Docker host** and being surprised when networking breaks.
- **Using `--privileged` to "make it work"** instead of adding the one capability needed.
- **Ignoring subnet overlap** until a VPN connects and traffic vanishes.

## 11. Interview Questions

**🎯 Beginner:** _"What two Linux features make containers possible?"_
**Model answer:** Namespaces, which give each container an isolated view of PIDs, mounts, network, hostname, IPC, and users; and cgroups, which limit and account for CPU, memory, I/O, and process counts.
_What the interviewer is probing for:_ That the candidate knows containers are kernel features, not a separate technology.

**🎯 Intermediate:** _"How does a container get network access on the default bridge?"_
**Model answer:** Docker creates a network namespace, a veth pair with one end as `eth0` in the container and the other attached to the `docker0` bridge, assigns an IP from the bridge subnet, and relies on iptables MASQUERADE for outbound NAT. Published ports add DNAT rules.
_What the interviewer is probing for:_ Ability to trace the packet path.

**🎯 Senior:** _"A container is repeatedly killed with exit code 137 but the host shows plenty of free memory. Why?"_
**Model answer:** The container's memory cgroup limit was hit, so the kernel OOM-killed within that cgroup regardless of host free memory. I would confirm `OOMKilled` in `docker inspect`, check `memory.events`, and either raise the limit or reduce the app's footprint (including page cache and JVM heap sizing relative to the limit).
_What the interviewer is probing for:_ Understanding of cgroup-scoped OOM behavior.

**🎯 Architect:** _"How would you argue for or against containers versus VMs for hostile multi-tenant workloads?"_
**Model answer:** Containers share a kernel, so the isolation boundary is the kernel's attack surface; for untrusted tenants I would add layers such as user namespaces or rootless mode, seccomp, and LSMs, or use a stronger boundary such as microVMs or gVisor-style sandboxes. For trusted internal workloads, containers' density and speed generally win.
_What the interviewer is probing for:_ Risk-based reasoning rather than dogma.

## 12. Common Misconceptions

1. **"Containers have their own kernel."** They share the host kernel.
2. **"Namespaces limit resources."** They limit visibility; cgroups limit resources.
3. **"Root in a container is harmless."** Without user namespaces it is uid 0 on the host, constrained only by other controls.
4. **"Docker implements isolation itself."** Docker configures kernel features; runc does the syscalls ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)).

## 13. 🔑 Key Takeaways

- A container is a process plus namespaces, cgroups, and a root filesystem.
- Namespaces control what a process can see; cgroups control what it can use.
- Default container networking is veth pairs, the `docker0` bridge, and iptables NAT.
- Everything shown here is inspectable from the host with standard Linux tools.
- Shared-kernel isolation is strong but not equivalent to a hypervisor boundary.

## 14. Related Concepts & What's Next

[§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md) dissects each namespace type and how runc creates them, and [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) does the same for cgroups v1 versus v2. [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) explains the layered root filesystem that completes the picture. [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) showed how rootless mode uses user namespaces, and [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) shows which component performs these operations. Later Parts cover bridge, overlay, and host networking, and resource-limit tuning in depth.

**Next Section:** [§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md) — `Section-06-Part1-Docker-Editions-and-Licensing-Changes.md`
