# Section 57 (Part 7): Remote File Transfer: scp, rsync, sftp

## 1. Overview: Three Tools, One Transport

[§56](./Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) covered SSH's architecture, key-based authentication, and tunneling — the secure channel this section takes entirely for granted. All three tools covered here (`scp`, `rsync`, `sftp`) authenticate and encrypt exactly the way an interactive SSH session does: same keys, same `~/.ssh/config` host aliases, same agent forwarding, same hardening posture. Nothing in this section introduces a new trust model — it's entirely about what happens _after_ that SSH connection is established, when the goal shifts from "run a command on a remote host" to "move files between two hosts."

The three tools are not interchangeable despite superficial similarity — each answers a different practical question:

- **`scp`** — "copy this file (or tree) to/from a remote host, once, simply." Closest in spirit to `cp` ([§21](../Part3/Section-21-Part3-File-Directory-Operations.md)), just pointed at a remote path instead of a local one.
- **`rsync`** — "efficiently synchronize a source and destination, transferring only what actually changed." The tool of choice for anything repeated — backups, deployments, mirrors.
- **`sftp`** — "give me an interactive, FTP-like session over SSH" — browsing, spot-checking, and transferring files conversationally rather than in a single scripted command.

> 💡 **Tip:** A useful mental anchor for this whole section: `scp` and `sftp` both move whole files every time; `rsync`'s entire reason to exist is not doing that when it doesn't have to. Keep that one distinction in mind and the rest of the flag-level detail below falls into place as refinements of it.

## 2. scp: Simple, One-Shot Remote Copy

**`scp`** (secure copy) extends `cp`'s familiar syntax across the network, using SSH for both authentication and the data channel itself.

**Basic syntax:**

```bash
scp localfile.txt user@remotehost:/path/to/destination/
scp user@remotehost:/path/to/remotefile.txt ./local-destination/
```

Either side of the copy can be the remote one — `scp` infers direction from which argument carries a `host:` prefix. A copy between two _remote_ hosts, proxied through the local machine, also works by giving both arguments a `host:` prefix.

**Key flags:**

| Flag | Meaning                                                                                                                                                 |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-r` | Recursive — copy an entire directory tree, not just a single file (the `cp -r` analogue, [§21](../Part3/Section-21-Part3-File-Directory-Operations.md)) |
| `-P` | Specify a non-default SSH port (capital `-P`, distinct from `ssh`'s own lowercase `-p`)                                                                 |
| `-p` | Preserve modification times, access times, and modes from the source file                                                                               |
| `-C` | Enable compression during transfer                                                                                                                      |
| `-i` | Specify an identity (private key) file, same meaning as `ssh -i`                                                                                        |

**Example — recursive copy of a directory to a non-standard SSH port:**

```bash
scp -r -P 2222 ./build-output/ deploy@app-server:/var/www/app/
```

**The important modern caveat — scp's protocol is legacy:** For most of its history, `scp` used the old SCP protocol directly — a simple, unauthenticated-beyond-SSH-itself protocol for streaming files. Newer OpenSSH releases (9.0 and later) have **deprecated that legacy protocol** and made the `scp` client instead perform its transfer over the **SFTP protocol** under the hood, purely for the wire behavior — the `scp` command-line interface itself is unchanged. This matters practically for a few reasons: the old protocol had known weaknesses around how it handled wildcard filename expansion and could be tricked by a malicious server into writing files outside the intended destination directory, which the SFTP-backed implementation closes off. It also means **some legacy edge-case behaviors differ by OpenSSH version** — most visibly, remote wildcard expansion (`scp remote:*.log ./`) can behave differently, and copies to/from very old SSH servers that only speak the legacy SCP protocol may fail against a client that now assumes SFTP underneath (mitigated with an explicit `-O` flag on recent OpenSSH clients to force the old protocol back on for that one case).

> ⚠️ **Warning:** Don't assume `scp` behaves identically across a fleet of hosts with different OpenSSH versions. A script that relies on remote-side glob expansion, or that talks to a very old or embedded SSH server, can silently behave differently — or fail outright — depending on which protocol that particular `scp` binary is actually using. Check `ssh -V` and consult release notes when scripting `scp` for a mixed-version fleet rather than assuming version-independence.

`scp` always transfers the **full file**, every time, regardless of whether the destination already has a byte-identical (or nearly identical) copy — which is exactly the limitation [§3](../Part1/Section-03-Part1-Open-Source-Licensing-GPL-Governance.md) exists to solve.

## 3. rsync: Efficient, Delta-Based Synchronization

**`rsync`**'s defining feature, and the reason it exists as a separate tool rather than just "`scp` with more flags," is the **rsync algorithm**: before transferring a file that already has some version present at the destination, `rsync` computes checksums of blocks on both sides and transfers **only the blocks that actually differ**, reconstructing the full file at the destination from a mix of "reuse this local block" and "here's new data for this range." For genuinely new files this collapses to a full copy — no different from `scp` — but for **repeated syncs of large, mostly-unchanged data** (nightly backups, redeploying an application where only a handful of files changed, mirroring a slowly-changing dataset), the difference is dramatic: a multi-gigabyte file with a few kilobytes of actual changes transfers in a fraction of the time and bandwidth `scp`'s always-full-copy model would require, because `scp` and `sftp` have no concept of "what's already there" at all.

**Essential flags:**

```bash
rsync -avz --progress -e "ssh -p 2222" ./build-output/ deploy@app-server:/var/www/app/
```

| Flag                | Meaning                                                                                                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `-a` (archive mode) | Shorthand bundling several preservation flags — see field-by-field breakdown below                                                                                                                           |
| `-v`                | Verbose — list files as they're transferred                                                                                                                                                                  |
| `-z`                | Compress data during transfer (useful over slow links; less useful for already-compressed data like media files)                                                                                             |
| `-P` / `--progress` | Show a per-file progress meter; `-P` also implies `--partial`, keeping partially transferred files instead of deleting them on interruption, so a resumed transfer can pick up rather than restart from zero |
| `--delete`          | Delete files at the destination that no longer exist at the source, making the destination a true mirror                                                                                                     |
| `-e`                | Specify the remote shell command — how to reach into SSH options like a non-default port, since rsync has no `-P`-for-port of its own the way `scp` does                                                     |

**`-a` (archive mode) field by field** — it is itself shorthand for `-rlptgoD`:

| Component | Meaning                                                                    |
| --------- | -------------------------------------------------------------------------- |
| `-r`      | Recursive                                                                  |
| `-l`      | Copy symlinks as symlinks, rather than following and copying their targets |
| `-p`      | Preserve permissions                                                       |
| `-t`      | Preserve modification times                                                |
| `-g`      | Preserve group ownership                                                   |
| `-o`      | Preserve owner (typically requires running as root or the target user)     |
| `-D`      | Preserve device and special files                                          |

In practice, `-a` is the default starting point for almost every real `rsync` invocation — it's what makes a synced tree a faithful copy of the source's metadata, not just its byte content, and forgetting it is the single most common way an `rsync`-based backup silently loses permission or ownership information that later turns into a confusing restore-time problem.

> ⚠️ **Warning:** `--delete` makes the destination a true mirror of the source by removing anything present at the destination but absent from the source — which means it will happily delete files at the destination that were never meant to be temporary, if the source and destination were pointed at the wrong pair of directories, or if a source file was accidentally deleted before the sync ran. Always dry-run a `--delete` sync first with `--dry-run` (combined with `-v` to see exactly what would be removed) before running it for real against anything that matters, and treat any automated job using `--delete` as needing the same change-review scrutiny as a destructive database migration.

> ⚠️ **Warning — the trailing-slash gotcha:** `rsync`'s behavior toward a _source_ directory changes materially depending on whether it ends in a trailing slash, and this is one of the most common real-world `rsync` mistakes:
>
> ```bash
> rsync -a ./src/  user@host:/dest/   # copies the CONTENTS of src/ into dest/
> rsync -a ./src   user@host:/dest/   # copies src/ itself AS A SUBDIRECTORY of dest/, i.e. dest/src/
> ```
>
> With the trailing slash, `src/`'s contents land directly inside `dest/` — `dest/file1`, `dest/file2`, and so on. Without it, `rsync` treats `src` as a single directory entry to be created inside `dest/`, producing `dest/src/file1`, `dest/src/file2` — an entire extra directory level the author usually didn't intend. Both invocations run without error and produce a plausible-looking result, which is exactly why this mistake survives unnoticed until someone later goes looking for a file at the path they expected and it isn't there (or finds it nested one level deeper than every other tool in the pipeline assumes). The destination path's trailing slash, by contrast, has no such special meaning — it's purely the source side this applies to.

`rsync` also runs perfectly well purely locally (no `host:` prefix at all, source and destination both local paths) — the same delta-transfer efficiency applies, which is why it shows up as a backup tool ([§79](../Part10/Section-79-Part10-Backup-Strategies-Tools.md)) independent of any network transfer use case.

## 4. sftp: Interactive, Session-Based File Access

**`sftp`** provides an interactive, FTP-like command shell running over an SSH connection — but it's worth being precise about what that means, because "sftp is scp with a UI" undersells it. SFTP (SSH File Transfer Protocol) is a **genuinely distinct protocol** layered on top of an SSH connection, not simply an interactive wrapper spawning `scp` commands underneath — it defines its own request/response messages for listing directories, reading/writing file ranges, renaming, and managing permissions remotely, independent of what a plain SSH exec session (running an arbitrary shell command) provides. That distinction is exactly why [§2](../Part1/Section-02-Part1-History-and-Evolution.md)'s OpenSSH-version note about `scp` moving to "the SFTP protocol under the hood" is a meaningful change rather than a cosmetic one — it's genuinely switching to this different protocol's wire behavior.

**Basic usage:**

```bash
sftp user@remotehost
```

Once connected, the session behaves like a local/remote pair of shells:

| Command                | Effect                                                              |
| ---------------------- | ------------------------------------------------------------------- |
| `ls`                   | List files in the current remote directory                          |
| `lls`                  | List files in the current **local** directory                       |
| `cd` / `lcd`           | Change remote / local working directory                             |
| `get remotefile`       | Download a file from the remote host to the local working directory |
| `put localfile`        | Upload a local file to the remote host                              |
| `get -r remotedir`     | Recursive download of a directory                                   |
| `mkdir`, `rm`, `chmod` | Remote filesystem operations, issued directly within the session    |
| `bye` / `exit`         | Close the session                                                   |

`sftp` can also be driven non-interactively for scripting, via `sftp -b batchfile.txt user@host` (a file of the same commands listed above, one per line) — useful when the interactive convenience is wanted for development but the final workflow needs to be automated without a human at the prompt.

**Hardening technique worth knowing — restricted SFTP-only accounts:** Because SFTP is architecturally separate from a general SSH shell session, `sshd` can be configured to give certain users (or an entire group) **SFTP access only, with no shell access at all** — a genuinely useful least-privilege pattern for accounts that exist purely to drop off or pick up files (a vendor integration, a scheduled data-exchange partner) and should never be able to execute arbitrary commands on the host. The relevant `sshd_config` directive is `ForceCommand internal-sftp`, typically scoped to a `Match Group sftponly` block, often paired with `ChrootDirectory` to additionally confine that user's visible filesystem to a single directory tree:

```
Match Group sftponly
    ForceCommand internal-sftp
    ChrootDirectory /srv/sftp/%u
    AllowTcpForwarding no
    X11Forwarding no
```

This is real, commonly deployed hardening — not a niche configuration — anywhere a Linux host needs to accept file drops from a party that shouldn't have shell access, and it's worth recognizing on sight during a security review of `sshd_config` ([§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md) covers SSH hardening more broadly).

## 5. Choosing the Right Tool

| Scenario                                                                                              | Reach for                | Why                                                                                                       |
| ----------------------------------------------------------------------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------- |
| One-off copy of a file or small tree to/from a remote host                                            | `scp`                    | Simplest syntax, no session state, good enough when efficiency doesn't matter                             |
| Repeated syncs of large or mostly-unchanged data (backups, deploys)                                   | `rsync`                  | Delta transfer avoids re-sending unchanged bytes; dramatically faster on repeat runs (3)                  |
| Mirroring a destination exactly, including removing stale files                                       | `rsync --delete`         | Only `rsync` has this concept at all; use with `--dry-run` first (3's warning)                            |
| Interactive exploration — browsing an unfamiliar remote tree, spot-checking, ad hoc up/down transfers | `sftp`                   | FTP-like `ls`/`cd`/`get`/`put` workflow beats scripting one-off `scp` invocations                         |
| Vendor or partner accounts that should transfer files but never get a shell                           | `sftp` (server-enforced) | `ForceCommand internal-sftp` restricts the account to file transfer only (4)                              |
| Resuming an interrupted large transfer                                                                | `rsync -P`               | `--partial` (implied by `-P`) preserves partial output for a later resume; `scp`/`sftp` restart from zero |
| Scripted, non-interactive automation (CI/CD, cron)                                                    | `scp` or `rsync`         | Both work non-interactively; prefer `rsync` once the same data set is touched repeatedly                  |

## 6. Common Misconceptions

1. **"scp, rsync, and sftp are three ways to do the same thing — pick whichever."** They overlap in the base case (copying a file to a remote host) but diverge sharply outside it: `rsync`'s delta-transfer model is a structurally different transfer mechanism, not a syntax variant, and `sftp`'s interactive session model solves a different problem (exploration) than either scripted-copy tool.
2. **"rsync's `-z` and `-a` flags always help."** `-z` compression helps most on slow links transferring already-compressible data; it can add CPU overhead for little benefit on fast local networks or on data (media files, already-compressed archives) that doesn't compress further. `-a` is close to always correct as a starting point, but it's still worth knowing what it expands to (3) rather than treating it as an opaque "do the right thing" flag.
3. **"sftp is just scp with an interactive menu on top."** They're built on genuinely different underlying protocols (SFTP vs. the legacy SCP protocol, or — on modern OpenSSH — `scp` itself now riding on SFTP), not one tool wrapping the other's wire behavior (4).
4. **"A trailing slash on an rsync source is just cosmetic."** It changes whether the source directory's _contents_ or the directory _itself_ land at the destination — one of the most common real-world `rsync` mistakes, covered in 3's dedicated warning.
5. **"`--delete` only removes truly temporary junk."** It removes anything at the destination absent from the source, with no concept of what was "meant" to be there — a wrong source/destination pairing or an accidentally-deleted source file turns `--delete` into unintended data loss at the destination (3).

## 7. Key Takeaways

- All three tools run entirely over the SSH transport and trust model [§56](./Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md) established — same keys, same config, same hardening posture; this section is about post-connection file movement, not a new auth story.
- `scp` is the simplest tool — `cp`-like syntax, `-r` for recursion, `-P` for a non-default port — but always transfers full files and, on modern OpenSSH (9.0+), now runs over the SFTP protocol under the hood rather than the deprecated legacy SCP protocol, which can shift edge-case behavior (wildcard expansion) across a mixed-version fleet.
- `rsync`'s delta-transfer algorithm — sending only changed blocks — is its core differentiator, making repeated syncs of large or mostly-unchanged data dramatically more efficient than `scp`'s always-full-copy behavior.
- `-a` (archive mode) is `-rlptgoD` bundled together — recursion plus preservation of symlinks, permissions, times, group, owner, and device files — and is the correct default starting point for almost any real `rsync` invocation.
- The trailing slash on an `rsync` source path changes whether contents or the directory itself get copied to the destination — a genuinely common, easy-to-miss mistake.
- `--delete` makes the destination a true mirror by removing destination-only files — always `--dry-run` it first against anything that matters.
- `sftp` is a distinct protocol offering an interactive, FTP-like session (`get`/`put`/`ls`/`cd`) over SSH, and its architectural separation from a plain shell session is exactly what makes `ForceCommand internal-sftp` a real, practical hardening technique for file-transfer-only accounts.

## 8. Related Concepts & What's Next

This section is a direct extension of [§56](./Section-56-Part7-SSH-Architecture-Key-Auth-Config-Tunneling-Hardening.md)'s SSH architecture and key-based authentication — every tool here rides that same transport and trust model rather than introducing a new one. It also builds on [§21](../Part3/Section-21-Part3-File-Directory-Operations.md)'s local file and directory operations (Part 3), since `scp`, `rsync`, and `sftp` are best understood as those same copy/move semantics extended across a network boundary rather than a new conceptual model. [§58](./Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md) (next) moves to network services on Linux — `systemd-networkd` and `NetworkManager` — closing out Part 7's networking coverage by returning to how a host manages its own network configuration day to day.

**Next Section:** [§58](./Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md) — `Section-58-Part7-Network-Services.md`
