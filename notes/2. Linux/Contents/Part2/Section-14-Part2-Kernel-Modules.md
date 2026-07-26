# Section 14 (Part 2): Kernel Modules (lsmod, modprobe, insmod, /lib/modules)

## 1. Definition

**Plain language:** A kernel module is a piece of compiled code you can plug into — and unplug from — a running kernel, the way you'd plug a USB device into a running machine, without rebooting anything. It's how Linux adds support for a new driver, filesystem, or kernel feature on the fly.

**Precise definition:** A **Loadable Kernel Module (LKM)** is object code, compiled separately from the main kernel image, that can be dynamically inserted into and removed from the running kernel's address space at runtime. §9 introduced this as the practical answer to monolithic design's apparent rigidity: Linux gets the function-call-speed internal communication of a single, privileged kernel address space, _and_ the flexibility of not needing every possible driver, filesystem, or feature statically compiled into one fixed kernel image. A module is not an isolated, sandboxed add-on — once loaded, it runs in kernel space with exactly the same full hardware privilege as code that was compiled directly into the kernel image (§9's point, worth restating because it drives this section's misconceptions and security discussion).

> 💡 **Tip:** "Loadable" describes _when_ the code becomes part of the kernel (at runtime, on demand) — it says nothing about how trusted or how privileged that code is once loaded. A module and a built-in subsystem are peers inside kernel space.

## 2. The Module Lifecycle

A module's life runs through five distinct stages, and understanding each one is what separates "I ran `modprobe`" from actually knowing what happened:

1. **Build.** The module's source is compiled against the **headers and build artifacts of a specific kernel version** — not just any kernel, but the exact version (and often exact build configuration) it will run under. This matters because the module calls internal kernel functions and touches internal kernel data structures whose layout and symbol addresses are not a stable, guaranteed-compatible interface across versions (unlike the stable syscall ABI userspace relies on, §11). A module built for one kernel version generally will not load into a different one.
2. **Load.** The module's code and data are copied into kernel space and linked against the running kernel's exported symbol table — this is where dependency resolution happens (4).
3. **Initialize.** The kernel calls the module's registered **`module_init()`** entry point — the module's own setup code: registering a driver with a subsystem, allocating resources, creating `/proc` or `/sys` entries, etc. If initialization fails (a resource conflict, a hardware probe failure), the load is aborted and the module is not left half-installed.
4. **Run.** The module now sits resident in kernel space, its registered functions callable by the rest of the kernel (interrupt handlers, syscall paths, other subsystems) for as long as it's loaded — this is the module's normal operating state, often for the system's entire uptime.
5. **Cleanup and unload.** The kernel calls the module's **`module_exit()`** entry point, which is responsible for undoing everything `module_init()` set up — releasing resources, unregistering handlers, removing `/proc`/`/sys` entries — before the module's code and data are removed from kernel memory. A module currently in use (open file handles, an active mount depending on it, another module depending on it) cannot be unloaded until that usage drops to zero — the kernel tracks per-module reference counts precisely to enforce this.

```text
   BUILD                LOAD              INIT              RUN                 UNLOAD
(against a       (copied into      (module_init()    (resident,        (module_exit(),
 specific         kernel space,     registers          callable by       then removed
 kernel's         symbols           driver/feature,     rest of           from kernel
 headers)         resolved)         allocates           kernel)           memory)
                                     resources)
   │                  │                  │                 │                   │
   ▼                  ▼                  ▼                 ▼                   ▼
 (offline)  ──►  modprobe/insmod  ──►  kernel calls   ──►  in use   ──►   modprobe -r/rmmod
                                        entry point                       (only if refcount = 0)
```

## 3. Command Documentation: The Core Toolset

### `lsmod` — List loaded modules

- **Purpose:** Show every module currently loaded into the running kernel, along with its size and what else depends on it.
- **Syntax:** `lsmod`
- **What it actually is:** `lsmod` does no work of its own — it is a thin, formatted reader of the kernel-exposed `/proc/modules` virtual file (§24 covers `/proc` in depth). Reading `/proc/modules` directly gives you the identical information.
- **Example output:**
  ```
  Module                  Size  Used by
  nf_tables             253952  10 nft_chain_nat,nft_counter,...
  xt_conntrack           16384  1
  e1000e                323584  0
  ```
- **Column meaning:**
  - **Module** — the module's name.
  - **Size** — memory footprint in bytes.
  - **Used by** — a reference count, followed by (if any) the names of other modules that depend on this one. A count of `0` with no names means nothing currently depends on it, and it's a candidate for safe removal.
- **Common pitfall:** `lsmod` output order is not alphabetical or load-order — it reflects the kernel's internal module list, so don't infer a dependency chain purely from row order; use the "Used by" column, or `modinfo -F depends`, instead.

### `modprobe` — The smart loader (preferred)

- **Purpose:** Load (or remove) a module **and everything it depends on**, automatically.
- **Syntax:** `modprobe [options] module_name`
- **Common flags:**
  - `-r` — remove a module (and, if now unused, its dependencies)
  - `-n -v` — dry run with verbose output: show exactly what would be loaded, without loading it
  - `-c` — print the effective configuration (useful for debugging blacklists, 5)
- **Example:**
  ```bash
  modprobe e1000e
  modprobe -r e1000e
  modprobe -n -v vfat     # dry-run: shows it would also pull in "fat"
  ```
- **Why it's preferred for virtually all real usage:** `modprobe` consults `modules.dep` (4) to resolve the full dependency chain before touching anything — if `module_a` requires `module_b`, `modprobe module_a` loads `module_b` first, automatically. It also understands module aliases (loading by a hardware/feature alias rather than requiring you to know the exact module name) and respects `/etc/modprobe.d/` configuration (5) — blacklists, parameter overrides, install/remove hooks. This is the tool used by udev, boot-time module loading, and essentially every scripted or interactive workflow.

### `insmod` / `rmmod` — The dumb, low-level loaders

- **Purpose:** Insert or remove a **single, specific module file**, with no dependency resolution, no alias lookup, and no `/etc/modprobe.d/` awareness.
- **Syntax:**
  ```bash
  insmod /lib/modules/$(uname -r)/kernel/drivers/net/ethernet/intel/e1000e/e1000e.ko
  rmmod e1000e
  ```
- **Why "dumb":** `insmod` takes a literal path to a `.ko` (kernel object) file and attempts to load exactly that file — if it depends on another module that isn't already loaded, `insmod` simply fails with an unresolved-symbol error rather than going and loading the dependency for you. `rmmod` is the same story in reverse: it removes exactly the named module and nothing else, and refuses if the reference count isn't zero.
- **When they're still the right tool:** low-level debugging of a specific `.ko` build (e.g., a module you just compiled yourself and want to test in isolation, bypassing the installed module tree entirely), or kernel-development contexts where you deliberately want to bypass dependency auto-resolution to see exactly what a single module does or doesn't need. Outside that, reach for `modprobe`.

> ⚠️ **Warning:** "`insmod` and `modprobe` do the same thing" is a common but incorrect simplification — see Common Misconceptions (8). The dependency-resolution gap is the entire reason `modprobe` exists as a wrapper in the first place.

## 4. `/lib/modules/`, `modules.dep`, and `depmod`

Every installed module lives under a directory tree scoped to one specific kernel build:

```text
/lib/modules/$(uname -r)/
├── kernel/                  # the actual .ko module files, organized by subsystem
│   ├── drivers/
│   ├── fs/
│   └── net/
├── modules.dep              # dependency map — what requires what
├── modules.dep.bin          # binary-indexed version, for fast lookup
├── modules.alias            # hardware/feature aliases → module names
├── modules.symbols           # which module exports which symbol
└── modules.builtin          # modules compiled directly into this kernel, not loadable separately
```

- **Why version-pinned:** as noted in the lifecycle (2), a module is compiled against a specific kernel's internal ABI — struct layouts, exported symbol addresses, internal calling conventions — none of which the kernel promises to keep stable across versions (unlike the userspace syscall ABI, §11). `uname -r` reports the exact running kernel version, and `/lib/modules/$(uname -r)/` is where that specific build's matching modules live. Loading a module built for a different kernel version reliably fails (6).
- **`modules.dep`** is the dependency map `modprobe` reads to figure out what else needs loading first — it's a plain-text (and binary-indexed) file mapping each module to the list of other modules it requires.
- **`depmod`** is the tool that _generates_ `modules.dep` (and the related `.alias`/`.symbols` index files) by scanning every `.ko` file under `/lib/modules/$(uname -r)/` and recording its declared dependencies and symbol usage. It's run automatically by package managers whenever a new kernel or a new set of modules is installed; running `depmod -a` manually rebuilds the index for the current kernel and is a standard troubleshooting step after manually dropping a new `.ko` file into the tree (6).

## 5. Configuration and Persistence

Module state is not, by default, persistent across a reboot — a module you `modprobe`'d by hand is gone on the next boot unless it's loaded automatically at boot time (either by udev detecting matching hardware, or via explicit configuration).

- **`/etc/modules-load.d/*.conf`** — one module name per line, per file; systemd's `systemd-modules-load` service loads every listed module at boot. This is how you make a manually-loaded module persistent.
  ```
  # /etc/modules-load.d/my-modules.conf
  vfio_pci
  ```
- **`/etc/modprobe.d/*.conf`** — configuration consulted by `modprobe` (not `insmod`) for **parameters** and **blacklisting**, using directives like `options`, `blacklist`, `install`, and `alias`.
  - **Setting a module parameter:**
    ```
    # /etc/modprobe.d/e1000e.conf
    options e1000e InterruptThrottleRate=3000,3000
    ```
  - **Blacklisting a conflicting driver** — a common, concrete production scenario: a system has two drivers that can both claim the same piece of hardware (e.g., an open-source driver and a vendor's proprietary one, or a legacy driver superseded by a newer one), and the wrong one auto-loading at boot causes the device to misbehave or not initialize correctly.
    ```
    # /etc/modprobe.d/blacklist-nouveau.conf
    blacklist nouveau
    options nouveau modeset=0
    ```
    `blacklist` prevents _automatic_ loading (by alias resolution, udev, or another module's dependency chain) — it does **not** prevent an explicit `modprobe nouveau` from working. That distinction trips people up: blacklisting stops the module from being pulled in indirectly, not from being loadable at all.

> 💡 **Tip:** `modprobe -c` prints the fully merged, effective configuration `modprobe` would act on — the fastest way to confirm whether a blacklist or parameter override is actually taking effect, rather than guessing from file contents alone.

## 6. Troubleshooting

When `modprobe` or `insmod` fails, `dmesg` (§9) is the first place to look — the kernel logs the actual reason from kernel space, which is almost always more specific than the shell's own error message:

```bash
modprobe some_module
dmesg -T | tail -20
```

Common failure modes and their `dmesg` signatures:

- **Missing dependency:** `insmod` (or `modprobe` with a broken/stale `modules.dep`) reports `Unknown symbol` errors — the module references a kernel or module symbol that isn't currently loaded or exported. Fix: load the dependency first, or (if `modules.dep` itself is stale after manually adding a `.ko`) run `depmod -a`.
- **Version mismatch:** `insmod: ERROR: could not insert module ...: Invalid module format`, with a corresponding `dmesg` line naming a kernel-version or "vermagic" mismatch — the module was built against a different kernel build than the one currently running. Fix: rebuild the module against the running kernel's headers, or load the version-matched module actually shipped for that kernel.
- **Secure Boot / module signing enforcement:** `modprobe: ERROR: could not insert '...': Operation not permitted`, with `dmesg` reporting something like `Lockdown: modprobe: unsigned module loading is restricted`. When Secure Boot is enabled (§12 covered Secure Boot in the boot-process chain), the kernel typically runs in a **lockdown mode** that refuses to load modules lacking a valid cryptographic signature trusted by the kernel's key ring — this is a deliberate hardening measure, not a bug, and blocks exactly the class of "load arbitrary code into kernel space" attack the misconceptions section below is warning about. The fix is either to properly sign the module against a key enrolled in the system's Machine Owner Key (MOK) store, or (in non-production/lab contexts only) to disable Secure Boot — never a step to take on a production system without understanding the tradeoff.
- **Resource/hardware probe failure:** the module loads but `module_init()` itself fails (e.g., a driver can't claim the hardware it expects) — `dmesg` typically names the specific device or resource conflict; this is a hardware/driver-logic problem rather than a loading-mechanism problem.

## 7. Production Relevance

- **Hot-adding driver support without a reboot.** The headline operational win: attaching new storage (a new HBA card, an iSCSI/NVMe driver) or network hardware to a live server and bringing it fully into service with `modprobe <driver>` — no maintenance window, no reboot, no service interruption for anything unrelated to that hardware. This is the direct, practical payoff of the LKM mechanism §9 described conceptually.
- **The operational risk side.** Because a module runs with full kernel-space privilege once loaded (1), a bad module — buggy, incompatible, or outright malicious — can crash the kernel (a panic, §9's blast-radius discussion) or fully compromise the machine, with none of the containment a user-space process failure would get. This is exactly the licensing-and-trust angle §3 raised about binary-blob drivers and kernel taint: an untrusted or unauditable module isn't just a licensing question, it's an unrestricted-privilege operational risk. Treat "what modules are we loading, from where, and why" as a real production concern, not a formality — particularly on hosts where module loading is exposed to any user with elevated but not full-root access.

## 8. Common Misconceptions

1. **"Loaded modules are less trusted or less powerful than code built into the kernel."** False. Once loaded, a module runs in kernel space with exactly the same full hardware privilege as any code compiled directly into the kernel image — there is no reduced trust tier, no sandbox, no isolation (§9). "Loadable" is purely about _when_ the code joins the kernel, not _how much_ privilege it gets when it does.
2. **"`insmod` and `modprobe` do the same thing."** No — `insmod` inserts exactly one named `.ko` file with zero dependency resolution and fails outright if a dependency isn't already loaded; `modprobe` consults `modules.dep`, resolves and loads the full dependency chain automatically, understands aliases, and respects `/etc/modprobe.d/` configuration. `modprobe` is best understood as a smart wrapper that makes `insmod`/`rmmod`-equivalent operations usable without manually tracking dependencies yourself.
3. **"A module will load on any kernel as long as the architecture matches."** No — modules are pinned to the specific kernel build they were compiled against (kernel version plus, often, exact build configuration), not just CPU architecture. This is a common surprise for anyone used to userspace binary portability across kernel versions, which the stable syscall ABI (§11) does guarantee — the module-loading ABI makes no equivalent promise.
4. **"Blacklisting a module in `/etc/modprobe.d/` prevents it from ever loading."** Not quite — `blacklist` prevents _automatic_ loading via alias resolution or another module's dependency chain; an explicit `modprobe <module>` still works unless something else (module signing lockdown, a hard filesystem removal) also blocks it.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `lsmod`, `modprobe`, and `insmod`?"_
**Model answer:** `lsmod` just lists what's currently loaded — it's a read-only view formatted from `/proc/modules`. `modprobe` and `insmod` both load modules, but differently: `insmod` inserts one specific `.ko` file with no dependency resolution, failing if something it needs isn't already loaded. `modprobe` is the smart wrapper — it reads `modules.dep` to figure out the full dependency chain and loads everything required automatically, and it also understands module aliases and honors configuration in `/etc/modprobe.d/`. In practice, almost all real usage — interactive or scripted — goes through `modprobe`; `insmod`/`rmmod` are for low-level or debugging scenarios.
_What the interviewer is probing for:_ basic tool literacy and whether the candidate knows _why_ one is generally preferred, not just that it is.

**🎯 Intermediate:** _"A `modprobe` for a driver you just built fails with an 'Invalid module format' error. Walk through how you'd diagnose it."_
**Model answer:** First I'd check `dmesg -T | tail` right after the failed attempt — the kernel logs the actual reason from kernel space, and "Invalid module format" almost always corresponds to a vermagic/kernel-version mismatch: the module was compiled against a different kernel build than the one currently running. I'd confirm the running kernel with `uname -r` and check that against what the module was built for — usually visible via `modinfo` on the `.ko` file, or by checking which headers were used at build time. If it's a real mismatch, the fix is rebuilding against the currently running kernel's headers, or dropping the module into the matching `/lib/modules/$(uname -r)/` tree and re-running `depmod -a` so `modules.dep` picks it up. I'd also rule out a signing/Secure Boot lockdown issue first, since that produces a different, more specific "Operation not permitted" error rather than "Invalid module format" — different failure modes need different fixes.
_What the interviewer is probing for:_ real troubleshooting method — going to `dmesg` first rather than guessing, and distinguishing failure modes by their actual signature rather than pattern-matching on "module load failed."

**🎯 Senior:** _"Why can't a module built for one kernel version just load into a different one, when a userspace binary built years ago still runs fine on a modern kernel?"_
**Model answer:** Those are two entirely different ABI contracts. The kernel guarantees a stable, backward-compatible **syscall interface** to userspace (§11) — that's the interface a compiled userspace binary actually depends on, and the kernel treats breaking it as close to unthinkable. A kernel module, by contrast, doesn't talk to the kernel through that stable boundary at all — it's linked directly against internal kernel symbols, internal struct layouts, and internal calling conventions, none of which the kernel promises to keep stable release to release, precisely because keeping internal implementation details frozen forever would badly constrain kernel development. That's why modules are version-pinned to `/lib/modules/$(uname -r)/` and carry a "vermagic" string checked at load time — the kernel is explicitly refusing to trust that internal-ABI compatibility holds across versions it never promised to preserve.
_What the interviewer is probing for:_ understanding the distinction between the stable external syscall ABI and the deliberately unstable internal kernel ABI — a frequently confused pair even among engineers who've used `modprobe` for years.

**🎯 Architect:** _"How would you govern kernel module loading across a production fleet to balance operational flexibility against the security risk of a compromised or buggy module?"_
**Model answer:** I'd treat it as a layered control problem rather than a single switch. At the platform level, I'd enable Secure Boot with kernel lockdown and enforce module signature verification, so only modules signed against a trusted key — ideally one under our own CI/build-signing pipeline, not just vendor-default keys — can load at all; that closes off the "arbitrary unsigned code in kernel space" attack path entirely. I'd pair that with a minimal, explicitly enumerated module allowlist per host role rather than letting arbitrary hardware-triggered auto-loading run unconstrained, and route any manual module operations through the same change-management and audit trail as any other privileged system change, since a module load is functionally equivalent to a live kernel patch in terms of blast radius. I'd also fold `modinfo`-declared licensing and provenance (§3's compliance angle) into that same review, since an unaudited proprietary or third-party binary module is both a licensing and a trust-boundary question at once. The overarching principle: because a loaded module runs with full, unrestrained kernel privilege, the controls around _what_ gets signed and _who_ can trigger a load matter far more than any runtime sandboxing, because there effectively isn't any once it's loaded.
_What the interviewer is probing for:_ architect-level synthesis — connecting module-loading mechanics to Secure Boot, signing infrastructure, change management, and the licensing/trust material from §3, rather than treating module security as an isolated technical detail.

## 10. 🔑 Key Takeaways

- A **Loadable Kernel Module (LKM)** is compiled code inserted into and removed from a running kernel without a reboot — it runs with full kernel-space privilege once loaded, identical to compiled-in code (§9).
- The module lifecycle is build (against a specific kernel version) → load → `module_init()` → run → `module_exit()` → unload; a module in use (non-zero reference count) cannot be unloaded until dependents release it.
- `modprobe` is the preferred, "smart" loader — it resolves dependencies via `modules.dep`, understands aliases, and honors `/etc/modprobe.d/`; `insmod`/`rmmod` are "dumb," single-module, no-dependency-resolution tools for low-level or debugging use.
- Modules live under `/lib/modules/$(uname -r)/`, version-pinned because modules bind to the kernel's internal, deliberately unstable ABI — not the stable syscall ABI userspace relies on (§11); `depmod` generates the `modules.dep` dependency index that `modprobe` reads.
- `/etc/modules-load.d/` makes module loading persistent across reboots; `/etc/modprobe.d/` configures parameters and blacklists — `blacklist` stops automatic loading, not explicit `modprobe` invocation.
- `dmesg` is the first troubleshooting stop after a failed load — missing-dependency, version-mismatch, and Secure-Boot-lockdown signing failures each have a distinct, identifiable signature there.
- The production trade-off is real: hot-adding driver support without downtime is a genuine operational win, but a bad or malicious module carries the same unrestricted blast radius as any other kernel-space fault or compromise (§3, §9).

## 11. Related Concepts & What's Next

- §3 covered the GPL/derivative-work and licensing angle on kernel modules (`modinfo`, `MODULE_LICENSE()`, tainted kernels, binary blob drivers) — this section deliberately did not re-cover that ground, focusing instead on load mechanics; read them together for the full picture.
- §9 introduced LKMs conceptually as monolithic design's answer to rigidity and established that a loaded module has full kernel-space privilege — this section is the operational deep dive that section forward-referenced.
- §12's boot-process coverage of Secure Boot is the direct upstream context for this section's module-signing/lockdown troubleshooting material.
- §15 (next) moves from "what code is resident in kernel space" to "how the CPU actually schedules and interrupts that code" — interrupts, context switching, and CPU scheduling fundamentals.
- Part 12 (§89–§96) returns to kernel hardening in depth, including `sysctl` parameters and module-signing enforcement policy at a production-hardening level of detail.

---

**Next Section:** §15 — `Section-15-Part2-Interrupts-Context-Switching-CPU-Scheduling.md`
