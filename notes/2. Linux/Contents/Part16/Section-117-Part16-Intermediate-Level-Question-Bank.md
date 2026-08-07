# Section 117 (Part 16): Intermediate-Level Question Bank

[§116](./Section-116-Part16-Beginner-Level-Question-Bank.md) covered beginner-tier questions — definitions and basic mechanics. This section raises the bar to the **intermediate tier**: questions that require some real operational experience and a deeper grasp of mechanics, not just a textbook definition — the kind of question that separates someone who has actually run these systems from someone who has only read about them.

## 1. Permissions and Identity Management

**Q: Why does running `usermod -G developers alice` without the `-a` flag cause a real, sometimes dangerous problem?**

Model answer: `-G` without `-a` sets the user's supplementary group list to exactly the groups listed, replacing whatever was there before — it doesn't add to the existing list, it overwrites it. If `alice` was already in `docker`, `sudo`, or other groups not mentioned in that command, she silently loses membership in all of them the moment the command runs. `-a` (append) is what actually adds a group without touching the rest. This is a genuinely common real-world mistake because the flag name `-G` reads like "add this group" when it actually means "these are now the only groups," and the failure mode (a user quietly losing access) often isn't noticed until something that used to work suddenly doesn't.

What this probes for: Real hands-on scar tissue with `usermod`, since this is exactly the kind of mistake that only shows up after actually breaking someone's access with it once ([§26](../Part4/Section-26-Part4-User-Group-Management-Commands.md)).

**Q: What's the practical difference between a standard permission model (owner/group/other) and an ACL, and when do you actually need the latter?**

Model answer: The standard rwx model gives exactly three permission slots per file — owner, one group, and everyone else — which is enough for most cases but breaks down when you need, say, two different groups to have different levels of access to the same file, or one specific additional user to have access without changing the file's owner or primary group. ACLs (`setfacl`/`getfacl`) let you attach permission entries for arbitrary additional users or groups beyond the standard three slots. In practice, ACLs come up in shared project directories where multiple teams with different access levels need to work against the same files, and the standard model simply doesn't have enough slots to express that.

What this probes for: Recognizing the standard model's structural limitation (only one group slot) as the actual reason ACLs exist, not just "ACLs are more granular" ([§27](../Part4/Section-27-Part4-Standard-Permission-Model.md), [§30](../Part4/Section-30-Part4-Access-Control-Lists.md)).

**Q: Explain what SUID on a shell script would do, and why most systems refuse to honor it.**

Model answer: In principle, SUID would make a script run with its owning user's privileges regardless of who invoked it, the same as it does for compiled binaries. In practice, most Linux kernels ignore the SUID bit on scripts (interpreted files starting with a shebang) specifically because of a well-known race condition and symlink-swap exploitation class — an attacker could potentially swap the script's contents or manipulate the interpreter invocation between the kernel checking permissions and the interpreter actually reading the file, executing arbitrary code with elevated privileges. Because of this, privileged operations needing SUID-style elevation are generally implemented as compiled binaries, or delegated to `sudo` rules instead.

What this probes for: Awareness that SUID-on-scripts is a real, well-documented security hole the kernel specifically guards against, not just abstract permission-bit trivia ([§28](../Part4/Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)).

**Q: What does `sudo -l` actually tell you, and why should you check it before assuming a user's access level?**

Model answer: `sudo -l` lists exactly what commands (if any) the current user is permitted to run via `sudo`, according to the resolved `/etc/sudoers` and `/etc/sudoers.d/` rules — including any restrictions to specific commands, hosts, or argument patterns rather than blanket root access. Checking it matters because sudoers rules are frequently scoped much more narrowly than "full root" — a user might only be permitted to run a specific service-restart command, and assuming broader access than that (or assuming none, when some exists) leads to either wasted troubleshooting time or a false sense of the access boundary actually in place.

What this probes for: Practical fluency with actually verifying access rather than assuming it from role or group membership alone ([§31](../Part4/Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)).

## 2. Process and Signal Handling

**Q: Why might `kill -9` fail to actually terminate a process?**

Model answer: `SIGKILL` (signal 9) can't be caught, blocked, or ignored by the target process itself, so in the overwhelming majority of cases it does work — but it can still appear to "fail" in a few specific situations: the process is stuck in an uninterruptible kernel sleep state (`D` state, typically waiting on I/O such as an unresponsive NFS mount or failing disk), in which case the kernel won't deliver any signal, including SIGKILL, until that I/O wait resolves. A process can also already be a zombie, in which case there's no live process left to kill at all — the entry that remains is just an unreclaimed exit status waiting on its parent. Distinguishing these cases is exactly why checking process state (`ps -o stat`) matters before concluding a signal simply "didn't work."

What this probes for: Real diagnostic depth beyond "SIGKILL always works" — specifically knowing about uninterruptible sleep as the genuine exception ([§35](../Part5/Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md), [§36](../Part5/Section-36-Part5-Signals.md)).

**Q: What's the difference between `nohup` and `disown`, and when would you use one over the other?**

Model answer: `nohup` is used at the time you start a command — it launches the process with `SIGHUP` ignored and redirects output away from the terminal, so the process survives the parent shell exiting, from the very first moment it runs. `disown` is applied to a job that's already running in your current shell (typically backgrounded with `&`) — it removes the job from the shell's job table so the shell won't send it `SIGHUP` when the shell exits, but it doesn't retroactively change signal handling the way starting with `nohup` does. In practice: use `nohup` when you know in advance a long-running command needs to survive your session ending; use `disown` when you forgot to and the process is already running.

What this probes for: Correctly distinguishing "prevention at launch time" from "after-the-fact detachment," a distinction often blurred by candidates who've only used one of the two ([§37](../Part5/Section-37-Part5-Foreground-Background-Jobs-Nohup-Disown-Screen-Tmux.md)).

**Q: Why does `nice`/`renice` sometimes have less effect than expected on a process's actual scheduling behavior?**

Model answer: `nice` values only influence the CPU scheduler's relative prioritization among processes competing for CPU time — they do nothing for processes that are blocked waiting on I/O, memory, or locks rather than CPU, which is a large fraction of real-world slowness. A process reniced to the lowest priority will still get CPU time immediately if it's the only runnable process on the system, since niceness only matters under actual CPU contention. Expecting `renice` to fix an I/O-bound or memory-starved process is a common misapplication of the tool to the wrong bottleneck.

What this probes for: Understanding that niceness is specifically a CPU-scheduling lever, not a general-purpose "make this less impactful" knob ([§38](../Part5/Section-38-Part5-Process-Priority-Nice-Renice.md)).

**Q: What's a practical reason a cron job might silently fail to run correctly even though the crontab entry looks correct?**

Model answer: The most common cause is environment differences — cron jobs run with a minimal environment, not the interactive shell's full `PATH` and variables, so a script that works fine when run manually can fail under cron because it can't find a binary or expects an environment variable that isn't set. Other common causes include the job assuming a working directory it isn't actually launched from, and output/errors going nowhere because cron mails job output to a local mail spool nobody checks rather than to a visible log. Diagnosing this usually means explicitly setting `PATH` in the crontab or script, using absolute paths throughout, and redirecting output to a file to actually see what's failing.

What this probes for: Real operational exposure to the classic "works interactively, fails under cron" environment gap ([§39](../Part5/Section-39-Part5-Scheduling-Tasks-Cron-At-Systemd-Timers.md)).

## 3. Shell Scripting and Automation

**Q: What's the practical difference between `$@` and `$*` in a Bash script, and when does it actually matter?**

Model answer: Both expand to all positional arguments, but they behave differently when quoted: `"$@"` expands to each argument as its own separate, individually-quoted word, preserving arguments that contain spaces correctly. `"$*"` expands to all arguments joined into a single string using the first character of `IFS` (a space by default), which merges everything into one word. The difference is invisible with simple single-word arguments, but it matters as soon as any argument contains spaces or needs to be passed on to another command as distinct arguments — using `"$*"` there will silently mangle multi-word arguments into one.

What this probes for: Whether the candidate has actually been bitten by this distinction in a real script, since it's an easy trap that only surfaces with certain input ([§47](../Part6/Section-47-Part6-Functions-Arrays-String-Manipulation.md)).

**Q: Why is `set -euo pipefail` commonly recommended near the top of production Bash scripts?**

Model answer: `-e` causes the script to exit immediately if any command fails (non-zero exit), instead of silently continuing past a failure. `-u` treats references to unset variables as an error rather than silently expanding to an empty string, which catches typos in variable names early. `-o pipefail` makes a pipeline's exit status reflect the first failing command in it rather than just the last command's exit status — without it, a failure earlier in a pipe can be masked by a later command that succeeds. Together they convert several classes of silent, hard-to-notice failure into an immediate, loud script failure, which is generally what you want in automation that shouldn't proceed on a bad assumption.

What this probes for: Genuine operational judgment about defensive scripting, not just reciting the flags without explaining what specific silent failure each one prevents ([§45](../Part6/Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md), [§46](../Part6/Section-46-Part6-Control-Structures-If-Case-For-While-Until.md)).

**Q: What's the difference between using `awk` for a task versus chaining `grep`, `cut`, and `sort` together, from a maintainability standpoint?**

Model answer: Chaining several single-purpose tools is often more readable line-by-line and easier for someone unfamiliar with `awk` syntax to follow, and it fits the traditional Unix philosophy of small composable tools. A single `awk` script, once you're comfortable with its field-based model, is often more efficient (fewer processes forked, fewer intermediate pipes) and can express field-based logic more directly and compactly than several chained tools. The practical trade-off in a real team is readability and shared team familiarity versus efficiency and expressiveness — heavily piped one-liners can become genuinely hard to debug, while a well-commented `awk` script can be clearer once the team is fluent in it.

What this probes for: Practical judgment about tool choice as a team and maintainability decision, not just "which is technically more powerful" ([§48](../Part6/Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md), [§49](../Part6/Section-49-Part6-Essential-Utilities-Cut-Sort-Uniq-Tr-Wc-Xargs-Find.md)).

**Q: A script behaves differently when run as `./script.sh` versus `source script.sh` (or `. script.sh`). Why?**

Model answer: `./script.sh` executes the script in a new child shell process — any `cd`, variable exports, or `exit` calls inside it only affect that child process and vanish once it finishes, leaving the calling shell's environment untouched. `source`ing (or the `.` equivalent) runs the script's commands directly in the current shell process instead of spawning a new one — so a `cd` inside the script actually changes the calling shell's working directory, variable assignments persist in the calling shell after the script finishes, and an `exit` inside the sourced script will exit the calling shell entirely, not just a subprocess. This distinction is exactly why environment-setup scripts (like a virtualenv activation script) are meant to be sourced rather than executed directly.

What this probes for: Correctly explaining the subshell-vs-current-shell execution model, a common point of real confusion ([§45](../Part6/Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)).

## 4. Networking and Remote Access

**Q: Explain the difference between `Requires=` and `After=` in a systemd unit file, and why conflating them causes real ordering bugs.**

Model answer: `After=` is purely about ordering — it says "if this other unit is going to start at all, start it before me," but it says nothing about whether that other unit actually needs to succeed or even exist for this unit to start. `Requires=` is purely about dependency — it says "this other unit must be active for me to be considered started, and if it fails or stops, pull me down too," but by itself says nothing about the order they start in. The two are commonly combined (`After=` plus `Requires=` on the same target) because most real dependencies need both properties, and using only one of the two produces a specific, subtle bug: `After=` alone lets a service start successfully even if its dependency failed to come up, just later in sequence; `Requires=` alone can start two units in parallel with no guaranteed order, defeating the point of a dependency that needs to already be running.

What this probes for: Correctly separating "ordering" from "dependency," a distinction that a surprising number of engineers get wrong when writing their first custom unit files ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md), [§67](../Part9/Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md)).

**Q: What's the practical difference between `rsync` and `scp` for transferring files, beyond just syntax?**

Model answer: `scp` copies files wholesale every time — if you re-run it against the same destination, it re-transfers everything regardless of what's already there. `rsync` computes the delta between source and destination and transfers only the changed portions of files, which makes repeated syncs of large, mostly-unchanged directory trees dramatically faster and lower-bandwidth. `rsync` also supports resuming interrupted transfers, mirroring with deletion of files no longer present at the source, and more granular control over what gets preserved (permissions, timestamps, symlinks). `scp` remains simpler for a genuine one-off single-file copy where none of that matters.

What this probes for: Understanding rsync's delta-transfer mechanism as the actual reason it's preferred for repeated syncs, not just "rsync is the newer/better tool" ([§57](../Part7/Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)).

**Q: Why might a firewall rule added with `iptables` disappear after a reboot, and what's the fix?**

Model answer: `iptables` rules live only in the kernel's in-memory ruleset by default — running `iptables -A ...` takes effect immediately but isn't persisted anywhere on disk, so a reboot (which reinitializes the kernel's netfilter tables from scratch) wipes any rules that weren't explicitly saved. The fix is to persist the ruleset using the distribution's mechanism for it — commonly `iptables-save`/`iptables-restore` invoked from a systemd unit or init script, or a package like `iptables-persistent` on Debian-based systems — so the saved rules get reloaded at boot rather than relying on the rules surviving in memory across a restart.

What this probes for: Practical awareness of a very common real-world "why did my firewall rule vanish" incident, and knowing the actual persistence mechanism rather than just the rule syntax ([§54](../Part7/Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)).

**Q: What does SSH agent forwarding actually do, and what's the real security risk of enabling it carelessly?**

Model answer: Agent forwarding lets you SSH from your local machine into a remote host, and then from that remote host SSH onward to a third host, using your local machine's SSH keys the whole way — without ever copying your private key onto the intermediate host. The private key material never leaves your local machine; the intermediate host only gets to relay signing requests to your local agent. The risk is that anyone with root (or sufficient privilege) on that intermediate host, while your forwarded session is active, can use your forwarded agent to authenticate onward as you to anything your key has access to — so enabling it on a host you don't fully trust effectively extends your identity's reach to that host for the session's duration, even though the key itself never left your machine.

What this probes for: Correctly explaining that the risk is session-scoped impersonation via the agent socket, not "the private key gets copied to the remote host," a common misconception ([§56](../Part7/Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md)).

## 5. Systemd and Service Management

**Q: What's the difference between `systemctl stop` and `systemctl disable`, and why do people often confuse them?**

Model answer: `stop` acts on the currently running instance — it halts the service right now, but leaves its boot-time enablement untouched, so it will start again on the next reboot if it was enabled. `disable` acts on boot-time behavior — it removes the symlinks that would start the service at boot, but has no effect on whatever instance is currently running right now. Confusing the two produces two common mistakes: stopping a service expecting it to stay off after a reboot (it doesn't, if still enabled), or disabling a service expecting it to stop running immediately (it doesn't, until the next stop or reboot). Fully decommissioning a service generally needs both `stop` and `disable` together.

What this probes for: Real operational precision about current-state versus boot-time-state, a distinction that matters a lot during actual service decommissioning ([§66](../Part9/Section-66-Part9-Managing-Services-Systemctl.md)).

**Q: Why would a systemd service configured with `Restart=always` still end up permanently stopped after repeated crash-loops?**

Model answer: systemd has a built-in rate limiter (`StartLimitIntervalSec=` / `StartLimitBurst=`) that caps how many times a unit is allowed to restart within a given time window — `Restart=always` says "always try to restart after it exits," but if it crashes and restarts more than the configured burst limit within the configured interval, systemd considers the unit to have failed the start-limit and stops trying entirely, leaving it in a failed state until manually reset (`systemctl reset-failed`) or restarted. This is a deliberate safety mechanism to stop a genuinely broken service from restart-looping indefinitely and consuming resources, but it surprises engineers who expect `Restart=always` to mean literally always, unconditionally.

What this probes for: Awareness of the start-limit safety valve as a real, commonly-missed piece of systemd restart behavior ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md), [§67](../Part9/Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md)).

**Q: What's actually different about how `journalctl` stores and lets you query logs compared to traditional flat-file syslog output?**

Model answer: `journald` stores logs in a structured, indexed binary format rather than flat text lines, which lets `journalctl` filter efficiently on fields like unit name, priority, boot session, or time range without needing to grep through potentially huge text files. It also natively captures structured metadata per entry (PID, unit, boot ID) that a traditional syslog line would only have if the logging application chose to include it manually in its text output. The trade-off is that journal files aren't human-readable by direct inspection the way flat syslog files are — you need `journalctl` (or export tooling) to read them meaningfully.

What this probes for: Understanding the structured-vs-flat-text distinction as the actual reason journald enables richer querying, not just "journald is systemd's newer logging thing" ([§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)).

**Q: When would a systemd timer be a better choice than a traditional cron job, and when would cron still be preferable?**

Model answer: A systemd timer integrates with the rest of systemd's dependency and logging model — it can require other units to be active first, its execution history and output are visible via `journalctl` alongside every other service, and it supports options cron lacks natively, like automatically running a missed job after the system was powered off during its scheduled time (`Persistent=true`). Cron remains preferable when simplicity and portability matter more than integration — a crontab is a single, well-understood, distribution-agnostic file format that works identically across virtually every Unix-like system, whereas systemd timers are systemd-specific and involve two files (a `.timer` and its corresponding `.service`) instead of one line.

What this probes for: Balanced judgment rather than reflexively favoring the newer tool — recognizing cron's portability advantage as a genuine, still-valid reason to choose it ([§69](../Part9/Section-69-Part9-Systemd-Timers-Vs-Cron-Deep-Comparison.md)).

## 6. Storage and Performance

**Q: What's the practical benefit of LVM over using raw disk partitions directly, and what's the real cost of that flexibility?**

Model answer: LVM adds a layer of abstraction — physical volumes pooled into volume groups, sliced into logical volumes — that lets you resize filesystems, add and remove underlying disks, and take snapshots without the rigid constraints of fixed partition boundaries, which is genuinely valuable on systems whose storage needs grow or change over time. The cost is added complexity: an extra layer to understand and troubleshoot, a modest performance overhead versus raw partitions, and a boot process that now depends on LVM metadata being intact and correctly detected — a corrupted or misconfigured LVM metadata area can make an otherwise-healthy disk's data appear inaccessible in a way a simple partition table failure wouldn't.

What this probes for: A balanced answer that names both LVM's real benefit and its real operational cost, rather than treating it as an unconditional upgrade ([§73](../Part10/Section-73-Part10-LVM-Physical-Volumes-Volume-Groups-Logical-Volumes.md), [§74](../Part10/Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md)).

**Q: `df` and `du` can report wildly different numbers for "how full is this filesystem." Why, and what's a common real cause?**

Model answer: `df` reports space usage from the filesystem's own accounting, while `du` calculates usage by walking the directory tree and summing file sizes it can actually see. A common cause of divergence is a file that's been deleted but is still held open by a running process — the filesystem still has the space allocated (so `df` shows it as used) but `du`, which only sees what's reachable in the directory tree, doesn't count it because there's no longer a directory entry pointing to it. This is a very common "disk full but I can't find what's using the space" scenario, and the fix is finding and dealing with the process still holding the deleted file open (via `lsof`), not searching the directory tree harder.

What this probes for: Real diagnostic experience with the deleted-but-open-file gap between df and du, a classic troubleshooting scenario ([§76](../Part10/Section-76-Part10-Filesystem-Creation-Checking-Repair.md), [§83](../Part11/Section-83-Part11-Disk-IO-Analysis.md)).

**Q: What does a high load average actually measure, and why can it be misleading on its own?**

Model answer: Load average represents the average number of processes that are either running on CPU or waiting in a runnable/uninterruptible state, averaged over 1, 5, and 15 minute windows — it is not a CPU-utilization percentage. A high load average can come entirely from processes stuck in uninterruptible I/O wait (disk or network storage issues) with CPU utilization actually low, which is a very different problem from CPU saturation, even though both would show up as "high load." Reading load average without also checking CPU utilization and I/O wait breakdown risks diagnosing a storage problem as a CPU problem, or vice versa.

What this probes for: Correctly distinguishing load average from CPU usage, and knowing it includes uninterruptible I/O wait, not just runnable processes ([§81](../Part11/Section-81-Part11-CPU-Load-Analysis.md)).

**Q: Why does deleting files not always immediately free up reported disk space, even without any process holding them open?**

Model answer: Beyond the held-open-file case, a common cause is deleting the visible files but not their snapshots — if the filesystem or LVM has a snapshot referencing the old data blocks, that space stays allocated to the snapshot even after the live filesystem no longer references it, since the snapshot's whole purpose is to preserve a past state. Reclaiming the space actually requires removing or aging out the snapshot as well as the live files, which is a common surprise for administrators used to simple filesystems without snapshot support.

What this probes for: Awareness that snapshot-aware filesystems (and LVM snapshots) change the mental model of what "deleting a file" actually frees ([§74](../Part10/Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md), [§76](../Part10/Section-76-Part10-Filesystem-Creation-Checking-Repair.md)).

## 7. Key Takeaways

- Intermediate-tier questions consistently probe operational mechanics — what actually happens under the hood — rather than definitions: why `usermod -G` overwrites, why load average isn't CPU usage, why `iptables` rules vanish on reboot.
- A recurring pattern is distinguishing two similar-sounding things that are actually mechanically different: `Requires=` vs. `After=`, `stop` vs. `disable`, `nohup` vs. `disown`, `df` vs. `du` — precision on these pairs is a strong intermediate-tier signal.
- Several answers here (systemd dependency semantics, LVM trade-offs, load-average interpretation) are direct prerequisites for the diagnostic synthesis the senior tier ([§118](./Section-118-Part16-Senior-Engineer-Question-Bank.md)) demands next.

## 8. Related Concepts & What's Next

This section drew questions from roughly Parts 4–11 ([§25](../Part4/Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md)–[§88](../Part11/Section-88-Part11-Incident-Case-Studies.md)) — permissions and identity, process and signal handling, shell scripting, networking and remote access, systemd service management, and storage/performance fundamentals. [§118](./Section-118-Part16-Senior-Engineer-Question-Bank.md) (next) moves to the senior-engineer tier: questions requiring synthesis across multiple concepts and genuine production diagnostic reasoning, drawing on topics spanning roughly Parts 8–14.

**Next Section:** [§118](./Section-118-Part16-Senior-Engineer-Question-Bank.md) — `Section-118-Part16-Senior-Engineer-Question-Bank.md`
