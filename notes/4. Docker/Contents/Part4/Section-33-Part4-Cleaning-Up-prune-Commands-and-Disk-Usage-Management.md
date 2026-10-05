# Section 33 (Part 4): Cleaning Up: prune Commands and Disk Usage Management

## 1. Definition

**Plain language:** Docker leaves things behind: stopped containers, old image versions, unused networks, orphaned volumes and build cache. `docker system df` shows how much space each category uses, and the `prune` commands delete the unused parts in bulk.

**Precise definition:** Docker Engine tracks five storage categories: images, containers (writable layers), local volumes, networks (no disk cost, but clutter) and build cache. `docker system df [-v]` reports TOTAL, ACTIVE, SIZE and RECLAIMABLE for images, containers, volumes and build cache. Each object type has a prune command: `docker container prune`, `docker image prune`, `docker volume prune`, `docker network prune`, `docker builder prune`, plus the umbrella `docker system prune`. "Unused" has a different meaning per type: a stopped container; a **dangling** image (an untagged `<none>:<none>` layer chain) or, with `-a`, any image no container references; a volume no container references; a network with no attached containers; build cache not in use by a running build. All prunes accept `-f/--force` to skip the confirmation prompt and `--filter` (notably `until=<duration or timestamp>` and `label=` / `label!=`) to narrow the scope.

> ⚠️ **Warning:** Prune commands delete data and volume deletion is irreversible. Everything in this section that deletes should be run only in a throwaway environment (a disposable VM, or the sandbox daemon in section 5.1) until you know exactly what each command selects. Never rehearse on a machine whose images, volumes or databases you care about.

> 💡 **Tip:** Always run `docker system df` and the matching `docker <object> ls` (or `ls --filter`) first. The listing shows what a prune would take.

## 2. Why This Matters

- Disks fill silently: every build leaves layers and cache, every `docker run` without `--rm` leaves a container, and a full `/var/lib/docker` makes the daemon fail with `no space left on device`, taking all containers on the host with it.
- CI runners and developer laptops are the worst offenders; scheduled cleanup is standard operations hygiene.
- Over-eager cleanup is equally dangerous: `docker system prune -a --volumes` on the wrong host deletes images you cannot rebuild offline and, before Engine 23, deleted every unused volume including database data.
- Knowing what "unused" means for each type is a common interview and DCA question.
- Cloud and Docker Desktop disk costs are real: Desktop's virtual disk grows and does not shrink on its own after pruning.

## 3. Prerequisites and Dependencies

Requires an understanding of how images are layered and referenced ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), how overlay2 stores layers and writable container layers under `/var/lib/docker` ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), and the daemon's data-root setting ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Dangling images arise from retagging and rebuilds ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)); the build cache is a BuildKit concept. Inspecting what is large uses `docker history` and `docker inspect` ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)). Container states and restart-heavy hosts are covered in [§32](Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md); limits that prevent runaway growth are in [§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md). Volumes and networks get full treatment in Parts 6 and 7.

## 4. Architecture / Conceptual Diagram

```text
   /var/lib/docker  (the daemon's data-root)
   ┌───────────────────────────────────────────────────────────────┐
   │ overlay2/      image layers + container writable layers      │
   │ image/         image metadata (tags, digests)                 │
   │ containers/    per-container config and json-file logs        │
   │ volumes/       named + anonymous volumes                      │
   │ buildkit/      build cache                                    │
   └───────────────────────────────────────────────────────────────┘

   What each command removes (unused only; in-use objects are always kept)

   docker container prune ──► stopped containers
   docker image prune     ──► dangling images           (-a: all unreferenced images)
   docker volume prune    ──► anonymous unused volumes  (--all/-a: named unused too)
   docker network prune   ──► networks with no containers (never default bridge/host/none)
   docker builder prune   ──► build cache               (-a: all, not just dangling)

   docker system prune    ──► containers + networks + dangling images + build cache
        + -a              ──► + all unreferenced images
        + --volumes       ──► + anonymous unused volumes (add -a to include named ones)

   Reference chain: running container ──► image ──► layers ──► (protected from prune)
                    container using a volume ──► volume (protected)
```

- Prune only removes objects with **no reference**; a running container protects its image, its volumes and its networks.
- A stopped container still references its image, so `image prune -a` will not remove it until `container prune` removes the container.
- `system df` RECLAIMABLE is an estimate of what an `-a` prune of that category could free.
- Container log files (`containers/<id>/*-json.log`) are not in `system df`, yet can be large.

## 5. Hands-On

### 5.1 Build a Disposable Sandbox First

Run every destructive example below inside a throwaway Docker daemon, never against your real one. A Docker-in-Docker sandbox has its own images, volumes and networks, so pruning inside it cannot touch the host daemon's data:

```bash
docker run -d --privileged --name sandbox -e DOCKER_TLS_CERTDIR= docker:27-dind
docker exec sandbox docker version --format '{{.Server.Version}}'
alias sbx='docker exec sandbox docker'
```

```text
27.x.y
```

`--privileged` is required for dind and is itself a risk; use it only for this lab. A disposable VM works equally well. When finished: `docker rm -f -v sandbox` removes the sandbox and all its contents. Every `sbx ...` command below runs against the sandbox only.

### 5.2 Measure First: docker system df

```bash
sbx pull alpine:3.19 ; sbx pull alpine:3.20
sbx run --name stopped1 alpine:3.19 echo hi
sbx run -d --name running1 alpine:3.20 sleep 3600
sbx volume create keepme
sbx run --rm -v /anon alpine:3.20 true
sbx system df
sbx system df -v
```

```text
TYPE            TOTAL   ACTIVE   SIZE      RECLAIMABLE
Images          2       1        15.6MB    7.8MB (50%)
Containers      2       1        0B        0B
Local Volumes   2       0        0B        0B
Build Cache     0       0        0B        0B
```

`-v` adds a per-image, per-container and per-volume breakdown with the link count (how many containers use each).

### 5.3 container prune

```bash
sbx ps -a --filter status=exited
sbx container prune -f
sbx container prune -f --filter "until=24h"
```

```text
CONTAINER ID   IMAGE         STATUS
a1b2c3d4e5f6   alpine:3.19   Exited (0) 1 minute ago
Deleted Containers:
a1b2c3d4e5f6...
Total reclaimed space: 0B
```

`until=24h` removes only containers created more than 24 hours ago. The running container is untouched.

### 5.4 image prune: dangling versus -a

```bash
printf 'FROM alpine:3.20\nRUN echo v1 > /v\n' | sbx build -t app:latest -
printf 'FROM alpine:3.20\nRUN echo v2 > /v\n' | sbx build -t app:latest -
sbx images -f dangling=true
sbx image prune -f
sbx image prune -a -f --filter "until=720h"
```

```text
REPOSITORY   TAG      IMAGE ID
<none>       <none>   9f8e7d6c5b4a
Deleted Images:
deleted: sha256:9f8e7d6c5b4a...
Total reclaimed space: 4.1kB
```

Rebuilding `app:latest` moved the tag, leaving the v1 image dangling. Plain `image prune` removes dangling images only; `-a` also removes tagged images not referenced by any container (here, the unused `alpine:3.19`). **Warning:** `-a` on a real host deletes every cached image not currently used, forcing re-pulls.

### 5.5 volume prune and the Engine 23 Behavior Change

```bash
sbx volume ls
sbx volume prune -f
sbx volume ls
sbx volume prune -f --all
```

```text
DRIVER    VOLUME NAME
local     keepme
local     3c1f...a9
Total reclaimed space: 0B
DRIVER    VOLUME NAME
local     keepme
Deleted Volumes:
keepme
```

Since Docker Engine 23.0, plain `docker volume prune` removes only **anonymous** unused volumes; the named volume `keepme` survived. Before 23.0 it removed all unused volumes, named included. To delete unused named volumes you must pass `--all` (`-a`). Use `--filter "label=env=ci"` to prune only labelled volumes. Anything holding data you cannot recreate must never be pruned on a real host.

### 5.6 network prune and builder prune

```bash
sbx network create demo-net
sbx network prune -f
sbx builder prune -f --filter "until=168h"
sbx builder prune -a -f --keep-storage 2GB
```

```text
Deleted Networks:
demo-net
Total:  0B
```

The default networks (`bridge`, `host`, `none`) are never pruned. `builder prune` removes dangling build cache; `-a` removes all unused cache; `--keep-storage` keeps a given amount of the most useful cache, which is the right knob for CI.

### 5.7 system prune: The Umbrella Command

```bash
sbx system prune
sbx system prune -a -f
sbx system prune -a --volumes -f
sbx system df
```

```text
WARNING! This will remove:
  - all stopped containers
  - all networks not used by at least one container
  - all dangling images
  - unused build cache

Are you sure you want to continue? [y/N]
```

The prompt lists exactly what will be removed; read it. `-a` adds all unreferenced images, and `--volumes` adds unused anonymous volumes (add `--all` as well to include named ones). Prefer targeted commands over `system prune -a --volumes -f` outside a sandbox.

### 5.8 Targeted Cleanup With Labels

```bash
sbx run -d --label purpose=ci --name ci-job alpine:3.20 sleep 1
sleep 3
sbx container prune -f --filter "label=purpose=ci"
sbx container prune -f --filter "label!=keep=true"
```

Labels let teams prune only what they created, which is the safest strategy on shared hosts. Label at creation time (`--label`, Dockerfile `LABEL`, Compose `labels:`).

### 5.9 Remove Single Objects and Clean Up the Sandbox

```bash
sbx rm -f running1
sbx rmi alpine:3.19
docker rm -f -v sandbox
```

`docker rm`, `docker rmi`, `docker volume rm` and `docker network rm` remove named objects; prune is for "everything unused". The final command deletes the whole sandbox and its volumes.

### 5.10 Finding Space the Prunes Cannot Reach

```bash
sudo du -sh /var/lib/docker/containers/*/*-json.log | sort -h | tail
docker ps -a --size
```

`system df` ignores container log files; large `-json.log` files come from the default json-file driver without rotation. Fix with `--log-opt max-size=10m --log-opt max-file=3` or in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). On Docker Desktop the virtual disk file does not shrink automatically after pruning; use the Desktop "Clean / Purge data" and disk-compaction options (or `Optimize-VHD` for WSL 2 backends).

## 6. Production Usage Notes

- **Schedule it:** run a cron or systemd timer such as `docker system prune -f --filter "until=168h"` and `docker builder prune -f --keep-storage 20GB` on build hosts; leave volumes out of automated jobs.
- **Disk alerts first:** alert on the `/var/lib/docker` filesystem at 70-80 percent so cleanup is planned, not an emergency.
- **CI runners:** ephemeral runners are the cleanest answer; for persistent runners prune builder cache by age and size, and prune images by `until=`.
- **Registries versus hosts:** prune the host, but remove old tags from the registry with its own garbage collection or lifecycle policies.
- **Never prune volumes unattended** on stateful hosts; manage them explicitly and back them up first.
- **Leave rollback room:** keep at least the previous image tags so rollbacks do not require a pull during an incident.
- **Immutable infrastructure:** on orchestrated nodes (Swarm, Kubernetes), the orchestrator or kubelet garbage collects images and containers; do not fight it with host cron jobs.
- **Use `--filter until=`** (duration like `24h` or timestamp) to protect fresh objects from a cleanup that races with active deploys or builds.
- **Dangling build churn:** reuse tags deliberately and use BuildKit cache mounts to limit waste at the source.

## 7. Security Considerations

- **Data destruction is the primary risk.** Restrict who can run Docker commands; access to the daemon is root-equivalent and includes the ability to prune anything.
- **Dry-run culture:** list with `docker ... ls --filter` and read the prompt before `-f`. Never paste `-a --volumes -f` into production unreviewed.
- **Old images retain vulnerabilities:** pruning stale images shrinks the attack surface and reduces scanner noise, so cleanup is also a hygiene control.
- **Leftover volumes and caches can contain secrets** (database files, build cache from `--mount=type=secret` misuse, credentials in layers). Removing them reduces exposure, but deletion is not secure erasure of the underlying disk.
- **Automated jobs run as privileged:** a prune script with socket access is a high-value target; run it from a locked-down account, log what it deletes, and avoid exposing the socket over the network.
- **Unattended pruning of the wrong host** (a shared or production daemon selected via `DOCKER_HOST` or context) is a common accident. Check `docker context show` and `docker info` before destructive commands.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `no space left on device` during pull/build | `/var/lib/docker` full | `docker system df`, then targeted prunes; extend disk |
| Prune freed little space | Images still referenced by stopped containers | `container prune` first, then `image prune -a` |
| `docker system prune` did not remove my named volume | Engine 23+ keeps named volumes by default | `docker volume prune --all` (only if you are sure) |
| Unexpectedly lost data after prune on old Engine | Pre-23 volume prune removed named unused volumes | Upgrade, label volumes, back up before cleaning |
| `unable to delete ... image is being used by stopped container` | `rmi` blocked by a container | Remove the container, then the image |
| `conflict: unable to delete ... (must be forced)` | Image has multiple tags | Remove each tag or use `-f` knowingly |
| `system df` totals small but disk full | Container logs, or other data-root content | Check `*-json.log` sizes; configure rotation |
| Disk not freed on Docker Desktop host | Virtual disk does not auto-shrink | Use Desktop's compaction/purge, or compact the VHDX |
| Build cache keeps coming back | Normal BuildKit behavior | `builder prune --keep-storage` on a schedule |
| `network prune` leaves a network | A container (even stopped) is attached | Remove the container first |
| Prune removed something just built | No `until` filter and a concurrent job | Use `--filter until=` and separate runners |

## 9. Best Practices

- Run `docker system df -v` before any cleanup and prune by category, not by reflex.
- Prefer targeted prunes (`container`, `image`, `builder`) over `system prune -a --volumes`.
- Use `--filter until=` and labels to bound blast radius.
- Never include volume pruning in unattended jobs on hosts with data.
- Use `--rm` for throwaway containers so they never accumulate.
- Configure log rotation (`max-size`, `max-file`) on every host.
- Monitor disk usage on the data-root filesystem and alert early.
- Check `docker context show` before running destructive commands.
- Test new cleanup scripts in a disposable daemon, then document them in the runbook.

## 10. Common Anti-Patterns / Mistakes

- Running `docker system prune -a --volumes -f` on a shared or production host out of habit.
- Assuming `volume prune` is safe because named volumes are "protected" on a pre-23 Engine, or assuming the opposite on 23+.
- Relying on prune to reclaim space held by container logs or by a Desktop virtual disk.
- Deleting images with `rmi -f` that rollbacks need.
- Pruning on a schedule with no `until` filter, racing against active builds and deploys.
- Never pruning at all, then discovering a full disk during an incident.
- Using host cron prune on Kubernetes nodes that already have kubelet image garbage collection.
- Tagging everything `latest`, which constantly creates dangling images.

## 11. Interview Questions

**🎯 Beginner:** _"What does `docker system prune` remove, and what does it not remove by default?"_
**Model answer:** By default it removes stopped containers, networks not used by any container, dangling images (untagged layers) and unused build cache, after showing a confirmation prompt that lists them. It does not remove tagged images that are not dangling, and it does not remove volumes. Adding `-a` also removes all images not used by a container, and adding `--volumes` includes volumes; since Engine 23 that means anonymous unused volumes unless `--all` is also given. Running containers and the objects they use are never removed. Before pruning I would look at `docker system df` to see what is reclaimable.
_What the interviewer is probing for:_ Precise defaults and the dangling versus unused distinction.

**🎯 Intermediate:** _"A host reports `no space left on device`. Walk through diagnosing and reclaiming space safely."_
**Model answer:** First confirm which filesystem is full (`df -h`), usually the one holding `/var/lib/docker`. Run `docker system df -v` to see images, containers, volumes and build cache, and `docker ps -a --size`. Then reclaim in order of safety: `docker container prune`, `docker builder prune --filter until=...`, `docker image prune` for dangling images, then `image prune -a --filter until=...` once I know rollbacks are covered. I avoid volume pruning until I have listed the volumes and confirmed none hold data. If `system df` totals do not explain the usage, I check container `*-json.log` sizes and set log rotation. Afterwards I add disk alerts and a scheduled targeted cleanup.
_What the interviewer is probing for:_ A safe, evidence-driven method and awareness of logs outside `system df`.

**🎯 Senior:** _"What changed for `docker volume prune` in Engine 23, and how does it affect your cleanup tooling?"_
**Model answer:** Before 23.0, `volume prune` deleted every unused volume, named included, which destroyed data for people who had stopped a database container temporarily. From 23.0 it removes only anonymous unused volumes by default, and you need `--all` to include named volumes. Tooling written for older behavior may now leave named volumes behind (a space leak) or, if someone adds `--all` to compensate, become destructive. I would audit scripts and CI runners across Engine versions, label volumes (`env`, `owner`, `keep`) and filter with `label=` or `label!=`, separate disposable volumes from stateful ones, take backups before any removal, and keep volume pruning out of unattended jobs on stateful hosts.
_What the interviewer is probing for:_ Version-specific knowledge and risk-aware script design.

**🎯 Architect:** _"Design the disk and cleanup strategy for 200 CI runners and 50 stateful container hosts."_
**Model answer:** Make CI runners ephemeral (autoscaled, recycled after N jobs) so cleanup is deletion of the VM; where runners persist, run scheduled `builder prune --keep-storage <budget>` and `image prune -a --filter until=<age>` outside job windows, excluding volumes, with remote cache (registry or S3 backed BuildKit cache) replacing local cache to cut waste. For stateful hosts, no automated volume pruning: label and inventory volumes, back them up, and clean only containers, dangling images and old builder cache with `until` filters. Put the data-root on its own filesystem with alerts at 70 percent, enforce log rotation in `daemon.json`, and track `system df` metrics centrally. Orchestrated nodes rely on kubelet or Swarm garbage collection rather than host cron. Rehearse all scripts in a disposable dind or VM sandbox, log every deletion, and document rollback image retention and registry lifecycle policies.
_What the interviewer is probing for:_ Fleet-scale trade-offs between ephemerality, caching, safety of state and governance.

## 12. Common Misconceptions

- "`docker system prune` cleans everything." It skips non-dangling images, and volumes unless asked.
- "`docker image prune` removes all unused images." Only dangling ones; `-a` is needed for unreferenced tagged images.
- "`volume prune` always deletes named volumes." Not since Engine 23.0; use `--all`.
- "Pruning reclaims all disk usage." Container logs and Docker Desktop's virtual disk are outside its reach.
- "Prune can delete a running container's image or volume." In-use objects are protected.
- "Stopped containers cost nothing." They keep image layers pinned and hold a writable layer.
- "`until=` takes only dates." It accepts durations like `24h` and timestamps.

## 13. 🔑 Key Takeaways

- `docker system df [-v]` first; then prune by category.
- Defaults: containers (stopped), images (dangling), networks (unused), build cache (dangling), volumes (anonymous unused since 23).
- `-a` widens images/cache; `--all` widens volumes; `--volumes` adds volumes to `system prune`.
- Bound the blast radius with `--filter until=...` and `label=` / `label!=`.
- In-use objects are protected, but stopped containers still pin images.
- Logs and Desktop virtual disks need separate handling.
- Rehearse destructive commands only in a disposable sandbox, and never automate volume pruning on stateful hosts.

## 14. Related Concepts & What's Next

Related: image anatomy and references ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), overlay2 storage layout ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), daemon data-root and log options ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), tagging and builds ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), restart-heavy hosts ([§32](Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)), resource limits ([§31](Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)). This closes Part 4 on the container lifecycle and CLI. Part 5 turns to defining multi-container applications declaratively with Docker Compose.

**Next Section:** [§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md) — `Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md`
