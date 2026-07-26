# Section 5 (Part 1): Major Distribution Families (Debian/Ubuntu, RHEL/Fedora, SUSE, Arch, Alpine) and How to Choose

**Roadmap Reference:** 1.5
**Phase:** Phase 1 — Foundations

---

## 1.5.1 The Main Families

§1 established that a distribution is "the kernel plus everything packaged around it." This section makes that concrete: the handful of family trees almost every production Linux host you'll ever touch descends from, and the practical criteria for choosing between them.

| Family                         | Representative Distributions                        | Package Format                   | Package Manager                 | Typical Use Case                                                        |
| ------------------------------ | --------------------------------------------------- | -------------------------------- | ------------------------------- | ----------------------------------------------------------------------- |
| Debian-based                   | Debian, Ubuntu, Linux Mint                          | `.deb`                           | `apt` / `apt-get` / `dpkg`      | General purpose, cloud, desktop, widely used in DevOps tooling defaults |
| Red Hat-based                  | RHEL, CentOS Stream, Fedora, Rocky Linux, AlmaLinux | `.rpm`                           | `dnf` (modern) / `yum` (legacy) | Enterprise servers, regulated environments, long-term vendor support    |
| SUSE-based                     | SUSE Linux Enterprise Server (SLES), openSUSE       | `.rpm`                           | `zypper`                        | Enterprise, strong in Europe, SAP-certified workloads                   |
| Independent / Rolling          | Arch Linux, Gentoo                                  | `pacman` packages / source-based | `pacman`, Portage               | Enthusiasts, highly customized systems, bleeding-edge packages          |
| Minimalist / Container-focused | Alpine Linux                                        | `.apk`                           | `apk`                           | Small container base images (musl libc, small footprint)                |

A useful mental model: most families share a package _format_ (`.rpm` is used by both Red Hat and SUSE lineages) but not necessarily a package _manager_ or repository ecosystem — a `.rpm` built for RHEL is not automatically installable on SLES without compatibility work, because dependency naming, library versions, and repository conventions diverge even when the on-disk format matches. Family relationships are about shared ancestry and tooling philosophy, not universal binary interchangeability.

## 1.5.2 How to Choose in Practice

Distro selection in a professional setting is rarely "which one is technically best" — it's a multi-factor decision where the deciding factors are usually organizational, not technical:

- **Support lifecycle length, concretely.** This is the single most consequential axis for production fleets. Rolling-release distros (Arch) offer no fixed end-of-life — you're always on the latest, at the cost of continuous small breakage risk. Point-release enterprise distros (RHEL, SLES, Ubuntu LTS) instead commit to a fixed support window during which security patches are backported without changing the underlying package versions wholesale — this predictability is what most regulated and large-scale production environments are actually buying. ⚠️ **Verify current source:** exact support-window lengths (e.g., "5 years," "10 years with extended support") change by vendor and by release; don't cite a specific number from memory in an interview or a document without checking the vendor's current lifecycle page.
- **Compliance certifications, at a concept level.** Regulated industries (government, defense, healthcare, finance) frequently require the underlying OS to hold specific certifications before it can even be considered — for example, **FedRAMP** authorization for US federal cloud workloads, or **Common Criteria** evaluation for security-sensitive systems. Enterprise distros with a commercial vendor behind them (RHEL, SLES, Ubuntu Pro) are the ones that typically pursue and maintain these certifications, because certification is an expensive, ongoing process that community-only distros generally don't undertake. If a compliance requirement mandates a specific certification, it can eliminate entire distro families from consideration before any technical comparison even starts.
- **Ecosystem lock-in.** Once a fleet standardizes on a family, switching later is expensive in ways that compound: configuration management playbooks (Ansible roles, Chef cookbooks) often embed distro-specific package names and paths, monitoring/vulnerability-scanning tooling is licensed and tuned per-distro, internal runbooks and tribal knowledge accumulate around one package manager's quirks, and staff hiring/training skews toward whatever the organization already runs. This is why large organizations rarely change their base distro family opportunistically — the switching cost is organizational, not just a `dnf` vs. `apt` syntax difference.
- **RHEL / Rocky / AlmaLinux** — chosen where long vendor support lifecycles, compliance certifications, and enterprise support contracts matter (banks, healthcare, government).
- **Ubuntu (LTS releases)** — extremely common in cloud environments (AWS, Azure, GCP default images) due to predictable long-term support releases and a large ecosystem of documentation and tooling.
- **Debian** — favored for its stability and strict adherence to free software principles; often the base for other distributions.
- **SLES / openSUSE** — a strong default where SAP-certified enterprise application support is a hard requirement, and historically has a larger enterprise footprint in Europe than in North America.
- **Arch / Gentoo** — rarely a production server choice; their value is maximum control and currency for engineers who want to understand a system deeply, not predictable multi-year support.
- **Alpine** — favored for containers because of its very small image size, though its use of `musl` libc (instead of `glibc`) can occasionally cause subtle compatibility issues with software expecting `glibc` behavior. ⚠️ **Warning:** always verify third-party binary compatibility with musl before standardizing on Alpine for production container images.

🔑 **Key Takeaway:** The choice of distribution in enterprise settings is driven less by technical superiority and more by **support lifecycle, compliance certification availability, ecosystem/tooling compatibility, and existing organizational expertise.**

## 1.5.3 Hands-On: Identifying a Distribution and Its Package Ecosystem

When you land on an unfamiliar host — during onboarding, an incident, or auditing a fleet you didn't build — the first question is "what am I actually working with," and the second is "what tooling does it expect me to use." These commands answer both.

### `cat /etc/os-release` — Distribution Identity

**Purpose:** Read the standardized, machine-parseable file that identifies the distribution family, name, and version. This is the same file introduced in §1's hands-on section; it's repeated here because it's the correct _first_ command specifically for the family-identification question this section is about.

**Syntax:**

```bash
cat /etc/os-release
```

**Example output — Debian family (Ubuntu):**

```bash
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.1 LTS"
NAME="Ubuntu"
ID=ubuntu
ID_LIKE=debian
```

**Example output — Red Hat family (Rocky Linux):**

```bash
$ cat /etc/os-release
NAME="Rocky Linux"
ID="rocky"
ID_LIKE="rhel centos fedora"
PLATFORM_ID="platform:el9"
```

**Example output — SUSE family:**

```bash
$ cat /etc/os-release
NAME="openSUSE Leap"
ID="opensuse-leap"
ID_LIKE="suse opensuse"
```

**Example output — Alpine:**

```bash
$ cat /etc/os-release
NAME="Alpine Linux"
ID=alpine
VERSION_ID=3.20.1
```

Alpine's entry notably has **no `ID_LIKE` field** and no meaningful upstream lineage to declare — consistent with it being an independent, purpose-built minimalist distro rather than a downstream rebuild of something else.

**Production usage example:** the `ID` and `ID_LIKE` fields are exactly what configuration-management tooling (Ansible `ansible_os_family`, Chef `platform_family`, custom shell provisioning scripts) branches on to decide which package manager and package names to use — this is the automated equivalent of the manual family lookup this section teaches by hand.

**Common errors:** trusting `NAME` alone and ignoring `ID`/`ID_LIKE` — `NAME` is a human-readable string that can vary in format across versions, while `ID`/`ID_LIKE` are the stable, script-safe fields meant for exactly this kind of branching logic.

### `lsb_release -a` — Legacy Standardized Identity

**Purpose:** Print distribution identity via the older **Linux Standard Base** convention, predating `/etc/os-release`. Still encountered on older systems and in some scripts/documentation that haven't been updated to the newer standard.

**Syntax:**

```bash
lsb_release -a
```

**Key flags:**

| Flag                  | Meaning                                        |
| --------------------- | ---------------------------------------------- |
| `-a`, `--all`         | Print all fields                               |
| `-d`, `--description` | Print only the human-readable description line |
| `-r`, `--release`     | Print only the release/version number          |
| `-c`, `--codename`    | Print only the release codename                |

**Example output:**

```bash
$ lsb_release -a
No LSB modules are available.
Distributor ID: Ubuntu
Description:    Ubuntu 24.04.1 LTS
Release:        24.04
Codename:       noble
```

**Common errors and troubleshooting:**

- `lsb_release: command not found` — the `lsb-release` (or `redhat-lsb-core`) package is not installed by default on many minimal images, including minimal RHEL-family and most container base images. This is the single most common failure mode for this command; when it happens, fall back to `/etc/os-release`, which requires no extra package and is present far more reliably.
- The "No LSB modules are available" line is harmless noise on many systems — it refers to optional LSB compliance modules unrelated to the fields you actually care about.

> 💡 **Tip:** In practice, prefer `/etc/os-release` over `lsb_release` for anything you're scripting — it's present on more systems out of the box, doesn't require installing an extra package, and is the current standardized convention (as covered in §1). Reach for `lsb_release` mainly when a runbook or legacy script already expects it.

### `hostnamectl` — Consolidated Identity (systemd hosts)

Covered in depth in §1's hands-on section; the same command applies here as a fast first check that includes distro identity alongside kernel and virtualization info. Not available on non-systemd distros — most notably **Alpine**, which uses OpenRC by default rather than systemd.

### Identifying Available Package Managers on an Unfamiliar Host

**Purpose:** Confirm which package manager(s) are actually present and usable on a host, rather than assuming based on distro name alone — useful when scripting portable provisioning logic, auditing an unfamiliar system, or working across a genuinely mixed fleet.

**Syntax:**

```bash
which apt dnf yum zypper pacman apk 2>/dev/null
```

**Example output on an Ubuntu host:**

```bash
$ which apt dnf yum zypper pacman apk 2>/dev/null
/usr/bin/apt
```

**Example output on a Rocky Linux 9 host:**

```bash
$ which apt dnf yum zypper pacman apk 2>/dev/null
/usr/bin/dnf
/usr/bin/yum
```

Note both `dnf` and `yum` appear here — on modern RHEL-family systems, `yum` is typically a compatibility symlink to `dnf` rather than a genuinely separate legacy tool, preserved so that older scripts and muscle memory keep working (package-manager internals and the `dnf`/`yum` relationship are covered fully in §59–§64).

**Example output on Alpine:**

```bash
$ which apt dnf yum zypper pacman apk 2>/dev/null
/usr/bin/apk
```

**Common errors:**

- `which` silently returns nothing (and a non-zero exit code) for every tool not present — the `2>/dev/null` suppresses the "not found" stderr noise, but forgetting it clutters output with irrelevant errors for every absent manager, which is expected and harmless, just noisy.
- Assuming the _presence_ of a binary means it's the _primary_ manager in active use — some systems carry a secondary or compatibility package manager installed for edge-case tooling; cross-check against `/etc/os-release`'s `ID`/`ID_LIKE` rather than relying on `which` output alone as the sole signal.

**Production usage example:** bootstrap scripts for configuration management agents (e.g., a shell script that installs Ansible or a monitoring agent before the "real" provisioning tooling takes over) commonly use exactly this pattern — probe for which package manager exists, then branch installation logic — because it works correctly even against a host whose distro identity file is missing, malformed, or from an unanticipated derivative distro.

## 1.5.4 Package Format Internals — Conceptual Comparison Only

This section deliberately stays at the philosophy level; the mechanics of dependency resolution, repository metadata, and transaction handling are covered in full in Part 8 (§59–§64). At a conceptual level, though, the families differ in a way worth understanding now because it explains _why_ certain operational behaviors (like Arch requiring manual intervention on some upgrades, or apt/dnf mostly "just working") exist:

- **Debian/apt and Red Hat/dnf** both use a **declarative, repository-metadata-driven dependency resolver**: you declare what you want installed, and the tool computes a full dependency graph against pre-published repository metadata, resolving conflicts largely automatically. This is why both feel similar in daily use despite different underlying formats.
- **Arch/pacman** uses a simpler, more direct dependency model with less resolver sophistication historically, paired with a strong cultural expectation that the administrator reads release announcements before major updates — rolling-release distros trade automated safety for currency and transparency.
- **Alpine/apk** is deliberately minimal and fast, targeting small, mostly-static container images rather than long-lived, heavily-customized systems — its dependency resolution philosophy optimizes for small closure size over exhaustive compatibility shimming.

🔑 **Key Takeaway:** These philosophy differences are _why_ certain distros feel more or less "hands-off" in daily operations — but the actual command syntax, repository configuration, and transaction mechanics live in §59–§64, not here.

## 1.5.5 Production Usage Notes: Fleet Automation and Mixed-Distro Overhead

- **Golden images diverge by family.** Golden-image pipelines (§102) typically build one base image per distro family, since the provisioning steps, hardening baselines, and package sets are not portable as-is across `apt`/`dnf`/`zypper`/`apk` ecosystems. A fleet standardized on a single family needs one golden-image pipeline; a fleet spanning two families effectively needs two full pipelines maintained in parallel.
- **Ansible/Terraform provisioning differences.** Infrastructure-as-code tooling (§97) has to branch per distro family in real, concrete ways — Ansible's `package` module abstracts _some_ of this, but package names themselves are rarely identical across families (e.g., a library package might be named differently on Debian vs. RHEL vs. SUSE), so playbooks maintained across a mixed fleet accumulate per-family conditionals (`when: ansible_os_family == "Debian"`) that are a real, ongoing maintenance cost, not a one-time setup cost.
- **Mixed-distro fleets create real operational overhead**, not just inconvenience: duplicated hardening baselines, duplicated vulnerability-scanning tool configuration (a scanner needs distro-aware package-to-CVE mapping, per §96), duplicated on-call runbooks, and a wider hiring/training surface for staff who need to be comfortable across ecosystems. Organizations sometimes accumulate a mixed fleet organically (an acquisition, a team going rogue, a specific vendor requiring one family) rather than by deliberate design — recognizing this as _debt_ rather than neutral diversity is a useful senior-level framing.

## 1.5.6 Security Considerations: Default Posture Differences

Distro families differ meaningfully in their **default** security posture out of the box — this matters because "default" is what a host actually runs unless someone deliberately configures otherwise:

- **RHEL-family distros (RHEL, Rocky, AlmaLinux, Fedora)** ship with **SELinux** (Security-Enhanced Linux) enabled and enforcing by default — a mandatory access control system that constrains what processes can do even if they're compromised or misconfigured, beyond standard discretionary Unix permissions.
- **Debian/Ubuntu** instead default to **AppArmor**, a different mandatory access control implementation with a generally simpler, path-based policy model compared to SELinux's label-based model.
- **SUSE** also uses AppArmor by default, consistent with its historical role as an AppArmor-originating distro.
- **Arch and Alpine** generally ship with neither enabled by default, leaving mandatory access control as an opt-in step for the administrator.

The practical consequence: an application that behaves correctly on Ubuntu (AppArmor's default policies) can be unexpectedly blocked by SELinux on a RHEL-family host with no code change involved — a very common real-world troubleshooting scenario, and one reason "it worked on my dev box" bugs sometimes trace back to distro-family security defaults rather than application logic. Full coverage of SELinux and AppArmor mechanics, policy authoring, and troubleshooting (`audit2allow`, `aa-complain`, etc.) is in Part 12, §89–§96.

## 1.5.7 Best Practices

- Standardize on as few distro families as the organization's actual compliance and technical requirements demand — treat every additional family as a recurring multiplier on pipeline, tooling, and runbook maintenance cost, not a one-time decision.
- Pin distro _and_ version explicitly in golden images and IaC definitions — "latest Ubuntu" is not a reproducible specification any more than "Linux" alone is (§1 makes the same point about kernel vs. distro).
- Verify compliance certification requirements (FedRAMP, Common Criteria, industry-specific mandates) _before_ a technical bake-off, since they can eliminate entire families up front and make later technical comparison moot.
- Treat container base-image distro choice (often Alpine, for size) as a decision independent from host OS distro choice — they don't need to match, and conflating "our servers run RHEL so our containers should too" is a common, low-value assumption.

## 1.5.8 Common Anti-Patterns / Mistakes

- **Standardizing on Alpine for production application servers without verifying musl compatibility.** Alpine's small size makes it an attractive default for container base images, but software with compiled dependencies on `glibc`-specific behavior (some Python/Node native modules, some JVM-adjacent tooling, some proprietary binaries) can fail subtly or outright under `musl` — sometimes only under specific edge-case inputs, making the bug hard to reproduce outside the exact container. ⚠️ **Warning:** always test the actual application under musl in a representative environment before standardizing on Alpine, rather than assuming "it's just Linux" compatibility.
- **Mixing distro families without a deliberate reason and cost/benefit assessment.** Accumulating a second family "because a team wanted it" without accounting for the doubled pipeline, tooling, and runbook maintenance cost described in 1.5.5.
- **Letting configuration management scripts assume one distro family** (hardcoding `apt` calls, for instance) without guarding for a different family being present — this breaks silently and confusingly when the script runs against an unexpected host, rather than failing with a clear error.
- **Choosing a distro primarily on personal familiarity** rather than organizational support-lifecycle, compliance, and ecosystem-lock-in criteria — a reasonable individual preference is not, by itself, an adequate justification for a fleet-wide decision.

## 1.5.9 Common Misconceptions

1. **"A newer distro version is always better/safer to run."** Newer isn't automatically more stable or more secure in isolation — a well-supported older LTS/enterprise release still receiving backported security patches can be a _better_ production choice than a newer release nearing its own end-of-life, or one that hasn't yet accumulated the same operational track record. "Current within its support window" matters more than "newest available."
2. **"All distros in the same family behave identically."** Fedora and RHEL share lineage and package format but have very different release cadences, stability guarantees, and intended use cases (Fedora is a fast-moving community release; RHEL is a slow, certified, paid-support product) — family membership tells you about shared tooling and ancestry, not identical behavior or identical suitability for production.
3. **"Package format compatibility means cross-distro binary compatibility."** SUSE and RHEL both use `.rpm`, but a package built for one is not reliably installable on the other without rebuilding or compatibility work — shared format is not the same as a shared repository ecosystem or shared library versions.
4. **"Rolling-release means unstable/unsuitable for any production use."** Rolling-release distros like Arch are a poor fit for most _enterprise_ production fleets for support-lifecycle reasons, but "rolling" and "broken" aren't synonyms — it's a different stability/currency trade-off, appropriate for some specialized use cases (e.g., some ML/research environments wanting the newest driver or library support), not a universal disqualifier.

## 1.5.10 Tiered Interview Questions

**🎯 Beginner:** _"What's the practical difference between Ubuntu and Debian, given that Ubuntu is built on Debian?"_
**Model answer:** Ubuntu is derived from Debian and shares its `.deb` package format and much of its userland tooling, but the two differ in release philosophy and target use case. Debian prioritizes strict free-software principles and a very conservative, thoroughly-tested stable release cycle. Ubuntu adds a more predictable, marketed LTS release cadence, broader default hardware/driver support, and a larger ecosystem of commercial and cloud-vendor support — which is a big part of why Ubuntu LTS became the default base image on major cloud providers. Practically, an engineer moving between the two can reuse almost all `apt`-based knowledge, but should expect differences in default package versions and release timing.
_What the interviewer is probing for:_ whether the candidate understands "family" as shared lineage/tooling rather than interchangeable identity — a common early gap.

**🎯 Intermediate:** _"A team wants to run Alpine as the base image for a Java application in production containers, purely to shrink image size. What would you want to verify before signing off?"_
**Model answer:** I'd flag the musl libc vs. glibc difference as the first thing to check — Alpine uses musl, and some JVM builds and native-dependency Java libraries have historically had subtle compatibility or performance issues under musl that don't show up under glibc-based distros. I'd want the team to actually run the application's test suite and any performance-sensitive paths against an Alpine-based image before committing, rather than assuming compatibility from "it's just Linux." I'd also check whether a smaller glibc-based base image (a slim/minimal variant of a mainstream distro) gets most of the size benefit with less compatibility risk, since Alpine's size advantage is sometimes worth less than the debugging cost of a musl-specific bug found in production.
_What the interviewer is probing for:_ practical skepticism of a popular default (small image size) and awareness of the specific, real compatibility risk behind the section's Alpine warning — not just reciting "Alpine uses musl" as trivia.

**🎯 Senior:** _"Your company currently runs CentOS 7 in production, and CentOS's role changed significantly a few years ago. Walk me through how you'd evaluate a migration path."_
**Model answer:** I'd first confirm the exact current support status and end-of-life date for the distribution in use, since CentOS's traditional role as a free rebuild of RHEL changed when Red Hat shifted focus toward CentOS Stream as a rolling preview of RHEL, pushing organizations wanting a stable free RHEL-compatible option toward alternatives like Rocky Linux or AlmaLinux, or toward paid RHEL subscriptions. I'd evaluate candidates against three criteria: binary compatibility with RHEL (to minimize application changes), support lifecycle length, and total cost of ownership including support contracts. I'd also verify the current state of this transition against official vendor announcements rather than relying on memory, since these decisions and timelines have shifted more than once.
_What the interviewer is probing for:_ Awareness of real, high-profile ecosystem changes and a disciplined "verify current facts before deciding" instinct — not just a fixed opinion.

**🎯 Architect:** _"You're standardizing a multi-thousand-host fleet across teams that have historically run a mix of Ubuntu, RHEL-family, and a handful of Alpine-based container services. How do you approach consolidation, and what do you deliberately leave as legitimate exceptions?"_
**Model answer:** I'd start by quantifying the actual cost of the current mix — duplicated golden-image pipelines, duplicated IaC conditionals, duplicated vulnerability-scanning configuration, and the security-posture inconsistency from differing SELinux/AppArmor defaults — because that cost, not abstract "standardization is good" sentiment, is what justifies the migration effort. I'd separate host OS from container base image as two different decisions: Alpine-based containers are usually fine to leave as-is since container base image choice doesn't carry the same fleet-wide operational weight as host OS choice, provided musl compatibility has actually been verified per-service. For the host-level Ubuntu/RHEL-family split, I'd push toward one primary family chosen against the organization's actual compliance requirements (checking first whether anything mandates FedRAMP or similar certification, which would settle the RHEL-family question immediately) and support-lifecycle needs, then treat any remaining team on the other family as a documented, time-boxed exception requiring active justification to keep — not a permanent parallel track maintained indefinitely by default. I'd explicitly avoid mandating one distro for every workload without exception, since a genuine technical or compliance reason for divergence (e.g., a specific vendor-certified appliance requiring SLES) is a legitimate cost worth paying, distinct from divergence that exists purely from historical inertia.
_What the interviewer is probing for:_ whether the candidate can turn a broad "which distro" question into a structured, cost-aware consolidation strategy that distinguishes legitimate exceptions from accumulated technical debt — an architect-level synthesis of the whole section.

## 🔑 Key Takeaways

- The main distro families are Debian-based (`.deb`/`apt`), Red Hat-based (`.rpm`/`dnf`), SUSE-based (`.rpm`/`zypper`), independent/rolling (Arch, `pacman`), and minimalist/container-focused (Alpine, `.apk`/musl) — shared package _format_ does not imply shared repository ecosystem or binary compatibility.
- Distro choice in production is driven primarily by support lifecycle length, compliance certification availability (FedRAMP, Common Criteria, etc.), and ecosystem lock-in — not raw technical preference.
- `cat /etc/os-release` (preferred, standardized), `lsb_release -a` (legacy, may not be installed), `hostnamectl` (systemd hosts only), and `which apt dnf yum zypper pacman apk` are the practical toolkit for identifying a host's distro family and available package manager.
- Package-format dependency-resolution _philosophy_ differs across families (declarative resolver vs. simpler direct model vs. minimal/static-optimized) — the full mechanics live in §59–§64, not here.
- Distro families ship different default mandatory access control systems — SELinux by default on RHEL-family, AppArmor by default on Debian/Ubuntu/SUSE — which is a common, non-obvious source of "works on one distro, blocked on another" bugs (full depth in §89–§96).
- Mixed-distro fleets carry real, ongoing operational overhead (duplicated golden images, IaC conditionals, scanning configuration, runbooks) — treat additional families as deliberate, justified exceptions rather than accumulated default.
- The Alpine/musl compatibility warning is the highest-value practical anti-pattern in this section: verify before standardizing, don't assume "it's just Linux."

## Related Concepts & What's Next

§1 established the kernel-vs-distribution layering and the standardized identification files (`/etc/os-release`, `uname`) this section builds directly on. §6 (next) takes the distribution concept a step further — where Linux actually runs today across servers, cloud, embedded, mobile, and containers, which is where family choice (especially the Alpine/container question raised here) gets applied concretely. Part 8 (§59–§64) is the deep dive into the package-management internals only summarized conceptually in 1.5.4 — dependency resolution, repository metadata, and transaction mechanics for `apt`, `dnf`/`yum`, and beyond. Part 12 (§89–§96) returns to the SELinux-vs-AppArmor default-posture point from 1.5.6 with full mandatory-access-control policy authoring and troubleshooting coverage. Part 13 (§97–§102) covers golden images and IaC provisioning patterns referenced in 1.5.5's fleet-automation discussion. Part 14 (§103–§110) covers enterprise support models and subscription economics for the vendor-backed families (RHEL, SLES, Ubuntu Pro) discussed in 1.5.2.

---

**Next Section:** §6 — `Section-06-Part1-Where-Linux-Runs-Today.md`
