# Section 60 (Part 8): Seccomp Profiles

## 1. Definition

**Plain language:** Seccomp is a kernel filter that decides which system calls a process may make. Docker attaches a filter to every container by default, so even a root process inside cannot call dangerous kernel entry points such as `kexec_load` or `bpf` (unless granted).

**Precise definition:** Seccomp-BPF (secure computing mode, filter mode) lets a process install a Berkeley Packet Filter program that the kernel runs on each syscall. The program inspects the syscall number, architecture and (limited) argument values, and returns an action: `SCMP_ACT_ALLOW`, `SCMP_ACT_ERRNO` (fail with an error code), `SCMP_ACT_KILL_PROCESS`, `SCMP_ACT_TRAP`, `SCMP_ACT_LOG` or `SCMP_ACT_NOTIFY`. Filters are inherited by children and can only be made stricter, never loosened, once installed (with `no_new_privs` set). Docker expresses a filter as a JSON profile; the runtime (runc, via libseccomp) compiles it to BPF and installs it before the container's entrypoint runs. Docker's **default profile** is an allowlist (default action `SCMP_ACT_ERRNO`) of roughly 300+ syscalls and blocks about 44 of the 300-plus syscalls in modern Linux, plus some conditional ones that depend on granted capabilities.

> 💡 **Tip:** Seccomp restricts *what the process can ask the kernel to do*. Capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)) restrict *which privileged operations are permitted*. They are complementary layers.

## 2. Why This Matters

- Containers share the host kernel ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)); every reachable syscall is attack surface. Most kernel container-escape CVEs need a rarely-used syscall, and seccomp blocks them before the vulnerable code runs.
- The default profile has mitigated real vulnerabilities (for example, those reachable only through `keyctl`, `userfaultfd` or unprivileged `clone` flags) without any user action.
- `--privileged` and `--security-opt seccomp=unconfined` silently remove this layer; many teams do so just to make one error go away.
- A custom, application-specific profile can shrink the allowed set to tens of syscalls, a strong hardening step for internet-facing services.
- Kubernetes defaulted workloads to `Unconfined` for years unless `seccompDefault` is enabled; knowing Docker's profile helps you demand `RuntimeDefault`.

## 3. Prerequisites and Dependencies

Requires the isolation model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) and capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)). The filter is installed by runc during container creation ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). The host kernel must be built with `CONFIG_SECCOMP` and `CONFIG_SECCOMP_FILTER`; verify with `docker info --format '{{.SecurityOptions}}'` (look for `name=seccomp,profile=builtin`). On Docker Desktop the "host" is the Linux VM, so profiles apply inside it. Complements AppArmor and SELinux ([§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)).

## 4. Architecture / Conceptual Diagram

```text
   Container process (even uid 0)
          │  syscall(nr, args...)
          ▼
   ┌──────────────────────────────┐
   │ Kernel syscall entry         │
   │   seccomp-BPF filter         │◄── installed by runc from profile JSON
   │   (runs BEFORE the handler)  │
   └───────┬──────────────────────┘
           │ verdict
     ┌─────┼───────────────┬────────────────┐
     ▼     ▼               ▼                ▼
   ALLOW  ERRNO(EPERM)   KILL_PROCESS     LOG / NOTIFY
     │     (call fails)   (SIGSYS, dead)   (audit / supervisor)
     ▼
   normal kernel handler ──► capability check ──► LSM check (AppArmor/SELinux)

 Profile JSON shape
 ┌────────────────────────────────────────────────────────────┐
 │ { "defaultAction": "SCMP_ACT_ERRNO",                       │
 │   "architectures": ["SCMP_ARCH_X86_64", ...],              │
 │   "syscalls": [ { "names": ["read","write",...],           │
 │                   "action": "SCMP_ACT_ALLOW" },            │
 │                 { "names": ["clone"], "action": ...,       │
 │                   "args": [ {index,value,op} ] } ] }       │
 └────────────────────────────────────────────────────────────┘
```

- **Order of defence:** seccomp runs first, then capability checks, then LSM hooks. A call must pass all three.
- **Allowlist vs denylist:** the default profile is an allowlist with `ERRNO` default; a denylist (default `ALLOW`) is simpler but weaker.
- **Conditional rules:** Docker's profile uses `includes`/`excludes` on capabilities, so granting `CAP_SYS_ADMIN` also unlocks `mount`, `unshare` and related calls.

## 5. Hands-On

### 5.1 Confirm Seccomp Is Active

```bash
docker info --format '{{json .SecurityOptions}}'
docker run --rm alpine:3.20 grep Seccomp /proc/self/status
```

```text
["name=seccomp,profile=builtin","name=cgroupns"]
Seccomp:	2
Seccomp_filters:	1
```

`Seccomp: 2` means filter mode. `0` means disabled (unconfined).

### 5.2 See the Default Profile Block a Syscall

`unshare` creating new namespaces needs `CAP_SYS_ADMIN`, which the default profile withholds:

```bash
docker run --rm alpine:3.20 unshare --user --map-root-user id
docker run --rm --security-opt seccomp=unconfined alpine:3.20 unshare --user --map-root-user id
```

```text
unshare: unshare(0x10000000): Operation not permitted
uid=0(root) gid=0(root) groups=0(root)
```

Same image, same user; only the filter differs.

### 5.3 Get the Default Profile and Read It

```bash
curl -fsSLo default.json https://raw.githubusercontent.com/moby/profiles/main/seccomp/default.json
head -c 600 default.json
```

```text
{
	"defaultAction": "SCMP_ACT_ERRNO",
	"defaultErrnoRet": 1,
	"archMap": [
		{
			"architecture": "SCMP_ARCH_X86_64",
			"subArchitectures": [
```

### 5.4 Write a Minimal Custom Profile (Deny a Few Calls)

Start from the default and add an explicit deny, which is safer than writing an allowlist from scratch:

```bash
# Edit a copy; add this object to the "syscalls" array BEFORE the broad allow rules
cp default.json custom.json
```

```json
{
  "names": ["chmod", "fchmod", "fchmodat"],
  "action": "SCMP_ACT_ERRNO",
  "errnoRet": 1
}
```

```bash
docker run --rm --security-opt seccomp=custom.json alpine:3.20 sh -c 'touch /tmp/f && chmod 777 /tmp/f'
```

```text
chmod: /tmp/f: Operation not permitted
```

Note: with duplicate names, later rules take precedence in libseccomp's evaluation of the Docker JSON, so place and test the deny carefully; always verify behavior rather than trusting ordering.

### 5.5 Trace the Syscalls an Application Needs

Build an allowlist from observation (run on a throwaway test host or container):

```bash
docker run --rm --cap-add SYS_PTRACE --security-opt seccomp=unconfined \
  alpine:3.20 sh -c 'apk add -q strace && strace -f -c -o /tmp/s.txt ls / >/dev/null; cat /tmp/s.txt | head -15'
```

```text
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 26.67    0.000112          14         8           mmap
 ...
```

Tools such as `oci-seccomp-bpf-hook` (Podman), `inspektor-gadget` (`trace`/`advise seccomp-profile`) and the Kubernetes Security Profiles Operator record syscalls and emit a profile.

### 5.6 Log Instead of Block (Audit Mode)

```bash
# profile with "defaultAction": "SCMP_ACT_LOG" for discovery on a Linux host
docker run --rm --security-opt seccomp=audit.json myapp:test
sudo journalctl -k | grep -i 'type=1326'    # AUDIT_SECCOMP records
```

```text
audit: type=1326 audit(...): auid=... comm="myapp" syscall=435 compat=0 ...
```

### 5.7 Disable, Verify, and Compose Usage

```bash
docker run --rm --security-opt seccomp=unconfined alpine:3.20 grep Seccomp: /proc/self/status
```

```text
Seccomp:	0
```

```yaml
services:
  api:
    image: myapp:1.4
    security_opt:
      - seccomp=./seccomp/api.json
```

## 6. Production Usage Notes

- **Keep the default.** Never ship `seccomp=unconfined` or `--privileged` as a convenience; document and approve any exception.
- **Daemon-wide default:** set `"seccomp-profile": "/etc/docker/seccomp.json"` in `daemon.json` to replace the built-in profile for all containers that do not specify one.
- **Kubernetes:** set `securityContext.seccompProfile.type: RuntimeDefault` (or enable the kubelet `--seccomp-default`) and `Localhost` with `localhostProfile` for custom profiles stored on nodes.
- **Custom profiles pay off** for high-exposure services (parsers, image processors, browsers/headless Chrome). For ordinary apps the default is usually enough.
- **Build profiles in CI:** run the integration test suite under a tracer, generate the allowlist, review it, commit it, and fail the build on new syscalls.
- **Language runtimes drift:** a Go or glibc upgrade can start using a new syscall (`clone3`, `faccessat2`, `io_uring_*`). Pin the base image and re-run profile tests when upgrading.
- Older Docker or libseccomp versions return `EPERM` for unknown newer syscalls where glibc expects `ENOSYS`; this is a classic cause of failures on new base images running on old hosts.

## 7. Security Considerations

- **Defaults block:** `kexec_load`, `init_module`/`finit_module`, `delete_module`, `reboot`, `swapon`, `mount`/`umount2` (without `CAP_SYS_ADMIN`), `bpf`, `perf_event_open` (conditional), `keyctl`, `add_key`, `request_key`, `ptrace` (allowed on kernel 4.8+), `unshare`, `setns`, `open_by_handle_at`, and `clock_settime`.
- **`open_by_handle_at`** is the syscall behind the 2014 "Shocker" breakout; it stays blocked without `CAP_DAC_READ_SEARCH`.
- **`io_uring`** has been a steady source of kernel LPEs; Docker 25+ default profile no longer allows it, and many distributions restrict it separately. Do not re-enable it casually.
- **Seccomp is not a sandbox on its own:** it cannot stop abuse of allowed calls (a logic bug in `write`, or a kernel bug in `socket`). Combine it with non-root ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)), dropped capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)), LSM profiles ([§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)) and a read-only filesystem ([§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Argument filtering is weak:** BPF cannot dereference pointers, so it cannot check file paths or buffer contents (TOCTOU risk).
- **Profile files are trusted input:** protect them like code; a profile that is world-writable on the host lets an attacker weaken confinement.
- For stronger isolation than a shared kernel can give, consider gVisor or Kata ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Operation not permitted` on a call that works with `--privileged` | Syscall blocked by seccomp (or missing capability) | Run with `seccomp=unconfined` once to confirm, then trace and allow only that syscall |
| App crashes with `Bad system call` / exit 159 (SIGSYS) | Profile action is `KILL`/`TRAP` for a syscall | Add the syscall to the allowlist; check `dmesg` / audit log |
| `Permission denied` from `clone3` or `faccessat2` on a new image | Old Docker/libseccomp host returns `EPERM` instead of `ENOSYS` | Upgrade Docker and libseccomp, or run with a newer profile |
| `ptrace`/`strace` fails in container | Needs `CAP_SYS_PTRACE` plus allowed syscall | `--cap-add SYS_PTRACE` for debugging only |
| Custom profile ignored | Wrong path (relative to client, not daemon), or JSON invalid | Use a valid path; the Docker CLI reads the file and sends its content; check `docker run` error output |
| `Seccomp: 0` in `/proc/self/status` | Unconfined or kernel lacks seccomp | Remove `seccomp=unconfined`; check `docker info` |
| Chrome/Electron fails in container | Needs `unshare`/`clone` namespace flags for its own sandbox | Use a Chrome-specific profile, or `--no-sandbox` only in isolated test containers |

## 9. Best Practices

- Keep Docker's default profile on every container; treat any deviation as a reviewed exception.
- Customize by extending the default, not by writing an allowlist from nothing.
- Generate profiles from traces under realistic test load, including startup, shutdown, TLS, DNS and error paths.
- Version-control profiles next to the Dockerfile and test them in CI in both allow and deny directions.
- Use `SCMP_ACT_LOG` in staging first, then `ERRNO` in production.
- Prefer `SCMP_ACT_ERRNO` over `KILL` when apps handle failures gracefully; use `KILL_PROCESS` for known-never-used syscalls.
- Never use `--privileged` as a debug shortcut on shared hosts.
- Layer with capabilities, non-root and read-only rootfs; no single control is sufficient.

## 10. Common Anti-Patterns / Mistakes

- Setting `--security-opt seccomp=unconfined` permanently in Compose because one library call failed.
- Using `--privileged` where a single `--cap-add` would do, which also disables seccomp.
- Handing out a copied community profile without understanding or reviewing it.
- Writing an allowlist from `strace` of only the happy path, then breaking on the first error branch.
- Forgetting multi-architecture differences (`SCMP_ARCH_AARCH64` vs `X86_64`; syscall numbers and availability differ, for example no `open` on arm64).
- Never retesting after base-image or language runtime upgrades.
- Believing seccomp makes running as root safe.

## 11. Interview Questions

**🎯 Beginner:** _"What is seccomp in Docker and is it on by default?"_
**Model answer:** Seccomp is a Linux kernel facility that filters system calls. Docker applies a default profile to every container automatically: an allowlist of normal syscalls that blocks dangerous ones such as `kexec_load`, module loading, `bpf` and `keyctl`. It is on unless you pass `--security-opt seccomp=unconfined` or `--privileged`. You can check with `grep Seccomp /proc/self/status` inside a container, where `2` means a filter is active.
_What the interviewer is probing for:_ Knowing it is enabled by default and how to verify and disable it.

**🎯 Intermediate:** _"A container works with `--privileged` but fails with `Operation not permitted` otherwise. How do you find the minimal fix?"_
**Model answer:** `--privileged` turns off seccomp, grants all capabilities and removes other restrictions, so first isolate which layer is responsible. Run with `--security-opt seccomp=unconfined` alone; if it works, seccomp is the cause, otherwise try `--cap-add` candidates. Then trace the failing syscall (`strace -f`, audit log with `SCMP_ACT_LOG`, or dmesg), add only that syscall to a copy of the default profile, retest and commit the profile. Keep capabilities and seccomp changes as narrow as possible and document why.
_What the interviewer is probing for:_ A methodical layer-by-layer diagnosis instead of reaching for `--privileged`.

**🎯 Senior:** _"How would you build and maintain a custom seccomp profile for a service in CI/CD?"_
**Model answer:** Run the full integration and load test suite with a tracer (strace, eBPF-based advisor, or the Security Profiles Operator recorder) to collect the syscalls used, merge them with the runtime's baseline needs (startup, DNS, TLS, signals, shutdown), and generate a JSON allowlist with `defaultAction` `ERRNO` and correct architectures. Review the result, keep it in the repo, and add CI jobs that run the container under the profile and fail on `EPERM`/`SIGSYS`. Re-generate on dependency or base-image upgrades, deploy first in `SCMP_ACT_LOG` mode, and monitor audit logs before enforcing. Fall back to the default profile if the effort outweighs the risk for low-exposure services.
_What the interviewer is probing for:_ Operational maturity: automation, drift handling and staged enforcement.

**🎯 Architect:** _"Design the syscall-confinement strategy for a multi-tenant platform running untrusted customer containers."_
**Model answer:** Layer defences. Enforce a non-negotiable baseline via admission control (Pod Security `restricted`, `seccompProfile: RuntimeDefault`, no privileged, dropped capabilities, non-root, read-only rootfs) and a daemon/kubelet default. Offer a tiered model: the default profile for most workloads, tighter curated profiles for known workload classes, and reject unconfined. Because seccomp still exposes the shared kernel, add a second boundary for truly untrusted code: user-space kernels (gVisor) or microVMs (Kata, Firecracker), plus per-tenant nodes for high-risk tenants. Add runtime detection (Falco, audit of `SIGSYS` events) and a patch cadence for kernels, since seccomp cannot defend against bugs in allowed syscalls.
_What the interviewer is probing for:_ Understanding seccomp's limits and combining it with stronger isolation and policy enforcement.

## 12. Common Misconceptions

- "Containers have no syscall filtering unless I configure it." Docker applies a default profile automatically.
- "Seccomp and capabilities are the same thing." Capabilities gate privileged operations; seccomp gates syscall entry. Both apply.
- "A seccomp profile makes root in the container safe." It narrows the kernel surface but does not remove allowed-call bugs.
- "`--cap-add ALL` is fine because seccomp still protects me." Some default-profile rules unlock with capabilities, so adding them widens the allowed syscalls.
- "A custom profile replaces the default additively." A custom profile completely replaces it; omitted syscalls are blocked.

## 13. 🔑 Key Takeaways

- Seccomp-BPF filters syscalls before the kernel handler runs; Docker enables a default allowlist profile automatically.
- `seccomp=unconfined` and `--privileged` remove the layer; avoid both.
- Verify with `grep Seccomp /proc/self/status` (`2` = filtering).
- Build custom profiles from the default plus traced needs, tested in CI and staged via `SCMP_ACT_LOG`.
- Seccomp is one layer: pair it with non-root, dropped capabilities, LSMs and read-only rootfs.

## 14. Related Concepts & What's Next

Related: container security model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), running as non-root ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)), capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)), read-only filesystems ([§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)), namespaces ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)). Next, [§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md) covers the mandatory-access-control layer that restricts files, networks and capabilities by policy.

**Next Section:** [§61](Section-61-Part8-AppArmor-and-SELinux-with-Docker.md) — `Section-61-Part8-AppArmor-and-SELinux-with-Docker.md`
