# 00 — Roadmap: Linux (Complete Topic Roadmap)

## 0. Assumption Line

Linux is treated in its most common **DevOps / Cloud / Infrastructure / SRE engineering** interpretation: Linux as a production server operating system (kernel + userland, primarily via distributions such as Ubuntu/Debian and RHEL/CentOS/Rocky/Alma family), covering administration, shell usage, networking, storage, security, automation, and enterprise operations — rather than desktop usage, embedded Linux, or kernel driver development. Kernel internals are covered to the depth required for a senior engineer/architect/SRE interview and for real troubleshooting, not to the depth of a kernel contributor.

Because Linux is an extremely broad subject, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations and History

1.1 What Linux Is; Kernel vs. OS vs. Distribution
1.2 History and Evolution (Unix → GNU → Linux → Modern Distros)
1.3 The Open-Source Model, Licensing (GPL), and Community Governance
1.4 Linux Philosophy and Design Principles
1.5 Major Distribution Families (Debian/Ubuntu, RHEL/Fedora, SUSE, Arch, Alpine) and How to Choose
1.6 Where Linux Runs Today (servers, cloud, embedded, mobile/Android, supercomputers, containers)
1.7 Prerequisites Recap and How This Roadmap Is Organized

### Part 2 — Architecture and the Kernel

2.1 System Architecture Overview (hardware → kernel → userland → applications)
2.2 The Linux Kernel: Monolithic Design, Kernel Space vs. User Space
2.3 Kernel Components (process scheduler, memory manager, VFS, network stack, device drivers)
2.4 System Calls and the Kernel–Userland Boundary
2.5 Boot Process: BIOS/UEFI → Bootloader (GRUB) → Kernel → initramfs → init/systemd
2.6 init Systems: SysVinit vs. Upstart vs. systemd (deep dive in Part 9)
2.7 Kernel Modules (lsmod, modprobe, insmod, /lib/modules)
2.8 Interrupts, Context Switching, and CPU Scheduling Fundamentals
2.9 Virtual Memory, Paging, and Swap Fundamentals

### Part 3 — The Filesystem and Storage Basics

3.1 Filesystem Hierarchy Standard (FHS): /, /etc, /bin, /usr, /var, /home, /tmp, /proc, /sys, /dev
3.2 Filesystem Types (ext4, XFS, Btrfs, ZFS overview, tmpfs, overlayfs)
3.3 Inodes, Hard Links, and Symbolic Links
3.4 Mounting and Unmounting, /etc/fstab, mount options
3.5 File and Directory Operations (navigation, creation, copying, moving, deletion) — full command template
3.6 File Metadata: timestamps, ownership, attributes (chattr/lsattr)
3.7 Disk Partitioning Concepts (MBR vs. GPT), fdisk/parted/gdisk
3.8 /proc and /sys Virtual Filesystems for Introspection

### Part 4 — Users, Permissions, and Access Control

4.1 Users and Groups: /etc/passwd, /etc/shadow, /etc/group
4.2 User and Group Management Commands (useradd, usermod, userdel, groupadd, etc.)
4.3 Standard Permission Model (rwx, owner/group/other), chmod, chown, chgrp
4.4 Special Permissions: SUID, SGID, Sticky Bit
4.5 umask and Default Permissions
4.6 Access Control Lists (ACLs): getfacl, setfacl
4.7 sudo, /etc/sudoers, and Privilege Escalation Model
4.8 PAM (Pluggable Authentication Modules) Overview

### Part 5 — Process and Job Management

5.1 What a Process Is: PID, PPID, Process States
5.2 Viewing Processes: ps, top, htop, /proc/[pid]
5.3 Process Lifecycle: fork, exec, wait, zombie and orphan processes
5.4 Signals: SIGTERM, SIGKILL, SIGHUP, SIGINT, and Signal Handling
5.5 Foreground/Background Jobs, nohup, disown, screen/tmux
5.6 Process Priority: nice and renice
5.7 Scheduling Tasks: cron, at, systemd timers
5.8 Inter-Process Communication Overview (pipes, sockets, shared memory — conceptual)

### Part 6 — Shell, Scripting, and Text Processing

6.1 Shells Overview (bash, sh, zsh) and Shell Configuration Files
6.2 Shell Basics: variables, quoting, expansion, command substitution
6.3 Redirection and Pipes (stdin, stdout, stderr, |, >, >>, 2>&1)
6.4 Command Chaining and Control Operators (&&, ||, ;)
6.5 Bash Scripting Fundamentals: shebang, arguments, exit codes
6.6 Control Structures: if/else, case, for, while, until
6.7 Functions, Arrays, and String Manipulation in Bash
6.8 Text Processing Tools: grep, sed, awk (each with full command template)
6.9 Other Essential Utilities: cut, sort, uniq, tr, wc, xargs, find
6.10 Regular Expressions for Linux Administration

### Part 7 — Networking

7.1 Networking Fundamentals Recap (IP, TCP/UDP, DNS, routing) as applied to Linux
7.2 Network Configuration Tools: ip, nmcli, netplan, /etc/network/interfaces
7.3 DNS Resolution on Linux: /etc/resolv.conf, /etc/hosts, nsswitch.conf
7.4 Firewalls: iptables, nftables, firewalld, ufw
7.5 Network Diagnostics: ping, traceroute, ss, netstat, tcpdump, dig, curl
7.6 SSH: Architecture, Key-Based Auth, Config, Tunneling, Hardening
7.7 Remote File Transfer: scp, rsync, sftp
7.8 Network Services on Linux (systemd-networkd, NetworkManager)

### Part 8 — Package Management and Software Installation

8.1 Package Management Concepts (repositories, dependency resolution, package formats)
8.2 Debian-Based Tooling: dpkg, apt, apt-get, .deb files
8.3 RHEL-Based Tooling: rpm, yum, dnf, .rpm files
8.4 Building From Source: configure/make/make install, checkinstall
8.5 Universal Package Formats: Snap, Flatpak, AppImage (overview and trade-offs)
8.6 Managing Repositories and GPG Signing Keys

### Part 9 — System Administration and Services (systemd Deep Dive)

9.1 systemd Architecture: units, targets, dependencies
9.2 Managing Services: systemctl (start/stop/enable/status/mask)
9.3 Writing Custom systemd Unit Files
9.4 journald and Centralized Logging (journalctl)
9.5 systemd Timers vs. cron (deep comparison)
9.6 Runlevels/Targets and System State Transitions
9.7 Environment Configuration: /etc/environment, profile.d, systemd environment files
9.8 Time Synchronization: chrony/ntpd, timedatectl

### Part 10 — Advanced Storage and LVM

10.1 Logical Volume Manager (LVM): Physical Volumes, Volume Groups, Logical Volumes
10.2 Resizing, Snapshots, and Thin Provisioning with LVM
10.3 RAID Concepts and mdadm (software RAID)
10.4 Filesystem Creation, Checking, and Repair (mkfs, fsck, tune2fs/xfs_repair)
10.5 Swap Management (swapon, swapoff, swap files vs. partitions)
10.6 Network Storage: NFS and Samba Basics
10.7 Backup Strategies and Tools (tar, rsync, dd, enterprise backup concepts)

### Part 11 — Performance, Monitoring, and Troubleshooting

11.1 Performance Fundamentals: CPU, Memory, Disk I/O, Network as a Unified Model
11.2 CPU and Load Analysis: uptime, top, mpstat, vmstat
11.3 Memory Analysis: free, /proc/meminfo, OOM Killer
11.4 Disk I/O Analysis: iostat, iotop, df, du
11.5 Network Performance Analysis: iftop, nload, sar
11.6 Logging Deep Dive: rsyslog, log rotation (logrotate), centralized logging pipelines
11.7 Observability on Linux: metrics, tracing (strace, ltrace, perf), APM concepts
11.8 Structured Troubleshooting Methodology and Runbooks
11.9 Incident Case Studies (disk full, memory leak, fork bomb, network saturation, zombie apocalypse)

### Part 12 — Security Hardening

12.1 Linux Security Model Recap and Threat Landscape
12.2 SSH Hardening and Bastion Host Patterns
12.3 SELinux and AppArmor (Mandatory Access Control)
12.4 Kernel Hardening and sysctl Security Parameters
12.5 Auditing: auditd, ausearch, aureport
12.6 Vulnerability Management and Patch Management
12.7 Secrets Management on Linux Hosts
12.8 CIS Benchmarks and Compliance Frameworks (concept-level)

### Part 13 — Automation and DevOps Integration

13.1 Infrastructure as Code on Linux (concept-level: Ansible, Terraform provisioning of Linux hosts)
13.2 Configuration Management Concepts (idempotency, desired state)
13.3 Linux as the Foundation for Containers: namespaces, cgroups, chroot, OverlayFS (Docker/Kubernetes handoff)
13.4 CI/CD Runners on Linux
13.5 Shell Scripting for Automation Pipelines
13.6 Golden Images and Immutable Infrastructure Concepts

### Part 14 — Production, Enterprise, and Cloud Operations

14.1 Enterprise Linux Distributions and Support Models (RHEL subscriptions, Ubuntu LTS)
14.2 Linux in AWS/Azure/GCP (AMIs, VM images, cloud-init)
14.3 High Availability Architectures (Pacemaker/Corosync overview, load-balanced fleets)
14.4 Disaster Recovery and Backup/Restore at Scale
14.5 Capacity Planning for Linux Fleets
14.6 Patch and Upgrade Strategies (blue/green, canary, in-place vs. reimage)
14.7 Cost Optimization for Linux Infrastructure
14.8 Compliance and Governance in Regulated Environments

### Part 15 — Mastery: Best Practices, Anti-Patterns, and Comparisons

15.1 Linux Administration Best Practices Checklist
15.2 Common Anti-Patterns and Mistakes
15.3 Version and Distribution Differences That Matter (init systems, package managers, kernel versions)
15.4 Deprecated Tools and Modern Replacements (ifconfig→ip, iptables→nftables, netstat→ss)
15.5 Linux vs. Other Operating Systems — Decision Criteria

### Part 16 — Interview Preparation

16.1 Beginner-Level Question Bank
16.2 Intermediate-Level Question Bank
16.3 Senior Engineer Question Bank
16.4 Architect-Level Question Bank
16.5 FAANG-Style and System-Design Question Bank
16.6 Scenario-Based Production Troubleshooting Questions
16.7 Hiring-Manager and Behavioral-Technical Crossover Questions

### Part 17 — Wrap-Up

17.1 Progressive Hands-On Labs (beginner → production-style)
17.2 Consolidated Key-Takeaways Checklist
17.3 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                 | Needed For    | Introduced                          |
| -------------------------------------------- | ------------- | ----------------------------------- |
| Basic computer literacy (files, directories) | Part 1        | Assumed baseline                    |
| Basic networking concepts (IP, DNS)          | Part 7        | Briefly recapped in 7.1             |
| Basic command-line comfort                   | Part 3 onward | Built progressively starting Part 3 |

No external topic must be studied before starting; this roadmap builds every prerequisite in place.

---

## 3. Learning Phases

| Phase                             | Parts Covered   | Goal                                              |
| --------------------------------- | --------------- | ------------------------------------------------- |
| Phase 1 — Foundations             | Part 1, Part 2  | Understand what Linux is and how it's built       |
| Phase 2 — Core Skills             | Part 3, 4, 5, 6 | Filesystem, permissions, processes, shell fluency |
| Phase 3 — Connectivity & Software | Part 7, 8       | Networking and package management                 |
| Phase 4 — Administration          | Part 9, 10      | Services, systemd, advanced storage               |
| Phase 5 — Operations              | Part 11, 12     | Performance, monitoring, security                 |
| Phase 6 — Production Engineering  | Part 13, 14     | Automation, cloud, enterprise operations          |
| Phase 7 — Mastery                 | Part 15         | Best practices, comparisons, version awareness    |
| Phase 8 — Interview Readiness     | Part 16         | Full interview question bank                      |
| Phase 9 — Wrap-Up                 | Part 17         | Labs, checklists, next steps                      |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `2.4`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (AWS, Azure, GCP, GIT). Section numbers (`§`) are continuous across the entire 17-part roadmap (1–125), not reset per part.

| Part                                               | Roadmap Range | Continuous § Range | Folder             |
| -------------------------------------------------- | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations and History                   | 1.1–1.7       | §1–§7              | `Contents/Part1/`  |
| Part 2 — Architecture and the Kernel               | 2.1–2.9       | §8–§16             | `Contents/Part2/`  |
| Part 3 — Filesystem and Storage Basics             | 3.1–3.8       | §17–§24            | `Contents/Part3/`  |
| Part 4 — Users, Permissions, Access Control        | 4.1–4.8       | §25–§32            | `Contents/Part4/`  |
| Part 5 — Process and Job Management                | 5.1–5.8       | §33–§40            | `Contents/Part5/`  |
| Part 6 — Shell, Scripting, Text Processing         | 6.1–6.10      | §41–§50            | `Contents/Part6/`  |
| Part 7 — Networking                                | 7.1–7.8       | §51–§58            | `Contents/Part7/`  |
| Part 8 — Package Management                        | 8.1–8.6       | §59–§64            | `Contents/Part8/`  |
| Part 9 — Systemd and Services                      | 9.1–9.8       | §65–§72            | `Contents/Part9/`  |
| Part 10 — Advanced Storage and LVM                 | 10.1–10.7     | §73–§79            | `Contents/Part10/` |
| Part 11 — Performance, Monitoring, Troubleshooting | 11.1–11.9     | §80–§88            | `Contents/Part11/` |
| Part 12 — Security Hardening                       | 12.1–12.8     | §89–§96            | `Contents/Part12/` |
| Part 13 — Automation and DevOps Integration        | 13.1–13.6     | §97–§102           | `Contents/Part13/` |
| Part 14 — Production, Enterprise, Cloud Operations | 14.1–14.8     | §103–§110          | `Contents/Part14/` |
| Part 15 — Mastery: Best Practices and Comparisons  | 15.1–15.5     | §111–§115          | `Contents/Part15/` |
| Part 16 — Interview Preparation                    | 16.1–16.7     | §116–§122          | `Contents/Part16/` |
| Part 17 — Wrap-Up                                  | 17.1–17.3     | §123–§125          | `Contents/Part17/` |

**Total: 125 sections across 17 parts.**

---

## 5. Cross-Topic Dependency Graph

```text
Foundations & History (P1)
        │
        ▼
Architecture & Kernel (P2)  ──────────────► Boot, init, kernel modules
        │
        ▼
Filesystem & Storage Basics (P3)
        │
        ├──► Users, Permissions, Access Control (P4)
        │
        ▼
Process & Job Management (P5)
        │
        ▼
Shell, Scripting, Text Processing (P6)
        │
        ├──► Networking (P7) ──► SSH, firewalls, diagnostics
        │
        ▼
Package Management (P8)
        │
        ▼
Systemd & Services (P9) ──► journald, timers
        │
        ▼
Advanced Storage & LVM (P10)
        │
        ▼
Performance, Monitoring, Troubleshooting (P11)
        │
        ▼
Security Hardening (P12) ──► SELinux/AppArmor, auditd
        │
        ▼
Automation & DevOps Integration (P13) ──► namespaces/cgroups → Docker → Kubernetes (related topics)
        │
        ▼
Production, Enterprise, Cloud (P14) ──► AWS/Azure/GCP Linux images, HA, DR
        │
        ▼
Mastery: Best Practices & Comparisons (P15)
        │
        ▼
Interview Preparation (P16)
        │
        ▼
Wrap-Up: Labs & Next Steps (P17) ──► Recommended next topics: Docker, Kubernetes, Ansible, Terraform, Networking (deep dive), Bash Advanced Scripting, Prometheus/Grafana
```

**Recommended technologies to learn after Linux:** Docker, Kubernetes, Ansible, Terraform, Prometheus/Grafana, Nginx, Git (if not already known), AWS/Cloud fundamentals.

---

## 6. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 7. Current Roadmap State

| #   | Part                                               | Section   | Status       |
| --- | -------------------------------------------------- | --------- | ------------ |
| 01  | Part 1 — Foundations and History                   | 1.1–1.7   | ✅ Completed |
| —   | Part 2 — Architecture and the Kernel               | 2.1–2.9   | ⏳ Remaining |
| —   | Part 3 — Filesystem and Storage Basics             | 3.1–3.8   | ⏳ Remaining |
| —   | Part 4 — Users, Permissions, and Access Control    | 4.1–4.8   | ⏳ Remaining |
| —   | Part 5 — Process and Job Management                | 5.1–5.8   | ⏳ Remaining |
| —   | Part 6 — Shell, Scripting, and Text Processing     | 6.1–6.10  | ⏳ Remaining |
| —   | Part 7 — Networking                                | 7.1–7.8   | ⏳ Remaining |
| —   | Part 8 — Package Management                        | 8.1–8.6   | ⏳ Remaining |
| —   | Part 9 — Systemd and Services                      | 9.1–9.8   | ⏳ Remaining |
| —   | Part 10 — Advanced Storage and LVM                 | 10.1–10.7 | ⏳ Remaining |
| —   | Part 11 — Performance, Monitoring, Troubleshooting | 11.1–11.9 | ⏳ Remaining |
| —   | Part 12 — Security Hardening                       | 12.1–12.8 | ⏳ Remaining |
| —   | Part 13 — Automation and DevOps Integration        | 13.1–13.6 | ⏳ Remaining |
| —   | Part 14 — Production, Enterprise, Cloud Operations | 14.1–14.8 | ⏳ Remaining |
| —   | Part 15 — Mastery: Best Practices and Comparisons  | 15.1–15.5 | ⏳ Remaining |
| —   | Part 16 — Interview Preparation                    | 16.1–16.7 | ⏳ Remaining |
| —   | Part 17 — Wrap-Up                                  | 17.1–17.3 | ⏳ Remaining |

**Next Section:** 2.1–2.9 (`02-Architecture-and-Kernel.md`)
