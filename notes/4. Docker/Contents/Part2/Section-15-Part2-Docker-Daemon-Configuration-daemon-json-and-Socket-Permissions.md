# Section 15 (Part 2): Docker Daemon Configuration (daemon.json, Socket Permissions)

## 1. Definition

**Plain language:** The Docker daemon (`dockerd`) has many behaviors you can tune: where it stores data, how it logs, which registries it trusts, how it listens for clients. You set them in a JSON file, `daemon.json`, or with command-line flags. Separately, the daemon's Unix socket decides who is allowed to control Docker, and that permission is effectively root on the host.

**Precise definition:**

- **`daemon.json`** is the daemon's configuration file. Default locations: `/etc/docker/daemon.json` on Linux (rootful), `~/.config/docker/daemon.json` in rootless mode, and `C:\ProgramData\docker\config\daemon.json` on Windows. Docker Desktop exposes it under Settings ► Docker Engine.
- **The Docker socket** `/var/run/docker.sock` (a symlink to `/run/docker.sock`) is a Unix domain socket created by `dockerd`, owned by `root:docker` with mode `660`. Access to it grants full control of the daemon.
- The daemon can also listen on TCP (`2375` unencrypted, `2376` TLS) via the `hosts` option.
- A flag and the same key in `daemon.json` conflict: the daemon refuses to start if an option is set in both places with different sources (for example `-H` on the command line via the systemd unit and `hosts` in JSON).

> ⚠️ **Warning:** Membership in the `docker` group is equivalent to root: `docker run -v /:/host --privileged ...` gives a full host filesystem and process view.

## 2. Why This Matters

- **Operational defaults are wrong for production.** The default `json-file` log driver has no rotation, so a chatty container can fill the disk.
- **Storage location and driver** are set here, which matters when relocating `/var/lib/docker`.
- **Network defaults** (`bip`, `default-address-pools`) can collide with corporate VPN or VPC ranges.
- **Registry access.** Mirrors, insecure registries, and proxies are configured in this file.
- **Security posture.** The socket's exposure, TLS, user-namespace remapping, and live-restore are daemon-level decisions.
- **Reliability.** `live-restore` keeps containers running during daemon restarts and upgrades.

## 3. Prerequisites and Dependencies

- [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) explains what `dockerd` is and how it delegates to containerd ([§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).
- [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) covers the client, the REST API, and how the CLI selects the socket (`DOCKER_HOST`, contexts).
- [§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) explains cgroup drivers, which are set here through `exec-opts`.
- [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) explains storage drivers, selected by `storage-driver`.
- [§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md) covers installation and rootless mode.
- Familiarity with systemd (`systemctl`, `journalctl`, drop-in units) and JSON syntax.

## 4. Architecture / Conceptual Diagram

```text
   Config sources (precedence: flags must not conflict with JSON)

   ┌────────────────────┐   ┌──────────────────────────┐
   │ dockerd CLI flags  │   │ /etc/docker/daemon.json  │
   │ (systemd ExecStart)│   │ (or --config-file path)  │
   └─────────┬──────────┘   └────────────┬─────────────┘
             └──────────────┬────────────┘
                            ▼
                   ┌─────────────────┐
                   │     dockerd     │◄──── SIGHUP reloads a subset
                   └───┬─────────┬───┘      (debug, labels, live-restore...)
                       │         │
         listens on    │         │ delegates
                       ▼         ▼
   ┌──────────────────────┐   ┌──────────────┐
   │ /var/run/docker.sock │   │  containerd  │
   │ root:docker  mode 660│   └──────────────┘
   │ tcp://:2376 (TLS)    │
   └──────────┬───────────┘
              │
   ┌──────────┴────────────────────────────┐
   │ who can connect = who is root on host │
   │  root, `docker` group, TLS clients    │
   └───────────────────────────────────────┘
```

- **Reload versus restart.** `systemctl reload docker` (SIGHUP) applies only some options (for example `debug`, `labels`, `live-restore`, `max-concurrent-downloads`, `shutdown-timeout`); most others, such as `data-root`, `storage-driver`, and `log-driver`, need a restart.
- **Log driver default applies only to new containers.** Existing containers keep the driver they were created with.

## 5. Hands-On

### 5.1 Locate and validate the effective configuration

```bash
$ sudo cat /etc/docker/daemon.json
cat: /etc/docker/daemon.json: No such file or directory   # defaults in use

$ docker info | grep -E "Docker Root Dir|Logging Driver|Cgroup Driver|Live Restore"
 Logging Driver: json-file
 Cgroup Driver: systemd
 Docker Root Dir: /var/lib/docker
 Live Restore Enabled: false

$ sudo dockerd --validate --config-file /etc/docker/daemon.json
configuration OK
```

### 5.2 A production-oriented daemon.json

```bash
$ sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "live-restore": true,
  "data-root": "/data/docker",
  "storage-driver": "overlay2",
  "exec-opts": ["native.cgroupdriver=systemd"],
  "default-address-pools": [
    { "base": "10.200.0.0/16", "size": 24 }
  ],
  "registry-mirrors": ["https://mirror.example.internal"],
  "max-concurrent-downloads": 6,
  "default-ulimits": { "nofile": { "Name": "nofile", "Hard": 65536, "Soft": 65536 } }
}
EOF
$ sudo dockerd --validate --config-file /etc/docker/daemon.json
configuration OK
$ sudo systemctl restart docker
```

### 5.3 Verify the changes took effect

```bash
$ docker info | grep -E "Root Dir|Live Restore|Cgroup Driver"
 Cgroup Driver: systemd
 Docker Root Dir: /data/docker
 Live Restore Enabled: true

$ docker run -d --name t alpine sleep 60
$ docker inspect t --format '{{json .HostConfig.LogConfig}}'
{"Type":"json-file","Config":{"max-file":"3","max-size":"10m"}}
```

Moving `data-root` does not copy existing data. Stop Docker, `rsync -aHAX /var/lib/docker/ /data/docker/`, then start.

### 5.4 Debug mode via reload (no restart)

```bash
$ sudo sed -i 's/^{/{\n  "debug": true,/' /etc/docker/daemon.json
$ sudo systemctl reload docker
$ sudo journalctl -u docker -n 3 --no-pager
level=debug msg="Calling GET /v1.45/info"
```

### 5.5 Inspect socket permissions

```bash
$ ls -l /var/run/docker.sock
srw-rw---- 1 root docker 0 Sep 22 08:01 /var/run/docker.sock

$ id -nG
alice sudo

$ docker ps
permission denied while trying to connect to the Docker daemon socket at
unix:///var/run/docker.sock: connect: permission denied

$ sudo usermod -aG docker alice     # takes effect on next login
$ newgrp docker
$ docker ps
CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES
```

### 5.6 Change socket group and path via systemd

```bash
$ systemctl cat docker.socket
[Socket]
ListenStream=/run/docker.sock
SocketMode=0660
SocketUser=root
SocketGroup=docker
```

Override with `sudo systemctl edit docker.socket` to change `SocketGroup` (for example to a dedicated `dockerops` group). In `daemon.json`, `"group": "dockerops"` sets the group when `dockerd` creates the socket itself.

### 5.7 Expose the API remotely with TLS (safer than plain TCP)

```bash
# systemd unit override must clear -H from ExecStart, since "hosts" is in daemon.json
$ sudo mkdir -p /etc/systemd/system/docker.service.d
$ printf '[Service]\nExecStart=\nExecStart=/usr/bin/dockerd\n' | \
    sudo tee /etc/systemd/system/docker.service.d/override.conf
$ # daemon.json additions:
#  "hosts": ["fd://", "tcp://0.0.0.0:2376"],
#  "tlsverify": true, "tlscacert": "/etc/docker/ca.pem",
#  "tlscert": "/etc/docker/server-cert.pem", "tlskey": "/etc/docker/server-key.pem"
$ sudo systemctl daemon-reload && sudo systemctl restart docker
$ docker --tlsverify --tlscacert=ca.pem --tlscert=cert.pem --tlskey=key.pem \
    -H tcp://docker-host:2376 version --format '{{.Server.Version}}'
27.3.1
```

An alternative that avoids opening a TCP port is SSH: `docker -H ssh://user@docker-host ps` or a context (`docker context create remote --docker host=ssh://user@docker-host`).

### 5.8 Common failure: option set in two places

```bash
$ sudo systemctl restart docker
Job for docker.service failed.
$ sudo journalctl -u docker -n 2 --no-pager
unable to configure the Docker daemon with file /etc/docker/daemon.json: the following
directives are specified both as a flag and in the configuration file: hosts: (from flag: [fd://], from file: [fd:// tcp://0.0.0.0:2376])
```

Fix by using the empty `ExecStart=` override shown in 5.7.

## 6. Production Usage Notes

- Always set log rotation (`max-size`, `max-file`) or use the `local` log driver, which rotates by default.
- Enable `live-restore` to allow daemon upgrades without stopping containers (not compatible with Swarm mode).
- Manage `daemon.json` through configuration management (Ansible, cloud-init) and keep it in version control.
- Choose `default-address-pools` before creating networks; changing it does not recreate existing ones.
- Configure `registry-mirrors`, `proxies`, and `insecure-registries` (only for lab use) centrally.
- Validate with `dockerd --validate` before restarting production hosts.
- Set `default-ulimits`, `init: true`, and `default-runtime` if fleet-wide behavior is needed.
- Keep `shutdown-timeout` long enough for graceful container stops.

## 7. Security Considerations

- **Docker socket equals root.** Do not add unprivileged or service accounts to `docker` casually; prefer rootless mode ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)) or a controlled wrapper.
- **Never mount `/var/run/docker.sock` into containers** unless the container is fully trusted; a compromised container then controls the host.
- **Never expose TCP 2375.** It is unauthenticated. If remote access is needed, use TLS with client certificates (2376) or SSH.
- **Firewall the API port** to management networks only.
- **`userns-remap`** maps container root to an unprivileged host UID, limiting breakout impact (with feature trade-offs for volumes and privileged mode).
- **`no-new-privileges`, `icc: false`, and `seccomp-profile`** defaults can be set daemon-wide.
- **Audit access** with `auditd` rules on `/var/run/docker.sock` and `/etc/docker`.
- **Protect certificates and keys** used for TLS with `600` permissions.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `permission denied ... docker.sock` | User not in `docker` group, or session not refreshed | `usermod -aG docker`, re-login or `newgrp` |
| Daemon fails after editing daemon.json | Invalid JSON or duplicate flag/file option | `dockerd --validate`; `journalctl -u docker` |
| Config change ignored | Needed a restart, not reload | `systemctl restart docker` |
| Existing containers still use old log settings | Log config fixed at container creation | Recreate containers |
| Images vanished after `data-root` change | Data not migrated | Point back or rsync the old directory |
| `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | Daemon stopped, or `DOCKER_HOST` or context wrong | `systemctl status docker`; `docker context ls` |
| Networks conflict with VPN | Default `172.17.0.0/16` or pools overlap | Set `bip` and `default-address-pools` |
| `dial tcp: i/o timeout` pulling images | Proxy or mirror missing | Configure `proxies` or a systemd proxy drop-in |

```bash
$ systemctl status docker --no-pager | head -5
$ journalctl -u docker -b --no-pager | tail -20
$ docker context ls
```

## 9. Best Practices

- Keep daemon.json minimal, explicit, and version-controlled.
- Validate before restart and prefer reload for reloadable options.
- Rotate logs by default; ship them off-host for retention.
- Restrict socket access; prefer rootless, SSH contexts, or TLS.
- Allocate address pools that will not collide with corporate networks.
- Put `data-root` on dedicated storage ([§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)).
- Document changes and test daemon restarts in staging with `live-restore`.
- Avoid duplicating settings between systemd flags and daemon.json.

## 10. Common Anti-Patterns / Mistakes

- **`chmod 666 /var/run/docker.sock`** to "fix" permission errors; this makes every local user root.
- **Adding CI or application users to the `docker` group** without treating it as root access.
- **Exposing `tcp://0.0.0.0:2375`.** Internet scanners find these within hours.
- **No log rotation** leading to disks full of `*-json.log` files.
- **Editing daemon.json with a trailing comma** or comments (JSON does not allow them).
- **Assuming a reload applies everything.**
- **Mounting the socket in containers** for convenience.

## 11. Interview Questions

**🎯 Beginner:** _"Where does Docker's configuration live, and how do you change a daemon setting?"_
**Model answer:** The daemon reads `/etc/docker/daemon.json` on Linux, with flags on the `dockerd` command line as an alternative, but the same option must not be set in both places or the daemon refuses to start. After editing, reload or restart with `systemctl restart docker` (some settings like `debug` accept `SIGHUP`). Verify with `docker info`. Rootless mode uses `~/.config/docker/daemon.json` instead.
_What the interviewer is probing for:_ Basic daemon configuration and the file-versus-flag conflict.

**🎯 Intermediate:** _"The daemon fails to start after you edited daemon.json. How do you find and fix the problem?"_
**Model answer:** Run `journalctl -u docker.service` or `dockerd --validate --config-file=/etc/docker/daemon.json` to get the exact error. Common causes are invalid JSON (trailing commas), a key set both in the file and in the systemd unit's `ExecStart` (for example `hosts`), and unknown or misspelled options. Fix the file, then `systemctl daemon-reload` and restart. Keep a backup or version control of the file so rollback is a copy away.
_What the interviewer is probing for:_ Systematic log-driven debugging.

**🎯 Senior:** _"Explain docker.sock permissions and the safest ways to give a CI job or tool access to Docker."_
**Model answer:** The socket `/var/run/docker.sock` is owned by root:docker, and anyone who can write to it can start a privileged container mounting `/`, so access is root-equivalent. Mounting the socket into a container hands that same power to the container. Safer options are rootless Docker, a socket proxy that allows only specific API endpoints, a remote daemon over TLS with client certificate auth on 2376 (never an unauthenticated 2375), or daemonless builders like BuildKit or Kaniko in CI. If the group must be used, limit membership and audit it.
_What the interviewer is probing for:_ Recognition that socket access equals root and knowledge of mitigations.

**🎯 Architect:** _"Define a baseline daemon.json for a production fleet and explain the reasoning for each setting."_
**Model answer:** I would set `log-driver: json-file` with `log-opts` `max-size` and `max-file` so logs cannot fill disks, `live-restore: true` so daemon restarts do not kill containers, `default-ulimits` and `default-address-pools` to avoid subnet clashes with corporate networks, and `userns-remap` or rootless where compatible. Add `no-new-privileges`, a default seccomp profile, `icc: false` on the default bridge, `registry-mirrors` for pull resilience, and `data-root` on a dedicated disk. Manage the file through configuration management and roll changes by draining nodes, since some options need a restart. The trade-off is compatibility: `userns-remap` and `icc: false` can break workloads that expect otherwise, so canary first.
_What the interviewer is probing for:_ Turning individual options into a coherent, reviewed policy.

## 12. Common Misconceptions

- **"daemon.json changes apply immediately."** Most need a restart.
- **"The docker group is just for convenience."** It is root-equivalent.
- **"Port 2375 is fine on a private network."** Any reachable host becomes a root shell provider.
- **"Log rotation is on by default."** With `json-file`, it is not.
- **"Changing `data-root` moves my data."** It only changes where the daemon looks.

## 13. 🔑 Key Takeaways

- `daemon.json` (`/etc/docker/daemon.json`) is the declarative configuration; flags must not duplicate it.
- Validate with `dockerd --validate`; know which options reload (SIGHUP) versus restart.
- Set log rotation, `live-restore`, address pools, `data-root`, and cgroup driver deliberately.
- The socket (`root:docker`, `660`) is the control plane; access equals root.
- Use TLS on 2376 or SSH for remote access; never plain 2375.
- Never `chmod 666` the socket or mount it into untrusted containers.

## 14. Related Concepts & What's Next

- [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) and [§9](Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md) explain the daemon and the client-to-socket path this section configures.
- [§12](Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md) and [§13](Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md) supply the cgroup-driver and storage-driver values set here; [§14](Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) covers the containerd socket with the same trust implications.
- Later material covers Docker's security hardening (rootless mode, user namespaces, seccomp), logging drivers, and daemon operations in production in depth.

**Next Section:** Part 3 begins with [§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md) (Image Anatomy: Layers, Manifest, and Config)
