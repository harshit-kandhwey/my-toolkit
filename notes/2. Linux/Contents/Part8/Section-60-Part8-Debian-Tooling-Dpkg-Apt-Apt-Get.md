# Section 60 (Part 8): Debian-Based Tooling: dpkg, apt, apt-get, .deb Files

## 1. Overview: Two Layers, One Family

§59 established the general concepts every package manager has to solve — dependency resolution, repositories, and the split between a low-level tool that installs packages and a high-level tool that resolves dependencies and talks to repositories on top of it. This section is that layering made concrete for the Debian family (Debian, Ubuntu, and their many derivatives): **dpkg** is the low-level tool, **apt**/**apt-get** is the high-level tool built on top of it, and the **.deb** file is the package format both of them operate on.

The relationship is strict and one-directional. apt does not replace dpkg — it _drives_ dpkg. Every `apt install` ultimately ends in dpkg being invoked to actually unpack a `.deb` and register it in the system's package database. Understanding this layering isn't academic: it's exactly what explains why dpkg can leave a system in a broken dependency state that only apt can climb out of (6), and why "just use dpkg" is fine for a single offline `.deb` but the wrong tool the moment dependencies are involved.

> 💡 **Tip:** Keep the same two-question discipline §13 recommended for init systems: (1) _"what tool actually unpacks files and writes to the package database?"_ — always dpkg, no exceptions — and (2) _"what tool decided what to unpack, in what order, resolving what dependencies?"_ — apt, when repositories and dependency resolution are involved at all.

## 2. dpkg: The Low-Level Tool

**dpkg** (Debian Package) is the foundational tool — it operates directly on `.deb` files and the local package database at `/var/lib/dpkg/`, with no concept of a remote repository, no dependency resolution, and no network access at all. Its entire world is: a `.deb` file already sitting on disk, and the database of what's currently installed.

**Core operations:**

```bash
sudo dpkg -i package.deb      # install (or upgrade) a local .deb file
sudo dpkg -r package-name     # remove a package (config files retained)
sudo dpkg -P package-name     # purge a package (config files removed too)
dpkg -l                       # list all installed packages
dpkg -l 'nginx*'              # list installed packages matching a pattern
dpkg -L package-name          # list every file a package installed
dpkg -S /usr/bin/nginx        # reverse lookup: which package owns this file
dpkg -s package-name          # show status/metadata of an installed package
```

| Flag | Meaning                                                           |
| ---- | ----------------------------------------------------------------- |
| `-i` | Install a local `.deb` file                                       |
| `-r` | Remove a package, leaving configuration files in place            |
| `-P` | Purge — remove a package and its configuration files              |
| `-l` | List installed packages (optionally filtered by a glob pattern)   |
| `-L` | List the files belonging to an installed package                  |
| `-S` | Search: given a file path, report which installed package owns it |
| `-s` | Show a package's status entry from the dpkg database              |

**The critical limitation, stated plainly:** dpkg does not resolve dependencies and does not fetch anything from anywhere. If you hand it a `.deb` file whose control metadata declares a dependency on a package that isn't currently installed, dpkg will not go find and install that dependency — it has no repository to look in even if it wanted to. Depending on the specific dpkg version and flags, it will either refuse to complete the install or install the package anyway and leave it in a broken, unconfigured state, reporting unmet dependencies and leaving the system exactly where 6 picks up.

> ⚠️ **Warning:** `dpkg -i somepackage.deb` succeeding at the shell level (exit code aside) is not the same as the package being in a fully working state. dpkg will happily install a `.deb` with unmet dependencies and leave the binary sitting there non-functional — no dependency, no error loud enough to stop you, just a package that will fail at runtime until the missing dependencies are resolved separately. This is precisely the scenario that makes `apt --fix-broken install` (6) a command every Debian-family administrator ends up needing eventually, not a rare edge case.

**When dpkg is actually the right tool:** installing a single, already-downloaded `.deb` file where you already know its dependencies are satisfied (a vendor-provided package for software not in any repository, a package built in-house, a `.deb` downloaded directly from a project's release page) — and for read-only inspection (`-l`, `-L`, `-S`, `-s`), which apt doesn't replace at all. For anything involving fetching from a repository or resolving a dependency chain, apt is the tool, not dpkg.

## 3. apt / apt-get: The High-Level, Repository-Aware Tool

**apt** (and its older sibling `apt-get`) is the dependency-resolving, repository-aware layer built on top of dpkg. It reads the repository list at `/etc/apt/sources.list` and `/etc/apt/sources.list.d/*.list` (full depth on repositories and GPG signing: §64), maintains a local cache of what each configured repository currently offers, downloads `.deb` files as needed, works out the correct install order given the full dependency graph, and then hands each `.deb` off to dpkg to actually perform the unpack-and-register step.

### 3.1 Updating the package index vs. upgrading packages

```bash
sudo apt update                    # refresh the local package index only
sudo apt upgrade                   # upgrade installed packages, never removing any
sudo apt full-upgrade              # upgrade installed packages, removing/replacing as needed
sudo apt-get dist-upgrade          # apt-get's name for the same full-upgrade behavior
```

> ⚠️ **Warning:** `apt update` and `apt upgrade` are not two spellings of the same idea, and conflating them is one of the most common beginner mistakes on Debian-family systems. `apt update` does not install or upgrade a single package — it only refreshes the local index of what versions are currently available in each configured repository, by downloading each repository's metadata. Running `apt update` alone changes nothing about what's actually installed on the box. `apt upgrade` is the command that actually installs newer versions of already-installed packages, and it only considers versions that `apt update` most recently learned about — which is exactly why the two are almost always run back-to-back (`apt update && apt upgrade`) rather than either alone.

**`apt upgrade` vs. `apt full-upgrade` (`apt-get dist-upgrade`) — the real difference:** `apt upgrade` will upgrade a package to a newer version only if doing so doesn't require removing another currently-installed package to satisfy the new dependency graph — if an upgrade would require a removal, `apt upgrade` simply skips that package and leaves it held back at its current version rather than touching anything else. `apt full-upgrade` (and `apt-get dist-upgrade`, the older name for the same behavior) has no such restraint: it will remove packages if that's what's required to bring the rest of the system to the newest available versions, which makes it the right tool for a distribution version upgrade or a case where held-back packages need to be forced current, but also the reason it deserves more attention before running unattended than plain `upgrade` does — a full-upgrade can legitimately walk away with a package gone that was there five minutes earlier.

### 3.2 Install, remove, purge, search

```bash
sudo apt install nginx             # install a package (and its dependencies) from a repository
sudo apt install ./local.deb       # apt can also install a local .deb, resolving its deps first
sudo apt remove nginx              # remove a package, config files retained
sudo apt purge nginx               # remove a package AND its configuration files
apt search nginx                   # search package names/descriptions across the index
apt show nginx                     # show detailed metadata for a package (version, deps, description)
```

| Command                  | Effect                                                                                                                      |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `apt install <pkg>`      | Install `<pkg>` and any unmet dependencies from configured repositories                                                     |
| `apt install ./file.deb` | Install a local `.deb`, resolving its dependencies from repositories first — the apt-driven alternative to a bare `dpkg -i` |
| `apt remove <pkg>`       | Uninstall `<pkg>`'s program files; **configuration files under `/etc/` are left in place**                                  |
| `apt purge <pkg>`        | Uninstall `<pkg>` and also delete its configuration files                                                                   |
| `apt search <term>`      | Search package names and short descriptions in the local index                                                              |
| `apt show <pkg>`         | Print full metadata for a package: version, dependencies, maintainer, description                                           |

The `remove` vs. `purge` distinction matters operationally more often than it first appears: `remove` is the safer default when a package might be reinstalled later and its existing configuration is worth keeping, while `purge` is the correct choice when decommissioning something for good — a lingering `/etc/nginx/` full of old configuration on a host that no longer runs nginx is exactly the kind of stale state a later administrator (or a configuration-management diff) trips over.

## 4. apt vs. apt-get/apt-cache: Why Both Still Exist

`apt` is the newer, unified command — introduced specifically to give humans a single, friendlier interface (with things like a progress bar and cleaner default output) instead of switching between `apt-get` (install/remove/upgrade operations) and the separate `apt-cache` (search/show/query operations against the index) that predate it. For interactive, day-to-day administration, `apt` is the tool to reach for by default.

`apt-get` and `apt-cache` were not deprecated in the process, and that's deliberate rather than an oversight. `apt`'s output format is explicitly documented as not guaranteed stable across versions — it's designed to be pleasant for a human to read, which means its exact formatting, column layout, and wording are free to change in future releases. `apt-get`/`apt-cache`'s output, by contrast, has stayed stable for a very long time precisely because scripts, configuration-management modules, and automation depend on it.

> ⚠️ **Warning:** Writing a shell script, Ansible module invocation, or any other automation that parses `apt`'s output — checking installed versions, scraping `apt search` results, parsing `apt list --upgradable` — is building on a surface the tool's own documentation says can change. For anything programmatic, use `apt-get`/`apt-cache` (or better, a proper package-querying interface like `dpkg-query` with a format string, or the distribution's package-management API) instead of `apt`. Reserve `apt` for interactive human use, exactly as intended.

In practice this means an experienced Debian-family administrator ends up using both, not out of habit but by design: `apt install`/`apt upgrade`/`apt search` at an interactive terminal, `apt-get install`/`apt-cache policy` inside a script or playbook where output stability matters.

## 5. .deb File Structure, Briefly

A `.deb` file is not a custom binary format — it's an **`ar` archive** (the same archive format used for static libraries, `.a` files) containing a small, fixed set of members:

- **`debian-binary`** — a text file holding the format version number, so tooling can identify the archive as a valid Debian package before parsing anything else.
- **`control.tar.xz`** (or `.gz`/`.zst` depending on the dpkg version) — the package's metadata: the `control` file (name, version, architecture, maintainer, and critically the declared dependency list dpkg reads but never resolves), plus optional maintainer scripts (`preinst`, `postinst`, `prerm`, `postrm`) that run at specific points in the install/remove lifecycle.
- **`data.tar.xz`** (or `.gz`/`.zst`) — the actual payload: the files that get unpacked onto the filesystem, laid out exactly as they should appear once installed (e.g., `usr/bin/nginx`).

This is inspectable directly with standard archive tools — `ar t package.deb` lists the three members, and `dpkg-deb -c package.deb` / `dpkg-deb -e package.deb` are the purpose-built commands for listing a `.deb`'s payload contents and extracting its control metadata respectively, useful when auditing a third-party `.deb` before installing it on a system where that matters.

## 6. Fixing a Broken Dependency State

Because dpkg installs happily accept unmet dependencies (2) and because interrupted apt operations (a killed process, a lost connection mid-download) can leave the dpkg database in a half-configured state, Debian-family systems have a dedicated recovery path:

```bash
sudo apt --fix-broken install       # modern apt spelling
sudo apt-get -f install             # older, equivalent apt-get spelling
sudo dpkg --configure -a            # finish configuring any half-installed packages
```

`apt --fix-broken install` (commonly abbreviated `apt --fix-broken` or the older `apt-get -f install`) looks at the current, possibly-inconsistent state of the dpkg database, works out what needs to be installed, upgraded, or removed to bring every currently-unpacked package's dependencies back into a satisfied state, and does it — without requiring the administrator to manually diagnose which specific dependency is missing. `dpkg --configure -a` is a narrower companion: it resumes running the post-install configuration scripts for any package dpkg unpacked but never finished configuring, which is the common aftermath of an install that was interrupted partway through.

**Production usage example:** the sequence `sudo dpkg -i vendor-package.deb` followed by `apt --fix-broken install` is a routine, expected pattern for installing a vendor-provided `.deb` that isn't in any configured repository — dpkg installs the file directly (accepting the unmet dependencies it can't resolve on its own), and the immediate follow-up `apt --fix-broken install` reaches out to the configured repositories to pull in whatever dpkg couldn't, bringing the system back to a fully satisfied, working state.

## 7. Hands-On: Diagnosing and Repairing a Broken Package State

### 7.1 Confirming a broken state exists

**Purpose:** Establish ground truth on whether the dpkg database is actually in a broken/half-configured state before assuming a fix is needed.

```bash
sudo dpkg --audit
apt list --upgradable 2>/dev/null
```

**Expected output:** `dpkg --audit` reports nothing if the database is consistent; it names specific packages left in a broken or half-configured state otherwise. A package install or apt operation that previously errored out mid-way is the most common real-world cause.

**Common errors:** Assuming a package that merely shows as "held back" during `apt upgrade` is the same as "broken" — held-back packages (2) are a normal, non-error outcome of the safer `upgrade` behavior, not a sign of database corruption.

### 7.2 Running the repair

**Purpose:** Bring the dpkg database back to a fully consistent, satisfied-dependency state using the standard recovery sequence.

```bash
sudo apt --fix-broken install
sudo dpkg --configure -a
sudo apt update && sudo apt upgrade
```

**Expected output:** `apt --fix-broken install` reports what it's about to install/remove/upgrade to reach a consistent state and prompts for confirmation, same as any other apt operation. Running it a second time immediately after should report nothing left to fix — that's the confirmation the repair actually completed rather than only partially resolving the inconsistency.

**Troubleshooting:** If `apt --fix-broken install` itself fails (rather than fixing things), suspect a repository-level problem rather than a purely local one — a package it needs to pull in may no longer exist at the version pinned by a half-completed transaction, which points toward checking `/etc/apt/sources.list*` and `apt update`'s own output for errors before retrying.

## 8. Common Misconceptions

1. **"`apt update` upgrades my packages."** It refreshes the local index of what's available — it changes nothing about what's currently installed. `apt upgrade` (or `full-upgrade`) is the command that actually installs newer versions, and it only knows about versions `apt update` most recently fetched (3.1).
2. **"`dpkg -i` is a safe, complete way to install any `.deb`."** dpkg has no dependency resolution and no repository access — it will install a `.deb` with unmet dependencies and leave the system in a broken state rather than refusing outright or fetching what's missing (2). Use `apt install ./file.deb` when dependency resolution matters, or follow a `dpkg -i` with `apt --fix-broken install` (6).
3. **"`apt remove` and `apt purge` do the same thing."** `remove` leaves configuration files under `/etc/` in place; `purge` deletes them too. Decommissioning a package for good calls for `purge`; a temporary removal that might be reinstalled later usually calls for `remove` (3.2).
4. **"apt and apt-get are just two names for the same tool, use whichever."** They differ specifically in output-format stability — `apt`'s output isn't guaranteed stable across versions and is meant for interactive human use, `apt-get`/`apt-cache`'s output has stayed stable for scripting purposes. Using `apt` inside automation is building on a surface the tool itself doesn't promise to keep stable (4).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between dpkg and apt?"_
**Model answer:** dpkg is the low-level tool that actually installs a `.deb` file and maintains the local package database — it works directly with files already on disk and has no concept of a repository or dependency resolution. apt is the high-level tool that reads configured repositories, resolves the full dependency graph for what you're trying to install, downloads the needed `.deb` files, and then hands each one to dpkg to actually perform the install. Every apt operation ends in dpkg doing the actual unpacking; apt is the layer that figures out what dpkg needs to be told to do.
_What the interviewer is probing for:_ Correct layering — that apt doesn't replace dpkg, it drives it — rather than treating them as two unrelated, interchangeable package managers.

**🎯 Intermediate:** _"What does `apt update` actually do, and why doesn't it upgrade anything?"_
**Model answer:** `apt update` downloads and refreshes the local cache of each configured repository's current package index — what versions are available, their dependencies, checksums — it doesn't touch anything currently installed on the system. Upgrading is a separate, deliberate step (`apt upgrade` or `apt full-upgrade`) that looks at the freshly refreshed index and installs newer versions of packages already on the box. They're kept separate because refreshing the index is cheap, frequent, and safe, while actually upgrading installed software is a change to the running system that deserves its own explicit step — conflating the two is exactly the beginner mistake of running `apt update` and expecting the system to now be current.
_What the interviewer is probing for:_ Precise understanding of the update/upgrade split, not just "I know you run both."

**🎯 Senior:** _"When would you use `apt full-upgrade` instead of `apt upgrade`, and what risk does it carry that plain `upgrade` doesn't?"_
**Model answer:** `apt upgrade` refuses to touch a package if satisfying its new version's dependencies would require removing some other currently-installed package — it just holds that package back and leaves everything else alone, which makes it safe to run close to unattended. `apt full-upgrade` (or `apt-get dist-upgrade`) removes that restraint entirely: it will remove or replace packages if that's what's needed to bring the system fully current, which is exactly the behavior needed for a distribution version upgrade or clearing a backlog of held-back packages, but it means a full-upgrade can legitimately walk away with something gone that was present before it ran. I wouldn't run `full-upgrade` unattended on a production host without reviewing what it proposes to remove first — the same discipline as reviewing a Terraform plan before applying it, treating the dry-run/prompt output as a gate rather than noise to click through.
_What the interviewer is probing for:_ Recognizing that `full-upgrade`'s power (removing packages) is also its operational risk, and that the right response is reviewing its plan, not avoiding it or running it blindly.

**🎯 Architect:** _"You're designing the provisioning pipeline for a Debian-family fleet. Where does dpkg fit, where does apt fit, and how do you keep automation from breaking when apt's output format changes across versions?"_
**Model answer:** dpkg stays in the picture only for the narrow case of installing a specific vendor-provided or internally-built `.deb` that isn't published to any repository the fleet trusts — and even then, I'd prefer `apt install ./file.deb` over a bare `dpkg -i` so dependency resolution still happens, falling back to `dpkg -i` plus `apt --fix-broken install` only when apt genuinely can't be used for that install. For everything sourced from a repository — which should be the overwhelming majority of packages on a well-run fleet — apt is the tool, driven through the provisioning system (Ansible's apt module, a golden-image build step) rather than ad hoc shell commands. For any automation that needs to query package state programmatically — checking installed versions, detecting what's upgradable — I'd standardize on `apt-cache`/`dpkg-query` with explicit format strings rather than parsing `apt`'s human-oriented output, specifically because apt's own documentation doesn't promise output stability across versions; that's a script silently breaking on some future distribution upgrade for a reason that has nothing to do with the actual task, and it's avoidable entirely by choosing the tool that documents a stable contract in the first place.
_What the interviewer is probing for:_ Correctly scoping dpkg's role to true edge cases, defaulting to apt-driven repository installs at fleet scale, and specifically anticipating the apt-output-stability trap in automation design rather than discovering it after a break.

## 10. Key Takeaways

- dpkg is the low-level tool — installs a local `.deb` directly (`-i`), removes (`-r`) or purges (`-P`) packages, lists installed packages (`-l`) and their files (`-L`), reverse-looks-up file ownership (`-S`) — but has no dependency resolution and no repository access at all.
- A `dpkg -i` on a `.deb` with unmet dependencies will install anyway and leave the system in a broken state — this is expected dpkg behavior, not a bug, and it's exactly why apt exists as the layer above it.
- `apt update` only refreshes the local repository index; it never installs or upgrades anything by itself — that's `apt upgrade`/`apt full-upgrade`, a separate, deliberate step.
- `apt upgrade` never removes packages to satisfy an upgrade (it holds them back instead); `apt full-upgrade`/`apt-get dist-upgrade` will remove packages if needed — real risk that deserves reviewing the proposed plan before confirming.
- `apt remove` keeps configuration files under `/etc/`; `apt purge` deletes them too — pick deliberately based on whether the package might come back.
- `apt` is the friendlier, unified interactive interface over the older `apt-get`/`apt-cache` split; its output format isn't guaranteed stable, so automation and scripts should use `apt-get`/`apt-cache` instead.
- A `.deb` file is an `ar` archive containing `debian-binary`, a `control` metadata member, and a `data` payload member — inspectable with `ar t`, `dpkg-deb -c`, and `dpkg-deb -e`.
- `apt --fix-broken install` (or `apt-get -f install`), paired with `dpkg --configure -a`, is the standard recovery path for a broken dependency or half-configured package state.

## 11. Related Concepts & What's Next

This section is the concrete Debian-family instance of the low-level/high-level tool layering §59 introduced generally — dpkg as the local, dependency-blind installer and apt/apt-get as the repository-aware resolver built on top of it. The repository configuration apt reads from (`/etc/apt/sources.list` and friends) and the GPG signing that secures it are only sketched here and get full treatment in §64. §61 (next) covers the RHEL-family parallel to this same layering — `rpm` as the low-level tool, `yum`/`dnf` as the high-level tool — worth reading back-to-back with this section to see where the two families' tooling philosophies converge and where they genuinely differ.

**Next Section:** §61 — `Section-61-Part8-RHEL-Tooling-Rpm-Yum-Dnf.md`
