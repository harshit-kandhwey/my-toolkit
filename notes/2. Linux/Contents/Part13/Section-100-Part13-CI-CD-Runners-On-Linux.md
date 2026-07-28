# Section 100 (Part 13): CI/CD Runners on Linux

§99 covered the kernel primitives underneath containers in depth. This section applies that directly to a concrete, extremely common production use case: the Linux hosts and containers that actually execute CI/CD pipeline jobs.

## 1. What a CI/CD Runner Actually Is

A **runner** (sometimes called an agent or worker, depending on the platform) is a Linux host or container that executes pipeline jobs on behalf of a CI/CD platform — GitHub Actions, GitLab CI, Jenkins, and similar tools. When a pipeline is triggered (a push, a pull request, a scheduled run), the CI/CD platform's control plane doesn't do the actual work itself — it dispatches the job to a runner, which is the thing that actually checks out the repository's code, runs the build, executes the test suite, and potentially deploys the result. The control plane orchestrates and reports; the runner does the real, resource-consuming work.

This means a runner is, fundamentally, just a Linux host set up to do a specific job repeatedly and reliably — everything covered elsewhere in this roadmap about users and permissions (Part 4), package management (Part 8), and systemd-managed services (Part 9) applies to a runner host exactly as it applies to any other Linux host, because that's what it is underneath the CI/CD-specific framing.

## 2. Why Linux Dominates as the Runner OS

Linux is overwhelmingly the default choice for CI/CD runners, for reasons that compound rather than any single decisive factor:

- **Mature tooling ecosystem.** Build tools, compilers, package managers, and container runtimes all have their most mature, best-supported implementations on Linux — this is the direct, practical payoff of everything Part 8 covered about package management maturity.
- **Container-native.** §99's namespaces/cgroups/OverlayFS foundation is Linux-kernel machinery — running pipeline jobs in containers (3, below) is a first-class, low-overhead operation on Linux in a way it fundamentally is not on other operating systems, which either lack that kernel machinery or need a Linux VM underneath to provide it.
- **Cost-efficient at scale.** Linux hosts and containers are typically cheaper to run at the volume CI/CD demands — pipelines run constantly, often many times per hour across a busy team, and that volume makes per-minute or per-host cost differences compound quickly.
- **Target-environment alignment.** The vast majority of software being built, tested, and deployed by these pipelines targets Linux production environments anyway — building and testing on the same OS family the software will actually run on avoids an entire class of "works in CI, breaks in production" environment-mismatch problems.

## 3. Ephemeral vs. Persistent Runners

This is one of the most consequential architectural decisions in CI/CD runner design, and it's a genuine trade-off rather than a case where one option is simply better.

**Ephemeral runners** are freshly spun up — as a fresh container or VM — for each individual job, and destroyed immediately afterward. Every job starts from a known-clean state: no leftover files from a previous job, no state that could leak between unrelated pipeline runs, no risk of one job's dependencies silently interfering with another's. This directly mirrors §99's container-image model — starting a fresh container per job from a known image is exactly the fast-startup, no-shared-mutable-state property OverlayFS's layering makes cheap.

**Persistent runners** are long-lived hosts that stay up across many jobs over time, retaining state — build caches, downloaded dependencies, compiled artifacts from previous runs — between jobs specifically for speed. Re-downloading and rebuilding everything from scratch on every single job can be a substantial, repeated cost; a persistent runner that already has a warm dependency cache or partially-built artifacts from a previous run can finish the same job meaningfully faster.

| Dimension          | Ephemeral                                                  | Persistent                                                                    |
| ------------------ | ---------------------------------------------------------- | ----------------------------------------------------------------------------- |
| State between jobs | None — clean slate every time                              | Retained (caches, artifacts) — faster repeat runs                             |
| Reproducibility    | High — no cross-job contamination possible                 | Lower — a previous job's leftover state can affect the next                   |
| Speed per job      | Slower (no warm cache) unless caching is solved separately | Faster, assuming the retained state is actually helpful                       |
| Security exposure  | Lower — nothing persists for an attacker to leverage       | Higher — compromise of one job can potentially affect others sharing the host |

Many real setups don't pick one extreme — they use ephemeral runners for the isolation guarantee while layering in an external cache (a shared artifact/dependency cache outside the runner itself) to recover most of the speed benefit without keeping the runner host itself persistent.

## 4. Runner Registration and Security Considerations

A self-hosted runner — one an organization operates itself, as opposed to a fully managed runner the CI/CD platform provisions and tears down on its own — with network access to internal resources is a genuine privilege boundary, not a purely operational detail. A pipeline job running on that runner typically has whatever access the runner host itself has: internal network reachability, credentials or secrets configured on that host, and often broad permissions needed to actually deploy things.

⚠️ **Warning:** A compromised or maliciously-triggered pipeline job running on a persistent, self-hosted runner is a genuine attack vector, not a theoretical one — this has been the basis of real, documented supply-chain incidents. The specific case worth taking seriously: **running CI on pull requests from forks or untrusted external contributors.** A malicious PR can include pipeline-definition changes or build-script content that executes arbitrary code on whatever runner picks up that job — if that runner is persistent, self-hosted, and has access to internal resources or secrets, a single malicious contribution can pivot from "code that never even got merged" into a real internal-network foothold. Mitigations include requiring maintainer approval before running CI on fork PRs, using ephemeral runners with no access to production secrets for untrusted-contribution pipelines specifically, and never assuming "it's just a build job" means it can't be a genuine security incident.

## 5. Typical Runner Requirements

A Linux host or container intended to serve as a CI/CD runner typically needs:

- **A container runtime (Docker or equivalent) installed**, since most modern pipeline jobs run containerized per this section's direct tie to §99 — the runner itself often does relatively little work directly and instead spends most of its time starting and managing the containers that actually execute each job step.
- **Sufficient disk space** for build artifacts, dependency caches, and container images — CI/CD workloads are frequently far more disk-I/O- and storage-hungry than a casual glance at "just runs some scripts" would suggest, and running out of disk mid-pipeline is a common, avoidable failure mode.
- **Appropriately sized resources** (CPU, memory) for the expected concurrent job load — a runner host serving a busy team needs capacity planned for its actual peak concurrent-job count, not just its average, since pipeline triggers cluster heavily around common events (a merge to a shared branch, a scheduled nightly build) rather than arriving smoothly spread out.

## 6. Tying This Back to Earlier Parts of This Roadmap

It's worth being explicit that a "CI/CD runner" isn't a new category of thing requiring new fundamentals — it's a direct, concrete application of skills this roadmap already built:

- **Users and permissions (Part 4).** A runner process should run as a dedicated, appropriately scoped user rather than root, with access limited to exactly what pipeline jobs legitimately need — the same least-privilege reasoning §27–§31 covered generally.
- **Package management (Part 8).** Installing and keeping the build tools, language runtimes, and the container runtime itself up to date on a runner host is exactly the `apt`/`dnf`-based operations §59–§64 covered directly, just applied to a host whose specific job is running pipelines.
- **systemd-managed services (Part 9).** Runner agent software — the process that registers with the CI/CD platform and polls for or receives job assignments — is very often itself managed as a systemd service, using exactly the unit-file, `systemctl enable`/`start`, and restart-policy mechanisms §65–§67 covered, so that the runner agent survives reboots and recovers automatically if it crashes.

A runner is, in the end, just a Linux host (or a container running on one) with a specific job — everything this roadmap has built up to this point about administering Linux hosts correctly and securely applies to it without modification.

> 💡 **Tip:** When auditing or hardening a CI/CD runner fleet, it's worth applying the exact same fleet-audit discipline covered elsewhere in this roadmap for any other class of host — ground-truth checks over assumptions, least-privilege by default, and treating a runner with broad internal access as security-sensitive infrastructure rather than as disposable build-script execution that doesn't matter if compromised.

## 7. Common Misconceptions

1. **"CI/CD runners are a fundamentally different kind of infrastructure from regular servers."** They're ordinary Linux hosts or containers with a specific job — the same users/permissions, package management, and systemd-service administration skills that apply to any Linux host apply directly to a runner (6).
2. **"Ephemeral runners are strictly better because they're more secure."** They're a genuine trade-off, not a strict improvement — ephemeral runners give up the speed benefit of warm caches and retained build state that persistent runners provide, and many real setups combine ephemeral runners with an external cache to get most of both benefits (3).
3. **"CI running on pull requests is low-risk because it's 'just a build.'" ** A pipeline job on a persistent, self-hosted runner with internal access is a real privilege boundary — a malicious fork PR that triggers arbitrary pipeline execution is a documented real-world attack vector, not a theoretical concern (4).
4. **"Any managed/hosted CI runner is automatically as safe as a fully isolated ephemeral one."** Managed runners vary in isolation guarantees by platform and configuration — the ephemeral-vs-persistent distinction and its security implications (3, 4) still need to be actively verified for a given setup, not assumed by default.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What is a CI/CD runner, in plain terms?"_
**Model answer:** It's the Linux host or container that actually executes a pipeline's jobs — checking out code, running builds and tests, deploying — on behalf of a CI/CD platform like GitHub Actions or GitLab CI. The platform's control plane triggers and tracks pipelines, but the runner is what actually does the work.
_What the interviewer is probing for:_ A clean separation between "the CI/CD platform" (orchestration) and "the runner" (execution), which is often conflated by newcomers.

**🎯 Intermediate:** _"Explain the trade-off between ephemeral and persistent runners."_
**Model answer:** Ephemeral runners are spun up fresh per job and destroyed afterward — every job starts from a clean, known state with no risk of state leaking between unrelated jobs, which maximizes reproducibility and security, at the cost of losing any warm build cache from a previous run. Persistent runners stay up across many jobs and retain caches and artifacts between them, which can meaningfully speed up repeated builds, at the cost of reduced isolation — one job's leftover state can potentially affect the next, and a compromise persists longer. Many real setups use ephemeral runners for the isolation guarantee while adding an external, shared cache to recover most of the speed benefit.
_What the interviewer is probing for:_ Correctly framing this as a genuine trade-off with concrete costs on both sides, not asserting one option as unconditionally correct.

**🎯 Senior:** _"Why is running CI on pull requests from forks considered a security risk, specifically for self-hosted runners?"_
**Model answer:** A pipeline job typically runs with whatever access the runner host itself has — internal network reachability, configured secrets, deployment permissions. A fork PR can include changes to the pipeline definition or build scripts themselves, and if CI runs automatically on that PR, arbitrary attacker-controlled code executes on whatever runner picks up the job. On a persistent, self-hosted runner with internal access, that's a genuine foothold into internal infrastructure — not a hypothetical, but the basis of real documented supply-chain incidents. Mitigations include requiring maintainer approval before running CI on external PRs, and using isolated, ephemeral runners with no access to sensitive secrets specifically for untrusted-contribution pipelines.
_What the interviewer is probing for:_ Understanding that "just a build job" can be a genuine code-execution vector, and naming concrete, practical mitigations rather than only describing the risk.

**🎯 Architect:** _"How would you design a CI/CD runner fleet for a large organization that needs both fast builds and strong isolation for untrusted contributions?"_
**Model answer:** I'd segment the runner fleet by trust level rather than using one uniform pool. For trusted, internal pipeline triggers (merges from established maintainers, internal repos), I'd allow persistent runners with warm caches for speed, accepting the reduced isolation because the trust level of the triggering code is high. For untrusted triggers — fork PRs, external contributions — I'd route to strictly ephemeral, isolated runners with no access to internal secrets or network resources beyond what's minimally needed to build and test, explicitly requiring maintainer approval before those jobs even run, per §4's warning. Across both pools, I'd apply the same fundamentals this roadmap already covers: dedicated least-privilege users per Part 4, kept-current package management per Part 8, and systemd-managed runner-agent services per Part 9 so the fleet is operationally consistent and auditable. I'd also plan capacity for concurrent-job peaks rather than averages, since job arrivals cluster around common trigger events, and I'd treat container-runtime currency and disk-space headroom (5) as ongoing operational monitoring items, not one-time setup checks.
_What the interviewer is probing for:_ A realistic, segmented design that treats trust level as a first-class architectural input, not a single uniform runner pool, plus fluent integration of earlier-Part fundamentals into the design.

## 9. Key Takeaways

- A CI/CD runner is a Linux host or container that executes pipeline jobs — checking out code, building, testing, deploying — on behalf of a CI/CD platform's control plane, which orchestrates but doesn't itself do the work (1).
- Linux dominates as the runner OS due to tooling maturity, container-native kernel support (§99), cost efficiency at CI/CD's typical volume, and alignment with the Linux production environments most software actually targets (2).
- Ephemeral runners (fresh per job, clean state, more secure) and persistent runners (retained caches, faster, less isolated) represent a genuine reproducibility-vs-speed trade-off, not a clear-cut best choice (3).
- A persistent, self-hosted runner with internal access is a real privilege boundary — running CI on untrusted fork PRs without safeguards is a documented, genuine attack vector, not a theoretical one (4).
- Typical runner requirements — a container runtime (tying to §99), sufficient disk space, and correctly sized resources for concurrent job load — plus the underlying users/permissions (Part 4), package management (Part 8), and systemd-service (Part 9) fundamentals apply to runners exactly as they do to any other Linux host (5, 6).

## 10. Related Concepts & What's Next

This section ties directly to §99 (containers — most modern CI/CD runners execute jobs inside containers built from exactly the namespaces/cgroups/OverlayFS foundation covered there), §45 (bash scripting fundamentals, Part 6 — pipeline steps are very often just shell scripts), and §64 (GPG/package trust, Part 8 — CI pipelines often build and sign packages). This closes the core "how modern pipelines actually run on Linux" thread within Part 13; the remaining sections of this Part (shell scripting for automation pipelines, golden images and immutable infrastructure) build further on the same provisioning-and-execution foundation established across §97–§100.

**Next Section:** §101 — `Section-101-Part13-Shell-Scripting-For-Automation-Pipelines.md`
