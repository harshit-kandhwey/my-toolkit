# Section 59 (Part 8): Capabilities: --cap-add/--cap-drop and Least Privilege

## 1. Definition

**Plain language:** Linux splits the all-powerful "root" privilege into about 40 separate permissions called **capabilities**, such as binding low ports, changing file ownership, or loading kernel modules. Docker starts every container with a reduced default set and lets you remove more (`--cap-drop`) or add some back (`--cap-add`). Least privilege means granting only the few capabilities the application genuinely needs, usually none.

**Precise definition:** Capabilities are per-thread kernel privilege bits, held in five sets: permitted, effective, inheritable, bounding and ambient (see `capabilities(7)`). Docker (through containerd and runc) sets the container's **bounding set** and initial sets from the default list adjusted by `--cap-add` and `--cap-drop`. The bounding set is a hard ceiling: a process can never gain a capability outside it, even by running a setuid-root binary or a file with file capabilities. `--privileged` grants all capabilities, removes the default seccomp and AppArmor confinement, and exposes host devices. `--cap-drop ALL` empties the set.

> 💡 **Tip:** The idiomatic least-privilege pattern is `--cap-drop ALL` followed by an explicit `--cap-add` list of only what you can justify.

## 2. Why This Matters

- Root inside a container is not equal to root on the host only *because* of capabilities, namespaces, seccomp and LSMs. Capabilities are the most direct knob to shrink what root can do ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- Several capabilities (`SYS_ADMIN`, `SYS_PTRACE`, `SYS_MODULE`, `DAC_READ_SEARCH`) are repeatedly used in published container-escape techniques.
- `--privileged` and `--cap-add SYS_ADMIN` are the most common "make it work" shortcuts; understanding the narrower alternatives avoids them.
- Kubernetes, Compose, CIS benchmarks and Pod Security Standards all express policy in capability terms.

## 3. Prerequisites and Dependencies

Requires the security model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), non-root users ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)) and namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), because capabilities are scoped to the user namespace that owns the resource. Runtime enforcement is done by runc ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). Syscall filtering is the complementary control in [§60](Section-60-Part8-Seccomp-Profiles.md), and mandatory access control follows in [§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md). Flags are part of `docker run` ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)).

## 4. Architecture / Conceptual Diagram

```text
  Kernel full set (~40 caps)
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ SYS_ADMIN SYS_MODULE SYS_PTRACE SYS_TIME NET_ADMIN SYS_RAWIO BPF ...     │
  │                                                                          │
  │   Docker default set (14, subset of the above)                           │
  │  ┌────────────────────────────────────────────────────────────────────┐  │
  │  │ CHOWN DAC_OVERRIDE FSETID FOWNER MKNOD NET_RAW SETGID SETUID       │  │
  │  │ SETFCAP SETPCAP NET_BIND_SERVICE SYS_CHROOT KILL AUDIT_WRITE       │  │
  │  │                                                                    │  │
  │  │   --cap-drop ALL --cap-add NET_BIND_SERVICE                        │  │
  │  │  ┌──────────────────────────────┐                                  │  │
  │  │  │ NET_BIND_SERVICE   (minimal) │                                  │  │
  │  │  └──────────────────────────────┘                                  │  │
  │  └────────────────────────────────────────────────────────────────────┘  │
  │                                                                          │
  │   --privileged  ───►  the whole outer box + no seccomp + devices         │
  └──────────────────────────────────────────────────────────────────────────┘

  Effective vs bounding for a process in the container
  Bounding set  ── hard ceiling, set by Docker ─────────────────► never exceeded
  Permitted/Effective for UID 0 : = bounding set at start
  Permitted/Effective for UID != 0 : EMPTY at start (unless ambient caps used)
```

- **Order of evaluation:** Docker applies drops and adds to the default set; `--cap-drop ALL` is processed first, then the adds, so `--cap-drop ALL --cap-add X` and `--cap-add X --cap-drop ALL` give the same result.
- **Non-root processes start with no effective capabilities** even when the bounding set contains some. They only gain them through file capabilities on the binary or ambient capabilities, both limited by the bounding set.
- **The exact default list can differ between engine versions and runtimes.** Always check the running container rather than relying on memory (see 5.1).

## 5. Hands-On

### 5.1 Inspect the Capabilities of a Running Container

```bash
docker run --rm alpine:3.20 sh -c 'grep Cap /proc/self/status'
```

```text
CapInh: 0000000000000000
CapPrm: 00000000a80425fb
CapEff: 00000000a80425fb
CapBnd: 00000000a80425fb
CapAmb: 0000000000000000
```

Decode the hex mask with `capsh` (from the `libcap` tools on the host, or inside a Debian-based container with `libcap2-bin`):

```bash
capsh --decode=00000000a80425fb
docker run --rm debian:12-slim sh -c 'apt-get update -qq && apt-get install -y -qq libcap2-bin >/dev/null && capsh --print'
```

```text
0x00000000a80425fb=cap_chown,cap_dac_override,cap_fowner,cap_fsetid,cap_kill,cap_setgid,cap_setuid,cap_setpcap,cap_net_bind_service,cap_net_raw,cap_sys_chroot,cap_mknod,cap_audit_write,cap_setfcap
```

The mask above is the common default on Engine 27. If your output differs, trust your output; the default list can change across versions.

### 5.2 Drop Everything and Observe What Breaks

```bash
docker run --rm --cap-drop ALL alpine:3.20 sh -c 'grep CapEff /proc/self/status; chown nobody /tmp; echo rc=$?'
docker run --rm --cap-drop ALL --cap-add CHOWN alpine:3.20 sh -c 'chown nobody /tmp; echo rc=$?'
```

```text
CapEff: 0000000000000000
chown: /tmp: Operation not permitted
rc=1
rc=0
```

A root process with an empty capability set cannot even `chown`, which shows that "root" is just UID 0 plus a set of capabilities.

### 5.3 Add a Capability for a Specific Need

```bash
# Raw sockets for ping (NET_RAW is in the default set; shown for the drop-all pattern)
docker run --rm --cap-drop ALL --cap-add NET_RAW alpine:3.20 ping -c1 127.0.0.1

# Change interface settings inside the container's own network namespace
docker run --rm --cap-add NET_ADMIN alpine:3.20 sh -c 'ip link add dummy0 type dummy && ip link'

# Trace a process with strace/gdb (use only for debugging)
docker run --rm --cap-add SYS_PTRACE --security-opt seccomp=unconfined \
  alpine:3.20 sh -c 'apk add --no-cache strace >/dev/null && strace -c true'
```

`NET_ADMIN` here changes only the container's own network namespace, not the host's, unless `--network host` is also used.

### 5.4 Reference Table: What Each Common Capability Allows

| Capability | Allows | Typical legitimate use | Risk |
|---|---|---|---|
| `NET_BIND_SERVICE` | Bind ports below 1024 | Web servers on 80/443 | Low (often unneeded, see [§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)) |
| `CHOWN` / `FOWNER` / `DAC_OVERRIDE` | Change ownership, bypass file permission checks | Entrypoint fixing volume ownership | Medium; DAC_OVERRIDE ignores file modes |
| `SETUID` / `SETGID` | Change process identity | `gosu`/`su-exec` privilege drop, postgres | Medium |
| `KILL` | Signal processes of other users | Init, supervisors | Low |
| `NET_RAW` | Raw and packet sockets | `ping`, network tools | ARP/DNS spoofing within a bridge network |
| `NET_ADMIN` | Interfaces, routes, iptables in the netns | VPN, CNI, network tools | High with host networking |
| `SYS_PTRACE` | Trace other processes | Debuggers, `strace` | High, can read other processes' memory |
| `SYS_ADMIN` | A huge catch-all: mount, namespaces, cgroups, many ioctls | FUSE, nested containers | Critical; close to root on the host |
| `SYS_MODULE` | Load kernel modules | Almost never | Critical, kernel code execution |
| `SYS_TIME` | Set the system clock | NTP daemons | Affects the host clock (not namespaced) |
| `SYS_RAWIO` | Raw I/O ports, `/dev/mem` | Hardware tools | Critical |
| `DAC_READ_SEARCH` | Read any file, `open_by_handle_at` | Backup agents | High; used in the "shocker" escape |
| `BPF` / `PERFMON` | Load eBPF programs, performance monitoring | Observability agents | High |

### 5.5 Compose and Kubernetes Equivalents

```yaml
# docker-compose.yml
services:
  web:
    image: myapp:1.4.2
    user: "10001:10001"
    cap_drop: [ALL]
    cap_add: [NET_BIND_SERVICE]
    security_opt:
      - no-new-privileges:true
```

```yaml
# Kubernetes container securityContext
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
    add: ["NET_BIND_SERVICE"]
```

The Pod Security Standards "restricted" profile requires dropping `ALL` and allows adding back only `NET_BIND_SERVICE`.

### 5.6 Finding the Minimal Set Empirically

```bash
# Start from nothing and add only what the error messages demand
docker run --rm --cap-drop ALL myapp:1.4.2
docker logs <id>   # look for "Operation not permitted" / EPERM

# Trace which capabilities the app asks for (run on the host, needs bcc-tools or bpftrace)
sudo capable-bpfcc -p $(docker inspect -f '{{.State.Pid}}' <container>)

# Static hint from file capabilities baked into the image
docker run --rm --entrypoint sh myapp:1.4.2 -c 'find / -xdev -type f -perm /6000 2>/dev/null'
```

Iterate: drop all, run the test suite, add one capability per failure, and record why each was added.

### 5.7 File Capabilities and `no-new-privileges`

```dockerfile
FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libcap2-bin \
 && setcap 'cap_net_bind_service=+ep' /usr/local/bin/server \
 && rm -rf /var/lib/apt/lists/*
USER 10001
CMD ["/usr/local/bin/server"]
```

```bash
docker run --rm --security-opt no-new-privileges nonroot-demo
```

A file capability lets a non-root user get `NET_BIND_SERVICE` only while the capability is inside the bounding set. With `no-new-privileges` the kernel will not grant additional privileges through setuid or file capabilities during `execve`, so this trick stops working; choose one design, and prefer unprivileged ports so neither is necessary.

### 5.8 Privileged Mode and Its Narrower Alternatives

```bash
# Avoid
docker run --privileged myimage

# Prefer: grant a single device and a single capability
docker run --device /dev/fuse --cap-add SYS_ADMIN myimage       # FUSE (still broad; consider rootless-friendly options)
docker run --device /dev/ttyUSB0 myimage                         # one serial device
docker run --cap-add NET_ADMIN --device /dev/net/tun myimage     # VPN client
```

## 6. Production Usage Notes

- **Baseline policy:** `cap_drop: [ALL]` on every service, add back by exception with a written reason in the compose file or manifest comment.
- **Web workloads** typically need no capabilities at all when they listen above 1024 as a non-root user.
- **Databases and official images** often need `CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`, `FOWNER` only because the entrypoint fixes ownership and then drops to a service user. Rebuild with pre-owned directories to remove those.
- **Network tooling and CNI plugins** legitimately need `NET_ADMIN`; run them in dedicated, isolated pods or containers.
- **Agents (monitoring, security)** may need `SYS_PTRACE`, `BPF`, `PERFMON`; use the most recent split capabilities (`BPF`, `PERFMON`, `CHECKPOINT_RESTORE`) instead of `SYS_ADMIN` on kernels that support them.
- **Docker Desktop / VM-based hosts:** capabilities apply to the Linux VM kernel, so a "privileged" container there gives control of the VM, not your laptop OS, though it still weakens the boundary.
- **Audit with inspection:** `docker inspect --format '{{.HostConfig.CapAdd}} {{.HostConfig.CapDrop}} {{.HostConfig.Privileged}}' <c>`, and list all privileged containers across a host in a periodic job.
- **Rootless mode** limits what even `--cap-add` can reach, because capabilities are scoped to the user namespace ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)).

## 7. Security Considerations

- **`SYS_ADMIN` is the new root.** It grants mount, namespace manipulation and cgroup writes, and combined with default AppArmor/seccomp relaxations it enables well-known escapes (for example abusing cgroup `release_agent` on cgroup v1). Treat it as equivalent to `--privileged`.
- **`--privileged` removes several protections at once:** all capabilities, host device access, default seccomp and AppArmor, and writable `/sys`. Reserve it for tightly controlled build or infrastructure tasks ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **Capabilities and the host network namespace:** `NET_ADMIN` plus `--network host` lets a container modify the host's firewall and routes ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- **Capabilities combine with mounts.** `DAC_OVERRIDE` plus a writable host bind mount means the container can write any file in that mount regardless of mode bits.
- **Defense in depth:** capabilities do not filter syscalls (use seccomp, [§60](Section-60-Part8-Seccomp-Profiles.md)) and do not restrict file paths (use AppArmor/SELinux, [§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)). Use all three.
- **Do not add capabilities to fix a symptom you have not understood.** Most `EPERM` errors come from ownership, seccomp or a read-only filesystem rather than a missing capability ([§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Monitor for drift:** alert on `Privileged=true`, `SYS_ADMIN`, `SYS_MODULE` and `NET_ADMIN` in running workloads.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Operation not permitted` after `--cap-drop ALL` | A needed capability (often `CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`) removed | Identify via `strace`/`capable-bpfcc`, add the single capability |
| `ping: Operation not permitted` | `NET_RAW` dropped (or no `net.ipv4.ping_group_range`) | Add `NET_RAW`, or set `--sysctl net.ipv4.ping_group_range="0 2147483647"` |
| `bind: permission denied` on port 80 as non-root | Unprivileged-port sysctl not 0 and no `NET_BIND_SERVICE` | Use port 8080 and publish, or add `NET_BIND_SERVICE` |
| `mount: permission denied` inside container | Needs `SYS_ADMIN` and relaxed seccomp/AppArmor | Use a volume or a pre-mounted path; avoid mounting inside containers |
| `RTNETLINK answers: Operation not permitted` | Network change needs `NET_ADMIN` | Add `NET_ADMIN` (scoped to its own netns) |
| `ptrace: Operation not permitted` from `strace`/`gdb` | `SYS_PTRACE` missing and default seccomp blocks ptrace | `--cap-add SYS_PTRACE`, plus a custom seccomp profile if needed |
| `--cap-add` has no effect for a non-root user | Effective set is empty for non-root | Use file capabilities or run the specific step as root, then drop |
| Container works with `--privileged` but not with a listed capability | A device, seccomp or AppArmor restriction, not a capability | Bisect: add `--device`, `--security-opt seccomp=...` separately |
| `capsh: command not found` | Tool not in minimal image | Read `/proc/self/status` and decode on the host |

## 9. Best Practices

- Start with `--cap-drop ALL` and add back the smallest justified set.
- Combine with a non-root `USER`, `no-new-privileges`, read-only root and default seccomp.
- Never use `--privileged` for application workloads; grant specific `--device` entries instead.
- Prefer unprivileged ports to avoid `NET_BIND_SERVICE` entirely.
- Fix ownership at build time rather than keeping `CHOWN`/`DAC_OVERRIDE`/`SETUID` for an entrypoint.
- Record each added capability with a reason and an owner in code review.
- Verify the effective set at run time with `/proc/self/status` in CI smoke tests.
- Enforce via policy: Pod Security Admission, OPA/Kyverno, or a CI linter over Compose files.

## 10. Common Anti-Patterns / Mistakes

- `--privileged` as the first reaction to any permission error.
- `--cap-add SYS_ADMIN` or `ALL` "temporarily" and never removing it.
- Adding capabilities while the process is non-root and expecting them to be effective.
- Dropping `ALL` in production without a test run, then discovering the failure during a deploy.
- Assuming the default capability list is the same across Docker versions, runtimes and Kubernetes distributions.
- Mounting the Docker socket and then hardening capabilities, which achieves nothing.
- Using `NET_ADMIN` with `--network host` for convenience.
- Confusing capabilities with seccomp: dropping a capability does not block the underlying syscall for non-capability-gated operations.

## 11. Interview Questions

**🎯 Beginner:** _"What is a Linux capability, and what does `docker run --cap-drop ALL --cap-add NET_BIND_SERVICE` do?"_
**Model answer:** Capabilities divide root's powers into separate privileges, such as binding ports below 1024 or changing file ownership. Docker gives containers a reduced default set. The command removes all of them, including the defaults, and then adds back only `NET_BIND_SERVICE`, so the process can bind to ports below 1024 but cannot chown files, create device nodes, send raw packets or change its UID. It is the least-privilege pattern: deny by default, allow explicitly.
_What the interviewer is probing for:_ Understanding capabilities as split-up root and the drop-all-then-add pattern.

**🎯 Intermediate:** _"A tool works in a container with `--privileged` but fails with `Operation not permitted` otherwise. How do you find the minimal permissions needed?"_
**Model answer:** `--privileged` bundles several relaxations, so I bisect them. First run with `--cap-drop ALL` and add capabilities one at a time guided by the error and by tracing (`strace`, or `capable-bpfcc` on the host). If a capability alone is not enough, I check whether the default seccomp profile is blocking a syscall (`--security-opt seccomp=unconfined` as a test only), whether AppArmor or SELinux blocks it, and whether the tool needs a device (`--device`). Then I translate the result into a minimal set, for example `NET_ADMIN` plus `/dev/net/tun`, and write down why each element is there. I would avoid `SYS_ADMIN` unless the need is proven.
_What the interviewer is probing for:_ Systematic debugging across capabilities, seccomp, LSMs and devices rather than guesswork.

**🎯 Senior:** _"Explain the relationship between the bounding set, a non-root user, file capabilities and `no-new-privileges` in a container."_
**Model answer:** The bounding set, defined by Docker from the default list and the add/drop flags, is a ceiling no process in the container can exceed. A UID 0 process starts with effective and permitted capabilities equal to that set, but a non-root process starts with an empty effective set, so `--cap-add` alone does not help it. It can obtain a capability only via a file capability on the executable (`setcap`) or via ambient capabilities, and only if the capability is within the bounding set. `no-new-privileges` sets a kernel flag that blocks gaining privileges across `execve` through setuid binaries and file capabilities, so it disables the `setcap` route; in that case the app should avoid needing the capability, for example by listening on a high port. I would design for no capabilities, add `no-new-privileges`, and treat any file capability as an exception.
_What the interviewer is probing for:_ Mechanical understanding of capability sets rather than flag memorization.

**🎯 Architect:** _"Design a capability policy for a shared platform running hundreds of third-party and internal images."_
**Model answer:** Define tiers. The default tier requires non-root, `drop: [ALL]`, no added capabilities, `allowPrivilegeEscalation: false`, default seccomp and a read-only root; this is enforced with Pod Security "restricted" or an admission controller, with a mutating policy that injects the drops. A second tier allows `NET_BIND_SERVICE` and a short allowlist per namespace. A privileged tier (`NET_ADMIN`, `SYS_PTRACE`, `BPF`, `SYS_ADMIN`, `--privileged`) is limited to dedicated node pools or namespaces for infrastructure agents, requires security review, an owner and an expiry, and runs with extra monitoring (Falco/eBPF). Build pipelines use rootless BuildKit or isolated builders rather than privileged DinD. Exceptions are tracked as code, with automated reports on drift and a quarterly review; for untrusted tenants I add stronger isolation (gVisor, Kata or separate VMs), since capabilities alone do not contain kernel bugs.
_What the interviewer is probing for:_ Tiered policy, enforcement points, exception governance and awareness of the limits of capability-based isolation.

## 12. Common Misconceptions

- "Root in a container has all root powers." It has only the bounding-set capabilities, and Docker's default set omits the most dangerous ones.
- "`--cap-add` gives a non-root user those powers." Their effective set stays empty without file or ambient capabilities.
- "`--privileged` is just `--cap-add ALL`." It also disables seccomp and AppArmor confinement and exposes host devices.
- "`NET_ADMIN` in a container changes the host network." Only in its own network namespace, unless it shares the host's.
- "Dropping capabilities makes the container sandboxed." Capabilities are one layer; syscalls and file paths need seccomp and LSMs.
- "The default capability list never changes." It has changed over time and can differ by runtime; check the live container.

## 13. 🔑 Key Takeaways

- Capabilities split root into ~40 privileges; Docker starts containers with a reduced default set.
- Pattern: `--cap-drop ALL`, then `--cap-add` only what is justified.
- `SYS_ADMIN`, `SYS_MODULE`, `SYS_PTRACE`, `DAC_READ_SEARCH` and `--privileged` are effectively host-level risk.
- Non-root processes start with no effective capabilities; `--cap-add` alone does not help them.
- `no-new-privileges` blocks privilege gain through setuid and file capabilities.
- Verify with `/proc/self/status` and `capsh --decode`; combine with seccomp, LSMs, non-root and read-only filesystems.

## 14. Related Concepts & What's Next

Related: security model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), non-root users ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)), namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), `docker run` flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), network isolation ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)). Next, [§60](Section-60-Part8-Seccomp-Profiles.md) covers seccomp profiles, which filter the system calls a container may make even when it holds a capability.

**Next Section:** [§60](Section-60-Part8-Seccomp-Profiles.md) — `Section-60-Part8-Seccomp-Profiles.md`
