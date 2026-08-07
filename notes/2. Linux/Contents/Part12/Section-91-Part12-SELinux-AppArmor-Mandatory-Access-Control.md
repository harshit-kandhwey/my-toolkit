# Section 91 (Part 12): SELinux and AppArmor (Mandatory Access Control)

## 1. Overview: A New Layer Above the One You Already Know

[§89](./Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md) named least privilege as this Part's load-bearing idea and previewed that mandatory access control extends it beyond [§27](../Part4/Section-27-Part4-Standard-Permission-Model.md)'s standard permission model. This section delivers on that preview. Everything here sits **above** the discretionary permission model built in Part 4 — it doesn't replace `rwx` permissions or `chmod`/`chown`, it adds a second, independent decision a process must clear before an action is permitted at all.

## 2. DAC vs. MAC: The Single Most Important Distinction in This Section

Before naming either SELinux or AppArmor specifically, the distinction between the two access-control models they both implement has to be solid, because everything else in this section is really just "two different implementations of MAC" — the DAC/MAC line is the actual concept.

**Discretionary Access Control (DAC)** is the model [§27](../Part4/Section-27-Part4-Standard-Permission-Model.md) already covers in full: standard Unix `rwx` permissions, where the **owner of a resource decides** who else can access it. If you own a file, you can `chmod 777` it and grant anyone access — the system has no opinion beyond enforcing whatever the owner decided. Even `root`, as the ultimate owner-equivalent, can generally read, write, or change permissions on anything. Access is discretionary because it's left to the discretion of whoever owns the resource.

**Mandatory Access Control (MAC)** inverts that assumption entirely: a **system-wide security policy**, defined and loaded independently of any individual resource owner, decides what's permitted — and critically, **not even the resource owner, and not even `root`, can override that policy** without actually changing the policy itself. A process running as `root` on a MAC-enabled system can still be denied access to a file it technically owns, if the loaded policy doesn't grant that specific interaction. This is the property that makes MAC a genuinely different security layer rather than just "permissions, but stricter" — it removes discretion from the equation entirely and puts a centrally-administered policy in its place.

> 💡 **Tip:** If you remember exactly one sentence from this section, make it this: DAC asks "does the owner of this resource permit this access?"; MAC asks "does the system-wide policy permit this access?" — and a MAC "no" wins even when the DAC answer would have been "yes," including for `root`. Nearly every confusing MAC troubleshooting scenario ("I'm root, permissions look fine, why is this still denied?") traces back to forgetting that second question exists.

Concretely: a web server process might run as an unprivileged `www-data` account (a `sudo`/service-account instance of least privilege from [§89](./Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)) with `rwx` permissions on its content directory that look completely correct under DAC — yet still be denied from reading a specific file if the loaded MAC policy doesn't classify that file as something the web server's process type is permitted to touch. That denial is invisible to `ls -l`/`chmod` entirely; it only shows up in the MAC layer's own logs.

## 3. SELinux: Label-Based Mandatory Access Control

**SELinux** (Security-Enhanced Linux) is the default MAC implementation on RHEL-family distributions (RHEL, CentOS/Rocky/Alma, Fedora) and is generally considered the more powerful, more fine-grained, and correspondingly more complex of the two systems covered in this section.

### 3.1 Contexts and labels

Every file, process, port, and several other resource types under SELinux carry a **security context** — a label with four components: `user:role:type:level`. Viewing a file's context:

```bash
ls -Z /var/www/html/index.html
```

```
unconfined_u:object_r:httpd_sys_content_t:s0 /var/www/html/index.html
```

Of the four fields, **type** (`httpd_sys_content_t` here) is the one that matters for nearly all day-to-day policy decisions — SELinux's default policy family is specifically **type enforcement** (below), and the SELinux user/role/level fields exist for more advanced multi-level/multi-category security configurations that are out of scope for the well-established baseline this section covers.

### 3.2 Type enforcement: the actual enforcement model

**Type enforcement** is the mechanism that makes SELinux a real MAC system rather than an extra labeling scheme: a **process running under a given type** can only interact with **resources of types its loaded policy explicitly permits** — every interaction not explicitly allowed is denied by default. A process running as `httpd_t` (the type an Apache/nginx process typically runs under) can read files labeled `httpd_sys_content_t` because the policy has a rule permitting exactly that interaction — but the same process attempting to read a file labeled, say, `user_home_t` (a type used for content in user home directories) is denied outright, regardless of standard `rwx` permissions on that file, because no policy rule permits `httpd_t` to touch `user_home_t`.

This is precisely the DAC-vs-MAC distinction described above made concrete: the file's owner-based permissions might technically allow the web server's user account to read it, but type enforcement denies the interaction anyway, because the _type_ relationship isn't permitted by policy — a second, independent gate the DAC layer alone can't express.

### 3.3 Enforcing, permissive, and disabled modes

```bash
getenforce
```

SELinux operates in one of three modes:

| Mode           | Behavior                                                                                                        |
| -------------- | --------------------------------------------------------------------------------------------------------------- |
| **Enforcing**  | Policy violations are actually blocked, and logged                                                              |
| **Permissive** | Policy violations are logged but **not blocked** — everything proceeds as if SELinux weren't enforcing anything |
| **Disabled**   | SELinux is off entirely — no labeling, no policy evaluation, no logging                                         |

**Permissive mode's real diagnostic value** is worth calling out specifically, because it's easy to dismiss as "SELinux, but pointless": running a host or a specific service in permissive mode while developing or troubleshooting a policy lets every access that _would have been_ denied get logged without actually breaking anything in production. That log becomes the exact input the `audit2allow` workflow discussed below needs to generate a policy fix — permissive mode is a deliberate, useful diagnostic stance, not a broken half-measure.

```bash
setenforce 0   # switch to permissive
setenforce 1   # switch back to enforcing
```

`setenforce` changes the mode for the current boot only; the persistent setting lives in `/etc/selinux/config`.

### 3.4 `audit2allow`: turning observed denials into policy

When SELinux denies something, the denial is logged (typically to the audit log — full depth in [§93](./Section-93-Part12-Auditing-Auditd-Ausearch-Aureport.md)). `audit2allow` reads those denial log entries and generates a custom policy module granting exactly the access that was denied:

```bash
ausearch -m avc -ts recent | audit2allow -M mypolicy
semodule -i mypolicy.pp
```

This is the correct, narrow way to resolve a legitimate access need SELinux is blocking: it generates a policy change scoped to precisely the observed denial, rather than a blanket loosening of the entire system's policy. It should be reviewed before installing, though — `audit2allow` is a fast way to _generate a candidate fix_, not an authority on whether that fix is actually the right one to grant.

## 4. AppArmor: Path-Based Mandatory Access Control

**AppArmor** is the default MAC implementation on Debian-family distributions (Debian, Ubuntu) and takes a structurally simpler approach to the same underlying MAC idea described above.

Where SELinux labels _resources_ with types and writes policy in terms of type-to-type relationships, AppArmor writes **profiles tied to specific executable paths** — a profile for `/usr/sbin/nginx` names exactly which files, by path, that specific binary is permitted to read, write, or execute, along with capability grants and network access rules. There's no system-wide labeling scheme to maintain across every file on the filesystem; the policy is scoped per-application, expressed in terms of paths that are already meaningful to whoever's reading the profile.

This is generally considered **easier to learn and manage** than SELinux's label-based model — a profile reads like a fairly direct list of "this program may touch these paths," rather than requiring a mental model of a type hierarchy and a policy database of type-to-type rules. The trade-off is **flexibility**: SELinux's type-enforcement model can express relationships and constraints (multi-level security, fine-grained role-based access) that a purely path-based scheme has no direct equivalent for, and a path-based profile is inherently coupled to where a binary or its data physically live — if a path changes, the profile has to change with it, whereas SELinux's label-based approach is less sensitive to path structure specifically.

Key operational commands:

```bash
aa-status
```

Shows which profiles are loaded and, for each, whether it's in **enforce** mode (violations blocked) or **complain** mode (violations logged only — AppArmor's direct equivalent of SELinux's permissive mode).

```bash
aa-complain /usr/sbin/nginx
aa-enforce /usr/sbin/nginx
```

`aa-complain` switches a specific profile into complain mode for diagnostic logging without blocking; `aa-enforce` switches it back to actually enforcing. The same diagnostic value described for SELinux's permissive mode above applies here per-profile: put a profile into complain mode while adjusting it, observe what gets logged, tighten the profile, then switch back to enforce.

## 5. Comparison Table

| Dimension                      | SELinux                                                          | AppArmor                                                                       |
| ------------------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Default distribution family    | RHEL/CentOS/Rocky/Alma, Fedora                                   | Debian, Ubuntu                                                                 |
| Policy model                   | Label-based (type enforcement)                                   | Path-based (per-executable profiles)                                           |
| Learning curve                 | Steeper — requires understanding the type/label model            | Gentler — profiles map directly to filesystem paths                            |
| Flexibility                    | Higher — supports fine-grained, multi-level policy relationships | Lower — coupled to specific paths                                              |
| Diagnostic (non-blocking) mode | Permissive (`getenforce`/`setenforce`)                           | Complain (`aa-complain`/`aa-enforce`)                                          |
| Policy-generation tooling      | `audit2allow` from logged denials                                | Manual profile editing, `aa-genprof`/`aa-logprof` (profile-generation helpers) |

## 6. The "Just Disable It" Anti-Pattern

⚠️ **Warning:** The most common — and most damaging — real-world MAC mistake is treating "SELinux/AppArmor is blocking something" as a problem to eliminate by turning the entire subsystem off (`setenforce 0` left permanently in place, or `SELINUX=disabled` in `/etc/selinux/config`, or purging AppArmor entirely) rather than fixing the specific policy gap causing the denial. This shortcut does resolve the immediate symptom — but it also silently removes the _entire_ MAC layer's protection for that host going forward, not just the one rule that was actually in the way. Every other process on that host now runs with none of the type-enforcement or path-based confinement it previously had, for the sake of unblocking one specific interaction.

**The correct diagnostic approach**, every time:

1. Identify the specific denial — check the audit log (SELinux: `ausearch -m avc`; AppArmor: the kernel log via `dmesg` or `journalctl`, since AppArmor denials surface there) rather than assuming which interaction is being blocked.
2. Determine whether the denied access is actually legitimate and expected, or a sign of something else genuinely wrong (a misconfigured path, an application doing something it shouldn't).
3. If legitimate, generate a narrowly-scoped policy exception — `audit2allow` for SELinux, a targeted profile edit or `aa-logprof`-assisted update for AppArmor — that grants exactly the access observed, not a broad loosening.
4. Only ever consider permissive/complain mode as a **temporary diagnostic stance** while developing that fix, then return to enforcing — never leave a production host permanently in permissive/complain mode as a substitute for actually fixing the policy, since that quietly reproduces the same "no real protection" outcome as disabling it outright, just less visibly.

## 7. Common Misconceptions

1. **"SELinux/AppArmor are just extra permission systems, doing the same job as `chmod`."** They're a categorically different layer — DAC ([§27](../Part4/Section-27-Part4-Standard-Permission-Model.md), `chmod`) is owner-decided; MAC is policy-decided and overrides even the owner and `root`, as described above. Treating them as more of the same thing is the root cause of most "why is `root` still denied" confusion.
2. **"Disabling SELinux/AppArmor is a reasonable quick fix when something's blocked."** This is the "just disable it" anti-pattern described above — it removes the entire subsystem's protection host-wide to resolve one specific, almost always narrowly-fixable denial.
3. **"Permissive/complain mode means the MAC system is off."** It means denials are logged but not blocked — genuinely useful for policy development, as covered above, but it is not equivalent to disabling the subsystem, and it shouldn't be left in place indefinitely in production as if it were a lighter-weight "off."
4. **"AppArmor is objectively worse than SELinux since it's less flexible."** It's a different trade-off, not a strictly worse one — AppArmor's path-based simplicity is a genuine advantage for teams that need MAC protection without the operational overhead of learning SELinux's full label/type model, as described above, and it's the appropriate default for the distribution families that ship it.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between DAC and MAC, in one sentence each?"_
**Model answer:** DAC (standard Unix permissions, [§27](../Part4/Section-27-Part4-Standard-Permission-Model.md)) lets the resource owner decide who can access it — `chmod`/`chown` are the owner exercising that discretion. MAC (SELinux/AppArmor) has a system-wide policy decide access instead, and that policy overrides even the resource owner and `root` — no amount of owner-level permission changes can grant an interaction the loaded MAC policy doesn't permit, as described above.
_What the interviewer is probing for:_ Clean articulation of the core distinction, especially the "overrides root" detail that trips up candidates who think of MAC as just another permission flag.

**🎯 Intermediate:** _"A service running as root can still read files it 'shouldn't' be able to, under standard DAC — why might SELinux still deny it access to a specific file?"_
**Model answer:** Because SELinux's type enforcement, described above, evaluates a second, independent question: is the process's type permitted, by loaded policy, to interact with the target file's type? `root` bypasses DAC's owner checks, but SELinux policy doesn't grant blanket access to `root` by default the way DAC effectively does — if the process's type (say `httpd_t`) has no policy rule permitting interaction with the target file's type (say `user_home_t`), the access is denied regardless of the process's Unix-level privilege. This is the entire point of MAC as a layer above DAC.
_What the interviewer is probing for:_ Confirming the candidate actually understands type enforcement mechanically, not just that "SELinux can block root" as an isolated fact.

**🎯 Senior:** _"A team disabled SELinux fleet-wide six months ago after it 'broke' a deployment, and nobody's revisited it since. How do you approach re-enabling it safely?"_
**Model answer:** I wouldn't just flip it back to enforcing — that risks reproducing whatever broke the original deployment, at scale, with no diagnostic information about what will actually fail. I'd re-enable in permissive mode first, as described above, across a representative subset of hosts, let real production traffic run against it for a meaningful window, and collect every logged denial via `ausearch`. I'd then run `audit2allow` against that log to generate candidate policy modules, review each one for whether the access it grants is actually appropriate (not just accept the tool's output blindly), and build a fleet-specific policy module addressing the legitimate gaps. Only after validating that enforcing mode with the new policy module doesn't reproduce the original breakage would I roll it out fleet-wide, staged rather than all at once. The key discipline is treating the original "SELinux broke something" as an under-investigated policy gap, per the anti-pattern discussion above, not evidence that SELinux itself was the problem.
_What the interviewer is probing for:_ A staged, evidence-driven re-enablement plan rather than either "just turn it back on" or accepting that disabling it was the correct call in the first place.

**🎯 Architect:** _"You're standardizing a mixed fleet — some RHEL-family, some Debian-family hosts — on a consistent MAC hardening baseline. What's your approach given the two ecosystems use different systems?"_
**Model answer:** I wouldn't try to force one system onto both families — SELinux is the RHEL-family default and AppArmor is the Debian-family default for good reasons tied to how each ecosystem's tooling and packages are built and tested against their respective MAC system; fighting that is more operational risk than it's worth. Instead, I'd standardize on the _outcome_, not the implementation: every host, regardless of family, runs its distribution's native MAC system in enforcing/enforce mode as a non-negotiable baseline, with a documented process for handling denials that always goes through the diagnostic path described above (permissive/complain to observe, generate a scoped exception, re-enforce) rather than ever disabling the subsystem as a shortcut. I'd build family-specific runbooks — `audit2allow` workflows for RHEL-family, profile-editing/`aa-logprof` workflows for Debian-family — but hold both to the same policy: no host ships to production with its MAC layer disabled, and any permissive/complain state is treated as a tracked, time-boxed exception, not a silent permanent fallback.
_What the interviewer is probing for:_ Recognizing that standardizing on outcomes/policy discipline is more realistic than forcing tooling uniformity across genuinely different ecosystems, while still holding a firm line against the disable-it anti-pattern described above across the whole fleet.

## 9. Key Takeaways

- DAC ([§27](../Part4/Section-27-Part4-Standard-Permission-Model.md), standard Unix permissions) is owner-decided; MAC is policy-decided and overrides even the resource owner and `root` — this is the single most important distinction in the section.
- SELinux (RHEL-family default) uses label-based type enforcement — a process's type must be explicitly permitted by policy to interact with a resource's type, independent of standard `rwx` permissions.
- Permissive mode (SELinux) and complain mode (AppArmor) log denials without blocking them — genuinely useful for policy development, not a lesser "off" state.
- `audit2allow` generates narrowly-scoped policy modules from observed denials — the correct remediation path, reviewed before installing, rather than a blanket policy loosening.
- AppArmor (Debian-family default) uses simpler path-based profiles tied to specific executables — easier to learn and manage, at the cost of some of SELinux's flexibility.
- Disabling SELinux/AppArmor entirely to resolve a specific denial is a serious anti-pattern — it removes the whole MAC layer's protection host-wide; the correct approach is diagnosing the specific denial and generating a scoped exception.

## 10. Related Concepts & What's Next

This section builds directly on [§27](../Part4/Section-27-Part4-Standard-Permission-Model.md)'s DAC/permission model (Part 4), which it explicitly contrasts against throughout, and extends [§89](./Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)'s least-privilege framing into a genuinely mandatory, policy-enforced layer rather than a discretionary or convention-based one. Denials from either system are exactly the kind of security-relevant event [§93](./Section-93-Part12-Auditing-Auditd-Ausearch-Aureport.md)'s auditd coverage (later this Part) is built to capture and search systematically. [§92](./Section-92-Part12-Kernel-Hardening-Sysctl-Security-Parameters.md), next, moves from process-level MAC policy down to kernel runtime parameters — a separate, complementary hardening layer operating below where SELinux/AppArmor make their decisions.

**Next Section:** [§92](./Section-92-Part12-Kernel-Hardening-Sysctl-Security-Parameters.md) — `Section-92-Part12-Kernel-Hardening-Sysctl-Security-Parameters.md`
