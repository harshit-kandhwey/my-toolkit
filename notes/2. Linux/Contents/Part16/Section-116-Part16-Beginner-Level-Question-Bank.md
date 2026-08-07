# Section 116 (Part 16): Beginner-Level Question Bank

Part 15 ([§111](../Part15/Section-111-Part15-Linux-Administration-Best-Practices-Checklist.md)–[§115](../Part15/Section-115-Part15-Linux-Vs-Other-Operating-Systems-Decision-Criteria.md)) closed out the mastery phase — best practices, anti-patterns, version differences, and deprecated-tool replacements consolidated across Parts 1–15. This Part ([§116](./Section-116-Part16-Beginner-Level-Question-Bank.md)–[§122](./Section-122-Part16-Hiring-Manager-Behavioral-Technical-Crossover-Questions.md)) is the roadmap's dedicated interview-preparation phase, and unlike every prior Part it introduces no new material of its own — its entire purpose is compiling practice questions, tier by tier, drawing on topics from across the whole roadmap. This section, [§116](./Section-116-Part16-Beginner-Level-Question-Bank.md), opens that bank at the **beginner tier**: questions that test basic factual knowledge and fundamental understanding — definitions, mechanics, "what does this command do" — rather than the nuanced trade-offs later tiers will demand.

## 1. Foundations and Architecture

**Q: What is the difference between the Linux kernel, the operating system, and a distribution?**

Model answer: The kernel is the core program that manages hardware, memory, processes, and system calls — it's a single component, not the whole OS. The operating system is the kernel plus the userland tools built around it (shell, core utilities, libraries) needed to actually do useful work. A distribution packages the kernel, userland, a package manager, default configuration, and installation tooling into a coherent, installable product — Ubuntu and RHEL are both "Linux" at the kernel level but differ substantially in packaging, defaults, and tooling.

What this probes for: Whether the candidate conflates "Linux" with a single monolithic thing, versus understanding it as a layered kernel/OS/distribution stack ([§1](../Part1/Section-01-Part1-What-Linux-Is-Kernel-vs-OS-vs-Distribution.md)).

**Q: Is the Linux kernel monolithic or microkernel, and what does that mean in practice?**

Model answer: The Linux kernel is monolithic — the core subsystems (process scheduler, memory manager, virtual filesystem, network stack, device drivers) all run in a single privileged kernel space rather than as separate isolated services communicating over messages, which is how a microkernel design works. In practice this means kernel subsystems can call each other directly and efficiently, at the cost of a bug in one subsystem (like a driver) being able to affect the whole kernel rather than being isolated to its own process.

What this probes for: Basic recognition of the monolithic-vs-microkernel distinction and its practical trade-off ([§9](../Part2/Section-09-Part2-Kernel-Monolithic-Design-Kernel-vs-User-Space.md)).

**Q: What happens during a Linux boot, from power-on to a usable login prompt?**

Model answer: Firmware (BIOS or UEFI) initializes hardware and hands off to a bootloader (commonly GRUB), which loads the kernel and an initial RAM filesystem (initramfs) into memory. The kernel initializes hardware drivers and mounts the real root filesystem, then hands control to PID 1 — the init system (systemd on virtually all modern distributions) — which brings up services and mounts in dependency order until the system reaches a usable state.

What this probes for: A correct high-level sequence (firmware → bootloader → kernel → init) without needing deep internals yet ([§12](../Part2/Section-12-Part2-Boot-Process.md)).

**Q: What is PID 1, and why is it different from every other process on the system?**

Model answer: PID 1 is the first userspace process the kernel starts directly during boot — it isn't forked from anything else. It's the ancestor of every other process on the system, it's responsible for eventually reaping orphaned processes re-parented to it, and if it crashes the kernel panics rather than restarting it, because there's nothing left to do the restarting.

What this probes for: Basic grasp of PID 1's structural uniqueness, not just "it's the init process" ([§13](../Part2/Section-13-Part2-Init-Systems.md)).

## 2. Filesystem and Storage

**Q: What is the difference between a hard link and a symbolic link?**

Model answer: A hard link is a second directory entry pointing at the exact same inode as the original file — there's no "original" and "copy," both names are equally valid references to the same underlying data, and the data isn't actually removed until every hard link to it is deleted. A symbolic link is a separate small file that just stores a path to another file — it has its own inode, can point across filesystems (hard links can't), and breaks if the target is moved or deleted, leaving a dangling link.

What this probes for: Correct understanding that hard links share an inode while symlinks are path references with their own inode ([§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md)).

**Q: What does `chmod 755` mean when applied to a file?**

Model answer: The three digits represent permissions for owner, group, and others respectively, each digit being a sum of read (4), write (2), and execute (1). `7` (4+2+1) gives the owner read, write, and execute; `5` (4+1) gives group and others read and execute but not write. So `chmod 755` is a common pattern for an executable script or directory: the owner has full control, and everyone else can read and execute/traverse it but not modify it.

What this probes for: Comfort translating octal permission notation into actual rwx meaning, a baseline skill for any filesystem work ([§27](../Part4/Section-27-Part4-Standard-Permission-Model.md)).

**Q: What's the purpose of `/etc/fstab`?**

Model answer: `/etc/fstab` is the static table of filesystems the system should mount at boot — each line specifies a device (or UUID/label), a mount point, the filesystem type, and mount options. It's what lets the system automatically mount disks and partitions without manual intervention every time it boots, and it's the standard place to add a new persistent mount for a disk that should always be available.

What this probes for: Basic familiarity with fstab as the declarative mount configuration file, not just knowing the `mount` command exists ([§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)).

**Q: What is an inode, and what information does it actually store?**

Model answer: An inode is a data structure that stores a file's metadata — permissions, owner, group, size, timestamps, and pointers to the actual data blocks on disk — but notably not the filename itself; filenames live in directory entries that map a name to an inode number. This is exactly why multiple names (hard links) can point at one inode, and why renaming a file doesn't change its inode or its data.

What this probes for: Recognizing that the filename is separate from the inode, which underpins understanding hard links correctly ([§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md)).

## 3. Users, Permissions, and Access Control

**Q: Where does Linux store user account information, and why is the password hash kept in a separate file from the rest of the account details?**

Model answer: Basic account information (username, UID, GID, home directory, shell) lives in `/etc/passwd`, which is world-readable by design since many tools need to look up account details. Password hashes live in `/etc/shadow`, which is readable only by root — separating the two means every program that needs to check "does this UID exist" doesn't also get read access to password hash material, reducing the exposure of hashes to offline cracking attempts.

What this probes for: Understanding the security reasoning behind the passwd/shadow split, not just that it exists ([§25](../Part4/Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md)).

**Q: What is the difference between a user's primary group and their supplementary groups?**

Model answer: A primary group is the single group recorded directly in `/etc/passwd` for that user, and it's the group assigned to files the user creates by default. Supplementary (or secondary) groups are additional group memberships recorded in `/etc/group`, granting access to resources restricted to those groups without changing which group new files get created under.

What this probes for: Basic clarity on the primary-vs-supplementary group distinction, a prerequisite for understanding common `usermod` mistakes at later tiers ([§25](../Part4/Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md), [§26](../Part4/Section-26-Part4-User-Group-Management-Commands.md)).

**Q: What does `sudo` actually do, and how is it different from logging in as root directly?**

Model answer: `sudo` lets an authorized user run a specific command with elevated (typically root) privileges, governed by rules in `/etc/sudoers`, and it logs who ran what and when. Logging in as root directly gives unrestricted, unaudited access with no per-command record of which human took which action — `sudo` preserves individual accountability and lets access be scoped narrowly, rather than granting blanket root privileges to every administrator.

What this probes for: Understanding that `sudo`'s value is accountability and scoping, not just "another way to become root" ([§31](../Part4/Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)).

**Q: What are the special permission bits SUID and SGID used for, at a basic level?**

Model answer: SUID (set-user-ID), when set on an executable, makes it run with the file owner's privileges rather than the invoking user's — `passwd` is a classic example, since it needs root privileges to update `/etc/shadow` even when run by an ordinary user. SGID works the same way for the group, and on a directory it makes new files created inside inherit the directory's group rather than the creating user's primary group.

What this probes for: Baseline recognition of what these bits do mechanically, before later tiers probe the security risk of misapplied SUID ([§28](../Part4/Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)).

## 4. Processes and Job Control

**Q: What is a PID, and can two running processes ever share one?**

Model answer: A PID (process ID) is the unique numeric identifier the kernel assigns to every running process. Two processes can never share a PID at the same time — the kernel guarantees uniqueness among currently-running processes, though PIDs do get reused once a process exits and enough time/wraparound has passed.

What this probes for: A clean, correct definition without conflating PID uniqueness with permanence ([§33](../Part5/Section-33-Part5-What-A-Process-Is.md)).

**Q: What's the difference between `ps` and `top`?**

Model answer: `ps` takes a single snapshot of running processes at the moment it's run and prints it as static text, suitable for scripting or a one-off look. `top` is an interactive, continuously refreshing view that updates in place, showing live CPU and memory usage sorted dynamically — better for actively watching what's happening on a system right now rather than capturing a single point-in-time record.

What this probes for: Knowing these aren't interchangeable — snapshot vs. live monitoring — a common first distinction new administrators learn ([§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)).

**Q: What is a zombie process?**

Model answer: A zombie is a process that has finished executing and exited, but whose exit status hasn't yet been collected (`wait()`ed on) by its parent — the kernel keeps a minimal entry for it (just the PID and exit status) until the parent reads that status. It's not consuming CPU or doing any real work; it's just an entry waiting to be cleaned up, and it becomes a real problem only if it accumulates because a parent process never collects it.

What this probes for: Correct basic definition, distinguishing zombie from a truly "stuck" or resource-consuming process ([§35](../Part5/Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md)).

**Q: What's the difference between `SIGTERM` and `SIGKILL`?**

Model answer: `SIGTERM` (signal 15, the default sent by `kill`) asks a process to terminate gracefully — a well-behaved process can catch it, clean up open files or connections, and exit on its own terms. `SIGKILL` (signal 9) terminates the process immediately and unconditionally at the kernel level — it cannot be caught, blocked, or ignored, so it skips any graceful cleanup the process might otherwise have done.

What this probes for: Basic awareness that these aren't interchangeable "harder" versions of the same thing — one is a polite request, one is unconditional ([§36](../Part5/Section-36-Part5-Signals.md)).

## 5. Shell, Scripting, and Text Processing

**Q: What's the difference between `>` and `>>` in shell redirection?**

Model answer: `>` redirects output to a file, overwriting the file's existing contents entirely if it already exists (or creating it if it doesn't). `>>` appends output to the end of the file instead, preserving whatever was already there. Using `>` when `>>` was intended is a common way to accidentally destroy existing log or data file contents.

What this probes for: A precise, correct answer rather than a vague "they both redirect output" — the destructive-vs-additive distinction matters in practice ([§43](../Part6/Section-43-Part6-Redirection-Pipes-Stdin-Stdout-Stderr.md)).

**Q: What does the shebang line (`#!/bin/bash`) at the top of a script actually do?**

Model answer: The shebang tells the kernel which interpreter should execute the rest of the file when it's run directly (e.g. `./script.sh`) — the kernel reads that first line and execs the named interpreter, passing the script's path as an argument to it. Without a correct shebang, running the script directly may use the wrong shell or fail, though it can still be run explicitly as `bash script.sh` regardless.

What this probes for: Understanding the shebang's actual mechanical purpose, not just "it's required at the top of every script" ([§45](../Part6/Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)).

**Q: What is the basic difference between `grep`, `sed`, and `awk`?**

Model answer: `grep` searches text for lines matching a pattern and prints (or filters) matching lines. `sed` is a stream editor that can search and transform text — most commonly used for find-and-replace substitutions on a line-by-line basis. `awk` is a more complete text-processing language built around fields and records, suited to tasks like extracting or computing over specific columns of structured text, which is beyond what `grep` or basic `sed` usage typically does.

What this probes for: A correct high-level division of labor among the three, since new administrators often use them interchangeably without understanding what each is actually for ([§48](../Part6/Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md)).

**Q: What does an exit code of `0` mean for a shell command, and what does a non-zero exit code mean?**

Model answer: An exit code of `0` conventionally means the command completed successfully. Any non-zero value indicates some kind of failure or abnormal condition, though the specific non-zero number's meaning is command-specific (some tools use different non-zero codes to distinguish different failure types). This convention is what lets shell control operators like `&&` and `||` make decisions based on whether the previous command succeeded.

What this probes for: Basic but essential knowledge underlying all shell scripting logic and error handling ([§45](../Part6/Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)).

## 6. Networking and Package Management

**Q: What's the difference between TCP and UDP at a basic level?**

Model answer: TCP is connection-oriented and guarantees ordered, reliable delivery — it establishes a connection, acknowledges received data, and retransmits lost packets, at the cost of more overhead. UDP is connectionless and makes no delivery or ordering guarantees — packets are just sent, with no handshake and no automatic retransmission — which makes it lighter-weight and suited to use cases where occasional loss is acceptable and low latency matters more than guaranteed delivery.

What this probes for: A correct, basic contrast rather than just "TCP is reliable, UDP is fast" without explaining the actual mechanism ([§51](../Part7/Section-51-Part7-Networking-Fundamentals-Recap.md)).

**Q: What does the `ping` command actually test?**

Model answer: `ping` sends ICMP echo request packets to a target host and waits for ICMP echo reply packets back, measuring round-trip time and packet loss. A successful ping confirms basic network reachability at the IP layer, but it doesn't confirm that a specific service or application on that host is actually working — a host can respond to ping while the web server or database on it is completely down.

What this probes for: Understanding what ping actually verifies (basic reachability) versus what it doesn't (application-level health) ([§55](../Part7/Section-55-Part7-Network-Diagnostics.md)).

**Q: What's the difference between `apt` and `dpkg` on a Debian-based system?**

Model answer: `dpkg` is the low-level package tool that installs, removes, and queries individual `.deb` package files directly, but it has no concept of remote repositories and won't automatically resolve or fetch a package's dependencies. `apt` is the higher-level tool built on top of `dpkg` that adds repository management and automatic dependency resolution — it figures out what else needs installing and fetches everything from configured repositories, then hands the actual installation work to `dpkg`.

What this probes for: Correctly placing the two tools in a layered relationship rather than treating them as interchangeable alternatives ([§60](../Part8/Section-60-Part8-Debian-Tooling-Dpkg-Apt-Apt-Get.md)).

**Q: What is a systemd unit, in basic terms?**

Model answer: A unit is systemd's declarative configuration file describing something it manages — most commonly a service (a `.service` unit describing a program to run and how to run it), but also mount points, timers, sockets, and other resource types. Instead of an imperative shell script telling the system step by step what to do, a unit file declares what the thing is and what it depends on, and systemd figures out how and when to start it.

What this probes for: Basic recognition that unit files are declarative configuration, not scripts, as a foundation for later systemd-tier questions ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)).

## 7. Key Takeaways

- Beginner-tier questions test whether foundational vocabulary and mechanics are solid — kernel vs. OS vs. distribution, PID 1's role, inode vs. filename, TCP vs. UDP — before any nuanced trade-off reasoning is expected.
- A recurring theme across this tier is precision over vague familiarity: knowing that `>` overwrites while `>>` appends, or that `SIGKILL` cannot be caught while `SIGTERM` can, is the kind of specific correctness beginner interviews actually check for.
- Several answers here set up distinctions the intermediate tier ([§117](./Section-117-Part16-Intermediate-Level-Question-Bank.md)) will build directly on top of — primary vs. supplementary groups, zombie processes, and unit files all recur in deeper form at the next tier.

## 8. Related Concepts & What's Next

This section drew questions from across Parts 1–9 ([§1](../Part1/Section-01-Part1-What-Linux-Is-Kernel-vs-OS-vs-Distribution.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)) — foundations, kernel architecture, filesystem basics, permissions, process management, shell fundamentals, networking, package management, and systemd's basic vocabulary. [§117](./Section-117-Part16-Intermediate-Level-Question-Bank.md) (next) raises the bar to the intermediate tier: questions requiring real operational experience and deeper mechanical understanding rather than definitional recall, drawing on topics spanning roughly Parts 4–11.

**Next Section:** [§117](./Section-117-Part16-Intermediate-Level-Question-Bank.md) — `Section-117-Part16-Intermediate-Level-Question-Bank.md`
