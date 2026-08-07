# Section 78 (Part 10): Network Storage: NFS and Samba Basics

## 1. Overview: Persistent Network Storage vs. One-Off Transfer

[§57](../Part7/Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md) covered `scp`, `rsync`, and `sftp` — tools for moving files between hosts as discrete, one-off (or repeatable-but-manual) transfer operations. This section covers a different pattern entirely: **mounting remote storage so it behaves like local storage**, persistently, at the filesystem level, rather than copying files back and forth on demand. Once an NFS export or Samba share is mounted, applications on the client read and write to it using ordinary file I/O, with no awareness that the data is physically sitting on another host.

This builds directly on [§51](../Part7/Section-51-Part7-Networking-Fundamentals-Recap.md)'s networking fundamentals (Part 7) and [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)'s mounting concepts (Part 3) — a network filesystem mounts using the same `mount` command and `/etc/fstab` persistence mechanism as a local disk, just with a different filesystem type and additional network-specific options.

The two protocols covered here solve the same general problem — shared network-accessible storage — for different ecosystems: **NFS** is the native Unix/Linux approach, and **Samba** implements the Windows-native **SMB/CIFS** protocol for interoperability wherever Windows clients or SMB-expecting infrastructure are involved.

## 2. NFS Conceptually

**NFS (Network File System)** lets a server **export** a directory, which one or more clients then **mount** over the network as if it were a local path. The model has two sides:

- **Server side:** a directory is declared exportable via `/etc/exports`, and the NFS server daemon (`nfs-server`/`nfs-kernel-server`, depending on distribution) makes it available to permitted clients.
- **Client side:** the client mounts the export with `mount -t nfs`, after which the mounted path behaves like any other directory to applications — `ls`, `cat`, standard file operations all work transparently over the network connection underneath.

**A basic `/etc/exports` entry (server side):**

```
/srv/shared-data   192.168.1.0/24(rw,sync,no_subtree_check)
```

| Field              | Meaning                                                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/srv/shared-data` | The local directory being exported                                                                                                                     |
| `192.168.1.0/24`   | The client(s) permitted to mount it — a CIDR range here, but can be a single host or hostname                                                          |
| `rw`               | Clients may read and write (vs. `ro` for read-only)                                                                                                    |
| `sync`             | The server confirms writes to stable storage before acknowledging them to the client — safer, but slower than `async`                                  |
| `no_subtree_check` | Disables a subtree-consistency check that mostly adds overhead without meaningful benefit for whole-filesystem exports — a common, recommended default |

After editing `/etc/exports`, the server needs `exportfs -ra` (re-export everything, applying changes without a full service restart) for the new export to take effect.

**Discovering available exports from a client:**

```bash
showmount -e nfs-server.internal.example.com
```

**Mounting from a client:**

```bash
mount -t nfs nfs-server.internal.example.com:/srv/shared-data /mnt/shared-data
```

This follows exactly the `mount -t <type> <source> <mountpoint>` pattern [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) introduced for local filesystems — the network-specific part is entirely in the `<source>` syntax (`host:/path`) and the filesystem type (`nfs`).

## 3. NFS Versions Briefly

NFS has gone through several protocol versions, and the two worth distinguishing operationally:

- **NFSv3** — long-standing, widely deployed, but relies on separate auxiliary protocols (like `mountd` and `rpcbind`) running on their own ports, which complicates firewall configuration (multiple ports to permit, some dynamically assigned) and has a comparatively weak default trust model (3, Warning below).
- **NFSv4** — consolidates onto a single well-known port (2049), simplifying firewall rules considerably, and supports stronger authentication (Kerberos integration) as a first-class option rather than a bolted-on afterthought. NFSv4 is the version worth defaulting to on any new deployment where the option exists.

This section doesn't go deeper into version-specific mount option syntax — the conceptual distinction (single-port simplicity plus stronger optional security in v4 vs. v3's legacy multi-port/weaker-default-trust model) is what matters for making an informed choice.

## 4. Samba/CIFS Conceptually

**Samba** is the Linux/Unix implementation of **SMB (Server Message Block)**, the protocol Windows uses natively for file and printer sharing — sometimes still referred to by its older name **CIFS (Common Internet File System)**, an earlier SMB dialect whose name persists in tooling (`mount -t cifs`) even though modern SMB has moved well past that specific dialect.

Samba serves two distinct purposes worth keeping separate:

- **Server:** a Linux host runs Samba (`smbd`/`nmbd`) to expose its own directories to Windows clients (or other SMB-speaking clients) as network shares — useful when Linux storage needs to be accessible from a Windows-heavy environment.
- **Client:** a Linux host mounts an existing SMB share (commonly one hosted by an actual Windows server, or a NAS device) using `mount -t cifs`.

**Basic `smb.conf` share definition (server side, `/etc/samba/smb.conf`):**

```ini
[shared-data]
   path = /srv/shared-data
   read only = no
   valid users = alice, bob
```

| Directive       | Meaning                                                                                                                                      |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `[shared-data]` | The share name clients will see and connect to                                                                                               |
| `path`          | The local directory being shared                                                                                                             |
| `read only`     | Whether clients can write                                                                                                                    |
| `valid users`   | Restricts access to specific Samba users, backed by Samba's own user database (`smbpasswd`) rather than the system's Linux accounts directly |

**Mounting a Samba share from a Linux client:**

```bash
mount -t cifs //fileserver.example.com/shared-data /mnt/shared-data -o username=alice,password=secret
```

**Key flags:**

| Flag                     | Meaning                                                                                                                                                                                                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-t cifs`                | Specifies the CIFS/SMB filesystem type for `mount`                                                                                                                                                                                                                                          |
| `-o username=,password=` | SMB-specific authentication options — credentials can also be placed in a separate credentials file referenced via `-o credentials=/path/to/file` to avoid exposing a password in shell history or process listings, a meaningfully better practice for anything beyond a quick manual test |

## 5. Choosing Between Them

The honest, practical guidance is straightforward and doesn't require overthinking:

- **NFS** for Linux-to-Linux network storage — it's the native fit, generally simpler to reason about in an all-Linux environment, and doesn't carry SMB's Windows-oriented authentication/permission model baggage.
- **Samba/SMB** whenever Windows interoperability is required — Windows clients need to access the share, the share needs to behave like a Windows file server for compatibility with Windows-oriented tooling, or an existing environment already standardizes on SMB (a NAS device that only speaks SMB well, for instance).

Neither is universally "better" — the deciding factor is almost always which ecosystem the other end of the connection belongs to, not a performance or feature argument.

> ⚠️ **Warning:** NFS's traditional trust model — especially NFSv3's default behavior — is UID/GID-based rather than strongly authenticated. In the common default configuration, the NFS server trusts the UID/GID numbers a client presents at face value, rather than cryptographically verifying the identity behind them. This means that on a network where an untrusted or compromised client can reach the NFS server, that client can potentially present arbitrary UID/GID values and access files belonging to those IDs on the export, unless additional controls (`root_squash` to prevent a client's root user from being treated as the server's root, restrictive export client lists, or a properly configured Kerberized NFSv4 setup) are in place. This is a genuine, non-theoretical security consideration for NFS exports reachable from anything less trusted than a tightly controlled internal network — it is not a reason to avoid NFS outright, but it is a reason not to treat "it's mounted with `rw`" as the only access-control question worth asking.

## 6. Persisting Network Mounts and Handling Server Unavailability

Like local mounts and swap ([§77](./Section-77-Part10-Swap-Management.md)), a manual `mount` command doesn't survive a reboot — persistence goes through `/etc/fstab`, the same mechanism [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) established, but network mounts carry extra options worth knowing specifically because a network filesystem can become unreachable in ways a local disk generally can't.

**Example `/etc/fstab` entries:**

```
nfs-server.internal.example.com:/srv/shared-data   /mnt/shared-data   nfs    defaults,_netdev,soft,timeo=30   0   0

//fileserver.example.com/shared-data   /mnt/smb-data   cifs   credentials=/etc/samba/creds,_netdev,iocharset=utf8   0   0
```

| Option                    | Meaning                                                                                                                                                                                          |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `_netdev`                 | Tells the boot process this is a network-dependent mount — wait for networking to be up before attempting it, rather than trying (and failing) to mount it before the network is even configured |
| `soft` (NFS)              | If the server stops responding, an I/O operation eventually gives up and returns an error to the calling application, rather than blocking forever                                               |
| `hard` (NFS, the default) | An I/O operation retries indefinitely until the server responds again — the application-level call simply hangs until then                                                                       |
| `timeo=` (NFS)            | Timeout (in tenths of a second) before a retry, tuning how quickly `soft` gives up or `hard` retries                                                                                             |
| `credentials=` (CIFS)     | Points at a separate file containing `username=`/`password=` pairs, keeping credentials out of `/etc/fstab` itself (which is often world-readable)                                               |

**The `hard` vs. `soft` trade-off is worth understanding rather than picking blindly:** `hard` (the NFS default) is generally the safer choice for data-integrity-sensitive workloads, since an application never sees a partial-failure I/O error it might not handle correctly — it just waits, and resumes once the server returns. `soft` avoids the "application hangs indefinitely" problem when a server is genuinely gone, but at the cost of applications needing to handle I/O errors from what looks like an otherwise-healthy filesystem, which not all applications do gracefully. Neither is a universal default — the right choice depends on whether the calling application handles a failed I/O operation better or worse than an indefinite hang.

**Troubleshooting an unreachable NFS mount:** a client hung on an unresponsive `hard`-mounted NFS share often shows processes in uninterruptible sleep (D-state, [§33](../Part5/Section-33-Part5-What-A-Process-Is.md)) waiting on the stuck I/O call — this is a direct, practical instance of the D-state-means-I/O-wait connection [§33](../Part5/Section-33-Part5-What-A-Process-Is.md) introduced, now specifically caused by an unreachable network filesystem rather than a slow local disk.

## 7. Hands-On: Basic Diagnostics for Both Protocols

**Purpose:** Quickly confirm whether an NFS or Samba mount problem is server-side reachability, export/share configuration, or something else entirely.

**NFS:**

```bash
# Confirm the server's exports are visible at all from the client
showmount -e nfs-server.internal.example.com

# Confirm the NFS-related RPC services are actually running (v3-era check)
rpcinfo -p nfs-server.internal.example.com
```

**Samba:**

```bash
# List shares visible on a Samba server, prompting for credentials
smbclient -L //fileserver.example.com -U alice

# Test connectivity to a specific share interactively
smbclient //fileserver.example.com/shared-data -U alice
```

**Common errors:** `showmount -e` timing out or being refused usually means either a firewall blocking the relevant ports (NFSv3's multiple auxiliary ports, 3, are a common culprit) or the NFS service simply isn't running on the target host — check the service status ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)'s `systemctl`, Part 9) before assuming it's a network-layer problem. `smbclient -L` prompting successfully but then denying access to a specific share points at the share's own `valid users`/permission configuration (4) rather than a connectivity issue.

## 8. Common Misconceptions

1. **"NFS and Samba are interchangeable — pick whichever."** They target different ecosystems by design — NFS is Unix/Linux-native, Samba/SMB is Windows-native. The right choice is driven by what the other end of the connection needs to speak, not by a generic feature comparison (5).
2. **"A network mount is fundamentally different to use than a local mount, once it's set up."** Mechanically, both use the same `mount -t <type>` and `/etc/fstab` persistence pattern from [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) — the difference is entirely in the source syntax and network-specific options, not in how applications subsequently interact with the mounted path.
3. **"NFS is inherently insecure and shouldn't be used on any network."** NFSv3's default UID/GID trust model is a real consideration on untrusted networks (5, Warning), but NFSv4 supports proper Kerberized authentication, and even NFSv3 is entirely reasonable on a tightly controlled internal network with appropriate export restrictions — the risk is about default configuration on the wrong network, not the protocol being categorically unsafe.
4. **"CIFS and SMB are different protocols."** CIFS is an older SMB dialect name that persists in Linux tooling (`mount -t cifs`) for historical/compatibility reasons — modern Samba deployments typically negotiate a more current SMB protocol version even though the mount command still says `cifs`.
5. **"`soft` NFS mounts are strictly safer than `hard` mounts because they don't hang."** `soft` avoids indefinite hangs when a server is unreachable, but at the cost of applications receiving I/O errors from what looks like a normal, healthy filesystem — not every application handles that gracefully. `hard` (the NFS default) is often the safer choice specifically for data-integrity-sensitive workloads, because it never surfaces a partial-failure error the application might mishandle (6) — the trade-off depends on the calling application, not a universal rule.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between using `rsync` to copy files to a remote host and mounting that host's storage over NFS?"_
**Model answer:** `rsync` ([§57](../Part7/Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)) performs a discrete transfer — it copies files from one place to another at a point in time, and the two copies then exist independently until the next sync. Mounting over NFS makes the remote directory behave like a local path continuously — applications read and write directly to it over the network in real time, with no separate "copy" step and no two independent copies to keep in sync. They solve different problems: `rsync` for moving or synchronizing data between two independent storage locations, NFS for making one piece of storage transparently accessible from multiple hosts as if it were local.
_What the interviewer is probing for:_ Understanding the transfer-vs-persistent-mount distinction conceptually, not just knowing both are "ways to move files over a network."

**🎯 Intermediate:** _"When would you choose Samba over NFS for a new network storage setup?"_
**Model answer:** Whenever Windows interoperability is a requirement — Windows clients needing to access the share directly, or existing infrastructure (a NAS appliance, for instance) that only speaks SMB well. NFS is the more natural fit for pure Linux-to-Linux storage since it's the native Unix/Linux network filesystem without SMB's Windows-oriented user/permission model layered on top. The decision is almost entirely about which ecosystem the other end of the connection belongs to, not a general performance or feature comparison between the two.
_What the interviewer is probing for:_ A clear, practical decision rule rather than a vague "they're both fine" or an unfounded performance claim.

**🎯 Senior:** _"You're auditing an NFS export that's reachable from a broader network segment than intended. What are you specifically worried about?"_
**Model answer:** Primarily NFS's traditional UID/GID-based trust model, especially if it's NFSv3 — by default the server trusts the UID/GID a client presents rather than strongly authenticating identity, so a client on that broader segment could potentially present arbitrary UID/GID values and access files belonging to those IDs, unless protections like `root_squash` and a properly restricted client list in `/etc/exports` are in place. I'd check whether the export's client restriction in `/etc/exports` is actually as narrow as intended, whether `root_squash` is enabled (to prevent a remote root user from acting as root on the export), and whether migrating to NFSv4 with Kerberos is feasible for that particular export given its sensitivity — NFSv4's stronger authentication story directly addresses the underlying weak-trust concern rather than just narrowing network reachability around it.
_What the interviewer is probing for:_ Concrete knowledge of NFS's actual trust-model weakness (not a vague "NFS is insecure") and the specific mitigations (`root_squash`, client restriction, NFSv4/Kerberos) rather than just recommending "restrict the network."

**🎯 Architect:** _"You're designing shared storage for a mixed fleet — some Linux application servers, some Windows-based reporting tools that need to read the same data. How do you approach it?"_
**Model answer:** Rather than forcing one protocol to serve both ecosystems awkwardly, I'd consider whether the data genuinely needs to be accessed via both protocols simultaneously or whether one side can be a consumer of a single canonical source — a common pattern is Linux-native storage (NFS between Linux hosts) with a Samba re-export of the same underlying directory specifically for the Windows reporting tools, rather than maintaining two independently-written copies of the same data. I'd default to NFSv4 for the Linux-to-Linux side for its simpler single-port firewall story and stronger authentication option, and I'd be deliberate about the trust model on both sides — Kerberized NFSv4 where the sensitivity of the data justifies it, and Samba configured with proper per-user authentication (`valid users`, backed by a real identity source) rather than an overly permissive share. I'd also factor in that network storage introduces a genuine availability dependency — if the NFS/Samba server goes down, every client mount depending on it is affected, which is a design consideration for anything beyond low-stakes shared data (HA patterns for this are covered in Part 14).
_What the interviewer is probing for:_ Recognizing that mixed-ecosystem requirements don't have to mean picking one protocol and forcing the other side to adapt awkwardly, plus awareness of the availability and trust-model implications of centralizing storage behind a network filesystem.

## 10. Key Takeaways

- NFS and network mounts generally provide _persistent, transparent_ remote storage access — a fundamentally different pattern from [§57](../Part7/Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)'s one-off `scp`/`rsync`/`sftp` transfers, even though `rsync` specifically is later reused as a backup mechanism in [§79](./Section-79-Part10-Backup-Strategies-Tools.md).
- NFS exports a directory via `/etc/exports` on the server and mounts it with `mount -t nfs host:/path /mountpoint` on the client, using the same `mount`/`/etc/fstab` pattern [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) established for local filesystems (2).
- NFSv4 consolidates onto a single port and supports stronger Kerberized authentication as a first-class option; NFSv3 relies on multiple auxiliary-protocol ports and a weaker default trust model (3).
- Samba/CIFS implements Windows-native SMB for interoperability — `smb.conf` defines shares on the server side, `mount -t cifs` mounts them on a Linux client (4).
- Choose NFS for Linux-to-Linux storage, Samba/SMB wherever Windows interoperability is required — the decision is about ecosystem fit, not a general performance comparison (5).
- NFS's traditional UID/GID-based trust model, particularly in NFSv3, is a genuine security consideration on anything less trusted than a tightly controlled internal network — `root_squash`, restrictive export client lists, and NFSv4/Kerberos are the concrete mitigations (5).

## 11. Related Concepts & What's Next

This section depends on [§51](../Part7/Section-51-Part7-Networking-Fundamentals-Recap.md)'s networking fundamentals and [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)'s mounting concepts, and contrasts directly with [§57](../Part7/Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)'s file-transfer tools (persistent mount vs. one-off transfer). It also ties back to [§33](../Part5/Section-33-Part5-What-A-Process-Is.md)'s process-state coverage (Part 5) — a hung NFS client is a concrete, practical instance of the D-state/I-O-wait connection introduced there. [§79](./Section-79-Part10-Backup-Strategies-Tools.md) (next) covers backup strategies and tools — including a reuse of `rsync` in a different role than [§57](../Part7/Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)'s, this time specifically as a repeatable backup mechanism — closing out Part 10.

**Next Section:** [§79](./Section-79-Part10-Backup-Strategies-Tools.md) — `Section-79-Part10-Backup-Strategies-Tools.md`
