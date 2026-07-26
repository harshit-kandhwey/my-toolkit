# Section 3 (Part 1): The Open-Source Model, Licensing (GPL), and Community Governance

**Roadmap Reference:** 1.3
**Phase:** Phase 1 — Foundations

---

## 1.3.1 Definition

**Plain language:** Open source means the source code is publicly available, and — depending on the specific license — others are free to use, study, modify, and redistribute it. "Open" is not a single, uniform promise; different licenses grant different freedoms and impose different obligations, and the specific license attached to a piece of software is a legal fact with real engineering consequences, not a detail to skim past.

**Precise definition:** The Linux kernel is licensed under the **GNU General Public License version 2 (GPLv2)**, an OSI-approved copyleft license. Two license families matter for this discussion:

- **Copyleft licenses** (GPL family): if you distribute a **derivative work** of GPL-licensed code, you must distribute it under the same license, and you must make the corresponding source code available to whoever receives the binary. The obligation "propagates forward" — hence "copyleft," a pun on copyright's usual role of restricting copying. The GPL does not restrict private use, internal modification, or running the software for any purpose; the obligations trigger on **distribution**.
- **Permissive licenses** (MIT, BSD, Apache 2.0): you may take the code, modify it, and redistribute it — including as part of a closed-source, proprietary product — with minimal obligations, typically just preserving a copyright notice and license text. No requirement to share your modifications or your own code that uses the library.

### What counts as a "derivative work" of the kernel

This is where GPLv2 compliance gets genuinely technical, and where real controversy has played out for two decades.

- **Code compiled into the kernel image itself, or a kernel module that is tightly coupled to kernel internals** (uses internal, non-stable kernel APIs; is a structural extension of kernel functionality) is treated by the kernel community as a derivative work, and therefore must be GPLv2-licensed and have its source distributed.
- **User-space programs that merely run on top of the kernel and talk to it only through system calls** (the stable, published kernel-to-userspace ABI) are _not_ considered derivative works. This is the load-bearing distinction that lets proprietary applications run on Linux at all — see the misconceptions section below.
- **Kernel modules** occupy the contested middle ground. The kernel exposes `EXPORT_SYMBOL_GPL()` for symbols that only GPL-licensed modules may use, alongside plain `EXPORT_SYMBOL()` for symbols usable by any module regardless of license — the kernel build system enforces this at compile/link time, and `modinfo` reports each module's declared license (see the hands-on section below).

### The binary-blob-driver controversy

Many hardware vendors (GPU makers, some Wi-Fi/networking chipset vendors) ship **closed-source kernel modules** — compiled binaries with no available source — typically to protect proprietary intellectual property (e.g., graphics driver algorithms) or because the driver embeds licensed third-party code they cannot redistribute. This is contentious for concrete reasons:

- The kernel community's official position, expressed in the kernel's own documentation (`Documentation/process/license-rules.rst` and related files) and enforced informally by maintainers, is that a module using only the stable, non-GPL-restricted symbol surface can plausibly be considered "not a derivative work," but a module that is tightly bound into kernel internals is a derivative work regardless of what its own license claims — a proprietary license notice does not override GPLv2's terms if the work is in fact derivative.
- Binary blobs break kernel debugging and stability guarantees: maintainers can't see or fix bugs inside them, they can silently violate internal kernel invariants, and their presence is flagged at boot and in crash reports via the kernel's "tainted" flag (visible in `cat /proc/sys/kernel/tainted` and in `dmesg`/`ktainted` output) specifically so that bug reports involving tainted kernels get treated differently by maintainers.
- Practically: this is _why_ NVIDIA historically shipped a proprietary driver alongside the community-driven open-source **Nouveau** driver, and why distributions like RHEL/Fedora have policies restricting or flagging kernel taint from proprietary modules for supportability reasons. ⚠️ **Verify current source:** vendor driver licensing strategies change over time (e.g., NVIDIA's open-source kernel module efforts) — don't cite a vendor's current licensing posture from memory in an interview without caveating that it may have moved on.

### Why GPLv2, not GPLv3, for the kernel

The kernel has deliberately stayed on **GPLv2** and explicitly declined to move to GPLv3 (this is stated directly in the kernel source tree's top-level `COPYING` file). The core reasons cited by Linus Torvalds and other kernel developers:

- **Anti-tivoization clauses.** GPLv3 added provisions aimed at preventing "tivoization" — shipping GPL software on hardware that cryptographically refuses to run modified versions of that software (named after TiVo devices). Kernel developers, including Linus, have publicly objected to this restriction as overreaching into hardware-design territory the license shouldn't govern, and as something that could alienate the embedded/hardware vendors who ship Linux.
- **Patent-clause changes.** GPLv3's explicit patent grant and termination language was seen by some kernel developers as legally riskier or harder to reason about at kernel scale, with thousands of independent contributors and corporate patent portfolios involved.
- **Practical coordination cost.** Because kernel copyright is held by thousands of individual contributors (there is no single copyright holder who could unilaterally relicense it), moving the whole kernel to GPLv3 would require either unanimous consent from every contributor ever, or a substantial relicensing/rewrite effort — neither realistic nor, in the community's judgment, worth the benefit.

> 💡 **Tip:** This is a favorite trivia-adjacent interview question because it tests whether you understand licensing as an _engineering-relevant, not just legal_ decision — GPLv2's specific terms shaped how hardware vendors, embedded device makers, and cloud providers could build on Linux at all.

## 1.3.2 Governance Structure

Linux has no single corporate owner, and its governance is a deliberately layered structure of trademark holder, meritocratic maintainers, and a neutral non-profit umbrella.

- **Trademark and ultimate authority.** The "Linux" trademark is owned by **Linus Torvalds** and administered on his behalf by the **Linux Foundation**. Torvalds remains the final authority on what enters the mainline kernel, though in practice he merges almost nothing directly — he pulls from a small number of trusted lieutenants.
- **The Linux Foundation** is a non-profit consortium funded by dues-paying member companies (historically including IBM, Google, Microsoft, Intel, Samsung, and many others). It does not write kernel code or dictate technical direction; its role is infrastructure, legal/trademark stewardship, funding key maintainers' full-time work, organizing developer conferences, and hosting _other_ open-source projects under its umbrella (Kubernetes' CNCF, for instance, is a Linux Foundation project — a useful forward-reference for later container-ecosystem topics).
- **Maintainer hierarchy.** Development is organized as a tree of trust, documented in the kernel's `MAINTAINERS` file:
  - **Subsystem maintainers** own a specific area (networking, a filesystem, a driver family, memory management, etc.) and are the ones who actually review and merge patches touching their area, into their own subsystem-specific git tree.
  - A smaller set of trusted lieutenants pull work from subsystem maintainers upward.
  - **Linus Torvalds** pulls from those lieutenants into **mainline** (`torvalds/linux` on kernel.org / GitHub mirror). This "pull-based," hierarchical web-of-trust model is exactly the multi-tier tree topology mentioned as a DVCS pattern in the Git knowledge base (§1) — the kernel is, historically, the reason Git was built to support it at all (§2).
- **Patch submission workflow.** Kernel development still runs primarily over **email**, not pull requests on a hosting platform — a deliberate, historically-rooted choice that surprises many engineers used to GitHub-centric workflows:
  1. A contributor writes a patch and formats it as a properly structured commit (subject line, body explaining _why_, not just _what_).
  2. The patch is sent to the relevant subsystem's **mailing list** (hosted via infrastructure like `lore.kernel.org`) using `git send-email`, which sends the patch as plain-text email rather than requiring reviewers to visit a web UI.
  3. Reviewers reply inline on the list, often line-by-line; revisions are resubmitted as new patch versions (`v2`, `v3`, …) until accepted.
  4. Every patch must carry a **`Signed-off-by:` line**, which is the kernel's mechanism for the **Developer Certificate of Origin (DCO)** — a lightweight legal attestation (not a CLA) that the contributor has the right to submit the code under the project's license and is not, e.g., copying it from somewhere they don't have rights to. This is the kernel community's alternative to requiring a signed Contributor License Agreement.
  5. Once a maintainer is satisfied, they apply the patch to their subsystem tree with their own `Signed-off-by:` added, forming a chain of custody back to Linus.
- **Release cadence.** The kernel follows a strict, predictable cycle — roughly **9–10 weeks** per release:
  - A **~2-week merge window** opens immediately after the previous release, during which Linus pulls new features from subsystem maintainers.
  - The merge window closes and a sequence of **`-rc` (release candidate)** builds follow — `-rc1` through typically `-rc7` or `-rc8` — each roughly a week apart, progressively narrowing to bug fixes and stabilization only; no new features are accepted after the merge window closes.
  - The cycle ends with a stable numbered release (e.g., moving from one major/minor version to the next).
- **Long-Term Support (LTS) kernels.** Select releases are designated LTS and receive backported security and bug fixes for an extended period; enterprise distributions typically build their supported kernel on an LTS base rather than tracking every mainline release. ⚠️ **Warning:** exact LTS designations, version numbers, and support-duration policies change over time — verify against kernel.org's current LTS table rather than citing a specific version's support window from memory.

> 🔑 **Two governance ideas worth internalizing:** (1) authority in the kernel is _earned and delegated_, not appointed by a company — a maintainer's standing comes from sustained, trusted contribution; (2) the email-based review workflow is not a legacy relic being phased out — it remains the kernel's primary review mechanism today, and understanding `git send-email` / `Signed-off-by` is directly useful if you ever contribute upstream.

## 1.3.3 Hands-On: Inspecting License Information on a Running System

Understanding licensing isn't purely theoretical — you can inspect what license governs installed packages and loaded kernel modules on any running Linux system, which matters directly for compliance audits (1.3.4).

### `modinfo` — Inspect a kernel module's license and metadata

**Command Documentation**

- **Purpose:** Display metadata about a kernel module, including its declared license, author, description, and version — without loading it.
- **Syntax:** `modinfo [options] modulename`
- **Common flags:**
  - `-F license` — print only the license field
  - `-F <field>` — print any single field (`author`, `description`, `version`, `depends`, …)
- **Example:**
  ```bash
  modinfo e1000e
  ```
  Sample relevant output line:
  ```
  license:        GPL v2
  ```
  Or, to check just the license field for every loaded module:
  ```bash
  for mod in $(lsmod | awk 'NR>1{print $1}'); do
    echo "$mod: $(modinfo -F license "$mod" 2>/dev/null)"
  done
  ```
- **Expected output:** A `license:` field with values such as `GPL`, `GPL v2`, `Dual BSD/GPL`, `Proprietary`, or similar — this is a **self-declared** field set by the module's author at compile time via the `MODULE_LICENSE()` macro, and the kernel uses it to decide whether the module may access `EXPORT_SYMBOL_GPL()`-restricted symbols. A module lying about its license to gain access to GPL-only symbols is a compliance and trust violation, not a technical bypass.
- **Common pitfalls:**
  - `modinfo` reports the _declared_ license, not a legal determination of whether the module is genuinely GPL-compatible — a self-declared "Proprietary" or "Dual BSD/GPL" module loading successfully doesn't mean its licensing is unambiguous or unchallenged.
  - Checking `dmesg | grep -i taint` or `cat /proc/sys/kernel/tainted` after loading a proprietary module shows the kernel's own signal that it's running with non-GPL or otherwise "tainting" code loaded — useful both for licensing awareness and because kernel maintainers treat bug reports from tainted kernels differently.

### Inspecting distribution package licenses

Distributions record the license of every installed package, letting you audit an entire system's licensing posture without reading source code.

- **Debian/Ubuntu:** every package ships a copyright/license file at `/usr/share/doc/<package>/copyright`, following a machine-parseable format (DEP-5). Example: `cat /usr/share/doc/bash/copyright`.
- **RHEL/Fedora family:** `rpm -q --qf '%{NAME}: %{LICENSE}\n' <package>` prints the declared license tag from the package's spec file; omit the package name and loop over `rpm -qa` to audit an entire system.

> 💡 **Tip:** These per-package license fields are exactly the raw data that automated **SBOM (Software Bill of Materials)** tooling and license-compliance scanners (e.g., FOSSA, Black Duck, `license-scanner` type tools referenced again in Part 12/14 compliance contexts) consume to build an auditable inventory — knowing where the data actually lives on disk demystifies what those tools are doing under the hood.

## 1.3.4 Practical Impact for Engineers

🔑 **Key Takeaway:** Because Linux is community-governed rather than single-vendor-controlled, no single company can unilaterally deprecate a feature the whole ecosystem depends on overnight — but it also means that some changes (e.g., replacing `iptables` with `nftables`, discussed in §115) roll out unevenly across distributions and versions, which is why version-awareness (Part 15) is a core professional skill, not a nicety.

Beyond that structural point, licensing has concrete day-to-day engineering consequences:

- **Choosing between a GPL and a permissively-licensed kernel module in a commercial product.** If your company ships an embedded Linux device (a network appliance, an IoT product) with a custom kernel driver, the license of that driver determines your obligations on shipment. If the driver is a derivative work of the kernel (typical for anything beyond a trivial stub), GPLv2 requires you to make its corresponding source available to anyone who receives the device — including competitors. This is precisely why some hardware vendors build thin, GPL-licensed "shim" modules that call out to a separate, closed-source user-space or firmware-blob component that does the actual proprietary work — a common, legally deliberate architecture choice.
- **Compliance audits.** Enterprises distributing Linux-based products (routers, NAS devices, embedded systems, even some SaaS appliances) are routinely required — sometimes by customer contract, sometimes by license enforcement organizations like the **Software Freedom Conservancy** — to produce the corresponding source code for any GPL components they've modified or bundled. Failing to do so has led to real litigation and settlements historically; this isn't a theoretical risk.
- **SBOM relevance.** Modern supply-chain security and compliance practice (increasingly mandated by regulation and large-enterprise procurement policy) requires producing a **Software Bill of Materials** — a full inventory of every component, its version, and its license, in every shipped artifact, including container images built on a Linux base. The `modinfo`/`rpm -q`/`dpkg` inspection techniques above are the manual version of what automated SBOM generators do at scale; understanding them helps you sanity-check SBOM tool output and explain license findings to auditors or legal teams.
- **Choosing a base distribution for a commercial product** can itself be a licensing decision, not just a technical one — e.g., preferring distros and packages with clearly permissive or well-documented licensing over ones with ambiguous or copyleft-heavy userland components, depending on your product's distribution model.

## 1.3.5 Common Misconceptions

1. **"If my proprietary application runs on Linux, I have to open-source it."** **False, and this is the single highest-value misconception to get right.** GPLv2's obligations attach to **derivative works of GPL-licensed code** — specifically, code that incorporates, links against in a way courts and the community treat as derivative, or is compiled into GPL-licensed source. A proprietary application that merely **runs on top of the kernel**, communicating with it only through the stable, published system-call interface, is not a derivative work of the kernel — this is precisely the boundary discussed in 1.3.1, and it is _why_ companies can sell closed-source commercial software (databases, SaaS backends, proprietary CLIs) that runs on Linux without any obligation to release their source. The GPL is about what you do with GPL-licensed _code itself_ — copying it, modifying it, linking it into your own binary in a way that makes your binary a derivative work — not about what operating system your unrelated software happens to execute on. (Caveat, not a contradiction: if you _do_ modify the kernel itself, or write a kernel module that's genuinely a derivative work per 1.3.1, and you _distribute_ that modified kernel or module, GPLv2's source-availability obligation does apply to that component.)
2. **"GPL means the software is free of charge."** Free as in freedom (to use, study, modify, redistribute), not necessarily free as in price — the GPL explicitly permits charging money for distributing GPL software; you just can't restrict the recipient's further rights to it.
3. **"Open source and GPL are the same thing."** GPL is one specific copyleft license among many OSI-approved open-source licenses; permissive licenses (MIT, BSD, Apache 2.0) are equally "open source" by any standard definition but impose far fewer downstream obligations. Conflating "open source" with "copyleft" causes real confusion when reasoning about compliance across a mixed dependency tree.
4. **"A proprietary kernel module is always illegal."** Not automatically — whether a given module is a "derivative work" is a genuinely contested, fact-specific legal and technical question, not a bright line; the kernel community's own stance (favoring modules that use only the stable, non-restricted symbol interface as more defensible) is influential but is not itself a court ruling. Treat specific vendor situations with appropriate caution rather than blanket certainty in either direction.
5. **"The Linux Foundation controls what goes into the kernel."** It doesn't — it's a funding, infrastructure, and trademark-stewardship body; technical decisions rest entirely with Torvalds and the maintainer hierarchy, which predates and is independent of the Foundation's administrative role.

## 1.3.6 Interview Questions

**[Beginner] Q1. What's the difference between a copyleft license like GPL and a permissive license like MIT?**
**Model answer:** A permissive license (MIT, BSD, Apache 2.0) lets you take the code, modify it, and redistribute it — including inside a closed-source proprietary product — with minimal obligations, typically just preserving the original copyright notice. A copyleft license like GPL is more restrictive on redistribution: if you distribute a derivative work of GPL code, you must license your derivative under the same terms and make its source available to recipients. The obligation "propagates forward" through the derivative-work chain, which is why it's called copyleft. Both are genuinely open source — GPL just makes a stronger promise that downstream users retain the same freedoms you were given.
_What the interviewer is probing for:_ basic licensing literacy — a surprisingly common gap even among experienced engineers.

**[Intermediate] Q2. My company wants to ship a commercial appliance running Linux with a custom closed-source kernel driver. What licensing risk are we taking on, and how do vendors typically manage it?**
**Model answer:** The risk hinges on whether the driver counts as a derivative work of the kernel — which depends on how tightly it's coupled to kernel internals, not on what license the vendor slaps on it. A module using only stable, non-GPL-restricted symbols has a more defensible case for separateness; one that's deeply integrated into kernel internals is much harder to argue isn't derivative, regardless of its claimed license. If it is derivative and we distribute it, GPLv2 requires making that source available to anyone who receives the device. The common mitigation pattern is architectural: ship a thin, genuinely GPL-licensed kernel module or shim that handles only the kernel-facing plumbing, and push the actual proprietary logic into a separate user-space component or firmware blob that the kernel module merely talks to — that keeps the protected IP outside the part that's unambiguously a kernel derivative work. I'd also flag this as a legal question, not just an engineering one, and loop in counsel rather than making the call solo.
_What the interviewer is probing for:_ whether you understand that licensing decisions have real architectural consequences, and that you know your own limits (loop in legal) rather than overconfidently asserting a compliance conclusion.

**[Senior] Q3. Kernel development still happens mostly over mailing lists using `git send-email`, rather than GitHub pull requests. Why has that persisted, and what does the `Signed-off-by` line actually certify?**
**Model answer:** The email-based workflow predates GitHub by years and has stuck around because it scales well for a globally distributed, high-volume review process across many timezones and connectivity levels, integrates naturally with plain-text patch review (line-by-line inline replies are a very old, well-understood email convention), and doesn't tie a foundational piece of infrastructure to any single commercial hosting platform — consistent with the project's broader independence from any one vendor. `Signed-off-by:` is the kernel's implementation of the Developer Certificate of Origin: a lightweight attestation, not a signed legal contract like a CLA, where the contributor certifies they have the right to submit this code under the project's license (e.g., they wrote it themselves, or it's already appropriately licensed) and are not, for instance, copying it from a source they don't have rights to redistribute. As a patch moves up the maintainer chain, each maintainer who applies it adds their own `Signed-off-by:`, building a traceable chain of custody back to the original author.
_What the interviewer is probing for:_ real familiarity with how the kernel actually operates, beyond generic "open source is collaborative" statements — useful signal if the role touches upstream contribution or vendor kernel work.

**[Architect] Q4. How does open governance of the Linux kernel affect long-term technology risk for an enterprise choosing Linux as a strategic platform?**
**Model answer:** Open governance reduces vendor lock-in risk: no single company can hold the platform hostage through licensing changes, since the source and its history are public and multiple vendors (Red Hat, SUSE, Canonical, cloud providers) can independently support it. This is a meaningfully different risk profile from proprietary platforms controlled by one vendor. The trade-off is that support and roadmap decisions are distributed, so enterprises typically mitigate operational risk by paying for a supported distribution (RHEL, SLES, Ubuntu Pro) that commits to a fixed support lifecycle and backporting policy, rather than relying on community goodwill alone for production-critical patches.
_What the interviewer is probing for:_ Strategic, business-aware thinking beyond pure technical trivia — appropriate at architect level.

**[Architect] Q5. A regulated customer demands a full SBOM and license-compliance attestation for a Linux-based appliance your company ships. Walk through how you'd approach producing that.**
**Model answer:** I'd separate the problem into inventory and attestation. For inventory, I'd enumerate every component in the shipped image — base distro packages via `dpkg`/`rpm` query tooling (which expose per-package license tags directly, as with `/usr/share/doc/*/copyright` on Debian-based systems or `rpm -q --qf '%{LICENSE}'` on RPM-based ones), any custom kernel modules we ship (checked via `modinfo -F license` and cross-referenced against actual derivative-work status, not just the self-declared field), and any vendored or statically linked third-party libraries in our own application code, which package managers won't surface automatically. For attestation, I'd generate a machine-readable SBOM (SPDX or CycloneDX format, feeding into whatever tooling the customer's compliance pipeline expects), flag anything with copyleft obligations for legal review — especially anything modified from upstream, since that's where the source-disclosure obligation actually triggers — and treat self-declared license fields as a starting point for investigation, not a legal conclusion, particularly for any component whose licensing has historically been contested. I'd also make this a recurring, automated part of the release pipeline rather than a one-time audit, since dependencies and their licenses change over time.
_What the interviewer is probing for:_ whether you can operationalize compliance as an engineering process, not just cite the concepts — a genuinely senior/architect-level distinction.

## 🔑 Key Takeaways

- The Linux kernel is GPLv2-licensed (copyleft): distributing a derivative work requires licensing it under GPLv2 and making its source available; this obligation triggers on distribution, not on private use.
- "Derivative work" for the kernel hinges on coupling to internal kernel APIs, not on what license a module claims — user-space programs talking only through the stable syscall ABI are not derivative works, which is why proprietary software can run on Linux without being open-sourced.
- The kernel deliberately stayed on GPLv2 rather than moving to GPLv3, primarily over anti-tivoization and patent-clause objections, and because relicensing thousands of independent copyright holders' contributions is impractical.
- Governance is a layered structure: Torvalds holds the trademark and final mainline authority; the Linux Foundation is a neutral funding/infrastructure/trademark body with no technical control; a maintainer hierarchy documented in `MAINTAINERS` does the actual patch review.
- Kernel contribution still runs primarily through mailing lists and `git send-email`, with `Signed-off-by:`/DCO as the lightweight provenance attestation — not GitHub pull requests.
- Release cadence is a strict ~9–10 week cycle: a merge window, then successive `-rc` stabilization builds, then release; select releases get designated LTS.
- `modinfo -F license`, `/usr/share/doc/*/copyright`, and `rpm -q --qf '%{LICENSE}'` are the practical, on-system tools for auditing what's actually licensed how — the manual version of what SBOM tooling automates.
- The GPL applies to derivative works of GPL code itself, not to everything that merely executes on top of Linux — get this distinction right; it's the highest-value misconception in this section.

## Related Concepts & What's Next

- §1 established the kernel-vs-OS-vs-distribution distinction this section builds on — licensing questions differ for the kernel itself versus userland components a distribution bundles, which may carry different licenses entirely.
- §2 covered the historical arc (Unix → GNU → Linux) that explains _why_ the GPL exists at all — Richard Stallman's GNU Project and the Free Software Foundation predate Linux and supplied both the GPL itself and much of the userland the kernel needed to become a usable OS.
- §4 (next) covers Linux philosophy and design principles — the technical counterpart to this section's legal/governance framing.
- Part 8 (§59–§64) returns to package management, where per-package license metadata (introduced here) is what tooling like `dpkg`/`rpm`/repository signing actually operates on.
- Part 12 (§89–§96) covers security hardening and compliance frameworks in depth, where SBOM generation and license-compliance auditing (introduced practically here) become formal, recurring processes.
- Part 14 (§103–§110) covers enterprise support models (RHEL subscriptions, Ubuntu LTS) — the commercial answer to the governance trade-off (distributed roadmap, no single vendor) discussed in 1.3.4's architect-level material.
- Part 15 (§111–§115) covers version and distribution differences that matter in practice, including the uneven rollout of ecosystem-wide changes referenced in the Key Takeaway above (e.g., `iptables` → `nftables`).

---

**Next Section:** §4 — `Section-04-Part1-Linux-Philosophy-Design-Principles.md`
