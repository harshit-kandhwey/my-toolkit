# Section 90 (Part 12): SSH Hardening and Bastion Host Patterns

## 1. Overview: Closing the Loop [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) Opened

[§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) introduced SSH's architecture — key-based authentication, `~/.ssh/config`, tunneling — and covered a handful of hardening settings at baseline depth, explicitly deferring "full SSH hardening depth, including bastion host architecture patterns in production" to this section. This is that section. Nothing here contradicts [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md); it goes deeper into the same `sshd_config` directives, adds several [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) didn't cover at all, and then builds out the bastion host pattern as a network-topology decision rather than a single configuration line.

The throughline connecting everything in this section is [§89](./Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)'s threat-landscape category of weak/reused credentials and exposed SSH: SSH is very often the single most externally-reachable, most frequently attacked service on a Linux host, and it is also the door through which nearly every other administrative action eventually happens. Hardening it well is disproportionately valuable relative to the effort involved.

## 2. `sshd_config` Hardening Checklist, With Reasoning

Every directive below lives in `/etc/ssh/sshd_config` on the server. The checklist matters less than the reasoning behind each line — a candidate who can recite the directives but not explain what specific risk each one closes hasn't actually internalized the material.

### 2.1 `PermitRootLogin no`

Disables direct SSH login as `root` entirely. [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) already covered the audit-trail argument — an administrator must log in as a named, unprivileged user and escalate via `sudo` ([§31](../Part4/Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)) — but it's worth restating precisely why that matters operationally: every privileged action taken after that point is tied to an individual account in `sudo`'s log, not to an undifferentiated `root` session that could have been anyone. It also removes `root` as a guessable, universally-present username — every Linux host has a `root` account by definition, so any brute-force or credential-stuffing attempt against SSH can always assume that username exists, whereas a named account requires the attacker to also guess or discover a valid username first.

### 2.2 `PasswordAuthentication no`

Disables password-based login outright, requiring key-based authentication for every connection. The reasoning is categorical, not incremental: a private key has no meaningful "guess the key" attack space the way a password does, so this single setting doesn't just make brute-forcing harder — it removes the entire attack category. Automated credential-stuffing bots that hammer SSH with leaked password lists simply have nothing to try.

### 2.3 `AllowUsers` / `AllowGroups`: explicit allowlisting

```
AllowUsers deploy harshit
AllowGroups ssh-access
```

Rather than "every account on the box may attempt SSH login, subject to authentication succeeding," these directives invert the default to "only these specific users or group members may attempt SSH login at all" — everyone else is rejected before authentication is even evaluated. This matters because a host accumulates service accounts, application accounts, and one-off accounts over its lifetime, most of which have no legitimate reason to ever SSH in directly; an explicit allowlist means a newly created or forgotten account can't become an unintended SSH entry point just because nobody thought to lock it down individually.

### 2.4 `MaxAuthTries`

```
MaxAuthTries 3
```

Caps the number of authentication attempts permitted within a single SSH connection before the server disconnects. This is a narrower, connection-level throttle that complements (rather than replaces) something like Fail2ban, covered in operational depth below — it limits how much any one connection attempt can probe, independent of whether a broader IP-level ban has kicked in yet.

### 2.5 Idle timeout: `ClientAliveInterval` / `ClientAliveCountMax`

```
ClientAliveInterval 300
ClientAliveCountMax 2
```

`ClientAliveInterval` tells `sshd` to send a keep-alive probe to the client every N seconds; `ClientAliveCountMax` sets how many consecutive unanswered probes are tolerated before the server terminates the connection. Together they define an idle timeout — `300 × 2` means an unresponsive session is dropped after roughly 10 minutes. The security value is closing the window where an unattended, still-authenticated terminal session (a laptop left unlocked, a session forgotten open on a shared jump box) remains a live, fully-privileged access path indefinitely.

### 2.6 Disabling unused authentication methods

`sshd_config`'s `AuthenticationMethods` and per-method toggles (`ChallengeResponseAuthentication`, `KerberosAuthentication`, `GSSAPIAuthentication`, and similar) should be explicitly disabled if not actually in use, rather than left at distribution defaults. Every enabled authentication method is additional attack surface and additional configuration to reason about — a method nobody uses but that remains enabled is pure downside with no operational upside.

> ⚠️ **Warning:** This is the same lockout discipline [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) already established, and it applies with equal force here: never disable password authentication, tighten `AllowUsers`, or restart `sshd` without first confirming key-based login already works and testing the change from a second, still-open session. `MaxAuthTries` set too aggressively, or an `AllowUsers` list that omits an account someone still needs, are just as capable of causing a lockout as the settings [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) already warned about.

## 3. The Bastion Host / Jump Host Pattern

The `sshd_config` hardening in 2 makes each individual host harder to compromise via SSH. The **bastion host pattern** is a different, complementary layer: it changes the network topology so that most hosts are never reachable via SSH from the internet at all, regardless of how well or poorly each one's `sshd_config` is tuned.

**The pattern:** a single host — the bastion, sometimes called a jump host — is the _only_ system in the environment with a direct, internet-facing SSH listener. Every other host (application servers, databases, internal tooling) accepts SSH connections only from the bastion's internal IP address, enforced at the firewall layer ([§54](../Part7/Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)) on each of those hosts. An administrator or engineer who needs to reach an internal host must first authenticate to the bastion, then connect onward from there.

**Why this is a meaningful security improvement, not just an inconvenience:**

- **One chokepoint instead of many independent exposures.** Instead of every host on the fleet individually needing airtight SSH hardening, patch currency, and monitoring, there is exactly one host carrying that responsibility at the network edge. Concentrating the exposure makes it tractable to genuinely harden and monitor thoroughly — spreading the same effort thin across every host in the fleet is both more work and more likely to have at least one host fall behind.
- **A single, well-audited point for access logging.** Every session that eventually reaches any internal host passes through the bastion first, which means the bastion's authentication log is a comprehensive record of who accessed the environment and when — far more tractable to monitor and alert on than aggregating logs from every individual host.
- **Reduced blast radius from any one internal host's own misconfiguration.** If an internal application server's `sshd_config` is accidentally left permissive, it still isn't reachable from the internet at all — the firewall rule restricting SSH ingress to the bastion's IP is the actual control preventing exploitation, not that host's own SSH hardening.

The trade-off, worth stating plainly: the bastion becomes the single highest-value target in the entire environment. A compromised bastion is effectively a compromised path to everything behind it, which is exactly why it deserves the _most_ hardening effort in the fleet, not the least — full `sshd_config` hardening from the checklist above, Fail2ban tuning as covered below, and priority placement in any auditing or alerting pipeline ([§93](./Section-93-Part12-Auditing-Auditd-Ausearch-Aureport.md)).

## 4. `ProxyJump` / `-J`: The Client-Side Mechanic

[§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) already introduced `ProxyJump` in `~/.ssh/config` as the modern way to make bastion routing transparent — worth restating here specifically because it's the piece that makes the bastion pattern described above usable day-to-day rather than a manual-double-hop burden:

```
Host bastion
    HostName bastion.example.com
    User deploy
    IdentityFile ~/.ssh/prod-bastion

Host app-server-1
    HostName 10.20.30.5
    User deploy
    ProxyJump bastion
```

`ssh app-server-1` transparently opens a connection to `bastion` first, then tunnels a second SSH connection to `app-server-1` through it — one command, one multiplexed logical flow, with the topology documented in the config file rather than re-typed from memory. The equivalent one-off flag is `-J`:

```bash
ssh -J deploy@bastion.example.com deploy@10.20.30.5
```

`-J` is useful for a one-time connection through a bastion that doesn't yet have a `~/.ssh/config` entry; `ProxyJump` in the config file is the right choice for anything used routinely. Either way, the client-side mechanic doesn't change the security properties established by the bastion pattern described above — it just makes using the pattern as low-friction as connecting directly would be.

## 5. Fail2ban in Operational Depth

[§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) mentioned Fail2ban briefly as a complementary tool that watches auth logs and firewalls offending IPs; this section covers how it actually works operationally.

Fail2ban runs as a daemon that tails authentication-relevant log files (SSH's auth log being the canonical example) using regex-based **filters** to recognize a failed login attempt. When a given source IP accumulates enough failures within a configured time window, Fail2ban triggers a **jail action** — most commonly inserting a firewall rule ([§54](../Part7/Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)) that drops or rejects further traffic from that IP for a configured ban duration. The mental model: it's an automated, log-driven extension of firewall policy, reacting to observed behavior rather than a fixed, pre-configured allow/deny list.

This closes a real gap that the per-connection `MaxAuthTries` limit described above doesn't: `MaxAuthTries` limits attempts _within one connection_, but an attacker can simply open a new connection after being disconnected. Fail2ban operates across connections, at the IP level, which is what actually stops sustained brute-force or credential-stuffing campaigns rather than just slowing down any single attempt.

> ⚠️ **Warning:** Fail2ban's entire mechanism depends on accurately parsing log lines to recognize what counts as a "failure" — a filter regex that doesn't match the actual log format in use (after a distro upgrade that changes log formatting, for instance) silently stops protecting anything, with no obvious symptom until an incident reveals the gap. In the other direction, an overly aggressive or misconfigured jail (too few attempts, too long a ban duration, a filter that misfires on legitimate retry patterns like a flaky VPN reconnecting) can lock out real users or even automated systems like a monitoring agent that legitimately reconnects on a schedule. Treat Fail2ban configuration as something to validate against real log samples before trusting it in production, and always confirm there's an out-of-band access path (console access, a secondary bastion) in case a jail misfires against an administrator's own IP.

## 6. Hands-On: Auditing Current SSH Exposure on a Host

### 6.1 Confirm which hardening directives are actually active

**Purpose:** Verify the running configuration matches intent, since `sshd_config` can have duplicate or overridden directives, and the file on disk isn't proof of what's actually in effect until confirmed.

```bash
sshd -T | grep -Ei 'permitrootlogin|passwordauthentication|maxauthtries|clientaliveinterval'
```

**Key flags:** `-T` dumps `sshd`'s fully resolved effective configuration (after processing includes and any duplicate/overriding directives), rather than just echoing the raw file — the authoritative source for "what will `sshd` actually do."

**Common errors:** Reading `sshd_config` directly with `cat` and assuming that's the effective configuration — later directives, included files, or `Match` blocks can override what appears earlier in the file, which `sshd -T` accounts for and a raw file read does not.

### 6.2 Confirm the bastion-only firewall rule on an internal host

**Purpose:** Verify that an internal host genuinely only accepts SSH from the bastion's IP, not from anywhere — the actual control that makes the bastion pattern described above real rather than aspirational.

```bash
sudo iptables -L -n | grep -A2 'dpt:22'
```

**Expected output:** A rule permitting port 22 only from the bastion's specific internal IP (or CIDR), with a default-deny for everything else on that port — not a blanket `ACCEPT` for all sources, which would mean the bastion pattern exists in documentation but not in enforced network reality.

**Troubleshooting:** If the rule allows SSH from any source, the host is directly reachable despite the intended topology — this is exactly the kind of drift [§89](./Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)'s "misconfigured services exposed to the internet" threat category describes, and it should be treated as a live exposure, not a documentation mismatch.

## 7. Common Misconceptions

1. **"The bastion pattern is just `ProxyJump` — a client-side convenience feature."** `ProxyJump`, covered above, is how a client _uses_ the pattern conveniently; the actual security value comes from the firewall-enforced network topology described above restricting internal hosts to bastion-only SSH ingress. A client using `ProxyJump` against a host that also accepts direct internet SSH gets none of the pattern's real benefit.
2. **"Fail2ban replaces the need for `PasswordAuthentication no`."** They address different things — disabling password auth removes an entire attack category outright, as described above; Fail2ban is a detection-and-response layer that helps against whatever attack surface remains (including against a mistakenly-still-open password auth path), not a substitute for closing it.
3. **"A non-default SSH port makes `AllowUsers` or `MaxAuthTries` unnecessary."** As [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) established, a non-default port is noise reduction against indiscriminate scanning, not a real access control — it does nothing against a targeted attacker and provides no protection at all against an internal or already-network-adjacent threat, which is exactly what the `AllowUsers` allowlisting and the bastion pattern described above actually address.
4. **"The bastion just needs to be reachable — its own hardening matters less since it's 'just a jump point.'"** The opposite is true: concentrating access into one host concentrates risk into that host — the bastion warrants the _most_ hardening and monitoring in the fleet, not the least, since compromising it is equivalent to compromising the path to everything behind it.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"Why does `PasswordAuthentication no` eliminate brute-force attacks against SSH rather than just slowing them down?"_
**Model answer:** Brute-forcing a password works by guessing from a finite, human-memorable space that automation can enumerate at scale. A private key has no comparable guessable structure — there's no meaningful "guess the key" attack space to enumerate. Disabling password auth doesn't make guessing harder; it removes the entire attack category, since key-based auth is the only method left, and possession of the private key can't be brute-forced, as the categorical nature of disabling password authentication above establishes.
_What the interviewer is probing for:_ Understanding the categorical (not incremental) nature of this control, not just "keys are stronger than passwords."

**🎯 Intermediate:** _"What does a bastion host actually protect against that hardening every individual host's `sshd_config` doesn't already cover?"_
**Model answer:** Per-host `sshd_config` hardening as described above reduces each host's individual attack surface, but it depends on every single host in the fleet being configured correctly and staying that way — one host falling behind (a missed patch to configuration management, a manually provisioned box that skipped the baseline) reintroduces exposure. A bastion host changes the network topology itself: internal hosts simply aren't reachable via SSH from the internet at all, regardless of their own `sshd_config` state, because the firewall only permits SSH ingress from the bastion's IP. It converts "every host must be perfectly configured" into "one host, which gets disproportionate hardening and monitoring attention, is the only exposed surface."
_What the interviewer is probing for:_ Distinguishing host-level hardening from network-topology-level risk reduction — a candidate who only names `sshd_config` settings hasn't understood what the bastion pattern specifically adds.

**🎯 Senior:** _"Your Fail2ban jail for SSH just banned a legitimate engineer's IP mid-incident. Walk through your immediate response and your longer-term fix."_
**Model answer:** Immediately, I'd need an access path that doesn't depend on the now-banned IP or even on SSH working at all — console access or a cloud provider's serial console — to manually clear the ban (removing the firewall rule Fail2ban inserted) and get the engineer back in, since time matters mid-incident. Longer term, I'd review the jail's actual trigger conditions against the real log format and real user behavior: was the ban threshold too aggressive for a legitimate retry pattern (a flaky connection causing repeated reconnect attempts), or did a log format change cause the filter to misfire on non-failure lines counted as failures? I'd also confirm whether other engineers have a genuinely reliable out-of-band path in general, not just for this incident, since a misconfigured jail locking out legitimate access is a known failure mode of this exact tool, as described above, and shouldn't require rediscovering the fix live during every occurrence.
_What the interviewer is probing for:_ Calm incident response with a working out-of-band access path already in mind, plus follow-through into root-causing the jail misconfiguration rather than just clearing the immediate ban and moving on.

**🎯 Architect:** _"Design the SSH access model for a fleet of 200 hosts across multiple environments (dev, staging, prod), balancing engineer productivity against the hardening principles in this section."_
**Model answer:** I'd deploy a bastion per environment (or per network segment within an environment, for larger blast-radius separation) rather than one global bastion — a compromised dev bastion shouldn't be a path to prod. Every non-bastion host gets full `sshd_config` hardening from the checklist above as a baseline regardless of the bastion pattern, since defense in depth ([§89](./Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)) means the bastion isn't the only layer — `PermitRootLogin no`, `PasswordAuthentication no`, and `AllowUsers`/`AllowGroups` scoped to the specific accounts that legitimately need access to that host. Firewall rules on every non-bastion host restrict SSH ingress to that environment's bastion IP specifically. Engineers get `ProxyJump` entries in `~/.ssh/config` per environment, as covered above, so the productivity cost is close to zero despite the added hop. Each bastion gets the heaviest hardening and monitoring investment in the fleet — Fail2ban tuned and validated against real log samples as covered above, and its auth events prioritized in whatever centralized logging/auditing pipeline exists ([§93](./Section-93-Part12-Auditing-Auditd-Ausearch-Aureport.md)) — since it's the single highest-value target across the whole design. I'd also insist on a documented, tested out-of-band access path per environment before any of this ships, precisely because both SSH hardening and Fail2ban carry real lockout risk if something is misconfigured.
_What the interviewer is probing for:_ Multi-environment blast-radius thinking (not just one bastion for everything), correctly layering host-level hardening underneath the topology-level bastion control rather than treating them as substitutes, and proactive lockout mitigation baked into the design rather than an afterthought.

## 9. Key Takeaways

- `PermitRootLogin no` and `PasswordAuthentication no` remain the two highest-value `sshd_config` controls, closing an entire credential-guessing attack category and forcing a named-account audit trail, as covered above.
- `AllowUsers`/`AllowGroups`, `MaxAuthTries`, and idle-timeout directives (`ClientAliveInterval`/`ClientAliveCountMax`) each close a narrower, specific gap that the two headline controls don't address alone, as covered above.
- The bastion host pattern is a network-topology control, not a client convenience — it concentrates SSH exposure into one heavily-hardened, heavily-monitored host, making per-host hardening drift far less catastrophic.
- `ProxyJump`/`-J` make the bastion pattern transparent to daily use, but the security value comes from the enforced network topology, not the client flag.
- Fail2ban closes the cross-connection gap that per-connection controls like `MaxAuthTries` can't — but it depends entirely on accurate log parsing and correct jail tuning, with real lockout risk if misconfigured.
- The bastion, as the single highest-value target in a fleet using this pattern, warrants the _most_ hardening effort, not the least.

## 10. Related Concepts & What's Next

This section is the full-depth continuation [§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) explicitly promised, and it builds directly on [§89](./Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)'s threat-landscape framing (weak/exposed credentials) and defense-in-depth model. It connects forward to [§93](./Section-93-Part12-Auditing-Auditd-Ausearch-Aureport.md) (auditd), since SSH access — especially through a bastion — is one of the most natural and highest-value targets for detailed audit logging, and to [§31](../Part4/Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)'s `sudo` model, since `PermitRootLogin no` makes `sudo` the mandatory post-login privilege path rather than an alternative to direct root access. [§91](./Section-91-Part12-SELinux-AppArmor-Mandatory-Access-Control.md), next, moves from network/authentication hardening to mandatory access control at the OS policy layer.

**Next Section:** [§91](./Section-91-Part12-SELinux-AppArmor-Mandatory-Access-Control.md) — `Section-91-Part12-SELinux-AppArmor-Mandatory-Access-Control.md`
