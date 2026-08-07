# Section 70 (Part 9): Runlevels/Targets and System State Transitions

## 1. Overview: The Promised Deep Dive

[§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) introduced targets conceptually — named synchronization points that generalize SysVinit's runlevels into a dependency graph — and explicitly deferred the operational half of that story here: "how does a running system actually move from one target to another, on purpose, and how does that differ from a runlevel switch." [§66](./Section-66-Part9-Managing-Services-Systemctl.md) then gave `systemctl` as the general operational tool for units. This section is where those two threads converge on one specific question: **system-state transitions** — what the standard targets are, how they map onto the SysVinit runlevels an inherited fleet or muscle memory might still reference, how to change the boot-time default, how to change the _currently running_ state without touching that default, and the two real degraded-mode troubleshooting states (rescue and emergency) every SRE eventually needs under pressure.

## 2. The Standard Targets and Their Runlevel Equivalents

[§13](../Part2/Section-13-Part2-Init-Systems.md) covered SysVinit's 0–6 runlevel numbering only as history. Because a large amount of operational vocabulary, documentation, and older automation still speaks in runlevel numbers, systemd ships **runlevel-compatibility targets** — actual `.target` units, several of them symlinks to a "real" target — so that both languages resolve to the same running state:

| SysVinit Runlevel | systemd Target         | Meaning                                                                                                            |
| ----------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| 0                 | `poweroff.target`      | Halt and power off the system                                                                                      |
| 1                 | `rescue.target`        | Single-user / rescue mode — minimal services, root shell (5)                                                       |
| 2, 4              | (no direct equivalent) | Debian/RHEL-specific multi-user variants — generally treated as aliases of runlevel 3 on most modern distributions |
| 3                 | `multi-user.target`    | Full non-graphical multi-user system — networking, services, no display                                            |
| 5                 | `graphical.target`     | Multi-user system plus a display manager / graphical login                                                         |
| 6                 | `reboot.target`        | Reboot the system                                                                                                  |
| _(none)_          | `emergency.target`     | Bare-minimum recovery state — no SysVinit runlevel maps to this at all (5)                                         |

The runlevel numbers themselves still work as a typing convenience — `systemctl isolate runlevel3.target` is accepted because `runlevel3.target` is shipped as a symlink to `multi-user.target` — but that compatibility layer is a courtesy for muscle memory, not evidence that targets and runlevels are the same mechanism underneath. They aren't, and 3 is where that stops being cosmetic.

> 💡 **Tip:** `systemctl list-units --type=target` shows every target currently active on a live system — a fast way to confirm which of these compatibility symlinks are actually in play before assuming a runlevel number means what it historically meant.

## 3. The Real Difference: A Dependency Chain, Not a Flat List

[§13](../Part2/Section-13-Part2-Init-Systems.md) flagged this as a misconception worth correcting and [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) built the general dependency-directive vocabulary (`Requires=`/`Wants=`/`After=`) that makes the correction concrete here. SysVinit's runlevels are **mutually exclusive, flat, numbered states** — a system is in exactly one of 0 through 6, and nothing about runlevel 3 declares any relationship to runlevel 1 beyond an implicit "higher number, more services" convention with no machine-checkable meaning.

`graphical.target` is not a flat, self-contained state — it is the top of a genuine **dependency chain**, each link built from the ordinary `Requires=`/`After=` directives [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) covered:

```
graphical.target
      │  Requires= / After=
      ▼
multi-user.target
      │  Requires= / After=
      ▼
basic.target
      │  Requires= / After=
      ▼
sysinit.target
```

Reaching `graphical.target` means systemd resolves this entire chain: `sysinit.target` (early boot — mounting filesystems, activating swap, setting up the kernel-level basics) must be reached before `basic.target` (core system readiness — sockets, timers, path units, the generic infrastructure most services assume exists) can be reached, which must be reached before `multi-user.target` (the full non-graphical service set) can be reached, which must be reached before `graphical.target` layers a display manager on top. Every unit that declares `WantedBy=multi-user.target` gets pulled in as part of reaching that link in the chain — and because `graphical.target` requires `multi-user.target`, it transitively pulls in everything `multi-user.target` pulls in too, without `graphical.target` needing to enumerate any of it directly.

This has a concrete operational consequence SysVinit had no way to express: asking "is this system 'at least' multi-user-ready" is a meaningful, checkable question under systemd (is `multi-user.target` active, regardless of whether `graphical.target` ever gets reached on top of it), whereas under SysVinit, runlevel 5 was simply a _different_, independently-defined script set from runlevel 3 — not provably a superset of it.

## 4. Changing the Default Target

The **default target** is what a normal boot reaches without any manual intervention — the systemd equivalent of `/etc/inittab`'s `initdefault` line from the SysVinit era.

**Viewing the current default:**

```bash
systemctl get-default
```

**Setting a new default:**

```bash
sudo systemctl set-default multi-user.target
```

Mechanically, `set-default` does exactly one thing: it replaces the symlink `/etc/systemd/system/default.target` so that it points at the requested target file (e.g., `/usr/lib/systemd/system/multi-user.target`). On boot, systemd's earliest job is resolving `default.target` — whatever it points to at that moment is the state the system attempts to reach. A headless server running unnecessary display-manager overhead is the textbook case for setting `multi-user.target` as default instead of a distribution's `graphical.target` default; a workstation image is the reverse.

> 💡 **Tip:** `set-default` only changes what happens on the _next_ boot — it has no effect on the currently running target. Conflating the two is a common mistake and is exactly what 5 exists to separate.

## 5. Isolating the Current Target Without Changing the Default

Changing the boot-time default (4) is a persistent, future-boot decision. Moving the **currently running** system to a different target right now, without altering what the next boot will do, is a different operation entirely — and systemd deliberately gives it a different verb:

```bash
sudo systemctl isolate rescue.target
```

**Why "isolate" and not "switch" or "set":** the name is precise, not arbitrary. `isolate` tells systemd to activate the named target _and stop every currently running unit that is not a dependency of that target_ — it isolates the system down to exactly the unit set the target requires, tearing down everything else. This is a genuinely different mental model from SysVinit's runlevel switch, which just ran a different set of start/stop scripts for the new numbered state without any equivalent notion of "prove each currently-running thing is actually still wanted, and stop it if not."

> ⚠️ **Warning:** `isolate` stopping non-required units is the entire point of the command, but it is also the single easiest way to take down something unexpectedly. `systemctl isolate multi-user.target` on a system currently running `graphical.target` will stop the display manager and every unit that only the graphical layer wanted — correct if that's the intent, a nasty surprise on a workstation someone is actively using if it isn't. Before isolating on a live production host, check what's actually running (`systemctl list-units --state=running`) and what the target dependency chain (3) will keep versus drop — `systemctl show <target> -p Requires -p Wants` shows exactly what a given target considers required, before committing to the isolate.

`isolate` is exactly what runlevel-compatibility symlinks (2) are typed against in practice — `systemctl isolate rescue.target` is functionally what an administrator reaching for the old habit of `init 1` is actually trying to accomplish, and systemd accepts `systemctl isolate 1` as a courtesy alias for the same operation.

## 6. Rescue Mode vs. Emergency Mode

Both are troubleshooting states, and both are frequently confused for "the same thing at different depths" — they're closer to two distinct tools for two distinct severities of broken system.

**`rescue.target` (rescue mode):** a mostly-normal system. The root filesystem and other local filesystems from `/etc/fstab` are mounted read-write, basic system services are up, and the administrator gets a root shell. This is the correct target for the common case of "a specific service or unit is broken and I need to fix it with the rest of the system otherwise intact and usable" — networking, storage, and a normal shell environment are all still available to actually do the repair work.

**`emergency.target` (emergency mode):** a genuinely bare minimum. The root filesystem is mounted **read-only**, essentially nothing beyond a root shell and the most fundamental kernel-level setup is started, and no other filesystems are mounted at all. This exists for the case rescue mode itself can't handle — a corrupted or unmountable filesystem, a `fstab` entry so broken that even rescue mode's normal mount pass fails, or any situation broken enough that starting rescue mode's fuller unit set is itself unsafe or impossible. Because the root filesystem starts read-only, the first action inside emergency mode is frequently remounting it read-write deliberately (`mount -o remount,rw /`) once the administrator has confirmed it's safe to write to.

The practical decision rule: reach for `rescue.target` first for "something specific is broken and I need a working system to fix it from"; drop to `emergency.target` only when rescue mode itself is unreachable or unsafe, or when the problem is suspected to be at the filesystem level rather than at the service level.

## 7. Boot-Time Target Selection via Kernel Command Line

Everything in 5 and 6 assumes the system is already up enough to run `systemctl`. When a system won't reach a usable state on its own — a broken unit wedged into the default target's dependency chain, for instance — the target can be selected **before systemd's normal startup sequence runs at all**, by passing it as a kernel boot parameter.

At the GRUB boot menu, editing the kernel command line (typically `e` to edit the selected entry, locating the line starting with `linux` or `linux16`) and appending:

```
systemd.unit=rescue.target
```

tells the kernel to hand systemd `rescue.target` as its startup goal directly, overriding whatever `default.target` (4) is configured to point at for this one boot only — nothing is written to disk, and the next normal boot reverts to the configured default. `systemd.unit=emergency.target` works identically for the more severe case in 6. This is the real recovery technique for "the configured default target won't come up cleanly" — rather than trying to fix a broken unit blind from a system that won't finish booting, boot straight into a minimal, working state, diagnose from there with normal shell tools, and only then decide whether the actual fix belongs in the unit file, the default target, or somewhere else entirely.

> 💡 **Tip:** This is the direct practical payoff of `isolate` (5) framed as a boot-time operation instead of a live one — `systemd.unit=` is answering the same "what target should systemd try to reach" question, just asked before systemd has started rather than after.

## 8. Common Misconceptions

1. **"`systemctl set-default` changes what the system is running right now."** It only changes what the _next_ boot targets, by repointing the `default.target` symlink (4) — the currently running target is untouched until the next reboot, or until an explicit `isolate` (5) is run.
2. **"`isolate` is just systemd's word for `switch`."** The name reflects real, distinct behavior — `isolate` stops every unit not required by the target being isolated to, not just starts the new target's units alongside whatever was already running (5). This is a meaningfully different, and meaningfully riskier, operation than SysVinit's runlevel switch.
3. **"Rescue and emergency mode are the same thing, just named differently."** Rescue mode is a mostly-functional system with basic services and a read-write root filesystem, suitable for fixing a broken service with normal tools available; emergency mode is a bare-minimum, read-only-root state for when the system is too broken for even rescue mode to come up safely (6) — reaching for the wrong one wastes recovery time.
4. **"Runlevel numbers are just cosmetic history systemd doesn't actually support."** The compatibility symlinks (`runlevel3.target` → `multi-user.target`, etc.) genuinely work and are accepted by `systemctl isolate` and boot parameters alike (2) — they're a real, functioning courtesy layer, not a removed feature.
5. **"`graphical.target` and `multi-user.target` are two independent, parallel states, like runlevel 3 and 5 were."** `graphical.target` depends on `multi-user.target` and transitively includes everything it pulls in — a real dependency chain (3), not two independently-defined script sets that happen to be numbered differently.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What SysVinit runlevel does `multi-user.target` correspond to, and what does `graphical.target` add on top of it?"_
**Model answer:** `multi-user.target` corresponds to runlevel 3 — a full non-graphical multi-user system with networking and services but no display manager. `graphical.target` corresponds to runlevel 5 and adds a display-manager layer on top by depending on `multi-user.target` — reaching it means reaching `multi-user.target` first, then starting the graphical login layer, rather than being an independently defined state.
_What the interviewer is probing for:_ Basic familiarity with the mapping table and the fact that `graphical.target` builds on `multi-user.target` rather than existing beside it.

**🎯 Intermediate:** _"What's the difference between `systemctl set-default graphical.target` and `systemctl isolate graphical.target`, and when would you use each?"_
**Model answer:** `set-default` only changes the boot-time default by repointing the `default.target` symlink — it has no effect on the currently running state, and the change only takes effect on the next boot. `isolate` changes the _currently running_ state right now, activating the named target and stopping every unit not required by it, without touching what the next boot will do. I'd use `set-default` for a persistent policy change — this host should always boot graphical from now on — and `isolate` for an immediate, one-off state change, like dropping to rescue mode right now to fix something without rebooting or committing to that as the new permanent default.
_What the interviewer is probing for:_ Clean separation of the persistent-default-vs-current-state distinction, which is the most commonly conflated pair of operations in this area.

**🎯 Senior:** _"A teammate ran `systemctl isolate multi-user.target` on a production workstation to try to free up some resources, and now several things they didn't expect are down. What happened, and how would you have approached it differently?"_
**Model answer:** `isolate` doesn't just start `multi-user.target` — it stops every currently running unit that isn't a dependency of `multi-user.target`. If the system was previously at `graphical.target`, that target's entire dependency chain beyond `multi-user.target` — the display manager and anything only the graphical layer wanted — gets torn down, along with any unit that happened to be running outside that chain entirely (something started manually or via a different target). That's the intended behavior of `isolate`, not a bug, but it's easy to trigger without realizing the blast radius. Before running an isolate on a live host, I'd check `systemctl list-units --state=running` for what's actually up, and `systemctl show <target> -p Requires -p Wants` for what the target being isolated to actually keeps, so the set of things about to be stopped is known in advance rather than discovered after the fact. If the actual goal was narrower — stop one specific unnecessary service — a targeted `systemctl stop` on that unit is the correct tool; `isolate` should be reserved for genuinely wanting to move the whole running state to a different target.
_What the interviewer is probing for:_ Real understanding of `isolate`'s stop-everything-not-required semantics as a production risk, not just definitional knowledge, and the instinct to check before running a broad state-changing command.

**🎯 Architect:** _"You're designing the recovery runbook for a fleet where a bad configuration change could leave hosts unable to reach their default target on boot. What does the runbook actually rely on, mechanically?"_
**Model answer:** The core mechanism is that target selection can happen _before_ systemd's normal startup even runs, via the `systemd.unit=` kernel command-line parameter set at the GRUB boot menu — that's what makes it possible to get a working shell on a host whose configured default target won't come up cleanly, without needing the broken state to resolve itself first. The runbook would specify booting with `systemd.unit=rescue.target` first, since rescue mode keeps the root filesystem read-write and basic services up, giving enough of a working environment to diagnose and fix whatever's actually broken in the default target's dependency chain with normal tools. If rescue mode itself can't come up — filesystem-level corruption, an `fstab` bad enough that even rescue's mount pass fails — the fallback is `systemd.unit=emergency.target`, accepting a read-only root and doing the minimum needed (often `mount -o remount,rw /` first) to get enough access to fix the underlying issue. Critically, neither of these kernel-parameter boots writes anything to disk — they're single-boot overrides, so once the real fix is applied, a normal reboot without the parameter re-validates that the actual default target now comes up cleanly, rather than the fleet silently depending on rescue mode forever. I'd also make sure `systemctl get-default` and the target dependency chain for each host's actual default are documented ahead of time, so responders aren't discovering what "normal" looks like for the first time during an incident.
_What the interviewer is probing for:_ Whether the candidate treats kernel-command-line target selection as a first-class recovery mechanism with a clear escalation path (rescue before emergency), and understands that these are non-persistent, single-boot interventions rather than fixes in themselves.

## 10. Key Takeaways

- Standard targets map onto familiar runlevel numbers — `poweroff.target`=0, `rescue.target`=1, `multi-user.target`≈3, `graphical.target`≈5, `reboot.target`=6 — via real, functioning compatibility symlinks, with `emergency.target` as a target that has no SysVinit runlevel equivalent at all (2).
- The real upgrade over runlevels is structural: targets form a genuine dependency chain (`graphical.target` → `multi-user.target` → `basic.target` → `sysinit.target`), not a flat, mutually exclusive numbered list (3).
- `systemctl get-default`/`set-default` change only the boot-time default by repointing the `default.target` symlink — they have no effect on the currently running state (4).
- `systemctl isolate <target>` changes the currently running state immediately, and is named `isolate` because it stops every unit not required by the target being isolated to — a materially different, and materially riskier, operation than a SysVinit runlevel switch (5).
- Rescue mode (mostly-functional, read-write root, basic services, root shell) and emergency mode (bare minimum, read-only root, used when rescue itself is unreachable) are two distinct troubleshooting depths, not interchangeable synonyms (6).
- `systemd.unit=rescue.target` (or `emergency.target`) as a GRUB kernel command-line parameter selects the boot target before systemd's normal startup runs at all — a non-persistent, single-boot recovery technique for hosts whose configured default won't come up cleanly (7).

## 11. Related Concepts & What's Next

This section is the promised full depth on the target concept [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) introduced structurally in Part 9's opening section, and it operates on the general `[Unit]` dependency/ordering vocabulary (`Requires=`/`After=`) [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) established — 3's dependency-chain diagram is that vocabulary applied specifically to targets. It also assumes [§66](./Section-66-Part9-Managing-Services-Systemctl.md)'s `systemctl` fluency, since `get-default`/`set-default`/`isolate` are all `systemctl` subcommands rather than separate tools. [§71](./Section-71-Part9-Environment-Configuration-Etc-Environment-Profile-D-Systemd.md) (next) moves to environment configuration — `/etc/environment`, `profile.d`, and systemd environment files — a different corner of system-wide configuration that, unlike target transitions, is about what environment a started process inherits rather than which units get started at all.

**Next Section:** [§71](./Section-71-Part9-Environment-Configuration-Etc-Environment-Profile-D-Systemd.md) — `Section-71-Part9-Environment-Configuration.md`
