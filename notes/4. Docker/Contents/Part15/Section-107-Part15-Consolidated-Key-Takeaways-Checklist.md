# Section 107 (Part 15): Consolidated Key-Takeaways Checklist

## 1. Definition

**Plain language:** One page-per-topic review list that condenses the whole Docker knowledge base into checkable statements: "I can explain this", "I do this by default", "I verify this with that command". Tick a box only when you could defend it to a reviewer.

**Precise definition:** The checklist is organised in three tiers. **Understand** items test your mental model (what Docker is and how it works). **Do** items are defaults you apply when authoring and running containers. **Verify** items are commands that prove the default is in effect. Section 5 turns the *Verify* tier into an executable audit script that inspects a throwaway image and container, so the checklist can run in CI as well as in your head.

> 💡 **Tip:** Use the list three ways: before an interview (Understand), before merging a Dockerfile or Compose change (Do), and before a release or handover (Verify).

## 2. Why This Matters

- Fourteen parts of material are too large to hold in working memory; a checklist is the compressed index into it.
- Most production incidents trace back to a small set of skipped basics: root user, no limits, mutable tags, no healthcheck, no backup test. A checklist makes skipping them visible.
- Reviews become consistent: reviewers cite an item, not a preference.
- It doubles as gap analysis: unticked boxes show exactly which sections to reread.

## 3. Prerequisites and Dependencies

This section assumes you have read or at least skimmed Parts 1-14 and attempted the labs ([§106](Section-106-Part15-Progressive-Hands-On-Labs-Beginner-Production-Style.md)). Each group below links to the sections that justify it. The audit script in section 5 needs Docker Engine 27/28 with BuildKit and a POSIX shell; it uses only a temporary build directory and resources named `kb-audit-*`, and it removes them at the end. Deeper rationale for Dockerfile items is in [§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md); recurring errors are collected in [§95](../Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md) and recapped in [§108](Section-108-Part15-Common-Misconceptions-and-Anti-Patterns-Recap.md).

## 4. Architecture / Conceptual Diagram

```text
  Lifecycle of a containerised service and where each checklist group applies

  Author            Build               Ship               Run                Operate
 ┌────────┐      ┌──────────┐       ┌───────────┐      ┌───────────┐      ┌────────────┐
 │ Group B│─────►│ Group C  │──────►│ Group D   │─────►│ Group E   │─────►│ Group F    │
 │Dockerf.│      │ caching, │       │ registry, │      │ run flags,│      │ logs, health│
 │ basics │      │ multi-   │       │ tags,     │      │ limits,   │      │ backup,     │
 │        │      │ stage    │       │ signing   │      │ hardening │      │ rollback    │
 └────────┘      └──────────┘       └───────────┘      └───────────┘      └────────────┘
      ▲                                                                         │
      │                 Group A: mental model (engine, namespaces, cgroups,     │
      └──────────────── layers, networks, volumes)  ◄────────────────────────────┘
                        Group G: CI/CD and interview readiness wrap the whole loop

  Tiering:   Understand (explain)  ►  Do (default)  ►  Verify (command proves it)
```

- Groups A-G below follow this flow; each ends with its *Verify* commands.
- Tick boxes in a copy of this file (for example a PR template), not in the knowledge base itself.

## 5. Hands-On

### 5.1 Group A: Mental Model (Parts 1-2)

- [ ] A container is an isolated process using namespaces, limited by cgroups, with a layered filesystem; it is not a VM and shares the host kernel ([§1](../Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md), [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md)).
- [ ] I can draw the CLI ► REST ► dockerd ► containerd ► runc path ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)).
- [ ] I know that OCI image and runtime specs make images portable across engines ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)).
- [ ] I can name the six namespaces and the cgroup v2 controllers that matter (memory, cpu, pids, io) ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)).
- [ ] I can explain copy-on-write, whiteouts and why deleting in a later layer does not shrink an image ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)).
- [ ] I know who can talk to `dockerd` and why `docker` group membership is root-equivalent ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

### 5.2 Group B: Dockerfile Authoring (Part 3)

- [ ] Base image is pinned to a specific tag (ideally also a digest) and fits the job: slim, distroless or scratch where possible ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md), [§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- [ ] `CMD`/`ENTRYPOINT` use exec form; entrypoint scripts end with `exec "$@"` ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).
- [ ] `WORKDIR` set; `ENV`/`ARG` used correctly; no secrets in either ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).
- [ ] `USER` is a non-root numeric UID; `EXPOSE` documents ports; `VOLUME` is used deliberately ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)).
- [ ] `.dockerignore` excludes `.git`, local env files, build output and dependency folders ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).
- [ ] `COPY` is preferred over `ADD`; `RUN` steps combine install and cleanup in one layer ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)).
- [ ] I can inspect any image: `history`, `inspect`, `dive` ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)).

### 5.3 Group C: Build Quality (Parts 3, 10)

- [ ] Multi-stage build separates toolchain from runtime ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)).
- [ ] Layers ordered from least to most frequently changing; dependency manifests copied before source ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).
- [ ] BuildKit features used where they help: cache mounts, bind mounts for build context, heredocs ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)).
- [ ] Build-time secrets use `--mount=type=secret` or SSH forwarding, never `ARG`/`ENV`/`COPY` ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- [ ] Image size measured and justified; unused packages and docs removed ([§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)).
- [ ] Builds are reproducible: pinned versions, lockfiles, controlled build args ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)).
- [ ] Multi-platform images built with buildx where architectures differ ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md), [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)).

### 5.4 Group D: Registry and Supply Chain (Parts 8, 9)

- [ ] Images pushed with immutable version tags plus a moving convenience tag; deployments reference a version or digest, not `latest` ([§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)).
- [ ] Registry authentication uses credential helpers or CI-scoped tokens, not plaintext `config.json` passwords ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)).
- [ ] Retention and garbage collection policies are defined ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- [ ] Docker Hub rate limits handled with authenticated pulls or a mirror ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)).
- [ ] Every image is scanned in CI and on a schedule; findings have owners ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- [ ] SBOM generated, provenance recorded, images signed and signatures verified at deploy ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

### 5.5 Group E: Running Safely (Parts 4, 6, 7, 8)

- [ ] Containers run as non-root with `--cap-drop ALL` plus only needed `--cap-add` ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).
- [ ] `no-new-privileges`, default seccomp and an LSM profile (AppArmor/SELinux) stay enabled ([§60](../Part8/Section-60-Part8-Seccomp-Profiles.md), [§61](../Part8/Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)).
- [ ] Root filesystem read-only with explicit `tmpfs`/volume writable paths ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- [ ] No `--privileged`, no host namespaces, no docker.sock mounts without a written exception ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md), [§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- [ ] Memory, CPU and PID limits set ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)).
- [ ] Restart policy chosen deliberately; healthcheck defined ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)).
- [ ] Secrets delivered by secret mounts or a manager, not environment variables baked into images ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- [ ] Ports published only where needed and bound to a specific interface; internal tiers use `--internal` or unpublished networks ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md), [§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- [ ] User-defined networks provide DNS; I can explain bridge, host, none, overlay, macvlan ([§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md), [§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)).
- [ ] Persistent data lives in named volumes (or managed storage), not the container layer; I know when bind mounts and tmpfs apply ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md), [§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md), [§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)).

### 5.6 Group F: Operating (Parts 5, 12)

- [ ] Compose files use the Compose Specification, `depends_on` with `service_healthy`, profiles and override files ([§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), [§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md), [§38](../Part5/Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)).
- [ ] Logs go to stdout/stderr, the log driver has rotation (`max-size`, `max-file`) or ships off-host ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md), [§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)).
- [ ] Metrics collected (cAdvisor/Prometheus or equivalent) with alerts on restarts, OOM kills and saturation ([§87](../Part12/Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md), [§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)).
- [ ] Deployments are zero-downtime and have a tested rollback ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md), [§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)).
- [ ] Volume backups exist and a restore has been rehearsed this quarter ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)).
- [ ] Disk usage is monitored; `docker system df` reviewed; prune jobs are scoped with filters ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).
- [ ] I follow a fixed troubleshooting ladder: status, exit code, logs, inspect, exec, events ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)).

### 5.7 Group G: Pipelines and Judgement (Parts 11, 13, 14)

- [ ] CI builds with cache import/export, scans, tests with ephemeral containers, then pushes ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§83](../Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md), [§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)).
- [ ] Promotion between environments retags or pins digests via a reviewed change, not rebuilds ([§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)).
- [ ] I can state when Docker is the wrong tool and when to move to an orchestrator ([§97](../Part13/Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md), [§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).
- [ ] I can compare Docker, Podman and containerd honestly ([§96](../Part13/Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md)).
- [ ] I can answer the four-level interview ladder and do the live exercises ([§101](../Part14/Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md), [§105](../Part14/Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank.md)).

### 5.8 Executable Audit: Verify Tier as a Script

This script builds a deliberately small throwaway image, runs a container with the hardened profile, and checks the Verify-tier items. It touches only `kb-audit-*` resources and a temporary directory made with `mktemp -d`; the single removal at the end targets that temp directory by its variable and is guarded.

```bash
#!/usr/bin/env bash
set -u
T="$(mktemp -d)"; pass=0; fail=0
chk() { if eval "$2" >/dev/null 2>&1; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1"; fail=$((fail+1)); fi; }

cat > "$T/Dockerfile" <<'EOF'
FROM alpine:3.20
RUN adduser -S -u 10001 app
USER 10001
HEALTHCHECK --interval=2s --retries=2 CMD true
ENTRYPOINT ["sleep"]
CMD ["300"]
EOF
docker build -q -t kb-audit-img "$T" >/dev/null
docker run -d --name kb-audit-ctr --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 64m --pids-limit 100 \
  --restart on-failure:3 --log-opt max-size=1m --log-opt max-file=2 kb-audit-img >/dev/null

I='docker image inspect kb-audit-img --format'
C='docker inspect kb-audit-ctr --format'
chk "base tag pinned (not latest)"      "! $I '{{.Config.Image}}' | grep -q latest"
chk "non-root numeric USER"             "$I '{{.Config.User}}' | grep -Eq '^[0-9]+'"
chk "exec-form ENTRYPOINT"              "$I '{{json .Config.Entrypoint}}' | grep -q '\"sleep\"'"
chk "HEALTHCHECK defined"               "$I '{{json .Config.Healthcheck}}' | grep -q Test"
chk "read-only rootfs"                  "$C '{{.HostConfig.ReadonlyRootfs}}' | grep -q true"
chk "all caps dropped"                  "$C '{{json .HostConfig.CapDrop}}' | grep -q ALL"
chk "no-new-privileges"                 "$C '{{json .HostConfig.SecurityOpt}}' | grep -q no-new-privileges"
chk "memory limit set"                  "[ \"\$($C '{{.HostConfig.Memory}}')\" -gt 0 ]"
chk "pids limit set"                    "[ \"\$($C '{{.HostConfig.PidsLimit}}')\" -gt 0 ]"
chk "not privileged"                    "$C '{{.HostConfig.Privileged}}' | grep -q false"
chk "restart policy bounded"            "$C '{{.HostConfig.RestartPolicy.Name}}' | grep -q on-failure"
chk "log rotation configured"           "$C '{{json .HostConfig.LogConfig.Config}}' | grep -q max-size"
chk "no docker.sock mount"              "! $C '{{json .Mounts}}' | grep -q docker.sock"

docker rm -f kb-audit-ctr >/dev/null 2>&1
docker image rm kb-audit-img >/dev/null 2>&1
[ -n "$T" ] && [ -d "$T" ] && rm -r "$T"
echo "passed=$pass failed=$fail"
```

```text
PASS  base tag pinned (not latest)
PASS  non-root numeric USER
PASS  exec-form ENTRYPOINT
PASS  HEALTHCHECK defined
PASS  read-only rootfs
PASS  all caps dropped
PASS  no-new-privileges
PASS  memory limit set
PASS  pids limit set
PASS  not privileged
PASS  restart policy bounded
PASS  log rotation configured
PASS  no docker.sock mount
passed=13 failed=0
```

Note: the "pinned" check is a smoke test; lint the `FROM` line with hadolint in a real pipeline. Point the `chk` lines at your own names to audit real workloads (read-only, `inspect` only).

## 6. Production Usage Notes

- Embed the checklist in a PR template and a pipeline stage; automate the Verify tier (hadolint, an `inspect`-based script, Trivy).
- Record exceptions with an owner and an expiry date; review the list quarterly.
- Weight items by blast radius: user, capabilities, secrets and exposed ports first; image size last.

## 7. Security Considerations

- Security items are embedded in groups B, D and E on purpose, so they are reviewed with every change.
- The checklist reduces risk; it does not prove safety, because isolation is kernel-level ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- Audit scripts must be read-only (`inspect` only); scrub `Config.Env` before sharing output, since it often holds tokens.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| "memory limit set" fails | Limit not applied by Compose file | Use `mem_limit` or `deploy.resources.limits`, re-check `HostConfig.Memory` |
| Read-only container crashes | App writes to `/tmp` or caches | Add `--tmpfs` for those paths |
| User check fails with `appuser` | Name-based `USER` | Use a numeric UID |
| Script leaves `kb-audit-*` behind | Aborted mid-run | `docker rm -f kb-audit-ctr; docker image rm kb-audit-img` |

## 9. Best Practices

- Automate what can be automated; keep humans for judgement items.
- Fail the build on high-severity items (root, privileged, secrets in layers); warn on the rest.
- Keep every item testable and link each rule to its rationale.

## 10. Common Anti-Patterns / Mistakes

- Ticking boxes without running the verification command.
- Auditing only the Dockerfile and ignoring runtime flags and registry policy.
- Blanket "legacy" exceptions with no owner or end date.

## 11. Interview Questions

**🎯 Beginner:** _"Name five things you check before you say a Dockerfile is ready to merge."_
**Model answer:** Pinned base tag; non-root `USER`; exec-form `CMD`/`ENTRYPOINT`; a `.dockerignore`; dependencies installed before source is copied; no secrets in `ENV`/`ARG`; ideally multi-stage. I would also confirm `docker stop` is quick.
_What the interviewer is probing for:_ A working mental checklist.

**🎯 Intermediate:** _"How do you enforce those checks automatically?"_
**Model answer:** Lint with hadolint, build, scan with Trivy or Docker Scout and fail on fixable high/critical findings, run an `inspect`-based test for user, entrypoint form, healthcheck and labels, and apply policy as code (OPA/Conftest or admission policies) for limits, read-only root and dropped capabilities. Require all to pass before merge.
_What the interviewer is probing for:_ Automated, testable gates.

**🎯 Senior:** _"An audit found 40 images running as root. How do you remediate without an outage?"_
**Model answer:** Triage by exposure. Per image, add a numeric `USER`, fix ownership with `COPY --chown`, move writable paths to volumes or tmpfs, and use a high port or only `NET_BIND_SERVICE`. Test in staging with production's read-only and capability settings, roll out gradually behind health checks with rollback, rehearse any one-time volume ownership migration on a copy, and add a CI gate so the count cannot grow back.
_What the interviewer is probing for:_ Migration planning with risk control and regression prevention.

**🎯 Architect:** _"Define the organization's container baseline and how exceptions are governed."_
**Model answer:** Mandatory: non-root, no privileged mode or host namespaces, pinned and scanned images from approved registries, signed provenance, limits, no baked secrets, probes, stdout logs. Recommended: distroless/slim, read-only root, reproducible builds, SBOMs. Enforce in CI and at admission; exceptions need an owner, a compensating control and an expiry; track compliance rate and time to patch base images; review twice a year.
_What the interviewer is probing for:_ Tiered policy, automation, exception governance and measurement.

## 12. Common Misconceptions

- "A checklist guarantees secure containers." It guarantees a baseline of known controls.
- "Small image equals secure image." Small helps; patching, user and exposure matter more.
- "If CI passes the scan, we are done." New CVEs appear after the build; rescan on a schedule.
- "Non-root is optional on an internal network." Compromised internal services are the common pivot point.
- "Healthchecks make Docker restart a container." Only the restart policy (on exit) or an orchestrator acts.

## 13. 🔑 Key Takeaways

- Three tiers: Understand, Do, Verify; every Do item should have a command that proves it.
- The big five defaults: non-root user, pinned and scanned images, resource limits, health checks, no secrets in images.
- Build for cache and size with multi-stage builds; ship by immutable tag or digest; sign and verify.
- Operate with logs off the container, metrics and alerts, tested backups and a rehearsed rollback.
- Automate the audit, record exceptions, and revisit the baseline regularly.

## 14. Related Concepts & What's Next

Related: Dockerfile checklist ([§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)), anti-patterns ([§95](../Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)), performance recap ([§98](../Part13/Section-98-Part13-Performance-Tuning-Recap.md)), DCA domains ([§100](../Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)), labs ([§106](Section-106-Part15-Progressive-Hands-On-Labs-Beginner-Production-Style.md)). Next, the misconceptions and anti-patterns recap collects the traps behind the unticked boxes.

**Next Section:** [§108](Section-108-Part15-Common-Misconceptions-and-Anti-Patterns-Recap.md) — `Section-108-Part15-Common-Misconceptions-and-Anti-Patterns-Recap.md`
