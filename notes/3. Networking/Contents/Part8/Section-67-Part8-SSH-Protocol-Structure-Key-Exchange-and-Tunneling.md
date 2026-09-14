# Section 67 (Part 8): SSH: Protocol Structure, Key Exchange, and Tunneling

## 1. Definition

**Plain language:** SSH is how engineers get a secure command-line session on a remote machine, copy files securely, and — less obviously — punch secure tunnels through a network for other traffic entirely. It's the single most-used tool in an infrastructure engineer's daily workflow for touching remote systems, and it replaced older, plaintext remote-access protocols (Telnet, rlogin, rsh) specifically because those transmitted credentials and everything else in the clear.

**Precise definition:** **SSH (Secure Shell)**, standardized as a family of RFCs (4251–4256) with **SSH-2** as the current protocol version, is a cryptographic network protocol providing an encrypted, authenticated channel for remote command execution, file transfer, and arbitrary port forwarding over an otherwise untrusted network, typically on TCP port 22. An SSH session begins with a **key exchange (KEX)** — analogous in purpose to TLS's handshake ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) — during which client and server negotiate algorithms and derive a shared session key, and the **server authenticates itself** to the client via a **host key** the client either already trusts (from a prior connection, recorded in `known_hosts`) or is asked to accept on first connection (**Trust On First Use**, TOFU). The **client then authenticates to the server**, most commonly via **public-key authentication** (the client proves possession of a private key whose matching public key the server has been configured to trust) rather than a password. Once both directions of authentication complete, SSH multiplexes one or more logical **channels** over the single encrypted connection — an interactive shell, file transfer (SFTP, [§69](Section-69-Part8-File-Transfer-Protocols-FTP-SFTP-SCP.md)), or arbitrary TCP **port forwarding/tunneling**.

> 💡 **Tip:** SSH's trust model is fundamentally different from TLS's. TLS relies on a hierarchical chain of Certificate Authorities ([§66](Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md)) that both parties implicitly trust in advance. SSH, by default, has no CA hierarchy at all — trust is established directly and manually, host-by-host and key-by-key (TOFU for servers, an authorized-keys list for clients), which is simpler to bootstrap for small-scale ad hoc access but far harder to manage safely at large fleet scale without additional tooling (SSH certificates, discussed in Production Usage Notes).

## 2. Why This Matters

- **SSH is the primary interactive and automated access mechanism for nearly every Linux server, network device, and cloud instance in existence** — it underlies manual troubleshooting sessions, Ansible's default transport, `git` over SSH, and countless CI/CD deployment steps.
- **Key-based authentication is the foundation of modern server access hygiene**, and understanding exactly how it works (what's actually being proven, and by which side) is necessary to configure it correctly, rotate keys safely, and avoid common misconfigurations that either lock engineers out or leave a door open.
- **SSH tunneling/port forwarding is a genuinely load-bearing operational technique**, not a niche trick — reaching a database that's only bound to localhost on a remote host, securely exposing a local development server for a demo, and bypassing a restrictive network path are all routine uses of SSH tunnels in infrastructure work.
- **Host key verification failures are a routine but consequential troubleshooting scenario** — understanding what a changed host key actually means (server was rebuilt legitimately, or something worse) is a real security judgment call engineers make regularly.
- **SSH agent forwarding and jump hosts (bastions) are standard patterns in any network with a private/public segmentation model**, and misunderstanding how they work is a common source of both operational friction and security missteps.

## 3. Prerequisites and Dependencies

This section assumes the TCP connection model from Part 7 ([§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)), since SSH establishes its encrypted session on top of a standard TCP connection to port 22 (or a custom port), the same way TLS does for HTTPS. Comparing SSH's key exchange and authentication model against TLS's ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) is genuinely useful context, since both solve a similar problem — an encrypted, authenticated channel over an untrusted network — with meaningfully different trust architectures (SSH's decentralized host-key/authorized-keys model versus TLS's CA-hierarchy model, [§66](Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md)); reading [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) and [§66](Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md) first, while not strictly required, makes the contrast in this section's Tip and later sections more concrete. No prior cryptography-specific background beyond what those two sections cover is assumed.

## 4. Architecture / Conceptual Diagram

```text
   CLIENT                                                     SERVER

   1. TCP connection to port 22 (§55)
              │
   2. SSH KEY EXCHANGE (KEX):
      Version strings exchanged, algorithms negotiated
      (key exchange method, host key type, ciphers, MACs)
      Shared session key derived ────────────────────────────►◄
              │
   3. SERVER AUTHENTICATION (host key):
      Server presents its host key ─────────────────────────────
      Client checks: "have I seen this host key for this
      hostname before?" (~/.ssh/known_hosts)
        ├─ Yes, matches  ──► proceed
        ├─ Yes, MISMATCH ──► "REMOTE HOST IDENTIFICATION HAS
        │                     CHANGED" warning, connection
        │                     refused by default (possible MITM,
        │                     or a legitimately rebuilt server)
        └─ No (first time) ──► Trust On First Use (TOFU) prompt
              │
   4. CLIENT AUTHENTICATION:
      Client proves possession of a private key ──────────────►
      (public-key auth: signs a challenge with its private key;
       server verifies against the public key in
       ~/.ssh/authorized_keys on the server)
                                                   ◄──────────── Auth accepted
              │
   5. CHANNEL MULTIPLEXING over the ONE encrypted connection:
        ├── Interactive shell session
        ├── SFTP file transfer (§69)
        ├── Local port forward   (-L)  ──► reach a remote-only
        │                                   service via localhost
        ├── Remote port forward  (-R)  ──► expose a local service
        │                                   to the remote side
        └── Dynamic port forward (-D)  ──► SOCKS proxy through
                                             the SSH connection
```

- **Host key verification protects against man-in-the-middle attacks on the server side of the connection** — it's the client's way of confirming "I am really talking to the server I think I am," conceptually parallel to certificate hostname verification in TLS ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)), but using SSH's own decentralized trust model instead of a CA chain.
- **Public-key client authentication never transmits the private key anywhere** — the client proves possession by signing a server-provided challenge with the private key, and the server verifies that signature using the public key it already has on file; this is the same asymmetric-cryptography principle underlying TLS's certificate-based authentication, applied in the opposite direction (client authenticating to server, which TLS supports via optional mutual TLS but SSH uses as its default mode).
- **All SSH channels — shell, SFTP, and every port-forwarding mode — share the same single encrypted TCP connection**, multiplexed the same conceptual way HTTP/2 multiplexes streams ([§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)); this is why a single SSH session can run an interactive shell and a tunnel simultaneously without opening a second connection.

## 5. Hands-On

### 5.1 Connecting with Verbose Output to Observe the Handshake

**Purpose:** Directly observe key exchange algorithm negotiation and host key verification as they actually happen.

**Syntax:**

```bash
ssh -v <user>@<host>
```

**Example usage and expected output:**

```bash
$ ssh -v deploy@10.0.1.20
OpenSSH_9.6p1, OpenSSL 3.1.4
debug1: Connecting to 10.0.1.20 port 22.
debug1: Local version string SSH-2.0-OpenSSH_9.6
debug1: Remote protocol version 2.0, remote software version OpenSSH_8.9p1
debug1: kex: algorithm: curve25519-sha256
debug1: kex: host key algorithm: ssh-ed25519
debug1: Server host key: ssh-ed25519 SHA256:AbCdEf1234567890...
debug1: Host '10.0.1.20' is known and matches the ED25519 host key.
debug1: Offering public key: /home/user/.ssh/id_ed25519
debug1: Server accepts key: /home/user/.ssh/id_ed25519
debug1: Authentication succeeded (publickey).
```

- `kex: algorithm: curve25519-sha256` shows the negotiated key exchange algorithm — this is the SSH equivalent of a TLS cipher suite negotiation, agreed upon before any authentication happens.
- `Host '10.0.1.20' is known and matches the ED25519 host key` confirms successful host key verification against the local `known_hosts` file — exactly the check diagrammed above.
- `Authentication succeeded (publickey)` confirms client authentication completed via a private key, not a password — the specific key offered and accepted is named explicitly.

**Production usage example:** `ssh -v` (or `-vvv` for maximum detail) is the standard first diagnostic step whenever an SSH connection fails or behaves unexpectedly — it isolates precisely which phase failed (TCP connectivity, key exchange, host key verification, or client authentication), each of which has a completely different root cause and fix.

**Common errors:** Confusing a host-key-verification failure ("REMOTE HOST IDENTIFICATION HAS CHANGED") with an authentication failure — the former means the server's identity itself is in question and should be investigated (was the server legitimately rebuilt or reimaged?) before ever blindly removing the offending `known_hosts` entry to "fix" the error, since that action removes the exact protection meant to catch a genuine man-in-the-middle.

### 5.2 Setting Up a Local Port Forward (SSH Tunnel)

**Purpose:** Reach a service that's only listening on a remote host's `localhost` (e.g., a database bound to `127.0.0.1` for security) through an encrypted SSH tunnel.

**Syntax:**

```bash
ssh -L <local_port>:<destination_host>:<destination_port> <user>@<ssh_host>
```

**Example usage and expected output:**

```bash
$ ssh -L 5432:localhost:5432 deploy@db-bastion.internal
# (session stays open; in another terminal:)
$ psql -h localhost -p 5432 -U appuser -d production
psql (16.1)
Type "help" for help.
production=>
```

- The `psql` client connects to `localhost:5432` on the *local* machine, but that traffic is actually encrypted, sent through the SSH connection to `db-bastion.internal`, and from there forwarded to `localhost:5432` as seen *from the bastion's perspective* — which is why this pattern works even when the database only accepts connections from `127.0.0.1` and has no direct network exposure at all.
- No changes to the database's own network configuration or firewall rules are needed — the tunnel makes the remote `localhost` service reachable without ever exposing it on a public or even a routable internal interface.

**Production usage example:** This exact pattern is standard practice for reaching administrative interfaces, databases, or internal dashboards that are deliberately bound only to localhost or a private interface on a bastion/jump host, as a deliberate security boundary — rather than opening that service's port to a broader network, engineers tunnel through SSH to the one host that can reach it.

**Common errors:** Forgetting that the destination host/port in `-L` is resolved *from the SSH server's network perspective*, not the client's — a common mistake is using an address only reachable from the client's own network, which the remote server then fails to resolve or connect to, producing a confusing "connection refused" that has nothing to do with SSH itself.

## 6. Production Usage Notes

- **SSH certificates (a separate feature from SSH keys) solve the fleet-scale trust management problem** the Definition's Tip alludes to — instead of distributing individual public keys to every server's `authorized_keys` and every client's `known_hosts`, an organization runs its own SSH CA that signs both host keys and user keys, and every server/client is configured to trust that one CA's signature, dramatically simplifying key rotation and revocation at scale.
- **Bastion/jump hosts remain a standard pattern for reaching private-subnet infrastructure**, using SSH's `ProxyJump` (`-J`) option to chain through an intermediary host in one command rather than manually establishing a tunnel and a second SSH session — this keeps private infrastructure with no direct public exposure while still allowing controlled interactive access.
- **SSH agent forwarding (`-A`) should be used deliberately, not by default** — it lets a remote host use the local SSH agent's keys for further onward connections without copying the private key to that host, which is convenient for hopping through a bastion, but also means a compromised intermediate host can (while the forwarded session is active) use the forwarded agent to authenticate elsewhere as if it were the original key.

## 7. Security Considerations

- **Password authentication should be disabled in favor of public-key authentication** on any production-facing SSH server — passwords are vulnerable to brute-force and credential-stuffing attacks in a way that a sufficiently long private key practically is not, and disabling `PasswordAuthentication` in `sshd_config` closes this off entirely.
- **A changed host key warning must never be dismissed reflexively.** While a legitimately rebuilt or reimaged server is the common benign cause, the warning exists specifically to catch a man-in-the-middle attacker presenting a different host key — verifying the change through an independent channel (checking with whoever rebuilt the server, comparing the new key's fingerprint against a known-good record) before clearing the `known_hosts` entry is the correct practice, not habit-clearing it.
- **Private keys should be protected with a passphrase and, ideally, held in an SSH agent or hardware security module rather than used unprotected from disk** — an unprotected private key that leaks (via a misconfigured backup, an exposed repository, a compromised laptop) grants immediate, silent access to every system trusting that key's public counterpart.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                                 | Resolution Path                                                                                                    |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| "REMOTE HOST IDENTIFICATION HAS CHANGED" warning, connection refused | The server's host key changed — either a legitimate rebuild/reimage or a possible MITM attack | Verify through an independent channel that the change is expected before removing the old entry from `known_hosts` |
| "Permission denied (publickey)"                                | The client's private key isn't offered, isn't in the server's `authorized_keys`, or has wrong permissions | Use `ssh -v` to see which keys were offered/accepted; verify `authorized_keys` content and file permissions (`600`) on the server |
| Local port forward connects but the destination service doesn't respond | The destination host/port in `-L` is being resolved from the SSH server's perspective, not the client's | Confirm the destination is reachable *from the SSH server*, not just from the local client machine                 |
| SSH connection hangs indefinitely with no error                | A firewall or security group is silently dropping (not rejecting) traffic to port 22          | Test raw TCP reachability first (`nc -zv <host> 22`, [§117](../Part14/Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md)) before assuming an SSH-specific problem                  |

## 9. Best Practices

- Default to public-key authentication with passwords disabled entirely on production SSH servers, and protect private keys with a passphrase, loaded into an agent for daily use rather than left unprotected on disk.
- At fleet scale, adopt SSH certificates (a private SSH CA) instead of manually distributing and rotating individual public keys across every host and client — this is the SSH-native answer to the same key-management-at-scale problem TLS solves with its CA hierarchy.
- Use bastion hosts with `ProxyJump` for reaching private-subnet infrastructure rather than exposing every internal host's SSH port directly to a wider network, and use agent forwarding deliberately and sparingly rather than as a blanket default.

## 10. Common Anti-Patterns / Mistakes

- **Reflexively deleting a `known_hosts` entry to silence a host-key-mismatch warning** without first confirming the change is legitimate — this defeats the exact protection the warning exists to provide.
- **Leaving password authentication enabled on internet-facing SSH servers** "just in case," which meaningfully expands the attack surface to brute-force and credential-stuffing attempts that public-key-only authentication effectively eliminates.
- **Enabling SSH agent forwarding by default on every connection**, including to hosts of uncertain trust level — this exposes the forwarded key's signing capability to any host in the forwarding chain for the duration of the session, which is a real risk if any intermediate host is compromised.

## 11. Interview Questions

**🎯 Beginner:** _"How does SSH public-key authentication work, at a high level?"_
**Model answer:** The client has a private/public key pair. The server has a copy of the client's public key, typically in `~/.ssh/authorized_keys`. During authentication, the server issues a challenge, and the client signs it using its private key. The server verifies that signature against the public key it already has on file. If it matches, authentication succeeds — the private key itself is never transmitted or exposed during this process.
_What the interviewer is probing for:_ Understanding that authentication is proof-of-possession via a cryptographic signature, not a plaintext or hashed secret being sent across the network.

**🎯 Intermediate:** _"What is host key verification in SSH, and what does a 'REMOTE HOST IDENTIFICATION HAS CHANGED' warning actually mean?"_
**Model answer:** Host key verification is how the SSH client confirms it's actually connecting to the server it intends to, not an impostor performing a man-in-the-middle attack. The client checks the server's presented host key against what it previously recorded for that hostname in `known_hosts`. The warning means the host key no longer matches what was previously recorded — this can be entirely benign (the server was rebuilt or reimaged, generating a new host key) or it can indicate an actual man-in-the-middle attack substituting a different server. The correct response is to verify the cause through an independent channel before proceeding, not to reflexively clear the warning.
_What the interviewer is probing for:_ Whether the candidate treats this warning as a real security signal requiring judgment, rather than a nuisance to clear automatically.

**🎯 Senior:** _"Your organization manages several hundred servers with SSH access distributed via individually-managed public keys in each server's `authorized_keys`. What problems does this create at scale, and how would you address them?"_
**Model answer:** The core problem is that key distribution and revocation don't scale — onboarding a new engineer means pushing their public key to every server they need access to, and offboarding means removing it from every one of those servers, which is error-prone and easy to miss entries on. It also makes auditing who has access to what nearly impossible without external tooling, since `authorized_keys` files are scattered across the fleet with no central record. I'd address this by standing up an internal SSH Certificate Authority: instead of distributing raw public keys, the CA signs short-lived user certificates, and every server is configured to trust that one CA's signing key rather than maintaining individual `authorized_keys` entries. This centralizes issuance, makes revocation a matter of not re-issuing (since certificates are short-lived) rather than hunting down every host, and gives a single audit point for who was issued access and when.
_What the interviewer is probing for:_ Awareness that ad hoc key management doesn't scale, and specific knowledge of SSH certificates as the standard solution, not just "use a password manager" or similarly inadequate answers.

**🎯 Architect:** _"Design the SSH access architecture for a company with a private VPC containing sensitive infrastructure and no direct public SSH exposure allowed on any internal host. What does the access path look like end to end?"_
**Model answer:** I'd deploy a hardened bastion host (or a small pool of them, behind a load balancer or in multiple AZs for availability) as the single point of ingress, with its own strict security group allowing SSH only from known corporate IP ranges or through an identity-aware proxy. Every internal host would have no SSH port exposed to anything except the bastion's security group, enforced at the network layer ([§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md), Part 10), not just by configuration convention. Engineers would connect via `ssh -J bastion internal-host` (ProxyJump) rather than two manual hops, using SSH certificates issued by an internal CA with short validity windows tied to an identity provider, so access is both auditable and automatically expiring rather than relying on long-lived static keys. I'd disable agent forwarding by default and require step-up, per-session certificate issuance for anything touching genuinely sensitive systems, and I'd centrally log every bastion session for audit purposes, since the bastion is the one chokepoint where all such access is guaranteed to be observable.
_What the interviewer is probing for:_ End-to-end architectural thinking that combines SSH-specific mechanisms (ProxyJump, certificates) with network-layer controls (security groups) and identity/audit concerns, rather than a narrow "just use a bastion" answer.

## 12. Common Misconceptions

1. **"SSH and TLS use the same trust model, just for different protocols."** They don't — TLS relies on a hierarchical CA system ([§66](Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md)) that both parties trust in advance; SSH's default model is decentralized trust-on-first-use for servers and an explicit authorized-keys list for clients, though SSH certificates offer an optional CA-like model at scale.
2. **"SSH tunneling requires special server-side configuration beyond normal SSH access."** Port forwarding is a standard SSH capability available to any account with SSH access by default (unless explicitly disabled in `sshd_config` via `AllowTcpForwarding no`) — no special setup is required on the server for the client to request a tunnel.
3. **"A changed host key always means an attack."** It's frequently benign (server rebuild, reimage, IP address reuse) — but because it can also indicate a genuine attack, it always warrants verification rather than automatic dismissal in either direction.
4. **"Password authentication and public-key authentication provide equivalent security if the password is strong."** Public-key authentication is resistant to remote brute-force in a way passwords fundamentally aren't (the private key never crosses the network at all), and disabling password authentication removes an entire attack class regardless of password strength.

## 13. 🔑 Key Takeaways

- SSH provides an encrypted, authenticated channel over TCP (typically port 22), with server authentication via host keys (TOFU/`known_hosts`) and client authentication typically via public-key proof-of-possession.
- SSH's trust model is decentralized by default (host-by-host, key-by-key), in contrast to TLS's CA-hierarchy model ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md), [§66](Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md)) — SSH certificates exist as an optional, CA-like solution for managing trust at fleet scale.
- All SSH functionality — shell sessions, SFTP ([§69](Section-69-Part8-File-Transfer-Protocols-FTP-SFTP-SCP.md)), and every port-forwarding mode — is multiplexed as separate channels over one underlying encrypted TCP connection.
- Local (`-L`), remote (`-R`), and dynamic (`-D`) port forwarding are genuinely load-bearing production techniques for reaching or exposing services across network boundaries without opening new firewall rules.
- A host-key-mismatch warning is a real security signal that always warrants independent verification, never reflexive dismissal in either direction.

## 14. Related Concepts & What's Next

[§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) and [§66](Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md) provide a useful point of comparison for SSH's authentication and trust model, since both protocols solve a structurally similar problem (an encrypted, authenticated channel) with different trust architectures worth contrasting explicitly. [§69](Section-69-Part8-File-Transfer-Protocols-FTP-SFTP-SCP.md) covers SFTP and SCP, both of which run as channels over the exact same underlying SSH connection and authentication model introduced in this section, rather than as separate protocols with their own handshakes. [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) (Part 10) covers security groups and network ACLs, directly relevant to the bastion-host and network-segmentation architecture discussed in this section's Architect answer. [§92](../Part11/Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md) (Part 11) covers IPsec and other tunneling protocols, offering a useful contrast against SSH's application-layer tunneling approach for readers who continue into the VPN-focused Part 11.

**Next Section:** [§68](Section-68-Part8-Email-Protocols-SMTP-IMAP-POP3-Conceptual-Overview.md) — `Section-68-Part8-Email-Protocols-SMTP-IMAP-POP3-Conceptual-Overview.md`
