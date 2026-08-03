# Part 2 · Section 9 — Network & Edge Security: WAF, Shield, Network Firewall (Preview)

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** WAF and Shield protect your application from bad traffic before it reaches your servers — WAF filters malicious requests by content, Shield defends against being flooded offline.

**Precise:** AWS's **edge and network security services** — **AWS WAF** (HTTP/HTTPS content filtering), **AWS Shield** (DDoS protection), **AWS Network Firewall** (broader network-layer filtering) — inspect/control traffic **before** it reaches application infrastructure, complementing Sections 1–8's identity/data-layer protections.

---

## 2. Why This Category Exists

- Sections 1–8 evaluate requests that have already reached your account. This section's services act earlier, at the network edge.
- **DDoS attacks** are about volume/traffic patterns, not identity or configuration — none of Sections 1–8's tools stop this; it needs edge-scale protection.
- **Application-layer attacks** (SQLi, XSS, bad bots) exploit how an app processes requests — need content-aware HTTP inspection (WAF's job), not network firewalls or DDoS protection.

---

## 3. AWS WAF (Web Application Firewall)

### 3.1 Definition

Firewall inspecting/filtering HTTP/HTTPS requests before they reach your web application, protecting against common web exploits.

### 3.2 Attachment Points

- **CloudFront** (CDN, edge-wide).
- **Application Load Balancer (ALB)**.
- **API Gateway**.
- **AppSync** (GraphQL).
- **Cognito** user pools.

### 3.3 Rule Types and Structure

- **Web ACL** — top-level rule container, attached to a resource above.
- **Rules** — conditions with an action: **Allow, Block, or Count** (Count logs matches without blocking — validates impact before enforcing).
- **Rule groups** — AWS Managed (pre-built) or customer-defined.
- **Common AWS Managed Rule Groups:** Core rule set (CRS, OWASP Top 10-style), SQL injection set, known bad inputs set, IP reputation sets (parallels GuardDuty's threat-intel feeds, Section 8, at the edge).

### 3.4 Rate-Based Rules

- Auto-blocks/rate-limits an IP exceeding a request-count threshold within a rolling window — mitigates application-layer (L7) volumetric abuse (brute-force, scraping), distinct from Shield's network-layer DDoS domain.

### 3.5 Bot Control and CAPTCHA

- **Bot Control** — identifies/manages bot traffic (malicious and unwanted-but-benign).
- **CAPTCHA/Challenge actions** — distinguishes human/browser traffic from scripts, instead of an outright block.

---

## 4. AWS Shield — DDoS Protection

### 4.1 Definition

Managed DDoS protection service, two tiers, protecting resources from traffic floods designed to cause unavailability.

### 4.2 Shield Standard

- **Automatic, free, for every AWS customer** — protects against common L3/4 DDoS attacks (SYN floods, UDP reflection) for CloudFront, Route 53, and AWS-assigned-IP resources.
- No setup required — baseline platform protection, reflecting AWS's Shared Responsibility Model infrastructure commitment.

### 4.3 Shield Advanced

- Paid subscription adding:
  - Enhanced detection/mitigation for sophisticated attacks, including **Layer 7**.
  - **24/7 DDoS Response Team (DRT)** access (parallels §7's TAM concept, for DDoS incidents).
  - **Cost protection** — reimbursement for scaling charges incurred specifically due to a DDoS attack.
  - Advanced real-time metrics/reporting, integration with WAF.

### 4.4 Shield Advanced + WAF Together

Shield = network/transport (L3/4), extending to L7 with Advanced. WAF = application layer (L7) content inspection. Comprehensive defense layers both — complementary, not overlapping.

---

## 5. AWS Network Firewall

### 5.1 Definition

Managed network firewall for fine-grained VPC-level traffic control — stateful inspection, IPS, filtering by domain name/IP/port/protocol, deployed within your VPC.

### 5.2 vs Security Groups/NACLs (full depth Part 4)

- Security groups/NACLs: basic stateless-or-simple-stateful IP/port/protocol filtering at instance/subnet level.
- Network Firewall: deeper stateful inspection — domain-name filtering (e.g., approved outbound domain list), IPS-style signature detection — materially more sophisticated.
- Positioned at chosen VPC points (commonly a dedicated inspection subnet) — an architectural decision, full depth Part 4.

### 5.3 Network Firewall vs WAF

- WAF: HTTP/HTTPS application-layer content, tied to a specific web-facing resource.
- Network Firewall: broader network-layer traffic control across a VPC, non-HTTP traffic, domain filtering, IPS — for needs beyond security groups/NACLs, not tied to one resource.

---

## 6. Layered Edge Defense

```
Internet
  ↓
Shield (Standard/Advanced) — DDoS protection (L3/4 always-on; L7 with Advanced)
  ↓
WAF (CloudFront/ALB/API GW) — application-layer (L7) content filtering: SQLi, XSS, bots, rate-based rules
  ↓
Network Firewall — VPC-level stateful inspection, domain filtering, IPS
  ↓
Security Groups/NACLs — basic instance/subnet IP/port filtering (Part 4)
  ↓
Your Application
```

> 🔑 A genuine defense-in-depth stack at the network edge, mirroring the layered philosophy from Sections 5–8 — each layer catches what others don't; traffic must pass every layer.

---

## 7. Production & Enterprise Usage

- **WAF + CloudFront as default edge pattern** — filters at global edge locations (§2) before traffic reaches the Region; security AND cost benefit (blocked requests never consume origin compute).
- **Shield Advanced for business-critical internet-facing workloads** — justified for DRT access + cost-protection guarantee, mirroring §7's support-plan risk/cost logic.
- **WAF logging into the Section 8 detective stack** — CloudWatch/S3/Kinesis Data Firehose, Security Hub ingestion — edge security folded into the same aggregated view.
- **Network Firewall for outbound/egress control** — restrict VPC egress to approved domains, defending against exfiltration/compromised-instance callbacks; complements GuardDuty's _detection_ with _prevention_.

---

## 8. Security Considerations

- **Start Managed Rule Groups in Count mode**, not Block, before enforcing — avoids self-inflicted outages from overly broad rules.
- **Shield Standard isn't a complete DDoS answer** for high-value targets — sophisticated/L7 attacks may need Shield Advanced + WAF together.
- **Rate-based rules need per-application tuning** — no universal correct threshold.

---

## 9. Troubleshooting

| Symptom                                                      | Cause                                                                        | Fix                                                          |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Legitimate users blocked after enabling a Managed Rule Group | Set to Block without Count-mode validation                                   | Switch to Count, review matches, enable Block once confident |
| Rate-based rule blocking legitimate bursty traffic           | Threshold too low for real usage                                             | Tune based on observed traffic patterns                      |
| DDoS symptoms despite Shield Standard "always on"            | Standard covers common L3/4; may be L7 or sophisticated attack outside scope | Consider Shield Advanced + WAF rate-based/bot-control rules  |
| WAF rule not matching expected traffic                       | Rule logic/scope-down mismatch, or wrong evaluation order in Web ACL         | Review rule order and match conditions                       |

---

## 10. Best Practices & Anti-Patterns

**Best practices:** attach WAF to CloudFront for internet-facing apps; validate Managed Rule Groups in Count mode before Block; layer WAF + Shield (+ Network Firewall where warranted); justify Shield Advanced by actual business risk; feed WAF logs into the Section 8 detective stack.

**Anti-patterns:** enabling broad rule groups directly in Block mode; assuming Shield Standard alone suffices for a high-profile target; setting rate-based thresholds without reference to real traffic; treating WAF/Shield/Network Firewall as interchangeable.

---

## 11. Common Misconceptions

- "Shield Standard means I don't need to think about DDoS." → False for business-critical targets — sophisticated/L7 attacks may need Advanced + WAF.
- "WAF and Network Firewall do the same thing." → False — WAF is HTTP-specific on web-facing resources; Network Firewall is broader VPC-level, non-HTTP-inclusive.
- "Security groups already provide firewall protection, so WAF/Network Firewall are redundant." → False — SGs have no HTTP-content or domain/IPS awareness.
- "Managed Rule Groups are risk-free since AWS maintains them." → False — can still match legitimate app-specific traffic; Count-mode validation still needed.

---

## 12. Interview Questions (with model answers)

**🟢 WAF vs Shield?** WAF inspects HTTP/HTTPS request content (SQLi, bad bots), attached to CloudFront/ALB/API Gateway. Shield is DDoS protection against traffic floods — Standard automatic/free for common network-layer attacks, Advanced adds sophisticated/L7 protection + DRT access. Complementary: Shield handles flooding, WAF handles malicious content.

**🟢 Is Shield Standard something you enable?** No — automatically active for every customer at no cost, covering common L3/4 DDoS attacks. Baseline platform protection (Shared Responsibility Model). Shield Advanced is opt-in/paid for more sophisticated protection.

**🟡 Why attach WAF to CloudFront rather than the origin ALB?** Filters malicious traffic at AWS's globally distributed edge locations before it reaches the application's Region — security benefit (block early) and cost/performance benefit (blocked requests don't consume origin compute or generate unneeded transfer). Preferred pattern for internet-facing apps already on CloudFront.

**🟡 A newly-enabled Managed Rule Group starts blocking legitimate traffic — first check?** Whether it was deployed directly in Block mode instead of validated in Count mode first — the most common cause. Switch to Count, review matches for false positives, re-enable Block once confident.

**🔴 Design edge security for a public e-commerce app expecting spikes and plausible DDoS targeting?** CloudFront with WAF attached (not origin), Managed Rule Groups (core, SQLi, IP reputation) validated in Count before Block. Rate-based rules tuned to observed traffic for credential-stuffing/scraping abuse. Shield Advanced for L7 DDoS coverage, DRT access, cost-protection guarantee given business impact of downtime. WAF/Shield logs feed into Security Hub alongside other detective findings. Periodically retune thresholds around high-traffic events.

**🔴 How do WAF, Network Firewall, and security groups/NACLs form a coherent strategy?** Shield handles volumetric flooding before meaningful inspection. WAF handles HTTP/HTTPS application-layer content for web-facing resources — understands the request itself. Network Firewall operates at VPC level with deeper protocol/domain-aware inspection beyond security groups — for broader traffic control (e.g., approved outbound domains) independent of any single resource. Security groups/NACLs are the basic instance/subnet IP/port baseline, always present. Decision: HTTP-specific content → WAF; broader VPC deep/domain filtering → Network Firewall; basic access control → security groups/NACLs (always there regardless). Complementary layers, used together.

---

## 🔑 Key Takeaways

1. This section's services protect at the network edge, before traffic reaches application infrastructure — a "stop it before it gets here" layer complementing Sections 1–8.
2. WAF filters HTTP/HTTPS application-layer content on web-facing resources; Shield protects against DDoS flooding, with free always-on Standard and paid Advanced (L7, DRT, cost protection).
3. Network Firewall provides deeper, VPC-level, protocol/domain-aware traffic control beyond security groups/NACLs — distinct from WAF's HTTP-specific focus.
4. These form a genuine defense-in-depth stack (Shield → WAF → Network Firewall → security groups/NACLs), mirroring Part 2's layered philosophy.
5. Validate before enforcing (Count before Block) and justify Shield Advanced by actual business risk — the two most practically important disciplines here.

## 🌐 Related Concepts (forward links)

- Full VPC architecture, security groups, NACLs, CloudFront, Route 53, Network Firewall placement → Part 4
- WAF/Shield logging integration with CloudWatch, S3, Kinesis Data Firehose → Part 7/Part 8
- Part 2 wrap-up and comprehensive drill → §18 (final section)
