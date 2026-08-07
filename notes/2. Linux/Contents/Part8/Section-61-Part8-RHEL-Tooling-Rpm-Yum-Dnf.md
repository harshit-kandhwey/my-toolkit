# Section 61 (Part 8): RHEL-Based Tooling: rpm, yum, dnf, .rpm Files

## 1. Overview: The Other Half of [§59](./Section-59-Part8-Package-Management-Concepts.md)'s Concepts

[§59](./Section-59-Part8-Package-Management-Concepts.md) laid out package management concepts in the abstract — repositories, dependency resolution, low-level vs. high-level tooling — and [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md) applied those concepts to the Debian family (`dpkg`/`apt`/`.deb`). This section applies the exact same concepts to the RHEL family: RHEL itself, CentOS, Rocky Linux, AlmaLinux, and Fedora. The architecture is structurally identical to Debian's, just with different names attached to each layer, which makes this section as much a translation exercise as a new topic.

> 💡 **Tip:** Hold [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)'s two-layer model in mind throughout: a **low-level tool** that installs a single local package file with no awareness of repositories or dependency resolution, and a **high-level tool** that wraps it, adds repository awareness, and resolves the full dependency graph. RHEL's low-level tool is `rpm`; its high-level tool is `dnf` (formerly `yum`). The division of labor is the same split as `dpkg`/`apt` — only the binary names change.

## 2. `rpm`: The Low-Level Tool

**`rpm`** (RPM Package Manager) is RHEL's direct structural equivalent to `dpkg` ([§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)): it installs, queries, verifies, and removes individual `.rpm` package files, and it does so with **no repository awareness and no dependency resolution** of its own. Point `rpm` at a local `.rpm` file and it will install exactly that file's contents — nothing more, nothing less.

**Core operations:**

```bash
rpm -i package.rpm          # install a new package from a local .rpm file
rpm -U package.rpm          # upgrade (or install if not already present)
rpm -e package-name         # erase (remove) an installed package
rpm -qa                     # list every installed package on the system
rpm -ql package-name        # list every file owned by an installed package
```

**Flag reference:**

| Flag         | Meaning                                                                                                                            |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `-i`         | Install — fails if the package (or a conflicting version) is already installed                                                     |
| `-U`         | Upgrade — installs if absent, upgrades in place if an older version is present; the flag used in practice far more often than `-i` |
| `-e`         | Erase — removes an installed package by name                                                                                       |
| `-q`         | Query mode — the prefix for all inspection subcommands (`-qa`, `-ql`, `-qi`, `-qf`)                                                |
| `-qa`        | Query all — list every package RPM believes is installed                                                                           |
| `-ql`        | Query list — list the files a given installed package owns                                                                         |
| `-qf <path>` | Query file — given a file path, report which installed package owns it (the reverse lookup of `-ql`)                               |
| `-v` / `-vv` | Increase verbosity — useful when a transaction fails and the default output doesn't say why                                        |
| `-h`         | Print hash marks (`#`) as progress during install/upgrade                                                                          |

**Example usage:**

```bash
$ rpm -i nginx-1.24.0-1.el9.x86_64.rpm
$ rpm -qa | grep nginx
nginx-1.24.0-1.el9.x86_64
$ rpm -ql nginx | head -5
/etc/nginx/nginx.conf
/etc/nginx/conf.d
/usr/sbin/nginx
/usr/lib/systemd/system/nginx.service
/var/log/nginx
```

> ⚠️ **Warning:** `rpm -i`/`-U` will refuse to install a package whose declared dependencies aren't already satisfied on the system — but refusing is the extent of its help. It does not go fetch the missing dependency from anywhere, because `rpm` has no concept of a repository to fetch from in the first place. Force past that check with `--nodeps` and the result is exactly what [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md) warned about for `dpkg --force-depends`: a package installed with unmet dependencies, silently broken until something else resolves them. This is the same "will leave a broken system" caveat as `dpkg`, for the same structural reason — the low-level tool's job ends at unpacking files and recording metadata, not at guaranteeing a working system.

**Production usage example:** `rpm -qa` is the fastest way to get a definitive, repository-independent answer to "is package X installed, and at what exact version" on a RHEL-family host — useful during an incident where you need ground truth on installed software without trusting whatever a configuration management tool's inventory claims. `rpm -qf` is the equally common reverse case: given a binary or config file found during an investigation, `rpm -qf /usr/sbin/nginx` immediately identifies which package dropped it there, which is often the fastest way to start a "where did this file come from" investigation.

## 3. `yum`: The Historical High-Level Tool

**`yum`** (Yellowdog Updater, Modified) is RHEL's historical high-level, dependency-resolving, repository-aware package manager — the direct structural equivalent to `apt` ([§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)). It wraps `rpm` the same way `apt` wraps `dpkg`: `yum` reads repository metadata, resolves the full dependency graph for a requested package, downloads everything needed, and hands the actual file installation off to `rpm` underneath.

```bash
yum install httpd           # resolve dependencies, download, and install
yum remove httpd            # remove a package and (optionally) its now-unneeded dependencies
yum update                  # update all installed packages to latest available versions
yum search httpd            # search repository metadata by name/description
```

For years, `yum` was simply _the_ RHEL-family package manager — the tool every administrator, script, and piece of documentation assumed. That's no longer the current state of affairs, and the reason why is 4.

## 4. `dnf`: Yum's Modern Successor

**`dnf`** (Dandified YUM) is `yum`'s successor and has been the default package manager on RHEL 8+, CentOS Stream, Rocky Linux, AlmaLinux, and Fedora for years now. It is not a competing project alongside `yum` — it's a rewrite that replaced it as the default, largely command-compatible with `yum`'s own syntax.

**What `dnf` actually improves on over `yum`:**

- **A better dependency resolution algorithm.** `dnf` uses a proper SAT-solver-based resolver (via `libsolv`), which handles complex dependency graphs — conflicting version requirements, multiple candidate packages satisfying the same requirement — more reliably than `yum`'s older resolution logic, which could get stuck or make suboptimal choices on complicated transactions.
- **Better performance**, particularly around repository metadata handling and memory usage during large transactions.
- **A cleaner, more maintainable codebase** with a documented, stable plugin/API surface — `yum`'s internals had accumulated years of organic growth that made it harder to extend safely.

**The "which one am I actually using" confusion — worth resolving explicitly:** On every modern RHEL-family system, `yum` is not a separate, independently maintained binary anymore — it is commonly just a symlink (or a thin compatibility wrapper) pointing at `dnf`. Typing `yum install httpd` on a RHEL 9 or Fedora host today invokes `dnf` underneath, with `yum`'s own command syntax accepted for backward compatibility. This is structurally the same situation as [§54](../Part7/Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)'s `iptables`-is-really-`nft` point: the command name an administrator or a decade-old runbook types is not necessarily the tool actually doing the work, and confirming that directly beats assuming from muscle memory.

```bash
readlink -f $(which yum)
# → .../dnf-3, or similar, on a modern host
```

> 💡 **Tip:** Because `dnf` is overwhelmingly command-compatible with `yum`, existing `yum`-based scripts, Ansible playbooks, and documentation largely keep working unmodified after a `yum` → `dnf` transition — which is a large part of why the migration was comparatively low-friction. Prefer typing `dnf` directly on any host where it's available, both to be explicit about what's actually running and because a handful of newer subcommands (5's `dnf history`, for one) either don't exist under the `yum` name at all or are less polished there.

## 5. Core `dnf` Commands

```bash
dnf install httpd                 # resolve dependencies, download, install
dnf remove httpd                  # remove a package
dnf update                        # update all installed packages
dnf update httpd                  # update a single package
dnf search httpd                  # search repository metadata by name/description
dnf info httpd                    # detailed metadata for a package (version, size, repo, description)
dnf list installed                # list every package dnf believes is installed
dnf history                       # list past transactions
dnf history undo <id>             # revert a specific past transaction
```

**Command reference:**

| Command                 | Purpose                                                                                  |
| ----------------------- | ---------------------------------------------------------------------------------------- |
| `dnf install <pkg>`     | Install a package and its dependencies from configured repositories                      |
| `dnf remove <pkg>`      | Remove a package                                                                         |
| `dnf update` (no args)  | Update every installed package to the latest available version                           |
| `dnf search <term>`     | Search repository name/description metadata                                              |
| `dnf info <pkg>`        | Show detailed metadata for a package, installed or available                             |
| `dnf list installed`    | List installed packages — the `dnf`-native equivalent of `rpm -qa`, but repository-aware |
| `dnf history`           | Review a log of past transactions (installs, removals, updates) with IDs                 |
| `dnf history undo <id>` | Roll back a specific past transaction, dependencies included                             |

**`dnf history` deserves particular attention** — it's a genuinely useful `dnf`-specific feature that `apt` doesn't have as clean an equivalent for. Every transaction `dnf` performs is logged with an ID, a timestamp, and the full set of packages it touched:

```bash
$ dnf history
ID     | Command line             | Date and time    | Action(s)  | Altered
-----------------------------------------------------------------------
   14   | update -y                | 2026-07-20 09:15 | Update     |    12
   13   | install httpd            | 2026-07-18 14:02 | Install    |     4
   12   | remove old-package       | 2026-07-15 11:30 | Removed    |     1

$ dnf history info 14        # what exactly did transaction 14 do
$ dnf history undo 14        # revert transaction 14 in full
```

**Production usage example:** After a `dnf update` on a host that starts misbehaving, `dnf history` lets you review exactly what changed in that transaction and, critically, **undo it as a single atomic operation** — rather than trying to manually figure out and reverse each individual package change. This is a meaningfully better incident-recovery story than `apt`'s equivalent workflow, which typically means reasoning about `/var/log/apt/history.log` by hand or pinning specific package versions manually.

## 6. `.rpm` File Structure

An `.rpm` file is a single archive combining **package metadata** and a **payload** (the actual files to be installed), built from a **spec file** — a text file declaring the package's name, version, dependencies, build steps, and file list, structurally the same role Debian's `debian/control` and `debian/rules` play together ([§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)). The payload portion is internally **cpio-based**, compressed, which is why low-level archive-inspection tools built for cpio can, in principle, peer inside an `.rpm` without needing `rpm` itself.

```bash
rpm -qpi package.rpm        # inspect metadata (name, version, deps) of a .rpm file without installing it
rpm -qpl package.rpm        # list the files a .rpm file would install, without installing it
```

Practically, package-building at this depth (writing a spec file, invoking `rpmbuild`) is out of scope here — [§63](./Section-63-Part8-Universal-Package-Formats-Snap-Flatpak-Appimage.md) (Part 8's build-from-source coverage) touches the adjacent "build software yourself" workflow, and full RPM packaging is a specialist skill beyond general RHEL administration.

## 7. Debian-Family vs. RHEL-Family: Direct Command Comparison

This is one of the most practically useful references for anyone who works across both families — the concepts ([§59](./Section-59-Part8-Package-Management-Concepts.md)) are identical, only the vocabulary differs:

| Task                               | Debian family ([§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)) | RHEL family                                                                                                                      |
| ---------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Install a local package file       | `dpkg -i package.deb`                                                        | `rpm -i package.rpm` (or `-U`)                                                                                                   |
| Remove a package                   | `dpkg -r package-name`                                                       | `rpm -e package-name`                                                                                                            |
| List installed packages            | `dpkg -l`                                                                    | `rpm -qa`                                                                                                                        |
| List a package's files             | `dpkg -L package-name`                                                       | `rpm -ql package-name`                                                                                                           |
| Find which package owns a file     | `dpkg -S /path/to/file`                                                      | `rpm -qf /path/to/file`                                                                                                          |
| Install with dependency resolution | `apt install pkg`                                                            | `dnf install pkg`                                                                                                                |
| Remove with dependency cleanup     | `apt remove pkg` / `apt autoremove`                                          | `dnf remove pkg` (autoremoves unneeded deps by default)                                                                          |
| Update all packages                | `apt update && apt upgrade`                                                  | `dnf update`                                                                                                                     |
| Search repository metadata         | `apt search term`                                                            | `dnf search term`                                                                                                                |
| Show package details               | `apt show pkg`                                                               | `dnf info pkg`                                                                                                                   |
| Fix a broken dependency state      | `apt --fix-broken install`                                                   | `dnf` largely avoids this class of failure via its resolver; `rpm -Va` verifies installed package integrity as the closer analog |
| Review/undo past transactions      | No clean equivalent — `/var/log/apt/history.log` by hand                     | `dnf history` / `dnf history undo <id>` (5)                                                                                      |

> 💡 **Tip:** `apt update` and `dnf update` look identical but mean different things — worth calling out explicitly since it's a frequent source of cross-family confusion. `apt update` only refreshes local repository metadata ([§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)); the package-upgrade step is a separate `apt upgrade`. `dnf update` with no arguments does both at once — it refreshes metadata _and_ upgrades every installed package in a single command. There is no `dnf`-native "refresh metadata only, don't upgrade anything" split the way `apt update`/`apt upgrade` are split (`dnf check-update` comes closest, as a read-only check).

## 8. Common Misconceptions

1. **"`yum` and `dnf` are two different package managers I need to choose between."** On any modern RHEL-family host, they're not competing options — `yum` is a compatibility name pointing at `dnf` underneath (4). There's no meaningful choice to make; type either and expect `dnf`'s resolver and behavior.
2. **"`rpm -i` on a `.rpm` file will fetch whatever dependencies it needs, like `dnf install` would."** `rpm` has no repository awareness at all — it only unpacks the file it's given and checks (not fetches) whether declared dependencies are already present (2). Confusing `rpm`'s and `dnf`'s scope is the single most common RHEL-family package management mistake.
3. **"`dnf update` just refreshes the package list, same as `apt update`."** They're not equivalent — `dnf update` with no arguments refreshes metadata _and_ performs the actual upgrade in one step, unlike `apt`'s explicit two-command split (7).
4. **"Since `dnf` is command-compatible with `yum`, there's no reason to ever type `dnf` directly."** Compatibility covers the common surface, not everything — some newer functionality (`dnf history`'s full feature set among it) is `dnf`-native and either missing or less complete under the `yum` compatibility name. Typing `dnf` directly is also simply more accurate about what's actually running (4).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `rpm` and `dnf`?"_
**Model answer:** `rpm` is the low-level tool — it installs, queries, and removes individual `.rpm` package files directly, with no awareness of repositories and no dependency resolution beyond checking (not fetching) whether required dependencies are already present. `dnf` is the high-level tool that wraps `rpm` — it's repository-aware, resolves the full dependency graph for a requested package, downloads everything needed, and hands the actual file installation to `rpm` underneath. The relationship is structurally identical to `dpkg`/`apt` on Debian-family systems, just with different names.
_What the interviewer is probing for:_ Correctly identifying the two-layer architecture rather than treating `rpm`/`yum`/`dnf` as three interchangeable tools with no structural distinction.

**🎯 Intermediate:** _"On a modern RHEL 9 host, what actually happens when someone types `yum install httpd`?"_
**Model answer:** `yum` isn't an independently maintained binary on modern RHEL-family systems anymore — it's commonly a symlink or thin compatibility wrapper pointing at `dnf`. So typing `yum install httpd` invokes `dnf`'s resolver and transaction logic underneath, with `yum`'s command syntax accepted for backward compatibility with existing scripts and muscle memory. It's the same situation as `iptables` frequently being a compatibility layer over `nft` — the command name typed isn't necessarily the tool actually doing the work, and `readlink -f $(which yum)` confirms it directly rather than assuming.
_What the interviewer is probing for:_ Awareness that command names and actual implementations can diverge, and the habit of verifying rather than assuming — a recurring theme across this knowledge base's tooling sections.

**🎯 Senior:** _"A `dnf update` on a production host caused a service to start misbehaving. How do you diagnose and recover?"_
**Model answer:** First, `dnf history` to see exactly what that transaction touched — package names, versions before and after, and how many packages were altered — rather than guessing from memory or logs. `dnf history info <id>` gives the full detail on that specific transaction. If the update is the confirmed cause, `dnf history undo <id>` reverts it as a single atomic operation, dependencies included, which is materially cleaner than the Debian-family equivalent of manually reasoning through `/var/log/apt/history.log` and reinstalling specific package versions by hand. Before undoing anything on a production host, I'd also cross-check `rpm -qa --last` for a quick chronological view of exactly what changed and when, as a second confirmation source independent of `dnf`'s own transaction log.
_What the interviewer is probing for:_ Concrete familiarity with `dnf history` as an operational recovery tool, not just as a listed feature — and instinct to cross-verify rather than trust a single source during an incident.

**🎯 Architect:** _"You're standardizing operational runbooks across a fleet that includes both Debian-family and RHEL-family hosts. How do you approach writing package-management procedures that work across both?"_
**Model answer:** I'd lean on the fact that the underlying concepts ([§59](./Section-59-Part8-Package-Management-Concepts.md)) are identical across both families — repositories, dependency resolution, a low-level/high-level tool split — and build runbooks around that shared model rather than writing family-specific procedures from scratch. Concretely, I'd maintain a translation table (7) as a first-class artifact, not tribal knowledge — install, remove, update, search, list-installed, show-info, and transaction-history/rollback all have a direct equivalent on both sides, with `dnf history` being the one place RHEL genuinely has a cleaner story than Debian's manual log-reading approach, worth calling out explicitly in the runbook rather than pretending the two are perfectly symmetric. I'd also bake in the verification habits from both families into any automation — confirming `yum` actually resolves to `dnf` before relying on `dnf`-specific behavior, and never assuming `rpm -i`/`dpkg -i` alone is sufficient for anything beyond a single already-satisfied local package install. The goal is one mental model with two vocabularies, documented as such, rather than two disconnected sets of tribal knowledge that drift apart over time.
_What the interviewer is probing for:_ Ability to operate at the concept level across ecosystems rather than memorizing two disconnected command sets, and to translate that into durable, fleet-wide documentation rather than ad hoc per-incident knowledge.

## 10. Key Takeaways

- `rpm` is RHEL's low-level package tool, the direct structural equivalent of `dpkg` — installs a local `.rpm` file, no repository awareness, no dependency fetching, and forcing past unmet dependencies (`--nodeps`) leaves a broken system exactly as `dpkg --force-depends` does.
- `yum` was RHEL's historical high-level, repository-aware, dependency-resolving tool — the direct equivalent of `apt` — wrapping `rpm` the same way `apt` wraps `dpkg`.
- `dnf` is `yum`'s modern successor, default on RHEL 8+/Fedora for years now, with a genuinely better SAT-solver-based dependency resolver and better performance; `yum` is commonly just a symlink to `dnf` on modern systems, so confirm with `readlink -f $(which yum)` rather than assuming.
- `dnf history` / `dnf history undo <id>` is a genuinely useful `dnf`-specific feature for reviewing and atomically reverting past transactions — a cleaner story than `apt`'s manual log-based equivalent.
- `.rpm` files are spec-file-built archives combining metadata and a cpio-based payload — structurally parallel to `.deb`'s `control`/`data` archive pair from [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md).
- The Debian-family/RHEL-family command mapping (7) — install, remove, update, search, list-installed, show-info, transaction-history — is one of the most practically useful references for anyone operating across both ecosystems.

## 11. Related Concepts & What's Next

This section applies [§59](./Section-59-Part8-Package-Management-Concepts.md)'s package management concepts to the RHEL family exactly as [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md) applied them to the Debian family, and the two sections are designed to be read as a pair — the comparison table in 7 only lands fully with [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)'s Debian-side detail in view. [§54](../Part7/Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)'s `iptables`-is-really-`nft` pattern reappears here in `yum`-is-really-`dnf` (4), reinforcing a recurring theme: confirm what a command name actually invokes rather than trusting muscle memory. [§64](./Section-64-Part8-Managing-Repositories-GPG-Signing-Keys.md), later in this Part, goes deeper on managing repositories and GPG signing keys — the `yum`/`dnf` repository files (`/etc/yum.repos.d/`) and package-signature verification this section deliberately left unexpanded.

**Next Section:** [§62](./Section-62-Part8-Building-From-Source.md) — `Section-62-Part8-Building-From-Source.md`
