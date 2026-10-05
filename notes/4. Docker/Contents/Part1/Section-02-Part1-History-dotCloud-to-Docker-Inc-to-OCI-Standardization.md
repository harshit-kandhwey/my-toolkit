# Section 2 (Part 1): History: dotCloud to Docker Inc. to OCI Standardization

## 1. Definition

**Plain language:** Docker did not invent containers. Isolation primitives had been accumulating in Unix and Linux for decades. What Docker did, starting in 2013, was package those primitives behind a simple workflow (build an image, push it, run it anywhere) that ordinary developers could adopt in an afternoon. The industry then standardized the image and runtime formats so no single company controls them.

**Precise definition:** The history of Docker is the story of three overlapping layers maturing in sequence: (1) **kernel isolation primitives** (chroot, jails, zones, Linux namespaces and cgroups), (2) **developer-facing tooling** (LXC, then dotCloud's internal platform, then Docker's CLI, image format, and Hub), and (3) **open standards and modular components** (the Open Container Initiative specifications, runc, containerd, and the Moby project) that decoupled the ecosystem from any single vendor. The resulting standards are dissected in [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md), and the component split in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md).

> 💡 **Tip:** When a Docker design decision looks odd (why is there a separate `containerd`? why is `runc` a standalone binary? why does Kubernetes talk to "CRI" instead of Docker?), the answer is almost always in this timeline.

## 2. Why This Matters

- **It explains the architecture.** The daemon-plus-containerd-plus-runc chain in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) is the direct result of a 2015-2017 decision to split a monolith into standards-based parts.
- **It explains vendor and licensing news** ([§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)): Docker Inc.'s pivots (Swarm, Enterprise sale, Desktop licensing) shaped which tools the industry actually uses.
- **It explains why "Docker" images run on Podman, Kubernetes, and cloud runtimes.** The OCI formats made images portable across tools.
- **It prevents vocabulary confusion.** Docker, Moby, containerd, runc, and OCI are separate things with separate owners; interviewers routinely probe the difference.
- **It shapes the Kubernetes story.** The removal of `dockershim` from Kubernetes ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)) only makes sense with the history of CRI and containerd in hand.

## 3. Prerequisites and Dependencies

Read [§1](Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md) first so that "container" already means "isolated process with a shared kernel". Familiarity with Linux basics is enough; the kernel features named in the timeline are treated properly in [§5](Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md), [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), and [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md). [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) continues from here with a comparison of Docker against Podman, LXC, rkt, and standalone containerd, and [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) gives the technical content of the OCI specifications that this section introduces only historically.

## 4. Architecture / Conceptual Diagram

```text
  Timeline of container technology (not to scale)

  1979  chroot (Unix V7) ────────────────────────────────────────┐
  2000  FreeBSD jails                                            │ isolation
  2001  Linux-VServer          2004  Solaris Zones               │ primitives
  2002  Linux mount namespace  2005  OpenVZ                      │
  2006-8 cgroups ("process containers", Google) merged in 2.6.24 │
  2008  LXC 0.1 (namespaces + cgroups, userland tooling) ────────┘
                 │
  2008  dotCloud founded (PaaS)
                 │  internal container tooling built on LXC
  2013-03  Docker unveiled (PyCon), open-sourced
  2013-10  dotCloud renamed Docker, Inc.
  2014-03  Docker 0.9: libcontainer replaces LXC as default driver
  2014-06  Docker 1.0 ; Kubernetes open-sourced (Google)
  2014-12  CoreOS announces rkt
                 │
  2015-06  Open Container Initiative formed (Linux Foundation)
           Docker donates runtime code ──► runc
  2016-06  Docker 1.12: Swarm mode built in
  2016-12  containerd extracted from Docker
  2017-03  containerd donated to CNCF ; versioning becomes YY.MM
  2017-04  Moby project announced (upstream of Docker)
  2017-07  OCI Runtime Spec 1.0 and Image Spec 1.0
  2019-02  containerd graduates in CNCF
  2019-11  Docker Enterprise sold to Mirantis
  2021-08  Docker Desktop licensing change (paid tiers for larger orgs)
  2022-05  Kubernetes 1.24 removes dockershim
```

```text
  Before OCI                             After OCI
  ┌──────────────────────┐              ┌─────────────────────────────┐
  │ Docker monolith      │              │ docker CLI                  │
  │ (CLI+daemon+runtime  │   split ──►  │   └► dockerd (Moby)         │
  │  +image format, all  │              │        └► containerd (CNCF) │
  │  one vendor)         │              │             └► runc (OCI)   │
  └──────────────────────┘              │ Image + runtime specs: OCI  │
                                        └─────────────────────────────┘
```

- **The top half is a slow build-up; the bottom is a fast consolidation.** Roughly 30 years of primitives were assembled into a product in 2013, and the standards fight was resolved within about four years.
- **The June 2015 OCI formation is the pivot.** It ended a real risk of fragmentation (Docker vs. CoreOS rkt's App Container spec) by merging efforts into one neutral spec.
- **Each donated component keeps its role today.** `runc` is the reference OCI runtime; `containerd` is a CNCF graduated project used by Docker and Kubernetes alike.

## 5. Hands-On

### 5.1 Trace the Lineage in a Running Docker Install

**Purpose:** Observe that a modern `docker run` still exercises the historical components: containerd, runc, and the OCI bundle.

**Syntax:**

```bash
docker info --format '{{json .}}' | jq '{ServerVersion, DefaultRuntime, Runtimes, ContainerdCommit, RuncCommit, InitCommit}'
```

**Example usage and expected output:**

```bash
$ docker info --format '{{json .}}' | jq '{ServerVersion, DefaultRuntime, Runtimes, ContainerdCommit, RuncCommit}'
{
  "ServerVersion": "27.3.1",
  "DefaultRuntime": "runc",
  "Runtimes": {
    "io.containerd.runc.v2": { "path": "runc" },
    "runc": { "path": "runc" }
  },
  "ContainerdCommit": { "ID": "7f7fdf5fed64eb6a7caf99b3e12efcf9d60e311c", "Expected": "7f7fdf5fed64eb6a7caf99b3e12efcf9d60e311c" },
  "RuncCommit": { "ID": "v1.1.14-0-g2c9f560", "Expected": "v1.1.14-0-g2c9f560" }
}
```

**Production usage example:** Auditing fleet nodes for runc/containerd versions is how teams respond to runtime CVEs (for example, the 2019 runc `CVE-2019-5736` container escape drove urgent fleet-wide patching).

**Common errors:** `jq: command not found`; use `docker info` without `--format` and read the `Runtimes`, `containerd version`, and `runc version` lines.

### 5.2 See the Pieces as Separate Binaries

**Purpose:** Confirm the post-2016 split is real: separate daemons and shims.

**Syntax:**

```bash
ps -eo pid,ppid,comm,args | grep -E 'dockerd|containerd|runc' | grep -v grep
```

**Example usage and expected output:**

```bash
$ ps -eo pid,ppid,comm,args | grep -E 'dockerd|containerd' | grep -v grep
  912     1 containerd      /usr/bin/containerd
 1187     1 dockerd         /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
20460     1 containerd-shim /usr/bin/containerd-shim-runc-v2 -namespace moby -id 8f3c1d2a9b7e...
```

`runc` does not appear as a long-running process: it starts the container and exits, leaving the shim as parent.

**Production usage example:** The `-namespace moby` argument shows containerd namespacing: Docker's containers live in the `moby` namespace, while Kubernetes uses `k8s.io`. That is why `ctr` on a Docker host shows nothing by default.

**Common errors:** Looking for `runc` in `ps` and concluding it is not used; it is short-lived by design.

### 5.3 Inspect an Image's OCI Identity

**Purpose:** Show that the Docker image format converged into the OCI format.

**Syntax:**

```bash
docker manifest inspect IMAGE
```

**Example usage and expected output:**

```bash
$ docker manifest inspect alpine:3.20 | head -12
{
   "schemaVersion": 2,
   "mediaType": "application/vnd.oci.image.index.v1+json",
   "manifests": [
      {
         "mediaType": "application/vnd.oci.image.manifest.v1+json",
         "size": 528,
         "digest": "sha256:1e42bbe2508154c9126d48c2b8a75420c3544343bf86fd041fb7527e017a4b4a",
         "platform": { "architecture": "amd64", "os": "linux" }
      }
```

Note the `application/vnd.oci...` media types, where older images use `application/vnd.docker.distribution.manifest.v2+json`.

**Production usage example:** Registries and tools such as Podman, Buildah, and Kubernetes consume the same manifest regardless of which tool built it.

**Common errors:** `docker manifest` may require the experimental CLI setting on very old clients; upgrade the client.

### 5.4 Compare the Pre-Docker Primitive Directly

**Purpose:** Reproduce the 1979 idea (chroot) to see how little separates it from a container.

**Syntax:**

```bash
sudo chroot NEWROOT COMMAND
```

**Example usage and expected output:**

```bash
$ docker export $(docker create alpine:3.20) -o /tmp/alpine.tar
$ mkdir /tmp/newroot && sudo tar -xf /tmp/alpine.tar -C /tmp/newroot
$ sudo chroot /tmp/newroot /bin/sh -c 'cat /etc/os-release | head -1; ps aux | head -2'
NAME="Alpine Linux"
ps: can't open '/proc': No such file or directory
```

The filesystem view is isolated, but there is no PID, network, or resource isolation: exactly the gap namespaces and cgroups later filled.

**Production usage example:** Understanding this gap makes it clear why `chroot` alone is never treated as a security boundary.

**Common errors:** `chroot: cannot run command '/bin/sh'` means the new root lacks the shell or its libraries.

## 6. Production Usage Notes

- **Names map to owners.** Docker (product and company), Moby (open-source upstream project for the engine), containerd (CNCF), runc (OCI reference runtime, maintained under the OCI umbrella), OCI (Linux Foundation specs). Know which one an issue belongs to before filing bugs.
- **Version schemes changed.** Docker moved from `1.13` to calendar-style `17.03` in 2017, and later to `23.0`, `24.0`, `25.0`, and onward. Do not assume a small number is old without checking.
- **Legacy image formats persist.** Docker Image Manifest V2 Schema 2 is still widely served; registries and runtimes accept both it and OCI. Schema 1 is deprecated and removed from modern tooling.
- **The runtime landscape is stable but not static.** Kubernetes nodes overwhelmingly run containerd or CRI-O directly, with no Docker daemon ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).
- **Vendor changes affect procurement.** Desktop licensing ([§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)) moved many teams to alternatives for developer laptops while leaving Docker Engine on servers unchanged.

## 7. Security Considerations

- **History is a list of isolation failures.** chroot escapes, shared-kernel exploits, and runc's `CVE-2019-5736` (overwriting the host runc binary via `/proc/self/exe`) each drove hardening: user namespaces, seccomp defaults, rootless mode, read-only runc handling.
- **Standardization improves auditability.** A common OCI bundle and image format allows scanners, signers, and admission controllers to work independent of the build tool.
- **A single-daemon design concentrated risk.** The early monolithic, root daemon model is why modern designs favor rootless operation and daemonless builds ([§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md), [§4](Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)).
- **Supply-chain trust arrived late.** Early Docker Hub usage was largely unsigned; content trust, signatures, and SBOM/provenance came later and are covered in the security parts of this knowledge base.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Diagnostic |
|---|---|---|
| Old image refuses to pull with `manifest ... schema 1 ... not supported` | Legacy Schema 1 image | `docker manifest inspect`; rebuild and push with a current client |
| `ctr containers ls` empty on a Docker host | Wrong containerd namespace | `ctr -n moby containers ls` |
| Confusion over `dockerd` vs `containerd` logs | Two separate daemons | `journalctl -u docker`, `journalctl -u containerd` |
| Tutorial commands fail on new Docker | Docs written for pre-17.03 or LXC-driver era (`docker daemon`, `-lxc-conf`) | Check `docker --version`; use `dockerd` and current flags |
| Kubernetes node cannot find Docker after upgrade to 1.24+ | dockershim removed | `crictl info`; use containerd or CRI-O runtime endpoint |

## 9. Best Practices

- Learn the **component names and owners** (Docker, Moby, containerd, runc, OCI, CNCF) and use them precisely.
- Build **OCI-compliant images** and avoid tool-specific extensions where portability matters.
- Track **runtime CVEs** for runc and containerd, not only for your application dependencies.
- Prefer **current, documented flags**; treat pre-2017 blog posts as historical.
- When evaluating tools, ask **which standard they implement** (OCI image, OCI runtime, CRI) rather than which brand they carry.

## 10. Common Anti-Patterns / Mistakes

- **Saying "Docker" when meaning "containers" or "OCI images".** It obscures what is actually required.
- **Assuming Kubernetes needs Docker.** It needs a CRI runtime; Docker was one option through dockershim.
- **Following outdated tutorials** that rely on removed features (Schema 1, LXC execution driver, `docker daemon`).
- **Pinning to an old runc** because "nothing changed", missing escape fixes.
- **Treating chroot-style isolation as a sandbox.**

## 11. Interview Questions

**🎯 Beginner:** _"A colleague says Docker invented containers in 2013. What is your response?"_
**Model answer:** Docker popularized and productized containers; the underlying pieces are older: chroot, FreeBSD jails, Solaris Zones, LXC, and the Linux namespaces and cgroups from the mid-2000s. Docker, created by Solomon Hykes at dotCloud and unveiled in March 2013, added a portable image format, layered builds, a simple CLI, and a registry (Hub). Its winning idea was the image workflow, not the isolation primitives.
_What the interviewer is probing for:_ Historical accuracy and knowing what Docker actually contributed.

**🎯 Intermediate:** _"What are runc and containerd, and why are they separate from Docker today?"_
**Model answer:** runc is the OCI reference runtime, extracted from Docker's libcontainer in 2015; it is a short-lived CLI that creates the container and exits. containerd was extracted from Docker in 2016 and donated to the CNCF in 2017; it manages images, snapshots, and lifecycle. Both are neutral components that Docker, Kubernetes, and others reuse. On a Docker host you can see the chain with `ps -ef | grep -E 'dockerd|containerd'` and `ctr -n moby containers ls`.
_What the interviewer is probing for:_ Knowing the component lineage and why modularity mattered.

**🎯 Senior:** _"After upgrading to Kubernetes 1.24, a team's nodes fail because they relied on Docker. Explain what changed and how you fix it."_
**Model answer:** Kubelet speaks CRI, which Docker Engine does not, so a built-in dockershim translated calls; it was removed in 1.24 as a maintenance burden since containerd implements CRI directly. Images built with Docker still run because they are OCI-compatible. Switch nodes to containerd or CRI-O, replace `docker ps/logs` debugging with `crictl ps/logs` or `ctr -n k8s.io`, and audit workloads that mount the Docker socket, since there is no dockerd on the node. If Docker Engine is truly needed, cri-dockerd provides a shim.
_What the interviewer is probing for:_ Understanding this was a CRI decision, not an anti-Docker one, and the practical migration impact.

**🎯 Architect:** _"Design a 10-year container platform strategy given the 2019-2021 vendor shifts (Mirantis acquisition, Desktop licensing). What do you standardize on?"_
**Model answer:** Depend on standards at the interfaces: OCI images and runtime spec, CRI for orchestration, and registry distribution APIs. Keep tools swappable: developers may use Docker Desktop, Podman, or Colima; CI uses rootless builders; clusters use containerd or CRI-O. Avoid vendor-specific features in Dockerfiles and Compose where possible, mirror base images in a registry you control, and track license terms as a risk item. Test a migration path periodically so switching cost stays low.
_What the interviewer is probing for:_ Managing vendor risk by pinning to standards rather than brands.
## 12. Common Misconceptions

- **"Docker invented containers."** It popularized and productized them on top of decades of prior work.
- **"Docker is the OCI."** Docker contributed to it, but the OCI is a neutral foundation project.
- **"containerd is part of Kubernetes."** It is an independent CNCF project that Kubernetes can use.
- **"Moby and Docker are the same."** Moby is the upstream project; Docker is a product assembled from it.
- **"Kubernetes dropped Docker images."** It dropped only the dockershim; images built with Docker still run.
- **"runc is a daemon."** It is a short-lived CLI that creates the container and exits.

## 13. 🔑 Key Takeaways

- Containers rest on ~30 years of isolation work; the key Linux pieces are namespaces and cgroups (mid-2000s).
- **dotCloud** (2008) built the tooling that became **Docker** (open-sourced 2013); its winning idea was the **image workflow**.
- The **OCI** (2015) standardized images and runtimes; **runc** and **containerd** came out of Docker as neutral components.
- **Moby** is the upstream; **Docker** is a product.
- The 2022 **dockershim removal** was a CRI decision, not an anti-Docker one.
- Standards, not brands, are what keep tooling portable.

## 14. Related Concepts & What's Next

- [§1](Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md) defines what a container is; this section explains how it got here.
- [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) positions Docker against Podman, LXC, rkt, and standalone containerd.
- [§6](Section-06-Part1-Docker-Editions-and-Licensing-Changes.md) continues the business history: editions and licensing changes.
- [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) shows the modern dockerd, containerd, runc chain; [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md) covers the OCI specs technically; [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md) covers containerd and Kubernetes.

**Next Section:** [§3](Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md) — `Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md`
