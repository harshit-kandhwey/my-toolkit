# Section 9 (Part 2): Client-Server Model: Docker CLI and the REST API

## 1. Definition

**Plain language:** The `docker` command you type is only a thin client. It does not start containers itself; it sends an HTTP request to the Docker daemon, which does the work and replies. Anything the CLI can do, any program can do by sending the same HTTP requests.

**Precise definition:** Docker uses a **client-server architecture**. The server, `dockerd` ([§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), exposes a versioned **REST API** (for example `/v1.47/containers/json`) over a Unix socket (`/var/run/docker.sock` by default), optionally over TCP (unencrypted on port 2375 or TLS on 2376), or over SSH via `ssh://` transport. The CLI, SDKs (Go, Python), Docker Compose, and third-party tools are all API clients. The target daemon is chosen with the `DOCKER_HOST` environment variable, the `-H` flag, or a named **context** (`docker context`).

> 💡 **Tip:** `docker` commands are just wrappers over `curl --unix-socket /var/run/docker.sock`. When a tool behaves oddly, replaying its request with curl is often the fastest way to see what the daemon really returned.

## 2. Why This Matters

- **It enables remote management.** The same CLI can drive a local daemon, a remote host over SSH, or a cloud VM, just by switching the context.
- **It explains tooling.** CI systems, dashboards (Portainer), and IDE plugins all use the API; understanding it clarifies what they can and cannot do.
- **It defines the security boundary.** Whoever can reach the API socket controls the host ([§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), so the transport and permissions are the perimeter.
- **It supports version compatibility reasoning.** Client and daemon negotiate an API version, and mismatches produce specific errors.
- **It lets you automate without a CLI.** Scripts and services can call the API through SDKs for finer control than shelling out.

## 3. Prerequisites and Dependencies

Requires [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) (dockerd as the server) and basic HTTP knowledge. Socket permissions and TLS setup are covered in [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md). The image and runtime specs behind API payloads are in [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md). Compose, contexts in CI, and remote build topics are covered in later Parts.

## 4. Architecture / Conceptual Diagram

```text
  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
  │  docker CLI   │   │ Docker SDK    │   │ curl / Compose │
  │               │   │ (Go, Python)  │   │ / Portainer    │
  └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
          └───────────────────┼───────────────────┘
                              │ HTTP + JSON  (API v1.xx)
        ┌─────────────────────┼─────────────────────────┐
        ▼                     ▼                         ▼
  unix:///var/run/     tcp://host:2376           ssh://user@host
   docker.sock          (TLS, mutual auth)       (runs `docker system
   (default, local)                               dial-stdio` remotely)
        └─────────────────────┼─────────────────────────┘
                              ▼
                           dockerd
                              │
                              ▼
                     containerd ► shim ► runc

   Selection order: -H flag  ►  DOCKER_HOST  ►  active context  ►  default socket
```

- **All clients speak the same protocol.** Anything in the CLI is available through the API, and the reverse is mostly true.
- **Three transports.** Unix socket for local use, TCP+TLS for remote, and SSH for the simplest secure remote access.
- **Streaming endpoints use HTTP upgrades.** `attach`, `exec`, and `logs` hijack the connection to stream stdin and stdout.

## 5. Hands-On

### 5.1 Call the API with curl

**Purpose:** Prove that the daemon is just an HTTP server on a Unix socket.

**Syntax:**

```bash
curl --unix-socket /var/run/docker.sock http://localhost/version
curl --unix-socket /var/run/docker.sock http://localhost/containers/json
```

**Example usage and expected output:**

```bash
$ curl -s --unix-socket /var/run/docker.sock http://localhost/version | head -c 220
{"Platform":{"Name":"Docker Engine - Community"},"Components":[{"Name":"Engine","Version":"27.3.1","Details":{"ApiVersion":"1.47","MinAPIVersion":"1.24"

$ curl -s --unix-socket /var/run/docker.sock http://localhost/containers/json | jq '.[].Names'
[
  "/web"
]
```

**Production usage example:** Health scripts on minimal hosts without the CLI installed can query container state directly, and monitoring agents commonly do exactly this.

**Common errors:** `curl: (7) Couldn't connect` or `Permission denied` means the socket path is wrong or your user lacks access (see [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

### 5.2 See What the CLI Really Sends

**Purpose:** Observe the API traffic a CLI command produces.

**Syntax:**

```bash
docker --debug ps
# or watch the daemon side
sudo journalctl -u docker -f
```

**Example usage and expected output:**

```bash
$ docker ps --format '{{.Names}}' && curl -s --unix-socket /var/run/docker.sock \
    'http://localhost/containers/json?all=1&filters=%7B%22status%22%3A%5B%22running%22%5D%7D' | jq length
web
1
```

**Production usage example:** Reproducing a failing pipeline step with curl isolates whether the bug is in the tooling or in the daemon's response.

**Common errors:** Forgetting to URL-encode the `filters` JSON returns an error such as `invalid filter`.

### 5.3 Use Contexts to Target Remote Daemons

**Purpose:** Point the same CLI at a remote host over SSH without changing your workflow.

**Syntax:**

```bash
docker context create prod --docker "host=ssh://deploy@203.0.113.10"
docker context ls
docker --context prod ps
docker context use prod
```

**Example usage and expected output:**

```bash
$ docker context ls
NAME        DESCRIPTION                               DOCKER ENDPOINT                    ERROR
default *   Current DOCKER_HOST based configuration   unix:///var/run/docker.sock
prod                                                  ssh://deploy@203.0.113.10

$ docker --context prod ps
CONTAINER ID   IMAGE        COMMAND    CREATED       STATUS       PORTS   NAMES
41d0e7b2a9c3   nginx:1.27   "/docker…" 2 hours ago   Up 2 hours   80/tcp  edge
```

**Production usage example:** Deployment scripts run `docker --context prod compose up -d`, using SSH keys and the remote host's own access controls rather than an exposed TCP port.

**Common errors:** `Cannot connect to the Docker daemon at ssh://...` is usually SSH auth, a missing `docker` binary for the remote user, or the user not being in the `docker` group.

### 5.4 Pin and Negotiate the API Version

**Purpose:** Handle client and server version mismatches.

**Syntax:**

```bash
docker version --format 'client={{.Client.APIVersion}} server={{.Server.APIVersion}}'
DOCKER_API_VERSION=1.43 docker ps
```

**Example usage and expected output:**

```bash
$ docker version --format 'client={{.Client.APIVersion}} server={{.Server.APIVersion}}'
client=1.47 server=1.47

$ DOCKER_API_VERSION=1.20 docker ps
Error response from daemon: client version 1.20 is too old. Minimum supported API version is 1.24, please upgrade your client to a newer version
```

**Production usage example:** Older CI images with old clients pinned to a lower API version keep working against a newer daemon, as long as the version is above the daemon's minimum.

**Common errors:** `client version 1.xx is too new. Maximum supported API version is 1.yy` means the client is newer than the daemon; set `DOCKER_API_VERSION` or upgrade the daemon.

## 6. Production Usage Notes

- **Prefer SSH contexts over exposed TCP.** Authentication and encryption come for free from SSH.
- **If TCP is needed, always use TLS with client certificates** on port 2376.
- **Name contexts by environment** and display the active context in your shell prompt to avoid running commands against production by accident.
- **Use SDKs for automation** rather than parsing CLI output, since the JSON API is stable and versioned.
- **Socket proxies** (limiting which API endpoints a tool can call) are a common pattern for CI runners and dashboards.

## 7. Security Considerations

- **Unauthenticated TCP on 2375 is a full remote root compromise** and is routinely exploited by internet scanners to deploy cryptominers.
- **Membership in the `docker` group is root-equivalent.** Grant it as carefully as sudo.
- **Mounting the socket into a container gives it host control.** If needed, use a filtering proxy or a rootless daemon.
- **Protect client TLS keys** and rotate certificates.
- **API responses can include secrets** in environment variables through `inspect`; restrict who can call it.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `permission denied ... docker.sock` | User not in `docker` group | Add the user and re-login, or use `sudo` |
| `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | Daemon stopped | `sudo systemctl start docker` |
| Commands hit the wrong host | Stale `DOCKER_HOST` or context | `env \| grep DOCKER`, `docker context ls` |
| `client version is too new` | Client newer than daemon | Set `DOCKER_API_VERSION` or upgrade the daemon |
| SSH context fails | Missing key or shell banner output | Test `ssh host docker info` manually |

## 9. Best Practices

- Use contexts and SSH for remote access rather than exposing the API.
- Keep clients and daemons within a supported version window.
- Automate through SDKs and the API rather than scraping table output; use `--format` when scripting the CLI.
- Restrict socket access with group membership and filtering proxies.
- Audit for any listening 2375/2376 ports as part of host baselines.

## 10. Common Anti-Patterns / Mistakes

- **Enabling `-H tcp://0.0.0.0:2375` "temporarily".** It rarely stays temporary.
- **Setting `DOCKER_HOST` globally in a profile** and forgetting it points at production.
- **Parsing `docker ps` output with `awk`** instead of `--format '{{json .}}'`.
- **Sharing the `docker` group broadly** to avoid `sudo` prompts.
- **Assuming API endpoints are stable across major changes** without pinning a version prefix.

## 11. Interview Questions

**🎯 Beginner:** _"Is the `docker` command the Docker daemon? How does it talk to it, and how can you see that?"_
**Model answer:** No. `docker` is a client that sends requests to dockerd over a REST API, by default through the Unix socket `/var/run/docker.sock`. You can bypass the CLI entirely: `curl --unix-socket /var/run/docker.sock http://localhost/containers/json` returns the same data as `docker ps`. The `DOCKER_HOST` variable or a context changes the endpoint.
_What the interviewer is probing for:_ Understanding the client-server split and the default transport.

**🎯 Intermediate:** _"You need to run docker commands against a remote host from your laptop. What are your options and which do you prefer?"_
**Model answer:** Options are SSH, TCP with mutual TLS, or TCP without TLS (which is unacceptable). I prefer an SSH context: `docker context create prod --docker "host=ssh://user@host"` then `docker --context prod ps` or `docker context use prod`. It reuses SSH keys and auditing and needs no listening TCP port. API version mismatches are handled by negotiation, or you can pin with `DOCKER_API_VERSION`.
_What the interviewer is probing for:_ Choosing a secure transport and using contexts.

**🎯 Senior:** _"A CI job needs to build images. How do you provide daemon access without giving it host root, and how would you debug a tool that misreports container state?"_
**Model answer:** Avoid mounting the host socket. Use rootless Docker or a dedicated ephemeral build daemon, a remote BuildKit builder, or a socket proxy that allows only the required endpoints. To debug the tool, replay its requests with `curl --unix-socket /var/run/docker.sock` and compare with CLI output, checking the API version path (`/v1.43/...`) and filters. Differences usually point to the tool's request or parsing, not the daemon.
_What the interviewer is probing for:_ Balancing CI needs with least privilege and using the raw API for debugging.

**🎯 Architect:** _"Design remote access and authorization for a fleet of Docker hosts. Why is API access a privilege boundary problem?"_
**Model answer:** API calls can create privileged containers with host mounts, so anyone who reaches the socket is effectively root, and Docker's default authorization is all-or-nothing. Design: no TCP listeners, SSH with short-lived certificates via a bastion, per-environment contexts, audit logging, and an authorization plugin or proxy that restricts endpoints. Prefer declarative deployment (Compose over SSH, GitOps, Kubernetes) so humans rarely touch daemons directly.
_What the interviewer is probing for:_ Treating the API as a security boundary and designing access with audit and least privilege.
## 12. Common Misconceptions

- **"The CLI runs containers."** It only sends requests.
- **"Port 2375 is fine on a private network."** Any compromised host on that network gets root on the Docker host.
- **"Contexts only work with Docker Desktop."** They work with any engine.
- **"The API is only for Docker's own tools."** It is public and documented.

## 13. 🔑 Key Takeaways

- The CLI is a client of dockerd's versioned REST API.
- Transports: Unix socket, TCP (ideally TLS), and SSH.
- Use `docker context` to manage multiple daemons safely.
- API access is root-equivalent; never expose it unauthenticated.
- `curl --unix-socket` is a powerful debugging tool.

## 14. Related Concepts & What's Next

- [§8](Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) describes the daemon behind the API.
- [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) explains the OCI specs whose data appears in API payloads.
- [§15](Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) covers `daemon.json`, `hosts`, TLS settings, and socket permissions in detail.
- Later Parts cover Compose, remote builders, and security hardening of the daemon.

**Next Section:** [§10](Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) — `Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md`
