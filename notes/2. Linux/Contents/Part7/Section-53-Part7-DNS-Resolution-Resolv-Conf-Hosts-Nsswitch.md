# Section 53 (Part 7): DNS Resolution on Linux: /etc/resolv.conf, /etc/hosts, nsswitch.conf

## 1. Why Resolution Is Configuration, Not Just DNS

[§51](./Section-51-Part7-Networking-Fundamentals-Recap.md) introduced DNS conceptually — names, records, the resolution hierarchy. [§52](./Section-52-Part7-Network-Configuration-Tools.md) covered the tools (`ip`, `nmcli`, `netplan`) that configure interfaces and, often, feed DNS settings into the system as a side effect of configuring an interface. This section is the piece in between: **how a Linux host actually decides what a hostname resolves to**, which is not a single DNS query but a small pipeline of configuration files, each with its own job, that a program's C library consults before a DNS packet is ever sent.

That pipeline matters operationally because "hostname doesn't resolve" is one of the most common production symptoms, and it has at least four genuinely different root causes hiding behind one error message: a stale `/etc/hosts` entry, a misordered `nsswitch.conf`, a broken or overwritten `resolv.conf`, or an actual DNS server problem. Diagnosing it correctly means knowing which file governs which step — guessing wastes time on a fleet where minutes matter.

## 2. `/etc/hosts`: The Simplest, First-Checked Static Mapping

`/etc/hosts` is a flat text file mapping hostnames directly to IP addresses, with no DNS query involved at all. It predates DNS as a concept — early Unix networks distributed a single shared hosts file to every machine — and it survives today as a fast, local override mechanism rather than a scaling solution.

**Format:**

```text
127.0.0.1   localhost
::1         localhost ip6-localhost ip6-loopback
10.0.1.15   db-primary.internal db-primary
192.168.1.50 app01
```

Each line is `IP  canonical-hostname  [aliases...]`. Lines starting with `#` are comments. Whitespace-separated columns, one entry per line.

**Common operational uses:**

- **Local overrides.** Forcing a specific hostname to resolve to a specific IP on one machine only — bypassing DNS entirely for that name — useful for pointing a hostname at a local or alternate backend without touching shared DNS infrastructure.
- **Testing before DNS propagation.** When cutting over a service to new infrastructure, adding an entry to `/etc/hosts` on a test client lets you validate the new endpoint (TLS certs, application behavior) against the real hostname before the DNS record is actually changed or before a slow-propagating change has finished rolling out.
- **Bootstrapping and air-gapped environments.** Systems with no DNS resolver reachable at all (isolated networks, early boot before networking is fully up) can still resolve a fixed, known set of names via `/etc/hosts`.
- **Loopback and container-internal names.** `localhost` and container-injected hostname entries are conventionally delivered via `/etc/hosts` rather than DNS.

> 💡 **Tip:** `/etc/hosts` entries are checked in file order, and the **first** match wins — if a hostname appears twice with different IPs, the second line is silently ignored, not merged or treated as an error. This is a real source of confusion when a hastily-appended troubleshooting entry lingers at the bottom of the file below an older, stale one.

## 3. `/etc/resolv.conf`: `nameserver`, `search`, `options`

`/etc/resolv.conf` is the traditional configuration file for the DNS resolver itself — which server(s) to query, and how to interpret partial hostnames.

**Format and directives:**

```text
nameserver 10.0.0.2
nameserver 8.8.8.8
search prod.internal example.com
options timeout:2 attempts:3
```

| Directive    | Meaning                                                                                                                                                                                             |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nameserver` | IP address of a DNS server to query. Multiple lines are tried in order (traditionally up to three are honored) — a fallback list, not a load-balanced pool.                                         |
| `search`     | A list of domain suffixes to try, in order, when a query is a bare, unqualified name (e.g. `db-primary` rather than `db-primary.prod.internal`).                                                    |
| `options`    | Tunables such as `timeout` (seconds per query before retry), `attempts` (retry count), `ndots` (how many dots a name needs before it's tried as fully-qualified first rather than suffix-expanded). |

**Worked example:** with `search prod.internal example.com` set, a lookup of the bare name `db-primary` first tries `db-primary.prod.internal`, then `db-primary.example.com`, before (depending on `ndots`) trying `db-primary` as a fully-qualified name on its own. This is why an application config that "just works" with a short hostname in one environment can fail to resolve in another where the `search` list differs — the short name was never fully qualified, it was relying on suffix expansion.

> ⚠️ **Warning: `/etc/resolv.conf` is frequently not meant to be hand-edited anymore.** On most modern distributions, `/etc/resolv.conf` is auto-generated and actively managed by `systemd-resolved` or NetworkManager, not a static file an administrator maintains directly. Manually editing it in place often "works" immediately — then gets **silently overwritten** the next time NetworkManager reconnects, DHCP renews a lease, or `systemd-resolved` regenerates its output, with no error or warning that the edit was reverted. This is one of the single most common points of confusion in Linux DNS troubleshooting: an admin makes a change, confirms it works, walks away, and finds it reverted hours or days later with no obvious cause. Check whether `/etc/resolv.conf` is a symlink (commonly to `/run/systemd/resolve/stub-resolv.conf` or similar under `systemd-resolved`) before editing it directly — a symlink is a strong signal that the real, persistent configuration point is elsewhere (5), and that editing the target of the symlink, or the owning service's own configuration, is the durable fix.

**Checking whether `resolv.conf` is managed:**

```bash
ls -l /etc/resolv.conf
```

A regular file suggests it may be static (or managed by a tool that rewrites it in place, like some `dhclient` hooks). A symlink pointing into `/run/systemd/resolve/` is the clearest sign `systemd-resolved` owns it (5).

## 4. `/etc/nsswitch.conf`: Controlling Lookup Order

`/etc/nsswitch.conf` (Name Service Switch) is broader than DNS specifically — it governs where the C library looks up several categories of system information (users, groups, hosts, and more), each on its own line, each with its own ordered list of sources.

The line that matters for this section is `hosts:`:

```text
hosts:      files dns
```

This says: for a hostname lookup, check the source named `files` first — meaning `/etc/hosts` — and only fall through to `dns` if `files` has no match. **This one line is what actually enforces the "check `/etc/hosts` before DNS" behavior** described in 2 and 5 — it isn't an inherent property of how Linux resolution works, it's a configured order that this file controls and that could, in principle, be changed.

Other sources can appear here too, most commonly `myhostname` (resolves the machine's own configured hostname) and `mdns4_minimal`/`resolve` (multicast DNS or a handoff to `systemd-resolved`'s own NSS module, seen on distributions where `systemd-resolved` fully owns the lookup path rather than just managing `resolv.conf`):

```text
hosts:      files mdns4_minimal [NOTFOUND=return] resolve [!UNAVAIL=return] dns
```

> 💡 **Tip:** The `[NOTFOUND=return]` and `[!UNAVAIL=return]` bracketed qualifiers are lookup-control actions, not comments — they tell the resolver to stop the chain under specific result conditions rather than always falling through to the next source. Reading an unfamiliar `nsswitch.conf hosts:` line means reading these qualifiers, not just the bare source names, to know the real precedence.

**Why this file is worth checking explicitly during troubleshooting:** it's easy to assume `/etc/hosts` always takes priority over DNS, edit `/etc/hosts`, and be confused when nothing changes — because on a misconfigured or unusual host, `hosts:` might list `dns` before `files`, or omit `files` entirely. Confirming the actual order in `nsswitch.conf` removes that assumption from the debugging process.

## 5. `systemd-resolved`: The Modern Default Layer

On many current distributions (notably Ubuntu since 18.04 and other systemd-based distributions), DNS resolution is handled by **`systemd-resolved`**, a system service that sits between applications and the actual upstream DNS servers, rather than applications reading `/etc/resolv.conf` and querying nameservers directly.

Under this model:

- `/etc/resolv.conf` is typically a **symlink** to `/run/systemd/resolve/stub-resolv.conf`, which points resolution at a local stub listener (`127.0.0.53`) run by `systemd-resolved` itself — not at the real upstream nameservers directly.
- `systemd-resolved` maintains **per-interface** DNS configuration (relevant on hosts with multiple interfaces or VPN connections, where different interfaces legitimately need different DNS servers or search domains) and merges/selects between them, a capability plain `resolv.conf` was never designed to express.
- It provides caching, so repeated lookups for the same name don't necessarily hit the upstream server every time.

**Key commands:**

```bash
resolvectl status
```

Shows the current DNS configuration per interface — which nameservers, search domains, and the current default protocol/DNSSEC settings actually being used, which is the ground truth when `/etc/resolv.conf` alone doesn't tell the full story (e.g., it just shows the stub address, not the real upstream servers behind it).

```bash
resolvectl query db-primary.prod.internal
```

Performs a resolution through `systemd-resolved` directly and reports which interface and protocol answered it — useful for confirming resolution works at this layer specifically, isolating it from anything an individual application might be doing differently.

> ⚠️ **Warning:** On a `systemd-resolved`-managed host, editing `/etc/resolv.conf` directly edits (at best) a symlink target that gets regenerated, or a file that's simply not consulted the way it appears to be — the durable fix for changing DNS servers or search domains is through NetworkManager/netplan configuration ([§52](./Section-52-Part7-Network-Configuration-Tools.md)) or `systemd-resolved`'s own configuration (`/etc/systemd/resolved.conf`, or per-link settings), not the resolv.conf file itself. Treat any direct `resolv.conf` edit on such a host as temporary at best, and confirm persistence with `resolvectl status` after the next network reconnect rather than assuming the edit stuck.

## 6. Troubleshooting Flow: "This Hostname Doesn't Resolve"

Tying 2 through 5 together into an ordered diagnostic sequence:

1. **Check `/etc/hosts` first.** Is there a stale or conflicting static entry for this name? Remember only the first match on a duplicated name wins (2).
2. **Check `/etc/nsswitch.conf`'s `hosts:` line.** Confirm the actual lookup order — don't assume `files` comes before `dns` (or that `dns` is even consulted at all) without reading the line (4).
3. **Check `/etc/resolv.conf` and, if present, `resolvectl status`.** Is `resolv.conf` a symlink into `systemd-resolved`'s runtime directory? If so, trust `resolvectl status` over the raw file contents for what's actually being queried, and check whether a recent manual edit was silently reverted (3, 5).
4. **Test resolution directly with `dig`.** Once the configuration chain is confirmed, `dig hostname` (and `dig hostname @specific-nameserver` to bypass local configuration and test a specific upstream server directly) isolates whether the problem is genuinely in the DNS server's answer versus something in the local resolution pipeline covered in this section. Full `dig`/`nslookup` usage, output interpretation, and the broader network-diagnostics toolkit are [§55](./Section-55-Part7-Network-Diagnostics.md)'s territory, not this section's — this section's job ends at "which local file or service is responsible."

This ordering matters because each step rules out an entire category of cause before moving to the next, rather than jumping straight to "the DNS server must be broken" — which, in practice, is often the least likely of the four layers to actually be at fault on a host with a long uptime and a recently-changed configuration.

## 7. Common Misconceptions

1. **"Editing `/etc/resolv.conf` is the standard way to change DNS servers."** On a `systemd-resolved`- or NetworkManager-managed host, this is often a temporary, silently-reverted change rather than a persistent fix (3, 5) — the durable path is through the managing service's own configuration.
2. **"`/etc/hosts` always takes priority over DNS."** This is a configured behavior enforced by `nsswitch.conf`'s `hosts:` line ordering, not an inherent property of Linux — it can be, and occasionally is, configured differently (4).
3. **"If `dig` resolves a name correctly, an application on the same host will too."** `dig` by default can bypass some of the local resolution pipeline (depending on how it's invoked) and talks to a nameserver relatively directly, while applications go through the full NSS chain (`/etc/hosts`, `nsswitch.conf` ordering, and whatever `resolv.conf`/`systemd-resolved` actually configures) — a working `dig` result narrows the problem but doesn't fully rule out an application-visible resolution issue.
4. **"`resolv.conf`'s `search` domains only matter for typos or convenience."** They actively change what a bare hostname resolves to, and a mismatched `search` list between environments is a real, recurring cause of "works in staging, fails in production" bugs when application configuration uses short, unqualified hostnames (3).

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `/etc/hosts` and `/etc/resolv.conf`?"_
**Model answer:** `/etc/hosts` is a static, local file mapping specific hostnames directly to IP addresses with no DNS query involved — a hardcoded override. `/etc/resolv.conf` configures the DNS _resolver_ itself — which nameserver(s) to query and what search domains to try for unqualified names — for lookups that aren't satisfied by `/etc/hosts` or any other higher-priority source. They serve different steps in the same overall resolution process, not the same purpose with different syntax.
_What the interviewer is probing for:_ Basic separation of "static override" from "resolver configuration" rather than treating both as interchangeable "DNS files."

**🎯 Intermediate:** _"You edited `/etc/resolv.conf` to add a nameserver, confirmed it worked, and a day later it's gone. What happened and how do you fix it properly?"_
**Model answer:** On most modern distributions, `/etc/resolv.conf` isn't meant to be hand-edited — it's auto-generated and managed by `systemd-resolved` or NetworkManager, and it gets regenerated (silently overwriting a manual edit) on events like a DHCP lease renewal or a NetworkManager reconnect. I'd check `ls -l /etc/resolv.conf` first — if it's a symlink into `/run/systemd/resolve/`, that confirms `systemd-resolved` owns it. The durable fix is to set the nameserver through the actual managing layer — NetworkManager's per-connection DNS settings or `systemd-resolved`'s own configuration — not by re-editing the generated file, which would just get overwritten again.
_What the interviewer is probing for:_ Awareness of the auto-management trap specifically, not just "DNS config file editing" in the abstract — and knowing the actual durable fix, not just diagnosing the symptom.

**🎯 Senior:** _"A hostname resolves correctly with `dig` but a running application on the same host still fails to connect to it. Walk through your diagnosis."_
**Model answer:** I wouldn't assume `dig` succeeding rules out a local resolution problem — depending on how it was invoked, `dig` can talk close to directly to a nameserver, while the application goes through the full NSS chain: `/etc/hosts` first (checking `nsswitch.conf`'s configured order), then whatever `resolv.conf`/`systemd-resolved` provides. I'd check for a stale, conflicting `/etc/hosts` entry that the application's libc-based lookup would hit but a differently-invoked `dig` might not. I'd also check whether the application runs in a container or otherwise has its own `/etc/hosts` and `resolv.conf` visible to it, separate from the host's — a very common source of exactly this kind of split-brain symptom, where the host resolves fine but the process's mount namespace sees different configuration files entirely. Only after ruling out the local pipeline would I treat this as an application-level connection issue unrelated to name resolution at all.
_What the interviewer is probing for:_ Not taking a single successful `dig` as proof the whole resolution pipeline is fine, and awareness that containers/namespaces can present entirely separate copies of these configuration files (a preview of container-networking concerns covered more fully later in the toolkit).

**🎯 Architect:** _"You're designing DNS resolution behavior for a mixed fleet — some hosts still using static `resolv.conf`, others on `systemd-resolved`, some running containers with their own resolution stack. What do you standardize on and why?"_
**Model answer:** I'd push toward `systemd-resolved` as the standard where the distribution supports it, specifically because it handles per-interface DNS cleanly — a real requirement on hosts with VPNs or multiple network segments that static `resolv.conf` was never designed to express, and it centralizes caching and query logic in one auditable service rather than leaving every application to interact with `resolv.conf` inconsistently. For legacy hosts still on static `resolv.conf`, I'd document that explicitly rather than let it be discovered by accident during an incident, and I'd standardize the `nsswitch.conf` `hosts:` ordering across the fleet so `files`-before-`dns` behavior is consistent and predictable everywhere, since inconsistent ordering across a fleet is a subtle source of "works on one host, not another" bugs. For containers, I'd treat their resolution stack as a genuinely separate configuration surface — often injected by the container runtime or orchestrator rather than inherited from the host — and make sure runbooks distinguish "check the host's resolution chain" from "check the container's," since conflating them wastes time during an actual DNS-related incident. The overarching principle is minimizing the number of distinct resolution behaviors an on-call engineer has to hold in their head across the fleet.
_What the interviewer is probing for:_ Fleet-level standardization thinking, correctly identifying `systemd-resolved`'s actual advantage (per-interface DNS) rather than adopting it for vague "it's newer" reasons, and recognizing containers as a distinct resolution surface.

## 9. Key Takeaways

- `/etc/hosts` is a static, DNS-free hostname-to-IP override, checked first when `nsswitch.conf` says so — first match on a duplicated name wins, later duplicates are silently ignored (2).
- `/etc/resolv.conf`'s `nameserver`, `search`, and `options` directives configure the resolver, but on most modern distributions the file is auto-generated by `systemd-resolved` or NetworkManager and hand-edits are frequently, silently overwritten (3) — check for a symlink before editing.
- `/etc/nsswitch.conf`'s `hosts:` line is what actually enforces lookup order (commonly `files dns`) — it's a configured precedence, not an inherent Linux behavior, and worth reading explicitly rather than assumed (4).
- `systemd-resolved` is the modern default resolution layer on many distributions — `resolvectl status` and `resolvectl query` show the real, currently-active configuration and are more trustworthy than reading `resolv.conf` alone when it's a stub symlink (5).
- Troubleshooting "hostname doesn't resolve" is a four-step ordered check — `/etc/hosts` → `nsswitch.conf` order → `resolv.conf`/`resolvectl status` → direct `dig` test — not a single-file guess (6).

## 10. Related Concepts & What's Next

This section builds on [§51](./Section-51-Part7-Networking-Fundamentals-Recap.md)'s conceptual DNS introduction and [§52](./Section-52-Part7-Network-Configuration-Tools.md)'s network configuration tools, which often set these same DNS values as a side effect of interface configuration. [§55](./Section-55-Part7-Network-Diagnostics.md), next, covers `dig` and the broader network-diagnostics toolkit — the hands-on tools that make the last step of this section's troubleshooting flow (6) concrete rather than just named. [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) (before that) covers firewalls, a different but related "why can't this host reach that service" investigative surface.

**Next Section:** [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) — `Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md`
