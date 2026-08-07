# Section 64 (Part 8): Managing Repositories and GPG Signing Keys

## 1. Overview: Where This Section Sits

[§59](./Section-59-Part8-Package-Management-Concepts.md) introduced the trust model behind package management in the abstract — a repository is a claim about where software comes from, and dependency resolution happily installs whatever that repository serves without asking whether it should be trusted. [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md) and [§61](./Section-61-Part8-RHEL-Tooling-Rpm-Yum-Dnf.md) then covered apt's and dnf's repository configuration files as syntax: `sources.list` entries, `.repo` file fields, what each line means mechanically. This section is the deliberate return to that trust question, now with the actual mechanism that answers it: **GPG signing**, and the concrete files and commands that add a repository, import its key, and verify what's actually being trusted before doing either.

Treat this section as closing a loop [§59](./Section-59-Part8-Package-Management-Concepts.md) opened rather than introducing a new topic — every repository this section discusses is one more `baseurl`/`deb` line a package manager will resolve dependencies against and, on `install`, run arbitrary post-install scripts as root from. That last clause is the entire reason GPG signing exists, and it's worth holding in mind through every command below.

## 2. apt's Repository Files: `sources.list` and `sources.list.d/`

[§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md) covered this format; the recap here is deliberately brief, just enough to anchor where signing keys attach to it.

`/etc/apt/sources.list` and any `*.list` file under `/etc/apt/sources.list.d/` contain lines of the form:

```
deb [signed-by=/usr/share/keyrings/example-archive-keyring.gpg] https://packages.example.com/apt stable main
```

| Field        | Meaning                                                                          |
| ------------ | -------------------------------------------------------------------------------- |
| `deb`        | Binary packages (`deb-src` is the equivalent for source packages)                |
| `signed-by`  | Path to the GPG keyring apt must use to verify this specific repo's Release file |
| URI          | The repository's base URL                                                        |
| Distribution | Suite/codename — e.g. `stable`, `jammy`                                          |
| Component(s) | One or more sections within that suite — e.g. `main`, `contrib`                  |

The `signed-by` field is the detail this section adds on top of [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)'s syntax walkthrough, and it's central to the GPG signing section below.

## 3. dnf/yum's Repository Files: `.repo`

[§61](./Section-61-Part8-RHEL-Tooling-Rpm-Yum-Dnf.md) covered this format in full; the fields that matter for this section are `gpgcheck` and `gpgkey`.

```ini
# /etc/yum.repos.d/example.repo
[example]
name=Example Vendor Repository
baseurl=https://packages.example.com/rpm/el9/$basearch/
enabled=1
gpgcheck=1
gpgkey=https://packages.example.com/rpm/RPM-GPG-KEY-example
```

| Field       | Meaning                                                                                        |
| ----------- | ---------------------------------------------------------------------------------------------- |
| `[section]` | The repo's short ID, used in output and in `--enablerepo`/`--disablerepo`                      |
| `baseurl`   | Where dnf/yum fetches packages and metadata from                                               |
| `enabled`   | `1`/`0` — whether this repo participates in resolution at all without an explicit override     |
| `gpgcheck`  | `1`/`0` — whether dnf verifies each package's signature against an imported key before install |
| `gpgkey`    | URL or local path to the public key dnf should import/use for this repo                        |

`gpgcheck=1` is the field this section is really about — the `gpgcheck=0` anti-pattern section below covers what setting it to `0` actually means and why that's a dangerous shortcut, not a fix.

## 4. Adding a Third-Party Repository: What You're Actually Agreeing To

Adding any repository not shipped by the distribution's own maintainers — a PPA on Ubuntu, a vendor's official `.repo` on RHEL-family systems, a third-party tool's own apt/yum feed — is a **trust decision with root-level consequences**, not a configuration convenience. It's worth stating plainly, because the phrase "just add the repo" undersells what's happening:

- Package installation on Linux routinely runs **maintainer scripts** — apt's `postinst`/`preinst`/`postrm`/`prerm` and rpm's `%pre`/`%post`/`%preun`/`%postun` scriptlets — as **root**, during `install`, `upgrade`, and `remove`. This isn't a hypothetical edge case; it's how services get their systemd units enabled, users/groups get created, and config files get migrated across package versions.
- Adding a repository and running `apt install`/`dnf install` against it means **whoever controls that repository can execute arbitrary code as root on this host**, the moment you install (or auto-update) a package from it. This is true whether the repository is a well-run vendor feed or a single maintainer's PPA — the trust extended is the same in kind, even if the operational track record differs.
- This is why "which repositories are enabled on this host" is a legitimate, standing audit question for any fleet, not a one-time setup detail — every enabled repo is a live extension of root trust that persists until someone removes it.

**Concrete example — Ubuntu PPA (apt side):**

```bash
sudo add-apt-repository ppa:example-team/example-ppa
sudo apt update
```

`add-apt-repository` writes a `.list` file under `/etc/apt/sources.list.d/` pointing at Launchpad's PPA infrastructure for that team, and (on modern Ubuntu) also fetches and installs the PPA's signing key automatically. The trust question doesn't go away because the tooling is smooth — it's still "do I trust the `example-team` Launchpad account and everyone with commit access to it."

**Concrete example — vendor's official repo (dnf side):**

Vendors distributing RPM packages (a database vendor, a monitoring agent, a language runtime) typically publish setup instructions that do three things: write a `.repo` file, as covered above, import the vendor's public GPG key, covered in the GPG signing section below, and only then run `dnf install`. The order matters — installing before the key is trusted either fails cleanly (`gpgcheck=1`, key missing) or, worse, someone "fixes" the failure the wrong way, as the `gpgcheck=0` anti-pattern section below describes.

> 💡 **Tip:** Before adding any third-party repository, apply a short trust checklist: Is this the vendor's own documented/official endpoint, not a mirror or a search-result link of uncertain provenance? Does the setup instruct importing a GPG key over HTTPS (or from a source you can verify independently, like a printed fingerprint) rather than skip signing entirely? Is `gpgcheck`/`signed-by` left enabled in the resulting config rather than a step telling you to disable it? Does this repo actually need to stay enabled long-term, or was it only needed for one install — a repo enabled once and forgotten is exactly the kind of stale, unaudited trust grant that turns up in security reviews years later.

## 5. GPG Signing: What Problem It Actually Solves

It's worth being precise about what GPG signing verifies, because "is this package legitimate" gets conflated with a narrower, different guarantee. **GPG signing verifies that a package (or a repository's metadata) was signed by the private key corresponding to a specific public key you've chosen to trust, and that the signed content hasn't been altered since signing.** It does not, by itself, vouch for whether the key's owner is trustworthy, well-intentioned, or who they claim to be socially — that judgment is exactly what the trust checklist in the third-party-repository section above is for. GPG answers "is this the same bytes the key holder signed," not "should I trust the key holder."

That distinction matters because the threat GPG signing defends against isn't primarily "did I type the wrong URL" — it's:

- **Tampering in transit** — a compromised or malicious network path (a hostile Wi-Fi network, a compromised CDN edge, a misconfigured proxy) substituting a malicious package for a legitimate one between the repository and the host. HTTPS on the transport helps here too, but signing verifies the payload independently of transport security, which matters if the repository itself is served over HTTP or if transport trust is ever compromised.
- **A compromised mirror or upstream host** — third-party repos are frequently mirrored, and a compromised mirror serving subtly altered packages is a real, recurring category of supply-chain incident. A signature check catches this because it verifies the package content against a key that ideally never touches the mirror infrastructure at all — only the original signing process does.
- **A compromised repository server** feeding tampered metadata (a `Release` file on apt, repo metadata on dnf) pointing package managers at malicious package versions or altered checksums — apt and dnf both verify repository metadata signatures, not just individual package signatures, which is why the key needs to be trusted before metadata is even fetched, not just before install.

Package **checksums alone don't solve this** — a checksum published on the same compromised server as the tampered package protects against nothing, since an attacker who can alter the package can alter the checksum listed next to it. A signature only helps because verification uses a public key obtained and trusted **independently** of the repository serving the packages — which is exactly why how you import that key, covered in the key-import section below, matters as much as whether signing is enabled at all.

## 6. Importing a Repository's GPG Key

### 6.1 apt side: `signed-by` and `/etc/apt/trusted.gpg.d/`, not `apt-key`

`apt-key` — the historical command for adding a repo's public key to apt's global trusted keyring — is **deprecated** and removed outright on recent Debian/Ubuntu releases. This is a real, fairly recent change to apt's security model, and it's worth understanding why it happened, not just that it did: `apt-key` added a key to one **global** keyring trusted for **every** configured repository on the host, meaning a key imported to satisfy one third-party repo was implicitly trusted to sign packages claiming to come from any repo apt knew about — a scope mismatch between "I trust this key for this one PPA" and what actually got granted.

The modern replacement is **per-repository key scoping**, via either of two mechanisms:

- Place the repository's public key file directly under `/etc/apt/trusted.gpg.d/` (or, more explicitly, anywhere and reference it) and point that specific repository's `sources.list`/`.list` entry at it with `signed-by=/path/to/keyring.gpg`, as shown in the apt repository-files section above. This means the key is only ever consulted for that one repo's entries, not treated as globally trusted.
- Fetch and dearmor the key manually, which is the concrete recommended sequence most vendors now document:

```bash
curl -fsSL https://packages.example.com/gpg-key | \
  sudo gpg --dearmor -o /usr/share/keyrings/example-archive-keyring.gpg
```

then reference `/usr/share/keyrings/example-archive-keyring.gpg` via `signed-by` in the corresponding `.list` file. `gpg --dearmor` converts the key from its distributed ASCII-armored text form into the binary keyring format apt expects — a mechanical step, but one worth recognizing in vendor install scripts rather than treating as unexplained boilerplate.

> ⚠️ **Warning:** Fetching a key over plain HTTP, or from a URL you haven't confirmed is the vendor's actual documented source, undermines the entire point of signing before you've even added the repository — the key import step is itself part of the trust chain described in the GPG signing section above, not a formality that happens before "the real security" starts.

### 6.2 dnf/yum side: `rpm --import`

RHEL-family systems import a vendor's public key directly into the RPM database:

```bash
sudo rpm --import https://packages.example.com/rpm/RPM-GPG-KEY-example
```

Once imported, `rpm -q gpg-pubkey --qf '%{name}-%{version}-%{release} --> %{summary}\n'` lists every currently-trusted key on the host — a useful, underused audit command, since RPM keys, once imported, persist independently of whether the `.repo` file that prompted the import is still present or enabled. A stale trusted key from a repo removed months ago is the RPM-side equivalent of the "forgotten repo" risk flagged in the third-party-repository section's checklist above.

Many vendor `.repo` files reference `gpgkey=` pointing at a URL rather than requiring a manual `rpm --import` step at all — dnf fetches and imports the key automatically on first use, prompting for fingerprint confirmation unless run non-interactively. Either path lands in the same place: a key in RPM's trusted set, checked against `gpgcheck=1` on every subsequent install from that repo.

## 7. `gpgcheck=0`: The Anti-Pattern Worth Naming Directly

`gpgcheck=1` in a `.repo` file, covered above, means every package installed from that repo must carry a valid signature from an imported, trusted key before dnf/yum will install it. Disabling it — `gpgcheck=0` — does not fix a broken key setup. It **removes package signature verification entirely**, meaning dnf will install whatever it fetches from `baseurl`, unsigned or signed by anyone, with no cryptographic check that what arrived is what the maintainer actually published.

> ⚠️ **Warning:** Setting `gpgcheck=0` to work around an import error, an expired key, or a "GPG check FAILED" message is a genuinely common piece of advice in outdated tutorials and forum answers — and it is close to the worst available fix, because it silently converts every future install from that repo into an unverified install, on a system where a network path compromise, a compromised mirror, or a tampered package now goes completely undetected. The correct fix is almost always re-importing the correct key, as the dnf/yum key-import subsection above covers, confirming the `baseurl`/`gpgkey` URL actually matches the vendor's current documented values, or checking whether the vendor rotated their signing key and published a new one — not disabling the check that exists specifically to catch the failure mode you're currently hitting.

The apt-side equivalent anti-pattern is `[trusted=yes]` on a `sources.list` entry, or passing `--allow-unauthenticated`/`-y --allow-unauthenticated` to force an install past a signature failure — mechanically different flags, same underlying mistake: treating a trust-verification failure as an obstacle to route around rather than a signal to investigate.

A `gpgcheck=0` or `[trusted=yes]` repository found during a fleet audit should be treated the same way an unexpectedly-both-active dual network daemon was treated in [§58](../Part7/Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md) — a finding to remediate, not a curiosity, because it means every package that repo has ever supplied to that host arrived with no cryptographic assurance it was what the vendor actually published.

## 8. Hands-On: Auditing Configured Repositories and Their Trust State

### 8.1 Listing enabled repositories

**Purpose:** Establish ground truth on what's currently configured to receive root-level trust on this host, before evaluating any individual repo's signing setup.

```bash
# apt
grep -rh ^deb /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null

# dnf/yum
dnf repolist all
```

**Expected output:** Every `deb`/`deb-src` line (apt) or every configured repo ID with its enabled/disabled state (dnf) — the full current trust surface, not just the ones an administrator remembers adding.

### 8.2 Checking for `gpgcheck=0` or `[trusted=yes]`

**Purpose:** Directly find the anti-pattern flagged in the `gpgcheck=0` section above, rather than assuming it isn't present.

```bash
# dnf/yum: any repo with signature checking disabled
grep -l 'gpgcheck=0' /etc/yum.repos.d/*.repo

# apt: any entry marked trusted without a signature check
grep -rl 'trusted=yes' /etc/apt/sources.list.d/*.list 2>/dev/null
```

**Common errors:** Checking only `/etc/yum.repos.d/example.repo` for a repo you remember adding and concluding the host is clean — vendor install scripts and configuration-management tooling both routinely drop additional `.repo`/`.list` files without an administrator manually authoring them, so the audit needs to cover every file in both directories, not a remembered subset.

**Troubleshooting:** A `gpgcheck=0` finding on a repo that's actively used should be treated as urgent — re-import the correct key per the dnf/yum key-import subsection above and flip it back to `1` rather than leaving it disabled "until there's time," since every install in the interim is unverified.

### 8.3 Listing trusted GPG keys

**Purpose:** See what keys are actually trusted right now, independent of which repo files reference them — the check that catches stale, forgotten keys from removed repos.

```bash
# apt
apt-key list 2>/dev/null   # deprecated, but still useful read-only on hosts that haven't migrated
ls /etc/apt/trusted.gpg.d/

# dnf/yum
rpm -q gpg-pubkey --qf '%{name}-%{version}-%{release} --> %{summary}\n'
```

**Production usage example:** Ahead of a security review or a supply-chain audit ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md), covers this class of hardening concern in full), cross-referencing the enabled-repo list from the listing-repositories subsection above against the trusted-key list from the listing-keys subsection above surfaces both directions of drift worth flagging: repos with no corresponding trusted key (install will fail, or worse, is running with `gpgcheck=0`) and trusted keys with no corresponding enabled repo (stale trust from something removed but never cleaned up).

## 9. Common Misconceptions

1. **"HTTPS on the repository URL makes GPG signing redundant."** HTTPS protects the transport — it doesn't verify that the server at the other end of that HTTPS connection is serving legitimate, untampered packages. A compromised mirror or a compromised origin server can serve tampered packages over a perfectly valid HTTPS connection; GPG signing verifies the payload itself against a key trusted independently of that connection, as the GPG signing section above covers.
2. **"`gpgcheck=0` is a reasonable temporary fix while sorting out a key problem."** It's a full removal of signature verification for every future install from that repo, not a pause — the `gpgcheck=0` section above covers why this is a genuine anti-pattern rather than a shortcut, and why the correct fix is almost always re-importing the right key.
3. **"`apt-key` is just an older command that still does the same thing."** It's deprecated specifically because its global-keyring model over-scoped trust — a key added for one repo was implicitly trusted for all of them. The `signed-by` + `/etc/apt/trusted.gpg.d/` model exists to fix that specific scoping problem, not just to modernize syntax, as the apt-side key-import subsection above details.
4. **"A signed package guarantees the software itself is safe."** GPG signing verifies provenance and integrity — that the bytes came from the claimed key holder and weren't altered — not that the software is free of bugs, backdoors intentionally placed by that key holder, or vulnerabilities. Signing answers "is this what the maintainer published," not "should I trust the maintainer," as the GPG signing section above explains.
5. **"Adding a PPA/vendor repo is a low-stakes convenience, same as installing any app."** It's a standing grant of root-level trust that persists until explicitly removed — maintainer scripts run as root on every install/upgrade/remove from that repo — which is the entire reason the checklist in the third-party-repository section above and the audit habits in the hands-on section above matter.

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What does `gpgcheck=1` in a `.repo` file actually do?"_
**Model answer:** It tells dnf/yum to verify each package's GPG signature against an imported, trusted key before installing it — confirming the package matches what was signed by that key and hasn't been altered since. If the signature doesn't validate, or no trusted key is available for it, the install is refused rather than proceeding with an unverified package.
_What the interviewer is probing for:_ Basic literacy with the field before probing whether the candidate knows what disabling it means, as the `gpgcheck=0` section above covers.

**🎯 Intermediate:** _"Why is `apt-key` deprecated, and what replaced it?"_
**Model answer:** `apt-key` added a repository's public key to one global keyring trusted for every repository configured on the host — so a key imported to satisfy one third-party PPA was implicitly trusted to vouch for packages from any other configured repo too, a scope mismatch between what was needed and what was granted. The replacement scopes trust per-repository: the key lives as its own file (commonly under `/etc/apt/trusted.gpg.d/`), and each `sources.list`/`.list` entry references it explicitly via `signed-by=`, so a compromised or malicious key only affects the specific repo it's associated with, not every repo on the host.
_What the interviewer is probing for:_ Understanding this as a genuine security-model improvement, not just a syntax change — and recognizing why global trust scoping was the actual problem.

**🎯 Senior:** _"A teammate says a repo is failing GPG checks after a routine update, and proposes setting `gpgcheck=0` to unblock a deployment. How do you respond?"_
**Model answer:** I'd push back on `gpgcheck=0` specifically — it doesn't fix the underlying problem, it removes signature verification for every future install from that repo, converting it into an unverified install path with no cryptographic guarantee against tampering, which is a materially worse security posture than a blocked deployment. I'd instead investigate why the check is failing: has the vendor rotated their signing key (a legitimate, fairly common cause, requiring a fresh `rpm --import`/key refetch rather than disabling checking), does the `baseurl`/`gpgkey` still point at the vendor's current documented endpoint, or is there a metadata/mirror sync issue upstream that's a vendor-side problem rather than something to route around locally. If the deployment is genuinely time-critical, I'd rather pin to a known-good previously-verified package version or delay than ship with signature verification silently disabled — because that decision doesn't get reverted reliably in practice, and it's exactly the kind of finding that turns up in a security review months later against a repo nobody remembers disabling checks on.
_What the interviewer is probing for:_ Whether the candidate treats `gpgcheck=0` as the anti-pattern it is under real deployment pressure, not just in the abstract — and whether they diagnose root cause rather than routing around the safeguard.

**🎯 Architect:** _"You're standardizing how third-party repositories get approved and added across a large, organically-grown fleet. What does that process look like?"_
**Model answer:** I'd start from the premise established in the third-party-repository section above — every enabled third-party repo is a standing root-trust grant, so the process needs to treat adding one as equivalent in weight to granting root SSH access to whoever controls that repo, not as a routine package-manager convenience. Concretely: a documented approval step confirming the repo is the vendor's own official endpoint (not a mirror of uncertain provenance), the key is imported via HTTPS from a source independently verifiable against vendor documentation (never disabling `gpgcheck`/`signed-by` as part of setup), and the repo is added through the provisioning pipeline (golden image or config management) rather than ad hoc on individual hosts, so there's one auditable source of truth for what's trusted fleet-wide. On the audit side, I'd run the checks in the hands-on auditing section above — enabled-repo inventory, `gpgcheck=0`/`[trusted=yes]` scan, and trusted-key inventory — on a recurring schedule, not just at initial setup, specifically to catch two failure modes: repos added ad hoc outside the approval process, and stale trusted keys or enabled repos left behind from tooling that's since been removed. Any `gpgcheck=0` finding gets treated as a priority remediation item, and any repo with no clear current owner or justification gets removed rather than left "in case something needs it" — the default posture for standing root trust should be minimal and explicitly justified, not accumulated. This connects directly into the broader supply-chain hardening work in Part 12 ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)) — repository and signing-key hygiene is one concrete, checkable piece of that larger threat surface, not a separate concern from it.
_What the interviewer is probing for:_ Fleet-scale process design that treats repository trust as a governed, auditable grant rather than a per-host convenience, and correctly ties it into the broader security-hardening context rather than treating it as an isolated package-management detail.

## 11. Key Takeaways

- Adding a repository is granting root-level trust to whoever controls it — maintainer scripts (`postinst`/`%post` and equivalents) run as root during install/upgrade/remove, which is the entire stake behind everything else in this section.
- apt's format ([§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md) recap) attaches trust per-repository via `signed-by=/path/to/keyring`; dnf's format ([§61](./Section-61-Part8-RHEL-Tooling-Rpm-Yum-Dnf.md) recap) uses `gpgcheck=1` plus an imported key to enforce the same idea per `.repo` file.
- GPG signing verifies that content matches what a specific trusted key signed and wasn't altered since — it defends against transit tampering and compromised mirrors/servers specifically, and it's a materially different guarantee than a checksum published alongside the same package on the same server.
- `apt-key` is deprecated because its global keyring over-scoped trust; the replacement is per-repo key files referenced via `signed-by`, and `rpm --import` remains the RHEL-family equivalent, worth auditing periodically for stale keys.
- `gpgcheck=0` (and apt's `[trusted=yes]`/`--allow-unauthenticated`) is a real, commonly suggested anti-pattern that removes signature verification entirely rather than fixing a broken key setup — the correct fix is almost always re-importing the correct, current key.
- Auditing enabled repositories, scanning for disabled signature checks, and inventorying trusted keys are standing fleet-hygiene checks, not one-time setup steps — stale trust and silently-disabled verification both accumulate unnoticed on hosts that are never re-audited.

## 12. Related Concepts & What's Next

This section closes the trust-model question [§59](./Section-59-Part8-Package-Management-Concepts.md) raised when it first introduced repositories and dependency resolution, and builds directly on [§60](./Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)'s apt `sources.list`/`sources.list.d` syntax and [§61](./Section-61-Part8-RHEL-Tooling-Rpm-Yum-Dnf.md)'s dnf `.repo` file syntax by adding the signing mechanism that makes either format trustworthy rather than just well-formed. The supply-chain trust concerns raised here — root-level execution from an extended trust grant, stale unaudited trust, silently disabled verification — are a concrete instance of the broader security-hardening territory covered in depth in **Part 12 ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md))**, worth revisiting once that material is reached. This is the last section of Part 8 ([§59](./Section-59-Part8-Package-Management-Concepts.md)–[§64](./Section-64-Part8-Managing-Repositories-GPG-Signing-Keys.md)) — package management is now covered from concepts and trust model through both major distribution families' tooling, building from source, universal package formats, and repository/signing hygiene. **Part 9 (starting at [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md))** moves to systemd in full depth — unit files, `systemctl`, `journalctl`, timers, and targets — the operational layer [§13](../Part2/Section-13-Part2-Init-Systems.md) deliberately introduced only at a conceptual level.

**Next Section:** [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) — `Section-65-Part9-Systemd-Architecture.md`
