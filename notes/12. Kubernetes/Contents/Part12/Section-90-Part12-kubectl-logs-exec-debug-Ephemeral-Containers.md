# Section 90 (Part 12): kubectl logs, exec, debug, and Ephemeral Containers

## 1. Definition

**Plain language:** Probes (§89) tell you _that_ something is wrong — a failing readiness check, a restarting container — but they rarely tell you _why_. Once something is flagged as unhealthy, an engineer needs to actually look inside: read what the application printed before it died, run a command inside the live container, or attach a debugging toolset to a container image that was deliberately built without one. This section covers the manual, human-driven tools for exactly that.

**Precise definition:** `kubectl logs` retrieves the stdout/stderr stream the container runtime has captured for a container, sourced from files the kubelet (§9) maintains per-container on the node, independent of whether the container is still running. `kubectl exec` opens an interactive (or one-shot) session running an additional command **inside an already-running container's** namespaces, requiring that container to already have a shell or the target binary present in its filesystem. `kubectl debug` addresses exactly the case `exec` cannot: a **distroless** or otherwise minimal production image with no shell and no debugging tools at all. It does this via **ephemeral containers** — a special container type added to a running Pod's `spec.ephemeralContainers` list, which share the target Pod's network and (optionally, via `--target`) process namespace, letting a full-featured debug image (e.g., `busybox`, or a purpose-built `netshoot`) attach alongside a minimal production container without modifying, restarting, or replacing it.

## 2. Why This Matters

- **`kubectl logs` is almost always the first command run during any incident**, and understanding its `--previous`, `--since`, and multi-container flags correctly is the difference between diagnosing a `CrashLoopBackOff` (§98, Part 13) in seconds versus staring at logs from the wrong container restart entirely.
- **Ephemeral containers exist because minimal/distroless production images are a deliberate, correct security practice (smaller attack surface, no shell for an attacker to pivot through), and that same hardening breaks the traditional `kubectl exec`-a-shell debugging workflow** — this section's `kubectl debug` content is the direct answer to a security improvement elsewhere in the roadmap otherwise creating an operational dead end.
- **None of these tools modify the object a controller is reconciling** — `kubectl exec` and ephemeral containers operate on a live running Pod without touching its `spec.containers` (the part a Deployment's ReplicaSet, §27, actually manages), which is precisely why they're safe to use for diagnosis without triggering an unwanted rollout or restart.

🔑 **Key Takeaway:** `kubectl logs` reads what already happened, `kubectl exec` runs commands inside an already-capable running container, and `kubectl debug`/ephemeral containers solve the harder case of debugging a minimal image with no shell at all by attaching a separate debug container into the same Pod's namespaces without disturbing the original container.

## 3. Prerequisites and Dependencies

Builds directly on §89 (probes — the automated signal that typically precedes reaching for these manual tools) and §24 (Pod Spec Anatomy, Part 4, particularly the shared network namespace mechanics that make ephemeral containers possible at all). Assumes familiarity with §45 (SecurityContext, Part 6) since minimal/distroless images and read-only root filesystems are exactly the hardening choices that motivate ephemeral containers as a debugging mechanism.

## 4. Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────┐
│                              Node                                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                          Pod                                     │  |
│  │   Network namespace: shared (single IP)                          │  │
│  │                                                                  │  │
│  │  ┌────────────────┐   ┌─────────────────┐   ┌───────────────────┐│  │
│  │  │ Container: app │   │ initContainer   │   │ ephemeralContainer││  │
│  │  │ (distroless,   │   │ (already exited)│   │ (added AFTER      ││  │
│  │  │  no shell)     │   │                 │   │  Pod creation,    ││  │
│  │  │                │   │                 │   │  e.g. busybox)    ││  │
│  │  └───────┬────────┘   └─────────────────┘   └─────────┬─────────┘│  │
│  │          │  logs captured by kubelet                  │          │  │
│  │          │  (readable even after container dies)      │          │  │
│  │          │                                            │          │  │
│  │          │          --target=app shares app's         │          │  │
│  │          │          process namespace (can see its    │          │  │
│  │          │          PIDs, /proc/<pid>/root filesystem)│          │  │
│  │          └────────────────────────────────────────────┘          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘

kubectl logs   → reads captured stdout/stderr, works even on a dead/restarted container (--previous)
kubectl exec   → requires shell/binary already present in the target container's own filesystem
kubectl debug  → injects a NEW ephemeral container into the Pod, no restart, no spec.containers change
```

- **`kubectl logs` reads from files the kubelet already maintains on disk**, which is why `--previous` works even after a container has crashed and restarted — the prior container's captured output isn't discarded the instant the process exits.
- **An ephemeral container never appears in `spec.containers`** — it lives in its own `spec.ephemeralContainers` list, is added via a dedicated subresource update, and critically cannot be removed once added (the Pod must be deleted and recreated to get rid of it) — a deliberate, minimal-surface design choice.
- **`--target=<container>` on `kubectl debug` is what grants **process** namespace visibility**, not just network — without it, the ephemeral container shares the Pod's network namespace but sees only its own process tree, unable to inspect the target container's running processes or `/proc` filesystem.

## 5. Hands-On: Logs, Exec, and Ephemeral Container Debugging

### 5.1 kubectl logs — Reading Captured Output

**Purpose:** Retrieve current and previous container output, across single- and multi-container Pods.

**Syntax:** `kubectl logs <pod> [-c <container>] [--previous] [--since=<duration>] [-f] [--tail=<n>]`

```bash
# Current logs from a single-container Pod
kubectl logs web-app-7d4f9c-x8k2p

# Logs from the PRIOR instance of a crashed/restarted container
kubectl logs web-app-7d4f9c-x8k2p --previous

# Multi-container Pod — container name required
kubectl logs web-app-7d4f9c-x8k2p -c sidecar

# Follow live, last 100 lines, only the last 10 minutes
kubectl logs web-app-7d4f9c-x8k2p -f --tail=100 --since=10m

# All Pods matching a label selector at once
kubectl logs -l app=web-app --all-containers=true --prefix
```

**Example usage and expected output:**

```bash
$ kubectl logs web-app-7d4f9c-x8k2p --previous
2026-07-30T09:14:02Z ERROR failed to connect to db-service:5432: connection refused
2026-07-30T09:14:02Z FATAL shutting down after 3 failed connection attempts
```

**Production usage example:** `--previous` is the single most valuable flag for diagnosing `CrashLoopBackOff` (§98, Part 13) — by the time an engineer runs `kubectl logs` without it, the container has often already restarted and the _current_ logs show only the fresh, uninformative startup sequence, not the actual failure that caused the crash.

**Common errors:** Running `kubectl logs <pod>` on a multi-container Pod without `-c <container>` — this returns an error (`a container name must be specified`) rather than a meaningful default, a frequent stumbling block for engineers debugging a sidecar-containing Pod for the first time.

### 5.2 kubectl exec — Running Commands in a Live Container

**Purpose:** Open an interactive shell or run a one-shot command inside a running container that already has the necessary binary present.

**Syntax:** `kubectl exec [-it] <pod> [-c <container>] -- <command>`

```bash
# Interactive shell
kubectl exec -it web-app-7d4f9c-x8k2p -- /bin/sh

# One-shot command, explicit container in a multi-container Pod
kubectl exec web-app-7d4f9c-x8k2p -c app -- env

# Check DNS resolution from inside the Pod's network namespace
kubectl exec web-app-7d4f9c-x8k2p -- nslookup db-service.production.svc.cluster.local
```

**Example usage and expected output:**

```bash
$ kubectl exec -it web-app-7d4f9c-x8k2p -- /bin/sh
/ # curl -s localhost:8080/healthz
{"status":"ok"}

$ kubectl exec distroless-app-xk2p -- /bin/sh
OCI runtime exec failed: exec failed: unable to start container process: exec: "/bin/sh": stat /bin/sh: no such file or directory: unknown
```

**Production usage example:** `kubectl exec` is the standard first move for confirming whether an issue is inside the container (application logic, local config) versus outside it (network, DNS, an unreachable dependency) — running `curl localhost:<port>/<healthEndpoint>` from inside the container isolates whether the app itself is responding correctly, independent of any Service or network layer between it and the outside world.

**Common errors:** Attempting `kubectl exec ... -- /bin/sh` against a distroless or scratch-based production image, hitting `exec: "/bin/sh": stat /bin/sh: no such file or directory` — this is the exact scenario `kubectl debug` and ephemeral containers exist to solve, not a bug to work around with `-it`.

### 5.3 kubectl debug — Ephemeral Containers for Minimal Images

**Purpose:** Attach a full-featured debug container into a running Pod that has no shell of its own, without restarting or modifying the original container.

**Syntax:** `kubectl debug <pod> -it --image=<debug-image> --target=<container>`

```bash
# Attach busybox as an ephemeral container, sharing the "app" container's process namespace
kubectl debug distroless-app-xk2p -it --image=busybox:1.36 --target=app

# Create a full COPY of the Pod with a debug container swapped in (doesn't touch the original)
kubectl debug distroless-app-xk2p -it --image=busybox:1.36 --copy-to=debug-copy --container=app

# Debug a NODE itself (creates a privileged Pod on that node with host filesystem mounted at /host)
kubectl debug node/worker-3 -it --image=busybox:1.36
```

**Example usage and expected output:**

```bash
$ kubectl debug distroless-app-xk2p -it --image=busybox:1.36 --target=app
Targeting container "app". If you don't see processes from this container it may be because the container runtime doesn't support this feature.
Defaulting debug container name to debugger-8x7fn.
If you don't see a command prompt, try pressing enter.
/ # ps aux
PID   USER     TIME  COMMAND
    1 65534     0:00 /app/server
   17 root      0:00 ps aux
/ # ls -la /proc/1/root/app/
# inspects the target container's filesystem via the shared process namespace
```

**Production usage example:** `--target=app` is what makes the ephemeral container able to see the distroless container's running process (`PID 1`) and, through `/proc/1/root/`, its actual filesystem contents — this is the standard pattern for inspecting a hardened production image's config files or file layout without ever needing to rebuild that image with debugging tools baked in, preserving its minimal attack surface permanently.

**Common errors:** Forgetting that an ephemeral container, once added, **cannot be removed** from a Pod without deleting and recreating the entire Pod — repeatedly running `kubectl debug` against the same Pod during an extended incident accumulates ephemeral containers that persist in the Pod's spec indefinitely, which is a minor but real cleanup consideration for long-lived Pods (e.g., in a StatefulSet, §33, Part 5).

## 6. Production Usage Notes

- **`kubectl logs` only ever shows what the container itself wrote to stdout/stderr** — an application logging exclusively to a local file inside the container (rather than stdout/stderr) is invisible to `kubectl logs` entirely, which is one of several reasons centralized logging pipelines (§94, Part 12) that scrape stdout/stderr, not arbitrary files, are the standard.
- **`kubectl debug node/<name>` is a distinct and more privileged use case than debugging a Pod** — it creates a new Pod on the target node with the host's filesystem mounted at `/host` and typically runs with elevated privileges, making it a genuinely powerful (and risky) node-level diagnostic tool that deserves the same access scrutiny as direct SSH node access would.
- **`--copy-to` is the safer choice when the original Pod must remain completely untouched** — it creates an entirely new Pod (a copy of the original with the debug container substituted in) rather than mutating the live, traffic-serving Pod's `ephemeralContainers` list, at the cost of debugging a copy rather than the exact live instance experiencing the issue.

## 7. Security Considerations

- **`kubectl exec` and `kubectl debug` both require RBAC permission on the `pods/exec` (and `pods/ephemeralcontainers`) subresource**, and both are among the most powerful capabilities an RBAC role can grant — exec access to a Pod is effectively equivalent to root-level access to whatever that container can reach, and should be scoped and audited (§79–§81, Part 10) with the same rigor as direct host access.
- **Ephemeral containers inherit the Pod's SecurityContext by default but can be given their own**, and a debug image run with elevated privileges (or `--target` process-namespace sharing) can observe the target container's environment variables, mounted Secrets, and process memory — treat `kubectl debug` access as a meaningful privilege, not a routine, low-risk convenience.
- **`kubectl debug node/<name>` grants access to the entire node's filesystem via the `/host` mount**, which is a significantly broader privilege than debugging a single Pod — this capability should be restricted to a small, audited set of operators, not granted broadly alongside ordinary Pod-level debug access.

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Likely Cause                                                                               | Resolution Path                                                                                           |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| `kubectl logs` shows only a fresh startup sequence, no error   | Container already restarted; current logs don't include the crash reason                   | Use `kubectl logs <pod> --previous` to see the prior instance's output                                    |
| `a container name must be specified` error from `kubectl logs` | Pod has multiple containers and `-c <container>` was omitted                               | Run `kubectl get pod <pod> -o jsonpath='{.spec.containers[*].name}'`, then re-run with `-c`               |
| `exec: "/bin/sh": stat ...: no such file or directory`         | Target image is distroless/minimal with no shell                                           | Use `kubectl debug <pod> -it --image=busybox --target=<container>` instead of `kubectl exec`              |
| Ephemeral debug container sees no processes from the target    | `--target=<container>` omitted, or container runtime doesn't support PID namespace sharing | Re-run with `--target=<container>` explicitly; confirm runtime support (containerd/CRI-O, §11 support it) |

## 9. Best Practices

- Reach for `kubectl logs --previous` first, before `kubectl exec`, when diagnosing any crash or restart — it's non-invasive and frequently answers the question immediately.
- Use ephemeral containers (`kubectl debug --target=`) rather than rebuilding a hardened production image with debugging tools baked in "just in case" — this preserves the image's minimal attack surface permanently while still allowing full debugging capability when actually needed.
- Scope RBAC for `pods/exec`, `pods/ephemeralcontainers`, and especially `kubectl debug node/` tightly and audit their use — these are among the most powerful capabilities in the cluster and deserve access review commensurate with that power.

## 10. Common Anti-Patterns / Mistakes

- **Adding a shell and debugging tools to every production image "just in case" instead of using ephemeral containers**, permanently expanding the attack surface of every deployed container to accommodate an occasional debugging need.
- **Granting broad `pods/exec` RBAC access to entire teams by default**, rather than scoping it to specific namespaces or environments and treating it with the access rigor of direct host-level access.
- **Repeatedly running `kubectl debug` against the same long-lived Pod (e.g., a StatefulSet member) without accounting for the fact that ephemeral containers accumulate and cannot be removed**, leaving a growing, permanent list of stale debug containers in the Pod's spec.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `kubectl logs` and `kubectl exec`?"_
**Model answer:** `kubectl logs` retrieves the stdout/stderr output a container has already produced, sourced from files the kubelet maintains on the node — it works even after the container has crashed (with `--previous`) since it's just reading captured history, not interacting with a live process. `kubectl exec` opens a live session running an additional command inside an **already-running** container's own namespaces, and requires that the target container's filesystem already contains the shell or binary being run — it fails immediately against a minimal image with no shell present.
_What the interviewer is probing for:_ Clear distinction between reading historical output versus interacting with a live process, and awareness that `exec` has a filesystem prerequisite `logs` does not.

**🎯 Intermediate:** _"`kubectl exec -it <pod> -- /bin/sh` fails with 'no such file or directory.' What's happening, and how do you debug this Pod instead?"_
**Model answer:** The container image is almost certainly distroless or otherwise minimal, with no shell binary present at all — this is often a deliberate security hardening choice, not a misconfiguration, since a smaller image with no shell reduces the attack surface available to anyone who might compromise the container. The correct approach is `kubectl debug <pod> -it --image=busybox --target=<container-name>`, which attaches a separate, full-featured ephemeral container into the same Pod, sharing its network namespace and (via `--target`) its process namespace, without modifying, restarting, or adding a shell to the original hardened container at all.
_What the interviewer is probing for:_ Recognizing that a shell-less image is a security feature, not a bug, and knowing the correct modern tool (ephemeral containers) rather than suggesting the image be rebuilt with a shell added back in.

**🎯 Senior:** _"Why can't an ephemeral container be removed once added to a Pod, and what operational implications does that have?"_
**Model answer:** Ephemeral containers were deliberately designed as an append-only, minimal-surface mechanism — the API doesn't support removing them, in part to keep the mechanism simple and auditable (a Pod's ephemeral container history is a permanent, visible record of what debugging access occurred against it) and in part because container removal from a live Pod isn't a generally supported operation in the Kubernetes object model to begin with. Operationally, this means repeated `kubectl debug` sessions against a long-lived Pod — particularly a StatefulSet member that isn't casually recreated — accumulate ephemeral containers indefinitely; the practical response is either accepting that accumulation as a minor cost for genuinely long-lived Pods, or preferring `kubectl debug --copy-to` to debug a disposable copy instead of the live Pod when repeated debugging sessions are anticipated.
_What the interviewer is probing for:_ Understanding the design rationale (auditability, API simplicity) behind an easily-overlooked limitation, and a practical mitigation (`--copy-to`) rather than treating it as a pure inconvenience.

**🎯 Architect:** _"Design an access model for debugging capabilities (`exec`, `debug`, node-level debug) across a multi-tenant cluster with strict security requirements."_
**Model answer:** I'd tier debugging access by blast radius rather than granting a single flat "debug access" permission. Ordinary application engineers get `pods/exec` and `pods/ephemeralcontainers` scoped via RBAC (§74, Part 10) to their own team's namespace only, sufficient for the overwhelming majority of day-to-day debugging without touching anything outside their blast radius. A smaller, audited platform/SRE group gets broader cross-namespace exec access for incident response, ideally gated behind a break-glass or time-boxed access mechanism rather than standing broad grants. `kubectl debug node/<name>` — which mounts an entire node's filesystem and typically runs privileged — I'd restrict to an even smaller set of platform operators, since it's functionally equivalent to direct host access and a meaningful escalation beyond Pod-level debugging. Across all tiers, I'd ensure `pods/exec` and `pods/ephemeralcontainers` usage is captured in cluster audit logs (§96, Part 12) with alerting on exec sessions against production namespaces outside expected incident windows, since exec access is powerful enough that its use itself is a security-relevant event worth observing, not just gating.
_What the interviewer is probing for:_ Ability to design tiered, blast-radius-aware access control for a capability that's operationally necessary but also one of the most powerful privileges in the cluster, plus awareness that usage itself should be observable, not just access-controlled.

## 12. Common Misconceptions

1. **"`kubectl logs` without `--previous` always shows the relevant crash information."** Once a container restarts, current logs show only the new instance's output — the crash-causing output is only visible via `--previous`.
2. **"A shell-less production image is a debugging inconvenience to work around."** It's frequently a deliberate security hardening decision (reduced attack surface), and ephemeral containers are the correct, purpose-built tool to debug it without undoing that hardening.
3. **"Ephemeral containers can be removed once the debugging session is done."** They cannot — once added to a Pod's `ephemeralContainers` list, they persist for that Pod's lifetime; only deleting and recreating the Pod removes them.
4. **"`kubectl exec` and `kubectl debug` are roughly equally low-risk operations."** Both grant powerful, effectively root-equivalent access to a running container (and `kubectl debug node/` to an entire node's filesystem), and should be access-controlled and audited with corresponding rigor, not treated as routine conveniences.

## 13. 🔑 Key Takeaways

- `kubectl logs` reads already-captured output (use `--previous` for a crashed container's final words); `kubectl exec` runs commands inside an already-capable live container; `kubectl debug`/ephemeral containers solve debugging a shell-less minimal image without modifying it.
- `--target=<container>` on `kubectl debug` is what grants process-namespace visibility into the target container, beyond the network namespace shared by default.
- Ephemeral containers are append-only — they cannot be removed from a Pod once added, only avoided entirely (via `--copy-to`) or accepted as a minor persistent artifact.
- `pods/exec`, `pods/ephemeralcontainers`, and especially `kubectl debug node/` are high-privilege capabilities that deserve RBAC scoping and audit logging commensurate with direct host access, not routine convenience-tier access.
- Shell-less/distroless production images are a deliberate security improvement, and ephemeral containers exist specifically so that hardening doesn't come at the cost of debuggability.

## 14. Related Concepts & What's Next

This section built on §89's probe mechanics (the automated signal that typically precedes reaching for these manual tools) and §24's shared Pod network namespace (the mechanism ephemeral containers rely on). §91, next, moves from manual, human-driven diagnosis to the automated metrics pipeline — metrics-server and the metrics.k8s.io/custom.metrics.k8s.io/external.metrics.k8s.io APIs — that feeds both `kubectl top` and the Horizontal Pod Autoscaler (§37, Part 5) covered earlier in the roadmap.

**Next Section:** §91 — `Section-91-Part12-Metrics-Server-Kubernetes-Metrics-Pipeline.md`
