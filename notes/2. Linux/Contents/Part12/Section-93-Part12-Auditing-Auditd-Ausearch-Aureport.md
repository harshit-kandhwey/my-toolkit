# Section 93 (Part 12): Auditing: auditd, ausearch, aureport

## 1. What auditd Actually Is (and Isn't)

Lead with the distinction that matters most, because it's the one most often glossed over: **auditd is not "more logging."** §68 covered journald as the general-purpose, integrated logging subsystem for services and the system as a whole — what a service printed to stdout, what systemd did when a unit started or failed, kernel messages. **auditd is a separate, kernel-level subsystem with a narrower and more specific job: recording security-relevant events** — syscalls, file access, authentication decisions, changes to specific files — in a way that is deliberately harder to tamper with and structured for compliance and forensic review, not general troubleshooting.

The scope difference is the whole point:

- **journald/syslog** answer "what happened, generally, across services and the system" — useful for debugging, operational visibility, and general history.
- **auditd** answers a narrower question with a compliance/forensic framing: "who did what to this specific security-sensitive resource, and when, in a form that can stand up as evidence." It hooks directly into the kernel's audit framework (a distinct kernel subsystem, not a userspace log aggregator sitting on top of syslog), watching syscalls and file operations at a level journald doesn't reach by default.

Don't run both and expect redundancy — they answer different questions. A host can have flawless journald coverage and still have zero audit trail on "who edited `/etc/passwd` last Tuesday," because that's specifically auditd's job, not journald's.

> 💡 **Tip:** If asked "why not just grep the journal for this," the honest answer is that journald wasn't designed with tamper-resistance or a fixed, structured event schema as a design goal — auditd's records exist specifically to survive scrutiny in an incident review or compliance audit, which is a different bar than "helpful for debugging."

## 2. Audit Rules: `/etc/audit/rules.d/*.rules`

auditd doesn't watch everything by default — it watches exactly what's configured via **rules**, loaded from `/etc/audit/rules.d/*.rules` (compiled into the running configuration via `augenrules`, or historically edited directly in `/etc/audit/audit.rules`). Two rule types matter most operationally:

- **File/directory watch rules** — watch a specific path for a specific class of access.
- **Syscall rules** — watch for a specific system call being made, optionally filtered by argument, user, or architecture.

**Watching a file for writes and attribute changes:**

```bash
sudo auditctl -w /etc/passwd -p wa -k passwd_changes
```

| Component           | Meaning                                                                        |
| ------------------- | ------------------------------------------------------------------------------ |
| `-w /etc/passwd`    | The path to watch                                                              |
| `-p wa`             | Permissions to trigger on — `w` (write), `a` (attribute change); also `r`, `x` |
| `-k passwd_changes` | A searchable **key** tag attached to every event this rule generates           |

`auditctl` changes are applied to the running kernel audit configuration immediately but do **not** persist across reboot on their own — persistent rules belong in a `.rules` file under `/etc/audit/rules.d/` so `auditd`/`augenrules` reloads them at startup. This split (immediate `auditctl` for testing, `.rules` files for anything permanent) trips people up in practice: a rule tested and confirmed working with `auditctl` that was never also written to a rules file silently disappears on the next reboot.

## 3. Syscall Rules: Watching an Action Rather Than a Path

Watch rules (2) cover "did anything touch this specific file." **Syscall rules** cover a different, complementary question: "did anyone, anywhere on the system, make this specific system call" — useful when the concern is a class of action rather than a single known path. A common hardening example is watching for privilege-escalation-relevant syscalls:

```bash
sudo auditctl -a always,exit -F arch=b64 -S execve -F uid=0 -k root_exec
```

| Component        | Meaning                                                                                                                                 |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `-a always,exit` | Always log this rule's matches at syscall **exit** (the standard action for most rules)                                                 |
| `-F arch=b64`    | Restrict to the 64-bit syscall table — architecture must be specified explicitly since syscall numbers differ between 32-bit and 64-bit |
| `-S execve`      | The specific syscall to watch — here, program execution                                                                                 |
| `-F uid=0`       | Further filter to events where the acting UID is root                                                                                   |
| `-k root_exec`   | The searchable key, same idea as a watch rule's key                                                                                     |

Syscall rules are more powerful than watch rules but also more expensive (6) — a syscall rule with no filters at all watches that call system-wide, for every process, which is exactly the kind of unscoped rule that generates disproportionate volume.

## 4. `ausearch`: Finding Specific Events

`ausearch` queries the audit log for events matching criteria, and the **key** from a watch rule is the most direct way to find exactly what that rule was set up to catch:

```bash
sudo ausearch -k passwd_changes
```

Other common filters, usable alone or combined:

| Flag           | Meaning                                                                                                                                                                                              |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-k <key>`     | Events matching a specific rule key                                                                                                                                                                  |
| `-ua <uid>`    | Events by a specific **audit UID** — the UID that authenticated at login, preserved even through `sudo`/`su`, which is often the more useful identity than the UID a syscall actually executed under |
| `-ui <uid>`    | Events by a specific **effective UID** at the time of the syscall                                                                                                                                    |
| `-ts <time>`   | Events since a given start time (`today`, `recent`, or an explicit timestamp) — combine with `-te` for an end bound                                                                                  |
| `-m <msgtype>` | Filter by audit message type, e.g. `USER_LOGIN`, `USER_AUTH`                                                                                                                                         |

The `-ua` vs. `-ui` distinction is worth internalizing rather than memorizing: `-ua` tracks back to who actually logged in and authenticated, which matters for accountability ("who is responsible for this") even after a `sudo` to root changes the _effective_ UID the syscall ran under.

## 5. `aureport`: Summaries Over Raw Search

Where `ausearch` finds specific events matching a filter, `aureport` produces **aggregated summaries** — the better starting point when the question is "what's been happening" rather than "show me this one thing":

```bash
sudo aureport --summary
sudo aureport --failed
```

| Flag        | Purpose                                                                                                                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--summary` | High-level counts across all tracked event categories — logins, file access, syscalls                                                                                                                   |
| `--failed`  | Only events that **failed** — failed logins, denied syscalls, failed access attempts — often the fastest way to spot an attack or misconfiguration without wading through successful, expected activity |

A practical workflow: run `aureport --failed` first to get a shortlist of anomalies, then pivot to `ausearch` with the specific key, UID, or time range once a lead is identified — summary-first, then drill down, rather than starting from raw event volume.

## 6. Practical Example: Auditing Writes to `/etc/passwd` and `/etc/shadow`

Tying together 2 through 5 into the concrete hardening/compliance requirement referenced back in §25 (users and permissions): most compliance frameworks (and §96's CIS benchmarks, closing this Part) explicitly require auditing changes to the core account files.

```bash
# Persistent rule file
sudo tee /etc/audit/rules.d/accounts.rules <<'EOF'
-w /etc/passwd -p wa -k passwd_changes
-w /etc/shadow -p wa -k shadow_changes
-w /etc/group -p wa -k group_changes
EOF

sudo augenrules --load
```

After this, any write or attribute change to those files — whether via `useradd`/`usermod` or a direct edit — is captured and retrievable with `ausearch -k passwd_changes`. This is precisely the kind of control an auditor checking against a compliance framework looks for: not just "is the file permission correct" (§25/§4 already cover that), but "is there a durable, searchable record of every change to it."

**Reading the result:** `ausearch`'s raw output is a set of dense, machine-oriented `type=...` key-value lines — readable but not friendly. The `-i` flag ("interpret") is worth using by default in practice, since it resolves numeric UIDs/GIDs to names and translates some raw fields into human-readable form:

```bash
sudo ausearch -k passwd_changes -i
```

This turns a raw record showing `uid=1000` into one showing the actual username, which matters directly during an incident review — nobody wants to be cross-referencing `/etc/passwd` by hand mid-investigation to figure out who UID 1000 actually is.

## 7. Shipping Audit Logs Off-Host

A local audit log is only tamper-resistant up to a point — an attacker who gains root on the host can, in principle, edit or delete `/var/log/audit/audit.log` just like any other local file, which undercuts the "hard to tamper with" framing in 1 if the log never leaves the host it was generated on. Production auditd deployments commonly pair local rules with **`audisp-remote`** (part of the audit dispatcher plugin framework) to forward audit events to a centralized, append-only log collector in near-real-time, so the authoritative copy of the audit trail exists somewhere the compromised host itself can't reach. This connects directly to the architect-level judgment in the questions below: a security-relevant audit trail that lives only on the box being audited has a structural weakness baked in, regardless of how carefully the rules are scoped.

## 8. Operational Trade-Off: Volume and Overhead

It's tempting to audit everything — every syscall, every file — since auditd technically supports it. **Don't.** This section closes on the honest operational trade-off: comprehensive syscall auditing generates enormous event volume on an active host, consuming disk I/O, log storage, and non-trivial CPU overhead from the kernel-level hooking itself. A rule watching every `open()` syscall system-wide on a busy production server can produce more log volume than every other subsystem on the box combined.

> ⚠️ **Warning:** Broad, unscoped audit rules are a common self-inflicted incident — a well-meaning "audit everything for compliance" rule set can fill `/var/log/audit/` fast enough to trigger disk-full alerts or even auditd's own configured failure mode (some configurations halt the system on audit log exhaustion, by design, since a security-auditing subsystem that silently drops events defeats its own purpose). Scope rules to what's genuinely security-relevant — specific sensitive files, specific syscall classes tied to a real threat model — rather than maximal coverage. Broad is not the same as thorough; it's usually just noisy.

The engineering judgment call is the same one that runs through this whole Part: security controls have real operational cost, and the right amount of auditing is "enough to answer the questions that actually matter during an incident or audit," not "the theoretical maximum the tooling supports."

## 9. Common Misconceptions

1. **"auditd is just another way to view logs, like journalctl."** They serve different purposes at different layers — journald is general-purpose operational logging (§68); auditd is a kernel-level, compliance/forensic-oriented subsystem for security-relevant events specifically, with different retention and tamper-resistance goals (1).
2. **"`auditctl` rules are permanent once set."** Rules added via `auditctl` apply to the live kernel configuration immediately but vanish on reboot unless also written to a `.rules` file under `/etc/audit/rules.d/` and loaded via `augenrules` (2).
3. **"More audit rules is always better security."** Unscoped, maximal auditing produces volume and overhead that can itself become an operational problem — including, in some configurations, forcing the system to halt when audit storage fills — so scoping rules to genuinely security-relevant targets is part of doing this correctly, not a compromise (8).
4. **"SELinux denials show up in journald, so auditd is optional for SELinux troubleshooting."** SELinux (§91) actually logs its denials through the audit subsystem specifically — `ausearch -m avc` is a standard way to find SELinux denial events — so auditd and SELinux are more tightly coupled operationally than the general journald/auditd distinction in 1 might suggest.
5. **"A local audit log that's hard to tamper with is sufficient on its own."** Root-level compromise can still edit or delete a purely local audit log — pairing local rules with off-host forwarding (`audisp-remote`, 7) is what actually delivers on the tamper-resistance goal in practice (1).

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between auditd and journald/syslog?"_
**Model answer:** journald and syslog are general-purpose logging — whatever a service or the system chooses to log, for operational visibility and debugging. auditd is a separate, kernel-level subsystem specifically for security-relevant events — syscalls, file access, authentication — designed with tamper-resistance and compliance/forensic use in mind rather than general troubleshooting convenience.
_What the interviewer is probing for:_ Whether the candidate treats auditd as "extra logging" or understands it as a distinct subsystem with a narrower, specific purpose.

**🎯 Intermediate:** _"How would you set up auditing for changes to `/etc/shadow`, and how would you find those events later?"_
**Model answer:** Add a watch rule — `auditctl -w /etc/shadow -p wa -k shadow_changes` for immediate effect, and the same line in a `.rules` file under `/etc/audit/rules.d/` (loaded via `augenrules --load`) so it survives reboot. To find events later, `ausearch -k shadow_changes` pulls everything tagged with that key; `aureport --summary` gives a broader picture if I don't yet know what I'm looking for.
_What the interviewer is probing for:_ Practical command fluency and the auditctl-vs-persistent-rule-file distinction that's an easy trap.

**🎯 Senior:** _"A production host's disk is filling up and `/var/log/audit/` is the culprit. How do you approach it?"_
**Model answer:** First check what rules are actually loaded (`auditctl -l`) — the likely root cause is an overly broad rule, commonly a syscall-class rule with no path or UID filter, generating far more volume than intended. I'd use `aureport --summary` to see which event categories dominate, narrow or remove the offending rule, and only then deal with the immediate disk-full symptom (rotation, archiving). I'd also check whether `auditd.conf`'s `disk_full_action`/`space_left_action` is configured to something disruptive like halting the system — some hardened configurations do this intentionally, which changes the urgency significantly. Long-term, I'd push back on any "audit everything" rule set and replace it with rules scoped to what a real threat model or compliance requirement actually calls for.
_What the interviewer is probing for:_ Understanding audit volume as a real operational risk, not just a theoretical caveat, and knowing to check `auditd.conf`'s failure-mode configuration before treating it purely as a storage problem.

**🎯 Architect:** _"How do you decide what should and shouldn't be covered by audit rules across a fleet?"_
**Model answer:** I'd start from what's actually required — compliance frameworks like CIS (§96) and specific regulatory obligations typically enumerate concrete targets: account files (`/etc/passwd`, `/etc/shadow`, `/etc/group`), sudoers, SSH configuration, and specific security-relevant syscall classes (privilege escalation, module loading) — rather than trying to audit everything and hoping it's sufficient. I'd scope rules to those specific, justified targets, keep the rule set version-controlled and deployed consistently via configuration management rather than ad hoc per-host, and treat rule additions as reviewed changes given the volume/overhead trade-off in 8. I'd also make sure the audit trail itself is shipped off-host to centralized, append-only storage via something like `audisp-remote` (7) — a tamper-resistant local log that an attacker with root can still delete isn't actually tamper-resistant in practice.
_What the interviewer is probing for:_ Fleet-scale, compliance-driven rule design rather than host-by-host ad hoc rule addition, and awareness that local audit logs alone don't fully deliver on the tamper-resistance goal without off-host shipping.

## 11. Key Takeaways

- auditd is a kernel-level subsystem for security-relevant events specifically — distinct in scope and purpose from journald/syslog's general-purpose logging (§68), not a redundant alternative to it.
- Watch rules (`auditctl -w /path -p wa -k key`) tag file/directory access with a searchable key; syscall rules (`-a always,exit -S <call>`) watch a class of action system-wide; persist either in `/etc/audit/rules.d/*.rules` and load via `augenrules`, since `auditctl`-only changes don't survive reboot.
- `ausearch -k <key> -i` (plus `-ua`/`-ui` for user-based filtering and `-ts` for time ranges) finds specific tagged events in human-readable form; `aureport --summary`/`--failed` gives aggregated overviews, better as a starting point than raw search.
- A concrete, realistic use case is watching `/etc/passwd`/`/etc/shadow`/`/etc/group` for writes — a common compliance requirement tying directly back to §25's account-file coverage.
- A purely local audit log is only partially tamper-resistant — forwarding events off-host via `audisp-remote` to centralized, append-only storage is what closes the gap a root-level compromise on the audited host itself would otherwise create.
- Comprehensive auditing is possible but generates real volume and overhead — including risk of filling audit log storage or triggering a configured failure mode — so scoping rules to genuinely security-relevant targets is a deliberate design decision, not a shortcut.
- SELinux denials (§91) are specifically surfaced through the audit subsystem (`ausearch -m avc`), making auditd and SELinux more tightly coupled in practice than the general journald contrast might suggest.

## 12. Related Concepts & What's Next

This section specifically contrasts with §68's journald coverage (Part 9) on scope and purpose, builds on §25's account-file permission model with a concrete auditing use case, ties into §91's SELinux denial logging (prior this Part), and complements §90's SSH hardening (prior this Part) by giving a mechanism to audit authentication events directly. §94 (next) moves to vulnerability and patch management — a different security discipline concerned with reducing exposure to known vulnerabilities rather than recording who did what.

**Next Section:** §94 — `Section-94-Part12-Vulnerability-Patch-Management.md`
