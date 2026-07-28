# Section 95 (Part 12): Secrets Management on Linux Hosts

## 1. The Anti-Patterns First

These are common enough, and damaging enough, that they're worth naming directly before anything constructive — most secrets-management failures are one of these three, not some exotic attack:

- **Hardcoding secrets in application source code committed to version control.** Once a credential lands in a git repository, it's effectively permanent — it exists in every clone, every fork, and every prior commit even after being "removed," since removing a line in a new commit doesn't erase it from history. Treat any secret that touches a commit as compromised and requiring rotation (7), not as a mistake that a follow-up commit fixes.
- **Storing secrets in plain environment variables.** This feels like a reasonable middle ground — it's not in the source code, it's not in a file anyone can casually `cat` — but it's a materially weaker boundary than it appears, covered in the dedicated warning below.
- **Storing secrets in world-readable config files.** A config file with default `644` permissions containing a database password is readable by every local user on the host, which defeats the purpose of having a permission model at all (§25's ownership/permission coverage exists precisely so files can be scoped to who actually needs them).

> ⚠️ **Warning:** Environment variables feel private because they're not visible in a casual `ls`/`cat` of the filesystem, but that's an illusion of privacy, not an actual security boundary. Any process with sufficient privilege can read another process's environment via `/proc/[pid]/environ` — this isn't an edge-case attack, it's a standard, well-known technique. Environment variables are also routinely and accidentally logged — crash dumps, debugging output, CI/CD job logs, and error-reporting tools frequently capture the full process environment without anyone intending secrets to end up there. §71's environment configuration coverage (Part 9 — `/etc/environment`, `profile.d`, systemd environment files) is exactly the mechanism people reach for to inject secrets, and it's precisely the wrong tool for that job even though it's a completely correct tool for non-secret configuration.

## 2. Linux-Native Mechanisms That Do Better

Before reaching for dedicated tooling (3), a meaningful improvement is available using nothing but Linux's existing permission model, applied deliberately:

- **File permissions scoped to `600` (owner read/write only) combined with a dedicated service user.** §67's `User=` directive in a systemd unit already establishes running a service as a narrowly scoped, non-shared account rather than root or a shared generic user — pairing that with a secrets file owned by exactly that user, mode `600`, means only the process that actually needs the secret (and root) can read it. This is a genuinely effective minimum bar, not a token gesture, provided the service user itself isn't shared across unrelated services.
- **Encrypting secrets at rest.** A `600`-permission file still exists in plaintext on disk — recoverable from a stolen disk image, an unencrypted backup, or a compromised root account. Encrypting the secrets store at rest (whether via a dedicated tool's own encryption or filesystem-level encryption) adds a layer that survives some of those scenarios, though it introduces its own key-management question — encrypted with what key, unlocked how, by whom — which is exactly the problem dedicated secrets tooling is built to solve properly.

Both of these are real, meaningful improvements over the anti-patterns in 1 — they're not "insecure basics to skip past" on the way to real tooling. A correctly-scoped, `600`-permission, dedicated-service-user secret is a legitimate approach for a huge share of real deployments, not just a stopgap.

## 3. Dedicated Secrets-Management Tooling (Conceptual)

For environments with more secrets, more services, more people needing scoped access, or a compliance requirement for auditable access, dedicated tooling exists — **HashiCorp Vault**, and cloud-provider-native options like **AWS Secrets Manager** or **Azure Key Vault**. This section covers them at concept level only — deep tool-specific operation is out of scope for a Linux-focused roadmap — but the **operating principle** they share is worth understanding regardless of which specific tool a given environment uses:

**Secrets are fetched at runtime via short-lived, audited access, rather than persisted anywhere on disk long-term.** Instead of a secret sitting in a file indefinitely (even a well-permissioned one), a service authenticates to the secrets manager at startup (or periodically), retrieves what it needs into memory, and the secrets manager logs exactly who/what accessed which secret and when. Many of these systems also support **dynamic secrets** — credentials generated on demand with a short lifetime and automatically revoked, rather than a single long-lived credential that exists indefinitely.

The shift this represents is worth stating plainly: it moves the security boundary from "protect the file" (2's approach) to "protect and audit the access," which scales better once the number of secrets and services needing them grows past what file-permission scoping can reasonably track by hand.

## 4. SSH Keys as a Secrets-Management Case Study

§90's SSH hardening (prior this Part) covered SSH configuration; SSH **private keys** are worth revisiting here specifically as secrets, because the discipline is a concrete, familiar instance of everything above:

- **Private keys should never be shared or copied between users.** A private key is, definitionally, proof of identity — copying it to a second user or a second machine means that identity is no longer singular, which breaks the accountability assumption ("this key = this specific person/service") the whole model depends on.
- **Passphrase-protecting a private key** is defense specifically for the scenario where the key file itself is exposed — a stolen laptop, a misconfigured backup, an accidentally-committed key file. An unprotected private key is immediately usable by whoever obtains it; a passphrase-protected one requires also compromising the passphrase, which is a meaningfully higher bar even though it's not an absolute guarantee.
- **`ssh-agent`** solves the practical friction a passphrase otherwise creates — instead of re-entering a passphrase on every single SSH connection, `ssh-agent` caches the decrypted key in memory for the session, so the passphrase is entered once and the convenience of a plain key is regained without actually storing the key unprotected on disk.

## 5. Hands-On: Auditing a Host for Exposed Secrets

Before trusting that 1's anti-patterns aren't present, it's worth actually checking rather than assuming — a quick, practical sweep:

```bash
# Files under common config directories that are readable beyond their owner
find /etc /opt -type f \( -perm -044 -o -perm -004 \) -iname '*secret*' -o -iname '*password*' 2>/dev/null

# A running process's environment, to confirm what /proc exposes in practice
sudo cat /proc/<pid>/environ | tr '\0' '\n' | grep -i -E 'pass|secret|token|key'
```

The first command looks for plausible secret-named files with group- or world-readable permissions — a fast, imperfect but genuinely useful signal during a host audit. The second demonstrates the exact exposure the Warning in 1 describes: running it against a service's own PID shows precisely what a sufficiently privileged process (or an attacker who's gained that privilege) could already see. Neither replaces a dedicated secret-scanning tool (which typically also scans git history and source trees, not just the running filesystem), but both are fast enough to run as a first pass during any hardening review, and tie directly into the broader host-auditing discipline §93 covers for security-relevant events more generally.

## 6. Secret Rotation

A leaked secret's actual damage is bounded by **how quickly it can be rotated**, not by how well it was originally protected — protection reduces the odds of leakage, rotation limits the blast radius once leakage has already happened, and treating rotation as an afterthought is a structural risk in its own right. Systems worth calling out specifically:

- A **long-lived, rarely-rotated credential** shared across many services or people is a single point of failure — if it leaks, remediation means updating it everywhere it's used simultaneously, which is exactly the kind of coordination problem that causes rotation to get delayed or skipped under pressure.
- Dedicated secrets tooling's dynamic/short-lived secrets (3) sidestep this by design — a credential that expires in an hour has a bounded blast radius even without anyone noticing the leak, purely because rotation is baked into normal operation rather than being an emergency response step.
- Rotation-readiness is worth testing before it's needed — a rotation process only exercised for the first time during an actual incident, under pressure, is far more likely to go wrong than one that's been run routinely.

> 💡 **Tip:** A useful design question when evaluating any secrets-handling approach: "if this specific secret leaked right now, how long would it take to rotate it, and how would we even know it leaked?" A system that can't answer both halves of that question has a real, structural weakness — regardless of how well the secret is currently protected.

## 7. Common Misconceptions

1. **"Environment variables are a reasonably private way to pass secrets."** They're readable via `/proc/[pid]/environ` by anyone with sufficient privilege and are routinely captured accidentally in crash dumps and debug logs — a weaker boundary than it feels like, and §71's environment mechanism is the wrong tool for secrets specifically, despite being correct for ordinary configuration (1).
2. **"A `600`-permission file is a stopgap, not real security."** For a large share of deployments it's a legitimate, effective approach — especially paired with a dedicated service user (§67) — not merely a placeholder on the way to "real" tooling (2).
3. **"Dedicated secrets managers are only about storing secrets more securely."** Their real value is shifting the model from protecting a static file to auditing and time-bounding access — short-lived, audited retrieval rather than long-lived persisted storage — which is a different security property, not just a fancier storage box (3).
4. **"A passphrase on an SSH key is inconvenient friction with no real benefit if `ssh-agent` still needs to be used."** The passphrase and `ssh-agent` solve different problems — the passphrase protects against the key file being stolen while at rest; `ssh-agent` just avoids re-entering the passphrase on every connection during an active session. Both matter (4).
5. **"A quick manual look at `/etc` is enough to confirm no secrets are exposed."** The permission-and-keyword sweep in 5 is a fast first pass, not a substitute for a dedicated secret scanner covering git history and source trees — a manual filesystem check only catches what's currently on disk in an obviously-named file.
6. **"Rotation only matters after you know a secret has leaked."** A secret can leak without ever being detected as leaked — short rotation cycles and dynamic, short-lived credentials bound the damage even in the undetected-leak case, which is exactly why rotation cadence matters independent of whether an incident has been observed (6).

## 8. Tiered Interview Questions

**🎯 Beginner:** _"Why shouldn't application secrets be stored in plain environment variables?"_
**Model answer:** Environment variables are readable by any process with sufficient privilege to inspect another process's `/proc/[pid]/environ`, and they're frequently captured accidentally in crash dumps, debug output, and log aggregation — it feels private because it's not visible in a casual file listing, but it isn't actually a strong boundary. A more scoped approach is a narrowly-permissioned file (`600`, owned by a dedicated service user) or a dedicated secrets manager.
_What the interviewer is probing for:_ Whether the candidate understands the specific mechanism (`/proc/[pid]/environ`) rather than just repeating "env vars are insecure" without being able to say why.

**🎯 Intermediate:** _"What's the practical difference between a `600`-permission secrets file and using something like HashiCorp Vault?"_
**Model answer:** A `600` file scoped to a dedicated service user is a genuinely effective access-control boundary for a single host and a modest number of secrets — only that user (and root) can read it. A dedicated secrets manager shifts the model: secrets aren't persisted long-term at all, they're fetched at runtime via authenticated, audited access, often with short-lived dynamic credentials that expire automatically. The file approach protects the secret; the secrets-manager approach protects and logs the access, and scales better once there are many services, many people needing scoped access, or an audit requirement for who accessed what and when.
_What the interviewer is probing for:_ Recognizing the `600` approach as legitimate rather than dismissing it, while understanding what specifically a dedicated tool adds beyond "more secure storage."

**🎯 Senior:** _"You've found a database credential hardcoded in application source code that's been committed to the repository for six months. What do you do?"_
**Model answer:** I'd treat the credential as compromised regardless of whether there's evidence of actual misuse — six months in version control means it exists in every clone and fork, and removing the line in a new commit doesn't remove it from history. The immediate action is rotating the credential at the source (the database itself), not just editing the code. In parallel, I'd move the new credential to a properly scoped mechanism — a `600` file owned by the service's dedicated user at minimum, or a secrets manager if the environment has one — and audit whether other secrets in the same codebase have the same problem, since one instance of this anti-pattern is a strong signal there are more. I'd also treat this as a process gap worth fixing, not just an isolated incident — pre-commit secret-scanning tooling exists specifically to catch this before it lands in history at all.
_What the interviewer is probing for:_ Correctly prioritizing rotation over cleanup, understanding that git history removal doesn't undo exposure, and thinking about systemic prevention rather than just the one incident.

**🎯 Architect:** _"How would you design secrets handling for a fleet of services with varying sensitivity — some handling payment data, some purely internal tooling?"_
**Model answer:** I wouldn't apply one uniform mechanism — I'd tier by sensitivity and blast radius, similar to how §94's patch cadence was tiered by exposure. High-sensitivity services (payment-data-adjacent) get a dedicated secrets manager with short-lived, dynamic credentials and full access auditing, since the cost of that infrastructure is justified by the risk and likely a compliance requirement. Lower-sensitivity internal tooling can reasonably use the `600`-file-plus-dedicated-service-user model from 2 rather than paying the operational cost of full secrets-manager integration everywhere. Across the whole fleet, I'd enforce the anti-pattern bans in 1 uniformly regardless of tier — no hardcoded secrets in source, no secrets in plain environment variables, no world-readable config — since those are structural mistakes with no tier where they're acceptable. I'd also define and rehearse a rotation process before it's needed, sized to how quickly each tier's secrets need to be rotated if compromised, since untested rotation under real incident pressure is where this kind of design usually fails in practice rather than in the steady state.
_What the interviewer is probing for:_ Risk-tiered design rather than either over-engineering everything with heavy tooling or under-protecting sensitive services, plus recognizing that rotation readiness needs to be validated ahead of time, not assumed.

## 9. Key Takeaways

- The most common secrets failures are hardcoded secrets in version control, plain environment variables, and world-readable config files — worth naming and ruling out explicitly before anything else.
- Environment variables are a weaker boundary than they feel like — readable via `/proc/[pid]/environ` by sufficiently privileged processes and prone to accidental capture in logs/crash dumps — making §71's environment mechanism the wrong tool specifically for secrets.
- A `600`-permission file owned by a dedicated service user (§67's `User=`) is a legitimate, effective minimum-bar mechanism, not just a stopgap on the way to "real" tooling.
- Dedicated secrets managers (Vault, cloud-provider secret stores) share an operating principle worth understanding at concept level: short-lived, audited runtime access rather than long-term persisted storage.
- SSH private keys are a concrete secrets-management case study — never shared between users, passphrase-protected as defense against exposure, with `ssh-agent` solving the resulting convenience problem without weakening that protection.
- A permission-and-keyword sweep of the filesystem and a live process's `/proc/[pid]/environ` is a fast, practical first-pass audit for exposed secrets — not a replacement for dedicated scanning, but a useful habit before assuming a host is clean.
- Rotation speed bounds a leaked secret's blast radius — systems that make rotation slow or hard structurally increase risk, independent of how well the secret was originally protected.

## 10. Related Concepts & What's Next

This section builds directly on §71's environment configuration coverage (Part 9) by identifying it as the wrong mechanism for secrets specifically, extends §67's `User=` service-scoping (Part 9) into the file-permission approach in 2, revisits §90's SSH hardening (prior this Part) through the specific lens of private keys as secrets, and relates to but is distinct from §64's GPG/repository trust model (Part 8) — trust in a signing key and protection of a secret credential are related but separate concerns. §96 (next, and the final section of this Part) covers CIS benchmarks and compliance frameworks — the industry's codification of this Part's controls, including secrets and access hygiene, into a scored, auditable checklist.

**Next Section:** §96 — `Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md`
