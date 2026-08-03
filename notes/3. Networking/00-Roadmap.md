# 00 — Roadmap: Networking (Complete Topic Roadmap)

## 0. Assumption Line

Networking is treated in its **DevOps / Cloud / Infrastructure Engineering** interpretation: the practical networking knowledge a systems, cloud, or platform engineer needs to design, deploy, secure, and troubleshoot infrastructure — the OSI and TCP/IP models, IP addressing and subnetting, routing and switching fundamentals, DNS, transport- and application-layer protocols, load balancing, firewalls and security groups, VPNs and tunneling, cloud-provider virtual networking (VPC/VNet), and network troubleshooting/diagnostics — through to production/enterprise network patterns. This roadmap runs **145 sections across 17 parts**, sized to the same standard of depth as this repo's other tracks (comparable to Linux's 125 and Ansible's 119 sections).

This is explicitly **not** a telecom, RF/wireless engineering, or physical-layer hardware-vendor roadmap — CCNA-adjacent switching/routing concepts are covered at the depth a cloud/DevOps engineer needs to reason about and troubleshoot infrastructure, not to the depth of a Cisco hardware certification. Cloud-provider-specific networking (VPC internals, Transit Gateway, ExpressRoute, etc.) is introduced here at the conceptual/cross-cloud level; full provider-specific deep dives live in this repo's AWS, Azure, and GCP tracks.

Because networking underpins every other infrastructure topic in this repo, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations and History

1.1 What Networking Is; Why Infrastructure Engineers Must Understand It
1.2 A Brief History: ARPANET, TCP/IP's Adoption, the Rise of the Internet
1.3 Circuit Switching vs. Packet Switching
1.4 Network Types: LAN, WAN, MAN, PAN, and the Data Center Network
1.5 Clients, Servers, Peers, and the Network Edge
1.6 Bandwidth, Throughput, Latency, and Jitter — Core Vocabulary
1.7 Prerequisites Recap and How This Roadmap Is Organized

### Part 2 — The OSI and TCP/IP Models

2.1 The OSI 7-Layer Model: Purpose and Layer-by-Layer Breakdown
2.2 The TCP/IP 4-Layer Model and How It Maps to OSI
2.3 Encapsulation and De-Encapsulation Across Layers
2.4 PDUs at Each Layer: Bits, Frames, Packets, Segments, Data
2.5 Protocol Data Flow: A Packet's Journey From Application to Wire
2.6 Layer-by-Layer Troubleshooting Mental Model
2.7 Common Protocols Mapped to Their OSI/TCP-IP Layer

### Part 3 — Addressing and Subnetting

3.1 IPv4 Address Structure: Binary, Dotted-Decimal, and Address Classes
3.2 Subnet Masks and CIDR Notation
3.3 Subnetting Fundamentals: Borrowing Bits, Calculating Ranges
3.4 VLSM (Variable-Length Subnet Masking) and Subnetting Practice Problems
3.5 Private vs. Public IP Ranges; RFC 1918
3.6 NAT and PAT: Concepts and Real-World Use
3.7 IPv6 Addressing: Structure, Notation, and Address Types
3.8 IPv6 Subnetting and Dual-Stack Coexistence
3.9 Address Resolution: ARP and NDP
3.10 DHCP: Lease Lifecycle, Relay, and Options

### Part 4 — Routing Fundamentals

4.1 What Routing Is; Routers vs. Switches vs. Hosts
4.2 Routing Tables: Structure and the Longest-Prefix-Match Rule
4.3 Static Routing: Configuration Patterns and Use Cases
4.4 Default Routes, Null Routes, and Route Summarization
4.5 Dynamic Routing Overview: IGP vs. EGP
4.6 Distance-Vector Protocols: RIP Concepts
4.7 Link-State Protocols: OSPF Concepts
4.8 Path-Vector Protocols: BGP Concepts and Why the Internet Runs on It
4.9 Route Redistribution and Administrative Distance
4.10 Policy-Based Routing and Route Metrics

### Part 5 — Switching and VLANs

5.1 What Switching Is; Hubs vs. Switches vs. Bridges
5.2 MAC Addresses and the MAC Address Table (CAM Table)
5.3 Broadcast Domains vs. Collision Domains
5.4 VLANs: Purpose, Tagging (802.1Q), and Trunking
5.5 Inter-VLAN Routing
5.6 Spanning Tree Protocol (STP): Loop Prevention Concepts
5.7 Link Aggregation (LACP/EtherChannel) Concepts
5.8 Layer 2 vs. Layer 3 Switching
5.9 Software-Defined Networking (SDN) and Overlay Networks — Conceptual Introduction

### Part 6 — DNS

6.1 DNS Fundamentals: Namespace, Hierarchy, and Purpose
6.2 DNS Record Types: A, AAAA, CNAME, MX, TXT, NS, SOA, SRV, PTR
6.3 Recursive vs. Iterative Resolution; Resolvers and Root/TLD/Authoritative Servers
6.4 DNS Caching, TTLs, and Negative Caching
6.5 Zone Files and Zone Transfers (AXFR/IXFR)
6.6 DNSSEC: Chain of Trust and Threat Model
6.7 Split-Horizon / Split-View DNS
6.8 DNS in Cloud Environments (Route 53, Azure DNS, Cloud DNS — Conceptual)
6.9 DNS-Based Load Balancing and Failover Patterns
6.10 Common DNS Troubleshooting Tools: dig, nslookup, host

### Part 7 — Transport Layer: TCP, UDP, and Sockets

7.1 Transport Layer Purpose: Connection-Oriented vs. Connectionless
7.2 TCP Three-Way Handshake and Connection Teardown (FIN/RST)
7.3 TCP Reliability: Sequence Numbers, ACKs, Retransmission
7.4 TCP Flow Control and Congestion Control (Windowing, Slow Start)
7.5 UDP: Structure, Use Cases, and Trade-Offs vs. TCP
7.6 Ports and Sockets: Well-Known, Registered, and Ephemeral Ranges
7.7 Common Port Reference (22, 80, 443, 53, 3306, 5432, 6379, etc.)
7.8 Connection States and the TCP State Machine (LISTEN, ESTABLISHED, TIME_WAIT)
7.9 QUIC and the Shift Toward UDP-Based Transport

### Part 8 — Application-Layer Protocols

8.1 HTTP/1.1 Fundamentals: Requests, Responses, Methods, Status Codes
8.2 HTTP/2 and HTTP/3: Multiplexing, Header Compression, QUIC Transport
8.3 TLS/SSL Fundamentals: Handshake, Certificates, Cipher Suites
8.4 Certificate Authorities, Chains of Trust, and Let's Encrypt/ACME
8.5 SSH: Protocol Structure, Key Exchange, and Tunneling
8.6 Email Protocols: SMTP, IMAP, POP3 — Conceptual Overview
8.7 File Transfer Protocols: FTP, SFTP, SCP
8.8 WebSockets and Persistent Connections
8.9 gRPC and Modern RPC Protocol Concepts

### Part 9 — Load Balancing

9.1 Load Balancing Fundamentals: Why and Where in the Stack
9.2 Layer 4 vs. Layer 7 Load Balancing
9.3 Load-Balancing Algorithms: Round Robin, Least Connections, Weighted, Hashing
9.4 Health Checks and Failover Behavior
9.5 SSL/TLS Termination and Passthrough Patterns
9.6 Session Persistence (Sticky Sessions) and Its Trade-Offs
9.7 Reverse Proxies vs. Load Balancers vs. API Gateways
9.8 Global Server Load Balancing (GSLB) and Anycast
9.9 Cloud Load Balancer Types (ALB/NLB, Azure LB/App Gateway, GCP LB — Conceptual)
9.10 Software Load Balancers: NGINX, HAProxy, Envoy — Conceptual Comparison

### Part 10 — Firewalls and Network Security Fundamentals

10.1 Firewall Fundamentals: Stateless vs. Stateful Filtering
10.2 Firewall Placement: Perimeter, Host-Based, and Segmentation Patterns
10.3 Security Groups vs. Network ACLs (Cloud-Agnostic Concepts)
10.4 Linux Firewalling: iptables/nftables and firewalld Concepts
10.5 Network Segmentation and Zero Trust Networking Principles
10.6 Intrusion Detection/Prevention Systems (IDS/IPS) — Conceptual Overview
10.7 DDoS Attack Types and Mitigation Strategies
10.8 Web Application Firewalls (WAF) — Conceptual Overview
10.9 Network Access Control Lists and Micro-Segmentation

### Part 11 — VPNs and Tunneling

11.1 VPN Fundamentals: Why Tunnel Traffic
11.2 IPsec: AH/ESP, Tunnel vs. Transport Mode, IKE Phases
11.3 SSL/TLS VPNs vs. IPsec VPNs
11.4 WireGuard: Design Philosophy and Key Concepts
11.5 Site-to-Site VPNs and Cloud Gateway Patterns
11.6 Client-to-Site (Remote Access) VPN Patterns
11.7 GRE and Other Tunneling Protocols
11.8 MPLS Concepts and Where It Fits in Enterprise WANs
11.9 SD-WAN — Conceptual Overview

### Part 12 — Cloud Networking (VPC/VNet Concepts)

12.1 Cloud Virtual Networking Fundamentals: VPC/VNet Concepts Across Providers
12.2 Subnets, Route Tables, and Availability Zones in Cloud Networks
12.3 Internet Gateways, NAT Gateways, and Egress Patterns
12.4 VPC/VNet Peering and Transitive Routing Limitations
12.5 Hub-and-Spoke and Transit Gateway/Hub Architectures
12.6 Private Connectivity: PrivateLink/Private Endpoints/VPC Service Controls — Conceptual
12.7 Hybrid Connectivity: Direct Connect, ExpressRoute, Cloud Interconnect — Conceptual
12.8 Cloud DNS and Service Discovery Patterns
12.9 Multi-Region and Multi-Cloud Networking Considerations
12.10 Cross-Reference: Where AWS/Azure/GCP-Specific Networking Continues in This Repo

### Part 13 — Container and Kubernetes Networking (Conceptual Bridge)

13.1 Container Networking Fundamentals: Bridge, Host, and Overlay Modes
13.2 The Kubernetes Networking Model: Pod-to-Pod, Service, and Ingress Concepts
13.3 CNI Plugins — Conceptual Overview
13.4 Service Mesh Networking Concepts (Sidecar Proxies, mTLS)
13.5 Cross-Reference: Where Kubernetes-Specific Networking Continues in This Repo

### Part 14 — Network Troubleshooting and Diagnostics

14.1 A Systematic Troubleshooting Methodology (OSI-Layer Walkthrough)
14.2 Connectivity Testing: ping, traceroute/tracert, mtr
14.3 Port and Service Testing: telnet, nc, curl for Network Diagnostics
14.4 Packet Capture Fundamentals: tcpdump Basics
14.5 Deeper Packet Analysis: Wireshark Concepts and Filters
14.6 DNS Troubleshooting Workflows
14.7 Routing and Path Troubleshooting (Asymmetric Routing, Route Leaks)
14.8 MTU Issues and Path MTU Discovery
14.9 Common Failure Scenarios and Root-Cause Case Studies

### Part 15 — Performance and Monitoring

15.1 Network Performance Metrics: Latency, Jitter, Packet Loss, Throughput
15.2 Bandwidth Testing Tools: iperf and Friends
15.3 SNMP and Network Device Monitoring Concepts
15.4 Flow Data: NetFlow/sFlow/IPFIX Concepts
15.5 Network Observability in Cloud and Modern Stacks (VPC Flow Logs, Metrics)
15.6 Capacity Planning and Baseline Establishment
15.7 Alerting on Network-Layer Signals

### Part 16 — Production, Enterprise Patterns, and Mastery

16.1 Enterprise Network Architecture Patterns (Three-Tier, Spine-Leaf)
16.2 High Availability Networking: Redundancy, Failover, HSRP/VRRP Concepts
16.3 Network Change Management and Configuration Drift
16.4 Network-as-Code: Infrastructure Tooling for Network Configuration
16.5 Common Anti-Patterns and Misconceptions
16.6 Cloud vs. On-Prem vs. Hybrid Networking Trade-Off Comparisons
16.7 Security Best Practices Recap Across the Stack
16.8 Scaling Networking for Growth: From Single VPC to Multi-Region Enterprise

### Part 17 — Interview Prep and Wrap-Up

17.1 Core Networking Interview Question Bank (Beginner to Advanced)
17.2 Scenario-Based Troubleshooting Interview Questions
17.3 Subnetting and Addressing Practice Problem Bank
17.4 System Design Questions Involving Networking (Load Balancers, CDNs, DNS)
17.5 Progressive Hands-On Labs (Home Lab, Cloud Lab, Packet-Capture Exercises)
17.6 Consolidated Key-Takeaways Checklist
17.7 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                                   | Needed For     | Introduced                                        |
| -------------------------------------------------------------- | -------------- | ------------------------------------------------- |
| Basic Linux command-line familiarity                           | Part 14 onward | Assumed baseline (see [[../2. Linux/00-Roadmap]]) |
| Binary and hexadecimal number literacy                         | Part 3         | Briefly recapped in 3.1                           |
| General IT/systems literacy (no formal CS background required) | Throughout     | Assumed baseline                                  |

No external topic must be studied before starting; this roadmap builds every networking-specific prerequisite in place, though basic Linux CLI familiarity is assumed baseline knowledge for the diagnostics tooling in Part 14.

---

## 3. Learning Phases

| Phase                                         | Parts Covered | Goal                                                        |
| --------------------------------------------- | ------------- | ----------------------------------------------------------- |
| Phase 1 — Foundations                         | Part 1, 2     | Build the OSI/TCP-IP mental model and core vocabulary       |
| Phase 2 — Addressing and Path Selection       | Part 3, 4     | Master IP addressing, subnetting, and routing fundamentals  |
| Phase 3 — Local Network and Naming            | Part 5, 6     | Understand switching/VLANs and DNS resolution               |
| Phase 4 — Transport and Application Protocols | Part 7, 8     | TCP/UDP internals and the protocols built on top of them    |
| Phase 5 — Traffic Distribution and Security   | Part 9, 10    | Load balancing and firewall/security fundamentals           |
| Phase 6 — Secure Connectivity                 | Part 11       | VPNs, tunneling, and encrypted transport patterns           |
| Phase 7 — Modern Infrastructure Networking    | Part 12, 13   | Cloud VPC/VNet concepts and container/Kubernetes networking |
| Phase 8 — Operations                          | Part 14, 15   | Troubleshooting methodology and performance monitoring      |
| Phase 9 — Production Readiness                | Part 16       | Enterprise patterns, HA, and best-practice comparisons      |
| Phase 10 — Interview and Wrap-Up              | Part 17       | Question banks, practice problems, labs, and next steps     |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `4.5`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, Kubernetes, Ansible, GIT). Section numbers (`§`) are continuous across the entire 17-part roadmap (1–124), not reset per part.

| Part                                                              | Roadmap Range | Continuous § Range | Folder             |
| ----------------------------------------------------------------- | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations and History                                  | 1.1–1.7       | §1–§7              | `Contents/Part1/`  |
| Part 2 — The OSI and TCP/IP Models                                | 2.1–2.7       | §8–§14             | `Contents/Part2/`  |
| Part 3 — Addressing and Subnetting                                | 3.1–3.10      | §15–§24            | `Contents/Part3/`  |
| Part 4 — Routing Fundamentals                                     | 4.1–4.10      | §25–§34            | `Contents/Part4/`  |
| Part 5 — Switching and VLANs                                      | 5.1–5.9       | §35–§43            | `Contents/Part5/`  |
| Part 6 — DNS                                                      | 6.1–6.10      | §44–§53            | `Contents/Part6/`  |
| Part 7 — Transport Layer: TCP, UDP, and Sockets                   | 7.1–7.9       | §54–§62            | `Contents/Part7/`  |
| Part 8 — Application-Layer Protocols                              | 8.1–8.9       | §63–§71            | `Contents/Part8/`  |
| Part 9 — Load Balancing                                           | 9.1–9.10      | §72–§81            | `Contents/Part9/`  |
| Part 10 — Firewalls and Network Security Fundamentals             | 10.1–10.9     | §82–§90            | `Contents/Part10/` |
| Part 11 — VPNs and Tunneling                                      | 11.1–11.9     | §91–§99            | `Contents/Part11/` |
| Part 12 — Cloud Networking (VPC/VNet Concepts)                    | 12.1–12.10    | §100–§109          | `Contents/Part12/` |
| Part 13 — Container and Kubernetes Networking (Conceptual Bridge) | 13.1–13.5     | §110–§114          | `Contents/Part13/` |
| Part 14 — Network Troubleshooting and Diagnostics                 | 14.1–14.9     | §115–§123          | `Contents/Part14/` |
| Part 15 — Performance and Monitoring                              | 15.1–15.7     | §124–§130          | `Contents/Part15/` |
| Part 16 — Production, Enterprise Patterns, and Mastery            | 16.1–16.8     | §131–§138          | `Contents/Part16/` |
| Part 17 — Interview Prep and Wrap-Up                              | 17.1–17.7     | §139–§145          | `Contents/Part17/` |

**Total: 145 sections across 17 parts.**

---

## 5. Cross-Topic Dependency Graph

```text
Foundations and History (P1)
        │
        ▼
The OSI and TCP/IP Models (P2)
        │
        ▼
Addressing and Subnetting (P3) ──► IPv4/IPv6, CIDR, NAT, DHCP
        │
        ▼
Routing Fundamentals (P4) ──► Static/dynamic routing, BGP/OSPF concepts
        │
        ▼
Switching and VLANs (P5)
        │
        ▼
DNS (P6)
        │
        ▼
Transport Layer: TCP, UDP, and Sockets (P7)
        │
        ▼
Application-Layer Protocols (P8) ──► HTTP/TLS/SSH
        │
        ├──► Load Balancing (P9)
        ├──► Firewalls and Network Security Fundamentals (P10)
        │
        ▼
VPNs and Tunneling (P11)
        │
        ▼
Cloud Networking: VPC/VNet Concepts (P12) ──► Bridges to AWS/Azure/GCP tracks
        │
        ▼
Container and Kubernetes Networking (P13) ──► Bridges to Kubernetes track
        │
        ▼
Network Troubleshooting and Diagnostics (P14)
        │
        ▼
Performance and Monitoring (P15)
        │
        ▼
Production, Enterprise Patterns, and Mastery (P16)
        │
        ▼
Interview Prep and Wrap-Up (P17) ──► Recommended next topics: AWS/Azure/GCP cloud networking, Kubernetes networking, Security
```

**Recommended technologies to learn alongside or after Networking:** AWS/Azure/GCP provider-specific networking deep dives (VPC internals, Transit Gateway, ExpressRoute — see [[../6. Cloud]] and the respective cloud-provider tracks), Kubernetes networking (Services, Ingress, CNI, service mesh — see [[../12. Kubernetes/00-Roadmap]]), Linux fundamentals (already covered — see [[../2. Linux/00-Roadmap]]), security topics (firewalls, zero trust, and threat modeling in greater depth), Ansible for network automation (see [[../8. Ansible/00-Roadmap]] Part 10).

---

## 6. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 7. Current Roadmap State

| #   | Part                                                              | Section    | Status         |
| --- | ----------------------------------------------------------------- | ---------- | -------------- |
| 01  | Part 1 — Foundations and History                                  | 1.1–1.7    | ⬜ Not Started |
| 02  | Part 2 — The OSI and TCP/IP Models                                | 2.1–2.7    | ⬜ Not Started |
| 03  | Part 3 — Addressing and Subnetting                                | 3.1–3.10   | ⬜ Not Started |
| 04  | Part 4 — Routing Fundamentals                                     | 4.1–4.10   | ⬜ Not Started |
| 05  | Part 5 — Switching and VLANs                                      | 5.1–5.9    | ⬜ Not Started |
| 06  | Part 6 — DNS                                                      | 6.1–6.10   | ⬜ Not Started |
| 07  | Part 7 — Transport Layer: TCP, UDP, and Sockets                   | 7.1–7.9    | ⬜ Not Started |
| 08  | Part 8 — Application-Layer Protocols                              | 8.1–8.9    | ⬜ Not Started |
| 09  | Part 9 — Load Balancing                                           | 9.1–9.10   | ⬜ Not Started |
| 10  | Part 10 — Firewalls and Network Security Fundamentals             | 10.1–10.9  | ⬜ Not Started |
| 11  | Part 11 — VPNs and Tunneling                                      | 11.1–11.9  | ⬜ Not Started |
| 12  | Part 12 — Cloud Networking (VPC/VNet Concepts)                    | 12.1–12.10 | ⬜ Not Started |
| 13  | Part 13 — Container and Kubernetes Networking (Conceptual Bridge) | 13.1–13.5  | ⬜ Not Started |
| 14  | Part 14 — Network Troubleshooting and Diagnostics                 | 14.1–14.9  | ⬜ Not Started |
| 15  | Part 15 — Performance and Monitoring                              | 15.1–15.7  | ⬜ Not Started |
| 16  | Part 16 — Production, Enterprise Patterns, and Mastery            | 16.1–16.8  | ⬜ Not Started |
| 17  | Part 17 — Interview Prep and Wrap-Up                              | 17.1–17.7  | ⬜ Not Started |

**Next Section:** Part 1 — Foundations and History (§1–§7)
