# Section 101 (Part 14): Common Docker Interview Questions (Beginner to Advanced)

## 1. Definition

**Plain language:** A graded bank of the questions interviewers actually ask about Docker, with short model answers, grouped by topic and difficulty. Use it to rehearse out loud: answer first, then compare.

**Precise definition:** Each entry below is a question with a compact answer of two to five sentences, tagged **[B]** beginner, **[I]** intermediate, **[S]** senior or **[A]** architect. Longer scenario, Dockerfile-review, system-design and whiteboard material lives in [§102](Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md) to [§105](Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank.md). Answers assume Docker Engine 27/28, Compose v2, BuildKit as the default builder and cgroup v2.

> 💡 **Tip:** A strong answer has three parts: the definition, the mechanism underneath, and one trade-off or failure mode. Interviewers score the second and third parts.

## 2. Why This Matters

- Docker is a baseline expectation for DevOps, SRE, backend and platform roles; screening questions are predictable.
- Mechanism-level answers ("namespaces and cgroups", "layers are content-addressed") distinguish users from engineers.
- The same facts support the DCA ([§100](Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)) and day-to-day incident response.
- Rehearsed, concise answers free time for the follow-up discussion where senior candidates earn the offer.

## 3. Prerequisites and Dependencies

All earlier parts; this section is a revision index. Quick pointers: fundamentals ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)), internals ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md), [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), Dockerfile ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md), [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), networking ([§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), storage ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), security ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)), builds ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)).

## 4. Architecture / Conceptual Diagram

```text
   Question difficulty ladder                    Answer structure

   [A] trade-offs, org-wide decisions            ┌───────────────────────────────┐
        ▲                                        │ 1. One-sentence definition    │
   [S] failure modes, internals, scale           │ 2. Mechanism (how it works)   │
        ▲                                        │ 3. Command or example         │
   [I] how and why, commands, defaults           │ 4. Trade-off / failure mode   │
        ▲                                        └───────────────┬───────────────┘
   [B] what is it, basic commands                                ▼
                                                  "What would you do differently
   Topic map: fundamentals ► images ► runtime ►    in production?"  ◄── follow-up
              networking ► storage ► security ►
              build/CI ► operations ► orchestration
```

## 5. Hands-On

Rehearse by covering the answer and speaking it aloud. Try the commands in a throwaway container or VM.

### 5.1 Fundamentals

**Q1 [B]. What is a container and how does it differ from a VM?**
A container is an isolated process (or process tree) on the host kernel, constrained by namespaces (what it sees) and cgroups (what it can use), with a layered root filesystem. A VM virtualizes hardware and runs its own kernel under a hypervisor. Containers start in milliseconds and are lighter but share the host kernel, so isolation is weaker.

**Q2 [B]. Image vs container?**
An image is an immutable, layered template (filesystem plus config); a container is a running (or stopped) instance with a thin writable layer on top. One image can back many containers.

**Q3 [I]. Does a container have its own kernel? What happens on Docker Desktop for Mac or Windows?**
No. Docker Desktop runs a lightweight Linux VM (or WSL 2 backend) and containers share that VM's kernel. That is why a Linux container cannot run natively on a macOS kernel, and why bind-mount performance and networking behave differently there.

**Q4 [I]. Explain `dockerd`, containerd and runc.**
The CLI calls `dockerd` over a REST API; `dockerd` handles images, networks and volumes and delegates lifecycle to containerd, which uses a shim and runc (an OCI runtime) to create the namespaces, cgroups and process. After start, runc exits and the shim keeps the container alive, so restarting `dockerd` need not kill containers with `live-restore` ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)).


### 5.2 Images and Dockerfiles

**Q6 [B]. `COPY` vs `ADD`?**
`COPY` copies files from the build context or another stage. `ADD` also extracts local tar archives and fetches URLs, which makes it surprising; prefer `COPY` unless you need extraction.

**Q7 [B]. `CMD` vs `ENTRYPOINT`?**
`ENTRYPOINT` is the fixed executable; `CMD` is default arguments, replaced by anything after the image name in `docker run`. Final argv is ENTRYPOINT plus CMD or run-time arguments. Use exec form so the process is PID 1 and gets signals ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).

**Q8 [I]. Why does instruction order matter for build cache?**
Each instruction's cache key depends on the instruction and on its inputs (file hashes for `COPY`); a changed layer invalidates every later layer. Put rarely changing steps (OS packages, dependency manifests plus install) before frequently changing ones (source copy) ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).

**Q9 [I]. How do multi-stage builds shrink images?**
Build tools live in an early stage; the final stage starts from a minimal base and copies only artifacts with `COPY --from=build`. Compilers, caches and source never reach the runtime image ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)).

**Q10 [I]. A secret was in an earlier layer and deleted by a later `RUN rm`. Is it safe?**
No. Layers are immutable; the earlier layer still holds the file and anyone with the image can extract it. Use BuildKit secret mounts (`RUN --mount=type=secret`) so the value never lands in a layer ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).

**Q13 [S]. Choosing a base image: alpine, slim, distroless, scratch?**
Alpine is small but uses musl libc, which breaks some glibc-built binaries and can slow some workloads. Slim Debian keeps glibc with a smaller footprint. Distroless has no shell or package manager, so a smaller attack surface but harder debugging. Scratch suits static binaries ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)).

### 5.3 Running and Operating Containers

**Q14 [B]. How do you see logs, shell into a container and copy a file?**
`docker logs -f ctr`, `docker exec -it ctr sh`, `docker cp ctr:/path ./path`.

**Q15 [I]. `docker stop` vs `docker kill`; why does stop take 10 seconds?**
`stop` sends SIGTERM (or `STOPSIGNAL`), waits the grace period (default 10 s), then SIGKILL. `kill` sends SIGKILL by default. A 10-second stop means the app is not receiving or handling SIGTERM, often because a shell is PID 1.

**Q17 [I]. How do you limit memory and CPU, and what happens at the limit?**
`--memory 512m --cpus 1.5 --pids-limit 200`. Exceeding memory triggers the cgroup OOM killer; CPU limits throttle rather than kill. Setting `--memory-swap` equal to `--memory` disables swap ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)).

**Q19 [S]. A container is running but the app is unresponsive. How do you triage?**
`docker ps`/`inspect` for state and health, `docker logs --tail`, `docker stats` for resource pressure, `docker top`, `docker exec` for in-container checks, and `nsenter`/`docker run --net container:` with a debug image when the image has no tools. Check the host: disk (`docker system df`), `dmesg` for OOM, and the daemon journal ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)).


### 5.4 Networking

**Q21 [B]. What network drivers exist?**
bridge (default), host, none, overlay, macvlan, ipvlan. Single-host apps use user-defined bridges; multi-host uses overlay or a CNI under Kubernetes ([§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)).

**Q22 [I]. Why can containers on the default bridge not reach each other by name?**
The default bridge has no embedded DNS. User-defined networks provide automatic service discovery through the resolver at 127.0.0.11 and better isolation ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)).

**Q23 [I]. `EXPOSE` vs `-p`?**
`EXPOSE` is documentation (and `-P` uses it). `-p host:container` creates the NAT rule. Publishing to `0.0.0.0` can bypass host firewall rules written for the INPUT chain because Docker programs its own iptables/nftables rules ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).


### 5.5 Storage

**Q25 [B]. Volume vs bind mount vs tmpfs?**
Volumes are Docker-managed storage, portable and driver-capable; bind mounts map a host path (good for development, tied to host layout); tmpfs is RAM-only and vanishes at stop ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)).

**Q26 [I]. Where does data written inside a container go, and what happens on `rm`?**
Into the writable layer on the host (overlay2 upper dir). It is deleted with the container. Anything that must survive goes on a volume.

**Q27 [S]. How do you back up a database running in a container?**
Prefer application-level dumps (`pg_dump`, `mysqldump`) via `docker exec` for consistency; for volume-level backups, quiesce or snapshot, then archive with a helper container (`docker run --rm -v vol:/data -v $PWD:/backup alpine tar czf /backup/vol.tgz -C /data .`) and test restores regularly ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).

### 5.6 Compose

**Q28 [B]. What is Compose and how do you start a stack?**
A way to declare multi-container applications in YAML. `docker compose up -d` creates networks, volumes and services; `docker compose down -v` removes them including volumes.

**Q29 [I]. Does `depends_on` wait for the database to be ready?**
Only for start order by default. Use `depends_on: { db: { condition: service_healthy } }` with a healthcheck, and keep application-level retry logic ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)).


### 5.7 Security

**Q31 [B]. Why not run as root in a container?**
Root in the container is UID 0 on the host unless user namespaces are used; a breakout or a mounted host path turns that into host compromise. Set `USER` to an unprivileged UID.

**Q32 [I]. What is `--privileged` and why avoid it?**
It grants all capabilities, access to host devices and disables seccomp and AppArmor confinement. Use specific `--cap-add` or `--device` instead ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).

**Q33 [S]. Why is mounting `/var/run/docker.sock` dangerous?**
Access to the socket is root-equivalent on the host: the holder can start a privileged container mounting `/`. Alternatives are rootless builders (BuildKit, Kaniko), a socket proxy with an allow-list, or dedicated build runners ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).

**Q34 [S]. Build a hardened runtime profile.**
Non-root user, `--cap-drop ALL` plus only needed adds, `--read-only` with tmpfs for writable paths, `no-new-privileges`, default or custom seccomp, resource limits, pinned and scanned images, and secrets via mounts not env ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md) to [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

### 5.8 CI, Registries and Operations

**Q35 [I]. How do you speed up Docker builds in CI?**
Order Dockerfile for cache, use BuildKit cache mounts, import and export cache with `--cache-from/--cache-to` (registry or `type=gha`), keep `.dockerignore` tight, and build multi-platform with buildx only when needed ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)).

**Q37 [S]. Disk is full on a Docker host. What do you do?**
`docker system df -v` to see usage, `docker image prune -a`, `docker builder prune`, `docker volume prune` (carefully; verify unused), check container JSON logs (set `max-size`), and look for dangling build cache. Prevent recurrence with log rotation and scheduled cleanup ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).


### 5.9 Orchestration and Strategy

**Q39 [I]. Swarm vs Kubernetes in one minute?**
Swarm: built in, simple, Compose-like. Kubernetes: far richer API and ecosystem, more complex, industry standard ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

**Q40 [A]. When is Docker the wrong tool?**
When you need hard multi-tenant isolation (use VMs or microVMs), full desktop or kernel-module workloads, heavy GPU scheduling without proper runtime support, or when rootless daemonless alternatives better fit policy ([§97](../Part13/Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md)).

## 6. Production Usage Notes

- Interviewers often convert a basic question into a production one: "OK, and what happens at scale?" Prepare one production anecdote per area (logging, networking, storage, security).
- Quote real flags and defaults; vague answers read as unpracticed.
- Mention versions when behavior changed: BuildKit default since Engine 23, Compose v2 as `docker compose`, cgroup v2 default on modern distros, `docker-compose` v1 end-of-life.
- Have one clear opinion on a trade-off (alpine vs slim, Compose vs Kubernetes) and its conditions.

## 7. Security Considerations

- In interviews, volunteering security (non-root, minimal image, scanning, pinned digests, no secrets in layers) is a strong positive signal.
- Do not describe disabling security features as a fix ("just run `--privileged`"); explain the narrower alternative.
- Never reveal confidential employer details such as internal registry hostnames or incident specifics; abstract them.

## 8. Common Troubleshooting Scenarios

How interview answers fail and how to fix them.

| Symptom in your answer | Cause | Fix |
|---|---|---|
| Interviewer keeps asking "why?" | Surface-level answer | Add the mechanism (namespace, cgroup, layer) |
| Mixing up `save/export`, `ADD/COPY` | Memorized without practice | Re-run the commands in a lab |
| Rambling on open questions | No structure | Definition, mechanism, example, trade-off |
| Cannot recall flags | Reading without typing | Rehearse commands from memory |
| Stuck on a debugging scenario | No method | State a triage order: state, logs, resources, network, host |
| Vague on Kubernetes | Docker-only background | Learn the vocabulary map in [§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md) |

## 9. Best Practices

- Practise speaking answers aloud in under 90 seconds, then expand on request.
- Ask clarifying questions in scenario items (scale, OS, orchestrator, constraints).
- Use a consistent debug sequence: `docker ps -a`, `inspect`, `logs`, `stats`, `exec`, host metrics.
- Prefer exact vocabulary: layer, digest, namespace, cgroup, PID 1, SIGTERM.
- Admit uncertainty and explain how you would verify (`docker run --rm`, docs, `--help`).
- Prepare a short "project story": problem, your design, a failure, the fix, measured outcome.

## 10. Common Anti-Patterns / Mistakes

- Claiming containers are "lightweight VMs" without correction.
- Saying "Docker is secure because it is isolated" without qualification.
- Reciting commands without explaining effects.
- Recommending `docker system prune -af --volumes` on a shared host.
- Answering every design question with "use Kubernetes".
- Memorizing answers verbatim, then failing a variation.
- Ignoring the cost side: image size, build time, operations burden.

## 11. Interview Questions

**🎯 Beginner:** _"Explain Docker to a non-technical manager in two sentences, then show you understand the details: what actually happens when you run `docker run nginx`?"_
**Model answer:** Docker packages an application with everything it needs so it runs the same way on any machine, like a standard shipping container. Technically: the CLI calls the daemon; if `nginx:latest` is not local, it pulls the image's manifest and layers from Docker Hub; the daemon creates a container with a writable layer over the read-only layers, sets up namespaces, a cgroup, a network interface on the default bridge and the filesystem mounts; containerd and runc start the image's ENTRYPOINT/CMD as PID 1 in those namespaces; output streams back to the terminal, since no `-d` was used.
_What the interviewer is probing for:_ Ability to communicate at two levels and a correct end-to-end mental model of pull, create and start.

**🎯 Intermediate:** _"Your image is 1.4 GB. How would you investigate and reduce it, and what would you refuse to compromise on?"_
**Model answer:** Inspect with `docker history` and `dive` to find large layers, then apply multi-stage builds, a slimmer base, `--no-install-recommends` and cleanup in the same `RUN`, a strict `.dockerignore`, and removal of build tools and caches; use BuildKit cache mounts so caches stay out of layers. I would not compromise on reproducibility (pinned versions), a non-root user, or debuggability that operations genuinely need, for example keeping a debug variant or using ephemeral debug containers rather than shipping a shell in production. Measure pull time and startup, not size alone.
_What the interviewer is probing for:_ Method-driven optimization and awareness of trade-offs with security and operability.

**🎯 Senior:** _"A production container is OOM-killed every few hours but `docker stats` shows memory well under the limit just before it dies. What are your hypotheses?"_
**Model answer:** Short spikes between sampling intervals; the limit counting page cache and kernel memory, not only heap; `tmpfs` mounts and `/dev/shm` writes counting against the cgroup; a child process or JVM off-heap or native memory outside application metrics; a limit on the pod or a parent cgroup rather than the container; or host-level OOM from other tenants. I would confirm with `docker inspect` (`OOMKilled`), `dmesg` or `journalctl -k` for the OOM report which lists the cgroup and RSS breakdown, cgroup v2 `memory.events` and `memory.stat` for the container, and higher-resolution metrics from cAdvisor. Fix by right-sizing, capping JVM or runtime memory to the limit, moving temp files to disk, and adding alerts on working set rather than usage.
_What the interviewer is probing for:_ Cgroup-level reasoning and a systematic approach rather than just "raise the limit".

**🎯 Architect:** _"Design the container build-and-run standards for an organization starting to containerize 100 services."_
**Model answer:** Provide a small set of curated, patched base images rebuilt on a schedule; a Dockerfile template with multi-stage builds, non-root users, exec-form entrypoints, health checks and pinned digests; a shared CI pipeline that builds with BuildKit and cache, scans, generates SBOMs, signs images and pushes to a private registry with retention policies; admission or runtime policy enforcing non-root, no privileged mode and resource limits; centralized logging to stdout collectors and standard metrics; and a clear runtime platform (managed Kubernetes for most, documented exceptions). Add paved-road docs, a champion network, linting in pull requests (hadolint, policy checks), and metrics for build time, vulnerability age and adoption, so standards evolve with evidence.
_What the interviewer is probing for:_ Systems thinking across build, supply chain, runtime and governance, with enablement rather than only enforcement.

## 12. Common Misconceptions

- "Containers are secure sandboxes." They share the host kernel; hardening is required.
- "`docker stop` is instant." It waits for graceful shutdown (default 10 s).
- "Deleting a file in a later layer removes it from the image." The data stays in the earlier layer.
- "Volumes are deleted with `docker rm`." Only anonymous volumes with `-v`; named volumes persist.
- "`latest` means newest." It is just a default tag.
- "Alpine is always better because it is smaller." musl compatibility and debugging cost can outweigh size.

## 13. 🔑 Key Takeaways

- Structure answers: definition, mechanism, example, trade-off.
- Know the internals: namespaces, cgroups, layers, runc, PID 1, signals.
- Remember the classic traps: shell-form CMD, secrets in layers, default bridge DNS, `EXPOSE` versus `-p`, `depends_on` readiness.
- Have a debug order ready: state, logs, resources, network, host.
- Pair security and cost trade-offs with every recommendation.
- Practise aloud; verify uncertain details with `--help` and docs.

## 14. Related Concepts & What's Next

Related: DCA domain map ([§100](Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)), Dockerfile checklist ([§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)), anti-patterns ([§95](../Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)), production troubleshooting ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)). Next, [§102](Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md) moves from short questions to scenario-based troubleshooting.

**Next Section:** [§102](Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md) — `Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md`
