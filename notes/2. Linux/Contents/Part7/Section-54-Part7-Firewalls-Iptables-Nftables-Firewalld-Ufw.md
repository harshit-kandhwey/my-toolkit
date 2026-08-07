# Section 54 (Part 7): Firewalls: iptables, nftables, firewalld, ufw

## 1. Overview: One Kernel Framework, Four Names Administrators Argue About

[§51](./Section-51-Part7-Networking-Fundamentals-Recap.md) covered the ports and protocols a host actually exposes, and [§52](./Section-52-Part7-Network-Configuration-Tools.md) covered the tools that configure interfaces and routes. This section covers the layer that sits on top of both: deciding which of that traffic the kernel is actually allowed to let through. The most common source of confusion in this entire area isn't any single tool's syntax — it's that **iptables, nftables, firewalld, and ufw are not four competing firewalls**. They are four different altitudes of the same underlying capability, and conflating them ("should I use iptables or firewalld?") is a bit like asking "should I use assembly or my deployment script?" — the honest answer is that one is frequently built on the other.

At the bottom sits **Netfilter**, a packet-filtering framework built directly into the Linux kernel — hooks at specific points in the network stack where packets can be inspected, matched against rules, and accepted, dropped, or otherwise redirected. Netfilter itself has no user-facing command; it's activated and configured entirely through userspace tools that talk to it. **iptables** was, for roughly two decades, the standard userspace tool for that job. **nftables** is Netfilter's modern successor interface, aiming to replace iptables's syntax and internal model with something cleaner while using the same underlying kernel framework. **firewalld** and **ufw** sit a layer higher still — they don't talk to the kernel directly at all; they generate and manage iptables/nftables rules on the administrator's behalf, in exchange for a simpler, more distro-idiomatic command surface.

> 💡 **Tip:** Every tool in this section ultimately answers one of two questions about a packet: "should this be allowed?" and, if not, "should the sender be told, or just silently ignored?" Keeping that framing in mind while comparing four different syntaxes makes the differences feel like presentation choices layered over one shared decision, not four unrelated security models to memorize independently.

## 2. Netfilter and iptables: The Historical Foundation

**iptables** configures Netfilter's rule set, organized into **tables** and **chains**. A table groups rules by purpose; the default and most commonly touched table is `filter`, which is what most people mean when they say "firewall rules." Within a table, traffic passes through **chains** corresponding to points in the packet's journey:

| Chain     | When it fires                                                                   |
| --------- | ------------------------------------------------------------------------------- |
| `INPUT`   | Packets destined **for this host** itself                                       |
| `OUTPUT`  | Packets **originating from** this host                                          |
| `FORWARD` | Packets passing **through** this host to somewhere else (routing/NAT scenarios) |

Each chain holds an ordered list of **rules**, evaluated top to bottom until one matches. A rule pairs a **match** (source/destination IP, port, protocol, interface, connection state, and more) with a **target** — the action to take once matched:

| Target   | Effect                                                                                          |
| -------- | ----------------------------------------------------------------------------------------------- |
| `ACCEPT` | Let the packet through                                                                          |
| `DROP`   | Silently discard the packet — no response sent to the sender                                    |
| `REJECT` | Discard the packet but send back an explicit rejection (e.g., ICMP port-unreachable or TCP RST) |

A worked example — allowing inbound SSH ([§51](./Section-51-Part7-Networking-Fundamentals-Recap.md) covers why port 22/TCP is the relevant number here) while leaving a default-deny posture for everything else on `INPUT`:

```bash
iptables -A INPUT -p tcp --dport 22 -m state --state NEW,ESTABLISHED -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -P INPUT DROP
```

Read line by line: append (`-A`) a rule to `INPUT` matching TCP port 22 on new or established connections, jump (`-j`) to `ACCEPT`; separately accept any already-established or related traffic (so return traffic for connections _this host_ initiated isn't blocked); accept all loopback traffic; and finally set the chain's **default policy** to `DROP` for anything that fell through without matching an explicit `ACCEPT` rule above.

> ⚠️ **Warning:** That last line is also the classic way to lock yourself out of a remote box. `iptables -P INPUT DROP` takes effect immediately, and if the SSH-allow rule above it was never actually applied — a typo, wrong port, wrong interface, or rules flushed and reapplied out of order — the very next command over that same SSH session simply never returns, because the connection carrying it is now being silently dropped. There is no keystroke that undoes this remotely once it's live: recovery requires out-of-band access (console, cloud provider serial/VNC console, or a colleague with physical or already-open access) to fix the rule set. The standard mitigation is to always add and verify the allow rule for the connection you're currently using **before** setting a `DROP` default policy, and where possible, test destructive firewall changes via a mechanism that reverts automatically after a timeout (a `cron`/`at` job that restores a known-good rule set after N minutes) rather than trusting a live SSH session not to get cut off mid-change.

iptables rules are **not persistent** across reboots by default — they live only in the running kernel's rule tables — so production use pairs iptables (or its successor) with a persistence mechanism (`iptables-save`/`iptables-restore`, a distro package like `iptables-persistent`, or a higher-level tool that manages persistence itself, covered next).

## 3. nftables: The Modern Successor

**nftables** is Netfilter's designated replacement for iptables, built on the same underlying kernel framework but with a materially cleaner design: a single unified command (`nft`) instead of separate `iptables`/`ip6tables`/`arptables`/`ebtables` binaries for different protocol families, a more expressive native syntax for combining match conditions, and rule sets organized into administrator-defined tables and chains rather than iptables's fixed built-in ones.

The same INPUT-allow-SSH logic as 2, expressed in nftables syntax:

```bash
nft add table inet filter
nft add chain inet filter input { type filter hook input priority 0 \; policy drop \; }
nft add rule inet filter input tcp dport 22 ct state new,established accept
nft add rule inet filter input ct state established,related accept
nft add rule inet filter input iif lo accept
```

The `inet` family targets both IPv4 and IPv6 with one rule set — a direct improvement over iptables needing a parallel `ip6tables` invocation for every rule that should also apply to IPv6.

**The detail that resolves most "which one am I actually using" confusion:** on essentially every modern mainstream distribution, running the `iptables` command does not talk to the legacy iptables kernel code path at all anymore. It invokes **`iptables-nft`**, a compatibility shim that translates the familiar iptables syntax into nftables rules under the hood, storing them in the same nftables rule set that `nft` itself manages. This means an administrator can type `iptables -L` out of habit, see familiar-looking output, and reasonably assume they're running "classic" iptables — while the actual enforcement is happening via nftables underneath. `iptables --version` (or checking whether `/usr/sbin/iptables` is a symlink into the `xtables-nft` toolchain) is the way to confirm which backend is actually active on a given host; `iptables-legacy` still exists as an explicit opt-out on distributions that ship it, for the rare case something depends on genuinely old kernel behavior.

> 💡 **Tip:** Because of the shim, "does this host use iptables or nftables?" is often the wrong question — the honest modern answer on most distributions is "iptables syntax, nftables enforcement." The question worth actually asking during an audit is whether a host's rules were authored directly in `nft` syntax (bypassing the shim entirely) or via `iptables`/`iptables-nft` commands, since mixing both authoring paths against the same underlying rule set on one host is a real source of confusing, hard-to-diff configuration.

## 4. firewalld: RHEL/Fedora's Zone-Based Abstraction

**firewalld** is the default higher-level firewall manager on RHEL, Fedora, CentOS/Rocky/Alma, and related distributions. It does not replace nftables/iptables as the enforcement mechanism — it manages them, generating the underlying rules from a friendlier abstraction: **zones**.

A **zone** is a named trust level applied to a network interface or source — `public`, `internal`, `trusted`, `dmz`, `drop`, and others ship by default, each with a different baseline posture (the `drop` zone silently discards everything with no exceptions; `trusted` allows everything). Instead of writing chain/rule logic directly, an administrator assigns an interface to a zone and then allows specific services or ports within that zone:

```bash
firewall-cmd --zone=public --add-service=ssh --permanent
firewall-cmd --zone=public --add-port=8080/tcp --permanent
firewall-cmd --reload
```

The `--permanent` flag is the load-bearing detail here: firewalld maintains a strict split between **runtime** configuration (active right now, lost on reload/reboot) and **permanent** configuration (persisted to disk, applied on the _next_ reload). A change made without `--permanent` is live immediately but gone after `firewall-cmd --reload` or a reboot; a change made _with_ `--permanent` is written to disk but not actually active until a reload picks it up. Forgetting to reload after a permanent-only change, or forgetting `--permanent` on a change meant to survive a reboot, are the two most common firewalld operational mistakes — `firewall-cmd --add-service=ssh --permanent --zone=public && firewall-cmd --reload` as a single habitual sequence avoids both.

```bash
firewall-cmd --list-all                 # runtime state of the default zone
firewall-cmd --permanent --list-all     # what will apply after the next reload
```

Named **services** (`ssh`, `http`, `https`, and many more, defined in XML service files under `/usr/lib/firewalld/services/`) are firewalld's other major usability win over raw port numbers — `--add-service=ssh` reads far more intelligibly in a change log than `--add-port=22/tcp`, and it keeps the mapping between "what this rule is for" and "what port that means" in one maintained place rather than scattered across ad hoc comments.

## 5. ufw: Ubuntu/Debian's Simpler Abstraction

**ufw** (Uncomplicated Firewall) is Ubuntu's equivalent high-level layer, prioritizing terse, readable commands over firewalld's zone model. It manages iptables/iptables-nft rules underneath, with no separate zone concept — just a default-deny/default-allow posture per direction plus an ordered rule list.

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 8080/tcp
ufw enable
```

`ufw allow ssh` uses an **application profile** — a named entry (stored under `/etc/ufw/applications.d/`) mapping a friendly name to the port(s) and protocol(s) it actually needs, the same intelligibility win firewalld's named services provide. `ufw app list` shows which profiles are registered on a given host, and `ufw allow 'Nginx Full'` (matching an app profile with a space in its name, hence the quoting) is a common pattern once a web server package registers its own profile during installation.

> ⚠️ **Warning:** `ufw enable` applies the current rule set immediately, including the default-deny-incoming policy set moments earlier — running it over an SSH session **before** confirming `ufw allow ssh` (or the equivalent port) has actually been added is the ufw-specific version of the same lockout risk described in 2's warning. `ufw status` (or `ufw status verbose`) before `ufw enable` is the habitual check that prevents it — confirm the SSH rule is listed before flipping the switch that starts enforcing a default-deny posture.

ufw persists its rules across reboots on its own (it writes to files under `/etc/ufw/` and reapplies them via a systemd service at boot — [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) onward covers systemd unit mechanics in depth), so unlike raw iptables there's no separate persistence step to remember.

## 6. Hands-On: Checking What's Actually Enforcing Rules on an Unfamiliar Host

### 6.1 Identifying the active high-level frontend

**Purpose:** Before touching firewall rules on an inherited or unfamiliar host, confirm whether firewalld or ufw is managing them — running raw `iptables`/`nft` commands against a host where one of these is active will work in the moment but gets silently overwritten or fought the next time that frontend reconciles its own state.

```bash
systemctl is-active firewalld
systemctl is-active ufw
```

**Expected output:** One of the two returns `active`; on Debian/Ubuntu-family hosts ufw is more commonly present (though not always enabled), and on RHEL-family hosts firewalld is the default. Neither returning `active` means rules are either unmanaged raw iptables/nftables, or no firewall is configured at all — worth confirming explicitly rather than assuming, since an unmanaged host with no filtering is a materially different risk posture than one firewalld or ufw simply isn't reporting correctly.

### 6.2 Viewing the actual enforced rule set regardless of frontend

**Purpose:** Whatever frontend generated the rules, the ground truth of what the kernel is actually enforcing lives in the nftables rule set on modern hosts (or the classic iptables tables on older ones).

```bash
nft list ruleset
iptables -L -n -v --line-numbers
```

**Common errors:** Assuming `iptables -L` output reflects "the iptables way" of doing things when the host is actually running `iptables-nft` under the hood (3) — the output looks the same either way, which is exactly the ambiguity worth resolving with `iptables --version` if it matters for an audit or a migration decision.

**Troubleshooting:** If `firewall-cmd --list-all` or `ufw status` shows rules that don't appear to match what `nft list ruleset` shows, suspect a runtime-vs-permanent mismatch (firewalld, 4) or a rule added directly via `iptables`/`nft` outside the managing frontend's knowledge — both frontends can drift from the underlying enforced state if changes bypass them.

## 7. The Layering, Summarized

| Layer                      | What it is                                                           | Talks to                                   | Typical home                         |
| -------------------------- | -------------------------------------------------------------------- | ------------------------------------------ | ------------------------------------ |
| Netfilter                  | Kernel packet-filtering framework (hooks, no user-facing command)    | The kernel network stack itself            | Every Linux host, invisibly          |
| iptables / iptables-nft    | Historical userspace tool; now usually a shim into nftables          | Netfilter directly (or via nft)            | Legacy scripts, raw/manual rule work |
| nftables (`nft`)           | Modern unified userspace tool, Netfilter's designated successor      | Netfilter directly                         | Hand-rolled modern rule sets         |
| firewalld (`firewall-cmd`) | Zone-based abstraction generating nftables/iptables rules            | nftables/iptables, not the kernel directly | RHEL/Fedora/CentOS/Rocky/Alma        |
| ufw (`ufw`)                | Simple allow/deny abstraction generating iptables/iptables-nft rules | iptables/iptables-nft                      | Ubuntu/Debian                        |

**Practical guidance by distro:** on RHEL-family hosts, reach for `firewall-cmd` day to day and drop to `nft list ruleset` only to verify or debug; on Ubuntu/Debian, reach for `ufw` and drop to `iptables -L`/`nft list ruleset` for the same verification purpose. Hand-writing raw `nft` (or `iptables`) rules directly is appropriate for custom routing/NAT scenarios, container networking integration, or environments with no distro-default frontend installed — but doing so on a host where firewalld or ufw is actively running risks exactly the drift described in 6.2, since the higher-level tool doesn't know about rules it didn't create and may reconcile them away.

## 8. Common Misconceptions

1. **"iptables and nftables are two competing firewalls, pick one."** They're not independent competitors — nftables is Netfilter's designated successor to iptables, built on the same kernel framework, and on most modern distributions the `iptables` command itself is a compatibility shim translating into nftables rules (3). The real choice is usually which syntax to author in, not which enforcement engine to trust.
2. **"firewalld and ufw are alternative firewalls to iptables/nftables."** Both are higher-level frontends that generate and manage iptables/nftables rules on the administrator's behalf (4, 5) — they don't replace the enforcement layer, they abstract over it. Running raw `iptables`/`nft` commands alongside one of these frontends on the same host is what causes drift, not a genuine architecture conflict.
3. **"`DROP` and `REJECT` are interchangeable ways to say no."** `DROP` silently discards a packet with no response; `REJECT` sends back an explicit rejection (ICMP unreachable or a TCP RST). The choice affects what a connecting client experiences (a `REJECT`ed connection fails fast; a `DROP`ped one hangs until the client's own timeout) and, more operationally, what an administrator can accidentally lock themselves out with (2's warning).
4. **"A permanent firewalld change is active immediately."** It's the opposite risk from what people expect: `--permanent` changes are written to disk but not enforced until the next `firewall-cmd --reload` or reboot, while changes without `--permanent` are live now but gone after that same reload (4) — the split trips up administrators in both directions.
5. **"Checking `iptables -L` tells you whether a host is 'using iptables' in the legacy sense."** The output looks identical whether the host is running genuine legacy iptables or `iptables-nft` translating into nftables underneath (3) — `iptables --version` or checking the binary's actual backend is the only way to know which is really enforcing traffic.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between iptables and nftables?"_
**Model answer:** Both configure Netfilter, the kernel's packet-filtering framework — they're not two separate firewalls, they're two userspace tools for the same underlying mechanism. iptables is the older, historical tool, organized around fixed built-in chains (INPUT, OUTPUT, FORWARD) and separate binaries per protocol family. nftables is the designated modern successor: one unified `nft` command, a single `inet` family that covers IPv4 and IPv6 together, and a generally cleaner rule syntax. On most modern distributions, running the `iptables` command doesn't even use the legacy code path anymore — it's a compatibility shim (`iptables-nft`) that translates into nftables rules under the hood.
_What the interviewer is probing for:_ Whether the candidate understands these as layers of the same framework rather than two arbitrary alternatives, and whether they know about the `iptables-nft` shim specifically.

**🎯 Intermediate:** _"Where do firewalld and ufw fit relative to iptables and nftables?"_
**Model answer:** They're a layer above both — higher-level, distro-specific abstractions that generate and manage iptables/nftables rules rather than replacing the enforcement mechanism itself. firewalld is RHEL/Fedora's answer, organized around named zones (trust levels applied per interface) with a runtime-vs-permanent configuration split. ufw is Ubuntu/Debian's answer, simpler still — default-allow/default-deny per direction plus an ordered allow-rule list, with application profiles standing in for firewalld's named services. Neither talks to the kernel directly; both are convenience layers over the same underlying nftables/iptables enforcement.
_What the interviewer is probing for:_ Correctly placing all four tools in one coherent mental model instead of treating them as an arbitrary list to memorize, and knowing which distro defaults to which frontend.

**🎯 Senior:** _"You've inherited a host where `iptables -L` shows rules, but `firewall-cmd --list-all` shows nothing and firewalld is running. What's your diagnosis path?"_
**Model answer:** That's a strong signal of drift between a raw-iptables-authored rule set and firewalld's own managed state — someone (or some provisioning script) added rules directly via `iptables`/`iptables-nft` outside firewalld's knowledge, so firewalld's permanent/runtime configuration has no record of them. I'd check `firewall-cmd --state` to confirm firewalld is genuinely active and not just installed, then `nft list ruleset` to see the actual enforced state regardless of which frontend claims ownership, and cross-reference against `firewall-cmd --permanent --list-all` to see what firewalld believes should be there after a reload. The risk is that the next `firewall-cmd --reload` (or a reboot) could wipe the unmanaged rules firewalld doesn't know about, silently changing the host's effective security posture. The fix is to migrate whatever those raw rules were doing into firewalld's own zone/service/port model — services if there's a clean name for what's being allowed, ports otherwise — so there's one source of truth again, rather than leaving two systems fighting over the same rule set.
_What the interviewer is probing for:_ Recognizing the specific failure mode of mixing authoring layers, using ground-truth commands rather than trusting either frontend's view alone, and understanding the actual operational risk (silent rule loss on reload) rather than just noticing a discrepancy exists.

**🎯 Architect:** _"You're designing the firewall strategy for a mixed fleet of RHEL and Ubuntu hosts, some managed by configuration management, some legacy and hand-configured. How do you approach standardization without breaking anything mid-migration?"_
**Model answer:** I wouldn't try to force one syntax across both distro families — firewalld and ufw are each the idiomatic, best-supported choice on their respective platforms, and fighting that (running raw `nft` uniformly everywhere, say) trades a real usability and tooling-support advantage for a marginal consistency win. Instead I'd standardize on "each host uses its distro's native high-level frontend, driven entirely through configuration management, never hand-edited" — that gets consistency at the level that actually matters (declarative, reviewable, idempotent firewall state) without forcing a syntax mismatch with each distro's own conventions and documentation. For the legacy hand-configured hosts, before migrating anything I'd capture the actual enforced rule set with `nft list ruleset`/`iptables-save`, diff it against what the target frontend's declared configuration would produce, and stage the cutover per host with the lockout risk from 2 and 5 explicitly in mind — meaning an out-of-band access path (console access, a time-bombed rule revert) confirmed available before any host's default policy changes from allow to deny. I'd treat "which frontend" as settled by distro convention, and spend the actual design effort on making the transition from ad hoc to managed state safe and auditable, not on picking a single tool to rule every host.
_What the interviewer is probing for:_ Pragmatic standardization (consistency at the right layer, not forcing tool uniformity against distro convention), and concrete migration-safety discipline given the real lockout risk this whole topic carries.

## 10. Key Takeaways

- Netfilter is the kernel's packet-filtering framework; iptables, nftables, firewalld, and ufw are all userspace ways of configuring it, at increasing levels of abstraction — not four independent competing firewalls (1).
- iptables organizes rules into tables and chains (INPUT/OUTPUT/FORWARD), matching packets against conditions and dispatching to targets like ACCEPT/DROP/REJECT; rules aren't persistent across reboots without a separate save/restore mechanism (2).
- nftables is Netfilter's modern successor — one unified `nft` command, cleaner syntax, combined IPv4/IPv6 handling — and on most modern distributions, `iptables` itself is a compatibility shim (`iptables-nft`) translating into nftables rules under the hood (3).
- firewalld (RHEL/Fedora family) layers zones and a runtime-vs-permanent configuration split on top of nftables/iptables; ufw (Ubuntu/Debian family) layers a simpler allow/deny model with application profiles on the same underlying enforcement (4, 5).
- An overly broad default-deny policy applied before confirming the SSH-allow rule is actually active — in either raw iptables/nftables or via `ufw enable` — is the classic remote-lockout mistake; verify the allow rule is live before flipping the default to deny (2, 5).
- Mixed authoring — raw `iptables`/`nft` rules added alongside an active firewalld or ufw installation — causes drift between what's actually enforced and what the managing frontend believes exists, since neither frontend accounts for rules it didn't create (6, 9).
- Practical guidance: match the frontend to the distro (firewalld on RHEL-family, ufw on Ubuntu/Debian-family) and drop to `nft list ruleset`/`iptables -L` only to verify ground truth, not as the primary day-to-day interface (7).

## 11. Related Concepts & What's Next

This section builds directly on [§51](./Section-51-Part7-Networking-Fundamentals-Recap.md)'s ports/protocols (what firewall rules actually match against) and [§52](./Section-52-Part7-Network-Configuration-Tools.md)'s network configuration tools (interfaces that zones and rules attach to). It's a direct prerequisite for Part 12's security hardening coverage ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)), where firewall rules become one concrete control among several in a broader hardening posture, and for [§55](./Section-55-Part7-Network-Diagnostics.md) (next), which covers the diagnostic tools — `ss`, `tcpdump`, and friends — used to verify a firewall's actual observed behavior rather than trusting the rule set's intent on paper.

**Next Section:** [§55](./Section-55-Part7-Network-Diagnostics.md) — `Section-55-Part7-Network-Diagnostics.md`
