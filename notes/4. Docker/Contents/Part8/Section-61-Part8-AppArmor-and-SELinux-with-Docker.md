# Section 61 (Part 8): AppArmor and SELinux with Docker

## 1. Definition

**Plain language:** AppArmor and SELinux are Linux Security Modules (LSMs) that apply mandatory access control: a policy, set by the host administrator, limits what a process can touch (files, network, capabilities) no matter what user it runs as. Docker attaches a policy to each container so that even root inside the container is boxed in.

**Precise definition:** An LSM adds hooks to kernel decisions that run *after* normal Unix permission and capability checks; all must agree. **AppArmor** is path-based: a profile names the paths, capabilities, network families and mount operations a program may use. Used by Debian, Ubuntu and SUSE. Docker auto-generates and loads the `docker-default` profile and applies it to every container unless told otherwise. **SELinux** is label-based: every process has a security context (`user:role:type:level`) and every object (file, socket) has a label; policy rules say which types may do what to which types. Used by RHEL, Fedora, CentOS Stream, Amazon Linux. With SELinux enabled in the daemon (`--selinux-enabled`), containers run as type `container_t` with a unique **MCS** (Multi-Category Security) pair such as `s0:c123,c456`, and the container's files are labeled `container_file_t` with the same categories. Only one LSM is used for container confinement per host; the distribution picks it.

> 💡 **Tip:** On Ubuntu/Debian think AppArmor and `--security-opt apparmor=...`; on RHEL-family think SELinux and the `:z`/`:Z` volume flags.

## 2. Why This Matters

- LSM policy is the layer that stops a compromised root process in a container from reading `/proc/sysrq-trigger`, writing `/sys`, or touching host files after a partial escape.
- SELinux MCS labels are what keeps container A from reading container B's files even if both run as the same UID on the host.
- The most common SELinux support ticket, "permission denied on my bind mount", is solved in seconds if you know `:z`/`:Z`; the common bad fix, `setenforce 0`, removes a whole defence layer.
- Compliance baselines (CIS Docker Benchmark) require AppArmor/SELinux to be enabled on containers.
- Kubernetes pod security, OpenShift defaults and managed node images depend on these policies.

## 3. Prerequisites and Dependencies

Requires the security model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)) and seccomp ([§60](Section-60-Part8-Seccomp-Profiles.md)). Volume and bind-mount behavior is in Part 7 ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)). Policy is enforced by the kernel; runc sets the label or profile at container start ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). Host needs the LSM enabled in the kernel and userspace tools (`apparmor_parser`, or `policycoreutils`/`container-selinux`). Docker Desktop on Windows/macOS runs a Linux VM with its own settings, so the commands below apply to a real Linux host or WSL2 distro with the LSM enabled. Plain WSL2 kernels often lack AppArmor/SELinux.

## 4. Architecture / Conceptual Diagram

```text
   container process: open("/etc/shadow") / write("/proc/sysrq-trigger")
          │
          ▼
   1. seccomp filter ──────────────► is the syscall allowed?        (§60)
          ▼
   2. DAC: uid/gid/mode bits ──────► classic permissions
          ▼
   3. Capabilities ────────────────► CAP_* required?                (§59)
          ▼
   4. LSM hook (one active) ───────► mandatory policy
        ┌───────────────────────────┴───────────────────────────┐
        │ AppArmor (path-based)     │ SELinux (label-based)     │
        │ profile: docker-default   │ process: container_t:s0:c1,c2
        │ deny /proc/sysrq-trigger  │ file:    container_file_t:s0:c1,c2
        │ deny mount, ptrace(peer)  │ allow container_t -> container_file_t
        │ audit: dmesg / auditd     │ MCS match required (c1,c2 == c1,c2)
        └───────────────────────────┴───────────────────────────┘
          ▼
   allowed ──► operation proceeds        denied ──► EACCES + audit record

   SELinux MCS isolation
   Container A: container_t:s0:c10,c20 ──► files s0:c10,c20  allowed
   Container A ──────────────────────► files s0:c30,c40  DENIED (container B)
   Container A ──────────────────────► host /etc (etc_t) DENIED (type rule)
```

- **Stacking order:** all four checks must pass; LSM is the last, most policy-driven gate.
- **AppArmor `docker-default`:** denies writes to most of `/proc` and `/sys`, denies `mount`, and denies ptrace of other profiles; allows normal file and network use.
- **SELinux types:** `container_t` (normal), `spc_t` (super-privileged, unconfined; used by `--privileged`), `container_init_t`, `container_kvm_t`.

## 5. Hands-On

### 5.1 Check Which LSM Is Active

```bash
docker info --format '{{json .SecurityOptions}}'
cat /sys/kernel/security/lsm
aa-status 2>/dev/null | head -5     # AppArmor hosts
getenforce 2>/dev/null              # SELinux hosts
```

```text
["name=apparmor","name=seccomp,profile=builtin","name=cgroupns"]
lockdown,capability,landlock,yama,apparmor,bpf
apparmor module is loaded.
```

On SELinux hosts the option list shows `name=selinux` and `getenforce` prints `Enforcing`.

### 5.2 AppArmor: See the Default Confinement

```bash
docker run --rm alpine:3.20 cat /proc/self/attr/current
docker run --rm alpine:3.20 sh -c 'echo b > /proc/sysrq-trigger'
docker run --rm --security-opt apparmor=unconfined alpine:3.20 cat /proc/self/attr/current
```

```text
docker-default (enforce)
sh: can't create /proc/sysrq-trigger: Permission denied
unconfined
```

### 5.3 AppArmor: Write and Load a Custom Profile

Test on a throwaway Linux host or VM, since loading a profile changes host policy.

```text
# /etc/apparmor.d/containers/docker-nginx-ro
#include <tunables/global>

profile docker-nginx-ro flags=(attach_disconnected,mediate_deleted) {
  #include <abstractions/base>
  network inet tcp,
  capability net_bind_service,
  capability setuid,
  capability setgid,
  /usr/sbin/nginx ix,
  /etc/nginx/** r,
  /var/log/nginx/** w,
  /var/cache/nginx/** rw,
  /run/nginx.pid rw,
  deny /bin/** wl,
  deny /usr/** wl,
  deny @{PROC}/sys/** w,
  deny /sys/** w,
}
```

```bash
sudo apparmor_parser -r -W /etc/apparmor.d/containers/docker-nginx-ro
sudo aa-status | grep docker-nginx-ro
docker run -d --name web --security-opt apparmor=docker-nginx-ro nginx:1.27
docker exec web sh -c 'echo x > /usr/bin/test'
```

```text
   docker-nginx-ro
sh: 1: cannot create /usr/bin/test: Permission denied
```

Generate a first draft with `aa-genprof` or `bane`, then tighten by hand in complain mode (`flags=(complain)`) before enforcing.

### 5.4 AppArmor: Read the Denials

```bash
sudo dmesg | grep -i 'apparmor="DENIED"' | tail -3
sudo journalctl -k | grep DENIED | tail -3
```

```text
audit: type=1400 audit(...): apparmor="DENIED" operation="open" profile="docker-nginx-ro" name="/etc/passwd" pid=4242 comm="sh" requested_mask="w" denied_mask="w"
```

### 5.5 SELinux: Containers Run Confined with MCS Labels

```bash
getenforce
docker run -d --name s1 alpine:3.20 sleep 300
ps -eZ | grep sleep
docker inspect s1 --format '{{.ProcessLabel}} | {{.MountLabel}}'
```

```text
Enforcing
system_u:system_r:container_t:s0:c389,c764 sleep
system_u:system_r:container_t:s0:c389,c764 | system_u:object_r:container_file_t:s0:c389,c764
```

### 5.6 SELinux: The Bind-Mount Permission Denied (and `:z` / `:Z`)

Use a throwaway directory, never a real data folder:

```bash
mkdir -p /tmp/selinux-demo && echo hi > /tmp/selinux-demo/f
docker run --rm -v /tmp/selinux-demo:/data alpine:3.20 cat /data/f
docker run --rm -v /tmp/selinux-demo:/data:z alpine:3.20 cat /data/f
ls -dZ /tmp/selinux-demo
```

```text
cat: can't open '/data/f': Permission denied
hi
system_u:object_r:container_file_t:s0 /tmp/selinux-demo
```

- `:z` relabels the host path with a **shared** label (`s0`, no categories), readable by all containers.
- `:Z` relabels with a **private** label unique to this container's MCS pair; other containers cannot read it.
- The relabel changes the real host directory's labels, so never use `:z`/`:Z` on `/home`, `/etc`, `/usr` or other shared system paths. Use a dedicated data directory or a named volume ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)), which Docker labels automatically.

### 5.7 SELinux: Reading Denials and Custom Types

```bash
sudo ausearch -m avc -ts recent | tail -3
sudo sealert -a /var/log/audit/audit.log | head -20     # setroubleshoot
```

```text
type=AVC msg=audit(...): avc:  denied  { read } for  pid=5123 comm="cat" name="f" scontext=system_u:system_r:container_t:s0:c389,c764 tcontext=unconfined_u:object_r:user_tmp_t:s0 tclass=file
```

Fixes, in order of preference: correct the label (`:z`/`:Z`, or `chcon -t container_file_t`), then `--security-opt label=type:my_t` with a custom module, and only last `--security-opt label=disable` for one container. Never `setenforce 0` as a fix.

```bash
docker run --rm --security-opt label=disable alpine:3.20 cat /proc/self/attr/current
docker run --rm --security-opt label=level:s0:c100,c200 alpine:3.20 sleep 1
```

### 5.8 Compose and Daemon Settings

```yaml
services:
  web:
    image: nginx:1.27
    security_opt:
      - apparmor=docker-nginx-ro       # AppArmor host
      # - label=type:container_t        # SELinux host (default anyway)
    volumes:
      - ./site:/usr/share/nginx/html:ro,z
```

```json
{ "selinux-enabled": true }
```

`/etc/docker/daemon.json` with `selinux-enabled` turns on label support on SELinux hosts (usually the default on RHEL packages); restart the daemon afterwards. Note that this is incompatible with the `btrfs` driver and unsupported with some storage setups.

## 6. Production Usage Notes

- **Do not disable the LSM** that the OS ships. On RHEL-family, leave SELinux Enforcing; on Ubuntu, leave `docker-default` in place.
- **Profile distribution:** ship AppArmor profiles with configuration management (Ansible, cloud-init) to every node, because Docker fails to start a container if the named profile is not loaded.
- **Kubernetes:** AppArmor is set via `securityContext.appArmorProfile` (GA in 1.30; earlier by annotation); SELinux via `securityContext.seLinuxOptions`. Both require the node's LSM to be on; they are ignored silently on nodes without them in some configurations, so verify.
- **OpenShift** assigns each namespace an MCS range and runs pods with `container_t` by default; that is why arbitrary UIDs and per-namespace file isolation work there.
- **Use complain mode first** (AppArmor `complain`, SELinux permissive for one domain with `semanage permissive -a`), review logs, then enforce.
- **Bind mounts** on SELinux: prefer named volumes; use `:Z` for single-container data, `:z` for data shared between containers.
- **Rootless Docker** and Podman interplay with SELinux too, with the same label model.

## 7. Security Considerations

- `--privileged` runs as `spc_t` (SELinux) or unconfined (AppArmor) and removes this layer entirely.
- `--security-opt apparmor=unconfined` or `label=disable` are single-container escapes from policy; flag them in code review and admission policy.
- Mounting the Docker socket gives control of the daemon, which can launch an unconfined container, defeating LSM policy.
- **AppArmor is path-based**, so hard links, bind mounts and mount namespaces can create alternative paths. Write deny rules defensively and combine with read-only mounts ([§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **MCS labels are not strong tenant separation by themselves.** Category space is finite (about 500k pairs), and a kernel bug bypasses everything. Use VMs for hostile tenants.
- **`:Z` on the wrong path is destructive to host policy.** Relabeling `/var` or a home directory can break host services and applications. Recover with `restorecon -Rv <path>`.
- **Policy can be loosened by root on the host**, so protect `/etc/apparmor.d` and policy modules.
- Monitor denials centrally (auditd to SIEM); repeated AVC/DENIED messages from a container are a strong detection signal.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Permission denied` on a bind mount, only on RHEL/Fedora | SELinux label mismatch (`user_home_t`, `default_t`) | Add `:z` or `:Z`; check `ls -Z` and `ausearch -m avc` |
| `setenforce 0` "fixes" it | You disabled enforcement system-wide | `setenforce 1`; fix the label or write a module instead |
| `docker: Error response ... apparmor failed to apply: profile not found` | Named profile not loaded on this node | `apparmor_parser -r` the profile; check `aa-status` |
| Works on dev (Mac/WSL) and fails on Ubuntu server | Dev VM has no LSM; prod enforces `docker-default` | Test on a host with the same LSM; see denials in `dmesg` |
| App denied writing to `/proc/...` or `/sys/...` | `docker-default` forbids it | Redesign, or a narrowly scoped custom profile; avoid unconfined |
| `Permission denied` after `:Z` shared between two containers | Private label belongs to one container only | Use `:z` for shared data |
| Host service breaks after `-v /var/lib/x:/data:Z` | Relabeled a host path used by other services | `restorecon -Rv /var/lib/x`; use a dedicated directory |
| Profile changes have no effect | Container started before reload, or profile name differs | Restart the container; confirm with `/proc/self/attr/current` |

## 9. Best Practices

- Keep the platform's default LSM enforcing and apply it to all containers.
- Test on hosts that match production's LSM, not just developer laptops.
- Develop custom profiles in complain/permissive mode, then promote to enforce.
- Use named volumes or dedicated data directories for bind mounts; apply `:z`/`:Z` only to those.
- Distribute and version profiles with configuration management; verify with `aa-status` or `semodule -l` in node bootstrap checks.
- Alert on AVC/DENIED events and on any container started with `unconfined` or `label=disable`.
- Combine with seccomp, non-root and dropped capabilities for defence in depth.
- Document each exception with an owner and an expiry.

## 10. Common Anti-Patterns / Mistakes

- Running `setenforce 0` or `SELINUX=disabled` to silence bind-mount errors.
- Using `--privileged` or `apparmor=unconfined` as a default in Compose files.
- Applying `:Z` to `$HOME`, `/etc` or other shared host directories.
- Copying a profile from a blog onto production without review or testing under load.
- Assuming AppArmor and SELinux can both confine containers on the same host simultaneously.
- Forgetting that a profile must exist on every node a container may be scheduled to.
- Treating LSM as a replacement for patching the kernel and runtime.

## 11. Interview Questions

**🎯 Beginner:** _"What are AppArmor and SELinux, and how does Docker use them?"_
**Model answer:** They are Linux Security Modules that enforce mandatory access control: policy defined by the admin that applies even to root. AppArmor restricts programs by path using profiles; SELinux labels processes and files and allows access by type rules. Docker applies a default confinement automatically: on AppArmor hosts a `docker-default` profile, on SELinux hosts the `container_t` type with a unique MCS category pair. They are in addition to namespaces, capabilities and seccomp, and are disabled by `--privileged` or by explicit `unconfined`/`label=disable`.
_What the interviewer is probing for:_ Knowing the two models, which distro uses which, and that defaults are automatic.

**🎯 Intermediate:** _"On RHEL a bind-mounted directory gives `Permission denied` inside the container even though file modes are fine. Diagnose and fix without weakening security."_
**Model answer:** This is almost always an SELinux label mismatch: the container runs as `container_t` but the host directory carries a label such as `user_home_t`. Confirm with `ls -Z` and `ausearch -m avc`. Fix by adding `:z` (shared) or `:Z` (private to this container) to the volume, or by relabeling a dedicated directory with `chcon -R -t container_file_t` or `semanage fcontext` plus `restorecon`. Do not run `setenforce 0`, and do not use `:Z` on shared system directories because it relabels the real host path.
_What the interviewer is probing for:_ Practical SELinux knowledge and refusing to disable enforcement.

**🎯 Senior:** _"Explain how SELinux MCS stops one container reading another container's data when both run as the same host UID, and where that protection ends."_
**Model answer:** Each container gets a random category pair (`c1,c2`) on its process label and the same pair on its labeled content (volumes, container filesystem). Policy requires the process categories to dominate the file's categories, so a container with `c1,c2` cannot read objects labeled `c3,c4` even though the type `container_t` to `container_file_t` is otherwise allowed and UIDs match. The protection ends with shared labels (`:z` or categoryless `s0` objects), `label=disable`/`spc_t`, a kernel exploit that bypasses LSM hooks, a mounted Docker socket, and finite category space across very many containers. It is a strong defence-in-depth control but not hostile-tenant isolation.
_What the interviewer is probing for:_ Understanding the mechanism, not just the flags, and its limits.

**🎯 Architect:** _"Standardize LSM confinement across a mixed fleet: Ubuntu nodes with AppArmor and RHEL/Amazon Linux nodes with SELinux, running the same Kubernetes workloads."_
**Model answer:** Define the policy at the intent level: no privileged containers, no unconfined profiles, default confinement always on. Enforce via admission control (Pod Security `baseline`/`restricted`, Kyverno or Gatekeeper rules rejecting `Unconfined` AppArmor/seccomp and `privileged`, and `seLinuxOptions` abuse). Maintain per-OS node images: Ubuntu nodes get the AppArmor profile set via image build or DaemonSet loader, RHEL nodes keep SELinux Enforcing with `container-selinux` pinned. Use `RuntimeDefault` in pod specs so each node applies its native default. Add custom profiles only for justified workloads, versioned and tested in CI on both OS families. Verify at node bootstrap (`aa-status`, `getenforce`), centralize audit logs, alert on denials and unconfined starts, and apply kernel and runtime patches on a regular cadence.
_What the interviewer is probing for:_ Policy abstraction across LSMs, enforcement points, and operational verification.

## 12. Common Misconceptions

- "AppArmor and SELinux are interchangeable features I can both enable." One LSM does container confinement per host; the distro decides.
- "If the file mode is 777 the container can read it." On SELinux, label mismatch still denies.
- "`setenforce 0` is a harmless debugging step." It disables enforcement for the whole host, not just Docker.
- "`:z` and `:Z` only affect the container." They relabel the real host path.
- "Root in the container bypasses AppArmor/SELinux." MAC policy applies regardless of UID.
- "The default profile is a no-op." `docker-default` blocks sensitive `/proc`, `/sys` writes and mounts.

## 13. 🔑 Key Takeaways

- LSMs are mandatory access control checked after DAC, capabilities and seccomp.
- AppArmor (path-based, Debian/Ubuntu/SUSE): `docker-default` is applied automatically; verify with `/proc/self/attr/current`.
- SELinux (label-based, RHEL-family): `container_t` plus per-container MCS categories isolate containers and their files.
- Bind-mount denials on SELinux hosts: use `:z`/`:Z` on dedicated directories; never `setenforce 0`.
- `--privileged`, `apparmor=unconfined` and `label=disable` remove this layer; treat them as exceptions.
- Develop custom policy in complain/permissive mode, version it, and distribute it to every node.

## 14. Related Concepts & What's Next

Related: container security model ([§57](Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), non-root and user namespaces ([§58](Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)), capabilities ([§59](Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)), seccomp ([§60](Section-60-Part8-Seccomp-Profiles.md)), volumes and bind mounts ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)). Next, [§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md) covers read-only root filesystems and immutable containers, which complement MAC policy by removing write access at the mount level.

**Next Section:** [§62](Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md) — `Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md`
