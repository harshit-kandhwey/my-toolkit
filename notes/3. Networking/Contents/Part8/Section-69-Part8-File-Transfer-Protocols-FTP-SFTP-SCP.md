# Section 69 (Part 8): File Transfer Protocols: FTP, SFTP, SCP

## 1. Definition

**Plain language:** Moving a file between two machines over a network sounds like it should be one obvious thing, but there are several genuinely different ways to do it, with very different security and design properties: an old plaintext protocol built with its own separate control and data connections (FTP), a secure file-transfer protocol that rides inside an SSH connection (SFTP), and a simple secure copy command that also rides inside SSH (SCP). Knowing which one a given tool, script, or vendor integration is actually using changes how you secure, firewall, and troubleshoot it.

**Precise definition:** **FTP (File Transfer Protocol)**, RFC 959, is one of the internet's oldest protocols, using **two separate TCP connections** — a persistent **control connection** (port 21) for commands/responses, and a separate, per-transfer **data connection** for the actual file bytes, opened either in **active mode** (server connects back to the client) or **passive mode** (client connects to a server-specified port). FTP transmits credentials and data in **plaintext** by default; **FTPS** layers TLS ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) on top of classic FTP without changing its two-connection architecture. **SFTP (SSH File Transfer Protocol)**, despite the similar name, is an entirely different protocol from FTP — it is a **subsystem/channel running inside an already-established SSH connection** ([§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md)), using SSH's single encrypted connection, authentication, and port (22) for everything, with no separate data connection and no plaintext mode at all. **SCP (Secure Copy Protocol)** is an even simpler file-copy mechanism, also running as a channel over an SSH connection, historically implemented via the remote execution of a `scp` binary that streams file data over the SSH channel — modern OpenSSH has deprecated SCP's legacy wire protocol in favor of using SFTP as the underlying transfer mechanism while keeping the familiar `scp` command-line syntax.

> 💡 **Tip:** If a tool or vendor documentation says "FTP" without qualification, assume it means the original plaintext protocol with two connections and no encryption unless "FTPS" or "SFTP" is stated explicitly — the three-letter-acronym similarity between FTP, FTPS, and SFTP causes real, repeated confusion in production, including engineers opening the wrong firewall ports (21 and a passive-mode range for FTP/FTPS, versus just port 22 for SFTP) because they assumed all three worked the same way.

## 2. Why This Matters

- **FTP's dual-connection architecture is a genuine, persistent firewall and NAT headache** that infrastructure engineers still encounter today with legacy vendor integrations, and understanding active vs. passive mode is necessary to actually fix connectivity issues rather than guessing at firewall rules.
- **Plaintext FTP transmitting credentials in the clear is a real, still-encountered security liability** in legacy systems, and recognizing it for what it is (rather than assuming "FTP" is a generic safe term) is a basic security literacy requirement.
- **SFTP has become the de facto standard for secure file transfer in modern infrastructure** — it rides on the same well-understood SSH port and authentication model already covered in [§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md), making it simpler to firewall and secure correctly than FTP/FTPS ever was.
- **SCP's protocol-level deprecation (while the command survives) is a subtle but real detail** that trips up engineers relying on old scripts or automation, especially around specific edge-case behaviors that differ between legacy SCP and SFTP-backed `scp`.
- **File transfer automation is everywhere in infrastructure work** — deployment artifact distribution, log shipping, backup transfer, and legacy vendor/EDI integrations all commonly rely on one of these three protocols, making fluency with all three a practical day-to-day skill.

## 3. Prerequisites and Dependencies

This section directly builds on [§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md)'s coverage of SSH protocol structure, key exchange, and authentication, since both SFTP and modern SCP are channels running over an already-established SSH connection and inherit all of SSH's authentication and encryption properties rather than defining their own — [§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md) should be read first for that shared foundation to make sense. TCP connection fundamentals from Part 7 ([§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)), particularly the distinction between well-known ports ([§60](../Part7/Section-60-Part7-Common-Port-Reference-22-80-443-53-3306-5432-6379-etc.md)) and how NAT/firewalls handle inbound versus outbound connections, are directly relevant to understanding FTP's active/passive mode distinction covered in this section. [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)'s TLS coverage is relevant background for understanding FTPS specifically, though this section does not assume it as a strict prerequisite.

## 4. Architecture / Conceptual Diagram

```text
   FTP (plaintext, two connections)

   Client                                          Server
      │  Control connection (port 21, persistent)
      ├──────────────────────────────────────────────►
      │  USER/PASS, commands (LIST, RETR, STOR)
      │◄──────────────────────────────────────────────┤
      │  responses
      │
      │  ACTIVE MODE: server opens a NEW connection    PASSIVE MODE: client opens a
      │  back to a client-specified port for data      NEW connection to a server-
      │  (server ►client — often blocked by client-    specified port for data
      │  side firewalls/NAT)                            (client ►server — the modern
      │                                                   default, more firewall/NAT-
      │  Data connection (separate TCP connection,        friendly)
      │  ephemeral port, carries the actual file bytes)
      └────────────────────────────────────────────────►

   SFTP / SCP (both riding inside ONE existing SSH connection, §67)

   Client                                          Server
      │  ONE SSH connection (port 22) — key exchange,
      │  host key verification, client authentication
      │  all exactly as in §67
      ├──────────────────────────────────────────────►◄
      │
      │  SFTP: a dedicated SSH "subsystem" channel      SCP (modern OpenSSH): the scp
      │  offering a rich, structured file-transfer       command actually negotiates
      │  protocol (list directories, resume transfers,   and uses the SFTP protocol
      │  set permissions) — no second connection ever    underneath by default, kept
      │  opens                                            only for its familiar CLI syntax
      │
      └──────────────────────────────────────────────► (all traffic — auth, listing,
                                                           file bytes — inside the SAME
                                                           single encrypted TCP connection)
```

- **FTP's two-connection design is a direct product of its age (1971's original spec, RFC 959 in 1985)** — predating both NAT and modern stateful firewalls entirely, which is precisely why it interacts so awkwardly with both; SFTP and SCP's single-connection SSH-channel design avoids this entire class of problem by construction.
- **Passive mode became the practical default for FTP specifically because active mode requires the server to initiate a new inbound connection to the client** — something client-side firewalls and NAT devices routinely block by default, since inbound connections not matching an existing outbound request look identical to unsolicited traffic.
- **SFTP is not "FTP over SSH" despite the name suggesting a relationship** — it is a distinct protocol (defined as an SSH subsystem) with its own command set, entirely independent of the classic FTP protocol's commands and two-connection model; the naming similarity is a frequent, genuine source of confusion.

## 5. Hands-On

### 5.1 Transferring a File with SFTP

**Purpose:** Demonstrate SFTP's interactive, structured session model, riding entirely over one SSH connection.

**Syntax:**

```bash
sftp <user>@<host>
```

**Example usage and expected output:**

```bash
$ sftp deploy@app-server.internal
Connected to app-server.internal.
sftp> ls
releases/  logs/  config/
sftp> put build/app-v2.3.0.tar.gz releases/
Uploading build/app-v2.3.0.tar.gz to /home/deploy/releases/app-v2.3.0.tar.gz
app-v2.3.0.tar.gz    100%   42MB  38.1MB/s   00:01
sftp> chmod 644 releases/app-v2.3.0.tar.gz
sftp> exit
```

- The entire session — directory listing, upload, and even a permission change (`chmod`) — happens over the one SSH connection established at the start, with no separate data connection ever opening, unlike FTP's model.
- `chmod` inside an SFTP session is a genuine protocol feature (SFTP defines rich file-operation commands beyond simple get/put), something classic FTP's command set does not offer in the same structured way.

**Production usage example:** SFTP is the standard mechanism for exchanging files with external partners, vendors, and legacy systems (EDI file drops, batch report delivery) where a simple, secure, firewall-friendly (single port 22) transfer method is needed without standing up broader SSH shell access — many SFTP server deployments deliberately restrict an account to SFTP-only, with no interactive shell access at all, using SSH server configuration (`ForceCommand internal-sftp` in OpenSSH).

**Common errors:** Assuming an SFTP-only account (shell access deliberately disabled) will also work for a normal `ssh` login — a common point of confusion is expecting `ssh user@host` to work for an account intentionally locked to SFTP-only access, when only `sftp`/`scp` clients (which negotiate the SFTP subsystem specifically rather than requesting an interactive shell) will succeed.

### 5.2 Diagnosing FTP Passive Mode Connectivity with `curl` and Packet Inspection

**Purpose:** Show FTP's data-connection negotiation explicitly, since this is the single most common FTP troubleshooting scenario in production.

**Syntax:**

```bash
curl -v --ftp-pasv ftp://<host>/<path>
```

**Example usage and expected output:**

```bash
$ curl -v --ftp-pasv ftp://files.example.com/reports/daily.csv
* Connected to files.example.com port 21
< 220 FTP server ready
> USER anonymous
< 331 Please specify the password
> PASS curl@
< 230 Login successful
> PASV
< 227 Entering Passive Mode (203,0,113,10,200,15)
* Connecting to files.example.com (203.0.113.10) port 51215
> RETR reports/daily.csv
< 150 Opening data connection
< 226 Transfer complete
```

- `PASV` and the `227 Entering Passive Mode` response are the exact negotiation from the diagram above — the numbers `(203,0,113,10,200,15)` encode the IP address (`203.0.113.10`) and port (`200*256+15 = 51215`) the client must open a **new** connection to for the actual file data, distinct from the control connection on port 21.
- A firewall that allows outbound port 21 but blocks the ephemeral high port range (like `51215` above) will complete the control conversation successfully and then hang or fail specifically at the `RETR` step — a very recognizable and diagnosable failure pattern once this negotiation is understood.

**Production usage example:** This exact diagnostic approach — watching for the `PASV`/`227` exchange and confirming the negotiated data port is reachable — is the standard method for resolving "FTP connects but transfers hang or time out" tickets, which are almost always a firewall/NAT issue with the negotiated data connection, not a problem with the control connection or credentials.

**Common errors:** Firewalling only port 21 for an FTP server and assuming that's sufficient — without also allowing the passive-mode port range the server is configured to use (a configurable range, not a single fixed port), every data transfer will fail even though login and directory listing (which only use the control connection) appear to work fine.

## 6. Production Usage Notes

- **SFTP has effectively replaced plain FTP and FTPS for new infrastructure** almost everywhere encryption and firewall-friendliness matter, given it reuses the already-hardened, already-understood SSH transport and authentication model ([§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md)) rather than requiring a separate TLS configuration and a wide firewall port range for passive-mode data connections.
- **Legacy vendor and EDI integrations are the most common place plain FTP still survives in production** — many older enterprise systems and partner integrations were built against FTP decades ago and migrating them is a real, ongoing infrastructure modernization task rather than a solved problem.
- **Modern OpenSSH `scp` uses the SFTP protocol underneath by default** as of recent OpenSSH versions, specifically because SCP's original legacy wire protocol had known security and correctness issues around filename handling — scripts and automation relying on exact legacy `scp` protocol behavior (rather than just its command-line interface) should be reviewed when upgrading OpenSSH versions.

## 7. Security Considerations

- **Plain FTP transmits usernames, passwords, and file contents in cleartext** — any credentials or sensitive data transferred over unencrypted FTP are trivially interceptable by anyone on the network path; FTPS (FTP-over-TLS) or, preferably, SFTP should be used for anything beyond genuinely public, non-sensitive file distribution.
- **Passive-mode FTP's requirement for a wide range of open ephemeral ports on the server side is itself a security consideration** — a broad passive-port firewall rule is a larger attack surface than SFTP's single well-understood port 22, and passive port ranges should be kept as narrow as the deployment realistically allows.
- **SFTP inherits SSH's entire authentication model ([§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md)) directly**, meaning the same best practices apply without modification — public-key authentication over password authentication, and careful management of accounts restricted to SFTP-only access to ensure that restriction is actually enforced (`ForceCommand`/`ChrootDirectory` configured correctly) rather than assumed.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                   | Resolution Path                                                                                                    |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| FTP login and directory listing work, but file transfers hang or time out | The passive-mode data connection port range is blocked by a firewall/NAT, even though control-connection port 21 is open | Identify the server's configured passive port range and open it in the firewall; confirm with `curl -v --ftp-pasv`  |
| SFTP user can log in but "permission denied" on every file operation | The account's home directory or `ChrootDirectory` permissions are misconfigured for SFTP-only restricted access | Verify server-side `sshd_config` `Match` block settings and filesystem permissions for the SFTP-restricted account |
| `scp` between two servers fails after an OpenSSH upgrade, worked before | Legacy SCP wire-protocol-specific behavior no longer matches the SFTP-backed implementation now used by default | Test with explicit SFTP (`sftp`/`rsync -e ssh`) as an alternative, or use the legacy flag if truly required temporarily |
| FTP client reports "can't connect to data connection" specifically | Active mode is being used and the client's own firewall/NAT is blocking the server's inbound connection attempt | Switch the client to passive mode, which reverses the connection direction to client-initiated |

## 9. Best Practices

- Default to SFTP for any new file-transfer requirement needing encryption, given it reuses SSH's already-hardened transport and authentication and avoids FTP's firewall-unfriendly two-connection model entirely.
- When FTP/FTPS must be supported for legacy compatibility, use passive mode as the default and keep the passive port range as narrow as operationally viable, opening exactly that range (plus port 21) in the firewall rather than guessing.
- For SFTP-only accounts (partners, automated integrations that should never get shell access), explicitly configure `ForceCommand internal-sftp` and `ChrootDirectory` restrictions on the SSH server rather than relying on convention or assuming a restricted account is actually restricted.

## 10. Common Anti-Patterns / Mistakes

- **Continuing to use plaintext FTP for anything transmitting credentials or sensitive data**, purely out of legacy inertia, when SFTP or FTPS have been the clearly superior options for many years.
- **Firewalling only port 21 for an FTP server and being surprised transfers fail** — the passive (or active) data connection port range is just as essential to allow as the control port, and is the single most common FTP firewall misconfiguration.
- **Assuming SFTP and FTP are close enough to be interchangeable in firewall rules, client configuration, or vendor documentation** — the protocols share almost nothing at the wire level beyond both moving files, and treating them as interchangeable causes real, avoidable connectivity troubleshooting time.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between FTP and SFTP?"_
**Model answer:** Despite the similar name, they're different protocols. FTP is an old protocol that uses two separate TCP connections — one for commands, one for the actual file data — and transmits everything, including credentials, in plaintext by default. SFTP is a completely different protocol that runs as a channel inside an already-encrypted SSH connection, using SSH's single connection, port, and authentication model for everything, with no plaintext mode and no separate data connection.
_What the interviewer is probing for:_ Whether the candidate knows these are genuinely distinct protocols rather than "SFTP = FTP plus encryption," which is a very common and understandable but incorrect assumption from the naming alone.

**🎯 Intermediate:** _"Explain the difference between active and passive mode in FTP, and why passive mode is generally preferred today."_
**Model answer:** In active mode, after the client and server establish the control connection, the server initiates a new, separate connection back to a port the client specifies for the actual data transfer. In passive mode, the server instead tells the client a port to connect to, and the client initiates that second connection itself. Passive mode is generally preferred because most client-side firewalls and NAT devices block unsolicited inbound connections by default — active mode requires exactly that kind of server-initiated inbound connection to the client, which fails in most modern network setups, while passive mode only requires the client to make outbound connections, which is far more commonly allowed.
_What the interviewer is probing for:_ Real understanding of the connection-direction distinction and its practical firewall/NAT implications, not just memorized terminology.

**🎯 Senior:** _"A partner's automated FTP integration works fine on some days and mysteriously fails on others with data transfer timeouts, while logins always succeed. What's your investigation approach?"_
**Model answer:** Since logins and control-connection commands succeed consistently while data transfers specifically time out intermittently, I'd focus on the passive-mode data connection rather than authentication or the control channel. My first hypothesis is a firewall or load balancer in the path with a limited or dynamically-changing passive port range allowance, or a stateful firewall that's timing out idle data connections under certain conditions (larger files, slower transfers, or specific times of day with different traffic patterns affecting connection table pressure). I'd capture the exact `PASV`/`227` response during both a successful and a failing transfer to see whether the negotiated port falls outside an allowed range inconsistently, and check firewall/NAT logs for drops on that specific port during failure windows. Given FTP's inherent fragility here, I'd also raise migrating this partner integration to SFTP as the actual long-term fix, since it eliminates this entire class of intermittent failure by using a single, static, already-allowed port.
_What the interviewer is probing for:_ Systematic isolation of which connection (control vs. data) is actually failing, and recognition that FTP's architecture is the root cause worth addressing rather than endlessly firefighting firewall rules.

**🎯 Architect:** _"You're planning to migrate a legacy batch file-exchange system with dozens of external partners off plaintext FTP. What does the migration plan and target architecture look like?"_
**Model answer:** I'd target SFTP as the standard replacement protocol given it reuses SSH's already-understood authentication and transport model, needs only a single firewall port, and eliminates the entire class of passive/active mode and cleartext-credential problems inherent to FTP. Since partners are external and can't all migrate simultaneously, I'd run both protocols in parallel during a transition window, with SFTP as the default for any partner able to move, and a clear deprecation timeline communicated for plain FTP. For the SFTP side, I'd provision each partner an SFTP-only account (`ForceCommand internal-sftp`, `ChrootDirectory` scoped to only that partner's directory) so no partner can see another's files and none get incidental shell access. I'd standardize on public-key authentication per partner rather than passwords, with a clear key-rotation and offboarding process. I'd also build monitoring specifically for transfer completion and failure rates per partner during the transition, since silently broken automated integrations (a batch job failing overnight with nobody watching) are the realistic failure mode of this kind of migration, not a dramatic outage.
_What the interviewer is probing for:_ End-to-end migration planning that accounts for external-partner constraints, per-tenant isolation, and operational monitoring — not just "switch the protocol."

## 12. Common Misconceptions

1. **"SFTP is just FTP running over an encrypted connection."** SFTP is an entirely separate protocol (an SSH subsystem) with its own command set and single-connection model — it shares essentially nothing at the wire-protocol level with classic FTP beyond the general purpose of transferring files.
2. **"Opening port 21 is sufficient to allow FTP through a firewall."** The separate data connection (active or passive mode) requires its own port or port range to be allowed as well; port 21 alone only permits the control conversation.
3. **"SCP and SFTP are unrelated, competing protocols."** Modern OpenSSH's `scp` command uses the SFTP protocol as its underlying transfer mechanism by default, preserving only the familiar command-line syntax — they are not fully independent implementations at the wire level in current OpenSSH.
4. **"FTP is obsolete and never appears in modern infrastructure."** It persists meaningfully in legacy vendor, EDI, and partner integrations that predate more modern alternatives, making FTP troubleshooting and firewall configuration a still-relevant, if declining, skill.

## 13. 🔑 Key Takeaways

- FTP uses two separate TCP connections (control on port 21, data negotiated separately via active or passive mode) and transmits everything, including credentials, in plaintext by default.
- SFTP and modern SCP are unrelated to FTP at the wire-protocol level — both run as channels inside a single, already-encrypted, already-authenticated SSH connection ([§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md)), avoiding FTP's dual-connection firewall complications entirely.
- Passive mode (client-initiated data connection) is the practical default for FTP today because it works with standard firewall/NAT behavior in a way active mode (server-initiated inbound connection) generally does not.
- FTP data-connection timeouts, despite successful control-connection logins, are the single most common and most diagnosable FTP production issue, traceable directly via the `PASV`/`227` negotiation.
- SFTP has become the practical default for secure file transfer in modern infrastructure, with plain FTP persisting mainly in legacy vendor and partner integrations still awaiting migration.

## 14. Related Concepts & What's Next

[§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md) is the direct prerequisite for this section's SFTP and SCP coverage, since both protocols are channels running over the exact SSH connection, key exchange, and authentication model introduced there — revisiting [§67](Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md) alongside this section reinforces how little additional machinery SFTP/SCP actually need beyond SSH itself. [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) provides the TLS background relevant to FTPS specifically, for readers working with legacy FTPS deployments. [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) (Part 10) covers security groups and network ACLs, directly relevant to the passive-mode port-range firewall configuration this section's troubleshooting scenarios depend on. [§70](Section-70-Part8-WebSockets-and-Persistent-Connections.md) shifts to a very different persistent-connection model — WebSockets — closing out the request/response-oriented protocols of this Part before moving into protocols built around long-lived, bidirectional connections.

**Next Section:** [§70](Section-70-Part8-WebSockets-and-Persistent-Connections.md) — `Section-70-Part8-WebSockets-and-Persistent-Connections.md`
