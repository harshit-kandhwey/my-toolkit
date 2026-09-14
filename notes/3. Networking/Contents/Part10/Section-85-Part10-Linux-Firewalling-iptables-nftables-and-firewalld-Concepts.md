# Section 85 (Part 10): Linux Firewalling: iptables/nftables and firewalld Concepts

## 1. Definition

**Plain language:** On Linux, the kernel itself is the firewall — `iptables`, `nftables`, and `firewalld` are just different front-end tools for configuring the same underlying packet-filtering machinery (`netfilter`). `iptables` is the older, still-widespread tool with a table-and-chain model. `nftables` is its modern, more efficient successor with cleaner syntax. `firewalld` is a higher-level daemon (commonly the default on RHEL/Fedora/CentOS-family systems) that manages either backend for you through a "zones and services" abstraction, so you rarely write raw rules by hand.

**Precise definition:** **Netfilter** is the Linux kernel's packet-filtering framework, providing hooks at defined points in the network stack (prerouting, input, forward, output, postrouting) where rules can inspect, accept, drop, or modify packets. **`iptables`** is the traditional userspace tool for configuring netfilter, organizing rules into **tables** (`filter`, `nat`, `mangle`, `raw`) each containing **chains** (`INPUT`, `OUTPUT`, `FORWARD`, plus NAT-specific chains) evaluated in order. **`nftables`** is the modern replacement (targeted to eventually fully supersede iptables), using a single unified framework with user-defined tables and chains, a more expressive syntax, and better performance for large rule sets. **`firewalld`** is a dynamic firewall management daemon that sits atop either `iptables` or `nftables` as its backend, exposing a **zone**-based model (`public`, `internal`, `dmz`, `trusted`, etc.) where each network interface is assigned a zone, and each zone has an associated set of allowed services/ports — changes apply immediately without the connection-dropping rule-flush-and-reload cycle raw `iptables` editing can require.

> 💡 **Tip:** These three are not three competing firewalls — they are three layers of abstraction over the same kernel feature. `firewalld` calls into `nftables` (or `iptables` on older systems) on your behalf; if you're not sure which layer a production system uses, check `systemctl status firewalld` first, since a running `firewalld` means you should almost never hand-edit raw `iptables`/`nft` rules directly, as `firewalld` will overwrite or conflict with them.

## 2. Why This Matters

- **Nearly every Linux server in production sits behind one of these three tools** (or explicitly none, which is itself a security-relevant decision) — understanding at least one deeply, and recognizing the other two on sight, is baseline competency for any infrastructure engineer working with Linux hosts.
- **The stateful filtering concept from [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) is implemented concretely here** via `-m conntrack`/`-m state` in iptables or the `ct state` expression in nftables — this section is where that abstract concept becomes real, typeable syntax.
- **Mixing management tools on the same host causes real, hard-to-diagnose outages** — hand-editing `iptables` rules on a `firewalld`-managed system (or vice versa) leads to rules silently disappearing on the next `firewalld` reload, a genuinely common production incident.
- **nftables is the direction the entire Linux ecosystem is moving** (many distributions now ship `iptables` as a compatibility shim over `nftables` under the hood) — understanding the native `nft` syntax is increasingly necessary, not optional, for staying current.
- **Cloud instances running self-managed Linux firewalls layer directly beneath the security-group and NACL model from [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)** — a cloud engineer frequently needs to reason about both layers together when troubleshooting connectivity.

## 3. Prerequisites and Dependencies

This section directly implements the concepts from [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) (stateless vs. stateful filtering) using real Linux syntax, and extends [§83](Section-83-Part10-Firewall-Placement-Perimeter-Host-Based-and-Segmentation-Patterns.md)'s host-based placement pattern with the specific tooling that realizes it. Basic Linux command-line familiarity (this repository's Linux knowledge base) and comfort with the TCP/IP port and protocol concepts from Part 7 ([§59](../Part7/Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md) for ports/sockets) are assumed. [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)'s cloud security-group model is a useful point of contrast throughout, since a self-managed instance often runs both a cloud security group and one of these host-level tools simultaneously. [§90](Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md) (micro-segmentation) revisits `nftables`/`iptables` briefly in the context of implementing fine-grained segmentation policy on individual hosts.

## 4. Architecture / Conceptual Diagram

```text
                         KERNEL SPACE
   ┌──────────────────────────────────────────────────────────┐
   │                    NETFILTER HOOKS                        │
   │   prerouting ──► input ──► [ local process ] ──► output ──► postrouting
   │                     │                              ▲
   │                     ▼                              │
   │                  forward ────────────────────────────
   │   (packets not destined for this host route through forward)
   └───────────────────────────┬────────────────────────────────┘
                                │  configured by
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
   ┌──────────────────┐ ┌──────────────┐ ┌───────────────────┐
   │     iptables      │ │  nftables    │ │     firewalld      │
   │  tables → chains  │ │  tables →    │ │  zones → services  │
   │  → numbered rules  │ │  chains →    │ │  (calls nftables/  │
   │  (legacy, still    │ │  rules       │ │   iptables under   │
   │  ubiquitous)       │ │  (modern     │ │   the hood — do    │
   │                    │ │  successor)  │ │   NOT hand-edit    │
   │                    │ │              │ │   the backend      │
   │                    │ │              │ │   directly)         │
   └──────────────────────┘ └──────────────┘ └───────────────────┘
```

- **All three tools ultimately configure the same kernel hooks** — there is no functional difference in what's achievable, only in syntax, ergonomics, and (for nftables) performance at scale.
- **`firewalld`'s zone model maps interfaces to trust levels** (`public` for internet-facing interfaces, `internal`/`trusted` for internal networks) rather than requiring per-rule IP/port bookkeeping — this is a genuinely higher level of abstraction than raw `iptables`/`nft` rule authorship.
- **The `FORWARD` chain matters specifically for hosts acting as routers or NAT gateways** — traffic merely passing through a Linux box (not destined for a local process) traverses `FORWARD`, not `INPUT`/`OUTPUT`, a frequent source of confusion when a Linux NAT gateway's rules don't behave as expected.

## 5. Hands-On

### 5.1 Basic iptables Rule Management

**Purpose:** Establish the fundamental table/chain/rule vocabulary and demonstrate a minimal, production-shaped default-deny host firewall.

**Syntax:**

```bash
iptables -A <chain> -p <protocol> --dport <port> -j <target>
iptables -L -n -v --line-numbers
iptables -D <chain> <rule-number>
```

**Example usage and expected output:**

```bash
$ sudo iptables -A INPUT -p tcp --dport 22 -s 10.0.5.0/24 -j ACCEPT
$ sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
$ sudo iptables -A INPUT -j DROP

$ sudo iptables -L INPUT -n -v --line-numbers
Chain INPUT (policy ACCEPT 0 packets, 0 bytes)
num   pkts bytes target     prot opt in     out     source          destination
1        3   180 ACCEPT     tcp  --  any    any     10.0.5.0/24     0.0.0.0/0    tcp dpt:22
2      842  95K  ACCEPT     all  --  any    any     0.0.0.0/0       0.0.0.0/0    ctstate RELATED,ESTABLISHED
3        0    0  DROP       all  --  any    any     0.0.0.0/0       0.0.0.0/0
```

**Production usage example:** This exact three-rule shape (specific allow, established/related allow, default drop) is the minimal viable production host-firewall baseline, typically templated via configuration management and applied consistently across a fleet rather than hand-typed per host.

**Common errors:** Forgetting that `iptables` rules are not persistent across reboots by default on most distributions — a rule set built interactively and not saved (via `iptables-save`, or the distribution's persistence service) silently reverts to the previous ruleset on the next reboot, a classic "it worked yesterday" incident.

### 5.2 Equivalent Ruleset in nftables

**Purpose:** Show the same default-deny host firewall in modern `nftables` syntax, illustrating the unified table/chain model and native state matching.

**Syntax:**

```bash
nft add table inet <table-name>
nft add chain inet <table-name> <chain-name> { type filter hook input priority 0 \; policy drop \; }
nft add rule inet <table-name> <chain-name> <match> <action>
```

**Example usage and expected output:**

```bash
$ sudo nft add table inet filter
$ sudo nft add chain inet filter input { type filter hook input priority 0 \; policy drop \; }
$ sudo nft add rule inet filter input ct state established,related accept
$ sudo nft add rule inet filter input tcp dport 22 ip saddr 10.0.5.0/24 accept

$ sudo nft list ruleset
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        tcp dport 22 ip saddr 10.0.5.0/24 accept
    }
}
```

**Production usage example:** Distributions increasingly ship `nftables` as the actual backend even when administrators type `iptables` commands (via an `iptables-nft` compatibility layer) — writing native `nft` rules directly is the forward-compatible approach and avoids relying on a translation shim that may eventually be deprecated.

**Common errors:** Mixing `nft` and legacy `iptables` commands against the same underlying ruleset without understanding whether the system's `iptables` binary is the legacy backend or the `nft`-compatible shim — `iptables-legacy` and `iptables-nft` can produce genuinely different, non-interoperable rule stores on the same host.

### 5.3 Managing Zones and Services with firewalld

**Purpose:** Demonstrate the higher-level zone/service abstraction firewalld provides, and show that changes apply live without a disruptive full rule reload.

**Syntax:**

```bash
firewall-cmd --get-active-zones
firewall-cmd --zone=<zone> --add-service=<service> --permanent
firewall-cmd --reload
```

**Example usage and expected output:**

```bash
$ sudo firewall-cmd --get-active-zones
public
  interfaces: eth0

$ sudo firewall-cmd --zone=public --add-service=https --permanent
success
$ sudo firewall-cmd --reload
success

$ sudo firewall-cmd --zone=public --list-services
dhcpv6-client https ssh
```

**Production usage example:** `firewalld`'s live-reload model (`--reload` applies permanent changes without dropping existing tracked connections) is specifically why it's preferred on interactive or remotely-managed hosts over hand-editing raw `iptables`, where a mistimed flush-and-reapply cycle can sever the very SSH session the administrator is using to make the change.

**Common errors:** Forgetting `--permanent` (the change applies to the running configuration only and is lost on the next reload or reboot) or forgetting the subsequent `--reload` (a `--permanent` change without a reload doesn't take effect immediately) — both are extremely common firewalld mistakes that produce "I made the change but it's not working" confusion.

## 6. Production Usage Notes

- **`firewalld` is the practical default on RHEL/Fedora/CentOS-family production systems**, and hand-editing `iptables`/`nft` rules directly on such a host is an anti-pattern that will eventually be silently undone by a `firewalld` reload.
- **Debian/Ubuntu-family systems more commonly use raw `iptables`/`nftables` directly (often via `ufw` as a simpler wrapper)** — knowing which distribution family and which management layer a given host uses is a prerequisite to touching its firewall configuration at all.
- **Rule persistence across reboots is a real, easily-missed operational detail** for raw `iptables`/`nftables` — always confirm the distribution's persistence mechanism (`iptables-persistent`, `nftables.service` loading a saved ruleset file, or `firewalld` handling this automatically) before assuming a rule survives a restart.

## 7. Security Considerations

- **A host with no firewall at all, relying solely on a cloud security group, has no defense-in-depth if the security group is ever misconfigured** — this is the exact host-based layer argument from [§83](Section-83-Part10-Firewall-Placement-Perimeter-Host-Based-and-Segmentation-Patterns.md) made concrete: a Linux host firewall is cheap insurance against an upstream security-group mistake.
- **`iptables`/`nftables` rules can be bypassed by anything running with root/CAP_NET_ADMIN privileges**, meaning host-level firewall rules are not a substitute for limiting which processes and users have that level of access on a given host.
- **`firewalld`'s zone model, if misconfigured** (an interface accidentally placed in the permissive `trusted` zone instead of `public`), silently grants far broader access than intended — checking `firewall-cmd --get-active-zones` and each zone's actual interface assignment should be a routine part of any host security review.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                   | Resolution Path                                                                                                    |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Firewall rules that worked yesterday are gone after a reboot             | Rules were applied interactively without a persistence mechanism configured                       | Save/persist the ruleset explicitly (`iptables-save` + persistence package, `nft` ruleset file, or use `firewalld` which persists `--permanent` changes automatically) |
| A `firewall-cmd` change appears to have no effect                       | Missing `--permanent` flag, missing subsequent `--reload`, or editing the wrong zone               | Re-apply with `--permanent`, run `--reload`, and confirm with `--get-active-zones` which zone the relevant interface is actually in |
| Rules added with raw `iptables`/`nft` commands mysteriously disappear    | `firewalld` is running on the host and its own ruleset management overwrote the manual rules       | Check `systemctl status firewalld`; if active, manage rules exclusively through `firewall-cmd` (rich rules or direct interface) rather than raw commands |

## 9. Best Practices

- Identify and stick to exactly one management layer per host (`firewalld` XOR raw `iptables`/`nftables`) — never hand-edit the backend on a `firewalld`-managed system.
- Always confirm rule persistence across reboots explicitly rather than assuming an interactively-applied rule set survives a restart.
- Prefer native `nftables` syntax for new work where the distribution supports it well, since it's the direction the ecosystem is converging on and generally performs better with large rule sets.

## 10. Common Anti-Patterns / Mistakes

- **Hand-editing raw `iptables`/`nft` rules on a `firewalld`-managed host.** This produces rules that appear to work until the next `firewalld` reload silently reverts them, a genuinely confusing production incident when it happens.
- **Building a firewall ruleset interactively and never persisting it.** The very common "it worked, then a reboot happened and now it doesn't" failure mode, entirely avoidable by confirming the persistence mechanism up front.
- **Relying exclusively on a cloud security group with no host-level firewall at all "because the cloud already handles it."** This discards a legitimate, cheap defense-in-depth layer for no real operational savings, especially given how easy `firewalld`/`ufw`-level configuration is on modern distributions.

## 11. Interview Questions

**🎯 Beginner:** _"What's the relationship between iptables, nftables, and firewalld?"_
**Model answer:** All three ultimately configure the same underlying Linux kernel packet-filtering framework (netfilter). `iptables` is the traditional tool with a table-and-chain rule model. `nftables` is its modern successor, with a unified, more efficient syntax. `firewalld` is a higher-level management daemon that sits on top of either `iptables` or `nftables`, offering a simpler zone-and-service abstraction instead of requiring administrators to write raw rules directly.
_What the interviewer is probing for:_ Whether the candidate understands these as layers of abstraction over one mechanism, rather than three unrelated competing firewalls.

**🎯 Intermediate:** _"You SSH into a server, add an iptables rule to allow a new port, and it works — but after the next scheduled reboot, the rule is gone. What happened, and how do you fix it?"_
**Model answer:** `iptables` rules applied interactively are not persistent by default — they live only in the kernel's current running configuration and are lost on reboot unless explicitly saved. The fix is to persist the ruleset using the distribution's mechanism: `iptables-save` piped into the appropriate persistence file (often managed by an `iptables-persistent`-style package) so the rules are reloaded at boot, or migrating to `firewalld`, which handles `--permanent` changes and reboot persistence automatically without a separate save step.
_What the interviewer is probing for:_ Practical, hands-on awareness of a very common real-world gotcha, not just theoretical knowledge of iptables syntax.

**🎯 Senior:** _"A host is running `firewalld`, but a colleague insists on adding rules with raw `iptables` commands directly because 'it's faster.' What's the risk, and how would you address it?"_
**Model answer:** The risk is that `firewalld` actively manages the underlying `iptables`/`nftables` ruleset and will overwrite or reload it independently of any manually inserted rules — those manual rules can silently disappear on the next `firewalld` reload, service restart, or even certain zone changes, producing an intermittent and confusing security gap or outage that's hard to trace back to its cause since the manual rule "worked" when it was added. I'd address it by having the team standardize on managing that host exclusively through `firewall-cmd` (using rich rules for anything raw `iptables` syntax would otherwise be used for), and treat any raw rule-table edit on a `firewalld`-managed host as something to actively flag in review, similar to how you'd flag someone bypassing a configuration management tool with a manual server edit.
_What the interviewer is probing for:_ Recognition that this specific mixing-of-layers mistake is a real, recurring production risk, and the ability to propose a process fix (standardize on one tool) rather than just a one-off technical fix.

**🎯 Architect:** _"You're standardizing host-level firewalling across a fleet that includes both RHEL-family and Debian-family Linux distributions. What approach do you take, and what trade-offs are you weighing?"_
**Model answer:** I'd avoid trying to force a single tool (`firewalld` everywhere, or raw `nftables` everywhere) across both distribution families, since `firewalld` is the well-integrated native default on RHEL-family systems while Debian-family systems more idiomatically favor direct `nftables`/`iptables` management (often via `ufw` for simpler cases). Instead, I'd standardize at the configuration-management layer: define the desired firewall policy (allowed ports, source ranges, default-deny posture) once in a distribution-agnostic way, and let the configuration management tool translate that into the native mechanism for each distribution family — `firewalld` zones/services on RHEL-family hosts, direct `nftables` rules or `ufw` on Debian-family hosts. The trade-off is added translation complexity in the configuration-management layer versus forcing artificial uniformity that fights each distribution's native tooling and update path, which I'd judge not worth it — native tooling gets better distribution support, security updates, and documentation than a forced cross-distribution standard would.
_What the interviewer is probing for:_ Whether the candidate can reason about standardizing intent/policy versus standardizing implementation mechanism, and recognizes that fighting a distribution's native conventions has real long-term maintenance costs.

## 12. Common Misconceptions

1. **"iptables, nftables, and firewalld are three different firewalls you choose between."** They are three different abstraction layers over the same kernel packet-filtering mechanism — `firewalld` typically calls into `iptables` or `nftables` as its backend rather than replacing it.
2. **"iptables rules persist automatically."** They do not, by default, on most distributions — explicit persistence configuration (or using `firewalld`, which handles this) is required.
3. **"nftables is just a syntax change with no real functional difference from iptables."** `nftables` offers genuine architectural improvements — a single unified framework instead of separate tables per protocol family, and better performance characteristics for large rule sets — beyond just different command syntax.
4. **"It's safe to add manual iptables/nft rules on a firewalld-managed host as long as you're careful."** `firewalld` actively manages and can overwrite the underlying ruleset independently of manual edits; there is no genuinely safe way to permanently mix manual rule management with `firewalld` on the same host.

## 13. 🔑 Key Takeaways

- `iptables`, `nftables`, and `firewalld` all configure the same underlying Linux kernel netfilter framework, at increasingly higher levels of abstraction.
- The stateful filtering concept from [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) becomes concrete here as `-m conntrack`/`ct state` matching, permitting established/related traffic automatically.
- Rule persistence across reboots must be explicitly configured for raw `iptables`/`nftables`; `firewalld` handles this automatically for `--permanent` changes.
- Never mix manual raw-rule editing with `firewalld` management on the same host — pick exactly one management layer per host.
- A host-level firewall remains valuable defense-in-depth even behind a cloud security group ([§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)), guarding against upstream security-group misconfiguration.

## 14. Related Concepts & What's Next

[§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) supplies the stateless/stateful conceptual model this section implements in real syntax. [§83](Section-83-Part10-Firewall-Placement-Perimeter-Host-Based-and-Segmentation-Patterns.md) and [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) cover, respectively, the placement reasoning and the cloud-native security-group/NACL tools that this section's host-level tooling complements as an additional defense-in-depth layer. [§90](Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md) revisits `nftables`/`iptables` briefly when discussing fine-grained, host-level micro-segmentation policy enforcement.

**Next Section:** [§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) — `Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md`
