# Section 52 (Part 7): Network Configuration Tools: ip, nmcli, netplan, /etc/network/interfaces

## 1. The Two-Layer Problem This Section Solves

[§51](./Section-51-Part7-Networking-Fundamentals-Recap.md) recapped IP addressing, TCP/UDP, DNS, and routing as concepts. This section is where those concepts meet the actual commands and files used to configure them on a running Linux host — and it immediately runs into a distinction that trips up a lot of administrators moving between distributions: **runtime configuration** and **persistent configuration** are not the same layer, and several of the tools in this section only operate on one of them.

`ip` operates directly on the kernel's live network state — it's fast, universal, and takes effect immediately, but by itself it changes nothing that survives a reboot. `nmcli`, `netplan`, `/etc/network/interfaces`, and RHEL's `ifcfg-*` files exist specifically to solve the _other_ half of the problem: describing the network configuration a host should have, persistently, so it's reapplied automatically every time networking starts. Understanding which tool belongs to which layer — and, for `netplan` specifically, that it isn't even its own runtime layer at all — is most of what this section is about.

## 2. `ip`: The Modern Universal Tool

`ip`, part of the `iproute2` package, is the direct replacement for the older `ifconfig` (interface configuration) and `route` (routing table management) commands, both of which are deprecated and, on many modern minimal installs, not even present by default (`net-tools`, the package providing them, is often an optional extra). `ip` is universal across distributions — the same syntax works whether the host is Debian-family, RHEL-family, or something else entirely, which is not true of the higher-layer persistent-config tools covered later in this section.

### 2.1 Viewing and Managing Addresses

```bash
ip addr show
ip addr show dev eth0
ip addr add 192.168.1.50/24 dev eth0
ip addr del 192.168.1.50/24 dev eth0
```

`ip addr show` (often abbreviated `ip a`) lists every interface with its assigned IPv4/IPv6 addresses, state, and MAC address — the direct successor to `ifconfig -a`. `ip addr add`/`del` assigns or removes an address from an interface immediately, in CIDR notation rather than the older separate-netmask style.

### 2.2 Bringing Interfaces Up and Down

```bash
ip link set eth0 up
ip link set eth0 down
ip link show
```

`ip link` operates at the link (interface) layer — enabling or disabling an interface, independent of what addresses are or aren't assigned to it. `ip link show` lists interfaces with their link-layer state (`UP`/`DOWN`) and statistics, without the address detail `ip addr show` includes.

### 2.3 Viewing and Managing Routes

```bash
ip route show
ip route add 10.0.0.0/24 via 192.168.1.1 dev eth0
ip route add default via 192.168.1.1
ip route del 10.0.0.0/24
```

`ip route show` (`ip r`) prints the kernel routing table, the direct successor to `route -n`. `ip route add` inserts a route immediately — a specific destination network via a gateway, or `default` for the default route (the traditional "default gateway" concept from [§51](./Section-51-Part7-Networking-Fundamentals-Recap.md)).

> ⚠️ **Warning:** Every `ip` command in this section changes only the kernel's **live, in-memory** network state. None of it is written to any configuration file, and none of it survives a reboot or, in most cases, even a NetworkManager/systemd-networkd restart, which can silently reassert whatever _persistent_ configuration it has on file and overwrite the `ip`-applied change. This is the single most common cause of "I fixed the network, it worked, then it broke again after a reboot (or after the network service restarted)." `ip` is the right tool for immediate troubleshooting, temporary changes, and diagnostics — it is never, by itself, the right tool for a change that needs to survive past the current boot. Everything else in this section exists to make a change persistent.

> 💡 **Tip:** A reliable habit for any `ip`-based change intended to become permanent: apply it live with `ip` first to confirm it actually works and doesn't break connectivity, _then_ encode the same change in whichever persistent-config layer (3–6) the host actually uses. Testing live before committing to a config file avoids a broken persistent config locking a remote host out of SSH reach on its next reboot.

## 3. `nmcli`: NetworkManager's Command-Line Interface

**NetworkManager** is a background service (its full role alongside `systemd-networkd` is covered in [§58](./Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md)) that manages network connections and — critically for this section — persists its configuration itself, so changes made through it survive reboots without any separate step. `nmcli` is NetworkManager's command-line control surface, and it's the default persistent-configuration tool on most desktop-oriented distributions and a large share of RHEL-family server installs (RHEL, CentOS, Rocky, Alma all ship NetworkManager active by default on standard installs).

```bash
nmcli device status
nmcli connection show
nmcli connection add type ethernet ifname eth0 con-name eth0-static \
  ipv4.addresses 192.168.1.50/24 ipv4.gateway 192.168.1.1 ipv4.method manual
nmcli connection up eth0-static
nmcli connection modify eth0-static ipv4.dns "8.8.8.8 8.8.4.4"
nmcli connection down eth0-static
```

`nmcli device status` lists physical/virtual interfaces and which NetworkManager "connection" (a saved configuration profile) is currently active on each. `nmcli connection show` lists the saved profiles themselves — the persistent objects, distinct from the live devices. `nmcli connection add` creates a new persistent profile; `modify` edits an existing one; `up`/`down` activate or deactivate a profile, which is how a `modify`'d profile's changes actually get applied to the live interface.

Under the hood, NetworkManager stores these profiles as keyfiles (commonly under `/etc/NetworkManager/system-connections/`) and reapplies them automatically on boot and on interface events — `nmcli` is a friendly interface over that storage, not a separate mechanism.

> 💡 **Tip:** `nmcli` is deliberately interactive-friendly — `nmcli connection edit <name>` drops into a guided prompt for editing a profile field by field, which is a reasonable choice for one-off interactive changes on a box in front of you, but scripted/automated configuration (Ansible, cloud-init, provisioning pipelines) should prefer the single-line `nmcli connection add`/`modify` invocations shown above, or manage the underlying keyfiles directly, since they're idempotent and diffable in a way an interactive session isn't.

## 4. netplan: Ubuntu's YAML Configuration Layer

**netplan**, Ubuntu's default network configuration system since 17.10/18.04 LTS, is where the "which layer does this tool actually operate at" question matters most, because netplan is frequently misunderstood as a third independent runtime alongside NetworkManager and systemd-networkd. It is not — **netplan is a generator, not a runtime.** It reads declarative YAML files and _renders_ configuration for one of two actual backends: **NetworkManager** or **systemd-networkd** ([§58](./Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md) covers the latter's own native configuration format and role in full). netplan itself does nothing at the point a packet is actually sent — it only produces the config that whichever backend is selected then acts on.

Config files live under `/etc/netplan/*.yaml`:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.1.50/24
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

The `renderer` key is the layering decision made explicit: `networkd` targets systemd-networkd (the common choice on server-oriented Ubuntu installs, especially minimal/cloud images), while `NetworkManager` targets NetworkManager (common on Ubuntu Desktop). Applying a netplan change requires an explicit generation-and-apply step:

```bash
netplan generate   # renders the backend-specific config, without applying
netplan apply       # generates and immediately applies (restarts the relevant backend)
netplan try          # applies temporarily, auto-reverting if not confirmed within a timeout
```

`netplan try` deserves specific attention operationally: it applies the new config immediately but automatically rolls back to the previous working config if the user doesn't explicitly confirm within a short countdown (120 seconds by default) — a direct safeguard against exactly the "pushed a bad network config to a remote host and locked myself out over SSH" failure mode, since a broken config that severs the SSH session reverts on its own rather than requiring physical/console access to fix.

> ⚠️ **Warning:** Editing the rendered backend config directly (a NetworkManager keyfile or a systemd-networkd `.network` file) instead of the netplan YAML is a trap specific to netplan-managed hosts: the next `netplan apply` (including ones triggered automatically by package updates or cloud-init on boot) regenerates the backend config from the YAML source of truth and silently overwrites the manual edit. On a netplan-managed host, `/etc/netplan/*.yaml` is always the file to edit — never the generated backend config underneath it.

## 5. `/etc/network/interfaces`: The Legacy Debian/Ubuntu Approach

Before netplan, Debian-family distributions configured networking through `/etc/network/interfaces`, read by the `ifupdown` package's `ifup`/`ifdown` commands. It's largely superseded by netplan on Ubuntu 18.04 LTS and later, but it remains the live, current mechanism on Debian itself and on older Ubuntu releases (16.04 and earlier) still in service.

```
auto eth0
iface eth0 inet static
    address 192.168.1.50
    netmask 255.255.255.0
    gateway 192.168.1.1
    dns-nameservers 8.8.8.8 8.8.4.4

auto eth1
iface eth1 inet dhcp
```

`auto eth0` marks the interface to be brought up automatically at boot (or via `ifup -a`). `iface eth0 inet static` declares a static IPv4 configuration for `eth0`, followed by indented parameters (`inet dhcp` is the DHCP equivalent, needing no further parameters). Changes take effect via `ifdown eth0 && ifup eth0` or a full networking service restart — there's no separate "apply" step distinct from bringing the interface down and back up, unlike netplan's generate/apply split.

> 💡 **Tip:** A host still running `/etc/network/interfaces` is a useful, fast signal about its age or lineage even before checking the distribution version explicitly — encountering it during a fleet audit is a reasonable cue to check whether the host predates netplan's introduction or is a Debian (rather than Ubuntu) box, either of which carries its own set of upgrade and automation-compatibility considerations worth flagging.

## 6. RHEL-Family Legacy: `/etc/sysconfig/network-scripts/ifcfg-*`

RHEL-family distributions have their own historical equivalent, worth knowing by name even without deep operational depth here: `/etc/sysconfig/network-scripts/ifcfg-eth0`-style files, one per interface, using `KEY=value` shell-variable-style syntax (`IPADDR=192.168.1.50`, `NETMASK=255.255.255.0`, `GATEWAY=192.168.1.1`, `BOOTPROTO=static` or `dhcp`). These predate NetworkManager's dominance on RHEL-family systems and are the direct historical analog to Debian's `/etc/network/interfaces` — a flat-file, per-interface, non-YAML configuration format. On current RHEL/CentOS/Rocky/Alma releases, NetworkManager is the default and `nmcli`/its keyfiles are the primary supported path (3); `ifcfg-*` files are still read by NetworkManager for backward compatibility on many releases, but new configuration work on a modern RHEL-family host should go through `nmcli` rather than hand-editing `ifcfg-*` directly.

## 7. Which Tool Applies Where

| Distro / Version                               | Primary persistent tool        | Notes                                                                                |
| ---------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------ |
| Ubuntu 18.04 LTS and later                     | netplan (4)                    | Renders to systemd-networkd (server/cloud) or NetworkManager (desktop)               |
| Ubuntu 16.04 and earlier                       | `/etc/network/interfaces` (5)  | Pre-netplan Ubuntu                                                                   |
| Debian (any current release)                   | `/etc/network/interfaces` (5)  | netplan is available but not Debian's default                                        |
| RHEL / CentOS / Rocky / Alma (current)         | NetworkManager via `nmcli` (3) | `ifcfg-*` (6) still read for compatibility, not the preferred authoring path         |
| Any distro, any version, immediate/manual work | `ip` (2)                       | Universal, but non-persistent — always pair with the distro's actual persistent tool |

`ip` sits outside this table entirely because it applies everywhere regardless of distro — it's the layer beneath all of the persistent tools, not a competitor to them.

## 8. Common Misconceptions

1. **"`ip addr add` permanently configures the interface."** It changes only the kernel's live state — nothing is written to disk, and the change is lost on reboot or when the active persistence tool (NetworkManager, systemd-networkd, ifupdown) reasserts its own stored configuration (2). Persistence always requires a separate step through whichever tool the distro actually uses.
2. **"netplan is a network configuration daemon, running alongside NetworkManager and systemd-networkd."** It generates configuration for one of those two as a backend and then gets out of the way — it has no runtime component actively managing packets itself (4). Confusing it for a third independent backend is the most common netplan misunderstanding.
3. **"Editing the NetworkManager keyfile or systemd-networkd `.network` file directly is equivalent to editing the netplan YAML."** On a netplan-managed host it's actively dangerous — the next `netplan apply` regenerates and overwrites the backend file from the YAML, silently discarding the direct edit (4).
4. **"`/etc/network/interfaces` and netplan are just two syntaxes for the same underlying mechanism."** They're architecturally different — `ifupdown` is itself the thing that brings interfaces up and down in response to the file, with no generator step, while netplan explicitly generates config for a separate backend service (4, 5).
5. **"Every RHEL-family host still uses `ifcfg-*` files as the primary config method."** Current RHEL-family releases default to NetworkManager, with `nmcli`/keyfiles as the supported path; `ifcfg-*` persists mainly for backward compatibility, not as the recommended way to configure a modern host (6).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"Why did `ip addr add 192.168.1.50/24 dev eth0` disappear after the server rebooted?"_
**Model answer:** `ip` only changes the kernel's live, in-memory network state — it doesn't write anything to a configuration file. On reboot, networking starts up again driven by whatever persistent configuration tool the distro actually uses (NetworkManager, netplan, `/etc/network/interfaces`, or `ifcfg-*` files), and that stored configuration doesn't include the manually added address, so it's simply not reapplied. To make the address survive a reboot, the same configuration needs to be added through the distro's actual persistent tool, not just via `ip`.
_What the interviewer is probing for:_ Understanding the runtime-vs-persistent distinction as a structural fact about `ip`, not a quirk to memorize.

**🎯 Intermediate:** _"Explain what netplan actually is, architecturally — is it a network manager?"_
**Model answer:** No — netplan is a YAML configuration generator, not a runtime network manager. It reads declarative YAML under `/etc/netplan/` and, on `netplan apply`, renders that into configuration for one of two real backends specified by the `renderer` key: NetworkManager or systemd-networkd. Whichever backend is selected is the thing actually managing interfaces and applying configuration at runtime; netplan's job ends once it's generated and handed off the backend-specific config. That's why editing the generated backend file directly is a trap — the next `netplan apply` regenerates it from the YAML and overwrites the manual change.
_What the interviewer is probing for:_ Correctly placing netplan as a generator layer above NetworkManager/systemd-networkd, not a third independent competitor to them.

**🎯 Senior:** _"You're auditing a mixed fleet of Ubuntu 16.04, Ubuntu 20.04, Debian 11, and RHEL 8 hosts and need to write a single automation script that reliably sets a static IP persistently on any of them. What does that script need to account for?"_
**Model answer:** There's no single command that works everywhere, so the script needs to branch on which persistent configuration mechanism is actually in play, since distro name alone isn't fully sufficient (Ubuntu itself splits pre/post-netplan). I'd detect this concretely rather than assuming from a version string — check for `/etc/netplan/*.yaml` existing and netplan being installed (Ubuntu 18.04+), fall back to checking whether NetworkManager is active via `nmcli` or `systemctl status NetworkManager` (RHEL-family and Ubuntu Desktop), and fall back further to `/etc/network/interfaces` with `ifupdown` (Debian, old Ubuntu). For the netplan branch, I'd also need to know or detect the configured renderer, since the YAML syntax is the same either way but understanding which backend actually applies it matters for troubleshooting if the apply doesn't take effect. In every branch, I'd validate the change with `ip addr show`/`ip route show` (2) after applying, since that's the one universal, tool-independent way to confirm the live state actually matches what was intended — persistent config that doesn't correctly apply is worse than no config, because it looks handled in an inventory check while the host is actually misconfigured.
_What the interviewer is probing for:_ Recognizing that fleet-wide network automation must branch on the actual detected mechanism rather than assuming from distro/version alone, and using `ip` as the tool-agnostic verification layer regardless of which persistence tool did the configuring.

**🎯 Architect:** _"A team wants to standardize network configuration tooling across a fleet that's currently a mix of netplan, plain NetworkManager, and legacy `/etc/network/interfaces` hosts. How do you approach this?"_
**Model answer:** I'd resist the instinct to force one tool everywhere immediately, because the right tool is largely dictated by the distro/version each host is actually running, and fighting that (e.g., installing netplan on RHEL, or forcing NetworkManager onto an ifupdown-only Debian box) adds fragility without a proportional benefit. Instead I'd standardize the _interface_ the automation tooling (Ansible, etc.) presents to operators — a single declarative "desired network state" input — and let the automation layer translate that into whichever backend-specific format the target host actually needs: netplan YAML, `nmcli` invocations or keyfiles, or `/etc/network/interfaces` stanzas, selected by detecting the host's actual mechanism the way described in the prior answer. I'd also push the fleet toward consolidating on fewer distro/version combinations over time as a separate initiative, since that reduces the number of branches this tooling needs to support, but I wouldn't block the immediate automation need on that longer migration. Finally, I'd bake in the `ip`-based verification step (2) as a universal post-apply check regardless of which backend applied the config, since that's the one constant across every branch.
_What the interviewer is probing for:_ Pragmatic, layered thinking — building a distro-agnostic interface on top of genuinely distro-specific backends rather than forcing premature tooling uniformity, plus recognizing `ip` as the universal verification layer.

## 10. Key Takeaways

- `ip` (`ip addr`, `ip link`, `ip route`) is the universal, modern replacement for `ifconfig`/`route`, but every change it makes is live/in-memory only and does not survive a reboot unless separately persisted (2).
- `nmcli` is NetworkManager's CLI and persists its own configuration as keyfiles — the primary tool on desktop-oriented distros and current RHEL-family server installs (3).
- netplan is a YAML _generator_, not a runtime network manager — it renders config for either NetworkManager or systemd-networkd as the actual backend, selected via the `renderer` key, and editing the generated backend file directly gets silently overwritten on the next `netplan apply` (4).
- `/etc/network/interfaces` (via `ifupdown`) is the legacy Debian/Ubuntu mechanism, still current on Debian and pre-18.04 Ubuntu but superseded by netplan on modern Ubuntu (5).
- RHEL-family's own legacy format is `/etc/sysconfig/network-scripts/ifcfg-*`, still read for compatibility but no longer the preferred authoring path now that NetworkManager/`nmcli` is default (6).
- Which tool to use is a function of distro and version, not a free choice — 7's table is the fast lookup, and fleet automation needs to detect the actual mechanism in play rather than assume it from the distro label alone.

## 11. Related Concepts & What's Next

This section builds directly on [§51](./Section-51-Part7-Networking-Fundamentals-Recap.md)'s addressing/routing/DNS fundamentals, applying those concepts through actual commands and config files. The tools here — particularly `nmcli` and netplan's backends — are largely front ends to services covered in full architectural depth in [§58](./Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md) (Network Services on Linux: systemd-networkd and NetworkManager), which is the natural next stop for anyone who wants the service-layer picture underneath what this section covered operationally. [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) (Firewalls) picks up the adjacent concern of controlling _which_ traffic is allowed once addressing and routing are correctly configured, and [§53](./Section-53-Part7-DNS-Resolution-Resolv-Conf-Hosts-Nsswitch.md) (next) covers DNS resolution specifically — `/etc/resolv.conf`, `/etc/hosts`, and `nsswitch.conf` — which several of this section's tools (`nmcli`, netplan) also touch when they manage nameserver configuration.

**Next Section:** [§53](./Section-53-Part7-DNS-Resolution-Resolv-Conf-Hosts-Nsswitch.md) — `Section-53-Part7-DNS-Resolution-On-Linux.md`
