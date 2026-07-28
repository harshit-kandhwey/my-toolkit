# Section 123 (Part 17): Progressive Hands-On Labs (Beginner → Production-Style)

Everything in Parts 1–16 has been explanation, command reference, and interview framing. None of it becomes real skill until it's exercised on an actual machine — a spare laptop, a cloud free-tier VM, or a local VM/container is all any of these labs need. The ten labs below are ordered deliberately: each one either builds directly on the skills exercised by the previous lab or introduces exactly one new class of problem, so working through them in order roughly retraces the roadmap's own arc from filesystem basics to production-style operational judgment. Each lab states a goal and the roadmap sections it draws on, then describes what to actually do — not a scripted walkthrough, since the point is to force retrieval of the underlying commands and reasoning rather than transcription.

## 1. Lab 1 — Filesystem Navigation, File Operations, and Permissions

**Goal:** Build unconscious fluency with the filesystem hierarchy and the permission model before anything else depends on it.

**Draws on:** §17 (FHS), §21 (file/directory operations), §27 (standard permission model).

**What to do:** On a fresh VM, create a small directory tree under your home directory (a few nested subdirectories, a handful of files). Practice copying, moving, and renaming files and directories with relative and absolute paths. Then deliberately break and fix permissions: create a file only you can read, one a group can write to, one that's world-readable but not world-writable, and predict — before running `ls -l` — what the permission string will look like. Use `chmod` in both symbolic (`u+x`) and octal (`755`) form until both feel equally natural.

## 2. Lab 2 — New User, sudo Access, and SSH Key Authentication

**Goal:** Stand up a properly configured non-root operational account the way a real onboarding would.

**Draws on:** §25 (users/groups), §26 (user management commands), §31 (sudo/sudoers), §56 (SSH architecture and key-based auth).

**What to do:** Create a new user, add it to an appropriate group, and grant it sudo access via a dedicated `/etc/sudoers.d/` file rather than editing `/etc/sudoers` directly. Generate an SSH key pair on your client machine, install the public key for the new user, and disable password authentication for SSH entirely. Confirm you can SSH in as the new user with no password prompt, and that the account can run privileged commands via `sudo` but cannot log in directly as root.

## 3. Lab 3 — A Custom systemd Service for a Simple Script

**Goal:** Turn an ad-hoc script into a properly supervised, boot-persistent service.

**Draws on:** §65 (unit/target architecture), §66 (`systemctl`), §67 (writing unit files).

**What to do:** Write a small script that does something observable in a loop (append a timestamp to a log file every few seconds, for instance). Write a unit file for it with an appropriate `Type=`, a `Restart=` policy, and correct `After=`/`Requires=` ordering relative to networking. Enable it, start it, confirm it survives a reboot, then kill the underlying process directly and confirm systemd notices and restarts it per the policy you declared.

## 4. Lab 4 — Replace a Cron Job with a systemd Timer

**Goal:** Practice the timer-vs-cron migration this roadmap argues for directly, rather than just reading the comparison.

**Draws on:** §69 (systemd timers vs. cron).

**What to do:** Take a task you'd normally schedule with cron (rotating a file, running a cleanup script) and implement it twice: once as a traditional crontab entry, once as a paired `.service` + `.timer` unit. Compare what each approach gives you for free — timer's ability to see missed-run history via `systemctl list-timers`, catch-up behavior with `Persistent=true`, and journald-integrated output versus cron's mail-based (or silent) failure reporting.

## 5. Lab 5 — A Minimal, Correct Firewall Ruleset

**Goal:** Move from "firewall exists" to "firewall enforces exactly the intended policy, provably."

**Draws on:** §54 (firewalls: iptables/nftables/firewalld/ufw).

**What to do:** On a test VM (not anything with a production SSH session you can't afford to lose), configure a default-deny inbound policy that allows only SSH and one or two other services you're actually running, with everything else rejected. Verify from a second machine that the allowed ports are reachable and everything else is not — don't just trust the ruleset syntax, confirm the observed behavior matches intent. Practice reloading the ruleset without ever locking yourself out (test the change in a way that self-reverts if it breaks connectivity).

## 6. Lab 6 — An LVM Logical Volume, Formatted and Persistently Mounted

**Goal:** Practice the LVM stack end-to-end, from raw block device to a filesystem that survives a reboot.

**Draws on:** §73 (LVM: PVs, VGs, LVs), §20 (mounting and `/etc/fstab`).

**What to do:** Attach an extra virtual disk to a test VM (or use a loop device if no extra disk is available), initialize it as a physical volume, add it to a new volume group, carve out a logical volume, format it with a filesystem of your choice, and mount it at a sensible path. Add the correct entry to `/etc/fstab` — using the filesystem's UUID rather than the device path — and confirm the mount survives a full reboot rather than only working until the next power-off.

## 7. Lab 7 — A Bash Script With Proper Error Handling

**Goal:** Write automation that fails loudly and safely rather than silently continuing past a broken step.

**Draws on:** §45 (bash scripting fundamentals: shebang, arguments, exit codes), §101 (shell scripting for automation pipelines).

**What to do:** Write a script that performs a small real automation task (back up a directory, check disk usage and alert past a threshold, roll a log file). Require `set -euo pipefail` at the top, meaningful non-zero exit codes for each distinct failure mode, and explicit checks before destructive operations rather than assuming prior commands succeeded. Deliberately introduce a failure partway through a run (a missing file, an unwritable target) and confirm the script stops and reports clearly instead of limping forward with a partial, silent failure.

## 8. Lab 8 — Break Something on Purpose and Diagnose It Methodically

**Goal:** Practice structured troubleshooting under realistic pressure, using a controlled failure instead of a hypothetical one.

**Draws on:** §87 (structured troubleshooting methodology and runbooks), §88 (incident case studies).

**What to do:** Pick one deliberate failure and inflict it on a disposable VM without telling yourself in advance exactly what you broke: fill a filesystem to 100% with a large dummy file, kill a service's process out from under systemd in a way that produces a non-obvious symptom, or misconfigure a config file just enough that a service starts but behaves wrong rather than failing outright. Then work the problem using the structured methodology from §87 rather than randomly poking at it — reproduce the symptom, form a hypothesis, check the cheapest thing first, narrow scope systematically — and only look at the answer (what you actually broke) after you've either solved it or genuinely exhausted your own approach.

## 9. Lab 9 — Log Rotation and Forwarding for a Custom Application

**Goal:** Make a script or service's own log output behave like a properly operated production service's logs, not an unmanaged, ever-growing file.

**Draws on:** §85 (logging deep dive: rsyslog, `logrotate`, centralized logging pipelines).

**What to do:** Take the script or service from Lab 3 and give its log output a real lifecycle: configure `logrotate` for its log file with a sensible rotation schedule, size threshold, and retention count, and confirm a forced rotation (`logrotate -f`) behaves as configured. Then take it one step further and forward that log's content somewhere central — even a simple rsyslog forwarding rule to a second local VM counts — to practice the mechanics of centralized log shipping, not just local rotation.

## 10. Lab 10 — A Golden-Image-Style Provisioning Script and an Update Strategy

**Goal:** Reason through production-style change management, not just execute individual commands.

**Draws on:** §102 (golden images and immutable infrastructure concepts), §108 (patch and upgrade strategies: blue/green, canary, in-place vs. reimage).

**What to do:** Write a provisioning script that takes a bare VM to a known-good baseline state — the packages, users, hardened SSH config, and firewall rules from earlier labs, applied idempotently (safe to re-run without duplicating work or erroring on things that already exist). Treat that script's output as a conceptual "golden image." Then, without necessarily building the full infrastructure to do it, write out — in your own words — exactly how you would roll out a change to that baseline across a fleet using a blue/green or rolling strategy: what gets built first, what validates a new instance before traffic shifts to it, and what the rollback path looks like if the new baseline turns out to be broken.
