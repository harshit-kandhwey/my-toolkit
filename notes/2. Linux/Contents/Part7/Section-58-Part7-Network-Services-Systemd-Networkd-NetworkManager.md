# Section 58 (Part 7): Network Services on Linux (systemd-networkd, NetworkManager)

## 1. Overview: The Layer Underneath [§52](./Section-52-Part7-Network-Configuration-Tools.md)'s Tools

[§52](./Section-52-Part7-Network-Configuration-Tools.md) covered `ip`, `nmcli`, `netplan`, and `/etc/network/interfaces` — the commands and config files an administrator actually touches to bring up an interface, assign an address, or set a route. What [§52](./Section-52-Part7-Network-Configuration-Tools.md) deliberately left unresolved is what actually _executes_ that configuration and keeps it applied in the background: a running daemon, managed like any other systemd-supervised service, that owns the interfaces on the box for as long as the system is up. This section closes that gap.

Two daemons dominate this space on modern Linux: **NetworkManager** and **systemd-networkd**. Both do fundamentally the same job — bring interfaces up, assign addresses (statically or via DHCP), install routes, and react to link state changes (a cable unplugged, a Wi-Fi network appearing) — but they come from different design philosophies and different eras, and a given distribution's choice between them is rarely arbitrary.

> 💡 **Tip:** The mental model worth keeping throughout this section: `nmcli`/`nmtui`/netplan are frontends ([§52](./Section-52-Part7-Network-Configuration-Tools.md)); NetworkManager and systemd-networkd are the backends actually doing the work underneath. Netplan in particular is _only_ a translation layer — it generates configuration for whichever of the two backends it's told to target, and has no enforcement capability of its own (5).

## 2. NetworkManager: The Dominant, Broad-Scope Option

**NetworkManager** is the default network management daemon on essentially every major desktop-oriented distribution (Fedora, Ubuntu Desktop, most others) and, increasingly, on many server distributions and server images of the same families too — its footprint isn't limited to desktops.

Its defining characteristic is **scope**: NetworkManager manages wired Ethernet, Wi-Fi, VPN connections, mobile broadband, and bridged/bonded/VLAN interfaces all under one daemon and one connection-profile model, rather than treating Wi-Fi or VPN as a separate concern bolted on afterward. Every managed interface is represented as a **connection profile** — a named, persisted set of settings (addressing mode, DNS, routes, Wi-Fi credentials, and so on) that can be activated on a matching device.

**Architecture:**

- NetworkManager runs as a long-lived daemon (`NetworkManager.service`, itself a systemd unit — [§13](../Part2/Section-13-Part2-Init-Systems.md)'s conceptual systemd introduction and full depth in [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md) apply directly here) exposing its state and control surface over **D-Bus**, the same IPC mechanism much of the rest of the modern Linux desktop/server stack uses for inter-process communication.
- `nmcli` (scriptable CLI) and `nmtui` (a text-mode interactive UI) are both just D-Bus clients talking to that daemon — neither holds any state itself; killing and restarting NetworkManager, not `nmcli`, is what actually changes network state.
- Connection profiles persist under `/etc/NetworkManager/system-connections/`, one file per profile, applied automatically at boot and re-applied on events like a cable being plugged back in.

```bash
nmcli connection show                 # list known connection profiles
nmcli device status                   # per-interface: device, type, state, connection
nmcli connection up "Wired connection 1"
```

**Why NetworkManager over the alternative in practice:** anywhere Wi-Fi, VPN, or mobile broadband matter, NetworkManager is close to a forced choice — systemd-networkd has no native concept of Wi-Fi association or VPN negotiation on its own. On servers with none of that (a data-center box with two wired NICs and nothing else), the case for NetworkManager's broader scope is weaker, which is exactly where systemd-networkd's lighter footprint becomes attractive instead (3, 4).

## 3. systemd-networkd: The Lightweight, Server-Oriented Option

**systemd-networkd** is systemd's own network management daemon — bundled with systemd itself rather than a separate project, and deliberately narrower in scope than NetworkManager. It handles wired interfaces, VLANs, bridges, bonds, and basic DHCP client/server behavior well, but has no built-in Wi-Fi or VPN handling of its own (Wi-Fi association, where used alongside networkd, is typically handled by the separate `wpa_supplicant` or `iwd` rather than networkd itself).

Its configuration model is **declarative unit-style files** — the same philosophy [§13](../Part2/Section-13-Part2-Init-Systems.md) introduced for systemd services generally, applied here to network configuration instead of process supervision:

| File type  | Purpose                                                                                                                                                            |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.link`    | Matches physical devices by MAC address, driver, or other hardware properties; sets low-level device properties (naming, MTU) before the device is even brought up |
| `.network` | Matches interfaces (by name or the properties `.link` exposes) and assigns addressing — static IP, DHCP, DNS, routes                                               |
| `.netdev`  | Defines virtual devices — bridges, bonds, VLANs, tunnels — that don't correspond to physical hardware                                                              |

A minimal `.network` file enabling DHCP on a wired interface:

```ini
# /etc/systemd/network/20-wired.network
[Match]
Name=eth0

[Network]
DHCP=yes
```

```bash
systemctl status systemd-networkd
networkctl list                       # interfaces networkd knows about, and their state
networkctl status eth0                # detailed per-interface state
```

`networkctl` is networkd's equivalent of `nmcli device status` — a purpose-built inspection tool rather than raw `ip`/`nft`-style output, though `ip addr`/`ip route` remain valid ground-truth checks regardless of which daemon is managing the interface, since both ultimately configure the same kernel networking state.

**Why systemd-networkd fits minimal/server/container-oriented distributions well:** it ships with systemd already (no separate daemon to install on a systemd-based system), has a materially smaller resource footprint than NetworkManager's broader D-Bus-based stack, and its declarative `.network`/`.netdev` files fit naturally alongside the rest of a systemd-managed host's configuration style — which is exactly the profile of a minimal server image, a container base layer, or an embedded/appliance-style install that has no Wi-Fi or VPN requirement to justify NetworkManager's extra scope.

## 4. Why a Given Distro Defaults to One or the Other

There's no universal rule, but the practical pattern holds across most mainstream distributions:

- **Desktop-oriented installs** (a workstation, a laptop, anything expected to join Wi-Fi networks or dial a VPN) default to **NetworkManager** almost without exception — the broader scope isn't optional there, it's the actual requirement.
- **Minimal server images and container base images** vary by distribution and version — some ship **systemd-networkd** by default precisely because it's lighter and already present with systemd, others ship **NetworkManager** even on server installs for consistency with the desktop variant of the same distribution family. This has shifted over time as distributions have revised their defaults, so treat "which one does distro X default to" as something to verify directly on the actual host or image in front of you (6) rather than something to memorize as a fixed fact.
- **Neither** is guaranteed present at all on a genuinely minimal or container image — a container commonly has no network management daemon running inside it whatsoever, because its networking is configured externally by the container runtime/orchestrator rather than by an in-container daemon reacting to link events.

> ⚠️ **Verify current source:** Exact per-distribution, per-release defaults for server images specifically are worth confirming against current release notes if a specific decision depends on it — this section covers the architectural pattern (desktop leans NetworkManager, minimal/server leans either way depending on distro and era), not a frozen table of defaults that would go stale.

## 5. Netplan's Role: A Frontend Choosing a Backend

[§52](./Section-52-Part7-Network-Configuration-Tools.md) introduced netplan as Ubuntu's YAML-based network configuration frontend. The detail worth landing here, now that both backends have been covered: netplan itself **manages neither interface**. It reads a declarative YAML file and generates the actual configuration for whichever backend it's told to target — its `renderer` setting is literally the choice between `networkd` and `NetworkManager`:

```yaml
network:
  version: 2
  renderer: networkd # or: NetworkManager
  ethernets:
    eth0:
      dhcp4: true
```

`netplan apply` translates that YAML into `.network`/`.netdev` files under `/run/systemd/network/` (when targeting networkd) or into a NetworkManager connection profile (when targeting NetworkManager), then tells the corresponding backend daemon to reload. This is why "is this host using networkd or NetworkManager" and "is this host using netplan" are answers to two different, layered questions — a host can run netplan as the authoring interface while either daemon underneath actually enforces the result, exactly parallel to how firewalld and ufw ([§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)) author rules that nftables/iptables actually enforce.

## 6. The Real Operational Rule: Never Run Both on the Same Interfaces

Both daemons are capable of managing the same physical interface, and both will happily try to if both are installed, enabled, and unconfigured to stay out of each other's way. The result is not graceful coexistence — it's a **conflict**: both daemons independently attempt to bring the interface up, assign addresses, and install routes, and depending on timing and configuration, that manifests as an interface that flaps between two different addresses, DHCP leases fighting each other, routes being installed and then silently retracted, or one daemon's configuration appearing to have no effect at all because the other daemon reasserted its own state moments later.

> ⚠️ **Warning:** Having both `NetworkManager` and `systemd-networkd` active and managing the same interface at the same time is a real, commonly hit misconfiguration — not a hypothetical edge case. It typically happens after a distribution upgrade or migration that changed the default backend without fully disabling the old one, or after manually installing one daemon on a host that already had the other running from the base image. The fix is not clever coexistence configuration — it's picking exactly one daemon per interface (commonly one daemon for the whole host) and disabling the other outright (`systemctl disable --now`), or, where genuinely necessary, explicitly telling each daemon which interfaces it's allowed to touch and excluding it from the rest — NetworkManager's `unmanaged-devices` setting and networkd's own device-matching in `.network` files can both express "leave this interface alone," but the safer default for most hosts is one daemon owning networking entirely.

The check that resolves "which one is actually active on this box right now" before touching anything:

```bash
systemctl status NetworkManager systemd-networkd
```

Both reporting `active (running)` simultaneously against the same set of interfaces is the state to treat as a finding, not a curiosity — it means the host's actual network configuration is whatever the two daemons' independent, uncoordinated behavior happens to produce at any given moment, which is not a state to build further automation on top of.

## 7. Hands-On: Auditing Which Daemon Actually Owns an Interface

### 7.1 Confirming daemon state

**Purpose:** Establish ground truth on which network management daemon(s) are running before making any configuration change, exactly as [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md)'s firewall audit insists on confirming the active frontend before touching rules.

```bash
systemctl is-active NetworkManager
systemctl is-active systemd-networkd
```

**Expected output:** Ideally exactly one prints `active` and the other prints `inactive` (or the unit doesn't exist at all on a minimal image that never installed it). Both printing `active` is the conflict state described in 6.

### 7.2 Confirming which daemon manages a specific interface

**Purpose:** On a host where determining daemon presence alone isn't enough — some hosts run NetworkManager but deliberately hand specific interfaces to networkd or leave them unmanaged — confirm per-interface ownership rather than assuming host-wide uniformity.

```bash
nmcli device status                   # NetworkManager's view: device, type, state
networkctl list                       # networkd's view: index, link, type, operational state
```

**Common errors:** Assuming an interface listed by one tool as `unmanaged` means no daemon is touching it — `unmanaged` in NetworkManager's output specifically means _NetworkManager_ isn't managing that device, which is entirely consistent with networkd (or nothing at all) managing it instead. Cross-check both tools' output rather than trusting either one's silence as proof of "nothing is happening here."

**Troubleshooting:** If an interface's actual state (`ip addr show`) doesn't match what either daemon believes it configured, suspect exactly the dual-management conflict in 6 — check `journalctl -u NetworkManager -u systemd-networkd` for both daemons logging activity against the same interface name in the same time window, which is the direct evidence of the conflict rather than a coincidence.

## 8. Common Misconceptions

1. **"NetworkManager is only for desktops."** It's the default well beyond desktops now, including many server installs of the same distribution families — the desktop-only association was true historically but understates its current server footprint (2, 4).
2. **"systemd-networkd is strictly a downgrade from NetworkManager."** It's narrower in scope, not worse — for a wired-only server or container-oriented host with no Wi-Fi/VPN requirement, networkd's smaller footprint and native systemd integration are a genuine advantage, not a missing feature (3).
3. **"Using netplan means you're not using NetworkManager or networkd."** Netplan is a frontend with no enforcement capability of its own — it always delegates to one of the two backends via its `renderer` setting, so "I use netplan" is never a complete answer to "which daemon manages this host's networking" (5).
4. **"Both daemons running is fine as long as neither errors out."** Neither daemon errors when both are active and unconfigured to avoid each other — the conflict manifests as flapping addresses, fought DHCP leases, and routes that silently disappear, not as a clean failure that's easy to notice (6).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between NetworkManager and systemd-networkd?"_
**Model answer:** Both are background daemons that actually apply network configuration — bringing interfaces up, assigning addresses, installing routes — as opposed to `nmcli`/`ip`/netplan, which are just tools for telling one of those daemons what to do. NetworkManager is broader in scope: it handles wired, Wi-Fi, VPN, and mobile broadband under one D-Bus-based daemon, and is the default on desktop-oriented distributions and increasingly many servers. systemd-networkd is narrower and lighter — wired/VLAN/bridge/bond and basic DHCP, configured through declarative `.network`/`.netdev`/`.link` files, no native Wi-Fi or VPN handling — and is common on minimal server and container-oriented installs where that extra scope isn't needed.
_What the interviewer is probing for:_ Understanding these as backends with genuinely different scope, not two arbitrary options with the same feature set and different syntax.

**🎯 Intermediate:** _"Where does netplan fit relative to these two daemons?"_
**Model answer:** Netplan is purely a configuration frontend — it reads a YAML file and generates the actual configuration for whichever backend its `renderer` setting names, either networkd or NetworkManager. It has no enforcement ability of its own; `netplan apply` just translates the YAML into `.network`/`.netdev` files or a NetworkManager connection profile and tells that backend to reload. So "this host uses netplan" doesn't answer which daemon is actually managing the interfaces — you still have to check the renderer setting or the daemon state directly.
_What the interviewer is probing for:_ Correctly separating the authoring layer from the enforcement layer, the same layering discipline [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) required for firewalld/ufw versus nftables/iptables.

**🎯 Senior:** _"You inherit a host where an interface's IP address keeps changing unexpectedly with no obvious cause in the application logs. What's your diagnosis path?"_
**Model answer:** Before looking anywhere else, I'd check `systemctl status NetworkManager systemd-networkd` — flapping addresses with no application-level explanation is the classic signature of both daemons being active and fighting over the same interface, each reasserting its own idea of the correct configuration. If both report active, I'd cross-reference `nmcli device status` and `networkctl list` to confirm they're both claiming the same interface, then check `journalctl -u NetworkManager -u systemd-networkd` for both logging activity against that interface name in the same window as the flapping. The fix is disabling one of the two daemons outright for that interface (or the whole host, more commonly), not trying to tune both to coexist — coexistence configuration is available on both sides but is more fragile and harder to reason about than simply picking one owner.
_What the interviewer is probing for:_ Recognizing the specific symptom-to-cause pattern for this exact conflict, and defaulting to the simpler single-owner fix rather than over-engineering a coexistence setup.

**🎯 Architect:** _"You're standardizing network configuration across a fleet that's grown organically — some hosts provisioned from different base images, some hand-configured, some migrated between distribution versions. How do you approach eliminating dual-daemon conflicts fleet-wide?"_
**Model answer:** I'd start with an audit pass across the fleet checking `systemctl is-active NetworkManager systemd-networkd` on every host, the same ground-truth-first discipline as the init-system audit in [§13](../Part2/Section-13-Part2-Init-Systems.md) and the firewall-frontend audit in [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) — never trust the base image's documented default, because organic growth and version migrations are exactly how a host ends up with both installed and enabled. Any host where both report active goes on a remediation list before anything else, since a host in that state has effectively unpredictable networking regardless of what configuration files claim it should look like. For the standardization itself, I'd pick one daemon per host _class_ rather than forcing one daemon fleet-wide — desktop/workstation-style images stay on NetworkManager for the Wi-Fi/VPN scope, minimal server and container base images standardize on systemd-networkd for the lighter footprint — and drive that choice through the provisioning pipeline (golden image build, netplan renderer setting where used) rather than leaving it to whatever a given host happened to inherit. The remediation itself, per conflicted host, means confirming the intended backend's configuration actually reproduces current behavior before disabling the other daemon, not just disabling blindly and hoping DHCP sorts it out.
_What the interviewer is probing for:_ Fleet-scale audit discipline consistent with the pattern established elsewhere in this knowledge base, and a standardization strategy that matches the tool to the host's actual requirements rather than forcing uniformity for its own sake.

## 10. Key Takeaways

- NetworkManager and systemd-networkd are backend daemons that actually apply network configuration; `nmcli`, `nmtui`, and netplan ([§52](./Section-52-Part7-Network-Configuration-Tools.md)) are frontends that tell one of those daemons what to do — never the daemon itself.
- NetworkManager is D-Bus-based and broad in scope — wired, Wi-Fi, VPN, mobile broadband under one connection-profile model — and is the default on desktop-oriented distributions and increasingly many servers too (2).
- systemd-networkd is narrower and lighter — wired/VLAN/bridge/bond and DHCP via declarative `.network`/`.netdev`/`.link` files, no native Wi-Fi/VPN — and fits minimal server and container-oriented installs well, though it ships alongside systemd rather than replacing it (3).
- Which daemon a given distro or image defaults to varies and has shifted over time — verify directly on the host in front of you rather than assuming from the distro label (4).
- Netplan is purely a frontend with no enforcement of its own — its `renderer` setting chooses networkd or NetworkManager as the actual backend, mirroring the firewalld/ufw-over-nftables layering from [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) (5).
- Running both NetworkManager and systemd-networkd active on the same interfaces is a real, commonly hit conflict — flapping addresses, fought DHCP leases, silently retracted routes — not graceful coexistence; `systemctl status NetworkManager systemd-networkd` is the fast ground-truth check, and the fix is picking one owner per interface, not tuning both to coexist (6).

## 11. Related Concepts & What's Next

This section resolves the layering [§52](./Section-52-Part7-Network-Configuration-Tools.md) left open — the actual background services that the network configuration tools covered there ultimately configure — and echoes the same frontend-versus-enforcement-layer pattern [§54](./Section-54-Part7-Firewalls-Iptables-Nftables-Firewalld-Ufw.md) established for firewalld/ufw over nftables/iptables. Both daemons are themselves systemd-managed services, so [§13](../Part2/Section-13-Part2-Init-Systems.md)'s conceptual init-system/systemd introduction (Part 2) applies directly to how they're started, supervised, and inspected; the full unit-file syntax, `systemctl` operational depth, and `journalctl` log inspection needed to administer either daemon in earnest are covered properly in Part 9 ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)), not duplicated here. This is the last section of Part 7 ([§51](./Section-51-Part7-Networking-Fundamentals-Recap.md)–[§58](./Section-58-Part7-Network-Services-Systemd-Networkd-NetworkManager.md)) — networking is now covered from ports and protocols through diagnostics, SSH, file transfer, and the services underlying interface configuration. **Part 8 (starting at [§59](../Part8/Section-59-Part8-Package-Management-Concepts.md))** moves to package management — `dpkg`/`apt` and `rpm`/`dnf` — the next layer of host administration once networking is reliably in place.

**Next Section:** [§59](../Part8/Section-59-Part8-Package-Management-Concepts.md) — `Section-59-Part8-Package-Management-Concepts.md`
