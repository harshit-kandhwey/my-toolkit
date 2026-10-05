# Section 100 (Part 14): Docker Certified Associate (DCA) Domain Breakdown

## 1. Definition

**Plain language:** The Docker Certified Associate (DCA) is a vendor certification, now administered by Mirantis, that tests whether you can build, run, secure, network, store and orchestrate Docker containers. This section maps each exam domain to the sections of this knowledge base, lists the commands and facts that the exam rewards, and gives a study plan.

**Precise definition:** The exam is organized into six weighted domains. Published figures at the time of writing: **Orchestration 25%**, **Image Creation, Management and Registry 20%**, **Installation and Configuration 15%**, **Networking 15%**, **Security 15%**, **Storage and Volumes 10%**. The exam is a proctored, timed test (roughly 55 questions in 90 minutes) mixing multiple-choice, multiple-answer and discrete-option multiple-choice (DOMC) items. Weights, counts and the exact blueprint change; confirm them on the current Mirantis exam page before you book. The exam expects practical command knowledge, not only theory.

> 💡 **Tip:** Orchestration is the largest domain, and it means **Swarm** (plus basic Kubernetes concepts in the blueprint). Candidates who skip Swarm because "Kubernetes won" lose a quarter of the marks.

## 2. Why This Matters

- A structured checklist beats unfocused reading: each domain below lists what is testable and where to learn it.
- The same material doubles as interview preparation ([§101](Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md)); the exam's distinguishing feature is precision about flags, defaults and edge cases.
- The exam penalizes plausible-but-wrong answers. Knowing defaults (ports, timeouts, quorum rules) is what separates a pass from a fail.
- Even if you never sit the exam, the domain map is a good audit of gaps in operational Docker knowledge.

## 3. Prerequisites and Dependencies

The landscape overview is in [§7](../Part1/Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md). Practical prerequisites are everything in Parts 1 to 12; this section is the revision index. Lab access matters: a three-node Swarm (three VMs or three `docker:dind` containers) and a private registry are the minimum environment to practice on.

## 4. Architecture / Conceptual Diagram

```text
   DCA blueprint (weights approximate)                         Where to study
  ┌────────────────────────────────────────────┐
  │ Orchestration                       25%    │ ◄── Swarm: §90, §99, §46, §64, §91; Compose §34-§40
  ├────────────────────────────────────────────┤
  │ Image Creation, Mgmt, Registry      20%    │ ◄── §16-§25, §66-§72, §73-§79
  ├────────────────────────────────────────────┤
  │ Installation and Configuration      15%    │ ◄── §4, §8, §15, §29, §31, §33
  ├────────────────────────────────────────────┤
  │ Networking                          15%    │ ◄── §42-§49
  ├────────────────────────────────────────────┤
  │ Security                            15%    │ ◄── §57-§65, §67, §69
  ├────────────────────────────────────────────┤
  │ Storage and Volumes                 10%    │ ◄── §13, §50-§56
  └────────────────────────────────────────────┘

  Study loop:   read ──► lab (commands from memory) ──► timed practice questions
                  ▲                                              │
                  └────────────── review wrong answers ◄─────────┘
```

- Study by domain weight, but do not skip the 10% domain: storage questions are usually easy marks.
- The exam draws on the CLI; practice without shell history or autocomplete.

## 5. Hands-On

This section's hands-on is a domain-by-domain checklist of facts and commands. Treat each block as a flash-card deck and rehearse it in a lab.

### 5.1 Orchestration (25%)

Study: [§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md), [§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md), [§46](../Part6/Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md), [§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md).

```bash
docker swarm init --advertise-addr <ip>
docker swarm join-token manager|worker [--rotate]
docker node promote|demote|update --availability drain <node>
docker node update --label-add zone=a <node>
docker service create --name web --replicas 3 --publish 8080:80 \
  --constraint 'node.role==worker' --reserve-memory 64m --limit-memory 128m nginx
docker service scale web=5
docker service update --image nginx:1.27.1 --update-parallelism 1 --update-delay 10s \
  --update-failure-action rollback web
docker service rollback web
docker service create --mode global ...
docker stack deploy -c stack.yml app
docker secret create db_pw ./pw.txt ; docker config create nginx_conf ./nginx.conf
docker swarm update --autolock=true ; docker swarm unlock
```

Facts to memorize:
- Ports: **2377/tcp** cluster management, **7946/tcp+udp** node gossip, **4789/udp** overlay VXLAN.
- Raft quorum is a majority: 3 managers tolerate 1 failure, 5 tolerate 2, 7 tolerate 3 (Docker recommends at most 7). Even counts add no tolerance.
- Replicated vs global mode; `drain` evicts tasks but keeps the node in the cluster.
- Ingress routing mesh publishes a port on every node; `--publish mode=host` bypasses it.
- Secrets are mounted at `/run/secrets/<name>` (tmpfs); configs at a path you choose.
- Rolling update defaults: parallelism 1, no delay; `start-first` vs `stop-first` order.
- Recover from lost quorum with `docker swarm init --force-new-cluster` on a surviving manager.
- Placement: constraints (hard), preferences (spread), `--placement-pref 'spread=node.labels.zone'`.
- Kubernetes basics may appear: Pod, Deployment, Service types (ClusterIP, NodePort, LoadBalancer), ConfigMap, Secret, PV/PVC, `kubectl` verbs.

### 5.2 Image Creation, Management and Registry (20%)

Study: [§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md) to [§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md), [§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md) to [§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md), [§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md).

```bash
docker build -t app:1.0 -f Dockerfile.prod --target runtime --build-arg VER=1 .
docker image history app:1.0 ; docker image inspect app:1.0
docker tag app:1.0 registry.example.com:5000/team/app:1.0
docker push|pull ; docker save -o app.tar app:1.0 ; docker load -i app.tar
docker export <ctr> > fs.tar ; docker import fs.tar app:flat
docker commit -m msg <ctr> app:snap
docker run -d -p 5000:5000 --name registry registry:2
docker search nginx --filter is-official=true
docker image prune -a --filter until=24h
```

Facts to memorize:
- `ADD` extracts local tarballs and fetches URLs; `COPY` does neither. `CMD` vs `ENTRYPOINT` interaction ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).
- Only `RUN`, `COPY`, `ADD` create filesystem layers; the others add metadata.
- `save/load` keeps layers and tags; `export/import` flattens a container filesystem and loses history, ENV and CMD.
- Registry basics: `registry:2` is plain HTTP by default for non-localhost (needs TLS or `insecure-registries`); deleting images requires `REGISTRY_STORAGE_DELETE_ENABLED=true` and garbage collection ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- Content trust: `DOCKER_CONTENT_TRUST=1` ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Digest pinning: `image@sha256:...`.
- Cache invalidation order and `.dockerignore` ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md), [§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).

### 5.3 Installation and Configuration (15%)

Study: [§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md), [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md), [§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md).

```bash
sudo systemctl enable --now docker ; journalctl -u docker
sudo usermod -aG docker $USER        # docker group is root-equivalent
docker info ; docker system df ; docker system events
cat /etc/docker/daemon.json
```

```json
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "insecure-registries": ["registry.local:5000"],
  "live-restore": true,
  "userns-remap": "default",
  "data-root": "/var/lib/docker"
}
```

Facts to memorize:
- `daemon.json` lives at `/etc/docker/`; `SIGHUP` reloads some keys (live-restore, debug); others need a restart.
- Default socket `/var/run/docker.sock`; remote TLS API on 2376 (2375 is unencrypted).
- `live-restore` keeps containers running while `dockerd` restarts.
- Default log driver `json-file` has no rotation unless configured; `docker logs` works only with some drivers.
- Backup and restore of a Swarm manager: stop Docker, archive `/var/lib/docker/swarm`.

### 5.4 Networking (15%)

Study: [§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md) to [§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md).

```bash
docker network create -d bridge --subnet 172.30.0.0/24 appnet
docker network create -d overlay --attachable --opt encrypted ovl
docker run -d --network appnet --network-alias api --name api img
docker network connect|disconnect appnet <ctr>
docker network inspect appnet ; docker port <ctr>
docker run -p 127.0.0.1:8080:80 -P --dns 1.1.1.1 --add-host db:10.0.0.5 img
```

Facts to memorize:
- Drivers: bridge (default), host, none, overlay, macvlan, ipvlan.
- Automatic DNS name resolution works on **user-defined** bridges, not on the default `bridge`; the embedded DNS server is 127.0.0.11.
- `-p` publishes (iptables DNAT); `-P` publishes all `EXPOSE`d ports to random high ports; `EXPOSE` alone publishes nothing.
- `--network container:<name>` shares another container's network namespace.
- Overlay requires Swarm (or an external KV store historically) and the three ports above.
- `--internal` networks have no external route.

### 5.5 Security (15%)

Study: [§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md) to [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md), [§67](../Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md).

```bash
docker run --user 1000:1000 --cap-drop ALL --cap-add NET_BIND_SERVICE \
  --read-only --tmpfs /tmp --security-opt no-new-privileges \
  --security-opt seccomp=profile.json img
dockerd --tlsverify --tlscacert=ca.pem --tlscert=server-cert.pem --tlskey=server-key.pem -H tcp://0.0.0.0:2376
docker login registry.example.com ; cat ~/.docker/config.json
```

Facts to memorize:
- Namespaces isolate, cgroups limit, capabilities and seccomp restrict. `--privileged` disables most protections.
- Default seccomp profile blocks roughly 44 of 300+ syscalls; default AppArmor profile is `docker-default`.
- User namespace remapping (`userns-remap`) maps container root to an unprivileged host UID.
- Mutual TLS for the daemon; credentials in `config.json` are base64 unless a credential helper is configured.
- Swarm: mutual TLS between nodes, certificate rotation (default 90 days), autolock.
- Scanning (Scout, Trivy) and signing (Notation, Cosign, DCT) from [§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md).

### 5.6 Storage and Volumes (10%)

Study: [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§50](../Part7/Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md) to [§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md).

```bash
docker volume create data ; docker volume ls ; docker volume inspect data
docker run -v data:/var/lib/db img
docker run --mount type=bind,src=$PWD,dst=/app,readonly img
docker run --mount type=tmpfs,dst=/cache,tmpfs-size=64m img
docker volume prune ; docker system df -v
docker volume create --driver local --opt type=nfs --opt o=addr=10.0.0.9,rw --opt device=:/exports vol
```

Facts to memorize:
- Named volume vs bind mount vs tmpfs; `-v` creates missing host paths for bind mounts, `--mount` errors instead.
- A new empty named volume is populated from the image's content at the mount path; bind mounts hide image content.
- Volumes live under `/var/lib/docker/volumes/<name>/_data`; they persist after `docker rm` unless `-v` is used (anonymous volumes only).
- Storage drivers: overlay2 is the default and recommended; devicemapper and aufs are legacy.
- Copy-on-write: writes copy a file up to the container layer.
- Swarm volumes are node-local unless a cloud or NFS driver is used.

## 6. Production Usage Notes

- Map the exam to real tasks: draining a node before maintenance, rotating join tokens, recovering quorum, rotating registry credentials.
- The exam environment is multiple-choice; the skill that pays in production is the same flag-level precision.
- Re-verify details against the Docker Engine version in use: examples include BuildKit as default builder and Compose v2 replacing `docker-compose`.
- Keep a personal "defaults and ports" sheet; it is the highest-yield artifact for both exam and incident response.

## 7. Security Considerations

- Study only in disposable VMs or Docker-in-Docker labs so destructive commands (`prune`, `swarm leave --force`) cannot hurt real data. Avoid brain dumps: they violate exam agreements and are often wrong.
- Do not store registry credentials or Swarm join tokens in shared lab notes; tokens grant cluster membership.

## 8. Common Troubleshooting Scenarios

Exam-style fault finding. Know the diagnosis for each.

| Symptom | Likely cause | Command or fix |
|---|---|---|
| Service stuck at 0/3 replicas | Image not pullable from workers, or constraint unsatisfiable | `docker service ps --no-trunc svc` |
| Containers cannot resolve each other by name | Using default bridge | Create a user-defined network |
| `docker push` to private registry: "http response to https client" | Registry lacks TLS | Add TLS, or `insecure-registries` and restart |
| Data gone after `docker rm` | No volume, or anonymous volume removed | Use named volumes |
| Swarm commands fail "not a swarm manager" | Running on a worker | Run on a manager or promote the node |
| "Error response: No such image" after `docker load` | Loaded archive was an export, not a save | Use `import` for exports |
| Daemon will not start after editing `daemon.json` | Invalid JSON or key given both as flag and in file | `journalctl -u docker`, `dockerd --validate` |
| Port already allocated | Another container or host process uses it | `docker ps`, `ss -ltnp` |

## 9. Best Practices

- Spend about 40% of study time on hands-on labs with a real three-node Swarm.
- Build a one-page cheat sheet per domain and rewrite it from memory weekly.
- For every command, know what it does when it fails: the exam asks for the cause, not just the syntax.
- Read `--help` output for `docker service create`, `docker run` and `docker network create`; many questions are lifted from flag descriptions.
- On DOMC questions, evaluate each option independently as true or false for the scenario.
- Register only after you score consistently above the pass mark (historically about 65%, confirm current) on fresh practice questions.

## 10. Common Anti-Patterns / Mistakes

- Memorizing Kubernetes in depth while ignoring Swarm specifics.
- Confusing `docker save/load` with `docker export/import`.
- Assuming `EXPOSE` publishes ports.
- Believing the default bridge supports name resolution.
- Treating `docker stack deploy` as supporting `build:`.
- Forgetting that even manager counts do not add fault tolerance.
- Relying on outdated Enterprise (UCP/DTR) material.
- Studying only reading material and never typing the commands.

## 11. Interview Questions

**🎯 Beginner:** _"Which DCA domain carries the most weight, and what does it cover?"_
**Model answer:** Orchestration, about a quarter of the exam. It centres on Docker Swarm: initializing a cluster, joining nodes with tokens, manager and worker roles, services in replicated and global mode, scaling, rolling updates and rollbacks, stacks deployed from Compose files, secrets and configs, overlay networks, placement constraints, draining nodes and quorum rules. Basic Kubernetes concepts such as Pods, Deployments and Services also appear. I would back this with a lab of three nodes rather than just reading.
_What the interviewer is probing for:_ Awareness of the blueprint and that Swarm is examinable, not just Kubernetes.

**🎯 Intermediate:** _"An exam question says a Swarm has 5 managers and 3 fail. What happens, and how do you recover?"_
**Model answer:** Raft needs a majority: with 5 managers, 3 are required, so with 3 failed only 2 remain and quorum is lost. The cluster cannot accept management changes (no scaling, no updates), though existing tasks on workers keep running. Recovery: bring failed managers back if possible; otherwise on a surviving manager run `docker swarm init --force-new-cluster --advertise-addr <ip>`, which creates a one-node cluster from the existing state, then re-join or promote nodes to restore the manager count. Demoting is not possible without quorum, which is why the force flag exists.
_What the interviewer is probing for:_ Raft majority arithmetic and the difference between management plane and running workloads.

**🎯 Senior:** _"You must prepare a team of six for the DCA in six weeks with a limited lab budget. Outline the plan."_
**Model answer:** Weeks 1 and 2: Orchestration and Networking, with a three-node Swarm built from three VMs or `docker:dind` containers, because they are 40% of marks and need hands-on practice. Week 3: Images and Registry, including running `registry:2` with TLS and basic auth and doing push, pull, save, load, and garbage collection. Week 4: Installation, Security and Storage, covering `daemon.json`, userns-remap, capabilities, seccomp, secrets and volume drivers. Week 5: timed mixed practice sets, with error logs sorted by domain. Week 6: targeted remediation of weakest domains, one full mock under exam conditions, and a review of changes in the current blueprint. Pair people, rotate "break the cluster" exercises, and verify the official blueprint before booking.
_What the interviewer is probing for:_ Weight-based prioritisation, lab-first learning and a feedback loop.

**🎯 Architect:** _"Is the DCA worth requiring across a 200-person platform organisation? How would you use it?"_
**Model answer:** It validates a baseline of Docker Engine, image, network, storage and Swarm knowledge, which is useful as a shared vocabulary and for onboarding, but it is not evidence of Kubernetes or cloud-native production skill, and the industry has moved towards the CKA, CKAD and cloud-provider certifications. I would not require it organisation-wide. I would fund it for engineers who own base images, CI runners and developer tooling, and use its domain list as the skeleton of an internal competency matrix, backed by practical assessments such as hardening a Dockerfile or debugging a broken stack. Pair certification with internal labs and code reviews, because a pass proves recall, not judgement.
_What the interviewer is probing for:_ A pragmatic view of certification value and the ability to tie training to organisational outcomes.

## 12. Common Misconceptions

- "The DCA is mostly Kubernetes." It is mostly Docker Engine and Swarm.
- "It needs Docker Enterprise." Enterprise components have been retired from the blueprint; the exam targets Engine features.
- "Passing proves production readiness." It proves breadth of recall; operations skill is built in labs and incidents.
- "Weights are fixed forever." Mirantis revises the blueprint; always check the current one.
- "Exam commands are rarely tested." Many questions ask for the exact flag or resulting behavior.

## 13. 🔑 Key Takeaways

- Six domains: Orchestration 25, Image/Registry 20, Install/Config 15, Networking 15, Security 15, Storage 10 (verify current).
- Know ports 2377, 7946 and 4789, quorum arithmetic, and the secrets path `/run/secrets`.
- `save/load` preserves layers; `export/import` flattens.
- User-defined bridges provide DNS; the default bridge does not.
- `EXPOSE` documents, `-p` publishes.
- Practice commands hands-on in disposable labs, then timed question sets.

## 14. Related Concepts & What's Next

Related: certification landscape ([§7](../Part1/Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md)), Swarm ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)), Dockerfile practices ([§94](../Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)), orchestration path ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)). Next, [§101](Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md) collects interview questions from beginner to advanced.

**Next Section:** [§101](Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md) — `Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md`
