# Section 89 (Part 12): Linux Security Model Recap and Threat Landscape

## 1. Overview: Why This Part Starts With a Recap, Not New Material

Part 11 (§80–§88) closed out performance, monitoring, and troubleshooting — the operational side of keeping a Linux fleet running well. This section opens **Part 12 (Security Hardening)** by deliberately not introducing anything brand new yet. Every primitive this section names — standard permissions, `sudo`, PAM, firewalls, package signing — was already built, in full operational depth, across Parts 4, 7, and 8. What's missing so far is the **framing**: none of those earlier sections asked "what is this actually defending against, and how does it relate to the others?" That framing is this section's entire job, and it's the lens the rest of Part 12 (§90–§96) is built on.

Treat this section as a bridge: it reorganizes material you already have into a security-specific mental model, then Part 12 spends the next seven sections applying that model concretely — SSH hardening (§90), mandatory access control (§91), kernel-level parameters (§92), auditing (§93), patch management (§94), secrets (§95), and compliance frameworks (§96).

## 2. Defense in Depth: Layers, Not a Single Wall

The single most important structural idea in this section is **defense in depth**: no individual control on a Linux host is assumed to be sufficient on its own. Each layer exists on the assumption that the layers around it can, and eventually will, fail or be bypassed — the goal is that a single failure doesn't equal a full compromise.

Walking the layers already built in this knowledge base, from the resource level outward to the network edge:

- **Discretionary access control (§27).** Standard Unix `rwx` permissions are the innermost layer — the resource owner decides who can read, write, or execute a given file. This is the baseline every process and every user interaction passes through, and it's "discretionary" precisely because the owner (not a system-wide policy) makes the call — a distinction §91 revisits directly when contrasting this with mandatory access control.
- **Privilege escalation control via `sudo` (§31).** Rather than routine work happening as `root`, `sudo` lets specific users perform specific privileged actions, logged and scoped via `/etc/sudoers` — the layer that limits the blast radius of a compromised unprivileged account and creates an audit trail for privileged actions.
- **PAM (§32).** The pluggable authentication framework sitting underneath login, `sudo`, `su`, and SSH — a system-wide policy layer for how authentication and authorization decisions actually get made (password complexity, account lockout after failed attempts, time-of-day login restrictions), independent of any one tool implementing its own auth logic.
- **Network-layer controls via firewalls (§54).** `iptables`/`nftables`/`firewalld`/`ufw` decide what traffic reaches a host at all, before any application-layer or user-layer control ever gets a chance to matter — the layer that determines whether an attacker can even reach a vulnerable service in the first place.

> 💡 **Tip:** When asked to evaluate "is this server secure," resist answering as if there's one control that settles the question. The useful answer names which layers are present, which are absent, and — critically — what a failure of any single layer would expose given the layers still standing around it. A host with a locked-down firewall but permissive `sudoers` is exposed differently than one with the reverse; "secure" without qualification is rarely a complete answer in a senior-level conversation.

None of these layers is sufficient alone. A perfect firewall doesn't help if an authenticated user has unrestricted `sudo`. Flawless file permissions don't help if the network layer lets an attacker reach an unpatched, internet-facing service directly. The value is cumulative, and Part 12's remaining sections each add or refine one more layer onto this stack: mandatory access control (§91) sits above §27's discretionary permissions, kernel-level `sysctl` hardening (§92) sits below the userland layers entirely, and auditing (§93) doesn't prevent anything but makes every other layer's failures visible after the fact.

## 3. The Realistic Threat Landscape for a Production Linux Server

Threat modeling in the abstract is less useful than naming the actual, recurring categories of compromise a production Linux host realistically faces. None of these are exotic — they are the categories that show up in the overwhelming majority of real-world incident postmortems:

- **Unpatched software and known CVEs.** A vulnerable package version with a public exploit is one of the most common initial-access vectors in practice — not because attackers are targeting a specific organization, but because automated scanning constantly probes the internet for known-vulnerable service versions. Patch and vulnerability management (§94) exists specifically to close this window before it gets exploited.
- **Weak or reused credentials, and exposed SSH.** Password-based SSH access, especially with weak or reused passwords, is a perennial target for credential-stuffing and brute-force automation. §90 covers eliminating this vector at the SSH layer specifically, in far more depth than this section attempts.
- **Misconfigured services exposed to the internet.** A database, admin panel, or internal tool bound to `0.0.0.0` instead of a loopback or private interface, with no firewall rule restricting access, is a self-inflicted exposure independent of any actual software vulnerability — the service does exactly what it was configured to do, just to an audience nobody intended.
- **Supply-chain risk via untrusted packages.** Installing software from an unverified source, or trusting a repository without validating its GPG signing key, means the compromise doesn't need to happen on your host at all — it can happen upstream, in a package you installed in good faith (§64 covers repository trust and GPG signing in depth; the trust chain established there is exactly what supply-chain risk erodes when skipped).
- **Insider and lateral-movement risk.** Once any single host is compromised, the interesting question shifts from "how did they get in" to "what can they now reach." Overly broad `sudo` grants, shared credentials across hosts, and flat network topology with no segmentation all turn a single-host compromise into a fleet-wide one — this is the concrete, practical argument for least privilege (4) and for architectural patterns like bastion hosts (§90) that concentrate and monitor access rather than leaving it diffuse.

⚠️ **Warning:** None of these categories is rare or theoretical — they are the day-to-day background noise of running anything reachable from the internet. Treating them as edge cases rather than baseline expectations is itself a common and costly misjudgment; hardening work in this Part should be planned assuming all five categories apply to any given host until proven otherwise.

## 4. The CIA Triad: A Framework for What a Control Actually Protects

The **CIA triad** — **Confidentiality**, **Integrity**, **Availability** — is the standard vocabulary for reasoning precisely about what a given security control is actually for, rather than treating "security" as one undifferentiated goal.

| Property            | Meaning                                                                         | Example control from this knowledge base                                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Confidentiality** | Only authorized parties can read the data or access the resource                | File permissions (§27) restricting a config file containing credentials to its owning user; SSH key-based auth (§56) preventing credential interception     |
| **Integrity**       | Data or system state hasn't been tampered with, and any tampering is detectable | GPG package signature verification (§64) confirming a package wasn't altered in transit; file integrity concepts extended by auditd (§93)                   |
| **Availability**    | The system or resource is actually usable when a legitimate party needs it      | Firewall rate-limiting and Fail2ban (§90) protecting a service from being knocked offline by brute-force or flood traffic; redundancy patterns from Part 14 |

This framework matters practically because a given control usually protects one or two legs of the triad, not all three — `PasswordAuthentication no` on SSH is almost entirely a confidentiality/integrity control (it prevents credential compromise and unauthorized access) and does very little for availability, while Fail2ban leans more toward availability (keeping a service usable under attack) with a confidentiality side-benefit. Being able to say precisely which leg a proposed control addresses is what separates a checklist-following response from an architect-level one.

## 5. Least Privilege: The Load-Bearing Idea of This Entire Part

If Part 12 has one unifying principle, it is the **principle of least privilege**: every user, process, and service should hold the minimum set of permissions required to do its job, and nothing more. This isn't a new concept introduced here — it's the concept already underneath several sections built earlier in this knowledge base, named explicitly now because Part 12 is going to keep extending it into new layers:

- `sudo` scoping (§31) is least privilege applied to human privilege escalation — a user gets exactly the commands `/etc/sudoers` grants, not blanket `root`.
- Service `User=`/`Group=` directives in systemd unit files (§67) are least privilege applied to services — a web server or application process runs as an unprivileged, purpose-specific account rather than `root`, so a compromised service process inherits only that account's limited access rather than the whole system's.
- SELinux and AppArmor (§91) are least privilege enforced at the mandatory-access-control layer — even a process running as `root` can be confined to only the specific files, sockets, and capabilities its policy names, which is a materially stronger guarantee than discretionary permissions alone can offer.

> 💡 **Tip:** When evaluating any proposed configuration change in a security review, "does this grant more than is strictly needed" is a more useful default question than "does this technically work." A working configuration that over-grants access is a latent liability even when nothing has gone wrong yet — the risk shows up later, at exactly the moment some other layer of defense in depth (2) has already failed.

## 6. Walking a Single Incident Through the Layers

The abstractions in 2–5 are easiest to internalize against one concrete scenario, walked layer by layer, rather than as separate bullet points.

Suppose an internet-facing application server is running a web service with an unpatched, known-CVE vulnerability (3) that allows remote code execution. Here's how each layer this section named either fails, holds, or limits the outcome:

1. **Network layer (firewall, §54).** If the firewall permits inbound traffic on the vulnerable service's port from anywhere on the internet, this layer does nothing to stop the initial exploit — it was never designed to inspect application-layer request content, only to decide what reaches the port at all.
2. **Discretionary permissions (§27).** Once the attacker has code execution as the service's own user account, DAC permissions determine what that account can directly read or write — if the service correctly runs as an unprivileged, purpose-specific account (§89's least-privilege framing extended into §67's `User=`/`Group=` directives), the attacker's immediate reach is limited to that account's own files, not the whole filesystem.
3. **Mandatory access control (§91).** If SELinux or AppArmor is enforcing a tight policy for that service's process type, the attacker's code execution may be further confined even beyond what DAC alone would allow — unable to read files or open sockets the policy doesn't explicitly permit, even though the compromised process is technically running with valid Unix-level credentials.
4. **Privilege escalation control (`sudo`, §31).** If the attacker attempts to escalate to `root` from the compromised account, a correctly scoped `sudoers` file with no unnecessary grants for that account stops the escalation cold — this is exactly where an over-permissioned `sudoers` entry turns a contained compromise into a full host takeover.
5. **Lateral movement (network segmentation, §90's bastion pattern).** If the compromised host has no direct SSH or trust relationship to other hosts, the compromise stays contained to this one machine rather than propagating across the fleet.
6. **Visibility (auditd, §93).** Regardless of how far the compromise gets, audit logging is what eventually reveals it happened at all, and gives the specific trail needed to scope the actual damage.

Every one of these is a point where the _same_ initial vulnerability either does or doesn't turn into a catastrophic, fleet-wide incident — and that's the concrete, operational meaning of "defense in depth" (2) beyond the abstract definition: it's the difference between an unpatched CVE causing a contained, quickly-detected incident on one host versus an undetected, unrestricted compromise of the entire environment.

## 7. What the Rest of Part 12 Applies This To

This recap sets up the remaining seven sections as concrete applications of the principles above, not a random grab-bag of security topics:

- **§90 (SSH Hardening and Bastion Host Patterns)** — closes the credential/exposed-SSH threat category (3) at full depth, well beyond §56's basic hardening mention.
- **§91 (SELinux and AppArmor)** — extends least privilege (5) into a mandatory-access-control layer that sits above §27's discretionary permissions.
- **§92 (Kernel Hardening and sysctl)** — pushes defense in depth (2) down to the kernel-parameter layer.
- **§93 (Auditing)** — doesn't prevent compromise but gives visibility into every other layer, essential once insider/lateral-movement risk (3) is taken seriously.
- **§94 (Vulnerability and Patch Management)** — closes the unpatched-CVE threat category (3) systematically rather than reactively.
- **§95 (Secrets Management)** — a confidentiality-focused (4) control for credentials specifically.
- **§96 (CIS Benchmarks)** — a comprehensive, authoritative checklist tying all of the above back to an external compliance framework.

## 8. Common Misconceptions

1. **"We have a firewall, so the server is secure."** A firewall addresses one layer (network reachability) of defense in depth (2) — it says nothing about what happens once a permitted connection is established, what an authenticated user can then do, or whether the software behind the firewall is patched (3).
2. **"Least privilege is only about `sudo` and user accounts."** It's a principle applied at every layer this Part covers — service accounts (§67), mandatory access control policy (§91), and even kernel capability restrictions all instantiate the same idea (5), not just human privilege escalation.
3. **"The CIA triad is academic, not practically useful."** In practice it's a fast diagnostic for scoping a control's actual purpose — asking "which leg of the triad does this protect" surfaces gaps (a control that's strong on confidentiality but does nothing for availability) that a vague "is it secure" framing misses (4).
4. **"Insider risk means a malicious employee."** The more common practical case is a legitimate account or host being compromised externally and then used for lateral movement — insider/lateral-movement risk (3) is about what a single compromised credential or host can reach, regardless of whether the original actor was ever a trusted insider.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What does 'defense in depth' mean, and why isn't one strong control enough?"_
**Model answer:** Defense in depth means layering multiple independent security controls so that the failure of any single one doesn't result in a full compromise — file permissions, `sudo` scoping, PAM policy, and firewall rules (2) each cover a different part of the attack surface. One strong control is never enough because every control has failure modes or blind spots; the point is that the layers around it catch what it misses.
_What the interviewer is probing for:_ Whether the candidate can name concrete layers rather than repeating the phrase as a slogan.

**🎯 Intermediate:** _"Walk through the CIA triad and give a Linux example of a control for each."_
**Model answer:** Confidentiality is about restricting who can read data or access a resource — file permissions (§27) and SSH key auth (§56) are examples. Integrity is about detecting or preventing unauthorized tampering — GPG package signature verification (§64) is the clearest example in this KB. Availability is about the system staying usable for legitimate users — Fail2ban and firewall rate-limiting (§90) protect availability against brute-force and flood traffic specifically (4).
_What the interviewer is probing for:_ Precision — can the candidate map a specific control to the specific property it protects, rather than saying every control does all three.

**🎯 Senior:** _"A junior engineer says 'least privilege' just means being stingy with `sudo` access. How would you correct and expand that?"_
**Model answer:** `sudo` scoping is one instance of least privilege, not the whole concept. The same principle applies to service accounts (running a web server as an unprivileged `User=` in its unit file rather than `root`, §67), to mandatory access control policy (SELinux/AppArmor confining even a `root` process to specific resources, §91), and to network access (a bastion host pattern limiting which hosts can even attempt SSH, §90). The unifying idea is minimum necessary access at every layer, not just the sudoers file — treating it as a single-file concern misses most of where it actually matters in a production fleet (5).
_What the interviewer is probing for:_ Whether the candidate can generalize a principle across multiple subsystems rather than anchoring it to one familiar tool.

**🎯 Architect:** _"You're doing a security review of an unfamiliar production fleet. How do you structure the review using the concepts in this section?"_
**Model answer:** I'd walk the defense-in-depth layers (2) systematically rather than jumping straight to a tool-by-tool checklist: what does the network layer permit (firewall rules, exposed ports), what does the authentication layer require (SSH configuration, PAM policy, password vs. key auth), what can an authenticated user or service actually do (sudoers scope, service account privileges, file permissions), and is there a mandatory-access-control layer on top of all that. In parallel, I'd map the realistic threat landscape (3) against the fleet specifically — patch currency, credential exposure, service misconfiguration, package provenance, and blast radius if any single host were compromised. For every control I do find, I'd ask which leg of the CIA triad (4) it actually protects, since a fleet can look well-defended on paper while being lopsided — strong confidentiality controls with no availability protection, for instance. Underneath all of it, I'd be checking for least privilege violations (5) specifically, since over-granted access is the single most common way a contained incident turns into a fleet-wide one.
_What the interviewer is probing for:_ Structured, framework-driven review methodology rather than an ad hoc list of things to check — and explicit use of the vocabulary (defense in depth, CIA triad, least privilege) to organize findings rather than just naming tools.

## 10. Key Takeaways

- This section recaps and reframes material already built in Parts 4, 7, and 8 through a security lens — defense in depth, CIA triad, least privilege — rather than introducing new tools.
- Defense in depth means no single control (permissions, `sudo`, PAM, firewalls) is assumed sufficient alone; each layer's value depends on the layers around it (2).
- The realistic threat landscape for a production host centers on five recurring categories: unpatched CVEs, weak/exposed credentials, misconfigured exposed services, supply-chain/package trust risk, and insider/lateral-movement risk (3).
- The CIA triad (Confidentiality, Integrity, Availability) is the framework for precisely naming what a given control actually protects, rather than treating security as one undifferentiated goal (4).
- Least privilege is the single most load-bearing idea in this Part — it recurs in `sudo` scoping, service accounts, and mandatory access control, not just one configuration file (5).
- §90–§96 each apply one or more of these principles concretely — this section is the map, not the destination.

## 11. Related Concepts & What's Next

This section reframes §27 (standard permissions), §31 (sudo), §32 (PAM), and §54 (firewalls) from Part 4 and Part 7, and previews §64's GPG/repository trust from Part 8 in the supply-chain risk category (3). It sets up every remaining section of Part 12: §90 (SSH hardening and bastion patterns) closes the credential-exposure threat category at full depth; §91 (SELinux/AppArmor) extends least privilege into mandatory access control; §92 (kernel hardening) pushes defense in depth to the kernel-parameter layer; and §93–§96 cover auditing, patch management, secrets, and compliance. §90, next, is the first concrete application.

**Next Section:** §90 — `Section-90-Part12-SSH-Hardening-Bastion-Host-Patterns.md`
