# Section 113 (Part 15): Version and Distribution Differences That Matter (init Systems, Package Managers, Kernel Versions)

## 1. Why "Linux Is Linux" Is a Dangerous Assumption

§112 covered mistakes an administrator makes regardless of which distribution or version they happen to be running. This section covers the other class of trap: differences that are entirely correct on the specific system where they were learned, and entirely wrong the moment that knowledge is applied — unexamined — to a different distribution, version, or install base. This is a genuinely common failure mode precisely because it doesn't feel like a mistake in the moment: the command worked the last ten times, on the last ten hosts, so there's no obvious reason to suspect the eleventh host is different — until it is.

This section consolidates differences already introduced individually throughout Parts 1–14 into one practical reference, organized by the categories that actually bite in real administration.

## 2. init System Differences

§13 (Part 2) covered SysVinit, Upstart, and systemd in architectural depth. The practical consequence worth restating here: a runbook or automation script written assuming `systemctl restart servicename` will simply fail — not with a helpful error pointing at the real cause, but with "command not found" or worse, silent no-op behavior — on an old SysVinit host where the equivalent action is `service servicename restart` or a direct `/etc/init.d/servicename restart` invocation.

This isn't a hypothetical concern for a roadmap this focused on production operations: inherited fleets, older acquired infrastructure, and long-lived legacy hosts that were never migrated forward are a real and common category of system an administrator encounters. §13's hands-on check (`ps -p 1 -o comm=`, `readlink /sbin/init`) exists specifically because assuming systemd from the distribution name or version alone is unsafe — the only reliable answer comes from checking the running host directly.

## 3. Package Manager Differences

§60/§61 (Part 8) laid out the dpkg/apt vs. rpm/dnf comparison table in detail. The practical consequence for automation: a script hardcoded around `apt-get install -y packagename` will not work unmodified against an RHEL-family host expecting `dnf install -y packagename`, and the reverse is equally true. The package names themselves frequently differ too, not just the manager invoking them — the same software may be packaged under a different name, with different dependency splitting, across the two families.

There are two legitimate ways to handle this, and "write two separate scripts and remember to run the right one" is not one of them in any fleet of meaningful size:

- **Make automation distro-aware** — detect the package manager or distribution family at runtime and branch accordingly.
- **Use a configuration management tool's package abstraction layer** (§97, §98) instead of raw package-manager commands — most configuration management tools expose a package resource that maps to the correct underlying manager automatically, which is the more maintainable choice for anything beyond a one-off script.

## 4. Kernel Version Differences

Kernel version matters beyond just "newer is generally better," and the practical tension is worth naming directly rather than glossing over:

- **Newer kernels bring real capability gains** — more mature cgroups v2 support (relevant to the containers coverage in §101's area of Part 13), newer filesystem features, and security mitigations for vulnerability classes that simply didn't exist as concerns when an older kernel shipped.
- **"Always run the latest kernel" is in real tension with enterprise stability requirements.** §94's patch management coverage and §103's enterprise distribution support model both point at the same underlying reality: many organizations deliberately pin to an older, extensively-tested kernel version precisely because the newest kernel, however capable, hasn't accumulated the same track record of production stability — and an untested kernel upgrade introduces its own risk on a fleet where uptime matters more than having the newest feature set.

Neither position is universally correct — the right answer depends on what the specific workload actually needs from a newer kernel weighed against the organization's tolerance for the instability risk of being an early adopter of that kernel version in production.

## 5. Default Shell and Tool Differences

- **`/bin/sh` is not always bash.** §41's warning bears repeating in this consolidated context: Debian and Ubuntu link `/bin/sh` to `dash`, a smaller, faster, POSIX-focused shell that does not support bash-specific extensions (arrays, `[[ ]]` test syntax, certain parameter expansions). A script with a `#!/bin/sh` shebang that actually relies on bash-only syntax will fail, sometimes silently in confusing ways, specifically on Debian-family systems where this substitution is the default — and work fine on a system where `/bin/sh` happens to be bash.
- **`ip` vs. `ifconfig`, and their replacements generally, vary by distribution age.** A minimal or older image may still default to legacy networking tools where a newer one ships only the modern replacement, or vice versa — §114 (next) covers this specific family of differences in full reference-table depth.

## 6. Why This Matters in Practice

The unifying practical point across every difference above: writing genuinely portable automation or documentation means choosing one of two disciplines, not assuming "Linux is Linux" and being surprised in production:

1. **Test across the actual distribution/version matrix the organization actually runs** — not a single representative host, but every combination that exists in the real fleet, including inherited legacy systems.
2. **Deliberately abstract behind a tool that hides the differences** — configuration management's package/service resource abstractions, or containers (§99, §100) that bundle a known, consistent userland regardless of what the underlying host is running.

The failure mode this section exists to prevent is the third, unstated option: writing something once against whatever system happens to be on hand, and discovering the gap only when it's run against a different host in production.

> 💡 **Tip:** When inheriting documentation or automation of unknown provenance, treat any command that assumes a specific init system, package manager, or shell as a hypothesis about the target host, not a fact — verify against the actual host (§13's `ps -p 1 -o comm=` pattern generalizes well beyond just init systems) before trusting it at scale.

## 7. Quick-Reference: Where Assumptions Break

| Assumption Carried From One System              | Breaks On                                   | Section Ref |
| ----------------------------------------------- | ------------------------------------------- | ----------- |
| `systemctl restart svc` works everywhere        | Old SysVinit/Upstart hosts                  | §13         |
| `apt-get install pkg` works everywhere          | RHEL-family hosts (needs `dnf`)             | §60/§61     |
| `#!/bin/sh` scripts can use bash arrays/`[[ ]]` | Debian/Ubuntu (`/bin/sh` → `dash`)          | §41         |
| Latest kernel is always the safe default        | Enterprises pinning to a tested LTS kernel  | §94, §103   |
| `ifconfig`/`route`/`arp` present by default     | Minimal or newer images shipping only `ip`  | §52, §114   |
| Package names match across families             | Software split/named differently per family | §60/§61     |

## 8. Worked Scenario: A Runbook That Fails on the Eleventh Host

An administrator writes a remediation runbook after resolving an incident on a fleet of ten hosts, all running the same Ubuntu LTS image — `systemctl restart appsvc`, followed by `apt-get install -y diagnostic-tool` if a supporting package is missing. The runbook works cleanly the first ten times it's used, because all ten hosts share the same init system, package manager, and shell defaults.

The eleventh host is a long-lived RHEL server, acquired through a company merger years earlier and never migrated onto the standard image. `apt-get` doesn't exist there at all — the runbook's second step fails immediately with "command not found," at exactly the moment an on-call engineer is following it under incident pressure, with no fallback instructions for what to do instead. If that host had also still been running SysVinit rather than systemd (not this scenario, but a realistic one for sufficiently old inherited infrastructure per §13), the first step would have failed too, but potentially less obviously — some wrapper scripts silently no-op on an unrecognized command rather than erroring loudly, which is a worse failure mode because it looks like success.

The fix isn't to abandon runbooks — it's to write them either explicitly scoped to a known, verified distribution/version matrix ("this runbook applies to Ubuntu 20.04/22.04 LTS hosts only — verify with `cat /etc/os-release` before proceeding"), or to route the remediation through a configuration management tool's package/service abstraction so the same declared action resolves correctly regardless of which family the target host belongs to (3). A runbook that silently assumes uniformity is a runbook that fails exactly when it's needed most — on the one host that doesn't match the assumption, discovered live during an incident rather than caught ahead of time.

## 9. Common Misconceptions

1. **"A script that works on Ubuntu will work the same way on any Linux system."** Package manager, default shell, and init system can all differ enough to break an unexamined assumption — "Linux" is a kernel plus a userland that varies meaningfully across distributions and versions, not a single fixed environment.
2. **"Newer kernel version is always strictly better."** It's better along some axes (features, security mitigations) and worse along others in an organization that hasn't yet built confidence in that specific version's production stability — §94 and §103's tension between "patch aggressively" and "stability through conservative version pinning" applies directly here.
3. **"`/bin/sh` is just an alias for bash on every distribution."** It resolves to `dash` by default on Debian/Ubuntu specifically — a script relying on bash-only syntax under a `#!/bin/sh` shebang is a latent, distro-specific bug (§41).
4. **"Once a fleet standardizes on one distribution, version differences stop mattering."** Even within a single distribution family, a kernel or userland-tool version gap between an older host and a freshly provisioned one can reproduce the same class of surprise — standardizing on a distribution reduces this risk but doesn't eliminate it across versions.

## 10. Tiered Interview Questions

**🎯 Beginner:** _"Why might a shell script that starts with `#!/bin/sh` behave differently on Ubuntu than on a system where `/bin/sh` is bash?"_
**Model answer:** On Debian and Ubuntu, `/bin/sh` is linked to `dash`, a smaller POSIX-focused shell, not bash — so any bash-specific syntax in the script (arrays, `[[ ]]` test expressions, certain parameter expansions) will fail or behave unexpectedly under `dash` even though the same script runs fine on a system where `/bin/sh` happens to point at bash (§41). The fix is either writing genuinely POSIX-compliant `sh` syntax, or explicitly using `#!/bin/bash` when bash features are actually needed.
_What the interviewer is probing for:_ Awareness that shebang lines are a promise about required syntax, not just a formality, and that `/bin/sh` isn't a universal bash alias.

**🎯 Intermediate:** _"Your team wants one automation script that installs a package across both Debian-family and RHEL-family hosts. How do you approach it?"_
**Model answer:** I'd avoid hardcoding a single package manager invocation and instead either detect the distribution family at runtime (checking `/etc/os-release` or the presence of `apt`/`dnf`) and branch the install logic accordingly, or — the more maintainable option for anything beyond a one-off script — use a configuration management tool's package resource abstraction (§97, §98), which already maps a declared package name to the correct underlying manager and handles the cross-family package-naming differences that raw scripting would otherwise need to hardcode manually.
_What the interviewer is probing for:_ Preference for the more maintainable abstraction-layer approach over ad hoc runtime branching when the tooling is already available, while still understanding the branching approach as a valid fallback.

**🎯 Senior:** _"An organization insists on always running the absolute latest stable kernel release for security reasons. What pushback or nuance would you offer?"_
**Model answer:** The instinct is defensible — newer kernels do carry real security mitigations and capability improvements — but "latest" and "safest" aren't synonymous in production. A kernel version with a shorter production track record carries its own risk: an untested regression or an unexpected interaction with existing workloads can cause an outage that a more conservative, extensively-vetted version wouldn't have. §94's patch management and §103's enterprise-support model both point at organizations deliberately choosing a well-tested, often slightly older kernel precisely for this reason. I'd frame it as a genuine trade-off rather than a solved question — for workloads where a newer kernel provides a mitigation against an active, relevant threat, moving quickly might be worth the risk; for a stability-critical workload with no specific unmet need, a conservative, well-tested version pinned through the organization's normal patch cadence is often the better call.
_What the interviewer is probing for:_ Ability to push back thoughtfully on an oversimplified security argument without dismissing the underlying concern, and to frame the kernel-version decision as workload-specific rather than universal.

**🎯 Architect:** _"You're consolidating a newly-acquired company's infrastructure into your existing fleet, and their hosts span multiple distributions, several kernel versions, and at least one host still on SysVinit. What's your integration strategy?"_
**Model answer:** I'd start with an inventory pass using the ground-truth checks this roadmap already established rather than trusting any inherited documentation — §13's `ps -p 1 -o comm=`/`readlink /sbin/init` for init system, `/etc/os-release` and package-manager presence for distribution family, and kernel version directly from `uname -r`, run across every inherited host. That inventory determines the actual matrix I need to support, not an assumed one. For automation and runbooks going forward, I'd push toward the abstraction-layer approach (2) — bringing every inherited host under the same configuration management tooling used across the existing fleet, so that future changes are expressed once, declaratively, and resolve correctly regardless of the underlying distribution or init system differences. Any host that can't be brought under that abstraction in the short term (the SysVinit host, most likely, given how much more its operational model differs) gets explicitly flagged and excluded from any automation that assumes systemd, with its own interim runbook until it can be migrated or decommissioned — rather than either blocking the whole consolidation on that one host, or silently assuming it behaves like the rest of the fleet and finding out otherwise during an incident.
_What the interviewer is probing for:_ Fleet-integration discipline that starts from verified ground truth rather than assumed uniformity, and a clear plan for handling the genuinely incompatible outlier rather than pretending it isn't there.

## 11. Key Takeaways

- init system differences (§13) mean a systemd-assuming runbook can fail outright against an inherited SysVinit host — verify with `ps -p 1 -o comm=` rather than assuming from the distro label.
- Package manager differences (§60/§61) mean automation should either be distro-aware or route through a configuration management tool's abstraction layer rather than hardcoding raw `apt`/`dnf` commands.
- Kernel version differences carry a genuine trade-off between "latest for security/features" and "older, proven, for stability" (§94, §103) — there's no universally correct default.
- `/bin/sh` resolving to `dash` on Debian-family systems (§41), and `ip` vs. `ifconfig` availability varying by distro age, are concrete, recurring sources of scripts that work "everywhere I tested" and fail on the host that wasn't tested.
- The practical fix is either testing across the real distro/version matrix in use, or abstracting behind configuration management or containers deliberately — not assuming uniformity and discovering the gap in production.

## 12. Related Concepts & What's Next

This section consolidates init system differences from §13 (Part 2), distro family distinctions from §5 (Part 1), package management from §59–§64 (Part 8, particularly §60/§61's dpkg/apt vs. rpm/dnf comparison), and kernel/stability tension from §94 and §103 (Parts 12 and 14). §114 (next) is the natural companion to this section — a table-heavy reference of specifically deprecated tools and their modern replacements, several of which (init systems, `ifconfig`/`ip`) were introduced here as version/distribution differences and get their full side-by-side treatment there.

**Next Section:** §114 — `Section-114-Part15-Deprecated-Tools-Modern-Replacements.md`
