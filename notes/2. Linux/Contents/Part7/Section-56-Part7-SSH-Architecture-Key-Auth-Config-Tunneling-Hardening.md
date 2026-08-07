# Section 56 (Part 7): SSH: Architecture, Key-Based Auth, Config, Tunneling, Hardening

## 1. Overview: SSH as Encrypted Transport, Not Just "Remote Login"

[§55](./Section-55-Part7-Network-Diagnostics.md) covered the tools that observe traffic on a host; this section covers the protocol that most administrators actually spend their day operating inside of. **SSH (Secure Shell)** is usually described as "the way you log into a remote Linux box," which is true but understates what it actually is: a general-purpose **encrypted transport protocol** that happens to be most commonly used to carry an interactive shell session. That framing matters because SSH's other capabilities — tunneling, file transfer ([§57](./Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)), and even some VPN-like use cases — aren't separate protocols bolted onto SSH; they're additional payloads carried over the same encrypted connection.

Three things happen when an SSH client connects to an SSH server, layered on top of each other:

1. **An encrypted transport is established.** Client and server negotiate a shared session key so that everything after this point is encrypted and integrity-protected, even over an untrusted network.
2. **The client (and optionally the server) is authenticated.** The server proves its identity via a host key (what triggers the "authenticity of host X can't be established" prompt on first connection); the client proves its identity via a password or, far more commonly in production, a key pair (2).
3. **A logical channel is opened over the encrypted transport**, and this is the detail most administrators never think about explicitly: **one single TCP connection can carry multiple independent channels simultaneously** — an interactive shell, one or more port-forwarding tunnels (4), and an SFTP file-transfer session ([§57](./Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)) can all be multiplexed over the same underlying connection at once. This is why `ssh -L 8080:localhost:80 user@host` and an interactive shell can run from the same invocation, and why SSH connection-sharing (`ControlMaster`, briefly noted in 3) works at all — it's reusing one already-authenticated transport for multiple logical channels rather than opening a new TCP connection per use.

> 💡 **Tip:** Keep transport, authentication, and channel separate in your mental model. A surprising number of SSH troubleshooting scenarios are really "which of these three layers is actually failing" — a hang before any prompt is usually transport/network ([§55](./Section-55-Part7-Network-Diagnostics.md)'s tools apply), a rejected login after a successful connection is authentication, and something like "my tunnel works but my shell doesn't" is a channel-level problem on top of a transport and authentication that are both already fine.

## 2. Key-Based Authentication: The Mechanics

Password authentication asks the server to trust a secret the client transmits (over the encrypted channel, so not in cleartext on the wire — but still transmitted). **Key-based authentication** is structurally different, and the difference is the entire reason it's preferred in production: the secret half of the key pair is **never transmitted at all**.

An SSH key pair is **asymmetric**:

- The **private key** stays on the client, ideally protected by a passphrase, and is never copied anywhere else, never emailed, never checked into a repository (a private key committed to version control should be treated as compromised the moment it's pushed, not just rotated on a schedule).
- The **public key** is copied to every server the client needs to authenticate to, appended to that account's `~/.ssh/authorized_keys` file.

Authentication then proceeds as a **challenge-response**, not a secret handoff: the server generates a challenge (in practice, this is built into the SSH protocol's key-exchange-adjacent authentication messages) that can only be answered correctly by whoever holds the matching private key — the client signs data with the private key, and the server verifies that signature using the public key it already has on file. **The server never sees, never needs, and never could reconstruct the private key from this exchange** — possession is proven mathematically, not by transmitting the thing being proven.

This has a concrete, practical consequence worth stating plainly: **compromising a server's `authorized_keys` file** (or the whole server) **does not give an attacker anything usable against other servers** that trust the same public key, because the file only ever contained the public half. Compromising the **client's private key file**, by contrast, is the actual catastrophic event — which is exactly why the private key's file permissions matter (SSH refuses to use a private key file that's group- or world-readable, and will error out rather than silently proceed) and why passphrase-protecting the private key is a second layer of defense if the key file itself is ever exfiltrated.

> ⚠️ **Warning:** A private key without a passphrase is convenient — no prompt on every connection — but it means anyone who obtains the key file (a stolen laptop, a misconfigured backup, an over-permissive file share) can use it immediately with no second factor at all. `ssh-agent` (holding a decrypted key in memory for the duration of a session after one passphrase prompt) is the standard way to get both convenience and passphrase protection without typing the passphrase on every single connection.

## 3. Generating Keys and Choosing a Key Type

`ssh-keygen` generates a new key pair:

```bash
ssh-keygen -t ed25519 -C "harshit@laptop"
```

| Flag      | Meaning                                                                                  |
| --------- | ---------------------------------------------------------------------------------------- |
| `-t`      | Key type/algorithm                                                                       |
| `-C`      | A comment embedded in the public key — conventionally an identifying label, not a secret |
| (no `-f`) | Defaults to `~/.ssh/id_ed25519` (private) and `~/.ssh/id_ed25519.pub` (public)           |

**Key types, briefly:**

- **RSA** — the long-standing default, still universally supported, but requires a larger key size (2048-bit is the practical legacy minimum; 4096-bit is commonly recommended if RSA is used at all today) to carry comparable security margin to modern alternatives, and is measurably slower for key operations.
- **Ed25519** — the modern recommended default on essentially any system built in the last several years: smaller keys, faster signing/verification, and a design that avoids some classes of implementation pitfalls RSA and older elliptic-curve schemes are more exposed to. Use Ed25519 unless a specific legacy system in the fleet genuinely can't support it (some older network appliances or legacy Unix systems still only understand RSA).

`ssh-keygen` prompts for a passphrase during generation (2's recommendation applies) and, once complete, the public key (`id_ed25519.pub`) is what gets distributed to servers — via `ssh-copy-id user@host` (which appends it to the remote `~/.ssh/authorized_keys` for you), or manually pasted for cases (cloud provider instance metadata, `cloud-init`, configuration management) where `ssh-copy-id` doesn't apply.

## 4. `~/.ssh/config`: Client-Side Connection Aliases

Typing `ssh -i ~/.keys/prod-bastion.pem -p 2222 deploy@bastion.internal.example.com` for every connection to the same host is exactly the kind of repeated boilerplate `~/.ssh/config` exists to eliminate. It defines **Host aliases** — named shortcuts bundling together everything a specific connection needs:

```
Host bastion
    HostName bastion.internal.example.com
    User deploy
    Port 2222
    IdentityFile ~/.ssh/prod-bastion

Host app-server-1
    HostName 10.20.30.5
    User deploy
    ProxyJump bastion

Host app-server-2
    HostName 10.20.30.6
    User deploy
    ProxyJump bastion
```

| Directive      | Meaning                                                                                                           |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| `Host`         | The alias typed on the command line (`ssh bastion`) — does not need to match the real hostname                    |
| `HostName`     | The actual address/hostname to connect to                                                                         |
| `User`         | Remote username, so it never needs typing per-connection                                                          |
| `Port`         | Non-default SSH port for that host (6 covers changing the default port and its limited real value)                |
| `IdentityFile` | Which private key to present for this host — useful once a client holds keys for multiple, unrelated environments |
| `ProxyJump`    | Route the connection through an intermediate host (a **bastion/jump host**) rather than connecting directly       |

**`ProxyJump` is the detail worth understanding rather than just copying.** In many production network layouts, application servers sit on a private network with no direct inbound path from the internet at all — the only host reachable directly is a **bastion host** sitting at the network edge. `ProxyJump bastion` tells the SSH client: open a connection to `bastion` first, then tunnel a second SSH connection to the real target (`app-server-1`) through that first connection — all transparently, so `ssh app-server-1` just works without the administrator manually SSHing into the bastion and then SSHing again from there. It's functionally similar to hand-chaining two SSH sessions, but as one command, one channel-multiplexed connection (1), and one place (`~/.ssh/config`) where the topology is documented rather than re-typed from memory each time.

> 💡 **Tip:** `~/.ssh/config` is client-side only — it changes nothing about server behavior or security posture, only how conveniently _this_ client reaches known hosts. It's also a genuinely useful piece of environment documentation: a well-maintained config file is a legible map of "which hosts exist, which bastion each sits behind, which key each expects" for anyone who inherits the laptop or the onboarding checklist.

## 5. Port Forwarding and Tunneling: Three Directions, One Mental Model

SSH's channel-multiplexing (1) is what makes **tunneling** possible: an SSH connection can carry not just a shell, but arbitrary TCP traffic redirected through it. There are three forwarding modes, and the recurring point of confusion is direction — which end initiates, and which end the forwarded traffic actually reaches.

### 5.1 Local forwarding (`-L`): reach a remote-side service through your local machine

```bash
ssh -L 8080:localhost:5432 user@dbhost
```

**Mental model:** "Open a port **on my machine** that, when connected to, actually reaches something on the **far side** of the SSH connection." Here, connecting to `localhost:8080` on the client machine transparently reaches port `5432` on `dbhost` as seen from `dbhost`'s own perspective (which is why `localhost` in the middle argument means "localhost relative to the server," not the client). This is the classic pattern for reaching a database or internal admin UI that only listens on a server's loopback interface and was never meant to be exposed directly — a local Postgres client can point at `localhost:8080` on the laptop and transparently be talking to the production database, without that database ever accepting direct connections from the internet.

### 5.2 Remote forwarding (`-R`): expose something on your side, through the server, to others

```bash
ssh -R 9000:localhost:3000 user@publichost
```

**Mental model:** the reverse of 5.1 — "Open a port **on the remote server** that, when connected to, reaches something on **my side** of the connection." A developer running a service on `localhost:3000` on their laptop (behind NAT, no public IP) can make it reachable at `publichost:9000` for anyone who can reach `publichost`, without configuring any inbound firewall rule on the laptop's own network — the connection to the laptop rides back over the SSH tunnel the laptop itself initiated outbound. This is the pattern behind quick "expose my local dev server for a demo" tricks and behind some legitimate reverse-connectivity architectures (a host behind restrictive NAT/firewall dialing out to a jump point that other systems then use to reach it).

### 5.3 Dynamic forwarding (`-D`): a general-purpose SOCKS proxy through the tunnel

```bash
ssh -D 1080 user@bastion
```

**Mental model:** rather than forwarding one fixed port to one fixed destination, `-D` turns the SSH client into a **SOCKS proxy** listening locally on port `1080` — any application configured to use a SOCKS proxy at `localhost:1080` (a browser, most commonly) has _all_ of its outbound traffic routed through the SSH connection to whatever destination each individual request asks for, decided per-connection rather than fixed at tunnel-setup time. This is the closest SSH gets to VPN-like behavior — genuinely general-purpose routing of arbitrary destinations through the tunnel — without actually being a VPN (no routing-table-level integration, and it typically only proxies TCP, application by application, rather than transparently capturing all system traffic).

| Flag | Direction                | Listens on | Reaches                                        |
| ---- | ------------------------ | ---------- | ---------------------------------------------- |
| `-L` | Local → remote           | Client     | A specific destination as seen from the server |
| `-R` | Remote → local           | Server     | A specific destination as seen from the client |
| `-D` | Local → anywhere (SOCKS) | Client     | Whatever each proxied connection requests      |

> 💡 **Tip:** If a forward isn't working, ask two questions in order: "which end is listening?" (that's the first number after `-L`/`-R`) and "as seen from which side is the destination address resolved?" (`localhost` in a `-L`/`-R` argument means localhost _relative to the server_, which is the single most common source of "why can't I reach it" confusion with these flags).

## 6. Basic Hardening

Full SSH hardening depth — including bastion host architecture patterns in production — is **[§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)**; this section covers the handful of settings, all in `/etc/ssh/sshd_config` on the server, that are the practical baseline almost every production host applies.

- **`PermitRootLogin no`** — disables direct SSH login as `root` entirely, forcing an administrator to log in as an unprivileged user and escalate via `sudo` ([§31](../Part4/Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)) instead. This isn't just inconvenience-as-security — it means every privileged action has an audit trail tied to an individual account rather than an undifferentiated `root` login, and it removes `root` as a guessable, universally-present username attackers can target directly.
- **`PasswordAuthentication no`** — disables password-based login entirely, requiring key-based authentication (2) for every connection. Since a private key can't be brute-forced the way a password can (there's no meaningful "guess the key" attack space to speak of), this single setting eliminates an entire category of credential-stuffing and brute-force attempts against the SSH port outright — provided keys have actually been deployed to every account that needs to log in _before_ this is set (the classic lockout risk, below).
- **Changing the default port (`Port 2222` or similar)** — reduces the sheer volume of automated, indiscriminate scanning traffic hitting port 22 (a large share of internet background noise is scanners and bots probing 22 specifically), but it is honestly **security through obscurity**, not a real access control: a port scan finds a non-standard SSH port in seconds, and it does nothing at all against a targeted attacker who already knows (or checks) where the service actually lives. Worth doing for noise reduction, not worth relying on as an actual defense — `PermitRootLogin no` and `PasswordAuthentication no` are real controls; a non-default port is housekeeping.
- **Fail2ban** (briefly) — a complementary tool, not part of SSH itself, that watches authentication logs and temporarily firewalls ([§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)) source IPs after repeated failed login attempts. It's a good defense-in-depth layer even with password auth already disabled (it also rate-limits noisy scanning generally), but it's a separate piece of software with its own configuration and failure modes, covered properly alongside the rest of Part 12's hardening depth rather than here.

> ⚠️ **Warning:** This is the SSH-specific version of the lockout pattern [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) warned about for firewalls, and it deserves the same discipline. Setting `PasswordAuthentication no` before confirming a working key-based login already succeeds for every account that needs remote access, or restarting `sshd` with a syntax error in a hardening change, can both end the same way: the _current_ session usually survives (an already-established connection isn't retroactively killed by a config change), but the _next_ connection attempt — including the one you'd need to fix the mistake — fails outright, on a host with no other access path. The standard safeguard: make the change, restart/reload `sshd`, and **test the new configuration in a second, separate SSH session while the first session stays open** — only close the original session once the new one is confirmed working. Never edit `sshd_config`, restart the service, and close the only open session in the same breath.

## 7. Hands-On: Verifying a Config Change Didn't Break Anything

### 7.1 Validate `sshd_config` syntax before restarting

**Purpose:** Catch a typo or invalid directive before it takes down the SSH daemon, rather than discovering the mistake via a failed restart with no remaining access.

```bash
sshd -t
```

**Expected output:** No output at all on success; a specific line-numbered error on failure, naming exactly what's wrong before anything is restarted.

**Common errors:** Assuming a saved config file is automatically valid — `sshd` doesn't validate on save, only on `-t` or an actual (re)start.

### 7.2 Reload rather than restart where possible, and test from a second session

**Purpose:** Apply the change while minimizing the window where a mistake could cut off access, and prove the new behavior works before trusting it.

```bash
systemctl reload sshd
```

**Then, from a completely separate terminal/session — leaving the original session open:**

```bash
ssh -v user@host
```

**Key flags:** `-v` (verbose) surfaces which authentication method actually succeeded and which key/identity was offered — useful for confirming the intended hardening (e.g., that password auth was actually rejected and key auth was what succeeded) rather than assuming.

**Troubleshooting:** If the second session fails, the first session (still open, per the Warning in 6) is the only way to revert the change — fix `sshd_config`, `sshd -t` again, reload again, and re-test before closing anything.

## 8. Common Misconceptions

1. **"SSH is just for logging into a remote shell."** The shell session is the most common single use, but SSH is a general encrypted transport carrying multiple simultaneous channels (1) — tunnels (5) and file transfer ([§57](./Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md)) ride the same connection, not a separate protocol.
2. **"The server needs to store something secret to verify a key-based login."** The server only ever holds the **public** key in `authorized_keys` — the challenge-response mechanism (2) proves possession of the private key without it ever being transmitted or needing to be stored anywhere but the client.
3. **"`-L` and `-R` are basically the same flag with the direction flipped, no big deal."** They're often confused for exactly that reason, but the practical distinction is which end _listens_ and which end's local perspective resolves the destination address (5) — getting this backwards is the most common tunneling mistake, not a minor detail.
4. **"Changing the SSH port is a meaningful security measure."** It measurably cuts automated scanning noise but provides no real resistance to a targeted attacker (6) — it's housekeeping, not a substitute for `PermitRootLogin no` and `PasswordAuthentication no`, which are actual access controls.
5. **"Disabling password auth is safe to do any time, since keys are 'obviously' already set up."** This is exactly the assumption that causes lockouts (6's Warning) — the safe order is always: deploy and _verify_ key-based login works, only then disable password auth, and always test the change from a second session before closing the first.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"How does SSH key-based authentication prove who you are without sending your password or private key over the network?"_
**Model answer:** It's asymmetric-key challenge-response, not secret transmission. The private key never leaves the client; the public key is the only thing that ever needs to sit on the server, in `~/.ssh/authorized_keys`. During authentication, the client signs data using its private key, and the server verifies that signature against the public key it already has — proving possession of the private key mathematically, without ever transmitting it. Even if the server (or its `authorized_keys` file) is later compromised, the attacker only gets the public half, which is useless for authenticating anywhere else.
_What the interviewer is probing for:_ Understanding that key auth is fundamentally different from password auth (no secret is ever sent), not just "a different kind of password."

**🎯 Intermediate:** _"Explain the difference between `-L`, `-R`, and `-D` port forwarding, and give a real use case for each."_
**Model answer:** `-L` (local forwarding) opens a port on the client that, when connected to, reaches a destination as seen from the server's side — the classic use is reaching a database that only listens on a remote server's loopback interface, by tunneling `localhost:8080` on my machine to `localhost:5432` on the server. `-R` (remote forwarding) is the reverse: it opens a port on the server that reaches back to something on the client's side — useful for exposing a local dev server running behind NAT to a colleague who can reach the public server, without any inbound firewall change on the client's own network. `-D` (dynamic forwarding) turns the SSH client into a general SOCKS proxy — instead of one fixed destination, any application pointed at the local SOCKS port gets its traffic routed through the tunnel to whatever destination each connection actually requests, which is the closest SSH gets to VPN-like behavior without being one.
_What the interviewer is probing for:_ Correctly keeping the three directions straight (a very common point of real confusion) and being able to map each to a genuine operational scenario, not just recite the flags.

**🎯 Senior:** _"You've just pushed `PasswordAuthentication no` and `PermitRootLogin no` to a fleet of production hosts via configuration management. What's your rollout discipline to avoid a mass lockout?"_
**Model answer:** Before the change ships anywhere, I'd confirm key-based login already works for every account that needs remote access on a representative host — this change should never be the thing that _causes_ someone to set up their key for the first time. I'd stage the rollout (a canary host or small batch first, not the whole fleet at once), and for each host, apply the change, run `sshd -t` to validate syntax, reload rather than hard-restart where the platform supports it, and then test from a second, separate SSH session before considering that host done — never closing the session that applied the change until a fresh connection has been proven to succeed with the new settings in effect. I'd also want an out-of-band access path confirmed available per host (console access, a cloud provider's serial console) before this goes anywhere near hosts without one, exactly the same discipline [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) described for firewall default-deny changes — this is the same category of mistake, just at the SSH layer instead of the packet-filter layer.
_What the interviewer is probing for:_ Recognizing this as the same class of remote-lockout risk covered elsewhere in this KB (firewalls, [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)) rather than a new problem, and having a concrete staged, verified rollout process rather than "push it and see."

**🎯 Architect:** _"Design the SSH access pattern for a fleet where application servers must never be directly reachable from the internet, but engineers need routine shell and tunnel access for debugging. What do you build, and what are the trade-offs?"_
**Model answer:** A bastion host architecture is the right shape: one (or a small, highly monitored, highly hardened set of) host(s) at the network edge that's the only thing with any inbound path from outside the private network, with every application server reachable only from the bastion's network position. Engineers configure `ProxyJump` in their `~/.ssh/config` (4) so `ssh app-server-1` transparently routes through the bastion with no manual double-hop — this keeps the ergonomics reasonable without weakening the topology. For debugging that needs more than a shell — reaching an internal admin UI or database — `-L` local forwarding (5) through the same bastion covers it without opening any new inbound path on the target. The bastion itself gets the full hardening treatment from this section and Part 12 ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)) — key-only auth, no root login, Fail2ban, tight logging/auditing — since it's now the single highest-value target in the whole architecture; a compromised bastion is effectively a compromised path to everything behind it. The trade-off is that the bastion becomes a single point of both access and risk concentration, so I'd pair it with strong monitoring/alerting on bastion auth events specifically, and treat any anomaly there as a higher-priority signal than the same anomaly on an ordinary application host.
_What the interviewer is probing for:_ Ability to design the actual network/access topology (not just recite `ProxyJump` syntax), and awareness that concentrating access into a bastion also concentrates risk, which needs its own compensating controls.

## 10. Key Takeaways

- SSH is an encrypted transport that multiplexes multiple logical channels — shell, tunnels, file transfer — over one connection; thinking of it as "just remote login" undersells nearly everything covered here (1).
- Key-based authentication is challenge-response over an asymmetric key pair — the private key never leaves the client and is never transmitted, only its signature is verified against the public key the server already holds (2).
- Ed25519 is the modern recommended key type for new keys; RSA remains for legacy compatibility only (3).
- `~/.ssh/config` eliminates repeated connection boilerplate via `Host` aliases, and `ProxyJump` makes bastion-host routing transparent to the end user without manual double-hopping (4).
- `-L` (reach the far side, from here), `-R` (let the far side reach here), and `-D` (turn this client into a general SOCKS proxy through the tunnel) are three distinct directions, not variations on one idea — mixing them up is the most common real-world tunneling mistake (5).
- `PermitRootLogin no` and `PasswordAuthentication no` are real access controls; changing the default port is noise reduction, not meaningful security (6) — full hardening depth is [§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md).
- Disabling password auth or root login before verifying key-based access already works, or closing the only open session before confirming a config change succeeded, is the classic SSH lockout — always validate syntax (`sshd -t`), reload, and test from a second session first (6, 7).

## 11. Related Concepts & What's Next

This section builds on [§55](./Section-55-Part7-Network-Diagnostics.md)'s diagnostic tooling (useful when an SSH connection itself is failing at the transport level) and connects directly to [§32](../Part4/Section-32-Part4-PAM-Overview.md)'s PAM coverage (Part 4) — `sshd`'s authentication path is PAM-aware, so PAM policy can affect SSH login behavior beyond `sshd_config` alone — and to [§31](../Part4/Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)'s `sudo` model (Part 4), since disabling root login (6) makes `sudo` the standard privilege-escalation path after an SSH login rather than an alternative to it. [§57](./Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md) (next) covers `scp`, `sftp`, and `rsync` — the file-transfer tools that ride over this same SSH transport rather than being separate protocols. Full SSH hardening depth, including bastion host patterns in production and the broader Linux security model they sit inside, is Part 12, [§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md).

**Next Section:** [§57](./Section-57-Part7-Remote-File-Transfer-Scp-Rsync-Sftp.md) — `Section-57-Part7-Remote-File-Transfer.md`
