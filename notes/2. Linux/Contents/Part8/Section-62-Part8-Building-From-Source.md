# Section 62 (Part 8): Building From Source: configure, make, make install, checkinstall

## 1. Overview: The Escape Hatch, Not the Default

§59 introduced package management as the layered system every distro relies on — repositories, dependency resolution, and package formats that let a package manager install, track, upgrade, and cleanly remove software as a first-class, auditable unit. §60 and §61 covered the two dominant implementations of that layered model (Debian's `dpkg`/`apt`, RHEL's `rpm`/`dnf`). This section covers what happens when that entire layered model isn't available: **building software directly from its source code**, using the classic `configure`/`make`/`make install` pipeline.

This is deliberately framed as an escape hatch, not an alternative worth reaching for by default. Every mechanism §59–§61 provided — dependency tracking, clean removal, upgrade paths, checksum/signature verification — is absent by default when compiling from source and copying the result onto the filesystem by hand. Building from source is the right call in a narrow set of situations, and understanding exactly which situations those are is as important as knowing the mechanics.

> 💡 **Tip:** Treat "should I build this from source?" as a question with a strong default answer of "no, check the package manager first" — this section explains both how to do it when the answer really is yes, and how to avoid quietly landing back in an unmanaged, untracked state on a host that's supposed to be reproducible.

## 2. When Building From Source Is Actually Necessary

There are three legitimate reasons to build from source on a production or semi-production host, and none of them is "I didn't check if a package existed first":

- **No package exists for your distribution or version.** A tool is packaged for Ubuntu but the fleet runs a RHEL-family distro, or a package exists but only for a newer distro release than what's actually deployed, and no backport or third-party repository (§64 covers repository management) fills the gap.
- **A specific unreleased feature or patch is required.** The distro-packaged version lags upstream, and a bug fix, security patch, or feature the workload depends on only exists in a newer upstream release, a specific git commit, or a patched fork that hasn't propagated into any repository yet.
- **Custom compile-time flags or optimizations the distro package wasn't built with.** Distro packages are compiled with generic, broadly compatible flags — a distro-maintained build of a database or a numerical library is very unlikely to be compiled with CPU-specific optimization flags, a non-default allocator, or a compile-time feature toggle a particular workload benefits from, and the only way to get that specific build is compiling it yourself.

Outside of these three, building from source is usually the harder path chosen for the wrong reason — most commonly "I found a GitHub README with `./configure && make && make install` instructions and didn't look for a distro package first." §64's universal formats (Snap, Flatpak, AppImage) and third-party vendor repositories (§64) both sit between "distro package" and "raw source build" and are worth checking before reaching for this section's approach (7 covers the full priority order).

## 3. The Classic Pipeline: `./configure && make && make install`

The three-command idiom compresses three genuinely distinct phases, each worth understanding on its own rather than treating the whole thing as one opaque incantation.

```bash
tar -xzf software-1.2.3.tar.gz
cd software-1.2.3
./configure
make
sudo make install
```

### 3.1 `./configure` — Probing the Build Environment

`configure` is not a hand-written script for the specific project — it's almost always **generated** by the **GNU Autotools** toolchain (`autoconf`/`automake`), shipped pre-generated inside the source tarball so an end user doesn't need Autotools installed just to build the software. What it actually does at runtime:

- **Probes the build environment** — checks for a working C/C++ compiler and toolchain, looks for required libraries and their header files (a library's runtime `.so` is not enough; the `-dev`/`-devel` header package from §60/§61 is what `configure` is actually checking for), and tests compiler capabilities that vary across systems.
- **Resolves and validates dependencies** — for every library the source code needs (compression, TLS, a database client library, whatever the project links against), `configure` confirms both the library and its headers are present, and fails fast with a specific, named error ("configure: error: zlib not found") rather than letting a much less legible failure surface later during compilation.
- **Produces a `Makefile` tailored to this exact system** — the output of a successful `configure` run is a generated `Makefile`, written to reflect the compiler found, the paths where dependencies were located, and any options passed to `configure` itself. This is why `configure` must be re-run (or at least its cache cleared) after significant environment changes — the `Makefile` it already produced reflects the environment as it was probed, not as it currently is.

A failed `configure` run — "missing dependency X" — is the single most common failure point in this pipeline, and the fix is almost always installing the corresponding `-dev`/`-devel` package via the distro's own package manager (§60/§61) before retrying, which is itself a small irony worth noticing: even a from-source build usually depends on the distro package manager for its build-time dependencies.

### 3.2 `make` — Compiling, Respecting the Dependency Graph

`make` reads the `Makefile` `configure` just produced and drives the actual compilation. Its defining property, and the reason it has remained the standard build driver for decades rather than being replaced by a simple shell script, is that it understands the **dependency graph between source files**: each target in the `Makefile` declares which files it depends on, and `make` only rebuilds a target when one of its declared dependencies is newer (by filesystem timestamp) than the target itself.

Practically, this means:

- A full build from a clean checkout compiles everything, because nothing has been built yet.
- Re-running `make` after editing a single source file recompiles only that file and whatever depends on it (relinking the final binary, typically) — not the entire project from scratch. On a large C/C++ codebase this difference is the gap between a rebuild taking seconds versus tens of minutes.
- `make -j<N>` parallelizes compilation across independent targets that don't depend on each other, using multiple CPU cores — directly analogous to the parallel-startup model §13 described for systemd's dependency-graph-based service startup, applied here to compilation units instead of services.

### 3.3 `make install` — Copying Build Artifacts Into Place

`make install` reads the `install` target from the same `Makefile` and copies the already-built artifacts — compiled binaries, libraries, man pages, headers, config file templates — from the build directory into their final locations on the filesystem.

By convention, an unmodified `configure` install prefix is **`/usr/local/`** — `/usr/local/bin/`, `/usr/local/lib/`, `/usr/local/share/`, mirroring the layout under `/usr/` that §17's Filesystem Hierarchy Standard coverage described. That convention exists for a specific, deliberate reason: **`/usr/local/` is reserved by the FHS specifically for software installed outside the distribution's own package manager**, so that a locally built binary never collides with, overwrites, or gets silently overwritten by a distro-packaged file under `/usr/`. A distro's package manager never installs anything into `/usr/local/` and never expects anything there — it's the one region of the filesystem carved out precisely for this use case.

A common `configure` flag changes that destination:

```bash
./configure --prefix=/opt/software-1.2.3
```

`--prefix` is worth using deliberately whenever the build is meant to coexist cleanly alongside a system that might also get the same software from a distro package later, or when multiple versions of the same source build need to live side by side without overwriting each other.

## 4. The Real Problem With Raw `make install`

`make install` is a **file-copy operation**, not a package-management operation, and that distinction is the core operational risk of this entire pipeline:

- **No uninstall tracking.** `make install` writes files; it does not record _which_ files it wrote anywhere queryable. There is no `make uninstall` guarantee — some `Makefile`s implement one, most don't, and even the ones that do rely on the same file list still being accurate against the currently installed state, which drifts over time.
- **No dependency tracking.** Nothing records that this software depends on a specific version of a shared library it linked against. If that library is later upgraded or removed by the distro's own package manager, the from-source build can break silently, with no dependency-resolution mechanism (the kind §59 described for `apt`/`dnf`) available to catch or prevent it.
- **No upgrade path.** Installing a newer version means either manually locating and removing the old version's files first, or simply copying the new version's files over the old ones and hoping nothing changed in ways that leave stale files behind — there's no `apt upgrade`/`dnf upgrade` equivalent that understands what changed between versions.
- **Silent conflicts with a distro-packaged version of the same software.** If a distro package for the same software is later installed — or already exists — a raw `make install` targeting `/usr/` (rather than `/usr/local/`, per 3.3) can overwrite distro-managed files outright, or, more insidiously, install to a path earlier in `$PATH` than the distro version, silently shadowing it. A binary at `/usr/local/bin/foo` shadowing `/usr/bin/foo` — because `/usr/local/bin` conventionally precedes `/usr/bin` in `$PATH` — is a well-known source of "I updated the package but the version didn't change" confusion, and it's a direct consequence of the two installation methods having no awareness of each other whatsoever.

> ⚠️ **Warning:** Raw `make install` leaves the package manager with **zero knowledge** that the software exists. `dpkg -L`/`rpm -ql` (§60/§61) will never list its files, `apt remove`/`dnf remove` will never find it, and a `dpkg -S`/`rpm -qf` reverse-lookup (§60/§61) against one of its files will report nothing. On a host that's meant to be reproducible, auditable, or eventually torn down and rebuilt from a known state, an untracked `make install` is effectively invisible technical debt — it works fine until someone needs to know exactly what's installed on the box, at which point it's a manual archaeology exercise rather than a query.

## 5. `checkinstall`: Making the Build Trackable

**`checkinstall`** is the practical mitigation for the problem in 4, and it's worth treating as close to mandatory whenever a from-source build is genuinely necessary on a host that matters. Rather than running `make install` directly, `checkinstall` is substituted for that final step:

```bash
./configure
make
sudo checkinstall          # instead of: sudo make install
```

What `checkinstall` actually does: it runs the project's own `make install` under the hood, but **intercepts every file operation that step performs**, then packages everything that got written into an actual `.deb` (on Debian-family systems) or `.rpm` (on RHEL-family systems) — complete with a package name, version, and file manifest, built on the fly from the intercepted install. That generated package is then installed through the normal package manager (`dpkg -i`, or directly registered via `rpm`), not copied by hand.

The result is a from-source build that is now **fully trackable through the normal package manager**, closing every gap from 4:

- `dpkg -L <name>` / `rpm -ql <name>` (§60/§61) lists exactly which files it installed, because they're now registered like any other package.
- `apt remove` / `dnf remove` (§60/§61) cleanly uninstalls it — the actual uninstall guarantee raw `make install` never provided.
- It shows up in the standard installed-package inventory (`dpkg -l`, `rpm -qa`) alongside every distro-managed package, so a fleet audit or compliance inventory (§59's dependency-resolution and package-tracking concepts) doesn't have a blind spot for it.
- A later distro package for the same software installing over it is a normal package **conflict**, caught and reported by the package manager the way any package conflict would be — not a silent, undetected file overwrite.

**Why this is generally the better practice:** `checkinstall` doesn't eliminate the underlying risk of building from source (compile-time dependency drift, no upstream security advisory feed tied to a from-source build, no automatic future upgrades) — but it eliminates the specific, avoidable risk that raw `make install` adds on top of those: total invisibility to the tool responsible for knowing what's on the box. Given that `checkinstall` costs essentially nothing over plain `make install` — same build steps, one substituted final command — there's rarely a good reason to skip it once a from-source build has already been decided on.

## 6. Recommendation Hierarchy

A clear priority order for getting software onto a Linux host, from most to least preferred, with the reasoning behind each step down:

1. **Distro package** (`apt install` / `dnf install`, §60/§61) — full dependency resolution, signature verification, tracked installation, a maintained upgrade path, and security patches flowing through the distro's own advisory process. Always check here first.
2. **Third-party repository package** (a vendor's own `apt`/`yum` repo, added per §64) — still a real package, still tracked and upgradable through the normal package manager, still dependency-resolved — just sourced from outside the distro's default repositories because the distro doesn't package that software (or a current-enough version of it) itself.
3. **`checkinstall`-wrapped source build** — necessary when neither of the above has what's needed (2), but at least trackable, removable, and visible to the package manager afterward (5).
4. **Raw `make install`** — the last resort, used only when `checkinstall` genuinely isn't viable (a project's install step does something checkinstall can't cleanly intercept, or checkinstall itself isn't available and can't be added), and accepted only with the untracked-software risk from 4 explicitly understood and, ideally, documented somewhere a future administrator (including a future version of the same administrator) will actually see it.

Each step down this list trades tracking, dependency resolution, and upgrade convenience for flexibility — the ability to get exactly the version, patch, or compile-time configuration a package doesn't offer. The hierarchy isn't "always use the top option" so much as "never skip a step without a specific reason that step doesn't work," which is the same discipline §59 established for package management generally: reach for the layered, tracked tooling first, and treat dropping a layer as a deliberate, justified decision rather than a default habit.

## 7. Hands-On: Auditing a Host for Untracked Source Builds

### 7.1 Finding files under `/usr/local/` with no owning package

**Purpose:** `/usr/local/` (3.3) is exactly where raw `make install` output should live by convention — auditing it directly is the fastest way to inventory what's been built from source on an unfamiliar host.

```bash
ls -la /usr/local/bin /usr/local/lib
```

**Expected output:** Any binaries or libraries listed here are, by FHS convention, not distro-package-managed — cross-check each one against 7.2 to confirm.

### 7.2 Confirming a specific file has no owning package

**Purpose:** Directly ask the package manager whether it knows about a given file — the ground-truth check for "is this tracked or not."

```bash
dpkg -S /usr/local/bin/somefile     # Debian-family
rpm -qf /usr/local/bin/somefile     # RHEL-family
```

**Expected output:** A tracked file returns the owning package name. An untracked from-source build returns "no path found" (`dpkg -S`) or "file is not owned by any package" (`rpm -qf`) — that specific error message is the confirmation the file is an untracked artifact, not a false negative worth second-guessing.

**Common errors:** Assuming a file under `/usr/local/` is automatically untracked without checking — a `checkinstall`-built package can still choose `/usr/local/` as its prefix, and would then show up correctly in `dpkg -S`/`rpm -qf` despite living in the same directory raw builds use. Location alone isn't proof; the ownership query is.

**Troubleshooting:** If a fleet-wide audit turns up multiple untracked binaries across many hosts, that's a strong signal worth escalating into a standardization effort — replacing ad hoc source builds with either a proper third-party repository (§64) or a checkinstall-wrapped internal package process, rather than leaving every host's from-source software as an individually undocumented snowflake.

## 8. Common Misconceptions

1. **"`./configure && make && make install` is basically universal and always safe to run."** It's a genuine escape hatch with real, lasting downsides (4) — the fact that it works mechanically on most Autotools-based projects doesn't mean it's the right default choice ahead of checking for a distro package first (2, 7).
2. **"`configure` just checks compiler flags."** It's doing meaningfully more — probing for and validating every library/header dependency the source needs, and generating a `Makefile` tailored to this specific system's toolchain and paths (3.1). A `configure` failure is almost always a missing `-dev`/`-devel` dependency, not a compiler problem.
3. **"`make install` and a distro package achieve the same end state."** They both end with software available on the system, but only one of them is trackable, removable, dependency-aware, and upgrade-safe afterward (4) — the end state looks similar; the operational properties are not equivalent at all.
4. **"`checkinstall` is just a convenience wrapper, not worth the extra step."** It's the difference between an install the package manager can see and one it can't (5) — given the near-zero extra cost, skipping it is rarely justified once a from-source build has already been decided on.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What do `configure`, `make`, and `make install` each actually do?"_
**Model answer:** `configure` probes the build environment — checking for a compiler, required libraries, and their header files — and generates a `Makefile` tailored to this specific system if everything needed is present. `make` reads that `Makefile` and compiles the source, using the declared dependency graph between files so only what's changed (or never been built) gets recompiled, rather than rebuilding everything every time. `make install` copies the already-built binaries, libraries, and supporting files from the build directory to their final install locations — by convention `/usr/local/` unless a different `--prefix` was passed to `configure`.
_What the interviewer is probing for:_ That the candidate understands these as three distinct phases with distinct jobs, not one opaque three-word incantation.

**🎯 Intermediate:** _"Why does `/usr/local/` matter as the default install location, and what happens if you install into `/usr/` instead?"_
**Model answer:** `/usr/local/` is reserved by the Filesystem Hierarchy Standard specifically for software installed outside the distribution's package manager, precisely so it can never collide with distro-managed files under `/usr/`. Installing into `/usr/` directly risks overwriting a distro-packaged file outright, or landing in a `$PATH` position that shadows the distro version silently — since `/usr/local/bin` conventionally precedes `/usr/bin` in `$PATH`, a from-source build there can quietly take precedence over a package-manager-installed version of the same tool, producing confusing "I upgraded but nothing changed" symptoms that are actually "the wrong binary is running."
_What the interviewer is probing for:_ Concrete understanding of the FHS convention's actual purpose, not just "that's where it goes by default."

**🎯 Senior:** _"What's genuinely wrong with `make install`, and how does `checkinstall` fix it?"_
**Model answer:** `make install` is a raw file-copy operation with no tracking layer behind it — no record of which files it wrote, no dependency tracking against libraries it linked, no uninstall guarantee, and no upgrade path beyond manually managing file overwrites. On a host that needs to stay auditable or reproducible, that's untracked technical debt that's invisible until someone needs to know exactly what's on the box. `checkinstall` fixes this by running the same `make install` step but intercepting every file operation it performs, then packaging the result into an actual `.deb` or `.rpm` and installing that through the normal package manager instead of copying files directly. The build is then fully visible to `dpkg -L`/`rpm -ql`, cleanly removable through `apt remove`/`dnf remove`, and shows up in standard installed-package inventories — closing the tracking gap at essentially no extra cost over plain `make install`.
_What the interviewer is probing for:_ Specific, itemized understanding of what tracking gap exists and how checkinstall closes each part of it — not just "checkinstall is better."

**🎯 Architect:** _"You've inherited a fleet where some hosts have software installed via unknown means — not showing up in the package manager, but clearly present and in use. How do you approach this, and how do you prevent recurrence?"_
**Model answer:** First, an audit pass per 7 — enumerate what's under `/usr/local/` (and any other non-standard install prefixes discovered along the way) on each host, then cross-check every file against `dpkg -S`/`rpm -qf` to confirm which ones are genuinely untracked versus checkinstall-built packages that happen to share the same directory convention. For each confirmed untracked install, I'd want to understand why it exists before touching it — reproducing the original build (source version, configure flags, patches applied) is the prerequisite for safely converting it into a tracked package rather than just deleting something a workload might depend on. Where the original need was legitimate (2) — no distro package existed, a specific patch or compile flag was required — I'd repackage it properly: either promote it into an internal third-party repository (§64) if it needs to exist on many hosts long-term, or at minimum rebuild it through checkinstall so it's trackable and upgradable going forward. Prevention is a policy change, not a one-time cleanup: enforce the recommendation hierarchy from 7 as an actual standard — distro package first, then third-party repo, then checkinstall-wrapped build, raw `make install` only as a documented, justified exception — ideally backed by golden-image or configuration-management tooling (Part 13 covers this) so the decision is made once, centrally, rather than repeatedly and inconsistently per host by whoever happened to be troubleshooting at the time.
_What the interviewer is probing for:_ Fleet-scale audit discipline consistent with the pattern established elsewhere in this knowledge base, and recognizing that the durable fix is a policy/tooling change, not just cleaning up the current instances.

## 10. Key Takeaways

- Building from source is an escape hatch for three specific situations — no distro package exists, an unreleased upstream feature/patch is needed, or custom compile-time flags/optimizations the distro build lacks — not a default first choice (2).
- `configure` probes the environment for a compiler and dependencies (including headers, not just runtime libraries) and generates a `Makefile`; `make` compiles using a dependency graph so only changed files rebuild; `make install` copies the result to `/usr/local/` by convention, or wherever `--prefix` points (3).
- `/usr/local/` is reserved by the FHS specifically to keep from-source installs separate from distro-package-managed files under `/usr/` — installing outside that convention risks overwriting or silently shadowing a distro package via `$PATH` ordering (3.3, 4).
- Raw `make install` has no uninstall tracking, no dependency tracking, and no upgrade path, and it's entirely invisible to the package manager — a real, avoidable source of untracked technical debt on any host that needs to stay auditable (4).
- `checkinstall` fixes this by intercepting `make install`'s file operations and packaging them into a real `.deb`/`.rpm`, making the build trackable, removable, and visible through the normal package manager at essentially no extra cost (5).
- The recommendation hierarchy is distro package > third-party repository package > checkinstall-wrapped build > raw `make install` — each step down trades tracking and upgrade safety for flexibility, and should be a deliberate, justified choice, not a default habit (6).

## 11. Related Concepts & What's Next

This section is the direct escape-hatch counterpart to the layered package-management model §59 introduced and §60/§61 implemented for Debian- and RHEL-family systems — every tracking guarantee those sections described (dependency resolution, clean removal, upgrade paths) is what's missing from a raw source build, and `checkinstall` exists specifically to recover it. The `/usr/local/` convention ties directly back to §17's Filesystem Hierarchy Standard coverage (Part 3). §63 (next) covers the universal package formats — Snap, Flatpak, AppImage — a different answer to some of the same "distro package doesn't have what I need" pressure, worth comparing directly against this section's approach once both are in view.

**Next Section:** §63 — `Section-63-Part8-Universal-Package-Formats.md`
